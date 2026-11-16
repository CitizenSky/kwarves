"""Refresh public TOI and confirmed-planet matches without using stale cache.

A failed or incomplete request never becomes a negative catalog result.
"""
from __future__ import annotations

import csv
import io
import urllib.parse
import urllib.request

TAP_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
TOI_QUERY = "select tid,toi,pl_orbper from toi where tid is not null"
PLANET_QUERY = "select tic_id,pl_name,pl_orbper from ps where tic_id is not null"


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


def fetch_matches() -> dict[int, list[dict]]:
    toi_rows = fetch_csv(TOI_QUERY, {"tid", "toi", "pl_orbper"})
    planet_rows = fetch_csv(PLANET_QUERY, {"tic_id", "pl_name", "pl_orbper"})
    matches: dict[int, list[dict]] = {}
    for rows, tic_field, name_field, source in (
        (toi_rows, "tid", "toi", "TOI"),
        (planet_rows, "tic_id", "pl_name", "CONFIRMED"),
    ):
        for row in rows:
            tic = tic_number(row.get(tic_field))
            if tic is None:
                continue
            try:
                period = float(row["pl_orbper"])
                if not (0 < period < float("inf")):
                    period = None
            except (TypeError, ValueError):
                period = None
            matches.setdefault(tic, []).append({
                "source": source, "name": str(row.get(name_field) or ""),
                "periodDays": period,
            })
    return matches


def compare_period(candidate_period: object, matches: list[dict]) -> str:
    if not matches:
        return "NO_HOST_MATCH"
    try:
        period = float(candidate_period)
        if not (0 < period < float("inf")):
            return "PERIOD_NOT_AVAILABLE"
    except (TypeError, ValueError):
        return "PERIOD_NOT_AVAILABLE"
    known = [m["periodDays"] for m in matches if m["periodDays"] is not None]
    if not known:
        return "CATALOG_PERIOD_NOT_AVAILABLE"
    # Preliminary tolerance only; harmonics and period aliases require manual vetting.
    if any(abs(period - known_period) / known_period <= 0.001 for known_period in known):
        return "PERIOD_MATCH_REVIEW_REQUIRED"
    return "DIFFERENT_PERIOD_REVIEW_REQUIRED"


def refresh_catalog(summary: dict, details_dir, stamp: str) -> int:
    # Fetch both catalogs before modifying any files. Exceptions propagate to
    # the caller; an unavailable archive is NOT evidence of a non-match.
    matches_by_tic = fetch_matches()
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
        matches = matches_by_tic.get(tic, [])
        match = bool(matches)
        period_status = compare_period(detail.get("period"), matches)
        old = detail.get("astroMonitor") or {}
        monitor = {**old}
        if (old.get("exoFopMatch") != match or
                old.get("exoFopPeriodStatus") != period_status or
                not old.get("exoFopCatalogSource")):
            monitor.update({"exoFopMatch": match, "exoFopPeriodStatus": period_status,
                            "exoFopCatalogEntries": matches,
                            "exoFopCheckedAt": stamp,
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
