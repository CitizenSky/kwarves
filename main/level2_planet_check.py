#!/usr/bin/env python3
"""Level-2 vetting: check whether database candidates are planet-plausible.

This is not a validation claim. The script creates a reproducible local
screening table and folders for manual review. TTV is deliberately ignored here.
"""

from __future__ import annotations

import argparse
import csv
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path("/Users/koni/astro_projects")
DB_PATH = PROJECT_ROOT / "database" / "planet_hunter.db"
LIGHTCURVE_ROOT = PROJECT_ROOT / "lightcurves"
REFERENCE_PLOTS = PROJECT_ROOT / "level1_rohkandidaten" / "level1_alle_kandidaten_referenzplots"
OUT_ROOT = PROJECT_ROOT / "level2_planetencheck"


@dataclass(frozen=True)
class Candidate:
    tic: int
    gaia_id: str | None
    hz_status: str
    is_fp: int
    teff: float | None
    distance_ly: float | None
    stellar_radius: float | None
    stellar_logg: float | None
    period: float
    duration: float
    depth: float
    t0: float
    planet_radius: float | None
    transit_snr: float
    transit_count: int
    n_in_transit: int
    duration_fraction: float | None
    oe_ratio: float | None
    sec_ratio: float | None
    fp_oe_flag: int
    fp_sec_flag: int
    fp_baseline_flag: int
    fp_baseline_std_flag: int
    fp_scatter_flag: int
    baseline_delta: float | None
    baseline_std_delta: float | None
    oot_scatter_ratio: float | None
    lightcurve_dir: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Level-2 planet plausibility checks.")
    parser.add_argument("--tic", type=int, default=None, help="Check one TIC only.")
    parser.add_argument(
        "--source",
        default="priority",
        choices=["priority", "all"],
        help="priority = likely useful candidates first; all = all database candidates.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of candidates.")
    parser.add_argument("--overwrite", action="store_true", help="Recreate category folders.")
    return parser.parse_args()


def load_candidates(args: argparse.Namespace) -> list[Candidate]:
    sql = """
    SELECT
      TIC, gaia_id, COALESCE(hz_status, 'UNKNOWN') AS hz_status, COALESCE(is_fp, 0) AS is_fp,
      teff, distance_ly, stellar_radius, stellar_logg,
      best_period, duration, depth, transit_time, planet_radius_earth,
      COALESCE(transit_snr, 0) AS transit_snr,
      COALESCE(transit_count, 0) AS transit_count,
      COALESCE(n_in_transit, 0) AS n_in_transit,
      duration_fraction, oe_ratio, sec_ratio,
      COALESCE(fp_oe_flag, 0) AS fp_oe_flag,
      COALESCE(fp_sec_flag, 0) AS fp_sec_flag,
      COALESCE(fp_baseline_flag, 0) AS fp_baseline_flag,
      COALESCE(fp_baseline_std_flag, 0) AS fp_baseline_std_flag,
      COALESCE(fp_scatter_flag, 0) AS fp_scatter_flag,
      baseline_delta, baseline_std_delta, oot_scatter_ratio,
      lightcurve_dir
    FROM candidates_v2
    WHERE best_period IS NOT NULL
      AND duration IS NOT NULL
      AND depth IS NOT NULL
      AND transit_time IS NOT NULL
    """
    params: list[object] = []
    if args.tic is not None:
        sql += " AND TIC = ?"
        params.append(args.tic)
    elif args.source == "priority":
        sql += """
        AND (
          COALESCE(is_fp, 0) = 0
          OR hz_status IN ('KONSERVATIVE_HZ','OPT_HZ_INNEN','OPT_HZ_AUSSEN')
          OR COALESCE(transit_snr, 0) >= 20
        )
        """
    sql += """
    ORDER BY
      COALESCE(is_fp, 0),
      COALESCE(transit_snr, 0) DESC,
      COALESCE(transit_count, 0) DESC,
      TIC
    """
    if args.limit is not None:
        sql += " LIMIT ?"
        params.append(args.limit)

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    return [
        Candidate(
            tic=int(r["TIC"]),
            gaia_id=r["gaia_id"],
            hz_status=r["hz_status"],
            is_fp=int(r["is_fp"]),
            teff=maybe_float(r["teff"]),
            distance_ly=maybe_float(r["distance_ly"]),
            stellar_radius=maybe_float(r["stellar_radius"]),
            stellar_logg=maybe_float(r["stellar_logg"]),
            period=float(r["best_period"]),
            duration=float(r["duration"]),
            depth=float(r["depth"]),
            t0=float(r["transit_time"]),
            planet_radius=maybe_float(r["planet_radius_earth"]),
            transit_snr=float(r["transit_snr"]),
            transit_count=int(r["transit_count"]),
            n_in_transit=int(r["n_in_transit"]),
            duration_fraction=maybe_float(r["duration_fraction"]),
            oe_ratio=maybe_float(r["oe_ratio"]),
            sec_ratio=maybe_float(r["sec_ratio"]),
            fp_oe_flag=int(r["fp_oe_flag"]),
            fp_sec_flag=int(r["fp_sec_flag"]),
            fp_baseline_flag=int(r["fp_baseline_flag"]),
            fp_baseline_std_flag=int(r["fp_baseline_std_flag"]),
            fp_scatter_flag=int(r["fp_scatter_flag"]),
            baseline_delta=maybe_float(r["baseline_delta"]),
            baseline_std_delta=maybe_float(r["baseline_std_delta"]),
            oot_scatter_ratio=maybe_float(r["oot_scatter_ratio"]),
            lightcurve_dir=r["lightcurve_dir"],
        )
        for r in rows
    ]


