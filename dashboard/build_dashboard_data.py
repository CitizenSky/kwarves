#!/usr/bin/env python3
"""Build the static data bundle used by dashboard/index.html."""

from __future__ import annotations

import csv
import argparse
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
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
OUT_PATH = DASHBOARD_DIR / "dashboard-data.js"
GAIA_CACHE_PATH = DASHBOARD_DIR / "gaia_coordinates_cache.csv"
GAIA_FETCH_BATCH_SIZE = int(os.environ.get("GAIA_FETCH_BATCH_SIZE", "350"))
GAIA_FETCH_ENABLED = os.environ.get("GAIA_FETCH_ENABLED", "1").strip() not in {"0", "false", "False"}
AUTO_TESS_UPDATE_ENABLED = os.environ.get("KWARVES_AUTO_TESS_UPDATE", "1").strip() not in {"0", "false", "False"}
AUTO_TESS_MAX_AGE_HOURS = float(os.environ.get("KWARVES_AUTO_TESS_MAX_AGE_HOURS", "18"))
AUTO_TESS_SLEEP = float(os.environ.get("KWARVES_AUTO_TESS_SLEEP", "0.2"))

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
    parser.add_argument("--no-auto-update", action="store_true", help="Skip automatic TESS sector refresh and matrix rebuild.")
    parser.add_argument("--force-auto-update", action="store_true", help="Run TESS refresh even when inventory is still fresh.")
    parser.add_argument("--auto-update-limit", type=int, default=None, help="Limit candidates checked against MAST during automatic refresh.")
    parser.add_argument("--auto-update-sleep", type=float, default=AUTO_TESS_SLEEP, help="Delay between MAST queries during automatic refresh.")
    parser.add_argument("--no-sector-mark", action="store_true", help="Record new sectors but do not mark candidates RECHECK_NEW_SECTOR.")
    return parser.parse_args()


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


def fetch_gaia_coordinates(source_ids: list[int]) -> dict[int, dict[str, float | None]]:
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
        job = Gaia.launch_job_async(
            query=query,
            upload_resource=upload,
            upload_table_name="src_ids",
            verbose=False,
        )
        rows = job.get_results()
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


def run_command(command: list[str], label: str) -> None:
    print(f"[auto-update] {label}: {' '.join(command)}")
    subprocess.run(command, cwd=SCRIPT_ROOT, check=True)


