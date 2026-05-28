#!/usr/bin/env python3
"""Remove red false-positive folders from level0 and protect them in the DB."""

from __future__ import annotations

import csv
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "database" / "planet_hunter.db"
LEVEL0_ROOT = PROJECT_ROOT / "level0_lichtjahre_10ly_bis_500"
MANIFEST_PATH = LEVEL0_ROOT / "manifest_all_candidates_by_distance.csv"
REMOVED_CSV = LEVEL0_ROOT / "red_removed_from_folder_structure.csv"
ACTIVE_MANIFEST_CSV = LEVEL0_ROOT / "manifest_active_folder_structure.csv"
ACTIVE_HZ_CSV = LEVEL0_ROOT / "hz_purple_active_folder_structure.csv"


def read_manifest() -> list[dict[str, str]]:
    with MANIFEST_PATH.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        is not None
    )


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def remove_candidate_folder(folder_text: str) -> bool:
    folder = (PROJECT_ROOT / folder_text).resolve()
    level0 = LEVEL0_ROOT.resolve()
    if not folder.is_relative_to(level0):
        raise RuntimeError(f"Refusing to remove folder outside level0: {folder}")
    if not folder.name.startswith("RED_FP"):
        raise RuntimeError(f"Refusing to remove non-red folder: {folder}")
    if not folder.exists():
        return False
    if folder.is_symlink() or not folder.is_dir():
        folder.unlink()
    else:
        shutil.rmtree(folder)
    return True


