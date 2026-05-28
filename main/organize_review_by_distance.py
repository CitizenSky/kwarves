#!/usr/bin/env python3
"""Organize all level0 candidates by distance range and investigation stage.

The original level0 candidate folders stay in place.  This script builds a
non-destructive stage index inside each light-year range folder using symlinks,
plus top-tier review lists for the next manual steps.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(os.environ.get("ASTRO_PROJECT_ROOT", "/Users/koni/astro_projects"))
DB_PATH = PROJECT_ROOT / "database" / "planet_hunter.db"
LEVEL0_ROOT = PROJECT_ROOT / "level0_lichtjahre_10ly_bis_500"
MANIFEST_PATH = LEVEL0_ROOT / "manifest_all_candidates_by_distance.csv"
EVIDENCE_RUN = PROJECT_ROOT / "evidence_vetting" / "20260526_195116_evidence_vetting"
ADVANCED_RUN = PROJECT_ROOT / "advanced_bayesian_vetting" / "20260526_195324_advanced_bayesian_vetting"
MANUAL_REVIEW_DIR = EVIDENCE_RUN / "manual_review_top20"
OUT_DIR = PROJECT_ROOT / "reports" / "top_tier_next_steps_20260526"

STAGE_INDEX_NAME = "_INVESTIGATION_STAGE_INDEX"
PURPLE_LABEL_INDEX = 5

STAGE_DIRS = {
    "00_TOP_TIER_VIOLETT_NEXT_STEPS": "Top-tier Kandidaten fuer die naechste manuelle/RV/FU-Runde.",
    "01_HZ_TOP_TIER_VIOLETT": "HZ-fokussierte Top-Kandidaten ausserhalb/innerhalb der Gesamt-Topliste.",
    "02_ADVANCED_BAYES_STRONG": "Advanced-Modellvergleich stark.",
    "03_ADVANCED_BAYES_WEAK": "Advanced-Modellvergleich schwach, aber nicht verworfen.",
    "04_ADVANCED_GP_SENSITIVE": "Signal reagiert stark auf GP-Detrending.",
    "05_ADVANCED_MODEL_NOT_FAVORED": "Transitmodell im Advanced-Vergleich nicht bevorzugt.",
    "06_EVIDENCE_SPC_RV_NEEDED": "Evidence-Vetting: RV-relevanter SPC.",
    "07_EVIDENCE_SPC_FOLLOWUP_READY": "Evidence-Vetting: photometrisch follow-up-ready.",
    "08_EVIDENCE_NEEDS_MORE_TESS_DATA": "Evidence-Vetting: mehr TESS-Daten noetig.",
    "09_EVIDENCE_ACTIVE_ARTIFACT_OR_EB_RISK": "Evidence-Vetting: Aktivitaet, Artefakt oder EB-Risiko.",
    "10_LEVEL0_HZ_PURPLE": "Level0: HZ violett markiert, noch ohne neue Evidence-Stufe.",
    "11_LEVEL0_SPC_GREEN": "Level0: SPC gruen, noch ohne neue Evidence-Stufe.",
    "12_LEVEL0_RED_FP": "Level0: False-Positive rot.",
    "13_LEVEL0_YELLOW_INFO": "Level0: Info/unklar gelb.",
    "14_LEVEL0_OTHER": "Restliche Kandidaten.",
}


@dataclass(frozen=True)
class CandidateRecord:
    tic: int
    distance_range: str
    distance_ly: float | None
    candidate_folder: Path
    stage: str
    stage_reason: str
    row: dict[str, Any]


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except Exception:
        return None
    return out if np.isfinite(out) else None


def safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def clean_flags(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    return [part.strip() for part in str(value).split(";") if part.strip()]


def text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and np.isnan(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def read_csv_dict(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_db_status() -> dict[int, dict[str, Any]]:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=60)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT TIC, status, spc_class, is_fp, hz_class, hz_status, distance_ly,
                   best_period, planet_radius_earth, transit_snr, transit_count,
                   visible_transits, clean_sector_count
              FROM candidates_v2
            """
        ).fetchall()
    finally:
        conn.close()
    return {int(row["TIC"]): dict(row) for row in rows}


def load_optional_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def build_lookup(df: pd.DataFrame, suffix: str = "") -> dict[int, dict[str, Any]]:
    if df.empty or "TIC" not in df.columns:
        return {}
    out: dict[int, dict[str, Any]] = {}
    for _, row in df.iterrows():
        tic = safe_int(row["TIC"])
        data = row.to_dict()
        if suffix:
            data = {f"{key}{suffix}" if key not in {"TIC", "candidate_id"} else key: value for key, value in data.items()}
        out[tic] = data
    return out


