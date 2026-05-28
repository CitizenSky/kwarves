#!/usr/bin/env python3
"""Run local Level-5 checks for green/purple A-priority HZ candidates."""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sqlite3
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "database" / "planet_hunter.db"
PRIORITY_CSV = (
    PROJECT_ROOT
    / "level1_rohkandidaten"
    / "level1_visuelle_pruefung"
    / "level1_05_GRUEN_VIOLETT_SPC_HZ"
    / "05_GRUEN_VIOLETT_SPC_HZ_priority.csv"
)
LEVEL5_ROOT = PROJECT_ROOT / "level5_detailvalidierung"
SINGLE_ROOT = LEVEL5_ROOT / "level5_02_einzeltransit_plots"
ODD_EVEN_ROOT = LEVEL5_ROOT / "level5_03_odd_even_test"
SECONDARY_ROOT = LEVEL5_ROOT / "level5_04_secondary_check"
NEIGHBOR_ROOT = LEVEL5_ROOT / "level5_05_nachbarstern_check"
SUMMARY_ROOT = LEVEL5_ROOT / "level5_06_bestanden"
LOCAL_GAIA_SUMMARY = (
    PROJECT_ROOT
    / "level4_TTV_analyse"
    / "level4_18_HZ"
    / "additional_data"
    / "gaia_nearby_summary.csv"
)
LOCAL_GAIA_DIR = (
    PROJECT_ROOT
    / "level4_TTV_analyse"
    / "level4_18_HZ"
    / "additional_data"
    / "gaia_nearby"
)
GAIA_TAP_URL = "https://gea.esac.esa.int/tap-server/tap/sync"


@dataclass
class Candidate:
    rank: int
    tic: int
    gaia_id: str
    status: str
    hz_status: str
    period: float
    duration: float
    depth: float
    t0: float
    radius_rearth: float
    transit_snr: float
    transit_count: int
    visible_transits: int
    clean_sector_count: int
    sector_count: int
    distance_ly: float
    lightcurve_path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Level-5 checks for A_LEVEL5_NOW green/purple HZ candidates.")
    parser.add_argument("--group", default="A_LEVEL5_NOW", help="Priority group from the green/purple review CSV.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--online-gaia-missing", action="store_true", help="Query Gaia TAP when no local nearby file exists.")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def safe_float(value: Any, default: float = float("nan")) -> float:
    try:
        if value in (None, ""):
            return default
        out = float(value)
        return out if np.isfinite(out) else default
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def clean_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: clean_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean_json(v) for v in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        value = float(value)
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def robust_sigma(values: np.ndarray) -> float:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if len(finite) == 0:
        return float("nan")
    med = float(np.nanmedian(finite))
    mad = float(np.nanmedian(np.abs(finite - med)))
    if np.isfinite(mad) and mad > 0:
        return 1.4826 * mad
    return float(np.nanstd(finite))


def phase_days(time: np.ndarray, period: float, t0: float) -> np.ndarray:
    return ((time - t0 + 0.5 * period) % period) - 0.5 * period


def load_priority_rows(group: str, limit: int | None) -> list[dict[str, str]]:
    with PRIORITY_CSV.open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("priority_group") == group]
    rows.sort(key=lambda row: safe_int(row.get("rank"), 9999))
    return rows[:limit] if limit else rows


def load_candidates(priority_rows: list[dict[str, str]]) -> list[Candidate]:
    tics = [safe_int(row["TIC"]) for row in priority_rows]
    rank_by_tic = {safe_int(row["TIC"]): safe_int(row["rank"]) for row in priority_rows}
    distance_by_tic = {safe_int(row["TIC"]): safe_float(row.get("distance_ly")) for row in priority_rows}
    if not tics:
        return []
    placeholders = ",".join("?" for _ in tics)
    query = f"""
        SELECT TIC, gaia_id, status, spc_class, hz_status, best_period, duration, depth,
               transit_time, planet_radius_earth, transit_snr, transit_count,
               visible_transits, clean_sector_count, sector_count, distance_ly,
               lightcurve_dir
          FROM candidates_v2
         WHERE TIC IN ({placeholders})
    """
    candidates: list[Candidate] = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute(query, tuple(tics)):
            tic = int(row["TIC"])
            lightcurve = Path(str(row["lightcurve_dir"] or ""))
            distance = safe_float(row["distance_ly"], distance_by_tic.get(tic, float("nan")))
            candidates.append(
                Candidate(
                    rank=rank_by_tic[tic],
                    tic=tic,
                    gaia_id=str(row["gaia_id"] or ""),
                    status=str(row["status"] or row["spc_class"] or ""),
                    hz_status=str(row["hz_status"] or ""),
                    period=safe_float(row["best_period"]),
                    duration=safe_float(row["duration"], 0.195),
                    depth=safe_float(row["depth"], 0.0),
                    t0=safe_float(row["transit_time"]),
                    radius_rearth=safe_float(row["planet_radius_earth"]),
                    transit_snr=safe_float(row["transit_snr"]),
                    transit_count=safe_int(row["transit_count"]),
                    visible_transits=safe_int(row["visible_transits"]),
                    clean_sector_count=safe_int(row["clean_sector_count"]),
                    sector_count=safe_int(row["sector_count"]),
                    distance_ly=distance,
                    lightcurve_path=lightcurve,
                )
            )
    candidates.sort(key=lambda c: c.rank)
    return candidates


