"""
Super-Earth Hunter — Master Script v2
======================================
Vollständige Pipeline: TIC-Import → TESS-Check → BLS-Scan → False-Positive-Filter
→ HZ-Klassifikation → CSV-Export

Performance-Architektur:
  ┌─────────────────────────────────────────────────────────────┐
  │  Für jeden Batch:                                           │
  │  1. Cache-Check (sofort, kein Netzwerk)                     │
  │  2. Prozesse    → parallele MAST-Downloads mit Hard-Timeout │
  │  3. ProcessPool → paralleler BLS auf allen CPU-Kernen       │
  │  4. Main-Thread → DB-Schreibzugriff (sequenziell, sicher)   │
  └─────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import os
import builtins
import math
import multiprocessing as mp
import queue
import sqlite3
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/astro_project_matplotlib")
warnings.filterwarnings("ignore", message="Warning: the tpfmodel submodule.*")
warnings.filterwarnings("ignore", message=".*did not parse as fits unit.*")
warnings.filterwarnings("ignore", message="File may have been truncated.*")
warnings.filterwarnings("ignore", message="The following columns will be excluded from stitching.*")
warnings.filterwarnings("ignore", message="column .* has a unit but is kept as a Column.*")
warnings.filterwarnings("ignore", message="All-NaN slice encountered.*", category=RuntimeWarning)
warnings.filterwarnings("ignore", message="Degrees of freedom <= 0 for slice.*", category=RuntimeWarning)

import numpy as np
import pandas as pd

try:
    from tqdm.std import tqdm
    from tqdm.std import tqdm as _tqdm_cls
    HAS_TQDM = os.environ.get("PROGRESS_BARS", "1") != "0"
except ImportError:
    HAS_TQDM = False

if HAS_TQDM:
    _tqdm_orig_del = getattr(_tqdm_cls, "__del__", None)

    def _safe_tqdm_del(self):
        try:
            if hasattr(self, "last_print_t") and _tqdm_orig_del is not None:
                _tqdm_orig_del(self)
        except Exception:
            pass

    _tqdm_cls.__del__ = _safe_tqdm_del

from astroquery.mast import Catalogs, Observations
from astropy.timeseries import BoxLeastSquares
from lightkurve import LightCurveCollection, search_lightcurve, search_tesscut


# ============================================================
# KONFIGURATION
# ============================================================

PROJECT_ROOT        = Path(os.environ.get("ASTRO_PROJECT_ROOT", "/Users/koni/astro_projects"))
DB_PATH             = PROJECT_ROOT / "database" / "planet_hunter.db"
LIGHTCURVE_BASE_DIR = PROJECT_ROOT / "lightcurves"
RESULTS_CSV         = PROJECT_ROOT / "csv" / "masterscript_v2_candidates.csv"
HZ_REVISIT_CSV      = PROJECT_ROOT / "csv" / "hz_revisit_priority.csv"
CANDIDATE_PLOT_DIR  = PROJECT_ROOT / "level1_rohkandidaten" / "level1_auto_plots_neuer_lauf"

TABLE_RAW        = "rohdaten"
TABLE_ACTIVE     = "kstars_active"
TABLE_CANDIDATES = "candidates_v2"
RECHECK_STATUSES = ("NEW", "RECHECK", "RECHECK_NEW_SECTOR")

# --- Pipeline-Stufen ---
IMPORT_FROM_MAST  = True
CHECK_TESS_DATA   = True
RUN_BLS_SCAN      = True
REBUILD_ROHDATEN   = False
REBUILD_ACTIVE     = True
REBUILD_CANDIDATES = False
AUTO_PLOT_CANDIDATES = os.environ.get("AUTO_PLOT_CANDIDATES", "1") == "1"
AUTO_PLOT_FP_CANDIDATES = os.environ.get("AUTO_PLOT_FP_CANDIDATES", "0") == "1"
PLOT_MAX_POINTS = int(os.environ.get("PLOT_MAX_POINTS", "20000"))

# --- Zielparameter ---
TEFF_MIN        = 3900
TEFF_MAX        = 5300
MAX_DISTANCE_LY = float(os.environ.get("MAX_DISTANCE_LY", "500"))
TESSMAG_MAX     = 13.5
RADIUS_MIN      = 0.45
RADIUS_MAX      = 0.95
LOGG_MIN        = 4.2
LOGG_MAX        = 5.2
REQUIRE_DWARF_LOGG = True

TEFF_BLOCKS = [
    (3900, 4000), (4000, 4100), (4100, 4200), (4200, 4300),
    (4300, 4400), (4400, 4500), (4500, 4600), (4600, 4700),
    (4700, 4800), (4800, 4900), (4900, 5000), (5000, 5100),
    (5100, 5150), (5150, 5200), (5200, 5250), (5250, 5300),
]

# --- MAST-Import ---
QUERY_MAX_TRIES     = 4
QUERY_SLEEP_SECONDS = 8
BLOCK_SLEEP_SECONDS = 2

# --- TESS-Check ---
TESS_CHECK_LIMIT      = int(os.environ["TESS_CHECK_LIMIT"]) if os.environ.get("TESS_CHECK_LIMIT") else None
TESS_BATCH_SIZE       = 200
TESS_BATCH_SLEEP      = 0.2
TESS_BATCH_RETRIES    = 3
TESS_BATCH_RETRY_SLEEP = 10

# --- ★ Performance ---
CPU_COUNT        = os.cpu_count() or 2
DOWNLOAD_LIMIT   = int(os.environ["DOWNLOAD_LIMIT"]) if os.environ.get("DOWNLOAD_LIMIT") else None
DOWNLOAD_RETRIES = int(os.environ.get("DOWNLOAD_RETRIES", "3"))
DOWNLOAD_WORKERS = int(os.environ.get("DOWNLOAD_WORKERS", "8"))
DOWNLOAD_BATCH_TIMEOUT_SECONDS = int(os.environ.get("DOWNLOAD_BATCH_TIMEOUT_SECONDS", "180"))
DOWNLOAD_TARGET_TIMEOUT_SECONDS = int(os.environ.get("DOWNLOAD_TARGET_TIMEOUT_SECONDS", "75"))
DOWNLOAD_START_METHOD = os.environ.get("DOWNLOAD_START_METHOD", "spawn")
BLS_WORKERS      = int(os.environ.get("BLS_WORKERS", str(max(1, CPU_COUNT - 1))))
FETCH_BATCH_SIZE = int(os.environ.get("FETCH_BATCH_SIZE", str(DOWNLOAD_WORKERS * 8)))
MAX_LIGHTCURVES_PER_TARGET = int(os.environ.get("MAX_LIGHTCURVES_PER_TARGET", "4"))
ENABLE_TESSCUT_FALLBACK = os.environ.get("ENABLE_TESSCUT_FALLBACK", "0") == "1"
BLS_START_METHOD = os.environ.get("BLS_START_METHOD", "fork")

QUALITY_BITMASK  = "default"

# --- BLS ---
MIN_PERIOD       = 0.5
MAX_PERIOD       = float(os.environ.get("MAX_PERIOD", "80.0"))
HZ_PERIOD_BUFFER = float(os.environ.get("HZ_PERIOD_BUFFER", "1.15"))
MAX_HZ_PERIOD    = float(os.environ.get("MAX_HZ_PERIOD", "120.0"))
COARSE_PERIODS   = int(os.environ.get("COARSE_PERIODS", "1400"))
FINE_PERIODS     = int(os.environ.get("FINE_PERIODS", "700"))
FINE_WINDOW_FRAC = float(os.environ.get("FINE_WINDOW_FRAC", "0.015"))
DURATION_GRID    = np.linspace(0.05, 0.30, 8)
BLS_DURATIONS    = np.array([d for d in DURATION_GRID if d < MIN_PERIOD])
MIN_POINTS       = 300
POWER_THRESHOLD  = float(os.environ.get("POWER_THRESHOLD", "0.0"))
MIN_TRANSIT_SNR  = float(os.environ.get("MIN_TRANSIT_SNR", "7.0"))
MIN_TRANSITS     = int(os.environ.get("MIN_TRANSITS", "2"))
MIN_IN_TRANSIT_POINTS = int(os.environ.get("MIN_IN_TRANSIT_POINTS", "8"))
MAX_DURATION_FRACTION = float(os.environ.get("MAX_DURATION_FRACTION", "0.12"))
MAX_CANDIDATE_RADIUS_EARTH = 4.0
MAX_TRANSIT_DEPTH = 0.08

# --- HZ-Revisit / SPC ---
REVISIT_HZ_CLASSES = {"OPT_HZ_INNEN", "KONSERVATIVE_HZ"}
REVISIT_MAX_DISTANCE_LY = float(os.environ.get("REVISIT_MAX_DISTANCE_LY", "150"))
REVISIT_MIN_SNR = float(os.environ.get("REVISIT_MIN_SNR", str(MIN_TRANSIT_SNR)))
REVISIT_MIN_CLEAN_SECTORS = int(os.environ.get("REVISIT_MIN_CLEAN_SECTORS", "1"))
SECTOR_SPLIT_GAP_DAYS = float(os.environ.get("SECTOR_SPLIT_GAP_DAYS", "5.0"))
SECTOR_CLEAN_MIN_POINTS = int(os.environ.get("SECTOR_CLEAN_MIN_POINTS", "80"))
SECTOR_CLEAN_MAX_GAP_FRACTION = float(os.environ.get("SECTOR_CLEAN_MAX_GAP_FRACTION", "0.55"))
SECTOR_CLEAN_MAX_RMS_PPT = float(os.environ.get("SECTOR_CLEAN_MAX_RMS_PPT", "25.0"))
VISIBLE_TRANSIT_MIN_LOCAL_SNR = float(os.environ.get("VISIBLE_TRANSIT_MIN_LOCAL_SNR", "2.0"))

# --- False-Positive-Filter ---
FP_OE_MIN_RATIO  = 0.5
FP_OE_MAX_RATIO  = 2.0
FP_SEC_THRESHOLD = 0.5
FP_REJECT_ON_BOTH = True
FP_BASELINE_MIN_POINTS = int(os.environ.get("FP_BASELINE_MIN_POINTS", "8"))
FP_BASELINE_GAP_DURATIONS = float(os.environ.get("FP_BASELINE_GAP_DURATIONS", "0.75"))
FP_BASELINE_WINDOW_DURATIONS = float(os.environ.get("FP_BASELINE_WINDOW_DURATIONS", "2.0"))
FP_BASELINE_DELTA_MAX_DEPTHS = float(os.environ.get("FP_BASELINE_DELTA_MAX_DEPTHS", "0.75"))
FP_BASELINE_DELTA_ABS = float(os.environ.get("FP_BASELINE_DELTA_ABS", "0.002"))
FP_BASELINE_STD_DELTA_MAX_DEPTHS = float(os.environ.get("FP_BASELINE_STD_DELTA_MAX_DEPTHS", "0.75"))
FP_BASELINE_STD_DELTA_ABS = float(os.environ.get("FP_BASELINE_STD_DELTA_ABS", "0.002"))
FP_MAX_OOT_SCATTER_DEPTH_RATIO = float(os.environ.get("FP_MAX_OOT_SCATTER_DEPTH_RATIO", "1.0"))

# --- Allgemein ---
VERBOSE         = True


# ============================================================
# LOGGING
# ============================================================

def log(msg: str) -> None:
    if VERBOSE:
        ts = datetime.now().strftime("%H:%M:%S")
        try:
            safe_print(f"[{ts}] {msg}", flush=True)
        except (BrokenPipeError, OSError, ValueError):
            pass


def safe_print(*args, **kwargs) -> None:
    try:
        builtins.print(*args, **kwargs)
    except (BrokenPipeError, OSError, ValueError):
        pass


# ============================================================
# HABITABLE-ZONE  (Kopparapu et al. 2014)
# ============================================================

_KOPPARAPU = {
    "Recent Venus":       dict(S=1.7763, a=1.4335e-4, b=3.3954e-9,  c=-7.6364e-12, d=-1.1950e-15),
    "Runaway Greenhouse": dict(S=1.0385, a=1.2456e-4, b=1.4612e-8,  c=-7.6345e-12, d=-1.7511e-15),
    "Maximum Greenhouse": dict(S=0.3507, a=5.9578e-5, b=1.6707e-9,  c=-3.0058e-12, d=-5.1925e-16),
    "Early Mars":         dict(S=0.3207, a=5.4471e-5, b=1.5275e-9,  c=-2.1709e-12, d=-3.8282e-16),
}


def _s_eff(teff: float, edge: str) -> float:
    p = _KOPPARAPU[edge]
    t = teff - 5780.0
    return p["S"] + p["a"]*t + p["b"]*t**2 + p["c"]*t**3 + p["d"]*t**4


def _luminosity(teff: float, radius: float) -> float:
    return radius**2 * (teff / 5778.0)**4


def _stellar_mass(teff: float, radius: float) -> float:
    if teff < 3700:   return radius
    if teff < 5300:   return radius**0.8 * 0.95
    return radius**0.8


def _period_at_au(au: float, mass: float) -> float:
    return float(np.sqrt(au**3 / mass) * 365.25)


def _hz_au(teff: float, radius: float, edge: str) -> float:
    return float(np.sqrt(_luminosity(teff, radius) / _s_eff(teff, edge)))


@dataclass
class HZPeriods:
    cons_inner_d: float
    cons_outer_d: float
    opt_inner_d:  float
    opt_outer_d:  float

    def classify(self, period_days: float) -> str:
        if period_days < self.opt_inner_d:   return "ZU_HEISS"
        if period_days < self.cons_inner_d:  return "OPT_HZ_INNEN"
        if period_days <= self.cons_outer_d: return "KONSERVATIVE_HZ"
        if period_days <= self.opt_outer_d:  return "OPT_HZ_AUSSEN"
        return "ZU_KALT"

    def classify_hz_class(self, period_days: float) -> str:
        if not np.isfinite(period_days):
            return "UNKNOWN"
        if period_days < self.opt_inner_d:   return "ZU_HEISS"
        if period_days < self.cons_inner_d:  return "OPT_HZ_INNEN"
        if period_days <= self.cons_outer_d: return "KONSERVATIVE_HZ"
        return "ZU_KALT"


def compute_hz(teff: float, radius: float) -> Optional[HZPeriods]:
    try:
        if not (teff and radius and teff > 0 and radius > 0):
            return None
        mass = _stellar_mass(teff, radius)
        return HZPeriods(
            cons_inner_d=_period_at_au(_hz_au(teff, radius, "Runaway Greenhouse"), mass),
            cons_outer_d=_period_at_au(_hz_au(teff, radius, "Maximum Greenhouse"), mass),
            opt_inner_d =_period_at_au(_hz_au(teff, radius, "Recent Venus"),       mass),
            opt_outer_d =_period_at_au(_hz_au(teff, radius, "Early Mars"),         mass),
        )
    except Exception:
        return None


def normalize_hz_class(value: object) -> str:
    text = str(value or "").strip().upper()
    if text in {"ZU_HEISS", "OPT_HZ_INNEN", "KONSERVATIVE_HZ", "ZU_KALT"}:
        return text
    if text == "OPT_HZ_AUSSEN":
        return "ZU_KALT"
    return "UNKNOWN"


def compute_hz_class(teff: object, radius: object, period_days: object) -> str:
    try:
        period = float(period_days)
        hz = compute_hz(float(teff), float(radius))
    except Exception:
        return "UNKNOWN"
    return hz.classify_hz_class(period) if hz else "UNKNOWN"


# ============================================================
# FALSE-POSITIVE-FILTER
# ============================================================

def _phase_fold(time_arr, period, t0):
    return ((time_arr - t0) % period) / period


def _transit_mask(time_arr, period, t0, duration, window_scale=1.0):
    win = min(duration / period * window_scale, 0.20)
    phase = _phase_fold(time_arr, period, t0)
    return (phase < win / 2) | (phase > 1 - win / 2)


def signal_quality(time_arr, flux_arr, period, t0, duration, depth) -> dict:
    in_transit = _transit_mask(time_arr, period, t0, duration, window_scale=1.0)
    out_transit = ~_transit_mask(time_arr, period, t0, duration, window_scale=2.5)
    transit_n = np.floor((time_arr[in_transit] - t0) / period).astype(int)

    n_in = int(np.count_nonzero(in_transit))
    n_out = int(np.count_nonzero(out_transit))
    transit_count = int(len(np.unique(transit_n))) if n_in else 0
    duration_fraction = float(duration / period) if period > 0 else np.inf

    if n_out >= 10:
        oot = flux_arr[out_transit]
        scatter = float(1.4826 * np.nanmedian(np.abs(oot - np.nanmedian(oot))))
    else:
        scatter = float(np.nanstd(flux_arr))

    snr = None
    if np.isfinite(scatter) and scatter > 0 and n_in > 0 and np.isfinite(depth):
        snr = float(depth / scatter * np.sqrt(n_in))

    return {
        "snr": snr,
        "transit_count": transit_count,
        "n_in_transit": n_in,
        "duration_fraction": duration_fraction,
        "passes": (
            n_in >= MIN_IN_TRANSIT_POINTS
            and transit_count >= MIN_TRANSITS
            and snr is not None
            and snr >= MIN_TRANSIT_SNR
            and duration_fraction <= MAX_DURATION_FRACTION
        ),
    }


def odd_even_check(time_arr, flux_arr, period, t0, duration):
    win        = min(duration / period * 1.5, 0.15)
    transit_n  = np.floor((time_arr - t0) / period).astype(int)
    phase      = _phase_fold(time_arr, period, t0)
    in_transit = (phase < win / 2) | (phase > 1 - win / 2)
    out_transit = ~_transit_mask(time_arr, period, t0, duration, window_scale=2.5)
    baseline = float(np.nanmedian(flux_arr[out_transit])) if np.count_nonzero(out_transit) >= 10 else 1.0

    odd_flux  = flux_arr[in_transit & (transit_n % 2 == 1)]
    even_flux = flux_arr[in_transit & (transit_n % 2 == 0)]

    if len(odd_flux) < 4 or len(even_flux) < 4:
        return None, None, None

    odd_d  = float(baseline - np.nanmedian(odd_flux))
    even_d = float(baseline - np.nanmedian(even_flux))
    ratio  = float(odd_d / even_d) if abs(even_d) > 1e-8 else None
    return odd_d, even_d, ratio


def secondary_eclipse_check(time_arr, flux_arr, period, t0, duration, primary_depth):
    t0_sec = t0 + period / 2.0
    win    = min(duration / period * 1.5, 0.15)
    phase  = _phase_fold(time_arr, period, t0_sec)
    in_sec = (phase < win / 2) | (phase > 1 - win / 2)
    out_sec = ~_transit_mask(time_arr, period, t0_sec, duration, window_scale=2.5)

    sec_flux = flux_arr[in_sec]
    if len(sec_flux) < 4 or primary_depth <= 0:
        return None

    baseline = float(np.nanmedian(flux_arr[out_sec])) if np.count_nonzero(out_sec) >= 10 else 1.0
    return float((baseline - np.nanmedian(sec_flux)) / primary_depth)


def local_baseline_check(time_arr, flux_arr, period, t0, duration, depth) -> dict:
    centered_phase_days = ((time_arr - t0 + period / 2.0) % period) - period / 2.0
    gap = max(duration * FP_BASELINE_GAP_DURATIONS, 0.0)
    window = max(duration * FP_BASELINE_WINDOW_DURATIONS, duration)

    left_mask = (centered_phase_days >= -(gap + window)) & (centered_phase_days <= -gap)
    right_mask = (centered_phase_days >= gap) & (centered_phase_days <= gap + window)

    if np.count_nonzero(left_mask) < FP_BASELINE_MIN_POINTS or np.count_nonzero(right_mask) < FP_BASELINE_MIN_POINTS:
        return {"baseline_delta": None, "baseline_threshold": None, "fp_baseline_flag": False}

    left = float(np.nanmedian(flux_arr[left_mask]))
    right = float(np.nanmedian(flux_arr[right_mask]))
    delta = float(abs(left - right))
    threshold = max(float(abs(depth) * FP_BASELINE_DELTA_MAX_DEPTHS), FP_BASELINE_DELTA_ABS)

    return {
        "baseline_delta": delta,
        "baseline_threshold": threshold,
        "fp_baseline_flag": bool(np.isfinite(delta) and delta > threshold),
    }


def local_baseline_std_check(time_arr, flux_arr, period, t0, duration, depth) -> dict:
    centered_phase_days = ((time_arr - t0 + period / 2.0) % period) - period / 2.0
    left_mask = centered_phase_days < -2.0 * duration
    right_mask = centered_phase_days > 2.0 * duration

    if np.count_nonzero(left_mask) < FP_BASELINE_MIN_POINTS or np.count_nonzero(right_mask) < FP_BASELINE_MIN_POINTS:
        return {"baseline_std_delta": None, "baseline_std_threshold": None, "fp_baseline_std_flag": False}

    left_std = float(np.nanstd(flux_arr[left_mask]))
    right_std = float(np.nanstd(flux_arr[right_mask]))
    delta = float(abs(left_std - right_std))
    threshold = max(float(abs(depth) * FP_BASELINE_STD_DELTA_MAX_DEPTHS), FP_BASELINE_STD_DELTA_ABS)

    return {
        "baseline_std_delta": delta,
        "baseline_std_threshold": threshold,
        "fp_baseline_std_flag": bool(np.isfinite(delta) and delta > threshold),
    }


def outside_scatter_check(time_arr, flux_arr, period, t0, duration, depth) -> dict:
    out_transit = ~_transit_mask(time_arr, period, t0, duration, window_scale=2.5)
    if np.count_nonzero(out_transit) < 20 or not np.isfinite(depth) or depth <= 0:
        return {"oot_scatter": None, "oot_scatter_ratio": None, "fp_scatter_flag": False}

    oot = flux_arr[out_transit]
    scatter = float(1.4826 * np.nanmedian(np.abs(oot - np.nanmedian(oot))))
    ratio = float(scatter / depth) if np.isfinite(scatter) else None

    return {
        "oot_scatter": scatter,
        "oot_scatter_ratio": ratio,
        "fp_scatter_flag": bool(ratio is not None and ratio > FP_MAX_OOT_SCATTER_DEPTH_RATIO),
    }


def _robust_scatter(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return float("nan")
    med = float(np.nanmedian(values))
    mad = float(np.nanmedian(np.abs(values - med)))
    if np.isfinite(mad) and mad > 0:
        return float(1.4826 * mad)
    return float(np.nanstd(values))


def _safe_float(value: object, default: float = float("nan")) -> float:
    try:
        out = float(value)
    except Exception:
        return default
    return out if np.isfinite(out) else default


def _safe_int(value: object, default: int = 0) -> int:
    try:
        if value is None or (isinstance(value, float) and not np.isfinite(value)):
            return default
        return int(value)
    except Exception:
        return default


def _expected_event_centers(time_arr: np.ndarray, period: float, t0: float) -> list[float]:
    if len(time_arr) == 0 or not (np.isfinite(period) and period > 0 and np.isfinite(t0)):
        return []
    t_min = float(np.nanmin(time_arr))
    t_max = float(np.nanmax(time_arr))
    first = int(math.ceil((t_min - t0) / period)) - 1
    last = int(math.floor((t_max - t0) / period)) + 1
    centers: list[float] = []
    for epoch in range(first, last + 1):
        center = t0 + epoch * period
        if t_min <= center <= t_max:
            centers.append(float(center))
    return centers


def _measure_visible_event(
    time_arr: np.ndarray,
    flux_arr: np.ndarray,
    center: float,
    duration: float,
) -> dict:
    half = max(float(duration) / 2.0, 1e-6)
    local_window = max(4.0 * float(duration), 0.12)
    local = np.abs(time_arr - center) <= local_window
    if int(np.count_nonzero(local)) < 8:
        return {"visible": False, "snr": float("nan"), "depth": float("nan"), "n_in": 0, "n_out": 0}

    dt = time_arr[local] - center
    fl = flux_arr[local]
    inside = np.abs(dt) <= half
    outside = (np.abs(dt) >= 1.5 * half) & (np.abs(dt) <= local_window)
    n_in = int(np.count_nonzero(inside))
    n_out = int(np.count_nonzero(outside))
    if n_in < 3 or n_out < 5:
        return {"visible": False, "snr": float("nan"), "depth": float("nan"), "n_in": n_in, "n_out": n_out}

    baseline = float(np.nanmedian(fl[outside]))
    depth = max(0.0, baseline - float(np.nanmedian(fl[inside])))
    scatter_ppt = _robust_scatter((fl[outside] - baseline) * 1000.0)
    snr = depth * 1000.0 / scatter_ppt * math.sqrt(n_in) if scatter_ppt > 0 else float("nan")
    visible = bool(np.isfinite(snr) and snr >= VISIBLE_TRANSIT_MIN_LOCAL_SNR and depth > 0)
    return {"visible": visible, "snr": float(snr), "depth": float(depth), "n_in": n_in, "n_out": n_out}


def _infer_sector_slices(time_arr: np.ndarray) -> list[np.ndarray]:
    if len(time_arr) == 0:
        return []
    gaps = np.where(np.diff(time_arr) > SECTOR_SPLIT_GAP_DAYS)[0]
    starts = [0] + [int(i + 1) for i in gaps]
    ends = [int(i + 1) for i in gaps] + [len(time_arr)]
    return [np.arange(start, end) for start, end in zip(starts, ends) if end - start > 0]


def _gap_fraction(time_arr: np.ndarray) -> float:
    if len(time_arr) < 3:
        return 1.0
    diffs = np.diff(np.sort(time_arr))
    diffs = diffs[np.isfinite(diffs) & (diffs > 0)]
    if len(diffs) == 0:
        return 1.0
    cadence = float(np.nanmedian(diffs))
    if not np.isfinite(cadence) or cadence <= 0:
        return 1.0
    span = float(np.nanmax(time_arr) - np.nanmin(time_arr))
    expected = max(int(round(span / cadence)) + 1, len(time_arr))
    if expected <= 0:
        return 1.0
    return float(np.clip(1.0 - len(time_arr) / expected, 0.0, 1.0))


def _sap_pdcsap_agreement(sap_flux: Optional[np.ndarray], pdc_flux: Optional[np.ndarray]) -> Optional[bool]:
    if sap_flux is None or pdc_flux is None or len(sap_flux) != len(pdc_flux) or len(sap_flux) < 20:
        return None
    sap = np.asarray(sap_flux, dtype=float)
    pdc = np.asarray(pdc_flux, dtype=float)
    finite = np.isfinite(sap) & np.isfinite(pdc)
    if int(np.count_nonzero(finite)) < 20:
        return None
    sap = sap[finite]
    pdc = pdc[finite]
    sap_med = float(np.nanmedian(sap))
    pdc_med = float(np.nanmedian(pdc))
    if abs(sap_med) > 1e-8:
        sap = sap / sap_med
    if abs(pdc_med) > 1e-8:
        pdc = pdc / pdc_med
    diff_rms = _robust_scatter((sap - pdc) * 1000.0)
    pdc_rms = _robust_scatter((pdc - 1.0) * 1000.0)
    return bool(np.isfinite(diff_rms) and diff_rms <= max(5.0, 2.0 * pdc_rms))


def compute_sector_quality(
    time_arr: np.ndarray,
    flux_arr: np.ndarray,
    period: float,
    t0: float,
    duration: float,
    depth: float,
    sap_flux_arr: Optional[np.ndarray] = None,
    pdcsap_flux_arr: Optional[np.ndarray] = None,
) -> dict:
    time_arr = np.asarray(time_arr, dtype=float)
    flux_arr = np.asarray(flux_arr, dtype=float)
    finite = np.isfinite(time_arr) & np.isfinite(flux_arr)
    if int(np.count_nonzero(finite)) == 0:
        return {
            "sector_count": 0,
            "clean_sector_count": 0,
            "visible_transits": 0,
            "sector_quality_summary": "no_finite_lightcurve_points",
        }

    order = np.argsort(time_arr[finite])
    t = time_arr[finite][order]
    f = flux_arr[finite][order]
    sap = None
    pdc = None
    if sap_flux_arr is not None and len(sap_flux_arr) == len(time_arr):
        sap = np.asarray(sap_flux_arr, dtype=float)[finite][order]
    if pdcsap_flux_arr is not None and len(pdcsap_flux_arr) == len(time_arr):
        pdc = np.asarray(pdcsap_flux_arr, dtype=float)[finite][order]

    slices = _infer_sector_slices(t)
    sector_rows: list[dict] = []
    total_visible = 0
    total_expected = 0
    depth_ppt = abs(float(depth)) * 1000.0 if np.isfinite(depth) else float("nan")
    rms_limit = max(SECTOR_CLEAN_MAX_RMS_PPT, 3.0 * depth_ppt) if np.isfinite(depth_ppt) else SECTOR_CLEAN_MAX_RMS_PPT

    for idx, segment_idx in enumerate(slices, start=1):
        st = t[segment_idx]
        sf = f[segment_idx]
        n_points = int(len(st))
        gaps = _gap_fraction(st)
        med = float(np.nanmedian(sf)) if n_points else float("nan")
        rms_ppt = _robust_scatter((sf - med) * 1000.0) if np.isfinite(med) else float("nan")
        centers = _expected_event_centers(st, period, t0)
        event_metrics = [_measure_visible_event(st, sf, center, duration) for center in centers]
        n_visible = int(sum(1 for metric in event_metrics if metric["visible"]))
        total_expected += len(centers)
        total_visible += n_visible
        agreement = _sap_pdcsap_agreement(
            sap[segment_idx] if sap is not None else None,
            pdc[segment_idx] if pdc is not None else None,
        )
        data_clean = (
            n_points >= SECTOR_CLEAN_MIN_POINTS
            and np.isfinite(gaps)
            and gaps <= SECTOR_CLEAN_MAX_GAP_FRACTION
            and np.isfinite(rms_ppt)
            and rms_ppt <= rms_limit
            and agreement is not False
        )
        recovery_clean = n_visible > 0 if centers else True
        sector_rows.append(
            {
                "sector": idx,
                "n_points": n_points,
                "gap_fraction": gaps,
                "rms_ppt": rms_ppt,
                "expected_transits": len(centers),
                "visible_transits": n_visible,
                "sap_pdcsap_agreement": agreement,
                "clean": bool(data_clean and recovery_clean),
            }
        )

    if total_expected > 0:
        clean_sector_count = int(
            sum(1 for row in sector_rows if row["clean"] and int(row["expected_transits"]) > 0)
        )
    else:
        clean_sector_count = int(sum(1 for row in sector_rows if row["clean"]))
    med_rms = float(np.nanmedian([row["rms_ppt"] for row in sector_rows])) if sector_rows else float("nan")
    med_gap = float(np.nanmedian([row["gap_fraction"] for row in sector_rows])) if sector_rows else float("nan")
    agreement_values = [row["sap_pdcsap_agreement"] for row in sector_rows if row["sap_pdcsap_agreement"] is not None]
    if not agreement_values:
        sap_summary = "UNKNOWN"
    elif all(agreement_values):
        sap_summary = "OK"
    else:
        sap_summary = "MISMATCH"
    compact_rows = [
        (
            f"S{row['sector']}:n={row['n_points']},gap={row['gap_fraction']:.2f},"
            f"rms={row['rms_ppt']:.2f},vis={row['visible_transits']},"
            f"clean={'Y' if row['clean'] else 'N'}"
        )
        for row in sector_rows[:8]
    ]
    if len(sector_rows) > 8:
        compact_rows.append(f"+{len(sector_rows) - 8} more")
    summary = (
        f"sectors={len(sector_rows)} clean={clean_sector_count} "
        f"visible={total_visible}/{total_expected} "
        f"med_rms_ppt={med_rms:.2f} med_gap={med_gap:.2f} "
        f"SAP_PDCSAP={sap_summary}; " + " | ".join(compact_rows)
    )
    return {
        "sector_count": int(len(sector_rows)),
        "clean_sector_count": clean_sector_count,
        "visible_transits": int(total_visible),
        "sector_quality_summary": summary[:1000],
    }


def _strong_fp_evidence(fp: dict) -> bool:
    return bool(fp.get("fp_oe_flag") and fp.get("fp_sec_flag"))


def _artifact_risk(fp: dict) -> bool:
    return bool(
        fp.get("fp_baseline_flag")
        or fp.get("fp_baseline_std_flag")
        or fp.get("fp_scatter_flag")
    )


def is_hz_revisit_candidate(
    visible_transits: object,
    hz_class: object,
    distance_ly: object,
    snr: object,
    clean_sector_count: object,
    fp: Optional[dict] = None,
) -> bool:
    fp = fp or {}
    return (
        _safe_int(visible_transits) < 3
        and normalize_hz_class(hz_class) in REVISIT_HZ_CLASSES
        and _safe_float(distance_ly) <= REVISIT_MAX_DISTANCE_LY
        and _safe_float(snr) >= REVISIT_MIN_SNR
        and _safe_int(clean_sector_count) >= REVISIT_MIN_CLEAN_SECTORS
        and not _strong_fp_evidence(fp)
    )


def compute_revisit_priority(
    visible_transits: object,
    snr: object,
    hz_class: object,
    distance_ly: object,
    clean_sector_count: object,
    spc_class: object,
) -> float:
    hz = normalize_hz_class(hz_class)
    spc = str(spc_class or "").strip().upper()
    if spc == "FP" or hz not in REVISIT_HZ_CLASSES:
        return 0.0

    visible = _safe_int(visible_transits)
    clean = _safe_int(clean_sector_count)
    snr_value = _safe_float(snr, 0.0)
    distance = _safe_float(distance_ly, float("inf"))
    if spc == "SPC_ART" and clean == 0:
        return 0.0

    score = 0.0
    score += 35.0 if hz == "KONSERVATIVE_HZ" else 30.0
    if distance <= 50:
        score += 22.0
    elif distance <= 100:
        score += 18.0
    elif distance <= REVISIT_MAX_DISTANCE_LY:
        score += 14.0
    elif distance <= MAX_DISTANCE_LY:
        score += 4.0
    score += min(max(snr_value - REVISIT_MIN_SNR, 0.0) * 2.0, 20.0)
    score += min(clean * 6.0, 18.0)
    if visible <= 1:
        score += 12.0
    elif visible == 2:
        score += 10.0
    elif visible >= 3:
        score += 4.0
    if spc == "SPC-C":
        score += 10.0
    elif spc == "SPC-B":
        score += 6.0
    elif spc == "SPC-A":
        score += 2.0
    elif spc == "SPC_ART":
        score -= 12.0
    return round(float(np.clip(score, 0.0, 100.0)), 3)


def next_recheck_label(priority: float, visible_transits: object) -> str:
    visible = _safe_int(visible_transits)
    if priority >= 75:
        return "NEXT_TESS_SECTOR_OR_ARCHIVE_RECHECK"
    if priority >= 55:
        return "NEXT_DATA_RELEASE_RECHECK"
    if priority > 0 and visible < 3:
        return "LOW_PRIORITY_RECHECK"
    return ""


def classify_spc_followup(
    *,
    visible_transits: object,
    transit_count: object,
    snr: object,
    hz_class: object,
    distance_ly: object,
    clean_sector_count: object,
    sector_count: object,
    fp: dict,
    existing_notes: object = "",
) -> dict:
    visible = _safe_int(visible_transits)
    transits = _safe_int(transit_count)
    clean = _safe_int(clean_sector_count)
    sectors = _safe_int(sector_count)
    snr_value = _safe_float(snr, 0.0)
    if existing_notes is None or (isinstance(existing_notes, float) and not np.isfinite(existing_notes)):
        notes = []
    else:
        notes = [
            part
            for part in str(existing_notes or "").split(";")
            if part and part.strip().lower() not in {"nan", "none", "null"}
        ]

    if _strong_fp_evidence(fp):
        spc_class = "FP"
        notes.append("FALSE_POSITIVE_EVIDENCE")
    elif _artifact_risk(fp) or bool(fp.get("is_fp")) or (sectors > 0 and clean == 0):
        spc_class = "SPC_ART"
        notes.append("ARTIFACT_OR_SYSTEMATICS_RISK")
    elif visible >= 3 and clean >= 2 and snr_value >= 10:
        spc_class = "SPC-A"
    elif visible >= 2 and clean >= 1 and snr_value >= REVISIT_MIN_SNR:
        spc_class = "SPC-B"
    elif (visible >= 1 or transits >= 1) and clean >= 1 and snr_value >= REVISIT_MIN_SNR:
        spc_class = "SPC-C"
    else:
        spc_class = "SPC_ART"
        notes.append("LOW_RECOVERY_OR_NOISY_SECTORS")

    revisit = is_hz_revisit_candidate(visible, hz_class, distance_ly, snr_value, clean, fp)
    if revisit:
        spc_class = "SPC-C"
        notes.insert(0, "HZ_REVISIT_CANDIDATE")

    priority = compute_revisit_priority(visible, snr_value, hz_class, distance_ly, clean, spc_class)
    deduped_notes = []
    seen = set()
    for note in notes:
        clean_note = note.strip()
        if clean_note and clean_note not in seen:
            seen.add(clean_note)
            deduped_notes.append(clean_note)

    return {
        "spc_class": spc_class,
        "status": "SPC-C" if revisit else spc_class,
        "revisit_priority": priority,
        "next_recheck": next_recheck_label(priority, visible),
        "notes": ";".join(deduped_notes),
        "is_hz_revisit_candidate": revisit,
    }


def evaluate_fp(time_arr, flux_arr, period, t0, duration, depth) -> dict:
    odd_d, even_d, oe_ratio = odd_even_check(time_arr, flux_arr, period, t0, duration)
    sec_ratio = secondary_eclipse_check(time_arr, flux_arr, period, t0, duration, depth)
    baseline = local_baseline_check(time_arr, flux_arr, period, t0, duration, depth)
    baseline_std = local_baseline_std_check(time_arr, flux_arr, period, t0, duration, depth)
    scatter = outside_scatter_check(time_arr, flux_arr, period, t0, duration, depth)

    oe_flag  = (oe_ratio is not None) and (oe_ratio < FP_OE_MIN_RATIO or oe_ratio > FP_OE_MAX_RATIO)
    sec_flag = (sec_ratio is not None) and (sec_ratio > FP_SEC_THRESHOLD)
    eclipse_fp = (oe_flag and sec_flag) if FP_REJECT_ON_BOTH else (oe_flag or sec_flag)
    is_fp = (
        eclipse_fp
        or baseline["fp_baseline_flag"]
        or baseline_std["fp_baseline_std_flag"]
        or scatter["fp_scatter_flag"]
    )

    return {
        "odd_depth": odd_d, "even_depth": even_d, "oe_ratio": oe_ratio,
        "sec_ratio": sec_ratio, "fp_oe_flag": oe_flag, "fp_sec_flag": sec_flag,
        "baseline_delta": baseline["baseline_delta"],
        "baseline_threshold": baseline["baseline_threshold"],
        "baseline_std_delta": baseline_std["baseline_std_delta"],
        "baseline_std_threshold": baseline_std["baseline_std_threshold"],
        "oot_scatter": scatter["oot_scatter"],
        "oot_scatter_ratio": scatter["oot_scatter_ratio"],
        "fp_baseline_flag": baseline["fp_baseline_flag"],
        "fp_baseline_std_flag": baseline_std["fp_baseline_std_flag"],
        "fp_scatter_flag": scatter["fp_scatter_flag"],
        "is_fp": is_fp,
    }


def build_coarse_period_grid(time_arr: np.ndarray, teff: Optional[float],
                             stellar_r: Optional[float]) -> np.ndarray:
    max_period = MAX_PERIOD
    hz = compute_hz(teff, stellar_r) if (teff and stellar_r) else None
    if hz:
        max_period = max(max_period, min(MAX_HZ_PERIOD, hz.opt_outer_d * HZ_PERIOD_BUFFER))
    baseline = float(np.nanmax(time_arr) - np.nanmin(time_arr)) if len(time_arr) else MIN_PERIOD
    if np.isfinite(baseline) and baseline > MIN_PERIOD:
        max_period = min(max_period, max(MIN_PERIOD * 1.1, baseline * 0.95))
    return np.geomspace(MIN_PERIOD, max_period, COARSE_PERIODS)


def build_fine_period_grid(best_period: float) -> np.ndarray:
    half_width = max(best_period * FINE_WINDOW_FRAC, 0.05)
    lo = max(MIN_PERIOD, best_period - half_width)
    hi = best_period + half_width
    return np.linspace(lo, hi, FINE_PERIODS)


def run_bls_search(time_arr: np.ndarray, flux_arr: np.ndarray,
                   teff: Optional[float], stellar_r: Optional[float]):
    bls = BoxLeastSquares(time_arr, flux_arr)
    coarse_periods = build_coarse_period_grid(time_arr, teff, stellar_r)
    coarse = bls.power(coarse_periods, BLS_DURATIONS)
    if len(coarse.power) == 0:
        return None

    coarse_idx = int(np.nanargmax(coarse.power))
    coarse_power = float(coarse.power[coarse_idx])
    if not np.isfinite(coarse_power):
        return None

    fine_periods = build_fine_period_grid(float(coarse.period[coarse_idx]))
    fine = bls.power(fine_periods, BLS_DURATIONS)
    if len(fine.power) == 0:
        return coarse, coarse_idx

    fine_idx = int(np.nanargmax(fine.power))
    fine_power = float(fine.power[fine_idx])
    if np.isfinite(fine_power) and fine_power >= coarse_power:
        return fine, fine_idx
    return coarse, coarse_idx


# ============================================================
# ★ BLS-WORKER  (top-level → picklable für ProcessPool)
# ============================================================

def _bls_worker(args: tuple) -> tuple:
    """
    Läuft im Kindprozess. Nimmt numpy-Arrays, gibt serialisierbares dict zurück.
    Signatur: (tic_id, time_arr, flux_arr, stellar_r, teff, distance_ly,
                sap_flux_arr, pdcsap_flux_arr) → (tic_id, result_dict)
    result_dict hat Keys: cand, fp, hz_status, hz_ci, hz_co, hz_oi, hz_oo
    Bei Fehler: (tic_id, {"error": str})
    """
    tic_id, time_arr, flux_arr, stellar_r, teff, distance_ly, sap_flux_arr, pdcsap_flux_arr = args
    try:
        # BLS
        if len(time_arr) < MIN_POINTS:
            return tic_id, None

        if len(BLS_DURATIONS) == 0:
            return tic_id, None

        flux_med = np.nanmedian(flux_arr)
        if not np.isfinite(flux_med):
            return tic_id, None
        if flux_med <= 0:
            flux_arr = flux_arr - flux_med + 1.0

        bls_result = run_bls_search(time_arr, flux_arr, teff, stellar_r)
        if bls_result is None:
            return tic_id, None
        result, idx = bls_result

        power = float(result.power[idx])
        if not np.isfinite(power) or power < POWER_THRESHOLD:
            return tic_id, None

        period   = float(result.period[idx])
        duration = float(result.duration[idx])
        t0       = float(result.transit_time[idx])
        depth    = float(result.depth[idx]) if hasattr(result, "depth") else np.nan

        if not np.isfinite(depth) or depth <= 0 or depth > MAX_TRANSIT_DEPTH:
            return tic_id, None

        quality = signal_quality(time_arr, flux_arr, period, t0, duration, depth)

        # Planetenradius
        rp = None
        if stellar_r and not np.isnan(stellar_r) and stellar_r > 0 and depth > 0:
            rp = float(np.sqrt(depth) * stellar_r * 109.1)
        if rp is not None and rp > MAX_CANDIDATE_RADIUS_EARTH:
            return tic_id, None

        # HZ + Sektor-/Revisit-Metriken vor dem harten Transitanzahl-Gate.
        hz = compute_hz(teff, stellar_r) if (teff and stellar_r) else None
        hz_status = hz.classify(period) if hz else None
        hz_class = hz.classify_hz_class(period) if hz else "UNKNOWN"
        sector_quality = compute_sector_quality(
            time_arr,
            flux_arr,
            period,
            t0,
            duration,
            depth,
            sap_flux_arr=sap_flux_arr,
            pdcsap_flux_arr=pdcsap_flux_arr,
        )

        # False-Positive
        fp = evaluate_fp(time_arr, flux_arr, period, t0, duration, depth)

        followup = classify_spc_followup(
            visible_transits=sector_quality["visible_transits"],
            transit_count=quality["transit_count"],
            snr=quality["snr"],
            hz_class=hz_class,
            distance_ly=distance_ly,
            clean_sector_count=sector_quality["clean_sector_count"],
            sector_count=sector_quality["sector_count"],
            fp=fp,
        )

        core_quality_pass = (
            quality["n_in_transit"] >= MIN_IN_TRANSIT_POINTS
            and quality["snr"] is not None
            and quality["snr"] >= MIN_TRANSIT_SNR
            and quality["duration_fraction"] <= MAX_DURATION_FRACTION
        )
        if not quality["passes"] and not (core_quality_pass and followup["is_hz_revisit_candidate"]):
            return tic_id, None

        cand = {"period": period, "duration": duration, "transit_time": t0,
                "power": power, "depth": depth, "planet_radius_earth": rp,
                "transit_snr": quality["snr"],
                "transit_count": quality["transit_count"],
                "n_in_transit": quality["n_in_transit"],
                "duration_fraction": quality["duration_fraction"],
                "visible_transits": sector_quality["visible_transits"]}

        return tic_id, {
            "cand": cand, "fp": fp,
            "hz_status":      hz_status,
            "hz_class":       hz_class,
            "hz_cons_inner_d": hz.cons_inner_d if hz else None,
            "hz_cons_outer_d": hz.cons_outer_d if hz else None,
            "hz_opt_inner_d":  hz.opt_inner_d  if hz else None,
            "hz_opt_outer_d":  hz.opt_outer_d  if hz else None,
            **sector_quality,
            **followup,
        }

    except Exception as e:
        return tic_id, {"error": f"{type(e).__name__}: {e}"}


# ============================================================
# DB
# ============================================================

def connect_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA cache_size=-200000;")
    conn.execute("PRAGMA mmap_size=268435456;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def ensure_dirs() -> None:
    LIGHTCURVE_BASE_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    for subdir in ("raw", "folded", "combined"):
        (CANDIDATE_PLOT_DIR / subdir).mkdir(parents=True, exist_ok=True)


def ensure_raw_table(conn):
    if REBUILD_ROHDATEN:
        conn.execute(f"DROP TABLE IF EXISTS {TABLE_RAW}")
    conn.execute(f"""
    CREATE TABLE IF NOT EXISTS {TABLE_RAW} (
        TIC INTEGER PRIMARY KEY, gaia_id TEXT, teff REAL, distance_ly REAL,
        tmag REAL, radius REAL, logg REAL, lightcurve_dir TEXT, planet_radius_earth REAL,
        best_period REAL, status TEXT, has_tess_data INTEGER DEFAULT 0,
        checked_at TEXT, error_msg TEXT
    )""")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_RAW}_status   ON {TABLE_RAW}(status)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_RAW}_has_tess ON {TABLE_RAW}(has_tess_data)")
    try:
        conn.execute(f"ALTER TABLE {TABLE_RAW} ADD COLUMN logg REAL")
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e).lower():
            raise
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_RAW}_logg ON {TABLE_RAW}(logg)")
    conn.commit()


def ensure_active_table(conn):
    if REBUILD_ACTIVE:
        conn.execute(f"DROP TABLE IF EXISTS {TABLE_ACTIVE}")
    conn.execute(f"CREATE TABLE IF NOT EXISTS {TABLE_ACTIVE} AS SELECT * FROM {TABLE_RAW} WHERE 1=0")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_ACTIVE}_tic    ON {TABLE_ACTIVE}(TIC)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_ACTIVE}_status ON {TABLE_ACTIVE}(status)")
    conn.commit()


def ensure_candidates_table(conn):
    if REBUILD_CANDIDATES:
        conn.execute(f"DROP TABLE IF EXISTS {TABLE_CANDIDATES}")
    conn.execute(f"""
    CREATE TABLE IF NOT EXISTS {TABLE_CANDIDATES} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        TIC INTEGER, gaia_id TEXT, teff REAL, distance_ly REAL, stellar_radius REAL,
        stellar_logg REAL,
        best_period REAL, duration REAL, depth REAL, transit_time REAL, power REAL,
        planet_radius_earth REAL, lightcurve_dir TEXT,
        transit_snr REAL, transit_count INTEGER, n_in_transit INTEGER,
        duration_fraction REAL,
        oe_ratio REAL, sec_ratio REAL, baseline_delta REAL, baseline_std_delta REAL,
        oot_scatter_ratio REAL,
        fp_oe_flag INTEGER DEFAULT 0, fp_sec_flag INTEGER DEFAULT 0,
        fp_baseline_flag INTEGER DEFAULT 0, fp_baseline_std_flag INTEGER DEFAULT 0,
        fp_scatter_flag INTEGER DEFAULT 0,
        is_fp INTEGER DEFAULT 0,
        hz_status TEXT, hz_class TEXT,
        sector_count INTEGER, clean_sector_count INTEGER,
        sector_quality_summary TEXT, visible_transits INTEGER,
        spc_class TEXT, revisit_priority REAL, next_recheck TEXT, notes TEXT,
        hz_cons_inner_d REAL, hz_cons_outer_d REAL,
        hz_opt_inner_d REAL, hz_opt_outer_d REAL,
        status TEXT DEFAULT 'CANDIDATE',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    for col, col_type in [
        ("transit_snr", "REAL"),
        ("transit_count", "INTEGER"),
        ("n_in_transit", "INTEGER"),
        ("duration_fraction", "REAL"),
        ("stellar_logg", "REAL"),
        ("baseline_delta", "REAL"),
        ("baseline_std_delta", "REAL"),
        ("oot_scatter_ratio", "REAL"),
        ("fp_baseline_flag", "INTEGER DEFAULT 0"),
        ("fp_baseline_std_flag", "INTEGER DEFAULT 0"),
        ("fp_scatter_flag", "INTEGER DEFAULT 0"),
        ("hz_class", "TEXT"),
        ("sector_count", "INTEGER"),
        ("clean_sector_count", "INTEGER"),
        ("sector_quality_summary", "TEXT"),
        ("visible_transits", "INTEGER"),
        ("spc_class", "TEXT"),
        ("revisit_priority", "REAL"),
        ("next_recheck", "TEXT"),
        ("notes", "TEXT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE {TABLE_CANDIDATES} ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_CANDIDATES}_tic ON {TABLE_CANDIDATES}(TIC)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_CANDIDATES}_hz  ON {TABLE_CANDIDATES}(hz_status)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_CANDIDATES}_hz_class ON {TABLE_CANDIDATES}(hz_class)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_CANDIDATES}_spc ON {TABLE_CANDIDATES}(spc_class)")
    conn.commit()


# ============================================================
# HILFSFUNKTIONEN
# ============================================================

def pick_col(df, candidates):
    cols = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in cols:
            return cols[cand.lower()]
    return None


def stitch_collection(coll):
    try:
        return coll.stitch()
    except Exception:
        pieces = [x for x in coll if x is not None]
        if not pieces:
            return None
        lc = pieces[0]
        for extra in pieces[1:]:
            lc = lc.append(extra)
        return lc


def safe_sleep(s):
    if s and s > 0:
        time.sleep(s)


def fmt_exc(e):
    return f"{type(e).__name__}: {e}"[:500]


def progress(iterable, **kwargs):
    if not HAS_TQDM:
        return iterable
    if os.environ.get("PROGRESS_BARS", "1") == "safe":
        kwargs["leave"] = False
    stream = sys.__stderr__ or sys.stderr
    try:
        stream.write("")
        stream.flush()
    except (BrokenPipeError, OSError, ValueError, AttributeError):
        return iterable

    kwargs.setdefault("file", stream)
    kwargs.setdefault("dynamic_ncols", True)
    kwargs.setdefault("mininterval", 0.5)
    try:
        return tqdm(iterable, **kwargs)
    except (BrokenPipeError, OSError, ValueError):
        return iterable


def progress_bar(**kwargs):
    if not HAS_TQDM:
        return None
    stream = sys.__stderr__ or sys.stderr
    try:
        stream.write("")
        stream.flush()
    except (BrokenPipeError, OSError, ValueError, AttributeError):
        return None

    kwargs.setdefault("file", stream)
    kwargs.setdefault("dynamic_ncols", True)
    kwargs.setdefault("mininterval", 0.5)
    try:
        return tqdm(**kwargs)
    except (BrokenPipeError, OSError, ValueError):
        return None


# ============================================================
# ★ LC-CACHE  (wiederverwende bereits gespeicherte CSVs)
# ============================================================

def get_lc_cache_path(tic_id: int) -> Path:
    return LIGHTCURVE_BASE_DIR / f"TIC_{tic_id}" / f"TIC_{tic_id}_lightcurve.csv"


def try_load_lc_cache_with_aux(
    tic_id: int,
) -> Optional[Tuple[np.ndarray, np.ndarray, Optional[np.ndarray], Optional[np.ndarray]]]:
    """
    Lädt vorhandene Lichtkurven-CSV vom Disk. Kein Netzwerk nötig.
    Gibt (time_arr, flux_arr, sap_flux_arr, pdcsap_flux_arr) zurück, oder None wenn nicht vorhanden.
    """
    path = get_lc_cache_path(tic_id)
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path)
        if {"time", "flux"}.issubset(df.columns):
            t = np.asarray(df["time"], dtype=float)
            f = np.asarray(df["flux"], dtype=float)
            sap = np.asarray(df["sap_flux"], dtype=float) if "sap_flux" in df.columns else None
            pdc = np.asarray(df["pdcsap_flux"], dtype=float) if "pdcsap_flux" in df.columns else None
        else:
            arr = np.loadtxt(path, delimiter=",", skiprows=1, usecols=(0, 1), ndmin=2)
            t = np.asarray(arr[:, 0], dtype=float)
            f = np.asarray(arr[:, 1], dtype=float)
            sap = None
            pdc = None
        if len(t) == len(f) and len(t) > 0:
            return t, f, sap, pdc
    except Exception as e:
        log(f"⚠️  Cache TIC {tic_id} nicht lesbar: {fmt_exc(e)}")
    return None


