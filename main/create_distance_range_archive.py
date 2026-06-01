#!/usr/bin/env python3
"""Create an additive candidate archive sorted by 10 ly distance bins.

The generated folders use symlinks for existing plot/light-curve/report
artifacts. This keeps the old project structure untouched and avoids copying
many gigabytes of light-curve data.
"""

from __future__ import annotations

import csv
import json
import math
import os
import plistlib
import re
import sqlite3
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_CANDIDATES_CSV = (
    PROJECT_ROOT / "level4_TTV_analyse" / "level4_01_rohdaten_export" / "candidates_v2.csv"
)
SOURCE_DATABASE = PROJECT_ROOT / "database" / "planet_hunter.db"
OUTPUT_ROOT = PROJECT_ROOT / "level0_lichtjahre_10ly_bis_500"
RANGE_WIDTH_LY = 10
MAX_DISTANCE_LY = 500
MANAGED_FINDER_TAGS = {
    "SPC_GREEN\n2",
    "HZ_PURPLE\n3",
    "VIOLETT_HZ\n3",
    "Lila\n3",
    "Purple\n3",
    "INFO_NEEDED_YELLOW\n5",
    "FP_RED\n6",
}
MANAGED_MARKER_FILES = {
    "GRUEN_MARKIERT_SPC.md",
    "VIOLETT_MARKIERT_HZ.md",
    "GELB_MARKIERT_MEHR_INFORMATIONEN.md",
    "ROT_MARKIERT_FP.md",
}

SPC_GREEN_STATUSES = {"SPC", "SPC-A", "SPC-B", "SPC-C"}
FP_STATUSES = {"FP", "FP_ART", "FALSE_POSITIVE"}

ARTIFACT_ROOTS = [
    PROJECT_ROOT / "csv",
    PROJECT_ROOT / "level1_rohkandidaten",
    PROJECT_ROOT / "level2_planetencheck",
    PROJECT_ROOT / "level3_externe_katalogpruefung",
    PROJECT_ROOT / "level3_neue_planetenkandidaten",
    PROJECT_ROOT / "level4_TTV_analyse",
    PROJECT_ROOT / "level5_detailvalidierung",
    PROJECT_ROOT / "level6_kandidaten_dossier",
    PROJECT_ROOT / "reports",
]

CSV_DATA_ROOTS = [
    PROJECT_ROOT / "csv",
    PROJECT_ROOT / "level1_rohkandidaten",
    PROJECT_ROOT / "level2_planetencheck",
    PROJECT_ROOT / "level3_externe_katalogpruefung",
    PROJECT_ROOT / "level3_neue_planetenkandidaten",
    PROJECT_ROOT / "level4_TTV_analyse",
    PROJECT_ROOT / "level5_detailvalidierung",
    PROJECT_ROOT / "level6_kandidaten_dossier",
]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def read_candidate_rows() -> tuple[list[dict[str, str]], str]:
    if SOURCE_DATABASE.exists():
        try:
            uri = f"file:{SOURCE_DATABASE}?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=10) as conn:
                conn.row_factory = sqlite3.Row
                rows = []
                for row in conn.execute("select * from candidates_v2"):
                    rows.append(
                        {
                            key: "" if row[key] is None else str(row[key])
                            for key in row.keys()
                        }
                    )
                if rows:
                    return rows, str(SOURCE_DATABASE.relative_to(PROJECT_ROOT)) + ":candidates_v2"
        except sqlite3.Error:
            pass

    return read_csv_rows(SOURCE_CANDIDATES_CSV), str(SOURCE_CANDIDATES_CSV.relative_to(PROJECT_ROOT))