def load_lightcurve(path: Path) -> tuple[np.ndarray, np.ndarray]:
    arr = np.loadtxt(path, delimiter=",", skiprows=1, usecols=(0, 1), ndmin=2)
    time = arr[:, 0].astype(float)
    flux = arr[:, 1].astype(float)
    mask = np.isfinite(time) & np.isfinite(flux)
    time = time[mask]
    flux = flux[mask]
    order = np.argsort(time)
    return time[order], flux[order]


def expected_epochs(time: np.ndarray, candidate: Candidate) -> list[tuple[int, float]]:
    if len(time) == 0 or not np.isfinite(candidate.period) or candidate.period <= 0:
        return []
    first = int(math.ceil((float(np.nanmin(time)) - candidate.t0) / candidate.period)) - 1
    last = int(math.floor((float(np.nanmax(time)) - candidate.t0) / candidate.period)) + 1
    rows = []
    tmin = float(np.nanmin(time))
    tmax = float(np.nanmax(time))
    for epoch in range(first, last + 1):
        center = candidate.t0 + epoch * candidate.period
        if tmin <= center <= tmax:
            rows.append((epoch, float(center)))
    return rows


def measure_depth_at(
    time: np.ndarray,
    flux: np.ndarray,
    center: float,
    duration: float,
    local_scale: float = 6.0,
) -> dict[str, Any]:
    half = max(duration / 2.0, 1e-5)
    local_window = max(local_scale * duration, 0.18)
    dt = time - center
    local = np.abs(dt) <= local_window
    if np.count_nonzero(local) < 8:
        return {"depth": float("nan"), "snr": float("nan"), "n_in": 0, "n_out": 0}
    ldt = dt[local]
    lf = flux[local]
    inside = np.abs(ldt) <= half
    outside = (np.abs(ldt) >= 1.5 * half) & (np.abs(ldt) <= local_window)
    n_in = int(np.count_nonzero(inside))
    n_out = int(np.count_nonzero(outside))
    if n_in < 3 or n_out < 5:
        return {"depth": float("nan"), "snr": float("nan"), "n_in": n_in, "n_out": n_out}
    baseline = float(np.nanmedian(lf[outside]))
    depth = max(0.0, baseline - float(np.nanmedian(lf[inside])))
    scatter_ppt = robust_sigma((lf[outside] - baseline) * 1000.0)
    snr = depth * 1000.0 / scatter_ppt * math.sqrt(n_in) if scatter_ppt > 0 else float("nan")
    return {"depth": float(depth), "snr": float(snr), "n_in": n_in, "n_out": n_out}


def analyze_single_transits(candidate: Candidate, time: np.ndarray, flux: np.ndarray) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = []
    for epoch, center in expected_epochs(time, candidate):
        metric = measure_depth_at(time, flux, center, candidate.duration)
        depth_ppt = float(metric["depth"]) * 1000.0 if np.isfinite(metric["depth"]) else float("nan")
        local_snr = float(metric["snr"]) if np.isfinite(metric["snr"]) else float("nan")
        visible = bool(np.isfinite(local_snr) and local_snr >= 2.0 and depth_ppt > 0)
        robust = bool(np.isfinite(local_snr) and local_snr >= 5.0 and depth_ppt > 0)
        rows.append(
            {
                "epoch": epoch,
                "expected_time": center,
                "depth_ppt": depth_ppt,
                "local_snr": local_snr,
                "n_in": metric["n_in"],
                "n_out": metric["n_out"],
                "visible": visible,
                "robust": robust,
            }
        )
    visible_depths = [row["depth_ppt"] for row in rows if row["visible"] and np.isfinite(row["depth_ppt"])]
    visible_snrs = [row["local_snr"] for row in rows if row["visible"] and np.isfinite(row["local_snr"])]
    robust_rows = [row for row in rows if row["robust"]]
    median_depth = float(np.nanmedian(visible_depths)) if visible_depths else float("nan")
    min_depth_ratio = (
        float(np.nanmin(visible_depths) / median_depth)
        if visible_depths and np.isfinite(median_depth) and median_depth > 0
        else float("nan")
    )
    depth_cv = (
        float(np.nanstd(visible_depths) / median_depth)
        if len(visible_depths) >= 2 and np.isfinite(median_depth) and median_depth > 0
        else float("nan")
    )
    summary = {
        "expected_transits": len(rows),
        "visible_transits_level5": int(sum(1 for row in rows if row["visible"])),
        "robust_transits": len(robust_rows),
        "robust_epochs": ",".join(str(row["epoch"]) for row in robust_rows),
        "median_single_snr": float(np.nanmedian(visible_snrs)) if visible_snrs else float("nan"),
        "visible_depths_ppt": visible_depths,
        "all_depths_ppt": [row["depth_ppt"] for row in rows],
        "all_snrs": [row["local_snr"] for row in rows],
        "median_depth_ppt": median_depth,
        "min_depth_ratio": min_depth_ratio,
        "depth_cv": depth_cv,
    }
    return summary, rows


