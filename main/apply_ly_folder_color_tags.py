#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import plistlib
import re
import sqlite3
import subprocess
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path("/Users/koni/astro_projects")
LOCAL_LEVEL0 = PROJECT_ROOT / "level0_lichtjahre_10ly_bis_500"
ICLOUD_LEVEL0 = (
    Path("/Users/koni/Library/Mobile Documents/com~apple~CloudDocs")
    / "astro_projects"
    / "level0_lichtjahre_10ly_bis_500"
)
DB_PATH = PROJECT_ROOT / "database" / "planet_hunter.db"
MATRIX_CSV = PROJECT_ROOT / "candidate_matrix" / "candidate_matrix.csv"
DASHBOARD_DATA = PROJECT_ROOT / "scripts" / "dashboard" / "dashboard-data.js"

TAG_ATTR = "com.apple.metadata:_kMDItemUserTags"

# Apple tag payload color numbers differ from Finder's AppleScript label index.
# The first tag is the visible primary color in iOS Files.
TAG_SPECS = {
    "orange": ("Orange", 7, 1),
    "red": ("Rot", 6, 2),
    "yellow": ("Gelb", 5, 3),
    "green": ("Gr\u00fcn", 2, 6),
    # Apple stores the default tag names internally in English; iOS/macOS
    # localize "Purple" to "Lila" in German. A literal "Lila" tag becomes
    # a custom gray tag in iCloud Files.
    "purple": ("Purple", 3, 5),
}

TIC_RE = re.compile(r"TIC_(\d+)")


def candidate_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    dirs: list[Path] = []
    for range_dir in sorted(root.glob("*_ly")):
        if not range_dir.is_dir():
            continue
        dirs.extend(sorted(p for p in range_dir.iterdir() if p.is_dir() and "TIC_" in p.name))
    return dirs


def tic_from_path(path: Path) -> int | None:
    match = TIC_RE.search(path.name)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def normalize_text(value: object) -> str:
    return "" if value is None else str(value).strip().upper()


