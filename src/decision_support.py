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
