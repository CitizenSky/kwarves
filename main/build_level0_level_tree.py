#!/usr/bin/env python3
"""Build a tree-shaped level-system index inside the Level-0 distance folder.

The real candidate folders stay where they are.  This creates a clean
``LEVEL0`` entry tree made of symlinks:

    distance range -> level system -> status bucket -> candidate link

It also removes the older flat ``_INVESTIGATION_STAGE_INDEX`` folders generated
by ``organize_review_by_distance.py``.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(os.environ.get("ASTRO_PROJECT_ROOT", "/Users/koni/astro_projects"))
LEVEL0_ROOT = PROJECT_ROOT / "level0_lichtjahre_10ly_bis_500"
TREE_ROOT = LEVEL0_ROOT / "LEVEL0"
RANGE_TREE_NAME = "00_LEVEL_SYSTEM_TREE"
MANIFEST_PATH = LEVEL0_ROOT / "manifest_all_candidates_by_distance.csv"
DB_PATH = PROJECT_ROOT / "database" / "planet_hunter.db"

EVIDENCE_RUN = PROJECT_ROOT / "evidence_vetting" / "20260526_195116_evidence_vetting"
ADVANCED_RUN = PROJECT_ROOT / "advanced_bayesian_vetting" / "20260526_195324_advanced_bayesian_vetting"
MANUAL_REVIEW_DIR = EVIDENCE_RUN / "manual_review_top20"
LEVEL2_CSV = PROJECT_ROOT / "level2_planetencheck" / "level2_planetencheck_results.csv"
REPORT_DIR = TREE_ROOT / "99_REPORTS"

PURPLE_LABEL_INDEX = 5


LEVEL_BUCKETS = {
    "00_LEVEL0_ORIGINAL_BY_DISTANCE": [
        "00_ALL_LEVEL0_CANDIDATES",
        "01_LEVEL0_HZ_PURPLE",
        "02_LEVEL0_SPC_GREEN",
        "03_LEVEL0_RED_FP",
        "04_LEVEL0_OTHER",
    ],
    "01_LEVEL1_LIGHTCURVE_PNGS": [
        "00_PNG_COMPLETE_RAW_FOLDED_COMBINED",
        "01_HAS_COMBINED_PNG",
        "02_MISSING_RAW_OR_FOLDED",
        "03_MISSING_ALL_PNG",
    ],
    "02_LEVEL2_PLANET_CHECK": [
        "00_PLANET_PLAUSIBEL_A",
        "01_PLANET_MOEGLICH_B",
        "02_UNSICHER",
        "03_FP_ODER_SYSTEMATIK",
        "04_WAHRSCHEINLICH_KEIN_PLANET",
        "99_NOT_RUN",
    ],
    "03_LEVEL4_EVIDENCE_VETTING": [
        "00_TOP_TIER_VIOLETT",
        "01_HZ_TOP_TIER_VIOLETT",
        "02_SPC_RV_NEEDED",
        "03_SPC_FOLLOWUP_READY",
        "04_NEEDS_MORE_TESS_DATA",
        "05_ACTIVE_ARTIFACT_EB_RISK",
        "06_OTHER_EVIDENCE",
        "99_NOT_RUN",
    ],
    "04_LEVEL5_ADVANCED_SCIENCE": [
        "00_BAYES_STRONG",
        "01_BAYES_WEAK",
        "02_GP_SENSITIVE",
        "03_MODEL_NOT_FAVORED",
        "99_NOT_RUN",
    ],
    "05_NEXT_ACTION": [
        "00_CONTINUE_NOW_VIOLETT",
        "01_RV_FEASIBILITY",
        "02_PHOTOMETRIC_FOLLOWUP",
        "03_MORE_TESS_RECHECK",
        "04_MANUAL_GP_CHECK",
        "05_DEPRIORITIZE",
        "99_HOLD",
    ],
    "06_UNTERSUCHUNGSSTAND": [
        "00_NUR_LEVEL0_SORTIERT",
        "01_LICHTKURVE_COMBINED_READY",
        "02_LEVEL2_PLANETENCHECK_DONE",
        "03_LEVEL4_EVIDENCE_DONE",
        "04_LEVEL5_ADVANCED_DONE",
        "05_TOP_TIER_MARKIERT",
        "06_WARTET_AUF_MEHR_TESS",
        "07_STOPP_FP_SYSTEMATIK",
    ],
    "07_WEITER_UNTERSUCHEN": [
        "00_JETZT_TOP_TIER",
        "01_RV_PRUEFEN",
        "02_PHOTOMETRIE_FOLLOWUP",
        "03_GP_MANUELL_PRUEFEN",
        "04_MEHR_TESS_ABWARTEN",
        "05_HALTEPOSITION",
        "06_STOPP_DEPRIORISIERT",
    ],
}

GLOBAL_BUCKETS = {
    "00_VIOLETT_TOP_TIER_ALL": "Union aus Gesamt-Top-20 und HZ-Top-20.",
    "01_HZ_VIOLETT_TOP_TIER": "HZ-fokussierte Top-Tier Kandidaten.",
    "02_CONTINUE_NOW": "Naechste manuelle/RV/FU Kandidaten.",
    "03_MORE_TESS": "Kandidaten fuer spaeteren TESS-Recheck.",
    "04_GP_SENSITIVE_REVIEW": "GP-sensitive Kandidaten fuer manuelle Kontrolle.",
    "05_MODEL_NOT_FAVORED": "Advanced-Modell nicht bevorzugt.",
}

PIPELINE_LEVEL_DIRS = [
    ("00_META", PROJECT_ROOT / "meta", "Projekt-Konfiguration und Metadaten."),
    ("01_LEVEL1_ROHKANDIDATEN", PROJECT_ROOT / "level1_rohkandidaten", "Rohkandidaten, Referenzplots, manuelle Sichtung."),
    ("02_LEVEL2_PLANETENCHECK", PROJECT_ROOT / "level2_planetencheck", "Level-2 Plausibilitaets- und FP-Klassen."),
    ("03_LEVEL3_EXTERNE_KATALOGPRUEFUNG", PROJECT_ROOT / "level3_externe_katalogpruefung", "Externe Katalog-/TOI-/Known-Planet-Pruefung."),
    ("04_LEVEL3_NEUE_PLANETENKANDIDATEN", PROJECT_ROOT / "level3_neue_planetenkandidaten", "Neue Kandidatenklassen und HZ/SPC-Sammlungen."),
    ("05_LEVEL4_TTV_ANALYSE", PROJECT_ROOT / "level4_TTV_analyse", "TTV, O-C, Ziel- und Recheck-Analysen."),
    ("06_LEVEL5_DETAILVALIDIERUNG", PROJECT_ROOT / "level5_detailvalidierung", "Odd/even, Secondary, Nachbarstern und Detailvalidierung."),
    ("07_LEVEL6_KANDIDATEN_DOSSIER", PROJECT_ROOT / "level6_kandidaten_dossier", "Dossiers, Follow-up-Prioritaet und Exportpakete."),
]


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return default
        return int(float(value))
    except Exception:
        return default


def safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        out = float(value)
    except Exception:
        return None
    return out if np.isfinite(out) else None


def text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and np.isnan(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def clean_flags(value: Any) -> set[str]:
    text = text_value(value)
    return {part.strip() for part in text.split(";") if part.strip()}


def is_project_stop_candidate(row: dict[str, Any]) -> bool:
    if text_value(row.get("markierung")) == "ROT":
        return True
    if safe_int(row.get("is_fp")):
        return True
    status_text = " ".join(
        text_value(row.get(key))
        for key in ("db_status", "status", "spc_class", "evidence_class", "bayes_class")
    ).upper()
    stop_tokens = ("FP", "REJECT", "KNOWN_PLANET_ALIAS", "KNOWN_ALIAS", "SPC_ART", "EB_RISK")
    return any(token in status_text for token in stop_tokens)


def safe_name(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-+" else "_" for ch in text)


def read_manifest() -> list[dict[str, str]]:
    with MANIFEST_PATH.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_distance_ranges(manifest: list[dict[str, str]]) -> list[str]:
    from_manifest = {row["distance_range"] for row in manifest if row.get("distance_range")}
    from_folders = {path.name for path in LEVEL0_ROOT.glob("*_ly") if path.is_dir()}
    return sorted(from_manifest | from_folders)


def load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def lookup(df: pd.DataFrame) -> dict[int, dict[str, Any]]:
    if df.empty or "TIC" not in df.columns:
        return {}
    out: dict[int, dict[str, Any]] = {}
    for _, row in df.iterrows():
        tic = safe_int(row.get("TIC"))
        if tic:
            out[tic] = row.to_dict()
    return out


def load_db_lookup() -> dict[int, dict[str, Any]]:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=60)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT TIC, status AS db_status, spc_class, is_fp, hz_class, hz_status,
                   distance_ly, best_period, planet_radius_earth, transit_snr,
                   transit_count, visible_transits, clean_sector_count
              FROM candidates_v2
            """
        ).fetchall()
    finally:
        conn.close()
    return {int(row["TIC"]): dict(row) for row in rows}