def analyze_odd_even(candidate: Candidate, time: np.ndarray, flux: np.ndarray, event_rows: list[dict[str, Any]]) -> dict[str, Any]:
    odd_depths = [row["depth_ppt"] for row in event_rows if row["epoch"] % 2 and np.isfinite(row["depth_ppt"])]
    even_depths = [row["depth_ppt"] for row in event_rows if not row["epoch"] % 2 and np.isfinite(row["depth_ppt"])]
    odd_depth = float(np.nanmedian(odd_depths)) if odd_depths else float("nan")
    even_depth = float(np.nanmedian(even_depths)) if even_depths else float("nan")
    ratio = odd_depth / even_depth if np.isfinite(odd_depth) and np.isfinite(even_depth) and even_depth > 0 else float("nan")
    denom = float("nan")
    if len(odd_depths) >= 2 and len(even_depths) >= 2:
        denom = math.sqrt((robust_sigma(np.array(odd_depths)) ** 2 / len(odd_depths)) + (robust_sigma(np.array(even_depths)) ** 2 / len(even_depths)))
    delta_sigma = abs(odd_depth - even_depth) / denom if np.isfinite(denom) and denom > 0 else float("nan")

    ph = phase_days(time, candidate.period, candidate.t0)
    transit_n = np.floor((time - candidate.t0) / candidate.period).astype(int)
    inside = np.abs(ph) <= candidate.duration / 2.0
    outside = np.abs(ph) >= 2.0 * candidate.duration
    baseline = float(np.nanmedian(flux[outside])) if np.count_nonzero(outside) >= 10 else 1.0
    odd_points = inside & (transit_n % 2 == 1)
    even_points = inside & (transit_n % 2 == 0)
    if np.count_nonzero(odd_points) >= 4 and np.count_nonzero(even_points) >= 4:
        odd_point_depth = max(0.0, baseline - float(np.nanmedian(flux[odd_points]))) * 1000.0
        even_point_depth = max(0.0, baseline - float(np.nanmedian(flux[even_points]))) * 1000.0
        point_ratio = odd_point_depth / even_point_depth if even_point_depth > 0 else float("nan")
    else:
        odd_point_depth = even_point_depth = point_ratio = float("nan")

    flag = bool(
        (np.isfinite(ratio) and (ratio < 0.5 or ratio > 2.0))
        or (np.isfinite(point_ratio) and (point_ratio < 0.5 or point_ratio > 2.0))
        or (np.isfinite(delta_sigma) and delta_sigma >= 3.0)
    )
    return {
        "odd_depth_ppt_independent": odd_depth,
        "even_depth_ppt_independent": even_depth,
        "odd_even_ratio_independent": ratio,
        "odd_even_delta_sigma_independent": delta_sigma,
        "odd_depth_ppt_points": odd_point_depth,
        "even_depth_ppt_points": even_point_depth,
        "odd_even_ratio_points": point_ratio,
        "odd_event_count": len(odd_depths),
        "even_event_count": len(even_depths),
        "odd_n_points": int(np.count_nonzero(odd_points)),
        "even_n_points": int(np.count_nonzero(even_points)),
        "odd_even_flag_level5": flag,
    }


