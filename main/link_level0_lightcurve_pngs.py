#!/usr/bin/env python3
"""Expose light-curve PNGs for active level0 candidates.

For each selected candidate, this creates a `lichtkurven_png/` folder with
short symlinks to the best available plots. If a candidate has a local
light-curve CSV but no PNG yet, a compact raw/folded/combined plot set is
generated first.
"""

from __future__ import annotations

import csv
import math
import os
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "database" / "planet_hunter.db"
LEVEL0_MANIFEST = PROJECT_ROOT / "level0_lichtjahre_10ly_bis_500" / "manifest_all_candidates_by_distance.csv"
PLOT_ROOT = PROJECT_ROOT / "level1_rohkandidaten" / "level1_auto_plots_neuer_lauf"
GENERATED_ROOT = PLOT_ROOT / "generated_level0_missing"


def read_manifest() -> list[dict[str, str]]:
    with LEVEL0_MANIFEST.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def selected_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("markierung") != "ROT"]


def safe_float(value: Any, default: float = math.nan) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def load_candidate_row(tic: str) -> dict[str, Any]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("select * from candidates_v2 where TIC=?", (int(tic),)).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def load_lightcurve_csv(path: Path) -> tuple[np.ndarray, np.ndarray]:
    arr = np.loadtxt(path, delimiter=",", skiprows=1, usecols=(0, 1), ndmin=2)
    time = arr[:, 0].astype(float)
    flux = arr[:, 1].astype(float)
    mask = np.isfinite(time) & np.isfinite(flux)
    time = time[mask]
    flux = flux[mask]
    order = np.argsort(time)
    return time[order], flux[order]


def downsample(time: np.ndarray, flux: np.ndarray, max_points: int = 20000) -> tuple[np.ndarray, np.ndarray]:
    if len(time) <= max_points:
        return time, flux
    idx = np.linspace(0, len(time) - 1, max_points).astype(int)
    return time[idx], flux[idx]


def phase_hours(time: np.ndarray, period: float, transit_time: float) -> np.ndarray:
    phase_days = ((time - transit_time + 0.5 * period) % period) - 0.5 * period
    return phase_days * 24.0


def generated_plot_paths(tic: str, hz_status: str, period: float, rp: float, snr: float) -> dict[str, Path]:
    GENERATED_ROOT.mkdir(parents=True, exist_ok=True)
    prefix = f"TIC_{tic}_{hz_status or 'UNKNOWN'}_P{period:.6f}d_Rp{rp:.3f}Re_SNR{snr:.2f}"
    return {
        "raw": GENERATED_ROOT / f"{prefix}_raw.png",
        "folded": GENERATED_ROOT / f"{prefix}_folded.png",
        "combined": GENERATED_ROOT / f"{prefix}_combined.png",
    }


