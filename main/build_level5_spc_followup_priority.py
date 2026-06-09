#!/usr/bin/env python3
"""Build Level-5 input lists for SPC follow-up and Stage-2-relevant candidates."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "database" / "planet_hunter.db"
LEVEL0_ROOT = PROJECT_ROOT / "level0_lichtjahre_10ly_bis_500"
MANIFEST_PATH = LEVEL0_ROOT / "manifest_all_candidates_by_distance.csv"
OLD_PRIORITY_CSV = (
    PROJECT_ROOT
    / "level1_rohkandidaten"
    / "level1_visuelle_pruefung"
    / "level1_05_GRUEN_VIOLETT_SPC_HZ"
    / "05_GRUEN_VIOLETT_SPC_HZ_priority.csv"
)
OUT_ROOT = PROJECT_ROOT / "level5_detailvalidierung" / "level5_01_input_kandidaten"
SPC_PRIORITY_CSV = OUT_ROOT / "level5_spc_followup_stage2_priority.csv"
COMBINED_PRIORITY_CSV = OUT_ROOT / "level5_combined_priority.csv"
DASHBOARD_DATA_PATH = PROJECT_ROOT / "scripts" / "dashboard" / "dashboard-data.js"
TARGET_TICS = {75878355, 239187696}

FIELDS = [
    "rank",
    "priority_group",
    "priority_score",
    "TIC",
    "status",
    "spc_class",
    "spcStatus",
    "followup_status",
    "hz_status",
    "distance_ly",
    "best_period",
    "planet_radius_earth",
    "transit_snr",
    "snr",
    "transit_count",
    "visible_transits",
    "clean_sector_count",
    "sector_count",
    "evidence_score",
    "stage2_blocking_issues",
    "selection_reasons",
    "exclusion_reason",
    "revisit_priority",
    "next_recheck",
    "is_fp",
    "notes",
    "priority_reason",
    "combined_plot_link",
    "combined_plot_source",
    "level0_candidate_folder",
    "lightcurve_path",
    "source_list",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Level-5 SPC follow-up and combined priority CSVs.")
    parser.add_argument("--dry-run", action="store_true", help="Print coverage stats without writing CSV files.")
    parser.add_argument("--old-priority-csv", type=Path, default=OLD_PRIORITY_CSV)
    parser.add_argument("--out-root", type=Path, default=OUT_ROOT)
    parser.add_argument("--dashboard-data", type=Path, default=DASHBOARD_DATA_PATH)
    parser.add_argument("--evidence-threshold", type=float, default=60.0)
    return parser.parse_args()


def safe_float(value: Any, default: float = float("nan")) -> float:
    try:
        if value in (None, ""):
            return default
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"none", "null", "nan"} else text


def finite(value: float) -> bool:
    return isinstance(value, float) and math.isfinite(value)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_manifest() -> dict[int, dict[str, str]]:
    rows = read_csv(MANIFEST_PATH)
    return {safe_int(row.get("TIC")): row for row in rows if safe_int(row.get("TIC"))}


def plot_for_candidate(candidate_folder: str) -> Path | None:
    if not candidate_folder:
        return None
    png_dir = PROJECT_ROOT / candidate_folder / "lichtkurven_png"
    for name in ("LICHTKURVE_COMBINED.png", "LICHTKURVE_FOLDED.png", "LICHTKURVE_RAW.png"):
        path = png_dir / name
        if path.exists():
            return path
    return None


def lightcurve_exists(path_text: str) -> bool:
    if not path_text:
        return False
    path = Path(path_text)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.exists() and path.is_file()


def parse_stats_source(value: str) -> str:
    if not value:
        return ""
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return ""
    return clean_text(data.get("source"))


def load_dashboard_index(path: Path) -> dict[int, dict[str, Any]]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if "=" not in text:
        return {}
    payload = text.split("=", 1)[1].strip().rstrip(";")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return {safe_int(row.get("tic")): row for row in data.get("candidates", []) if safe_int(row.get("tic"))}


def load_candidate_rows() -> list[dict[str, Any]]:
    query = """
        SELECT c.TIC, c.gaia_id, c.status AS db_status, c.spc_class, c.is_fp, c.hz_status,
               c.distance_ly, c.best_period, c.duration, c.depth, c.transit_time,
               c.planet_radius_earth, c.transit_snr, c.transit_count, c.visible_transits,
               c.clean_sector_count, c.sector_count, c.revisit_priority, c.next_recheck,
               c.notes, c.lightcurve_dir,
               m.status AS matrix_status, m.status_color, m.extended_class, m.evidence_score,
               m.score_interpretation, m.decision_reason, m.next_step,
               m.individual_transit_statistics_json
          FROM candidates_v2 c
          LEFT JOIN candidate_matrix m ON m.tic_id = c.TIC
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(query)]


