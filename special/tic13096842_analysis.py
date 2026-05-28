#!/usr/bin/env python3
"""Central runner for the TIC 13096842 detail-analysis scripts.

The original single-purpose scripts are kept in the archive for
reproducibility. This wrapper keeps the active scripts folder small while
preserving the old analysis entry points.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ARCHIVE_DIR = SCRIPT_DIR.parents[1] / "archive" / "scripts" / "2026-05-21_cleanup" / "tic13096842"
SECTOR98_RUNNER = SCRIPT_DIR / "tic13096842_sector98.py"

STEPS = {
    "ttv-focus": "ttv_focus_13096842.py",
    "resonance-search": "ttv_resonance_search_13096842.py",
    "confirmation-check": "confirmation_check_13096842.py",
}

SECTOR98_STEPS = {
    "sector98": ["default"],
    "sector98-all": ["all"],
    "reanalyse": ["reanalyse"],
    "model-fit": ["fit", "--mode", "model"],
    "joint-fit": ["fit", "--mode", "joint"],
    "strict-joint-fit": ["fit", "--mode", "strict"],
    "robustness": ["robustness"],
}

DEFAULT_PIPELINE = [
    "sector98",
    "ttv-focus",
    "resonance-search",
    "confirmation-check",
]


def run_step(name: str) -> None:
    if name in SECTOR98_STEPS:
        if not SECTOR98_RUNNER.exists():
            raise FileNotFoundError(f"Sector-98 runner not found: {SECTOR98_RUNNER}")
        print(f"\n=== TIC 13096842: {name} via {SECTOR98_RUNNER.name} ===", flush=True)
        subprocess.run([sys.executable, str(SECTOR98_RUNNER), *SECTOR98_STEPS[name]], check=True)
        return

    script_name = STEPS[name]
    script_path = ARCHIVE_DIR / script_name
    if not script_path.exists():
        raise FileNotFoundError(f"Archived script not found: {script_path}")

    print(f"\n=== TIC 13096842: {name} ({script_name}) ===", flush=True)
    subprocess.run([sys.executable, str(script_path)], check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run archived TIC 13096842 Sector-98/TTV analysis steps."
    )
    parser.add_argument(
        "steps",
        nargs="*",
        help="Step(s) to run. Use 'all' for the default focused pipeline.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available steps and exit.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.list:
        for name, sector_args in SECTOR98_STEPS.items():
            print(f"{name:20s} {SECTOR98_RUNNER.name} {' '.join(sector_args)}")
        for name, script_name in STEPS.items():
            print(f"{name:20s} {script_name}")
        return

    selected = args.steps or ["all"]
    valid_steps = set(STEPS) | set(SECTOR98_STEPS) | {"all"}
    unknown_steps = [step for step in selected if step not in valid_steps]
    if unknown_steps:
        raise SystemExit(
            "Unknown step(s): "
            + ", ".join(unknown_steps)
            + "\nUse --list to show available steps."
        )

    if "all" in selected:
        selected = DEFAULT_PIPELINE

    for step in selected:
        run_step(step)


if __name__ == "__main__":
    main()
