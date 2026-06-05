"""Dark-lane honesty for the cockpit feed.

The feed must distinguish "checked and clear" from "not checked". This module
keeps that distinction structural so the cockpit does not rely on prose.
"""
from __future__ import annotations

from dataclasses import dataclass

STATUS_HAS_DATA = "has_data"
STATUS_CHECKED_CLEAR = "checked_clear"
STATUS_NOT_CHECKED = "not_checked"
STATUS_STALE = "stale"
STATUS_FAILED = "failed"

VALID_STATUSES = {
    STATUS_HAS_DATA,
    STATUS_CHECKED_CLEAR,
    STATUS_NOT_CHECKED,
    STATUS_STALE,
    STATUS_FAILED,
}

SOURCE_LABELS = {
    "portfolio": "Portfolio",
    "uw_price": "Prices",
    "uw_macro": "Macro",
    "fundstrat_bible": "FS Bible",
    "fundstrat_daily": "FS Daily",
}

EXTERNAL_LANES = {
    "catalysts": "Catalysts",
    "research": "Research Queue",
    "synthesis": "Daily Synthesis",
    "uw_opportunity": "UW Flow",
    "top_prospects": "Top Prospects",
    "target_drift": "Target Drift",
}


@dataclass(frozen=True)
class LaneInput:
    key: str
    label: str
    value: object


def _is_empty(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, dict):
        if len(value) == 0:
            return True
        return all(_is_empty(v) for v in value.values())
    if isinstance(value, (list, tuple, set, dict, str)):
        return len(value) == 0
    return False


def _count(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, dict):
        for key in ("signals", "rows", "items", "pending", "hot"):
            rows = value.get(key)
            if isinstance(rows, list):
                return len(rows)
        return len(value)
    if isinstance(value, (list, tuple, set)):
        return len(value)
    return 1


def _row(key: str, label: str, status: str, *, detail: str = "", count: int = 0,
         checked_at: str | None = None) -> dict:
    return {
        "key": key,
        "label": label,
        "status": status,
        "detail": detail,
        "count": count,
        "checked_at": checked_at or "",
    }


def source_rows(snapshot: dict, staleness: dict) -> list[dict]:
    """Rows for first-party collected sources."""
    ok = set(snapshot.get("sources_ok") or [])
    failed = {
        f.get("name"): f.get("error", "")
        for f in (snapshot.get("sources_failed") or [])
        if isinstance(f, dict) and f.get("name")
    }
    stale = set(staleness.get("stale") or [])
    dates = snapshot.get("staleness") or {}
    keys = list(dict.fromkeys([*SOURCE_LABELS.keys(), *ok, *failed.keys(), *dates.keys()]))

    rows = []
    for key in keys:
        label = SOURCE_LABELS.get(key, key)
        if key in failed:
            rows.append(_row(key, label, STATUS_FAILED, detail=str(failed[key])))
        elif key in stale:
            rows.append(_row(key, label, STATUS_STALE, detail="past freshness window"))
        elif key in ok:
            rows.append(_row(key, label, STATUS_HAS_DATA, detail="checked"))
        else:
            rows.append(_row(key, label, STATUS_NOT_CHECKED, detail="not checked"))
    return rows


def external_rows(**lanes: object) -> list[dict]:
    """Rows for optional cockpit lanes supplied by routines/caches."""
    rows = []
    for key, label in EXTERNAL_LANES.items():
        value = lanes.get(key)
        if value is None:
            rows.append(_row(key, label, STATUS_NOT_CHECKED, detail="not supplied"))
        elif _is_empty(value):
            rows.append(_row(key, label, STATUS_CHECKED_CLEAR, detail="checked clear"))
        else:
            rows.append(_row(key, label, STATUS_HAS_DATA, detail="checked", count=_count(value)))
    return rows


def build_lane_status(snapshot: dict, staleness: dict, **lanes: object) -> dict:
    rows = source_rows(snapshot or {}, staleness or {}) + external_rows(**lanes)
    counts = {status: 0 for status in VALID_STATUSES}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {
        "rows": rows,
        "counts": counts,
        "has_dark_lanes": counts.get(STATUS_NOT_CHECKED, 0) > 0,
        "has_stale_or_failed": (
            counts.get(STATUS_STALE, 0) + counts.get(STATUS_FAILED, 0)
        ) > 0,
    }