def try_load_lc_cache(tic_id: int) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    loaded = try_load_lc_cache_with_aux(tic_id)
    if loaded is None:
        return None
    return loaded[0], loaded[1]


def prepare_arrays_with_aux(
    time_arr: np.ndarray,
    flux_arr: np.ndarray,
    sap_flux_arr: Optional[np.ndarray] = None,
    pdcsap_flux_arr: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray], Optional[np.ndarray]]:
    """
    Numpy-only Vorbereitung (für Cache-Daten, kein lightkurve-Objekt nötig).
    Outlier-Clipping + Normalisierung.
    """
    time_arr = np.asarray(time_arr, dtype=float)
    flux_arr = np.asarray(flux_arr, dtype=float)
    if time_arr.shape != flux_arr.shape:
        return np.array([], dtype=float), np.array([], dtype=float), None, None

    sap = None
    pdc = None
    if sap_flux_arr is not None and np.asarray(sap_flux_arr).shape == time_arr.shape:
        sap = np.asarray(sap_flux_arr, dtype=float)
    if pdcsap_flux_arr is not None and np.asarray(pdcsap_flux_arr).shape == time_arr.shape:
        pdc = np.asarray(pdcsap_flux_arr, dtype=float)

    mask = np.isfinite(time_arr) & np.isfinite(flux_arr)
    t, f = time_arr[mask], flux_arr[mask]
    if sap is not None:
        sap = sap[mask]
    if pdc is not None:
        pdc = pdc[mask]
    if len(t) == 0:
        return t, f, sap, pdc

    # Sigma-Clip (5σ)
    med = np.nanmedian(f)
    std = np.nanstd(f)
    if np.isfinite(std) and std > 0:
        mask2 = np.abs(f - med) < 5 * std
        t, f  = t[mask2], f[mask2]
        if sap is not None:
            sap = sap[mask2]
        if pdc is not None:
            pdc = pdc[mask2]
    if len(t) == 0:
        return t, f, sap, pdc

    # Normalisieren
    med = np.nanmedian(f)
    f   = f / med if np.isfinite(med) and abs(med) > 1e-6 else f - med + 1.0
    order = np.argsort(t)
    t, f = t[order], f[order]
    if sap is not None:
        sap = sap[order]
    if pdc is not None:
        pdc = pdc[order]
    return t, f, sap, pdc


