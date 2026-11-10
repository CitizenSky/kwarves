#!/usr/bin/env python3
"""Poll public TESS light curves and Gaia catalogue releases once per run."""

from __future__ import annotations

import argparse
import fcntl
import json
import re
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import urlopen
from xml.etree import ElementTree

from check_new_tess_sectors import (
    DB_PATH, PROJECT_ROOT, TABLE_SECTORS, candidate_rows, connect_db,
    ensure_table, save_inventory,
)


SCRIPT_ROOT = PROJECT_ROOT / "scripts"
STATE_PATH = PROJECT_ROOT / "logs" / "astro-data-watcher.json"
MAST_URL = "https://mast.stsci.edu/api/v0/invoke"
GAIA_URLS = (
    "https://gea.esac.esa.int/tap-server/tap/sync",
    "https://gaia.aip.de/tap/sync",
)
GAIA_BULK_URL = "https://gaia.eu-1.cdn77-storage.com/?prefix=Gaia%2F&delimiter=%2F"
PROJECT_GAIA_RELEASE = 3


def log(message: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {message}", flush=True)


def fetch_tess_sectors(tics: list[int]) -> dict[int, set[int]]:
    sectors: dict[int, set[int]] = {tic: set() for tic in tics}
    for start in range(0, len(tics), 100):
        batch = {str(tic) for tic in tics[start : start + 100]}
        filters = {
            "obs_collection": ["TESS"],
            "dataproduct_type": ["timeseries"],
            "dataRights": ["PUBLIC"],
            "target_name": sorted(batch),
        }
        request = {
            "service": "Mast.Caom.Filtered",
            "params": {
                "columns": "target_name,sequence_number,obs_id",
                "filters": [{"paramName": name, "values": values} for name, values in filters.items()],
            },
            "format": "json",
            "pagesize": 2000,
            "page": 1,
        }
        while True:
            data = urlencode({"request": json.dumps(request)}).encode()
            with urlopen(MAST_URL, data=data, timeout=60) as response:
                result = json.load(response)
            if result.get("status") != "COMPLETE" or not isinstance(result.get("data"), list):
                raise RuntimeError(f"MAST query failed: {result.get('msg') or result.get('status')}")
            for row in result["data"]:
                tic = str(row["target_name"])
                # SPOC observation IDs identify pipeline target light curves, not FFIs.
                if tic in batch and re.fullmatch(r"tess\d+-s\d+-\d+-\d+-[as](?:_fast)?", row["obs_id"] or ""):
                    sectors[int(tic)].add(int(row["sequence_number"]))
            if request["page"] >= int(result["paging"]["pagesFiltered"]):
                break
            request["page"] += 1
    if not any(sectors.values()):
        raise RuntimeError("MAST returned no public target light curves for the candidate catalogue")
    return sectors


def fetch_gaia_release() -> int:
    query = "SELECT schema_name, table_name FROM TAP_SCHEMA.tables WHERE table_name LIKE '%gaia_source'"
    params = urlencode({"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "votable", "QUERY": query})
    for url in GAIA_URLS:
        try:
            with urlopen(f"{url}?{params}", timeout=20) as response:
                root = ElementTree.parse(response).getroot()
            statuses = [node.get("value") for node in root.findall(".//{*}INFO[@name='QUERY_STATUS']")]
            if not statuses or any(status != "OK" for status in statuses):
                raise RuntimeError(f"invalid Gaia TAP response: {statuses}")
            releases = []
            for row in root.findall(".//{*}TR"):
                schema, table = [cell.text or "" for cell in row.findall("{*}TD")]
                match = re.fullmatch(r"gaiadr(\d+)", schema.lower())
                if match and table.lower() in {"gaia_source", f"{schema.lower()}.gaia_source"}:
                    releases.append(int(match.group(1)))
            if not releases or max(releases) < PROJECT_GAIA_RELEASE:
                raise RuntimeError("no numbered Gaia source catalogues in TAP metadata")
            return max(releases)
        except (OSError, ValueError, ElementTree.ParseError, RuntimeError) as exc:
            log(f"Gaia {url}: {exc}")
    # The public ESA download directory remains usable when TAP jobs are unavailable.
    try:
        with urlopen(GAIA_BULK_URL, timeout=15) as response:
            root = ElementTree.parse(response).getroot()
        if root.findtext("{*}IsTruncated") != "false":
            raise RuntimeError("incomplete Gaia bulk catalogue listing")
        releases = []
        for prefix in root.findall("{*}CommonPrefixes/{*}Prefix"):
            match = re.fullmatch(r"Gaia/gdr(\d+)/", prefix.text or "")
            if match:
                releases.append(int(match.group(1)))
        if not releases or max(releases) < PROJECT_GAIA_RELEASE:
            raise RuntimeError("no numbered Gaia releases in the bulk directory")
        log("Gaia: read release metadata from the ESA bulk directory")
        return max(releases)
    except (OSError, ElementTree.ParseError, RuntimeError) as exc:
        log(f"Gaia bulk directory: {exc}")
    raise RuntimeError("No Gaia catalogue endpoint could be read")


def save_state(state: dict) -> None:
    temporary_path = STATE_PATH.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(STATE_PATH)


def tess_updates(conn: sqlite3.Connection, sectors: dict[int, set[int]]) -> list[tuple[int, str, set[int]]]:
    has_inventory = conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (TABLE_SECTORS,)).fetchone()
    existing = dict(conn.execute(f"SELECT TIC, sectors_text FROM {TABLE_SECTORS}")) if has_inventory else {}
    updates = []
    for row in candidate_rows(conn, limit=None, tic=None):
        tic = int(row["TIC"])
        if tic not in sectors:
            continue
        previous = {int(sector) for sector in existing.get(tic, "").split(",") if sector.strip().isdigit()}
        available = sectors[tic]
        if tic not in existing or available - previous:
            updates.append((tic, str(row["status"] or "CANDIDATE"), previous | available))
    return updates


def check_tess(state: dict, check_only: bool) -> None:
    with closing(sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)) as db:
        tics = [int(row["TIC"]) for row in candidate_rows(db, limit=None, tic=None)]
        sectors = fetch_tess_sectors(tics)
        updates = tess_updates(db, sectors)
    log(f"MAST checked {len(tics)} TICs; {len(updates)} inventory entries to update")
    if check_only:
        return
    if updates:
        state["pending_tess_publish"] = True
        save_state(state)
        with closing(connect_db()) as db, db:
            ensure_table(db)
            # Re-read under the write lock, since the standalone checker can also update the inventory.
            db.execute("BEGIN IMMEDIATE")
            for tic, status, available in tess_updates(db, sectors):
                changed, added = save_inventory(db, tic, status, available, mark=True)
                if changed:
                    log(f"TIC {tic}: new public sectors {added}")
    if state.get("pending_tess_publish"):
        subprocess.run([sys.executable, "main/build_candidate_matrix.py", "--no-color-index"], cwd=SCRIPT_ROOT, check=True)
        subprocess.run(
            [sys.executable, "dashboard/auto_update_and_publish.py", "--from-watcher"],
            cwd=SCRIPT_ROOT, check=True,
        )
        state["pending_tess_publish"] = False
        save_state(state)


def check_gaia(state: dict, check_only: bool) -> None:
    release = fetch_gaia_release()
    log(f"Newest public Gaia source catalogue: DR{release}")
    if release > PROJECT_GAIA_RELEASE:
        log(f"Gaia DR{release} is available. Import requires a release-specific cross-match from DR{PROJECT_GAIA_RELEASE}.")
        if not check_only and release > state.get("gaia_release_for_review", PROJECT_GAIA_RELEASE):
            state["gaia_release_for_review"] = release
            save_state(state)


def poll(state: dict, check_only: bool) -> int:
    failed = False
    for check in (check_gaia, check_tess):
        try:
            check(state, check_only)
        except (OSError, ValueError, RuntimeError, sqlite3.Error, subprocess.CalledProcessError) as exc:
            log(f"{check.__name__} failed: {exc}")
            failed = True
    return int(failed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", help="Read the archives and local inventory without changing or publishing anything.")
    args = parser.parse_args()
    if args.check_only:
        return poll({}, check_only=True)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STATE_PATH.with_suffix(".lock").open("a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("Another poll is already running")
            return 0
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except FileNotFoundError:
            state = {}
        return poll(state, check_only=False)


if __name__ == "__main__":
    raise SystemExit(main())
