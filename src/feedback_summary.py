"""Feedback-loop summary for the cockpit feed.

This is the bridge from existing calibration/persistence modules into the
operator-facing dashboard. It does not score trades itself; it makes overdue
source-call scoring and open-action backlog visible.
"""
from __future__ import annotations

from datetime import date

import open_opportunities as oo
import source_call_tracker as sct


def _today(as_of=None) -> str:
    return str(as_of or date.today().isoformat())[:10]


def _status(value) -> str:
    return "not_checked" if value is None else "checked_clear" if not value else "has_data"


def _source_rates(calls: list) -> list[dict]:
    sources = sorted({c.get("source") for c in calls if isinstance(c, dict) and c.get("source")})
    rows = []
    for src in sources:
        r = sct.compute_hit_rate(calls, source=src, tiers=["A", "B"])
        rows.append({
            "source": src,
            "n": r["n"],
            "wins": r["wins"],
            "losses": r["losses"],
            "pushes": r["pushes"],
            "hit_rate": r["hit_rate"],
            "tier_band": r["tier_band"],
            "discount_factor": r["discount_factor"],
        })
    return rows


def source_call_feedback(source_calls, *, as_of=None) -> dict:
    """Summarize source calibration health from source_calls.json-shaped rows."""
    if source_calls is None:
        return {
            "status": "not_checked",
            "line": "Source calls not checked.",
            "pending_count": 0,
            "overdue_count": 0,
            "oldest_overdue_days": 0,
            "rates": [],
            "due": [],
        }
    calls = source_calls if isinstance(source_calls, list) else []
    if not calls:
        return {
            "status": "checked_clear",
            "line": "Source calls checked: no calls in cache.",
            "pending_count": 0,
            "overdue_count": 0,
            "oldest_overdue_days": 0,
            "rates": [],
            "due": [],
        }
    sweep = sct.scoring_lag_sweep(calls, now=_today(as_of))
    pending = sum(1 for c in calls if isinstance(c, dict) and (c.get("outcome") or "Pending") == "Pending")
    due = [{
        "source": c.get("source") or "",
        "ticker": c.get("ticker"),
        "tier": c.get("tier") or "",
        "window_end": c.get("window_end") or "",
        "overdue_days": c.get("overdue_days", 0),
    } for c in sweep.get("due", [])[:5]]
    return {
        "status": "has_data",
        "line": sct.scoring_lag_surface_line(sweep),
        "pending_count": pending,
        "overdue_count": sweep.get("count", 0),
        "oldest_overdue_days": sweep.get("oldest_overdue_days", 0),
        "rates": _source_rates(calls),
        "due": due,
    }


def open_action_feedback(open_opportunities, *, prices=None, as_of=None) -> dict:
    """Summarize unacted opportunity backlog from open_opportunities.json."""
    if open_opportunities is None:
        return {
            "status": "not_checked",
            "line": "Open action backlog not checked.",
            "count": 0,
            "oldest_age_days": 0,
            "items": [],
        }
    rows = (open_opportunities or {}).get("opportunities") if isinstance(open_opportunities, dict) else []
    rows = [r for r in (rows or []) if isinstance(r, dict) and r.get("status", "open") == "open"]
    if not rows:
        return {
            "status": "checked_clear",
            "line": "Open action backlog clean.",
            "count": 0,
            "oldest_age_days": 0,
            "items": [],
        }
    today = _today(as_of)
    prices = prices or {}
    items = []
    for r in rows:
        age = oo.age_business_days(r.get("first_flagged"), today)
        tk = r.get("ticker")
        move = oo.compute_move_since(r.get("flag_price"), prices.get(tk)) if tk else ""
        items.append({
            "ticker": tk,
            "kind": r.get("kind") or "",
            "source": r.get("source") or "",
            "first_flagged": r.get("first_flagged") or "",
            "age_days": age if age is not None else 0,
            "move_since": move,
        })
    items.sort(key=lambda x: -x["age_days"])
    oldest = items[0]["age_days"] if items else 0
    return {
        "status": "has_data",
        "line": f"Open action backlog: {len(items)} open; oldest {oldest} trading day(s).",
        "count": len(items),
        "oldest_age_days": oldest,
        "items": items[:5],
    }


def build_feedback_summary(*, source_calls=None, open_opportunities=None,
                           prices=None, as_of=None) -> dict:
    source = source_call_feedback(source_calls, as_of=as_of)
    actions = open_action_feedback(open_opportunities, prices=prices, as_of=as_of)
    recommendations = []
    if source["overdue_count"]:
        recommendations.append("Score overdue source calls Win/Loss/Push.")
    if actions["count"]:
        recommendations.append("Resolve oldest open action: act, invalidate, or keep watching explicitly.")
    if not recommendations:
        recommendations.append("No feedback-loop action required.")
    return {
        "source_calls": source,
        "open_actions": actions,
        "recommendations": recommendations,
    }
