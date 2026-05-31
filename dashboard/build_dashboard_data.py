#!/usr/bin/env python3
"""Build the static data bundle used by dashboard/index.html."""

from __future__ import annotations

import csv
import json
import math
import os
import re
import shutil
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(os.environ.get("ASTRO_PROJECT_ROOT", "/Users/koni/astro_projects"))
SCRIPT_ROOT = PROJECT_ROOT / "scripts"
DASHBOARD_DIR = SCRIPT_ROOT / "dashboard"
LIGHTCURVE_WEB_DIR = DASHBOARD_DIR / "lightcurves"
DB_PATH = PROJECT_ROOT / "database" / "planet_hunter.db"
MANIFEST_PATH = PROJECT_ROOT / "level0_lichtjahre_10ly_bis_500" / "manifest_all_candidates_by_distance.csv"
OUT_PATH = DASHBOARD_DIR / "dashboard-data.js"


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"none", "null", "nan"} else text


def safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def safe_int_or_none(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(float(value))
    except Exception:
        return None


def parse_sector_text(value: Any) -> list[int]:
    text = clean_text(value)
    if not text:
        return []
    sectors: list[int] = []
    seen: set[int] = set()
    for raw_token in re.split(r"[,\s;/|]+", text):
        token = raw_token.strip()
        if not token:
            continue
        if "-" in token:
            left, _, right = token.partition("-")
            try:
                start = int(left)
                end = int(right)
            except Exception:
                continue
            if end < start:
                start, end = end, start
            for number in range(start, min(end, start + 200) + 1):
                if number > 0 and number not in seen:
                    sectors.append(number)
                    seen.add(number)
            continue
        try:
            number = int(token)
        except Exception:
            continue
        if number > 0 and number not in seen:
            sectors.append(number)
            seen.add(number)
    return sectors


def rel_from_dashboard(path: Path) -> str:
    return os.path.relpath(path, DASHBOARD_DIR)


def sync_curve_asset(source_path: Path, tic: int) -> Path | None:
    """Ensure a deployable copy exists under dashboard/lightcurves."""
    try:
        LIGHTCURVE_WEB_DIR.mkdir(parents=True, exist_ok=True)
        target_path = LIGHTCURVE_WEB_DIR / f"TIC_{tic}.png"
        needs_copy = not target_path.exists()
        if not needs_copy:
            src_stat = source_path.stat()
            dst_stat = target_path.stat()
            needs_copy = src_stat.st_size != dst_stat.st_size or src_stat.st_mtime > dst_stat.st_mtime
        if needs_copy:
            shutil.copy2(source_path, target_path)
        return target_path
    except Exception:
        return None


def load_db_rows() -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=60)
    conn.row_factory = sqlite3.Row
    try:
        candidate_rows = conn.execute(
            """
            SELECT TIC, status, spc_class, is_fp, hz_class, hz_status, distance_ly,
                   best_period, planet_radius_earth, transit_snr, transit_count,
                   visible_transits, clean_sector_count, sector_count,
                   revisit_priority, next_recheck, notes
              FROM candidates_v2
            """
        ).fetchall()
        try:
            matrix_rows = conn.execute(
                """
                SELECT tic_id, n_transits, n_sectors, depth_ppt, duration_hours,
                       sap_pdcsap_match, odd_even_result, transit_shape, depth_stability,
                       data_gap_risk, sector_edge_risk, secondary_eclipse, period_alias_risk,
                       rotation_risk, status, status_color, extended_class, evidence_score,
                       score_interpretation, decision_reason, next_step, visible_transits,
                       clean_sector_count
                  FROM candidate_matrix
                """
            ).fetchall()
        except sqlite3.OperationalError:
            matrix_rows = []
        try:
            sector_rows = conn.execute(
                """
                SELECT TIC, sectors_text, sector_count, previous_sectors_text, previous_sector_count,
                       new_sectors_text, source_status, last_checked_at, last_new_sector_at
                  FROM tess_sector_inventory
                """
            ).fetchall()
        except sqlite3.OperationalError:
            sector_rows = []
    finally:
        conn.close()
    return (
        {int(row["TIC"]): dict(row) for row in candidate_rows},
        {int(row["tic_id"]): dict(row) for row in matrix_rows},
        {
            int(row["TIC"]): {
                **dict(row),
                "sectors": parse_sector_text(row["sectors_text"]),
                "previousSectors": parse_sector_text(row["previous_sectors_text"]),
                "newSectors": parse_sector_text(row["new_sectors_text"]),
            }
            for row in sector_rows
        },
    )