def load_matrix_classes() -> dict[int, dict[str, str]]:
    if DB_PATH.exists():
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT tic_id, status, status_color, extended_class, score_interpretation
                    FROM candidate_matrix
                    """
                ).fetchall()
            return {
                int(row["tic_id"]): {
                    "status": str(row["status"] or ""),
                    "status_color": str(row["status_color"] or ""),
                    "extended_class": str(row["extended_class"] or ""),
                    "score_interpretation": str(row["score_interpretation"] or ""),
                }
                for row in rows
            }
        except sqlite3.Error:
            pass

    if MATRIX_CSV.exists():
        with MATRIX_CSV.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            result: dict[int, dict[str, str]] = {}
            for row in reader:
                try:
                    tic = int(float(row.get("tic_id") or row.get("TIC") or 0))
                except ValueError:
                    continue
                result[tic] = {
                    "status": str(row.get("status") or ""),
                    "status_color": str(row.get("status_color") or ""),
                    "extended_class": str(row.get("extended_class") or ""),
                    "score_interpretation": str(row.get("score_interpretation") or ""),
                }
            return result
    return {}


def load_dashboard_classes() -> dict[int, dict[str, object]]:
    if not DASHBOARD_DATA.exists():
        return {}
    text = DASHBOARD_DATA.read_text(encoding="utf-8")
    marker = "window.ASTRO_DASHBOARD_DATA = "
    if marker not in text:
        return {}
    payload = text.split(marker, 1)[1].strip()
    if payload.endswith(";"):
        payload = payload[:-1]
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    result: dict[int, dict[str, object]] = {}
    for row in data.get("candidates", []):
        try:
            tic = int(row.get("tic"))
        except (TypeError, ValueError):
            continue
        result[tic] = row
    return result


def classify(
    path: Path,
    matrix_by_tic: dict[int, dict[str, str]],
    dashboard_by_tic: dict[int, dict[str, object]],
) -> tuple[str, list[str]]:
    name = path.name
    tic = tic_from_path(path)
    dashboard = dashboard_by_tic.get(tic or -1, {})
    dashboard_text = " ".join(
        str(value or "")
        for value in (
            dashboard.get("status"),
            dashboard.get("matrixStatus"),
            dashboard.get("matrixClass"),
            dashboard.get("matrixScoreBand"),
            " ".join(str(label) for label in dashboard.get("displayLabels", []) if label),
        )
    ).upper()
    matrix = matrix_by_tic.get(tic or -1, {})
    status_color = normalize_text(matrix.get("status_color"))
    status_text = " ".join(
        normalize_text(matrix.get(key))
        for key in ("status", "extended_class", "score_interpretation")
    )

    if dashboard:
        color = normalize_text(dashboard.get("color")).lower()
        if color == "yellow" and "SPC_FOLLOWUP_READY" in dashboard_text:
            primary = "yellow"
        elif color == "yellow":
            primary = "orange"
        elif color == "green":
            primary = "green"
        elif color == "red":
            primary = "red"
        else:
            primary = "none"
    elif "SPC_FOLLOWUP_READY" in status_text:
        primary = "yellow"
    elif status_color == "YELLOW":
        primary = "orange"
    elif status_color == "GREEN":
        primary = "green"
    elif status_color == "RED":
        primary = "red"
    elif status_color == "PURPLE":
        primary = "purple"
    elif name.startswith("RED_"):
        primary = "red"
    elif name.startswith("YELLOW_INFO"):
        primary = "orange"
    elif name.startswith("SPC_GREEN"):
        primary = "green"
    elif "HZ_PURPLE" in name:
        primary = "purple"
    else:
        primary = "none"

    tags: list[str] = []
    if primary != "none":
        tags.append(primary)
    if primary != "none" and (dashboard.get("isViolet") is True or "HZ_PURPLE" in name) and "purple" not in tags:
        tags.append("purple")
    return primary, tags


def tag_payload(tag_keys: list[str]) -> bytes:
    tag_values = []
    for key in tag_keys:
        name, color_code, _finder_label = TAG_SPECS[key]
        tag_values.append(f"{name}\n{color_code}")
    return plistlib.dumps(tag_values, fmt=plistlib.FMT_BINARY)


def set_user_tags(path: Path, tag_keys: list[str]) -> None:
    if not tag_keys:
        subprocess.run(["xattr", "-d", TAG_ATTR, str(path)], check=False, stderr=subprocess.DEVNULL)
        return
    subprocess.run(
        ["xattr", "-w", "-x", TAG_ATTR, tag_payload(tag_keys).hex(), str(path)],
        check=True,
    )


APPLESCRIPT_SET_LABEL = """
on run argv
    set labelIndex to (item 1 of argv) as integer
    tell application "Finder"
        repeat with i from 2 to (count argv)
            set p to item i of argv
            set label index of (POSIX file p as alias) to labelIndex
        end repeat
    end tell
