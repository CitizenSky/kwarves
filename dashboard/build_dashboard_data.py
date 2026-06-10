#!/usr/bin/env python3
"""Build the static data bundle used by dashboard/index.html."""

from __future__ import annotations

import csv
import argparse
import json
import math
import os
import re
import signal
import shutil
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(os.environ.get("ASTRO_PROJECT_ROOT", "/Users/koni/astro_projects"))
SCRIPT_ROOT = PROJECT_ROOT / "scripts"
DASHBOARD_DIR = SCRIPT_ROOT / "dashboard"
LIGHTCURVE_WEB_DIR = DASHBOARD_DIR / "lightcurves"
DB_PATH = PROJECT_ROOT / "database" / "planet_hunter.db"
VETTING_REPORTS_DIR = PROJECT_ROOT / "vetting_reports"
MANIFEST_PATH = PROJECT_ROOT / "level0_lichtjahre_10ly_bis_500" / "manifest_all_candidates_by_distance.csv"
LEVEL5_SINGLE_TRANSIT_ROOT = PROJECT_ROOT / "level5_detailvalidierung" / "level5_02_einzeltransit_plots"
OUT_PATH = DASHBOARD_DIR / "dashboard-data.js"
CANDIDATE_SUMMARY_PATH = DASHBOARD_DIR / "candidates-summary.json"
CANDIDATE_DETAILS_DIR = DASHBOARD_DIR / "candidate-details"
GAIA_CACHE_PATH = DASHBOARD_DIR / "gaia_coordinates_cache.csv"
GAIA_FETCH_BATCH_SIZE = int(os.environ.get("GAIA_FETCH_BATCH_SIZE", "350"))
GAIA_FETCH_ENABLED = os.environ.get("GAIA_FETCH_ENABLED", "1").strip() not in {"0", "false", "False"}
AUTO_TESS_UPDATE_ENABLED = os.environ.get("KWARVES_AUTO_TESS_UPDATE", "1").strip() not in {"0", "false", "False"}
AUTO_TESS_MAX_AGE_HOURS = float(os.environ.get("KWARVES_AUTO_TESS_MAX_AGE_HOURS", "18"))
AUTO_TESS_SLEEP = float(os.environ.get("KWARVES_AUTO_TESS_SLEEP", "0.2"))
AUTO_TESS_BATCH_SIZE = int(os.environ.get("KWARVES_MAST_BATCH_SIZE", "20"))
AUTO_TESS_BATCH_SLEEP = float(os.environ.get("KWARVES_MAST_BATCH_SLEEP", "15"))
AUTO_TESS_RETRIES = int(os.environ.get("KWARVES_MAST_RETRIES", "2"))
AUTO_TESS_RETRY_SLEEP = float(os.environ.get("KWARVES_MAST_RETRY_SLEEP", "5"))
AUTO_TESS_TIMEOUT = float(os.environ.get("KWARVES_MAST_TIMEOUT", "45"))
AUTO_UPDATE_COMMAND_TIMEOUT = float(os.environ.get("KWARVES_AUTO_UPDATE_COMMAND_TIMEOUT", "900"))
MATRIX_BUILD_TIMEOUT = float(os.environ.get("KWARVES_MATRIX_BUILD_TIMEOUT", "900"))
GAIA_API_TIMEOUT = float(os.environ.get("KWARVES_GAIA_API_TIMEOUT", "45"))

# Pipeline thresholds (loaded from shared config file)
_PIPELINE_CFG: dict[str, Any] | None = None
def _load_pipeline_config() -> dict[str, Any]:
    global _PIPELINE_CFG
    if _PIPELINE_CFG is not None:
        return _PIPELINE_CFG
    cfg_path = DASHBOARD_DIR / "config" / "pipeline_thresholds.json"
    with open(cfg_path) as f:
        _PIPELINE_CFG = json.load(f)
    return _PIPELINE_CFG

TESS_SECTOR_SCHEDULE = [
    {"sector": 97, "start": "2025-09-15", "end": "2025-11-09", "arrangement": "Suedpol (4 Orbits)"},
    {"sector": 98, "start": "2025-11-09", "end": "2026-01-05", "arrangement": "Suedpol (4 Orbits)"},
    {"sector": 99, "start": "2026-01-05", "end": "2026-02-02", "arrangement": "Suedpol, 40 Grad Roll/Shift"},
    {"sector": 100, "start": "2026-02-02", "end": "2026-03-01", "arrangement": "Suedpol, 40 Grad Roll/Shift"},
    {"sector": 101, "start": "2026-03-01", "end": "2026-03-27", "arrangement": "Suedpol, 40 Grad Roll/Shift"},
    {"sector": 102, "start": "2026-03-27", "end": "2026-04-21", "arrangement": "Suedpol, 40 Grad Roll/Shift"},
    {"sector": 103, "start": "2026-04-21", "end": "2026-05-17", "arrangement": "Suedpol, 40 Grad Roll/Shift"},
    {"sector": 104, "start": "2026-05-17", "end": "2026-06-13", "arrangement": "Suedpol, 40 Grad Roll/Shift"},
    {"sector": 105, "start": "2026-06-13", "end": "2026-07-11", "arrangement": "Suedpol, 40 Grad Roll/Shift"},
    {"sector": 106, "start": "2026-07-11", "end": "2026-08-09", "arrangement": "Suedpol, 40 Grad Roll/Shift"},
    {"sector": 107, "start": "2026-08-09", "end": "2026-09-07", "arrangement": "Suedpol, 40 Grad Roll/Shift"},
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build dashboard-data.js with optional automatic TESS refresh and matrix rebuild.")
    parser.add_argument("--limit", type=int, default=None, help="Limit dashboard candidates built from the manifest.")
    parser.add_argument("--tic", type=int, default=None, help="Build only one dashboard candidate.")
    parser.add_argument("--no-auto-update", action="store_true", help="Skip automatic TESS sector refresh and matrix rebuild.")
    parser.add_argument("--skip-mast", action="store_true", help="Alias for --no-auto-update; avoids MAST calls during this dashboard build.")
    parser.add_argument("--offline-cache", action="store_true", help="Use local DB/cache only; skips MAST auto-update and Gaia network fetches.")
    parser.add_argument("--force-auto-update", action="store_true", help="Run TESS refresh even when inventory is still fresh.")
    parser.add_argument("--auto-update-limit", type=int, default=None, help="Limit candidates checked against MAST during automatic refresh.")
    parser.add_argument("--auto-update-sleep", type=float, default=AUTO_TESS_SLEEP, help="Delay between MAST queries during automatic refresh.")
    parser.add_argument("--auto-update-batch-size", type=int, default=AUTO_TESS_BATCH_SIZE, help="Number of MAST TIC queries per automatic refresh block.")
    parser.add_argument("--auto-update-batch-sleep", type=float, default=AUTO_TESS_BATCH_SLEEP, help="Delay between automatic MAST refresh blocks.")
    parser.add_argument("--auto-update-retries", type=int, default=AUTO_TESS_RETRIES, help="Retries per TIC during automatic MAST refresh.")
    parser.add_argument("--auto-update-retry-sleep", type=float, default=AUTO_TESS_RETRY_SLEEP, help="Base retry delay for automatic MAST refresh.")
    parser.add_argument("--auto-update-timeout", type=float, default=AUTO_TESS_TIMEOUT, help="Timeout in seconds for each MAST TIC lookup.")
    parser.add_argument("--auto-update-command-timeout", type=float, default=AUTO_UPDATE_COMMAND_TIMEOUT, help="Timeout in seconds for the sector refresh subprocess.")
    parser.add_argument("--matrix-build-timeout", type=float, default=MATRIX_BUILD_TIMEOUT, help="Timeout in seconds for the candidate matrix rebuild subprocess.")
    parser.add_argument("--gaia-api-timeout", type=float, default=GAIA_API_TIMEOUT, help="Timeout in seconds for each Gaia API chunk.")
    parser.add_argument("--progress-every", type=int, default=25, help="Print dashboard build progress every N candidates.")
    parser.add_argument("--no-sector-mark", action="store_true", help="Record new sectors but do not mark candidates RECHECK_NEW_SECTOR.")
    return parser.parse_args()


def load_existing_dashboard_data(path: Path = OUT_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    match = re.search(r"window\.ASTRO_DASHBOARD_DATA\s*=\s*(\{.*\});?\s*$", text, re.S)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except Exception:
        return {}


def existing_candidate_index(payload: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {
        safe_int(candidate.get("tic")): candidate
        for candidate in payload.get("candidates", [])
        if safe_int(candidate.get("tic"))
    }


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"none", "null", "nan"} else text


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    mask = getattr(value, "mask", None)
    if mask is True:
        return None
    if mask is not None:
        try:
            if bool(mask):
                return None
        except Exception:
            pass
    try:
        number = float(value)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def safe_int_or_none(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(float(value))
    except Exception:
        return None


def safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def parse_gaia_source_id(value: Any) -> int | None:
    text = clean_text(value)
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None
    try:
        source_id = int(digits)
    except Exception:
        return None
    return source_id if source_id > 0 else None


def load_gaia_cache(path: Path = GAIA_CACHE_PATH) -> dict[int, dict[str, float | None]]:
    if not path.exists():
        return {}
    cache: dict[int, dict[str, float | None]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            source_id = parse_gaia_source_id(row.get("source_id"))
            if source_id is None:
                continue
            cache[source_id] = {
                "ra": safe_float(row.get("ra_deg")),
                "dec": safe_float(row.get("dec_deg")),
                "parallax": safe_float(row.get("parallax_mas")),
                "pmra": safe_float(row.get("pmra_masyr")),
                "pmdec": safe_float(row.get("pmdec_masyr")),
            }
    return cache


def save_gaia_cache(cache: dict[int, dict[str, float | None]], path: Path = GAIA_CACHE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["source_id", "ra_deg", "dec_deg", "parallax_mas", "pmra_masyr", "pmdec_masyr"],
        )
        writer.writeheader()
        for source_id in sorted(cache):
            entry = cache[source_id] or {}
            writer.writerow(
                {
                    "source_id": source_id,
                    "ra_deg": entry.get("ra"),
                    "dec_deg": entry.get("dec"),
                    "parallax_mas": entry.get("parallax"),
                    "pmra_masyr": entry.get("pmra"),
                    "pmdec_masyr": entry.get("pmdec"),
                }
            )


class ApiTimeoutError(TimeoutError):
    pass


def run_with_timeout(label: str, timeout_seconds: float, func, *args, **kwargs):
    if timeout_seconds <= 0 or not hasattr(signal, "SIGALRM"):
        return func(*args, **kwargs)

    def _handler(signum, frame):
        raise ApiTimeoutError(f"{label} timed out after {timeout_seconds:.1f}s")

    old_handler = signal.signal(signal.SIGALRM, _handler)
    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        return func(*args, **kwargs)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)


def fetch_gaia_coordinates(source_ids: list[int], timeout_seconds: float = GAIA_API_TIMEOUT, offline_cache: bool = False) -> dict[int, dict[str, float | None]]:
    if offline_cache:
        print("[gaia] offline-cache enabled; using cached/local coordinates only", flush=True)
        return {}
    if not source_ids or not GAIA_FETCH_ENABLED:
        return {}
    try:
        from astropy.table import Table
        from astroquery.gaia import Gaia
    except Exception as exc:
        print(f"[gaia] astroquery unavailable, skipping fetch: {exc}")
        return {}

    Gaia.ROW_LIMIT = -1
    unique_ids = sorted({int(source_id) for source_id in source_ids if int(source_id) > 0})
    result: dict[int, dict[str, float | None]] = {}
    batch_size = max(25, GAIA_FETCH_BATCH_SIZE)

    def query_table(table_name: str, ids: list[int]) -> dict[int, dict[str, float | None]]:
        if not ids:
            return {}
        query = f"""
            SELECT g.source_id, g.ra, g.dec, g.parallax, g.pmra, g.pmdec
              FROM {table_name} AS g
              JOIN tap_upload.src_ids AS u
                ON g.source_id = u.source_id
        """
        fetched: dict[int, dict[str, float | None]] = {}
        upload = Table({"source_id": ids})
        job = run_with_timeout(
            f"Gaia {table_name}",
            timeout_seconds,
            Gaia.launch_job_async,
            query=query,
            upload_resource=upload,
            upload_table_name="src_ids",
            verbose=False,
        )
        rows = run_with_timeout(f"Gaia results {table_name}", timeout_seconds, job.get_results)
        for row in rows:
            source_id = parse_gaia_source_id(row["source_id"])
            if source_id is None:
                continue
            fetched[source_id] = {
                "ra": safe_float(row["ra"]),
                "dec": safe_float(row["dec"]),
                "parallax": safe_float(row["parallax"]),
                "pmra": safe_float(row["pmra"]),
                "pmdec": safe_float(row["pmdec"]),
            }
        return fetched

    for index in range(0, len(unique_ids), batch_size):
        chunk = unique_ids[index : index + batch_size]
        chunk_index = index // batch_size + 1
        resolved: dict[int, dict[str, float | None]] = {}
        try:
            resolved.update(query_table("gaiadr3.gaia_source", chunk))
        except Exception as exc:
            print(f"[gaia] DR3 chunk {chunk_index} failed ({len(chunk)} ids): {exc}")
        missing_ids = [source_id for source_id in chunk if source_id not in resolved]
        if missing_ids:
            try:
                resolved.update(query_table("gaiadr2.gaia_source", missing_ids))
            except Exception as exc:
                print(f"[gaia] DR2 fallback chunk {chunk_index} failed ({len(missing_ids)} ids): {exc}")
        result.update(resolved)
        print(f"[gaia] fetched {len(resolved)} rows (chunk {chunk_index}, total cached {len(result)}/{len(unique_ids)})")
    return result


def parse_sector_text(value: Any) -> list[int]:
    text = clean_text(value)
    if not text:
        return []
    sectors: list[int] = []
    seen: set[int] = set()
    for raw_token in re.split(r"[,\s;/|]+", text):
        token = raw_token.strip()
        if not token:
            continue
        if "-" in token:
            left, _, right = token.partition("-")
            try:
                start = int(left)
                end = int(right)
            except Exception:
                continue
            if end < start:
                start, end = end, start
            for number in range(start, min(end, start + 200) + 1):
                if number > 0 and number not in seen:
                    sectors.append(number)
                    seen.add(number)
            continue
        try:
            number = int(token)
        except Exception:
            continue
        if number > 0 and number not in seen:
            sectors.append(number)
            seen.add(number)
    return sectors


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def sector_inventory_is_stale(max_age_hours: float = AUTO_TESS_MAX_AGE_HOURS) -> bool:
    if not DB_PATH.exists():
        return False
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=30)
        try:
            if not table_exists(conn, "tess_sector_inventory"):
                return True
            row = conn.execute("SELECT MAX(last_checked_at) FROM tess_sector_inventory").fetchone()
            stamp = clean_text(row[0] if row else "")
            if not stamp:
                return True
            last = datetime.fromisoformat(stamp)
            return (datetime.now() - last).total_seconds() > max_age_hours * 3600
        finally:
            conn.close()
    except Exception as exc:
        print(f"[auto-update] could not inspect tess_sector_inventory: {exc}")
        return False


def run_command(
    command: list[str],
    label: str,
    *,
    timeout_seconds: float,
    retries: int = 0,
    retry_sleep: float = 0.0,
) -> None:
    attempts = max(1, int(retries) + 1)
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        started = time.monotonic()
        try:
            print(
                f"[auto-update] {label}: attempt {attempt}/{attempts}, timeout={timeout_seconds:.0f}s: {' '.join(command)}",
                flush=True,
            )
            subprocess.run(command, cwd=SCRIPT_ROOT, check=True, timeout=timeout_seconds if timeout_seconds > 0 else None)
            elapsed = time.monotonic() - started
            print(f"[auto-update] {label}: done in {elapsed:.1f}s", flush=True)
            return
        except subprocess.TimeoutExpired as exc:
            last_exc = exc
            print(f"[auto-update] {label}: TIMEOUT after {timeout_seconds:.0f}s", flush=True)
        except subprocess.CalledProcessError as exc:
            last_exc = exc
            print(f"[auto-update] {label}: FAILED exit={exc.returncode}", flush=True)
        if attempt < attempts:
            delay = max(0.0, float(retry_sleep)) * attempt
            print(f"[auto-update] {label}: retrying after {delay:.1f}s", flush=True)
            if delay:
                time.sleep(delay)
    raise RuntimeError(f"{label} failed after {attempts} attempt(s): {last_exc}")


def run_auto_update(args: argparse.Namespace) -> bool:
    if args.skip_mast or args.offline_cache:
        args.no_auto_update = True
    if args.no_auto_update or not AUTO_TESS_UPDATE_ENABLED:
        print("[auto-update] skipped")
        return False
    if not args.force_auto_update and not sector_inventory_is_stale():
        print("[auto-update] tess_sector_inventory fresh; rebuilding dashboard only")
        return False

    sector_cmd = [
        sys.executable,
        str(SCRIPT_ROOT / "main" / "check_new_tess_sectors.py"),
        "--sleep",
        str(args.auto_update_sleep),
        "--batch-size",
        str(args.auto_update_batch_size),
        "--batch-sleep",
        str(args.auto_update_batch_sleep),
        "--retries",
        str(args.auto_update_retries),
        "--retry-sleep",
        str(args.auto_update_retry_sleep),
        "--timeout",
        str(args.auto_update_timeout),
    ]
    update_limit = args.auto_update_limit if args.auto_update_limit is not None else args.limit
    if args.tic:
        sector_cmd.extend(["--tic", str(args.tic)])
    elif update_limit:
        sector_cmd.extend(["--limit", str(update_limit)])
    if args.no_sector_mark:
        sector_cmd.append("--no-mark")

    matrix_cmd = [sys.executable, str(SCRIPT_ROOT / "main" / "build_candidate_matrix.py")]
    if args.tic:
        matrix_cmd.extend(["--tic", str(args.tic)])
    elif args.limit:
        matrix_cmd.extend(["--limit", str(args.limit)])

    run_command(
        sector_cmd,
        "refresh TESS sector inventory",
        timeout_seconds=args.auto_update_command_timeout,
        retries=args.auto_update_retries,
        retry_sleep=args.auto_update_retry_sleep,
    )
    run_command(
        matrix_cmd,
        "rebuild candidate matrix",
        timeout_seconds=args.matrix_build_timeout,
        retries=0,
        retry_sleep=0,
    )
    return True


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def sector_phase(sector: int) -> int:
    return ((int(sector) - 1) % 13) + 1


def build_tess_state(today: date | None = None) -> dict[str, Any]:
    today = today or datetime.now().date()
    sectors: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    next_sector: dict[str, Any] | None = None
    for item in TESS_SECTOR_SCHEDULE:
        start = parse_date(item["start"])
        end = parse_date(item["end"])
        phase = "completed"
        if today < start:
            phase = "planned"
        elif start <= today <= end:
            phase = "running"
        row = {**item, "phase": phase}
        sectors.append(row)
        if phase == "running":
            current = row
        elif phase == "planned" and next_sector is None:
            next_sector = row
    return {
        "today": today.isoformat(),
        "sectors": sectors,
        "currentSector": current,
        "nextSector": next_sector,
        "dataReleaseLagDays": 21,
    }


def estimate_data_available(sector: dict[str, Any] | None, lag_days: int = 21) -> str:
    if not sector:
        return ""
    return (parse_date(sector["end"]) + timedelta(days=lag_days)).isoformat()


def planned_sectors_for_candidate(observed_sectors: list[int], tess_state: dict[str, Any]) -> list[dict[str, Any]]:
    observed_set = set(observed_sectors)
    phase_set = {sector_phase(sector) for sector in observed_set}
    planned: list[dict[str, Any]] = []
    for sector in tess_state["sectors"]:
        sector_id = int(sector["sector"])
        if sector_id in observed_set or sector_phase(sector_id) in phase_set:
            planned.append(sector)
    return planned


def recheck_model(observed_sectors: list[int], tess_state: dict[str, Any]) -> dict[str, Any]:
    planned = planned_sectors_for_candidate(observed_sectors, tess_state)
    current_sector = tess_state.get("currentSector")
    current_id = int(current_sector["sector"]) if current_sector else None
    live = next((item for item in planned if int(item["sector"]) == current_id and item["phase"] == "running"), None)
    upcoming = [item for item in planned if item["phase"] == "planned"]
    completed = [item for item in planned if item["phase"] == "completed"]
    if live:
        status = "LIVE_NOW"
        focus = live
    elif upcoming:
        status = "UPCOMING"
        focus = upcoming[0]
    elif completed:
        status = "WAITING_DATA"
        focus = completed[-1]
    else:
        status = "NO_PLANNED_RECHECK"
        focus = None
    return {
        "plannedSectors": [int(item["sector"]) for item in planned],
        "plannedSectorDetails": [
            {
                "sector": int(item["sector"]),
                "start": item["start"],
                "end": item["end"],
                "phase": item["phase"],
            }
            for item in planned
        ],
        "currentSector": int(live["sector"]) if live else None,
        "nextPlannedSector": int(upcoming[0]["sector"]) if upcoming else None,
        "latestPlannedSector": int(planned[-1]["sector"]) if planned else None,
        "recheckStatus": status,
        "estimatedDataAvailable": estimate_data_available(focus, tess_state.get("dataReleaseLagDays", 21)) if focus else "",
    }


def rel_from_dashboard(path: Path) -> str:
    return os.path.relpath(path, DASHBOARD_DIR)


def sync_curve_asset(source_path: Path, tic: int) -> Path | None:
    """Ensure a deployable copy exists under dashboard/lightcurves."""
    try:
        LIGHTCURVE_WEB_DIR.mkdir(parents=True, exist_ok=True)
        target_path = LIGHTCURVE_WEB_DIR / f"TIC_{tic}.png"
        needs_copy = not target_path.exists()
        if not needs_copy:
            src_stat = source_path.stat()
            dst_stat = target_path.stat()
            needs_copy = src_stat.st_size != dst_stat.st_size or src_stat.st_mtime > dst_stat.st_mtime
        if needs_copy:
            shutil.copy2(source_path, target_path)
        return target_path
    except Exception:
        return None


def robust_median(values: list[float]) -> float | None:
    values = sorted(value for value in values if math.isfinite(value))
    if not values:
        return None
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2.0


def robust_scatter(values: list[float]) -> float | None:
    median = robust_median(values)
    if median is None:
        return None
    deviations = [abs(value - median) for value in values if math.isfinite(value)]
    mad = robust_median(deviations)
    if mad is not None and mad > 0:
        return 1.4826 * mad
    if len(values) >= 2:
        mean = sum(values) / len(values)
        return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))
    return 0.0