def prepare_arrays(time_arr: np.ndarray, flux_arr: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    t, f, _, _ = prepare_arrays_with_aux(time_arr, flux_arr)
    return t, f


def _lightcurve_column(lc, names: tuple[str, ...]) -> Optional[np.ndarray]:
    colnames = set(getattr(lc, "colnames", []) or [])
    for name in names:
        if name in colnames:
            try:
                col = lc[name]
                return np.asarray(col.value if hasattr(col, "value") else col, dtype=float)
            except Exception:
                return None
    return None


def prepare_lc_fresh_with_aux(lc) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray], Optional[np.ndarray]]:
    """Vollständige Vorbereitung für frisch heruntergeladene lightkurve-Objekte."""
    lc = lc.remove_nans()
    try:
        lc = lc.remove_outliers(sigma=5)
    except Exception:
        pass
    try:
        lc = lc.flatten(window_length=401)
    except Exception:
        pass
    t = np.asarray(lc.time.value, dtype=float)
    f = np.asarray(lc.flux.value if hasattr(lc.flux, "value") else lc.flux, dtype=float)
    sap = _lightcurve_column(lc, ("sap_flux", "SAP_FLUX"))
    pdc = _lightcurve_column(lc, ("pdcsap_flux", "PDCSAP_FLUX"))
    return prepare_arrays_with_aux(t, f, sap, pdc)


