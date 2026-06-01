#!/usr/bin/env python3
"""Refresh Kwarves dashboard data and publish changed dashboard files."""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parents[1]
TRACKED_OUTPUTS = [
    "dashboard/dashboard-data.js",
    "dashboard/gaia_coordinates_cache.csv",
]


def run(command: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(command))
    return subprocess.run(
        command,
        cwd=SCRIPT_ROOT,
        text=True,
        stdout=None,
        stderr=None,
        check=check,
    )


def changed_tracked_outputs() -> list[str]:
    result = subprocess.run(
        ["git", "status", "--short", "--", *TRACKED_OUTPUTS],
        cwd=SCRIPT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    changed: list[str] = []
    for line in result.stdout.splitlines():
        path = line[3:].strip()
        if path:
            changed.append(path)
    return changed


def current_branch() -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=SCRIPT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip() or "main"


def main() -> int:
    run(["python3", "dashboard/build_dashboard_data.py"])

    changed = changed_tracked_outputs()
    if not changed:
        print("No dashboard data changes to publish.")
        return 0

    run(["git", "add", *changed])
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    run(["git", "commit", "-m", f"Auto-update dashboard data {stamp}"])
    run(["git", "push", "origin", current_branch()])
    print("Dashboard data updated and pushed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