def run_auto_update(args: argparse.Namespace) -> bool:
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
    ]
    if args.auto_update_limit:
        sector_cmd.extend(["--limit", str(args.auto_update_limit)])
    if args.no_sector_mark:
        sector_cmd.append("--no-mark")

    run_command(sector_cmd, "refresh TESS sector inventory")
    run_command([sys.executable, str(SCRIPT_ROOT / "main" / "build_candidate_matrix.py")], "rebuild candidate matrix")
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
                       sap_pdcsap_match, odd_even_result, transit_shape, depth_stability,
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
    
    # === Step 1: TESS Data ===
    has_tess_data = bool(observed_sectors)
    if not has_tess_data:
        check_tree.append({"name": "TESS Data", "status": "failed", "reason": "No TESS sectors available"})
        failed_checks.append("TESS Data")
        blockers.append("No TESS data available")
        return {
            "status": "NO_PLANET", "reason": "No TESS observations available.",
            "failed_test": "TESS Data", "next_action": "Wait for TESS observations.",
            "signal_quality": "unknown", "data_quality": "low", "matrix_cell": "no_tess_data",
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
            "status": "NO_PLANET", "reason": "No statistically significant transit signal detected.",
            "failed_test": "Signal Detection", "next_action": "Signal detection failed.",
            "signal_quality": "weak", "data_quality": "sufficient", "matrix_cell": "no_signal",
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
            "status": "NO_PLANET", "reason": f"False Positive: {fp_reason}. Candidate is likely not a planet.",
            "failed_test": "False Positive", "next_action": "Candidate excluded from follow-up.",
            "signal_quality": "weak", "data_quality": "sufficient", "matrix_cell": "false_positive",
            "passed_checks": passed_checks, "warning_checks": [], "failed_checks": ["Vetting Checks"],
            "not_run_checks": [], "blockers": [fp_reason], "check_tree": check_tree
        }
    
    # 2. Check for ZU WENIG DATEN (not enough data to assess)
    if not has_sufficient_sectors or not has_sufficient_transits:
        check_tree.append({"name": "Decision", "status": "warning", "reason": "Insufficient data for reliable assessment"})
        return {
            "status": "ZU_WENIG_DATEN", "reason": f"Not enough data: only {observed_transits} visible transits, {sector_count} sectors. Cannot reliably assess signal.",
            "failed_test": "Data Limit", "next_action": "Wait for additional TESS sectors or data.",
            "signal_quality": "strong", "data_quality": "low", "matrix_cell": "data_limited",
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
            "status": "SPC_ART_RECHECK", 
            "reason": f"Strong candidate, but artifact/systematics concerns remain: {', '.join(artifact_reasons)}. Manual vetting required.",
            "failed_test": "Artifact Check", "next_action": "Clean lightcurve, verify SAP/PDCSAP, check activity/rotation, analyze outliers.",
            "signal_quality": "medium", "data_quality": "medium", "matrix_cell": "artifact_recheck",
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
            "status": "SPC_PREP", 
            "reason": f"Strong signal and good data, but unresolved vetting checks: {', '.join(prep_reasons)}.",
            "failed_test": "Vetting Incomplete", "next_action": "Complete missing vetting checks before ExoFOP submission.",
            "signal_quality": "strong", "data_quality": "good", "matrix_cell": "spc_prep",
            "passed_checks": passed_checks, "warning_checks": warning_checks, "failed_checks": [],
            "not_run_checks": not_run_checks, "blockers": prep_reasons, "check_tree": check_tree
        }
    
    # 5. EXOFOP BEREIT - all checks passed
    check_tree.append({"name": "Decision", "status": "passed", "reason": "All scientific requirements met"})
    
    return {
        "status": "EXOFOP_BEREIT", 
        "reason": "Candidate meets all scientific requirements for ExoFOP submission.",
        "failed_test": None, "next_action": "Ready for ExoFOP upload and follow-up prioritization.",
        "signal_quality": "strong", "data_quality": "high", "matrix_cell": "exofop_ready",
        "passed_checks": passed_checks, "warning_checks": [], "failed_checks": [],
        "not_run_checks": not_run_checks, "blockers": [], "check_tree": check_tree
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
) -> dict[str, Any]:
    merged = {**row, **(db_row or {})}
    matrix = matrix_row or {}
    sector = sector_row or {}
    tic = safe_int(merged.get("TIC"))
    color = color_for(merged, matrix)
    is_violet = clean_text(merged.get("hz_markierung")).upper() == "VIOLETT"
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
            label_blob = " ".join([matrix_status, matrix_class, matrix_score_band, *display_labels]).upper()
            sync_for_dashboard = (
                is_violet
                or color == "green"
                or followup_strength == "STRONG"
                or "SPC_FOLLOWUP_READY" in label_blob
                or "FOLLOWUP_PRIORITY" in label_blob
            )
            if sync_for_dashboard:
                deploy_path = sync_curve_asset(path, tic)
                if deploy_path and deploy_path.exists():
                    lightcurve_img_deploy = rel_from_dashboard(deploy_path)
            lightcurve_img = lightcurve_img_deploy or lightcurve_img_local
    return {
        "tic": tic,
        "status": clean_text(merged.get("status")),
        "color": color,
        "colorLabel": color_label("violet" if is_violet else color),
        "baseColorLabel": color_label(color),
        "isViolet": is_violet,
        "reason": reason_for(merged, color, is_violet),
        "markierung": clean_text(merged.get("markierung")),
        "markierungsKlasse": clean_text(merged.get("markierungs_klasse")),
        "hzMarkierung": clean_text(merged.get("hz_markierung")),
        "hz": clean_text(merged.get("hz_status") or merged.get("hz_class")),
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
        "transitShape": clean_text(matrix.get("transit_shape")),
        "depthStability": clean_text(matrix.get("depth_stability")),
        "dataGapRisk": clean_text(matrix.get("data_gap_risk")),
        "sectorEdgeRisk": clean_text(matrix.get("sector_edge_risk")),
        "secondaryEclipse": clean_text(matrix.get("secondary_eclipse")),
        "periodAliasRisk": clean_text(matrix.get("period_alias_risk")),
        "rotationRisk": rotation_risk,
        "nextRecheck": clean_text(merged.get("next_recheck")),
        "revisitPriority": clean_text(merged.get("revisit_priority")),
        "notes": clean_text(merged.get("notes")),
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
        "finalDecision": compute_final_decision(
            row=merged,
            matrix=matrix,
            sector=sector,
            full_vetting=full_vetting,
            observed_sectors=observed_sectors,
            period=period,
        ),
        "folder": candidate_folder,
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


def main() -> int:
    args = parse_args()
    auto_updated = run_auto_update(args)
    db_rows, matrix_rows, sector_rows, local_coord_rows = load_db_rows()
    with MANIFEST_PATH.open(newline="", encoding="utf-8") as handle:
        manifest_rows = list(csv.DictReader(handle))

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

    fetched_coords = fetch_gaia_coordinates(source_ids_to_query)
    if fetched_coords:
        gaia_cache.update(fetched_coords)
        save_gaia_cache(gaia_cache)

    full_vetting_reports = load_full_vetting_reports()
    tess_state = build_tess_state()
    max_distance = max(safe_float(row.get("distance_ly")) or 0.0 for row in manifest_rows)
    candidates = [
        build_candidate(
            row,
            db_rows.get(safe_int(row.get("TIC"))),
            matrix_rows.get(safe_int(row.get("TIC"))),
            sector_rows.get(safe_int(row.get("TIC"))),
            local_coord_rows.get(safe_int(row.get("TIC"))),
            gaia_cache,
            max_distance,
            tess_state,
            full_vetting_reports.get(safe_int(row.get("TIC"))),
        )
        for row in manifest_rows
    ]
    candidates.sort(key=lambda item: (item["distance"], -item["snr"], item["tic"]))

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

    lightcurve_candidates = [
        candidate for candidate in candidates
        if candidate["lightcurveImg"] and candidate["color"] != "red"
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
    print(f"wrote {OUT_PATH}")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