def prepare_lc_fresh(lc) -> Tuple[np.ndarray, np.ndarray]:
    t, f, _, _ = prepare_lc_fresh_with_aux(lc)
    return t, f


def save_lightcurve_csv(
    tic_id: int,
    time_arr: np.ndarray,
    flux_arr: np.ndarray,
    sap_flux_arr: Optional[np.ndarray] = None,
    pdcsap_flux_arr: Optional[np.ndarray] = None,
) -> str:
    target_dir = LIGHTCURVE_BASE_DIR / f"TIC_{tic_id}"
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"TIC_{tic_id}_lightcurve.csv"
    data = {
        "time": np.asarray(time_arr, dtype=float),
        "flux": np.asarray(flux_arr, dtype=float),
    }
    if sap_flux_arr is not None and len(sap_flux_arr) == len(time_arr):
        data["sap_flux"] = np.asarray(sap_flux_arr, dtype=float)
    if pdcsap_flux_arr is not None and len(pdcsap_flux_arr) == len(time_arr):
        data["pdcsap_flux"] = np.asarray(pdcsap_flux_arr, dtype=float)
    pd.DataFrame(data).to_csv(path, index=False)
    return str(path)


def _safe_plot_token(value) -> str:
    text = str(value if value is not None else "UNKNOWN")
    keep = []
    for ch in text:
        keep.append(ch if ch.isalnum() or ch in "._-" else "_")
    return "".join(keep)