def classify_depth_stability_from_single_transits(stats: dict[str, Any]) -> str:
    visible_count = safe_int(stats.get("visible_transit_count"))
    min_ratio = safe_float(stats.get("min_depth_ratio"))
    depth_cv = safe_float(stats.get("depth_cv"))
    if visible_count < 2:
        return "INSUFFICIENT_TRANSITS"
    if min_ratio is not None and min_ratio < 0.35:
        return "UNSTABLE"
    if depth_cv is not None and depth_cv > 0.75:
        return "UNSTABLE"
    if min_ratio is not None and min_ratio < 0.6:
        return "BORDERLINE"
    if depth_cv is not None and depth_cv > 0.5:
        return "BORDERLINE"
    return "STABLE"


def single_transit_score_from_stats(stats: dict[str, Any]) -> float:
    stability = clean_text(stats.get("depth_stability")).upper()
    if stability == "STABLE":
        return 1.0
    if stability == "BORDERLINE":
        return 0.55
    if stability == "UNSTABLE":
        return 0.0
    return 0.5


def load_level5_single_transit_data(root: Path = LEVEL5_SINGLE_TRANSIT_ROOT) -> dict[int, dict[str, Any]]:
    """Load existing Level-5 single-transit CSV/PNG artifacts by TIC.

    This intentionally does not analyze light curves; it only persists already
    materialized Level-5 outputs.
    """
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
        try:
            with csv_path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    events.append({
                        "epoch": safe_int_or_none(row.get("epoch")),
                        "expected_time": safe_float(row.get("expected_time")),
                        "expectedTime": safe_float(row.get("expected_time")),
                        "depth_ppt": safe_float(row.get("depth_ppt")),
                        "depthPpt": safe_float(row.get("depth_ppt")),
                        "local_snr": safe_float(row.get("local_snr")),
                        "localSnr": safe_float(row.get("local_snr")),
                        "n_in": safe_int_or_none(row.get("n_in")),
                        "nIn": safe_int_or_none(row.get("n_in")),
                        "n_out": safe_int_or_none(row.get("n_out")),
                        "nOut": safe_int_or_none(row.get("n_out")),
                        "visible": safe_bool(row.get("visible")),
                    })
        except Exception:
            continue
        visible_events = [event for event in events if event.get("visible")]
        visible_depths = [event["depthPpt"] for event in visible_events if event.get("depthPpt") is not None]
        visible_snrs = [event["localSnr"] for event in visible_events if event.get("localSnr") is not None]
        median_depth = robust_median(visible_depths)
        depth_scatter = robust_scatter(visible_depths)
        depth_cv = (
            depth_scatter / median_depth
            if depth_scatter is not None and median_depth is not None and median_depth > 0
            else None
        )
        min_depth_ratio = (
            min(visible_depths) / median_depth
            if visible_depths and median_depth is not None and median_depth > 0
            else None
        )
        plot_path = csv_path.with_name(f"TIC_{tic}_single_transits.png")
        stats = {
            "source": "LEVEL5_SINGLE_TRANSITS",
            "csvPath": rel_from_dashboard(csv_path),
            "csv_path": rel_from_dashboard(csv_path),
            "csvAvailable": True,
            "csv_available": True,
            "individual_transit_count": len(events),
            "individualTransitCount": len(events),
            "visible_transit_count": len(visible_events),
            "visibleTransitCount": len(visible_events),
            "robust_transit_count": sum(1 for event in events if (event.get("localSnr") or 0) >= 5 and event.get("visible")),
            "robustTransitCount": sum(1 for event in events if (event.get("localSnr") or 0) >= 5 and event.get("visible")),
            "median_depth_ppt": round(median_depth, 5) if median_depth is not None else None,
            "medianDepthPpt": round(median_depth, 5) if median_depth is not None else None,
            "depth_scatter_ppt": round(depth_scatter, 5) if depth_scatter is not None else None,
            "depthScatterPpt": round(depth_scatter, 5) if depth_scatter is not None else None,
            "depth_cv": round(depth_cv, 5) if depth_cv is not None else None,
            "depthCv": round(depth_cv, 5) if depth_cv is not None else None,
            "median_single_transit_snr": round(robust_median(visible_snrs), 5) if visible_snrs else None,
            "medianSingleTransitSnr": round(robust_median(visible_snrs), 5) if visible_snrs else None,
            "min_depth_ratio": round(min_depth_ratio, 5) if min_depth_ratio is not None else None,
            "minDepthRatio": round(min_depth_ratio, 5) if min_depth_ratio is not None else None,
            "transit_visibility_ratio": round(len(visible_events) / len(events), 5) if events else None,
            "transitVisibilityRatio": round(len(visible_events) / len(events), 5) if events else None,
            "depth_stability": "",
            "depthStability": "",
            "plotAvailable": plot_path.exists(),
            "plot_available": plot_path.exists(),
            "plotStatus": "PLOT_AVAILABLE" if plot_path.exists() else "PLOT_NOT_AVAILABLE",
            "individualTransitPlotPath": rel_from_dashboard(plot_path) if plot_path.exists() else "",
            "individual_transit_plot_path": rel_from_dashboard(plot_path) if plot_path.exists() else "",
        }
        stability = classify_depth_stability_from_single_transits(stats)
        stats["depth_stability"] = stability
        stats["depthStability"] = stability
        data[tic] = {
            "statistics": stats,
            "events": events,
            "plotPath": stats["individualTransitPlotPath"],
            "plotStatus": stats["plotStatus"],
        }
    return data


def missing_level5_single_transit_data() -> dict[str, Any]:
    stats = {
        "source": "MISSING_LEVEL5_SINGLE_TRANSIT_CSV",
        "csvAvailable": False,
        "csv_available": False,
        "individual_transit_count": 0,
        "individualTransitCount": 0,
        "visible_transit_count": 0,
        "visibleTransitCount": 0,
        "robust_transit_count": 0,
        "robustTransitCount": 0,
        "median_depth_ppt": None,
        "medianDepthPpt": None,
        "depth_scatter_ppt": None,
        "depthScatterPpt": None,
        "depth_cv": None,
        "depthCv": None,
        "median_single_transit_snr": None,
        "medianSingleTransitSnr": None,
        "min_depth_ratio": None,
        "minDepthRatio": None,
        "transit_visibility_ratio": None,
        "transitVisibilityRatio": None,
        "depth_stability": "MISSING_LEVEL5_SINGLE_TRANSIT_CSV",
        "depthStability": "MISSING_LEVEL5_SINGLE_TRANSIT_CSV",
        "plotAvailable": False,
        "plot_available": False,
        "plotStatus": "PLOT_NOT_AVAILABLE",
        "individualTransitPlotPath": "",
        "individual_transit_plot_path": "",
    }
    return {"statistics": stats, "events": [], "plotPath": "", "plotStatus": "PLOT_NOT_AVAILABLE"}


def load_db_rows() -> tuple[
    dict[int, dict[str, Any]],
    dict[int, dict[str, Any]],
    dict[int, dict[str, Any]],
    dict[int, dict[str, Any]],
]:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=60)
    conn.row_factory = sqlite3.Row
    try:
        candidate_rows = conn.execute(
            """
            SELECT TIC, gaia_id, status, spc_class, is_fp, hz_class, hz_status, distance_ly,
                   teff, stellar_radius, best_period, planet_radius_earth, transit_snr, transit_count,
                   visible_transits, clean_sector_count, sector_count,
                   revisit_priority, next_recheck, notes
              FROM candidates_v2
            """
        ).fetchall()
        try:
            matrix_rows = conn.execute(
                """
                SELECT tic_id, n_transits, n_sectors, depth_ppt, duration_hours,
                       sap_pdcsap_match, odd_even_result, transit_shape,
                       transit_shape_score, transit_shape_source, shape_status, shape_snr,
                       measured_depth_ppt, secondary_depth_ppt, secondary_ratio_measured,
                       baseline_left_right_delta_ppt, oot_scatter_ppt, folded_lc_quality,
                       v_shape_score, shape_blocking_issues, shape_metrics_json,
                       depth_stability,
                       data_gap_risk, sector_edge_risk, secondary_eclipse, period_alias_risk,
                       rotation_risk, status, status_color, extended_class, evidence_score,
                       score_interpretation, decision_reason, next_step, visible_transits,
                       clean_sector_count
                  FROM candidate_matrix
                """
            ).fetchall()
        except sqlite3.OperationalError:
            matrix_rows = []
        try:
            sector_rows = conn.execute(
                """
                SELECT TIC, sectors_text, sector_count, previous_sectors_text, previous_sector_count,
                       new_sectors_text, source_status, last_checked_at, last_new_sector_at
                  FROM tess_sector_inventory
                """
            ).fetchall()
        except sqlite3.OperationalError:
            sector_rows = []
        try:
            coord_rows = conn.execute(
                """
                SELECT TIC, gaia_id, tic_ra, tic_dec, tic_plx, tic_pmra, tic_pmdec, target_ra, target_dec, target_parallax
                  FROM level4_hz_enriched_master
                """
            ).fetchall()
        except sqlite3.OperationalError:
            coord_rows = []
    finally:
        conn.close()
    return (
        {int(row["TIC"]): dict(row) for row in candidate_rows},
        {int(row["tic_id"]): dict(row) for row in matrix_rows},
        {
            int(row["TIC"]): {
                **dict(row),
                "sectors": parse_sector_text(row["sectors_text"]),
                "previousSectors": parse_sector_text(row["previous_sectors_text"]),
                "newSectors": parse_sector_text(row["new_sectors_text"]),
            }
            for row in sector_rows
        },
        {
            int(row["TIC"]): {
                "gaia_id": clean_text(row["gaia_id"]),
                "ra": safe_float(row["target_ra"]) if safe_float(row["target_ra"]) is not None else safe_float(row["tic_ra"]),
                "dec": safe_float(row["target_dec"]) if safe_float(row["target_dec"]) is not None else safe_float(row["tic_dec"]),
                "parallax": safe_float(row["target_parallax"]) if safe_float(row["target_parallax"]) is not None else safe_float(row["tic_plx"]),
                "pmra": safe_float(row["tic_pmra"]),
                "pmdec": safe_float(row["tic_pmdec"]),
            }
            for row in coord_rows
        },
    )