def maybe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except Exception:
        return None
    return v if np.isfinite(v) else None


def lightcurve_path(candidate: Candidate) -> Path:
    if candidate.lightcurve_dir:
        path = Path(candidate.lightcurve_dir)
        if path.exists():
            return path
    return LIGHTCURVE_ROOT / f"TIC_{candidate.tic}" / f"TIC_{candidate.tic}_lightcurve.csv"


def reference_plot_path(tic: int) -> str:
    matches = sorted(REFERENCE_PLOTS.glob(f"TIC_{tic}_*.png"))
    return str(matches[0]) if matches else ""


def load_lightcurve(candidate: Candidate) -> tuple[np.ndarray, np.ndarray]:
    data = np.genfromtxt(lightcurve_path(candidate), delimiter=",", names=True, dtype=float)
    time = np.asarray(data["time"], dtype=float)
    flux = np.asarray(data["flux"], dtype=float)
    mask = np.isfinite(time) & np.isfinite(flux)
    time, flux = time[mask], flux[mask]
    if len(time) < 20:
        raise ValueError("too few lightcurve points")
    med = np.nanmedian(flux)
    std = np.nanstd(flux)
    if np.isfinite(std) and std > 0:
        keep = np.abs(flux - med) < 7.0 * std
        time, flux = time[keep], flux[keep]
    med = np.nanmedian(flux)
    if np.isfinite(med) and abs(med) > 1e-8:
        flux = flux / med
    else:
        flux = flux - med + 1.0
    return time, flux


def centered_phase_days(time: np.ndarray, period: float, t0: float) -> np.ndarray:
    return ((time - t0 + period / 2.0) % period) - period / 2.0


def robust_scatter(values: np.ndarray) -> float:
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return float("nan")
    med = np.nanmedian(values)
    mad = np.nanmedian(np.abs(values - med))
    if np.isfinite(mad) and mad > 0:
        return float(1.4826 * mad)
    return float(np.nanstd(values))


def measure_shape(candidate: Candidate) -> dict[str, float | int | str]:
    time, flux = load_lightcurve(candidate)
    phase = centered_phase_days(time, candidate.period, candidate.t0)
    half_duration = candidate.duration / 2.0

    in_transit = np.abs(phase) <= half_duration
    near_left = (phase >= -3.0 * candidate.duration) & (phase <= -1.25 * candidate.duration)
    near_right = (phase >= 1.25 * candidate.duration) & (phase <= 3.0 * candidate.duration)
    oot = np.abs(phase) >= 2.0 * candidate.duration

    n_in = int(np.count_nonzero(in_transit))
    n_oot = int(np.count_nonzero(oot))
    if n_in < 3 or n_oot < 10:
        return {
            "shape_status": "INSUFFICIENT_POINTS",
            "measured_depth_ppt": float("nan"),
            "shape_snr": float("nan"),
            "secondary_depth_ppt": float("nan"),
            "secondary_ratio_measured": float("nan"),
            "baseline_left_right_delta_ppt": float("nan"),
            "oot_scatter_ppt": float("nan"),
            "n_shape_in": n_in,
            "n_shape_oot": n_oot,
        }

    base_med = np.nanmedian(flux[oot])
    in_med = np.nanmedian(flux[in_transit])
    depth = max(0.0, base_med - in_med)
    oot_scatter = robust_scatter((flux[oot] - np.nanmedian(flux[oot])) * 1000.0)
    shape_snr = depth * 1000.0 / oot_scatter * math.sqrt(n_in) if oot_scatter > 0 else float("nan")

    sec_phase = centered_phase_days(time, candidate.period, candidate.t0 + candidate.period / 2.0)
    sec_in = np.abs(sec_phase) <= half_duration
    sec_depth = max(0.0, base_med - np.nanmedian(flux[sec_in])) if np.any(sec_in) else float("nan")
    sec_ratio = sec_depth / depth if depth > 0 else float("nan")

    left_med = np.nanmedian(flux[near_left]) if np.any(near_left) else float("nan")
    right_med = np.nanmedian(flux[near_right]) if np.any(near_right) else float("nan")
    baseline_delta = abs(left_med - right_med) * 1000.0 if np.isfinite(left_med) and np.isfinite(right_med) else float("nan")

    status = "OK"
    if not np.isfinite(shape_snr) or shape_snr < 4.0:
        status = "WEAK_SHAPE"
    elif np.isfinite(sec_ratio) and sec_ratio > 0.65:
        status = "SECONDARY_LIKE"
    elif np.isfinite(baseline_delta) and baseline_delta > max(1.5 * depth * 1000.0, 1.5):
        status = "BASELINE_ASYMMETRY"

    return {
        "shape_status": status,
        "measured_depth_ppt": depth * 1000.0,
        "shape_snr": shape_snr,
        "secondary_depth_ppt": sec_depth * 1000.0 if np.isfinite(sec_depth) else float("nan"),
        "secondary_ratio_measured": sec_ratio,
        "baseline_left_right_delta_ppt": baseline_delta,
        "oot_scatter_ppt": oot_scatter,
        "n_shape_in": n_in,
        "n_shape_oot": n_oot,
    }


