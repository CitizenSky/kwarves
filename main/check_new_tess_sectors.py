#!/usr/bin/env python3
"""Check known candidates for newly available TESS sectors.

This script keeps a small sector inventory in the project database. When MAST
shows sectors that were not known during an earlier check, the target is marked
as RECHECK_NEW_SECTOR so the main scanner can process it again.
"""

from __future__ import annotations

import argparse
import math
import os
import re
import signal
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from lightkurve import search_lightcurve


PROJECT_ROOT = Path("/Users/koni/astro_projects")
DB_PATH = PROJECT_ROOT / "database" / "planet_hunter.db"
TABLE_RAW = "rohdaten"
TABLE_ACTIVE = "kstars_active"
TABLE_CANDIDATES = "candidates_v2"
TABLE_SECTORS = "tess_sector_inventory"

PROTECTED_STATUSES = {"FP", "FP_ART", "FALSE_POSITIVE"}
DEFAULT_SOURCE_STATUSES = (
    "CANDIDATE",
    "SPC",
    "SPC-A",
    "SPC-B",
    "SPC-C",
    "RECHECK",
    "RECHECK_NEW_SECTOR",
)
DEFAULT_BATCH_SIZE = int(os.environ.get("KWARVES_MAST_BATCH_SIZE", "20"))
DEFAULT_BATCH_SLEEP = float(os.environ.get("KWARVES_MAST_BATCH_SLEEP", "15"))
DEFAULT_RETRIES = int(os.environ.get("KWARVES_MAST_RETRIES", "2"))
DEFAULT_RETRY_SLEEP = float(os.environ.get("KWARVES_MAST_RETRY_SLEEP", "5"))
DEFAULT_TIMEOUT = float(os.environ.get("KWARVES_MAST_TIMEOUT", "45"))


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_SECTORS} (
            TIC INTEGER PRIMARY KEY,
            sectors_text TEXT NOT NULL DEFAULT '',
            sector_count INTEGER NOT NULL DEFAULT 0,
            previous_sectors_text TEXT NOT NULL DEFAULT '',
            previous_sector_count INTEGER NOT NULL DEFAULT 0,
            new_sectors_text TEXT NOT NULL DEFAULT '',
            source_status TEXT,
            last_checked_at TEXT NOT NULL,
            last_new_sector_at TEXT
        )
        """
    )
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_SECTORS}_new ON {TABLE_SECTORS}(last_new_sector_at)")
    conn.commit()


def sector_text(sectors: set[int]) -> str:
    return ",".join(str(s) for s in sorted(sectors))


def parse_sector_value(value: object) -> int | None:
    if value is None:
        return None
    text = str(value)
    match = re.search(r"(?:Sector|S)\s*0*(\d+)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    try:
        return int(float(text))
    except ValueError:
        return None


def extract_sectors(search_result) -> set[int]:
    sectors: set[int] = set()
    table = getattr(search_result, "table", None)
    if table is None:
        return sectors

    for col in ("sector", "sequence_number"):
        if col in table.colnames:
            for value in table[col]:
                sector = parse_sector_value(value)
                if sector is not None:
                    sectors.add(sector)

    if "mission" in table.colnames:
        for value in table["mission"]:
            sector = parse_sector_value(value)
            if sector is not None:
                sectors.add(sector)

    return sectors


class MastTimeoutError(TimeoutError):
    pass


def run_with_timeout(label: str, timeout_seconds: float, func, *args, **kwargs):
    if timeout_seconds <= 0 or not hasattr(signal, "SIGALRM"):
        return func(*args, **kwargs)

    def _handler(signum, frame):
        raise MastTimeoutError(f"{label} timed out after {timeout_seconds:.1f}s")

    old_handler = signal.signal(signal.SIGALRM, _handler)
    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        return func(*args, **kwargs)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)


def fetch_available_sectors(tic: int, timeout_seconds: float = DEFAULT_TIMEOUT) -> set[int]:
    result = run_with_timeout(
        f"MAST TIC {tic}",
        timeout_seconds,
        search_lightcurve,
        f"TIC {tic}",
        mission="TESS",
    )
    return extract_sectors(result)


def fetch_available_sectors_with_retry(tic: int, retries: int, retry_sleep: float, timeout_seconds: float) -> set[int]:
    attempts = max(1, int(retries) + 1)
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fetch_available_sectors(tic, timeout_seconds=timeout_seconds)
        except Exception as exc:
            last_exc = exc
            if attempt >= attempts:
                break
            delay = max(0.0, float(retry_sleep)) * attempt
            print(f"TIC {tic}: retry {attempt}/{attempts - 1} after {type(exc).__name__}; sleep={delay:.1f}s")
            if delay:
                time.sleep(delay)
    assert last_exc is not None
    raise last_exc


def candidate_rows(conn: sqlite3.Connection, limit: int | None, tic: int | None) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    if tic is not None:
        return conn.execute(
            f"SELECT TIC, status FROM {TABLE_CANDIDATES} WHERE TIC = ?",
            (tic,),
        ).fetchall()

    placeholders = ",".join("?" for _ in DEFAULT_SOURCE_STATUSES)
    sql = (
        f"SELECT TIC, status FROM {TABLE_CANDIDATES} "
        f"WHERE COALESCE(status, 'CANDIDATE') IN ({placeholders}) "
        f"ORDER BY TIC"
    )
    if limit:
        sql += f" LIMIT {int(limit)}"
    return conn.execute(sql, DEFAULT_SOURCE_STATUSES).fetchall()


def mark_recheck_new_sector(conn: sqlite3.Connection, tic: int) -> None:
    for table in (TABLE_CANDIDATES, TABLE_RAW, TABLE_ACTIVE):
        conn.execute(
            f"""
            UPDATE {table}
            SET status='RECHECK_NEW_SECTOR'
            WHERE TIC=?
              AND COALESCE(status, '') NOT IN ('FP', 'FP_ART', 'FALSE_POSITIVE')
            """,
            (tic,),
        )
    conn.execute(f"UPDATE {TABLE_RAW} SET checked_at=datetime('now') WHERE TIC=?", (tic,))
    conn.execute(f"UPDATE {TABLE_ACTIVE} SET checked_at=datetime('now') WHERE TIC=?", (tic,))


def save_inventory(
    conn: sqlite3.Connection,
    tic: int,
    source_status: str,
    current: set[int],
    mark: bool,
) -> tuple[bool, str]:
    now = datetime.now().isoformat(timespec="seconds")
    old = conn.execute(
        f"SELECT sectors_text FROM {TABLE_SECTORS} WHERE TIC=?",
        (tic,),
    ).fetchone()
    previous = {int(s) for s in old[0].split(",") if s.strip().isdigit()} if old else set()
    new_sectors = current - previous
    changed = bool(previous and new_sectors)
    new_sectors_text = sector_text(new_sectors) if changed else ""

    conn.execute(
        f"""
        INSERT INTO {TABLE_SECTORS}
          (TIC, sectors_text, sector_count, previous_sectors_text,
           previous_sector_count, new_sectors_text, source_status,
           last_checked_at, last_new_sector_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(TIC) DO UPDATE SET
          sectors_text=excluded.sectors_text,
          sector_count=excluded.sector_count,
          previous_sectors_text=excluded.previous_sectors_text,
          previous_sector_count=excluded.previous_sector_count,
          new_sectors_text=excluded.new_sectors_text,
          source_status=excluded.source_status,
          last_checked_at=excluded.last_checked_at,
          last_new_sector_at=COALESCE(excluded.last_new_sector_at, {TABLE_SECTORS}.last_new_sector_at)
        """,
        (
            tic,
            sector_text(current),
            len(current),
            sector_text(previous),
            len(previous),
            new_sectors_text,
            source_status,
            now,
            now if changed else None,
        ),
    )
    if changed and mark and source_status not in PROTECTED_STATUSES:
        mark_recheck_new_sector(conn, tic)
    return changed, sector_text(new_sectors)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check known candidates for new TESS sectors.")
    parser.add_argument("--tic", type=int, help="Check only one TIC.")
    parser.add_argument("--limit", type=int, help="Limit number of candidates checked.")
    parser.add_argument("--sleep", type=float, default=0.2, help="Delay between MAST queries.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Number of TICs per MAST request block.")
    parser.add_argument("--batch-sleep", type=float, default=DEFAULT_BATCH_SLEEP, help="Delay after each MAST request block.")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help="Retries per TIC after transient MAST/network errors.")
    parser.add_argument("--retry-sleep", type=float, default=DEFAULT_RETRY_SLEEP, help="Base retry delay; retry N sleeps N*delay seconds.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="Timeout in seconds per MAST TIC lookup.")
    parser.add_argument("--dry-run", action="store_true", help="Do not write DB changes.")
    parser.add_argument("--no-mark", action="store_true", help="Record sectors but do not mark RECHECK_NEW_SECTOR.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    conn = connect_db()
    try:
        ensure_table(conn)
        rows = candidate_rows(conn, args.limit, args.tic)
        checked = 0
        changed = 0
        errors = 0
        batch_size = max(1, int(args.batch_size or 1))
        total_batches = max(1, math.ceil(len(rows) / batch_size))

        for batch_start in range(0, len(rows), batch_size):
            batch = rows[batch_start : batch_start + batch_size]
            batch_index = batch_start // batch_size + 1
            print(f"batch {batch_index}/{total_batches}: TICs {batch_start + 1}-{batch_start + len(batch)} of {len(rows)}")

            for row in batch:
                tic = int(row["TIC"])
                status = str(row["status"] or "CANDIDATE")
                try:
                    print(f"TIC {tic}: query MAST timeout={args.timeout:.1f}s retries={args.retries}", flush=True)
                    sectors = fetch_available_sectors_with_retry(tic, args.retries, args.retry_sleep, args.timeout)
                    checked += 1
                    if args.dry_run:
                        old = conn.execute(
                            f"SELECT sectors_text FROM {TABLE_SECTORS} WHERE TIC=?",
                            (tic,),
                        ).fetchone()
                        previous = {int(s) for s in old[0].split(",") if s.strip().isdigit()} if old else set()
                        new_sectors = sectors - previous
                        is_changed = bool(previous and new_sectors)
                        new_text = sector_text(new_sectors)
                    else:
                        is_changed, new_text = save_inventory(
                            conn,
                            tic,
                            status,
                            sectors,
                            mark=not args.no_mark,
                        )
                        conn.commit()
                    if is_changed:
                        changed += 1
                        print(f"TIC {tic}: NEW_SECTORS {new_text} status={status}")
                    elif checked % 50 == 0:
                        print(f"checked {checked}/{len(rows)}")
                except Exception as exc:
                    errors += 1
                    print(f"TIC {tic}: ERROR {type(exc).__name__}: {exc}")
                if args.sleep:
                    time.sleep(args.sleep)

            if batch_index < total_batches and args.batch_sleep:
                print(f"batch {batch_index}/{total_batches}: sleep {args.batch_sleep:.1f}s before next MAST block")
                time.sleep(args.batch_sleep)

        print(f"Done. checked={checked} new_sector_targets={changed} errors={errors}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
