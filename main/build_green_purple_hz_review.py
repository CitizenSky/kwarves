#!/usr/bin/env python3
"""Build a focused review pack for green HZ-purple level0 candidates."""

from __future__ import annotations

import csv
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "database" / "planet_hunter.db"
LEVEL0_ROOT = PROJECT_ROOT / "level0_lichtjahre_10ly_bis_500"
MANIFEST_PATH = LEVEL0_ROOT / "manifest_all_candidates_by_distance.csv"
OUT_ROOT = (
    PROJECT_ROOT
    / "level1_rohkandidaten"
    / "level1_visuelle_pruefung"
    / "level1_05_GRUEN_VIOLETT_SPC_HZ"
)
PLOT_LINK_DIR = OUT_ROOT / "combined_plots"


@dataclass
class Candidate:
    row: dict[str, Any]
    plot_path: Path | None


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def read_manifest() -> list[dict[str, str]]:
    with MANIFEST_PATH.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_db_rows(tics: set[str]) -> dict[str, dict[str, Any]]:
    if not tics:
        return {}
    placeholders = ",".join("?" for _ in tics)
    fields = [
        "TIC",
        "status",
        "spc_class",
        "is_fp",
        "teff",
        "stellar_radius",
        "stellar_logg",
        "best_period",
        "duration",
        "depth",
        "planet_radius_earth",
        "transit_snr",
        "transit_count",
        "sector_count",
        "clean_sector_count",
        "visible_transits",
        "revisit_priority",
        "next_recheck",
        "notes",
        "created_at",
    ]
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT {','.join(fields)} FROM candidates_v2 WHERE TIC IN ({placeholders})",
            tuple(sorted(tics, key=int)),
        ).fetchall()
    return {str(row["TIC"]): dict(row) for row in rows}


def plot_for_candidate(candidate_folder: str) -> Path | None:
    folder = PROJECT_ROOT / candidate_folder
    png_dir = folder / "lichtkurven_png"
    for name in ("LICHTKURVE_COMBINED.png", "LICHTKURVE_FOLDED.png", "LICHTKURVE_RAW.png"):
        path = png_dir / name
        if path.exists():
            return path
    return None


def priority_score(row: dict[str, Any]) -> float:
    score = 0.0
    spc = str(row.get("status") or row.get("spc_class") or "").upper()
    hz = str(row.get("hz_status") or "").upper()
    snr = safe_float(row.get("transit_snr"))
    distance = safe_float(row.get("distance_ly"), 9999.0)
    radius = safe_float(row.get("planet_radius_earth"))
    visible = safe_int(row.get("visible_transits"))
    clean = safe_int(row.get("clean_sector_count"))
    transit_count = safe_int(row.get("transit_count"))

    score += {"SPC-A": 60, "SPC-B": 52, "SPC-C": 36, "SPC": 50}.get(spc, 20)
    score += 12 if hz == "KONSERVATIVE_HZ" else 8 if hz == "OPT_HZ_INNEN" else 4
    if distance <= 20:
        score += 22
    elif distance <= 50:
        score += 20
    elif distance <= 100:
        score += 17
    elif distance <= 150:
        score += 13
    elif distance <= 250:
        score += 9
    else:
        score += 4
    score += min(snr, 50.0) * 0.45
    score += min(visible, 4) * 4
    score += min(clean, 4) * 3
    score += min(transit_count, 4) * 2
    if 1.0 <= radius <= 2.5:
        score += 8
    elif radius <= 3.2:
        score += 5
    elif radius <= 4.0:
        score += 2
    return round(score, 3)


def priority_group(row: dict[str, Any]) -> str:
    status = str(row.get("status") or row.get("spc_class") or "").upper()
    snr = safe_float(row.get("transit_snr"))
    distance = safe_float(row.get("distance_ly"), 9999.0)
    hz = str(row.get("hz_status") or "").upper()
    if status in {"SPC-A", "SPC-B"}:
        return "A_LEVEL5_NOW"
    if status == "SPC-C" and distance <= 100 and snr >= 20:
        return "A_LEVEL5_NOW"
    if hz == "KONSERVATIVE_HZ" or snr >= 10 or distance <= 150:
        return "B_STRONG_REVIEW"
    return "C_RECHECK_LATER"


