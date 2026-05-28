#!/usr/bin/env python3
"""Evidence vetting layer for Super-Earth Hunter candidates.

This script is intentionally separate from ``masterscript_v2.py``.  The master
script stays a fast discovery pipeline; this layer turns raw candidates into
ranked, explainable targets for follow-up or slow Bayesian vetting.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import logging
import math
import os
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from astropy.timeseries import BoxLeastSquares, LombScargle

try:
    from astropy.time import Time
except Exception:  # pragma: no cover - astropy is expected, but keep CLI usable.
    Time = None


PROJECT_ROOT = Path(os.environ.get("ASTRO_PROJECT_ROOT", "/Users/koni/astro_projects"))
DB_PATH = PROJECT_ROOT / "database" / "planet_hunter.db"
LIGHTCURVE_ROOT = PROJECT_ROOT / "lightcurves"
DEFAULT_OUT_ROOT = PROJECT_ROOT / "evidence_vetting"
REFERENCE_PLOTS = PROJECT_ROOT / "level1_rohkandidaten" / "level1_auto_plots_neuer_lauf" / "combined"

SECTOR_GAP_DAYS = float(os.environ.get("EVIDENCE_SECTOR_GAP_DAYS", "5.0"))
VISIBLE_TRANSIT_MIN_SNR = float(os.environ.get("EVIDENCE_VISIBLE_TRANSIT_MIN_SNR", "2.0"))
LOCAL_WINDOW_MIN_DAYS = float(os.environ.get("EVIDENCE_LOCAL_WINDOW_MIN_DAYS", "0.12"))
SAP_PDC_LOCAL_BLS_PERIODS = int(os.environ.get("EVIDENCE_SAP_PDC_BLS_PERIODS", "220"))
ACTIVITY_MAX_POINTS = int(os.environ.get("EVIDENCE_ACTIVITY_MAX_POINTS", "30000"))
FEW_EVENT_LIMIT = int(os.environ.get("EVIDENCE_FEW_EVENT_LIMIT", "3"))
MIN_OBSERVED_TRANSIT_WINDOWS = int(os.environ.get("EVIDENCE_MIN_OBSERVED_TRANSIT_WINDOWS", "2"))
LOW_EPHEMERIS_COVERAGE_RATIO = float(os.environ.get("EVIDENCE_LOW_EPHEMERIS_COVERAGE_RATIO", "0.35"))

HZ_CLASSES = {"KONSERVATIVE_HZ", "OPT_HZ_INNEN", "OPT_HZ_AUSSEN"}
FOLLOWUP_CLASSES = {"SPC_STRONG", "SPC_FOLLOWUP_READY", "SPC_RV_NEEDED", "SPC_WEAK_DATA"}
ADVANCED_CLASSES = {"SPC_STRONG", "SPC_FOLLOWUP_READY", "SPC_RV_NEEDED"}


@dataclass(frozen=True)
class Candidate:
    tic: int
    candidate_id: int
    gaia_id: str | None
    teff: float | None
    distance_ly: float | None
    tmag: float | None
    stellar_radius: float | None
    stellar_logg: float | None
    period: float
    duration: float
    depth: float
    t0: float
    power: float | None
    planet_radius_earth: float | None
    lightcurve_dir: str | None
    transit_snr: float | None
    transit_count: int
    n_in_transit: int
    duration_fraction: float | None
    oe_ratio: float | None
    sec_ratio: float | None
    fp_oe_flag: int
    fp_sec_flag: int
    fp_baseline_flag: int
    fp_baseline_std_flag: int
    fp_scatter_flag: int
    is_fp: int
    hz_status: str
    hz_class: str
    sector_count: int | None
    clean_sector_count: int | None
    visible_transits: int | None
    spc_class: str | None
    status: str | None
    revisit_priority: float | None
    notes: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score candidates with an explainable evidence-vetting layer."
    )
    parser.add_argument("--tic", type=int, action="append", help="Only process this TIC. Repeatable.")
    parser.add_argument("--input-db", type=Path, default=DB_PATH, help="SQLite database path.")
    parser.add_argument("--input-csv", type=Path, default=None, help="Candidate CSV instead of database.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT_ROOT, help="Output root.")
    parser.add_argument("--max-candidates", type=int, default=None, help="Maximum candidates to process.")
    parser.add_argument(
        "--max-distance-ly",
        type=float,
        default=None,
        help="Only process candidates with distance_ly at or below this value.",
    )
    parser.add_argument(
        "--source",
        choices=["priority", "spc", "all"],
        default="priority",
        help="Database candidate selection mode.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Write files, but do not update SQLite.")
    parser.add_argument("--no-dashboard", action="store_true", help="Skip static HTML dashboard export.")
    return parser.parse_args()


def safe_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        out = float(value)
    except Exception:
        return default
    return out if np.isfinite(out) else default


def safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        if isinstance(value, float) and not np.isfinite(value):
            return default
        return int(value)
    except Exception:
        return default


def clip_score(value: float) -> float:
    if not np.isfinite(value):
        return 0.0
    return round(float(np.clip(value, 0.0, 100.0)), 3)


def robust_scatter(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return float("nan")
    med = float(np.nanmedian(values))
    mad = float(np.nanmedian(np.abs(values - med)))
    if np.isfinite(mad) and mad > 0:
        return float(1.4826 * mad)
    return float(np.nanstd(values))


def finite_median(values: list[Any] | np.ndarray) -> float:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return float("nan")
    return float(np.nanmedian(arr))


def centered_phase_days(time_arr: np.ndarray, period: float, t0: float) -> np.ndarray:
    return ((time_arr - t0 + period / 2.0) % period) - period / 2.0


def make_run_dir(output_root: Path) -> tuple[str, Path]:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = output_root / f"{run_id}_evidence_vetting"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_id, run_dir


def setup_logger(run_dir: Path) -> logging.Logger:
    logger = logging.getLogger("evidence_vetting")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(run_dir / "run.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def normalize_flux(flux: np.ndarray) -> np.ndarray:
    flux = np.asarray(flux, dtype=float)
    med = float(np.nanmedian(flux)) if len(flux) else float("nan")
    if np.isfinite(med) and abs(med) > 1e-10:
        return flux / med
    return flux - med + 1.0


def pick_col(columns: list[str], names: tuple[str, ...]) -> str | None:
    lowered = {c.lower(): c for c in columns}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def row_get(row: pd.Series, names: tuple[str, ...], default: Any = None) -> Any:
    col = pick_col(list(row.index), names)
    return row[col] if col else default


def candidate_from_csv_row(row: pd.Series, fallback_id: int) -> Candidate:
    tic = safe_int(row_get(row, ("TIC", "tic", "tic_id")))
    period = safe_float(row_get(row, ("best_period", "period", "posterior_period")), 0.0) or 0.0
    duration = safe_float(row_get(row, ("duration", "posterior_duration")), 0.0) or 0.0
    depth = safe_float(row_get(row, ("depth", "posterior_depth")), 0.0) or 0.0
    t0 = safe_float(row_get(row, ("transit_time", "epoch", "t0")), 0.0) or 0.0
    cid = safe_int(row_get(row, ("candidate_id", "id")), fallback_id)
    return Candidate(
        tic=tic,
        candidate_id=cid,
        gaia_id=str(row_get(row, ("gaia_id", "gaia"), "") or "") or None,
        teff=safe_float(row_get(row, ("teff", "Teff"))),
        distance_ly=safe_float(row_get(row, ("distance_ly", "distance"))),
        tmag=safe_float(row_get(row, ("tmag", "Tmag"))),
        stellar_radius=safe_float(row_get(row, ("stellar_radius", "radius", "rad"))),
        stellar_logg=safe_float(row_get(row, ("stellar_logg", "logg"))),
        period=period,
        duration=duration,
        depth=depth,
        t0=t0,
        power=safe_float(row_get(row, ("power", "bls_power"))),
        planet_radius_earth=safe_float(row_get(row, ("planet_radius_earth", "radius_rearth"))),
        lightcurve_dir=str(row_get(row, ("lightcurve_dir", "lightcurve_path"), "") or "") or None,
        transit_snr=safe_float(row_get(row, ("transit_snr", "snr"))),
        transit_count=safe_int(row_get(row, ("transit_count", "n_transits"))),
        n_in_transit=safe_int(row_get(row, ("n_in_transit",))),
        duration_fraction=safe_float(row_get(row, ("duration_fraction",))),
        oe_ratio=safe_float(row_get(row, ("oe_ratio", "odd_even_ratio"))),
        sec_ratio=safe_float(row_get(row, ("sec_ratio", "secondary_ratio"))),
        fp_oe_flag=safe_int(row_get(row, ("fp_oe_flag", "odd_even_flag"))),
        fp_sec_flag=safe_int(row_get(row, ("fp_sec_flag", "secondary_flag"))),
        fp_baseline_flag=safe_int(row_get(row, ("fp_baseline_flag",))),
        fp_baseline_std_flag=safe_int(row_get(row, ("fp_baseline_std_flag",))),
        fp_scatter_flag=safe_int(row_get(row, ("fp_scatter_flag",))),
        is_fp=safe_int(row_get(row, ("is_fp",))),
        hz_status=str(row_get(row, ("hz_status",), "UNKNOWN") or "UNKNOWN"),
        hz_class=str(row_get(row, ("hz_class",), "UNKNOWN") or "UNKNOWN"),
        sector_count=safe_int(row_get(row, ("sector_count",)), None),
        clean_sector_count=safe_int(row_get(row, ("clean_sector_count",)), None),
        visible_transits=safe_int(row_get(row, ("visible_transits",)), None),
        spc_class=str(row_get(row, ("spc_class",), "") or "") or None,
        status=str(row_get(row, ("status",), "") or "") or None,
        revisit_priority=safe_float(row_get(row, ("revisit_priority",))),
        notes=str(row_get(row, ("notes",), "") or "") or None,
    )


def load_candidates_from_csv(path: Path, args: argparse.Namespace) -> list[Candidate]:
    df = pd.read_csv(path)
    candidates = [candidate_from_csv_row(row, idx + 1) for idx, row in df.iterrows()]
    if args.tic:
        allowed = set(args.tic)
        candidates = [c for c in candidates if c.tic in allowed]
    if args.max_distance_ly is not None:
        candidates = [
            c
            for c in candidates
            if c.distance_ly is not None and c.distance_ly <= args.max_distance_ly
        ]
    candidates = [
        c for c in candidates if c.tic and c.period > 0 and c.duration > 0 and c.depth > 0
    ]
    if args.max_candidates is not None:
        candidates = candidates[: args.max_candidates]
    return candidates


def load_candidates_from_db(db_path: Path, args: argparse.Namespace) -> list[Candidate]:
    sql = """
    SELECT
      c.id AS candidate_id,
      c.TIC,
      c.gaia_id,
      c.teff,
      c.distance_ly,
      COALESCE(r.tmag, NULL) AS tmag,
      c.stellar_radius,
      c.stellar_logg,
      c.best_period,
      c.duration,
      c.depth,
      c.transit_time,
      c.power,
      c.planet_radius_earth,
      c.lightcurve_dir,
      c.transit_snr,
      c.transit_count,
      c.n_in_transit,
      c.duration_fraction,
      c.oe_ratio,
      c.sec_ratio,
      COALESCE(c.fp_oe_flag, 0) AS fp_oe_flag,
      COALESCE(c.fp_sec_flag, 0) AS fp_sec_flag,
      COALESCE(c.fp_baseline_flag, 0) AS fp_baseline_flag,
      COALESCE(c.fp_baseline_std_flag, 0) AS fp_baseline_std_flag,
      COALESCE(c.fp_scatter_flag, 0) AS fp_scatter_flag,
      COALESCE(c.is_fp, 0) AS is_fp,
      COALESCE(c.hz_status, 'UNKNOWN') AS hz_status,
      COALESCE(c.hz_class, 'UNKNOWN') AS hz_class,
      c.sector_count,
      c.clean_sector_count,
      c.visible_transits,
      c.spc_class,
      c.status,
      c.revisit_priority,
      c.notes
    FROM candidates_v2 c
    LEFT JOIN rohdaten r ON r.TIC = c.TIC
    WHERE c.best_period IS NOT NULL
      AND c.duration IS NOT NULL
      AND c.depth IS NOT NULL
      AND c.transit_time IS NOT NULL
    """
    params: list[Any] = []
    if args.tic:
        placeholders = ",".join("?" for _ in args.tic)
        sql += f" AND c.TIC IN ({placeholders})"
        params.extend(args.tic)
    elif args.source == "spc":
        sql += """
        AND (
          COALESCE(c.spc_class, '') LIKE 'SPC%'
          OR COALESCE(c.status, '') LIKE 'SPC%'
        )
        """
    elif args.source == "priority":
        sql += """
        AND COALESCE(c.status, 'CANDIDATE') != 'FP_ART'
        AND (
          COALESCE(c.spc_class, '') LIKE 'SPC%'
          OR COALESCE(c.hz_class, c.hz_status, '') IN ('KONSERVATIVE_HZ','OPT_HZ_INNEN','OPT_HZ_AUSSEN')
          OR COALESCE(c.transit_snr, 0) >= 10
          OR COALESCE(c.revisit_priority, 0) > 0
        )
        """
    if args.max_distance_ly is not None:
        sql += " AND c.distance_ly IS NOT NULL AND c.distance_ly <= ?"
        params.append(args.max_distance_ly)
    sql += """
    ORDER BY
      COALESCE(c.is_fp, 0),
      COALESCE(c.revisit_priority, 0) DESC,
      COALESCE(c.transit_snr, 0) DESC,
      COALESCE(c.transit_count, 0) DESC,
      c.TIC,
      c.id
    """
    if args.max_candidates is not None:
        sql += " LIMIT ?"
        params.append(args.max_candidates)

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=60)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    candidates: list[Candidate] = []
    for row in rows:
        candidates.append(
            Candidate(
                tic=int(row["TIC"]),
                candidate_id=int(row["candidate_id"] or row["TIC"]),
                gaia_id=str(row["gaia_id"]).strip() if row["gaia_id"] not in (None, "") else None,
                teff=safe_float(row["teff"]),
                distance_ly=safe_float(row["distance_ly"]),
                tmag=safe_float(row["tmag"]),
                stellar_radius=safe_float(row["stellar_radius"]),
                stellar_logg=safe_float(row["stellar_logg"]),
                period=float(row["best_period"]),
                duration=float(row["duration"]),
                depth=float(row["depth"]),
                t0=float(row["transit_time"]),
                power=safe_float(row["power"]),
                planet_radius_earth=safe_float(row["planet_radius_earth"]),
                lightcurve_dir=row["lightcurve_dir"],
                transit_snr=safe_float(row["transit_snr"]),
                transit_count=safe_int(row["transit_count"]),
                n_in_transit=safe_int(row["n_in_transit"]),
                duration_fraction=safe_float(row["duration_fraction"]),
                oe_ratio=safe_float(row["oe_ratio"]),
                sec_ratio=safe_float(row["sec_ratio"]),
                fp_oe_flag=safe_int(row["fp_oe_flag"]),
                fp_sec_flag=safe_int(row["fp_sec_flag"]),
                fp_baseline_flag=safe_int(row["fp_baseline_flag"]),
                fp_baseline_std_flag=safe_int(row["fp_baseline_std_flag"]),
                fp_scatter_flag=safe_int(row["fp_scatter_flag"]),
                is_fp=safe_int(row["is_fp"]),
                hz_status=str(row["hz_status"] or "UNKNOWN"),
                hz_class=str(row["hz_class"] or "UNKNOWN"),
                sector_count=safe_int(row["sector_count"], None),
                clean_sector_count=safe_int(row["clean_sector_count"], None),
                visible_transits=safe_int(row["visible_transits"], None),
                spc_class=str(row["spc_class"] or "") or None,
                status=str(row["status"] or "") or None,
                revisit_priority=safe_float(row["revisit_priority"]),
                notes=str(row["notes"] or "") or None,
            )
        )
    return candidates


def lightcurve_path(candidate: Candidate) -> Path:
    if candidate.lightcurve_dir:
        path = Path(candidate.lightcurve_dir)
        if path.exists():
            return path
    return LIGHTCURVE_ROOT / f"TIC_{candidate.tic}" / f"TIC_{candidate.tic}_lightcurve.csv"


def load_lightcurve(candidate: Candidate) -> dict[str, np.ndarray | None]:
    path = lightcurve_path(candidate)
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path)
    time_col = pick_col(list(df.columns), ("time", "btjd", "bjd"))
    flux_col = pick_col(list(df.columns), ("flux", "pdcsap_flux", "sap_flux"))
    if not time_col or not flux_col:
        raise ValueError(f"missing time/flux columns in {path}")

    time_arr = pd.to_numeric(df[time_col], errors="coerce").to_numpy(dtype=float)
    flux_arr = pd.to_numeric(df[flux_col], errors="coerce").to_numpy(dtype=float)
    sap_col = pick_col(list(df.columns), ("sap_flux", "SAP_FLUX"))
    pdc_col = pick_col(list(df.columns), ("pdcsap_flux", "PDCSAP_FLUX"))
    sap_arr = pd.to_numeric(df[sap_col], errors="coerce").to_numpy(dtype=float) if sap_col else None
    pdc_arr = pd.to_numeric(df[pdc_col], errors="coerce").to_numpy(dtype=float) if pdc_col else None

    mask = np.isfinite(time_arr) & np.isfinite(flux_arr)
    time_arr = time_arr[mask]
    flux_arr = flux_arr[mask]
    if sap_arr is not None:
        sap_arr = sap_arr[mask]
    if pdc_arr is not None:
        pdc_arr = pdc_arr[mask]
    if len(time_arr) < 20:
        raise ValueError(f"too few finite points in {path}")

    med = float(np.nanmedian(flux_arr))
    std = float(np.nanstd(flux_arr))
    if np.isfinite(std) and std > 0:
        keep = np.abs(flux_arr - med) < 7.0 * std
        time_arr = time_arr[keep]
        flux_arr = flux_arr[keep]
        if sap_arr is not None:
            sap_arr = sap_arr[keep]
        if pdc_arr is not None:
            pdc_arr = pdc_arr[keep]

    order = np.argsort(time_arr)
    time_arr = time_arr[order]
    flux_arr = normalize_flux(flux_arr[order])
    if sap_arr is not None:
        sap_arr = normalize_flux(sap_arr[order])
    if pdc_arr is not None:
        pdc_arr = normalize_flux(pdc_arr[order])

    return {"time": time_arr, "flux": flux_arr, "sap_flux": sap_arr, "pdcsap_flux": pdc_arr}


def infer_segments(time_arr: np.ndarray) -> list[np.ndarray]:
    if len(time_arr) == 0:
        return []
    gaps = np.where(np.diff(time_arr) > SECTOR_GAP_DAYS)[0]
    starts = [0] + [int(i + 1) for i in gaps]
    ends = [int(i + 1) for i in gaps] + [len(time_arr)]
    return [np.arange(start, end) for start, end in zip(starts, ends) if end > start]


def gap_fraction(time_arr: np.ndarray) -> float:
    if len(time_arr) < 3:
        return 1.0
    diffs = np.diff(np.sort(time_arr))
    diffs = diffs[np.isfinite(diffs) & (diffs > 0)]
    if len(diffs) == 0:
        return 1.0
    cadence = float(np.nanmedian(diffs))
    span = float(np.nanmax(time_arr) - np.nanmin(time_arr))
    if not np.isfinite(cadence) or cadence <= 0 or span <= 0:
        return 1.0
    expected = max(int(round(span / cadence)) + 1, len(time_arr))
    return float(np.clip(1.0 - len(time_arr) / expected, 0.0, 1.0))


def expected_events_for_segment(
    time_arr: np.ndarray,
    period: float,
    t0: float,
    duration: float,
) -> list[dict[str, Any]]:
    if len(time_arr) == 0 or period <= 0:
        return []
    t_min = float(np.nanmin(time_arr))
    t_max = float(np.nanmax(time_arr))
    half = max(duration / 2.0, 1e-6)
    first = int(math.ceil((t_min - t0) / period)) - 1
    last = int(math.floor((t_max - t0) / period)) + 1
    events: list[dict[str, Any]] = []
    for epoch in range(first, last + 1):
        center = t0 + epoch * period
        if t_min <= center <= t_max:
            complete = bool(t_min <= center - half and center + half <= t_max)
            edge = bool(
                not complete
                or abs(center - t_min) <= max(duration, 0.1)
                or abs(t_max - center) <= max(duration, 0.1)
            )
            events.append(
                {
                    "epoch": epoch,
                    "expected_time": float(center),
                    "complete_by_time": complete,
                    "sector_edge": edge,
                }
            )
    return events


def measure_event(
    time_arr: np.ndarray,
    flux_arr: np.ndarray,
    center: float,
    duration: float,
) -> dict[str, Any]:
    half = max(float(duration) / 2.0, 1e-6)
    local_window = max(4.0 * float(duration), LOCAL_WINDOW_MIN_DAYS)
    local = np.abs(time_arr - center) <= local_window
    if int(np.count_nonzero(local)) < 8:
        return {
            "depth_ppt": float("nan"),
            "local_snr": float("nan"),
            "duration_estimate": float("nan"),
            "timing_offset_days": float("nan"),
            "n_in": 0,
            "n_out": 0,
            "visible": False,
        }
    dt = time_arr[local] - center
    fl = flux_arr[local]
    inside = np.abs(dt) <= half
    outside = (np.abs(dt) >= 1.5 * half) & (np.abs(dt) <= local_window)
    n_in = int(np.count_nonzero(inside))
    n_out = int(np.count_nonzero(outside))
    if n_in < 3 or n_out < 5:
        return {
            "depth_ppt": float("nan"),
            "local_snr": float("nan"),
            "duration_estimate": float("nan"),
            "timing_offset_days": float("nan"),
            "n_in": n_in,
            "n_out": n_out,
            "visible": False,
        }
    baseline = float(np.nanmedian(fl[outside]))
    in_median = float(np.nanmedian(fl[inside]))
    depth = max(0.0, baseline - in_median)
    scatter_ppt = robust_scatter((fl[outside] - baseline) * 1000.0)
    snr = depth * 1000.0 / scatter_ppt * math.sqrt(n_in) if scatter_ppt > 0 else float("nan")

    inside_times = dt[inside]
    inside_flux = fl[inside]
    timing_offset = float("nan")
    if len(inside_flux) > 0 and np.any(np.isfinite(inside_flux)):
        timing_offset = float(inside_times[int(np.nanargmin(inside_flux))])

    duration_estimate = float("nan")
    if depth > 0:
        threshold = baseline - 0.5 * depth
        below = (fl < threshold) & (np.abs(dt) <= 1.5 * duration)
        if int(np.count_nonzero(below)) >= 2:
            duration_estimate = float(np.nanmax(dt[below]) - np.nanmin(dt[below]))

    visible = bool(np.isfinite(snr) and snr >= VISIBLE_TRANSIT_MIN_SNR and depth > 0)
    return {
        "depth_ppt": float(depth * 1000.0),
        "local_snr": float(snr),
        "duration_estimate": duration_estimate,
        "timing_offset_days": timing_offset,
        "n_in": n_in,
        "n_out": n_out,
        "visible": visible,
    }


def segment_for_time(center: float, segment_spans: list[tuple[int, float, float]]) -> int:
    for sector, start, end in segment_spans:
        if start <= center <= end:
            return sector
    return 0


def compute_ephemeris_coverage(
    candidate: Candidate,
    time_arr: np.ndarray,
    flux_arr: np.ndarray,
    segment_spans: list[tuple[int, float, float]],
) -> dict[str, Any]:
    if len(time_arr) == 0 or candidate.period <= 0:
        return {
            "event_rows": [],
            "n_ephemeris_windows": 0,
            "n_observed_transit_windows": 0,
            "n_visible_transits": 0,
            "n_driver_events": 0,
            "observed_fraction": 0.0,
            "visible_fraction": 0.0,
            "flags": ["NO_EPHEMERIS_COVERAGE"],
        }

    t_min = float(np.nanmin(time_arr))
    t_max = float(np.nanmax(time_arr))
    first = int(math.ceil((t_min - candidate.t0) / candidate.period))
    last = int(math.floor((t_max - candidate.t0) / candidate.period))
    event_rows: list[dict[str, Any]] = []
    flags: list[str] = []

    for epoch in range(first, last + 1):
        center = candidate.t0 + epoch * candidate.period
        metric = measure_event(time_arr, flux_arr, center, candidate.duration)
        observed_window = bool(metric["n_in"] >= 3 and metric["n_out"] >= 5)
        sector = segment_for_time(center, segment_spans)
        complete_by_time = bool(observed_window)
        event_rows.append(
            {
                "TIC": candidate.tic,
                "candidate_id": candidate.candidate_id,
                "sector": sector,
                "epoch": epoch,
                "expected_time": float(center),
                "complete_by_time": complete_by_time,
                "sector_edge": bool(sector == 0 or not observed_window),
                "observed_window": int(observed_window),
                **metric,
            }
        )

    n_ephemeris = len(event_rows)
    n_observed = int(sum(1 for row in event_rows if row["observed_window"]))
    n_visible = int(sum(1 for row in event_rows if row["visible"]))
    n_driver_events = int(
        sum(
            1
            for row in event_rows
            if np.isfinite(row["local_snr"]) and float(row["local_snr"]) >= VISIBLE_TRANSIT_MIN_SNR
        )
    )
    observed_fraction = n_observed / n_ephemeris if n_ephemeris else 0.0
    visible_fraction = n_visible / n_ephemeris if n_ephemeris else 0.0

    if n_observed < MIN_OBSERVED_TRANSIT_WINDOWS:
        flags.append("SINGLE_OBSERVED_TRANSIT" if n_observed == 1 else "NO_OBSERVED_TRANSIT_WINDOWS")
        flags.append("NEEDS_MORE_TESS_DATA")
    if n_visible < 2:
        flags.append("FEW_VISIBLE_TRANSITS")
    if n_driver_events <= FEW_EVENT_LIMIT:
        flags.append("ONLY_2_3_EVENTS_DRIVE_SIGNAL")
    if n_ephemeris >= 4 and observed_fraction < LOW_EPHEMERIS_COVERAGE_RATIO:
        flags.append("EPHEMERIS_COVERAGE_SPARSE")

    return {
        "event_rows": event_rows,
        "n_ephemeris_windows": n_ephemeris,
        "n_observed_transit_windows": n_observed,
        "n_visible_transits": n_visible,
        "n_driver_events": n_driver_events,
        "observed_fraction": observed_fraction,
        "visible_fraction": visible_fraction,
        "flags": flags,
    }


def compute_data_window(
    candidate: Candidate,
    time_arr: np.ndarray,
    flux_arr: np.ndarray,
) -> dict[str, Any]:
    segment_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    total_expected = 0
    total_visible = 0
    total_complete = 0
    segment_spans: list[tuple[int, float, float]] = []

    for sector_idx, indices in enumerate(infer_segments(time_arr), start=1):
        st = time_arr[indices]
        sf = flux_arr[indices]
        segment_spans.append((sector_idx, float(np.nanmin(st)), float(np.nanmax(st))))
        events = expected_events_for_segment(st, candidate.period, candidate.t0, candidate.duration)
        measured: list[dict[str, Any]] = []
        for event in events:
            metric = measure_event(st, sf, float(event["expected_time"]), candidate.duration)
            row = {
                "TIC": candidate.tic,
                "candidate_id": candidate.candidate_id,
                "sector": sector_idx,
                **event,
                **metric,
            }
            measured.append(row)
            event_rows.append(row)
        n_expected = len(events)
        n_visible = int(sum(1 for row in measured if row["visible"]))
        n_complete = int(
            sum(
                1
                for row in measured
                if row["complete_by_time"] and row["n_in"] >= 3 and row["n_out"] >= 5
            )
        )
        total_expected += n_expected
        total_visible += n_visible
        total_complete += n_complete
        segment_rows.append(
            {
                "TIC": candidate.tic,
                "candidate_id": candidate.candidate_id,
                "sector": sector_idx,
                "time_start": float(np.nanmin(st)),
                "time_end": float(np.nanmax(st)),
                "n_points": int(len(st)),
                "n_expected_transits": n_expected,
                "n_visible_transits": n_visible,
                "n_complete_transits": n_complete,
                "gap_fraction": gap_fraction(st),
                "transit_at_sector_edge": bool(any(row["sector_edge"] for row in measured)),
                "median_snr": finite_median([row["local_snr"] for row in measured]),
                "median_depth_ppt": finite_median([row["depth_ppt"] for row in measured]),
            }
        )

    coverage = compute_ephemeris_coverage(candidate, time_arr, flux_arr, segment_spans)
    if coverage["event_rows"]:
        event_rows = coverage["event_rows"]
        total_expected = int(coverage["n_ephemeris_windows"])
        total_visible = int(coverage["n_visible_transits"])
        total_complete = int(coverage["n_observed_transit_windows"])

    total_points = int(len(time_arr))
    median_gap = (
        float(np.nanmedian([row["gap_fraction"] for row in segment_rows]))
        if segment_rows
        else 1.0
    )
    snrs = [row["local_snr"] for row in event_rows if np.isfinite(row["local_snr"])]
    median_snr = float(np.nanmedian(snrs)) if snrs else float("nan")
    visible_ratio = total_visible / total_expected if total_expected else 0.0
    complete_ratio = total_complete / total_expected if total_expected else 0.0
    visible_sectors = len([row for row in segment_rows if row["n_visible_transits"] > 0])

    if total_expected == 0:
        score = min(total_points / 300.0, 1.0) * 20.0
    else:
        points_score = min(total_points / max(300.0, total_expected * 20.0), 1.0) * 15.0
        visible_score = visible_ratio * 35.0
        complete_score = complete_ratio * 15.0
        gap_score = max(0.0, 1.0 - median_gap) * 15.0
        snr_score = min(max(median_snr, 0.0) / 8.0, 1.0) * 15.0 if np.isfinite(median_snr) else 0.0
        sector_score = min(visible_sectors / 2.0, 1.0) * 5.0
        score = points_score + visible_score + complete_score + gap_score + snr_score + sector_score

    if coverage["n_observed_transit_windows"] < MIN_OBSERVED_TRANSIT_WINDOWS:
        score = min(score, 30.0)
    elif coverage["n_driver_events"] <= FEW_EVENT_LIMIT and coverage["n_ephemeris_windows"] >= 4:
        score = min(score, 45.0)
    if coverage["n_ephemeris_windows"] >= 4 and coverage["observed_fraction"] < LOW_EPHEMERIS_COVERAGE_RATIO:
        score = min(score, 40.0)

    flags: list[str] = []
    if score < 55:
        flags.append("WEAK_DATA_WINDOW")
    if total_expected < 2 or total_visible < 2:
        flags.append("NEEDS_MORE_TESS_DATA")
    if any(row["transit_at_sector_edge"] for row in segment_rows):
        flags.append("TRANSIT_AT_SECTOR_EDGE")
    if np.isfinite(median_gap) and median_gap > 0.45:
        flags.append("DATA_GAPS_HIGH")
    flags.extend(coverage["flags"])

    return {
        "score": clip_score(score),
        "flags": flags,
        "sector_rows": segment_rows,
        "event_rows": event_rows,
        "n_points": total_points,
        "n_expected_transits": total_expected,
        "n_visible_transits": total_visible,
        "n_complete_transits": total_complete,
        "n_ephemeris_windows": int(coverage["n_ephemeris_windows"]),
        "n_observed_transit_windows": int(coverage["n_observed_transit_windows"]),
        "n_driver_events": int(coverage["n_driver_events"]),
        "ephemeris_observed_fraction": float(coverage["observed_fraction"]),
        "median_snr": median_snr,
        "median_depth_ppt": finite_median([row["depth_ppt"] for row in event_rows]),
    }


def compute_transit_stability(
    candidate: Candidate,
    data_window: dict[str, Any],
) -> dict[str, Any]:
    event_rows = data_window["event_rows"]
    visible = [row for row in event_rows if row["visible"]]
    depths = np.asarray([row["depth_ppt"] for row in visible if np.isfinite(row["depth_ppt"])], dtype=float)
    durations = np.asarray(
        [row["duration_estimate"] for row in visible if np.isfinite(row["duration_estimate"])],
        dtype=float,
    )
    timings = np.asarray(
        [row["timing_offset_days"] for row in visible if np.isfinite(row["timing_offset_days"])],
        dtype=float,
    )
    flags: list[str] = []
    total_visible = len(visible)

    if total_visible < 2:
        flags.append("WEAK_DATA_WINDOW")
        return {
            "score": 35.0 if total_visible == 1 else 15.0,
            "flags": flags,
            "depth_cv": float("nan"),
            "duration_cv": float("nan"),
            "median_abs_timing_offset_days": float("nan"),
        }

    depth_cv = float("nan")
    if len(depths) >= 2 and abs(float(np.nanmedian(depths))) > 1e-6:
        depth_cv = robust_scatter(depths) / abs(float(np.nanmedian(depths)))
    duration_cv = float("nan")
    if len(durations) >= 2 and abs(float(np.nanmedian(durations))) > 1e-6:
        duration_cv = robust_scatter(durations) / abs(float(np.nanmedian(durations)))
    median_abs_timing = (
        float(np.nanmedian(np.abs(timings))) if len(timings) >= 2 else float("nan")
    )

    depth_score = 35.0
    if np.isfinite(depth_cv):
        depth_score = max(0.0, 35.0 * (1.0 - min(depth_cv / 0.6, 1.0)))
        if depth_cv > 0.55:
            flags.append("DEPTH_UNSTABLE")

    duration_score = 15.0
    if np.isfinite(duration_cv):
        duration_score = max(0.0, 15.0 * (1.0 - min(duration_cv / 0.7, 1.0)))
        if duration_cv > 0.65:
            flags.append("DURATION_UNSTABLE")

    timing_score = 25.0
    if np.isfinite(median_abs_timing):
        threshold = max(candidate.duration * 0.5, 0.02)
        timing_score = max(0.0, 25.0 * (1.0 - min(median_abs_timing / threshold, 1.0)))
        if median_abs_timing > max(candidate.duration * 0.35, 0.03):
            flags.append("EPHEMERIS_UNSTABLE")

    visible_by_sector = Counter(int(row["sector"]) for row in visible)
    sectors_with_expected = len(
        [row for row in data_window["sector_rows"] if row["n_expected_transits"] > 0]
    )
    max_sector_fraction = max(visible_by_sector.values()) / total_visible if visible_by_sector else 1.0
    sector_score = 15.0
    if sectors_with_expected > 1 and (len(visible_by_sector) == 1 or max_sector_fraction >= 0.8):
        sector_score = 3.0
        flags.append("SINGLE_SECTOR_DOMINATED")
    elif len(visible_by_sector) >= 2:
        sector_score = 20.0

    visible_score = min(total_visible / 3.0, 1.0) * 10.0
    score = depth_score + duration_score + timing_score + sector_score + visible_score
    return {
        "score": clip_score(score),
        "flags": flags,
        "depth_cv": depth_cv,
        "duration_cv": duration_cv,
        "median_abs_timing_offset_days": median_abs_timing,
    }


def folded_signal(
    time_arr: np.ndarray,
    flux_arr: np.ndarray,
    candidate: Candidate,
) -> dict[str, float | int]:
    finite = np.isfinite(time_arr) & np.isfinite(flux_arr)
    t = time_arr[finite]
    f = normalize_flux(flux_arr[finite])
    if len(t) < 20:
        return {"depth_ppt": float("nan"), "snr": float("nan"), "n_in": 0, "n_out": 0}
    phase = centered_phase_days(t, candidate.period, candidate.t0)
    half = candidate.duration / 2.0
    inside = np.abs(phase) <= half
    outside = np.abs(phase) >= 1.5 * candidate.duration
    n_in = int(np.count_nonzero(inside))
    n_out = int(np.count_nonzero(outside))
    if n_in < 4 or n_out < 12:
        return {"depth_ppt": float("nan"), "snr": float("nan"), "n_in": n_in, "n_out": n_out}
    baseline = float(np.nanmedian(f[outside]))
    depth = max(0.0, baseline - float(np.nanmedian(f[inside])))
    scatter_ppt = robust_scatter((f[outside] - baseline) * 1000.0)
    snr = depth * 1000.0 / scatter_ppt * math.sqrt(n_in) if scatter_ppt > 0 else float("nan")
    return {"depth_ppt": depth * 1000.0, "snr": snr, "n_in": n_in, "n_out": n_out}


def local_bls(
    time_arr: np.ndarray,
    flux_arr: np.ndarray,
    candidate: Candidate,
) -> dict[str, float]:
    finite = np.isfinite(time_arr) & np.isfinite(flux_arr)
    t = time_arr[finite]
    f = normalize_flux(flux_arr[finite])
    if len(t) < 50:
        return {"period": float("nan"), "power": float("nan"), "depth": float("nan")}
    if len(t) > 25000:
        idx = np.linspace(0, len(t) - 1, 25000, dtype=int)
        t = t[idx]
        f = f[idx]
    lo = max(candidate.period * 0.97, 0.05)
    hi = candidate.period * 1.03
    periods = np.linspace(lo, hi, SAP_PDC_LOCAL_BLS_PERIODS)
    durations = np.asarray([max(candidate.duration, 0.01)], dtype=float)
    try:
        result = BoxLeastSquares(t, f).power(periods, durations)
        idx = int(np.nanargmax(result.power))
        depth = float(result.depth[idx]) if hasattr(result, "depth") else float("nan")
        return {
            "period": float(result.period[idx]),
            "power": float(result.power[idx]),
            "depth": depth,
        }
    except Exception:
        return {"period": float("nan"), "power": float("nan"), "depth": float("nan")}


def compute_sap_pdcsap(
    candidate: Candidate,
    time_arr: np.ndarray,
    sap_flux: np.ndarray | None,
    pdc_flux: np.ndarray | None,
) -> dict[str, Any]:
    flags: list[str] = []
    if sap_flux is None and pdc_flux is None:
        return {
            "score": 45.0,
            "flags": ["SAP_PDCSAP_UNAVAILABLE"],
            "sap_depth_ppt": float("nan"),
            "pdcsap_depth_ppt": float("nan"),
            "sap_snr": float("nan"),
            "pdcsap_snr": float("nan"),
            "sap_period": float("nan"),
            "pdcsap_period": float("nan"),
        }
    if sap_flux is None or pdc_flux is None:
        flags.append("SAP_PDCSAP_PARTIAL")
        flux = sap_flux if sap_flux is not None else pdc_flux
        sig = folded_signal(time_arr, flux, candidate)  # type: ignore[arg-type]
        signal = bool(np.isfinite(sig["snr"]) and float(sig["snr"]) >= 4.0)
        return {
            "score": 55.0 if signal else 45.0,
            "flags": flags,
            "sap_depth_ppt": float(sig["depth_ppt"]) if sap_flux is not None else float("nan"),
            "pdcsap_depth_ppt": float(sig["depth_ppt"]) if pdc_flux is not None else float("nan"),
            "sap_snr": float(sig["snr"]) if sap_flux is not None else float("nan"),
            "pdcsap_snr": float(sig["snr"]) if pdc_flux is not None else float("nan"),
            "sap_period": float("nan"),
            "pdcsap_period": float("nan"),
        }

    sap_sig = folded_signal(time_arr, sap_flux, candidate)
    pdc_sig = folded_signal(time_arr, pdc_flux, candidate)
    sap_bls = local_bls(time_arr, sap_flux, candidate)
    pdc_bls = local_bls(time_arr, pdc_flux, candidate)
    sap_signal = bool(np.isfinite(sap_sig["snr"]) and float(sap_sig["snr"]) >= 4.0)
    pdc_signal = bool(np.isfinite(pdc_sig["snr"]) and float(pdc_sig["snr"]) >= 4.0)
    period_close = (
        np.isfinite(sap_bls["period"])
        and np.isfinite(pdc_bls["period"])
        and abs(float(sap_bls["period"]) - float(pdc_bls["period"])) / candidate.period <= 0.02
    )
    depth_ratio = float("nan")
    if np.isfinite(sap_sig["depth_ppt"]) and np.isfinite(pdc_sig["depth_ppt"]) and pdc_sig["depth_ppt"]:
        depth_ratio = float(sap_sig["depth_ppt"]) / max(float(pdc_sig["depth_ppt"]), 1e-9)
    depth_close = bool(np.isfinite(depth_ratio) and 0.45 <= depth_ratio <= 2.2)

    if pdc_signal and not sap_signal:
        flags.append("PDCSAP_ONLY_SIGNAL")
        score = 30.0
    elif sap_signal and not pdc_signal:
        flags.append("SAP_ONLY_SIGNAL")
        score = 35.0
    elif sap_signal and pdc_signal and period_close and depth_close:
        score = 100.0
    elif sap_signal and pdc_signal:
        flags.append("SAP_PDCSAP_MISMATCH")
        score = 55.0
    else:
        flags.append("SAP_PDCSAP_MISMATCH")
        score = 40.0

    return {
        "score": clip_score(score),
        "flags": flags,
        "sap_depth_ppt": sap_sig["depth_ppt"],
        "pdcsap_depth_ppt": pdc_sig["depth_ppt"],
        "sap_snr": sap_sig["snr"],
        "pdcsap_snr": pdc_sig["snr"],
        "sap_period": sap_bls["period"],
        "pdcsap_period": pdc_bls["period"],
        "depth_ratio": depth_ratio,
    }


def compute_odd_even(candidate: Candidate, event_rows: list[dict[str, Any]]) -> dict[str, Any]:
    flags: list[str] = []
    usable = [row for row in event_rows if np.isfinite(row["depth_ppt"])]
    odd = [row for row in usable if int(row["epoch"]) % 2 != 0]
    even = [row for row in usable if int(row["epoch"]) % 2 == 0]
    if len(odd) < 1 or len(even) < 1:
        flags.append("ODD_EVEN_INSUFFICIENT")
        return {
            "score": 40.0 if len(usable) < 2 else 55.0,
            "flags": flags,
            "odd_depth_ppt": float("nan"),
            "even_depth_ppt": float("nan"),
            "odd_even_ratio": float("nan"),
            "odd_even_timing_delta_days": float("nan"),
        }

    odd_depth = float(np.nanmedian([row["depth_ppt"] for row in odd]))
    even_depth = float(np.nanmedian([row["depth_ppt"] for row in even]))
    ratio = odd_depth / max(even_depth, 1e-9) if even_depth > 0 else float("nan")
    odd_timing = [row["timing_offset_days"] for row in odd if np.isfinite(row["timing_offset_days"])]
    even_timing = [row["timing_offset_days"] for row in even if np.isfinite(row["timing_offset_days"])]
    timing_delta = (
        abs(float(np.nanmedian(odd_timing)) - float(np.nanmedian(even_timing)))
        if odd_timing and even_timing
        else float("nan")
    )

    mismatch = bool(
        (np.isfinite(ratio) and (ratio < 0.5 or ratio > 2.0))
        or (np.isfinite(timing_delta) and timing_delta > max(candidate.duration * 0.45, 0.03))
    )
    score = 100.0
    if mismatch:
        flags.append("ODD_EVEN_MISMATCH")
        score = 35.0
        if (np.isfinite(ratio) and (ratio < 0.35 or ratio > 2.8)) or candidate.fp_sec_flag:
            flags.append("EB_RISK")
            score = 20.0
    if candidate.fp_oe_flag and candidate.fp_sec_flag:
        flags.append("EB_RISK")
        score = min(score, 20.0)
    elif candidate.fp_oe_flag:
        flags.append("ODD_EVEN_MISMATCH")
        score = min(score, 45.0)

    return {
        "score": clip_score(score),
        "flags": flags,
        "odd_depth_ppt": odd_depth,
        "even_depth_ppt": even_depth,
        "odd_even_ratio": ratio,
        "odd_even_timing_delta_days": timing_delta,
    }


def acf_rotation_period(time_arr: np.ndarray, flux_arr: np.ndarray, min_period: float, max_period: float) -> tuple[float, float]:
    if len(time_arr) < 50:
        return float("nan"), float("nan")
    span = float(np.nanmax(time_arr) - np.nanmin(time_arr))
    cadence = float(np.nanmedian(np.diff(np.sort(time_arr))))
    if not np.isfinite(cadence) or cadence <= 0 or span <= 0:
        return float("nan"), float("nan")
    dt = max(cadence, span / 50000.0)
    grid = np.arange(float(np.nanmin(time_arr)), float(np.nanmax(time_arr)), dt)
    if len(grid) < 50:
        return float("nan"), float("nan")
    y = np.interp(grid, time_arr, flux_arr)
    y = y - float(np.nanmedian(y))
    std = float(np.nanstd(y))
    if not np.isfinite(std) or std <= 0:
        return float("nan"), float("nan")
    y = y / std
    n = len(y)
    fft = np.fft.rfft(y, n=2 * n)
    acf = np.fft.irfft(fft * np.conjugate(fft), n=2 * n)[:n]
    if acf[0] == 0:
        return float("nan"), float("nan")
    acf = acf / acf[0]
    lags = np.arange(n) * dt
    mask = (lags >= min_period) & (lags <= max_period)
    if int(np.count_nonzero(mask)) < 5:
        return float("nan"), float("nan")
    try:
        from scipy.signal import find_peaks

        local_acf = acf[mask]
        local_lags = lags[mask]
        peaks, props = find_peaks(local_acf, height=0.08)
        if len(peaks) == 0:
            return float("nan"), float("nan")
        best_idx = peaks[int(np.argmax(props["peak_heights"]))]
        return float(local_lags[best_idx]), float(local_acf[best_idx])
    except Exception:
        local_acf = acf[mask]
        local_lags = lags[mask]
        best = int(np.nanargmax(local_acf))
        if not np.isfinite(local_acf[best]) or local_acf[best] < 0.08:
            return float("nan"), float("nan")
        return float(local_lags[best]), float(local_acf[best])


def is_rotation_alias(rotation_period: float | None, planet_period: float) -> bool:
    if rotation_period is None or not np.isfinite(rotation_period) or rotation_period <= 0:
        return False
    for factor in (1.0, 2.0, 0.5, 3.0, 1.0 / 3.0):
        target = planet_period * factor
        if target > 0 and abs(rotation_period - target) / target <= 0.06:
            return True
    return False


def compute_activity(
    candidate: Candidate,
    time_arr: np.ndarray,
    flux_arr: np.ndarray,
) -> dict[str, Any]:
    flags: list[str] = []
    phase = centered_phase_days(time_arr, candidate.period, candidate.t0)
    oot = np.abs(phase) > max(1.5 * candidate.duration, 0.05)
    if int(np.count_nonzero(oot)) >= 50:
        t = time_arr[oot]
        f = flux_arr[oot]
    else:
        t = time_arr
        f = flux_arr
    finite = np.isfinite(t) & np.isfinite(f)
    t = t[finite]
    f = f[finite]
    if len(t) < 80:
        return {
            "score": 70.0,
            "flags": ["ACTIVITY_UNMEASURED"],
            "rotation_period_ls": float("nan"),
            "rotation_period_acf": float("nan"),
            "rotation_power": float("nan"),
            "acf_power": float("nan"),
        }
    if len(t) > ACTIVITY_MAX_POINTS:
        idx = np.linspace(0, len(t) - 1, ACTIVITY_MAX_POINTS, dtype=int)
        t = t[idx]
        f = f[idx]
    y = normalize_flux(f) - 1.0
    scatter = robust_scatter(y)
    if np.isfinite(scatter) and scatter > 0:
        keep = np.abs(y - np.nanmedian(y)) < 6.0 * scatter
        t = t[keep]
        y = y[keep]
    baseline = float(np.nanmax(t) - np.nanmin(t))
    if baseline < 2.0:
        return {
            "score": 70.0,
            "flags": ["ACTIVITY_BASELINE_SHORT"],
            "rotation_period_ls": float("nan"),
            "rotation_period_acf": float("nan"),
            "rotation_power": float("nan"),
            "acf_power": float("nan"),
        }

    min_period = 0.2
    max_period = min(100.0, max(1.0, baseline / 1.5))
    if max_period <= min_period:
        max_period = baseline
    try:
        freqs = np.linspace(1.0 / max_period, 1.0 / min_period, 5000)
        power = LombScargle(t, y).power(freqs, normalization="standard")
        best = int(np.nanargmax(power))
        rotation_period_ls = float(1.0 / freqs[best])
        rotation_power = float(power[best])
    except Exception:
        rotation_period_ls = float("nan")
        rotation_power = float("nan")

    rotation_period_acf, acf_power = acf_rotation_period(t, y, min_period, max_period)
    alias = is_rotation_alias(rotation_period_ls, candidate.period) or is_rotation_alias(
        rotation_period_acf, candidate.period
    )
    active = bool(
        (np.isfinite(rotation_power) and rotation_power > 0.22)
        or (np.isfinite(acf_power) and acf_power > 0.22)
    )
    ls_acf_agree = bool(
        np.isfinite(rotation_period_ls)
        and np.isfinite(rotation_period_acf)
        and abs(rotation_period_ls - rotation_period_acf)
        / max(rotation_period_ls, rotation_period_acf)
        < 0.2
    )

    score = 100.0
    if active:
        flags.append("ACTIVE_STAR_RISK")
        score -= 25.0
    if ls_acf_agree and active:
        score -= 10.0
    if alias:
        flags.append("ROTATION_ALIAS_RISK")
        score -= 35.0
    if active and alias:
        flags.append("ACTIVITY_CONFUSED")
        score -= 10.0

    return {
        "score": clip_score(score),
        "flags": flags,
        "rotation_period_ls": rotation_period_ls,
        "rotation_period_acf": rotation_period_acf,
        "rotation_power": rotation_power,
        "acf_power": acf_power,
    }


def stellar_class(teff: float | None) -> str:
    if teff is None or not np.isfinite(teff):
        return "UNKNOWN"
    if teff < 3900:
        return "M"
    if teff < 5300:
        return "K"
    if teff < 6000:
        return "G"
    return "HOT"


def compute_scientific_value(candidate: Candidate, n_visible: int, clean_sectors: int | None) -> dict[str, Any]:
    score = 0.0
    reasons: list[str] = []
    distance = candidate.distance_ly
    if distance is not None:
        if distance <= 50:
            score += 18
            reasons.append("nearby")
        elif distance <= 100:
            score += 15
            reasons.append("nearby_100ly")
        elif distance <= 150:
            score += 12
            reasons.append("followup_distance")
        elif distance <= 500:
            score += 6

    sclass = stellar_class(candidate.teff)
    if sclass == "M":
        score += 18
        reasons.append("M_star")
    elif sclass == "K":
        score += 16
        reasons.append("K_star")
    elif sclass == "G":
        score += 10
        reasons.append("G_star")

    if candidate.teff is not None and 3900 <= candidate.teff <= 5300:
        score += 10
    if candidate.stellar_radius is not None and 0.45 <= candidate.stellar_radius <= 0.95:
        score += 8

    hz = str(candidate.hz_class or candidate.hz_status or "UNKNOWN")
    if hz == "KONSERVATIVE_HZ":
        score += 24
        reasons.append("conservative_HZ")
    elif hz == "OPT_HZ_INNEN":
        score += 18
        reasons.append("optimistic_HZ_inner")
    elif hz == "OPT_HZ_AUSSEN":
        score += 10
        reasons.append("optimistic_HZ_outer")

    rp = candidate.planet_radius_earth
    if rp is not None:
        if rp <= 1.6:
            score += 18
            reasons.append("small_planet_radius")
        elif rp <= 2.0:
            score += 16
            reasons.append("super_Earth_radius")
        elif rp <= 4.0:
            score += 10
            reasons.append("sub_Neptune_radius")

    score += min(max(n_visible, 0), 5) * 3.0
    if clean_sectors is not None:
        score += min(max(clean_sectors, 0), 3) * 3.0
    if candidate.tmag is not None:
        if candidate.tmag <= 11:
            score += 8
            reasons.append("bright_TESS_target")
        elif candidate.tmag <= 13:
            score += 5
    return {"score": clip_score(score), "reasons": reasons, "stellar_class": sclass}


def current_btjd() -> float:
    if Time is None:
        return float("nan")
    return float(Time(datetime.now(timezone.utc)).tdb.jd - 2457000.0)


def next_transits(candidate: Candidate, count: int = 8) -> list[dict[str, Any]]:
    now = current_btjd()
    if not np.isfinite(now) or candidate.period <= 0:
        return []
    first_epoch = int(math.ceil((now - candidate.t0) / candidate.period))
    rows: list[dict[str, Any]] = []
    for epoch in range(first_epoch, first_epoch + count):
        center = candidate.t0 + epoch * candidate.period
        item = {
            "epoch": epoch,
            "btjd": round(float(center), 6),
            "window_start_btjd": round(float(center - candidate.duration / 2.0), 6),
            "window_end_btjd": round(float(center + candidate.duration / 2.0), 6),
        }
        if Time is not None:
            try:
                item["utc"] = Time(center + 2457000.0, format="jd", scale="tdb").utc.iso
            except Exception:
                pass
        rows.append(item)
    return rows


def compute_followup(
    candidate: Candidate,
    preliminary_evidence: float,
    scientific_score: float,
    data_window_score: float,
) -> dict[str, Any]:
    transits = next_transits(candidate)
    now = current_btjd()
    upcoming_90 = 0
    if np.isfinite(now):
        upcoming_90 = int(sum(1 for row in transits if float(row["btjd"]) <= now + 90.0))
    frequency_score = min(upcoming_90 / 5.0, 1.0) * 20.0
    brightness_score = 0.0
    if candidate.tmag is not None:
        if candidate.tmag <= 11:
            brightness_score = 15.0
        elif candidate.tmag <= 13:
            brightness_score = 10.0
        else:
            brightness_score = 4.0
    distance_score = 0.0
    if candidate.distance_ly is not None:
        if candidate.distance_ly <= 100:
            distance_score = 12.0
        elif candidate.distance_ly <= 150:
            distance_score = 8.0
        elif candidate.distance_ly <= 500:
            distance_score = 4.0
    score = (
        preliminary_evidence * 0.33
        + scientific_score * 0.25
        + data_window_score * 0.15
        + frequency_score
        + brightness_score
        + distance_score
    )
    return {"score": clip_score(score), "next_transits": transits, "upcoming_90d": upcoming_90}


def build_base_flags(candidate: Candidate) -> list[str]:
    flags: list[str] = []
    if candidate.is_fp:
        flags.append("PIPELINE_FP")
    if candidate.fp_baseline_flag or candidate.fp_baseline_std_flag or candidate.fp_scatter_flag:
        flags.append("PIPELINE_ARTIFACT_RISK")
    if candidate.fp_oe_flag:
        flags.append("PIPELINE_ODD_EVEN_FLAG")
    if candidate.fp_sec_flag:
        flags.append("PIPELINE_SECONDARY_FLAG")
    if candidate.fp_oe_flag and candidate.fp_sec_flag:
        flags.append("EB_RISK")
    if candidate.sec_ratio is not None and candidate.sec_ratio > 0.5:
        flags.append("SECONDARY_ECLIPSE_RISK")
    return flags


def classify_candidate(
    evidence_score: float,
    data_window_score: float,
    activity_score: float,
    followup_score: float,
    scientific_score: float,
    flags: set[str],
    candidate: Candidate,
) -> str:
    if "EB_RISK" in flags or "SECONDARY_ECLIPSE_RISK" in flags:
        return "EB_RISK"
    if "PIPELINE_FP" in flags and evidence_score < 45:
        return "REJECTED"
    if "PIPELINE_ARTIFACT_RISK" in flags or "SAP_PDCSAP_MISMATCH" in flags:
        if evidence_score < 55:
            return "SPC_ART"
    if (
        "SINGLE_OBSERVED_TRANSIT" in flags
        or "NO_OBSERVED_TRANSIT_WINDOWS" in flags
        or "ONLY_2_3_EVENTS_DRIVE_SIGNAL" in flags
    ):
        if scientific_score >= 45 or str(candidate.hz_class or candidate.hz_status) in HZ_CLASSES:
            return "NEEDS_MORE_TESS_DATA"
        return "SPC_WEAK_DATA"
    if data_window_score < 35 or "NEEDS_MORE_TESS_DATA" in flags:
        if scientific_score >= 45 or str(candidate.hz_class or candidate.hz_status) in HZ_CLASSES:
            return "NEEDS_MORE_TESS_DATA"
        return "SPC_WEAK_DATA"
    if activity_score < 50 or "ACTIVITY_CONFUSED" in flags:
        return "SPC_ACTIVE_STAR"
    if evidence_score < 35:
        return "REJECTED"
    if scientific_score >= 75 and evidence_score >= 65:
        return "SPC_RV_NEEDED"
    if followup_score >= 72 and evidence_score >= 58:
        return "SPC_FOLLOWUP_READY"
    if evidence_score >= 75:
        return "SPC_STRONG"
    if evidence_score >= 50:
        return "SPC_WEAK_DATA"
    return "REJECTED"


def why_interesting(candidate: Candidate, classification: str, science: dict[str, Any], flags: set[str]) -> str:
    pieces: list[str] = []
    hz = str(candidate.hz_class or candidate.hz_status or "UNKNOWN")
    sclass = science.get("stellar_class", "UNKNOWN")
    if hz in HZ_CLASSES:
        pieces.append(f"{hz} orbit")
    if sclass in {"K", "M", "G"}:
        pieces.append(f"{sclass}-star host")
    if candidate.distance_ly is not None and candidate.distance_ly <= 150:
        pieces.append(f"{candidate.distance_ly:.0f} ly")
    if candidate.planet_radius_earth is not None:
        pieces.append(f"Rp~{candidate.planet_radius_earth:.2f} Re")
    if not pieces:
        pieces.append("transit-like signal")
    risk_bits = sorted(flag for flag in flags if flag.endswith("_RISK") or flag in {"WEAK_DATA_WINDOW", "NEEDS_MORE_TESS_DATA"})
    risk_text = f"; main uncertainty: {', '.join(risk_bits[:4])}" if risk_bits else ""
    return f"{classification}: " + ", ".join(pieces) + risk_text


def evidence_score_from_components(
    data_window: float,
    stability: float,
    sap_pdcsap: float,
    odd_even: float,
    activity: float,
    followup: float,
    scientific: float,
) -> float:
    return clip_score(
        data_window * 0.20
        + stability * 0.20
        + sap_pdcsap * 0.12
        + odd_even * 0.14
        + activity * 0.12
        + followup * 0.10
        + scientific * 0.12
    )


def analyze_candidate(candidate: Candidate) -> dict[str, Any]:
    lc = load_lightcurve(candidate)
    time_arr = lc["time"]
    flux_arr = lc["flux"]
    assert isinstance(time_arr, np.ndarray)
    assert isinstance(flux_arr, np.ndarray)
    sap_flux = lc["sap_flux"]
    pdc_flux = lc["pdcsap_flux"]
    assert sap_flux is None or isinstance(sap_flux, np.ndarray)
    assert pdc_flux is None or isinstance(pdc_flux, np.ndarray)

    data_window = compute_data_window(candidate, time_arr, flux_arr)
    stability = compute_transit_stability(candidate, data_window)
    sap_pdcsap = compute_sap_pdcsap(candidate, time_arr, sap_flux, pdc_flux)
    odd_even = compute_odd_even(candidate, data_window["event_rows"])
    activity = compute_activity(candidate, time_arr, flux_arr)
    science = compute_scientific_value(
        candidate,
        int(data_window["n_visible_transits"]),
        candidate.clean_sector_count,
    )
    preliminary = evidence_score_from_components(
        data_window["score"],
        stability["score"],
        sap_pdcsap["score"],
        odd_even["score"],
        activity["score"],
        50.0,
        science["score"],
    )
    followup = compute_followup(candidate, preliminary, science["score"], data_window["score"])
    evidence = evidence_score_from_components(
        data_window["score"],
        stability["score"],
        sap_pdcsap["score"],
        odd_even["score"],
        activity["score"],
        followup["score"],
        science["score"],
    )
    flags = set(build_base_flags(candidate))
    for part in (data_window, stability, sap_pdcsap, odd_even, activity):
        flags.update(part.get("flags", []))

    classification = classify_candidate(
        evidence,
        data_window["score"],
        activity["score"],
        followup["score"],
        science["score"],
        flags,
        candidate,
    )
    advanced_recommended = bool(
        classification in ADVANCED_CLASSES
        or (evidence >= 65 and str(candidate.hz_class or candidate.hz_status) in HZ_CLASSES)
    )
    why = why_interesting(candidate, classification, science, flags)
    result = {
        "TIC": candidate.tic,
        "candidate_id": candidate.candidate_id,
        "period": candidate.period,
        "epoch": candidate.t0,
        "duration": candidate.duration,
        "depth": candidate.depth,
        "planet_radius_earth": candidate.planet_radius_earth,
        "transit_snr": candidate.transit_snr,
        "transit_count": candidate.transit_count,
        "hz_status": candidate.hz_status,
        "hz_class": candidate.hz_class,
        "pipeline_spc_class": candidate.spc_class,
        "pipeline_status": candidate.status,
        "evidence_score": evidence,
        "data_window_score": data_window["score"],
        "transit_stability_score": stability["score"],
        "sap_pdcsap_score": sap_pdcsap["score"],
        "odd_even_score": odd_even["score"],
        "activity_score": activity["score"],
        "followup_score": followup["score"],
        "scientific_value_score": science["score"],
        "evidence_class": classification,
        "bayes_recommended": int(advanced_recommended),
        "n_points": data_window["n_points"],
        "n_expected_transits": data_window["n_expected_transits"],
        "n_visible_transits": data_window["n_visible_transits"],
        "n_complete_transits": data_window["n_complete_transits"],
        "n_ephemeris_windows": data_window["n_ephemeris_windows"],
        "n_observed_transit_windows": data_window["n_observed_transit_windows"],
        "n_driver_events": data_window["n_driver_events"],
        "ephemeris_observed_fraction": data_window["ephemeris_observed_fraction"],
        "median_single_snr": data_window["median_snr"],
        "median_depth_ppt": data_window["median_depth_ppt"],
        "rotation_period_ls": activity["rotation_period_ls"],
        "rotation_period_acf": activity["rotation_period_acf"],
        "rotation_power": activity["rotation_power"],
        "sap_depth_ppt": sap_pdcsap["sap_depth_ppt"],
        "pdcsap_depth_ppt": sap_pdcsap["pdcsap_depth_ppt"],
        "sap_period": sap_pdcsap["sap_period"],
        "pdcsap_period": sap_pdcsap["pdcsap_period"],
        "odd_depth_ppt": odd_even["odd_depth_ppt"],
        "even_depth_ppt": odd_even["even_depth_ppt"],
        "odd_even_ratio": odd_even["odd_even_ratio"],
        "depth_cv": stability["depth_cv"],
        "duration_cv": stability["duration_cv"],
        "flags": ";".join(sorted(flags)),
        "why_interesting": why,
        "next_transits_json": json.dumps(followup["next_transits"], ensure_ascii=True),
        "lightcurve_path": str(lightcurve_path(candidate)),
        "reference_plot": reference_plot_path(candidate.tic),
    }
    return {
        "result": result,
        "sector_rows": data_window["sector_rows"],
        "event_rows": data_window["event_rows"],
        "followup_transits": followup["next_transits"],
    }


def reference_plot_path(tic: int) -> str:
    if not REFERENCE_PLOTS.exists():
        return ""
    matches = sorted(REFERENCE_PLOTS.glob(f"TIC_{tic}_*.png"))
    return str(matches[0]) if matches else ""


def ensure_evidence_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS evidence_vetting_results (
            run_id TEXT NOT NULL,
            TIC INTEGER NOT NULL,
            candidate_id INTEGER NOT NULL,
            period REAL,
            epoch REAL,
            duration REAL,
            depth REAL,
            evidence_score REAL,
            data_window_score REAL,
            transit_stability_score REAL,
            sap_pdcsap_score REAL,
            odd_even_score REAL,
            activity_score REAL,
            followup_score REAL,
            scientific_value_score REAL,
            evidence_class TEXT,
            bayes_recommended INTEGER,
            rotation_period_ls REAL,
            rotation_period_acf REAL,
            rotation_power REAL,
            n_points INTEGER,
            n_expected_transits INTEGER,
            n_visible_transits INTEGER,
            flags TEXT,
            why_interesting TEXT,
            next_transits_json TEXT,
            output_dir TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (run_id, TIC, candidate_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_tic ON evidence_vetting_results(TIC)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_evidence_class ON evidence_vetting_results(evidence_class)"
    )
    conn.commit()


def write_results_to_db(db_path: Path, run_id: str, run_dir: Path, rows: list[dict[str, Any]]) -> None:
    conn = sqlite3.connect(db_path, timeout=60)
    try:
        ensure_evidence_table(conn)
        for row in rows:
            conn.execute(
                """
                INSERT OR REPLACE INTO evidence_vetting_results (
                    run_id, TIC, candidate_id, period, epoch, duration, depth,
                    evidence_score, data_window_score, transit_stability_score,
                    sap_pdcsap_score, odd_even_score, activity_score, followup_score,
                    scientific_value_score, evidence_class, bayes_recommended,
                    rotation_period_ls, rotation_period_acf, rotation_power,
                    n_points, n_expected_transits, n_visible_transits,
                    flags, why_interesting, next_transits_json, output_dir, created_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?, datetime('now')
                )
                """,
                (
                    run_id,
                    row["TIC"],
                    row["candidate_id"],
                    row["period"],
                    row["epoch"],
                    row["duration"],
                    row["depth"],
                    row["evidence_score"],
                    row["data_window_score"],
                    row["transit_stability_score"],
                    row["sap_pdcsap_score"],
                    row["odd_even_score"],
                    row["activity_score"],
                    row["followup_score"],
                    row["scientific_value_score"],
                    row["evidence_class"],
                    row["bayes_recommended"],
                    row["rotation_period_ls"],
                    row["rotation_period_acf"],
                    row["rotation_power"],
                    row["n_points"],
                    row["n_expected_transits"],
                    row["n_visible_transits"],
                    row["flags"],
                    row["why_interesting"],
                    row["next_transits_json"],
                    str(run_dir),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    if not fields:
        fields = ["status"]
        rows = [{"status": "empty"}]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_dashboard(path: Path, rows: list[dict[str, Any]]) -> None:
    top = sorted(rows, key=lambda r: float(r["evidence_score"]), reverse=True)
    body_rows = []
    for row in top:
        flags = html.escape(str(row.get("flags", ""))).replace(";", "<br>")
        plot = str(row.get("reference_plot") or "")
        plot_link = f'<a href="{html.escape(plot)}">plot</a>' if plot else ""
        body_rows.append(
            "<tr>"
            f"<td>{int(row['TIC'])}</td>"
            f"<td>{html.escape(str(row['evidence_class']))}</td>"
            f"<td>{float(row['evidence_score']):.1f}</td>"
            f"<td>{html.escape(str(row.get('hz_class') or row.get('hz_status') or ''))}</td>"
            f"<td>{float(row['period']):.4f}</td>"
            f"<td>{html.escape(str(row.get('why_interesting', '')))}</td>"
            f"<td>{flags}</td>"
            f"<td>{plot_link}</td>"
            "</tr>"
        )
    html_text = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Candidate Evidence Dashboard</title>
  <style>
    body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #1d2430; background: #f6f7f9; }
    header { padding: 24px 32px; background: #102033; color: white; }
    main { padding: 24px 32px; }
    table { width: 100%; border-collapse: collapse; background: white; border: 1px solid #d8dde6; }
    th, td { padding: 9px 10px; border-bottom: 1px solid #e6e9ef; text-align: left; vertical-align: top; font-size: 13px; }
    th { background: #edf1f6; font-weight: 650; }
    tr:hover { background: #f8fbff; }
    .meta { color: #657184; font-size: 13px; margin-top: 6px; }
  </style>
</head>
<body>
  <header>
    <h1>Candidate Evidence Dashboard</h1>
    <div class="meta">Static review export from evidence_vetting.py</div>
  </header>
  <main>
    <table>
      <thead>
        <tr>
          <th>TIC</th><th>Class</th><th>Evidence</th><th>HZ</th><th>Period d</th>
          <th>Why interesting?</th><th>Flags</th><th>Plot</th>
        </tr>
      </thead>
      <tbody>
""" + "\n".join(body_rows) + """
      </tbody>
    </table>
  </main>
</body>
</html>
"""
    path.write_text(html_text, encoding="utf-8")


