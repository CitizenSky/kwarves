#!/usr/bin/env python3
from __future__ import annotations

import argparse
import plistlib
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

TAG_ATTR = "com.apple.metadata:_kMDItemUserTags"

# Apple tag payload color numbers differ from Finder's AppleScript label index.
# The first tag is the visible primary color in iOS Files.
TAG_SPECS = {
    "red": ("Rot", 6, 2),
    "yellow": ("Gelb", 5, 3),
    "green": ("Gr\u00fcn", 2, 6),
    "purple": ("Violett", 3, 5),
}


def candidate_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    dirs: list[Path] = []
    for range_dir in sorted(root.glob("*_ly")):
        if not range_dir.is_dir():
            continue
        dirs.extend(sorted(p for p in range_dir.iterdir() if p.is_dir() and "TIC_" in p.name))
    return dirs


def classify(path: Path) -> tuple[str, list[str]]:
    name = path.name
    if name.startswith("RED_"):
        primary = "red"
    elif name.startswith("YELLOW_INFO"):
        primary = "yellow"
    elif "HZ_PURPLE" in name:
        primary = "purple"
    elif name.startswith("SPC_GREEN"):
        primary = "green"
    else:
        primary = "none"

    tags: list[str] = []
    if primary != "none":
        tags.append(primary)
    if "HZ_PURPLE" in name and "purple" not in tags:
        tags.append("purple")
    if name.startswith("SPC_GREEN") and "green" not in tags:
        tags.append("green")
    return primary, tags


def tag_payload(tag_keys: list[str]) -> bytes:
    tag_values = []
    for key in tag_keys:
        name, color_code, _finder_label = TAG_SPECS[key]
        tag_values.append(f"{name}\n{color_code}")
    return plistlib.dumps(tag_values, fmt=plistlib.FMT_BINARY)


def set_user_tags(path: Path, tag_keys: list[str]) -> None:
    if not tag_keys:
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
    dry_run: bool = False,
    verify_only: bool = False,
    labels_only: bool = False,
    verify_finder_labels: bool = False,
) -> dict[str, object]:
    dirs = candidate_dirs(root)
    counts: Counter[str] = Counter()
    unclassified: list[str] = []
    paths_by_label: dict[int, list[Path]] = defaultdict(list)

    for path in dirs:
        primary, tag_keys = classify(path)
        counts[primary] += 1
        if primary == "none":
            unclassified.append(str(path))
            continue
        if not dry_run and not verify_only and not labels_only:
            set_user_tags(path, tag_keys)
        if not dry_run and not verify_only:
            _tag_name, _color_code, finder_label = TAG_SPECS[primary]
            paths_by_label[finder_label].append(path)

    if not dry_run and not verify_only:
        set_finder_labels(paths_by_label)

    missing_tags: list[str] = []
    missing_finder_labels: list[str] = []
    if not dry_run:
        for path in dirs:
            primary, tag_keys = classify(path)
            if primary == "none":
                continue
            expected = [unicodedata.normalize("NFC", TAG_SPECS[key][0]) for key in tag_keys]
            actual = read_user_tag_names(path)
            if actual[: len(expected)] != expected:
                missing_tags.append(f"{path}: expected={expected} actual={actual}")
            if verify_finder_labels:
                _tag_name, expected_label, _finder_label = TAG_SPECS[primary]
                actual_label = read_fs_label(path)
                if actual_label != expected_label:
                    missing_finder_labels.append(
                        f"{path}: expected_fs_label={expected_label} actual_fs_label={actual_label}"
                    )

    return {
        "root": str(root),
        "total": len(dirs),
        "counts": dict(sorted(counts.items())),
        "unclassified": unclassified,
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
    parser.add_argument("--verify-finder-labels", action="store_true", help="Also verify Finder label colors via kMDItemFSLabel.")
    args = parser.parse_args()

    roots = []
    if not args.icloud_only:
        roots.append(LOCAL_LEVEL0)
    if not args.local_only:
        roots.append(ICLOUD_LEVEL0)

    failed = False
    for root in roots:
        result = apply_root(
            root,
            dry_run=args.dry_run,
            verify_only=args.verify_only,
            labels_only=args.labels_only,
            verify_finder_labels=args.verify_finder_labels,
        )
        print(f"root={result['root']}")
        print(f"total={result['total']}")
        print(f"counts={result['counts']}")
        if result["unclassified"]:
            failed = True
            print("unclassified:")
            for item in result["unclassified"]:
                print(item)
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