def load_manual_downgrades() -> set[int]:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=60)
    try:
        rows = conn.execute(
            """
            SELECT TIC
              FROM candidate_annotations
             WHERE annotation_type IN ('MANUAL_DOWNGRADE', 'MANUAL_REJECT', 'MANUAL_HOLD_RECHECK')
            """
        ).fetchall()
    except sqlite3.Error:
        rows = []
    finally:
        conn.close()
    return {int(row[0]) for row in rows}


def load_latest_evidence_lookup() -> dict[int, dict[str, Any]]:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=60)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT ev.*
              FROM evidence_vetting_results ev
              JOIN (
                    SELECT TIC, MAX(created_at) AS latest_created_at
                      FROM evidence_vetting_results
                     GROUP BY TIC
                   ) latest
                ON latest.TIC = ev.TIC
               AND latest.latest_created_at = ev.created_at
            """
        ).fetchall()
    except sqlite3.Error:
        rows = []
    finally:
        conn.close()
    return {int(row["TIC"]): dict(row) for row in rows}


def link_to(target: Path, link: Path) -> None:
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


def remove_path(path: Path) -> bool:
    if not path.exists() and not path.is_symlink():
        return False
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)
    return True


def clear_directory_contents(path: Path) -> int:
    if not path.exists() or not path.is_dir():
        return 0
    removed = 0
    for child in path.iterdir():
        remove_path(child)
        removed += 1
    return removed


def remove_symlinks(path: Path) -> int:
    if not path.exists() or not path.is_dir():
        return 0
    removed = 0
    for child in path.iterdir():
        if child.is_symlink():
            child.unlink()
            removed += 1
    return removed


def remove_old_generated_indexes() -> tuple[int, int]:
    removed_flat_indexes = 0
    removed_generated_trees = 0
    for path in LEVEL0_ROOT.glob("*_ly/_INVESTIGATION_STAGE_INDEX"):
        if path.is_dir():
            shutil.rmtree(path)
            removed_flat_indexes += 1
    for path in (LEVEL0_ROOT / "_LEVEL_SYSTEM_TREE",):
        if remove_path(path):
            removed_generated_trees += 1
    return removed_flat_indexes, removed_generated_trees


def range_tree_root(distance_range: str) -> Path:
    return LEVEL0_ROOT / distance_range / RANGE_TREE_NAME


def mirror_range_link(distance_range: str) -> Path:
    return TREE_ROOT / "02_BY_LY_RANGE" / distance_range


def make_tree_dirs(distance_ranges: list[str]) -> None:
    for bucket in GLOBAL_BUCKETS:
        bucket_dir = TREE_ROOT / "01_NEXT_STEPS_GLOBAL" / bucket
        bucket_dir.mkdir(parents=True, exist_ok=True)
        clear_directory_contents(bucket_dir)
    original_root = TREE_ROOT / "00_ORIGINAL_BY_LY_RANGE"
    original_root.mkdir(parents=True, exist_ok=True)
    remove_symlinks(original_root)
    mirror_root = TREE_ROOT / "02_BY_LY_RANGE"
    mirror_root.mkdir(parents=True, exist_ok=True)
    for distance_range in distance_ranges:
        original_range = LEVEL0_ROOT / distance_range
        if original_range.exists():
            link_to(original_range, original_root / distance_range)
        range_root = range_tree_root(distance_range)
        range_root.mkdir(parents=True, exist_ok=True)
        mirror = mirror_range_link(distance_range)
        if mirror.exists() or mirror.is_symlink():
            remove_path(mirror)
        link_to(range_root, mirror)
        for level_name, buckets in LEVEL_BUCKETS.items():
            for bucket in buckets:
                bucket_dir = range_root / level_name / bucket
                bucket_dir.mkdir(parents=True, exist_ok=True)
                clear_directory_contents(bucket_dir)
        for generated_file in ("00_RANGE_STATUS.csv", "00_RANGE_STATUS.md"):
            remove_path(range_root / generated_file)
    pipeline_root = TREE_ROOT / "03_PIPELINE_LEVELS"
    pipeline_root.mkdir(parents=True, exist_ok=True)
    remove_symlinks(pipeline_root)
    for link_name_part, source, _description in PIPELINE_LEVEL_DIRS:
        if source.exists():
            link_to(source, pipeline_root / link_name_part)


def png_status_for(candidate_folder: Path) -> dict[str, int]:
    png_dir = candidate_folder / "lichtkurven_png"
    if not png_dir.exists():
        return {
            "has_any_png": 0,
            "has_raw_png": 0,
            "has_folded_png": 0,
            "has_combined_png": 0,
        }
    raw = int((png_dir / "LICHTKURVE_RAW.png").exists())
    folded = int((png_dir / "LICHTKURVE_FOLDED.png").exists())
    combined = int((png_dir / "LICHTKURVE_COMBINED.png").exists())
    return {
        "has_any_png": int(any(png_dir.glob("*.png")) or raw or folded or combined),
        "has_raw_png": raw,
        "has_folded_png": folded,
        "has_combined_png": combined,
    }


def link_name(row: dict[str, Any]) -> str:
    tic = safe_int(row.get("TIC"))
    rank = safe_int(row.get("manual_review_rank"))
    bits = [
        f"TIC_{tic}",
        text_value(row.get("evidence_class")) or text_value(row.get("db_status")) or text_value(row.get("status")),
        text_value(row.get("bayes_class")),
        text_value(row.get("hz_class")) or text_value(row.get("hz_status")),
    ]
    prefix = f"R{rank:03d}_" if rank else ""
    return prefix + "__".join(safe_name(bit) for bit in bits if bit)


def level0_bucket(row: dict[str, Any]) -> str:
    markierung = text_value(row.get("markierung"))
    db_status = text_value(row.get("db_status"))
    if text_value(row.get("hz_markierung")) == "VIOLETT":
        return "01_LEVEL0_HZ_PURPLE"
    if is_project_stop_candidate(row) or "FP" in db_status:
        return "03_LEVEL0_RED_FP"
    if markierung == "GELB":
        return "04_LEVEL0_OTHER"
    if markierung == "GRUEN" or (not markierung and db_status.startswith("SPC")):
        return "02_LEVEL0_SPC_GREEN"
    return "04_LEVEL0_OTHER"


def png_bucket(row: dict[str, Any]) -> str:
    has_raw = safe_int(row.get("has_raw_png"))
    has_folded = safe_int(row.get("has_folded_png"))
    has_combined = safe_int(row.get("has_combined_png"))
    has_any = safe_int(row.get("has_any_png"))
    if has_raw and has_folded and has_combined:
        return "00_PNG_COMPLETE_RAW_FOLDED_COMBINED"
    if has_combined:
        return "01_HAS_COMBINED_PNG"
    if has_any:
        return "02_MISSING_RAW_OR_FOLDED"
    return "03_MISSING_ALL_PNG"


def level2_bucket(row: dict[str, Any]) -> str:
    label = text_value(row.get("level2_planet_label"))
    mapping = {
        "PLANET_PLAUSIBEL_A": "00_PLANET_PLAUSIBEL_A",
        "PLANET_MOEGLICH_B": "01_PLANET_MOEGLICH_B",
        "UNSICHER": "02_UNSICHER",
        "FP_ODER_SYSTEMATIK": "03_FP_ODER_SYSTEMATIK",
        "WAHRSCHEINLICH_KEIN_PLANET": "04_WAHRSCHEINLICH_KEIN_PLANET",
    }
    return mapping.get(label, "99_NOT_RUN")


def evidence_bucket(row: dict[str, Any], top_tics: set[int], hz_top_tics: set[int]) -> str:
    tic = safe_int(row.get("TIC"))
    evidence_class = text_value(row.get("evidence_class"))
    if tic in top_tics:
        return "00_TOP_TIER_VIOLETT"
    if tic in hz_top_tics:
        return "01_HZ_TOP_TIER_VIOLETT"
    mapping = {
        "SPC_RV_NEEDED": "02_SPC_RV_NEEDED",
        "SPC_FOLLOWUP_READY": "03_SPC_FOLLOWUP_READY",
        "NEEDS_MORE_TESS_DATA": "04_NEEDS_MORE_TESS_DATA",
        "SPC_ACTIVE_STAR": "05_ACTIVE_ARTIFACT_EB_RISK",
        "SPC_ART": "05_ACTIVE_ARTIFACT_EB_RISK",
        "EB_RISK": "05_ACTIVE_ARTIFACT_EB_RISK",
        "REJECTED": "05_ACTIVE_ARTIFACT_EB_RISK",
    }
    if evidence_class in mapping:
        return mapping[evidence_class]
    return "06_OTHER_EVIDENCE" if evidence_class else "99_NOT_RUN"


def advanced_bucket(row: dict[str, Any]) -> str:
    mapping = {
        "BAYES_STRONG": "00_BAYES_STRONG",
        "BAYES_WEAK": "01_BAYES_WEAK",
        "GP_SENSITIVE": "02_GP_SENSITIVE",
        "MODEL_NOT_FAVORED": "03_MODEL_NOT_FAVORED",
    }
    return mapping.get(text_value(row.get("bayes_class")), "99_NOT_RUN")


def action_bucket(row: dict[str, Any], top_tics: set[int], hz_top_tics: set[int]) -> str:
    tic = safe_int(row.get("TIC"))
    flags = clean_flags(row.get("combined_flags") or row.get("flags") or "")
    bayes_class = text_value(row.get("bayes_class"))
    evidence_class = text_value(row.get("evidence_class"))
    if (
        is_project_stop_candidate(row)
        or bayes_class == "MODEL_NOT_FAVORED"
        or evidence_class in {"SPC_ART", "EB_RISK", "REJECTED"}
        or {"EB_RISK", "PIPELINE_FP", "PIPELINE_ARTIFACT_RISK"} & flags
    ):
        return "05_DEPRIORITIZE"
    if bayes_class == "GP_SENSITIVE" or "GP_SIGNAL_CHANGED" in flags:
        return "04_MANUAL_GP_CHECK"
    if evidence_class == "NEEDS_MORE_TESS_DATA":
        return "03_MORE_TESS_RECHECK"
    if tic in top_tics or tic in hz_top_tics:
        return "00_CONTINUE_NOW_VIOLETT"
    if evidence_class == "SPC_RV_NEEDED":
        return "01_RV_FEASIBILITY"
    if evidence_class == "SPC_FOLLOWUP_READY":
        return "02_PHOTOMETRIC_FOLLOWUP"
    return "99_HOLD"


def investigation_status_bucket(row: dict[str, Any], top_tics: set[int], hz_top_tics: set[int]) -> str:
    tic = safe_int(row.get("TIC"))
    flags = clean_flags(row.get("combined_flags") or row.get("flags") or "")
    evidence_class = text_value(row.get("evidence_class"))
    bayes_class = text_value(row.get("bayes_class"))
    level2_label = text_value(row.get("level2_planet_label"))
    if (
        is_project_stop_candidate(row)
        or evidence_class in {"SPC_ART", "EB_RISK", "REJECTED"}
        or bayes_class == "MODEL_NOT_FAVORED"
        or {"EB_RISK", "PIPELINE_FP", "PIPELINE_ARTIFACT_RISK"} & flags
    ):
        return "07_STOPP_FP_SYSTEMATIK"
    if evidence_class == "NEEDS_MORE_TESS_DATA":
        return "06_WARTET_AUF_MEHR_TESS"
    if tic in top_tics or tic in hz_top_tics:
        return "05_TOP_TIER_MARKIERT"
    if bayes_class:
        return "04_LEVEL5_ADVANCED_DONE"
    if evidence_class:
        return "03_LEVEL4_EVIDENCE_DONE"
    if level2_label:
        return "02_LEVEL2_PLANETENCHECK_DONE"
    if safe_int(row.get("has_combined_png")):
        return "01_LICHTKURVE_COMBINED_READY"
    return "00_NUR_LEVEL0_SORTIERT"


def weiter_untersuchen_bucket(row: dict[str, Any], top_tics: set[int], hz_top_tics: set[int]) -> str:
    mapping = {
        "00_CONTINUE_NOW_VIOLETT": "00_JETZT_TOP_TIER",
        "01_RV_FEASIBILITY": "01_RV_PRUEFEN",
        "02_PHOTOMETRIC_FOLLOWUP": "02_PHOTOMETRIE_FOLLOWUP",
        "04_MANUAL_GP_CHECK": "03_GP_MANUELL_PRUEFEN",
        "03_MORE_TESS_RECHECK": "04_MEHR_TESS_ABWARTEN",
        "05_DEPRIORITIZE": "06_STOPP_DEPRIORISIERT",
        "99_HOLD": "05_HALTEPOSITION",
    }
    return mapping.get(action_bucket(row, top_tics, hz_top_tics), "05_HALTEPOSITION")


def global_action_bucket(row: dict[str, Any], top_tics: set[int], hz_top_tics: set[int]) -> str | None:
    tic = safe_int(row.get("TIC"))
    action = action_bucket(row, top_tics, hz_top_tics)
    bayes = text_value(row.get("bayes_class"))
    if tic in top_tics:
        return "00_VIOLETT_TOP_TIER_ALL"
    if tic in hz_top_tics:
        return "01_HZ_VIOLETT_TOP_TIER"
    if action in {"00_CONTINUE_NOW_VIOLETT", "01_RV_FEASIBILITY", "02_PHOTOMETRIC_FOLLOWUP"}:
        return "02_CONTINUE_NOW"
    if action == "03_MORE_TESS_RECHECK":
        return "03_MORE_TESS"
    if bayes == "GP_SENSITIVE" or "GP_SIGNAL_CHANGED" in clean_flags(row.get("combined_flags") or row.get("flags") or ""):
        return "04_GP_SENSITIVE_REVIEW"
    if bayes == "MODEL_NOT_FAVORED":
        return "05_MODEL_NOT_FAVORED"
    return None


def first_transit(value: Any) -> tuple[str, str]:
    text = text_value(value)
    if not text:
        return "", ""
    try:
        rows = json.loads(text)
    except Exception:
        return "", ""
    if not rows:
        return "", ""
    row = rows[0]
    return str(row.get("btjd", "")), str(row.get("utc", ""))


def write_range_status_reports(summary: pd.DataFrame, distance_ranges: list[str]) -> None:
    if summary.empty:
        groups: dict[str, pd.DataFrame] = {}
    else:
        groups = {str(name): group.copy() for name, group in summary.groupby("distance_range", sort=True)}
    for distance_range in distance_ranges:
        range_root = range_tree_root(str(distance_range))
        group = groups.get(str(distance_range), summary.iloc[0:0].copy())
        group.to_csv(range_root / "00_RANGE_STATUS.csv", index=False)

        current_counts = group["investigation_status_bucket"].value_counts().sort_index()
        next_counts = group["weiter_untersuchen_bucket"].value_counts().sort_index()
        top = group[
            group["weiter_untersuchen_bucket"].isin(
                [
                    "00_JETZT_TOP_TIER",
                    "01_RV_PRUEFEN",
                    "02_PHOTOMETRIE_FOLLOWUP",
                    "03_GP_MANUELL_PRUEFEN",
                    "04_MEHR_TESS_ABWARTEN",
                ]
            )
        ].sort_values(
            by=["is_violett_top_tier", "review_score", "evidence_score"],
            ascending=[False, False, False],
            na_position="last",
        )

        lines = [
            f"# Untersuchungsstand {distance_range}",
            "",
            f"Kandidaten in dieser LY-Range: {len(group)}",
            "",
            "## Aktueller Stand",
            "",
        ]
        if len(current_counts):
            for bucket, count in current_counts.items():
                lines.append(f"- `{bucket}`: {int(count)}")
        else:
            lines.append("- keine Kandidaten in dieser Range")
        lines.extend(["", "## Naechste Untersuchung", ""])
        if len(next_counts):
            for bucket, count in next_counts.items():
                lines.append(f"- `{bucket}`: {int(count)}")
        else:
            lines.append("- keine Kandidaten in dieser Range")
        lines.extend(
            [
                "",
                "## Kandidaten fuer weitere Untersuchung",
                "",
                "| TIC | Review | Evidence | Bayes | HZ | Period d | Naechster Schritt |",
                "|---:|---:|---|---|---|---:|---|",
            ]
        )
        for _, row in top.head(25).iterrows():
            period = safe_float(row.get("period")) or 0.0
            review = safe_float(row.get("review_score")) or 0.0
            lines.append(
                f"| {safe_int(row.get('TIC'))} | {review:.1f} | "
                f"{text_value(row.get('evidence_class'))} | {text_value(row.get('bayes_class'))} | "
                f"{text_value(row.get('hz_class'))} | {period:.4f} | "
                f"{text_value(row.get('weiter_untersuchen_bucket'))} |"
            )
        lines.extend(
            [
                "",
                "## Dateien",
                "",
                "- `00_RANGE_STATUS.csv`: komplette Kandidatenliste dieser LY-Range mit Statusspalten.",
            ]
        )
        (range_root / "00_RANGE_STATUS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_readme(
    distance_ranges: list[str],
    removed_old: int,
    removed_generated_trees: int,
    purple_ok: int,
    purple_fail: int,
) -> None:
    lines = [
        "# Level0 Level-System Tree",
        "",
        "Dieser Baum ist automatisch erzeugt. Die echten Kandidatenordner werden nicht verschoben;",
        "alle Eintraege hier sind Symlinks auf die Originalordner in den Lichtjahre-Ranges.",
        "",
        f"Alte flache `_INVESTIGATION_STAGE_INDEX` Ordner entfernt: {removed_old}",
        f"Alte generierte Level-Baeume entfernt: {removed_generated_trees}",
        f"Violette Finder-Labels gesetzt: {purple_ok}",
        f"Violette Finder-Labels fehlgeschlagen: {purple_fail}",
        "",
        "## Struktur",
        "",
        "- `00_ORIGINAL_BY_LY_RANGE`: Links auf die echten LY-Range-Ordner.",
        "- `01_NEXT_STEPS_GLOBAL`: globale Top-/Next-Step-Listen ueber alle Entfernungen.",
        "- `02_BY_LY_RANGE`: Links auf den Level-System-Baum in jedem echten LY-Ordner.",
        "- `03_PIPELINE_LEVELS`: Einstieg in meta und Level 1 bis Level 6.",
        "- `99_REPORTS`: Manifest, Bucket-Zaehler und Top-Tier-Listen.",
        "",
        f"Der eigentliche Level-System-Baum beginnt pro Range unter `{RANGE_TREE_NAME}` im jeweiligen LY-Ordner.",
        "",
        "Innerhalb jedes Range-Baums:",
    ]
    for level, buckets in LEVEL_BUCKETS.items():
        lines.append(f"- `{level}`")
        for bucket in buckets:
            lines.append(f"  - `{bucket}`")
    lines.extend(
        [
            "",
            "Jeder LY-Range-Baum enthaelt zusaetzlich:",
            "",
            "- `00_RANGE_STATUS.md`: kurze Zaehler und Kandidaten fuer weitere Untersuchung.",
            "- `00_RANGE_STATUS.csv`: komplette Status-Tabelle dieser Range.",
        ]
    )
    lines.extend(
        [
            "",
            "## Pipeline-Level",
            "",
        ]
    )
    for link_name_part, source, description in PIPELINE_LEVEL_DIRS:
        lines.append(f"- `{link_name_part}` -> `{source}`: {description}")
    lines.extend(
        [
            "",
            "## Distanzbereiche",
            "",
            ", ".join(distance_ranges),
        ]
    )
    (TREE_ROOT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    manifest = read_manifest()
    distance_ranges = read_distance_ranges(manifest)
    removed_old, removed_generated_trees = remove_old_generated_indexes()
    make_tree_dirs(distance_ranges)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    db = load_db_lookup()
    manual_downgrades = load_manual_downgrades()
    evidence = lookup(load_csv(EVIDENCE_RUN / "evidence_vetting_results.csv"))
    latest_evidence = load_latest_evidence_lookup()
    for tic, latest_row in latest_evidence.items():
        evidence[tic] = {**evidence.get(tic, {}), **latest_row}
    advanced_df = load_csv(ADVANCED_RUN / "advanced_vetting_results.csv")
    if not advanced_df.empty:
        advanced_df = advanced_df.rename(columns={"flags": "advanced_flags", "evidence_score": "advanced_input_evidence_score"})
    advanced = lookup(advanced_df)
    level2 = lookup(load_csv(LEVEL2_CSV))
    ranked = lookup(load_csv(MANUAL_REVIEW_DIR / "manual_review_ranked_all.csv"))
    top20_df = load_csv(MANUAL_REVIEW_DIR / "manual_review_top20.csv")
    hz_top20_df = load_csv(MANUAL_REVIEW_DIR / "manual_review_top20_hz.csv")
    top_tics = {safe_int(tic) for tic in top20_df.get("TIC", [])}
    hz_top_tics = {safe_int(tic) for tic in hz_top20_df.get("TIC", [])}
    top_tics -= manual_downgrades
    hz_top_tics -= manual_downgrades
    purple_tics = top_tics | hz_top_tics

    summary_rows: list[dict[str, Any]] = []
    bucket_counts: dict[str, int] = {}
    purple_ok = 0
    purple_fail = 0

    for manifest_row in manifest:
        tic = safe_int(manifest_row.get("TIC"))
        row: dict[str, Any] = {**manifest_row}
        row.update(db.get(tic, {}))
        row.update(level2.get(tic, {}))
        row.update(ranked.get(tic, {}))
        row.update(evidence.get(tic, {}))
        row.update(advanced.get(tic, {}))
        merged_flags = clean_flags(row.get("combined_flags") or "")
        merged_flags.update(clean_flags(row.get("flags") or ""))
        if merged_flags:
            row["combined_flags"] = ";".join(sorted(merged_flags))
        row["TIC"] = tic
        row["manual_downgrade"] = int(tic in manual_downgrades)
        if tic in manual_downgrades:
            flags = clean_flags(row.get("combined_flags") or "")
            flags.add("MANUAL_DOWNGRADED")
            if is_project_stop_candidate(row):
                flags.add("PIPELINE_FP")
                flags.add("KNOWN_PLANET_ALIAS")
                if text_value(row.get("evidence_class")) in {"", "SPC_RV_NEEDED", "SPC_FOLLOWUP_READY", "SPC_STRONG"}:
                    row["evidence_class"] = "REJECTED"
            else:
                flags.add("NEEDS_MORE_TESS_DATA")
                if text_value(row.get("evidence_class")) in {"", "SPC_RV_NEEDED", "SPC_FOLLOWUP_READY", "SPC_STRONG"}:
                    row["evidence_class"] = "NEEDS_MORE_TESS_DATA"
            row["combined_flags"] = ";".join(sorted(flags))

        candidate_folder = PROJECT_ROOT / manifest_row["candidate_folder"]
        if not candidate_folder.exists():
            continue
        row.update(png_status_for(candidate_folder))
        name = link_name(row)
        range_root = range_tree_root(manifest_row["distance_range"])
        buckets = {
            "level0_bucket": ("00_LEVEL0_ORIGINAL_BY_DISTANCE", "00_ALL_LEVEL0_CANDIDATES"),
            "level0_status_bucket": ("00_LEVEL0_ORIGINAL_BY_DISTANCE", level0_bucket(row)),
            "level1_png_bucket": ("01_LEVEL1_LIGHTCURVE_PNGS", png_bucket(row)),
            "level2_bucket": ("02_LEVEL2_PLANET_CHECK", level2_bucket(row)),
            "level4_evidence_bucket": ("03_LEVEL4_EVIDENCE_VETTING", evidence_bucket(row, top_tics, hz_top_tics)),
            "level5_advanced_bucket": ("04_LEVEL5_ADVANCED_SCIENCE", advanced_bucket(row)),
            "next_action_bucket": ("05_NEXT_ACTION", action_bucket(row, top_tics, hz_top_tics)),
            "investigation_status_bucket": (
                "06_UNTERSUCHUNGSSTAND",
                investigation_status_bucket(row, top_tics, hz_top_tics),
            ),
            "weiter_untersuchen_bucket": (
                "07_WEITER_UNTERSUCHEN",
                weiter_untersuchen_bucket(row, top_tics, hz_top_tics),
            ),
        }
        for key, (level, bucket) in buckets.items():
            link_to(candidate_folder, range_root / level / bucket / name)
            bucket_counts[f"{level}/{bucket}"] = bucket_counts.get(f"{level}/{bucket}", 0) + 1
        global_bucket = global_action_bucket(row, top_tics, hz_top_tics)
        if global_bucket:
            link_to(candidate_folder, TREE_ROOT / "01_NEXT_STEPS_GLOBAL" / global_bucket / name)
            bucket_counts[f"01_NEXT_STEPS_GLOBAL/{global_bucket}"] = bucket_counts.get(f"01_NEXT_STEPS_GLOBAL/{global_bucket}", 0) + 1

        if tic in purple_tics:
            if finder_label_purple(candidate_folder):
                purple_ok += 1
            else:
                purple_fail += 1

        next_btjd, next_utc = first_transit(row.get("next_transits_json"))
        summary_rows.append(
            {
                "TIC": tic,
                "distance_range": manifest_row["distance_range"],
                "distance_ly": safe_float(row.get("distance_ly")),
                "candidate_folder": str(candidate_folder),
                "is_violett_top_tier": int(tic in purple_tics),
                "manual_downgrade": int(tic in manual_downgrades),
                "manual_review_rank": row.get("manual_review_rank", ""),
                "review_score": row.get("review_score", ""),
                "level0_status_bucket": buckets["level0_status_bucket"][1],
                "level1_png_bucket": buckets["level1_png_bucket"][1],
                "level2_bucket": buckets["level2_bucket"][1],
                "level4_evidence_bucket": buckets["level4_evidence_bucket"][1],
                "level5_advanced_bucket": buckets["level5_advanced_bucket"][1],
                "next_action_bucket": buckets["next_action_bucket"][1],
                "investigation_status_bucket": buckets["investigation_status_bucket"][1],
                "weiter_untersuchen_bucket": buckets["weiter_untersuchen_bucket"][1],
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
                "flags": row.get("combined_flags", row.get("flags", "")),
            }
        )

    finder_label_purple(TREE_ROOT / "01_NEXT_STEPS_GLOBAL")
    finder_label_purple(TREE_ROOT / "01_NEXT_STEPS_GLOBAL" / "00_VIOLETT_TOP_TIER_ALL")
    finder_label_purple(TREE_ROOT / "01_NEXT_STEPS_GLOBAL" / "01_HZ_VIOLETT_TOP_TIER")

    summary = pd.DataFrame(summary_rows)
    write_range_status_reports(summary, distance_ranges)
    summary.to_csv(REPORT_DIR / "level0_level_tree_manifest.csv", index=False)
    counts = pd.DataFrame(
        [{"bucket": bucket, "count": count} for bucket, count in sorted(bucket_counts.items())]
    )
    counts.to_csv(REPORT_DIR / "level0_level_tree_bucket_counts.csv", index=False)

    top = summary[summary["is_violett_top_tier"].eq(1)].sort_values(
        by=["manual_review_rank", "review_score"],
        ascending=[True, False],
        na_position="last",
    )
    top.to_csv(REPORT_DIR / "top_tier_planets_next_steps.csv", index=False)
    hz = top[top["hz_class"].isin(["KONSERVATIVE_HZ", "OPT_HZ_INNEN", "OPT_HZ_AUSSEN"])]
    hz.to_csv(REPORT_DIR / "top_tier_hz_planets_next_steps.csv", index=False)

    lines = [
        "# Top Tier Planets - Next Steps",
        "",
        f"Tree root: `{TREE_ROOT}`",
        "",
        "## Continue now",
        "",
        "| Rank | TIC | Range | Review | Evidence | Bayes | HZ | Period d | Next bucket |",
        "|---:|---:|---|---:|---|---|---|---:|---|",
    ]
    for _, row in top.head(30).iterrows():
        period = safe_float(row.get("period")) or 0.0
        review = safe_float(row.get("review_score")) or 0.0
        lines.append(
            f"| {safe_int(row.get('manual_review_rank'))} | {safe_int(row.get('TIC'))} | "
            f"{text_value(row.get('distance_range'))} | {review:.1f} | "
            f"{text_value(row.get('evidence_class'))} | {text_value(row.get('bayes_class'))} | "
            f"{text_value(row.get('hz_class'))} | {period:.4f} | {text_value(row.get('next_action_bucket'))} |"
        )
    lines.extend(
        [
            "",
            "## Reports",
            "",
            f"- `{REPORT_DIR / 'level0_level_tree_manifest.csv'}`",
            f"- `{REPORT_DIR / 'level0_level_tree_bucket_counts.csv'}`",
            f"- `{REPORT_DIR / 'top_tier_planets_next_steps.csv'}`",
            f"- `{REPORT_DIR / 'top_tier_hz_planets_next_steps.csv'}`",
        ]
    )
    (REPORT_DIR / "TOP_TIER_PLANETS_NEXT_STEPS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    build_readme(distance_ranges, removed_old, removed_generated_trees, purple_ok, purple_fail)

    print(f"tree_root={TREE_ROOT}")
    print(f"report_dir={REPORT_DIR}")
    print(f"records={len(summary_rows)}")
    print(f"removed_old_investigation_indexes={removed_old}")
    print(f"removed_generated_trees={removed_generated_trees}")
    print(f"purple_label_ok={purple_ok}")
    print(f"purple_label_fail={purple_fail}")
    print("top_bucket_counts")
    for bucket, count in sorted(bucket_counts.items())[:20]:
        print(f"{bucket}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
