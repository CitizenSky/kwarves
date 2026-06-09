#!/usr/bin/env python3
"""Build the automatic candidate decision matrix."""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import os
import re
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "database" / "planet_hunter.db"
OUT_ROOT = PROJECT_ROOT / "candidate_matrix"
MATRIX_CSV = OUT_ROOT / "candidate_matrix.csv"
MATRIX_MD = OUT_ROOT / "candidate_matrix_dashboard.md"
MATRIX_HTML = OUT_ROOT / "candidate_matrix_dashboard.html"
COLOR_INDEX_ROOT = OUT_ROOT / "color_index"
LEVEL2_CSV = PROJECT_ROOT / "level2_planetencheck" / "level2_planetencheck_results.csv"
LEVEL0_MANIFEST = PROJECT_ROOT / "level0_lichtjahre_10ly_bis_500" / "manifest_all_candidates_by_distance.csv"
LEVEL5_SUMMARIES = [
    PROJECT_ROOT / "level5_detailvalidierung" / "level5_06_bestanden" / "green_purple_A_level5_summary.csv",
    PROJECT_ROOT / "level5_detailvalidierung" / "level5_06_bestanden" / "level5_all_6_summary.csv",
    PROJECT_ROOT / "level5_detailvalidierung" / "level5_06_bestanden" / "level5_recheck_summary.csv",
]
LEVEL5_SINGLE_TRANSIT_ROOT = PROJECT_ROOT / "level5_detailvalidierung" / "level5_02_einzeltransit_plots"


COLOR_FOLDERS = {
    "GREEN": "GREEN_SPC",
    "YELLOW": "YELLOW_SPC_ART",
    "PURPLE": "PURPLE_NEEDS_MORE_DATA",
    "RED": "RED_FP_REJECTED",
    "GRAY": "GRAY_IGNORE",
}


