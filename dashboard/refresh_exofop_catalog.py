"""Refresh public TOI and confirmed-planet matches without using stale cache.

A failed or incomplete request never becomes a negative catalog result.
"""
from __future__ import annotations

import csv
import io
import urllib.parse
import urllib.request
from datetime import datetime, timezone

TAP_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
TOI_QUERY = "select tid,toi from toi where tid is not null"
PLANET_QUERY = "select tic_id,pl_name from ps where tic_id is not null"


def fetch_csv(query: str, required: set[str]) -> list[dict[str, str]]:
    url = TAP_URL + "?" + urllib.parse.urlencode({"query": query, "format": "csv"})
    with urllib.request.urlopen(url, timeout=90) as response:
        content = response.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ValueError("Archive returned an invalid catalog schema")
    rows = list(reader)
    if not rows:
        raise ValueError("Archive returned an empty catalog")
    return rows


def tic_number(value: object) -> int | None:
    try:
        return int(str(value).strip().removeprefix("TIC").strip())
    except (TypeError, ValueError):
        return None


def fetch_matches() -> tuple[set[int], set[int]]:
    toi_rows = fetch_csv(TOI_QUERY, {"tid", "toi"})
    planet_rows = fetch_csv(PLANET_QUERY, {"tic_id", "pl_name"})
    toi = {number for row in toi_rows if (number := tic_number(row["tid"])) is not None}
    planets = {
        number for row in planet_rows
        if row.get("pl_name") and (number := tic_number(row["tic_id"])) is not None
    }
    return toi, planets


def refresh_catalog(summary: dict, details_dir, stamp: str) -> int:
    # Fetch both catalogs before modifying any files. Exceptions propagate to
    # the caller; an unavailable archive is NOT evidence of a non-match.
    toi, planets = fetch_matches()
    changes = 0
    for item in summary["candidates"]:
        tic = tic_number(item.get("tic"))
        if tic is None:
            continue
        path = details_dir / f"TIC_{tic}.json"
        if not path.is_file():
            continue
        import json
        detail = json.loads(path.read_text(encoding="utf-8"))
        match = tic in toi or tic in planets
        old = detail.get("astroMonitor") or {}
        monitor = {**old}
        if old.get("exoFopMatch") != match or not old.get("exoFopCatalogSource"):
            monitor.update({"exoFopMatch": match, "exoFopCheckedAt": stamp,
                            "exoFopCatalogSource": "NASA Exoplanet Archive TOI + PS"})
        # Keep scientific classification separate: a TIC-level match does not
        # prove that the detected transit belongs to the cataloged planet.
        if monitor != old:
            detail["astroMonitor"] = monitor
            path.write_text(json.dumps(detail, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
            changes += 1
        if "astroMonitor" in item:
            item["astroMonitor"] = monitor
    return changes
