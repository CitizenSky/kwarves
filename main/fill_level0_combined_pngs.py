#!/usr/bin/env python3
"""Ensure every Level-0 candidate folder has LICHTKURVE_COMBINED.png."""

from __future__ import annotations

import csv
import math
import os
import shutil
import sqlite3
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


PROJECT_ROOT = Path(os.environ.get("ASTRO_PROJECT_ROOT", "/Users/koni/astro_projects"))
DB_PATH = PROJECT_ROOT / "database" / "planet_hunter.db"
LEVEL0_ROOT = PROJECT_ROOT / "level0_lichtjahre_10ly_bis_500"
MANIFEST_PATH = LEVEL0_ROOT / "manifest_all_candidates_by_distance.csv"
REPORT_DIR = LEVEL0_ROOT / "LEVEL0" / "99_REPORTS"
REFERENCE_DIR = PROJECT_ROOT / "level1_rohkandidaten" / "level1_alle_kandidaten_referenzplots"
GENERATED_ROOT = PROJECT_ROOT / "level1_rohkandidaten" / "level1_auto_plots_neuer_lauf" / "generated_level0_missing"


def safe_float(value: Any, default: float = math.nan) -> float:
    try:
        if value in (None, ""):
            return default
        out = float(value)
    except Exception:
        return default
    return out if np.isfinite(out) else default


def read_manifest() -> list[dict[str, str]]:
    with MANIFEST_PATH.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_db_rows() -> dict[int, dict[str, Any]]:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=60)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM candidates_v2").fetchall()
    finally:
        conn.close()
    return {int(row["TIC"]): dict(row) for row in rows}


def normalize_flux(flux: np.ndarray) -> np.ndarray:
    med = float(np.nanmedian(flux)) if len(flux) else math.nan
    if np.isfinite(med) and abs(med) > 1e-10:
        return flux / med
    return flux - med + 1.0


def load_lightcurve(path: Path) -> tuple[np.ndarray, np.ndarray] | None:
    if not path.exists():
        return None
    try:
        data = np.genfromtxt(path, delimiter=",", names=True, dtype=float)
        if data.size == 0:
            return None
        time = np.asarray(data["time"], dtype=float)
        flux = np.asarray(data["flux"], dtype=float)
        mask = np.isfinite(time) & np.isfinite(flux)
        time, flux = time[mask], flux[mask]
        if len(time) < 20:
            return None
        med = float(np.nanmedian(flux))
        std = float(np.nanstd(flux))
        if np.isfinite(std) and std > 0:
            keep = np.abs(flux - med) < 7.0 * std
            time, flux = time[keep], flux[keep]
        order = np.argsort(time)
        return time[order], normalize_flux(flux[order])
    except Exception:
        return None


def sample(x: np.ndarray, y: np.ndarray, max_points: int) -> tuple[np.ndarray, np.ndarray]:
    if len(x) <= max_points:
        return x, y
    idx = np.linspace(0, len(x) - 1, max_points, dtype=int)
    return x[idx], y[idx]


def robust_ylim(values: np.ndarray, min_abs: float = 6.0) -> tuple[float, float]:
    finite = values[np.isfinite(values)]
    if len(finite) == 0:
        return -min_abs, min_abs
    lo, hi = np.nanpercentile(finite, [1, 99])
    span = max(abs(float(lo)), abs(float(hi)), min_abs) * 1.15
    return -span, span


def binned_median(x: np.ndarray, y: np.ndarray, bins: int = 90) -> tuple[np.ndarray, np.ndarray]:
    if len(x) == 0:
        return np.array([]), np.array([])
    edges = np.linspace(float(np.nanmin(x)), float(np.nanmax(x)), bins + 1)
    centers = 0.5 * (edges[:-1] + edges[1:])
    out = np.full(bins, np.nan)
    which = np.digitize(x, edges) - 1
    for idx in range(bins):
        mask = which == idx
        if np.any(mask):
            out[idx] = float(np.nanmedian(y[mask]))
    keep = np.isfinite(out)
    return centers[keep], out[keep]


def reference_plot(tic: str) -> Path | None:
    matches = sorted(REFERENCE_DIR.glob(f"TIC_{tic}_*_combined.png"))
    if matches:
        return matches[0]
    matches = sorted(GENERATED_ROOT.glob(f"TIC_{tic}_*_combined.png"))
    return matches[0] if matches else None


