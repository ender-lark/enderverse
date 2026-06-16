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


def _source_observations(source_call_observations) -> list[dict]:
    rows: list[dict] = []
    for row in source_call_observations or []:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        quote = str(row.get("quote") or row.get("call_summary") or row.get("verbatim_quote") or "").strip()
        if not ticker and not quote:
            continue
        rows.append({
            "source": row.get("source") or "unclassified source call",
            "author": row.get("author") or "",
            "ticker": ticker or None,
            "direction": row.get("direction") or "",
            "date": str(row.get("date") or "")[:10],
            "quote": quote,
        })
    rows.sort(key=lambda r: (r.get("date") or "", r.get("ticker") or ""), reverse=True)
    return rows


def _calibration_feedback(calls: list, *, inbox_call_dates=None, log_call_dates=None,
                          as_of=None) -> tuple[dict, bool]:
    cache_dates = [c.get("date") for c in calls if isinstance(c, dict) and c.get("date")]
    newest_cache = max(cache_dates) if cache_dates else ""
    if not inbox_call_dates and not log_call_dates:
        return ({
            "status": "not_checked",
            "line": (
                "Calibration chain not checked; source persistence is provisional "
                f"(cache as-of {newest_cache or 'unknown'})."
            ),
            "worst_days_behind": 0,
            "cache_as_of": newest_cache,
            "stale_hops": [],
            "provisional": True,
        }, False)

    chain = sct.calibration_chain_staleness(
        inbox_call_dates or [], log_call_dates or [], cache_dates, now=_today(as_of)
    )
    if not chain.get("stale"):
        return ({
            "status": "checked_fresh",
            "line": "Calibration chain checked fresh.",
            "worst_days_behind": 0,
            "cache_as_of": newest_cache,
            "stale_hops": [],
            "provisional": False,
        }, True)
    stale_hops = chain.get("stale_hops") or []
    hop_label = ", ".join(str(h).replace("_", "->") for h in stale_hops) or "unknown hop"
    surface = sct.chain_staleness_surface(chain)
    return ({
        "status": "stale",
        "line": (
            "Calibration chain stale: "
            f"{chain.get('worst_days_behind', 0)}d behind ({hop_label}); "
            "SOURCE CALIB output is provisional."
        ),
        "worst_days_behind": chain.get("worst_days_behind", 0),
        "cache_as_of": newest_cache,
        "stale_hops": stale_hops,
        "provisional": True,
        "surface_line": surface,
        "inbox_log": chain.get("inbox_log") or {},
        "log_cache": chain.get("log_cache") or {},
    }, False)


def _persistence_feedback(calls: list, *, core_tickers=None, calibration_fresh=False,
                          as_of=None) -> dict:
    clusters = sct.persistence_scan(calls, core_tickers=core_tickers, now=_today(as_of))
    guarded = False
    rows = []
    for c in clusters:
        row = dict(c)
        if not calibration_fresh and row.get("loud"):
            row["loud"] = False
            row["quiet_reason"] = "calib_provisional"
            row["provisional"] = True
            guarded = True
        rows.append({
            "source": row.get("source") or "",
            "ticker": row.get("ticker") or "",
            "count": row.get("count", 0),
            "within_days": row.get("within_days", 0),
            "has_ab": bool(row.get("has_ab")),
            "loud": bool(row.get("loud")),
            "provisional": bool(row.get("provisional")),
            "quiet_reason": row.get("quiet_reason") or "",
            "fired_on": row.get("fired_on") or "",
        })

    if not rows:
        return {
            "status": "checked_clear",
            "line": "Source persistence checked: no repeated-call clusters.",
            "cluster_count": 0,
            "loud_count": 0,
            "provisional_count": 0,
            "guarded": guarded,
            "clusters": [],
        }

    loud_n = sum(1 for r in rows if r["loud"])
    provisional_n = sum(1 for r in rows if r["provisional"])
    line = sct.persistence_surface_line(rows)
    if guarded:
        line += " PROVISIONAL: calibration chain not confirmed fresh."
    return {
        "status": "has_data",
        "line": line,
        "cluster_count": len(rows),
        "loud_count": loud_n,
        "provisional_count": provisional_n,
        "guarded": guarded,
        "clusters": rows[:5],
    }


