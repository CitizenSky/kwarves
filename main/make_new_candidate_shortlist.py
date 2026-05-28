#!/usr/bin/env python3
"""Create Level-3 shortlist of externally unknown planet candidates.

Input is the external catalog cross-match table. Output is a practical folder
structure for manual vetting: the cleanest unknown signals first, weaker cases
later. This does not confirm planets; it prioritizes what to inspect next.
"""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path("/Users/koni/astro_projects")
INPUT_CSV = PROJECT_ROOT / "level3_externe_katalogpruefung/external_catalog_crossmatch_results.csv"
OUT_ROOT = PROJECT_ROOT / "level3_neue_planetenkandidaten"


GROUP_DIRS = {
    "PRIME_NEU_A": "level3_01_PRIME_NEU_A",
    "STARK_NEU_B": "level3_02_STARK_NEU_B",
    "LANGPERIODE_2_TRANSITS": "level3_03_LANGPERIODE_2_TRANSITS",
    "VISUELL_NACHPRUEFEN": "level3_04_VISUELL_NACHPRUEFEN",
    "AUSSORTIERT_STRIKT": "level3_05_AUSSORTIERT_STRIKT",
}


def num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def good_or_nan(series: pd.Series, threshold: float) -> pd.Series:
    values = num(series)
    return values.isna() | (values <= threshold)


