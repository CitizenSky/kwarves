#!/usr/bin/env python3
"""Measure simple transit timing variations for selected candidates.

This script is intentionally conservative. It does not claim planet validation;
it creates per-transit timing measurements and O-C plots for manual review.
"""

from __future__ import annotations

import argparse
import csv
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


PROJECT_ROOT = Path("/Users/koni/astro_projects")
DB_PATH = PROJECT_ROOT / "database" / "planet_hunter.db"
OUT_ROOT = PROJECT_ROOT / "level4_TTV_analyse" / "level4_04_oc_ergebnisse"
LIGHTCURVE_ROOT = PROJECT_ROOT / "lightcurves"


def priority_folder(priority: str) -> str:
    return priority if priority.startswith("level4_") else f"level4_{priority}"


@dataclass(frozen=True)
class Candidate:
    tic: int
    hz_status: str
    is_fp: int
    period: float
    duration: float
    depth: float
    t0: float
    snr: float
    transit_count: int
    radius_rearth: float | None
    lightcurve_dir: str | None
    ttv_priority: str


@dataclass(frozen=True)
class TransitMeasurement:
    tic: int
    epoch: int
    expected_time: float
    observed_time: float
    oc_minutes: float
    timing_uncertainty_minutes: float
    depth_ppt: float
    local_scatter_ppt: float
    n_points: int
    n_in_transit: int
    quality: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create O-C timing tables and plots for TTV candidates.",
    )
    parser.add_argument(
        "--priority",
        default="TTV_A",
        choices=["TTV_A", "TTV_B", "TTV_C", "HZ_TTV_SCHWER", "ALL"],
        help="Candidate priority class to analyze.",
    )
    parser.add_argument(
        "--tic",
        type=int,
        default=None,
        help="Analyze one TIC only.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of candidates to analyze.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Recompute existing per-TIC result folders.",
    )
    parser.add_argument(
        "--min-points",
        type=int,
        default=10,
        help="Minimum local points required around an expected transit.",
    )
    return parser.parse_args()


def priority_expr() -> str:
    return """
    CASE
      WHEN c.is_fp = 0 AND c.transit_count >= 10 AND c.transit_snr >= 12 THEN 'TTV_A'
      WHEN c.is_fp = 0 AND c.transit_count >= 6 AND c.transit_snr >= 8 THEN 'TTV_B'
      WHEN c.is_fp = 0 AND c.transit_count >= 4 THEN 'TTV_C'
      WHEN c.hz_status IN ('KONSERVATIVE_HZ','OPT_HZ_INNEN','OPT_HZ_AUSSEN') THEN 'HZ_TTV_SCHWER'
      ELSE 'NIEDRIG'
    END
    """


def load_candidates(priority: str, tic: int | None, limit: int | None) -> list[Candidate]:
    sql = f"""
    SELECT
      c.TIC,
      COALESCE(c.hz_status, 'UNKNOWN') AS hz_status,
      COALESCE(c.is_fp, 0) AS is_fp,
      c.best_period,
      c.duration,
      c.depth,
      c.transit_time,
      c.transit_snr,
      c.transit_count,
      c.planet_radius_earth,
      c.lightcurve_dir,
      {priority_expr()} AS ttv_priority
    FROM candidates_v2 c
    WHERE c.best_period IS NOT NULL
      AND c.duration IS NOT NULL
      AND c.transit_time IS NOT NULL
      AND c.depth IS NOT NULL
    """
    params: list[object] = []
    if tic is not None:
        sql += " AND c.TIC = ?"
        params.append(tic)
    elif priority != "ALL":
        sql += f" AND {priority_expr()} = ?"
        params.append(priority)

    sql += """
    ORDER BY
      CASE ttv_priority
        WHEN 'TTV_A' THEN 0
        WHEN 'TTV_B' THEN 1
        WHEN 'TTV_C' THEN 2
        WHEN 'HZ_TTV_SCHWER' THEN 3
        ELSE 4
      END,
      c.transit_count DESC,
      c.transit_snr DESC,
      c.TIC
    """
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    candidates: list[Candidate] = []
    for row in rows:
        candidates.append(
            Candidate(
                tic=int(row["TIC"]),
                hz_status=str(row["hz_status"]),
                is_fp=int(row["is_fp"] or 0),
                period=float(row["best_period"]),
                duration=float(row["duration"]),
                depth=float(row["depth"]),
                t0=float(row["transit_time"]),
                snr=float(row["transit_snr"] or 0.0),
                transit_count=int(row["transit_count"] or 0),
                radius_rearth=(
                    float(row["planet_radius_earth"])
                    if row["planet_radius_earth"] is not None
                    else None
                ),
                lightcurve_dir=row["lightcurve_dir"],
                ttv_priority=str(row["ttv_priority"]),
            )
        )
    return candidates