def link_candidate(target: Path, link: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    target = target.resolve()
    if link.is_symlink():
        if Path(os.readlink(link)) == target:
            return
        link.unlink()
    elif link.exists():
        if link.is_dir():
            shutil.rmtree(link)
        else:
            link.unlink()
    os.symlink(target, link)


def safe_name(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-+" else "_" for ch in text)


def finder_label_purple(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                f'tell application "Finder" to set label index of (POSIX file "{path}" as alias) to {PURPLE_LABEL_INDEX}',
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def first_transit(value: Any) -> tuple[str, str]:
    if not isinstance(value, str) or not value.strip():
        return "", ""
    try:
        rows = json.loads(value)
    except Exception:
        return "", ""
    if not rows:
        return "", ""
    row = rows[0]
    return str(row.get("btjd", "")), str(row.get("utc", ""))


def stage_for(row: dict[str, Any], top_tics: set[int], hz_top_tics: set[int]) -> tuple[str, str]:
    tic = safe_int(row.get("TIC"))
    evidence_class = str(row.get("evidence_class") or "")
    bayes_class = str(row.get("bayes_class") or "")
    manifest_mark = str(row.get("markierung") or "")
    manifest_hz = str(row.get("hz_markierung") or "")
    status = str(row.get("status") or row.get("db_status") or "")
    flags = set(clean_flags(row.get("combined_flags") or row.get("flags") or ""))

    if tic in top_tics:
        return "00_TOP_TIER_VIOLETT_NEXT_STEPS", "Top-tier next-step review"
    if tic in hz_top_tics:
        return "01_HZ_TOP_TIER_VIOLETT", "HZ top-tier next-step review"
    if bayes_class == "BAYES_STRONG":
        return "02_ADVANCED_BAYES_STRONG", "Advanced model comparison strong"
    if bayes_class == "BAYES_WEAK":
        return "03_ADVANCED_BAYES_WEAK", "Advanced model comparison weak"
    if bayes_class == "GP_SENSITIVE" or "GP_SIGNAL_CHANGED" in flags:
        return "04_ADVANCED_GP_SENSITIVE", "GP sensitivity needs manual check"
    if bayes_class == "MODEL_NOT_FAVORED":
        return "05_ADVANCED_MODEL_NOT_FAVORED", "Advanced model not favored"
    if evidence_class == "SPC_RV_NEEDED":
        return "06_EVIDENCE_SPC_RV_NEEDED", "Evidence says RV needed"
    if evidence_class == "SPC_FOLLOWUP_READY":
        return "07_EVIDENCE_SPC_FOLLOWUP_READY", "Evidence says follow-up ready"
    if evidence_class == "NEEDS_MORE_TESS_DATA":
        return "08_EVIDENCE_NEEDS_MORE_TESS_DATA", "Needs more TESS data"
    if evidence_class in {"SPC_ACTIVE_STAR", "SPC_ART", "EB_RISK", "REJECTED"}:
        return "09_EVIDENCE_ACTIVE_ARTIFACT_OR_EB_RISK", evidence_class
    if manifest_hz == "VIOLETT":
        return "10_LEVEL0_HZ_PURPLE", "Level0 HZ purple"
    if manifest_mark == "GRUEN" or status.startswith("SPC"):
        return "11_LEVEL0_SPC_GREEN", "Level0 SPC green"
    if manifest_mark == "ROT" or "FP" in status:
        return "12_LEVEL0_RED_FP", "Level0 red false positive"
    if manifest_mark == "GELB":
        return "13_LEVEL0_YELLOW_INFO", "Level0 yellow info"
    return "14_LEVEL0_OTHER", "Other/unsorted level0 candidate"


def review_action(row: pd.Series) -> str:
    flags = set(clean_flags(row.get("combined_flags")))
    bayes = str(row.get("bayes_class") or "")
    eclass = str(row.get("evidence_class") or "")
    hz = str(row.get("hz_class") or "")
    if bayes == "MODEL_NOT_FAVORED" or "EB_RISK" in flags:
        return "depriorisieren; nur Plausibilitaetscheck"
    if bayes == "GP_SENSITIVE" or "GP_SIGNAL_CHANGED" in flags:
        return "manuelle Lichtkurve + GP-Sensitivitaet pruefen"
    if eclass == "NEEDS_MORE_TESS_DATA":
        return "auf neue TESS-Daten/Recheck setzen"
    if hz in {"KONSERVATIVE_HZ", "OPT_HZ_INNEN", "OPT_HZ_AUSSEN"}:
        return "HZ Review, RV-Feasibility, Follow-up Fenster pruefen"
    if eclass == "SPC_RV_NEEDED":
        return "RV-Feasibility pruefen"
    if eclass == "SPC_FOLLOWUP_READY":
        return "photometrisches Follow-up planen"
    return "manuelle Review"


def write_stage_readme(path: Path) -> None:
    lines = ["# Investigation Stage Index", ""]
    lines.append("Dieser Ordner ist automatisch erzeugt und enthaelt Symlinks auf die Original-Level0-Kandidatenordner.")
    lines.append("Die Originaldaten bleiben unveraendert.")
    lines.append("")
    for name, desc in STAGE_DIRS.items():
        lines.append(f"- `{name}`: {desc}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = read_csv_dict(MANIFEST_PATH)
    db_rows = load_db_status()
    evidence = load_optional_csv(EVIDENCE_RUN / "evidence_vetting_results.csv")
    advanced = load_optional_csv(ADVANCED_RUN / "advanced_vetting_results.csv")
    top20 = load_optional_csv(MANUAL_REVIEW_DIR / "manual_review_top20.csv")
    hz_top20 = load_optional_csv(MANUAL_REVIEW_DIR / "manual_review_top20_hz.csv")
    ranked_all = load_optional_csv(MANUAL_REVIEW_DIR / "manual_review_ranked_all.csv")

    advanced = advanced.rename(columns={"flags": "advanced_flags", "evidence_score": "advanced_input_evidence_score"})
    evidence_lookup = build_lookup(evidence)
    advanced_lookup = build_lookup(advanced)
    ranked_lookup = build_lookup(ranked_all)
    top_tics = {safe_int(tic) for tic in top20.get("TIC", [])}
    hz_top_tics = {safe_int(tic) for tic in hz_top20.get("TIC", [])}
    purple_tics = top_tics | hz_top_tics

    range_folders = sorted({str(row["distance_range"]) for row in manifest if row.get("distance_range")})
    for range_name in range_folders:
        index_dir = LEVEL0_ROOT / range_name / STAGE_INDEX_NAME
        if index_dir.exists():
            shutil.rmtree(index_dir)
        for stage in STAGE_DIRS:
            (index_dir / stage).mkdir(parents=True, exist_ok=True)
        write_stage_readme(index_dir / "README.md")

    records: list[CandidateRecord] = []
    stage_counts: dict[str, int] = {stage: 0 for stage in STAGE_DIRS}
    purple_label_ok = 0
    purple_label_fail = 0

    for manifest_row in manifest:
        tic = safe_int(manifest_row.get("TIC"))
        db_row = db_rows.get(tic, {})
        row: dict[str, Any] = {**manifest_row, **db_row}
        row["TIC"] = tic
        row["db_status"] = db_row.get("status", "")
        row.update(evidence_lookup.get(tic, {}))
        row.update(advanced_lookup.get(tic, {}))
        row.update(ranked_lookup.get(tic, {}))
        stage, reason = stage_for(row, top_tics, hz_top_tics)
        stage_counts[stage] = stage_counts.get(stage, 0) + 1

        distance_range = str(manifest_row["distance_range"])
        distance_ly = safe_float(row.get("distance_ly"))
        candidate_folder = PROJECT_ROOT / str(manifest_row["candidate_folder"])
        label_bits = [
            f"TIC_{tic}",
            text_value(row.get("evidence_class")) or text_value(row.get("status")),
            text_value(row.get("bayes_class")),
            text_value(row.get("hz_class")) or text_value(row.get("hz_status")),
        ]
        if "manual_review_rank" in row and safe_int(row.get("manual_review_rank")):
            link_name = f"R{safe_int(row.get('manual_review_rank')):03d}_" + "__".join(safe_name(x) for x in label_bits if x)
        else:
            link_name = "__".join(safe_name(x) for x in label_bits if x)
        link_path = LEVEL0_ROOT / distance_range / STAGE_INDEX_NAME / stage / link_name
        if candidate_folder.exists():
            link_candidate(candidate_folder, link_path)
        if tic in purple_tics and candidate_folder.exists():
            if finder_label_purple(candidate_folder):
                purple_label_ok += 1
            else:
                purple_label_fail += 1
            finder_label_purple(link_path)

        records.append(
            CandidateRecord(
                tic=tic,
                distance_range=distance_range,
                distance_ly=distance_ly,
                candidate_folder=candidate_folder,
                stage=stage,
                stage_reason=reason,
                row=row,
            )
        )

    finder_label_purple(MANUAL_REVIEW_DIR)
    finder_label_purple(OUT_DIR)

    summary_rows: list[dict[str, Any]] = []
    for rec in records:
        row = rec.row
        next_btjd, next_utc = first_transit(row.get("next_transits_json"))
        summary_rows.append(
            {
                "TIC": rec.tic,
                "distance_range": rec.distance_range,
                "distance_ly": rec.distance_ly,
                "investigation_stage": rec.stage,
                "stage_reason": rec.stage_reason,
                "is_violett_top_tier": int(rec.tic in purple_tics),
                "manual_review_rank": row.get("manual_review_rank", ""),
                "review_score": row.get("review_score", ""),
                "evidence_class": row.get("evidence_class", ""),
                "bayes_class": row.get("bayes_class", ""),
                "delta_bic": row.get("delta_bic", ""),
                "evidence_score": row.get("evidence_score", ""),
                "scientific_value_score": row.get("scientific_value_score", ""),
                "followup_score": row.get("followup_score", ""),
                "hz_class": row.get("hz_class", row.get("hz_status", "")),
                "period": row.get("period", row.get("best_period", "")),
                "planet_radius_earth": row.get("planet_radius_earth", ""),
                "transit_snr": row.get("transit_snr", ""),
                "next_transit_btjd": next_btjd,
                "next_transit_utc": next_utc,
                "combined_flags": row.get("combined_flags", row.get("flags", "")),
                "candidate_folder": str(rec.candidate_folder),
            }
        )
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(OUT_DIR / "all_candidates_by_ly_and_stage.csv", index=False)

    top_next = ranked_all.head(30).copy() if not ranked_all.empty else pd.DataFrame()
    if not top_next.empty:
        top_next["next_action"] = top_next.apply(review_action, axis=1)
        top_next.to_csv(OUT_DIR / "top_tier_next_steps_all.csv", index=False)
    hz_next = ranked_all[ranked_all["hz_class"].isin(["KONSERVATIVE_HZ", "OPT_HZ_INNEN", "OPT_HZ_AUSSEN"])].head(30).copy() if not ranked_all.empty else pd.DataFrame()
    if not hz_next.empty:
        hz_next["next_action"] = hz_next.apply(review_action, axis=1)
        hz_next.to_csv(OUT_DIR / "top_tier_next_steps_hz.csv", index=False)

    stage_count_df = pd.DataFrame(
        [{"investigation_stage": stage, "count": count, "description": STAGE_DIRS.get(stage, "")} for stage, count in stage_counts.items()]
    )
    stage_count_df.to_csv(OUT_DIR / "stage_counts.csv", index=False)

    lines = [
        "# Top Tier Next Steps",
        "",
        "Violett markiert: Union aus Gesamt-Top-20 und HZ-Top-20.",
        "",
        "## Naechste Kandidaten",
        "",
        "| Rank | TIC | Review | Evidence | Bayes | HZ | Period d | Next action |",
        "|---:|---:|---:|---:|---|---|---:|---|",
    ]
    if not top_next.empty:
        for _, row in top_next.head(20).iterrows():
            lines.append(
                f"| {safe_int(row.get('manual_review_rank'))} | {safe_int(row.get('TIC'))} | "
                f"{float(row.get('review_score')):.1f} | {float(row.get('evidence_score')):.1f} | "
                f"{row.get('bayes_class', '')} | {row.get('hz_class', '')} | "
                f"{float(row.get('period')):.4f} | {row.get('next_action', '')} |"
            )
    lines.extend(
        [
            "",
            "## HZ-Fokus",
            "",
            "| Rank | TIC | Review | Evidence | Bayes | HZ | Period d | Next action |",
            "|---:|---:|---:|---:|---|---|---:|---|",
        ]
    )
    if not hz_next.empty:
        for _, row in hz_next.head(20).iterrows():
            lines.append(
                f"| {safe_int(row.get('manual_review_rank'))} | {safe_int(row.get('TIC'))} | "
                f"{float(row.get('review_score')):.1f} | {float(row.get('evidence_score')):.1f} | "
                f"{row.get('bayes_class', '')} | {row.get('hz_class', '')} | "
                f"{float(row.get('period')):.4f} | {row.get('next_action', '')} |"
            )
    lines.extend(
        [
            "",
            "## Stage-Ordner",
            "",
            f"- Level0 Root: `{LEVEL0_ROOT}`",
            f"- Pro Range: `{STAGE_INDEX_NAME}`",
            f"- Vollstaendige CSV: `{OUT_DIR / 'all_candidates_by_ly_and_stage.csv'}`",
            "",
            "## Stage Counts",
            "",
        ]
    )
    for stage, count in stage_counts.items():
        lines.append(f"- `{stage}`: {count}")
    lines.extend(
        [
            "",
            "## Finder-Farbe",
            "",
            f"- violette Finder-Labels gesetzt: {purple_label_ok}",
            f"- Finder-Label fehlgeschlagen: {purple_label_fail}",
        ]
    )
    (OUT_DIR / "TOP_TIER_NEXT_STEPS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"records={len(records)}")
    print(f"out_dir={OUT_DIR}")
    print(f"purple_label_ok={purple_label_ok}")
    print(f"purple_label_fail={purple_label_fail}")
    for stage, count in stage_counts.items():
        print(f"{stage}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