def color_for(row: dict[str, Any]) -> str:
    mark = clean_text(row.get("markierung")).upper()
    status = clean_text(row.get("status")).upper()
    mark_class = clean_text(row.get("markierungs_klasse")).upper()
    if mark == "ROT" or "FALSE" in status or "FP" in status or "FP" in mark_class:
        return "red"
    if mark == "GELB" or "TESS" in status or "INFO" in mark_class:
        return "yellow"
    if mark == "GRUEN" or "SPC" in status:
        return "green"
    return "gray"


def color_label(color: str) -> str:
    return {
        "green": "Gruen",
        "yellow": "Gelb",
        "red": "Rot",
        "violet": "Violett",
        "gray": "Unsortiert",
    }.get(color, color)


def reason_for(row: dict[str, Any], color: str, is_violet: bool) -> str:
    mark_class = clean_text(row.get("markierungs_klasse"))
    status = clean_text(row.get("status"))
    hz = clean_text(row.get("hz_status") or row.get("hz_class"))
    if is_violet and color == "green":
        return f"SPC-Kandidat und HZ-Ziel ({hz})"
    if is_violet:
        return f"HZ-Ziel / violett markiert ({hz})"
    if color == "green":
        return mark_class or "SPC-Kandidat"
    if color == "yellow":
        return mark_class or status or "mehr Informationen noetig"
    if color == "red":
        return mark_class or status or "False-Positive/Systematik"
    return status or "noch nicht eingeordnet"


def stable_angle(tic: int) -> float:
    return ((tic * 137.508) % 360.0) * math.pi / 180.0