def main() -> None:
    manifest_rows = read_manifest()
    red_rows = [row for row in manifest_rows if row.get("markierung") == "ROT"]
    active_rows = [row for row in manifest_rows if row.get("markierung") != "ROT"]
    active_hz_rows = [row for row in active_rows if row.get("hz_markierung") == "VIOLETT"]
    red_tics = sorted({int(row["TIC"]) for row in red_rows})
    now = datetime.now().isoformat(timespec="seconds")

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS level0_folder_removals (
                TIC INTEGER PRIMARY KEY,
                removed_at TEXT NOT NULL,
                reason TEXT NOT NULL,
                candidate_folder TEXT,
                distance_range TEXT,
                distance_ly REAL,
                previous_status TEXT,
                hz_status TEXT,
                hz_mark TEXT,
                source TEXT
            )
            """
        )
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
            CREATE TABLE IF NOT EXISTS pipeline_status_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                note_type TEXT NOT NULL,
                note_text TEXT NOT NULL,
                source TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute("DROP TABLE IF EXISTS temp_red_level0_cleanup")
        conn.execute(
            """
            CREATE TEMP TABLE temp_red_level0_cleanup (
                TIC INTEGER PRIMARY KEY,
                candidate_folder TEXT,
                distance_range TEXT,
                distance_ly REAL,
                previous_status TEXT,
                hz_status TEXT,
                hz_mark TEXT
            )
            """
        )

        for row in red_rows:
            tic = int(row["TIC"])
            previous_status = (
                conn.execute(
                    "SELECT COALESCE(status, 'CANDIDATE') FROM candidates_v2 WHERE TIC=?",
                    (tic,),
                ).fetchone()
                or ["CANDIDATE"]
            )[0]
            conn.execute(
                """
                INSERT OR REPLACE INTO temp_red_level0_cleanup
                    (TIC, candidate_folder, distance_range, distance_ly,
                     previous_status, hz_status, hz_mark)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tic,
                    row.get("candidate_folder", ""),
                    row.get("distance_range", ""),
                    float(row["distance_ly"]) if row.get("distance_ly") else None,
                    previous_status,
                    row.get("hz_status", ""),
                    row.get("hz_markierung", ""),
                ),
            )

        conn.execute(
            """
            INSERT OR REPLACE INTO level0_folder_removals
                (TIC, removed_at, reason, candidate_folder, distance_range,
                 distance_ly, previous_status, hz_status, hz_mark, source)
            SELECT
                TIC,
                ?,
                'ROT/FP aus level0-Ordnerstruktur entfernt; DB-Status schuetzt vor erneutem Scan.',
                candidate_folder,
                distance_range,
                distance_ly,
                previous_status,
                hz_status,
                hz_mark,
                'scripts/main/remove_red_level0_folders.py'
            FROM temp_red_level0_cleanup
            """,
            (now,),
        )

        conn.execute(
            """
            INSERT OR REPLACE INTO candidate_annotations
                (TIC, annotation_type, annotation_text, source, created_at)
            SELECT
                TIC,
                'LEVEL0_RED_REMOVED_NO_RESCAN',
                'ROT/FP: aus level0-Ordnerstruktur entfernt. Nicht erneut scannen; Status ist als FP geschuetzt.',
                'scripts/main/remove_red_level0_folders.py',
                ?
            FROM temp_red_level0_cleanup
            """,
            (now,),
        )

        conn.execute(
            """
            UPDATE candidates_v2
               SET is_fp=1,
                   status=CASE
                       WHEN COALESCE(status, '') IN ('FP_ART', 'FALSE_POSITIVE') THEN status
                       ELSE 'FALSE_POSITIVE'
                   END
             WHERE TIC IN (SELECT TIC FROM temp_red_level0_cleanup)
            """
        )
        for table in ("rohdaten", "kstars_active"):
            if table_exists(conn, table):
                conn.execute(
                    f"""
                    UPDATE {table}
                       SET status=CASE
                           WHEN COALESCE(status, '') IN ('FP_ART', 'FALSE_POSITIVE') THEN status
                           ELSE 'FALSE_POSITIVE'
                       END,
                           checked_at=?
                     WHERE TIC IN (SELECT TIC FROM temp_red_level0_cleanup)
                    """,
                    (now,),
                )
        if table_exists(conn, "level0_distance_status"):
            conn.execute(
                """
                UPDATE level0_distance_status
                   SET db_status=CASE
                           WHEN COALESCE(db_status, '') IN ('FP_ART', 'FALSE_POSITIVE') THEN db_status
                           ELSE 'FALSE_POSITIVE'
                       END,
                       review_mark='ROT',
                       review_class='FALSE_POSITIVE_REMOVED_FROM_LEVEL0',
                       source='scripts/main/remove_red_level0_folders.py',
                       updated_at=?
                 WHERE TIC IN (SELECT TIC FROM temp_red_level0_cleanup)
                """,
                (now,),
            )
        if table_exists(conn, "tess_sector_inventory"):
            conn.execute(
                """
                UPDATE tess_sector_inventory
                   SET source_status='FALSE_POSITIVE',
                       last_checked_at=?
                 WHERE TIC IN (
                       SELECT TIC FROM temp_red_level0_cleanup
                        WHERE previous_status NOT IN ('FP_ART', 'FALSE_POSITIVE')
                 )
                """,
                (now,),
            )
        conn.execute(
            """
            INSERT INTO pipeline_status_notes (note_type, note_text, source, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                "LEVEL0_RED_REMOVED_NO_RESCAN",
                f"{len(red_tics)} rote FP-Kandidaten aus level0 entfernt; "
                "candidates_v2/rohdaten/kstars_active sind als FP_ART oder FALSE_POSITIVE geschuetzt.",
                "scripts/main/remove_red_level0_folders.py",
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    removed_rows: list[dict[str, Any]] = []
    removed_count = 0
    already_missing = 0
    for row in red_rows:
        did_remove = remove_candidate_folder(row["candidate_folder"])
        removed_count += 1 if did_remove else 0
        already_missing += 0 if did_remove else 1
        removed_rows.append(
            {
                **row,
                "removed_from_folder_structure_at": now,
                "folder_removed": "yes" if did_remove else "already_missing",
            }
        )

    fieldnames = list(red_rows[0].keys()) if red_rows else []
    write_csv(
        REMOVED_CSV,
        removed_rows,
        fieldnames + ["removed_from_folder_structure_at", "folder_removed"],
    )
    if manifest_rows:
        manifest_fieldnames = list(manifest_rows[0].keys())
        write_csv(ACTIVE_MANIFEST_CSV, active_rows, manifest_fieldnames)
        write_csv(ACTIVE_HZ_CSV, active_hz_rows, manifest_fieldnames)
        rows_by_range: dict[str, list[dict[str, str]]] = {}
        for row in active_rows:
            rows_by_range.setdefault(row["distance_range"], []).append(row)
        for range_dir in sorted(p for p in LEVEL0_ROOT.iterdir() if p.is_dir() and p.name.endswith("_ly")):
            write_csv(
                range_dir / "active_range_manifest.csv",
                rows_by_range.get(range_dir.name, []),
                manifest_fieldnames,
            )

    readme_lines = [
        "# Kandidaten nach Lichtjahren",
        "",
        "Aktive `level0`-Ordnerstruktur bis 500 ly in 10-ly-Schritten.",
        "",
        f"- Aktive Ordner-Kandidaten: {len(active_rows)}",
        f"- Rote FP-Ordner entfernt: {len(red_rows)}",
        "- Rote Kandidaten bleiben in der Datenbank als `FP_ART` oder `FALSE_POSITIVE` vermerkt.",
        "- Dadurch werden sie von New-Sector/Recheck-Laeufen geschuetzt und nicht doppelt gescannt.",
        "- `manifest_all_candidates_by_distance.csv` bleibt die Gesamtuebersicht inklusive roter FP.",
        "- `manifest_active_folder_structure.csv` beschreibt nur die Ordner, die aktuell sichtbar bleiben.",
        "- `red_removed_from_folder_structure.csv` ist die Audit-Liste der entfernten roten Ordner.",
        "",
        "Farbmarkierung der verbleibenden Ordner:",
        "",
        "- Gruen: `SPC_GREEN_TIC_<TIC>` = SPC-Kandidat.",
        "- Gelb: `YELLOW_INFO_TIC_<TIC>` = mehr Informationen werden benoetigt.",
        "- Violett: `_HZ_PURPLE_` im Ordnernamen = HZ-Kandidat.",
        "",
    ]
    (LEVEL0_ROOT / "README.md").write_text("\n".join(readme_lines), encoding="utf-8")

    print(f"Red TICs protected in DB: {len(red_tics)}")
    print(f"Red folders removed: {removed_count}")
    print(f"Red folders already missing: {already_missing}")
    print(f"Removal audit CSV: {REMOVED_CSV}")
    print(f"Active folder manifest: {ACTIVE_MANIFEST_CSV}")


if __name__ == "__main__":
    main()
