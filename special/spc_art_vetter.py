#!/usr/bin/env python3
"""
SPC_ART TESS candidate vetting helper.

Runs the high-information tests for long-period BY-Draconis-like false positives:

1. Sector-wise detrending for SAP and PDCSAP
2. Lomb-Scargle stellar rotation search
3. Autocorrelation Function rotation search
4. TLS search, with BLS fallback/comparison
5. Odd/even event checks
6. Raw phase-fold diagnostic without binning
7. Transit-duration plausibility estimate
8. Transit injection/recovery
9. Aperture sweep from TESS target pixel files
10. Pixel-level difference image

Examples:
    python spc_art_vetter.py --tic 123456789 --period 100.605 --duration 0.195
    python spc_art_vetter.py --tic 123456789 --period 100.605 --duration 0.195 --sectors 14 15 21
"""

from __future__ import annotations

import argparse
import json
import math
import warnings
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
from astropy.timeseries import BoxLeastSquares, LombScargle

try:
    import lightkurve as lk
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: lightkurve. Install with:\n"
        "  python -m pip install lightkurve astropy scipy matplotlib numpy\n"
    ) from exc

try:
    from scipy.signal import correlate, find_peaks
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Missing dependency: scipy. Install with: python -m pip install scipy") from exc

try:
    from transitleastsquares import transitleastsquares
except ImportError:  # pragma: no cover
    transitleastsquares = None


R_SUN_AU = 0.00465047
DEFAULT_REVIEW_ROOT = Path("/Users/koni/astro_projects/level4_TTV_analyse")


@dataclass
class SearchResult:
    method: str
    period_days: float | None
    sde_or_power: float | None
    duration_days: float | None
    depth: float | None
    note: str = ""


@dataclass
class OddEvenResult:
    odd_depth: float | None
    even_depth: float | None
    odd_even_sigma: float | None
    n_odd: int
    n_even: int


