#!/usr/bin/env python3
"""Focused SPC assessment for one TIC candidate."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

import level2_planet_check as l2
import level4_candidate_filter as l4
import ttv_analyse as ttv


PROJECT_ROOT = Path("/Users/koni/astro_projects")
DB_PATH = PROJECT_ROOT / "database" / "planet_hunter.db"
OUT_ROOT = PROJECT_ROOT / "level4_TTV_analyse" / "level4_08_spc_target_checks"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a focused SPC assessment for one TIC.")
    parser.add_argument("--tic", type=int, required=True)
    parser.add_argument("--online-gaia-simbad", action="store_true")
    parser.add_argument("--refresh-catalogs", action="store_true")
    parser.add_argument("--write-db-note", action="store_true")
    return parser.parse_args()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def load_db_snapshot(tic: int) -> dict[str, Any]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return {
            "candidates_v2": row_to_dict(
                conn.execute("SELECT * FROM candidates_v2 WHERE TIC=?", (tic,)).fetchone()
            ),
            "rohdaten": row_to_dict(
                conn.execute("SELECT * FROM rohdaten WHERE TIC=?", (tic,)).fetchone()
            ),
            "level0_distance_status": row_to_dict(
                conn.execute("SELECT * FROM level0_distance_status WHERE TIC=?", (tic,)).fetchone()
            ),
            "annotations": [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM candidate_annotations WHERE TIC=? ORDER BY annotation_type",
                    (tic,),
                )
            ],
        }
    finally:
        conn.close()


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        fields: list[str] = []
        for row in rows:
            for key in row:
                if key not in fields:
                    fields.append(key)
    else:
        fields = ["status"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def assess_level2(tic: int) -> dict[str, Any]:
    args = SimpleNamespace(tic=tic, source="all", limit=None)
    candidates = l2.load_candidates(args)
    if not candidates:
        return {"status": "not_found"}
    candidate = candidates[0]
    metrics = l2.measure_shape(candidate)
    label, score, reason = l2.classify(candidate, metrics)
    return {
        "status": "ok",
        "level2_planet_label": label,
        "level2_planet_score": score,
        "level2_reason": reason,
        "fp_flag_count": l2.fp_flag_count(candidate),
        "hz_status": candidate.hz_status,
        "period": candidate.period,
        "duration": candidate.duration,
        "depth": candidate.depth,
        "planet_radius_earth": candidate.planet_radius,
        "transit_snr": candidate.transit_snr,
        "transit_count": candidate.transit_count,
        "stellar_logg": candidate.stellar_logg,
        "teff": candidate.teff,
        "distance_ly": candidate.distance_ly,
        **metrics,
    }


def assess_level4(tic: int, out_dir: Path, online: bool, refresh: bool) -> dict[str, Any]:
    l4.OUT_ROOT = out_dir / "level4_filter"
    args = SimpleNamespace(
        tic=tic,
        status=None,
        from_folder=None,
        limit=None,
        include_fp=True,
        refresh_catalogs=refresh,
        online_gaia_simbad=online,
        apply_status=False,
        overwrite=True,
    )
    candidates = l4.load_candidates(args)
    if not candidates:
        return {"status": "not_found"}
    toi, ps = l4.load_external_catalogs(refresh)
    row = l4.analyze_candidate(candidates[0], toi, ps, args)
    row["status"] = "ok"
    return row


def assess_ttv(tic: int, out_dir: Path) -> dict[str, Any]:
    ttv.OUT_ROOT = out_dir / "ttv_oc"
    candidates = ttv.load_candidates(priority="ALL", tic=tic, limit=None)
    if not candidates:
        return {"status": "not_found"}
    row = ttv.analyze_candidate(candidates[0], min_points=10, overwrite=True)
    return row


def summarize_decision(level2: dict[str, Any], level4: dict[str, Any], ttv_row: dict[str, Any]) -> dict[str, Any]:
    level4_label = str(level4.get("level4_label", ""))
    level4_reasons = str(level4.get("level4_reasons", ""))
    level2_label = str(level2.get("level2_planet_label", ""))
    expected = int(level4.get("expected_transits") or 0)
    visible = int(level4.get("visible_transits") or 0)
    ttv_measured = ttv_row.get("n_measured", "")

    blockers: list[str] = []
    warnings: list[str] = []
    if level4_label != "SPC":
        blockers.append(f"level4={level4_label}:{level4_reasons}")
    if level2_label not in {"PLANET_PLAUSIBEL_A", "PLANET_MOEGLICH_B"}:
        blockers.append(f"level2={level2_label}")
    if expected and visible < max(2, min(3, int(level2.get("transit_count") or 0))):
        blockers.append(f"visible_transits={visible}/{expected}")
    if int(level2.get("transit_count") or 0) <= 2:
        warnings.append("only_two_pipeline_transits")
    if level4.get("nearby_star_flag"):
        warnings.append("nearby_star_flag")
    if level4.get("external_fp_flag"):
        blockers.append("external_fp_flag")
    if level4.get("simbad_fp_flag"):
        blockers.append("simbad_fp_flag")

    if blockers:
        recommendation = "RECHECK"
    elif warnings:
        recommendation = "SPC_CANDIDATE_HIGH_PRIORITY_RECHECK"
    else:
        recommendation = "SPC"

    return {
        "recommendation": recommendation,
        "blockers": blockers,
        "warnings": warnings,
        "level2_label": level2_label,
        "level2_score": level2.get("level2_planet_score"),
        "level4_label": level4_label,
        "level4_score": level4.get("level4_score"),
        "level4_reasons": level4_reasons,
        "expected_transits": expected,
        "visible_transits": visible,
        "ttv_measured": ttv_measured,
    }


def write_db_note(tic: int, summary: dict[str, Any], out_dir: Path) -> None:
    note_text = (
        f"SPC target check: recommendation={summary['recommendation']}; "
        f"level2={summary['level2_label']} score={summary['level2_score']}; "
        f"level4={summary['level4_label']} score={summary['level4_score']} "
        f"reasons={summary['level4_reasons']}; "
        f"visible_transits={summary['visible_transits']}/{summary['expected_transits']}; "
        f"warnings={';'.join(summary['warnings']) or 'none'}; "
        f"blockers={';'.join(summary['blockers']) or 'none'}; "
        f"artifacts={out_dir}"
    )
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS candidate_annotations (
                TIC INTEGER NOT NULL,
                annotation_type TEXT NOT NULL,
                annotation_text TEXT NOT NULL,
                source TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (TIC, annotation_type)
            )
            """
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO candidate_annotations
                (TIC, annotation_type, annotation_text, source, created_at)
            VALUES (?, 'SPC_TARGET_CHECK', ?, 'scripts/main/assess_spc_candidate.py', datetime('now'))
            """,
            (tic, note_text),
        )
        conn.execute(
            """
            UPDATE level0_distance_status
               SET review_class=?,
                   source='scripts/main/assess_spc_candidate.py',
                   updated_at=datetime('now')
             WHERE TIC=?
            """,
            (summary["recommendation"], tic),
        )
        conn.commit()
    finally:
        conn.close()


def main() -> int:
    args = parse_args()
    tic_dir = OUT_ROOT / f"TIC_{args.tic}"
    tic_dir.mkdir(parents=True, exist_ok=True)

    snapshot = load_db_snapshot(args.tic)
    level2 = assess_level2(args.tic)
    level4 = assess_level4(args.tic, tic_dir, args.online_gaia_simbad, args.refresh_catalogs)
    ttv_row = assess_ttv(args.tic, tic_dir)
    summary = summarize_decision(level2, level4, ttv_row)

    payload = {
        "TIC": args.tic,
        "summary": summary,
        "database_snapshot": snapshot,
        "level2": level2,
        "level4": level4,
        "ttv": ttv_row,
    }
    (tic_dir / f"TIC_{args.tic}_spc_assessment.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    write_csv(tic_dir / f"TIC_{args.tic}_spc_summary.csv", [summary])
    write_csv(tic_dir / f"TIC_{args.tic}_level2.csv", [level2])
    write_csv(tic_dir / f"TIC_{args.tic}_level4.csv", [level4])
    write_csv(tic_dir / f"TIC_{args.tic}_ttv.csv", [ttv_row])

    if args.write_db_note:
        write_db_note(args.tic, summary, tic_dir)

    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    print(f"Artifacts: {tic_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