def lightcurve_path(candidate: Candidate) -> Path:
    if candidate.lightcurve_dir:
        path = Path(candidate.lightcurve_dir)
        if path.exists():
            return path
    return LIGHTCURVE_ROOT / f"TIC_{candidate.tic}" / f"TIC_{candidate.tic}_lightcurve.csv"


def load_lightcurve(candidate: Candidate) -> tuple[np.ndarray, np.ndarray]:
    path = lightcurve_path(candidate)
    data = np.genfromtxt(path, delimiter=",", names=True, dtype=float)
    time = np.asarray(data["time"], dtype=float)
    flux = np.asarray(data["flux"], dtype=float)
    mask = np.isfinite(time) & np.isfinite(flux)
    time, flux = time[mask], flux[mask]
    if len(time) == 0:
        raise ValueError(f"empty lightcurve: {path}")

    median = np.nanmedian(flux)
    scatter = np.nanstd(flux)
    if np.isfinite(scatter) and scatter > 0:
        keep = np.abs(flux - median) < 7.0 * scatter
        time, flux = time[keep], flux[keep]
    median = np.nanmedian(flux)
    if np.isfinite(median) and abs(median) > 1e-8:
        flux = flux / median
    else:
        flux = flux - median + 1.0
    order = np.argsort(time)
    return time[order], flux[order]


def expected_epochs(time: np.ndarray, candidate: Candidate) -> list[tuple[int, float]]:
    first = int(math.ceil((float(np.nanmin(time)) - candidate.t0) / candidate.period)) - 1
    last = int(math.floor((float(np.nanmax(time)) - candidate.t0) / candidate.period)) + 1
    epochs: list[tuple[int, float]] = []
    for epoch in range(first, last + 1):
        expected = candidate.t0 + epoch * candidate.period
        if np.nanmin(time) <= expected <= np.nanmax(time):
            epochs.append((epoch, expected))
    return epochs


def robust_scatter(values: np.ndarray) -> float:
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return float("nan")
    med = np.nanmedian(values)
    mad = np.nanmedian(np.abs(values - med))
    if np.isfinite(mad) and mad > 0:
        return float(1.4826 * mad)
    return float(np.nanstd(values))


def measure_one_transit(
    candidate: Candidate,
    time: np.ndarray,
    flux: np.ndarray,
    epoch: int,
    expected_time: float,
    min_points: int,
) -> TransitMeasurement | None:
    duration = candidate.duration
    half_duration = duration / 2.0
    local_half_window = max(3.0 * duration, 0.12)
    search_half_window = min(max(duration, 0.04), candidate.period * 0.18)

    local_mask = np.abs(time - expected_time) <= local_half_window
    if int(np.count_nonzero(local_mask)) < min_points:
        return None

    local_t = time[local_mask]
    local_f = flux[local_mask]
    dt = local_t - expected_time
    outside = np.abs(dt) >= max(1.25 * half_duration, duration)
    if int(np.count_nonzero(outside)) >= 5:
        baseline = float(np.nanmedian(local_f[outside]))
    else:
        baseline = float(np.nanmedian(local_f))
    rel = local_f / baseline if abs(baseline) > 1e-8 else local_f

    scatter = robust_scatter((rel - 1.0) * 1000.0)
    grid_step = max(duration / 80.0, 0.0005)
    centers = np.arange(
        expected_time - search_half_window,
        expected_time + search_half_window + grid_step,
        grid_step,
    )

    best_center = float("nan")
    best_score = -np.inf
    best_depth = float("nan")
    best_n_in = 0
    for center in centers:
        offset = local_t - center
        in_transit = np.abs(offset) <= half_duration
        side = (np.abs(offset) >= 1.25 * half_duration) & (np.abs(offset) <= local_half_window)
        n_in = int(np.count_nonzero(in_transit))
        n_side = int(np.count_nonzero(side))
        if n_in < 3 or n_side < 3:
            continue
        in_med = float(np.nanmedian(rel[in_transit]))
        side_med = float(np.nanmedian(rel[side]))
        depth = max(0.0, side_med - in_med)
        score = depth * math.sqrt(n_in)
        if score > best_score:
            best_score = score
            best_center = float(center)
            best_depth = depth
            best_n_in = n_in

    if not np.isfinite(best_center):
        return None

    oc_minutes = (best_center - expected_time) * 24.0 * 60.0
    depth_ppt = best_depth * 1000.0
    uncertainty = estimate_timing_uncertainty_minutes(
        duration_days=duration,
        depth_ppt=depth_ppt,
        scatter_ppt=scatter,
        n_in=best_n_in,
    )
    quality = classify_measurement(
        abs_oc_minutes=abs(oc_minutes),
        uncertainty_minutes=uncertainty,
        depth_ppt=depth_ppt,
        scatter_ppt=scatter,
        n_in=best_n_in,
        duration_days=duration,
    )

    return TransitMeasurement(
        tic=candidate.tic,
        epoch=epoch,
        expected_time=expected_time,
        observed_time=best_center,
        oc_minutes=oc_minutes,
        timing_uncertainty_minutes=uncertainty,
        depth_ppt=depth_ppt,
        local_scatter_ppt=scatter,
        n_points=int(len(local_t)),
        n_in_transit=best_n_in,
        quality=quality,
    )