def priority_reason(row: dict[str, Any]) -> str:
    parts = []
    status = row.get("status") or row.get("spc_class") or ""
    hz = row.get("hz_status") or ""
    if status:
        parts.append(str(status))
    if hz == "KONSERVATIVE_HZ":
        parts.append("konservative HZ")
    elif hz:
        parts.append(str(hz))
    distance = safe_float(row.get("distance_ly"), 9999.0)
    snr = safe_float(row.get("transit_snr"))
    if distance <= 100:
        parts.append(f"nah {distance:.1f} ly")
    if snr >= 20:
        parts.append(f"sehr hohes SNR {snr:.1f}")
    elif snr >= 10:
        parts.append(f"SNR {snr:.1f}")
    visible = safe_int(row.get("visible_transits"))
    clean = safe_int(row.get("clean_sector_count"))
    if visible or clean:
        parts.append(f"vis/clean {visible}/{clean}")
    return "; ".join(parts)


def link_plot(target: Path, link: Path) -> None:
    target = target.resolve()
    if link.is_symlink():
        if Path(os.readlink(link)) == target:
            return
        link.unlink()
    elif link.exists():
        link.unlink()
    os.symlink(target, link)


def build_candidates() -> list[Candidate]:
    manifest_rows = [
        row
        for row in read_manifest()
        if row.get("markierung") == "GRUEN" and row.get("hz_markierung") == "VIOLETT"
    ]
    db_rows = load_db_rows({row["TIC"] for row in manifest_rows})
    candidates: list[Candidate] = []
    for manifest in manifest_rows:
        tic = manifest["TIC"]
        combined = {**manifest, **db_rows.get(tic, {})}
        combined["TIC"] = tic
        combined["level0_candidate_folder"] = manifest["candidate_folder"]
        combined["combined_plot"] = str(plot_for_candidate(manifest["candidate_folder"]) or "")
        combined["priority_score"] = priority_score(combined)
        combined["priority_group"] = priority_group(combined)
        combined["priority_reason"] = priority_reason(combined)
        candidates.append(Candidate(combined, Path(combined["combined_plot"]) if combined["combined_plot"] else None))

    candidates.sort(
        key=lambda item: (
            {"A_LEVEL5_NOW": 0, "B_STRONG_REVIEW": 1, "C_RECHECK_LATER": 2}.get(
                item.row["priority_group"], 9
            ),
            -safe_float(item.row["priority_score"]),
            safe_float(item.row.get("distance_ly"), 9999.0),
            int(item.row["TIC"]),
        )
    )
    return candidates


def write_outputs(candidates: list[Candidate]) -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    PLOT_LINK_DIR.mkdir(parents=True, exist_ok=True)
    for old in PLOT_LINK_DIR.glob("*.png"):
        old.unlink()

    fields = [
        "rank",
        "priority_group",
        "priority_score",
        "TIC",
        "status",
        "spc_class",
        "hz_status",
        "distance_ly",
        "best_period",
        "planet_radius_earth",
        "transit_snr",
        "transit_count",
        "visible_transits",
        "clean_sector_count",
        "sector_count",
        "revisit_priority",
        "next_recheck",
        "is_fp",
        "notes",
        "priority_reason",
        "combined_plot_link",
        "combined_plot_source",
        "level0_candidate_folder",
    ]
    rows: list[dict[str, Any]] = []
    for idx, candidate in enumerate(candidates, 1):
        row = dict(candidate.row)
        plot_link = ""
        if candidate.plot_path and candidate.plot_path.exists():
            link_name = f"{idx:03d}_TIC_{row['TIC']}_{row['priority_group']}_combined.png"
            link_path = PLOT_LINK_DIR / link_name
            link_plot(candidate.plot_path, link_path)
            plot_link = str(link_path)
        rows.append(
            {
                **row,
                "rank": idx,
                "combined_plot_link": plot_link,
                "combined_plot_source": str(candidate.plot_path or ""),
            }
        )

    csv_path = OUT_ROOT / "05_GRUEN_VIOLETT_SPC_HZ_priority.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    markdown_lines = [
        "# Gruen-violette SPC/HZ-Kandidaten",
        "",
        f"Gesamt: {len(rows)}",
        "",
        "| Rang | Gruppe | TIC | Status | HZ | SNR | Periode d | Rp Re | Distanz ly | Grund |",
        "|---:|---|---:|---|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        markdown_lines.append(
            "| {rank} | {priority_group} | {TIC} | {status} | {hz_status} | "
            "{transit_snr:.2f} | {best_period:.4f} | {planet_radius_earth:.2f} | "
            "{distance_ly:.1f} | {priority_reason} |".format(
                rank=row["rank"],
                priority_group=row["priority_group"],
                TIC=row["TIC"],
                status=row.get("status") or "",
                hz_status=row.get("hz_status") or "",
                transit_snr=safe_float(row.get("transit_snr")),
                best_period=safe_float(row.get("best_period")),
                planet_radius_earth=safe_float(row.get("planet_radius_earth")),
                distance_ly=safe_float(row.get("distance_ly")),
                priority_reason=str(row.get("priority_reason") or "").replace("|", "/"),
            )
        )
    markdown_lines.extend(
        [
            "",
            "Naechster sinnvoller Schritt: `A_LEVEL5_NOW` zuerst mit Odd/Even, Secondary und Nachbarstern-Checks pruefen.",
            "",
        ]
    )
    (OUT_ROOT / "README.md").write_text("\n".join(markdown_lines), encoding="utf-8")

    render_contact_sheets(rows)