def analyze_secondary(candidate: Candidate, time: np.ndarray, flux: np.ndarray) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    primary = measure_depth_at(time, flux, candidate.t0, candidate.duration, local_scale=8.0)
    primary_depth = float(primary["depth"]) if np.isfinite(primary["depth"]) and primary["depth"] > 0 else candidate.depth
    rows = []
    best = {"phase": float("nan"), "depth_ppt": -np.inf, "ratio": float("nan"), "snr": float("nan")}
    for phase in np.linspace(0.1, 0.9, 81):
        if abs(phase - 0.5) > 0.45:
            continue
        ph_days = phase_days(time, candidate.period, candidate.t0) - phase * candidate.period
        ph_days = ((ph_days + 0.5 * candidate.period) % candidate.period) - 0.5 * candidate.period
        half = candidate.duration / 2.0
        inside = np.abs(ph_days) <= half
        outside = (np.abs(ph_days) >= 2.0 * candidate.duration) & (np.abs(ph_days) <= 8.0 * candidate.duration)
        n_in = int(np.count_nonzero(inside))
        n_out = int(np.count_nonzero(outside))
        if n_in < 3 or n_out < 5:
            depth = ratio = snr = float("nan")
        else:
            baseline = float(np.nanmedian(flux[outside]))
            depth = max(0.0, baseline - float(np.nanmedian(flux[inside])))
            scatter_ppt = robust_sigma((flux[outside] - baseline) * 1000.0)
            snr = depth * 1000.0 / scatter_ppt * math.sqrt(n_in) if scatter_ppt > 0 else float("nan")
            ratio = depth / primary_depth if primary_depth > 0 else float("nan")
        depth_ppt = depth * 1000.0 if np.isfinite(depth) else float("nan")
        row = {
            "phase": float(phase),
            "depth_ppt": depth_ppt,
            "ratio_to_primary": ratio,
            "snr": snr,
            "n_in": n_in,
            "n_out": n_out,
        }
        rows.append(row)
        if np.isfinite(depth_ppt) and depth_ppt > best["depth_ppt"]:
            best = {"phase": float(phase), "depth_ppt": depth_ppt, "ratio": ratio, "snr": snr}

    half_phase = min(rows, key=lambda row: abs(row["phase"] - 0.5)) if rows else {}
    secondary_ratio = safe_float(half_phase.get("ratio_to_primary")) if half_phase else float("nan")
    secondary_depth_ppt = safe_float(half_phase.get("depth_ppt")) if half_phase else float("nan")
    secondary_snr = safe_float(half_phase.get("snr")) if half_phase else float("nan")
    flag = bool(
        (np.isfinite(secondary_ratio) and secondary_ratio > 0.5)
        or (np.isfinite(best["ratio"]) and best["ratio"] > 0.65)
        or (np.isfinite(best["snr"]) and best["snr"] >= 7.0 and np.isfinite(best["ratio"]) and best["ratio"] > 0.25)
    )
    borderline = bool(
        not flag
        and (
            (np.isfinite(secondary_ratio) and secondary_ratio > 0.25)
            or (np.isfinite(best["ratio"]) and best["ratio"] > 0.35)
            or (np.isfinite(best["snr"]) and best["snr"] >= 5.0)
        )
    )
    return (
        {
            "primary_depth_ppt_level5": primary_depth * 1000.0 if np.isfinite(primary_depth) else float("nan"),
            "secondary_best_phase_independent": best["phase"],
            "secondary_best_depth_ppt_independent": best["depth_ppt"],
            "secondary_best_ratio_independent": best["ratio"],
            "secondary_best_snr_independent": best["snr"],
            "secondary_half_phase_depth_ppt": secondary_depth_ppt,
            "secondary_half_phase_ratio": secondary_ratio,
            "secondary_half_phase_snr": secondary_snr,
            "secondary_flag_level5": flag,
            "secondary_borderline_level5": borderline,
        },
        rows,
    )


def gaia_local_summary(tic: int) -> dict[str, Any] | None:
    if LOCAL_GAIA_SUMMARY.exists():
        with LOCAL_GAIA_SUMMARY.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if safe_int(row.get("TIC")) == tic:
                    return {
                        "gaia_status": row.get("gaia_detail_status") or "OK",
                        "nearby_star_count": safe_int(row.get("gaia_nearby_60_count")),
                        "nearby_bright_count": safe_int(row.get("gaia_bright_nearby_60_count")),
                        "nearest_neighbor_sep_arcsec": safe_float(row.get("nearest_neighbor_sep_arcsec")),
                        "nearest_neighbor_delta_g": safe_float(row.get("nearest_neighbor_delta_g")),
                        "brightest_neighbor_delta_g": safe_float(row.get("brightest_neighbor_delta_g")),
                        "gaia_source": str(LOCAL_GAIA_SUMMARY),
                    }
    detail = LOCAL_GAIA_DIR / f"TIC_{tic}_gaia_nearby_60arcsec.csv"
    if detail.exists():
        rows = list(csv.DictReader(detail.open(newline="", encoding="utf-8")))
        deltas = [safe_float(row.get("delta_g_mag")) for row in rows]
        seps = [safe_float(row.get("sep_arcsec")) for row in rows]
        deltas = [value for value in deltas if np.isfinite(value)]
        seps = [value for value in seps if np.isfinite(value)]
        return {
            "gaia_status": "OK",
            "nearby_star_count": len(rows),
            "nearby_bright_count": int(sum(1 for value in deltas if value <= 5.0)),
            "nearest_neighbor_sep_arcsec": min(seps) if seps else float("nan"),
            "nearest_neighbor_delta_g": float("nan"),
            "brightest_neighbor_delta_g": min(deltas) if deltas else float("nan"),
            "gaia_source": str(detail),
        }
    return None