def estimate_timing_uncertainty_minutes(
    duration_days: float,
    depth_ppt: float,
    scatter_ppt: float,
    n_in: int,
) -> float:
    if n_in <= 0 or not np.isfinite(depth_ppt) or depth_ppt <= 0:
        return float("nan")
    if not np.isfinite(scatter_ppt) or scatter_ppt <= 0:
        scatter_ppt = max(depth_ppt, 1.0)
    duration_minutes = duration_days * 24.0 * 60.0
    snr_local = depth_ppt / scatter_ppt * math.sqrt(max(n_in, 1))
    if snr_local <= 0:
        return float("nan")
    return float(max(duration_minutes / (2.0 * snr_local), 0.5))


def classify_measurement(
    abs_oc_minutes: float,
    uncertainty_minutes: float,
    depth_ppt: float,
    scatter_ppt: float,
    n_in: int,
    duration_days: float,
) -> str:
    if n_in < 3:
        return "BAD_FEW_POINTS"
    if not np.isfinite(depth_ppt) or depth_ppt <= 0:
        return "BAD_NO_DIP"
    local_snr = depth_ppt / scatter_ppt * math.sqrt(max(n_in, 1)) if scatter_ppt > 0 else 0
    if local_snr < 2.0:
        return "WEAK"
    duration_minutes = duration_days * 24.0 * 60.0
    if abs_oc_minutes > max(0.75 * duration_minutes, 180.0):
        return "WARN_LARGE_OC"
    if np.isfinite(uncertainty_minutes) and uncertainty_minutes > 0.5 * duration_minutes:
        return "WEAK_TIMING"
    return "OK"


def analyze_candidate(candidate: Candidate, min_points: int, overwrite: bool) -> dict[str, object]:
    out_dir = OUT_ROOT / priority_folder(candidate.ttv_priority) / f"TIC_{candidate.tic}"
    measurements_path = out_dir / f"TIC_{candidate.tic}_oc_measurements.csv"
    plot_path = out_dir / f"TIC_{candidate.tic}_oc_plot.png"
    if measurements_path.exists() and plot_path.exists() and not overwrite:
        return {
            "TIC": candidate.tic,
            "status": "exists",
            "priority": candidate.ttv_priority,
            "n_measured": "",
            "plot": str(plot_path),
            "csv": str(measurements_path),
        }

    out_dir.mkdir(parents=True, exist_ok=True)
    time, flux = load_lightcurve(candidate)
    epochs = expected_epochs(time, candidate)
    measurements: list[TransitMeasurement] = []
    for epoch, expected_time in epochs:
        measurement = measure_one_transit(
            candidate,
            time,
            flux,
            epoch,
            expected_time,
            min_points=min_points,
        )
        if measurement is not None:
            measurements.append(measurement)

    write_measurements(measurements_path, measurements)
    write_candidate_summary(out_dir / f"TIC_{candidate.tic}_summary.txt", candidate, measurements)
    if measurements:
        plot_candidate_oc(plot_path, candidate, measurements)
    else:
        plot_empty_candidate(plot_path, candidate)

    return {
        "TIC": candidate.tic,
        "status": "created",
        "priority": candidate.ttv_priority,
        "n_expected": len(epochs),
        "n_measured": len(measurements),
        "plot": str(plot_path),
        "csv": str(measurements_path),
    }


def write_measurements(path: Path, measurements: list[TransitMeasurement]) -> None:
    fields = [
        "TIC",
        "epoch",
        "expected_time_btjd",
        "observed_time_btjd",
        "oc_minutes",
        "timing_uncertainty_minutes",
        "depth_ppt",
        "local_scatter_ppt",
        "n_points",
        "n_in_transit",
        "quality",
    ]
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for m in measurements:
            writer.writerow(
                {
                    "TIC": m.tic,
                    "epoch": m.epoch,
                    "expected_time_btjd": f"{m.expected_time:.10f}",
                    "observed_time_btjd": f"{m.observed_time:.10f}",
                    "oc_minutes": f"{m.oc_minutes:.4f}",
                    "timing_uncertainty_minutes": f"{m.timing_uncertainty_minutes:.4f}",
                    "depth_ppt": f"{m.depth_ppt:.5f}",
                    "local_scatter_ppt": f"{m.local_scatter_ppt:.5f}",
                    "n_points": m.n_points,
                    "n_in_transit": m.n_in_transit,
                    "quality": m.quality,
                }
            )


