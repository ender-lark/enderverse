#!/usr/bin/env python3
"""Blocker-only alert policy for Investing OS.

This module decides what would be eligible for an external alert. It does not
send notifications. The intent is to keep future Pushover or similar wiring
from alerting on routine dashboard updates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


_DOSSIER_ACTION_DIRECTIONS = {"BUY", "ADD", "TRIM", "SELL", "REDUCE", "HEDGE"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _add(
    rows: list[dict[str, Any]],
    *,
    severity: str,
    kind: str,
    title: str,
    why: str,
    source: str = "",
    ticker: str = "",
    trigger: str = "",
    next_step: str = "",
) -> None:
    key = (severity, kind, title, source, ticker)
    if any(row.get("_key") == key for row in rows):
        return
    rows.append({
        "_key": key,
        "severity": severity,
        "kind": kind,
        "ticker": ticker,
        "title": title,
        "why": why,
        "source": source,
        "trigger": trigger,
        "next_step": next_step,
        "delivery": "eligible_review_only",
    })


def _strip_private(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in row.items() if k != "_key"} for row in rows]


def _calibration_detail(calibration: dict[str, Any]) -> str:
    line = _text(calibration.get("line"))
    if line:
        return line
    days = int(calibration.get("worst_days_behind") or 0)
    return f"Fundstrat source-call calibration chain is stale ({days}d behind)."


def _card_direction(card: dict[str, Any]) -> str:
    move = (card.get("decision_card") or {}).get("move") or {}
    direction = _text(move.get("direction") or card.get("direction")).upper()
    return "TRIM" if direction == "REDUCE" else direction


def _card_is_alert_actionable(card: dict[str, Any]) -> bool:
    if _card_direction(card) not in _DOSSIER_ACTION_DIRECTIONS:
        return False
    if _text(card.get("action_state")).upper() == "ACT_NOW":
        return True
    if _text(card.get("decision_group")).lower() == "key_now":
        return True
    return _text((card.get("window") or {}).get("class")).upper() == "OPEN-NOW"


def _dossier_item_applies_to_card(item: dict[str, Any], card: dict[str, Any]) -> bool:
    item_ticker = _text(item.get("ticker")).upper()
    card_ticker = _text(card.get("ticker")).upper()
    card_id = _text(card.get("card_id"))
    item_card_ids = {_text(value) for value in item.get("card_ids") or [] if _text(value)}
    return bool((item_ticker and item_ticker == card_ticker) or (card_id and card_id in item_card_ids))


def _dossier_health_items(feed: dict[str, Any]) -> list[dict[str, Any]]:
    today = feed.get("today_decide") or {}
    health = today.get("data_health") or {}
    return [
        item for item in health.get("items") or []
        if isinstance(item, dict) and item.get("source") == "decision_dossier" and item.get("blocks")
    ]


def build_alert_policy(feed: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    system_health: list[dict[str, Any]] = []

    lane_rows = [
        row for row in ((feed.get("lane_status") or {}).get("rows") or [])
        if isinstance(row, dict)
    ]
    failed_lanes = [row for row in lane_rows if row.get("status") == "failed"]
    for lane in failed_lanes:
        _add(
            rows,
            severity="critical",
            kind="source_failed",
            title=f"{lane.get('label') or lane.get('key') or 'Source'} failed",
            why=_text(lane.get("missing_impact") or lane.get("detail") or "A source lane failed."),
            source=_text(lane.get("key")),
            trigger="source lane status=failed",
            next_step="Check the failed source lane before relying on decisions that depend on it.",
        )

    social_dark = [
        row for row in lane_rows
        if row.get("key") == "social_watch" and row.get("status") == "not_checked"
    ]
    if social_dark:
        suppressed.append({
            "reason": "optional_dark_lane",
            "count": len(social_dark),
            "why": "Social Watch is intentionally queued/dark; absence is not an alert.",
        })

    calibration = (
        ((feed.get("feedback") or {}).get("source_calls") or {}).get("calibration") or {}
    )
    if calibration.get("status") == "stale":
        days = int(calibration.get("worst_days_behind") or 0)
        stale_hops = ", ".join(
            str(h).replace("_", "->") for h in (calibration.get("stale_hops") or [])
        )
        _add(
            rows,
            severity="high" if days >= 2 else "warn",
            kind="source_call_calibration_stale",
            title="Fundstrat source-call chain is stale",
            why=_calibration_detail(calibration),
            source="source_call_calibration",
            trigger=(
                f"calibration.status=stale; days_behind={days}"
                + (f"; stale_hops={stale_hops}" if stale_hops else "")
            ),
            next_step=(
                "Classify the Fundstrat inbox into the Source Call Log and regenerate "
                "source_calls.json before relying on Fundstrat/source-call evidence."
            ),
        )

    for action in feed.get("actions") or []:
        if not isinstance(action, dict):
            continue
        refresh = action.get("assumption_refresh") or {}
        status = _text(refresh.get("status"))
        blockers = [b for b in (refresh.get("blockers") or []) if _text(b)]
        ticker = _text(action.get("ticker")) or "EVENT"
        title = _text(action.get("what") or action.get("your_move") or ticker)
        if status == "invalidated":
            _add(
                rows,
                severity="critical",
                kind="urgent_invalidation",
                ticker=ticker,
                title=title,
                why=_text(refresh.get("next_step") or "Action assumptions were invalidated."),
                source=_text(action.get("source") or action.get("kind")),
                trigger="assumption_refresh.status=invalidated",
                next_step="Do not act on the old setup; resolve or re-run the action gate.",
            )
        elif action.get("action_state") == "ACT_NOW" and blockers:
            _add(
                rows,
                severity="high",
                kind="blocked_key_action",
                ticker=ticker,
                title=title,
                why="Key action is blocked by " + ", ".join(str(b) for b in blockers[:3]),
                source=_text(action.get("source") or action.get("kind")),
                trigger="ACT_NOW with assumption blockers",
                next_step="Clear the blocker before acting; do not trade from the headline alone.",
            )
        elif status in {"changed_recheck", "stale"}:
            suppressed.append({
                "reason": "dashboard_recheck",
                "ticker": ticker,
                "why": "Re-check item stays visible in the dashboard; no alert unless it becomes invalidated or ACT_NOW-blocked.",
            })

    dossier_items = _dossier_health_items(feed)
    alerted_dossier_items: set[int] = set()
    today = feed.get("today_decide") or {}
    for card in today.get("cards") or []:
        if not isinstance(card, dict) or not _card_is_alert_actionable(card):
            continue
        for item in dossier_items:
            if not _dossier_item_applies_to_card(item, card):
                continue
            ticker = _text(card.get("ticker") or item.get("ticker"))
            direction = _card_direction(card) or "action"
            _add(
                rows,
                severity="high",
                kind="decision_dossier_freshness_blocker",
                ticker=ticker,
                title=f"{ticker} dossier freshness blocks {direction}",
                why=_text(item.get("detail") or "Decision dossier freshness blocks this action."),
                source="decision_dossier",
                trigger=(
                    f"today_decide.data_health decision_dossier status={item.get('status')}; "
                    f"card={card.get('card_id') or ticker}"
                ),
                next_step=(
                    "Re-sync or refresh the Live Theses dossier before acting; "
                    "stale/not-checked dossier reads must stay UNKNOWN."
                ),
            )
            alerted_dossier_items.add(id(item))
    quiet_dossier_count = len([item for item in dossier_items if id(item) not in alerted_dossier_items])
    if quiet_dossier_count:
        suppressed.append({
            "reason": "dossier_dashboard_blocker",
            "count": quiet_dossier_count,
            "why": "Dossier freshness blockers stay on the matching Today card unless the blocked card is alert-actionable.",
        })

    event_rows = [
        row for row in (feed.get("event_risk") or [])
        if isinstance(row, dict) and row.get("severity") == "critical"
    ]
    for event in event_rows:
        _add(
            rows,
            severity="high",
            kind="critical_event_risk",
            title=_text(event.get("title") or "Critical event risk"),
            why=_text(event.get("summary") or "Critical event risk requires operator review."),
            source="event_risk",
            trigger=_text(event.get("trigger")),
            next_step="Review affected holdings, new buys, hedges, and trims before adding risk.",
        )

    open_actions = ((feed.get("feedback") or {}).get("open_actions") or {})
    stale_reviews = [
        row for row in (open_actions.get("items") or [])
        if isinstance(row, dict) and int(row.get("age_days") or 0) >= 5
    ]
    for review in stale_reviews:
        _add(
            rows,
            severity="high",
            kind="stale_open_review",
            ticker=_text(review.get("ticker")),
            title=f"{review.get('ticker') or 'Open review'} is stale",
            why="Open review is stale; resolve as acted, invalidated, missed, ignored, or explicitly deferred.",
            source="action_memory",
            trigger="open review age >= 5 trading days",
            next_step="Resolve the stale review so old prompts do not masquerade as current decisions.",
        )
    new_reviews = int(open_actions.get("count") or 0) - len(stale_reviews)
    if new_reviews > 0:
        suppressed.append({
            "reason": "fresh_open_reviews",
            "count": new_reviews,
            "why": "Fresh open reviews stay visible but do not alert until due/stale or invalidated.",
        })

    cloud = ((feed.get("source_audits") or {}).get("cloud_routines") or {})
    failed_latest = int(cloud.get("failed_latest_count") or 0)
    if failed_latest:
        system_health.append({
            "severity": "warn",
            "kind": "cloud_routine_failed",
            "title": f"{failed_latest} cloud routine(s) failed latest receipt",
            "why": _text(cloud.get("line") or "A cloud routine failed its latest receipt."),
            "source": "cloud_routines",
            "trigger": "failed_latest_count > 0",
            "next_step": "Check Ops/System Health when debugging routines; this is not a portfolio alert.",
        })
    missing_scheduled = int(cloud.get("missing_scheduled_success_count") or 0)
    if missing_scheduled:
        suppressed.append({
            "reason": "background_cloud_proof",
            "count": missing_scheduled,
            "why": "Natural-schedule proof gaps are monitored in the dashboard, not alerted unless failed/overdue.",
        })

    clean_rows = _strip_private(rows)
    status = "notify" if clean_rows else "quiet"
    line = (
        f"Push alerts: {len(clean_rows)} action-relevant alert candidate(s)."
        if clean_rows else
        "Push alerts: quiet - no market/action item qualifies for notification."
    )
    return {
        "status": status,
        "line": line,
        "rows": clean_rows,
        "suppressed": suppressed[:8],
        "system_health": system_health[:8],
        "policy": "Push alerts only interrupt for action-changing market, portfolio, Fundstrat, dossier-freshness, stale-review, or invalidated-decision items. Routine/system-health warnings stay in Ops.",
        "delivery": "review_only_no_send",
    }


def _format_text(block: dict[str, Any]) -> str:
    lines = [block.get("line") or "Alert policy"]
    lines.append(f"policy: {block.get('policy') or ''}")
    for row in block.get("rows") or []:
        lines.append(f"- ALERT {row.get('severity')}: {row.get('title')} [{row.get('kind')}]")
        if row.get("why"):
            lines.append(f"  why: {row.get('why')}")
        if row.get("trigger"):
            lines.append(f"  trigger: {row.get('trigger')}")
        if row.get("next_step"):
            lines.append(f"  next: {row.get('next_step')}")
    for row in block.get("system_health") or []:
        lines.append(f"- system {row.get('severity')}: {row.get('title')} [{row.get('kind')}]")
        if row.get("why"):
            lines.append(f"  why: {row.get('why')}")
        if row.get("next_step"):
            lines.append(f"  next: {row.get('next_step')}")
    for row in block.get("suppressed") or []:
        lines.append(f"- quiet {row.get('reason')}: {row.get('why')}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate blocker-only alert policy.")
    parser.add_argument("--feed", default=str(Path(__file__).resolve().parent / "latest_cockpit_feed.json"))
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    feed = json.loads(Path(args.feed).read_text(encoding="utf-8"))
    block = build_alert_policy(feed)
    if args.format == "json":
        print(json.dumps(block, indent=2, sort_keys=True))
    else:
        print(_format_text(block))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
