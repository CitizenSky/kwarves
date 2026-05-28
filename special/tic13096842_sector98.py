#!/usr/bin/env python3
"""Single entry point for TIC 13096842 Sector-98 analyses.

The original Sector-98 scripts are kept in the archive so older results remain
reproducible. This runner exposes the useful workflow through one command.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ARCHIVE_DIR = SCRIPT_DIR.parents[1] / "archive" / "scripts" / "2026-05-21_cleanup" / "tic13096842"
ARCHIVE_BUNDLE = ARCHIVE_DIR / "sector98_original_scripts.tar.gz"

ARCHIVED_SCRIPTS = {
    "reanalyse": "sector98_reanalyse_13096842.py",
    "model": "sector98_model_fit_13096842.py",
    "joint": "sector98_joint_transit_fit_13096842.py",
    "strict": "sector98_strict_joint_fit_13096842.py",
    "robustness": "sector98_robustness_13096842.py",
}

DEFAULT_SEQUENCE = ["reanalyse", "strict", "robustness"]
FULL_SEQUENCE = ["reanalyse", "model", "joint", "strict", "robustness"]


def run_archived(step: str) -> None:
    script_name = ARCHIVED_SCRIPTS[step]
    loose_path = ARCHIVE_DIR / script_name

    if loose_path.exists():
        print(f"\n=== TIC 13096842 Sector 98: {step} ({script_name}) ===", flush=True)
        subprocess.run([sys.executable, str(loose_path)], check=True)
        return

    if not ARCHIVE_BUNDLE.exists():
        raise FileNotFoundError(f"Sector-98 archive bundle not found: {ARCHIVE_BUNDLE}")

    with tempfile.TemporaryDirectory(prefix="sector98_") as tmpdir:
        tmp_path = Path(tmpdir) / script_name
        with tarfile.open(ARCHIVE_BUNDLE, "r:gz") as tar:
            member = tar.getmember(script_name)
            source = tar.extractfile(member)
            if source is None:
                raise FileNotFoundError(f"{script_name} not found inside {ARCHIVE_BUNDLE}")
            tmp_path.write_bytes(source.read())

        print(f"\n=== TIC 13096842 Sector 98: {step} ({script_name}) ===", flush=True)
        subprocess.run([sys.executable, str(tmp_path)], check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run TIC 13096842 Sector-98 analysis steps.")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("reanalyse", help="Run the Sector-98 reanalysis and event extraction.")

    fit_parser = subparsers.add_parser("fit", help="Run one of the Sector-98 transit-fit variants.")
    fit_parser.add_argument(
        "--mode",
        choices=("model", "joint", "strict"),
        default="strict",
        help="Fit mode to run. Default: strict.",
    )

    subparsers.add_parser("robustness", help="Run robustness checks across detrending/clip variants.")
    subparsers.add_parser("default", help="Run the focused default sequence: reanalyse, strict fit, robustness.")
    subparsers.add_parser("all", help="Run every archived Sector-98 step.")
    subparsers.add_parser("list", help="List available Sector-98 steps and archived files.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    command = args.command or "list"

    if command == "list":
        for step, script_name in ARCHIVED_SCRIPTS.items():
            print(f"{step:12s} {script_name}")
        print("\ndefault sequence:", ", ".join(DEFAULT_SEQUENCE))
        print("full sequence:   ", ", ".join(FULL_SEQUENCE))
        return

    if command == "reanalyse":
        run_archived("reanalyse")
    elif command == "fit":
        run_archived(args.mode)
    elif command == "robustness":
        run_archived("robustness")
    elif command == "default":
        for step in DEFAULT_SEQUENCE:
            run_archived(step)
    elif command == "all":
        for step in FULL_SEQUENCE:
            run_archived(step)
    else:
        raise SystemExit("Unknown command. Use 'list' to show available steps.")


if __name__ == "__main__":
    main()