def source_call_feedback(source_calls, *, as_of=None, core_tickers=None,
                         inbox_call_dates=None, log_call_dates=None,
                         source_call_observations=None) -> dict:
    """Summarize source calibration health from source_calls.json-shaped rows."""
    if source_calls is None:
        observations = _source_observations(source_call_observations)
        if observations:
            dated = [r.get("date") for r in observations if r.get("date")]
            newest = max(dated) if dated else ""
            return {
                "status": "not_checked",
                "line": (
                    f"Source-call calibration not checked; {len(observations)} "
                    f"unscored daily call(s) are flowing"
                    + (f" through {newest}." if newest else ".")
                ),
                "pending_count": 0,
                "overdue_count": 0,
                "oldest_overdue_days": 0,
                "rates": [],
                "due": [],
                "observed_count": len(observations),
                "observations": observations[:5],
            }
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
    calibration, calibration_fresh = _calibration_feedback(
        calls,
        inbox_call_dates=inbox_call_dates,
        log_call_dates=log_call_dates,
        as_of=as_of,
    )
    persistence = _persistence_feedback(
        calls,
        core_tickers=core_tickers,
        calibration_fresh=calibration_fresh,
        as_of=as_of,
    )
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
        "calibration": calibration,
        "persistence": persistence,
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
            "recent_history": [],
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
            "recent_history": _recent_history(open_opportunities),
        }
    today = _today(as_of)
    prices = prices or {}
    items = []
    for r in rows:
        age = oo.age_business_days(r.get("first_flagged"), today)
        tk = r.get("ticker")
        move = oo.compute_move_since(r.get("flag_price"), prices.get(tk)) if tk else ""
        age_days = age if age is not None else 0
        items.append({
            "ticker": tk,
            "kind": r.get("kind") or "",
            "source": r.get("source") or "",
            "first_flagged": r.get("first_flagged") or "",
            "age_days": age_days,
            "move_since": move,
            **oo.review_age_state(age_days),
        })
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda x: (
        priority_rank.get(str(x.get("cleanup_priority") or "low"), 9),
        -x["age_days"],
        str(x.get("ticker") or ""),
    ))
    oldest = max([int(item.get("age_days") or 0) for item in items], default=0)
    due_count = sum(1 for item in items if item.get("due"))
    stale_count = sum(1 for item in items if item.get("review_state") == "stale")
    return {
        "status": "has_data",
        "line": (
            f"Open action backlog: {len(items)} open; {due_count} due; "
            f"{stale_count} stale; oldest {oldest} trading day(s)."
        ),
        "count": len(items),
        "oldest_age_days": oldest,
        "due_count": due_count,
        "stale_count": stale_count,
        "items": items[:5],
        "recent_history": _recent_history(open_opportunities),
    }


def _recent_history(store, limit=5):
    rows = (store or {}).get("history") if isinstance(store, dict) else []
    out = []
    for r in (rows or []):
        if not isinstance(r, dict):
            continue
        out.append({
            "ticker": r.get("ticker"),
            "status": r.get("status") or "",
            "reason": r.get("reason") or "",
            "resolved_at": r.get("resolved_at") or "",
        })
    out.sort(key=lambda r: r.get("resolved_at") or "", reverse=True)
    return out[:limit]


def build_feedback_summary(*, source_calls=None, open_opportunities=None,
                           prices=None, as_of=None, core_tickers=None,
                           inbox_call_dates=None, log_call_dates=None,
                           source_call_observations=None) -> dict:
    source = source_call_feedback(
        source_calls,
        as_of=as_of,
        core_tickers=core_tickers,
        inbox_call_dates=inbox_call_dates,
        log_call_dates=log_call_dates,
        source_call_observations=source_call_observations,
    )
    actions = open_action_feedback(open_opportunities, prices=prices, as_of=as_of)
    recommendations = []
    if source["overdue_count"]:
        recommendations.append("Score overdue source calls Win/Loss/Push.")
    persistence = source.get("persistence") or {}
    if persistence.get("loud_count"):
        recommendations.append("Escalate LOUD source-persistence cluster into research/action review.")
    elif persistence.get("provisional_count"):
        recommendations.append("Refresh calibration chain, then review provisional source-persistence cluster.")
    if source.get("observed_count") and source.get("status") == "not_checked":
        recommendations.append("Classify daily source calls into the calibration cache before using persistence.")
    if actions["count"]:
        if actions.get("stale_count"):
            recommendations.append("Resolve stale open actions first: act, invalidate, ignore, miss, expire, or explicitly defer.")
        elif actions.get("due_count"):
            recommendations.append("Review due open actions: act, invalidate, ignore, or keep watching explicitly.")
        else:
            recommendations.append("Keep new open actions visible until their review window.")
    if not recommendations:
        recommendations.append("No feedback-loop action required.")
    return {
        "source_calls": source,
        "open_actions": actions,
        "recommendations": recommendations,
    }