def _plot_sample(time_arr: np.ndarray, flux_arr: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    if PLOT_MAX_POINTS <= 0 or len(time_arr) <= PLOT_MAX_POINTS:
        return time_arr, flux_arr
    idx = np.linspace(0, len(time_arr) - 1, PLOT_MAX_POINTS, dtype=int)
    return time_arr[idx], flux_arr[idx]


def save_candidate_plots(
    tic_id: int,
    time_arr: np.ndarray,
    flux_arr: np.ndarray,
    cand: dict,
    worker_result: dict,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    if not AUTO_PLOT_CANDIDATES:
        return None, None, None
    if worker_result.get("fp", {}).get("is_fp") and not AUTO_PLOT_FP_CANDIDATES:
        return None, None, None

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        log(f"⚠️  Plot-Modul nicht verfügbar: {fmt_exc(e)}")
        return None, None, None

    try:
        for subdir in ("raw", "folded", "combined"):
            (CANDIDATE_PLOT_DIR / subdir).mkdir(parents=True, exist_ok=True)

        period = float(cand["period"])
        duration = float(cand["duration"])
        t0 = float(cand["transit_time"])
        radius = cand.get("planet_radius_earth")
        snr = cand.get("transit_snr")
        hz_status = worker_result.get("hz_status") or "UNKNOWN"

        prefix = (
            f"TIC_{tic_id}_{_safe_plot_token(hz_status)}"
            f"_P{period:.6f}d"
            f"_Rp{float(radius):.3f}Re" if radius is not None else
            f"TIC_{tic_id}_{_safe_plot_token(hz_status)}_P{period:.6f}d_RpNA"
        )
        if snr is not None:
            prefix += f"_SNR{float(snr):.2f}"

        raw_path = CANDIDATE_PLOT_DIR / "raw" / f"{prefix}_raw.png"
        folded_path = CANDIDATE_PLOT_DIR / "folded" / f"{prefix}_folded.png"
        combined_path = CANDIDATE_PLOT_DIR / "combined" / f"{prefix}_combined.png"

        t = np.asarray(time_arr, dtype=float)
        f = np.asarray(flux_arr, dtype=float)
        finite = np.isfinite(t) & np.isfinite(f)
        t, f = t[finite], f[finite]
        if len(t) == 0:
            return None, None, None

        t_plot, f_plot = _plot_sample(t, f)
        phase_days = ((t - t0 + period / 2.0) % period) - period / 2.0
        phase_hours = phase_days * 24.0
        order = np.argsort(phase_hours)
        phase_hours = phase_hours[order]
        folded_flux = f[order]
        phase_plot, folded_plot = _plot_sample(phase_hours, folded_flux)

        title = (
            f"TIC {tic_id} | P={period:.4f} d | "
            f"Rp={float(radius):.2f} Re | SNR={float(snr):.1f} | {hz_status}"
            if radius is not None and snr is not None
            else f"TIC {tic_id} | P={period:.4f} d | {hz_status}"
        )

        fig, ax = plt.subplots(figsize=(11, 4.5), dpi=150)
        ax.scatter(t_plot, f_plot, s=3, alpha=0.55, linewidths=0)
        ax.set_title(title)
        ax.set_xlabel("Zeit [BTJD]")
        ax.set_ylabel("Normalisierter Flux")
        ax.grid(alpha=0.25)
        fig.tight_layout()
        fig.savefig(raw_path)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(9, 4.8), dpi=150)
        ax.scatter(phase_plot, folded_plot, s=4, alpha=0.5, linewidths=0)
        transit_half_hours = duration * 24.0 / 2.0
        ax.axvspan(-transit_half_hours, transit_half_hours, color="tab:red", alpha=0.12)
        ax.axvline(0, color="tab:red", alpha=0.6, linewidth=1)
        ax.set_title(f"Gefaltet | {title}")
        ax.set_xlabel("Phase relativ zum Transit [Stunden]")
        ax.set_ylabel("Normalisierter Flux")
        ax.grid(alpha=0.25)
        fig.tight_layout()
        fig.savefig(folded_path)
        plt.close(fig)

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8), dpi=150)
        ax1.scatter(t_plot, f_plot, s=3, alpha=0.55, linewidths=0)
        ax1.set_title(title)
        ax1.set_xlabel("Zeit [BTJD]")
        ax1.set_ylabel("Flux")
        ax1.grid(alpha=0.25)

        ax2.scatter(phase_plot, folded_plot, s=4, alpha=0.5, linewidths=0)
        ax2.axvspan(-transit_half_hours, transit_half_hours, color="tab:red", alpha=0.12)
        ax2.axvline(0, color="tab:red", alpha=0.6, linewidth=1)
        ax2.set_title("Gefaltete Transitansicht")
        ax2.set_xlabel("Phase relativ zum Transit [Stunden]")
        ax2.set_ylabel("Flux")
        ax2.grid(alpha=0.25)
        fig.tight_layout()
        fig.savefig(combined_path)
        plt.close(fig)

        return str(raw_path), str(folded_path), str(combined_path)
    except Exception as e:
        log(f"⚠️  Plot TIC {tic_id}: {fmt_exc(e)}")
        try:
            plt.close("all")
        except Exception:
            pass
        return None, None, None


# ============================================================
# MAST / TIC-IMPORT
# ============================================================

def query_tic_block(teff_min, teff_max):
    for attempt in range(1, QUERY_MAX_TRIES + 1):
        try:
            log(f"🔄 TIC-Block {teff_min}–{teff_max} K | Versuch {attempt}")
            res = Catalogs.query_criteria(
                catalog="Tic", Teff=[teff_min, teff_max],
                Tmag=[0, TESSMAG_MAX], rad=[RADIUS_MIN, RADIUS_MAX],
                logg=[LOGG_MIN, LOGG_MAX],
            )
            df = res.to_pandas()
            log(f"✅ Block {teff_min}–{teff_max} | {len(df)} Zeilen")
            return df
        except Exception as e:
            log(f"⚠️  {fmt_exc(e)}")
            if attempt < QUERY_MAX_TRIES:
                safe_sleep(QUERY_SLEEP_SECONDS)
    return pd.DataFrame()


def build_raw_dataframe(df):
    tic_col  = pick_col(df, ["ID", "TIC", "ticid"])
    teff_col = pick_col(df, ["Teff", "teff"])
    gaia_col = pick_col(df, ["GAIA", "GAIA_ID", "gaia_id"])
    tmag_col = pick_col(df, ["Tmag", "tmag"])
    rad_col  = pick_col(df, ["rad", "Rad", "radius"])
    logg_col = pick_col(df, ["logg", "Logg", "LOGG"])
    plx_col  = pick_col(df, ["plx", "Plx", "parallax"])

    if not tic_col or not teff_col:
        raise ValueError("TIC- oder Teff-Spalte fehlt.")

    df = df.copy()
    for col in filter(None, [teff_col, tmag_col, rad_col, logg_col]):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if plx_col:
        plx = pd.to_numeric(df[plx_col], errors="coerce")
        df["distance_ly"] = np.where(plx > 0, 1000.0 / plx * 3.26156, np.nan)
    else:
        df["distance_ly"] = np.nan

    result = pd.DataFrame({
        "TIC":         pd.to_numeric(df[tic_col], errors="coerce"),
        "gaia_id":     df[gaia_col].astype(str) if gaia_col else None,
        "teff":        pd.to_numeric(df[teff_col], errors="coerce"),
        "distance_ly": pd.to_numeric(df["distance_ly"], errors="coerce"),
        "tmag":        pd.to_numeric(df[tmag_col], errors="coerce") if tmag_col else np.nan,
        "radius":      pd.to_numeric(df[rad_col], errors="coerce")  if rad_col  else np.nan,
        "logg":        pd.to_numeric(df[logg_col], errors="coerce") if logg_col else np.nan,
        "lightcurve_dir": None, "planet_radius_earth": np.nan, "best_period": np.nan,
        "status": "NEW", "has_tess_data": 0, "checked_at": None, "error_msg": None,
    })

    result = result.dropna(subset=["TIC", "teff"]).copy()
    result["TIC"] = result["TIC"].astype(int)
    result = result[(result["teff"] >= TEFF_MIN) & (result["teff"] <= TEFF_MAX)].copy()
    if result["distance_ly"].notna().sum() > 0:
        result = result[result["distance_ly"] <= MAX_DISTANCE_LY].copy()
    if result["radius"].notna().sum() > 0:
        result = result[(result["radius"] >= RADIUS_MIN) & (result["radius"] <= RADIUS_MAX)].copy()
    if REQUIRE_DWARF_LOGG:
        result = result[(result["logg"] >= LOGG_MIN) & (result["logg"] <= LOGG_MAX)].copy()
    elif result["logg"].notna().sum() > 0:
        result = result[result["logg"].isna() | ((result["logg"] >= LOGG_MIN) & (result["logg"] <= LOGG_MAX))].copy()
    if result["tmag"].notna().sum() > 0:
        result = result[result["tmag"] <= TESSMAG_MAX].copy()
    return result.drop_duplicates(subset=["TIC"], keep="first").copy()