def load_current_status_overlay() -> dict[str, str]:
    """Load fresh candidate statuses from the DB, with SPC-folder fallback."""
    statuses: dict[str, str] = {}

    if SOURCE_DATABASE.exists():
        try:
            uri = f"file:{SOURCE_DATABASE}?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=10) as conn:
                for tic, status in conn.execute("select TIC, status from candidates_v2"):
                    statuses[str(tic)] = status or ""
        except sqlite3.Error:
            statuses = {}

    if statuses:
        return statuses

    final_spc_root = PROJECT_ROOT / "level4_TTV_analyse" / "level4_07_SPC_22_final"
    if final_spc_root.exists():
        for directory in final_spc_root.iterdir():
            if directory.is_dir():
                for tic in tic_from_text(directory.name):
                    statuses[tic] = "SPC"

    return statuses


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def distance_range_name(distance_ly: float) -> str:
    start = int(math.floor(distance_ly / RANGE_WIDTH_LY) * RANGE_WIDTH_LY)
    if start >= MAX_DISTANCE_LY:
        start = MAX_DISTANCE_LY - RANGE_WIDTH_LY
    end = start + RANGE_WIDTH_LY
    return f"{start:03d}_{end:03d}_ly"


def is_truthy_flag(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def classify_candidate(status: str, is_fp: str = "") -> dict[str, str]:
    normalized_status = str(status or "").strip().upper()
    if normalized_status in FP_STATUSES or is_truthy_flag(is_fp):
        return {
            "markierung": "ROT",
            "klasse": "FALSE_POSITIVE",
            "folder_prefix": "RED_FP",
            "finder_tag": "FP_RED\n6",
            "marker_file": "ROT_MARKIERT_FP.md",
            "marker_title": "RED - false positive",
        }
    if normalized_status in SPC_GREEN_STATUSES:
        return {
            "markierung": "GRUEN",
            "klasse": "SPC_KANDIDAT",
            "folder_prefix": "SPC_GREEN",
            "finder_tag": "SPC_GREEN\n2",
            "marker_file": "GRUEN_MARKIERT_SPC.md",
            "marker_title": "GREEN - SPC candidate",
        }
    return {
        "markierung": "GELB",
        "klasse": "MEHR_INFORMATIONEN_NOETIG",
        "folder_prefix": "YELLOW_INFO",
        "finder_tag": "INFO_NEEDED_YELLOW\n5",
        "marker_file": "GELB_MARKIERT_MEHR_INFORMATIONEN.md",
        "marker_title": "YELLOW - more information needed",
    }


def is_hz_candidate(hz_status: str) -> bool:
    return bool(hz_status) and hz_status != "ZU_HEISS"


def candidate_folder_name(tic: str, color_info: dict[str, str], is_hz: bool) -> str:
    hz_part = "_HZ_PURPLE" if is_hz else ""
    return f"{color_info['folder_prefix']}{hz_part}_TIC_{tic}"


def sanitize_link_name(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:180] or "artifact"


def unique_path(parent: Path, name: str) -> Path:
    candidate = parent / name
    if not candidate.exists() and not candidate.is_symlink():
        return candidate

    stem = Path(name).stem
    suffix = Path(name).suffix
    for idx in range(2, 10000):
        candidate = parent / f"{stem}_{idx:03d}{suffix}"
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise RuntimeError(f"Could not create unique link name for {name}")


def safe_symlink(target: Path, link: Path) -> Path:
    target = target.resolve()
    if link.is_symlink():
        if Path(os.readlink(link)) == target:
            return link
        link.unlink()
    elif link.exists():
        link = unique_path(link.parent, link.name)

    link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(target, link, target_is_directory=target.is_dir())
    return link


def tic_from_text(text: str) -> set[str]:
    return set(re.findall(r"TIC[_ -]?(\d+)", text, flags=re.IGNORECASE))


def build_artifact_index(candidate_tics: set[str]) -> dict[str, list[Path]]:
    artifacts: dict[str, list[Path]] = defaultdict(list)

    for root in ARTIFACT_ROOTS:
        if not root.exists():
            continue

        for current_root, dirs, files in os.walk(root):
            current = Path(current_root)

            kept_dirs: list[str] = []
            for dirname in dirs:
                directory = current / dirname
                matches = tic_from_text(dirname)
                matches |= tic_from_text(str(directory.relative_to(PROJECT_ROOT)))
                matched_candidates = matches & candidate_tics
                if matched_candidates:
                    for tic in matched_candidates:
                        artifacts[tic].append(directory)
                    continue
                kept_dirs.append(dirname)
            dirs[:] = kept_dirs

            for filename in files:
                file_path = current / filename
                matches = tic_from_text(filename)
                matches |= tic_from_text(str(file_path.relative_to(PROJECT_ROOT)))
                for tic in matches & candidate_tics:
                    artifacts[tic].append(file_path)

    for tic, paths in artifacts.items():
        artifacts[tic] = sorted(set(paths), key=lambda p: str(p.relative_to(PROJECT_ROOT)))
    return artifacts


def build_csv_row_index(candidate_tics: set[str]) -> dict[str, list[dict[str, Any]]]:
    rows_by_tic: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for root in CSV_DATA_ROOTS:
        if not root.exists():
            continue

        for csv_path in root.rglob("*.csv"):
            if OUTPUT_ROOT in csv_path.parents:
                continue
            try:
                with csv_path.open(newline="", encoding="utf-8-sig") as handle:
                    reader = csv.DictReader(handle)
                    if not reader.fieldnames:
                        continue
                    tic_columns = [
                        col
                        for col in reader.fieldnames
                        if col and col.lower() in {"tic", "tic_id", "ticid"}
                    ]
                    if not tic_columns:
                        continue
                    for row in reader:
                        for column in tic_columns:
                            value = (row.get(column) or "").strip()
                            if value.endswith(".0"):
                                value = value[:-2]
                            if value in candidate_tics:
                                rows_by_tic[value].append(
                                    {
                                        "source_csv": str(csv_path.relative_to(PROJECT_ROOT)),
                                        "row": row,
                                    }
                                )
                                break
            except (UnicodeDecodeError, csv.Error, OSError):
                continue

    return rows_by_tic


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def apply_finder_tag(path: Path, finder_tags: str | list[str]) -> bool:
    """Best-effort macOS Finder tag, preserving unrelated existing tags."""
    attr_name = "com.apple.metadata:_kMDItemUserTags"
    tags: list[str]
    if isinstance(finder_tags, str):
        desired_tags = [finder_tags]
    else:
        desired_tags = list(finder_tags)

    try:
        getxattr = getattr(os, "getxattr")
        setxattr = getattr(os, "setxattr")
        existing_raw = getxattr(path, attr_name)
        existing = plistlib.loads(existing_raw)
        tags = list(existing) if isinstance(existing, list) else []
        tags = [tag for tag in tags if tag not in MANAGED_FINDER_TAGS]
        for finder_tag in desired_tags:
            if finder_tag not in tags:
                tags.append(finder_tag)
        setxattr(path, attr_name, plistlib.dumps(tags, fmt=plistlib.FMT_BINARY))
        return True
    except AttributeError:
        pass
    except OSError:
        tags = []
    except Exception:
        return False

    try:
        result = subprocess.run(
            ["xattr", "-p", "-x", attr_name, str(path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            raw_hex = re.sub(r"\s+", "", result.stdout)
            existing = plistlib.loads(bytes.fromhex(raw_hex))
            tags = list(existing) if isinstance(existing, list) else []
        else:
            tags = []
    except Exception:
        tags = []

    tags = [tag for tag in tags if tag not in MANAGED_FINDER_TAGS]
    for finder_tag in desired_tags:
        if finder_tag not in tags:
            tags.append(finder_tag)
    try:
        subprocess.run(
            [
                "xattr",
                "-w",
                "-x",
                attr_name,
                plistlib.dumps(tags, fmt=plistlib.FMT_BINARY).hex(),
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except Exception:
        return False


def mark_existing_spc_folders(spc_rows: list[dict[str, str]]) -> int:
    spc_tics = {row["TIC"] for row in spc_rows}
    final_spc_root = PROJECT_ROOT / "level4_TTV_analyse" / "level4_07_SPC_22_final"
    if not final_spc_root.exists():
        return 0

    marked = 0
    for directory in final_spc_root.iterdir():
        if not directory.is_dir():
            continue
        matches = tic_from_text(directory.name)
        if not matches & spc_tics:
            continue

        tic = sorted(matches & spc_tics)[0]
        marker = directory / "GRUEN_MARKIERT_SPC.md"
        marker.write_text(
            "\n".join(
                [
                    f"TIC {tic} final mark: GREEN - SPC",
                    "",
                    "Additive marker only. Existing data was not moved or deleted.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        apply_finder_tag(directory, "SPC_GREEN\n2")
        marked += 1
    return marked


def main() -> None:
    candidates, candidate_source = read_candidate_rows()
    status_overlay = load_current_status_overlay()
    candidates = [
        row
        for row in candidates
        if row.get("TIC") and row.get("distance_ly") and float(row["distance_ly"]) <= MAX_DISTANCE_LY
    ]
    for row in candidates:
        tic = row["TIC"]
        if tic in status_overlay:
            row["status"] = status_overlay[tic]
    candidates.sort(key=lambda row: (float(row["distance_ly"]), int(row["TIC"])))
    candidate_tics = {row["TIC"] for row in candidates}

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    for start in range(0, MAX_DISTANCE_LY, RANGE_WIDTH_LY):
        (OUTPUT_ROOT / f"{start:03d}_{start + RANGE_WIDTH_LY:03d}_ly").mkdir(
            parents=True, exist_ok=True
        )

    print(f"Indexing artifacts for {len(candidate_tics)} candidates...")
    artifact_index = build_artifact_index(candidate_tics)
    print("Indexing CSV data rows...")
    csv_row_index = build_csv_row_index(candidate_tics)

    manifest_rows: list[dict[str, Any]] = []
    rows_by_range: dict[str, list[dict[str, Any]]] = defaultdict(list)
    spc_rows: list[dict[str, str]] = []
    yellow_rows: list[dict[str, str]] = []
    red_rows: list[dict[str, str]] = []
    hz_rows: list[dict[str, str]] = []
    total_links = 0

    for row in candidates:
        tic = row["TIC"]
        distance_ly = float(row["distance_ly"])
        range_name = distance_range_name(distance_ly)
        status = row.get("status") or ""
        hz_status = row.get("hz_status") or ""
        is_hz = is_hz_candidate(hz_status)
        color_info = classify_candidate(status, row.get("is_fp") or "")
        is_spc = color_info["markierung"] == "GRUEN"
        markierung = color_info["markierung"]
        hz_markierung = "VIOLETT" if is_hz else ""
        folder_name = candidate_folder_name(tic, color_info, is_hz)
        candidate_dir = OUTPUT_ROOT / range_name / folder_name
        legacy_folder_names = [f"TIC_{tic}"]
        for prefix in ["SPC_GREEN", "YELLOW_INFO", "RED_FP"]:
            legacy_folder_names.append(f"{prefix}_TIC_{tic}")
            legacy_folder_names.append(f"{prefix}_HZ_PURPLE_TIC_{tic}")
        for legacy_folder_name in legacy_folder_names:
            legacy_candidate_dir = OUTPUT_ROOT / range_name / legacy_folder_name
            if legacy_candidate_dir == candidate_dir:
                continue
            if legacy_candidate_dir.exists() and not candidate_dir.exists():
                legacy_candidate_dir.rename(candidate_dir)
                break
        data_links = candidate_dir / "data_links"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        data_links.mkdir(parents=True, exist_ok=True)

        for marker_file in MANAGED_MARKER_FILES:
            stale_marker = candidate_dir / marker_file
            if stale_marker.name != color_info["marker_file"] and stale_marker.exists():
                stale_marker.unlink()

        (candidate_dir / color_info["marker_file"]).write_text(
            "\n".join(
                [
                    f"TIC {tic} final mark: {color_info['marker_title']}",
                    f"Status: {status}",
                    f"Distance range: {range_name}",
                    f"Distance ly: {distance_ly:.6f}",
                    "",
                    "Color code: GRUEN = SPC candidate, GELB = more information needed, ROT = false positive.",
                    "Existing project structure was not moved or deleted.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        if is_hz:
            (candidate_dir / "VIOLETT_MARKIERT_HZ.md").write_text(
                "\n".join(
                    [
                        f"TIC {tic} HZ-Markierung: VIOLETT - Habitable-Zone-Kandidat",
                        f"HZ status: {hz_status}",
                        f"Status color: {markierung}",
                        f"Distance range: {range_name}",
                        f"Distance ly: {distance_ly:.6f}",
                        "",
                        "Violett ist ein zusaetzlicher HZ-Marker. Gruen/gelb/rot beschreiben weiter den Review-Status.",
                        "Technischer Ordnercode: HZ_PURPLE ist ein Legacy-Name fuer die sichtbare Violett-Markierung.",
                        "Existing project structure was not moved or deleted.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
        apply_finder_tag(
            candidate_dir,
            [color_info["finder_tag"], "Purple\n3"] if is_hz else color_info["finder_tag"],
        )

        artifacts = list(artifact_index.get(tic, []))
        lightcurve_dir = row.get("lightcurve_dir")
        if lightcurve_dir:
            lightcurve_path = Path(lightcurve_dir).expanduser()
            if lightcurve_path.exists():
                artifacts.insert(0, lightcurve_path.parent if lightcurve_path.is_file() else lightcurve_path)

        source_rows: list[dict[str, str]] = []
        linked_targets: set[Path] = set()
        link_count = 0
        for artifact in artifacts:
            if not artifact.exists():
                continue
            resolved = artifact.resolve()
            if resolved in linked_targets:
                continue
            linked_targets.add(resolved)
            rel = artifact.relative_to(PROJECT_ROOT)
            link_name = sanitize_link_name(str(rel))
            if artifact.is_file() and artifact.suffix and not link_name.endswith(artifact.suffix):
                link_name += artifact.suffix
            link_path = data_links / link_name
            link_path = safe_symlink(artifact, link_path)
            link_count += 1
            source_rows.append(
                {
                    "link_name": link_path.name,
                    "source_path": str(artifact),
                    "source_relative_path": str(rel),
                    "kind": "directory" if artifact.is_dir() else "file",
                }
            )

        total_links += link_count
        source_fieldnames = ["link_name", "kind", "source_relative_path", "source_path"]
        write_csv(candidate_dir / "source_paths.csv", source_rows, source_fieldnames)

        candidate_payload = {
            "candidate": row,
            "distance_range": range_name,
            "markierung": markierung,
            "markierungs_klasse": color_info["klasse"],
            "hz_markierung": hz_markierung,
            "source_candidates": candidate_source,
            "linked_source_count": link_count,
            "csv_rows": csv_row_index.get(tic, []),
        }
        write_json(candidate_dir / "candidate_data.json", candidate_payload)
        write_csv(candidate_dir / "candidate_data.csv", [row], list(row.keys()))

        sources_md = [
            f"# TIC {tic}",
            "",
            f"- distance_range: {range_name}",
            f"- distance_ly: {distance_ly:.6f}",
            f"- status: {status}",
            f"- markierung: {markierung}",
            f"- markierungs_klasse: {color_info['klasse']}",
            f"- hz_status: {hz_status}",
            f"- hz_markierung: {hz_markierung or 'none'}",
            f"- linked_sources: {link_count}",
            "",
            "The `data_links` folder contains symlinks to existing project artifacts.",
            "The old folder structure was not moved or deleted.",
            "",
        ]
        (candidate_dir / "QUELLEN.md").write_text("\n".join(sources_md), encoding="utf-8")

        manifest_row = {
            "distance_range": range_name,
            "TIC": tic,
            "status": status,
            "markierung": markierung,
            "markierungs_klasse": color_info["klasse"],
            "hz_markierung": hz_markierung,
            "distance_ly": f"{distance_ly:.9f}",
            "best_period": row.get("best_period", ""),
            "planet_radius_earth": row.get("planet_radius_earth", ""),
            "transit_snr": row.get("transit_snr", ""),
            "transit_count": row.get("transit_count", ""),
            "hz_status": hz_status,
            "lightcurve_dir": row.get("lightcurve_dir", ""),
            "candidate_folder": str(candidate_dir.relative_to(PROJECT_ROOT)),
            "linked_source_count": link_count,
        }
        manifest_rows.append(manifest_row)
        rows_by_range[range_name].append(manifest_row)
        if is_spc:
            spc_rows.append(manifest_row)
        elif markierung == "ROT":
            red_rows.append(manifest_row)
        else:
            yellow_rows.append(manifest_row)
        if is_hz:
            hz_rows.append(manifest_row)

    manifest_fields = [
        "distance_range",
        "TIC",
        "status",
        "markierung",
        "markierungs_klasse",
        "hz_markierung",
        "distance_ly",
        "best_period",
        "planet_radius_earth",
        "transit_snr",
        "transit_count",
        "hz_status",
        "lightcurve_dir",
        "candidate_folder",
        "linked_source_count",
    ]
    write_csv(OUTPUT_ROOT / "manifest_all_candidates_by_distance.csv", manifest_rows, manifest_fields)
    write_csv(OUTPUT_ROOT / "spc_green_candidates.csv", spc_rows, manifest_fields)
    write_csv(OUTPUT_ROOT / "yellow_more_info_candidates.csv", yellow_rows, manifest_fields)
    write_csv(OUTPUT_ROOT / "red_false_positive_candidates.csv", red_rows, manifest_fields)
    write_csv(OUTPUT_ROOT / "hz_purple_candidates.csv", hz_rows, manifest_fields)

    for start in range(0, MAX_DISTANCE_LY, RANGE_WIDTH_LY):
        range_name = f"{start:03d}_{start + RANGE_WIDTH_LY:03d}_ly"
        range_rows = rows_by_range.get(range_name, [])
        write_csv(OUTPUT_ROOT / range_name / "range_manifest.csv", range_rows, manifest_fields)

    existing_marked = mark_existing_spc_folders(spc_rows)

    readme = [
        "# Kandidaten nach Lichtjahren",
        "",
        "Additive Sortierung aller `candidates_v2` Kandidaten bis 500 ly in 10-ly-Schritten.",
        "",
        "- Ordner: `000_010_ly` bis `490_500_ly`",
        f"- Kandidaten: {len(manifest_rows)}",
        f"- SPC gruen markiert: {len(spc_rows)}",
        f"- Mehr Informationen noetig gelb markiert: {len(yellow_rows)}",
        f"- False Positives rot markiert: {len(red_rows)}",
        f"- HZ violett zusaetzlich markiert: {len(hz_rows)}",
        "- Bestehende Struktur: nicht verschoben, nicht geloescht",
        "- Zugehoerige Artefakte: als Symlinks in `data_links/` verknuepft",
        "",
        "Wichtige Dateien:",
        "",
        "- `manifest_all_candidates_by_distance.csv`",
        "- `spc_green_candidates.csv`",
        "- `yellow_more_info_candidates.csv`",
        "- `red_false_positive_candidates.csv`",
        "- `hz_purple_candidates.csv`",
        "- Pro Kandidat: `candidate_data.csv`, `candidate_data.json`, `source_paths.csv`, `QUELLEN.md`",
        "",
        "Farbmarkierung:",
        "",
        "- Gruen: `SPC_GREEN_TIC_<TIC>` = SPC-Kandidat.",
        "- Gelb: `YELLOW_INFO_TIC_<TIC>` = mehr Informationen werden benoetigt.",
        "- Rot: `RED_FP_TIC_<TIC>` = False Positive / FP.",
        "- Violett: `_HZ_PURPLE_` im Ordnernamen = HZ-Kandidat; `HZ_PURPLE` ist nur der technische Legacy-Code.",
        "- Kombiniert: z.B. `YELLOW_INFO_HZ_PURPLE_TIC_<TIC>`.",
        "- Auf macOS wurden best-effort Finder-Tags gesetzt.",
        "- Zusaetzlich wurden vorhandene Ordner in `level4_07_SPC_22_final` additiv markiert.",
        "",
    ]
    (OUTPUT_ROOT / "README.md").write_text("\n".join(readme), encoding="utf-8")

    print(f"Created/updated: {OUTPUT_ROOT}")
    print(f"Candidates sorted: {len(manifest_rows)}")
    print(f"Ranges created: {MAX_DISTANCE_LY // RANGE_WIDTH_LY}")
    print(f"SPC green candidates: {len(spc_rows)}")
    print(f"Yellow more-info candidates: {len(yellow_rows)}")
    print(f"Red false-positive candidates: {len(red_rows)}")
    print(f"HZ purple candidates: {len(hz_rows)}")
    print(f"Source links created/kept: {total_links}")
    print(f"Existing final-SPC folders marked: {existing_marked}")


if __name__ == "__main__":
    main()