def is_clear_false_positive(row: dict[str, Any]) -> bool:
    status_text = " ".join(
        clean_text(row.get(key)).upper()
        for key in ("db_status", "spc_class", "matrix_status", "status_color", "extended_class", "score_interpretation")
    )
    if safe_int(row.get("is_fp")):
        return True
    if "FALSE_POSITIVE" in status_text or "RED_FP" in status_text:
        return True
    if clean_text(row.get("status_color")).upper() == "RED":
        return True
    if any(token in status_text for token in ("EB_RISK", "REJECTED")):
        return True
    return False


def exclusion_reason(row: dict[str, Any], dashboard_row: dict[str, Any] | None = None) -> str:
    if is_clear_false_positive(row):
        return "CLEAR_FALSE_POSITIVE"
    period = safe_float(row.get("best_period"))
    if not finite(period) or period <= 0:
        return "NO_PERIOD"
    epoch = safe_float(row.get("transit_time"))
    if not finite(epoch):
        return "NO_EPHEMERIS"
    if not lightcurve_exists(clean_text(row.get("lightcurve_dir"))):
        return "NO_LIGHTCURVE_DATA"
    dashboard_row = dashboard_row or {}
    status_text = " ".join(
        clean_text(value).upper()
        for value in (
            row.get("db_status"),
            row.get("matrix_status"),
            dashboard_row.get("status"),
            dashboard_row.get("vettingStage2Class"),
        )
    )
    if "WAIT_FOR_TESS" in status_text and not lightcurve_exists(clean_text(row.get("lightcurve_dir"))):
        return "WAIT_FOR_TESS_NO_LIGHTCURVE"
    return ""


def dashboard_stage2_blockers(dashboard_row: dict[str, Any] | None) -> list[str]:
    dashboard_row = dashboard_row or {}
    blockers = dashboard_row.get("stage2BlockingIssues") or dashboard_row.get("stage2_blocking_issues") or []
    if isinstance(blockers, list):
        return [clean_text(item) for item in blockers if clean_text(item)]
    return [clean_text(blockers)] if clean_text(blockers) else []


def dashboard_followup_status(dashboard_row: dict[str, Any] | None) -> str:
    dashboard_row = dashboard_row or {}
    text = " ".join(
        clean_text(value).upper()
        for value in (
            dashboard_row.get("matrixClass"),
            dashboard_row.get("matrixStatus"),
            dashboard_row.get("followupStrength"),
            " ".join(dashboard_row.get("displayLabels") or []),
            ((dashboard_row.get("fullVetting") or {}).get("classification") if isinstance(dashboard_row.get("fullVetting"), dict) else ""),
            ((dashboard_row.get("fullVetting") or {}).get("status") if isinstance(dashboard_row.get("fullVetting"), dict) else ""),
        )
    )
    return "FOLLOWUP_PRIORITY" if "FOLLOWUP_PRIORITY" in text else ""


def selection_reasons(row: dict[str, Any], dashboard_row: dict[str, Any] | None, evidence_threshold: float) -> list[str]:
    reasons: list[str] = []
    extended = clean_text(row.get("extended_class")).upper()
    evidence = safe_float(row.get("evidence_score"), 0.0)
    visible = safe_int(row.get("visible_transits"))
    snr = safe_float(row.get("transit_snr"), 0.0)
    followup_status = "FOLLOWUP_PRIORITY" if extended == "FOLLOWUP_PRIORITY" else dashboard_followup_status(dashboard_row)
    blockers = dashboard_stage2_blockers(dashboard_row)
    if extended == "SPC_FOLLOWUP_READY":
        reasons.append("SPC_FOLLOWUP_READY")
    if evidence >= evidence_threshold:
        reasons.append(f"EVIDENCE_SCORE>={evidence_threshold:g}")
    if "MISSING_LEVEL5_SINGLE_TRANSIT_CSV" in blockers:
        reasons.append("MISSING_LEVEL5_SINGLE_TRANSIT_CSV")
    if followup_status == "FOLLOWUP_PRIORITY":
        reasons.append("FOLLOWUP_PRIORITY")
    if visible >= 3 and snr >= 10:
        reasons.append("VISIBLE_TRANSITS>=3_AND_SNR>=10")
    return reasons


