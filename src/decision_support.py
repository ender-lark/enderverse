"""Decision-support enrichment for cockpit action surfacing.

This module is intentionally deterministic: it annotates already-produced feed
rows with freshness, grouping, and opportunity context. It does not fetch data,
change recommendations, or decide trades.
"""
from __future__ import annotations

from datetime import datetime, date, timezone
from typing import Any
from zoneinfo import ZoneInfo


GROUPS = (
    {
        "key": "key_now",
        "label": "Key Now",
        "description": "Decision pressure that is current, time-sensitive, or goal-moving.",
    },
    {
        "key": "recheck_before_acting",
        "label": "Re-check Before Acting",
        "description": "Items where a missing source, stale source, or gate must be checked first.",
    },
    {
        "key": "important_backlog",
        "label": "Important Backlog",
        "description": "Still-important decisions that should stay visible but are not the loudest current item.",
    },
    {
        "key": "quiet_watch",
        "label": "Quiet Watch",
        "description": "Monitored context with no current action pressure.",
    },
)

FAST_DECAY_KINDS = {"event_risk", "macro_alert", "buy_now", "reentry_zone"}
SLOW_DECAY_KINDS = {"conviction_gap", "lean_in", "decision_aging", "top_prospect"}
ARCHIVE_SOURCES = {"meridian"}
CRYPTO_COMPLEX = {"BMNR", "IBIT", "ETHA", "MSTR", "COIN", "HYPE", "BTC", "ETH", "SOL"}
SOURCE_ALIASES = {
    "daily_synthesis": "synthesis",
    "synthesis": "synthesis",
    "event_risk": "event_risk",
    "target_drift": "portfolio",
    "lean_in": "uw_price",
    "top_prospects": "fundstrat_bible",
    "top_prospects:sell_fast": "fundstrat_bible",
    "fundstrat_daily": "fundstrat_daily",
    "research": "research",
    "research_queue": "research",
}
ET = ZoneInfo("America/New_York")


def _parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed_date = date.fromisoformat(text[:10])
        except ValueError:
            return None
        return datetime(parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=timezone.utc)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _iso_day(value: Any) -> str:
    parsed = _parse_dt(value)
    return parsed.date().isoformat() if parsed else str(value or "")[:10]