end run
"""


def set_finder_labels(paths_by_label: dict[int, list[Path]], chunk_size: int = 80) -> None:
    for label_index, paths in paths_by_label.items():
        if not paths:
            continue
        for i in range(0, len(paths), chunk_size):
            chunk = [str(p) for p in paths[i : i + chunk_size]]
            subprocess.run(
                ["osascript", "-e", APPLESCRIPT_SET_LABEL, str(label_index), *chunk],
                check=True,
                stdout=subprocess.DEVNULL,
            )


def read_user_tag_names(path: Path) -> list[str]:
    result = subprocess.run(
        ["xattr", "-px", TAG_ATTR, str(path)],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        return []
    try:
        raw = bytes.fromhex(result.stdout.decode("ascii"))
        values = plistlib.loads(raw)
    except Exception:
        return []
    names = []
    for value in values:
        text = str(value)
        names.append(unicodedata.normalize("NFC", text.split("\n", 1)[0]))
    return names


def read_fs_label(path: Path) -> int | None:
    result = subprocess.run(
        ["mdls", "-raw", "-name", "kMDItemFSLabel", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    text = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    try:
        return int(text)
    except ValueError:
        return None


def apply_root(
    root: Path,
    matrix_by_tic: dict[int, dict[str, str]],
    dashboard_by_tic: dict[int, dict[str, object]],
    dry_run: bool = False,
    verify_only: bool = False,
    labels_only: bool = False,
    tags_only: bool = False,
    verify_finder_labels: bool = False,
) -> dict[str, object]:
    dirs = candidate_dirs(root)
    counts: Counter[str] = Counter()
    paths_by_label: dict[int, list[Path]] = defaultdict(list)

    for path in dirs:
        primary, tag_keys = classify(path, matrix_by_tic, dashboard_by_tic)
        counts[primary] += 1
        if not dry_run and not verify_only and not labels_only:
            set_user_tags(path, tag_keys)
        if not dry_run and not verify_only and not tags_only:
            finder_label = 0 if primary == "none" else TAG_SPECS[primary][2]
            paths_by_label[finder_label].append(path)

    if not dry_run and not verify_only and not tags_only:
        set_finder_labels(paths_by_label)

    missing_tags: list[str] = []
    missing_finder_labels: list[str] = []
    if not dry_run:
        for path in dirs:
            primary, tag_keys = classify(path, matrix_by_tic, dashboard_by_tic)
            expected = [unicodedata.normalize("NFC", TAG_SPECS[key][0]) for key in tag_keys]
            actual = read_user_tag_names(path)
            if actual[: len(expected)] != expected:
                missing_tags.append(f"{path}: expected={expected} actual={actual}")
            if verify_finder_labels:
                expected_label = 0 if primary == "none" else TAG_SPECS[primary][2]
                actual_label = read_fs_label(path)
                if actual_label != expected_label:
                    missing_finder_labels.append(
                        f"{path}: expected_fs_label={expected_label} actual_fs_label={actual_label}"
                    )

    return {
        "root": str(root),
        "total": len(dirs),
        "counts": dict(sorted(counts.items())),
        "missing_tags": missing_tags,
        "missing_finder_labels": missing_finder_labels,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply Finder/iCloud color tags to all LY candidate folders.")
    parser.add_argument("--local-only", action="store_true", help="Only tag the local Level0 tree.")
    parser.add_argument("--icloud-only", action="store_true", help="Only tag the iCloud Level0 mirror.")
    parser.add_argument("--dry-run", action="store_true", help="Count folders without changing tags.")
    parser.add_argument("--verify-only", action="store_true", help="Only verify existing tags without changing tags.")
    parser.add_argument("--labels-only", action="store_true", help="Only set Finder color labels; leave UserTags unchanged.")
    parser.add_argument("--tags-only", action="store_true", help="Only set UserTags; skip Finder label AppleScript.")
    parser.add_argument("--verify-finder-labels", action="store_true", help="Also verify Finder label colors via kMDItemFSLabel.")
    args = parser.parse_args()

    roots = []
    if not args.icloud_only:
        roots.append(LOCAL_LEVEL0)
    if not args.local_only:
        roots.append(ICLOUD_LEVEL0)

    failed = False
    matrix_by_tic = load_matrix_classes()
    dashboard_by_tic = load_dashboard_classes()
    for root in roots:
        result = apply_root(
            root,
            matrix_by_tic,
            dashboard_by_tic,
            dry_run=args.dry_run,
            verify_only=args.verify_only,
            labels_only=args.labels_only,
            tags_only=args.tags_only,
            verify_finder_labels=args.verify_finder_labels,
        )
        print(f"root={result['root']}")
        print(f"total={result['total']}")
        print(f"counts={result['counts']}")
        if result["missing_tags"]:
            failed = True
            print("missing_tags:")
            for item in result["missing_tags"][:50]:
                print(item)
            if len(result["missing_tags"]) > 50:
                print(f"... {len(result['missing_tags']) - 50} more")
        if result["missing_finder_labels"]:
            failed = True
            print("missing_finder_labels:")
            for item in result["missing_finder_labels"][:50]:
                print(item)
            if len(result["missing_finder_labels"]) > 50:
                print(f"... {len(result['missing_finder_labels']) - 50} more")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