FIELDS = [
    "candidate_id",
    "tic_id",
    "period_days",
    "planet_radius_re",
    "snr",
    "n_transits",
    "n_sectors",
    "depth_ppt",
    "duration_hours",
    "sap_pdcsap_match",
    "odd_even_result",
    "transit_shape",
    "depth_stability",
    "data_gap_risk",
    "sector_edge_risk",
    "secondary_eclipse",
    "period_alias_risk",
    "rotation_risk",
    "status",
    "status_color",
    "extended_class",
    "evidence_score",
    "score_interpretation",
    "decision_reason",
    "next_step",
    "transit_stability_score",
    "sap_pdcsap_score",
    "odd_even_score",
    "data_window_score",
    "shape_score",
    "activity_score",
    "followup_score",
    "source_status",
    "source_spc_class",
    "hz_status",
    "distance_ly",
    "visible_transits",
    "clean_sector_count",
    "individual_transit_count",
    "visible_transit_count",
    "robust_transit_count",
    "median_depth_ppt",
    "depth_scatter_ppt",
    "depth_cv",
    "median_single_transit_snr",
    "min_depth_ratio",
    "transit_visibility_ratio",
    "individual_transit_plot_path",
    "individual_transit_statistics_json",
    "individual_transit_events_json",
    "level0_candidate_folder",
    "reference_plot",
    "updated_at",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build automatic candidate status/color matrix.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--tic", type=int, default=None)
    parser.add_argument("--no-db", action="store_true", help="Do not write candidate_matrix table.")
    parser.add_argument("--no-color-index", action="store_true", help="Do not write color index symlinks.")
    return parser.parse_args()


def safe_float(value: Any, default: float = float("nan")) -> float:
    try:
        if value in (None, ""):
            return default
        out = float(value)
        return out if math.isfinite(out) else default
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def finite(value: float) -> bool:
    return isinstance(value, float) and math.isfinite(value)


def none_if_nan(value: float) -> float | None:
    return value if finite(value) else None


def safe_int_or_none(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def robust_median(values: list[float]) -> float | None:
    clean = sorted(value for value in values if finite(value))
    if not clean:
        return None
    midpoint = len(clean) // 2
    if len(clean) % 2:
        return clean[midpoint]
    return (clean[midpoint - 1] + clean[midpoint]) / 2.0


def robust_scatter(values: list[float]) -> float | None:
    clean = [value for value in values if finite(value)]
    if not clean:
        return None
    median = robust_median(clean)
    if median is None:
        return None
    deviations = [abs(value - median) for value in clean]
    mad = robust_median(deviations)
    if mad is not None and mad > 0:
        return 1.4826 * mad
    if len(clean) >= 2:
        mean = sum(clean) / len(clean)
        return math.sqrt(sum((value - mean) ** 2 for value in clean) / len(clean))
    return 0.0


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def load_csv_by_tic(path: Path, tic_field: str = "TIC") -> dict[int, dict[str, str]]:
    if not path.exists():
        return {}
    rows: dict[int, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            tic = safe_int(row.get(tic_field) or row.get("tic") or row.get("tic_id"))
            if tic:
                rows[tic] = row
    return rows


def load_level5_rows() -> dict[int, dict[str, str]]:
    merged: dict[int, dict[str, str]] = {}
    for path in LEVEL5_SUMMARIES:
        tic_field = "tic" if path.name.startswith(("green", "level5")) else "TIC"
        for tic, row in load_csv_by_tic(path, tic_field=tic_field).items():
            merged.setdefault(tic, {}).update(row)
    return merged


def rel_project(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def classify_depth_stability_from_single_transits(stats: dict[str, Any]) -> str:
    visible_count = safe_int(stats.get("visible_transit_count"))
    min_ratio = safe_float(stats.get("min_depth_ratio"))
    depth_cv = safe_float(stats.get("depth_cv"))
    if visible_count < 2:
        return "INSUFFICIENT_TRANSITS"
    if finite(min_ratio) and min_ratio < 0.35:
        return "UNSTABLE"
    if finite(depth_cv) and depth_cv > 0.75:
        return "UNSTABLE"
    if finite(min_ratio) and min_ratio < 0.6:
        return "BORDERLINE"
    if finite(depth_cv) and depth_cv > 0.5:
        return "BORDERLINE"
    return "STABLE"


def load_level5_single_transit_data(root: Path = LEVEL5_SINGLE_TRANSIT_ROOT) -> dict[int, dict[str, Any]]:
    """Persist already materialized Level-5 single-transit CSV/PNG outputs."""
    data: dict[int, dict[str, Any]] = {}
    if not root.exists():
        return data
    for csv_path in sorted(root.glob("**/TIC_*_visible_single_transits_level5.csv")):
        match = re.search(r"TIC_(\d+)_visible_single_transits_level5\.csv$", csv_path.name)
        if not match:
            continue
        tic = safe_int(match.group(1))
        if not tic:
            continue
        events: list[dict[str, Any]] = []
        with csv_path.open(newline="", encoding="utf-8") as handle:
            for csv_row in csv.DictReader(handle):
                events.append({
                    "epoch": safe_int_or_none(csv_row.get("epoch")),
                    "expected_time": none_if_nan(safe_float(csv_row.get("expected_time"))),
                    "depth_ppt": none_if_nan(safe_float(csv_row.get("depth_ppt"))),
                    "local_snr": none_if_nan(safe_float(csv_row.get("local_snr"))),
                    "visible": boolish(csv_row.get("visible")),
                    "n_in": safe_int_or_none(csv_row.get("n_in")),
                    "n_out": safe_int_or_none(csv_row.get("n_out")),
                })
        visible_events = [event for event in events if event["visible"]]
        visible_depths = [event["depth_ppt"] for event in visible_events if event["depth_ppt"] is not None]
        visible_snrs = [event["local_snr"] for event in visible_events if event["local_snr"] is not None]
        median_depth = robust_median(visible_depths)
        depth_scatter = robust_scatter(visible_depths)
        depth_cv = depth_scatter / median_depth if depth_scatter is not None and median_depth and median_depth > 0 else None
        min_depth_ratio = min(visible_depths) / median_depth if visible_depths and median_depth and median_depth > 0 else None
        median_snr = robust_median(visible_snrs)
        plot_path = csv_path.with_name(f"TIC_{tic}_single_transits.png")
        stats = {
            "source": "LEVEL5_SINGLE_TRANSITS",
            "csv_path": rel_project(csv_path),
            "csv_available": True,
            "individual_transit_count": len(events),
            "visible_transit_count": len(visible_events),
            "robust_transit_count": sum(1 for event in visible_events if (event.get("local_snr") or 0) >= 5),
            "median_depth_ppt": round(median_depth, 5) if median_depth is not None else None,
            "depth_scatter_ppt": round(depth_scatter, 5) if depth_scatter is not None else None,
            "depth_cv": round(depth_cv, 5) if depth_cv is not None else None,
            "median_single_transit_snr": round(median_snr, 5) if median_snr is not None else None,
            "min_depth_ratio": round(min_depth_ratio, 5) if min_depth_ratio is not None else None,
            "transit_visibility_ratio": round(len(visible_events) / len(events), 5) if events else None,
            "plot_available": plot_path.exists(),
            "plot_status": "PLOT_AVAILABLE" if plot_path.exists() else "PLOT_NOT_AVAILABLE",
            "individual_transit_plot_path": rel_project(plot_path) if plot_path.exists() else "",
        }
        stats["depth_stability"] = classify_depth_stability_from_single_transits(stats)
        data[tic] = {"statistics": stats, "events": events}
    return data


def missing_level5_single_transit_data() -> dict[str, Any]:
    stats = {
        "source": "MISSING_LEVEL5_SINGLE_TRANSIT_CSV",
        "csv_available": False,
        "individual_transit_count": 0,
        "visible_transit_count": 0,
        "robust_transit_count": 0,
        "median_depth_ppt": None,
        "depth_scatter_ppt": None,
        "depth_cv": None,
        "median_single_transit_snr": None,
        "min_depth_ratio": None,
        "transit_visibility_ratio": None,
        "plot_available": False,
        "plot_status": "PLOT_NOT_AVAILABLE",
        "individual_transit_plot_path": "",
    }
    return {"statistics": stats, "events": []}


def load_candidates(conn: sqlite3.Connection, limit: int | None, tic: int | None) -> list[sqlite3.Row]:
    query = "SELECT * FROM candidates_v2"
    params: list[Any] = []
    if tic:
        query += " WHERE TIC=?"
        params.append(tic)
    query += " ORDER BY TIC"
    if limit:
        query += f" LIMIT {int(limit)}"
    return conn.execute(query, params).fetchall()


def parse_sap_pdcsap(summary: str) -> str:
    text = str(summary or "")
    match = re.search(r"SAP_PDCSAP=([A-Z_]+)", text)
    if not match:
        return "UNKNOWN"
    value = match.group(1)
    if value in {"OK", "MATCH", "AGREE", "TRUE"}:
        return "OK"
    if value in {"MISMATCH", "DISAGREE", "FALSE"}:
        return "MISMATCH"
    return "UNKNOWN"


def parse_med_gap(summary: str) -> float:
    match = re.search(r"med_gap=([0-9.]+)", str(summary or ""))
    return safe_float(match.group(1)) if match else float("nan")


def odd_even_result(row: sqlite3.Row, level5: dict[str, str]) -> str:
    # Prefer newer Level5 measurements over older DB flags. With only a few
    # transits, the historical odd/even flag can be too aggressive.
    for key in ("odd_even_ratio_independent", "odd_even_ratio", "odd_even_ratio_points"):
        ratio = safe_float(level5.get(key))
        if finite(ratio):
            if ratio < 0.5 or ratio > 2.0:
                return "BAD"
            if ratio < 0.7 or ratio > 1.5:
                return "BORDERLINE"
            return "OK"
    if boolish(row["fp_oe_flag"]):
        return "BAD"
    ratio = safe_float(row["oe_ratio"])
    if finite(ratio):
        if ratio < 0.5 or ratio > 2.0:
            return "BAD"
        if ratio < 0.7 or ratio > 1.5:
            return "BORDERLINE"
        return "OK"
    return "UNKNOWN"


def secondary_eclipse(row: sqlite3.Row, level2: dict[str, str], level5: dict[str, str]) -> str:
    # Level5 is the newest dedicated secondary scan, so let it override older
    # database flags when it exists.
    level5_ratios = [
        safe_float(level5.get("secondary_half_phase_ratio")),
        safe_float(level5.get("secondary_best_ratio_independent")),
    ]
    best_level5 = max((ratio for ratio in level5_ratios if finite(ratio)), default=float("nan"))
    if finite(best_level5):
        if best_level5 > 0.5:
            return "YES"
        if best_level5 > 0.25:
            return "BORDERLINE"
        return "NO"
    if boolish(row["fp_sec_flag"]):
        return "YES"
    ratios = [
        safe_float(row["sec_ratio"]),
        safe_float(level2.get("secondary_ratio_measured")),
    ]
    best = max((ratio for ratio in ratios if finite(ratio)), default=float("nan"))
    if finite(best) and best > 0.5:
        return "YES"
    if finite(best) and best > 0.25:
        return "BORDERLINE"
    if any(finite(ratio) for ratio in ratios):
        return "NO"
    return "UNKNOWN"


def transit_shape(level2: dict[str, str], row: sqlite3.Row) -> str:
    shape = str(level2.get("shape_status") or "").upper()
    duration_fraction = safe_float(row["duration_fraction"])
    if shape == "OK":
        return "U_SHAPE"
    if shape == "BASELINE_ASYMMETRY":
        return "ASYMMETRIC"
    if shape == "SECONDARY_LIKE":
        return "V_SHAPE"
    if finite(duration_fraction) and duration_fraction > 0.12:
        return "V_SHAPE"
    if shape in {"WEAK_SHAPE", "INSUFFICIENT_POINTS"}:
        return "UNKNOWN"
    return "UNKNOWN"


def depth_stability(row: sqlite3.Row, level5: dict[str, str]) -> str:
    if boolish(row["fp_scatter_flag"]):
        return "UNSTABLE"
    min_ratio = safe_float(level5.get("min_depth_ratio"))
    depth_cv = safe_float(level5.get("depth_cv"))
    if finite(min_ratio) and min_ratio < 0.35:
        return "UNSTABLE"
    if finite(depth_cv) and depth_cv > 0.75:
        return "UNSTABLE"
    if finite(min_ratio) and min_ratio < 0.6:
        return "BORDERLINE"
    if finite(depth_cv) and depth_cv > 0.5:
        return "BORDERLINE"
    if finite(min_ratio) or finite(depth_cv):
        return "STABLE"
    if boolish(row["fp_baseline_flag"]) or boolish(row["fp_baseline_std_flag"]):
        return "BORDERLINE"
    return "UNKNOWN"


def data_gap_risk(row: sqlite3.Row) -> str:
    med_gap = parse_med_gap(row["sector_quality_summary"])
    clean = safe_int(row["clean_sector_count"])
    sectors = safe_int(row["sector_count"])
    if boolish(row["fp_baseline_flag"]) or boolish(row["fp_baseline_std_flag"]):
        return "HIGH"
    if finite(med_gap) and med_gap >= 0.45:
        return "HIGH"
    if sectors and clean < sectors:
        return "MEDIUM"
    if finite(med_gap) and med_gap >= 0.2:
        return "MEDIUM"
    if sectors:
        return "LOW"
    return "UNKNOWN"


def sector_edge_risk(row: sqlite3.Row, level5: dict[str, str]) -> str:
    visible = safe_int(row["visible_transits"])
    transits = safe_int(row["transit_count"])
    if "sector_consistency_recheck" in str(level5.get("flags") or ""):
        return "HIGH"
    if transits and visible and visible < max(2, min(3, transits)):
        return "MEDIUM"
    if transits and visible == 0:
        return "HIGH"
    if visible:
        return "LOW"
    return "UNKNOWN"


def period_alias_risk(row: sqlite3.Row) -> str:
    period = safe_float(row["best_period"])
    if not finite(period) or period <= 0:
        return "UNKNOWN"
    tess_orbit = 13.7
    for multiple in range(1, 10):
        alias = tess_orbit * multiple
        if abs(period - alias) / alias < 0.02:
            return "HIGH"
    nearest_int = round(period)
    if nearest_int > 0 and abs(period - nearest_int) < 0.02:
        return "MEDIUM"
    return "LOW"


def rotation_risk(row: sqlite3.Row) -> str:
    notes = str(row["notes"] or "").upper()
    if "ACTIVE" in notes or "ROTATION" in notes:
        return "HIGH"
    if "ARTIFACT_OR_SYSTEMATICS_RISK" in notes or str(row["spc_class"] or "") == "SPC_ART":
        return "POSSIBLE"
    return "UNKNOWN"


def score_components(metrics: dict[str, Any]) -> dict[str, int]:
    n_transits = safe_int(metrics["n_transits"])
    n_sectors = safe_int(metrics["n_sectors"])
    visible = safe_int(metrics.get("visible_transits"))
    clean = safe_int(metrics.get("clean_sector_count"))

    if metrics["depth_stability"] == "STABLE" and n_transits >= 5:
        transit_stability = 20
    elif metrics["depth_stability"] == "BORDERLINE" or n_transits >= 5:
        transit_stability = 12
    elif n_transits >= 3:
        transit_stability = 8
    else:
        transit_stability = 2

    sap = {"OK": 20, "UNKNOWN": 10, "MISMATCH": 0}.get(metrics["sap_pdcsap_match"], 8)
    odd_even = {"OK": 15, "BORDERLINE": 8, "UNKNOWN": 7, "BAD": 0}.get(metrics["odd_even_result"], 7)

    if metrics["data_gap_risk"] == "LOW" and metrics["sector_edge_risk"] == "LOW" and n_sectors >= 2:
        data_window = 15
    elif metrics["data_gap_risk"] in {"MEDIUM", "UNKNOWN"} or metrics["sector_edge_risk"] in {"MEDIUM", "UNKNOWN"}:
        data_window = 8
    else:
        data_window = 2
    if visible >= 3 and clean >= 2:
        data_window = min(15, data_window + 3)

    shape = {"U_SHAPE": 10, "UNKNOWN": 5, "ASYMMETRIC": 3, "V_SHAPE": 0}.get(metrics["transit_shape"], 5)
    activity = {"UNKNOWN": 6, "LOW": 10, "POSSIBLE": 5, "HIGH": 0}.get(metrics["rotation_risk"], 6)
    followup = 10 if n_transits >= 5 and n_sectors >= 2 else 7 if n_transits >= 3 else 2
    if metrics["secondary_eclipse"] == "YES":
        followup = min(followup, 2)
    elif metrics["secondary_eclipse"] == "BORDERLINE":
        followup = min(followup, 5)

    return {
        "transit_stability_score": transit_stability,
        "sap_pdcsap_score": sap,
        "odd_even_score": odd_even,
        "data_window_score": data_window,
        "shape_score": shape,
        "activity_score": activity,
        "followup_score": followup,
    }


def score_interpretation(score: int) -> str:
    if score >= 90:
        return "SPC_STRONG"
    if score >= 75:
        return "SPC"
    if score >= 60:
        return "SPC_ART"
    if score >= 40:
        return "NEEDS_MORE_DATA"
    return "FP"


def decide(metrics: dict[str, Any], components: dict[str, int]) -> tuple[str, str, str, str, str]:
    reasons: list[str] = []
    n_transits = safe_int(metrics["n_transits"])
    n_sectors = safe_int(metrics["n_sectors"])
    score = sum(components.values())
    interpretation = score_interpretation(score)

    odd_bad = metrics["odd_even_result"] == "BAD"
    secondary_bad = metrics["secondary_eclipse"] == "YES"
    strong_v = metrics["transit_shape"] == "V_SHAPE"
    sap_mismatch = metrics["sap_pdcsap_match"] == "MISMATCH"
    depth_unstable = metrics["depth_stability"] == "UNSTABLE"
    gap_risk = metrics["data_gap_risk"] == "HIGH"
    edge_risk = metrics["sector_edge_risk"] == "HIGH"
    u_shape_ok = metrics["transit_shape"] == "U_SHAPE"
    odd_even_ok = metrics["odd_even_result"] == "OK"
    sap_ok = metrics["sap_pdcsap_match"] == "OK"
    depth_stable = metrics["depth_stability"] == "STABLE"
    secondary_ok = metrics["secondary_eclipse"] == "NO"
    data_window_ok = metrics["data_gap_risk"] == "LOW" and metrics["sector_edge_risk"] == "LOW"

    if n_transits < 3:
        status, color = "IGNORE", "GRAY"
        reasons.append("Ntr<3: Einzelereignis/zu wenige Transits.")
    elif n_transits < 5:
        status, color = "NEEDS_MORE_DATA", "PURPLE"
        reasons.append("Ntr<5: neue TESS-Daten/mehr Transits abwarten.")
    elif odd_bad:
        status, color = "FP", "RED"
        reasons.append("Odd/Even auffaellig.")
    elif secondary_bad:
        status, color = "FP", "RED"
        reasons.append("Secondary Eclipse vorhanden oder starkes Secondary-Signal.")
    elif strong_v:
        status, color = "FP", "RED"
        reasons.append("Starke V-Form/EB-Risiko.")
    elif sap_mismatch:
        status, color = "SPC_ART", "YELLOW"
        reasons.append("SAP/PDCSAP widersprechen sich.")
    elif depth_unstable:
        status, color = "SPC_ART", "YELLOW"
        reasons.append("Transit-Tiefe instabil.")
    elif gap_risk:
        status, color = "SPC_ART", "YELLOW"
        reasons.append("Datenluecken/Systematik-Risiko.")
    elif edge_risk:
        status, color = "SPC_ART", "YELLOW"
        reasons.append("Transitfenster/Sektorrand-Risiko.")
    elif (
        n_transits >= 5
        and odd_even_ok
        and sap_ok
        and u_shape_ok
        and depth_stable
        and secondary_ok
        and data_window_ok
        and n_sectors >= 2
    ):
        status, color = "SPC", "GREEN"
        reasons.append("Alle SPC-Kriterien erfuellt: Ntr>=5, SAP/PDCSAP ok, Odd/Even ok, stabile U-Form, kein Secondary.")
    else:
        status, color = "SPC_ART", "YELLOW"
        reasons.append("Signal sichtbar, aber mindestens ein Vetting-Kriterium ist unvollstaendig/unsicher.")

    extended = extended_class(status, interpretation, metrics)
    return status, color, extended, interpretation, " ".join(reasons)


def extended_class(status: str, interpretation: str, metrics: dict[str, Any]) -> str:
    if status == "SPC" and interpretation == "SPC_STRONG":
        return "SPC_STRONG"
    if status == "SPC":
        if safe_float(metrics["planet_radius_re"]) <= 2.0 and safe_float(metrics["snr"]) >= 10:
            return "SPC_RV_NEEDED"
        return "SPC"
    if status == "SPC_ART":
        if metrics["rotation_risk"] in {"HIGH", "POSSIBLE"}:
            return "SPC_ACTIVE_STAR"
        if safe_int(metrics["n_transits"]) >= 5 and metrics["sap_pdcsap_match"] != "MISMATCH":
            return "SPC_FOLLOWUP_READY"
        return "SPC_ART"
    if status == "NEEDS_MORE_DATA":
        return "SPC_WEAK_DATA"
    if status == "FP":
        if metrics["odd_even_result"] == "BAD" or metrics["secondary_eclipse"] == "YES" or metrics["transit_shape"] == "V_SHAPE":
            return "EB_RISK"
        return "REJECTED"
    return "IGNORE"


def next_step(status: str, metrics: dict[str, Any]) -> str:
    if status == "IGNORE":
        return "Nicht weiter verfolgen, ausser neue Daten liefern unabhaengige Transits."
    if status == "NEEDS_MORE_DATA":
        return "Automatisch auf neue TESS-Sektoren warten; danach BLS/Vetting erneut laufen lassen."
    if status == "FP":
        return "Aus Toplisten entfernen; FP/Reject dokumentieren."
    if status == "SPC_ART":
        if metrics["sap_pdcsap_match"] in {"UNKNOWN", "MISMATCH"}:
            return "SAP/PDCSAP Vergleich nachholen, danach Odd/Even und Einzeltransite pruefen."
        if metrics["secondary_eclipse"] == "BORDERLINE":
            return "Secondary-Scan manuell pruefen und bei Bedarf Level5-Recheck."
        if metrics["depth_stability"] != "STABLE":
            return "Einzeltransite und Tiefenstabilitaet pruefen."
        return "Level5-Detailvalidierung: Odd/Even, Secondary, Einzeltransite, Nachbarstern."
    if status == "SPC":
        if safe_float(metrics["planet_radius_re"]) <= 2.0:
            return "Level6-Dossier vorbereiten; RV/Folgebeobachtung als naechster Schritt."
        return "Level6-Dossier vorbereiten und externe Katalog-/Blend-Pruefung finalisieren."
    return "Manuell pruefen."


def build_row(
    row: sqlite3.Row,
    level2: dict[str, str],
    level5: dict[str, str],
    level5_single: dict[str, Any],
    level0: dict[str, str],
    updated_at: str,
) -> dict[str, Any]:
    level5_single = level5_single or missing_level5_single_transit_data()
    single_stats = dict(level5_single.get("statistics") or {})
    single_events = list(level5_single.get("events") or [])
    if single_stats and not finite(safe_float(level5.get("min_depth_ratio"))):
        level5 = {**level5, "min_depth_ratio": single_stats.get("min_depth_ratio") or ""}
    if single_stats and not finite(safe_float(level5.get("depth_cv"))):
        level5 = {**level5, "depth_cv": single_stats.get("depth_cv") or ""}
    metrics: dict[str, Any] = {
        "candidate_id": row["id"],
        "tic_id": row["TIC"],
        "period_days": safe_float(row["best_period"]),
        "planet_radius_re": safe_float(row["planet_radius_earth"]),
        "snr": safe_float(row["transit_snr"]),
        "n_transits": safe_int(row["transit_count"]),
        "n_sectors": safe_int(row["sector_count"]),
        "depth_ppt": safe_float(row["depth"], 0.0) * 1000.0,
        "duration_hours": safe_float(row["duration"], 0.0) * 24.0,
        "sap_pdcsap_match": parse_sap_pdcsap(row["sector_quality_summary"]),
        "odd_even_result": odd_even_result(row, level5),
        "transit_shape": transit_shape(level2, row),
        "depth_stability": depth_stability(row, level5),
        "data_gap_risk": data_gap_risk(row),
        "sector_edge_risk": sector_edge_risk(row, level5),
        "secondary_eclipse": secondary_eclipse(row, level2, level5),
        "period_alias_risk": period_alias_risk(row),
        "rotation_risk": rotation_risk(row),
        "source_status": row["status"] or "",
        "source_spc_class": row["spc_class"] or "",
        "hz_status": row["hz_status"] or "",
        "distance_ly": safe_float(row["distance_ly"]),
        "visible_transits": safe_int(row["visible_transits"]),
        "clean_sector_count": safe_int(row["clean_sector_count"]),
        "individual_transit_count": single_stats.get("individual_transit_count"),
        "visible_transit_count": single_stats.get("visible_transit_count"),
        "robust_transit_count": single_stats.get("robust_transit_count"),
        "median_depth_ppt": single_stats.get("median_depth_ppt"),
        "depth_scatter_ppt": single_stats.get("depth_scatter_ppt"),
        "depth_cv": single_stats.get("depth_cv"),
        "median_single_transit_snr": single_stats.get("median_single_transit_snr"),
        "min_depth_ratio": single_stats.get("min_depth_ratio"),
        "transit_visibility_ratio": single_stats.get("transit_visibility_ratio"),
        "individual_transit_plot_path": single_stats.get("individual_transit_plot_path", ""),
        "individual_transit_statistics_json": json.dumps(single_stats, ensure_ascii=False, separators=(",", ":")) if single_stats else "",
        "individual_transit_events_json": json.dumps(single_events, ensure_ascii=False, separators=(",", ":")) if single_events else "",
        "level0_candidate_folder": level0.get("candidate_folder", ""),
        "reference_plot": level2.get("reference_plot") or level2.get("level2_folder_plot") or "",
        "updated_at": updated_at,
    }
    components = score_components(metrics)
    status, color, extended, interpretation, reason = decide(metrics, components)
    score = sum(components.values())
    out = {
        **metrics,
        "status": status,
        "status_color": color,
        "extended_class": extended,
        "evidence_score": score,
        "score_interpretation": interpretation,
        "decision_reason": reason,
        "next_step": next_step(status, metrics),
        **components,
    }
    return out


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS candidate_matrix (
            tic_id INTEGER PRIMARY KEY,
            candidate_id INTEGER,
            period_days REAL,
            planet_radius_re REAL,
            snr REAL,
            n_transits INTEGER,
            n_sectors INTEGER,
            depth_ppt REAL,
            duration_hours REAL,
            sap_pdcsap_match TEXT,
            odd_even_result TEXT,
            transit_shape TEXT,
            depth_stability TEXT,
            data_gap_risk TEXT,
            sector_edge_risk TEXT,
            secondary_eclipse TEXT,
            period_alias_risk TEXT,
            rotation_risk TEXT,
            status TEXT,
            status_color TEXT,
            extended_class TEXT,
            evidence_score REAL,
            score_interpretation TEXT,
            decision_reason TEXT,
            next_step TEXT,
            transit_stability_score REAL,
            sap_pdcsap_score REAL,
            odd_even_score REAL,
            data_window_score REAL,
            shape_score REAL,
            activity_score REAL,
            followup_score REAL,
            source_status TEXT,
            source_spc_class TEXT,
            hz_status TEXT,
            distance_ly REAL,
            visible_transits INTEGER,
            clean_sector_count INTEGER,
            individual_transit_count INTEGER,
            visible_transit_count INTEGER,
            robust_transit_count INTEGER,
            median_depth_ppt REAL,
            depth_scatter_ppt REAL,
            depth_cv REAL,
            median_single_transit_snr REAL,
            min_depth_ratio REAL,
            transit_visibility_ratio REAL,
            individual_transit_plot_path TEXT,
            individual_transit_statistics_json TEXT,
            individual_transit_events_json TEXT,
            level0_candidate_folder TEXT,
            reference_plot TEXT,
            updated_at TEXT
        )
        """
    )
    existing = {row[1] for row in conn.execute("PRAGMA table_info(candidate_matrix)").fetchall()}
    column_types = {
        "individual_transit_count": "INTEGER",
        "visible_transit_count": "INTEGER",
        "robust_transit_count": "INTEGER",
        "median_depth_ppt": "REAL",
        "depth_scatter_ppt": "REAL",
        "depth_cv": "REAL",
        "median_single_transit_snr": "REAL",
        "min_depth_ratio": "REAL",
        "transit_visibility_ratio": "REAL",
        "individual_transit_plot_path": "TEXT",
        "individual_transit_statistics_json": "TEXT",
        "individual_transit_events_json": "TEXT",
    }
    for column, column_type in column_types.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE candidate_matrix ADD COLUMN {column} {column_type}")


def write_db(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
    ensure_table(conn)
    fields = [field for field in FIELDS if field != "tic_id"]
    insert_fields = ["tic_id", *fields]
    placeholders = ",".join("?" for _ in insert_fields)
    updates = ",".join(f"{field}=excluded.{field}" for field in fields)
    conn.executemany(
        f"""
        INSERT INTO candidate_matrix ({','.join(insert_fields)})
        VALUES ({placeholders})
        ON CONFLICT(tic_id) DO UPDATE SET {updates}
        """,
        [[row.get(field) for field in insert_fields] for row in rows],
    )
    conn.commit()


def write_csv_output(rows: list[dict[str, Any]]) -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    with MATRIX_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: list[dict[str, Any]]) -> None:
    counts = Counter(row["status_color"] for row in rows)
    status_counts = Counter(row["status"] for row in rows)
    top = sorted(rows, key=lambda row: (-safe_float(row["evidence_score"]), row["tic_id"]))[:25]
    lines = [
        "# Candidate Matrix Dashboard",
        "",
        f"Updated: {datetime.now().isoformat(timespec='seconds')}",
        f"Candidates: {len(rows)}",
        "",
        "## Colors",
        "",
    ]
    for color in ("GREEN", "YELLOW", "PURPLE", "RED", "GRAY"):
        lines.append(f"- {color}: {counts.get(color, 0)}")
    lines.extend(["", "## Status", ""])
    for status, count in status_counts.most_common():
        lines.append(f"- {status}: {count}")
    lines.extend(
        [
            "",
            "## Top Evidence Scores",
            "",
            "| TIC | Status | Color | Score | P d | Rp Re | SNR | Ntr | Reason | Next step |",
            "|---:|---|---|---:|---:|---:|---:|---:|---|---|",
        ]
    )
    for row in top:
        lines.append(
            "| {tic} | {status} | {color} | {score} | {period:.3f} | {rp:.2f} | {snr:.1f} | {ntr} | {reason} | {next_step} |".format(
                tic=row["tic_id"],
                status=row["status"],
                color=row["status_color"],
                score=row["evidence_score"],
                period=safe_float(row["period_days"], 0.0),
                rp=safe_float(row["planet_radius_re"], 0.0),
                snr=safe_float(row["snr"], 0.0),
                ntr=row["n_transits"],
                reason=str(row["decision_reason"]).replace("|", "/"),
                next_step=str(row["next_step"]).replace("|", "/"),
            )
        )
    lines.append("")
    MATRIX_MD.write_text("\n".join(lines), encoding="utf-8")


def write_html(rows: list[dict[str, Any]]) -> None:
    rows_sorted = sorted(rows, key=lambda row: (COLOR_ORDER.get(row["status_color"], 99), -safe_float(row["evidence_score"]), row["tic_id"]))
    style = """
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 24px; color: #18202a; }
    table { border-collapse: collapse; width: 100%; font-size: 13px; }
    th, td { border-bottom: 1px solid #d8dee6; padding: 6px 8px; text-align: left; vertical-align: top; }
    th { position: sticky; top: 0; background: #f7f9fb; z-index: 1; }
    .GREEN { background: #e8f6ed; }
    .YELLOW { background: #fff6d8; }
    .PURPLE { background: #f0e9ff; }
    .RED { background: #ffe9e8; }
    .GRAY { background: #eef1f4; }
    .num { text-align: right; font-variant-numeric: tabular-nums; }
    """
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<title>Candidate Matrix Dashboard</title>",
        f"<style>{style}</style></head><body>",
        "<h1>Candidate Matrix Dashboard</h1>",
        f"<p>Updated: {html.escape(datetime.now().isoformat(timespec='seconds'))} | Candidates: {len(rows)}</p>",
        "<table><thead><tr>",
    ]
    headers = ["TIC", "Status", "Color", "Score", "P", "Rp", "SNR", "Ntr", "Shape", "Odd/Even", "Secondary", "Reason", "Next step"]
    parts.extend(f"<th>{h}</th>" for h in headers)
    parts.append("</tr></thead><tbody>")
    for row in rows_sorted:
        cls = row["status_color"]
        parts.append(f"<tr class='{cls}'>")
        cells = [
            row["tic_id"],
            row["status"],
            row["status_color"],
            row["evidence_score"],
            f"{safe_float(row['period_days'], 0.0):.3f}",
            f"{safe_float(row['planet_radius_re'], 0.0):.2f}",
            f"{safe_float(row['snr'], 0.0):.1f}",
            row["n_transits"],
            row["transit_shape"],
            row["odd_even_result"],
            row["secondary_eclipse"],
            row["decision_reason"],
            row["next_step"],
        ]
        for idx, cell in enumerate(cells):
            td_class = " class='num'" if idx in {0, 3, 4, 5, 6, 7} else ""
            parts.append(f"<td{td_class}>{html.escape(str(cell))}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table></body></html>")
    MATRIX_HTML.write_text("".join(parts), encoding="utf-8")


COLOR_ORDER = {"GREEN": 0, "YELLOW": 1, "PURPLE": 2, "RED": 3, "GRAY": 4}


def link_color_index(rows: list[dict[str, Any]]) -> None:
    for folder in COLOR_FOLDERS.values():
        path = COLOR_INDEX_ROOT / folder
        path.mkdir(parents=True, exist_ok=True)
        for old in path.glob("*"):
            if old.is_symlink():
                old.unlink()
    for row in rows:
        color = row["status_color"]
        folder = COLOR_INDEX_ROOT / COLOR_FOLDERS[color]
        target_text = row.get("level0_candidate_folder") or row.get("reference_plot")
        if not target_text:
            continue
        target = PROJECT_ROOT / target_text if not str(target_text).startswith("/") else Path(str(target_text))
        if not target.exists():
            continue
        name = f"{int(row['evidence_score']):03d}_TIC_{row['tic_id']}_{row['status']}"
        if target.is_file():
            name += target.suffix
        link = folder / name
        if link.exists() or link.is_symlink():
            link.unlink()
        os.symlink(target.resolve(), link, target_is_directory=target.is_dir())


def main() -> int:
    args = parse_args()
    updated_at = datetime.now().isoformat(timespec="seconds")
    level2 = load_csv_by_tic(LEVEL2_CSV)
    level5 = load_level5_rows()
    level5_single = load_level5_single_transit_data()
    level0 = load_csv_by_tic(LEVEL0_MANIFEST)
    conn = connect_db()
    try:
        candidate_rows = load_candidates(conn, args.limit, args.tic)
        rows = [
            build_row(
                row,
                level2.get(int(row["TIC"]), {}),
                level5.get(int(row["TIC"]), {}),
                level5_single.get(int(row["TIC"]), {}),
                level0.get(int(row["TIC"]), {}),
                updated_at,
            )
            for row in candidate_rows
        ]
        rows.sort(key=lambda row: (COLOR_ORDER.get(row["status_color"], 99), -safe_float(row["evidence_score"]), row["tic_id"]))
        write_csv_output(rows)
        write_markdown(rows)
        write_html(rows)
        if not args.no_db:
            write_db(conn, rows)
        if not args.no_color_index:
            link_color_index(rows)
    finally:
        conn.close()

    counts = Counter(row["status_color"] for row in rows)
    print(f"Candidates: {len(rows)}")
    print("Colors:", dict(counts))
    print(f"CSV: {MATRIX_CSV}")
    print(f"Dashboard: {MATRIX_HTML}")
    print(f"DB table: {'skipped' if args.no_db else 'candidate_matrix'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