def lightkurve_precheck(tic: str, outdir: Path | None = None):
    target = tess_target_name(tic)
    search = lk.search_lightcurve(target, mission="TESS")
    print("\n=== Lightkurve precheck: available TESS light curves ===")
    print(search)

    rows = []
    try:
        table = search.table
        for row in table:
            rows.append(
                {
                    "mission": str(row["mission"]),
                    "year": int(row["year"]) if "year" in table.colnames else None,
                    "author": str(row["author"]),
                    "exptime": float(row["exptime"]) if "exptime" in table.colnames else None,
                    "target_name": str(row["target_name"]),
                    "distance_arcsec": float(row["distance"]) if "distance" in table.colnames else None,
                }
            )
    except Exception as exc:
        rows.append({"error": f"could not summarize search table: {exc}"})

    summary = {}
    for row in rows:
        if "error" in row:
            continue
        key = (row["author"], row["exptime"])
        summary.setdefault(key, set()).add(row["mission"])

    print("\nPrecheck summary by author/exptime:")
    for (author, exptime), missions in sorted(summary.items(), key=lambda x: (x[0][0], x[0][1] or 0)):
        print(f"  {author:9s} exptime={exptime:g}s products={len(missions):2d} sectors={', '.join(sorted(missions))}")

    if outdir is not None:
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "lightkurve_precheck.txt").write_text(str(search) + "\n", encoding="utf-8")
        (outdir / "lightkurve_precheck.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return search, rows


def clean_tic_id(tic: str) -> str:
    return tic.upper().replace("TIC", "").replace("_", " ").strip()


def tess_target_name(tic: str) -> str:
    return f"TIC {clean_tic_id(tic)}"


def tic_slug(tic: str) -> str:
    return f"TIC_{clean_tic_id(tic)}"


def default_output_dir(tic: str) -> Path:
    return DEFAULT_REVIEW_ROOT / f"{tic_slug(tic)}_spc_art_vetting_{date.today().isoformat()}"


def finite_arrays(time: np.ndarray, flux: np.ndarray, err: np.ndarray | None = None):
    mask = np.isfinite(time) & np.isfinite(flux)
    if err is not None:
        mask &= np.isfinite(err) & (err > 0)
        return time[mask], flux[mask], err[mask]
    return time[mask], flux[mask]


def normalize_flux(flux: np.ndarray) -> np.ndarray:
    med = np.nanmedian(flux)
    if not np.isfinite(med) or med == 0:
        return flux
    return flux / med


def robust_sigma(x: np.ndarray) -> float:
    med = np.nanmedian(x)
    mad = np.nanmedian(np.abs(x - med))
    return 1.4826 * mad if np.isfinite(mad) and mad > 0 else float(np.nanstd(x))


def search_lightcurves(tic: str, sectors: list[int] | None, exptime: int | None = None):
    target = tess_target_name(tic)
    kwargs = {"mission": "TESS", "author": "SPOC"}
    if sectors:
        kwargs["sector"] = sectors
    if exptime:
        kwargs["exptime"] = exptime
    return lk.search_lightcurve(target, **kwargs)


def download_and_flatten(
    tic: str,
    sectors: list[int] | None,
    flux_column: str,
    windows: Iterable[int],
    exptime: int | None = None,
):
    search = search_lightcurves(tic, sectors, exptime)
    if len(search) == 0:
        raise RuntimeError(f"No SPOC TESS light curves found for TIC {tic}.")

    stitched_by_window = {}
    sector_curves = {}
    for wl in windows:
        flattened = []
        per_sector = []
        for sr in search:
            lc = sr.download(flux_column=flux_column)
            if lc is None or len(lc.time) == 0:
                continue
            sector = lc.sector
            lc = lc.remove_nans().normalize()
            lc = lc.remove_outliers(sigma=8)
            # Window length must be odd for Lightkurve flatten.
            win = int(wl)
            if win % 2 == 0:
                win += 1
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                flat = lc.flatten(window_length=win, break_tolerance=5, niters=3)
            flat.meta["SECTOR"] = sector
            flattened.append(flat)
            per_sector.append(flat)
        if flattened:
            stitched_by_window[wl] = lk.LightCurveCollection(flattened).stitch().remove_nans()
            sector_curves[wl] = per_sector
    return stitched_by_window, sector_curves


def download_rotation_lightcurve(tic: str, sectors: list[int] | None, flux_column: str, exptime: int | None = None):
    search = search_lightcurves(tic, sectors, exptime)
    raw = []
    for sr in search:
        lc = sr.download(flux_column=flux_column)
        if lc is None or len(lc.time) == 0:
            continue
        lc = lc.remove_nans().normalize().remove_outliers(sigma=8)
        raw.append(lc)
    if not raw:
        return None
    return lk.LightCurveCollection(raw).stitch().remove_nans()


def as_arrays(lc):
    time = np.asarray(lc.time.value, dtype=float)
    flux = normalize_flux(np.asarray(lc.flux.value, dtype=float))
    if getattr(lc, "flux_err", None) is not None:
        err = np.asarray(lc.flux_err.value, dtype=float)
        err = err / np.nanmedian(np.asarray(lc.flux.value, dtype=float))
    else:
        err = np.full_like(flux, robust_sigma(flux))
    return finite_arrays(time, flux, err)


def lomb_scargle_rotation(time, flux, min_period=0.2, max_period=150.0) -> SearchResult:
    time, flux = finite_arrays(time, flux)
    y = flux - np.nanmedian(flux)
    frequency, power = LombScargle(time, y).autopower(
        minimum_frequency=1 / max_period,
        maximum_frequency=1 / min_period,
        samples_per_peak=10,
    )
    periods = 1 / frequency
    best = int(np.nanargmax(power))
    return SearchResult(
        method="Lomb-Scargle",
        period_days=float(periods[best]),
        sde_or_power=float(power[best]),
        duration_days=None,
        depth=None,
    )


def acf_rotation(time, flux, max_lag_days=150.0) -> SearchResult:
    time, flux = finite_arrays(time, flux)
    cadence = max(float(np.nanmedian(np.diff(np.sort(time)))), 0.05)
    if not np.isfinite(cadence) or cadence <= 0:
        return SearchResult("ACF", None, None, None, None, "invalid cadence")

    grid = np.arange(np.nanmin(time), np.nanmax(time), cadence)
    interp = np.interp(grid, time, flux)
    y = interp - np.nanmedian(interp)
    y /= np.nanstd(y) if np.nanstd(y) else 1.0
    acf = correlate(y, y, mode="full", method="fft")[len(y) - 1 :]
    acf /= acf[0] if acf[0] else 1.0
    lags = np.arange(len(acf)) * cadence

    mask = (lags > 0.5) & (lags < max_lag_days)
    peaks, props = find_peaks(acf[mask], distance=max(1, int(1.0 / cadence)), prominence=0.02)
    if len(peaks) == 0:
        return SearchResult("ACF", None, None, None, None, "no significant ACF peak")
    lag_subset = lags[mask]
    acf_subset = acf[mask]
    best = peaks[np.argmax(acf_subset[peaks])]
    return SearchResult("ACF", float(lag_subset[best]), float(acf_subset[best]), None, None)


def run_tls(time, flux, err, period_min=1.0, period_max=200.0, tls_threads=1) -> SearchResult:
    if transitleastsquares is None:
        return SearchResult("TLS", None, None, None, None, "transitleastsquares not installed")
    model = transitleastsquares(time, flux, dy=err)
    results = model.power(
        period_min=period_min,
        period_max=period_max,
        show_progress_bar=False,
        use_threads=tls_threads,
    )
    return SearchResult(
        method="TLS",
        period_days=float(results.period),
        sde_or_power=float(results.SDE),
        duration_days=float(results.duration),
        depth=float(results.depth),
    )


def run_bls(time, flux, period_min=1.0, period_max=200.0, duration_days=0.195) -> SearchResult:
    time, flux = finite_arrays(time, flux)
    periods = np.linspace(period_min, period_max, 20_000)
    durations = np.unique(
        np.clip(
            np.array([duration_days / 2, duration_days, duration_days * 2, 0.05, 0.1, 0.3]),
            0.03,
            1.5,
        )
    )
    bls = BoxLeastSquares(time, flux)
    power = bls.power(periods, durations)
    best = int(np.nanargmax(power.power))
    return SearchResult(
        method="BLS",
        period_days=float(power.period[best]),
        sde_or_power=float(power.power[best]),
        duration_days=float(power.duration[best]),
        depth=float(power.depth[best]),
    )


def phase(time, period, t0=0.0):
    return ((time - t0 + 0.5 * period) % period) / period - 0.5


def estimate_event_depths(time, flux, period, duration, t0=None):
    if t0 is None:
        t0 = estimate_t0(time, flux, period, duration)
    epochs = np.round((time - t0) / period).astype(int)
    depths = []
    for epoch in sorted(set(epochs)):
        center = t0 + epoch * period
        in_tr = np.abs(time - center) < duration / 2
        oot = (np.abs(time - center) > duration) & (np.abs(time - center) < duration * 3)
        if np.sum(in_tr) >= 3 and np.sum(oot) >= 6:
            depth = np.nanmedian(flux[oot]) - np.nanmedian(flux[in_tr])
            scatter = robust_sigma(flux[oot])
            depths.append((epoch, depth, scatter, int(np.sum(in_tr))))
    return depths, t0


def estimate_t0(time, flux, period, duration):
    phases = phase(time, period, 0.0)
    bins = np.linspace(-0.5, 0.5, 500)
    idx = np.digitize(phases, bins)
    med = np.array([np.nanmedian(flux[idx == i]) if np.any(idx == i) else np.nan for i in range(1, len(bins))])
    centers = 0.5 * (bins[:-1] + bins[1:])
    best_phase = centers[int(np.nanargmin(med))]
    return -best_phase * period


def odd_even_check(time, flux, period, duration, t0=None) -> OddEvenResult:
    depths, _ = estimate_event_depths(time, flux, period, duration, t0)
    odd = np.array([d[1] for d in depths if d[0] % 2])
    even = np.array([d[1] for d in depths if not d[0] % 2])
    if len(odd) == 0 or len(even) == 0:
        return OddEvenResult(None, None, None, len(odd), len(even))
    odd_depth = float(np.nanmedian(odd))
    even_depth = float(np.nanmedian(even))
    denom = math.sqrt((robust_sigma(odd) ** 2 / max(len(odd), 1)) + (robust_sigma(even) ** 2 / max(len(even), 1)))
    sigma = abs(odd_depth - even_depth) / denom if denom and np.isfinite(denom) else None
    return OddEvenResult(odd_depth, even_depth, float(sigma) if sigma is not None else None, len(odd), len(even))


def transit_duration_plausibility(period, duration, stellar_radius=1.0, stellar_mass=1.0):
    # Kepler's third law in convenient units: a/AU = (M * P_yr^2)^(1/3)
    p_yr = period / 365.25
    a_au = (stellar_mass * p_yr * p_yr) ** (1 / 3)
    r_au = stellar_radius * R_SUN_AU
    central_duration = period / math.pi * math.asin(min(1.0, r_au / a_au))
    ratio = duration / central_duration if central_duration > 0 else np.nan
    return {
        "a_au": a_au,
        "central_duration_days": central_duration,
        "observed_duration_days": duration,
        "observed_over_central": ratio,
        "note": "duration longer than central transit" if ratio > 1.3 else "duration plausible for central/near-central transit",
    }


def inject_box_transits(time, flux, period, duration, depth, t0=None):
    if t0 is None:
        t0 = estimate_t0(time, flux, period, duration)
    injected = np.array(flux, copy=True)
    ph = phase(time, period, t0)
    injected[np.abs(ph * period) < duration / 2] -= depth
    return injected, t0


def harmonic_flags(rotation_periods, candidate_period, tolerance=0.03):
    flags = []
    for label, rot in rotation_periods:
        if rot is None or not np.isfinite(rot):
            continue
        for n in [1, 2, 3, 4]:
            ratio = candidate_period / (rot * n)
            if abs(ratio - 1) < tolerance:
                flags.append(f"{label}: candidate period ~= {n} x rotation ({rot:.3f} d)")
        for div in [2, 3, 4]:
            ratio = candidate_period / (rot / div)
            if abs(ratio - 1) < tolerance:
                flags.append(f"{label}: candidate period ~= rotation/{div} ({rot:.3f} d)")
    return flags


def plot_diagnostics(outdir, label, time, flux, period, duration, ls_result, acf_result, t0=None):
    outdir.mkdir(parents=True, exist_ok=True)
    if t0 is None:
        t0 = estimate_t0(time, flux, period, duration)
    ph = phase(time, period, t0)

    fig, axs = plt.subplots(3, 1, figsize=(10, 10), constrained_layout=True)
    axs[0].scatter(time, flux, s=2, c="black", alpha=0.45)
    axs[0].set_title(f"{label}: flattened light curve")
    axs[0].set_xlabel("Time [BTJD]")
    axs[0].set_ylabel("Normalized flux")

    axs[1].scatter(ph, flux, s=2, c="black", alpha=0.45)
    axs[1].axvspan(-duration / (2 * period), duration / (2 * period), color="tab:red", alpha=0.18)
    axs[1].set_xlim(-0.08, 0.08)
    axs[1].set_title(f"Raw phase fold, no binning, P={period:.6f} d")
    axs[1].set_xlabel("Phase")
    axs[1].set_ylabel("Normalized flux")

    txt = [
        f"LS rotation: {fmt_result(ls_result)}",
        f"ACF rotation: {fmt_result(acf_result)}",
    ]
    axs[2].axis("off")
    axs[2].text(0.02, 0.85, "\n".join(txt), va="top", family="monospace")
    fig.savefig(outdir / f"{label}_diagnostics.png", dpi=180)
    plt.close(fig)


def fmt_result(result: SearchResult) -> str:
    if result.period_days is None:
        return result.note or "no result"
    strength = "n/a" if result.sde_or_power is None else f"{result.sde_or_power:.3g}"
    duration = "" if result.duration_days is None else f", dur={result.duration_days:.4f} d"
    depth = "" if result.depth is None else f", depth={result.depth:.5g}"
    return f"P={result.period_days:.6f} d, strength={strength}{duration}{depth}"


def aperture_sweep(tic, sectors, period, duration, outdir, t0=None, exptime: int | None = None):
    target = tess_target_name(tic)
    kwargs = {"mission": "TESS", "author": "SPOC"}
    if sectors:
        kwargs["sector"] = sectors
    if exptime:
        kwargs["exptime"] = exptime
    search = lk.search_targetpixelfile(target, **kwargs)
    if len(search) == 0:
        return {"note": "no SPOC target pixel files found"}

    summaries = []
    for sr in search[: min(len(search), 4)]:
        tpf = sr.download()
        if tpf is None:
            continue
        masks = {
            "pipeline": tpf.pipeline_mask,
            "threshold_2": tpf.create_threshold_mask(threshold=2),
            "threshold_5": tpf.create_threshold_mask(threshold=5),
            "all_pixels": np.ones(tpf.shape[1:], dtype=bool),
        }
        for name, mask in masks.items():
            try:
                lc = tpf.to_lightcurve(aperture_mask=mask).remove_nans().normalize().flatten(window_length=401)
                time, flux, _ = as_arrays(lc)
                depths, _ = estimate_event_depths(time, flux, period, duration, t0)
                depth = float(np.nanmedian([d[1] for d in depths])) if depths else None
                summaries.append(
                    {
                        "sector": int(getattr(tpf, "sector", -1)),
                        "mask": name,
                        "pixels": int(np.sum(mask)),
                        "median_event_depth": depth,
                        "events": len(depths),
                    }
                )
            except Exception as exc:
                summaries.append({"sector": int(getattr(tpf, "sector", -1)), "mask": name, "error": str(exc)})

        try:
            make_difference_image(tpf, period, duration, outdir, t0)
        except Exception as exc:
            summaries.append({"sector": int(getattr(tpf, "sector", -1)), "difference_image_error": str(exc)})
    return summaries


def make_difference_image(tpf, period, duration, outdir, t0=None):
    lc = tpf.to_lightcurve(aperture_mask=tpf.pipeline_mask).remove_nans().normalize()
    time, flux, _ = as_arrays(lc)
    if t0 is None:
        t0 = estimate_t0(time, flux, period, duration)
    ph = phase(np.asarray(tpf.time.value, dtype=float), period, t0) * period
    in_tr = np.abs(ph) < duration / 2
    oot = (np.abs(ph) > duration * 1.5) & (np.abs(ph) < duration * 4)
    if np.sum(in_tr) < 1 or np.sum(oot) < 1:
        return
    in_img = np.nanmedian(np.asarray(tpf.flux[in_tr], dtype=float), axis=0)
    out_img = np.nanmedian(np.asarray(tpf.flux[oot], dtype=float), axis=0)
    diff = out_img - in_img

    fig, axs = plt.subplots(1, 3, figsize=(10, 3.5), constrained_layout=True)
    for ax, img, title in zip(axs, [out_img, in_img, diff], ["Out of transit", "In transit", "Out - In"]):
        im = ax.imshow(img, origin="lower", cmap="viridis")
        ax.contour(tpf.pipeline_mask, colors="white", linewidths=0.8)
        ax.set_title(title)
        fig.colorbar(im, ax=ax, fraction=0.046)
    outdir.mkdir(parents=True, exist_ok=True)
    fig.savefig(outdir / f"sector_{getattr(tpf, 'sector', 'unknown')}_difference_image.png", dpi=180)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Vet SPC_ART long-period TESS candidates.")
    parser.add_argument("--tic", required=True, help="TIC id, with or without 'TIC ' prefix")
    parser.add_argument("--period", type=float, required=True, help="Candidate period in days")
    parser.add_argument("--duration", type=float, required=True, help="Candidate duration in days")
    parser.add_argument("--t0", type=float, default=None, help="Optional transit epoch in the same time system as TESS light curves, usually BTJD")
    parser.add_argument("--depth", type=float, default=0.001, help="Injection depth in relative flux")
    parser.add_argument("--sectors", type=int, nargs="*", default=None, help="Optional TESS sectors")
    parser.add_argument("--windows", type=int, nargs="*", default=[301, 501, 801], help="Flatten window lengths")
    parser.add_argument("--stellar-radius", type=float, default=1.0, help="Stellar radius in solar radii")
    parser.add_argument("--stellar-mass", type=float, default=1.0, help="Stellar mass in solar masses")
    parser.add_argument("--period-min", type=float, default=1.0, help="TLS/BLS minimum period")
    parser.add_argument("--period-max", type=float, default=200.0, help="TLS/BLS maximum period")
    parser.add_argument("--exptime", type=int, default=None, help="Optional TESS exposure time filter in seconds, e.g. 120")
    parser.add_argument("--tls-threads", type=int, default=1, help="Number of TLS worker threads")
    parser.add_argument("--skip-injection", action="store_true", help="Skip transit injection/recovery tests")
    parser.add_argument("--skip-precheck", action="store_true", help="Skip initial Lightkurve product availability precheck")
    parser.add_argument("--precheck-only", action="store_true", help="Only run the Lightkurve product availability precheck, then exit")
    parser.add_argument("--skip-aperture", action="store_true", help="Skip TPF aperture sweep and difference image")
    parser.add_argument("--outdir", type=Path, default=None, help="Output directory. Defaults to a TIC-specific folder under level4_TTV_analyse.")
    args = parser.parse_args()

    args.tic = clean_tic_id(args.tic)
    if args.outdir is None:
        args.outdir = default_output_dir(args.tic)

    args.outdir.mkdir(parents=True, exist_ok=True)
    if not args.skip_precheck:
        lightkurve_precheck(args.tic, args.outdir)
    if args.precheck_only:
        print(f"\nPrecheck only; wrote files to: {args.outdir}")
        return

    report = {
        "target": tess_target_name(args.tic),
        "tic_id": args.tic,
        "candidate_period_days": args.period,
        "candidate_duration_days": args.duration,
        "candidate_t0": args.t0,
        "flux_products": {},
    }

    for flux_column in ["pdcsap_flux", "sap_flux"]:
        product_label = flux_column.replace("_flux", "").upper()
        print(f"\n=== {product_label}: sector-wise detrending ===")
        rotation_lc = download_rotation_lightcurve(args.tic, args.sectors, flux_column, args.exptime)
        if rotation_lc is not None:
            rot_time, rot_flux, _ = as_arrays(rotation_lc)
            ls_result = lomb_scargle_rotation(rot_time, rot_flux, max_period=min(args.period_max, 180))
            acf_result = acf_rotation(rot_time, rot_flux, max_lag_days=min(args.period_max, 180))
        else:
            ls_result = SearchResult("Lomb-Scargle", None, None, None, None, "no raw rotation light curve")
            acf_result = SearchResult("ACF", None, None, None, None, "no raw rotation light curve")

        stitched_by_window, _ = download_and_flatten(args.tic, args.sectors, flux_column, args.windows, args.exptime)
        product_report = {}
        for wl, lc in stitched_by_window.items():
            label = f"{product_label}_window_{wl}"
            time, flux, err = as_arrays(lc)
            print(f"\n[{label}] cadences={len(time)}")

            tls_result = run_tls(time, flux, err, args.period_min, args.period_max, args.tls_threads)
            bls_result = run_bls(time, flux, args.period_min, args.period_max, args.duration)
            odd_even = odd_even_check(time, flux, args.period, args.duration, args.t0)

            if args.skip_injection:
                injection_t0 = None
                inj_tls = SearchResult("TLS injection", None, None, None, None, "skipped")
                inj_bls = SearchResult("BLS injection", None, None, None, None, "skipped")
            else:
                injected_flux, injection_t0 = inject_box_transits(time, flux, args.period, args.duration, args.depth, args.t0)
                inj_tls = run_tls(time, injected_flux, err, args.period_min, args.period_max, args.tls_threads)
                inj_bls = run_bls(time, injected_flux, args.period_min, args.period_max, args.duration)

            flags = harmonic_flags(
                [("LS", ls_result.period_days), ("ACF", acf_result.period_days)],
                args.period,
            )

            print(f"LS:  {fmt_result(ls_result)}")
            print(f"ACF: {fmt_result(acf_result)}")
            print(f"TLS: {fmt_result(tls_result)}")
            print(f"BLS: {fmt_result(bls_result)}")
            print(f"Odd/even: {odd_even}")
            if flags:
                print("Rotation harmonic warnings:")
                for flag in flags:
                    print(f"  - {flag}")

            plot_diagnostics(args.outdir, label, time, flux, args.period, args.duration, ls_result, acf_result, args.t0)

            product_report[str(wl)] = {
                "lomb_scargle": asdict(ls_result),
                "acf": asdict(acf_result),
                "tls": asdict(tls_result),
                "bls": asdict(bls_result),
                "odd_even": asdict(odd_even),
                "rotation_harmonic_flags": flags,
                "injection_t0": injection_t0,
                "injection_tls": asdict(inj_tls),
                "injection_bls": asdict(inj_bls),
            }
        report["flux_products"][product_label] = product_report

    report["duration_plausibility"] = transit_duration_plausibility(
        args.period,
        args.duration,
        stellar_radius=args.stellar_radius,
        stellar_mass=args.stellar_mass,
    )

    if not args.skip_aperture:
        print("\n=== TPF aperture sweep and difference images ===")
        report["aperture_sweep"] = aperture_sweep(args.tic, args.sectors, args.period, args.duration, args.outdir, args.t0, args.exptime)

    json_path = args.outdir / "vetting_report.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nWrote report: {json_path}")
    print(f"Wrote diagnostic plots to: {args.outdir}")


if __name__ == "__main__":
    main()