def fp_flag_count(candidate: Candidate) -> int:
    return (
        candidate.fp_oe_flag
        + candidate.fp_sec_flag
        + candidate.fp_baseline_flag
        + candidate.fp_baseline_std_flag
        + candidate.fp_scatter_flag
    )


def classify(candidate: Candidate, metrics: dict[str, object]) -> tuple[str, float, str]:
    reasons: list[str] = []
    score = 0.0

    shape_snr = float(metrics.get("shape_snr", float("nan")))
    shape_status = str(metrics.get("shape_status", "UNKNOWN"))
    sec_ratio = float(metrics.get("secondary_ratio_measured", float("nan")))
    baseline_delta = float(metrics.get("baseline_left_right_delta_ppt", float("nan")))

    if candidate.is_fp:
        score -= 35
        reasons.append("pipeline_is_fp")
    flags = fp_flag_count(candidate)
    score -= 12 * flags
    if flags:
        reasons.append(f"fp_flags={flags}")

    score += min(candidate.transit_snr, 60.0) * 0.8
    score += min(candidate.transit_count, 20) * 1.2
    if np.isfinite(shape_snr):
        score += min(shape_snr, 40.0) * 0.9
    else:
        reasons.append("shape_snr_nan")

    if candidate.planet_radius is None or candidate.planet_radius <= 0:
        score -= 10
        reasons.append("radius_missing")
    elif candidate.planet_radius <= 4.0:
        score += 10
    elif candidate.planet_radius <= 6.0:
        score -= 5
        reasons.append("large_radius")
    else:
        score -= 20
        reasons.append("too_large_radius")

    if candidate.stellar_logg is not None and candidate.stellar_logg >= 4.2:
        score += 6
    else:
        score -= 8
        reasons.append("dwarf_not_secure")

    if shape_status == "OK":
        score += 12
    else:
        score -= 14
        reasons.append(shape_status.lower())

    if np.isfinite(sec_ratio) and sec_ratio > 0.65:
        score -= 25
        reasons.append("secondary_like")
    if np.isfinite(baseline_delta) and baseline_delta > 3.0:
        score -= 8
        reasons.append("baseline_delta")

    if candidate.hz_status in {"KONSERVATIVE_HZ", "OPT_HZ_INNEN", "OPT_HZ_AUSSEN"}:
        score += 5

    if candidate.is_fp or flags >= 2 or shape_status in {"SECONDARY_LIKE", "BASELINE_ASYMMETRY"}:
        label = "FP_ODER_SYSTEMATIK"
    elif score >= 65:
        label = "PLANET_PLAUSIBEL_A"
    elif score >= 42:
        label = "PLANET_MOEGLICH_B"
    elif score >= 20:
        label = "UNSICHER"
    else:
        label = "WAHRSCHEINLICH_KEIN_PLANET"

    return label, round(score, 3), ";".join(reasons) if reasons else "ok"


def clean_output_dirs(overwrite: bool) -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    for name in [
        "level2_01_PLANET_PLAUSIBEL_A",
        "level2_02_PLANET_MOEGLICH_B",
        "level2_03_UNSICHER",
        "level2_04_FP_ODER_SYSTEMATIK",
        "level2_05_WAHRSCHEINLICH_KEIN_PLANET",
    ]:
        path = OUT_ROOT / name
        path.mkdir(parents=True, exist_ok=True)
        if overwrite:
            for item in path.glob("*"):
                if item.is_file():
                    item.unlink()