def read_tap_csv(query: str, timeout: int = 90) -> pd.DataFrame:
    data = urllib.parse.urlencode(
        {
            "REQUEST": "doQuery",
            "LANG": "ADQL",
            "QUERY": query.strip(),
            "FORMAT": "csv",
        }
    ).encode()
    req = urllib.request.Request(GAIA_TAP_URL, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        text = response.read().decode("utf-8", errors="replace")
    return pd.read_csv(io.StringIO(text))


def gaia_online_summary(candidate: Candidate, out_dir: Path) -> dict[str, Any]:
    if not candidate.gaia_id.isdigit():
        return {"gaia_status": "NO_GAIA_ID", "nearby_star_count": 0, "nearby_bright_count": 0, "nearby_star_flag": False}
    source_id = int(candidate.gaia_id)
    try:
        source_query = f"""
        SELECT source_id, ra, dec, phot_g_mean_mag
        FROM gaiadr3.gaia_source
        WHERE source_id = {source_id}
        """
        source = read_tap_csv(source_query, timeout=60)
        if source.empty:
            return {"gaia_status": "GAIA_SOURCE_NOT_FOUND", "nearby_star_count": 0, "nearby_bright_count": 0, "nearby_star_flag": False}
        ra = float(source.iloc[0]["ra"])
        dec = float(source.iloc[0]["dec"])
        gmag = safe_float(source.iloc[0].get("phot_g_mean_mag"))
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
        nearby = read_tap_csv(cone_query, timeout=90)
        if not nearby.empty and np.isfinite(gmag):
            nearby["delta_g_mag"] = pd.to_numeric(nearby["phot_g_mean_mag"], errors="coerce") - gmag
        out_dir.mkdir(parents=True, exist_ok=True)
        nearby.to_csv(out_dir / f"TIC_{candidate.tic}_gaia_nearby_60arcsec.csv", index=False)
        deltas = pd.to_numeric(nearby.get("delta_g_mag", pd.Series(dtype=float)), errors="coerce")
        seps = pd.to_numeric(nearby.get("sep_arcsec", pd.Series(dtype=float)), errors="coerce")
        return {
            "gaia_status": "OK_ONLINE",
            "nearby_star_count": int(len(nearby)),
            "nearby_bright_count": int((deltas <= 5.0).sum()) if len(deltas) else 0,
            "nearest_neighbor_sep_arcsec": float(seps.min()) if len(seps.dropna()) else float("nan"),
            "nearest_neighbor_delta_g": float("nan"),
            "brightest_neighbor_delta_g": float(deltas.min()) if len(deltas.dropna()) else float("nan"),
            "gaia_source": str(out_dir / f"TIC_{candidate.tic}_gaia_nearby_60arcsec.csv"),
        }
    except Exception as exc:
        return {
            "gaia_status": f"ERROR:{type(exc).__name__}",
            "nearby_star_count": 0,
            "nearby_bright_count": 0,
            "nearest_neighbor_sep_arcsec": float("nan"),
            "nearest_neighbor_delta_g": float("nan"),
            "brightest_neighbor_delta_g": float("nan"),
            "gaia_source": "",
        }


def neighbor_summary(candidate: Candidate, out_dir: Path, online_missing: bool) -> dict[str, Any]:
    summary = gaia_local_summary(candidate.tic)
    if summary is None and online_missing:
        summary = gaia_online_summary(candidate, out_dir)
    if summary is None:
        summary = {
            "gaia_status": "NO_LOCAL_GAIA_FILE",
            "nearby_star_count": 0,
            "nearby_bright_count": 0,
            "nearest_neighbor_sep_arcsec": float("nan"),
            "nearest_neighbor_delta_g": float("nan"),
            "brightest_neighbor_delta_g": float("nan"),
            "gaia_source": "",
        }
    nearest = safe_float(summary.get("nearest_neighbor_sep_arcsec"))
    brightest_delta = safe_float(summary.get("brightest_neighbor_delta_g"))
    bright_count = safe_int(summary.get("nearby_bright_count"))
    summary["nearby_star_flag"] = bool(
        bright_count > 0
        or (np.isfinite(nearest) and nearest < 10.0)
        or (np.isfinite(brightest_delta) and brightest_delta <= 5.0)
    )
    return summary


def infer_segments(time: np.ndarray, gap_days: float = 5.0) -> list[np.ndarray]:
    gaps = np.where(np.diff(time) > gap_days)[0]
    starts = [0] + [int(i + 1) for i in gaps]
    ends = [int(i + 1) for i in gaps] + [len(time)]
    return [np.arange(start, end) for start, end in zip(starts, ends) if end - start >= 20]


def segment_summary(candidate: Candidate, time: np.ndarray, flux: np.ndarray) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = []
    for idx, seg_idx in enumerate(infer_segments(time), start=1):
        st = time[seg_idx]
        sf = flux[seg_idx]
        event_rows = []
        for epoch, center in expected_epochs(st, candidate):
            metric = measure_depth_at(st, sf, center, candidate.duration)
            event_rows.append(metric)
        snrs = [safe_float(row["snr"]) for row in event_rows if np.isfinite(row["snr"])]
        depths = [safe_float(row["depth"]) * 1000.0 for row in event_rows if np.isfinite(row["depth"])]
        rows.append(
            {
                "segment": idx,
                "time_start": float(np.nanmin(st)),
                "time_end": float(np.nanmax(st)),
                "n_points": int(len(st)),
                "n_expected": len(event_rows),
                "n_visible": int(sum(1 for snr in snrs if snr >= 2.0)),
                "median_snr": float(np.nanmedian(snrs)) if snrs else float("nan"),
                "median_depth_ppt": float(np.nanmedian(depths)) if depths else float("nan"),
            }
        )
    with_transits = [row for row in rows if row["n_expected"] > 0]
    visible_segments = [row for row in with_transits if row["n_visible"] > 0]
    return (
        {
            "segments_total": len(rows),
            "segments_with_expected_transit": len(with_transits),
            "segments_with_visible_transit": len(visible_segments),
            "sector_consistency_ok_level5": bool(visible_segments and (len(with_transits) <= 1 or len(visible_segments) / len(with_transits) >= 0.5)),
        },
        rows,
    )


def status_from_flags(payload: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    flags: list[str] = []
    notes: list[str] = []
    robust = safe_int(payload.get("robust_transits"))
    visible = safe_int(payload.get("visible_transits_level5"))
    if visible < 2:
        flags.append("only_1_visible_transit")
    elif robust < 2:
        flags.append("weak_visible_transits")
    elif robust < 3:
        flags.append("only_2_robust_transits")
    if safe_float(payload.get("median_single_snr")) < 5.0:
        flags.append("low_median_single_snr")
    if np.isfinite(safe_float(payload.get("min_depth_ratio"))) and safe_float(payload.get("min_depth_ratio")) < 0.35:
        flags.append("inconsistent_visible_depths")
    if np.isfinite(safe_float(payload.get("depth_cv"))) and safe_float(payload.get("depth_cv")) > 0.75:
        flags.append("large_depth_scatter")
    if payload.get("odd_even_flag_level5"):
        flags.append("odd_even_recheck")
    if payload.get("secondary_flag_level5"):
        flags.append("secondary_reject_signal")
    elif payload.get("secondary_borderline_level5"):
        flags.append("secondary_borderline")
    if not payload.get("sector_consistency_ok_level5"):
        flags.append("sector_consistency_recheck")
    if payload.get("nearby_star_flag"):
        flags.append("nearby_star_recheck")
    if str(payload.get("gaia_status", "")).startswith("NO_") or str(payload.get("gaia_status", "")).startswith("ERROR"):
        notes.append(str(payload.get("gaia_status")))

    strong_reject = bool(
        payload.get("secondary_flag_level5")
        or (
            payload.get("odd_even_flag_level5")
            and np.isfinite(safe_float(payload.get("odd_even_ratio_independent")))
            and (safe_float(payload.get("odd_even_ratio_independent")) < 0.35 or safe_float(payload.get("odd_even_ratio_independent")) > 2.8)
        )
    )
    if strong_reject:
        status = "REJECT_LEVEL5_LOCAL"
    elif flags:
        status = "HOLD_RECHECK"
    else:
        status = "PASS_LEVEL5_LOCAL"
    return status, flags, notes


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{key: clean_json(value) for key, value in row.items()} for row in rows])