def priority_score(row: dict[str, Any], reasons: list[str]) -> float:
    evidence = safe_float(row.get("evidence_score"), 0.0)
    snr = safe_float(row.get("transit_snr"), 0.0)
    visible = safe_int(row.get("visible_transits"))
    transits = safe_int(row.get("transit_count"))
    score = evidence
    score += min(snr, 100.0) * 0.25
    score += min(visible, 10) * 2.0
    score += min(transits, 20) * 0.4
    if "SPC_FOLLOWUP_READY" in reasons:
        score += 20
    if "MISSING_LEVEL5_SINGLE_TRANSIT_CSV" in reasons:
        score += 15
    if "FOLLOWUP_PRIORITY" in reasons:
        score += 15
    return round(score, 3)


def priority_group(reasons: list[str], score: float) -> str:
    if "SPC_FOLLOWUP_READY" in reasons or "MISSING_LEVEL5_SINGLE_TRANSIT_CSV" in reasons:
        return "A_LEVEL5_NOW"
    if score >= 85:
        return "A_LEVEL5_NOW"
    if "EVIDENCE_SCORE>=60" in reasons or "VISIBLE_TRANSITS>=3_AND_SNR>=10" in reasons:
        return "B_STRONG_REVIEW"
    return "C_RECHECK_LATER"