def category_folder(label: str) -> Path:
    mapping = {
        "PLANET_PLAUSIBEL_A": "level2_01_PLANET_PLAUSIBEL_A",
        "PLANET_MOEGLICH_B": "level2_02_PLANET_MOEGLICH_B",
        "UNSICHER": "level2_03_UNSICHER",
        "FP_ODER_SYSTEMATIK": "level2_04_FP_ODER_SYSTEMATIK",
        "WAHRSCHEINLICH_KEIN_PLANET": "level2_05_WAHRSCHEINLICH_KEIN_PLANET",
    }
    return OUT_ROOT / mapping[label]


def link_reference_plot(tic: int, label: str, rank: int) -> str:
    src_text = reference_plot_path(tic)
    if not src_text:
        return ""
    src = Path(src_text)
    dst = category_folder(label) / f"{rank:04d}_{src.name}"
    if dst.exists():
        return str(dst)
    try:
        dst.hardlink_to(src)
    except Exception:
        import shutil

        shutil.copy2(src, dst)
    return str(dst)


def write_readme() -> None:
    (OUT_ROOT / "README.md").write_text(
        "# Level 2 Planetencheck\n\n"
        "Dieses Ergebnis prueft nur, ob ein Kandidat planetenplausibel ist.\n"
        "TTV und weitere Planeten werden hier nicht interpretiert.\n\n"
        "## Kategorien\n\n"
        "- `level2_01_PLANET_PLAUSIBEL_A`: starke planetenartige Kandidaten.\n"
        "- `level2_02_PLANET_MOEGLICH_B`: moegliche Kandidaten, brauchen manuelle Pruefung.\n"
        "- `level2_03_UNSICHER`: nicht genug Vertrauen.\n"
        "- `level2_04_FP_ODER_SYSTEMATIK`: False-Positive/Systematik-Verdacht.\n"
        "- `level2_05_WAHRSCHEINLICH_KEIN_PLANET`: schwache oder unplausible Faelle.\n\n"
        "Die automatische Klasse ist eine Vorsortierung, keine Bestaetigung.\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    clean_output_dirs(args.overwrite)
    write_readme()
    candidates = load_candidates(args)
    print(f"Kandidaten: {len(candidates)} | source={args.source}", flush=True)

    rows: list[dict[str, object]] = []
    for idx, candidate in enumerate(candidates, start=1):
        try:
            metrics = measure_shape(candidate)
            label, score, reason = classify(candidate, metrics)
            status = "ok"
        except Exception as exc:
            metrics = {}
            label, score, reason = "UNSICHER", -999.0, f"{type(exc).__name__}: {exc}"
            status = "error"

        row = {
            "TIC": candidate.tic,
            "level2_planet_label": label,
            "level2_planet_score": score,
            "level2_reason": reason,
            "status": status,
            "hz_status": candidate.hz_status,
            "is_fp": candidate.is_fp,
            "fp_flag_count": fp_flag_count(candidate),
            "period": candidate.period,
            "duration": candidate.duration,
            "depth": candidate.depth,
            "planet_radius_earth": candidate.planet_radius,
            "transit_snr": candidate.transit_snr,
            "transit_count": candidate.transit_count,
            "stellar_logg": candidate.stellar_logg,
            "teff": candidate.teff,
            "distance_ly": candidate.distance_ly,
            "reference_plot": reference_plot_path(candidate.tic),
            **metrics,
        }
        rows.append(row)
        print(f"{idx}/{len(candidates)} TIC {candidate.tic}: {label} score={score}", flush=True)

    rows.sort(key=lambda r: (str(r["level2_planet_label"]), -float(r["level2_planet_score"])))
    for rank, row in enumerate(rows, start=1):
        row["level2_rank"] = rank
        row["level2_folder_plot"] = link_reference_plot(
            int(row["TIC"]),
            str(row["level2_planet_label"]),
            rank,
        )

    fields = [
        "level2_rank",
        "TIC",
        "level2_planet_label",
        "level2_planet_score",
        "level2_reason",
        "status",
        "hz_status",
        "is_fp",
        "fp_flag_count",
        "period",
        "duration",
        "depth",
        "planet_radius_earth",
        "transit_snr",
        "transit_count",
        "stellar_logg",
        "teff",
        "distance_ly",
        "shape_status",
        "measured_depth_ppt",
        "shape_snr",
        "secondary_depth_ppt",
        "secondary_ratio_measured",
        "baseline_left_right_delta_ppt",
        "oot_scatter_ppt",
        "n_shape_in",
        "n_shape_oot",
        "reference_plot",
        "level2_folder_plot",
    ]
    out_csv = OUT_ROOT / "level2_planetencheck_results.csv"
    with out_csv.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    counts: dict[str, int] = {}
    for row in rows:
        label = str(row["level2_planet_label"])
        counts[label] = counts.get(label, 0) + 1
    print(f"Fertig: {out_csv}")
    print(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
