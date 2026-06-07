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


def _text(value: Any) -> str:
    return str(value or "").strip()


def _add(rows: list[dict[str, Any]], *, severity: str, kind: str, title: str,
         why: str, source: str = "", ticker: str = "", trigger: str = "") -> None:
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
        "delivery": "eligible_review_only",
    })


def _strip_private(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in row.items() if k != "_key"} for row in rows]


def build_alert_policy(feed: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []

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
            )
        elif status in {"changed_recheck", "stale"}:
            suppressed.append({
                "reason": "dashboard_recheck",
                "ticker": ticker,
                "why": "Re-check item stays visible in the dashboard; no alert unless it becomes invalidated or ACT_NOW-blocked.",
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
        _add(
            rows,
            severity="critical",
            kind="cloud_routine_failed",
            title=f"{failed_latest} cloud routine(s) failed latest receipt",
            why=_text(cloud.get("line") or "A cloud routine failed its latest receipt."),
            source="cloud_routines",
            trigger="failed_latest_count > 0",
        )
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
        f"Alert policy: {len(clean_rows)} blocker/urgent invalidation alert candidate(s)."
        if clean_rows else
        "Alert policy: quiet - no blocker or urgent invalidation qualifies for notification."
    )
    return {
        "status": status,
        "line": line,
        "rows": clean_rows,
        "suppressed": suppressed[:8],
        "policy": "Only blockers, failed proof, stale reviews, critical event risk, or urgent invalidations can alert; routine dashboard updates stay quiet.",
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