def generate_plots_if_missing(tic: str) -> dict[str, Path]:
    cand = load_candidate_row(tic)
    if not cand:
        return {}

    lc_path = Path(str(cand.get("lightcurve_dir") or ""))
    if not lc_path.exists():
        return {}

    period = safe_float(cand.get("best_period"))
    duration = safe_float(cand.get("duration"), 0.2)
    transit_time = safe_float(cand.get("transit_time"))
    depth = safe_float(cand.get("depth"), 0.0)
    rp = safe_float(cand.get("planet_radius_earth"), 0.0)
    snr = safe_float(cand.get("transit_snr"), 0.0)
    hz_status = str(cand.get("hz_status") or "")

    if not np.isfinite(period) or period <= 0 or not np.isfinite(transit_time):
        return {}

    paths = generated_plot_paths(tic, hz_status, period, rp, snr)
    if all(path.exists() for path in paths.values()):
        return paths

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    time, flux = load_lightcurve_csv(lc_path)
    if len(time) == 0:
        return {}
    plot_time, plot_flux = downsample(time, flux)
    ph = phase_hours(time, period, transit_time)
    phase_window_hours = max(duration * 24.0 * 4.0, 8.0)
    phase_mask = np.abs(ph) <= phase_window_hours

    title = f"TIC {tic} | P={period:.4f} d | Rp={rp:.2f} Re | SNR={snr:.1f} | {hz_status}"

    fig, ax = plt.subplots(figsize=(11, 4.5), dpi=150)
    ax.scatter(plot_time, plot_flux, s=1.5, alpha=0.55, color="black", linewidths=0)
    ax.set_title(f"{title} | raw")
    ax.set_xlabel("Time [BTJD]")
    ax.set_ylabel("Flux")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(paths["raw"])
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9.5, 4.8), dpi=150)
    if np.any(phase_mask):
        ax.scatter(ph[phase_mask], flux[phase_mask], s=4, alpha=0.65, color="black", linewidths=0)
    else:
        ax.scatter(ph, flux, s=2, alpha=0.35, color="black", linewidths=0)
    half_duration_h = max(duration * 12.0, 0.2)
    ax.axvspan(-half_duration_h, half_duration_h, color="tab:red", alpha=0.12)
    ax.axvline(0, color="tab:red", alpha=0.55, linewidth=1)
    if depth and np.isfinite(depth):
        ax.axhline(1.0 - depth, color="tab:blue", alpha=0.4, linewidth=1)
    ax.set_title(f"{title} | folded")
    ax.set_xlabel("Phase relative to transit [hours]")
    ax.set_ylabel("Flux")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(paths["folded"])
    plt.close(fig)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8), dpi=150)
    ax1.scatter(plot_time, plot_flux, s=1.5, alpha=0.55, color="black", linewidths=0)
    ax1.set_title(f"{title} | raw")
    ax1.set_xlabel("Time [BTJD]")
    ax1.set_ylabel("Flux")
    ax1.grid(alpha=0.25)
    if np.any(phase_mask):
        ax2.scatter(ph[phase_mask], flux[phase_mask], s=4, alpha=0.65, color="black", linewidths=0)
    else:
        ax2.scatter(ph, flux, s=2, alpha=0.35, color="black", linewidths=0)
    ax2.axvspan(-half_duration_h, half_duration_h, color="tab:red", alpha=0.12)
    ax2.axvline(0, color="tab:red", alpha=0.55, linewidth=1)
    ax2.set_title("Folded transit view")
    ax2.set_xlabel("Phase relative to transit [hours]")
    ax2.set_ylabel("Flux")
    ax2.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(paths["combined"])
    plt.close(fig)

    return paths


def choose_existing_pngs(candidate_dir: Path) -> dict[str, Path]:
    data_links = candidate_dir / "data_links"
    pngs = sorted(data_links.glob("*.png")) if data_links.exists() else []
    chosen: dict[str, Path] = {}

    priority = {
        "combined": ("combined", "lightcurve"),
        "folded": ("folded", "phase"),
        "raw": ("raw",),
    }
    for key, needles in priority.items():
        for path in pngs:
            name = path.name.lower()
            if any(needle in name for needle in needles):
                chosen[key] = path
                break
    return chosen


def link_plot(target: Path, link: Path) -> None:
    target = target.resolve()
    if link.is_symlink():
        if Path(os.readlink(link)) == target:
            return
        link.unlink()
    elif link.exists():
        link.unlink()
    os.symlink(target, link)


def main() -> None:
    rows = selected_rows(read_manifest())
    linked = 0
    generated = 0
    missing: list[str] = []

    for row in rows:
        tic = row["TIC"]
        candidate_dir = PROJECT_ROOT / row["candidate_folder"]
        png_dir = candidate_dir / "lichtkurven_png"
        png_dir.mkdir(parents=True, exist_ok=True)

        chosen = choose_existing_pngs(candidate_dir)
        if "combined" not in chosen:
            generated_paths = generate_plots_if_missing(tic)
            generated += len([p for p in generated_paths.values() if p.exists()])
            for key, path in generated_paths.items():
                if path.exists():
                    chosen.setdefault(key, path)

        if not chosen:
            missing.append(tic)
            continue

        for key, path in chosen.items():
            link_plot(path, png_dir / f"LICHTKURVE_{key.upper()}.png")
            linked += 1

    missing_path = PROJECT_ROOT / "level0_lichtjahre_10ly_bis_500" / "lichtkurven_png_missing.csv"
    with missing_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["TIC"])
        for tic in missing:
            writer.writerow([tic])

    print(f"Selected active candidates: {len(rows)}")
    print(f"PNG links created/updated: {linked}")
    print(f"Generated PNG files: {generated}")
    print(f"Missing candidates without PNG: {len(missing)}")
    print(f"Missing manifest: {missing_path}")


if __name__ == "__main__":
    main()
