#!/usr/bin/env python3
"""Monitor candidates with insufficient data for newly available TESS sectors."""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "database" / "planet_hunter.db"
REPORT_ROOT = PROJECT_ROOT / "reports" / "insufficient_data_monitor"
LEVEL5_SUMMARY = (
    PROJECT_ROOT
    / "level5_detailvalidierung"
    / "level5_06_bestanden"
    / "green_purple_A_level5_summary.csv"
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_new_tess_sectors as sectors  # noqa: E402


PROTECTED_STATUSES = {"FP", "FP_ART", "FALSE_POSITIVE", "REJECT_LEVEL5_LOCAL"}
DROP_ACTIONS = {"DROP_FROM_TOPLIST_RECHECK_FP"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor insufficient-data candidates for new TESS information.")
    parser.add_argument("--limit", type=int, default=None, help="Limit candidates checked.")
    parser.add_argument("--sleep", type=float, default=0.2, help="Delay between MAST queries.")
    parser.add_argument("--dry-run", action="store_true", help="Do not update DB sector inventory or statuses.")
    parser.add_argument("--no-mark", action="store_true", help="Record sectors but do not mark RECHECK_NEW_SECTOR.")
    return parser.parse_args()


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def load_level5_actions() -> dict[int, dict[str, str]]:
    if not LEVEL5_SUMMARY.exists():
        return {}
    with LEVEL5_SUMMARY.open(newline="", encoding="utf-8") as handle:
        return {safe_int(row["tic"]): row for row in csv.DictReader(handle)}


def insufficiency_reasons(row: sqlite3.Row, level5: dict[str, str] | None) -> list[str]:
    reasons: list[str] = []
    status = str(row["status"] or "")
    if status in {"RECHECK", "RECHECK_NEW_SECTOR", "SPC-C", "SPC_ART"}:
        reasons.append(f"status={status}")
    if safe_int(row["visible_transits"]) < 3:
        reasons.append(f"visible_transits={safe_int(row['visible_transits'])}<3")
    if safe_int(row["clean_sector_count"]) < 2:
        reasons.append(f"clean_sector_count={safe_int(row['clean_sector_count'])}<2")
    if safe_int(row["transit_count"]) < 3:
        reasons.append(f"transit_count={safe_int(row['transit_count'])}<3")
    if str(row["next_recheck"] or "").strip():
        reasons.append(f"next_recheck={row['next_recheck']}")
    if level5 and level5.get("recommended_action") not in DROP_ACTIONS:
        reasons.append(f"level5_action={level5.get('recommended_action')}")
    return reasons


def load_targets(conn: sqlite3.Connection, limit: int | None) -> list[dict[str, Any]]:
    level5_actions = load_level5_actions()
    rows = conn.execute(
        """
        SELECT TIC, status, spc_class, is_fp, hz_status, best_period, transit_snr,
               distance_ly, transit_count, visible_transits, clean_sector_count,
               sector_count, revisit_priority, next_recheck
          FROM candidates_v2
         WHERE COALESCE(is_fp, 0) = 0
           AND COALESCE(status, '') NOT IN ('FP', 'FP_ART', 'FALSE_POSITIVE')
         ORDER BY
           CASE COALESCE(hz_status, '')
             WHEN 'KONSERVATIVE_HZ' THEN 0
             WHEN 'OPT_HZ_INNEN' THEN 1
             ELSE 2
           END,
           COALESCE(revisit_priority, 0) DESC,
           COALESCE(transit_snr, 0) DESC,
           TIC
        """
    ).fetchall()

    targets: list[dict[str, Any]] = []
    for row in rows:
        tic = int(row["TIC"])
        level5 = level5_actions.get(tic)
        if level5 and level5.get("recommended_action") in DROP_ACTIONS:
            continue
        reasons = insufficiency_reasons(row, level5)
        if not reasons:
            continue
        targets.append(
            {
                "TIC": tic,
                "status": row["status"] or "",
                "spc_class": row["spc_class"] or "",
                "hz_status": row["hz_status"] or "",
                "best_period": row["best_period"],
                "transit_snr": row["transit_snr"],
                "distance_ly": row["distance_ly"],
                "transit_count": row["transit_count"],
                "visible_transits": row["visible_transits"],
                "clean_sector_count": row["clean_sector_count"],
                "sector_count": row["sector_count"],
                "revisit_priority": row["revisit_priority"],
                "next_recheck": row["next_recheck"] or "",
                "level5_action": (level5 or {}).get("recommended_action", ""),
                "insufficient_reasons": ";".join(reasons),
            }
        )
        if limit and len(targets) >= limit:
            break
    return targets


def write_report(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "checked_at",
        "TIC",
        "status",
        "spc_class",
        "hz_status",
        "best_period",
        "transit_snr",
        "distance_ly",
        "transit_count",
        "visible_transits",
        "clean_sector_count",
        "sector_count",
        "revisit_priority",
        "next_recheck",
        "level5_action",
        "insufficient_reasons",
        "previous_sectors",
        "current_sectors",
        "new_sectors",
        "changed",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    changed = [row for row in rows if row.get("changed")]
    errors = [row for row in rows if row.get("error")]
    lines = [
        "# Insufficient Data Monitor",
        "",
        f"Checked at: {datetime.now().isoformat(timespec='seconds')}",
        f"Targets checked: {len(rows)}",
        f"New-sector targets: {len(changed)}",
        f"Errors: {len(errors)}",
        "",
    ]
    if changed:
        lines.extend(["## New Sectors", "", "| TIC | Status | New sectors | Reasons |", "|---:|---|---|---|"])
        for row in changed:
            lines.append(
                f"| {row['TIC']} | {row['status']} | {row['new_sectors']} | {row['insufficient_reasons']} |"
            )
        lines.append("")
    else:
        lines.extend(["No new TESS sectors found for monitored insufficient-data targets.", ""])
    if errors:
        lines.extend(["## Errors", "", "| TIC | Error |", "|---:|---|"])
        for row in errors[:25]:
            lines.append(f"| {row['TIC']} | {row['error']} |")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    checked_at = datetime.now().isoformat(timespec="seconds")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    conn = connect_db()
    try:
        sectors.ensure_table(conn)
        targets = load_targets(conn, args.limit)
        report_rows: list[dict[str, Any]] = []
        changed_count = 0
        error_count = 0
        for index, target in enumerate(targets, start=1):
            tic = int(target["TIC"])
            report_row = {"checked_at": checked_at, **target}
            try:
                old = conn.execute(
                    f"SELECT sectors_text FROM {sectors.TABLE_SECTORS} WHERE TIC=?",
                    (tic,),
                ).fetchone()
                previous = old[0] if old else ""
                current_set = sectors.fetch_available_sectors(tic)
                current = sectors.sector_text(current_set)
                previous_set = {int(s) for s in previous.split(",") if s.strip().isdigit()}
                new_set = current_set - previous_set
                changed = bool(previous_set and new_set)
                new_text = sectors.sector_text(new_set) if changed else ""
                if not args.dry_run:
                    saved_changed, saved_new_text = sectors.save_inventory(
                        conn,
                        tic,
                        str(target["status"] or ""),
                        current_set,
                        mark=not args.no_mark,
                    )
                    conn.commit()
                    changed = saved_changed
                    new_text = saved_new_text
                if changed:
                    changed_count += 1
                    print(f"TIC {tic}: NEW_SECTORS {new_text}")
                elif index % 25 == 0:
                    print(f"checked {index}/{len(targets)}")
                report_row.update(
                    {
                        "previous_sectors": previous,
                        "current_sectors": current,
                        "new_sectors": new_text,
                        "changed": changed,
                        "error": "",
                    }
                )
            except Exception as exc:
                error_count += 1
                report_row.update(
                    {
                        "previous_sectors": "",
                        "current_sectors": "",
                        "new_sectors": "",
                        "changed": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                print(f"TIC {tic}: ERROR {type(exc).__name__}: {exc}")
            report_rows.append(report_row)
            if args.sleep:
                import time

                time.sleep(args.sleep)

        latest_csv = REPORT_ROOT / "latest_insufficient_data_monitor.csv"
        latest_md = REPORT_ROOT / "latest_insufficient_data_monitor.md"
        stamped_csv = REPORT_ROOT / f"insufficient_data_monitor_{stamp}.csv"
        write_report(stamped_csv, report_rows)
        write_report(latest_csv, report_rows)
        write_markdown(latest_md, report_rows)
        print(f"Done. checked={len(report_rows)} new_sector_targets={changed_count} errors={error_count}")
        print(f"Latest report: {latest_md}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
