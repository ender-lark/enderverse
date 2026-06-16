"""Feed/file adapter for battery evidence inputs.

The core battery mappers stay pure in ``battery_evidence``. This module owns the
repo-local cache reads and feed-shape normalization used by build-time callers.
It never performs live fetches.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SRC = Path(__file__).resolve().parent
DEFAULT_OPPORTUNITY_SIGNALS_PATH = SRC / "uw_opportunity_signals.json"


def _ticker(value: Any) -> str:
    return str(value or "").upper().strip()


def _coerce_opportunity_cache(
    opportunity_signals: Any,
) -> dict[str, Any]:
    if isinstance(opportunity_signals, dict):
        rows = opportunity_signals.get("signals")
        if isinstance(rows, list):
            return {
                "status": "checked",
                "signals": rows,
                "as_of": opportunity_signals.get("as_of")
                or opportunity_signals.get("generated_at"),
            }
        return {
            "status": "not_checked",
            "signals": [],
            "as_of": opportunity_signals.get("as_of")
            or opportunity_signals.get("generated_at"),
            "reason": "uw_opportunity source unavailable",
        }
    if isinstance(opportunity_signals, list):
        return {"status": "checked", "signals": opportunity_signals, "as_of": None}
    return {
        "status": "not_checked",
        "signals": [],
        "as_of": None,
        "reason": "uw_opportunity source unavailable",
    }


def _load_opportunity_cache(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "not_checked",
            "signals": [],
            "as_of": None,
            "reason": "uw_opportunity source unavailable",
        }
    return _coerce_opportunity_cache(payload)


def _opportunity_for_ticker(
    ticker: str,
    *,
    opportunity_signals: Any = None,
    signals_path: Path | None = None,
) -> dict[str, Any]:
    tick = _ticker(ticker)
    cache = (
        _coerce_opportunity_cache(opportunity_signals)
        if opportunity_signals is not None
        else _load_opportunity_cache(signals_path or DEFAULT_OPPORTUNITY_SIGNALS_PATH)
    )
    if cache.get("status") != "checked":
        return {
            "status": "not_checked",
            "ticker": tick,
            "signals": [],
            "as_of": cache.get("as_of"),
            "reason": cache.get("reason") or "uw_opportunity source unavailable",
        }
    rows = [
        row for row in cache.get("signals") or []
        if isinstance(row, dict) and _ticker(row.get("ticker")) == tick
    ]
    return {
        "status": "checked",
        "ticker": tick,
        "signals": rows,
        "as_of": cache.get("as_of"),
    }


def _holdings_rotation_for_ticker(ticker: str, feed: dict[str, Any]) -> dict[str, Any]:
    tick = _ticker(ticker)
    holdings = feed.get("holdings") if isinstance(feed, dict) else None
    if not isinstance(holdings, list):
        return {"status": "not_checked", "ticker": tick}
    for group in holdings:
        if not isinstance(group, dict):
            continue
        positions = group.get("pos")
        if not isinstance(positions, list):
            continue
        for pos in positions:
            if not isinstance(pos, dict):
                continue
            if _ticker(pos.get("t") or pos.get("ticker")) != tick:
                continue
            rot = group.get("rot") if isinstance(group.get("rot"), dict) else {}
            return {
                "status": "checked",
                "ticker": tick,
                "category": group.get("cat"),
                "rot_w": rot.get("w"),
                "cd": pos.get("cd"),
                "cd_note": pos.get("cdNote"),
            }
    return {"status": "not_checked", "ticker": tick}


def gather_battery_inputs(
    ticker: str,
    feed: dict[str, Any],
    *,
    opportunity_signals: Any = None,
    signals_path: Path | None = None,
) -> dict[str, Any]:
    """Return normalized battery inputs for one ticker from existing data only."""
    tick = _ticker(ticker)
    safe_feed = feed if isinstance(feed, dict) else {}
    return {
        "uw_opportunity": _opportunity_for_ticker(
            tick,
            opportunity_signals=opportunity_signals,
            signals_path=signals_path,
        ),
        "group_rotation": _holdings_rotation_for_ticker(tick, safe_feed),
        "iv_ctx": None,
    }