def save_rohdaten_block(conn, df):
    if df.empty:
        return 0
    rows = [(int(r.TIC), r.gaia_id,
             float(r.teff) if pd.notna(r.teff) else None,
             float(r.distance_ly) if pd.notna(r.distance_ly) else None,
             float(r.tmag) if pd.notna(r.tmag) else None,
             float(r.radius) if pd.notna(r.radius) else None,
             float(r.logg) if pd.notna(r.logg) else None,
             None, None, None, r.status, 0, None, None)
            for r in df.itertuples(index=False)]
    before = conn.execute(f"SELECT COUNT(*) FROM {TABLE_RAW}").fetchone()[0]
    conn.executemany(f"""
        INSERT OR IGNORE INTO {TABLE_RAW}
        (TIC, gaia_id, teff, distance_ly, tmag, radius, logg, lightcurve_dir,
         planet_radius_earth, best_period, status, has_tess_data, checked_at, error_msg)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, rows)
    conn.commit()
    return conn.execute(f"SELECT COUNT(*) FROM {TABLE_RAW}").fetchone()[0] - before


def import_blocks_to_rohdaten(conn):
    for tmin, tmax in TEFF_BLOCKS:
        already = conn.execute(
            f"SELECT COUNT(*) FROM {TABLE_RAW} WHERE teff >= ? AND teff < ?", (tmin, tmax)
        ).fetchone()[0]
        if already and not REBUILD_ROHDATEN:
            log(f"⏭️  Block {tmin}–{tmax} K übersprungen ({already} vorhanden)")
            continue
        part = query_tic_block(tmin, tmax)
        if part.empty:
            safe_sleep(BLOCK_SLEEP_SECONDS)
            continue
        inserted = save_rohdaten_block(conn, build_raw_dataframe(part))
        log(f"💾 Block {tmin}–{tmax} → {inserted} neue Einträge")
        safe_sleep(BLOCK_SLEEP_SECONDS)
    log(f"✅ Gesamt in {TABLE_RAW}: {conn.execute(f'SELECT COUNT(*) FROM {TABLE_RAW}').fetchone()[0]}")


# ============================================================
# TESS-CHECK
# ============================================================

def _extract_tic(name):
    name = str(name).strip()
    for prefix in ["TIC ", "TIC", "tic ", "tic"]:
        if name.lower().startswith(prefix.lower()):
            try:
                return int(name[len(prefix):].strip())
            except ValueError:
                pass
    try:
        return int(name)
    except ValueError:
        return None


def batch_tess_check(tic_list):
    has_data = set()
    total = len(tic_list)
    batch_starts = range(0, total, TESS_BATCH_SIZE)
    if HAS_TQDM:
        batch_starts = progress(
            batch_starts,
            total=(total + TESS_BATCH_SIZE - 1) // TESS_BATCH_SIZE,
            desc="TESS-Check",
            unit="batch",
        )
    for i in batch_starts:
        batch = tic_list[i:i + TESS_BATCH_SIZE]
        for attempt in range(1, TESS_BATCH_RETRIES + 1):
            try:
                obs = Observations.query_criteria(
                    target_name=[str(t) for t in batch],
                    obs_collection="TESS", dataproduct_type="timeseries",
                )
                if obs is not None and len(obs) > 0:
                    obs_df   = obs.to_pandas()
                    name_col = pick_col(obs_df, ["target_name", "s_target_name"])
                    if name_col:
                        batch_set = set(batch)
                        for raw in obs_df[name_col].unique():
                            tic = _extract_tic(raw)
                            if tic and tic in batch_set:
                                has_data.add(tic)
                break
            except Exception as e:
                log(f"⚠️  Batch {i}–{i+len(batch)} V{attempt}: {fmt_exc(e)}")
                if attempt < TESS_BATCH_RETRIES:
                    safe_sleep(TESS_BATCH_RETRY_SLEEP * attempt)
        log(f"📡 {min(i+TESS_BATCH_SIZE, total)}/{total} | Treffer: {len(has_data)}")
        safe_sleep(TESS_BATCH_SLEEP)
    return has_data


def update_tess_availability(conn):
    if TESS_CHECK_LIMIT == 0:
        log("⏭️  TESS-Check übersprungen (TESS_CHECK_LIMIT=0).")
        return
    limit = f"LIMIT {int(TESS_CHECK_LIMIT)}" if TESS_CHECK_LIMIT else ""
    rows  = conn.execute(
        f"SELECT TIC FROM {TABLE_RAW} WHERE checked_at IS NULL ORDER BY TIC {limit}"
    ).fetchall()
    if not rows:
        log("⚠️  Keine ungeprüften TICs.")
        return
    tic_list = [r[0] for r in rows]
    log(f"📡 TESS-Check für {len(tic_list)} TICs ...")
    has_data = batch_tess_check(tic_list)
    no_data  = [t for t in tic_list if t not in has_data]
    if has_data:
        conn.executemany(
            f"UPDATE {TABLE_RAW} SET has_tess_data=1, checked_at=datetime('now') WHERE TIC=?",
            [(t,) for t in has_data])
    if no_data:
        conn.executemany(
            f"UPDATE {TABLE_RAW} SET has_tess_data=0, checked_at=datetime('now') WHERE TIC=?",
            [(t,) for t in no_data])
    conn.commit()
    log(f"✅ TESS: {len(has_data)} mit Daten | {len(no_data)} ohne")


# ============================================================
# ACTIVE TABLE
# ============================================================

def build_active_table(conn):
    conn.execute(f"DELETE FROM {TABLE_ACTIVE}")
    parts = [f"teff BETWEEN {TEFF_MIN} AND {TEFF_MAX}"]
    if conn.execute(f"SELECT SUM(CASE WHEN distance_ly IS NOT NULL THEN 1 ELSE 0 END) FROM {TABLE_RAW}").fetchone()[0]:
        parts.append(f"distance_ly <= {MAX_DISTANCE_LY}")
    parts.append(f"radius BETWEEN {RADIUS_MIN} AND {RADIUS_MAX}")
    if REQUIRE_DWARF_LOGG:
        parts.append(f"logg BETWEEN {LOGG_MIN} AND {LOGG_MAX}")
    else:
        parts.append(f"(logg IS NULL OR logg BETWEEN {LOGG_MIN} AND {LOGG_MAX})")
    if CHECK_TESS_DATA:
        parts.append("has_tess_data = 1")
    parts.append("(status IS NULL OR status IN ('NEW','RECHECK','RECHECK_NEW_SECTOR'))")
    conn.execute(f"INSERT INTO {TABLE_ACTIVE} SELECT * FROM {TABLE_RAW} WHERE {' AND '.join(parts)}")
    conn.commit()
    n = conn.execute(f"SELECT COUNT(*) FROM {TABLE_ACTIVE}").fetchone()[0]
    log(f"🚀 {TABLE_ACTIVE}: {n} Targets")


# ============================================================
# ★ DOWNLOAD  (einzeln, wird vom ThreadPool aufgerufen)
# ============================================================

def _download_one(tic_id: int):
    try:
        sr = search_lightcurve(f"TIC {tic_id}", mission="TESS")
        if len(sr) > 0:
            if MAX_LIGHTCURVES_PER_TARGET > 0:
                sr = sr[:MAX_LIGHTCURVES_PER_TARGET]
            coll = sr.download_all(quality_bitmask=QUALITY_BITMASK)
            if coll and len(coll) > 0:
                lc = stitch_collection(coll)
                if lc is not None:
                    return lc
    except Exception:
        pass
    if not ENABLE_TESSCUT_FALLBACK:
        return None
    try:
        sr2 = search_tesscut(f"TIC {tic_id}")
        if len(sr2) > 0:
            if MAX_LIGHTCURVES_PER_TARGET > 0:
                sr2 = sr2[:MAX_LIGHTCURVES_PER_TARGET]
            tpfs = sr2.download_all(cutout_size=11)
            if tpfs and len(tpfs) > 0:
                lcs = []
                for tpf in tpfs:
                    try:
                        lcs.append(tpf.to_lightcurve(aperture_mask="threshold"))
                    except Exception:
                        pass
                if lcs:
                    lc = stitch_collection(LightCurveCollection(lcs))
                    if lc is not None:
                        return lc
    except Exception:
        pass
    return None


def get_lightcurve(tic_id: int):
    for attempt in range(1, DOWNLOAD_RETRIES + 1):
        lc = _download_one(tic_id)
        if lc is not None:
            return lc
        if attempt < DOWNLOAD_RETRIES:
            safe_sleep(3)
    return None


def _download_cache_worker(tic_id: int, result_queue) -> None:
    """
    Eigenständiger Download-Prozess.
    Wichtig: Der Parent kann diesen Prozess hart beenden, falls Lightkurve/MAST hängt.
    """
    try:
        lc = get_lightcurve(tic_id)
        if lc is None:
            result_queue.put({"tic": tic_id, "status": "no_lc"})
            return
        t, f, sap, pdc = prepare_lc_fresh_with_aux(lc)
        if len(t) == 0:
            result_queue.put({"tic": tic_id, "status": "too_few_points", "points": 0})
            return
        path = save_lightcurve_csv(tic_id, t, f, sap, pdc)
        result_queue.put({"tic": tic_id, "status": "ok", "path": path, "points": int(len(t))})
    except Exception as e:
        result_queue.put({"tic": tic_id, "status": "error", "error": fmt_exc(e)})


def download_lightcurves_to_cache(tic_ids: List[int]) -> Dict[int, dict]:
    """
    Lädt eine Batch-Liste in killbaren Prozessen in den CSV-Cache.
    Threads reichen hier nicht, weil blockierende Netzwerk-/FITS-Aufrufe nicht sauber
    abgebrochen werden können.
    """
    if not tic_ids:
        return {}

    try:
        ctx = mp.get_context(DOWNLOAD_START_METHOD)
    except ValueError:
        ctx = mp.get_context()

    results: Dict[int, dict] = {}
    pending = list(tic_ids)
    running: Dict[int, Tuple[mp.Process, object, float]] = {}
    batch_deadline = time.monotonic() + DOWNLOAD_BATCH_TIMEOUT_SECONDS
    dl_bar = progress_bar(total=len(tic_ids), desc="  Downloads", leave=False)

    def finish(tic: int, result: dict) -> None:
        if tic not in results:
            results[tic] = result
            if dl_bar is not None:
                dl_bar.update(1)

    def start_next() -> bool:
        if not pending:
            return False
        tic = int(pending.pop(0))
        q = ctx.Queue()
        proc = ctx.Process(target=_download_cache_worker, args=(tic, q), daemon=True)
        proc.start()
        running[tic] = (proc, q, time.monotonic())
        return True

    try:
        while pending and len(running) < DOWNLOAD_WORKERS:
            start_next()

        while running:
            now = time.monotonic()
            if now >= batch_deadline:
                for tic, (proc, q, started) in list(running.items()):
                    if proc.is_alive():
                        proc.terminate()
                        proc.join(timeout=2)
                        if proc.is_alive():
                            proc.kill()
                    proc.join(timeout=1)
                    finish(tic, {"status": "timeout", "error": "DOWNLOAD_BATCH_TIMEOUT"})
                    running.pop(tic, None)
                break

            for tic, (proc, q, started) in list(running.items()):
                result = None
                try:
                    result = q.get_nowait()
                except queue.Empty:
                    pass

                if result is not None:
                    proc.join(timeout=1)
                    finish(tic, result)
                    running.pop(tic, None)
                    continue

                if now - started > DOWNLOAD_TARGET_TIMEOUT_SECONDS:
                    if proc.is_alive():
                        proc.terminate()
                        proc.join(timeout=2)
                        if proc.is_alive():
                            proc.kill()
                    proc.join(timeout=1)
                    finish(tic, {"status": "timeout", "error": "DOWNLOAD_TARGET_TIMEOUT"})
                    running.pop(tic, None)
                    continue

                if not proc.is_alive():
                    proc.join(timeout=1)
                    try:
                        result = q.get_nowait()
                    except queue.Empty:
                        result = {"status": "no_lc"}
                    finish(tic, result)
                    running.pop(tic, None)

            while pending and len(running) < DOWNLOAD_WORKERS and time.monotonic() < batch_deadline:
                start_next()

            if running:
                safe_sleep(0.25)
    finally:
        for tic, (proc, q, started) in list(running.items()):
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=2)
                if proc.is_alive():
                    proc.kill()
            proc.join(timeout=1)
            finish(tic, {"status": "timeout", "error": "DOWNLOAD_INTERRUPTED"})
        if dl_bar is not None:
            dl_bar.close()

    for tic in pending:
        finish(int(tic), {"status": "timeout", "error": "DOWNLOAD_NOT_STARTED"})

    return results


# ============================================================
# DB — KANDIDATEN & STATUS
# ============================================================

def candidate_exists(conn, tic_id, period, tol=0.02):
    return conn.execute(
        f"SELECT COUNT(*) FROM {TABLE_CANDIDATES} WHERE TIC=? AND ABS(best_period-?)<=?",
        (tic_id, period, tol)
    ).fetchone()[0] > 0


def _row_value(row, name: str):
    if isinstance(row, pd.Series):
        return row.get(name)
    return getattr(row, name)


def save_candidate(conn, row, cand: dict, lc_path: Optional[str], worker_result: dict,
                   commit: bool = True) -> bool:
    tic = int(_row_value(row, "TIC"))
    if candidate_exists(conn, tic, float(cand["period"])):
        return False
    teff = _row_value(row, "teff")
    distance_ly = _row_value(row, "distance_ly")
    radius = _row_value(row, "radius")
    logg = _row_value(row, "logg")
    fp = worker_result.get("fp", {})
    conn.execute(f"""
    INSERT INTO {TABLE_CANDIDATES}
    (TIC, gaia_id, teff, distance_ly, stellar_radius, stellar_logg,
     best_period, duration, depth, transit_time, power, planet_radius_earth, lightcurve_dir,
     transit_snr, transit_count, n_in_transit, duration_fraction,
     oe_ratio, sec_ratio, baseline_delta, baseline_std_delta, oot_scatter_ratio,
     fp_oe_flag, fp_sec_flag, fp_baseline_flag, fp_baseline_std_flag, fp_scatter_flag, is_fp,
     hz_status, hz_class, sector_count, clean_sector_count, sector_quality_summary,
     visible_transits, spc_class, revisit_priority, next_recheck, notes,
     hz_cons_inner_d, hz_cons_outer_d, hz_opt_inner_d, hz_opt_outer_d, status)
    VALUES ({','.join(['?'] * 43)})
    """, (
        tic,
        _row_value(row, "gaia_id"),
        float(teff)        if pd.notna(teff)        else None,
        float(distance_ly) if pd.notna(distance_ly) else None,
        float(radius)      if pd.notna(radius)      else None,
        float(logg)        if pd.notna(logg)        else None,
        float(cand["period"]),    float(cand["duration"]),
        float(cand["depth"]),     float(cand["transit_time"]),
        float(cand["power"]),
        float(cand["planet_radius_earth"]) if cand["planet_radius_earth"] is not None else None,
        lc_path,
        float(cand["transit_snr"]) if cand.get("transit_snr") is not None else None,
        int(cand["transit_count"]) if cand.get("transit_count") is not None else None,
        int(cand["n_in_transit"]) if cand.get("n_in_transit") is not None else None,
        float(cand["duration_fraction"]) if cand.get("duration_fraction") is not None else None,
        fp.get("oe_ratio"),       fp.get("sec_ratio"),
        fp.get("baseline_delta"), fp.get("baseline_std_delta"), fp.get("oot_scatter_ratio"),
        int(fp.get("fp_oe_flag", False)),
        int(fp.get("fp_sec_flag", False)),
        int(fp.get("fp_baseline_flag", False)),
        int(fp.get("fp_baseline_std_flag", False)),
        int(fp.get("fp_scatter_flag", False)),
        int(fp.get("is_fp", False)),
        worker_result.get("hz_status"),
        worker_result.get("hz_class") or normalize_hz_class(worker_result.get("hz_status")),
        _safe_int(worker_result.get("sector_count")),
        _safe_int(worker_result.get("clean_sector_count")),
        worker_result.get("sector_quality_summary"),
        _safe_int(worker_result.get("visible_transits")),
        worker_result.get("spc_class"),
        _safe_float(worker_result.get("revisit_priority"), 0.0),
        worker_result.get("next_recheck"),
        worker_result.get("notes"),
        worker_result.get("hz_cons_inner_d"), worker_result.get("hz_cons_outer_d"),
        worker_result.get("hz_opt_inner_d"),  worker_result.get("hz_opt_outer_d"),
        worker_result.get("status") or "CANDIDATE",
    ))
    if commit:
        conn.commit()
    return True


def update_status(conn, tic_id, status, period=None, rp=None, lc_dir=None, err=None,
                  commit: bool = True):
    for table in [TABLE_RAW, TABLE_ACTIVE]:
        try:
            conn.execute(f"""
            UPDATE {table}
            SET status=?,
                best_period=COALESCE(?,best_period),
                planet_radius_earth=COALESCE(?,planet_radius_earth),
                lightcurve_dir=COALESCE(?,lightcurve_dir),
                error_msg=?, checked_at=datetime('now')
            WHERE TIC=?
            """, (status, period, rp, lc_dir, err, tic_id))
        except Exception:
            pass
    if commit:
        conn.commit()


# ============================================================
# ★ SCAN-LOOP  (Download-Prozesse + BLS-ProcessPool)
# ============================================================

def get_scan_targets(conn) -> pd.DataFrame:
    limit = f"LIMIT {int(DOWNLOAD_LIMIT)}" if DOWNLOAD_LIMIT else ""
    return pd.read_sql_query(f"""
        SELECT * FROM {TABLE_ACTIVE}
        WHERE status IS NULL
           OR status IN ('NEW','RECHECK','RECHECK_NEW_SECTOR')
        ORDER BY TIC {limit}
    """, conn)


def run_scan_loop(conn: sqlite3.Connection) -> None:
    targets   = get_scan_targets(conn)
    if targets.empty:
        log("⚠️  Keine Scan-Targets.")
        return

    total     = len(targets)
    rows_list = list(targets.itertuples(index=False))
    stats     = {"candidates": 0, "no_lc": 0, "no_signal": 0,
                 "cached": 0, "fp_flagged": 0, "hz_hits": 0,
                 "hz_revisit": 0, "errors": 0}
    t_start   = time.perf_counter()

    log(f"🔍 Scan: {total} Targets | {DOWNLOAD_WORKERS} Download-Worker | "
        f"{BLS_WORKERS} BLS-Prozesse | Batch-Größe: {FETCH_BATCH_SIZE}")
    log(f"💽 LC-Cache unter {LIGHTCURVE_BASE_DIR}")

    batches = range(0, total, FETCH_BATCH_SIZE)
    if HAS_TQDM:
        batches = progress(
            batches,
            total=(total + FETCH_BATCH_SIZE - 1) // FETCH_BATCH_SIZE,
            desc="Batches",
            unit="batch",
        )

    try:
        bls_context = mp.get_context(BLS_START_METHOD)
    except ValueError:
        log(f"⚠️  Ungültige BLS_START_METHOD={BLS_START_METHOD!r}; nutze Standardkontext.")
        bls_context = None

    pool_kwargs = {"max_workers": BLS_WORKERS}
    if bls_context is not None:
        pool_kwargs["mp_context"] = bls_context

    with ProcessPoolExecutor(**pool_kwargs) as bls_pool:
        for batch_start in batches:
            batch_rows = rows_list[batch_start: batch_start + FETCH_BATCH_SIZE]

            # ── 1. Cache-Check ──────────────────────────────────────────
            cached_arrays: Dict[int, Tuple] = {}   # {tic: (t, f, sap, pdc, path_str)}
            to_download: List[int] = []

            for row in batch_rows:
                tic = int(row.TIC)
                cached = try_load_lc_cache_with_aux(tic)
                if cached:
                    t, f, sap, pdc = prepare_arrays_with_aux(*cached)
                    cached_arrays[tic] = (t, f, sap, pdc, str(get_lc_cache_path(tic)))
                    stats["cached"] += 1
                else:
                    to_download.append(tic)

            log(f"  Batch {batch_start//FETCH_BATCH_SIZE+1}: "
                f"{len(cached_arrays)} aus Cache | {len(to_download)} Downloads")

            # ── 2. Parallele Downloads ──────────────────────────────────
            downloaded: Dict[int, Tuple[np.ndarray, np.ndarray, Optional[np.ndarray], Optional[np.ndarray], str]] = {}
            download_failures: Dict[int, dict] = {}
            if to_download:
                dl_results = download_lightcurves_to_cache(to_download)
                timeout_tics = []
                for tic in to_download:
                    result = dl_results.get(tic, {"status": "timeout", "error": "DOWNLOAD_NO_RESULT"})
                    status = result.get("status")
                    if status == "ok":
                        cached = try_load_lc_cache_with_aux(tic)
                        if cached:
                            t, f, sap, pdc = prepare_arrays_with_aux(*cached)
                            downloaded[tic] = (t, f, sap, pdc, str(get_lc_cache_path(tic)))
                        else:
                            download_failures[tic] = {
                                "status": "error",
                                "error": "CACHE_READ_AFTER_DOWNLOAD_FAILED",
                            }
                    else:
                        download_failures[tic] = result
                        if status == "timeout":
                            timeout_tics.append(tic)

                if timeout_tics:
                    sample = ", ".join(str(t) for t in timeout_tics[:5])
                    more = " ..." if len(timeout_tics) > 5 else ""
                    log(f"⚠️  Download-Timeout für {len(timeout_tics)} Targets: {sample}{more}")

            # ── 3. LCs vorbereiten + BLS-Arbeit einreihen ──────────────
            bls_work: List[tuple] = []       # (tic, t, f, stellar_r, teff, lc_path, row)

            for row in batch_rows:
                tic       = int(row.TIC)
                stellar_r = float(row.radius) if pd.notna(row.radius) else None
                teff      = float(row.teff)   if pd.notna(row.teff)   else None
                distance_ly = float(row.distance_ly) if pd.notna(row.distance_ly) else None

                if tic in cached_arrays:
                    t, f, sap, pdc, path = cached_arrays[tic]
                    if len(t) < MIN_POINTS:
                        update_status(conn, tic, "TOO_FEW_POINTS", lc_dir=path, commit=False)
                    else:
                        bls_work.append((tic, t, f, sap, pdc, stellar_r, teff, distance_ly, path, row))

                elif tic in downloaded:
                    t, f, sap, pdc, path = downloaded[tic]
                    if len(t) < MIN_POINTS:
                        update_status(conn, tic, "TOO_FEW_POINTS", lc_dir=path, commit=False)
                    else:
                        bls_work.append((tic, t, f, sap, pdc, stellar_r, teff, distance_ly, path, row))

                elif tic in download_failures and download_failures[tic].get("status") == "timeout":
                    update_status(conn, tic, "SCAN_ERROR",
                                  err=download_failures[tic].get("error", "DOWNLOAD_TIMEOUT"),
                                  commit=False)
                    stats["errors"] += 1
                else:
                    update_status(conn, tic, "NO_TESS_DATA", commit=False)
                    stats["no_lc"] += 1

            # ── 4. Paralleler BLS (ProcessPool) ────────────────────────
            row_map = {tic: (path, row, t, f) for tic, t, f, _, _, _, _, _, path, row in bls_work}
            worker_args = [
                (tic, t, f, sr, te, dist, sap, pdc)
                for tic, t, f, sap, pdc, sr, te, dist, _, _ in bls_work
            ]
            conn.commit()

            if not worker_args:
                continue

            bls_futures = {bls_pool.submit(_bls_worker, args): args[0]
                           for args in worker_args}

            inner = as_completed(bls_futures)
            if HAS_TQDM:
                inner = progress(inner, total=len(bls_futures), desc="  BLS", leave=False)

            for fut in inner:
                tic = bls_futures[fut]
                path, row, time_arr, flux_arr = row_map[tic]
                t_tic = time.perf_counter()

                try:
                    _, worker_result = fut.result()

                    if worker_result is None:
                        update_status(conn, tic, "SCANNED_NO_SIGNAL", lc_dir=path, commit=False)
                        stats["no_signal"] += 1
                        continue

                    if "error" in worker_result:
                        update_status(conn, tic, "SCAN_ERROR", lc_dir=path,
                                      err=worker_result["error"], commit=False)
                        stats["errors"] += 1
                        continue

                    cand = worker_result["cand"]
                    fp   = worker_result.get("fp", {})

                    inserted = save_candidate(conn, row, cand, path, worker_result, commit=False)
                    if inserted:
                        save_candidate_plots(tic, time_arr, flux_arr, cand, worker_result)
                    update_status(conn, tic, worker_result.get("status") or "CANDIDATE",
                                  period=cand["period"],
                                  rp=cand["planet_radius_earth"],
                                  lc_dir=path,
                                  commit=False)

                    stats["candidates"] += 1
                    if fp.get("is_fp"):
                        stats["fp_flagged"] += 1
                    if worker_result.get("hz_status") in (
                            "KONSERVATIVE_HZ", "OPT_HZ_INNEN", "OPT_HZ_AUSSEN"):
                        stats["hz_hits"] += 1
                    if worker_result.get("is_hz_revisit_candidate"):
                        stats["hz_revisit"] += 1

                    elapsed = time.perf_counter() - t_tic
                    rp_str  = f"{cand['planet_radius_earth']:.2f} Re" if cand["planet_radius_earth"] else "?"
                    log(f"  ★ TIC {tic} | P={cand['period']:.4f}d | Rp={rp_str} | "
                        f"SNR={cand.get('transit_snr', 0):.1f} | Ntr={cand.get('transit_count', 0)} | "
                        f"HZ={worker_result.get('hz_class') or worker_result.get('hz_status','?')} | "
                        f"SPC={worker_result.get('spc_class','?')} | "
                        f"FP={'⚠️' if fp.get('is_fp') else '✓'} | {elapsed:.1f}s")

                except Exception as e:
                    update_status(conn, tic, "SCAN_ERROR", err=fmt_exc(e), commit=False)
                    stats["errors"] += 1
                    log(f"  💥 TIC {tic}: {fmt_exc(e)}")

            conn.commit()

    elapsed_total = time.perf_counter() - t_start
    log("\n" + "=" * 65)
    log(f"SCAN FERTIG  {elapsed_total/60:.1f} min | ⌀ {elapsed_total/max(total,1):.1f}s pro Stern")
    log(f"  Kandidaten   : {stats['candidates']}")
    log(f"  Aus Cache    : {stats['cached']}")
    log(f"  Keine LC     : {stats['no_lc']}")
    log(f"  Kein Signal  : {stats['no_signal']}")
    log(f"  FP-Verdacht  : {stats['fp_flagged']}")
    log(f"  HZ-Treffer   : {stats['hz_hits']}")
    log(f"  HZ-Revisit   : {stats['hz_revisit']}")
    log(f"  Fehler       : {stats['errors']}")
    log("=" * 65)


# ============================================================
# EXPORT & REPORT
# ============================================================

def load_lightcurve_data_for_candidate(
    tic: int,
    lc_path: object,
) -> Optional[Tuple[np.ndarray, np.ndarray, Optional[np.ndarray], Optional[np.ndarray]]]:
    path = Path(str(lc_path)) if lc_path not in (None, "", "nan") else get_lc_cache_path(tic)
    if not path.exists():
        path = get_lc_cache_path(tic)
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path)
        if {"time", "flux"}.issubset(df.columns):
            t = np.asarray(df["time"], dtype=float)
            f = np.asarray(df["flux"], dtype=float)
            sap = np.asarray(df["sap_flux"], dtype=float) if "sap_flux" in df.columns else None
            pdc = np.asarray(df["pdcsap_flux"], dtype=float) if "pdcsap_flux" in df.columns else None
        else:
            arr = np.loadtxt(path, delimiter=",", skiprows=1, usecols=(0, 1), ndmin=2)
            t = np.asarray(arr[:, 0], dtype=float)
            f = np.asarray(arr[:, 1], dtype=float)
            sap = None
            pdc = None
        if len(t) == len(f) and len(t) > 0:
            return prepare_arrays_with_aux(t, f, sap, pdc)
    except Exception as e:
        log(f"⚠️  Revisit-LC TIC {tic} nicht lesbar: {fmt_exc(e)}")
    return None


def load_lightcurve_arrays_for_candidate(tic: int, lc_path: object) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    loaded = load_lightcurve_data_for_candidate(tic, lc_path)
    if loaded is None:
        return None
    return loaded[0], loaded[1]


def refresh_revisit_fields(conn: sqlite3.Connection) -> None:
    try:
        df = pd.read_sql_query(f"""
            SELECT TIC, teff, distance_ly, stellar_radius, best_period, duration,
                   depth, transit_time, transit_snr, transit_count, lightcurve_dir,
                   hz_status, status, notes,
                   fp_oe_flag, fp_sec_flag, fp_baseline_flag, fp_baseline_std_flag,
                   fp_scatter_flag, is_fp
            FROM {TABLE_CANDIDATES}
            WHERE best_period IS NOT NULL
        """, conn)
    except Exception as e:
        log(f"⚠️  Revisit-Nachklassifikation übersprungen: {fmt_exc(e)}")
        return
    if df.empty:
        return

    updates = []
    protected = {"FP", "FP_ART", "FALSE_POSITIVE"}
    for row in df.itertuples(index=False):
        tic = int(row.TIC)
        hz_class = compute_hz_class(row.teff, row.stellar_radius, row.best_period)
        if hz_class == "UNKNOWN":
            hz_class = normalize_hz_class(row.hz_status)

        sector_quality = {
            "sector_count": 0,
            "clean_sector_count": 0,
            "visible_transits": _safe_int(row.transit_count),
            "sector_quality_summary": "lightcurve_not_available_for_sector_quality",
        }
        arrays = load_lightcurve_data_for_candidate(tic, row.lightcurve_dir)
        if arrays is not None:
            time_arr, flux_arr, sap_flux_arr, pdcsap_flux_arr = arrays
            if len(time_arr) >= 20:
                sector_quality = compute_sector_quality(
                    time_arr,
                    flux_arr,
                    _safe_float(row.best_period),
                    _safe_float(row.transit_time),
                    _safe_float(row.duration),
                    _safe_float(row.depth),
                    sap_flux_arr=sap_flux_arr,
                    pdcsap_flux_arr=pdcsap_flux_arr,
                )

        fp = {
            "fp_oe_flag": bool(_safe_int(row.fp_oe_flag)),
            "fp_sec_flag": bool(_safe_int(row.fp_sec_flag)),
            "fp_baseline_flag": bool(_safe_int(row.fp_baseline_flag)),
            "fp_baseline_std_flag": bool(_safe_int(row.fp_baseline_std_flag)),
            "fp_scatter_flag": bool(_safe_int(row.fp_scatter_flag)),
            "is_fp": bool(_safe_int(row.is_fp)),
        }
        followup = classify_spc_followup(
            visible_transits=sector_quality["visible_transits"],
            transit_count=row.transit_count,
            snr=row.transit_snr,
            hz_class=hz_class,
            distance_ly=row.distance_ly,
            clean_sector_count=sector_quality["clean_sector_count"],
            sector_count=sector_quality["sector_count"],
            fp=fp,
            existing_notes=row.notes,
        )
        status = str(row.status or "")
        new_status = followup["status"]
        if status in protected and new_status != "FP" and not followup["is_hz_revisit_candidate"]:
            new_status = status
        updates.append(
            (
                hz_class,
                sector_quality["sector_count"],
                sector_quality["clean_sector_count"],
                sector_quality["sector_quality_summary"],
                sector_quality["visible_transits"],
                followup["spc_class"],
                followup["revisit_priority"],
                followup["next_recheck"],
                followup["notes"],
                new_status,
                tic,
            )
        )

    conn.executemany(
        f"""
        UPDATE {TABLE_CANDIDATES}
           SET hz_class=?,
               sector_count=?,
               clean_sector_count=?,
               sector_quality_summary=?,
               visible_transits=?,
               spc_class=?,
               revisit_priority=?,
               next_recheck=?,
               notes=?,
               status=?
         WHERE TIC=?
        """,
        updates,
    )
    for hz_class, sector_count, clean_sector_count, summary, visible, spc, priority, next_recheck, notes, status, tic in updates:
        for table in (TABLE_RAW, TABLE_ACTIVE):
            try:
                conn.execute(
                    f"""
                    UPDATE {table}
                       SET status=?,
                           checked_at=datetime('now')
                     WHERE TIC=?
                       AND (
                            COALESCE(status, '') NOT IN ('FP', 'FP_ART', 'FALSE_POSITIVE')
                            OR ? = 'SPC-C'
                       )
                    """,
                    (status, tic, status),
                )
            except Exception:
                pass
    conn.commit()
    log(f"🔁 Revisit-/SPC-Felder aktualisiert: {len(updates)} Kandidaten")


def export_candidates_csv(conn):
    df = pd.read_sql_query(f"""
        SELECT TIC, teff, distance_ly, stellar_radius, stellar_logg,
               best_period, duration, depth, planet_radius_earth, power,
               transit_snr, transit_count, n_in_transit, duration_fraction,
               oe_ratio, sec_ratio, baseline_delta, baseline_std_delta, oot_scatter_ratio,
               fp_oe_flag, fp_sec_flag, fp_baseline_flag, fp_baseline_std_flag, fp_scatter_flag, is_fp,
               hz_status, hz_class, sector_count, clean_sector_count,
               sector_quality_summary, visible_transits, spc_class,
               revisit_priority, next_recheck, notes,
               hz_cons_inner_d, hz_cons_outer_d, created_at
        FROM {TABLE_CANDIDATES}
        ORDER BY
            CASE COALESCE(hz_class, hz_status)
                WHEN 'KONSERVATIVE_HZ' THEN 1
                WHEN 'OPT_HZ_INNEN'   THEN 2
                ELSE 4
            END,
            revisit_priority DESC,
            planet_radius_earth ASC
    """, conn)
    if df.empty:
        log("ℹ️  Keine Kandidaten zum Exportieren.")
        return
    df.to_csv(RESULTS_CSV, index=False)
    log(f"\n📄 CSV exportiert → {RESULTS_CSV}  ({len(df)} Kandidaten)")


def export_hz_revisit_priority_csv(conn):
    try:
        df = pd.read_sql_query(f"""
            SELECT
                TIC,
                teff,
                distance_ly,
                stellar_radius AS radius,
                best_period,
                COALESCE(hz_class, hz_status, 'UNKNOWN') AS hz_class,
                COALESCE(visible_transits, transit_count, 0) AS visible_transits,
                COALESCE(sector_count, 0) AS sector_count,
                COALESCE(clean_sector_count, 0) AS clean_sector_count,
                COALESCE(transit_snr, 0) AS snr,
                COALESCE(spc_class, status, 'UNKNOWN') AS spc_class,
                COALESCE(revisit_priority, 0) AS revisit_priority,
                COALESCE(next_recheck, '') AS next_recheck,
                COALESCE(notes, '') AS notes
            FROM {TABLE_CANDIDATES}
            WHERE COALESCE(hz_class, hz_status, 'UNKNOWN') IN ('OPT_HZ_INNEN', 'KONSERVATIVE_HZ')
              AND COALESCE(spc_class, status, '') != 'FP'
              AND COALESCE(revisit_priority, 0) > 0
              AND (
                    COALESCE(visible_transits, transit_count, 99) < 3
                    OR COALESCE(notes, '') LIKE '%HZ_REVISIT_CANDIDATE%'
                    OR COALESCE(revisit_priority, 0) > 0
                  )
            ORDER BY revisit_priority DESC, snr DESC, distance_ly ASC, TIC
        """, conn)
    except Exception as e:
        log(f"⚠️  HZ-Revisit-Export fehlgeschlagen: {fmt_exc(e)}")
        return
    HZ_REVISIT_CSV.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "TIC", "teff", "distance_ly", "radius", "best_period", "hz_class",
        "visible_transits", "sector_count", "clean_sector_count", "snr",
        "spc_class", "revisit_priority", "next_recheck", "notes",
    ]
    df = df.reindex(columns=columns)
    df.to_csv(HZ_REVISIT_CSV, index=False)
    log(f"🌿 HZ-Revisit-Prioritäten → {HZ_REVISIT_CSV}  ({len(df)} Kandidaten)")



def show_report(conn):
    safe_print("\n" + "=" * 65)
    safe_print("MASTER REPORT — Super-Earth Hunter v2")
    safe_print("=" * 65)
    for table in [TABLE_RAW, TABLE_ACTIVE, TABLE_CANDIDATES]:
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            safe_print(f"  {table:35s}: {n:>6}")
        except Exception:
            safe_print(f"  {table}: nicht gefunden")
    safe_print()
    try:
        safe_print("--- Kandidaten nach HZ-Status ---")
        df = pd.read_sql_query(f"""
            SELECT COALESCE(hz_class, hz_status, 'UNKNOWN') AS hz_class,
                   COUNT(*) AS n,
                   SUM(COALESCE(is_fp, 0)) AS fp_verdacht,
                   SUM(CASE WHEN COALESCE(notes, '') LIKE '%HZ_REVISIT_CANDIDATE%' THEN 1 ELSE 0 END) AS hz_revisit
            FROM {TABLE_CANDIDATES}
            GROUP BY COALESCE(hz_class, hz_status, 'UNKNOWN')
            ORDER BY n DESC
        """, conn)
        safe_print(df.to_string(index=False))
    except Exception as e:
        safe_print(f"HZ-Report Fehler: {e}")
    safe_print()
    try:
        safe_print("--- SPC-Klassen ---")
        df = pd.read_sql_query(f"""
            SELECT COALESCE(spc_class, status, 'UNKNOWN') AS spc_class,
                   COUNT(*) AS n,
                   ROUND(MAX(COALESCE(revisit_priority, 0)), 3) AS max_revisit_priority
            FROM {TABLE_CANDIDATES}
            GROUP BY COALESCE(spc_class, status, 'UNKNOWN')
            ORDER BY n DESC
        """, conn)
        safe_print(df.to_string(index=False))
    except Exception as e:
        safe_print(f"SPC-Report Fehler: {e}")
    safe_print()
    try:
        safe_print("--- Scan-Status (rohdaten) ---")
        df = pd.read_sql_query(f"""
            SELECT status, COUNT(*) AS n FROM {TABLE_RAW}
            GROUP BY status ORDER BY n DESC
        """, conn)
        safe_print(df.to_string(index=False))
    except Exception as e:
        safe_print(f"Status-Report Fehler: {e}")


# ============================================================
# MAIN
# ============================================================

def main():
    ensure_dirs()
    conn = connect_db()
    try:
        log("🛠️  Initialisiere Tabellen ...")
        ensure_raw_table(conn)
        ensure_active_table(conn)
        ensure_candidates_table(conn)

        if IMPORT_FROM_MAST:
            log("🌌 Lade TIC-Katalog ...")
            import_blocks_to_rohdaten(conn)

        if CHECK_TESS_DATA:
            log("📡 TESS-Verfügbarkeit prüfen ...")
            update_tess_availability(conn)

        log("🎯 Aktive Scan-Tabelle aufbauen ...")
        build_active_table(conn)

        if RUN_BLS_SCAN:
            log("🚀 BLS-Scan starten ...")
            run_scan_loop(conn)

        refresh_revisit_fields(conn)
        export_candidates_csv(conn)
        export_hz_revisit_priority_csv(conn)
        show_report(conn)

    finally:
        conn.close()
        log("\n✅ masterscript_v2.py fertig.")


if __name__ == "__main__":
    main()