def build_spc_rows(evidence_threshold: float, dashboard_data_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manifest_by_tic = read_manifest()
    dashboard_by_tic = load_dashboard_index(dashboard_data_path)
    selected: list[dict[str, Any]] = []
    excluded_selected: list[dict[str, Any]] = []
    for db_row in load_candidate_rows():
        tic = safe_int(db_row.get("TIC"))
        dashboard_row = dashboard_by_tic.get(tic, {})
        reasons = selection_reasons(db_row, dashboard_row, evidence_threshold)
        if not reasons:
            continue
        reject_reason = exclusion_reason(db_row, dashboard_row)
        if reject_reason:
            excluded_selected.append({"TIC": tic, "exclusion_reason": reject_reason, "selection_reasons": ";".join(reasons)})
            continue
        manifest = manifest_by_tic.get(tic, {})
        candidate_folder = clean_text(manifest.get("candidate_folder"))
        plot = plot_for_candidate(candidate_folder)
        score = priority_score(db_row, reasons)
        row = {
            "priority_group": priority_group(reasons, score),
            "priority_score": score,
            "TIC": tic,
            "status": clean_text(db_row.get("db_status") or db_row.get("spc_class")),
            "spc_class": clean_text(db_row.get("spc_class")),
            "spcStatus": clean_text(db_row.get("extended_class")),
            "followup_status": dashboard_followup_status(dashboard_row)
            or ("FOLLOWUP_PRIORITY" if clean_text(db_row.get("extended_class")).upper() == "FOLLOWUP_PRIORITY" else ""),
            "hz_status": clean_text(db_row.get("hz_status")),
            "distance_ly": safe_float(db_row.get("distance_ly"), 0.0),
            "best_period": safe_float(db_row.get("best_period"), 0.0),
            "planet_radius_earth": safe_float(db_row.get("planet_radius_earth"), 0.0),
            "transit_snr": safe_float(db_row.get("transit_snr"), 0.0),
            "snr": safe_float(db_row.get("transit_snr"), 0.0),
            "transit_count": safe_int(db_row.get("transit_count")),
            "visible_transits": safe_int(db_row.get("visible_transits")),
            "clean_sector_count": safe_int(db_row.get("clean_sector_count")),
            "sector_count": safe_int(db_row.get("sector_count")),
            "evidence_score": safe_float(db_row.get("evidence_score"), 0.0),
            "stage2_blocking_issues": ";".join(dashboard_stage2_blockers(dashboard_row)),
            "selection_reasons": ";".join(reasons),
            "exclusion_reason": "",
            "revisit_priority": clean_text(db_row.get("revisit_priority")),
            "next_recheck": clean_text(db_row.get("next_recheck")),
            "is_fp": safe_int(db_row.get("is_fp")),
            "notes": clean_text(db_row.get("notes")),
            "priority_reason": "; ".join(reasons),
            "combined_plot_link": "",
            "combined_plot_source": str(plot or ""),
            "level0_candidate_folder": candidate_folder,
            "lightcurve_path": clean_text(db_row.get("lightcurve_dir")),
            "source_list": "SPC_STAGE2",
        }
        selected.append(row)
    selected.sort(
        key=lambda row: (
            {"A_LEVEL5_NOW": 0, "B_STRONG_REVIEW": 1, "C_RECHECK_LATER": 2}.get(row["priority_group"], 9),
            -safe_float(row["priority_score"]),
            safe_float(row.get("distance_ly"), 999999.0),
            safe_int(row["TIC"]),
        )
    )
    for index, row in enumerate(selected, start=1):
        row["rank"] = index
    return selected, excluded_selected


def normalize_old_rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    for row in read_csv(path):
        normalized = {field: row.get(field, "") for field in FIELDS}
        normalized["TIC"] = safe_int(row.get("TIC"))
        normalized["rank"] = safe_int(row.get("rank"))
        normalized["priority_score"] = safe_float(row.get("priority_score"), 0.0)
        normalized["source_list"] = "GREEN_VIOLET_HZ"
        rows.append(normalized)
    return rows


def combine_rows(old_rows: list[dict[str, Any]], spc_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, int]:
    combined_by_tic: dict[int, dict[str, Any]] = {}
    duplicates = 0
    for row in old_rows:
        tic = safe_int(row.get("TIC"))
        if tic:
            combined_by_tic[tic] = dict(row)
    old_tics = set(combined_by_tic)
    for row in spc_rows:
        tic = safe_int(row.get("TIC"))
        if not tic:
            continue
        if tic in combined_by_tic:
            duplicates += 1
            merged = {**row, **{key: value for key, value in combined_by_tic[tic].items() if value not in ("", None)}}
            merged["source_list"] = "GREEN_VIOLET_HZ;SPC_STAGE2"
            merged["selection_reasons"] = row.get("selection_reasons", merged.get("selection_reasons", ""))
            merged["stage2_blocking_issues"] = row.get("stage2_blocking_issues", merged.get("stage2_blocking_issues", ""))
            combined_by_tic[tic] = merged
        else:
            combined_by_tic[tic] = dict(row)
    combined = list(combined_by_tic.values())
    combined.sort(
        key=lambda row: (
            {"A_LEVEL5_NOW": 0, "B_STRONG_REVIEW": 1, "C_RECHECK_LATER": 2}.get(row.get("priority_group"), 9),
            -safe_float(row.get("priority_score")),
            safe_float(row.get("distance_ly"), 999999.0),
            safe_int(row.get("TIC")),
        )
    )
    for index, row in enumerate(combined, start=1):
        row["rank"] = index
    return combined, duplicates, sum(1 for row in spc_rows if safe_int(row.get("TIC")) not in old_tics)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    spc_rows, excluded = build_spc_rows(args.evidence_threshold, args.dashboard_data)
    old_rows = normalize_old_rows(args.old_priority_csv)
    combined, duplicates, new_for_level5 = combine_rows(old_rows, spc_rows)
    spc_tics = {safe_int(row.get("TIC")) for row in spc_rows}
    combined_tics = {safe_int(row.get("TIC")) for row in combined}

    print(f"old_priority_count={len(old_rows)}")
    print(f"new_spc_stage2_count={len(spc_rows)}")
    print(f"duplicates={duplicates}")
    print(f"new_for_level5={new_for_level5}")
    print(f"combined_count={len(combined)}")
    print(f"excluded_selected_count={len(excluded)}")
    for tic in sorted(TARGET_TICS):
        print(
            f"TIC {tic}: in_new={'yes' if tic in spc_tics else 'no'} "
            f"in_combined={'yes' if tic in combined_tics else 'no'}"
        )

    if args.dry_run:
        print("dry_run=true; no files written")
        return 0

    out_root = args.out_root
    write_csv(out_root / SPC_PRIORITY_CSV.name, spc_rows)
    write_csv(out_root / COMBINED_PRIORITY_CSV.name, combined)
    print(f"spc_priority_csv={out_root / SPC_PRIORITY_CSV.name}")
    print(f"combined_priority_csv={out_root / COMBINED_PRIORITY_CSV.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
