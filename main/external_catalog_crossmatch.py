#!/usr/bin/env python3
"""Cross-match local candidates against public exoplanet/TOI catalogs.

This script answers one practical question for our candidate list:
"Is this TIC already known outside our local search?"

Sources:
- NASA Exoplanet Archive TOI table, which mirrors TESS/ExoFOP TOI dispositions.
- NASA Exoplanet Archive Planetary Systems table for confirmed/known planets.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/koni/astro_projects")
LEVEL2_RESULTS = PROJECT_ROOT / "level2_planetencheck/level2_planetencheck_results.csv"
OUT_ROOT = PROJECT_ROOT / "level3_externe_katalogpruefung"
TAP_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"


TOI_QUERY = """
select tid,toi,ctoi_alias,tfopwg_disp,pl_orbper,pl_tranmid,pl_rade
from toi
where tid is not null
"""

PS_QUERY = """
select pl_name,hostname,tic_id,sy_dist,disc_facility,discoverymethod,pl_orbper,pl_rade
from ps
where tic_id is not null
"""


GROUP_DIRS = {
    "SCHON_BEKANNTER_PLANET": "level3_01_SCHON_BEKANNTER_PLANET",
    "EXOFOP_TOI_PLANET_CANDIDATE": "level3_02_EXOFOP_TOI_PLANET_CANDIDATE",
    "EXOFOP_TOI_FALSE_POSITIVE": "level3_03_EXOFOP_TOI_FALSE_POSITIVE",
    "EXTERN_UNBEKANNT_TOP": "level3_04_EXTERN_UNBEKANNT_TOP",
    "EXTERN_UNBEKANNT_REST": "level3_05_EXTERN_UNBEKANNT_REST",
    "EXTERN_MATCH_ANDERE": "level3_06_EXTERN_MATCH_ANDERE",
}


def log(message: str) -> None:
    print(message, flush=True)


def run_tap_csv(query: str, cache_file: Path, *, refresh: bool, retries: int = 4) -> pd.DataFrame:
    """Fetch a TAP CSV query via curl with retry and cache it locally."""
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    if cache_file.exists() and not refresh:
        return pd.read_csv(cache_file)

    last_error = None
    for attempt in range(1, retries + 1):
        log(f"Download {cache_file.name} Versuch {attempt}/{retries} ...")
        cmd = [
            "curl",
            "-G",
            "-L",
            "-sS",
            "--fail",
            "--max-time",
            "120",
            TAP_URL,
            "--data-urlencode",
            f"query={query.strip()}",
            "--data-urlencode",
            "format=csv",
        ]
        try:
            completed = subprocess.run(cmd, check=True, capture_output=True, text=True)
            text = completed.stdout.strip()
            if not text or "\n" not in text:
                raise RuntimeError(f"Leere oder unvollstaendige Antwort: {text[:200]!r}")
            df = pd.read_csv(io.StringIO(text))
            df.to_csv(cache_file, index=False)
            return df
        except Exception as exc:  # curl/network failures are common enough to retry.
            last_error = exc
            time.sleep(3 * attempt)

    raise RuntimeError(f"Konnte {cache_file.name} nicht laden: {last_error}")


def tic_number_from_ps(value: object) -> int | None:
    if pd.isna(value):
        return None
    text = str(value).strip().replace("TIC", "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def norm_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def join_unique(values: pd.Series, limit: int = 8) -> str:
    items: list[str] = []
    for value in values:
        text = norm_text(value)
        if text and text not in items:
            items.append(text)
    if len(items) > limit:
        return ";".join(items[:limit]) + f";+{len(items)-limit} mehr"
    return ";".join(items)


def summarize_catalogs(toi: pd.DataFrame, ps: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    toi = toi.copy()
    ps = ps.copy()

    toi["TIC"] = pd.to_numeric(toi["tid"], errors="coerce").astype("Int64")
    toi_summary = (
        toi.dropna(subset=["TIC"])
        .groupby("TIC", dropna=True)
        .agg(
            exofop_toi_count=("toi", "count"),
            exofop_toi_ids=("toi", join_unique),
            exofop_ctoi_aliases=("ctoi_alias", join_unique),
            exofop_dispositions=("tfopwg_disp", join_unique),
            exofop_periods_d=("pl_orbper", lambda s: join_unique(s.map(lambda x: f"{x:.6g}" if pd.notna(x) else ""))),
            exofop_radii_re=("pl_rade", lambda s: join_unique(s.map(lambda x: f"{x:.4g}" if pd.notna(x) else ""))),
        )
        .reset_index()
    )
    toi_summary["TIC"] = toi_summary["TIC"].astype(int)

    ps["TIC"] = ps["tic_id"].map(tic_number_from_ps)
    ps_summary = (
        ps.dropna(subset=["TIC"])
        .groupby("TIC", dropna=True)
        .agg(
            confirmed_planet_count=("pl_name", "count"),
            confirmed_planet_names=("pl_name", join_unique),
            confirmed_hosts=("hostname", join_unique),
            discovery_facilities=("disc_facility", join_unique),
            discovery_methods=("discoverymethod", join_unique),
            confirmed_periods_d=("pl_orbper", lambda s: join_unique(s.map(lambda x: f"{x:.6g}" if pd.notna(x) else ""))),
            confirmed_radii_re=("pl_rade", lambda s: join_unique(s.map(lambda x: f"{x:.4g}" if pd.notna(x) else ""))),
        )
        .reset_index()
    )
    ps_summary["TIC"] = ps_summary["TIC"].astype(int)
    return toi_summary, ps_summary


def classify(row: pd.Series) -> str:
    if int(row.get("confirmed_planet_count", 0) or 0) > 0:
        return "SCHON_BEKANNTER_PLANET"

    dispositions = {x.strip().upper() for x in norm_text(row.get("exofop_dispositions")).split(";") if x.strip()}
    if dispositions & {"CP", "KP"}:
        return "SCHON_BEKANNTER_PLANET"
    if dispositions & {"PC", "APC"}:
        return "EXOFOP_TOI_PLANET_CANDIDATE"
    if dispositions & {"FP", "FA"}:
        return "EXOFOP_TOI_FALSE_POSITIVE"
    if int(row.get("exofop_toi_count", 0) or 0) > 0:
        return "EXTERN_MATCH_ANDERE"

    if row.get("level2_planet_label") in {"PLANET_PLAUSIBEL_A", "PLANET_MOEGLICH_B"}:
        return "EXTERN_UNBEKANNT_TOP"
    return "EXTERN_UNBEKANNT_REST"


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


def export_plot_groups(df: pd.DataFrame, out_root: Path) -> None:
    for dirname in GROUP_DIRS.values():
        (out_root / dirname).mkdir(parents=True, exist_ok=True)

    ranked = df.sort_values(
        ["external_sort", "level2_planet_score", "transit_snr"],
        ascending=[True, False, False],
        na_position="last",
    )
    counters = {key: 0 for key in GROUP_DIRS}
    for _, row in ranked.iterrows():
        group = row["external_group"]
        src_text = norm_text(row.get("level2_folder_plot")) or norm_text(row.get("reference_plot"))
        if not src_text:
            continue
        src = Path(src_text)
        if not src.exists():
            continue
        counters[group] = counters.get(group, 0) + 1
        tic = int(row["TIC"])
        dst_name = f"{counters[group]:04d}_TIC_{tic}_{src.name}"
        link_or_copy(src, out_root / GROUP_DIRS[group] / dst_name)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sort candidates by external ExoFOP/NASA catalog matches.")
    parser.add_argument("--level2", type=Path, default=LEVEL2_RESULTS, help="Level-2 planet check CSV")
    parser.add_argument("--out", type=Path, default=OUT_ROOT, help="Output folder")
    parser.add_argument("--refresh", action="store_true", help="Force fresh downloads from NASA Exoplanet Archive")
    args = parser.parse_args()

    if not args.level2.exists():
        raise FileNotFoundError(args.level2)

    args.out.mkdir(parents=True, exist_ok=True)
    cache_dir = args.out / "level3_00_externe_catalog_cache"

    log("Lade lokale Level-2 Kandidaten ...")
    local = pd.read_csv(args.level2)
    local["TIC"] = pd.to_numeric(local["TIC"], errors="coerce").astype("Int64")
    local = local.dropna(subset=["TIC"]).copy()
    local["TIC"] = local["TIC"].astype(int)

    toi = run_tap_csv(TOI_QUERY, cache_dir / "nasa_exoplanet_archive_toi.csv", refresh=args.refresh)
    ps = run_tap_csv(PS_QUERY, cache_dir / "nasa_exoplanet_archive_confirmed_planets.csv", refresh=args.refresh)

    log("Fasse externe Treffer pro TIC zusammen ...")
    toi_summary, ps_summary = summarize_catalogs(toi, ps)
    merged = local.merge(toi_summary, on="TIC", how="left").merge(ps_summary, on="TIC", how="left")

    count_cols = ["exofop_toi_count", "confirmed_planet_count"]
    for col in count_cols:
        merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0).astype(int)

    text_cols = [
        "exofop_toi_ids",
        "exofop_ctoi_aliases",
        "exofop_dispositions",
        "exofop_periods_d",
        "exofop_radii_re",
        "confirmed_planet_names",
        "confirmed_hosts",
        "discovery_facilities",
        "discovery_methods",
        "confirmed_periods_d",
        "confirmed_radii_re",
    ]
    for col in text_cols:
        if col not in merged:
            merged[col] = ""
        merged[col] = merged[col].fillna("")

    merged["external_group"] = merged.apply(classify, axis=1)
    order = {
        "SCHON_BEKANNTER_PLANET": 1,
        "EXOFOP_TOI_PLANET_CANDIDATE": 2,
        "EXOFOP_TOI_FALSE_POSITIVE": 3,
        "EXTERN_UNBEKANNT_TOP": 4,
        "EXTERN_UNBEKANNT_REST": 5,
        "EXTERN_MATCH_ANDERE": 6,
    }
    merged["external_sort"] = merged["external_group"].map(order).fillna(99).astype(int)
    merged["external_match_any"] = (
        (merged["exofop_toi_count"] > 0) | (merged["confirmed_planet_count"] > 0)
    )

    sort_cols = ["external_sort", "level2_planet_score", "transit_snr"]
    merged = merged.sort_values(sort_cols, ascending=[True, False, False], na_position="last")

    result_csv = args.out / "external_catalog_crossmatch_results.csv"
    merged.to_csv(result_csv, index=False, quoting=csv.QUOTE_MINIMAL)

    for group, group_df in merged.groupby("external_group", dropna=False):
        filename = f"{order.get(group, 99):02d}_{group}.csv"
        group_df.to_csv(args.out / filename, index=False)

    log("Sortiere Referenzgrafiken in externe Kataloggruppen ...")
    export_plot_groups(merged, args.out)

    summary = (
        merged.groupby("external_group")
        .size()
        .reset_index(name="count")
        .sort_values("external_group")
    )
    summary.to_csv(args.out / "external_catalog_summary.csv", index=False)

    log("")
    log("Fertig.")
    log(f"Ergebnis CSV: {result_csv}")
    log(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
