#!/usr/bin/env python3
"""Refresh Kwarves split dashboard data and publish changed dashboard files."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = SCRIPT_ROOT / "dashboard" / "candidates-summary.json"
DETAILS_DIR = SCRIPT_ROOT / "dashboard" / "candidate-details"
NOTIFICATION_PATH = SCRIPT_ROOT / "dashboard" / "dashboard-notifications.js"
TRACKED_OUTPUTS = [
    "dashboard/candidates-summary.json",
    "dashboard/candidate-details",
    "dashboard/dashboard-notifications.js",
    "dashboard/gaia_coordinates_cache.csv",
]
WATCHED_FIELDS = [
    "rank",
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
    "observedSectors",
    "newSectors",
    "followupStrength",
    "lastUpdated",
    "lastSectorAdded",
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


def load_dashboard_candidates() -> dict:
    candidates: list[dict] = []
    if DETAILS_DIR.exists():
        for detail_path in sorted(DETAILS_DIR.glob("TIC_*.json")):
            try:
                candidate = json.loads(detail_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if candidate.get("tic"):
                candidates.append(candidate)
    generated_at = datetime.now().isoformat(timespec="seconds")
    if SUMMARY_PATH.exists():
        try:
            generated_at = json.loads(SUMMARY_PATH.read_text(encoding="utf-8")).get("generatedAt") or generated_at
        except Exception:
            pass
    return {"generatedAt": generated_at, "candidates": candidates}


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
    types = set(item.get("types") or [item.get("type")])
    changes = {change["field"] for change in item.get("changes", [])}
    if status == "LIVE_NOW" or "UPGRADED" in types or "DOWNGRADED" in types or "color" in changes or "matrixStatus" in changes or "matrixClass" in changes:
        return "high"
    if status in {"UPCOMING", "WAITING_DATA"} or "NEW_DATA" in types or "RANK_CHANGED" in types or "evidenceScore" in changes:
        return "medium"
    return "low"


def notification_types(previous: dict | None, candidate: dict, changes: list[dict]) -> list[str]:
    types: list[str] = []
    fields = {change["field"] for change in changes}
    if previous is None:
        types.append("NEW_CANDIDATE")
    if changes:
        types.append("UPDATED")
    if candidate.get("newSectors") or "lastSectorAdded" in fields or "last_sector_added" in fields or "observedSectors" in fields:
        types.append("NEW_DATA")
    old_rank = previous.get("rank") if previous else candidate.get("rankPrevious")
    new_rank = candidate.get("rank")
    try:
        old_rank_i = int(old_rank)
        new_rank_i = int(new_rank)
    except Exception:
        old_rank_i = None
        new_rank_i = None
    if old_rank_i is not None and new_rank_i is not None and old_rank_i != new_rank_i:
        types.append("RANK_CHANGED")
        types.append("UPGRADED" if new_rank_i < old_rank_i else "DOWNGRADED")
    elif "rank" in fields:
        types.append("RANK_CHANGED")
    return list(dict.fromkeys(types))


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
        types = notification_types(previous, candidate, changes)
        if types or new_sectors:
            item = {
                "tic": candidate.get("tic"),
                "type": types[0] if types else ("NEW_CANDIDATE" if not previous else "REVALUATION"),
                "types": types,
                "status": candidate.get("status"),
                "matrixStatus": candidate.get("matrixStatus"),
                "matrixClass": candidate.get("matrixClass"),
                "color": candidate.get("color"),
                "baseColorLabel": candidate.get("baseColorLabel"),
                "isViolet": candidate.get("isViolet", False),
                "hz": candidate.get("hz"),
                "evidenceScore": candidate.get("evidenceScore"),
                "scorePrevious": candidate.get("scorePrevious") or candidate.get("score_previous"),
                "rank": candidate.get("rank"),
                "rankPrevious": candidate.get("rankPrevious") or candidate.get("rank_previous"),
                "recheckStatus": recheck_status,
                "currentSector": candidate.get("currentSector"),
                "nextPlannedSector": candidate.get("nextPlannedSector"),
                "estimatedDataAvailable": candidate.get("estimatedDataAvailable"),
                "lastUpdated": candidate.get("lastUpdated") or candidate.get("last_updated"),
                "lastSectorAdded": candidate.get("lastSectorAdded") or candidate.get("last_sector_added"),
                "newSectors": new_sectors,
                "changes": changes,
                "summary": (
                    f"TIC {candidate.get('tic')}: {recheck_status}; "
                    f"Rank {candidate.get('rankPrevious') or '-'} → {candidate.get('rank') or '-'}; "
                    f"Score {candidate.get('scorePrevious') or '-'} → {candidate.get('evidenceScore', '-')}; "
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
            "updated": sum(1 for item in items if "UPDATED" in (item.get("types") or [])),
            "newData": sum(1 for item in items if "NEW_DATA" in (item.get("types") or [])),
            "rankChanged": sum(1 for item in items if "RANK_CHANGED" in (item.get("types") or [])),
            "upgraded": sum(1 for item in items if "UPGRADED" in (item.get("types") or [])),
            "downgraded": sum(1 for item in items if "DOWNGRADED" in (item.get("types") or [])),
        },
    }


def write_notifications(payload: dict) -> None:
    text = "window.ASTRO_DASHBOARD_NOTIFICATIONS = "
    text += json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    text += ";\n"
    NOTIFICATION_PATH.write_text(text, encoding="utf-8")


def main() -> int:
    before = load_dashboard_candidates()
    run(["python3", "dashboard/build_dashboard_data.py"])
    after = load_dashboard_candidates()
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
