#!/usr/bin/env python3
"""Refresh Kwarves dashboard data and publish changed dashboard files."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = SCRIPT_ROOT / "dashboard" / "dashboard-data.js"
NOTIFICATION_PATH = SCRIPT_ROOT / "dashboard" / "dashboard-notifications.js"
TRACKED_OUTPUTS = [
    "dashboard/dashboard-data.js",
    "dashboard/dashboard-notifications.js",
    "dashboard/gaia_coordinates_cache.csv",
]
WATCHED_FIELDS = [
    "color",
    "baseColorLabel",
    "colorLabel",
    "status",
    "matrixStatus",
    "matrixClass",
    "matrixScoreBand",
    "evidenceScore",
    "recheckStatus",
    "currentSector",
    "nextPlannedSector",
    "estimatedDataAvailable",
    "observedSectorCount",
    "followupStrength",
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


def load_dashboard_data() -> dict:
    if not DATA_PATH.exists():
        return {}
    text = DATA_PATH.read_text(encoding="utf-8")
    match = re.search(r"window\.ASTRO_DASHBOARD_DATA\s*=\s*(\{.*\});?\s*$", text, re.S)
    if not match:
        return {}
    return json.loads(match.group(1))


def candidate_index(payload: dict) -> dict[str, dict]:
    return {str(item.get("tic")): item for item in payload.get("candidates", []) if item.get("tic")}


def sector_text(sectors: list[int] | None) -> str:
    values = [f"S{sector}" for sector in sectors or []]
    return ", ".join(values) if values else "-"


def field_changes(before: dict, after: dict) -> list[dict]:
    changes: list[dict] = []
    for field in WATCHED_FIELDS:
        old = before.get(field)
        new = after.get(field)
        if old != new:
            changes.append({"field": field, "before": old, "after": new})
    return changes


def notification_severity(item: dict) -> str:
    status = str(item.get("recheckStatus") or "")
    changes = {change["field"] for change in item.get("changes", [])}
    if status == "LIVE_NOW" or "color" in changes or "matrixStatus" in changes or "matrixClass" in changes:
        return "high"
    if status in {"UPCOMING", "WAITING_DATA"} or "evidenceScore" in changes:
        return "medium"
    return "low"


def build_notifications(before: dict, after: dict) -> dict:
    old = candidate_index(before)
    new = candidate_index(after)
    generated_at = after.get("generatedAt") or datetime.now().isoformat(timespec="seconds")
    items: list[dict] = []

    for tic, candidate in new.items():
        previous = old.get(tic)
        changes = field_changes(previous or {}, candidate)
        new_sectors = candidate.get("newSectors") or []
        recheck_status = candidate.get("recheckStatus") or "NO_PLANNED_RECHECK"
        if not previous or changes or new_sectors:
            item = {
                "tic": candidate.get("tic"),
                "type": "NEW_CANDIDATE" if not previous else "REVALUATION",
                "status": candidate.get("status"),
                "matrixStatus": candidate.get("matrixStatus"),
                "matrixClass": candidate.get("matrixClass"),
                "color": candidate.get("color"),
                "baseColorLabel": candidate.get("baseColorLabel"),
                "isViolet": candidate.get("isViolet", False),
                "hz": candidate.get("hz"),
                "evidenceScore": candidate.get("evidenceScore"),
                "recheckStatus": recheck_status,
                "currentSector": candidate.get("currentSector"),
                "nextPlannedSector": candidate.get("nextPlannedSector"),
                "estimatedDataAvailable": candidate.get("estimatedDataAvailable"),
                "newSectors": new_sectors,
                "changes": changes,
                "summary": (
                    f"TIC {candidate.get('tic')}: {recheck_status}; "
                    f"Score {candidate.get('evidenceScore', '-')}; "
                    f"neue Sektoren {sector_text(new_sectors)}"
                ),
            }
            item["severity"] = notification_severity(item)
            items.append(item)

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda item: (
        severity_rank.get(item.get("severity"), 3),
        -float(item.get("evidenceScore") or 0),
        int(item.get("tic") or 0),
    ))
    visible_items = items[:80]
    return {
        "generatedAt": generated_at,
        "total": len(items),
        "items": visible_items,
        "counts": {
            "high": sum(1 for item in items if item.get("severity") == "high"),
            "medium": sum(1 for item in items if item.get("severity") == "medium"),
            "low": sum(1 for item in items if item.get("severity") == "low"),
            "liveNow": sum(1 for item in items if item.get("recheckStatus") == "LIVE_NOW"),
            "upcoming": sum(1 for item in items if item.get("recheckStatus") == "UPCOMING"),
            "waitingData": sum(1 for item in items if item.get("recheckStatus") == "WAITING_DATA"),
            "newSectorHits": sum(1 for item in items if item.get("newSectors")),
        },
    }


def write_notifications(payload: dict) -> None:
    text = "window.ASTRO_DASHBOARD_NOTIFICATIONS = "
    text += json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    text += ";\n"
    NOTIFICATION_PATH.write_text(text, encoding="utf-8")


def main() -> int:
    before = load_dashboard_data()
    run(["python3", "dashboard/build_dashboard_data.py"])
    after = load_dashboard_data()
    write_notifications(build_notifications(before, after))

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