def finite_score(value: object) -> float:
    try:
        if pd.isna(value):
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def link_or_copy(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def classify(row: pd.Series) -> str:
    clean_shape = bool(row["strict_clean_shape"])
    dwarf = bool(row["strict_dwarf"])
    k_dwarf = bool(row["strict_k_dwarf"])
    planet_size = bool(row["strict_planet_size"])
    enough_snr = bool(row["strict_snr"])
    enough_transits = bool(row["strict_transits"])
    two_transit_long_period = bool(row["two_transit_long_period"])
    label = str(row.get("level2_planet_label", ""))

    if clean_shape and dwarf and k_dwarf and planet_size and enough_snr and enough_transits and label == "PLANET_PLAUSIBEL_A":
        return "PRIME_NEU_A"
    if clean_shape and dwarf and k_dwarf and planet_size and enough_snr and enough_transits:
        return "STARK_NEU_B"
    if clean_shape and dwarf and k_dwarf and planet_size and enough_snr and two_transit_long_period:
        return "LANGPERIODE_2_TRANSITS"
    if clean_shape and dwarf and planet_size:
        return "VISUELL_NACHPRUEFEN"
    return "AUSSORTIERT_STRIKT"


def reason(row: pd.Series) -> str:
    parts: list[str] = []
    checks = [
        ("extern_unbekannt", row.get("external_group") == "EXTERN_UNBEKANNT_TOP"),
        ("shape_ok", row.get("shape_status") == "OK"),
        ("kein_fp_flag", int(finite_score(row.get("fp_flag_count"))) == 0 and int(finite_score(row.get("is_fp"))) == 0),
        ("zwerg_logg", bool(row.get("strict_dwarf"))),
        ("k_zwerg_teff", bool(row.get("strict_k_dwarf"))),
        ("radius_ok", bool(row.get("strict_planet_size"))),
        ("snr_ok", bool(row.get("strict_snr"))),
        ("transits_ok", bool(row.get("strict_transits")) or bool(row.get("two_transit_long_period"))),
        ("secondary_ok", bool(row.get("strict_secondary"))),
        ("baseline_ok", bool(row.get("strict_baseline"))),
        ("scatter_ok", bool(row.get("strict_scatter"))),
    ]
    for name, ok in checks:
        if ok:
            parts.append(name)
        else:
            parts.append(f"nicht_{name}")
    return ";".join(parts)


def add_scores(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    out["strict_secondary"] = good_or_nan(out["secondary_ratio_measured"], 0.25)
    out["strict_baseline"] = good_or_nan(out["baseline_left_right_delta_ppt"], 0.35)
    out["strict_scatter"] = good_or_nan(out["oot_scatter_ppt"], 3.0)
    out["strict_clean_shape"] = (
        (out["shape_status"].fillna("") == "OK")
        & (num(out["is_fp"]).fillna(0).astype(int) == 0)
        & (num(out["fp_flag_count"]).fillna(0).astype(int) == 0)
        & out["strict_secondary"]
        & out["strict_baseline"]
        & out["strict_scatter"]
    )
    out["strict_dwarf"] = (num(out["stellar_logg"]) >= 4.35) & (num(out["distance_ly"]) <= 500)
    out["strict_k_dwarf"] = num(out["teff"]).between(3900, 5300, inclusive="both")
    out["strict_planet_size"] = num(out["planet_radius_earth"]).between(0.5, 4.0, inclusive="both")
    out["strict_snr"] = (num(out["transit_snr"]) >= 10.0) & (num(out["shape_snr"]) >= 8.0)
    out["strict_transits"] = num(out["transit_count"]) >= 3
    out["two_transit_long_period"] = (num(out["transit_count"]) == 2) & (num(out["period"]) >= 20.0)

    out["shortlist_group"] = out.apply(classify, axis=1)
    out["shortlist_reason"] = out.apply(reason, axis=1)

    group_bonus = {
        "PRIME_NEU_A": 1000,
        "STARK_NEU_B": 800,
        "LANGPERIODE_2_TRANSITS": 650,
        "VISUELL_NACHPRUEFEN": 400,
        "AUSSORTIERT_STRIKT": 0,
    }
    out["shortlist_score"] = (
        out["shortlist_group"].map(group_bonus).fillna(0)
        + num(out["level2_planet_score"]).fillna(0)
        + np.minimum(num(out["transit_snr"]).fillna(0), 80) * 0.3
        + np.minimum(num(out["transit_count"]).fillna(0), 20) * 0.8
        - num(out["secondary_ratio_measured"]).fillna(0) * 20
        - num(out["baseline_left_right_delta_ppt"]).fillna(0) * 4
    ).round(3)
    return out


def export_plots(df: pd.DataFrame, out_root: Path) -> None:
    for dirname in GROUP_DIRS.values():
        group_dir = out_root / dirname
        group_dir.mkdir(parents=True, exist_ok=True)
        for old_plot in group_dir.glob("*.png"):
            old_plot.unlink()

    counters = {key: 0 for key in GROUP_DIRS}
    for _, row in df.sort_values("shortlist_score", ascending=False).iterrows():
        group = row["shortlist_group"]
        src_text = str(row.get("level2_folder_plot") or row.get("reference_plot") or "").strip()
        if not src_text or src_text == "nan":
            continue
        src = Path(src_text)
        if not src.exists():
            continue
        counters[group] += 1
        tic = int(row["TIC"])
        dst = out_root / GROUP_DIRS[group] / f"{counters[group]:04d}_TIC_{tic}_{src.name}"
        link_or_copy(src, dst)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build strict shortlist of new planet candidates.")
    parser.add_argument("--input", type=Path, default=INPUT_CSV)
    parser.add_argument("--out", type=Path, default=OUT_ROOT)
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(args.input)

    args.out.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.input)
    unknown = df[df["external_group"].eq("EXTERN_UNBEKANNT_TOP")].copy()
    unknown = add_scores(unknown)
    unknown = unknown.sort_values("shortlist_score", ascending=False)

    csv_dir = args.out / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)

    result_csv = csv_dir / "level3_neue_planetenkandidaten.csv"
    unknown.to_csv(result_csv, index=False)

    for group, group_df in unknown.groupby("shortlist_group", dropna=False):
        prefix = GROUP_DIRS.get(group, "99_SONSTIGE").split("_", 1)[0]
        group_df.to_csv(csv_dir / f"{prefix}_{group}.csv", index=False)

    summary = unknown.groupby("shortlist_group").size().reset_index(name="count")
    summary = summary.sort_values("shortlist_group")
    summary.to_csv(csv_dir / "level3_summary.csv", index=False)

    export_plots(unknown, args.out)

    readme = args.out / "README.md"
    readme.write_text(
        "# Level 3 neue Planetenkandidaten\n\n"
        "Diese Sortierung enthaelt nur Kandidaten, die in der externen Katalogpruefung nicht als TOI, ExoFOP-Treffer oder bestaetigter Planet gefunden wurden.\n\n"
        "Stufen:\n"
        "- level3_01_PRIME_NEU_A: strengste automatische Auswahl, Level-2 A, K-Zwerg, saubere Form, >=3 Transits.\n"
        "- level3_02_STARK_NEU_B: sehr gute unbekannte Kandidaten, aber nicht Level-2 A.\n"
        "- level3_03_LANGPERIODE_2_TRANSITS: lange Perioden mit nur zwei Transits; visuell wichtig, statistisch vorsichtig.\n"
        "- level3_04_VISUELL_NACHPRUEFEN: brauchbare Faelle, aber weniger hart.\n"
        "- level3_05_AUSSORTIERT_STRIKT: faellt durch mindestens einen strengen Filter.\n\n"
        "Das ist eine Priorisierung, keine Planet-Bestaetigung.\n",
        encoding="utf-8",
    )

    print(f"Input extern unbekannt top: {len(unknown)}")
    print(f"Level-3 Ergebnis: {result_csv}")
    print(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