def _et_day(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "T" not in text:
        return _iso_day(text)
    parsed = _parse_dt(text)
    return parsed.astimezone(ET).date().isoformat() if parsed else text[:10]


def _date_index(staleness: dict[str, Any], synthesis: dict[str, Any] | None, event_risk: list[dict] | None) -> dict[str, str]:
    index: dict[str, str] = {}
    for row in (staleness or {}).get("entries") or []:
        if not isinstance(row, dict):
            continue
        source = str(row.get("source") or "")
        if source and row.get("date"):
            index[source] = _iso_day(row.get("date"))
    if isinstance(synthesis, dict) and synthesis.get("date"):
        index["synthesis"] = _iso_day(synthesis.get("date"))
    event_dates = [
        _iso_day(row.get("date"))
        for row in event_risk or []
        if isinstance(row, dict) and row.get("date")
    ]
    if event_dates:
        index["event_risk"] = sorted(event_dates)[-1]
    return index


def _freshness_label(kind: str, source: str, evidence_date: str, staleness: dict[str, Any]) -> str:
    if source in ARCHIVE_SOURCES:
        return "archive"
    stale_sources = {
        str(row.get("source") or "")
        for row in (staleness or {}).get("stale") or []
        if isinstance(row, dict)
    }
    if source in stale_sources:
        return "stale"
    if not evidence_date:
        return "not checked"
    if kind in FAST_DECAY_KINDS:
        return "fast-moving"
    return "fresh"


def _decay_window(kind: str, source: str) -> str:
    if source in ARCHIVE_SOURCES:
        return "thesis archive; not tactical"
    if kind in FAST_DECAY_KINDS:
        return "intraday to 1 trading day"
    if kind in SLOW_DECAY_KINDS:
        return "until position, price, thesis, or target changes"
    return "1-3 trading days"


def _freshness_judgment(action: dict[str, Any], *, staleness: dict[str, Any], dates: dict[str, str], generated_at: str) -> dict[str, Any]:
    kind = str(action.get("kind") or "")
    source_raw = str(action.get("source") or "")
    source = SOURCE_ALIASES.get(source_raw, source_raw)
    evidence_date = (
        dates.get(source)
        or dates.get(source_raw)
        or _iso_day(action.get("when"))
        or _iso_day(action.get("date"))
    )
    label = _freshness_label(kind, source, evidence_date, staleness)
    decay = _decay_window(kind, source)
    last_checked = _et_day(generated_at)
    if label == "archive":
        judgment = "Thesis context only; do not treat as fresh tactical evidence."
    elif label == "fast-moving":
        if evidence_date and evidence_date != last_checked:
            judgment = (
                f"Fast-moving evidence is dated {evidence_date}; re-check levels/headlines "
                "before any capital action."
            )
        else:
            judgment = "Fresh enough to surface, but levels/headlines can change during the session."
    elif label == "stale":
        judgment = "Source is stale; re-check before acting."
    elif label == "not checked":
        judgment = "No evidence date was found; re-check before acting."
    else:
        judgment = "Fresh enough for a decision prompt; still run the gate before capital moves."
    return {
        "label": label,
        "evidence_date": evidence_date,
        "last_checked": last_checked,
        "decay_window": decay,
        "judgment": judgment,
    }


def _group_for(action: dict[str, Any]) -> str:
    missing = [m for m in action.get("missing_evidence") or [] if str(m).strip()]
    kind = str(action.get("kind") or "")
    state = str(action.get("action_state") or "")
    time_window = str(action.get("time_window") or "")
    impact = str(action.get("goal_impact") or "")
    freshness = action.get("freshness_judgment") or {}
    freshness_label = str(freshness.get("label") or "")

    if freshness_label in {"stale", "not checked"}:
        return "recheck_before_acting"
    if (
        freshness_label == "fast-moving"
        and freshness.get("evidence_date")
        and freshness.get("last_checked")
        and freshness.get("evidence_date") != freshness.get("last_checked")
    ):
        return "recheck_before_acting"
    if missing and state != "ACT_NOW":
        return "recheck_before_acting"
    if state == "ACT_NOW":
        return "key_now"
    if kind in {"event_risk", "decision_aging"}:
        return "key_now"
    if time_window in {"today", "1-3 trading days"} and impact in {"High", "Medium"}:
        return "key_now"
    if impact == "High":
        return "important_backlog"
    if state in {"WATCH", "RESEARCH"}:
        return "important_backlog"
    return "quiet_watch"


def _requires_recheck_before_capital(freshness: dict[str, Any]) -> bool:
    label = str(freshness.get("label") or "")
    return (
        label == "fast-moving"
        and bool(freshness.get("evidence_date"))
        and bool(freshness.get("last_checked"))
        and freshness.get("evidence_date") != freshness.get("last_checked")
    )


def _dedupe_text(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _disconfirmation(action: dict[str, Any], freshness: dict[str, Any]) -> dict[str, Any]:
    """Explain what would make the action wrong before the operator acts."""
    existing = action.get("disconfirmation")
    if isinstance(existing, dict) and existing.get("summary"):
        return dict(existing)

    kind = str(action.get("kind") or "")
    source = str(action.get("source") or "")
    ticker = str(action.get("ticker") or "").strip().upper()
    missing = [str(v).strip() for v in action.get("missing_evidence") or [] if str(v).strip()]
    label = str(freshness.get("label") or "")
    stale_or_missing = label in {"stale", "not checked"} or _requires_recheck_before_capital(freshness)
    confirm: list[str] = []
    invalidates: list[str] = []

    if stale_or_missing:
        invalidates.append("Evidence is stale, missing, or too fast-moving for a capital action without a live re-check.")
        confirm.append("Refresh the evidence lane and confirm the action still survives with same-session data.")

    if kind == "event_risk":
        invalidates.extend([
            "The listed event trigger does not occur or reverses.",
            "Affected exposures stabilize while rates, oil, volatility, or headlines stop worsening.",
        ])
        confirm.extend(missing or ["Check the event trigger, affected tickers, and latest headlines before changing exposure."])
    elif kind == "conviction_gap" or source == "target_drift":
        invalidates.extend([
            "The target weight or thesis is outdated relative to the current portfolio.",
            "The funding leg creates more risk or opportunity cost than the add solves.",
            "The pre-trade gate fails on live price, source freshness, or sizing.",
        ])
        confirm.extend(missing or ["Confirm current position size, live entry, funding source, and pre-trade gate."])
    elif kind == "lean_in":
        invalidates.extend([
            "The live tape no longer confirms leadership or flow strength.",
            "Current sizing is already large enough after account and wrapper exposure.",
            "A better funding use ranks higher after fresh portfolio review.",
        ])
        confirm.extend(missing or ["Confirm same-session price/flow, current sizing, and funding source."])
    elif source.startswith("fundstrat") or source in {"radar", "top_prospects"}:
        invalidates.extend([
            "The Fundstrat/source call is stale, superseded, or contradicted by live tape.",
            "The name has already moved enough that the entry is no longer asymmetric.",
        ])
        confirm.extend(missing or ["Confirm latest source date, live entry, and whether the call was superseded."])
    elif kind in {"research", "research_queue", "top_prospect"}:
        invalidates.extend([
            "The research item lacks decision-grade evidence or a current catalyst.",
            "Independent source checks do not confirm the thesis or timing.",
        ])
        confirm.extend(missing or ["Promote only after a dated thesis, catalyst, and independent confirmation."])
    else:
        invalidates.extend([
            "The source evidence is stale, contradictory, or not decision-grade.",
            "Live price, flow, or portfolio context changes the action's risk/reward.",
        ])
        confirm.extend(missing or ["Run the relevant source, freshness, and pre-action checks."])

    if ticker:
        confirm.append(f"Check same-session price/flow and current exposure for {ticker}.")
    if action.get("gate"):
        confirm.append("Run the pre-trade gate; no auto-trade from the dashboard.")

    invalidates = _dedupe_text(invalidates)
    confirm = _dedupe_text(confirm)
    downgrade = "Re-check Before Acting" if stale_or_missing or missing else "Quiet Watch"
    return {
        "question": "What would make this wrong?",
        "summary": f"Do not act if {invalidates[0][0].lower() + invalidates[0][1:] if invalidates else 'the evidence fails live checks.'}",
        "invalidates_if": invalidates,
        "confirm_before_acting": confirm,
        "downgrade_to": downgrade,
    }


def _capital_efficiency(action: dict[str, Any], freshness: dict[str, Any]) -> dict[str, Any]:
    """Describe whether this is the best current use of scarce capital."""
    channels = set(action.get("goal_channels") or [])
    effect = str(action.get("capital_effect") or "")
    kind = str(action.get("kind") or "")
    state = str(action.get("action_state") or "")
    window = str(action.get("time_window") or "")
    score = action.get("goal_score")
    requires_capital = effect in {"start", "add", "trim", "sell", "hedge", "rotate", "review"}
    opportunity_sensitive = bool(channels.intersection({"opportunity_cost", "sizing_gap", "upside", "downside_protection"}))
    stale_or_recheck = _requires_recheck_before_capital(freshness) or str(freshness.get("label") or "") in {"stale", "not checked"}

    if kind == "event_risk" or "downside_protection" in channels:
        label = "protect capital"
        summary = "Efficient capital use can mean not adding risk until the shock is re-checked."
    elif state == "ACT_NOW" and opportunity_sensitive:
        label = "compare and stage"
        summary = "Do not park capital here only because it is good; compare it against higher-ranked uses and funding legs."
    elif opportunity_sensitive:
        label = "opportunity-cost watch"
        summary = "Keep visible because a good opportunity can still be the wrong capital use if a better setup ranks higher."
    elif requires_capital:
        label = "capital check"
        summary = "Any capital move should be compared with the current best alternative use."
    else:
        label = "no capital move"
        summary = "No capital should move until this becomes decision-grade."

    timing_balance = (
        "Avoid waiting for a perfect bottom; if live checks confirm, consider staged exposure rather than all-or-nothing timing."
        if window in {"today", "1-3 trading days"} or state == "ACT_NOW"
        else
        "Do not force timing; keep a review trigger so capital is not parked in a merely adequate setup."
    )
    if stale_or_recheck:
        timing_balance = (
            "Re-check first, but do not turn that into indefinite waiting; once fresh evidence confirms, stage rather than chase perfection."
        )

    compare_against = [
        "higher-ranked Key Now actions",
        "funded reallocation legs",
        "risk reduction or hedging if event risk is active",
    ]
    if score is not None:
        compare_against.append(f"goal score {score}/100")
    return {
        "label": label,
        "summary": summary,
        "timing_balance": timing_balance,
        "compare_against": compare_against,
    }


def _action_assumption_refresh(action: dict[str, Any],
                               freshness: dict[str, Any],
                               capital: dict[str, Any],
                               generated_at: str) -> dict[str, Any]:
    """Snapshot and re-check assumptions that make an action valid."""
    ticker = str(action.get("ticker") or "").strip().upper()
    missing = _dedupe_text([str(v) for v in action.get("missing_evidence") or []])
    label = str(freshness.get("label") or "")
    state = str(action.get("action_state") or "")
    source = str(action.get("source") or action.get("kind") or "")
    blockers: list[str] = []
    changed: list[str] = []
    invalidates_if: list[str] = []

    if label in {"stale", "not checked"}:
        blockers.append("source freshness")
        changed.append(str(freshness.get("judgment") or "Source evidence is stale or not checked."))
    elif _requires_recheck_before_capital(freshness):
        blockers.append("same-session refresh")
        changed.append(str(freshness.get("judgment") or "Fast-moving evidence must be re-checked."))

    if missing:
        blockers.append("missing evidence")
        changed.append("Required live checks are missing: " + "; ".join(missing[:3]))

    dependency_text = " ".join(missing).lower()
    if any(term in dependency_text for term in ("price", "flow", "live", "same-session", "pre-trade")):
        invalidates_if.append("Live price or flow moved enough that the original entry/setup is no longer asymmetric.")
    if source in {"target_drift", "portfolio"} or action.get("kind") == "conviction_gap":
        invalidates_if.append("Current positions, target weights, or funding legs changed.")
    if source.startswith("fundstrat"):
        invalidates_if.append("The Fundstrat call was superseded, absorbed by the tape, or contradicted by live evidence.")
    if ticker in CRYPTO_COMPLEX:
        blockers.append("crypto re-check")
        changed.append(f"{ticker} is in the crypto/BMNR complex; keep undecided until fresh evidence resolves defend versus reduce.")
        invalidates_if.append("Crypto/BMNR evidence remains split, stale, or contradicted by price/flow.")

    if label == "stale":
        status = "stale"
    elif blockers:
        status = "changed_recheck"
    elif state == "ACT_NOW" and action.get("goal_score") and int(action.get("goal_score") or 0) >= 85:
        status = "upgraded"
    else:
        status = "still_valid"

    if status == "still_valid":
        changed.append("No material assumption break detected from available feed evidence.")
    elif status == "upgraded":
        changed.append("Action remains high-impact with fresh enough evidence; still run the gate.")

    if not invalidates_if:
        invalidates_if = [
            "Fresh price, flow, position, source, or event-risk evidence changes the expected risk/reward.",
        ]

    next_step = {
        "still_valid": "Keep in its current group; run normal gate before acting.",
        "upgraded": "Keep loud, but confirm same-session gate before any capital move.",
        "changed_recheck": "Refresh assumptions before acting; do not treat the old setup as still valid.",
        "stale": "Downgrade until fresh evidence is supplied.",
        "invalidated": "Move out of action lanes unless a new setup appears.",
    }.get(status, "Refresh assumptions before acting.")

    return {
        "status": status,
        "checked_at": _et_day(generated_at),
        "snapshot": {
            "ticker": ticker,
            "action_state": state,
            "source": source,
            "evidence_date": freshness.get("evidence_date") or "",
            "freshness": label,
            "decay_window": freshness.get("decay_window") or "",
            "capital_label": capital.get("label") or "",
            "time_window": action.get("time_window") or "",
        },
        "what_changed": _dedupe_text(changed),
        "blockers": _dedupe_text(blockers),
        "invalidates_if": _dedupe_text(invalidates_if),
        "next_step": next_step,
        "honesty_rule": "Assumption refresh can downgrade stale or missing evidence; it does not execute or auto-promote trades.",
    }


def enrich_actions(
    actions: list[dict[str, Any]] | None,
    *,
    staleness: dict[str, Any] | None = None,
    synthesis: dict[str, Any] | None = None,
    event_risk: list[dict] | None = None,
    generated_at: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return enriched actions and a grouped dashboard summary."""
    staleness = staleness or {}
    dates = _date_index(staleness, synthesis, event_risk)
    enriched: list[dict[str, Any]] = []
    for action in actions or []:
        row = dict(action)
        freshness = _freshness_judgment(
            row,
            staleness=staleness,
            dates=dates,
            generated_at=generated_at,
        )
        row["freshness_judgment"] = freshness
        if row.get("action_state") == "ACT_NOW" and _requires_recheck_before_capital(freshness):
            row["action_state"] = "WATCH"
            row["action_label"] = "RE-CHECK"
        row["freshness"] = (
            f"{freshness['label']}: evidence {freshness.get('evidence_date') or 'n/a'}; "
            f"decays {freshness['decay_window']}"
        )
        row["why_this_matters"] = (
            row.get("why_it_moves_goal")
            or row.get("why")
            or "This is surfaced because it may affect conviction, sizing, timing, or risk."
        )
        row["disconfirmation"] = _disconfirmation(row, freshness)
        row["capital_efficiency"] = _capital_efficiency(row, freshness)
        row["assumption_refresh"] = _action_assumption_refresh(
            row,
            freshness,
            row["capital_efficiency"],
            generated_at,
        )
        if row["assumption_refresh"]["status"] in {"changed_recheck", "stale"} and row.get("action_state") == "ACT_NOW":
            row["action_state"] = "WATCH"
            row["action_label"] = "RE-CHECK"
        group = _group_for(row)
        row["decision_group"] = group
        row["decision_group_label"] = next(g["label"] for g in GROUPS if g["key"] == group)
        enriched.append(row)

    sections = []
    for group in GROUPS:
        rows = [row for row in enriched if row.get("decision_group") == group["key"]]
        sections.append({
            **group,
            "count": len(rows),
            "ranks": [row.get("rank") for row in rows if row.get("rank") is not None],
        })
    return enriched, {
        "sections": sections,
        "counts": {section["key"]: section["count"] for section in sections},
    }


def _ticker(row: dict[str, Any]) -> str:
    return str(row.get("ticker") or row.get("subject") or "").strip().upper()


def build_asymmetric_opportunities(feed: dict[str, Any], *, max_items: int = 8) -> dict[str, Any]:
    """Dedup opportunity candidates across target drift, actions, prospects, radar, and UW flow."""
    candidates: dict[str, dict[str, Any]] = {}

    def add(ticker: str, *, source: str, score: int, reason: str, evidence: str = "", decay: str = "") -> None:
        tk = ticker.strip().upper()
        if not tk:
            return
        cur = candidates.get(tk)
        if cur is None or score > cur["score"]:
            candidates[tk] = {
                "ticker": tk,
                "source": source,
                "score": score,
                "reason": reason,
                "evidence": evidence,
                "decay_window": decay or "source dependent",
                "action": "review setup; no auto-trade",
            }
        elif cur:
            cur["source"] = ", ".join(sorted(set((cur.get("source") or "").split(", ") + [source])))

    for action in feed.get("actions") or []:
        if not isinstance(action, dict):
            continue
        tk = _ticker(action)
        channels = set(action.get("goal_channels") or [])
        if tk and channels.intersection({"upside", "sizing_gap", "leverage", "opportunity_cost"}):
            freshness = action.get("freshness_judgment") or {}
            add(
                tk,
                source=str(action.get("source") or action.get("kind") or "actions"),
                score=int(action.get("goal_score") or 60),
                reason=str(action.get("why_it_moves_goal") or action.get("why") or action.get("what") or ""),
                evidence=str(action.get("what") or ""),
                decay=str(freshness.get("decay_window") or action.get("time_window") or ""),
            )

    for row in ((feed.get("target_drift") or {}).get("rows") or []):
        if not isinstance(row, dict):
            continue
        if row.get("direction") in {"UNDERSIZED", "MISSING"}:
            score = 70 + min(20, int(abs(float(row.get("drift_absolute_pct") or 0))))
            add(
                _ticker(row),
                source="target_drift",
                score=score,
                reason="High-conviction target gap can make the right thesis too small.",
                evidence=f"{row.get('direction')} vs target",
                decay="until account/target changes",
            )

    for row in (
        ((feed.get("prospects") or {}).get("hot") or [])
        + ((feed.get("prospects") or {}).get("movers_best") or [])
    ):
        if isinstance(row, dict):
            add(
                _ticker(row),
                source="prospects",
                score=int(row.get("urgency_score") or row.get("conviction_score") or 45),
                reason=str(row.get("summary") or "Prospect is building and should stay visible."),
                evidence=str(row.get("provenance") or ""),
                decay="source dependent",
            )

    for row in feed.get("radar") or []:
        if isinstance(row, dict) and str(row.get("direction") or "").lower() not in {"avoid", "sell"}:
            add(
                _ticker(row),
                source="radar",
                score=52,
                reason="External endorsed-not-owned call may be an early opportunity.",
                evidence=str(row.get("quote") or row.get("author") or ""),
                decay="1-3 trading days",
            )

    for row in ((feed.get("bullish_flow") or {}).get("rows") or []):
        if isinstance(row, dict) and str(row.get("direction") or "").lower() == "bullish":
            add(
                _ticker(row),
                source="bullish_flow",
                score=68 if row.get("strength") == "strong" else 54,
                reason="Fresh bullish flow can mark an asymmetric setup when it aligns with thesis and sizing.",
                evidence=", ".join(str(x) for x in (row.get("evidence") or [])[:2]),
                decay="intraday to 1 trading day",
            )

    rows = sorted(candidates.values(), key=lambda row: (-row["score"], row["ticker"]))[:max_items]
    return {
        "status": "has_data" if rows else "checked_clear",
        "count": len(rows),
        "rows": rows,
        "dedupe_rule": "One row per ticker; strongest evidence wins while source names are merged.",
    }
