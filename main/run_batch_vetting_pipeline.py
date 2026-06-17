#!/usr/bin/env python3
"""Run persistent vetting/VVT/TTV batches across the candidate catalog.

The script deliberately orchestrates existing local analyzers instead of
inventing new science logic. It can resume safely, writes intermediate state
after every batch, and lets downstream candidate_matrix/dashboard builders
consume the persisted Level-5 and O-C artifacts.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import signal
import sqlite3
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from run_level5_green_purple_batch import Candidate as Level5Candidate
from run_level5_green_purple_batch import process_candidate as process_level5_candidate
from ttv_analyse import Candidate as TtvCandidate
from ttv_analyse import analyze_candidate as process_ttv_candidate


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = PROJECT_ROOT / "scripts"
DB_PATH = PROJECT_ROOT / "database" / "planet_hunter.db"
OUT_ROOT = PROJECT_ROOT / "batch_vetting_pipeline"
RESUME_PATH = OUT_ROOT / "resume.json"
RESULTS_JSONL = OUT_ROOT / "batch_results.jsonl"
RESULTS_CSV = OUT_ROOT / "batch_results.csv"


@dataclass(frozen=True)
class BatchCandidate:
    rank: int
    tic: int
    gaia_id: str
    status: str
    spc_class: str
    hz_status: str
    is_fp: int
    period: float
    duration: float
    depth: float
    t0: float
    radius_rearth: float
    transit_snr: float
    transit_count: int
    visible_transits: int
    clean_sector_count: int
    sector_count: int
    distance_ly: float
    lightcurve_path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run batch vetting/VVT/TTV processing for local candidates.")
    parser.add_argument("--all-candidates", action="store_true", help="Process all candidates from candidates_v2.")
    parser.add_argument("--tic", type=int, default=None, help="Process one TIC only.")
    parser.add_argument("--limit", type=int, default=None, help="Optional safety limit for development runs.")
    parser.add_argument("--batch-size", type=int, default=50, help="Candidates per batch.")
    parser.add_argument("--resume", action="store_true", help="Skip TICs already marked done/skipped in the resume file.")
    parser.add_argument("--offline-cache", action="store_true", help="Use local caches only; disables online Gaia fallback.")
    parser.add_argument("--skip-no-lightcurve", action="store_true", help="Skip candidates whose lightcurve CSV is missing.")
    parser.add_argument("--skip-not-enough-transits", action="store_true", help="Skip candidates with fewer than three visible/transit events.")
    parser.add_argument("--no-dashboard-rebuild", action="store_true", help="Do not rebuild candidate_matrix/dashboard data at the end.")
    parser.add_argument("--progress-every", type=int, default=10, help="Print progress every N candidates inside a batch.")
    parser.add_argument("--candidate-timeout", type=int, default=240, help="Maximum seconds per candidate before recording an error and continuing.")
    return parser.parse_args()


def safe_float(value: Any, default: float = float("nan")) -> float:
    try:
        if value in (None, ""):
            return default
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def finite(value: float) -> bool:
    return isinstance(value, float) and math.isfinite(value)


def resolve_lightcurve_path(value: Any, tic: int) -> Path:
    path = Path(str(value or ""))
    if path and path.exists():
        return path
    if path and not path.is_absolute():
        candidate = PROJECT_ROOT / path
        if candidate.exists():
            return candidate
    return PROJECT_ROOT / "lightcurves" / f"TIC_{tic}" / f"TIC_{tic}_lightcurve.csv"


def ttv_priority(row: sqlite3.Row) -> str:
    is_fp = safe_int(row["is_fp"])
    transit_count = safe_int(row["transit_count"])
    snr = safe_float(row["transit_snr"], 0.0)
    hz_status = str(row["hz_status"] or "")
    if is_fp == 0 and transit_count >= 10 and snr >= 12:
        return "TTV_A"
    if is_fp == 0 and transit_count >= 6 and snr >= 8:
        return "TTV_B"
    if is_fp == 0 and transit_count >= 4:
        return "TTV_C"
    if hz_status in {"KONSERVATIVE_HZ", "OPT_HZ_INNEN", "OPT_HZ_AUSSEN"}:
        return "HZ_TTV_SCHWER"
    return "NIEDRIG"


def load_candidates(args: argparse.Namespace) -> list[BatchCandidate]:
    if not args.all_candidates and args.tic is None:
        raise SystemExit("Use --all-candidates or --tic.")
    sql = """
        SELECT TIC, gaia_id, status, spc_class, is_fp, hz_status, best_period,
               duration, depth, transit_time, planet_radius_earth, transit_snr,
               transit_count, visible_transits, clean_sector_count, sector_count,
               distance_ly, lightcurve_dir
          FROM candidates_v2
         WHERE best_period IS NOT NULL
           AND transit_time IS NOT NULL
    """
    params: list[Any] = []
    if args.tic is not None:
        sql += " AND TIC = ?"
        params.append(args.tic)
    sql += " ORDER BY TIC"
    if args.limit is not None:
        sql += " LIMIT ?"
        params.append(max(1, int(args.limit)))

    with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()

    candidates: list[BatchCandidate] = []
    for index, row in enumerate(rows, start=1):
        tic = safe_int(row["TIC"])
        lightcurve_path = resolve_lightcurve_path(row["lightcurve_dir"], tic)
        candidates.append(
            BatchCandidate(
                rank=index,
                tic=tic,
                gaia_id=str(row["gaia_id"] or ""),
                status=str(row["status"] or ""),
                spc_class=str(row["spc_class"] or ""),
                hz_status=str(row["hz_status"] or ""),
                is_fp=safe_int(row["is_fp"]),
                period=safe_float(row["best_period"]),
                duration=safe_float(row["duration"], 0.195),
                depth=safe_float(row["depth"], 0.0),
                t0=safe_float(row["transit_time"]),
                radius_rearth=safe_float(row["planet_radius_earth"]),
                transit_snr=safe_float(row["transit_snr"], 0.0),
                transit_count=safe_int(row["transit_count"]),
                visible_transits=safe_int(row["visible_transits"]),
                clean_sector_count=safe_int(row["clean_sector_count"]),
                sector_count=safe_int(row["sector_count"]),
                distance_ly=safe_float(row["distance_ly"]),
                lightcurve_path=lightcurve_path,
            )
        )
    return candidates


def load_resume() -> dict[str, Any]:
    if not RESUME_PATH.exists():
        return {"processed": {}, "batches": []}
    try:
        return json.loads(RESUME_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"processed": {}, "batches": []}


def write_resume(resume: dict[str, Any]) -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    resume["updatedAt"] = datetime.now().isoformat(timespec="seconds")
    RESUME_PATH.write_text(json.dumps(resume, indent=2, sort_keys=True), encoding="utf-8")


def append_result(row: dict[str, Any]) -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    with RESULTS_JSONL.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def rewrite_results_csv() -> None:
    if not RESULTS_JSONL.exists():
        return
    rows = [json.loads(line) for line in RESULTS_JSONL.read_text(encoding="utf-8").splitlines() if line.strip()]
    fields = [
        "tic",
        "status",
        "skipReason",
        "level5Status",
        "level5Flags",
        "ttvStatus",
        "ttvPriority",
        "ttvMeasurements",
        "error",
        "updatedAt",
    ]
    with RESULTS_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def should_skip(candidate: BatchCandidate, args: argparse.Namespace) -> str:
    if args.skip_no_lightcurve and not candidate.lightcurve_path.exists():
        return "NO_LIGHTCURVE"
    if args.skip_not_enough_transits and max(candidate.visible_transits, candidate.transit_count) < 3:
        return "NOT_ENOUGH_TRANSITS"
    if not finite(candidate.period) or candidate.period <= 0 or not finite(candidate.t0):
        return "MISSING_EPHEMERIS"
    return ""


def to_level5_candidate(candidate: BatchCandidate) -> Level5Candidate:
    return Level5Candidate(
        rank=candidate.rank,
        tic=candidate.tic,
        gaia_id=candidate.gaia_id,
        status=candidate.status or candidate.spc_class,
        hz_status=candidate.hz_status,
        period=candidate.period,
        duration=candidate.duration,
        depth=candidate.depth,
        t0=candidate.t0,
        radius_rearth=candidate.radius_rearth,
        transit_snr=candidate.transit_snr,
        transit_count=candidate.transit_count,
        visible_transits=candidate.visible_transits,
        clean_sector_count=candidate.clean_sector_count,
        sector_count=candidate.sector_count,
        distance_ly=candidate.distance_ly,
        lightcurve_path=candidate.lightcurve_path,
    )


def to_ttv_candidate(candidate: BatchCandidate) -> TtvCandidate:
    return TtvCandidate(
        tic=candidate.tic,
        hz_status=candidate.hz_status,
        is_fp=candidate.is_fp,
        period=candidate.period,
        duration=candidate.duration,
        depth=candidate.depth,
        t0=candidate.t0,
        snr=candidate.transit_snr,
        transit_count=candidate.transit_count,
        radius_rearth=candidate.radius_rearth if finite(candidate.radius_rearth) else None,
        lightcurve_dir=str(candidate.lightcurve_path),
        ttv_priority=ttv_priority_from_candidate(candidate),
    )


def ttv_priority_from_candidate(candidate: BatchCandidate) -> str:
    if candidate.is_fp == 0 and candidate.transit_count >= 10 and candidate.transit_snr >= 12:
        return "TTV_A"
    if candidate.is_fp == 0 and candidate.transit_count >= 6 and candidate.transit_snr >= 8:
        return "TTV_B"
    if candidate.is_fp == 0 and candidate.transit_count >= 4:
        return "TTV_C"
    if candidate.hz_status in {"KONSERVATIVE_HZ", "OPT_HZ_INNEN", "OPT_HZ_AUSSEN"}:
        return "HZ_TTV_SCHWER"
    return "NIEDRIG"


def process_one(candidate: BatchCandidate, args: argparse.Namespace) -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    skip_reason = should_skip(candidate, args)
    if skip_reason:
        return {
            "tic": candidate.tic,
            "status": "skipped",
            "skipReason": skip_reason,
            "updatedAt": now,
        }

    result: dict[str, Any] = {
        "tic": candidate.tic,
        "status": "processed",
        "skipReason": "",
        "updatedAt": now,
    }
    level5_payload = process_level5_candidate(
        to_level5_candidate(candidate),
        online_gaia_missing=not args.offline_cache,
        overwrite=False,
    )
    result["level5Status"] = level5_payload.get("status", "")
    result["level5Flags"] = ";".join(level5_payload.get("flags") or [])
    result["transitVettingMetrics"] = {
        key: level5_payload.get(key)
        for key in (
            "visible_transits_level5",
            "robust_transits",
            "median_single_snr",
            "median_depth_ppt",
            "depth_cv",
            "odd_even_ratio_independent",
            "secondary_best_ratio_independent",
            "secondary_best_snr_independent",
            "nearby_star_flag",
        )
    }

    ttv_row = process_ttv_candidate(
        to_ttv_candidate(candidate),
        min_points=10,
        overwrite=False,
    )
    result["ttvStatus"] = ttv_row.get("status", "")
    result["ttvPriority"] = ttv_row.get("priority", "")
    result["ttvMeasurements"] = ttv_row.get("n_measured", "")
    result["ocTtvMetrics"] = {
        "csv": ttv_row.get("csv", ""),
        "plot": ttv_row.get("plot", ""),
        "nMeasured": ttv_row.get("n_measured", ""),
    }
    return result


def process_one_with_timeout(candidate: BatchCandidate, args: argparse.Namespace) -> dict[str, Any]:
    timeout = int(args.candidate_timeout or 0)
    if timeout <= 0 or not hasattr(signal, "SIGALRM"):
        return process_one(candidate, args)

    def _handler(signum, frame):
        raise TimeoutError(f"candidate timed out after {timeout}s")

    previous_handler = signal.signal(signal.SIGALRM, _handler)
    signal.setitimer(signal.ITIMER_REAL, timeout)
    try:
        return process_one(candidate, args)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def run_subprocess(cmd: list[str], cwd: Path) -> None:
    print(f"[post] {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def rebuild_dashboard(args: argparse.Namespace) -> None:
    run_subprocess([sys.executable, "main/build_candidate_matrix.py"], SCRIPT_ROOT)
    dashboard_cmd = [sys.executable, "dashboard/build_dashboard_data.py"]
    if args.offline_cache:
        dashboard_cmd.append("--offline-cache")
    run_subprocess(dashboard_cmd, SCRIPT_ROOT)


def main() -> int:
    args = parse_args()
    candidates = load_candidates(args)
    batch_size = max(1, int(args.batch_size or 1))
    resume = load_resume() if args.resume else {"processed": {}, "batches": []}
    processed = resume.setdefault("processed", {})
    total = len(candidates)
    print(f"[batch] candidates={total} batch_size={batch_size} resume={bool(args.resume)}", flush=True)

    for batch_start in range(0, total, batch_size):
        batch = candidates[batch_start : batch_start + batch_size]
        batch_index = batch_start // batch_size + 1
        batch_rows: list[dict[str, Any]] = []
        print(f"[batch] {batch_index}: {batch_start + 1}-{batch_start + len(batch)} / {total}", flush=True)
        for offset, candidate in enumerate(batch, start=1):
            key = str(candidate.tic)
            if args.resume and key in processed and processed[key].get("status") in {"processed", "skipped"}:
                continue
            try:
                row = process_one_with_timeout(candidate, args)
            except Exception as exc:
                row = {
                    "tic": candidate.tic,
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "updatedAt": datetime.now().isoformat(timespec="seconds"),
                }
            append_result(row)
            processed[key] = {
                "status": row.get("status"),
                "skipReason": row.get("skipReason", ""),
                "updatedAt": row.get("updatedAt"),
            }
            batch_rows.append(row)
            if offset == 1 or offset == len(batch) or offset % max(1, int(args.progress_every or 1)) == 0:
                print(f"  TIC {candidate.tic}: {row.get('status')} {row.get('skipReason') or row.get('error') or ''}", flush=True)

        resume.setdefault("batches", []).append({
            "batchIndex": batch_index,
            "start": batch_start + 1,
            "end": batch_start + len(batch),
            "rows": len(batch_rows),
            "updatedAt": datetime.now().isoformat(timespec="seconds"),
        })
        write_resume(resume)
        rewrite_results_csv()
        print(f"[batch] {batch_index}: saved intermediate results", flush=True)

    if not args.no_dashboard_rebuild:
        rebuild_dashboard(args)
    print(f"[done] results={RESULTS_JSONL} resume={RESUME_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