def write_candidate_summary(
    path: Path,
    candidate: Candidate,
    measurements: list[TransitMeasurement],
) -> None:
    ok = [m for m in measurements if m.quality == "OK"]
    oc = np.array([m.oc_minutes for m in ok], dtype=float)
    lines = [
        f"TIC: {candidate.tic}",
        f"Priority: {candidate.ttv_priority}",
        f"HZ status: {candidate.hz_status}",
        f"False-positive flag: {candidate.is_fp}",
        f"Period [d]: {candidate.period:.10f}",
        f"Duration [d]: {candidate.duration:.10f}",
        f"T0 [BTJD]: {candidate.t0:.10f}",
        f"Pipeline transit_count: {candidate.transit_count}",
        f"Pipeline SNR: {candidate.snr:.4f}",
        f"Measurements total: {len(measurements)}",
        f"Measurements OK: {len(ok)}",
    ]
    if len(oc) >= 2:
        lines.extend(
            [
                f"OK O-C median [min]: {float(np.nanmedian(oc)):.4f}",
                f"OK O-C std [min]: {float(np.nanstd(oc)):.4f}",
                f"OK O-C peak-to-peak [min]: {float(np.nanmax(oc) - np.nanmin(oc)):.4f}",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def plot_candidate_oc(
    path: Path,
    candidate: Candidate,
    measurements: list[TransitMeasurement],
) -> None:
    epochs = np.array([m.epoch for m in measurements], dtype=float)
    oc = np.array([m.oc_minutes for m in measurements], dtype=float)
    unc = np.array([m.timing_uncertainty_minutes for m in measurements], dtype=float)
    depth = np.array([m.depth_ppt for m in measurements], dtype=float)
    colors = ["tab:blue" if m.quality == "OK" else "tab:orange" for m in measurements]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10.5, 7.5), dpi=150, sharex=True)
    ax1.axhline(0, color="black", linewidth=0.9, alpha=0.55)
    ax1.errorbar(epochs, oc, yerr=unc, fmt="none", ecolor="0.55", alpha=0.55, linewidth=0.8)
    ax1.scatter(epochs, oc, c=colors, s=34, zorder=3)
    ax1.set_ylabel("O-C [min]")
    ax1.set_title(
        f"TIC {candidate.tic} | {candidate.ttv_priority} | "
        f"P={candidate.period:.5f} d | Ntr={candidate.transit_count} | SNR={candidate.snr:.1f}"
    )
    ax1.grid(alpha=0.25)

    ax2.scatter(epochs, depth, c=colors, s=30)
    ax2.set_xlabel("Transit epoch")
    ax2.set_ylabel("Measured depth [ppt]")
    ax2.grid(alpha=0.25)

    legend_text = "blue=OK, orange=weak/warn"
    ax2.text(
        0.01,
        0.04,
        legend_text,
        transform=ax2.transAxes,
        fontsize=8,
        color="0.25",
    )
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_empty_candidate(path: Path, candidate: Candidate) -> None:
    fig, ax = plt.subplots(figsize=(8, 4), dpi=150)
    ax.text(0.5, 0.5, "No measurable transits", ha="center", va="center")
    ax.set_title(f"TIC {candidate.tic} | {candidate.ttv_priority}")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def write_run_summary(path: Path, rows: list[dict[str, object]]) -> None:
    fields = ["TIC", "status", "priority", "n_expected", "n_measured", "plot", "csv", "error"]
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def main() -> int:
    args = parse_args()
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    candidates = load_candidates(priority=args.priority, tic=args.tic, limit=args.limit)
    print(f"Kandidaten: {len(candidates)} | priority={args.priority}", flush=True)

    summary_rows: list[dict[str, object]] = []
    for idx, candidate in enumerate(candidates, start=1):
        try:
            row = analyze_candidate(
                candidate,
                min_points=args.min_points,
                overwrite=args.overwrite,
            )
        except Exception as exc:
            row = {
                "TIC": candidate.tic,
                "status": "error",
                "priority": candidate.ttv_priority,
                "error": f"{type(exc).__name__}: {exc}",
            }
        summary_rows.append(row)
        print(
            f"{idx}/{len(candidates)} TIC {candidate.tic}: "
            f"{row.get('status')} measured={row.get('n_measured', '')}",
            flush=True,
        )

    summary_name = "ttv_run_summary"
    if args.tic is not None:
        summary_name += f"_TIC_{args.tic}"
    else:
        summary_name += f"_{args.priority}"
    write_run_summary(OUT_ROOT / f"{summary_name}.csv", summary_rows)
    print(f"Fertig: {OUT_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