def build_candidate(
    row: dict[str, Any],
    db_row: dict[str, Any] | None,
    matrix_row: dict[str, Any] | None,
    sector_row: dict[str, Any] | None,
    max_distance: float,
) -> dict[str, Any]:
    merged = {**row, **(db_row or {})}
    matrix = matrix_row or {}
    sector = sector_row or {}
    tic = safe_int(merged.get("TIC"))
    color = color_for(merged)
    is_violet = clean_text(merged.get("hz_markierung")).upper() == "VIOLETT"
    distance = safe_float(merged.get("distance_ly")) or 0.0
    period = safe_float(merged.get("best_period")) or 0.0
    snr = safe_float(merged.get("transit_snr")) or 0.0
    angle = stable_angle(tic)
    radial = math.sqrt(max(distance, 1.0) / max(max_distance, 1.0))
    jitter = ((tic % 97) / 97.0 - 0.5) * 0.08
    x = math.cos(angle) * (0.16 + radial * 0.76) + jitter
    y = math.sin(angle) * (0.16 + radial * 0.76) - jitter
    z = min(1.0, max(0.0, snr / 120.0))
    candidate_folder = clean_text(merged.get("candidate_folder"))
    lightcurve_img = ""
    lightcurve_img_local = ""
    lightcurve_img_deploy = ""
    if candidate_folder and (color == "green" or is_violet):
        path = PROJECT_ROOT / candidate_folder / "lichtkurven_png" / "LICHTKURVE_COMBINED.png"
        if path.exists():
            lightcurve_img_local = rel_from_dashboard(path)
            deploy_path = sync_curve_asset(path, tic)
            if deploy_path and deploy_path.exists():
                lightcurve_img_deploy = rel_from_dashboard(deploy_path)
                lightcurve_img = lightcurve_img_deploy
            else:
                lightcurve_img = lightcurve_img_local
    matrix_status_color = clean_text(matrix.get("status_color")).upper()
    evidence_score = safe_float(matrix.get("evidence_score"))
    if evidence_score is not None:
        evidence_score = round(evidence_score, 1)
    observed_sectors = list(sector.get("sectors") or [])
    previous_sectors = list(sector.get("previousSectors") or [])
    new_sectors = list(sector.get("newSectors") or [])
    return {
        "tic": tic,
        "status": clean_text(merged.get("status")),
        "color": color,
        "colorLabel": color_label("violet" if is_violet else color),
        "baseColorLabel": color_label(color),
        "isViolet": is_violet,
        "reason": reason_for(merged, color, is_violet),
        "markierung": clean_text(merged.get("markierung")),
        "markierungsKlasse": clean_text(merged.get("markierungs_klasse")),
        "hzMarkierung": clean_text(merged.get("hz_markierung")),
        "hz": clean_text(merged.get("hz_status") or merged.get("hz_class")),
        "distance": round(distance, 2),
        "period": round(period, 4),
        "radius": round(safe_float(merged.get("planet_radius_earth")) or 0.0, 2),
        "snr": round(snr, 2),
        "transits": safe_int(merged.get("transit_count")),
        "visibleTransits": safe_int(merged.get("visible_transits")),
        "cleanSectors": safe_int(merged.get("clean_sector_count")),
        "matrixStatus": clean_text(matrix.get("status")),
        "matrixColor": matrix_status_color,
        "matrixClass": clean_text(matrix.get("extended_class")),
        "matrixScoreBand": clean_text(matrix.get("score_interpretation")),
        "evidenceScore": evidence_score,
        "decisionReason": clean_text(matrix.get("decision_reason")),
        "nextStep": clean_text(matrix.get("next_step")),
        "matrixTransits": safe_int_or_none(matrix.get("n_transits")),
        "matrixSectors": safe_int_or_none(matrix.get("n_sectors")),
        "matrixVisibleTransits": safe_int_or_none(matrix.get("visible_transits")),
        "matrixCleanSectors": safe_int_or_none(matrix.get("clean_sector_count")),
        "depthPpt": safe_float(matrix.get("depth_ppt")),
        "durationHours": safe_float(matrix.get("duration_hours")),
        "sapPdcsapMatch": clean_text(matrix.get("sap_pdcsap_match")),
        "oddEvenResult": clean_text(matrix.get("odd_even_result")),
        "transitShape": clean_text(matrix.get("transit_shape")),
        "depthStability": clean_text(matrix.get("depth_stability")),
        "dataGapRisk": clean_text(matrix.get("data_gap_risk")),
        "sectorEdgeRisk": clean_text(matrix.get("sector_edge_risk")),
        "secondaryEclipse": clean_text(matrix.get("secondary_eclipse")),
        "periodAliasRisk": clean_text(matrix.get("period_alias_risk")),
        "rotationRisk": clean_text(matrix.get("rotation_risk")),
        "observedSectors": observed_sectors,
        "observedSectorCount": safe_int_or_none(sector.get("sector_count")) or len(observed_sectors),
        "previousSectors": previous_sectors,
        "previousSectorCount": safe_int_or_none(sector.get("previous_sector_count")) or len(previous_sectors),
        "newSectors": new_sectors,
        "sectorInventoryStatus": clean_text(sector.get("source_status")),
        "sectorLastCheckedAt": clean_text(sector.get("last_checked_at")),
        "sectorLastNewAt": clean_text(sector.get("last_new_sector_at")),
        "folder": candidate_folder,
        "lightcurveImg": lightcurve_img,
        "lightcurveImgLocal": lightcurve_img_local,
        "lightcurveImgDeploy": lightcurve_img_deploy,
        "map": {"x": round(x, 4), "y": round(y, 4), "z": round(z, 4)},
    }


def bucket(counter: Counter[str], key: str) -> int:
    return int(counter.get(key, 0))


