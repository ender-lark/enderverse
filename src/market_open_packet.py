#!/usr/bin/env python3
"""Compact market-open operator packet.

The packet compresses the existing action, re-check, UW, reallocation, and dark
lane state into an ordered sequence for a low-attention market-open review.
It is not a new action engine and it never creates trade orders.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _ticker(action: dict[str, Any]) -> str:
    return str(action.get("ticker") or ("EVENT" if action.get("kind") == "event_risk" else "PORTFOLIO"))


def _action_label(action: dict[str, Any]) -> str:
    ticker = _ticker(action)
    what = str(action.get("what") or action.get("your_move") or "").strip()
    return f"{ticker}: {what}" if what else ticker


def _first_text(values: list[Any] | None) -> str:
    for value in values or []:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _dark_lanes(feed: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row for row in ((feed.get("lane_status") or {}).get("rows") or [])
        if isinstance(row, dict) and row.get("status") in {"not_checked", "stale", "failed"}
    ]


def _packet_row(
    *,
    priority: int,
    kind: str,
    label: str,
    why: str,
    next_step: str,
    blocks: str = "",
    source: str = "",
    command: str = "",
) -> dict[str, Any]:
    return {
        "priority": priority,
        "kind": kind,
        "label": label,
        "why": why,
        "next_step": next_step,
        "blocks": blocks,
        "source": source,
        "command": command,
    }


def build_market_open_packet(feed: dict[str, Any]) -> dict[str, Any]:
    actions = [row for row in (feed.get("actions") or []) if isinstance(row, dict)]
    key_now = [row for row in actions if row.get("decision_group") == "key_now"]
    rechecks = [row for row in actions if row.get("decision_group") == "recheck_before_acting"]
    backlog = [row for row in actions if row.get("decision_group") == "important_backlog"]
    dark_lanes = _dark_lanes(feed)
    reallocation = feed.get("reallocation_brief") or {}
    social = feed.get("social_watch") or {}
    uw_rows = (feed.get("uw_action_runbook") or {}).get("rows") or []
    rows: list[dict[str, Any]] = []

    if rechecks:
        action = rechecks[0]
        freshness = action.get("freshness_judgment") or {}
        disconfirmation = action.get("disconfirmation") or {}
        rows.append(_packet_row(
            priority=1,
            kind="recheck_first",
            label=f"Re-check first: {_action_label(action)}",
            why=str(freshness.get("judgment") or action.get("why_this_matters") or action.get("why") or ""),
            next_step=_first_text(disconfirmation.get("confirm_before_acting") or action.get("missing_evidence") or [])
            or "Refresh same-session evidence before any capital move.",
            blocks=str(disconfirmation.get("summary") or "Do not act until fast-moving evidence is fresh."),
            source=str(action.get("source") or ""),
        ))

    if key_now:
        action = key_now[0]
        capital = action.get("capital_efficiency") or {}
        disconfirmation = action.get("disconfirmation") or {}
        rows.append(_packet_row(
            priority=2,
            kind="gate_key_now",
            label=f"Gate Key Now: {_action_label(action)}",
            why=str(capital.get("summary") or action.get("why_this_matters") or action.get("why") or ""),
            next_step=str(action.get("your_move") or "Run the pre-action gate and decide explicitly."),
            blocks=_first_text(disconfirmation.get("invalidates_if") or action.get("missing_evidence") or []),
            source=str(action.get("source") or ""),
        ))

    if reallocation.get("status") == "test_data_only":
        rows.append(_packet_row(
            priority=3,
            kind="positions_blocker",
            label="Reallocation waits for current positions",
            why=str(reallocation.get("line") or "Reallocation brief is test-data only."),
            next_step="Supply current positions before treating trim/add legs as current.",
            blocks=_first_text(reallocation.get("blockers") or []),
            source="reallocation_brief",
            command=str(reallocation.get("command") or ""),
        ))

    for uw in [row for row in uw_rows if isinstance(row, dict)][:3]:
        rows.append(_packet_row(
            priority=4 + len([r for r in rows if r.get("kind") == "uw_check"]),
            kind="uw_check",
            label=f"Run UW check set: {uw.get('label') or uw.get('mode') or 'UW'}",
            why=str(uw.get("operator_question") or uw.get("why") or ""),
            next_step="Use the listed endpoint group before promoting any capital-sized action.",
            blocks=str(uw.get("blocks_action_if") or ""),
            source="uw_action_runbook",
            command=str((feed.get("uw_action_runbook") or {}).get("command") or ""),
        ))

    if social.get("status") == "not_checked":
        rows.append(_packet_row(
            priority=max([int(row.get("priority") or 0) for row in rows] or [0]) + 1,
            kind="dark_lane",
            label="Social Watch is not checked",
            why=str((next((row.get("missing_impact") for row in dark_lanes if row.get("key") == "social_watch"), "")) or social.get("line") or ""),
            next_step="Do not infer no social anomaly; populate social_watch.json only through compliant API/cache intake.",
            blocks="Social evidence cannot promote a trade without independent confirmation.",
            source="social_watch",
            command=str(social.get("command") or ""),
        ))

    open_actions = (feed.get("feedback") or {}).get("open_actions") or {}
    if open_actions.get("count"):
        rows.append(_packet_row(
            priority=max([int(row.get("priority") or 0) for row in rows] or [0]) + 1,
            kind="open_reviews",
            label=f"Open reviews: {open_actions.get('count')} item(s)",
            why=str(open_actions.get("line") or ""),
            next_step="Keep visible; resolve only after act, invalidate, defer, ignore, or miss is explicit.",
            blocks="Open reviews are not build blockers unless due or stale.",
            source="action_memory",
        ))

    rows = sorted(rows, key=lambda row: int(row.get("priority") or 99))[:8]
    blockers = [
        row.get("blocks") for row in rows
        if row.get("blocks") and row.get("kind") in {"recheck_first", "positions_blocker", "dark_lane"}
    ]
    status = "recheck_first" if rechecks else "ready_with_blockers" if blockers else "ready"
    line = (
        f"Market-open packet: {len(key_now)} key, {len(rechecks)} re-check, "
        f"{len(backlog)} backlog; {len(blockers)} blocker(s)."
    )
    return {
        "status": status,
        "line": line,
        "rows": rows,
        "counts": {
            "key_now": len(key_now),
            "recheck": len(rechecks),
            "backlog": len(backlog),
            "dark_lanes": len(dark_lanes),
            "blockers": len(blockers),
        },
        "blockers": blockers,
        "honesty_rule": "Decision packet sequences review work only; it does not execute or recommend un-gated trades.",
    }


def _format_text(block: dict[str, Any]) -> str:
    lines = [block.get("line") or "Market-open packet"]
    if block.get("honesty_rule"):
        lines.append(f"honesty: {block['honesty_rule']}")
    for row in block.get("rows") or []:
        lines.append(f"{row.get('priority')}. {row.get('label')}")
        if row.get("why"):
            lines.append(f"   why: {row.get('why')}")
        if row.get("next_step"):
            lines.append(f"   next: {row.get('next_step')}")
        if row.get("blocks"):
            lines.append(f"   blocks: {row.get('blocks')}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Print market-open decision packet.")
    parser.add_argument("--feed", default=str(Path(__file__).resolve().parent / "latest_cockpit_feed.json"))
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    feed = json.loads(Path(args.feed).read_text(encoding="utf-8"))
    block = build_market_open_packet(feed)
    if args.format == "json":
        print(json.dumps(block, indent=2, sort_keys=True))
    else:
        print(_format_text(block))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
