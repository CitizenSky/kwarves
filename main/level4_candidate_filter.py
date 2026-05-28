#!/usr/bin/env python3
"""Level-4 candidate vetting.

Creates the next manual/automatic filter layer for planet candidates:

1. single-transit plots
2. odd/even depth check
3. secondary-eclipse search
4. sector/time-segment consistency
5. Gaia nearby-star check
6. Gaia/ExoFOP/Simbad catalog cross-match

The default mode is non-destructive: write diagnostics, CSV, and a database
result table only. Use --apply-status to write a conservative status back to
candidates_v2/rohdaten/kstars_active.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


PROJECT_ROOT = Path("/Users/koni/astro_projects")
DB_PATH = PROJECT_ROOT / "database" / "planet_hunter.db"
LIGHTCURVE_ROOT = PROJECT_ROOT / "lightcurves"
OUT_ROOT = PROJECT_ROOT / "level4_TTV_analyse" / "level4_06_level4_filter"
EXTERNAL_CACHE = PROJECT_ROOT / "level3_externe_katalogpruefung" / "level3_00_externe_catalog_cache"

NASA_TAP_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
GAIA_TAP_URL = "https://gea.esac.esa.int/tap-server/tap/sync"
SIMBAD_TAP_URL = "https://simbad.cds.unistra.fr/simbad/sim-tap/sync"

TOI_QUERY = """
select tid,toi,ctoi_alias,tfopwg_disp,pl_orbper,pl_rade
from toi
where tid is not null
"""

PS_QUERY = """
select pl_name,hostname,tic_id,disc_facility,discoverymethod,pl_orbper,pl_rade
from ps
where tic_id is not null
"""


@dataclass(frozen=True)
class Candidate:
    tic: int
    gaia_id: str | None
    status: str
    is_fp: int
    period: float
    duration: float
    depth: float
    t0: float
    snr: float
    transit_count: int
    radius_rearth: float | None
    hz_status: str
    lightcurve_dir: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Level-4 candidate vetting.")
    parser.add_argument("--tic", type=int, default=None, help="Analyze one TIC only.")
    parser.add_argument(
        "--status",
        default=None,
        choices=["CANDIDATE", "SPC", "RECHECK", "FP_ART"],
        help="Analyze candidates with this current candidates_v2 status.",
    )
    parser.add_argument(
        "--from-folder",
        type=Path,
        default=None,
        help="Recursively extract TIC IDs from filenames in this folder and analyze those candidates.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of candidates.")
    parser.add_argument(
        "--include-fp",
        action="store_true",
        help="Also process candidates already marked FP_ART or is_fp=1.",
    )
    parser.add_argument(
        "--refresh-catalogs",
        action="store_true",
        help="Refresh NASA Exoplanet Archive cache.",
    )
    parser.add_argument(
        "--online-gaia-simbad",
        action="store_true",
        help="Query Gaia and Simbad online per candidate. Slower, but enables nearby-star checks.",
    )
    parser.add_argument(
        "--apply-status",
        action="store_true",
        help="Write conservative SPC/RECHECK/FP_ART status back to candidate tables.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing plots.")
    return parser.parse_args()


def log(message: str) -> None:
    print(message, flush=True)


def maybe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except Exception:
        return None
    return v if np.isfinite(v) else None


def extract_tics_from_folder(folder: Path) -> list[int]:
    if not folder.exists():
        raise FileNotFoundError(folder)
    tics: set[int] = set()
    pattern = re.compile(r"TIC[_ -]*(\d+)", re.IGNORECASE)
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        match = pattern.search(path.name)
        if match:
            tics.add(int(match.group(1)))
    return sorted(tics)


def load_candidates(args: argparse.Namespace) -> list[Candidate]:
    folder_tics = extract_tics_from_folder(args.from_folder) if args.from_folder else []
    sql = """
    SELECT TIC, gaia_id, COALESCE(status, 'CANDIDATE') AS status, COALESCE(is_fp, 0) AS is_fp,
           best_period, duration, depth, transit_time, COALESCE(transit_snr, 0) AS transit_snr,
           COALESCE(transit_count, 0) AS transit_count, planet_radius_earth,
           COALESCE(hz_status, 'UNKNOWN') AS hz_status, lightcurve_dir
    FROM candidates_v2
    WHERE best_period IS NOT NULL
      AND duration IS NOT NULL
      AND depth IS NOT NULL
      AND transit_time IS NOT NULL
    """
    params: list[object] = []
    if args.tic is not None:
        sql += " AND TIC = ?"
        params.append(args.tic)
    elif folder_tics:
        placeholders = ",".join("?" for _ in folder_tics)
        sql += f" AND TIC IN ({placeholders})"
        params.extend(folder_tics)
    elif args.status is not None:
        sql += " AND COALESCE(status, 'CANDIDATE') = ?"
        params.append(args.status)
    elif not args.include_fp:
        sql += " AND COALESCE(status, 'CANDIDATE') != 'FP_ART' AND COALESCE(is_fp, 0) = 0"
    sql += " ORDER BY transit_snr DESC, transit_count DESC, TIC"
    if args.limit is not None:
        sql += " LIMIT ?"
        params.append(args.limit)

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    return [
        Candidate(
            tic=int(r["TIC"]),
            gaia_id=str(r["gaia_id"]).strip() if r["gaia_id"] not in (None, "") else None,
            status=str(r["status"]),
            is_fp=int(r["is_fp"] or 0),
            period=float(r["best_period"]),
            duration=float(r["duration"]),
            depth=float(r["depth"]),
            t0=float(r["transit_time"]),
            snr=float(r["transit_snr"] or 0.0),
            transit_count=int(r["transit_count"] or 0),
            radius_rearth=maybe_float(r["planet_radius_earth"]),
            hz_status=str(r["hz_status"]),
            lightcurve_dir=r["lightcurve_dir"],
        )
        for r in rows
    ]


def lightcurve_path(candidate: Candidate) -> Path:
    if candidate.lightcurve_dir:
        path = Path(candidate.lightcurve_dir)
        if path.exists():
            return path
    return LIGHTCURVE_ROOT / f"TIC_{candidate.tic}" / f"TIC_{candidate.tic}_lightcurve.csv"


def load_lightcurve(candidate: Candidate) -> tuple[np.ndarray, np.ndarray]:
    path = lightcurve_path(candidate)
    data = np.genfromtxt(path, delimiter=",", names=True, dtype=float)
    time_arr = np.asarray(data["time"], dtype=float)
    flux_arr = np.asarray(data["flux"], dtype=float)
    mask = np.isfinite(time_arr) & np.isfinite(flux_arr)
    time_arr, flux_arr = time_arr[mask], flux_arr[mask]
    if len(time_arr) < 20:
        raise ValueError(f"too few lightcurve points: {path}")

    med = np.nanmedian(flux_arr)
    std = np.nanstd(flux_arr)
    if np.isfinite(std) and std > 0:
        keep = np.abs(flux_arr - med) < 7.0 * std
        time_arr, flux_arr = time_arr[keep], flux_arr[keep]
    med = np.nanmedian(flux_arr)
    flux_arr = flux_arr / med if np.isfinite(med) and abs(med) > 1e-8 else flux_arr - med + 1.0
    order = np.argsort(time_arr)
    return time_arr[order], flux_arr[order]


def robust_scatter(values: np.ndarray) -> float:
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return float("nan")
    med = np.nanmedian(values)
    mad = np.nanmedian(np.abs(values - med))
    if np.isfinite(mad) and mad > 0:
        return float(1.4826 * mad)
    return float(np.nanstd(values))


def phase_days(time_arr: np.ndarray, period: float, t0: float) -> np.ndarray:
    return ((time_arr - t0 + period / 2.0) % period) - period / 2.0


def expected_epochs(time_arr: np.ndarray, candidate: Candidate) -> list[tuple[int, float]]:
    first = int(math.ceil((float(np.nanmin(time_arr)) - candidate.t0) / candidate.period)) - 1
    last = int(math.floor((float(np.nanmax(time_arr)) - candidate.t0) / candidate.period)) + 1
    epochs: list[tuple[int, float]] = []
    for epoch in range(first, last + 1):
        expected = candidate.t0 + epoch * candidate.period
        if np.nanmin(time_arr) <= expected <= np.nanmax(time_arr):
            epochs.append((epoch, expected))
    return epochs


def measure_depth_at(
    time_arr: np.ndarray,
    flux_arr: np.ndarray,
    center: float,
    duration: float,
    local_scale: float = 4.0,
) -> dict[str, float | int]:
    half = duration / 2.0
    local = np.abs(time_arr - center) <= max(local_scale * duration, 0.12)
    if int(np.count_nonzero(local)) < 8:
        return {"depth": float("nan"), "snr": float("nan"), "scatter": float("nan"), "n_in": 0, "n_out": 0}
    dt = time_arr[local] - center
    fl = flux_arr[local]
    inside = np.abs(dt) <= half
    outside = (np.abs(dt) >= 1.5 * half) & (np.abs(dt) <= max(local_scale * duration, 0.12))
    n_in = int(np.count_nonzero(inside))
    n_out = int(np.count_nonzero(outside))
    if n_in < 3 or n_out < 5:
        return {"depth": float("nan"), "snr": float("nan"), "scatter": float("nan"), "n_in": n_in, "n_out": n_out}
    base = float(np.nanmedian(fl[outside]))
    depth = max(0.0, base - float(np.nanmedian(fl[inside])))
    scatter = robust_scatter((fl[outside] - base) * 1000.0)
    snr = depth * 1000.0 / scatter * math.sqrt(n_in) if scatter > 0 else float("nan")
    return {"depth": depth, "snr": snr, "scatter": scatter, "n_in": n_in, "n_out": n_out}


def check_single_transits(
    candidate: Candidate,
    time_arr: np.ndarray,
    flux_arr: np.ndarray,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    for epoch, expected in expected_epochs(time_arr, candidate):
        m = measure_depth_at(time_arr, flux_arr, expected, candidate.duration)
        rows.append(
            {
                "epoch": epoch,
                "expected_time": expected,
                "depth_ppt": float(m["depth"]) * 1000.0 if np.isfinite(m["depth"]) else float("nan"),
                "local_snr": m["snr"],
                "n_in": m["n_in"],
                "n_out": m["n_out"],
                "visible": bool(np.isfinite(m["snr"]) and float(m["snr"]) >= 2.0 and float(m["depth"]) > 0),
            }
        )
    visible = [r for r in rows if r["visible"]]
    return (
        {
            "expected_transits": len(rows),
            "visible_transits": len(visible),
            "median_single_snr": float(np.nanmedian([r["local_snr"] for r in rows])) if rows else float("nan"),
            "single_transit_ok": len(visible) >= max(2, min(3, candidate.transit_count)),
        },
        rows,
    )


def check_odd_even(candidate: Candidate, time_arr: np.ndarray, flux_arr: np.ndarray) -> dict[str, Any]:
    ph = phase_days(time_arr, candidate.period, candidate.t0)
    transit_n = np.floor((time_arr - candidate.t0) / candidate.period).astype(int)
    inside = np.abs(ph) <= candidate.duration / 2.0
    outside = np.abs(ph) >= 2.0 * candidate.duration
    base = float(np.nanmedian(flux_arr[outside])) if np.count_nonzero(outside) >= 10 else 1.0
    odd = inside & (transit_n % 2 == 1)
    even = inside & (transit_n % 2 == 0)
    if np.count_nonzero(odd) < 4 or np.count_nonzero(even) < 4:
        return {"odd_depth_ppt": float("nan"), "even_depth_ppt": float("nan"), "odd_even_ratio": float("nan"), "odd_even_flag": False}
    odd_depth = max(0.0, base - float(np.nanmedian(flux_arr[odd])))
    even_depth = max(0.0, base - float(np.nanmedian(flux_arr[even])))
    ratio = odd_depth / even_depth if even_depth > 1e-8 else float("nan")
    flag = bool(np.isfinite(ratio) and (ratio < 0.5 or ratio > 2.0))
    return {
        "odd_depth_ppt": odd_depth * 1000.0,
        "even_depth_ppt": even_depth * 1000.0,
        "odd_even_ratio": ratio,
        "odd_even_flag": flag,
    }


def check_secondary(candidate: Candidate, time_arr: np.ndarray, flux_arr: np.ndarray) -> dict[str, Any]:
    primary = measure_depth_at(time_arr, flux_arr, candidate.t0, candidate.duration, local_scale=8.0)
    primary_depth = float(primary["depth"]) if np.isfinite(primary["depth"]) and primary["depth"] > 0 else candidate.depth
    sec_center = candidate.t0 + candidate.period / 2.0
    sec = measure_depth_at(time_arr, flux_arr, sec_center, candidate.duration, local_scale=8.0)
    sec_depth = float(sec["depth"]) if np.isfinite(sec["depth"]) else float("nan")
    sec_ratio = sec_depth / primary_depth if primary_depth > 0 and np.isfinite(sec_depth) else float("nan")

    ph = phase_days(time_arr, candidate.period, candidate.t0)
    phase_grid = np.linspace(0.15, 0.85, 57)
    best_phase = float("nan")
    best_depth = -np.inf
    for phase in phase_grid:
        center = candidate.t0 + phase * candidate.period
        folded_center = ph - phase * candidate.period
        folded_center = ((folded_center + candidate.period / 2.0) % candidate.period) - candidate.period / 2.0
        inside = np.abs(folded_center) <= candidate.duration / 2.0
        outside = np.abs(folded_center) >= 2.0 * candidate.duration
        if np.count_nonzero(inside) < 4 or np.count_nonzero(outside) < 10:
            continue
        base = float(np.nanmedian(flux_arr[outside]))
        depth = max(0.0, base - float(np.nanmedian(flux_arr[inside])))
        if depth > best_depth:
            best_depth = depth
            best_phase = float(phase)
    best_ratio = best_depth / primary_depth if primary_depth > 0 and np.isfinite(best_depth) else float("nan")
    flag = bool((np.isfinite(sec_ratio) and sec_ratio > 0.5) or (np.isfinite(best_ratio) and best_ratio > 0.65))
    return {
        "secondary_depth_ppt": sec_depth * 1000.0 if np.isfinite(sec_depth) else float("nan"),
        "secondary_ratio": sec_ratio,
        "max_secondary_phase": best_phase,
        "max_secondary_ratio": best_ratio,
        "secondary_flag": flag,
    }


def infer_segments(time_arr: np.ndarray, gap_days: float = 5.0) -> list[np.ndarray]:
    gaps = np.where(np.diff(time_arr) > gap_days)[0]
    starts = [0] + [int(i + 1) for i in gaps]
    ends = [int(i + 1) for i in gaps] + [len(time_arr)]
    return [np.arange(s, e) for s, e in zip(starts, ends) if e - s >= 20]


def check_segments(
    candidate: Candidate,
    time_arr: np.ndarray,
    flux_arr: np.ndarray,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    for idx, segment_idx in enumerate(infer_segments(time_arr), start=1):
        t = time_arr[segment_idx]
        f = flux_arr[segment_idx]
        transit_rows = []
        for epoch, expected in expected_epochs(t, candidate):
            transit_rows.append(measure_depth_at(t, f, expected, candidate.duration))
        snrs = [float(r["snr"]) for r in transit_rows if np.isfinite(r["snr"])]
        depths = [float(r["depth"]) * 1000.0 for r in transit_rows if np.isfinite(r["depth"])]
        rows.append(
            {
                "segment": idx,
                "time_start": float(np.nanmin(t)),
                "time_end": float(np.nanmax(t)),
                "n_points": int(len(t)),
                "n_expected": len(transit_rows),
                "n_visible": int(sum(1 for s in snrs if s >= 2.0)),
                "median_snr": float(np.nanmedian(snrs)) if snrs else float("nan"),
                "median_depth_ppt": float(np.nanmedian(depths)) if depths else float("nan"),
            }
        )
    segments_with_transits = [r for r in rows if int(r["n_expected"]) > 0]
    visible_segments = [r for r in segments_with_transits if int(r["n_visible"]) > 0]
    ok = len(visible_segments) >= 1 and (
        len(segments_with_transits) <= 1 or len(visible_segments) / len(segments_with_transits) >= 0.5
    )
    return (
        {
            "segments_total": len(rows),
            "segments_with_expected_transit": len(segments_with_transits),
            "segments_with_visible_transit": len(visible_segments),
            "sector_consistency_ok": ok,
        },
        rows,
    )


def read_tap_csv(url: str, query: str, timeout: int = 90) -> pd.DataFrame:
    data = urllib.parse.urlencode(
        {
            "REQUEST": "doQuery",
            "LANG": "ADQL",
            "QUERY": query.strip(),
            "FORMAT": "csv",
        }
    ).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        text = response.read().decode("utf-8", errors="replace")
    return pd.read_csv(io.StringIO(text))


def run_nasa_query(query: str, cache_path: Path, refresh: bool) -> pd.DataFrame:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_path.exists() and not refresh:
        return pd.read_csv(cache_path)
    df = read_tap_csv(NASA_TAP_URL, query, timeout=120)
    df.to_csv(cache_path, index=False)
    return df


def tic_from_ps(value: object) -> int | None:
    if pd.isna(value):
        return None
    text = str(value).replace("TIC", "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def load_external_catalogs(refresh: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    toi = run_nasa_query(TOI_QUERY, EXTERNAL_CACHE / "nasa_exoplanet_archive_toi.csv", refresh)
    ps = run_nasa_query(PS_QUERY, EXTERNAL_CACHE / "nasa_exoplanet_archive_confirmed_planets.csv", refresh)
    toi["TIC"] = pd.to_numeric(toi["tid"], errors="coerce").astype("Int64")
    ps["TIC"] = ps["tic_id"].map(tic_from_ps).astype("Int64")
    return toi, ps


def catalog_check(candidate: Candidate, toi: pd.DataFrame, ps: pd.DataFrame) -> dict[str, Any]:
    toi_hits = toi[toi["TIC"] == candidate.tic]
    ps_hits = ps[ps["TIC"] == candidate.tic]
    dispositions = sorted({str(x).strip().upper() for x in toi_hits.get("tfopwg_disp", []) if str(x).strip()})
    confirmed = len(ps_hits)
    toi_count = len(toi_hits)
    exofop_fp = any(x in {"FP", "FA"} for x in dispositions)
    exofop_pc = any(x in {"PC", "APC", "CP", "KP"} for x in dispositions)
    group = "NO_EXTERNAL_MATCH"
    if confirmed:
        group = "KNOWN_PLANET"
    elif exofop_fp:
        group = "EXOFOP_FALSE_POSITIVE"
    elif exofop_pc:
        group = "EXOFOP_PLANET_CANDIDATE"
    elif toi_count:
        group = "EXOFOP_OTHER_MATCH"
    return {
        "exofop_toi_count": toi_count,
        "exofop_dispositions": ";".join(dispositions),
        "confirmed_planet_count": confirmed,
        "external_catalog_group": group,
        "external_fp_flag": bool(exofop_fp),
    }


def gaia_nearby_check(candidate: Candidate, online: bool) -> dict[str, Any]:
    if not online:
        return {"gaia_status": "SKIPPED_OFFLINE", "nearby_star_count": "", "nearby_bright_count": "", "nearby_star_flag": False}
    if not candidate.gaia_id or not candidate.gaia_id.isdigit():
        return {"gaia_status": "NO_GAIA_ID", "nearby_star_count": "", "nearby_bright_count": "", "nearby_star_flag": False}
    try:
        source_id = int(candidate.gaia_id)
        source_query = f"""
        SELECT source_id, ra, dec, phot_g_mean_mag
        FROM gaiadr3.gaia_source
        WHERE source_id = {source_id}
        """
        source = read_tap_csv(GAIA_TAP_URL, source_query, timeout=60)
        if source.empty:
            return {"gaia_status": "GAIA_SOURCE_NOT_FOUND", "nearby_star_count": 0, "nearby_bright_count": 0, "nearby_star_flag": False}
        ra = float(source.iloc[0]["ra"])
        dec = float(source.iloc[0]["dec"])
        gmag = maybe_float(source.iloc[0].get("phot_g_mean_mag"))
        cone_query = f"""
        SELECT source_id, ra, dec, phot_g_mean_mag,
               DISTANCE(POINT('ICRS', ra, dec), POINT('ICRS', {ra}, {dec})) * 3600.0 AS sep_arcsec
        FROM gaiadr3.gaia_source
        WHERE 1 = CONTAINS(
          POINT('ICRS', ra, dec),
          CIRCLE('ICRS', {ra}, {dec}, {60.0 / 3600.0})
        )
        AND source_id <> {source_id}
        """
        nearby = read_tap_csv(GAIA_TAP_URL, cone_query, timeout=90)
        bright_count = 0
        if gmag is not None and "phot_g_mean_mag" in nearby:
            mags = pd.to_numeric(nearby["phot_g_mean_mag"], errors="coerce")
            bright_count = int(((mags - gmag) <= 5.0).sum())
        flag = bool(len(nearby) > 0 and bright_count > 0)
        return {
            "gaia_status": "OK",
            "nearby_star_count": int(len(nearby)),
            "nearby_bright_count": bright_count,
            "nearby_star_flag": flag,
        }
    except Exception as exc:
        return {
            "gaia_status": f"ERROR:{type(exc).__name__}",
            "nearby_star_count": "",
            "nearby_bright_count": "",
            "nearby_star_flag": False,
        }


def simbad_check(candidate: Candidate, online: bool) -> dict[str, Any]:
    if not online:
        return {"simbad_status": "SKIPPED_OFFLINE", "simbad_main_id": "", "simbad_otype": "", "simbad_fp_flag": False}
    if not candidate.gaia_id or not candidate.gaia_id.isdigit():
        return {"simbad_status": "NO_GAIA_ID", "simbad_main_id": "", "simbad_otype": "", "simbad_fp_flag": False}
    ident = f"Gaia DR3 {candidate.gaia_id}"
    safe_ident = ident.replace("'", "''")
    query = f"""
    SELECT basic.main_id, basic.otype
    FROM basic
    JOIN ident ON basic.oid = ident.oidref
    WHERE ident.id = '{safe_ident}'
    """
    try:
        df = read_tap_csv(SIMBAD_TAP_URL, query, timeout=60)
        if df.empty:
            return {"simbad_status": "NO_MATCH", "simbad_main_id": "", "simbad_otype": "", "simbad_fp_flag": False}
        otype = str(df.iloc[0].get("otype", "")).strip()
        main_id = str(df.iloc[0].get("main_id", "")).strip()
        fp_like = any(token in otype.upper() for token in ["EB", "ECL", "BIN", "VAR"])
        return {"simbad_status": "OK", "simbad_main_id": main_id, "simbad_otype": otype, "simbad_fp_flag": fp_like}
    except Exception as exc:
        return {"simbad_status": f"ERROR:{type(exc).__name__}", "simbad_main_id": "", "simbad_otype": "", "simbad_fp_flag": False}


def safe_float(value: Any) -> float:
    try:
        v = float(value)
    except Exception:
        return float("nan")
    return v if np.isfinite(v) else float("nan")


def classify_level4(row: dict[str, Any]) -> tuple[str, str, float]:
    reasons: list[str] = []
    score = 100.0
    if not row.get("single_transit_ok"):
        score -= 30
        reasons.append("single_transits_weak")
    if row.get("odd_even_flag"):
        score -= 25
        reasons.append("odd_even")
    if row.get("secondary_flag"):
        score -= 35
        reasons.append("secondary")
    if not row.get("sector_consistency_ok"):
        score -= 20
        reasons.append("sector_inconsistent")
    if row.get("nearby_star_flag"):
        score -= 15
        reasons.append("nearby_star")
    if row.get("external_fp_flag") or row.get("simbad_fp_flag"):
        score -= 50
        reasons.append("external_fp")

    if score < 35 or row.get("external_fp_flag") or (row.get("secondary_flag") and row.get("odd_even_flag")):
        label = "FP_ART"
    elif score < 75 or reasons:
        label = "RECHECK"
    else:
        label = "SPC"
    return label, ";".join(reasons) if reasons else "ok", round(score, 3)


def write_transit_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["epoch", "expected_time", "depth_ppt", "local_snr", "n_in", "n_out", "visible"]
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_segment_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["segment", "time_start", "time_end", "n_points", "n_expected", "n_visible", "median_snr", "median_depth_ppt"]
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def plot_single_transits(path: Path, candidate: Candidate, time_arr: np.ndarray, flux_arr: np.ndarray, transit_rows: list[dict[str, Any]]) -> None:
    n = min(len(transit_rows), 24)
    cols = 4
    rows = max(1, math.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 3.2, rows * 2.3), dpi=140, squeeze=False)
    half_window = max(3.0 * candidate.duration, 0.12)
    for ax in axes.ravel():
        ax.set_axis_off()
    for ax, tr in zip(axes.ravel(), transit_rows[:n]):
        center = float(tr["expected_time"])
        mask = np.abs(time_arr - center) <= half_window
        ax.set_axis_on()
        ax.scatter((time_arr[mask] - center) * 24.0, (flux_arr[mask] - 1.0) * 1000.0, s=5, alpha=0.55)
        ax.axvspan(-candidate.duration * 12.0, candidate.duration * 12.0, color="tab:red", alpha=0.12)
        ax.axhline(0, color="0.4", linewidth=0.7)
        ax.set_title(f"E{tr['epoch']} SNR={safe_float(tr['local_snr']):.1f}", fontsize=8)
        ax.grid(alpha=0.2)
    fig.suptitle(f"TIC {candidate.tic} Einzeltransits | P={candidate.period:.5f} d", fontsize=12)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_phase_diagnostics(path: Path, candidate: Candidate, time_arr: np.ndarray, flux_arr: np.ndarray) -> None:
    ph = phase_days(time_arr, candidate.period, candidate.t0)
    fig, axes = plt.subplots(2, 1, figsize=(9, 7), dpi=140)
    axes[0].scatter(ph * 24.0, (flux_arr - 1.0) * 1000.0, s=3, alpha=0.3)
    axes[0].axvspan(-candidate.duration * 12.0, candidate.duration * 12.0, color="tab:red", alpha=0.12)
    axes[0].set_xlim(-min(candidate.period * 12.0, 48.0), min(candidate.period * 12.0, 48.0))
    axes[0].set_ylabel("Flux-1 [ppt]")
    axes[0].set_title("Primary folded transit")
    sec_phase = phase_days(time_arr, candidate.period, candidate.t0 + candidate.period / 2.0)
    axes[1].scatter(sec_phase * 24.0, (flux_arr - 1.0) * 1000.0, s=3, alpha=0.3, color="tab:purple")
    axes[1].axvspan(-candidate.duration * 12.0, candidate.duration * 12.0, color="tab:purple", alpha=0.12)
    axes[1].set_xlim(-min(candidate.period * 12.0, 48.0), min(candidate.period * 12.0, 48.0))
    axes[1].set_xlabel("Phase around event [hours]")
    axes[1].set_ylabel("Flux-1 [ppt]")
    axes[1].set_title("Secondary phase 0.5")
    for ax in axes:
        ax.grid(alpha=0.22)
    fig.suptitle(f"TIC {candidate.tic} Odd/Even + Secondary diagnostic")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def ensure_results_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS level4_filter_results (
            TIC INTEGER PRIMARY KEY,
            level4_label TEXT,
            level4_score REAL,
            level4_reasons TEXT,
            result_json TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def save_result_to_db(conn: sqlite3.Connection, candidate: Candidate, row: dict[str, Any], apply_status: bool) -> None:
    ensure_results_table(conn)
    conn.execute(
        """
        INSERT INTO level4_filter_results (TIC, level4_label, level4_score, level4_reasons, result_json, updated_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(TIC) DO UPDATE SET
            level4_label=excluded.level4_label,
            level4_score=excluded.level4_score,
            level4_reasons=excluded.level4_reasons,
            result_json=excluded.result_json,
            updated_at=datetime('now')
        """,
        (
            candidate.tic,
            row["level4_label"],
            row["level4_score"],
            row["level4_reasons"],
            json.dumps(row, ensure_ascii=True, default=str),
        ),
    )
    if apply_status:
        status = str(row["level4_label"])
        is_fp = 1 if status == "FP_ART" else candidate.is_fp
        conn.execute("UPDATE candidates_v2 SET status=?, is_fp=? WHERE TIC=?", (status, is_fp, candidate.tic))
        conn.execute("UPDATE rohdaten SET status=?, checked_at=datetime('now') WHERE TIC=?", (status, candidate.tic))
        conn.execute("UPDATE kstars_active SET status=?, checked_at=datetime('now') WHERE TIC=?", (status, candidate.tic))
    conn.commit()


def analyze_candidate(
    candidate: Candidate,
    toi: pd.DataFrame,
    ps: pd.DataFrame,
    args: argparse.Namespace,
) -> dict[str, Any]:
    out_dir = OUT_ROOT / f"TIC_{candidate.tic}"
    out_dir.mkdir(parents=True, exist_ok=True)
    time_arr, flux_arr = load_lightcurve(candidate)

    single_metrics, transit_rows = check_single_transits(candidate, time_arr, flux_arr)
    odd_even = check_odd_even(candidate, time_arr, flux_arr)
    secondary = check_secondary(candidate, time_arr, flux_arr)
    segment_metrics, segment_rows = check_segments(candidate, time_arr, flux_arr)
    catalogs = catalog_check(candidate, toi, ps)
    gaia = gaia_nearby_check(candidate, args.online_gaia_simbad)
    simbad = simbad_check(candidate, args.online_gaia_simbad)

    transit_csv = out_dir / f"TIC_{candidate.tic}_single_transits.csv"
    segment_csv = out_dir / f"TIC_{candidate.tic}_sector_segments.csv"
    single_plot = out_dir / f"TIC_{candidate.tic}_single_transits.png"
    phase_plot = out_dir / f"TIC_{candidate.tic}_phase_secondary.png"
    write_transit_csv(transit_csv, transit_rows)
    write_segment_csv(segment_csv, segment_rows)
    if args.overwrite or not single_plot.exists():
        plot_single_transits(single_plot, candidate, time_arr, flux_arr, transit_rows)
    if args.overwrite or not phase_plot.exists():
        plot_phase_diagnostics(phase_plot, candidate, time_arr, flux_arr)

    row: dict[str, Any] = {
        "TIC": candidate.tic,
        "gaia_id": candidate.gaia_id or "",
        "candidate_status": candidate.status,
        "period": candidate.period,
        "duration": candidate.duration,
        "depth": candidate.depth,
        "transit_snr": candidate.snr,
        "transit_count": candidate.transit_count,
        "planet_radius_earth": candidate.radius_rearth,
        "hz_status": candidate.hz_status,
        "single_transit_plot": str(single_plot),
        "phase_secondary_plot": str(phase_plot),
        "single_transit_csv": str(transit_csv),
        "sector_csv": str(segment_csv),
        **single_metrics,
        **odd_even,
        **secondary,
        **segment_metrics,
        **gaia,
        **catalogs,
        **simbad,
    }
    label, reasons, score = classify_level4(row)
    row["level4_label"] = label
    row["level4_reasons"] = reasons
    row["level4_score"] = score
    return row


def write_summary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "TIC",
        "level4_label",
        "level4_score",
        "level4_reasons",
        "candidate_status",
        "period",
        "duration",
        "depth",
        "transit_snr",
        "transit_count",
        "planet_radius_earth",
        "hz_status",
        "expected_transits",
        "visible_transits",
        "median_single_snr",
        "single_transit_ok",
        "odd_depth_ppt",
        "even_depth_ppt",
        "odd_even_ratio",
        "odd_even_flag",
        "secondary_depth_ppt",
        "secondary_ratio",
        "max_secondary_phase",
        "max_secondary_ratio",
        "secondary_flag",
        "segments_total",
        "segments_with_expected_transit",
        "segments_with_visible_transit",
        "sector_consistency_ok",
        "gaia_status",
        "nearby_star_count",
        "nearby_bright_count",
        "nearby_star_flag",
        "external_catalog_group",
        "exofop_toi_count",
        "exofop_dispositions",
        "confirmed_planet_count",
        "external_fp_flag",
        "simbad_status",
        "simbad_main_id",
        "simbad_otype",
        "simbad_fp_flag",
        "single_transit_plot",
        "phase_secondary_plot",
        "single_transit_csv",
        "sector_csv",
    ]
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_readme() -> None:
    (OUT_ROOT / "README.md").write_text(
        "# Level 4 Candidate Filter\n\n"
        "Dieser Lauf erzeugt die naechste Filterstufe fuer Kandidaten.\n\n"
        "Checks:\n"
        "1. Einzeltransits als Plot und CSV.\n"
        "2. Odd/Even-Tiefenvergleich.\n"
        "3. Sekundaere Eclipse bei Phase 0.5 und Scan ueber Nebenphasen.\n"
        "4. Sektorweise beziehungsweise zeitsegmentweise Konsistenz.\n"
        "5. Gaia-Nearby-Star-Check, wenn `--online-gaia-simbad` gesetzt ist.\n"
        "6. Gaia/ExoFOP/Simbad-Abgleich: ExoFOP/NASA aus Cache, Gaia/Simbad optional online.\n\n"
        "Labels:\n"
        "- `SPC`: stabiler Planetenkandidat fuer die naechste Stufe.\n"
        "- `RECHECK`: auffaellig oder unvollstaendig, manuell erneut pruefen.\n"
        "- `FP_ART`: False-Positive/Systematik-Verdacht.\n\n"
        "Ohne `--apply-status` werden keine Kandidatenstatus geaendert.\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    write_readme()
    log("Lade Kandidaten ...")
    candidates = load_candidates(args)
    log(f"Kandidaten: {len(candidates)}")
    log("Lade ExoFOP/NASA-Katalogcache ...")
    toi, ps = load_external_catalogs(args.refresh_catalogs)

    conn = sqlite3.connect(DB_PATH)
    rows: list[dict[str, Any]] = []
    try:
        for idx, candidate in enumerate(candidates, start=1):
            try:
                row = analyze_candidate(candidate, toi, ps, args)
                save_result_to_db(conn, candidate, row, args.apply_status)
                rows.append(row)
                log(f"{idx}/{len(candidates)} TIC {candidate.tic}: {row['level4_label']} score={row['level4_score']} {row['level4_reasons']}")
            except Exception as exc:
                row = {
                    "TIC": candidate.tic,
                    "candidate_status": candidate.status,
                    "level4_label": "RECHECK",
                    "level4_score": -999.0,
                    "level4_reasons": f"{type(exc).__name__}: {exc}",
                }
                save_result_to_db(conn, candidate, row, False)
                rows.append(row)
                log(f"{idx}/{len(candidates)} TIC {candidate.tic}: ERROR {type(exc).__name__}: {exc}")
    finally:
        conn.close()

    rows.sort(key=lambda r: (str(r.get("level4_label")), -safe_float(r.get("level4_score")), int(r.get("TIC", 0))))
    out_csv = OUT_ROOT / "level4_filter_results.csv"
    write_summary_csv(out_csv, rows)
    counts: dict[str, int] = {}
    for row in rows:
        label = str(row.get("level4_label", "UNKNOWN"))
        counts[label] = counts.get(label, 0) + 1
    log(f"Fertig: {out_csv}")
    log(str(counts))
    if args.apply_status:
        log("Status wurde in candidates_v2, rohdaten und kstars_active geschrieben.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