def load_full_vetting_reports() -> dict[int, dict[str, Any]]:
    reports: dict[int, dict[str, Any]] = {}
    if not VETTING_REPORTS_DIR.exists():
        return reports

    def report_rank(payload: dict[str, Any]) -> tuple[float, int, float]:
        return (
            safe_float(payload.get("evidence_score")) or 0.0,
            safe_int(payload.get("visible_transits")),
            safe_float(payload.get("sap_pdcsap_ratio")) or 0.0,
        )

    for path in VETTING_REPORTS_DIR.glob("TIC_*/vetting_summary.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        tic = safe_int(payload.get("tic")) or safe_int(path.parent.name.replace("TIC_", ""))
        if tic and (tic not in reports or report_rank(payload) > report_rank(reports[tic])):
            reports[tic] = payload
    return reports


def is_public_green_matrix(matrix: dict[str, Any] | None) -> bool:
    if not matrix:
        return False
    return clean_text(matrix.get("status_color")).upper() == "GREEN"


def yellow_reason_tags(merged: dict[str, Any], matrix: dict[str, Any], is_violet: bool) -> list[str]:
    tags: list[str] = []
    period = safe_float(merged.get("best_period")) or safe_float(matrix.get("period_days")) or 0.0
    snr = safe_float(merged.get("transit_snr")) or safe_float(matrix.get("snr")) or 0.0
    evidence = safe_float(matrix.get("evidence_score")) or 0.0
    n_transits = safe_int(matrix.get("n_transits") or merged.get("transit_count"))
    visible = safe_int(matrix.get("visible_transits") or merged.get("visible_transits"))
    text = " ".join(
        clean_text(value).upper()
        for value in (
            matrix.get("status"),
            matrix.get("status_color"),
            matrix.get("extended_class"),
            matrix.get("score_interpretation"),
            matrix.get("decision_reason"),
            matrix.get("next_step"),
            merged.get("notes"),
            merged.get("next_recheck"),
            merged.get("spc_class"),
            merged.get("status"),
        )
    )

    if n_transits < 5 or visible < 3:
        tags.append("Y_NTR_LOW")
    if period >= 40:
        tags.append("Y_LONG_PERIOD")
    if clean_text(matrix.get("data_gap_risk")).upper() in {"MEDIUM", "HIGH"} or clean_text(matrix.get("sector_edge_risk")).upper() in {"MEDIUM", "HIGH"}:
        tags.append("Y_DATA_GAP")
    if clean_text(matrix.get("rotation_risk")).upper() in {"POSSIBLE", "HIGH"} or "BY_DRA" in text or "ACTIVE" in text or "ROTATION" in text or (is_violet and period >= 80 and n_transits < 5):
        tags.append("Y_ACTIVITY_RISK")
    if "ARTIFACT" in text or "SYSTEMATIC" in text or "SPC_ART" in text or clean_text(matrix.get("depth_stability")).upper() == "UNSTABLE" or clean_text(matrix.get("period_alias_risk")).upper() == "HIGH":
        tags.append("Y_SYSTEMATICS")
    if clean_text(matrix.get("sap_pdcsap_match")).upper() == "MISMATCH":
        tags.append("Y_SAP_PDCSAP_MISMATCH")
    if clean_text(matrix.get("odd_even_result")).upper() in {"UNKNOWN", "BORDERLINE", ""}:
        tags.append("Y_ODD_EVEN_MISSING")
    if "RECHECK" in text or "MANUAL" in text or "SPC_ART" in text or "NEEDS_MORE" in text:
        tags.append("Y_MANUAL_REVIEW")
    if evidence >= _load_pipeline_config()["BUILD_STRONG_UNCONFIRMED_EVIDENCE"] or (is_violet and snr >= 20 and period >= 40):
        tags.append("Y_STRONG_BUT_UNCONFIRMED")

    return list(dict.fromkeys(tags))


def next_checks_for_tags(tags: list[str], matrix: dict[str, Any]) -> list[str]:
    checks: list[str] = []
    if "Y_NTR_LOW" in tags or "Y_LONG_PERIOD" in tags or clean_text(matrix.get("status")).upper() == "NEEDS_MORE_DATA":
        checks.append("More TESS data")
    if "Y_SAP_PDCSAP_MISMATCH" in tags or clean_text(matrix.get("sap_pdcsap_match")).upper() == "UNKNOWN":
        checks.append("SAP/PDCSAP comparison")
    if "Y_ODD_EVEN_MISSING" in tags:
        checks.append("Odd-even test")
    if "Y_ACTIVITY_RISK" in tags:
        checks.append("Rotation/activity check")
    if "Y_SYSTEMATICS" in tags or "Y_MANUAL_REVIEW" in tags:
        checks.append("Manual lightcurve review")
    if "Y_STRONG_BUT_UNCONFIRMED" in tags and "Y_NTR_LOW" not in tags:
        checks.append("RV follow-up")
    return list(dict.fromkeys(checks))


def is_full_vetting_exofop_prep(full_vetting: dict[str, Any]) -> bool:
    classification = clean_text(full_vetting.get("classification")).upper()
    readiness = clean_text(full_vetting.get("exofop_readiness")).upper()
    status = clean_text(full_vetting.get("status")).upper()
    return (
        readiness in {"EXOFOP_PREP", "READY_FOR_EXOFOP"}
        or "EXOFOP_PREP" in status
        or classification == "HIGH_VALUE_HZ_RECHECK"
    )


def color_for(row: dict[str, Any], matrix: dict[str, Any] | None = None) -> str:
    if is_public_green_matrix(matrix):
        return "green"

    matrix_color = clean_text((matrix or {}).get("status_color")).upper()
    if matrix_color:
        return {
            "YELLOW": "yellow",
            "PURPLE": "yellow",
            "RED": "red",
            "GRAY": "gray",
        }.get(matrix_color, "gray")

    mark = clean_text(row.get("markierung")).upper()
    status = clean_text(row.get("status")).upper()
    mark_class = clean_text(row.get("markierungs_klasse")).upper()
    if mark == "ROT" or "FALSE" in status or "FP" in status or "FP" in mark_class:
        return "red"
    if mark == "GELB" or "TESS" in status or "INFO" in mark_class:
        return "yellow"
    if mark == "GRUEN" or "SPC" in status:
        return "green"
    return "gray"


def color_label(color: str) -> str:
    return {
        "green": "Gruen",
        "yellow": "Gelb",
        "red": "Rot",
        "violet": "Violett",
        "gray": "Unsortiert",
    }.get(color, color)


def reason_for(row: dict[str, Any], color: str, is_violet: bool) -> str:
    mark_class = clean_text(row.get("markierungs_klasse"))
    status = clean_text(row.get("status"))
    hz = clean_text(row.get("hz_status") or row.get("hz_class"))
    if is_violet and color == "green":
        return f"SPC-Kandidat und HZ-Ziel ({hz})"
    if is_violet:
        return f"HZ-Ziel / violett markiert ({hz})"
    if color == "green":
        return mark_class or "SPC-Kandidat"
    if color == "yellow":
        return mark_class or status or "mehr Informationen noetig"
    if color == "red":
        return mark_class or status or "False-Positive/Systematik"
    return status or "noch nicht eingeordnet"


def stable_angle(tic: int) -> float:
    return ((tic * 137.508) % 360.0) * math.pi / 180.0


def build_map_coordinates(
    tic: int,
    distance_ly: float,
    snr: float,
    max_distance: float,
    gaia_coords: dict[str, float | None] | None,
) -> tuple[dict[str, float], str]:
    radial = math.sqrt(max(distance_ly, 1.0) / max(max_distance, 1.0))
    scale = 0.16 + radial * 0.76
    if gaia_coords:
        ra = safe_float(gaia_coords.get("ra"))
        dec = safe_float(gaia_coords.get("dec"))
        if ra is not None and dec is not None:
            ra_rad = math.radians(ra)
            dec_rad = math.radians(dec)
            x = math.cos(dec_rad) * math.cos(ra_rad) * scale
            y = math.cos(dec_rad) * math.sin(ra_rad) * scale
            z = math.sin(dec_rad) * scale
            return (
                {"x": round(x, 4), "y": round(y, 4), "z": round(z, 4)},
                "gaia_dr3",
            )

    angle = stable_angle(tic)
    jitter = ((tic % 97) / 97.0 - 0.5) * 0.08
    x = math.cos(angle) * scale + jitter
    y = math.sin(angle) * scale - jitter
    z = min(1.0, max(0.0, snr / 120.0))
    return (
        {"x": round(x, 4), "y": round(y, 4), "z": round(z, 4)},
        "heuristic_fallback",
    )




def compute_final_decision(
    row: dict[str, Any],
    matrix: dict[str, Any] | None,
    sector: dict[str, Any] | None,
    full_vetting: dict[str, Any] | None,
    observed_sectors: list[int],
    period: float,
    monitor_result: dict[str, Any] | None = None,
    single_transit_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _cfg = _load_pipeline_config()
    """
    Compute the Final Decision Pipeline for a candidate.
    
    Decision hierarchy (in order):
    1. FALSE POSITIVE / KEIN PLANET (red) - Hard FP evidence
    2. ZU WENIG DATEN (gray) - Not enough data to assess  
    3. SPC_ART RECHECK (orange) - Artifact/systematics concerns
    4. SPC PREP / RECHECK (yellow) - Strong signal, some checks missing
    5. EXOFOP BEREIT (green) - All checks passed
    """
    check_tree: list[dict[str, Any]] = []
    passed_checks: list[str] = []
    warning_checks: list[str] = []
    failed_checks: list[str] = []
    not_run_checks: list[str] = []
    blockers: list[str] = []
    
    monitor_result = monitor_result or {}
    tic_id = safe_int(row.get("TIC"))
    products_available = bool(monitor_result.get("productsAvailable"))
    # === Step 1: Astro Monitor / TESS Data Gate ===
    has_tess_data = bool(observed_sectors) and products_available
    if not has_tess_data:
        check_tree.append({"name": "TESS Data", "status": "failed", "reason": "No TESS sectors available"})
        failed_checks.append("TESS Data")
        blockers.append("No TESS data available")
        return {
            "ticId": tic_id,
            "status": "WAIT_FOR_TESS",
            "vettingStage2Class": "WAIT_FOR_TESS",
            "reason": "No TESS observations available.",
            "decisionReason": "No TESS observations available",
            "failed_test": "TESS Data",
            "next_action": "wait_for_tess",
            "suggestedAction": "Wait for TESS observations",
            "signal_quality": "unknown",
            "signalStatus": "NO_DATA",
            "data_quality": "low",
            "dataStatus": "NO_TESS_DATA",
            "monitorStatus": "NO_TESS_DATA",
            "matrix_cell": "no_tess_data",
            "scoreDelta": 0,
            "badges": ["WAIT_FOR_TESS", "NO_TESS_DATA"],
            "warnings": ["No TESS data available"],
            "passed_checks": [], "warning_checks": [], "failed_checks": failed_checks,
            "not_run_checks": ["Signal Detection", "Folded Light Curve", "Sector Coverage", "Transit Count", "Vetting Checks"],
            "blockers": blockers, "check_tree": check_tree
        }
    
    check_tree.append({"name": "TESS Data", "status": "passed", "reason": f"{len(observed_sectors)} TESS sector(s) available"})
    passed_checks.append("TESS Data")
    
    # === Step 2: Signal Detection ===
    snr = safe_float(row.get("transit_snr")) or 0.0
    has_signal = snr > 0
    if not has_signal:
        check_tree.append({"name": "Signal Detection", "status": "failed", "reason": "No BLS/TLS signal detected"})
        failed_checks.append("Signal Detection")
        blockers.append("No transit signal detected")
        return {
            "ticId": tic_id,
            "status": "LOW_CONFIDENCE", "vettingStage2Class": "LOW_CONFIDENCE",
            "reason": "No statistically significant transit signal detected.",
            "decisionReason": "No statistically significant transit signal detected.",
            "failed_test": "Signal Detection", "next_action": "manual_review_required",
            "suggestedAction": "Signal detection failed.",
            "signal_quality": "weak", "signalStatus": "NO_SIGNAL",
            "data_quality": "sufficient", "dataStatus": "TESS_DATA_AVAILABLE",
            "monitorStatus": monitor_result.get("monitorStatus", "TESS_DATA_AVAILABLE"),
            "matrix_cell": "no_signal", "scoreDelta": 0,
            "badges": ["LOW_CONFIDENCE"], "warnings": ["No transit signal detected"],
            "passed_checks": passed_checks, "warning_checks": [], "failed_checks": failed_checks,
            "not_run_checks": ["Folded Light Curve", "Sector Coverage", "Transit Count", "Vetting Checks"],
            "blockers": blockers, "check_tree": check_tree
        }
    
    check_tree.append({"name": "Signal Detection", "status": "passed", "reason": f"BLS/TLS signal detected (SNR: {snr:.1f})"})
    passed_checks.append("Signal Detection")
    
    # === Step 3: Data Quality Assessment ===
    matrix_transits = safe_int_or_none((matrix or {}).get("n_transits"))
    visible_transits = safe_int_or_none((matrix or {}).get("visible_transits"))
    row_transits = safe_int(row.get("transit_count"))
    observed_transits = max(matrix_transits or 0, visible_transits or 0, row_transits)
    min_transits = _cfg["BUILD_MIN_TRANSITS"]
    has_sufficient_transits = visible_transits is not None and visible_transits >= min_transits
    
    sector_count = len(observed_sectors)
    min_sectors_for_period = max(1, int(period / 10) + 1) if period > 0 else 1
    has_sufficient_sectors = sector_count >= min_sectors_for_period
    
    check_tree.append({"name": "Transit Count", "status": "passed" if has_sufficient_transits else "warning",
        "reason": f"{observed_transits} visible transit(s), need {min_transits}+"})
    check_tree.append({"name": "Sector Coverage", "status": "passed" if has_sufficient_sectors else "warning",
        "reason": f"{sector_count} sector(s), need {min_sectors_for_period}+ for period {period:.2f} days"})
    
    # === Step 4: Folded Light Curve Assessment ===
    transit_shape = clean_text((matrix or {}).get("transit_shape")).upper()
    depth_stability = clean_text((matrix or {}).get("depth_stability")).upper()
    valid_shapes = {"U_SHAPED", "BOX", "BOX_SHAPED", "TRAPEZOID", "PLAUIBLE"}
    has_valid_shape = transit_shape in valid_shapes or not transit_shape
    has_bad_shape = transit_shape in {"INVERTED", "NOISE", "SPURIOUS", "IRREGULAR", "INVALID"}
    is_unknown_shape = transit_shape in {"UNKNOWN", ""}
    is_unstable_depth = depth_stability in {"UNSTABLE", "HIGH_VARIABILITY"}
    
    flc_status = "passed"
    if has_bad_shape:
        flc_status = "failed"
    elif is_unstable_depth or is_unknown_shape:
        flc_status = "warning"
    
    check_tree.append({"name": "Folded Light Curve", "status": flc_status,
        "reason": f"Transit shape: {transit_shape or 'unknown'}, Depth stability: {depth_stability or 'unknown'}"})
    
    # === Step 5: Vetting Checks ===
    sap_pdcsap = clean_text((matrix or {}).get("sap_pdcsap_match")).upper()
    sap_pdcsap_ok = sap_pdcsap in {"OK", "MATCH", "CONSISTENT", "GOOD", ""}
    
    odd_even = clean_text((matrix or {}).get("odd_even_result")).upper()
    odd_even_ok = odd_even in {"OK", "PASS", "CONSISTENT", "GOOD", "NONE", ""}
    
    secondary = clean_text((matrix or {}).get("secondary_eclipse")).upper()
    secondary_ok = secondary in {"NONE", "NOT_DETECTED", "NO", "OK", ""}
    
    rotation_risk = clean_text((matrix or {}).get("rotation_risk")).upper()
    rotation_ok = rotation_risk in {"NONE", "LOW", "OK", "NO", ""}
    
    # Check for SPC_ART
    spc_art = clean_text((matrix or {}).get("spc_class")).upper() in {"SPC_ART", "ARTIFACT", "SYSTEMATIC"}
    spc_text = " ".join(clean_text(v).upper() for v in (
        (matrix or {}).get("status"), (matrix or {}).get("status_color"),
        (matrix or {}).get("extended_class"), (matrix or {}).get("decision_reason"),
        row.get("notes"), row.get("next_recheck")))
    has_spcar_art = spc_art or "SPC_ART" in spc_text or "ARTIFACT" in spc_text or "SYSTEMATIC" in spc_text
    
    # Evidence score
    evidence_score = safe_float((matrix or {}).get("evidence_score")) or 0.0
    
    # Check for recheck flags
    has_recheck = "RECHECK" in spc_text or "NEEDS_MORE" in spc_text or "MANUAL" in spc_text
    
    # Matrix color
    matrix_color = clean_text((matrix or {}).get("status_color")).upper()
    is_orange = matrix_color == "ORANGE"
    spc_art_stage2 = evaluate_spc_art_stage2(
        matrix,
        row,
        visible_transits or 0,
        observed_transits,
        has_lightcurve_product=bool(monitor_result.get("productsAvailable")),
        single_transit_data=single_transit_data,
    ) if (has_spcar_art or is_orange) else None
    
    # === DECISION LOGIC ===
    
    # 1. Check for FALSE POSITIVE (hard evidence)
    is_fp = False
    fp_reason = ""
    
    if secondary and secondary not in {"NONE", "NOT_DETECTED", "NO", "OK", ""}:
        is_fp = True
        fp_reason = f"Secondary eclipse detected: {secondary}"
    elif has_bad_shape and has_sufficient_transits and has_sufficient_sectors:
        is_fp = True
        fp_reason = f"Transit shape implausible: {transit_shape}"
    elif odd_even in {"BAD", "MISMATCH", "SIGNIFICANT"} and has_sufficient_transits and has_sufficient_sectors:
        is_fp = True
        fp_reason = f"Odd/Even mismatch: {odd_even}"
    elif rotation_risk in {"HIGH", "STRONG"} and has_sufficient_transits and has_sufficient_sectors:
        is_fp = True
        fp_reason = f"Rotation/activity signal: {rotation_risk}"
    elif sap_pdcsap in {"MISMATCH"} and has_sufficient_transits and has_sufficient_sectors:
        is_fp = True
        fp_reason = f"SAP/PDCSAP mismatch: {sap_pdcsap}"
    
    if is_fp:
        check_tree.append({"name": "Decision", "status": "failed", "reason": fp_reason})
        return {
            "ticId": tic_id,
            "status": "RED_FP", "vettingStage2Class": "RED_FP",
            "reason": f"False Positive: {fp_reason}. Candidate is likely not a planet.",
            "decisionReason": f"False Positive: {fp_reason}. Candidate is likely not a planet.",
            "failed_test": "False Positive", "next_action": "exclude",
            "suggestedAction": "Candidate excluded from follow-up.",
            "signal_quality": "weak", "signalStatus": "VISIBLE_SIGNAL",
            "data_quality": "sufficient", "dataStatus": "TESS_DATA_AVAILABLE",
            "monitorStatus": monitor_result.get("monitorStatus", "TESS_DATA_AVAILABLE"),
            "matrix_cell": "false_positive", "scoreDelta": 0,
            "badges": ["RED_FP"], "warnings": [fp_reason],
            "passed_checks": passed_checks, "warning_checks": [], "failed_checks": ["Vetting Checks"],
            "not_run_checks": [], "blockers": [fp_reason], "check_tree": check_tree
        }

    if spc_art_stage2:
        check_tree.append({
            "name": "Individual Transits",
            "status": "passed" if spc_art_stage2["singleTransitStatus"] == "STABLE" else ("failed" if spc_art_stage2["singleTransitStatus"] == "NOT_REPRODUCIBLE" else "warning"),
            "reason": f"{spc_art_stage2['singleTransitStatus']}; {spc_art_stage2['plotStatus']}",
        })
        check_tree.append({
            "name": "Depth Stability",
            "status": "passed" if spc_art_stage2["depthStabilityScore"] >= 0.65 else ("failed" if spc_art_stage2["depthStabilityScore"] < 0.4 else "warning"),
            "reason": f"median={spc_art_stage2['medianDepthPpt'] or '-'} ppt, scatter={spc_art_stage2['depthScatterPpt'] or '-'}, score={spc_art_stage2['depthStabilityScore']}",
        })
        check_tree.append({
            "name": "SPC_ART Stage 2",
            "status": "passed" if spc_art_stage2["recommendation"] == "PROMOTE_RECHECK" else ("failed" if spc_art_stage2["recommendation"] == "FALSE_POSITIVE" else "warning"),
            "reason": f"Folded LC: {spc_art_stage2['foldedLightCurveStatus']}; Activity: {spc_art_stage2['activityStatus']}",
        })

        if spc_art_stage2["recommendation"] == "FALSE_POSITIVE":
            return {
                "ticId": tic_id,
                "status": "RED_FP", "vettingStage2Class": "RED_FP",
                "reason": "SPC_ART Stage 2: signal is not reproducible in individual transits.",
                "decisionReason": "SPC_ART Stage 2: signal is not reproducible in individual transits.",
                "failed_test": "Individual Transits", "next_action": "exclude",
                "suggestedAction": spc_art_stage2["nextAction"],
                "signal_quality": "medium", "signalStatus": "NOT_REPRODUCIBLE",
                "data_quality": "medium", "dataStatus": "TESS_DATA_AVAILABLE",
                "monitorStatus": monitor_result.get("monitorStatus", "TESS_DATA_AVAILABLE"),
                "matrix_cell": "false_positive", "scoreDelta": 0,
                "badges": ["RED_FP", "SPC_ART_STAGE2"], "warnings": spc_art_stage2["missingChecks"],
                "spcArtStage2": spc_art_stage2,
                "passed_checks": passed_checks, "warning_checks": warning_checks,
                "failed_checks": ["Individual Transits"], "not_run_checks": not_run_checks,
                "blockers": ["Signal not reproducible", *spc_art_stage2["missingChecks"]],
                "check_tree": check_tree,
            }

        if spc_art_stage2["recommendation"] != "PROMOTE_RECHECK":
            return {
                "ticId": tic_id,
                "status": "PURPLE_SPC_ART",
                "vettingStage2Class": "PURPLE_SPC_ART",
                "reason": "SPC_ART Stage 2 required: artifact/systematics concerns remain.",
                "decisionReason": "SPC_ART Stage 2 required: " + (", ".join(spc_art_stage2["missingChecks"]) if spc_art_stage2["missingChecks"] else "artifact/systematics concerns remain") + ".",
                "failed_test": "SPC_ART Stage 2", "next_action": "manual_review_required",
                "suggestedAction": spc_art_stage2["nextAction"],
                "signal_quality": "medium", "signalStatus": "VISIBLE_SIGNAL",
                "data_quality": "medium", "dataStatus": "TESS_DATA_AVAILABLE",
                "monitorStatus": monitor_result.get("monitorStatus", "TESS_DATA_AVAILABLE"),
                "matrix_cell": "artifact_recheck", "scoreDelta": 0,
                "badges": ["PURPLE_SPC_ART", "SPC_ART_STAGE2"], "warnings": spc_art_stage2["missingChecks"],
                "spcArtStage2": spc_art_stage2,
                "passed_checks": passed_checks, "warning_checks": list(dict.fromkeys([*warning_checks, "SPC_ART Stage 2"])),
                "failed_checks": [], "not_run_checks": not_run_checks,
                "blockers": spc_art_stage2["missingChecks"],
                "check_tree": check_tree,
            }
    
    # 2. Check for ZU WENIG DATEN (not enough data to assess)
    if not has_sufficient_sectors or not has_sufficient_transits:
        check_tree.append({"name": "Decision", "status": "warning", "reason": "Insufficient data for reliable assessment"})
        return {
            "ticId": tic_id,
            "status": "YELLOW_RECHECK", "vettingStage2Class": "YELLOW_RECHECK",
            "reason": f"Not enough data: only {observed_transits} visible transits, {sector_count} sectors. Cannot reliably assess signal.",
            "decisionReason": f"Not enough data: only {observed_transits} visible transits, {sector_count} sectors. Cannot reliably assess signal.",
            "failed_test": "Data Limit", "next_action": "wait_for_more_sectors",
            "suggestedAction": "Wait for additional TESS sectors or data.",
            "signal_quality": "strong", "signalStatus": "VISIBLE_SIGNAL",
            "data_quality": "low", "dataStatus": "TESS_DATA_LIMITED",
            "monitorStatus": monitor_result.get("monitorStatus", "TESS_DATA_AVAILABLE"),
            "matrix_cell": "data_limited", "scoreDelta": 0,
            "badges": ["YELLOW_RECHECK"], "warnings": ["Data limited"],
            "passed_checks": passed_checks, "warning_checks": ["Transit Count", "Sector Coverage"],
            "failed_checks": [], "not_run_checks": [], "blockers": [f"Only {observed_transits} transits, {sector_count} sectors"], 
            "check_tree": check_tree
        }
    
    # 3. Check for SPC_ART RECHECK (artifact concerns)
    if has_spcar_art or is_orange or has_recheck:
        check_tree.append({"name": "Decision", "status": "warning", "reason": "Artifact/systematics concerns"})
        
        artifact_reasons = []
        if has_spcar_art: artifact_reasons.append("SPC_ART flagged")
        if is_orange: artifact_reasons.append("Orange matrix color")
        if has_recheck: artifact_reasons.append("Recheck needed")
        if flc_status == "warning": artifact_reasons.append("Folded Light Curve unclear")
        if not sap_pdcsap_ok: artifact_reasons.append("SAP/PDCSAP not proven")
        if not rotation_ok: artifact_reasons.append("Activity/Rotation unclear")
        
        return {
            "ticId": tic_id,
            "status": "PURPLE_SPC_ART",
            "vettingStage2Class": "PURPLE_SPC_ART",
            "reason": f"Strong candidate, but artifact/systematics concerns remain: {', '.join(artifact_reasons)}. Manual vetting required.",
            "decisionReason": f"Strong candidate, but artifact/systematics concerns remain: {', '.join(artifact_reasons)}. Manual vetting required.",
            "failed_test": "Artifact Check", "next_action": "manual_review_required",
            "suggestedAction": "Clean lightcurve, verify SAP/PDCSAP, check activity/rotation, analyze outliers.",
            "signal_quality": "medium", "signalStatus": "VISIBLE_SIGNAL",
            "data_quality": "medium", "dataStatus": "TESS_DATA_AVAILABLE",
            "monitorStatus": monitor_result.get("monitorStatus", "TESS_DATA_AVAILABLE"),
            "matrix_cell": "artifact_recheck", "scoreDelta": 0,
            "badges": ["PURPLE_SPC_ART"], "warnings": artifact_reasons,
            "passed_checks": passed_checks, "warning_checks": warning_checks, "failed_checks": [],
            "not_run_checks": not_run_checks, "blockers": artifact_reasons, "check_tree": check_tree
        }
    
    # 4. Check for SPC PREP / RECHECK (good signal but some checks missing)
    core_vetting_ok = sap_pdcsap_ok and odd_even_ok and secondary_ok and rotation_ok
    flc_ok = flc_status == "passed"
    
    if not core_vetting_ok or not flc_ok or evidence_score < _cfg["BUILD_EXOFOP_EVIDENCE"]:
        prep_reasons = []
        if not core_vetting_ok:
            if not sap_pdcsap_ok: prep_reasons.append("SAP/PDCSAP unclear")
            if not odd_even_ok: prep_reasons.append("Odd/Even unclear")
            if not rotation_ok: prep_reasons.append("Activity/Rotation unclear")
            if not secondary_ok: prep_reasons.append("Secondary Eclipse unclear")
        if not flc_ok:
            prep_reasons.append("Folded Light Curve not fully validated")
        if evidence_score < _cfg["BUILD_EXOFOP_EVIDENCE"]:
            prep_reasons.append(f"Evidence score {evidence_score:.1f} < {_cfg['BUILD_EXOFOP_EVIDENCE']}")
        
        check_tree.append({"name": "Decision", "status": "warning", "reason": "Some vetting checks not complete"})
        
        return {
            "ticId": tic_id,
            "status": "YELLOW_RECHECK",
            "vettingStage2Class": "YELLOW_RECHECK",
            "reason": f"Strong signal and good data, but unresolved vetting checks: {', '.join(prep_reasons)}.",
            "decisionReason": f"Strong signal and good data, but unresolved vetting checks: {', '.join(prep_reasons)}.",
            "failed_test": "Vetting Incomplete", "next_action": "manual_review_required",
            "suggestedAction": "Complete missing vetting checks before ExoFOP submission.",
            "signal_quality": "strong", "signalStatus": "VISIBLE_SIGNAL",
            "data_quality": "good", "dataStatus": "TESS_DATA_AVAILABLE",
            "monitorStatus": monitor_result.get("monitorStatus", "TESS_DATA_AVAILABLE"),
            "matrix_cell": "spc_prep", "scoreDelta": 0,
            "badges": ["YELLOW_RECHECK"], "warnings": prep_reasons,
            "passed_checks": passed_checks, "warning_checks": warning_checks, "failed_checks": [],
            "not_run_checks": not_run_checks, "blockers": prep_reasons, "check_tree": check_tree
        }
    
    # 5. EXOFOP BEREIT - all checks passed
    check_tree.append({"name": "Decision", "status": "passed", "reason": "All scientific requirements met"})
    
    return {
        "ticId": tic_id,
        "status": "GREEN_SPC",
        "vettingStage2Class": "GREEN_SPC",
        "reason": "Candidate meets all scientific requirements for ExoFOP submission.",
        "decisionReason": "Candidate meets all scientific requirements for ExoFOP submission.",
        "failed_test": None, "next_action": "prepare_exofop_upload",
        "suggestedAction": "Ready for ExoFOP upload and follow-up prioritization.",
        "signal_quality": "strong", "signalStatus": "VISIBLE_SIGNAL",
        "data_quality": "high", "dataStatus": "TESS_DATA_AVAILABLE",
        "monitorStatus": monitor_result.get("monitorStatus", "TESS_DATA_AVAILABLE"),
        "matrix_cell": "exofop_ready", "scoreDelta": 0,
        "badges": ["GREEN_SPC"], "warnings": [],
        "passed_checks": passed_checks, "warning_checks": [], "failed_checks": [],
        "not_run_checks": not_run_checks, "blockers": [], "check_tree": check_tree
    }


def classify_folded_lightcurve_status(transit_shape: str, depth_stability: str) -> str:
    shape = clean_text(transit_shape).upper()
    stability = clean_text(depth_stability).upper()
    if shape in {"SHAPE_CLEAR", "U_SHAPE", "U_SHAPED", "BOX", "BOX_SHAPED", "CLEAR"}:
        return "CLEAR"
    if shape in {"V_SHAPE", "V_SHAPED"}:
        return "V_SHAPED"
    if shape in {"NOISE", "NOISY"}:
        return "NOISY"
    if shape in {"ARTIFACT", "ARTIFACT_LIKE", "SPURIOUS", "INVERTED", "IRREGULAR", "INVALID"} or stability in {"UNSTABLE", "HIGH_VARIABILITY"}:
        return "ARTIFACT_LIKE"
    return "UNCLEAR"


def normalize_stage2_missing_status(
    raw_value: str,
    *,
    has_lightcurve_product: bool,
    visible_transits: int,
    min_transits: int = 2,
) -> str:
    value = clean_text(raw_value).upper()
    if value and value not in {"UNKNOWN", "NOT_COMPUTED", "MISSING_RAW_DATA", "INSUFFICIENT_TRANSITS"}:
        return value
    if visible_transits < min_transits:
        return "INSUFFICIENT_TRANSITS"
    if not has_lightcurve_product:
        return "MISSING_RAW_DATA"
    return "NOT_COMPUTED"


def evaluate_spc_art_stage2(
    matrix: dict[str, Any] | None,
    row: dict[str, Any],
    visible_transits: int,
    observed_transits: int,
    has_lightcurve_product: bool = False,
    single_transit_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    matrix = matrix or {}
    single_transit_data = single_transit_data or missing_level5_single_transit_data()
    single_stats = dict(single_transit_data.get("statistics") or {})
    single_events = list(single_transit_data.get("events") or [])
    depth_ppt = safe_float(matrix.get("depth_ppt")) or 0.0
    duration_hours = safe_float(matrix.get("duration_hours")) or 0.0
    depth_stability = clean_text(matrix.get("depth_stability")).upper()
    transit_shape = clean_text(matrix.get("transit_shape")).upper()
    transit_shape_score = safe_float(matrix.get("transit_shape_score"))
    transit_shape_source = clean_text(matrix.get("transit_shape_source"))
    shape_blockers_text = clean_text(matrix.get("shape_blocking_issues"))
    shape_blockers = [item for item in re.split(r"[;|]", shape_blockers_text) if clean_text(item)]
    folded_lc_quality = clean_text(matrix.get("folded_lc_quality")).upper()
    rotation_risk = clean_text(matrix.get("rotation_risk")).upper()
    sector_edge_risk = clean_text(matrix.get("sector_edge_risk")).upper()
    data_gap_risk = clean_text(matrix.get("data_gap_risk")).upper()
    expected_transits = max(observed_transits, visible_transits, safe_int(row.get("transit_count")))
    shape_class = folded_lc_quality if folded_lc_quality in {"CLEAR", "V_SHAPED", "NOISY", "ARTIFACT_LIKE", "UNCLEAR"} else classify_folded_lightcurve_status(transit_shape, depth_stability)
    transit_shape_status = normalize_stage2_missing_status(
        transit_shape,
        has_lightcurve_product=has_lightcurve_product,
        visible_transits=visible_transits,
    )

    has_level5_events = bool(single_events)
    single_source = clean_text(single_stats.get("source")) or "MISSING_LEVEL5_SINGLE_TRANSIT_CSV"
    plot_status = clean_text(single_stats.get("plotStatus")) or "PLOT_NOT_AVAILABLE"

    if has_level5_events:
        visible_events = [event for event in single_events if bool(event.get("visible"))]
        visible_transits = safe_int(single_stats.get("visibleTransitCount") or single_stats.get("visible_transit_count")) or len(visible_events)
        expected_transits = safe_int(single_stats.get("individualTransitCount") or single_stats.get("individual_transit_count")) or len(single_events)
        depth_stability = clean_text(single_stats.get("depthStability") or single_stats.get("depth_stability")).upper()
        depth_stability_status = depth_stability or "UNKNOWN"
        depth_stability_score = single_transit_score_from_stats(single_stats)
        median_depth_ppt = safe_float(single_stats.get("medianDepthPpt") or single_stats.get("median_depth_ppt"))
        depth_scatter_ppt = safe_float(single_stats.get("depthScatterPpt") or single_stats.get("depth_scatter_ppt"))
        median_single_snr = safe_float(single_stats.get("medianSingleTransitSnr") or single_stats.get("median_single_transit_snr"))
        transit_status: list[dict[str, Any]] = []
        for idx, event in enumerate(single_events):
            event_visible = bool(event.get("visible"))
            event_snr = safe_float(event.get("localSnr") or event.get("local_snr"))
            flags: list[str] = []
            if not event_visible:
                flags.append("missing_or_not_visible")
            if event_snr is not None and event_snr < 5:
                flags.append("low_single_transit_snr")
            if sector_edge_risk == "HIGH" or data_gap_risk == "HIGH":
                flags.append("edge_or_gap_risk")
            if depth_stability_score < 0.4:
                flags.append("depth_outlier_possible")
            transit_status.append({
                "index": idx + 1,
                "epoch": event.get("epoch"),
                "expectedTime": event.get("expectedTime") if event.get("expectedTime") is not None else event.get("expected_time"),
                "status": "OK" if event_visible and not flags else ("MISSING" if not event_visible else "NEEDS_REVIEW"),
                "depthPpt": event.get("depthPpt") if event.get("depthPpt") is not None else event.get("depth_ppt"),
                "localSnr": event_snr,
                "nIn": event.get("nIn") if event.get("nIn") is not None else event.get("n_in"),
                "nOut": event.get("nOut") if event.get("nOut") is not None else event.get("n_out"),
                "visible": event_visible,
                "flags": flags,
            })

        missing_checks: list[str] = []
        if visible_transits < 2:
            missing_checks.append("Signal reproducibility")
        if shape_class == "UNCLEAR":
            missing_checks.append("Folded Light Curve classification")
        if depth_stability_status in {"NOT_COMPUTED", "MISSING_RAW_DATA", "INSUFFICIENT_TRANSITS", "UNKNOWN", ""}:
            missing_checks.append("Depth stability measurement")
        if rotation_risk in {"UNKNOWN", "", "POSSIBLE"}:
            missing_checks.append("Activity/Rotation check")
        if any(item["status"] != "OK" for item in transit_status):
            missing_checks.append("Individual transit review")

        blocking_issues: list[str] = []
        if transit_shape_status == "MISSING_RAW_DATA":
            blocking_issues.append("Transit shape not computed because raw folded-light-curve metrics are missing from the data export.")
        elif transit_shape_status == "INSUFFICIENT_TRANSITS":
            blocking_issues.append("Transit shape not computed because fewer than two visible transits are available.")
        elif transit_shape_status == "NOT_COMPUTED":
            blocking_issues.append("Transit shape metric exists neither in candidate_matrix nor in Stage 2 raw measurements.")
        blocking_issues.extend(shape_blockers)
        if plot_status == "PLOT_NOT_AVAILABLE":
            missing_checks.append("PLOT_NOT_AVAILABLE")

        activity_flag = rotation_risk in {"HIGH", "STRONG", "FAST_ROTATION_ACTIVITY_RECHECK"}
        activity_status = "FLAGGED" if activity_flag else ("LOW_RISK" if rotation_risk in {"LOW", "NONE", "OK", "NO"} else "UNCLEAR")
        stable_individual = visible_transits >= 2 and depth_stability_score >= 0.65 and all(item["status"] != "MISSING" for item in transit_status)
        artifact_concern = shape_class == "ARTIFACT_LIKE" or depth_stability_score < 0.4 or activity_flag or sector_edge_risk == "HIGH" or data_gap_risk == "HIGH"
        reproducible = visible_transits >= 2

        recommendation = "KEEP_SPC_ART"
        next_action = "Review individual transits, folded light curve, depth stability, and activity/rotation."
        if not reproducible:
            recommendation = "FALSE_POSITIVE"
            next_action = "Mark as false positive unless new data reproduces the signal."
        elif stable_individual and shape_class == "CLEAR" and activity_status == "LOW_RISK":
            recommendation = "PROMOTE_RECHECK"
            next_action = "Move to recheck/SPC preparation after documenting Stage 2 evidence."
        elif artifact_concern:
            recommendation = "KEEP_SPC_ART"
            next_action = "Keep SPC_ART and resolve artifact/systematics concerns before follow-up."

        return {
            "applies": True,
            "source": "LEVEL5_SINGLE_TRANSITS",
            "fallbackUsed": False,
            "stage2Completed": True,
            "computationStatus": "COMPUTED" if not blocking_issues else "COMPUTED_WITH_LIMITED_EXPORT_DATA",
            "blockingIssues": blocking_issues,
            "singleTransitStatus": "STABLE" if stable_individual else ("NOT_REPRODUCIBLE" if not reproducible else "NEEDS_REVIEW"),
            "individualTransitStatus": "STABLE" if stable_individual else ("NOT_REPRODUCIBLE" if not reproducible else "NEEDS_REVIEW"),
            "transits": transit_status,
            "individualTransitCount": len(transit_status),
            "visibleTransits": visible_transits,
            "totalTransits": expected_transits,
            "medianDepthPpt": median_depth_ppt,
            "depthScatterPpt": depth_scatter_ppt,
            "medianSingleTransitSnr": median_single_snr,
            "depthStabilityScore": round(depth_stability_score, 3),
            "depthStability": depth_stability_status,
            "rawDepthStability": depth_stability or "UNKNOWN",
            "transitShape": transit_shape_status,
            "rawTransitShape": transit_shape or "UNKNOWN",
            "transitShapeScore": transit_shape_score,
            "transitShapeSource": transit_shape_source,
            "shapeStatus": clean_text(matrix.get("shape_status")),
            "shapeSnr": safe_float(matrix.get("shape_snr")),
            "measuredDepthPpt": safe_float(matrix.get("measured_depth_ppt")),
            "secondaryRatioMeasured": safe_float(matrix.get("secondary_ratio_measured")),
            "baselineLeftRightDeltaPpt": safe_float(matrix.get("baseline_left_right_delta_ppt")),
            "ootScatterPpt": safe_float(matrix.get("oot_scatter_ppt")),
            "vShapeScore": safe_float(matrix.get("v_shape_score")),
            "shapeBlockingIssues": shape_blockers,
            "foldedLightCurveStatus": shape_class,
            "transitShapeClass": shape_class,
            "activityStatus": activity_status,
            "activityRotationStatus": activity_status,
            "activityFlag": activity_flag,
            "missingChecks": list(dict.fromkeys(missing_checks)),
            "recommendation": recommendation,
            "nextAction": next_action,
            "plotStatus": plot_status,
            "individualTransitPlotPath": clean_text(single_stats.get("individualTransitPlotPath") or single_stats.get("individual_transit_plot_path")),
            "individualTransitStatistics": single_stats,
            "individualTransitEvents": single_events,
        }
    depth_stability_status = normalize_stage2_missing_status(
        depth_stability,
        has_lightcurve_product=has_lightcurve_product,
        visible_transits=visible_transits,
    )

    if depth_stability in {"STABLE", "LOW", "OK", "GOOD"}:
        depth_stability_score = 1.0
    elif depth_stability in {"UNSTABLE", "HIGH_VARIABILITY"}:
        depth_stability_score = 0.0
    elif depth_ppt > 0 and visible_transits >= 3:
        depth_stability_score = 0.55
    else:
        depth_stability_score = 0.5

    transit_status: list[dict[str, Any]] = []
    for idx in range(max(expected_transits, visible_transits, 0)):
        flags: list[str] = []
        status = "NEEDS_REVIEW" if idx < visible_transits else "MISSING"
        if idx >= visible_transits:
            flags.append("missing_or_not_visible")
        if sector_edge_risk == "HIGH" or data_gap_risk == "HIGH":
            flags.append("edge_or_gap_risk")
        if depth_stability_score < 0.4:
            flags.append("depth_outlier_possible")
        transit_status.append({
            "index": idx + 1,
            "status": status,
            "depthPpt": round(depth_ppt, 5) if depth_ppt else None,
            "durationHours": round(duration_hours, 5) if duration_hours else None,
            "flags": flags,
        })

    missing_checks: list[str] = []
    if single_source == "MISSING_LEVEL5_SINGLE_TRANSIT_CSV":
        missing_checks.append("MISSING_LEVEL5_SINGLE_TRANSIT_CSV")
    if visible_transits < 2:
        missing_checks.append("Signal reproducibility")
    if shape_class == "UNCLEAR":
        missing_checks.append("Folded Light Curve classification")
    if depth_stability_status in {"NOT_COMPUTED", "MISSING_RAW_DATA", "INSUFFICIENT_TRANSITS", "UNKNOWN"}:
        missing_checks.append("Depth stability measurement")
    if rotation_risk in {"UNKNOWN", "", "POSSIBLE"}:
        missing_checks.append("Activity/Rotation check")
    if any(item["status"] != "OK" for item in transit_status):
        missing_checks.append("Individual transit review")

    blocking_issues: list[str] = []
    if single_source == "MISSING_LEVEL5_SINGLE_TRANSIT_CSV":
        blocking_issues.append("MISSING_LEVEL5_SINGLE_TRANSIT_CSV")
    if transit_shape_status == "MISSING_RAW_DATA":
        blocking_issues.append("Transit shape not computed because raw folded-light-curve metrics are missing from the data export.")
    elif transit_shape_status == "INSUFFICIENT_TRANSITS":
        blocking_issues.append("Transit shape not computed because fewer than two visible transits are available.")
    elif transit_shape_status == "NOT_COMPUTED":
        blocking_issues.append("Transit shape metric exists neither in candidate_matrix nor in Stage 2 raw measurements.")
    blocking_issues.extend(shape_blockers)
    if depth_stability_status == "MISSING_RAW_DATA":
        blocking_issues.append("Depth stability not computed because individual-transit depth measurements are missing from the data export.")
    elif depth_stability_status == "INSUFFICIENT_TRANSITS":
        blocking_issues.append("Depth stability not computed because fewer than two visible transits are available.")
    elif depth_stability_status == "NOT_COMPUTED":
        blocking_issues.append("Depth stability metric exists neither in candidate_matrix nor in Stage 2 raw measurements.")

    activity_flag = rotation_risk in {"HIGH", "STRONG", "FAST_ROTATION_ACTIVITY_RECHECK"}
    if activity_flag:
        activity_status = "FLAGGED"
    elif rotation_risk in {"LOW", "NONE", "OK", "NO"}:
        activity_status = "LOW_RISK"
    else:
        activity_status = "UNCLEAR"

    depth_scatter_ppt = round(depth_ppt * (1 - depth_stability_score), 5) if depth_ppt else None
    stable_individual = visible_transits >= 2 and depth_stability_score >= 0.65 and all(item["status"] != "MISSING" for item in transit_status)
    artifact_concern = (
        shape_class == "ARTIFACT_LIKE"
        or depth_stability_score < 0.4
        or activity_flag
        or sector_edge_risk == "HIGH"
        or data_gap_risk == "HIGH"
    )
    reproducible = visible_transits >= 2

    recommendation = "KEEP_SPC_ART"
    next_action = "Review individual transits, folded light curve, depth stability, and activity/rotation."
    if not reproducible:
        recommendation = "FALSE_POSITIVE"
        next_action = "Mark as false positive unless new data reproduces the signal."
    elif stable_individual and shape_class == "CLEAR" and activity_status == "LOW_RISK":
        recommendation = "PROMOTE_RECHECK"
        next_action = "Move to recheck/SPC preparation after documenting Stage 2 evidence."
    elif artifact_concern:
        recommendation = "KEEP_SPC_ART"
        next_action = "Keep SPC_ART and resolve artifact/systematics concerns before follow-up."

    return {
        "applies": True,
        "source": "DATA_BUILD",
        "fallbackUsed": False,
        "stage2Completed": True,
        "computationStatus": "COMPUTED_WITH_LIMITED_EXPORT_DATA" if blocking_issues else "COMPUTED",
        "blockingIssues": blocking_issues,
        "singleTransitStatus": "STABLE" if stable_individual else ("NOT_REPRODUCIBLE" if not reproducible else "NEEDS_REVIEW"),
        "individualTransitStatus": "STABLE" if stable_individual else ("NOT_REPRODUCIBLE" if not reproducible else "NEEDS_REVIEW"),
        "transits": transit_status,
        "individualTransitCount": len(transit_status),
        "visibleTransits": visible_transits,
        "totalTransits": expected_transits,
        "medianDepthPpt": round(depth_ppt, 5) if depth_ppt else None,
        "depthScatterPpt": depth_scatter_ppt,
        "depthStabilityScore": round(depth_stability_score, 3),
        "depthStability": depth_stability_status,
        "rawDepthStability": depth_stability or "UNKNOWN",
        "transitShape": transit_shape_status,
        "rawTransitShape": transit_shape or "UNKNOWN",
        "transitShapeScore": transit_shape_score,
        "transitShapeSource": transit_shape_source,
        "shapeStatus": clean_text(matrix.get("shape_status")),
        "shapeSnr": safe_float(matrix.get("shape_snr")),
        "measuredDepthPpt": safe_float(matrix.get("measured_depth_ppt")),
        "secondaryRatioMeasured": safe_float(matrix.get("secondary_ratio_measured")),
        "baselineLeftRightDeltaPpt": safe_float(matrix.get("baseline_left_right_delta_ppt")),
        "ootScatterPpt": safe_float(matrix.get("oot_scatter_ppt")),
        "vShapeScore": safe_float(matrix.get("v_shape_score")),
        "shapeBlockingIssues": shape_blockers,
        "foldedLightCurveStatus": shape_class,
        "transitShapeClass": shape_class,
        "activityStatus": activity_status,
        "activityRotationStatus": activity_status,
        "activityFlag": activity_flag,
        "missingChecks": list(dict.fromkeys(missing_checks)),
        "recommendation": recommendation,
        "nextAction": next_action,
        "plotStatus": plot_status,
        "individualTransitPlotPath": clean_text(single_stats.get("individualTransitPlotPath") or single_stats.get("individual_transit_plot_path")),
        "individualTransitStatistics": single_stats,
        "individualTransitEvents": single_events,
    }


def build_astro_monitor_result(
    tic: int,
    observed_sectors: list[int],
    lightcurve_img: str,
    row: dict[str, Any],
    matrix: dict[str, Any] | None,
    gaia_coord: dict[str, Any] | None,
) -> dict[str, Any]:
    products_available = bool(lightcurve_img)
    has_tess_sectors = bool(observed_sectors)
    data_status = "TESS_DATA_AVAILABLE" if has_tess_sectors and products_available else "NO_TESS_DATA"
    monitor_status = data_status
    warnings: list[str] = []
    if not has_tess_sectors:
        warnings.append("No TESS sectors available")
    if not products_available:
        warnings.append("No lightcurve products available")
    ruwe = safe_float((gaia_coord or {}).get("ruwe"))
    duplicated_source = bool((gaia_coord or {}).get("duplicated_source"))
    if ruwe is not None and ruwe > 1.4:
        warnings.append("Gaia RUWE elevated")
    if duplicated_source:
        warnings.append("Gaia duplicated_source")
    text = " ".join(clean_text(value).upper() for value in (
        row.get("notes"),
        row.get("status"),
        row.get("markierung"),
        row.get("markierungs_klasse"),
        (matrix or {}).get("decision_reason"),
        (matrix or {}).get("extended_class"),
    ))
    return {
        "ticId": tic,
        "hasTessSectors": has_tess_sectors,
        "sectors": observed_sectors,
        "productsAvailable": products_available,
        "exoFopMatch": "EXOFOP" in text or "TOI" in text,
        "simbadVariableOrBinary": "VARIABLE" in text or "BINARY" in text or "EB" in text,
        "gaiaRuwe": ruwe,
        "gaiaDuplicatedSource": duplicated_source,
        "dataStatus": data_status,
        "monitorStatus": monitor_status,
        "warnings": warnings,
    }


def _method_flag(method: str, status: str, effect: str, reason: str, score: int) -> dict[str, Any]:
    return {
        "method": method,
        "status": status,
        "effect": effect,
        "reason": reason,
        "score": max(0, min(100, int(score))),
    }


def _clean_status(status: str) -> bool:
    return clean_text(status).upper() in {"CLEAN", "SUPPORTS", "LOW_RISK", "HIGH_PRIORITY", "MEDIUM_PRIORITY"}


def build_multi_method_evidence(
    *,
    tic: int,
    merged: dict[str, Any],
    matrix: dict[str, Any],
    monitor_result: dict[str, Any],
    full_vetting: dict[str, Any],
    single_transit_statistics: dict[str, Any],
    observed_sectors: list[int],
    distance: float,
    period: float,
    snr: float,
    evidence_score: float | None,
    hz: str,
    is_violet: bool,
) -> dict[str, Any]:
    flags: list[dict[str, Any]] = []

    visible_transits = safe_int_or_none(matrix.get("visible_transits")) or safe_int(merged.get("visible_transits"))
    total_transits = safe_int_or_none(matrix.get("n_transits")) or safe_int(merged.get("transit_count"))
    products_available = bool(monitor_result.get("productsAvailable"))
    sectors_available = bool(observed_sectors)
    transit_shape = clean_text(matrix.get("transit_shape")).upper()
    depth_stability = clean_text(matrix.get("depth_stability")).upper()
    sap_pdcsap = clean_text(matrix.get("sap_pdcsap_match")).upper()
    odd_even = clean_text(matrix.get("odd_even_result")).upper()
    secondary = clean_text(matrix.get("secondary_eclipse")).upper()
    rotation_risk = clean_text(matrix.get("rotation_risk")).upper()
    text = " ".join(clean_text(value).upper() for value in (
        merged.get("status"),
        merged.get("spc_class"),
        merged.get("notes"),
        matrix.get("status"),
        matrix.get("extended_class"),
        matrix.get("decision_reason"),
        matrix.get("next_step"),
        *(full_vetting.get("flags") or []),
    ))

    if not sectors_available or not products_available:
        transit_status = "NO_TESS_DATA"
        flags.append(_method_flag("transit", transit_status, "weaken", "No TESS sectors/lightcurve products available.", 0))
    elif (evidence_score or 0) >= 65 and visible_transits >= 3 and snr >= 7:
        transit_status = "SUPPORTS"
        flags.append(_method_flag("transit", transit_status, "support", f"BLS/TLS signal with SNR {snr:.1f}, {visible_transits} visible transits.", 90))
    elif (evidence_score or 0) >= 35 and visible_transits >= 2:
        transit_status = "PARTIAL_SUPPORT"
        flags.append(_method_flag("transit", transit_status, "support", f"Signal present but limited by {visible_transits} visible transits.", 62))
    else:
        transit_status = "WEAK_OR_INSUFFICIENT"
        flags.append(_method_flag("transit", transit_status, "weaken", "Transit evidence is weak or insufficient.", 25))

    individual_count = safe_int_or_none(single_transit_statistics.get("individualTransitCount") or single_transit_statistics.get("individual_transit_count")) or 0
    visible_count = safe_int_or_none(single_transit_statistics.get("visibleTransitCount") or single_transit_statistics.get("visible_transit_count")) or 0
    depth_cv = safe_float(single_transit_statistics.get("depthCv") or single_transit_statistics.get("depth_cv"))
    if individual_count < 2 or visible_count < 2:
        ttv_status = "NOT_ENOUGH_TRANSITS"
        flags.append(_method_flag("ttv", ttv_status, "neutral", "Too few measured individual transits for a TTV check.", 45))
    elif depth_cv is not None and depth_cv > 0.75:
        ttv_status = "TIMING_OR_DEPTH_SCATTER_RISK"
        flags.append(_method_flag("ttv", ttv_status, "weaken", "Individual transits show high scatter; timing fit needs review.", 35))
    else:
        ttv_status = "NO_STRONG_TTV_FLAG"
        flags.append(_method_flag("ttv", ttv_status, "support", "Individual transit set has no strong TTV scatter flag.", 70))

    gaia_ruwe = safe_float(monitor_result.get("gaiaRuwe"))
    gaia_duplicated = bool(monitor_result.get("gaiaDuplicatedSource"))
    if gaia_ruwe is not None and gaia_ruwe > 1.4:
        gaia_status = "RUWE_ELEVATED"
        flags.append(_method_flag("gaia_astrometry", gaia_status, "weaken", f"Gaia RUWE {gaia_ruwe:.2f} is elevated.", 35))
    elif gaia_duplicated:
        gaia_status = "DUPLICATED_SOURCE"
        flags.append(_method_flag("gaia_astrometry", gaia_status, "weaken", "Gaia duplicated_source is set.", 35))
    elif gaia_ruwe is None:
        gaia_status = "NOT_AVAILABLE"
        flags.append(_method_flag("gaia_astrometry", gaia_status, "neutral", "Gaia RUWE/duplicated_source not available in local export.", 50))
    else:
        gaia_status = "CLEAN"
        flags.append(_method_flag("gaia_astrometry", gaia_status, "support", "Gaia astrometry has no elevated RUWE/duplicate flag.", 80))

    simbad_variable_or_binary = bool(monitor_result.get("simbadVariableOrBinary"))
    if rotation_risk in {"HIGH", "POSSIBLE", "FAST_ROTATION_ACTIVITY_RECHECK"} or simbad_variable_or_binary:
        variability_status = "ACTIVITY_OR_VARIABLE_RISK"
        flags.append(_method_flag("variability", variability_status, "weaken", "Rotation/activity or variable/binary flag needs review.", 35))
    elif rotation_risk in {"LOW", "OK", "NO"}:
        variability_status = "CLEAN"
        flags.append(_method_flag("variability", variability_status, "support", "No strong stellar-activity flag in local checks.", 80))
    else:
        variability_status = "NOT_CHECKED"
        flags.append(_method_flag("variability", variability_status, "neutral", "Long-term variability catalog/check is not available.", 50))

    known_match = (
        bool(monitor_result.get("exoFopMatch"))
        or "TOI" in text
        or "EXOFOP" in text
        or "KNOWN_PLANET" in text
        or "NASA_EXOPLANET" in text
        or "ECLIPSING_BINARY" in text
        or " EB" in f" {text}"
    )
    if "FALSE_POSITIVE" in text or "EB_RISK" in text or "ECLIPSING_BINARY" in text:
        known_object_status = "KNOWN_FP_OR_EB"
        flags.append(_method_flag("known_object", known_object_status, "weaken", "Known-object text indicates FP/EB risk.", 10))
    elif known_match:
        known_object_status = "KNOWN_MATCH_REVIEW"
        flags.append(_method_flag("known_object", known_object_status, "neutral", "Known-object catalog match exists and needs explicit review.", 55))
    else:
        known_object_status = "NO_KNOWN_MATCH"
        flags.append(_method_flag("known_object", known_object_status, "support", "No ExoFOP/TOI/NASA/EB/SIMBAD match in local fields.", 75))

    if gaia_duplicated or (gaia_ruwe is not None and gaia_ruwe > 1.4):
        blend_status = "POSSIBLE_BLEND"
        flags.append(_method_flag("blend", blend_status, "weaken", "Gaia astrometric flags can indicate blend/contamination risk.", 35))
    else:
        blend_status = "NO_LOCAL_BLEND_FLAG"
        flags.append(_method_flag("blend", blend_status, "support", "No local Gaia duplicated/RUWE blend flag.", 70))

    radius = safe_float(merged.get("planet_radius_earth")) or 0.0
    teff = safe_float(merged.get("teff")) or 0.0
    rv_score = 0
    if distance and distance <= 150:
        rv_score += 25
    elif distance and distance <= 300:
        rv_score += 15
    else:
        rv_score += 5
    if 0.8 <= radius <= 3.5:
        rv_score += 20
    elif radius:
        rv_score += 8
    if 1 <= period <= 80:
        rv_score += 18
    elif period:
        rv_score += 8
    if 3200 <= teff <= 5600:
        rv_score += 15
    if snr >= 10:
        rv_score += 12
    if is_violet:
        rv_score += 10
    rv_score = max(0, min(100, rv_score))
    rv_priority_status = "HIGH_PRIORITY" if rv_score >= 70 else ("MEDIUM_PRIORITY" if rv_score >= 45 else "LOW_PRIORITY")
    flags.append(_method_flag("rv_priority", rv_priority_status, "support" if rv_score >= 45 else "neutral", f"RV priority score {rv_score}/100 from distance, stellar type, radius, period and SNR.", rv_score))

    science_score = 0
    if is_violet or (hz and hz not in {"", "ZU_HEISS", "UNKNOWN"}):
        science_score += 30
    if distance and distance <= 150:
        science_score += 20
    elif distance and distance <= 300:
        science_score += 12
    if 0.8 <= radius <= 2.5:
        science_score += 20
    elif 2.5 < radius <= 4:
        science_score += 12
    if 3500 <= teff <= 5400:
        science_score += 12
    science_score += min(18, max(0, visible_transits) * 4)
    science_score = max(0, min(100, science_score))
    science_priority_status = "HIGH_PRIORITY" if science_score >= 70 else ("MEDIUM_PRIORITY" if science_score >= 45 else "LOW_PRIORITY")
    flags.append(_method_flag("science_priority", science_priority_status, "support" if science_score >= 45 else "neutral", f"Science value score {science_score}/100 from HZ, distance, stellar type, radius and observed transits.", science_score))

    weighted_score = round(sum(flag["score"] for flag in flags) / max(1, len(flags)))
    clean_for_exofop = (
        transit_status in {"SUPPORTS", "PARTIAL_SUPPORT"}
        and blend_status == "NO_LOCAL_BLEND_FLAG"
        and known_object_status == "NO_KNOWN_MATCH"
        and variability_status == "CLEAN"
    )
    if not clean_for_exofop:
        # TODO(EXOFOP_READY): replace this conservative gate with the final upload workflow once
        # pixel/centroid, formal catalog crossmatches, and human review exports are available.
        flags.append(_method_flag("exofop_gate", "BLOCKED", "weaken", "EXOFOP_READY blocked until transit, blend, known-object and variability checks are clean.", 0))
        weighted_score = round(sum(flag["score"] for flag in flags) / max(1, len(flags)))

    return {
        "ticId": tic,
        "flags": flags,
        "score": weighted_score,
        "cleanForExofop": clean_for_exofop,
        "transitEvidenceStatus": transit_status,
        "ttvStatus": ttv_status,
        "gaiaAstrometryStatus": gaia_status,
        "variabilityStatus": variability_status,
        "knownObjectStatus": known_object_status,
        "blendStatus": blend_status,
        "rvPriorityStatus": rv_priority_status,
        "sciencePriorityStatus": science_priority_status,
    }




def build_candidate(
    row: dict[str, Any],
    db_row: dict[str, Any] | None,
    matrix_row: dict[str, Any] | None,
    sector_row: dict[str, Any] | None,
    gaia_row: dict[str, Any] | None,
    gaia_cache: dict[int, dict[str, float | None]],
    max_distance: float,
    tess_state: dict[str, Any],
    full_vetting: dict[str, Any] | None = None,
    single_transit_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged = {**row, **(db_row or {})}
    matrix = matrix_row or {}
    sector = sector_row or {}
    tic = safe_int(merged.get("TIC"))
    single_transit_data = single_transit_data or missing_level5_single_transit_data()
    single_transit_statistics = dict(single_transit_data.get("statistics") or {})
    single_transit_events = list(single_transit_data.get("events") or [])
    single_transit_plot_path = clean_text(
        single_transit_statistics.get("individualTransitPlotPath")
        or single_transit_statistics.get("individual_transit_plot_path")
    )
    color = color_for(merged, matrix)
    is_violet = clean_text(merged.get("hz_markierung")).upper() == "VIOLETT"
    hz_status = clean_text(merged.get("hz_status") or merged.get("hz_class"))
    distance = safe_float(merged.get("distance_ly")) or 0.0
    period = safe_float(merged.get("best_period")) or 0.0
    snr = safe_float(merged.get("transit_snr")) or 0.0
    gaia_source_id = parse_gaia_source_id(merged.get("gaia_id"))
    coord_from_cache = gaia_cache.get(gaia_source_id) if gaia_source_id else None
    gaia_coord = coord_from_cache or gaia_row or {}
    map_coord, map_source = build_map_coordinates(tic, distance, snr, max_distance, gaia_coord)
    candidate_folder = clean_text(merged.get("candidate_folder"))
    lightcurve_img = ""
    lightcurve_img_local = ""
    lightcurve_img_deploy = ""
    matrix_status_color = clean_text(matrix.get("status_color")).upper()
    evidence_score = safe_float(matrix.get("evidence_score"))
    if evidence_score is not None:
        evidence_score = round(evidence_score, 1)
    reason_tags = yellow_reason_tags(merged, matrix, is_violet)
    next_checks = next_checks_for_tags(reason_tags, matrix)
    followup_strength = (
        "STRONG"
        if "Y_STRONG_BUT_UNCONFIRMED" in reason_tags or color == "green"
        else ("MEDIUM" if evidence_score is not None and evidence_score >= _load_pipeline_config()["BUILD_MEDIUM_FOLLOWUP_EVIDENCE"] else "LOW")
    )
    yellow_summary = (
        "Gelb: starker HZ-Kandidat, aber Nachpruefung noetig"
        if color == "yellow" and is_violet and followup_strength == "STRONG"
        else (
            "Gelb: wissenschaftlich interessant, aber nicht sauber genug fuer automatisches Gruen"
            if color == "yellow"
            else ""
        )
    )
    observed_sectors = list(sector.get("sectors") or [])
    previous_sectors = list(sector.get("previousSectors") or [])
    new_sectors = list(sector.get("newSectors") or [])
    recheck = recheck_model(observed_sectors, tess_state)
    full_vetting = full_vetting or {}
    full_vetting_promotes = is_full_vetting_exofop_prep(full_vetting)
    dashboard_exofop_readiness = clean_text(full_vetting.get("exofop_readiness"))
    dashboard_full_vetting_status = clean_text(full_vetting.get("status"))
    display_labels: list[str] = []
    sap_pdcsap_match = clean_text(matrix.get("sap_pdcsap_match"))
    odd_even_result = clean_text(matrix.get("odd_even_result"))
    rotation_risk = clean_text(matrix.get("rotation_risk"))
    matrix_transits = safe_int_or_none(matrix.get("n_transits"))
    matrix_visible_transits = safe_int_or_none(matrix.get("visible_transits"))
    if full_vetting_promotes:
        color = "yellow"
        vetted_score = safe_float(full_vetting.get("evidence_score"))
        if vetted_score is not None:
            evidence_score = round(max(evidence_score or 0.0, vetted_score), 1)
        full_flags = [clean_text(flag).upper() for flag in full_vetting.get("flags", []) if clean_text(flag)]
        full_visible_transits = safe_int_or_none(full_vetting.get("visible_transits"))
        reason_tags = [
            "Y_LONG_PERIOD",
            "Y_ACTIVITY_RISK",
            "Y_MANUAL_REVIEW",
            "Y_STRONG_BUT_UNCONFIRMED",
        ]
        next_checks = ["Gaia Companion Check", "TPF Pixel Test", "Centroid Shift Analysis", "TLS Refit", "Rotation/activity check"]
        followup_strength = "STRONG"
        yellow_summary = "Gelb: hoch interessanter HZ-Kandidat, intern priorisiert, aber nicht fuer ExoFOP-Upload freigegeben"
        matrix_status_color = "YELLOW"
        matrix_status = "HIGH_VALUE_HZ_RECHECK"
        matrix_class = "FOLLOWUP_PRIORITY"
        matrix_score_band = "NOT_EXOFOP_READY"
        dashboard_exofop_readiness = "NOT_EXOFOP_READY"
        dashboard_full_vetting_status = "HIGH_VALUE_HZ_RECHECK / NOT_EXOFOP_READY"
        display_labels = [
            "FOLLOWUP_PRIORITY",
            "HIGH_VALUE_HZ_RECHECK",
            "NOT_EXOFOP_READY",
            "SAP_PDCSAP_OK",
            "ODD_EVEN_OK",
            *full_flags,
        ]
        sap_pdcsap_match = "OK"
        odd_even_result = "OK"
        rotation_risk = "FAST_ROTATION_ACTIVITY_RECHECK" if "FAST_ROTATION_ACTIVITY_RECHECK" in full_flags else rotation_risk
        matrix_visible_transits = full_visible_transits or matrix_visible_transits
        decision_reason = "Full Vetting: SAP/PDCSAP konsistent, Odd-Even OK, HZ-Ziel mit starkem Follow-up-Wert; wegen Aktivitaet/Recheck nicht fuer ExoFOP-Upload freigeben."
        next_step = "Intern weiter verfolgen: RV-Feasibility, Pixel-/Centroid-Checks und Aktivitaets-Recheck priorisieren."
    else:
        matrix_status = clean_text(matrix.get("status"))
        matrix_class = clean_text(matrix.get("extended_class"))
        matrix_score_band = clean_text(matrix.get("score_interpretation"))
        decision_reason = clean_text(matrix.get("decision_reason"))
        next_step = clean_text(matrix.get("next_step"))
        display_labels = [label for label in [matrix_class, matrix_status, matrix_score_band] if label]

    if candidate_folder:
        path = PROJECT_ROOT / candidate_folder / "lichtkurven_png" / "LICHTKURVE_COMBINED.png"
        if path.exists():
            lightcurve_img_local = rel_from_dashboard(path)
            deploy_path = sync_curve_asset(path, tic)
            if deploy_path and deploy_path.exists():
                lightcurve_img_deploy = rel_from_dashboard(deploy_path)
            lightcurve_img = lightcurve_img_deploy or lightcurve_img_local
    monitor_result = build_astro_monitor_result(
        tic=tic,
        observed_sectors=observed_sectors,
        lightcurve_img=lightcurve_img,
        row=merged,
        matrix=matrix,
        gaia_coord=gaia_coord,
    )
    multi_method = build_multi_method_evidence(
        tic=tic,
        merged=merged,
        matrix=matrix,
        monitor_result=monitor_result,
        full_vetting=full_vetting,
        single_transit_statistics=single_transit_statistics,
        observed_sectors=observed_sectors,
        distance=distance,
        period=period,
        snr=snr,
        evidence_score=evidence_score,
        hz=hz_status,
        is_violet=is_violet,
    )
    if not multi_method["cleanForExofop"] and dashboard_exofop_readiness.upper() in {"EXOFOP_READY", "READY_FOR_EXOFOP"}:
        dashboard_exofop_readiness = "NOT_EXOFOP_READY"
    final_decision = compute_final_decision(
        row=merged,
        matrix=matrix,
        sector=sector,
        full_vetting=full_vetting,
        observed_sectors=observed_sectors,
        period=period,
        monitor_result=monitor_result,
        single_transit_data=single_transit_data,
    )
    if final_decision.get("vettingStage2Class") == "WAIT_FOR_TESS":
        color = "gray"
        matrix_status = "WAIT_FOR_TESS"
        matrix_status_color = "GRAY"
        matrix_class = "WAIT_FOR_TESS"
        matrix_score_band = "NO_TESS_DATA"
        display_labels = ["WAIT_FOR_TESS", "NO_TESS_DATA"]
        reason_tags = []
        next_checks = ["Wait for TESS observations"]
        followup_strength = "LOW"
        yellow_summary = ""
        decision_reason = final_decision["decisionReason"]
        next_step = final_decision["suggestedAction"]
        sap_pdcsap_match = "NOT_RUN"
        odd_even_result = "NOT_RUN"
        rotation_risk = "NOT_RUN"
        display_reason = "WAIT_FOR_TESS"
        display_markierung = ""
        display_markierungs_klasse = "WAIT_FOR_TESS"
        display_notes = ""
        display_folder = ""
        lightcurve_img = ""
        lightcurve_img_local = ""
        lightcurve_img_deploy = ""
    else:
        display_reason = reason_for(merged, color, is_violet)
        display_markierung = clean_text(merged.get("markierung"))
        display_markierungs_klasse = clean_text(merged.get("markierungs_klasse"))
        display_notes = clean_text(merged.get("notes"))
        display_folder = candidate_folder
    spc_art_stage2_export = final_decision.get("spcArtStage2") or {}
    raw_transit_shape = clean_text(matrix.get("transit_shape"))
    raw_depth_stability = clean_text(matrix.get("depth_stability"))
    exported_transit_shape = spc_art_stage2_export.get("transitShape") or raw_transit_shape
    exported_depth_stability = spc_art_stage2_export.get("depthStability") or raw_depth_stability
    stage2_blocking_issues = spc_art_stage2_export.get("blockingIssues") or spc_art_stage2_export.get("missingChecks") or []
    shape_blocking_issues = [
        clean_text(item)
        for item in re.split(r"[;|]", clean_text(matrix.get("shape_blocking_issues")))
        if clean_text(item)
    ]
    folded_shape_metrics = {
        "transitShape": raw_transit_shape,
        "transitShapeScore": safe_float(matrix.get("transit_shape_score")),
        "transitShapeSource": clean_text(matrix.get("transit_shape_source")),
        "shapeStatus": clean_text(matrix.get("shape_status")),
        "shapeSnr": safe_float(matrix.get("shape_snr")),
        "measuredDepthPpt": safe_float(matrix.get("measured_depth_ppt")),
        "secondaryDepthPpt": safe_float(matrix.get("secondary_depth_ppt")),
        "secondaryRatioMeasured": safe_float(matrix.get("secondary_ratio_measured")),
        "baselineLeftRightDeltaPpt": safe_float(matrix.get("baseline_left_right_delta_ppt")),
        "ootScatterPpt": safe_float(matrix.get("oot_scatter_ppt")),
        "foldedLcQuality": clean_text(matrix.get("folded_lc_quality")),
        "vShapeScore": safe_float(matrix.get("v_shape_score")),
        "shapeBlockingIssues": shape_blocking_issues,
    }
    return {
        "tic": tic,
        "status": "WAIT_FOR_TESS" if final_decision.get("vettingStage2Class") == "WAIT_FOR_TESS" else clean_text(merged.get("status")),
        "color": color,
        "colorLabel": color_label("violet" if is_violet else color),
        "baseColorLabel": color_label(color),
        "isViolet": is_violet,
        "reason": display_reason,
        "markierung": display_markierung,
        "markierungsKlasse": display_markierungs_klasse,
        "hzMarkierung": clean_text(merged.get("hz_markierung")),
        "hz": hz_status,
        "distance": round(distance, 2),
        "teff": round(safe_float(merged.get("teff")) or 0.0, 0),
        "starRadius": round(safe_float(merged.get("stellar_radius")) or 0.0, 3),
        "period": round(period, 4),
        "radius": round(safe_float(merged.get("planet_radius_earth")) or 0.0, 2),
        "snr": round(snr, 2),
        "gaiaSourceId": gaia_source_id,
        "raDeg": safe_float(gaia_coord.get("ra")) if gaia_coord else None,
        "decDeg": safe_float(gaia_coord.get("dec")) if gaia_coord else None,
        "parallaxMas": safe_float(gaia_coord.get("parallax")) if gaia_coord else None,
        "mapSource": map_source,
        "transits": safe_int(merged.get("transit_count")),
        "visibleTransits": safe_int(merged.get("visible_transits")),
        "cleanSectors": safe_int(merged.get("clean_sector_count")),
        "matrixStatus": matrix_status,
        "matrixColor": matrix_status_color,
        "matrixClass": matrix_class,
        "matrixScoreBand": matrix_score_band,
        "displayLabels": list(dict.fromkeys(display_labels)),
        "evidenceScore": evidence_score,
        "reasonTags": reason_tags,
        "nextChecks": next_checks,
        "followupStrength": followup_strength,
        "yellowSummary": yellow_summary,
        "decisionReason": decision_reason,
        "nextStep": next_step,
        "matrixTransits": safe_int_or_none(matrix.get("n_transits")),
        "matrixSectors": safe_int_or_none(matrix.get("n_sectors")),
        "matrixVisibleTransits": matrix_visible_transits,
        "matrixCleanSectors": safe_int_or_none(matrix.get("clean_sector_count")),
        "depthPpt": safe_float(matrix.get("depth_ppt")),
        "durationHours": safe_float(matrix.get("duration_hours")),
        "sapPdcsapMatch": sap_pdcsap_match,
        "oddEvenResult": odd_even_result,
        "transitShape": exported_transit_shape,
        "transitShapeScore": folded_shape_metrics["transitShapeScore"],
        "transitShapeSource": folded_shape_metrics["transitShapeSource"],
        "shapeStatus": folded_shape_metrics["shapeStatus"],
        "shapeSnr": folded_shape_metrics["shapeSnr"],
        "foldedLcQuality": folded_shape_metrics["foldedLcQuality"],
        "foldedLightCurveShape": folded_shape_metrics,
        "folded_light_curve_shape": folded_shape_metrics,
        "depthStability": exported_depth_stability,
        "rawTransitShape": raw_transit_shape,
        "rawDepthStability": raw_depth_stability,
        "transit_shape": exported_transit_shape,
        "depth_stability": exported_depth_stability,
        "raw_transit_shape": raw_transit_shape,
        "raw_depth_stability": raw_depth_stability,
        "dataGapRisk": clean_text(matrix.get("data_gap_risk")),
        "sectorEdgeRisk": clean_text(matrix.get("sector_edge_risk")),
        "secondaryEclipse": clean_text(matrix.get("secondary_eclipse")),
        "periodAliasRisk": clean_text(matrix.get("period_alias_risk")),
        "rotationRisk": rotation_risk,
        "nextRecheck": clean_text(merged.get("next_recheck")),
        "revisitPriority": clean_text(merged.get("revisit_priority")),
        "notes": display_notes,
        "observedSectors": observed_sectors,
        "plannedSectors": recheck["plannedSectors"],
        "planned_sectors": recheck["plannedSectors"],
        "plannedSectorDetails": recheck["plannedSectorDetails"],
        "currentSector": recheck["currentSector"],
        "current_sector": recheck["currentSector"],
        "nextPlannedSector": recheck["nextPlannedSector"],
        "next_planned_sector": recheck["nextPlannedSector"],
        "latestPlannedSector": recheck["latestPlannedSector"],
        "recheckStatus": recheck["recheckStatus"],
        "recheck_status": recheck["recheckStatus"],
        "estimatedDataAvailable": recheck["estimatedDataAvailable"],
        "estimated_data_available": recheck["estimatedDataAvailable"],
        "observedSectorCount": safe_int_or_none(sector.get("sector_count")) or len(observed_sectors),
        "previousSectors": previous_sectors,
        "previousSectorCount": safe_int_or_none(sector.get("previous_sector_count")) or len(previous_sectors),
        "newSectors": new_sectors,
        "sectorInventoryStatus": clean_text(sector.get("source_status")),
        "sectorLastCheckedAt": clean_text(sector.get("last_checked_at")),
        "sectorLastNewAt": clean_text(sector.get("last_new_sector_at")),
        "astroMonitor": monitor_result,
        "monitorStatus": final_decision.get("monitorStatus", monitor_result["monitorStatus"]),
        "dataStatus": final_decision.get("dataStatus", monitor_result["dataStatus"]),
        "signalStatus": final_decision.get("signalStatus", ""),
        "vettingStage2Class": final_decision.get("vettingStage2Class", ""),
        "suggestedAction": final_decision.get("suggestedAction", ""),
        "methodEvidenceFlags": multi_method["flags"],
        "method_evidence_flags": multi_method["flags"],
        "multiMethodScore": multi_method["score"],
        "multi_method_score": multi_method["score"],
        "multiMethodCleanForExofop": multi_method["cleanForExofop"],
        "multi_method_clean_for_exofop": multi_method["cleanForExofop"],
        "transitEvidenceStatus": multi_method["transitEvidenceStatus"],
        "transit_evidence_status": multi_method["transitEvidenceStatus"],
        "ttvStatus": multi_method["ttvStatus"],
        "ttv_status": multi_method["ttvStatus"],
        "gaiaAstrometryStatus": multi_method["gaiaAstrometryStatus"],
        "gaia_astrometry_status": multi_method["gaiaAstrometryStatus"],
        "variabilityStatus": multi_method["variabilityStatus"],
        "variability_status": multi_method["variabilityStatus"],
        "knownObjectStatus": multi_method["knownObjectStatus"],
        "known_object_status": multi_method["knownObjectStatus"],
        "blendStatus": multi_method["blendStatus"],
        "blend_status": multi_method["blendStatus"],
        "rvPriorityStatus": multi_method["rvPriorityStatus"],
        "rv_priority_status": multi_method["rvPriorityStatus"],
        "sciencePriorityStatus": multi_method["sciencePriorityStatus"],
        "science_priority_status": multi_method["sciencePriorityStatus"],
        "spcArtStage2": spc_art_stage2_export or None,
        "individualTransitStatistics": single_transit_statistics,
        "individual_transit_statistics": single_transit_statistics,
        "individualTransitEvents": single_transit_events,
        "individual_transit_events": single_transit_events,
        "individualTransitPlotPath": single_transit_plot_path,
        "individual_transit_plot_path": single_transit_plot_path,
        "individualTransitPlotStatus": single_transit_statistics.get("plotStatus", "PLOT_NOT_AVAILABLE"),
        "individual_transit_plot_status": single_transit_statistics.get("plotStatus", "PLOT_NOT_AVAILABLE"),
        "singleTransitStatus": spc_art_stage2_export.get("singleTransitStatus", ""),
        "individualTransitStatus": spc_art_stage2_export.get("individualTransitStatus", ""),
        "individual_transit_status": spc_art_stage2_export.get("individualTransitStatus", ""),
        "depthStabilityScore": spc_art_stage2_export.get("depthStabilityScore"),
        "depth_stability_score": spc_art_stage2_export.get("depthStabilityScore"),
        "foldedLightCurveStatus": spc_art_stage2_export.get("foldedLightCurveStatus", ""),
        "activityStatus": spc_art_stage2_export.get("activityStatus", ""),
        "activityRotationStatus": spc_art_stage2_export.get("activityRotationStatus", ""),
        "activity_rotation_status": spc_art_stage2_export.get("activityRotationStatus", ""),
        "stage2Completed": bool(spc_art_stage2_export.get("stage2Completed")),
        "stage2_completed": bool(spc_art_stage2_export.get("stage2Completed")),
        "stage2FallbackUsed": bool(spc_art_stage2_export.get("fallbackUsed")),
        "stage2_fallback_used": bool(spc_art_stage2_export.get("fallbackUsed")),
        "stage2ComputationStatus": spc_art_stage2_export.get("computationStatus", "NOT_COMPUTED"),
        "stage2_computation_status": spc_art_stage2_export.get("computationStatus", "NOT_COMPUTED"),
        "stage2BlockingIssues": stage2_blocking_issues,
        "stage2_blocking_issues": stage2_blocking_issues,
        "visible_transits": spc_art_stage2_export.get("visibleTransits", matrix_visible_transits),
        "total_transits": spc_art_stage2_export.get("totalTransits", safe_int_or_none(matrix.get("n_transits"))),
        "fullVetting": {
            "classification": clean_text(full_vetting.get("classification")),
            "evidence_score": safe_float(full_vetting.get("evidence_score")),
            "sap_pdcsap_ratio": safe_float(full_vetting.get("sap_pdcsap_ratio")),
            "rotation_period": safe_float(full_vetting.get("rotation_period")),
            "odd_even_status": clean_text(full_vetting.get("odd_even_status")),
            "exofop_readiness": dashboard_exofop_readiness,
            "flags": [clean_text(flag) for flag in full_vetting.get("flags", []) if clean_text(flag)],
            "visible_transits": safe_int_or_none(full_vetting.get("visible_transits")),
            "report_dir": clean_text(full_vetting.get("report_dir")),
            "status": dashboard_full_vetting_status,
        } if full_vetting else None,
        "finalDecision": final_decision,
        "folder": display_folder,
        "lightcurveImg": lightcurve_img,
        "lightcurveImgLocal": lightcurve_img_local,
        "lightcurveImgDeploy": lightcurve_img_deploy,
        "map": map_coord,
    }


def bucket(counter: Counter[str], key: str) -> int:
    return int(counter.get(key, 0))


def build_tree(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    colors = Counter(candidate["color"] for candidate in candidates)
    violet = sum(1 for candidate in candidates if candidate["isViolet"])
    hz = Counter(candidate["hz"] or "UNKNOWN" for candidate in candidates)
    status = Counter(candidate["status"] or "UNKNOWN" for candidate in candidates)
    return [
        {
            "id": "level0",
            "title": "Level 0: erste Farbsortierung",
            "description": "Die sichtbare Farbe kommt aus der Evidence-Matrix; alte Level-0-Gruenlabels werden nur noch uebernommen, wenn das Vetting sie bestaetigt.",
            "children": [
                {"label": "Gruen", "count": bucket(colors, "green"), "meaning": "Matrix-bestaetigter SPC-Kandidat mit erfuellten Vetting-Kriterien."},
                {"label": "Gelb", "count": bucket(colors, "yellow"), "meaning": "Noch nicht genug Daten oder unklare Lage."},
                {"label": "Rot", "count": bucket(colors, "red"), "meaning": "False Positive, Artefakt oder Systematik-Risiko."},
                {"label": "Violett", "count": violet, "meaning": "HZ-Ziel oder Top-Tier; liegt als Zusatzfarbe ueber gruen/gelb/rot."},
            ],
        },
        {
            "id": "hz",
            "title": "HZ: warum violett?",
            "description": "Violett ist kein Ersatz fuer rot/gruen/gelb, sondern ein Fokusmarker: Habitable-Zone oder Top-Tier.",
            "children": [
                {"label": "Konservative HZ", "count": bucket(hz, "KONSERVATIVE_HZ"), "meaning": "Periode liegt im engeren HZ-Fenster."},
                {"label": "Optimistische HZ innen", "count": bucket(hz, "OPT_HZ_INNEN"), "meaning": "Nah an der warmen HZ-Kante."},
                {"label": "Zu heiss", "count": bucket(hz, "ZU_HEISS"), "meaning": "Nicht HZ, aber kann trotzdem gruen sein."},
            ],
        },
        {
            "id": "next",
            "title": "Naechste Aktion",
            "description": "Die Farbe entscheidet nicht allein. Der naechste Schritt kommt aus Status, HZ und Vetting-Hinweisen.",
            "children": [
                {"label": "SPC-A/B/C", "count": sum(status.get(key, 0) for key in ("SPC-A", "SPC-B", "SPC-C")), "meaning": "weiter untersuchen"},
                {"label": "Mehr TESS", "count": bucket(status, "NEEDS_MORE_TESS_DATA"), "meaning": "warten/rechecken"},
                {"label": "False Positive", "count": bucket(status, "FALSE_POSITIVE") + bucket(status, "FP_ART"), "meaning": "depriorisieren"},
                {"label": "Artefakt", "count": bucket(status, "SPC_ART"), "meaning": "nur mit starker Evidenz weiter"},
            ],
        },
    ]


def candidate_rank_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    evidence = safe_float(candidate.get("evidenceScore")) or 0.0
    snr = safe_float(candidate.get("snr")) or 0.0
    distance = safe_float(candidate.get("distance")) or 999999.0
    followup = clean_text(candidate.get("followupStrength")).upper()
    final_class = clean_text(candidate.get("vettingStage2Class") or (candidate.get("finalDecision") or {}).get("vettingStage2Class")).upper()
    matrix_class = " ".join(clean_text(value).upper() for value in (
        candidate.get("matrixClass"),
        candidate.get("matrixStatus"),
        candidate.get("status"),
        *(candidate.get("displayLabels") or []),
    ))
    is_readyish = final_class in {"GREEN_SPC", "YELLOW_RECHECK"} or "SPC_FOLLOWUP_READY" in matrix_class
    is_fp = final_class == "RED_FP" or "FALSE_POSITIVE" in matrix_class or candidate.get("color") == "red"
    # TODO(EXOFOP_READY): when the EXOFOP_READY workflow is implemented, add its readiness signal
    # ahead of generic GREEN_SPC/YELLOW_RECHECK in this key instead of treating it as readyish.
    return (
        1 if is_fp else 0,
        0 if followup == "STRONG" else (1 if followup == "MEDIUM" else 2),
        0 if is_readyish else 1,
        0 if candidate.get("isViolet") else 1,
        0 if candidate.get("color") == "green" else (1 if candidate.get("color") == "yellow" else 2),
        -evidence,
        -snr,
        distance,
        safe_int(candidate.get("tic")),
    )


def apply_candidate_ranking(candidates: list[dict[str, Any]], previous_by_tic: dict[int, dict[str, Any]]) -> None:
    generated_at = datetime.now().isoformat(timespec="seconds")
    candidates.sort(key=candidate_rank_key)
    for index, candidate in enumerate(candidates, start=1):
        tic = safe_int(candidate.get("tic"))
        previous = previous_by_tic.get(tic, {})
        previous_rank = safe_int_or_none(previous.get("rank"))
        previous_score = safe_float(previous.get("evidenceScore"))
        new_score = safe_float(candidate.get("evidenceScore"))
        previous_sectors = set(previous.get("observedSectors") or [])
        current_sectors = set(candidate.get("observedSectors") or [])
        added_sectors = sorted(current_sectors - previous_sectors)
        if not added_sectors:
            added_sectors = list(candidate.get("newSectors") or [])

        candidate["rank"] = index
        candidate["rankPrevious"] = previous_rank
        candidate["rank_previous"] = previous_rank
        candidate["scorePrevious"] = round(previous_score, 1) if previous_score is not None else None
        candidate["score_previous"] = candidate["scorePrevious"]
        candidate["lastSectorAdded"] = max(added_sectors) if added_sectors else previous.get("lastSectorAdded")
        candidate["last_sector_added"] = candidate["lastSectorAdded"]

        changed_fields: list[dict[str, Any]] = []
        for field in ("status", "matrixStatus", "matrixClass", "color", "followupStrength"):
            if previous and previous.get(field) != candidate.get(field):
                changed_fields.append({"field": field, "before": previous.get(field), "after": candidate.get(field)})
        if previous_rank is not None and previous_rank != index:
            changed_fields.append({"field": "rank", "before": previous_rank, "after": index})
        if previous_score is not None and new_score is not None and round(previous_score, 1) != round(new_score, 1):
            changed_fields.append({"field": "evidenceScore", "before": round(previous_score, 1), "after": round(new_score, 1)})
        if added_sectors:
            changed_fields.append({"field": "observedSectors", "before": sorted(previous_sectors), "after": sorted(current_sectors)})

        history = list(previous.get("updateHistory") or previous.get("update_history") or [])
        if changed_fields:
            history.append({
                "checkedAt": generated_at,
                "event": "AUTO_RERANK",
                "rankPrevious": previous_rank,
                "rank": index,
                "scorePrevious": round(previous_score, 1) if previous_score is not None else None,
                "score": round(new_score, 1) if new_score is not None else None,
                "newSectors": added_sectors,
                "changes": changed_fields,
            })
            history = history[-20:]

        candidate["updateHistory"] = history
        candidate["update_history"] = history
        if changed_fields:
            candidate["lastUpdated"] = generated_at
        else:
            candidate["lastUpdated"] = previous.get("lastUpdated") or previous.get("last_updated") or generated_at
        candidate["last_updated"] = candidate["lastUpdated"]
        candidate["updateStatus"] = "UPDATED" if changed_fields else previous.get("updateStatus", "")
        candidate["update_status"] = candidate["updateStatus"]


def candidate_summary_record(candidate: dict[str, Any]) -> dict[str, Any]:
    fields = [
        "tic", "status", "color", "colorLabel", "baseColorLabel", "isViolet", "hz",
        "distance", "period", "snr", "evidenceScore", "multiMethodScore",
        "matrixStatus", "matrixColor", "matrixClass", "matrixScoreBand",
        "displayLabels", "followupStrength", "decisionReason", "nextStep",
        "visibleTransits", "transits", "matrixVisibleTransits", "matrixTransits",
        "observedSectors", "plannedSectors", "observedSectorCount", "recheckStatus",
        "estimatedDataAvailable", "currentSector", "nextPlannedSector", "latestPlannedSector",
        "transitEvidenceStatus", "ttvStatus", "gaiaAstrometryStatus",
        "variabilityStatus", "knownObjectStatus", "blendStatus",
        "rvPriorityStatus", "sciencePriorityStatus", "multiMethodCleanForExofop",
        "lightcurveImg", "map", "mapSource", "rank",
    ]
    record = {field: candidate.get(field) for field in fields if field in candidate}
    record["detailsPath"] = f"candidate-details/TIC_{candidate.get('tic')}.json"
    return record


def write_candidate_summary_data(data: dict[str, Any]) -> None:
    summary_payload = {
        "generatedAt": data.get("generatedAt"),
        "summary": data.get("summary"),
        "tess": data.get("tess"),
        "tree": data.get("tree"),
        "candidates": [candidate_summary_record(candidate) for candidate in data.get("candidates", [])],
        "splitDataVersion": 1,
        "detailsPattern": "candidate-details/TIC_{tic}.json",
    }
    CANDIDATE_SUMMARY_PATH.write_text(
        json.dumps(summary_payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def write_candidate_detail_data(candidates: list[dict[str, Any]]) -> None:
    if CANDIDATE_DETAILS_DIR.exists():
        shutil.rmtree(CANDIDATE_DETAILS_DIR)
    CANDIDATE_DETAILS_DIR.mkdir(parents=True, exist_ok=True)
    for candidate in candidates:
        tic = safe_int(candidate.get("tic"))
        if not tic:
            continue
        (CANDIDATE_DETAILS_DIR / f"TIC_{tic}.json").write_text(
            json.dumps(candidate, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )


def main() -> int:
    args = parse_args()
    build_started = time.monotonic()
    previous_payload = load_existing_dashboard_data()
    previous_by_tic = existing_candidate_index(previous_payload)
    summary_counts = {"processed": 0, "updated": 0, "failed": 0, "skipped": 0}
    auto_updated = False
    try:
        auto_updated = run_auto_update(args)
    except Exception as exc:
        print(f"[auto-update] ERROR {type(exc).__name__}: {exc}", flush=True)
        summary_counts["failed"] += 1
    db_rows, matrix_rows, sector_rows, local_coord_rows = load_db_rows()
    with MANIFEST_PATH.open(newline="", encoding="utf-8") as handle:
        manifest_rows = list(csv.DictReader(handle))
    original_manifest_count = len(manifest_rows)
    if args.tic:
        manifest_rows = [row for row in manifest_rows if safe_int(row.get("TIC")) == args.tic]
        summary_counts["skipped"] += original_manifest_count - len(manifest_rows)
        if not manifest_rows:
            print(f"[build] ERROR TIC {args.tic} not found in manifest", flush=True)
            print(f"[summary] processed=0 updated=0 failed={summary_counts['failed'] + 1} skipped={summary_counts['skipped']}", flush=True)
            return 1
    elif args.limit:
        manifest_rows = manifest_rows[: max(0, int(args.limit))]
        summary_counts["skipped"] += original_manifest_count - len(manifest_rows)
    print(
        f"[build] candidates selected={len(manifest_rows)} skipped={summary_counts['skipped']} "
        f"mode={'tic=' + str(args.tic) if args.tic else ('limit=' + str(args.limit) if args.limit else 'full')}",
        flush=True,
    )
    if not manifest_rows:
        print(f"[summary] processed=0 updated=0 failed={summary_counts['failed']} skipped={summary_counts['skipped']}", flush=True)
        return 1

    gaia_cache = load_gaia_cache()
    manifest_tics = [safe_int(row.get("TIC")) for row in manifest_rows]
    source_ids_to_query: list[int] = []
    for tic in manifest_tics:
        db_row = db_rows.get(tic) or {}
        local_coord = local_coord_rows.get(tic) or {}
        gaia_source_id = parse_gaia_source_id(db_row.get("gaia_id") or local_coord.get("gaia_id"))
        if gaia_source_id is None:
            continue
        if gaia_source_id in gaia_cache:
            cached = gaia_cache.get(gaia_source_id) or {}
            if safe_float(cached.get("ra")) is not None and safe_float(cached.get("dec")) is not None:
                continue
        source_ids_to_query.append(gaia_source_id)

    fetched_coords = fetch_gaia_coordinates(
        source_ids_to_query,
        timeout_seconds=args.gaia_api_timeout,
        offline_cache=args.offline_cache,
    )
    if fetched_coords:
        gaia_cache.update(fetched_coords)
        save_gaia_cache(gaia_cache)

    full_vetting_reports = load_full_vetting_reports()
    level5_single_transits = load_level5_single_transit_data()
    tess_state = build_tess_state()
    max_distance = max(safe_float(row.get("distance_ly")) or 0.0 for row in manifest_rows)
    candidates: list[dict[str, Any]] = []
    failed_candidates: list[dict[str, Any]] = []
    progress_every = max(1, int(args.progress_every or 1))
    total_selected = len(manifest_rows)
    for index, row in enumerate(manifest_rows, start=1):
        tic = safe_int(row.get("TIC"))
        if index == 1 or index == total_selected or index % progress_every == 0 or args.tic:
            print(f"[build] candidate {index}/{total_selected} TIC {tic}", flush=True)
        try:
            candidate = build_candidate(
                row,
                db_rows.get(tic),
                matrix_rows.get(tic),
                sector_rows.get(tic),
                local_coord_rows.get(tic),
                gaia_cache,
                max_distance,
                tess_state,
                full_vetting_reports.get(tic),
                level5_single_transits.get(tic),
            )
            candidates.append(candidate)
            summary_counts["processed"] += 1
        except Exception as exc:
            summary_counts["failed"] += 1
            failed_candidates.append({"tic": tic, "error": f"{type(exc).__name__}: {exc}"})
            print(f"[build] TIC {tic}: ERROR {type(exc).__name__}: {exc}", flush=True)
    if failed_candidates:
        print(f"[build] failed candidates: {json.dumps(failed_candidates[:20], ensure_ascii=False)}", flush=True)
    if not candidates:
        print(
            f"[summary] processed=0 updated=0 failed={summary_counts['failed']} skipped={summary_counts['skipped']}",
            flush=True,
        )
        return 1
    # Override color based on final decision status
    for candidate in candidates:
        fd = candidate.get("finalDecision", {})
        final_status = fd.get("status", "")
        if final_status == "EXOFOP_BEREIT":
            candidate["color"] = "green"
        elif final_status in {"ZU_WENIG_DATEN"}:
            # Not enough data -> gray
            if candidate.get("color") == "red":
                candidate["color"] = "gray"
        elif final_status == "SPC_ART_RECHECK":
            # Artifact concerns -> orange (preserve original color or set to orange)
            if candidate.get("color") == "red":
                candidate["color"] = "orange"
        elif final_status == "SPC_PREP":
            # Good signal but some checks missing -> yellow
            if candidate.get("color") == "red":
                candidate["color"] = "yellow"
        elif final_status == "NO_PLANET":
            # False Positive -> keep red if there are hard failures
            if not fd.get("failed_checks") and candidate.get("color") == "red":
                candidate["color"] = "gray"

    apply_candidate_ranking(candidates, previous_by_tic)
    summary_counts["updated"] = sum(1 for candidate in candidates if candidate.get("updateStatus") == "UPDATED")

    lightcurve_candidates = [
        candidate for candidate in candidates
        if candidate["lightcurveImg"]
    ]
    priority_candidates = sorted(
        lightcurve_candidates,
        key=lambda item: (
            not (item.get("followupStrength") == "STRONG"),
            not item["isViolet"],
            item["color"] != "green",
            -safe_float(item.get("evidenceScore")) if safe_float(item.get("evidenceScore")) is not None else 0,
            -item["snr"],
            item["distance"],
        ),
    )

    summary = {
        "total": len(candidates),
        "green": sum(1 for candidate in candidates if candidate["color"] == "green"),
        "yellow": sum(1 for candidate in candidates if candidate["color"] == "yellow"),
        "red": sum(1 for candidate in candidates if candidate["color"] == "red"),
        "violet": sum(1 for candidate in candidates if candidate["isViolet"]),
        "lightcurves": len(lightcurve_candidates),
        "mapAstrometric": sum(1 for candidate in candidates if candidate["mapSource"] == "gaia_dr3"),
        "mapFallback": sum(1 for candidate in candidates if candidate["mapSource"] != "gaia_dr3"),
        "gaiaCacheSize": len(gaia_cache),
        "autoTessUpdateRan": auto_updated,
        "recheckLiveNow": sum(1 for candidate in candidates if candidate["recheckStatus"] == "LIVE_NOW"),
        "recheckUpcoming": sum(1 for candidate in candidates if candidate["recheckStatus"] == "UPCOMING"),
        "recheckWaitingData": sum(1 for candidate in candidates if candidate["recheckStatus"] == "WAITING_DATA"),
        "recheckNotPlanned": sum(1 for candidate in candidates if candidate["recheckStatus"] == "NO_PLANNED_RECHECK"),
    }
    summary["mapCoveragePct"] = round(
        100.0 * summary["mapAstrometric"] / max(1, summary["total"]),
        2,
    )
    summary["mapMode"] = (
        "gaia_full"
        if summary["mapAstrometric"] == summary["total"]
        else ("gaia_mixed" if summary["mapAstrometric"] > 0 else "heuristic_only")
    )
    summary["coordinatesUpdatedAt"] = datetime.now().isoformat(timespec="seconds")

    data = {
        "generatedAt": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "tess": tess_state,
        "tree": build_tree(candidates),
        "candidates": candidates,
        "lightcurveCandidates": lightcurve_candidates,
        "priorityCandidates": priority_candidates,
    }

    OUT_PATH.write_text(
        "window.ASTRO_DASHBOARD_DATA = "
        + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    write_candidate_summary_data(data)
    write_candidate_detail_data(candidates)
    print(f"wrote {OUT_PATH}")
    print(f"wrote {CANDIDATE_SUMMARY_PATH}")
    print(f"wrote {CANDIDATE_DETAILS_DIR} ({len(candidates)} files)")
    print(json.dumps(summary, ensure_ascii=False))
    elapsed = time.monotonic() - build_started
    print(
        f"[summary] processed={summary_counts['processed']} updated={summary_counts['updated']} "
        f"failed={summary_counts['failed']} skipped={summary_counts['skipped']} elapsed={elapsed:.1f}s",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