def plot_single_transits(path: Path, candidate: Candidate, time: np.ndarray, flux: np.ndarray, event_rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = max(1, len(event_rows))
    cols = min(3, n)
    rows = int(math.ceil(n / cols))
    fig, axs = plt.subplots(rows, cols, figsize=(cols * 4.2, rows * 3.1), dpi=150, squeeze=False)
    for ax in axs.flat:
        ax.axis("off")
    for ax, event in zip(axs.flat, event_rows):
        center = event["expected_time"]
        window = max(4.0 * candidate.duration, 0.35)
        mask = np.abs(time - center) <= window
        ax.axis("on")
        if np.count_nonzero(mask):
            ax.scatter((time[mask] - center) * 24.0, flux[mask], s=5, alpha=0.55, linewidths=0)
        half_h = candidate.duration * 12.0
        ax.axvspan(-half_h, half_h, color="tab:red", alpha=0.14)
        ax.axvline(0, color="tab:red", alpha=0.65, linewidth=1)
        ax.set_title(f"epoch {event['epoch']} | SNR {safe_float(event['local_snr']):.1f} | {safe_float(event['depth_ppt']):.2f} ppt")
        ax.set_xlabel("hours from transit")
        ax.set_ylabel("flux")
        ax.grid(alpha=0.2)
    fig.suptitle(f"TIC {candidate.tic} Level5 single transits", fontsize=13)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_odd_even(path: Path, candidate: Candidate, time: np.ndarray, flux: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ph = phase_days(time, candidate.period, candidate.t0) * 24.0
    transit_n = np.floor((time - candidate.t0) / candidate.period).astype(int)
    window = max(candidate.duration * 24.0 * 5.0, 8.0)
    mask = np.abs(ph) <= window
    fig, ax = plt.subplots(figsize=(8.5, 4.8), dpi=150)
    odd = mask & (transit_n % 2 == 1)
    even = mask & (transit_n % 2 == 0)
    ax.scatter(ph[even], flux[even], s=5, alpha=0.45, label="even", linewidths=0)
    ax.scatter(ph[odd], flux[odd], s=5, alpha=0.45, label="odd", linewidths=0)
    half_h = candidate.duration * 12.0
    ax.axvspan(-half_h, half_h, color="tab:red", alpha=0.12)
    ax.axvline(0, color="tab:red", alpha=0.65, linewidth=1)
    ax.set_title(f"TIC {candidate.tic} odd/even phase fold")
    ax.set_xlabel("hours from transit")
    ax.set_ylabel("flux")
    ax.grid(alpha=0.25)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_secondary(path: Path, candidate: Candidate, scan_rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    phases = [row["phase"] for row in scan_rows]
    ratios = [row["ratio_to_primary"] for row in scan_rows]
    snrs = [row["snr"] for row in scan_rows]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.5, 6.0), dpi=150, sharex=True)
    ax1.plot(phases, ratios, marker="o", markersize=2.5, linewidth=1)
    ax1.axhline(0.25, color="tab:orange", linestyle="--", linewidth=1)
    ax1.axhline(0.5, color="tab:red", linestyle="--", linewidth=1)
    ax1.axvline(0.5, color="tab:purple", alpha=0.6)
    ax1.set_ylabel("secondary / primary")
    ax1.grid(alpha=0.25)
    ax2.plot(phases, snrs, marker="o", markersize=2.5, linewidth=1, color="tab:green")
    ax2.axhline(5, color="tab:orange", linestyle="--", linewidth=1)
    ax2.axhline(7, color="tab:red", linestyle="--", linewidth=1)
    ax2.axvline(0.5, color="tab:purple", alpha=0.6)
    ax2.set_xlabel("orbital phase")
    ax2.set_ylabel("local SNR")
    ax2.grid(alpha=0.25)
    fig.suptitle(f"TIC {candidate.tic} secondary scan")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def process_candidate(candidate: Candidate, online_gaia_missing: bool, overwrite: bool) -> dict[str, Any]:
    slug = f"{candidate.rank:02d}_TIC_{candidate.tic}"
    single_dir = SINGLE_ROOT / slug
    odd_dir = ODD_EVEN_ROOT / slug
    sec_dir = SECONDARY_ROOT / slug
    neigh_dir = NEIGHBOR_ROOT / slug
    for directory in (single_dir, odd_dir, sec_dir, neigh_dir):
        directory.mkdir(parents=True, exist_ok=True)

    summary_path = odd_dir / f"TIC_{candidate.tic}_odd_even_level5.json"
    if summary_path.exists() and not overwrite:
        try:
            return json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    time, flux = load_lightcurve(candidate.lightcurve_path)
    single_summary, event_rows = analyze_single_transits(candidate, time, flux)
    odd_even = analyze_odd_even(candidate, time, flux, event_rows)
    secondary, scan_rows = analyze_secondary(candidate, time, flux)
    segments, segment_rows = segment_summary(candidate, time, flux)
    neighbor = neighbor_summary(candidate, neigh_dir, online_gaia_missing)

    payload: dict[str, Any] = {
        "tic": candidate.tic,
        "rank": candidate.rank,
        "period_days": candidate.period,
        "duration_days": candidate.duration,
        "radius_rearth": candidate.radius_rearth,
        "transit_snr": candidate.transit_snr,
        "db_status": candidate.status,
        "hz_status": candidate.hz_status,
        "distance_ly": candidate.distance_ly,
        "db_visible_transits": candidate.visible_transits,
        "db_clean_sector_count": candidate.clean_sector_count,
        "db_sector_count": candidate.sector_count,
        **single_summary,
        **odd_even,
        **secondary,
        **segments,
        **neighbor,
    }
    status, flags, notes = status_from_flags(payload)
    payload["status"] = status
    payload["flags"] = flags
    payload["notes"] = notes

    write_csv(single_dir / f"TIC_{candidate.tic}_visible_single_transits_level5.csv", event_rows)
    write_csv(single_dir / f"TIC_{candidate.tic}_sector_segments.csv", segment_rows)
    write_csv(sec_dir / f"TIC_{candidate.tic}_secondary_phase_scan_level5.csv", scan_rows)
    plot_single_transits(single_dir / f"TIC_{candidate.tic}_single_transits.png", candidate, time, flux, event_rows)
    plot_odd_even(odd_dir / f"TIC_{candidate.tic}_level5_odd_even.png", candidate, time, flux)
    plot_secondary(sec_dir / f"TIC_{candidate.tic}_level5_secondary_scan.png", candidate, scan_rows)
    (odd_dir / f"TIC_{candidate.tic}_odd_even_level5.json").write_text(
        json.dumps(clean_json(payload), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (sec_dir / f"TIC_{candidate.tic}_secondary_level5.json").write_text(
        json.dumps(clean_json(payload), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (neigh_dir / f"TIC_{candidate.tic}_neighbor_blend_level5.json").write_text(
        json.dumps(clean_json(payload), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (neigh_dir / "LEVEL5_NACHBARSTERN_CHECK.md").write_text(
        "\n".join(
            [
                f"# Level 5 Nachbarstern-/Blend-Check: TIC {candidate.tic}",
                "",
                f"- Gaia-Status: {payload.get('gaia_status')}",
                f"- Nahe Quellen: {payload.get('nearby_star_count')}",
                f"- Helle nahe Quellen: {payload.get('nearby_bright_count')}",
                f"- Naechster Nachbar: {safe_float(payload.get('nearest_neighbor_sep_arcsec')):.2f} arcsec",
                f"- Hellster Nachbar delta G: {safe_float(payload.get('brightest_neighbor_delta_g')):.2f}",
                f"- Nearby-Star-Flag: {payload.get('nearby_star_flag')}",
                "",
                "Level-5-Einordnung: "
                + ("Blend-/Nachbarstern-Recheck noetig." if payload.get("nearby_star_flag") else "kein lokaler heller Gaia-Blend-Hinweis."),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return payload


def write_summary(payloads: list[dict[str, Any]]) -> None:
    SUMMARY_ROOT.mkdir(parents=True, exist_ok=True)
    fields = [
        "rank",
        "tic",
        "status",
        "recommended_action",
        "flags",
        "notes",
        "db_status",
        "hz_status",
        "period_days",
        "radius_rearth",
        "transit_snr",
        "distance_ly",
        "expected_transits",
        "visible_transits_level5",
        "robust_transits",
        "median_single_snr",
        "median_depth_ppt",
        "min_depth_ratio",
        "depth_cv",
        "odd_even_ratio_independent",
        "odd_even_ratio_points",
        "secondary_half_phase_ratio",
        "secondary_best_phase_independent",
        "secondary_best_ratio_independent",
        "secondary_best_snr_independent",
        "nearby_star_count",
        "nearby_bright_count",
        "nearest_neighbor_sep_arcsec",
        "brightest_neighbor_delta_g",
        "gaia_status",
    ]
    rows = []
    for payload in sorted(payloads, key=lambda row: safe_int(row.get("rank"))):
        row = {field: payload.get(field, "") for field in fields}
        row["recommended_action"] = recommended_action(payload)
        row["flags"] = ";".join(payload.get("flags") or [])
        row["notes"] = ";".join(payload.get("notes") or [])
        rows.append(row)
    summary_csv = SUMMARY_ROOT / "green_purple_A_level5_summary.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{key: clean_json(value) for key, value in row.items()} for row in rows])

    lines = [
        "# Green/Purple A-Level5 Summary",
        "",
        f"Candidates: {len(rows)}",
        "",
        "| Rank | TIC | Status | Flags | SNR | Visible/Robust | Odd/Even | Secondary | Nearby bright |",
        "|---:|---:|---|---|---:|---|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {rank} | {tic} | {status} | {flags} | {snr:.1f} | {visible}/{robust} | {oe:.3g} | {sec:.3g} | {nearby} |".format(
                rank=row["rank"],
                tic=row["tic"],
                status=row["status"],
                flags=str(row["recommended_action"] or row["flags"] or "ok").replace("|", "/"),
                snr=safe_float(row["transit_snr"], 0.0),
                visible=safe_int(row["visible_transits_level5"]),
                robust=safe_int(row["robust_transits"]),
                oe=safe_float(row["odd_even_ratio_independent"]),
                sec=safe_float(row["secondary_best_ratio_independent"]),
                nearby=safe_int(row["nearby_bright_count"]),
            )
        )
    lines.append("")
    (SUMMARY_ROOT / "GREEN_PURPLE_A_LEVEL5_SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


def recommended_action(payload: dict[str, Any]) -> str:
    status = str(payload.get("status") or "")
    flags = set(payload.get("flags") or [])
    if status == "REJECT_LEVEL5_LOCAL":
        return "DROP_FROM_TOPLIST_RECHECK_FP"
    if flags == {"only_2_robust_transits"}:
        return "KEEP_TOP_WAIT_MORE_TRANSITS"
    if "only_1_visible_transit" in flags:
        return "WAIT_MORE_DATA_LOW_CONFIDENCE"
    if "secondary_borderline" in flags or "odd_even_recheck" in flags:
        return "MANUAL_REVIEW_BEFORE_LEVEL6"
    if "nearby_star_recheck" in flags:
        return "BLEND_REVIEW_BEFORE_LEVEL6"
    return "KEEP_REVIEW"


def main() -> int:
    args = parse_args()
    priority_rows = load_priority_rows(args.group, args.limit)
    candidates = load_candidates(priority_rows)
    payloads = []
    for candidate in candidates:
        print(f"Level5 {candidate.rank:02d} TIC {candidate.tic} ...", flush=True)
        payload = process_candidate(candidate, args.online_gaia_missing, args.overwrite)
        payloads.append(payload)
        print(f"  -> {payload.get('status')} flags={';'.join(payload.get('flags') or []) or 'ok'}", flush=True)
    write_summary(payloads)
    print(f"Processed: {len(payloads)}")
    print(f"Summary: {SUMMARY_ROOT / 'green_purple_A_level5_summary.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
