"""Dashboard-facing UW routing recommendations.

This module consumes an already-built cockpit feed and recommends which
scenario-specific UW routing profiles should be used next. It does not fetch UW
data and does not prove that any endpoint has run.
"""
from __future__ import annotations

from typing import Any

from uw_endpoint_router import profile_for_mode


def _profile_row(mode: str, *, reason: str, priority: int) -> dict[str, Any]:
    profile = profile_for_mode(mode)
    groups = sorted(profile.get("groups") or [], key=lambda row: row.get("priority") or 99)
    top_groups = []
    top_endpoints: list[str] = []
    for group in groups[:3]:
        endpoints = [row.get("name") or "" for row in group.get("endpoints") or [] if row.get("name")]
        top_endpoints.extend(endpoints[:3])
        top_groups.append({
            "key": group.get("key") or "",
            "priority": group.get("priority") or 0,
            "scope": group.get("scope") or "",
            "endpoints": endpoints,
            "decision_use": group.get("decision_use") or "",
        })
    return {
        "mode": mode,
        "label": profile.get("label") or mode,
        "priority": priority,
        "reason": reason,
        "operator_question": profile.get("operator_question") or "",
        "freshness_requirement": profile.get("freshness_requirement") or "",
        "top_endpoints": top_endpoints[:8],
        "groups": top_groups,
    }


def build_uw_routing_recommendations(feed: dict[str, Any]) -> dict[str, Any]:
    actions = [row for row in feed.get("actions") or [] if isinstance(row, dict)]
    rows: list[dict[str, Any]] = []

    if any(row.get("kind") == "event_risk" for row in actions) or feed.get("event_risk"):
        rows.append(_profile_row(
            "event_risk_political_macro",
            reason="Active event-risk lane can overpower normal thesis and flow signals.",
            priority=1,
        ))

    if any(row.get("kind") == "conviction_gap" or row.get("source") == "target_drift" for row in actions):
        rows.append(_profile_row(
            "portfolio_reallocation",
            reason="Sizing-gap actions need current exposure, funding, factor, and flow checks.",
            priority=2,
        ))

    if any(str(row.get("source") or "").startswith("fundstrat") for row in actions) or (feed.get("source_audits") or {}).get("fundstrat"):
        rows.append(_profile_row(
            "fundstrat_signal_confirmation",
            reason="Fundstrat-derived calls should be checked against live market structure before action.",
            priority=3,
        ))

    asym = feed.get("asymmetric_opportunities") or {}
    if int(asym.get("count") or 0) > 0:
        rows.append(_profile_row(
            "asymmetric_discovery",
            reason="Asymmetric-opportunity rows need a discovery/follow-up endpoint set, not only generic ticker flow.",
            priority=4,
        ))

    if any(row.get("source") == "reddit" for row in actions) or feed.get("reddit_watch"):
        rows.append(_profile_row(
            "reddit_escalation_vetting",
            reason="Social anomalies require independent UW/news/price vetting before escalation.",
            priority=5,
        ))

    rows = sorted(rows, key=lambda row: row["priority"])
    status = "has_data" if rows else "checked_clear"
    return {
        "status": status,
        "line": (
            f"UW routing: {len(rows)} scenario profile(s) recommended; top={rows[0]['label']}."
            if rows else
            "UW routing: no scenario profile recommended from current feed."
        ),
        "rows": rows,
        "honesty_rule": "Routing recommends endpoint groups only; it is not proof that those endpoints were fetched.",
    }