def load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font: ImageFont.ImageFont) -> None:
    draw.text(xy, text, fill=(20, 24, 28), font=font)


def render_contact_sheets(rows: list[dict[str, Any]]) -> None:
    cols = 3
    rows_per_page = 4
    tile_w = 620
    image_h = 410
    label_h = 106
    gap = 28
    margin = 36
    header_h = 72
    page_size = cols * rows_per_page
    title_font = load_font(26, bold=True)
    label_font = load_font(18, bold=True)
    small_font = load_font(15)

    for page_idx, start in enumerate(range(0, len(rows), page_size), 1):
        page_rows = rows[start : start + page_size]
        sheet_w = margin * 2 + cols * tile_w + (cols - 1) * gap
        sheet_h = margin * 2 + header_h + rows_per_page * (image_h + label_h) + (rows_per_page - 1) * gap
        sheet = Image.new("RGB", (sheet_w, sheet_h), (246, 248, 250))
        draw = ImageDraw.Draw(sheet)
        draw.text(
            (margin, margin),
            f"Gruen-violette SPC/HZ-Kandidaten - Kontaktbogen {page_idx}",
            fill=(20, 24, 28),
            font=title_font,
        )

        for idx, row in enumerate(page_rows):
            col = idx % cols
            line = idx // cols
            x = margin + col * (tile_w + gap)
            y = margin + header_h + line * (image_h + label_h + gap)
            draw.rounded_rectangle(
                (x, y, x + tile_w, y + image_h + label_h),
                radius=8,
                fill=(255, 255, 255),
                outline=(205, 213, 222),
                width=1,
            )
            image_path = Path(str(row.get("combined_plot_link") or row.get("combined_plot_source") or ""))
            image_box = (x + 10, y + label_h, x + tile_w - 10, y + label_h + image_h - 10)
            if image_path.exists():
                with Image.open(image_path) as source:
                    source = source.convert("RGB")
                    source.thumbnail((image_box[2] - image_box[0], image_box[3] - image_box[1]))
                    px = image_box[0] + ((image_box[2] - image_box[0]) - source.width) // 2
                    py = image_box[1] + ((image_box[3] - image_box[1]) - source.height) // 2
                    sheet.paste(source, (px, py))
            else:
                draw.rectangle(image_box, fill=(238, 241, 244), outline=(205, 213, 222))
                draw_label(draw, (image_box[0] + 18, image_box[1] + 18), "Plot fehlt", label_font)

            rank = row.get("rank")
            tic = row.get("TIC")
            group = row.get("priority_group")
            status = row.get("status") or row.get("spc_class") or ""
            label_1 = f"#{rank} TIC {tic} | {group}"
            label_2 = (
                f"{status} | {row.get('hz_status') or ''} | "
                f"SNR {safe_float(row.get('transit_snr')):.1f} | P {safe_float(row.get('best_period')):.2f} d"
            )
            label_3 = (
                f"Rp {safe_float(row.get('planet_radius_earth')):.2f} Re | "
                f"{safe_float(row.get('distance_ly')):.1f} ly | "
                f"vis/clean {safe_int(row.get('visible_transits'))}/{safe_int(row.get('clean_sector_count'))}"
            )
            draw_label(draw, (x + 16, y + 14), label_1, label_font)
            draw_label(draw, (x + 16, y + 43), label_2, small_font)
            draw_label(draw, (x + 16, y + 68), label_3, small_font)

        out_path = OUT_ROOT / f"kontaktbogen_gruen_violett_spc_hz_{page_idx:02d}.png"
        sheet.save(out_path)


def main() -> int:
    candidates = build_candidates()
    write_outputs(candidates)
    print(f"Candidates: {len(candidates)}")
    print(f"Output: {OUT_ROOT}")
    print(f"Priority CSV: {OUT_ROOT / '05_GRUEN_VIOLETT_SPC_HZ_priority.csv'}")
    print(f"Contact sheets: {len(list(OUT_ROOT.glob('kontaktbogen_gruen_violett_spc_hz_*.png')))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
