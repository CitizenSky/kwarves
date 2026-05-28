#!/usr/bin/env python3
"""Scan green Level-0 candidate plots and create a simple vetting report.

The script is intentionally separate from masterscript_v2.py.  It reads the
existing project artifacts, applies conservative rule-based checks, then writes
a versioned CSV plus an HTML overview.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import os
import re
import shutil
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(os.environ.get("ASTRO_PROJECT_ROOT", "/Users/koni/astro_projects"))
LEVEL0_ROOT = PROJECT_ROOT / "level0_lichtjahre_10ly_bis_500"
MANIFEST_PATH = LEVEL0_ROOT / "manifest_all_candidates_by_distance.csv"
TREE_MANIFEST_PATH = LEVEL0_ROOT / "LEVEL0" / "99_REPORTS" / "level0_level_tree_manifest.csv"
CANDIDATES_CSV = PROJECT_ROOT / "csv" / "masterscript_v2_candidates.csv"
DB_PATH = PROJECT_ROOT / "database" / "planet_hunter.db"
EVIDENCE_ROOT = PROJECT_ROOT / "evidence_vetting"
ADVANCED_ROOT = PROJECT_ROOT / "advanced_bayesian_vetting"
LEVEL5_ROOT = PROJECT_ROOT / "level5_detailvalidierung"
OUT_BASE = PROJECT_ROOT / "green_candidate_plot_vetting"

LABELS = ("HIGH_PRIORITY", "SPC", "SPC_ART", "LIKELY_FP", "EB_VERDACHT", "NEED_MORE_DATA")
SEVERE_ARTIFACT_FLAGS = {
    "SAP_PDCSAP_MISMATCH",
    "PDCSAP_ONLY_SIGNAL",
    "SAP_ONLY_SIGNAL",
    "PIPELINE_ARTIFACT_RISK",
    "SPC_ART",
}
WEAK_DATA_FLAGS = {
    "WEAK_DATA_WINDOW",
    "SINGLE_OBSERVED_TRANSIT",
    "FEW_VISIBLE_TRANSITS",
    "ONLY_2_3_EVENTS_DRIVE_SIGNAL",
    "TRANSIT_AT_SECTOR_EDGE",
    "ODD_EVEN_INSUFFICIENT",
}
EB_FLAGS = {
    "ODD_EVEN_MISMATCH",
    "EB_RISK",
    "PIPELINE_ODD_EVEN_FLAG",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Vet all green-marked candidate plots and write CSV/HTML reports."
    )
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None, help="Limit candidates for a quick test run.")
    parser.add_argument(
        "--skip-lightcurve-analysis",
        action="store_true",
        help="Use metadata only; skip per-lightcurve flux/shape checks.",
    )
    parser.add_argument(
        "--copy-plots",
        action="store_true",
        help="Copy plot PNGs into the report instead of creating symlinks.",
    )
    return parser.parse_args()


def text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        text = text_value(value)
        if text == "":
            return default
        out = float(text)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def safe_int(value: Any, default: int = 0) -> int:
    val = safe_float(value)
    return default if val is None else int(val)


def split_flags(value: Any) -> set[str]:
    text = text_value(value)
    if not text:
        return set()
    return {part.strip() for part in re.split(r"[;,|]", text) if part.strip()}


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def lookup_by_tic(rows: list[dict[str, Any]], key: str = "TIC") -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        tic = safe_int(row.get(key) or row.get("tic"))
        if tic:
            out[tic] = dict(row)
    return out


def latest_run_csv(root: Path, filename: str) -> Path | None:
    if not root.exists():
        return None
    matches = sorted(root.glob(f"*/{filename}"), key=lambda path: path.parent.name, reverse=True)
    return matches[0] if matches else None


def load_db_latest(table: str, tic_column: str = "TIC") -> dict[int, dict[str, Any]]:
    if not DB_PATH.exists() or DB_PATH.stat().st_size == 0:
        return {}
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=30)
        conn.row_factory = sqlite3.Row
        cols = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]
        if not cols:
            return {}
        if "created_at" in cols:
            rows = conn.execute(
                f"""
                SELECT t.*
                  FROM {table} t
                  JOIN (
                        SELECT {tic_column} AS tic_key, MAX(created_at) AS latest_created_at
                          FROM {table}
                         GROUP BY {tic_column}
                       ) latest
                    ON latest.tic_key = t.{tic_column}
                   AND latest.latest_created_at = t.created_at
                """
            ).fetchall()
        else:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    except sqlite3.Error:
        return {}
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return {safe_int(row[tic_column]): dict(row) for row in rows if safe_int(row[tic_column])}


def load_tables() -> dict[str, dict[int, dict[str, Any]]]:
    latest_evidence = latest_run_csv(EVIDENCE_ROOT, "evidence_vetting_results.csv")
    latest_advanced = latest_run_csv(ADVANCED_ROOT, "advanced_vetting_results.csv")
    data = {
        "manifest": lookup_by_tic(read_csv_rows(MANIFEST_PATH)),
        "candidates": lookup_by_tic(read_csv_rows(CANDIDATES_CSV)),
        "tree": lookup_by_tic(read_csv_rows(TREE_MANIFEST_PATH)),
        "evidence": lookup_by_tic(read_csv_rows(latest_evidence)) if latest_evidence else {},
        "advanced": lookup_by_tic(read_csv_rows(latest_advanced)) if latest_advanced else {},
        "level5_final": lookup_by_tic(
            read_csv_rows(LEVEL5_ROOT / "level5_06_bestanden" / "level5_final_status_after_recheck.csv"),
            key="tic",
        ),
        "level5_recheck": lookup_by_tic(
            read_csv_rows(LEVEL5_ROOT / "level5_06_bestanden" / "level5_recheck_summary.csv"),
            key="tic",
        ),
        "level5_all": lookup_by_tic(
            read_csv_rows(LEVEL5_ROOT / "level5_06_bestanden" / "level5_all_6_summary.csv"),
            key="tic",
        ),
        "db_candidates": load_db_latest("candidates_v2"),
        "db_evidence": load_db_latest("evidence_vetting_results"),
        "db_advanced": load_db_latest("advanced_vetting_results"),
    }
    return data


def green_candidate_folders(manifest: dict[int, dict[str, Any]]) -> list[tuple[int, Path, dict[str, Any]]]:
    rows: list[tuple[int, Path, dict[str, Any]]] = []
    seen: set[int] = set()

    for tic, row in manifest.items():
        candidate_folder = text_value(row.get("candidate_folder"))
        folder = PROJECT_ROOT / candidate_folder if candidate_folder else Path()
        if row.get("markierung") == "GRUEN" or folder.name.startswith("SPC_GREEN"):
            if folder.exists():
                rows.append((tic, folder, row))
                seen.add(tic)

    for folder in sorted(LEVEL0_ROOT.glob("*_ly/SPC_GREEN*")):
        if not folder.is_dir():
            continue
        match = re.search(r"TIC_(\d+)", folder.name)
        if not match:
            continue
        tic = int(match.group(1))
        if tic not in seen:
            rows.append((tic, folder, {"candidate_folder": str(folder.relative_to(PROJECT_ROOT))}))
            seen.add(tic)
    return sorted(rows, key=lambda item: (str(item[1].parent.name), item[0]))


def find_plot(folder: Path) -> Path | None:
    preferred = [
        folder / "lichtkurven_png" / "LICHTKURVE_COMBINED.png",
        folder / "lichtkurven_png" / "LICHTKURVE_FOLDED.png",
        folder / "lichtkurven_png" / "LICHTKURVE_RAW.png",
    ]
    for path in preferred:
        if path.exists():
            return path
    candidates: list[Path] = []
    for pattern in ("*combined*.png", "*folded*.png", "*raw*.png", "*.png"):
        candidates.extend(sorted((folder / "data_links").glob(pattern)))
    for path in candidates:
        if path.exists():
            return path
    return None


def find_lightcurve_csv(tic: int, folder: Path, row: dict[str, Any]) -> Path | None:
    for value in (row.get("lightcurve_dir"), row.get("lightcurve_path")):
        path = Path(text_value(value))
        if path.exists():
            return path
    preferred = [
        PROJECT_ROOT / "lightcurves" / f"TIC_{tic}" / f"TIC_{tic}_lightcurve.csv",
    ]
    preferred.extend(sorted((folder / "data_links").glob("*lightcurve*.csv")))
    preferred.extend(sorted((folder / "data_links").glob("*.csv")))
    for path in preferred:
        if path.exists() and path.suffix.lower() == ".csv":
            return path
    return None


def parse_plot_metadata(tic: int, plot: Path | None) -> dict[str, Any]:
    source = plot.name if plot else ""
    out: dict[str, Any] = {
        "plot_filename": source,
        "parsed_tic": tic,
        "parsed_period": "",
        "parsed_radius_re": "",
        "parsed_snr": "",
        "parsed_hz_status": "",
    }
    if not source:
        return out
    patterns = {
        "parsed_period": r"(?:^|[_\s|])P=?([0-9]+(?:\.[0-9]+)?)\s*d?",
        "parsed_radius_re": r"Rp=?([0-9]+(?:\.[0-9]+)?)\s*R?e?",
        "parsed_snr": r"SNR=?([0-9]+(?:\.[0-9]+)?)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, source, flags=re.IGNORECASE)
        if match:
            out[key] = match.group(1)
    for hz in (
        "KONSERVATIVE_HZ",
        "OPT_HZ_INNEN",
        "OPT_HZ_AUSSEN",
        "ZU_HEISS",
        "ZU_KALT",
        "UNBEKANNT",
    ):
        if hz in source:
            out["parsed_hz_status"] = hz
            break
    return out


def load_json(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def first_glob(pattern: str) -> Path | None:
    matches = sorted(LEVEL5_ROOT.glob(pattern))
    return matches[0] if matches else None


def load_level5_details(tic: int) -> dict[str, Any]:
    details: dict[str, Any] = {}
    json_patterns = [
        f"**/TIC_{tic}_odd_even_level5.json",
        f"**/TIC_{tic}_secondary_level5.json",
        f"**/TIC_{tic}_neighbor_blend_level5.json",
    ]
    for pattern in json_patterns:
        payload = load_json(first_glob(pattern))
        for key, value in payload.items():
            details[f"level5_{key}"] = value

    transits = first_glob(f"**/TIC_{tic}_visible_single_transits_level5.csv")
    if transits:
        rows = read_csv_rows(transits)
        visible = [row for row in rows if text_value(row.get("visible")).lower() == "true"]
        robust = [row for row in rows if text_value(row.get("robust")).lower() == "true"]
        details["level5_visible_transits_csv"] = len(visible)
        details["level5_robust_transits_csv"] = len(robust)
        depths = [safe_float(row.get("depth_ppt")) for row in robust]
        depths = [value for value in depths if value is not None]
        if depths:
            details["level5_robust_depth_median_ppt"] = float(np.median(depths))

    sectors = first_glob(f"**/TIC_{tic}_sector_segments.csv")
    if sectors:
        rows = read_csv_rows(sectors)
        details["level5_segments_total_csv"] = len(rows)
        details["level5_segments_expected_csv"] = sum(safe_int(row.get("n_expected")) for row in rows)
        details["level5_segments_visible_csv"] = sum(safe_int(row.get("n_visible")) for row in rows)
    return details


def finite_array(values: np.ndarray) -> np.ndarray:
    return values[np.isfinite(values)]


def analyze_lightcurve(
    path: Path | None,
    period: float | None,
    epoch: float | None,
    duration: float | None,
) -> dict[str, Any]:
    empty = {
        "lightcurve_path": str(path or ""),
        "lc_points": "",
        "flux_one_fraction": "",
        "flux_std_ppt": "",
        "measured_depth_ppt_lc": "",
        "positive_bump_ppt_lc": "",
        "local_snr_lc": "",
        "v_shape_metric_lc": "",
    }
    if not path or not path.exists():
        return empty
    try:
        data = np.genfromtxt(path, delimiter=",", names=True, dtype=float)
    except Exception:
        return empty
    if data.size == 0 or "time" not in data.dtype.names or "flux" not in data.dtype.names:
        return empty
    time = np.asarray(data["time"], dtype=float)
    flux = np.asarray(data["flux"], dtype=float)
    valid = np.isfinite(time) & np.isfinite(flux)
    time = time[valid]
    flux = flux[valid]
    if len(flux) < 20:
        return {**empty, "lc_points": len(flux)}

    out: dict[str, Any] = {
        **empty,
        "lc_points": int(len(flux)),
        "flux_one_fraction": float(np.mean(np.isclose(flux, 1.0, rtol=0.0, atol=1e-10))),
        "flux_std_ppt": float(np.nanstd(flux) * 1000.0),
    }
    if not period or not epoch or not duration or period <= 0 or duration <= 0:
        return out

    phase = ((time - epoch + 0.5 * period) % period) - 0.5 * period
    transit = np.abs(phase) <= 0.5 * duration
    oot = np.abs(phase) >= max(2.0 * duration, 0.03 * period)
    if transit.sum() < 5 or oot.sum() < 20:
        return out

    transit_flux = finite_array(flux[transit])
    oot_flux = finite_array(flux[oot])
    if len(transit_flux) < 5 or len(oot_flux) < 20:
        return out
    oot_median = float(np.median(oot_flux))
    in_median = float(np.median(transit_flux))
    oot_std = float(np.std(oot_flux))
    depth = (oot_median - in_median) * 1000.0
    out["measured_depth_ppt_lc"] = depth
    out["positive_bump_ppt_lc"] = max(0.0, -depth)
    out["local_snr_lc"] = depth / (oot_std * 1000.0) if oot_std > 0 else ""

    core = np.abs(phase) <= max(0.16 * duration, min(0.01, 0.25 * duration))
    edge = transit & ~core
    if core.sum() >= 5 and edge.sum() >= 5:
        core_depth = (oot_median - float(np.median(finite_array(flux[core])))) * 1000.0
        edge_depth = (oot_median - float(np.median(finite_array(flux[edge])))) * 1000.0
        if core_depth > 0.05:
            out["v_shape_metric_lc"] = edge_depth / core_depth
    return out


def choose_float(*values: Any) -> float | None:
    for value in values:
        parsed = safe_float(value)
        if parsed is not None:
            return parsed
    return None


def sap_status(row: dict[str, Any], flags: set[str]) -> str:
    text = text_value(row.get("sector_quality_summary"))
    match = re.search(r"SAP_PDCSAP=([A-Z_]+)", text)
    if match:
        return match.group(1)
    if {"SAP_PDCSAP_MISMATCH", "PDCSAP_ONLY_SIGNAL", "SAP_ONLY_SIGNAL"} & flags:
        return "MISMATCH"
    if "SAP_PDCSAP_UNAVAILABLE" in flags:
        return "UNAVAILABLE"
    return "UNKNOWN"


def classify_candidate(row: dict[str, Any]) -> tuple[str, int, list[str], list[str]]:
    flags = split_flags(row.get("flags"))
    status_text = " ".join(
        text_value(row.get(key)).upper()
        for key in ("status", "spc_class", "evidence_class", "bayes_class", "tree_status")
    )
    score = 100.0
    hits: list[str] = []
    reasons: list[str] = []

    def penalty(points: float, code: str, reason: str) -> None:
        nonlocal score
        score -= points
        hits.append(code)
        reasons.append(reason)

    snr = choose_float(row.get("transit_snr"), row.get("parsed_snr"))
    visible = max(
        safe_int(row.get("visible_transits")),
        safe_int(row.get("n_visible_transits")),
        safe_int(row.get("level5_visible_transits_level5")),
        safe_int(row.get("level5_visible_transits_csv")),
    )
    robust = max(
        safe_int(row.get("robust_transits")),
        safe_int(row.get("level5_robust_transits")),
        safe_int(row.get("level5_robust_transits_csv")),
    )
    expected = max(safe_int(row.get("n_expected_transits")), safe_int(row.get("level5_expected_transits")))
    clean = safe_int(row.get("clean_sector_count"))
    sectors = safe_int(row.get("sector_count"))
    depth_ppt = choose_float(row.get("median_depth_ppt"), row.get("depth_ppt"), row.get("model_depth_ppt"))
    if depth_ppt is None:
        depth = safe_float(row.get("depth"))
        depth_ppt = depth * 1000.0 if depth is not None else None
    measured_depth = safe_float(row.get("measured_depth_ppt_lc"))
    flux_one = safe_float(row.get("flux_one_fraction"), 0.0) or 0.0
    positive_bump = safe_float(row.get("positive_bump_ppt_lc"), 0.0) or 0.0
    v_shape = safe_float(row.get("v_shape_metric_lc"))
    sap = text_value(row.get("sap_pdcsap_status"))
    odd_even_ratio = choose_float(row.get("odd_even_ratio"), row.get("level4_odd_even_ratio"))
    depth_cv = safe_float(row.get("depth_cv"))
    duration_cv = safe_float(row.get("duration_cv"))
    secondary_ratio = max(
        safe_float(row.get("sec_ratio"), 0.0) or 0.0,
        safe_float(row.get("secondary_best_ratio_independent"), 0.0) or 0.0,
        safe_float(row.get("level4_secondary_ratio"), 0.0) or 0.0,
        safe_float(row.get("level4_max_secondary_ratio"), 0.0) or 0.0,
    )

    if "KNOWN_PLANET_ALIAS" in status_text or "FALSE_POSITIVE" in status_text or safe_int(row.get("is_fp")):
        penalty(80, "KNOWN_OR_FP", "already marked FP/known alias in project metadata")
    if snr is None:
        penalty(8, "SNR_MISSING", "SNR not available")
    elif snr < 7:
        penalty(28, "LOW_SNR", f"SNR {snr:.1f} below robust threshold")
    elif snr < 10:
        penalty(12, "BORDERLINE_SNR", f"SNR {snr:.1f} is borderline")
    elif snr >= 30:
        score += 3

    if visible < 1:
        penalty(35, "NO_VISIBLE_TRANSIT", "no visible transit counted")
    elif visible == 1:
        penalty(28, "ONLY_ONE_VISIBLE_TRANSIT", "only one visible transit")
    elif visible == 2:
        penalty(8, "ONLY_TWO_VISIBLE_TRANSITS", "only two visible transits")
    if robust and robust < 2:
        penalty(18, "ONLY_ONE_ROBUST_TRANSIT", "only one robust single-transit measurement")
    if expected >= 3 and visible and visible / expected < 0.5:
        penalty(14, "LOW_TRANSIT_COVERAGE", f"visible transits {visible}/{expected}")
    if sectors and sectors < 2:
        penalty(10, "SINGLE_SECTOR", "only one sector")
    if clean and clean < 2:
        penalty(10, "LOW_CLEAN_SECTOR_COUNT", f"clean sectors {clean}")

    if sap in {"UNKNOWN", "UNAVAILABLE"}:
        penalty(6, f"SAP_PDCSAP_{sap}", f"SAP/PDCSAP comparison {sap.lower()}")
    elif sap == "MISMATCH":
        penalty(26, "SAP_PDCSAP_MISMATCH", "SAP and PDCSAP disagree")

    if flags & WEAK_DATA_FLAGS:
        penalty(18, "WEAK_DATA_FLAGS", "weak data-window flags: " + ";".join(sorted(flags & WEAK_DATA_FLAGS)))
    if flags & EB_FLAGS:
        penalty(22, "EB_FLAGS", "odd/even or EB-risk flags: " + ";".join(sorted(flags & EB_FLAGS)))
    if flags & SEVERE_ARTIFACT_FLAGS:
        penalty(30, "ARTIFACT_FLAGS", "artifact flags: " + ";".join(sorted(flags & SEVERE_ARTIFACT_FLAGS)))
    if "ACTIVE_STAR_RISK" in flags or "ACTIVITY_CONFUSED" in flags:
        penalty(8, "ACTIVITY_RISK", "stellar activity risk")

    if flux_one > 0.35:
        penalty(32, "STRONG_FLUX_ONE_ARTIFACT", f"{flux_one:.1%} of flux samples are exactly 1")
    elif flux_one > 0.12:
        penalty(14, "FLUX_ONE_ARTIFACT", f"{flux_one:.1%} of flux samples are exactly 1")
    if positive_bump > 0.10:
        penalty(28, "POSITIVE_BUMP", f"folded transit window shows positive bump {positive_bump:.3f} ppt")
    if measured_depth is not None and measured_depth < -0.05:
        penalty(25, "NEGATIVE_DEPTH", f"measured depth is positive bump ({measured_depth:.3f} ppt)")
    if v_shape is not None and v_shape > 0.75:
        penalty(14, "V_SHAPE_RISK", f"V-shape metric {v_shape:.2f}")
    if depth_ppt is not None:
        if depth_ppt > 30:
            penalty(28, "VERY_DEEP_TRANSIT", f"very deep transit {depth_ppt:.2f} ppt")
        elif depth_ppt > 15:
            penalty(14, "DEEP_TRANSIT", f"deep transit {depth_ppt:.2f} ppt")
        elif depth_ppt < 0.08:
            penalty(8, "VERY_SHALLOW_TRANSIT", f"very shallow transit {depth_ppt:.3f} ppt")
    if secondary_ratio > 0.25:
        penalty(28, "SECONDARY_SIGNAL", f"secondary ratio {secondary_ratio:.2f}")
    if odd_even_ratio is not None and (odd_even_ratio < 0.55 or odd_even_ratio > 1.85):
        penalty(22, "ODD_EVEN_DEPTH_MISMATCH", f"odd/even ratio {odd_even_ratio:.2f}")
    if depth_cv is not None and depth_cv > 0.45:
        penalty(16, "DEPTH_UNSTABLE", f"depth CV {depth_cv:.2f}")
    if duration_cv is not None and duration_cv > 0.45:
        penalty(12, "DURATION_UNSTABLE", f"duration CV {duration_cv:.2f}")

    posterior_period = safe_float(row.get("posterior_period"))
    period = choose_float(row.get("period"), row.get("best_period"), row.get("parsed_period"))
    if posterior_period and period and abs(posterior_period - period) / period > 0.01:
        penalty(16, "PERIOD_INSTABILITY", "posterior period differs from pipeline period by >1%")

    score = max(0, min(100, round(score)))
    hit_set = set(hits)
    if "KNOWN_OR_FP" in hit_set or score <= 20:
        label = "LIKELY_FP"
    elif hit_set & {"SECONDARY_SIGNAL", "ODD_EVEN_DEPTH_MISMATCH", "VERY_DEEP_TRANSIT", "EB_FLAGS"}:
        label = "EB_VERDACHT"
    elif hit_set & {
        "STRONG_FLUX_ONE_ARTIFACT",
        "POSITIVE_BUMP",
        "NEGATIVE_DEPTH",
        "SAP_PDCSAP_MISMATCH",
        "ARTIFACT_FLAGS",
    }:
        label = "SPC_ART"
    elif visible < 2 or "WEAK_DATA_FLAGS" in hit_set or score < 50:
        label = "NEED_MORE_DATA"
    elif score >= 82 and visible >= 3 and (snr or 0) >= 12 and not (hit_set & {"V_SHAPE_RISK", "ACTIVITY_RISK"}):
        label = "HIGH_PRIORITY"
    else:
        label = "SPC"

    return label, score, hits, reasons


def merge_candidate_row(
    tic: int,
    folder: Path,
    manifest_row: dict[str, Any],
    tables: dict[str, dict[int, dict[str, Any]]],
    skip_lightcurve: bool,
) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for name in (
        "manifest",
        "candidates",
        "db_candidates",
        "tree",
        "evidence",
        "db_evidence",
        "advanced",
        "db_advanced",
        "level5_all",
        "level5_recheck",
        "level5_final",
    ):
        row.update(tables.get(name, {}).get(tic, {}))
    row.update(manifest_row)
    row["TIC"] = tic
    row["candidate_folder"] = str(folder)
    row["distance_range"] = folder.parent.name

    plot = find_plot(folder)
    row["plot_path"] = str(plot or "")
    row.update(parse_plot_metadata(tic, plot))
    row.update(load_level5_details(tic))

    flags = set()
    for key in ("flags", "combined_flags", "advanced_flags", "final_notes", "level5_flags"):
        flags.update(split_flags(row.get(key)))
    row["flags"] = ";".join(sorted(flags))
    row["sap_pdcsap_status"] = sap_status(row, flags)

    period = choose_float(row.get("period"), row.get("best_period"), row.get("parsed_period"))
    epoch = choose_float(row.get("epoch"), row.get("transit_time"))
    duration = choose_float(row.get("duration"), row.get("posterior_duration"))
    if not skip_lightcurve:
        lc_path = find_lightcurve_csv(tic, folder, row)
        row.update(analyze_lightcurve(lc_path, period, epoch, duration))
    return row


def make_plot_link(plot: Path | None, plot_dir: Path, name: str, copy: bool) -> str:
    if not plot or not plot.exists():
        return ""
    plot_dir.mkdir(parents=True, exist_ok=True)
    dest = plot_dir / name
    if dest.exists() or dest.is_symlink():
        dest.unlink()
    if copy:
        shutil.copy2(plot, dest)
    else:
        os.symlink(plot.resolve(), dest)
    return str(dest)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    preferred = [
        "rank",
        "output_label",
        "vetting_score",
        "TIC",
        "distance_range",
        "status",
        "spc_class",
        "hz_status",
        "distance_ly",
        "period",
        "best_period",
        "duration",
        "depth_ppt",
        "planet_radius_earth",
        "transit_snr",
        "transit_count",
        "visible_transits",
        "robust_transits",
        "sector_count",
        "clean_sector_count",
        "sap_pdcsap_status",
        "flux_one_fraction",
        "measured_depth_ppt_lc",
        "positive_bump_ppt_lc",
        "v_shape_metric_lc",
        "rule_hits",
        "why_label",
        "flags",
        "plot_report_path",
        "plot_path",
        "candidate_folder",
    ]
    ordered = [field for field in preferred if field in fields] + [field for field in fields if field not in preferred]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ordered, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def fmt(value: Any, digits: int = 2) -> str:
    number = safe_float(value)
    if number is None:
        return ""
    return f"{number:.{digits}f}"


def label_class(label: str) -> str:
    return label.lower().replace("_", "-")


def write_html(path: Path, rows: list[dict[str, Any]], csv_name: str) -> None:
    counts = Counter(row["output_label"] for row in rows)
    css = """
    body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:24px;background:#f6f7f9;color:#17202a}
    h1{margin-bottom:4px}.meta{color:#5f6b7a;margin-bottom:20px}
    .counts{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0 22px}
    .pill{border-radius:999px;padding:6px 10px;background:white;border:1px solid #d8dee8;font-size:13px}
    table{border-collapse:collapse;width:100%;background:white;border:1px solid #d8dee8}
    th,td{border-bottom:1px solid #e6eaf0;padding:8px;vertical-align:top;font-size:13px}
    th{position:sticky;top:0;background:#eef2f7;z-index:2;text-align:left}
    tr:hover{background:#fbfcff}
    img{max-width:280px;max-height:190px;border:1px solid #d8dee8;background:white}
    .label{font-weight:700;border-radius:5px;padding:4px 7px;display:inline-block}
    .high-priority{background:#d8f5df;color:#0d5c23}.spc{background:#e8f1ff;color:#164f99}
    .spc-art{background:#fff0cc;color:#7a4b00}.likely-fp{background:#ffd8d8;color:#8a1e1e}
    .eb-verdacht{background:#f0dcff;color:#5d2382}.need-more-data{background:#fff7c2;color:#625000}
    .small{color:#607080;font-size:12px}.reasons{max-width:440px}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
    """
    lines = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'>",
        "<title>Green Candidate Plot Vetting</title>",
        f"<style>{css}</style></head><body>",
        "<h1>Green Candidate Plot Vetting</h1>",
        f"<div class='meta'>Generated {html.escape(datetime.now().isoformat(timespec='seconds'))}. "
        f"CSV: <span class='mono'>{html.escape(csv_name)}</span></div>",
        "<div class='counts'>",
    ]
    for label in LABELS:
        lines.append(f"<span class='pill'>{label}: {counts.get(label, 0)}</span>")
    lines.extend(
        [
            "</div>",
            "<table>",
            "<thead><tr>",
            "<th>#</th><th>Label</th><th>Score</th><th>Plot</th><th>Candidate</th>"
            "<th>Data</th><th>Rule hits</th><th>Why</th>",
            "</tr></thead><tbody>",
        ]
    )
    for row in rows:
        plot_rel = Path(row["plot_report_path"]).name if row.get("plot_report_path") else ""
        plot_html = (
            f"<a href='plots/{html.escape(plot_rel)}'><img loading='lazy' src='plots/{html.escape(plot_rel)}'></a>"
            if plot_rel
            else "<span class='small'>no plot</span>"
        )
        label = html.escape(row["output_label"])
        reasons = "<br>".join(html.escape(item) for item in text_value(row.get("why_label")).split(" | ") if item)
        hits = "<br>".join(html.escape(item) for item in text_value(row.get("rule_hits")).split(";") if item)
        candidate = (
            f"<b>TIC {safe_int(row.get('TIC'))}</b><br>"
            f"<span class='small'>{html.escape(text_value(row.get('distance_range')))}</span><br>"
            f"HZ: {html.escape(text_value(row.get('hz_status')))}<br>"
            f"Status: {html.escape(text_value(row.get('status') or row.get('spc_class')))}"
        )
        data = (
            f"P {fmt(row.get('period') or row.get('best_period') or row.get('parsed_period'), 4)} d<br>"
            f"Rp {fmt(row.get('planet_radius_earth') or row.get('parsed_radius_re'), 2)} Re<br>"
            f"SNR {fmt(row.get('transit_snr') or row.get('parsed_snr'), 1)}<br>"
            f"vis {safe_int(row.get('visible_transits'))} / sectors {safe_int(row.get('sector_count'))}<br>"
            f"SAP/PDCSAP {html.escape(text_value(row.get('sap_pdcsap_status')))}"
        )
        lines.append(
            "<tr>"
            f"<td>{safe_int(row.get('rank'))}</td>"
            f"<td><span class='label {label_class(row['output_label'])}'>{label}</span></td>"
            f"<td>{safe_int(row.get('vetting_score'))}</td>"
            f"<td>{plot_html}</td>"
            f"<td>{candidate}</td>"
            f"<td>{data}</td>"
            f"<td class='reasons'>{hits}</td>"
            f"<td class='reasons'>{reasons}</td>"
            "</tr>"
        )
    lines.extend(["</tbody></table>", "</body></html>"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    global PROJECT_ROOT, LEVEL0_ROOT, MANIFEST_PATH, TREE_MANIFEST_PATH, CANDIDATES_CSV
    global DB_PATH, EVIDENCE_ROOT, ADVANCED_ROOT, LEVEL5_ROOT, OUT_BASE
    PROJECT_ROOT = args.project_root
    LEVEL0_ROOT = PROJECT_ROOT / "level0_lichtjahre_10ly_bis_500"
    MANIFEST_PATH = LEVEL0_ROOT / "manifest_all_candidates_by_distance.csv"
    TREE_MANIFEST_PATH = LEVEL0_ROOT / "LEVEL0" / "99_REPORTS" / "level0_level_tree_manifest.csv"
    CANDIDATES_CSV = PROJECT_ROOT / "csv" / "masterscript_v2_candidates.csv"
    DB_PATH = PROJECT_ROOT / "database" / "planet_hunter.db"
    EVIDENCE_ROOT = PROJECT_ROOT / "evidence_vetting"
    ADVANCED_ROOT = PROJECT_ROOT / "advanced_bayesian_vetting"
    LEVEL5_ROOT = PROJECT_ROOT / "level5_detailvalidierung"
    OUT_BASE = PROJECT_ROOT / "green_candidate_plot_vetting"

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.output_dir or OUT_BASE / run_id
    plot_dir = out_dir / "plots"
    out_dir.mkdir(parents=True, exist_ok=True)
    tables = load_tables()
    green = green_candidate_folders(tables["manifest"])
    if args.limit:
        green = green[: args.limit]

    rows: list[dict[str, Any]] = []
    for tic, folder, manifest_row in green:
        row = merge_candidate_row(tic, folder, manifest_row, tables, args.skip_lightcurve_analysis)
        label, score, hits, reasons = classify_candidate(row)
        row["output_label"] = label
        row["vetting_score"] = score
        row["rule_hits"] = ";".join(hits)
        row["why_label"] = " | ".join(reasons)
        plot = Path(row["plot_path"]) if text_value(row.get("plot_path")) else None
        row["plot_report_path"] = make_plot_link(
            plot,
            plot_dir,
            f"{tic}_{label}_combined.png",
            copy=args.copy_plots,
        )
        depth = safe_float(row.get("depth"))
        row["depth_ppt"] = depth * 1000.0 if depth is not None else row.get("median_depth_ppt", "")
        rows.append(row)

    rows.sort(key=lambda item: (LABELS.index(item["output_label"]), -safe_int(item["vetting_score"]), safe_int(item["TIC"])))
    for idx, row in enumerate(rows, 1):
        row["rank"] = idx

    csv_path = out_dir / "green_candidate_vetting.csv"
    html_path = out_dir / "green_candidate_vetting.html"
    write_csv(csv_path, rows)
    write_html(html_path, rows, csv_path.name)

    latest_link = OUT_BASE / "latest"
    if latest_link.exists() or latest_link.is_symlink():
        if latest_link.is_dir() and not latest_link.is_symlink():
            shutil.rmtree(latest_link)
        else:
            latest_link.unlink()
    latest_link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(out_dir, latest_link)

    counts = Counter(row["output_label"] for row in rows)
    print(f"output_dir={out_dir}")
    print(f"csv={csv_path}")
    print(f"html={html_path}")
    print(f"candidates={len(rows)}")
    for label in LABELS:
        print(f"{label}={counts.get(label, 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
