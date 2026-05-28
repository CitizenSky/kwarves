#!/usr/bin/env python3
"""Export combined candidate plots in the manual-reference style."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


PROJECT_ROOT = Path("/Users/koni/astro_projects")
DB_PATH = PROJECT_ROOT / "database" / "planet_hunter.db"
OUT_DIR = PROJECT_ROOT / "level1_rohkandidaten" / "level1_alle_kandidaten_referenzplots"
MANIFEST_PATH = OUT_DIR / "alle_kandidaten_referenzplots_manifest.csv"
MAX_RAW_POINTS = 30000
MAX_FOLDED_POINTS = 18000


def safe_token(value) -> str:
    text = str(value if value is not None else "UNKNOWN")
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in text)


def sample_arrays(x: np.ndarray, y: np.ndarray, max_points: int) -> tuple[np.ndarray, np.ndarray]:
    if max_points <= 0 or len(x) <= max_points:
        return x, y
    idx = np.linspace(0, len(x) - 1, max_points, dtype=int)
    return x[idx], y[idx]


def load_lightcurve(path: str | None, tic: int) -> tuple[np.ndarray, np.ndarray] | None:
    candidates = []
    if path:
        candidates.append(Path(path))
    candidates.append(PROJECT_ROOT / "lightcurves" / f"TIC_{tic}" / f"TIC_{tic}_lightcurve.csv")

    for csv_path in candidates:
        if not csv_path.exists():
            continue
        try:
            data = np.genfromtxt(csv_path, delimiter=",", names=True, dtype=float)
            if data.size == 0:
                continue
            time = np.asarray(data["time"], dtype=float)
            flux = np.asarray(data["flux"], dtype=float)
            mask = np.isfinite(time) & np.isfinite(flux)
            time, flux = time[mask], flux[mask]
            if len(time) < 20:
                continue

            med = np.nanmedian(flux)
            std = np.nanstd(flux)
            if np.isfinite(std) and std > 0:
                keep = np.abs(flux - med) < 5.0 * std
                time, flux = time[keep], flux[keep]
            med = np.nanmedian(flux)
            if np.isfinite(med) and abs(med) > 1e-8:
                flux = flux / med
            elif np.isfinite(med):
                flux = flux - med + 1.0
            return time, flux
        except Exception:
            continue
    return None


def rolling_bin_median(x: np.ndarray, y: np.ndarray, bins: int = 90) -> tuple[np.ndarray, np.ndarray]:
    if len(x) == 0:
        return np.array([]), np.array([])
    edges = np.linspace(np.nanmin(x), np.nanmax(x), bins + 1)
    centers = 0.5 * (edges[:-1] + edges[1:])
    values = np.full(bins, np.nan)
    which = np.digitize(x, edges) - 1
    for idx in range(bins):
        mask = which == idx
        if np.any(mask):
            values[idx] = np.nanmedian(y[mask])
    keep = np.isfinite(values)
    return centers[keep], values[keep]


def row_dicts() -> list[sqlite3.Row]:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            """
            SELECT
                id, TIC, best_period, duration, transit_time, depth,
                planet_radius_earth, transit_snr, transit_count,
                hz_status, is_fp, lightcurve_dir
            FROM candidates_v2
            ORDER BY
                CASE hz_status
                    WHEN 'KONSERVATIVE_HZ' THEN 0
                    WHEN 'OPT_HZ_INNEN' THEN 1
                    WHEN 'OPT_HZ_AUSSEN' THEN 2
                    ELSE 3
                END,
                COALESCE(is_fp, 0),
                transit_snr DESC,
                TIC
            """
        ).fetchall()
    finally:
        conn.close()


def robust_ylim(values: np.ndarray, pad: float = 1.15, min_abs: float = 4.0) -> tuple[float, float]:
    finite = values[np.isfinite(values)]
    if len(finite) == 0:
        return -min_abs, min_abs
    lo, hi = np.nanpercentile(finite, [1, 99])
    span = max(abs(lo), abs(hi), min_abs) * pad
    return -span, span


def plot_candidate(row: sqlite3.Row) -> tuple[str, str]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tic = int(row["TIC"])
    period = float(row["best_period"])
    duration = float(row["duration"])
    t0 = float(row["transit_time"])
    hz = row["hz_status"] or "UNKNOWN"
    is_fp = int(row["is_fp"] or 0)
    radius = row["planet_radius_earth"]
    snr = row["transit_snr"]
    ntr = row["transit_count"]

    if not np.isfinite(period) or period <= 0 or not np.isfinite(t0):
        return "bad_ephemeris", ""

    lc = load_lightcurve(row["lightcurve_dir"], tic)
    if lc is None:
        return "missing_lightcurve", ""
    time, flux = lc

    rel_ppt = (flux - 1.0) * 1000.0
    phase_days = ((time - t0 + period / 2.0) % period) - period / 2.0
    phase_hours = phase_days * 24.0

    duration_hours = duration * 24.0 if np.isfinite(duration) and duration > 0 else 1.0
    half_duration = duration_hours / 2.0
    zoom_hours = min(period * 12.0, max(6.0, 6.0 * duration_hours))
    zoom_mask = np.abs(phase_hours) <= zoom_hours
    if np.count_nonzero(zoom_mask) < 20:
        return "too_few_zoom_points", ""

    raw_t, raw_y = sample_arrays(time, rel_ppt, MAX_RAW_POINTS)
    fold_x = phase_hours[zoom_mask]
    fold_y = rel_ppt[zoom_mask]
    order = np.argsort(fold_x)
    fold_x, fold_y = fold_x[order], fold_y[order]
    fold_x_plot, fold_y_plot = sample_arrays(fold_x, fold_y, MAX_FOLDED_POINTS)
    bin_x, bin_y = rolling_bin_median(fold_x, fold_y, bins=95)

    rp_token = f"{float(radius):.3f}" if radius is not None else "NA"
    snr_token = f"{float(snr):.2f}" if snr is not None else "NA"
    fp_token = "_FP" if is_fp else ""
    filename = (
        f"TIC_{tic}_{safe_token(hz)}{fp_token}"
        f"_P{period:.6f}d_Rp{rp_token}Re_SNR{snr_token}_combined.png"
    )
    out_path = OUT_DIR / filename

    title = (
        f"TIC {tic} | {hz} | P={period:.4f} d | "
        f"Rp={float(radius):.2f} Re | SNR={float(snr):.1f} | Ntr={ntr}"
    )

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), dpi=150)

    ax1.scatter(raw_t, raw_y, s=4, alpha=0.45, linewidths=0, color="#336699")
    ax1.axhline(0, color="black", alpha=0.45, linewidth=0.8)
    ax1.set_title(title)
    ax1.set_xlabel("TESS time [BTJD days]")
    ax1.set_ylabel("relative flux [ppt]")
    ax1.grid(alpha=0.25)
    ax1.set_ylim(*robust_ylim(raw_y, min_abs=8.0))

    ax2.scatter(fold_x_plot, fold_y_plot, s=5, alpha=0.18, linewidths=0, color="#336699")
    if len(bin_x):
        ax2.plot(bin_x, bin_y, color="#b7352d", linewidth=2.0)
    ax2.axhline(0, color="black", alpha=0.45, linewidth=0.8)
    ax2.axvline(0, color="black", alpha=0.65, linewidth=0.9)
    ax2.axvspan(-half_duration, half_duration, color="#d77b72", alpha=0.16)
    ax2.set_xlim(-zoom_hours, zoom_hours)
    ax2.set_ylim(*robust_ylim(fold_y, min_abs=6.0))
    ax2.set_xlabel("Phase relativ zum Transitzentrum [Stunden]")
    ax2.set_ylabel("relative flux [ppt]")
    ax2.grid(alpha=0.25)

    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    return "created", str(out_path)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = row_dicts()
    stats: dict[str, int] = {}
    with MANIFEST_PATH.open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "TIC",
                "status",
                "path",
                "hz_status",
                "is_fp",
                "period",
                "planet_radius_earth",
                "transit_snr",
                "transit_count",
            ],
        )
        writer.writeheader()
        for idx, row in enumerate(rows, start=1):
            try:
                status, path = plot_candidate(row)
            except Exception as exc:
                plt.close("all")
                status, path = f"error:{type(exc).__name__}", ""
            stats[status] = stats.get(status, 0) + 1
            writer.writerow(
                {
                    "TIC": row["TIC"],
                    "status": status,
                    "path": path,
                    "hz_status": row["hz_status"],
                    "is_fp": row["is_fp"],
                    "period": row["best_period"],
                    "planet_radius_earth": row["planet_radius_earth"],
                    "transit_snr": row["transit_snr"],
                    "transit_count": row["transit_count"],
                }
            )
            if idx % 100 == 0 or idx == len(rows):
                print(f"{idx}/{len(rows)} Kandidaten verarbeitet | {stats}", flush=True)
    print(f"Fertig. Output: {OUT_DIR}")
    print(f"Manifest: {MANIFEST_PATH}")
    print(stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
