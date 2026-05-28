#!/usr/bin/env python3
"""Create overview graphics from TTV CSV and O-C plot outputs."""

from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path("/Users/koni/astro_projects")
TTV_ROOT = PROJECT_ROOT / "level4_TTV_analyse"
PRIORITY_CSV = TTV_ROOT / "level4_02_ttv_prioritaet" / "ttv_prioritaet_alle_kandidaten.csv"
OC_ROOT = TTV_ROOT / "level4_04_oc_ergebnisse"
OUT_DIR = TTV_ROOT / "level4_05_grafiken"


def priority_folder(priority: str) -> str:
    return priority if priority.startswith("level4_") else f"level4_{priority}"


def read_priority_rows() -> list[dict[str, str]]:
    with PRIORITY_CSV.open(newline="") as fh:
        return list(csv.DictReader(fh))


def float_col(rows: list[dict[str, str]], key: str) -> np.ndarray:
    values = []
    for row in rows:
        try:
            values.append(float(row.get(key, "") or "nan"))
        except ValueError:
            values.append(float("nan"))
    return np.asarray(values, dtype=float)


def str_col(rows: list[dict[str, str]], key: str) -> list[str]:
    return [str(row.get(key, "")) for row in rows]


def priority_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        prio = row.get("ttv_prioritaet", "UNKNOWN") or "UNKNOWN"
        counts[prio] = counts.get(prio, 0) + 1
    return counts


def save_priority_bar(rows: list[dict[str, str]]) -> None:
    counts = priority_counts(rows)
    order = ["TTV_A", "TTV_B", "TTV_C", "HZ_TTV_SCHWER", "NIEDRIG"]
    labels = [label for label in order if label in counts]
    values = [counts[label] for label in labels]

    fig, ax = plt.subplots(figsize=(10, 5), dpi=160)
    bars = ax.bar(labels, values, color=["#2c7fb8", "#41b6c4", "#a1dab4", "#fdae61", "#bdbdbd"])
    ax.set_title("TTV-Prioritaetsverteilung")
    ax.set_ylabel("Anzahl Kandidaten")
    ax.grid(axis="y", alpha=0.25)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), str(value), ha="center", va="bottom")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "01_ttv_prioritaet_verteilung.png")
    plt.close(fig)


def save_snr_transit_scatter(rows: list[dict[str, str]]) -> None:
    snr = float_col(rows, "transit_snr")
    ntr = float_col(rows, "transit_count")
    period = float_col(rows, "best_period")
    prios = str_col(rows, "ttv_prioritaet")
    colors = {
        "TTV_A": "#1f78b4",
        "TTV_B": "#33a02c",
        "TTV_C": "#ff7f00",
        "HZ_TTV_SCHWER": "#6a3d9a",
        "NIEDRIG": "#bdbdbd",
    }

    fig, ax = plt.subplots(figsize=(10, 6), dpi=160)
    for prio, color in colors.items():
        mask = np.array([p == prio for p in prios])
        if np.any(mask):
            sizes = np.clip(np.sqrt(period[mask]) * 18.0, 16.0, 110.0)
            ax.scatter(ntr[mask], snr[mask], s=sizes, alpha=0.65, label=prio, color=color, edgecolors="none")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Transitanzahl")
    ax.set_ylabel("Transit SNR")
    ax.set_title("TTV-Kandidaten: Transitanzahl vs. SNR")
    ax.grid(alpha=0.25, which="both")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "02_transitanzahl_vs_snr.png")
    plt.close(fig)


def save_period_transit_scatter(rows: list[dict[str, str]]) -> None:
    period = float_col(rows, "best_period")
    ntr = float_col(rows, "transit_count")
    radius = float_col(rows, "planet_radius_earth")
    prios = str_col(rows, "ttv_prioritaet")
    colors = {
        "TTV_A": "#1f78b4",
        "TTV_B": "#33a02c",
        "TTV_C": "#ff7f00",
        "HZ_TTV_SCHWER": "#6a3d9a",
        "NIEDRIG": "#bdbdbd",
    }

    fig, ax = plt.subplots(figsize=(10, 6), dpi=160)
    for prio, color in colors.items():
        mask = np.array([p == prio for p in prios])
        if np.any(mask):
            sizes = np.clip(radius[mask] * 18.0, 14.0, 95.0)
            ax.scatter(period[mask], ntr[mask], s=sizes, alpha=0.65, label=prio, color=color, edgecolors="none")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Periode [Tage]")
    ax.set_ylabel("Transitanzahl")
    ax.set_title("TTV-Kandidaten: Periode vs. Transitanzahl")
    ax.grid(alpha=0.25, which="both")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "03_periode_vs_transitanzahl.png")
    plt.close(fig)


def read_run_summaries() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(OC_ROOT.glob("ttv_run_summary_*.csv")):
        with path.open(newline="") as fh:
            for row in csv.DictReader(fh):
                rows.append(row)
    return rows


def save_measured_bar(rows: list[dict[str, str]]) -> None:
    selected = []
    for row in rows:
        try:
            measured = int(float(row.get("n_measured", "") or 0))
        except ValueError:
            measured = 0
        selected.append((str(row.get("TIC", "")), str(row.get("priority", "")), measured))
    selected.sort(key=lambda x: (x[1], -x[2], x[0]))

    if not selected:
        return
    labels = [tic for tic, _, _ in selected]
    values = [measured for _, _, measured in selected]
    colors = ["#1f78b4" if prio == "TTV_A" else "#33a02c" for _, prio, _ in selected]

    height = max(6.0, 0.28 * len(selected))
    fig, ax = plt.subplots(figsize=(11, height), dpi=160)
    y = np.arange(len(selected))
    ax.barh(y, values, color=colors)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Gemessene Einzeltransits")
    ax.set_title("O-C Lauf: gemessene Transits pro TIC")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "04_gemessene_transits_pro_tic.png")
    plt.close(fig)


def make_contact_sheet(priority: str, max_images: int = 60) -> None:
    paths = sorted((OC_ROOT / priority_folder(priority)).glob("TIC_*/TIC_*_oc_plot.png"))[:max_images]
    if not paths:
        return

    thumbs: list[Image.Image] = []
    labels: list[str] = []
    for path in paths:
        img = Image.open(path).convert("RGB")
        img.thumbnail((360, 260), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (380, 300), "white")
        canvas.paste(img, ((380 - img.width) // 2, 20))
        tic = path.parent.name
        labels.append(tic)
        draw = ImageDraw.Draw(canvas)
        draw.text((12, 6), tic, fill=(0, 0, 0))
        thumbs.append(canvas)

    cols = 3
    rows = math.ceil(len(thumbs) / cols)
    sheet = Image.new("RGB", (cols * 380, rows * 300 + 46), "white")
    draw = ImageDraw.Draw(sheet)
    draw.text((14, 14), f"{priority} O-C Kontaktbogen ({len(thumbs)} Plots)", fill=(0, 0, 0))
    for idx, thumb in enumerate(thumbs):
        x = (idx % cols) * 380
        y = 46 + (idx // cols) * 300
        sheet.paste(thumb, (x, y))
    sheet.save(OUT_DIR / f"05_{priority}_oc_kontaktbogen.png")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = read_priority_rows()
    save_priority_bar(rows)
    save_snr_transit_scatter(rows)
    save_period_transit_scatter(rows)
    save_measured_bar(read_run_summaries())
    make_contact_sheet("TTV_A")
    make_contact_sheet("TTV_B")
    print(f"Fertig: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