def build_tree(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    colors = Counter(candidate["color"] for candidate in candidates)
    violet = sum(1 for candidate in candidates if candidate["isViolet"])
    hz = Counter(candidate["hz"] or "UNKNOWN" for candidate in candidates)
    status = Counter(candidate["status"] or "UNKNOWN" for candidate in candidates)
    return [
        {
            "id": "level0",
            "title": "Level 0: erste Farbsortierung",
            "description": "Die erste Farbe kommt aus dem Level-0-Ordner und sagt: vielversprechend, unklar oder wahrscheinlich raus.",
            "children": [
                {"label": "Gruen", "count": bucket(colors, "green"), "meaning": "SPC-Kandidat, Signal wirkt brauchbar."},
                {"label": "Gelb", "count": bucket(colors, "yellow"), "meaning": "Noch nicht genug Daten oder unklare Lage."},
                {"label": "Rot", "count": bucket(colors, "red"), "meaning": "False Positive, Artefakt oder Systematik-Risiko."},
                {"label": "Violett", "count": violet, "meaning": "HZ-Ziel oder Top-Tier; liegt als Zusatzfarbe ueber gruen/gelb/rot."},
            ],
        },
        {
            "id": "hz",
            "title": "HZ: warum violett?",
            "description": "Violett ist kein Ersatz fuer rot/gruen/gelb, sondern ein Fokusmarker: Habitable-Zone oder Top-Tier.",
            "children": [
                {"label": "Konservative HZ", "count": bucket(hz, "KONSERVATIVE_HZ"), "meaning": "Periode liegt im engeren HZ-Fenster."},
                {"label": "Optimistische HZ innen", "count": bucket(hz, "OPT_HZ_INNEN"), "meaning": "Nah an der warmen HZ-Kante."},
                {"label": "Zu heiss", "count": bucket(hz, "ZU_HEISS"), "meaning": "Nicht HZ, aber kann trotzdem gruen sein."},
            ],
        },
        {
            "id": "next",
            "title": "Naechste Aktion",
            "description": "Die Farbe entscheidet nicht allein. Der naechste Schritt kommt aus Status, HZ und Vetting-Hinweisen.",
            "children": [
                {"label": "SPC-A/B/C", "count": sum(status.get(key, 0) for key in ("SPC-A", "SPC-B", "SPC-C")), "meaning": "weiter untersuchen"},
                {"label": "Mehr TESS", "count": bucket(status, "NEEDS_MORE_TESS_DATA"), "meaning": "warten/rechecken"},
                {"label": "False Positive", "count": bucket(status, "FALSE_POSITIVE") + bucket(status, "FP_ART"), "meaning": "depriorisieren"},
                {"label": "Artefakt", "count": bucket(status, "SPC_ART"), "meaning": "nur mit starker Evidenz weiter"},
            ],
        },
    ]


def main() -> int:
    db_rows, matrix_rows, sector_rows = load_db_rows()
    with MANIFEST_PATH.open(newline="", encoding="utf-8") as handle:
        manifest_rows = list(csv.DictReader(handle))

    max_distance = max(safe_float(row.get("distance_ly")) or 0.0 for row in manifest_rows)
    candidates = [
        build_candidate(
            row,
            db_rows.get(safe_int(row.get("TIC"))),
            matrix_rows.get(safe_int(row.get("TIC"))),
            sector_rows.get(safe_int(row.get("TIC"))),
            max_distance,
        )
        for row in manifest_rows
    ]
    candidates.sort(key=lambda item: (item["distance"], -item["snr"], item["tic"]))

    lightcurve_candidates = [
        candidate for candidate in candidates
        if candidate["lightcurveImg"] and (candidate["isViolet"] or candidate["color"] == "green")
    ]
    priority_candidates = sorted(
        lightcurve_candidates,
        key=lambda item: (not item["isViolet"], item["color"] != "green", -item["snr"], item["distance"]),
    )[:80]

    summary = {
        "total": len(candidates),
        "green": sum(1 for candidate in candidates if candidate["color"] == "green"),
        "yellow": sum(1 for candidate in candidates if candidate["color"] == "yellow"),
        "red": sum(1 for candidate in candidates if candidate["color"] == "red"),
        "violet": sum(1 for candidate in candidates if candidate["isViolet"]),
        "lightcurves": len(lightcurve_candidates),
    }

    data = {
        "generatedAt": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "tree": build_tree(candidates),
        "candidates": candidates,
        "lightcurveCandidates": lightcurve_candidates,
        "priorityCandidates": priority_candidates,
    }

    OUT_PATH.write_text(
        "window.ASTRO_DASHBOARD_DATA = "
        + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT_PATH}")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
