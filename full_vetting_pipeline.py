#!/usr/bin/env python3
"""Run a compact full-vetting pass for one local TESS candidate.

Example:
    python full_vetting_pipeline.py \
        --fits-dir /Users/koni/astro_projects/tess_fits/TIC_47579336 \
        --period 99.925
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from astropy.io import fits
from astropy.timeseries import BoxLeastSquares, LombScargle


PROJECT_ROOT = Path("/Users/koni/astro_projects")
REPORT_ROOT = PROJECT_ROOT / "vetting_reports"
TODO_MODULES = [
    "TLS Refit",
    "BLS Refit",
    "Gaia Companion Check",
    "TPF Pixel Test",
    "Centroid Shift Analysis",
]


@dataclass
class SectorSummary:
    sector: int | None
    cadence: str
    file: str
    points_raw: int
    points_used: int


@dataclass
class VettingSummary:
    tic: int | None
    generated_at: str
    fits_dir: str
    report_dir: str
    period_input: float
    alternate_period_days: float
    period_delta_days: float
    duration_days: float
    t0_btjd: float | None
    classification: str
    evidence_score: float
    sap_pdcsap_ratio: float | None
    sap_depth_ppm: float | None
    pdcsap_depth_ppm: float | None
    rotation_period: float | None
    rotation_power: float | None
    odd_even_status: str
    odd_depth_ppm: float | None
    even_depth_ppm: float | None
    visible_transits: int
    sectors_loaded: int
    files_loaded: int
    exofop_readiness: str
    status: str
    flags: list[str]
    todo_modules: list[str]
    outputs: dict[str, str]
    sector_summaries: list[dict[str, Any]]


def safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def infer_tic(path: Path) -> int | None:
    match = re.search(r"TIC[_-]?(\d+)", str(path), re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = re.search(r"-(\d{16})-", str(path))
    if match:
        return int(match.group(1))
    return None


def sector_from_path(path: Path) -> int | None:
    match = re.search(r"-s(\d{4})-", path.name)
    if not match:
        match = re.search(r"-s(\d{4})-", str(path))
    return int(match.group(1)) if match else None


def cadence_from_path(path: Path) -> str:
    text = str(path).lower()
    if "a_fast" in text:
        return "fast"
    if "_lc.fits" in text or "-s_lc.fits" in text:
        return "short"
    return "unknown"


def discover_fits(fits_dir: Path, include_fast: bool) -> list[Path]:
    files = sorted(
        path
        for path in fits_dir.rglob("*.fits")
        if path.is_file() and ("lc.fits" in path.name.lower() or path.name.lower().endswith(".fits"))
    )
    if not include_fast:
        files = [path for path in files if "a_fast" not in str(path).lower()]
    return files


def read_lightcurve(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, int]:
    with fits.open(path, memmap=False) as hdul:
        if len(hdul) < 2 or hdul[1].data is None:
            raise ValueError("missing light-curve table extension")
        data = hdul[1].data
        names = {name.upper(): name for name in (data.names or [])}
        required = ["TIME", "SAP_FLUX", "PDCSAP_FLUX"]
        missing = [name for name in required if name not in names]
        if missing:
            raise ValueError(f"missing FITS columns: {', '.join(missing)}")
        time = np.asarray(data[names["TIME"]], dtype=float)
        sap = np.asarray(data[names["SAP_FLUX"]], dtype=float)
        pdc = np.asarray(data[names["PDCSAP_FLUX"]], dtype=float)
        quality = np.asarray(data[names["QUALITY"]], dtype=int) if "QUALITY" in names else np.zeros(len(time), dtype=int)

    raw_count = int(len(time))
    good = np.isfinite(time) & np.isfinite(sap) & np.isfinite(pdc) & (quality == 0)
    time, sap, pdc = time[good], sap[good], pdc[good]
    if len(time) < 20:
        raise ValueError("too few good points")
    sap_med = np.nanmedian(sap)
    pdc_med = np.nanmedian(pdc)
    if not np.isfinite(sap_med) or sap_med == 0 or not np.isfinite(pdc_med) or pdc_med == 0:
        raise ValueError("invalid flux median")
    return time, sap / sap_med, pdc / pdc_med, raw_count, int(len(time))


def load_all_lightcurves(fits_dir: Path, include_fast: bool) -> tuple[list[SectorSummary], np.ndarray, np.ndarray, np.ndarray]:
    files = discover_fits(fits_dir, include_fast=include_fast)
    if not files:
        raise FileNotFoundError(f"no light-curve FITS files found in {fits_dir}")

    summaries: list[SectorSummary] = []
    times: list[np.ndarray] = []
    saps: list[np.ndarray] = []
    pdcsaps: list[np.ndarray] = []
    errors: list[str] = []
    for path in files:
        try:
            time, sap, pdc, raw_count, used_count = read_lightcurve(path)
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        summaries.append(
            SectorSummary(
                sector=sector_from_path(path),
                cadence=cadence_from_path(path),
                file=str(path),
                points_raw=raw_count,
                points_used=used_count,
            )
        )
        times.append(time)
        saps.append(sap)
        pdcsaps.append(pdc)

    if not times:
        detail = "; ".join(errors[:8])
        raise RuntimeError(f"no usable light curves loaded. {detail}")

    time_all = np.concatenate(times)
    sap_all = np.concatenate(saps)
    pdc_all = np.concatenate(pdcsaps)
    order = np.argsort(time_all)
    return summaries, time_all[order], sap_all[order], pdc_all[order]


def robust_normalized_flux(flux: np.ndarray) -> np.ndarray:
    median = np.nanmedian(flux)
    if not np.isfinite(median) or median == 0:
        return flux
    y = flux / median
    return y - np.nanmedian(y)


def rotation_check(time: np.ndarray, flux: np.ndarray) -> tuple[float | None, float | None, np.ndarray, np.ndarray]:
    y = robust_normalized_flux(flux)
    finite = np.isfinite(time) & np.isfinite(y)
    time, y = time[finite], y[finite]
    if len(time) < 200:
        return None, None, np.array([]), np.array([])
    freq = np.linspace(1 / 30.0, 1 / 0.5, 25000)
    power = LombScargle(time, y).power(freq, normalization="standard")
    best = int(np.nanargmax(power))
    return float(1 / freq[best]), float(power[best]), 1 / freq, power


def transit_mask(time: np.ndarray, period: float, duration: float, t0: float, scale: float = 0.5) -> np.ndarray:
    phase = ((time - t0 + 0.5 * period) % period) - 0.5 * period
    return np.abs(phase) < duration * scale


def folded_depth(time: np.ndarray, flux: np.ndarray, period: float, duration: float, t0: float) -> float | None:
    phase = ((time - t0 + 0.5 * period) % period) - 0.5 * period
    inside = np.abs(phase) < duration / 2
    outside = (np.abs(phase) > duration * 2) & (np.abs(phase) < duration * 8)
    if int(inside.sum()) < 5 or int(outside.sum()) < 30:
        return None
    depth = np.nanmedian(flux[outside]) - np.nanmedian(flux[inside])
    return safe_float(depth)


def find_best_t0(time: np.ndarray, flux: np.ndarray, period: float, duration: float) -> float | None:
    if len(time) < 50:
        return None
    start = float(np.nanmin(time))
    grid = np.linspace(start, start + period, 1200)
    depths = np.array([
        folded_depth(time, flux, period, duration, t0) if np.isfinite(t0) else np.nan
        for t0 in grid
    ], dtype=float)
    if not np.isfinite(depths).any():
        return None
    return float(grid[int(np.nanargmax(depths))])


def visible_transits(time: np.ndarray, period: float, duration: float, t0: float | None) -> int:
    if t0 is None:
        return 0
    epochs = np.round((time - t0) / period).astype(int)
    count = 0
    for epoch in sorted(set(epochs.tolist())):
        center = t0 + epoch * period
        if np.any(np.abs(time - center) < max(duration, 0.1)):
            count += 1
    return count


def odd_even_check(time: np.ndarray, flux: np.ndarray, period: float, duration: float, t0: float | None) -> tuple[str, float | None, float | None]:
    if t0 is None:
        return "UNKNOWN", None, None
    epochs = np.round((time - t0) / period).astype(int)
    odd_depths: list[float] = []
    even_depths: list[float] = []
    for epoch in sorted(set(epochs.tolist())):
        center = t0 + epoch * period
        depth = folded_depth(time, flux, period, duration, center)
        if depth is None:
            continue
        if epoch % 2:
            odd_depths.append(depth)
        else:
            even_depths.append(depth)
    if not odd_depths or not even_depths:
        return "INSUFFICIENT", safe_float(np.nanmedian(odd_depths)) if odd_depths else None, safe_float(np.nanmedian(even_depths)) if even_depths else None
    odd = float(np.nanmedian(odd_depths))
    even = float(np.nanmedian(even_depths))
    denom = max(abs(odd), abs(even), 1e-8)
    rel = abs(odd - even) / denom
    if rel < 0.25:
        return "OK", odd, even
    if rel < 0.5:
        return "BORDERLINE", odd, even
    return "MISMATCH", odd, even


def bls_refit(time: np.ndarray, flux: np.ndarray, period: float, duration: float) -> dict[str, Any]:
    try:
        y = flux / np.nanmedian(flux)
        y = y - np.nanmedian(y)
        periods = np.linspace(max(0.5, period * 0.96), period * 1.04, 700)
        durations = np.array([duration * 0.6, duration, duration * 1.4])
        model = BoxLeastSquares(time, y)
        result = model.power(periods, durations)
        best = int(np.nanargmax(result.power))
        return {
            "status": "DONE",
            "period_days": safe_float(result.period[best]),
            "duration_days": safe_float(result.duration[best]),
            "power": safe_float(result.power[best]),
            "todo": False,
        }
    except Exception as exc:
        return {"status": "TODO", "reason": str(exc), "todo": True}


def placeholder_module(name: str) -> dict[str, Any]:
    return {
        "status": "TODO",
        "module": name,
        "reason": "placeholder registered; implementation can be connected to catalog/pixel-level pipeline later",
        "todo": True,
    }


def evidence_score(
    sap_depth: float | None,
    pdc_depth: float | None,
    sap_pdcsap_ratio: float | None,
    rotation_period: float | None,
    odd_even_status: str,
    visible: int,
) -> tuple[float, list[str]]:
    score = 45.0
    flags: list[str] = []
    if sap_pdcsap_ratio is not None and 0.9 <= sap_pdcsap_ratio <= 1.1:
        score += 15
    else:
        flags.append("SAP_PDCSAP_RECHECK")
        score -= 8
    if pdc_depth is not None and pdc_depth > 0.005:
        score += 10
    if visible >= 3:
        score += 8
    else:
        flags.append("LOW_VISIBLE_TRANSITS")
        score -= 10
    if odd_even_status == "OK":
        score += 8
    elif odd_even_status in {"MISMATCH", "BORDERLINE"}:
        flags.append(f"ODD_EVEN_{odd_even_status}")
        score -= 10
    else:
        flags.append("ODD_EVEN_INSUFFICIENT")
        score -= 3
    if rotation_period is not None and rotation_period < 10:
        flags.append("FAST_ROTATION_ACTIVITY_RECHECK")
        score -= 5
    return round(max(0.0, min(100.0, score)), 1), flags


def classify_candidate(score: float, flags: list[str]) -> tuple[str, str, str]:
    # Keep high-value HZ candidates out of the final/green path until all manual vetting is complete.
    if score >= 60:
        return "HIGH_VALUE_HZ_RECHECK", "EXOFOP_PREP", "HIGH_VALUE_HZ_RECHECK / EXOFOP_PREP"
    return "RECHECK", "NOT_READY", "RECHECK"


def plot_folded(time: np.ndarray, sap: np.ndarray, pdc: np.ndarray, period: float, t0: float | None, out: Path) -> None:
    if t0 is None:
        return
    phase = ((time - t0 + 0.5 * period) % period) / period - 0.5
    order = np.argsort(phase)
    plt.figure(figsize=(10, 5))
    plt.scatter(phase[order], (sap[order] - 1) * 1e6, s=3, alpha=0.22, label="SAP")
    plt.scatter(phase[order], (pdc[order] - 1) * 1e6, s=3, alpha=0.22, label="PDCSAP")
    plt.axvline(0, color="#10201e", lw=1)
    plt.xlabel("Phase")
    plt.ylabel("Relative flux [ppm]")
    plt.title(f"Folded SAP/PDCSAP, P={period:.5f} d")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out, dpi=160)
    plt.close()


def plot_rotation(periods: np.ndarray, power: np.ndarray, rotation_period: float | None, out: Path) -> None:
    plt.figure(figsize=(10, 4))
    if len(periods) and len(power):
        order = np.argsort(periods)
        plt.plot(periods[order], power[order], color="#147a68", lw=1)
    if rotation_period is not None:
        plt.axvline(rotation_period, color="#b88220", lw=1.5, label=f"{rotation_period:.4f} d")
        plt.legend()
    plt.xlabel("Period [days]")
    plt.ylabel("Lomb-Scargle power")
    plt.title("Rotation periodogram")
    plt.tight_layout()
    plt.savefig(out, dpi=160)
    plt.close()


def write_text_report(summary: VettingSummary, modules: dict[str, Any], out: Path) -> None:
    lines = [
        "Kwarves Full Vetting Report",
        "=" * 28,
        f"TIC: {summary.tic}",
        f"Generated: {summary.generated_at}",
        f"Classification: {summary.classification}",
        f"Status: {summary.status}",
        f"ExoFOP readiness: {summary.exofop_readiness}",
        "",
        "Core metrics",
        "-" * 12,
        f"Period input: {summary.period_input:.6f} d",
        f"Alternate period: {summary.alternate_period_days:.6f} d",
        f"Period delta: {summary.period_delta_days:.6f} d",
        f"Rotation period: {summary.rotation_period}",
        f"SAP depth ppm: {summary.sap_depth_ppm}",
        f"PDCSAP depth ppm: {summary.pdcsap_depth_ppm}",
        f"SAP/PDCSAP ratio: {summary.sap_pdcsap_ratio}",
        f"Odd/even: {summary.odd_even_status}",
        f"Evidence score: {summary.evidence_score}",
        f"Visible transits: {summary.visible_transits}",
        "",
        "Flags",
        "-" * 5,
        *(summary.flags or ["none"]),
        "",
        "Dashboard fields",
        "-" * 16,
        f"classification={summary.classification}",
        f"evidence_score={summary.evidence_score}",
        f"sap_pdcsap_ratio={summary.sap_pdcsap_ratio}",
        f"rotation_period={summary.rotation_period}",
        f"odd_even_status={summary.odd_even_status}",
        f"exofop_readiness={summary.exofop_readiness}",
        "",
        "TODO / module status",
        "-" * 20,
    ]
    for name, payload in modules.items():
        lines.append(f"{name}: {payload.get('status')} - {payload.get('reason', payload.get('period_days', ''))}")
    out.write_text("\n".join(str(line) for line in lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> VettingSummary:
    fits_dir = Path(args.fits_dir).expanduser().resolve()
    tic = args.tic or infer_tic(fits_dir)
    report_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else REPORT_ROOT / f"TIC_{tic or 'UNKNOWN'}"
    report_dir.mkdir(parents=True, exist_ok=True)

    sectors, time, sap, pdc = load_all_lightcurves(fits_dir, include_fast=args.include_fast)
    rotation_period, rotation_power, rotation_periods, rotation_powers = rotation_check(time, pdc)
    t0 = find_best_t0(time, pdc, args.period, args.duration)
    sap_depth = folded_depth(time, sap, args.period, args.duration, t0) if t0 is not None else None
    pdc_depth = folded_depth(time, pdc, args.period, args.duration, t0) if t0 is not None else None
    sap_depth_ppm = round(sap_depth * 1e6, 2) if sap_depth is not None else None
    pdc_depth_ppm = round(pdc_depth * 1e6, 2) if pdc_depth is not None else None
    ratio = (sap_depth / pdc_depth) if sap_depth is not None and pdc_depth not in (None, 0) else None
    ratio = round(ratio, 4) if ratio is not None and np.isfinite(ratio) else None
    odd_even_status, odd_depth, even_depth = odd_even_check(time, pdc, args.period, args.duration, t0)
    visible = visible_transits(time, args.period, args.duration, t0)
    score, flags = evidence_score(sap_depth, pdc_depth, ratio, rotation_period, odd_even_status, visible)
    classification, readiness, status = classify_candidate(score, flags)

    modules = {
        "TLS Refit": placeholder_module("TLS Refit"),
        "BLS Refit": bls_refit(time, pdc, args.period, args.duration),
        "Gaia Companion Check": placeholder_module("Gaia Companion Check"),
        "TPF Pixel Test": placeholder_module("TPF Pixel Test"),
        "Centroid Shift Analysis": placeholder_module("Centroid Shift Analysis"),
    }
    outputs = {
        "vetting_summary.json": str(report_dir / "vetting_summary.json"),
        "vetting_report.txt": str(report_dir / "vetting_report.txt"),
        "folded_sap_pdcsap.png": str(report_dir / "folded_sap_pdcsap.png"),
        "rotation_periodogram.png": str(report_dir / "rotation_periodogram.png"),
    }
    summary = VettingSummary(
        tic=tic,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        fits_dir=str(fits_dir),
        report_dir=str(report_dir),
        period_input=float(args.period),
        alternate_period_days=float(args.alternate_period),
        period_delta_days=round(abs(float(args.period) - float(args.alternate_period)), 6),
        duration_days=float(args.duration),
        t0_btjd=round(t0, 6) if t0 is not None else None,
        classification=classification,
        evidence_score=score,
        sap_pdcsap_ratio=ratio,
        sap_depth_ppm=sap_depth_ppm,
        pdcsap_depth_ppm=pdc_depth_ppm,
        rotation_period=round(rotation_period, 6) if rotation_period is not None else None,
        rotation_power=round(rotation_power, 6) if rotation_power is not None else None,
        odd_even_status=odd_even_status,
        odd_depth_ppm=round(odd_depth * 1e6, 2) if odd_depth is not None else None,
        even_depth_ppm=round(even_depth * 1e6, 2) if even_depth is not None else None,
        visible_transits=visible,
        sectors_loaded=len({s.sector for s in sectors if s.sector is not None}),
        files_loaded=len(sectors),
        exofop_readiness=readiness,
        status=status,
        flags=flags,
        todo_modules=TODO_MODULES,
        outputs=outputs,
        sector_summaries=[asdict(item) for item in sectors],
    )
    plot_folded(time, sap, pdc, args.period, t0, report_dir / "folded_sap_pdcsap.png")
    plot_rotation(rotation_periods, rotation_powers, rotation_period, report_dir / "rotation_periodogram.png")
    (report_dir / "vetting_summary.json").write_text(json.dumps(asdict(summary) | {"modules": modules}, indent=2), encoding="utf-8")
    write_text_report(summary, modules, report_dir / "vetting_report.txt")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Kwarves full vetting for one local TIC FITS directory.")
    parser.add_argument("--fits-dir", required=True, help="Directory containing downloaded TESS light-curve FITS files.")
    parser.add_argument("--period", type=float, required=True, help="Candidate transit period in days.")
    parser.add_argument("--alternate-period", type=float, default=100.605, help="Alternative period to track for recheck.")
    parser.add_argument("--duration", type=float, default=0.195, help="Transit duration in days.")
    parser.add_argument("--tic", type=int, default=None, help="TIC override. Inferred from path/FITS names if omitted.")
    parser.add_argument("--output-dir", default=None, help="Optional output directory override.")
    parser.add_argument("--include-fast", action="store_true", help="Include a_fast cadence products as well as SPOC light curves.")
    return parser.parse_args()


def main() -> int:
    summary = run(parse_args())
    print(json.dumps({
        "tic": summary.tic,
        "classification": summary.classification,
        "evidence_score": summary.evidence_score,
        "sap_pdcsap_ratio": summary.sap_pdcsap_ratio,
        "rotation_period": summary.rotation_period,
        "odd_even_status": summary.odd_even_status,
        "exofop_readiness": summary.exofop_readiness,
        "report_dir": summary.report_dir,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
