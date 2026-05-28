#!/usr/bin/env python3
"""Slow Bayesian-style vetting for selected high-value candidates.

This script is deliberately not imported by ``masterscript_v2.py``.  It is for
SPCs, strong evidence candidates, and HZ targets that deserve slower modeling.
When optional MCMC packages are unavailable, the run records that limitation in
the flags instead of producing overconfident pseudo-posteriors.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import sqlite3
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

import evidence_vetting as ev


PROJECT_ROOT = Path(os.environ.get("ASTRO_PROJECT_ROOT", "/Users/koni/astro_projects"))
DB_PATH = PROJECT_ROOT / "database" / "planet_hunter.db"
DEFAULT_OUT_ROOT = PROJECT_ROOT / "advanced_bayesian_vetting"
ADVANCED_CLASSES = {"SPC_STRONG", "SPC_FOLLOWUP_READY", "SPC_RV_NEEDED"}
HZ_CLASSES = {"KONSERVATIVE_HZ", "OPT_HZ_INNEN", "OPT_HZ_AUSSEN"}


@dataclass(frozen=True)
class AdvancedCandidate:
    tic: int
    candidate_id: int
    period: float
    epoch: float
    duration: float
    depth: float
    evidence_score: float | None
    evidence_class: str | None
    hz_class: str | None
    lightcurve_dir: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run slow Bayesian-style vetting.")
    parser.add_argument("--tic", type=int, action="append", help="Only process this TIC. Repeatable.")
    parser.add_argument("--input-db", type=Path, default=DB_PATH, help="SQLite database path.")
    parser.add_argument("--input-csv", type=Path, default=None, help="Evidence CSV or candidate CSV.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT_ROOT, help="Output root.")
    parser.add_argument("--max-candidates", type=int, default=None, help="Maximum candidates.")
    parser.add_argument("--dry-run", action="store_true", help="List targets, but skip fitting and DB writes.")
    return parser.parse_args()


def make_run_dir(output_root: Path) -> tuple[str, Path]:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = output_root / f"{run_id}_advanced_bayesian_vetting"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_id, run_dir


def setup_logger(run_dir: Path) -> logging.Logger:
    logger = logging.getLogger("advanced_bayesian_vetting")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    file_handler = logging.FileHandler(run_dir / "run.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def pick(row: pd.Series, names: tuple[str, ...], default: Any = None) -> Any:
    col = ev.pick_col(list(row.index), names)
    return row[col] if col else default


def candidate_from_row(row: pd.Series, fallback_id: int) -> AdvancedCandidate:
    return AdvancedCandidate(
        tic=ev.safe_int(pick(row, ("TIC", "tic", "tic_id"))),
        candidate_id=ev.safe_int(pick(row, ("candidate_id", "id")), fallback_id),
        period=ev.safe_float(pick(row, ("period", "best_period", "posterior_period")), 0.0) or 0.0,
        epoch=ev.safe_float(pick(row, ("epoch", "transit_time", "t0")), 0.0) or 0.0,
        duration=ev.safe_float(pick(row, ("duration", "posterior_duration")), 0.0) or 0.0,
        depth=ev.safe_float(pick(row, ("depth", "posterior_depth")), 0.0) or 0.0,
        evidence_score=ev.safe_float(pick(row, ("evidence_score",))),
        evidence_class=str(pick(row, ("evidence_class", "spc_class", "status"), "") or "") or None,
        hz_class=str(pick(row, ("hz_class", "hz_status"), "") or "") or None,
        lightcurve_dir=str(pick(row, ("lightcurve_dir", "lightcurve_path"), "") or "") or None,
    )


def load_candidates_from_csv(path: Path, args: argparse.Namespace) -> list[AdvancedCandidate]:
    df = pd.read_csv(path)
    candidates = [candidate_from_row(row, idx + 1) for idx, row in df.iterrows()]
    if "bayes_recommended" in df.columns:
        recommended = pd.to_numeric(df["bayes_recommended"], errors="coerce").fillna(0).astype(int)
        candidates = [cand for cand, keep in zip(candidates, recommended) if keep]
    else:
        candidates = [
            cand
            for cand in candidates
            if (cand.evidence_class in ADVANCED_CLASSES)
            or ((cand.evidence_score or 0) >= 65 and cand.hz_class in HZ_CLASSES)
        ]
    return filter_candidates(candidates, args)


def evidence_table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='evidence_vetting_results'"
    ).fetchone()
    return row is not None


def load_candidates_from_db(db_path: Path, args: argparse.Namespace) -> list[AdvancedCandidate]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=60)
    conn.row_factory = sqlite3.Row
    try:
        if evidence_table_exists(conn):
            sql = """
            WITH latest AS (
              SELECT TIC, candidate_id, MAX(created_at) AS max_created
              FROM evidence_vetting_results
              GROUP BY TIC, candidate_id
            )
            SELECT
              e.TIC,
              e.candidate_id,
              e.period,
              e.epoch,
              COALESCE(c.duration, e.duration) AS duration,
              COALESCE(c.depth, e.depth) AS depth,
              e.evidence_score,
              e.evidence_class,
              COALESCE(c.hz_class, c.hz_status, e.evidence_class) AS hz_class,
              c.lightcurve_dir
            FROM evidence_vetting_results e
            JOIN latest l
              ON l.TIC=e.TIC AND l.candidate_id=e.candidate_id AND l.max_created=e.created_at
            LEFT JOIN candidates_v2 c
              ON c.TIC=e.TIC AND c.id=e.candidate_id
            WHERE (
              e.bayes_recommended=1
              OR e.evidence_class IN ('SPC_STRONG','SPC_FOLLOWUP_READY','SPC_RV_NEEDED')
            )
            """
            params: list[Any] = []
            if args.tic:
                placeholders = ",".join("?" for _ in args.tic)
                sql += f" AND e.TIC IN ({placeholders})"
                params.extend(args.tic)
            sql += " ORDER BY e.evidence_score DESC, e.TIC"
            rows = conn.execute(sql, params).fetchall()
        else:
            sql = """
            SELECT
              TIC,
              id AS candidate_id,
              best_period AS period,
              transit_time AS epoch,
              duration,
              depth,
              transit_snr AS evidence_score,
              COALESCE(spc_class, status) AS evidence_class,
              COALESCE(hz_class, hz_status) AS hz_class,
              lightcurve_dir
            FROM candidates_v2
            WHERE best_period IS NOT NULL
              AND transit_time IS NOT NULL
              AND duration IS NOT NULL
              AND depth IS NOT NULL
              AND (
                COALESCE(spc_class, '') IN ('SPC-A','SPC-B','SPC-C')
                OR COALESCE(status, '') LIKE 'SPC%'
                OR COALESCE(hz_class, hz_status, '') IN ('KONSERVATIVE_HZ','OPT_HZ_INNEN','OPT_HZ_AUSSEN')
              )
            """
            params = []
            if args.tic:
                placeholders = ",".join("?" for _ in args.tic)
                sql += f" AND TIC IN ({placeholders})"
                params.extend(args.tic)
            sql += " ORDER BY COALESCE(transit_snr,0) DESC, TIC"
            rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    candidates = [
        AdvancedCandidate(
            tic=int(row["TIC"]),
            candidate_id=ev.safe_int(row["candidate_id"], int(row["TIC"])),
            period=float(row["period"]),
            epoch=float(row["epoch"]),
            duration=float(row["duration"]),
            depth=float(row["depth"]),
            evidence_score=ev.safe_float(row["evidence_score"]),
            evidence_class=str(row["evidence_class"] or "") or None,
            hz_class=str(row["hz_class"] or "") or None,
            lightcurve_dir=row["lightcurve_dir"],
        )
        for row in rows
    ]
    return filter_candidates(candidates, args)


def filter_candidates(candidates: list[AdvancedCandidate], args: argparse.Namespace) -> list[AdvancedCandidate]:
    out = [
        cand
        for cand in candidates
        if cand.tic and cand.period > 0 and cand.duration > 0 and cand.depth > 0
    ]
    if args.tic:
        allowed = set(args.tic)
        out = [cand for cand in out if cand.tic in allowed]
    if args.max_candidates is not None:
        out = out[: args.max_candidates]
    return out


def to_ev_candidate(candidate: AdvancedCandidate) -> ev.Candidate:
    return ev.Candidate(
        tic=candidate.tic,
        candidate_id=candidate.candidate_id,
        gaia_id=None,
        teff=None,
        distance_ly=None,
        tmag=None,
        stellar_radius=None,
        stellar_logg=None,
        period=candidate.period,
        duration=candidate.duration,
        depth=candidate.depth,
        t0=candidate.epoch,
        power=None,
        planet_radius_earth=None,
        lightcurve_dir=candidate.lightcurve_dir,
        transit_snr=None,
        transit_count=0,
        n_in_transit=0,
        duration_fraction=None,
        oe_ratio=None,
        sec_ratio=None,
        fp_oe_flag=0,
        fp_sec_flag=0,
        fp_baseline_flag=0,
        fp_baseline_std_flag=0,
        fp_scatter_flag=0,
        is_fp=0,
        hz_status=candidate.hz_class or "UNKNOWN",
        hz_class=candidate.hz_class or "UNKNOWN",
        sector_count=None,
        clean_sector_count=None,
        visible_transits=None,
        spc_class=candidate.evidence_class,
        status=candidate.evidence_class,
        revisit_priority=None,
        notes=None,
    )


def mask_transits(time_arr: np.ndarray, candidate: AdvancedCandidate, scale: float = 1.5) -> np.ndarray:
    phase = ev.centered_phase_days(time_arr, candidate.period, candidate.epoch)
    return np.abs(phase) <= max(scale * candidate.duration, 0.05)


def gp_detrend(
    time_arr: np.ndarray,
    flux_arr: np.ndarray,
    candidate: AdvancedCandidate,
) -> tuple[np.ndarray, float, list[str]]:
    flags: list[str] = []
    try:
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import ConstantKernel, RBF, WhiteKernel
        from sklearn.exceptions import ConvergenceWarning
    except Exception:
        flags.append("GP_DEPENDENCY_UNAVAILABLE")
        return flux_arr, float("nan"), flags

    finite = np.isfinite(time_arr) & np.isfinite(flux_arr)
    t = time_arr[finite]
    f = flux_arr[finite]
    oot = ~mask_transits(t, candidate, scale=2.0)
    if int(np.count_nonzero(oot)) < 100:
        flags.append("GP_INSUFFICIENT_OOT")
        return flux_arr, float("nan"), flags

    x_train = t[oot]
    y_train = f[oot] - 1.0
    if len(x_train) > 2500:
        idx = np.linspace(0, len(x_train) - 1, 2500, dtype=int)
        x_train = x_train[idx]
        y_train = y_train[idx]
    x0 = float(np.nanmin(x_train))
    x_scale = max(float(np.nanmax(x_train) - x0), 1.0)
    x_train_scaled = ((x_train - x0) / x_scale).reshape(-1, 1)
    x_all_scaled = ((time_arr - x0) / x_scale).reshape(-1, 1)

    amp = max(float(np.nanstd(y_train)), 1e-5)
    kernel = ConstantKernel(amp**2, (1e-8, 1e-2)) * RBF(length_scale=0.15, length_scale_bounds=(1e-3, 5.0)) + WhiteKernel(
        noise_level=max(amp**2 * 0.25, 1e-8),
        noise_level_bounds=(1e-10, 1e-2),
    )
    try:
        gp = GaussianProcessRegressor(
            kernel=kernel,
            normalize_y=True,
            n_restarts_optimizer=0,
            alpha=0.0,
            random_state=42,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConvergenceWarning)
            gp.fit(x_train_scaled, y_train)
        trend = gp.predict(x_all_scaled)
        detrended = flux_arr - trend
        detrended = ev.normalize_flux(detrended)
    except Exception:
        flags.append("GP_FAILED")
        return flux_arr, float("nan"), flags

    ev_candidate = to_ev_candidate(candidate)
    raw_depth = ev.folded_signal(time_arr, flux_arr, ev_candidate)["depth_ppt"]
    gp_depth = ev.folded_signal(time_arr, detrended, ev_candidate)["depth_ppt"]
    if np.isfinite(raw_depth) and abs(float(raw_depth)) > 1e-9 and np.isfinite(gp_depth):
        change = abs(float(gp_depth) - float(raw_depth)) / abs(float(raw_depth))
    else:
        change = float("nan")
    if np.isfinite(change) and change > 0.5:
        flags.append("GP_SIGNAL_CHANGED")
    return detrended, float(change), flags


def trapezoid_model(
    time_arr: np.ndarray,
    period: float,
    epoch: float,
    depth: float,
    duration: float,
    baseline: float,
) -> np.ndarray:
    phase = ev.centered_phase_days(time_arr, period, epoch)
    half = max(duration / 2.0, 1e-5)
    ingress = max(duration * 0.18, 0.003)
    flat_half = max(half - ingress, half * 0.25)
    abs_phase = np.abs(phase)
    shape = np.zeros_like(time_arr, dtype=float)
    shape[abs_phase <= flat_half] = 1.0
    ramp = (abs_phase > flat_half) & (abs_phase <= half)
    shape[ramp] = 1.0 - (abs_phase[ramp] - flat_half) / max(half - flat_half, 1e-6)
    return baseline - depth * shape


def fit_transit_model(
    time_arr: np.ndarray,
    flux_arr: np.ndarray,
    candidate: AdvancedCandidate,
) -> dict[str, Any]:
    flags: list[str] = []
    fit_window = np.abs(ev.centered_phase_days(time_arr, candidate.period, candidate.epoch)) <= max(
        4.0 * candidate.duration,
        0.18,
    )
    if int(np.count_nonzero(fit_window)) < 25:
        return {
            "posterior_period": float("nan"),
            "posterior_depth": float("nan"),
            "posterior_duration": float("nan"),
            "delta_bic": float("nan"),
            "flags": ["FIT_INSUFFICIENT_POINTS"],
        }
    t = time_arr[fit_window]
    f = flux_arr[fit_window]
    scatter = ev.robust_scatter(f - np.nanmedian(f))
    if not np.isfinite(scatter) or scatter <= 0:
        scatter = float(np.nanstd(f)) or 1e-4

    p0 = np.asarray(
        [
            candidate.period,
            candidate.epoch,
            max(candidate.depth, 1e-5),
            max(candidate.duration, 0.01),
            1.0,
        ],
        dtype=float,
    )
    lower = np.asarray(
        [
            max(candidate.period * 0.995, 0.05),
            candidate.epoch - max(candidate.period * 0.2, candidate.duration),
            1e-6,
            max(0.005, candidate.duration * 0.35),
            0.95,
        ],
        dtype=float,
    )
    upper = np.asarray(
        [
            candidate.period * 1.005,
            candidate.epoch + max(candidate.period * 0.2, candidate.duration),
            min(max(candidate.depth * 6.0, 0.01), 0.2),
            min(max(candidate.duration * 3.0, 0.05), candidate.period * 0.2),
            1.05,
        ],
        dtype=float,
    )

    def residual(params: np.ndarray) -> np.ndarray:
        model = trapezoid_model(t, *params)
        return (f - model) / scatter

    try:
        fit = least_squares(residual, p0, bounds=(lower, upper), max_nfev=2500)
        params = fit.x
    except Exception:
        return {
            "posterior_period": float("nan"),
            "posterior_depth": float("nan"),
            "posterior_duration": float("nan"),
            "delta_bic": float("nan"),
            "flags": ["FIT_FAILED"],
        }

    model = trapezoid_model(t, *params)
    rss_model = float(np.nansum((f - model) ** 2))
    flat = np.full_like(f, float(np.nanmedian(f)))
    rss_flat = float(np.nansum((f - flat) ** 2))
    n = max(len(f), 1)
    bic_model = n * math.log(max(rss_model / n, 1e-16)) + 5 * math.log(n)
    bic_flat = n * math.log(max(rss_flat / n, 1e-16)) + 1 * math.log(n)
    delta_bic = bic_flat - bic_model

    try:
        import emcee  # noqa: F401
    except Exception:
        flags.append("MCMC_UNAVAILABLE")
    return {
        "posterior_period": float(params[0]),
        "posterior_depth": float(params[2]),
        "posterior_duration": float(params[3]),
        "delta_bic": float(delta_bic),
        "flags": flags,
    }


def classify_bayes(activity_score: float, gp_signal_change: float, delta_bic: float, flags: list[str]) -> str:
    if any(flag in flags for flag in ("FIT_FAILED", "FIT_INSUFFICIENT_POINTS", "GP_FAILED")):
        return "FAILED"
    if activity_score < 45 and np.isfinite(gp_signal_change) and gp_signal_change > 0.4:
        return "ACTIVITY_DOMINATED"
    if np.isfinite(gp_signal_change) and gp_signal_change > 0.75:
        return "GP_SENSITIVE"
    if np.isfinite(delta_bic) and delta_bic >= 10:
        return "BAYES_STRONG"
    if np.isfinite(delta_bic) and delta_bic >= 2:
        return "BAYES_WEAK"
    return "MODEL_NOT_FAVORED"


def analyze_candidate(candidate: AdvancedCandidate) -> dict[str, Any]:
    ev_candidate = to_ev_candidate(candidate)
    lc = ev.load_lightcurve(ev_candidate)
    time_arr = lc["time"]
    flux_arr = lc["flux"]
    assert isinstance(time_arr, np.ndarray)
    assert isinstance(flux_arr, np.ndarray)

    activity = ev.compute_activity(ev_candidate, time_arr, flux_arr)
    detrended, gp_signal_change, gp_flags = gp_detrend(time_arr, flux_arr, candidate)
    fit = fit_transit_model(time_arr, detrended, candidate)
    flags = list(dict.fromkeys([*gp_flags, *fit["flags"], *activity.get("flags", [])]))
    bayes_class = classify_bayes(
        float(activity["score"]),
        gp_signal_change,
        float(fit["delta_bic"]),
        flags,
    )
    return {
        "TIC": candidate.tic,
        "candidate_id": candidate.candidate_id,
        "period": candidate.period,
        "epoch": candidate.epoch,
        "rotation_period_ls": activity["rotation_period_ls"],
        "rotation_period_acf": activity["rotation_period_acf"],
        "activity_score": activity["score"],
        "gp_signal_change": gp_signal_change,
        "posterior_period": fit["posterior_period"],
        "posterior_depth": fit["posterior_depth"],
        "posterior_duration": fit["posterior_duration"],
        "bayes_class": bayes_class,
        "evidence_score": candidate.evidence_score,
        "flags": ";".join(flags),
        "delta_bic": fit["delta_bic"],
    }


def ensure_advanced_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS advanced_vetting_results (
            run_id TEXT NOT NULL,
            TIC INTEGER NOT NULL,
            candidate_id INTEGER NOT NULL,
            period REAL,
            epoch REAL,
            rotation_period_ls REAL,
            rotation_period_acf REAL,
            activity_score REAL,
            gp_signal_change REAL,
            posterior_period REAL,
            posterior_depth REAL,
            posterior_duration REAL,
            bayes_class TEXT,
            evidence_score REAL,
            flags TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            output_dir TEXT,
            PRIMARY KEY (run_id, TIC, candidate_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_advanced_tic ON advanced_vetting_results(TIC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_advanced_class ON advanced_vetting_results(bayes_class)")
    conn.commit()


def write_results_to_db(db_path: Path, run_id: str, run_dir: Path, rows: list[dict[str, Any]]) -> None:
    conn = sqlite3.connect(db_path, timeout=60)
    try:
        ensure_advanced_table(conn)
        for row in rows:
            conn.execute(
                """
                INSERT OR REPLACE INTO advanced_vetting_results (
                    run_id, TIC, candidate_id, period, epoch,
                    rotation_period_ls, rotation_period_acf, activity_score,
                    gp_signal_change, posterior_period, posterior_depth,
                    posterior_duration, bayes_class, evidence_score, flags,
                    created_at, output_dir
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
                """,
                (
                    run_id,
                    row["TIC"],
                    row["candidate_id"],
                    row["period"],
                    row["epoch"],
                    row["rotation_period_ls"],
                    row["rotation_period_acf"],
                    row["activity_score"],
                    row["gp_signal_change"],
                    row["posterior_period"],
                    row["posterior_depth"],
                    row["posterior_duration"],
                    row["bayes_class"],
                    row["evidence_score"],
                    row["flags"],
                    str(run_dir),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    if not fields:
        fields = ["status"]
        rows = [{"status": "empty"}]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    run_id, run_dir = make_run_dir(args.output_dir)
    logger = setup_logger(run_dir)
    logger.info("Advanced Bayesian vetting run: %s", run_id)
    logger.info("Output: %s", run_dir)

    if args.input_csv:
        candidates = load_candidates_from_csv(args.input_csv, args)
    else:
        candidates = load_candidates_from_db(args.input_db, args)
    logger.info("Candidates selected: %d", len(candidates))

    target_rows = [
        {
            "run_id": run_id,
            "TIC": c.tic,
            "candidate_id": c.candidate_id,
            "period": c.period,
            "epoch": c.epoch,
            "duration": c.duration,
            "depth": c.depth,
            "evidence_score": c.evidence_score,
            "evidence_class": c.evidence_class,
            "hz_class": c.hz_class,
            "lightcurve_dir": c.lightcurve_dir,
        }
        for c in candidates
    ]
    write_csv(run_dir / "advanced_targets.csv", target_rows)
    if args.dry_run:
        logger.info("Dry run: fitting and SQLite update skipped.")
        return 0

    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for idx, candidate in enumerate(candidates, start=1):
        try:
            row = analyze_candidate(candidate)
            row["run_id"] = run_id
            row["output_dir"] = str(run_dir)
            rows.append(row)
            logger.info(
                "%d/%d TIC %s: %s delta_bic=%.2f flags=%s",
                idx,
                len(candidates),
                candidate.tic,
                row["bayes_class"],
                float(row["delta_bic"]) if np.isfinite(row["delta_bic"]) else float("nan"),
                row["flags"] or "none",
            )
        except Exception as exc:
            err = {
                "run_id": run_id,
                "TIC": candidate.tic,
                "candidate_id": candidate.candidate_id,
                "error": f"{type(exc).__name__}: {exc}",
            }
            errors.append(err)
            logger.exception("TIC %s failed: %s", candidate.tic, err["error"])

    write_csv(run_dir / "advanced_vetting_results.csv", rows)
    if errors:
        write_csv(run_dir / "errors.csv", errors)
    if rows and not args.input_csv:
        write_results_to_db(args.input_db, run_id, run_dir, rows)
        logger.info("SQLite advanced_vetting_results updated.")
    elif args.input_csv:
        logger.info("Input was CSV: SQLite update skipped.")
    logger.info("Done: %s", run_dir)
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