def main() -> int:
    args = parse_args()
    run_id, run_dir = make_run_dir(args.output_dir)
    logger = setup_logger(run_dir)
    logger.info("Evidence vetting run: %s", run_id)
    logger.info("Output: %s", run_dir)

    if args.input_csv:
        candidates = load_candidates_from_csv(args.input_csv, args)
    else:
        candidates = load_candidates_from_db(args.input_db, args)
    logger.info("Candidates selected: %d", len(candidates))

    result_rows: list[dict[str, Any]] = []
    sector_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    followup_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for idx, candidate in enumerate(candidates, start=1):
        try:
            payload = analyze_candidate(candidate)
            row = payload["result"]
            row["run_id"] = run_id
            row["output_dir"] = str(run_dir)
            result_rows.append(row)
            for sector in payload["sector_rows"]:
                sector_rows.append({"run_id": run_id, **sector})
            for event in payload["event_rows"]:
                event_rows.append({"run_id": run_id, **event})
            if row["evidence_class"] in FOLLOWUP_CLASSES:
                followup_rows.append(
                    {
                        "run_id": run_id,
                        "TIC": row["TIC"],
                        "candidate_id": row["candidate_id"],
                        "evidence_class": row["evidence_class"],
                        "followup_score": row["followup_score"],
                        "evidence_score": row["evidence_score"],
                        "scientific_value_score": row["scientific_value_score"],
                        "period": row["period"],
                        "epoch": row["epoch"],
                        "hz_class": row["hz_class"],
                        "next_transits_json": row["next_transits_json"],
                        "why_interesting": row["why_interesting"],
                        "flags": row["flags"],
                    }
                )
            logger.info(
                "%d/%d TIC %s: %s evidence=%.1f flags=%s",
                idx,
                len(candidates),
                candidate.tic,
                row["evidence_class"],
                float(row["evidence_score"]),
                row["flags"] or "none",
            )
        except Exception as exc:
            error = {
                "run_id": run_id,
                "TIC": candidate.tic,
                "candidate_id": candidate.candidate_id,
                "error": f"{type(exc).__name__}: {exc}",
            }
            errors.append(error)
            logger.exception("TIC %s failed: %s", candidate.tic, error["error"])

    result_rows.sort(key=lambda r: float(r["evidence_score"]), reverse=True)
    followup_rows.sort(key=lambda r: float(r["followup_score"]), reverse=True)
    advanced_rows = [row for row in result_rows if int(row.get("bayes_recommended", 0))]

    write_csv(run_dir / "evidence_vetting_results.csv", result_rows)
    write_csv(run_dir / "data_window_quality.csv", sector_rows)
    write_csv(run_dir / "transit_events.csv", event_rows)
    write_csv(run_dir / "followup_priority.csv", followup_rows)
    write_csv(run_dir / "advanced_bayesian_input.csv", advanced_rows)
    if errors:
        write_csv(run_dir / "errors.csv", errors)
    if not args.no_dashboard:
        write_dashboard(run_dir / "candidate_dashboard.html", result_rows)

    if args.dry_run:
        logger.info("Dry run: SQLite update skipped.")
    elif result_rows and not args.input_csv:
        write_results_to_db(args.input_db, run_id, run_dir, result_rows)
        logger.info("SQLite evidence_vetting_results updated.")
    elif args.input_csv:
        logger.info("Input was CSV: SQLite update skipped.")

    counts = Counter(row["evidence_class"] for row in result_rows)
    logger.info("Class counts: %s", dict(counts))
    logger.info("Done: %s", run_dir)
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
