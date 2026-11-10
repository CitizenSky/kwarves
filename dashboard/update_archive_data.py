#!/usr/bin/env python3
"""Refresh archive metadata in the published dashboard without the local database."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from auto_update_and_publish import build_notifications, write_notifications


DASHBOARD = Path(__file__).resolve().parent
sys.path.insert(0, str(DASHBOARD.parent / "main"))

from check_new_tess_sectors import DEFAULT_SOURCE_STATUSES
from watch_astro_data import PROJECT_GAIA_RELEASE, fetch_gaia_release, fetch_tess_sectors


class ArchiveUnavailable(RuntimeError):
    pass


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def refresh_tess(summary: dict, stamp: str) -> int:
    candidates = [item for item in summary["candidates"] if item.get("status") in DEFAULT_SOURCE_STATUSES]
    try:
        available = fetch_tess_sectors([item["tic"] for item in candidates])
    except (OSError, RuntimeError) as exc:
        raise ArchiveUnavailable(str(exc)) from exc
    before, after = [], []
    for item in candidates:
        previous = set(item.get("observedSectors") or [])
        added = available[item["tic"]] - previous
        if not added:
            continue

        path = DASHBOARD / "candidate-details" / f"TIC_{item['tic']}.json"
        detail = json.loads(path.read_text(encoding="utf-8"))
        if detail.get("tic") != item["tic"] or set(detail.get("observedSectors") or []) != previous:
            raise ValueError(f"Summary and detail disagree for TIC {item['tic']}")

        current = sorted(previous | added)
        updates = {
            "observedSectors": current,
            "observedSectorCount": len(current),
            "newSectors": sorted(added),
        }
        history = [*(detail.get("updateHistory") or []), {
            "checkedAt": stamp,
            "event": "TESS_ARCHIVE_UPDATE",
            "newSectors": sorted(added),
            "changes": [{"field": "observedSectors", "before": sorted(previous), "after": current}],
        }][-20:]
        before.append(detail)
        after.append((path, {
            **detail, **updates,
            "previousSectors": sorted(previous),
            "previousSectorCount": len(previous),
            "sectorInventoryStatus": "RECHECK_NEW_SECTOR",
            "sectorLastCheckedAt": stamp,
            "sectorLastNewAt": stamp,
            "lastSectorAdded": max(added),
            "last_sector_added": max(added),
            "lastUpdated": stamp,
            "last_updated": stamp,
            "updateStatus": "UPDATED",
            "update_status": "UPDATED",
            "updateHistory": history,
            "update_history": history,
        }))
        item.update(updates)

    for path, detail in after:
        write_json(path, detail)
    if after:
        write_notifications(build_notifications(
            {"candidates": before},
            {"generatedAt": stamp, "candidates": [detail for _, detail in after]},
        ))
    print(f"TESS: checked {len(candidates)} TICs, updated {len(after)}", flush=True)
    return len(after)


def refresh_gaia(summary: dict) -> bool:
    try:
        release = fetch_gaia_release()
    except (OSError, RuntimeError) as exc:
        raise ArchiveUnavailable(str(exc)) from exc
    state = summary.get("archiveWatch", {})
    previous = state.get("latestGaiaRelease", PROJECT_GAIA_RELEASE)
    print(f"Gaia: newest public source catalogue is DR{release}", flush=True)
    if release <= previous:
        return False
    state["latestGaiaRelease"] = release
    summary["archiveWatch"] = state
    print(f"::warning::Gaia DR{release} is available. Import requires a cross-match of source IDs.", flush=True)
    return True


def main() -> int:
    path = DASHBOARD / "candidates-summary.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    changed = False
    failures = 0
    for source, refresh in (("Gaia", lambda: refresh_gaia(summary)), ("TESS", lambda: refresh_tess(summary, stamp))):
        try:
            changed = bool(refresh()) or changed
        except ArchiveUnavailable as exc:
            print(f"::warning::{source} archive unavailable: {exc}", flush=True)
            failures += 1
    if changed:
        summary["generatedAt"] = stamp
        write_json(path, summary)
    return int(failures == 2)


if __name__ == "__main__":
    raise SystemExit(main())
