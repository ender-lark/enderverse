#!/usr/bin/env python3
"""Operator-facing hardening panels for the Investing OS dashboard."""
from __future__ import annotations

from datetime import date
from typing import Any


def _text(value: Any) -> str:
    return str(value).strip() if value not in (None, "", [], {}) else ""


def freshness_downgrade_audit(feed: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for action in feed.get("actions") or []:
        if not isinstance(action, dict):
            continue
        freshness = action.get("freshness_judgment") or {}
        judgment = _text(freshness.get("judgment"))
        label = _text(freshness.get("label"))
        action_state = _text(action.get("action_state"))
        action_label = _text(action.get("action_label"))
        is_recheck = (
            action_label.upper() == "RE-CHECK"
            or "re-check" in judgment.lower()
            or label in {"stale", "not checked"}
        )
        if not is_recheck:
            continue
        rows.append({
            "ticker": action.get("ticker") or "EVENT",
            "kind": action.get("kind") or "",
            "what": action.get("what") or "",
            "action_state": action_state,
            "action_label": action_label,
            "freshness_label": label,
            "evidence_date": freshness.get("evidence_date") or "",
            "last_checked": freshness.get("last_checked") or "",
            "decay_window": freshness.get("decay_window") or "",
            "judgment": judgment,
        })
    return {
        "status": "has_data" if rows else "checked_clear",
        "count": len(rows),
        "line": (
            f"Freshness downgrade audit: {len(rows)} action(s) require re-check before capital action."
            if rows else
            "Freshness downgrade audit: no action was downgraded or gated by stale evidence."
        ),
        "rows": rows,
    }


def stale_action_cleanup(feed: dict[str, Any] | None) -> dict[str, Any]:
    feedback = ((feed or {}).get("feedback") or {}).get("open_actions") or {}
    items = feedback.get("items") or []
    rows = []
    for row in items:
        if not isinstance(row, dict):
            continue
        age = int(row.get("age_days") or 0)
        stale = age >= 5
        due = age >= 3
        if not (stale or due):
            continue
        rows.append({
            "ticker": row.get("ticker") or "",
            "kind": row.get("kind") or "",
            "age_days": age,
            "state": "stale" if stale else "due",
            "next_step": (
                "Resolve stale item: acted, invalidated, missed, ignored, or explicitly deferred."
                if stale else
                "Review due item before it becomes stale."
            ),
        })
    return {
        "status": "has_data" if rows else "checked_clear",
        "count": len(rows),
        "line": (
            f"Stale-action cleanup: {len(rows)} due/stale open review(s)."
            if rows else
            "Stale-action cleanup: no due or stale open reviews."
        ),
        "rows": rows,
    }


def condition_checklist(feed: dict[str, Any], *, as_of: str | None = None) -> dict[str, Any]:
    today = str(as_of or date.today().isoformat())[:10]
    rows = []
    for row in feed.get("event_risk") or []:
        if not isinstance(row, dict):
            continue
        rows.append({
            "source": "event_risk",
            "ticker": ", ".join(str(t) for t in row.get("tickers") or []),
            "date": row.get("date") or "",
            "title": row.get("title") or "Event risk",
            "check": row.get("trigger") or row.get("summary") or "Re-check headline/level confirmation.",
            "why": "Fast-moving event evidence can expire before the next market session.",
        })
    latest_radar = sorted(
        [row for row in feed.get("radar") or [] if isinstance(row, dict)],
        key=lambda row: str(row.get("date") or ""),
        reverse=True,
    )
    for row in latest_radar[:5]:
        quote = _text(row.get("quote"))
        if not quote:
            continue
        rows.append({
            "source": "fundstrat_daily",
            "ticker": row.get("ticker") or "",
            "date": row.get("date") or "",
            "title": f"{row.get('ticker') or ''} {row.get('direction') or 'watch'}".strip(),
            "check": quote,
            "why": "Use as a pre-market condition check, not as an automatic trade.",
        })
    return {
        "status": "has_data" if rows else "checked_clear",
        "date": today,
        "line": (
            f"Condition checklist: {len(rows)} pre-action level/headline check(s)."
            if rows else
            "Condition checklist: no pre-action checks in current feed."
        ),
        "rows": rows[:8],
    }


def watch_only_why(feed: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for row in feed.get("signal_log") or []:
        if not isinstance(row, dict):
            continue
        rows.append({
            "ticker": row.get("ticker") or row.get("subject") or "",
            "title": row.get("signal") or row.get("title") or "",
            "source": "signal_log",
            "why_not_acting": "Signal Log is watch-only context; require explicit setup, sizing, and gate before action.",
        })
    for row in feed.get("radar") or []:
        if not isinstance(row, dict):
            continue
        rows.append({
            "ticker": row.get("ticker") or "",
            "title": f"{row.get('direction') or 'watch'} from {row.get('author') or 'source'}",
            "source": "fundstrat_daily",
            "why_not_acting": "Fundstrat radar rows are context unless promoted by a fresh action gate.",
        })
    return {
        "status": "has_data" if rows else "checked_clear",
        "count": len(rows),
        "line": (
            f"Why-not-acting lane: {len(rows)} watch-only signal(s) kept out of trade prompts."
            if rows else
            "Why-not-acting lane: no watch-only signals in current feed."
        ),
        "rows": rows[:10],
    }


def build_operator_hardening(feed: dict[str, Any]) -> dict[str, Any]:
    return {
        "freshness_downgrades": freshness_downgrade_audit(feed),
        "stale_action_cleanup": stale_action_cleanup(feed),
        "condition_checklist": condition_checklist(feed),
        "watch_only_why": watch_only_why(feed),
    }