def materialize_png(source: Path, target: Path) -> None:
    source = source.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        if not target.is_symlink():
            try:
                if os.path.samefile(source, target):
                    return
            except OSError:
                pass
        target.unlink()
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def plot_combined(row: dict[str, Any], out_path: Path) -> str:
    tic = int(row["TIC"])
    period = safe_float(row.get("best_period") or row.get("period"))
    duration = safe_float(row.get("duration"), 0.2)
    t0 = safe_float(row.get("transit_time") or row.get("epoch"))
    depth = safe_float(row.get("depth"), 0.0)
    rp = safe_float(row.get("planet_radius_earth"), 0.0)
    snr = safe_float(row.get("transit_snr"), 0.0)
    hz = str(row.get("hz_class") or row.get("hz_status") or "UNKNOWN")
    lc_path = Path(str(row.get("lightcurve_dir") or ""))
    if not lc_path.exists():
        lc_path = PROJECT_ROOT / "lightcurves" / f"TIC_{tic}" / f"TIC_{tic}_lightcurve.csv"
    if not np.isfinite(period) or period <= 0 or not np.isfinite(t0):
        return "bad_ephemeris"
    loaded = load_lightcurve(lc_path)
    if loaded is None:
        return "missing_lightcurve"
    time, flux = loaded
    rel_ppt = (flux - 1.0) * 1000.0
    raw_t, raw_y = sample(time, rel_ppt, 25000)
    phase_h = (((time - t0 + period / 2.0) % period) - period / 2.0) * 24.0
    zoom_h = min(period * 12.0, max(8.0, duration * 24.0 * 6.0))
    zoom = np.abs(phase_h) <= zoom_h
    if int(np.count_nonzero(zoom)) < 20:
        zoom = np.ones(len(phase_h), dtype=bool)
    fold_x = phase_h[zoom]
    fold_y = rel_ppt[zoom]
    order = np.argsort(fold_x)
    fold_x, fold_y = fold_x[order], fold_y[order]
    fold_x_plot, fold_y_plot = sample(fold_x, fold_y, 18000)
    bin_x, bin_y = binned_median(fold_x, fold_y, bins=95)

    title = f"TIC {tic} | {hz} | P={period:.4f} d | Rp={rp:.2f} Re | SNR={snr:.1f}"
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), dpi=150)
    ax1.scatter(raw_t, raw_y, s=3, alpha=0.45, linewidths=0, color="#336699")
    ax1.axhline(0, color="black", alpha=0.45, linewidth=0.8)
    ax1.set_title(title)
    ax1.set_xlabel("TESS time [BTJD days]")
    ax1.set_ylabel("relative flux [ppt]")
    ax1.set_ylim(*robust_ylim(raw_y, min_abs=8.0))
    ax1.grid(alpha=0.25)

    ax2.scatter(fold_x_plot, fold_y_plot, s=4, alpha=0.18, linewidths=0, color="#336699")
    if len(bin_x):
        ax2.plot(bin_x, bin_y, color="#b7352d", linewidth=2.0)
    half_duration_h = max(duration * 12.0, 0.2)
    ax2.axhline(0, color="black", alpha=0.45, linewidth=0.8)
    ax2.axvline(0, color="black", alpha=0.65, linewidth=0.9)
    ax2.axvspan(-half_duration_h, half_duration_h, color="#d77b72", alpha=0.16)
    if np.isfinite(depth) and depth > 0:
        ax2.axhline(-depth * 1000.0, color="#2f5597", alpha=0.45, linewidth=1)
    ax2.set_xlim(-zoom_h, zoom_h)
    ax2.set_ylim(*robust_ylim(fold_y, min_abs=6.0))
    ax2.set_xlabel("Phase relative to transit center [hours]")
    ax2.set_ylabel("relative flux [ppt]")
    ax2.grid(alpha=0.25)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    return "generated"


def main() -> int:
    manifest = read_manifest()
    db = load_db_rows()
    stats: dict[str, int] = {}
    rows_out: list[dict[str, Any]] = []
    for idx, manifest_row in enumerate(manifest, start=1):
        tic = manifest_row["TIC"]
        candidate_dir = PROJECT_ROOT / manifest_row["candidate_folder"]
        png_dir = candidate_dir / "lichtkurven_png"
        combined = png_dir / "LICHTKURVE_COMBINED.png"
        status = "already_exists" if combined.exists() and not combined.is_symlink() else ""
        source = ""
        if combined.is_symlink() and combined.exists():
            source_path = combined.resolve()
            materialize_png(source_path, combined)
            status = "materialized_symlink"
            source = str(source_path)
        if not status:
            ref = reference_plot(tic)
            if ref is not None and ref.exists():
                materialize_png(ref, combined)
                status = "linked_reference"
                source = str(ref)
            else:
                row = {**manifest_row, **db.get(int(tic), {})}
                row["TIC"] = tic
                generated = GENERATED_ROOT / f"TIC_{tic}_level0_combined.png"
                status = plot_combined(row, generated)
                if status == "generated" and generated.exists():
                    materialize_png(generated, combined)
                    source = str(generated)
        stats[status] = stats.get(status, 0) + 1
        rows_out.append(
            {
                "TIC": tic,
                "candidate_folder": str(candidate_dir),
                "combined_png": str(combined),
                "status": status,
                "source": source,
            }
        )
        if idx % 100 == 0 or idx == len(manifest):
            print(f"{idx}/{len(manifest)} {stats}", flush=True)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = REPORT_DIR / "level0_combined_png_fill_report.csv"
    with report.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["TIC", "candidate_folder", "combined_png", "status", "source"])
        writer.writeheader()
        writer.writerows(rows_out)
    legacy_report = LEVEL0_ROOT / "level0_combined_png_fill_report.csv"
    if legacy_report.exists() and legacy_report != report:
        legacy_report.unlink()
    print(f"Report: {report}")
    print(stats)
    return 0 if not any(row["status"] in {"bad_ephemeris", "missing_lightcurve"} for row in rows_out) else 2


if __name__ == "__main__":
    raise SystemExit(main())
