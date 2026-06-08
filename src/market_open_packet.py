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


def _first_instruction(values: list[Any] | None) -> str:
    for value in values or []:
        text = str(value or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered.startswith(("check ", "confirm ", "refresh ", "run ", "review ", "decide ", "use ")):
            return text
    return ""


def _text_list(values: list[Any] | None) -> list[str]:
    return [str(value).strip() for value in values or [] if str(value or "").strip()]


def _action_packet_metadata(action: dict[str, Any]) -> dict[str, Any]:
    freshness = action.get("freshness_judgment") or {}
    disconfirmation = action.get("disconfirmation") or {}
    refresh = action.get("assumption_refresh") or {}
    capital = action.get("capital_efficiency") or {}
    placement = action.get("account_placement") or {}
    snapshot = refresh.get("snapshot") or {}
    assumptions: list[str] = []
    evidence_date = str(freshness.get("evidence_date") or snapshot.get("evidence_date") or "")
    freshness_label = str(freshness.get("label") or snapshot.get("freshness") or "")
    decay_window = str(freshness.get("decay_window") or snapshot.get("decay_window") or "")
    last_checked = str(freshness.get("last_checked") or refresh.get("checked_at") or "")
    if freshness_label or evidence_date:
        assumptions.append(f"evidence {evidence_date or 'n/a'} is {freshness_label or 'unlabeled'}")
    if decay_window:
        assumptions.append(f"decays {decay_window}")
    if snapshot.get("time_window") or action.get("time_window"):
        assumptions.append(f"time window {snapshot.get('time_window') or action.get('time_window')}")
    if snapshot.get("capital_label") or capital.get("label"):
        assumptions.append(f"capital posture {snapshot.get('capital_label') or capital.get('label')}")
    invalidates = _first_text(
        _text_list(refresh.get("invalidates_if"))
        + _text_list(disconfirmation.get("invalidates_if"))
    )
    return {
        "freshness_label": freshness_label,
        "evidence_date": evidence_date,
        "last_checked": last_checked,
        "decay_window": decay_window,
        "key_assumptions": "; ".join(assumptions),
        "invalidates": invalidates,
        "do_nothing_risk": str(capital.get("do_nothing_risk") or ""),
        "capital_priority_reason": str(capital.get("priority_reason") or capital.get("summary") or ""),
        "capital_priority_score": (
            int(action.get("capital_priority_score"))
            if isinstance(action.get("capital_priority_score"), int)
            else None
        ),
        "compare_against": " / ".join(_text_list(capital.get("compare_against"))),
        "account_placement": placement,
        "account_placement_summary": str(placement.get("summary") or ""),
        "account_placement_why": str(placement.get("why") or ""),
    }


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
    refresh_status: str = "",
    what_changed: str = "",
    freshness_label: str = "",
    evidence_date: str = "",
    last_checked: str = "",
    decay_window: str = "",
    key_assumptions: str = "",
    invalidates: str = "",
    do_nothing_risk: str = "",
    capital_priority_reason: str = "",
    capital_priority_score: int | None = None,
    compare_against: str = "",
    account_placement: dict[str, Any] | None = None,
    account_placement_summary: str = "",
    account_placement_why: str = "",
) -> dict[str, Any]:
    row = {
        "priority": priority,
        "kind": kind,
        "label": label,
        "why": why,
        "next_step": next_step,
        "blocks": blocks,
        "source": source,
        "command": command,
        "refresh_status": refresh_status,
        "what_changed": what_changed,
    }
    for key, value in {
        "freshness_label": freshness_label,
        "evidence_date": evidence_date,
        "last_checked": last_checked,
        "decay_window": decay_window,
        "key_assumptions": key_assumptions,
        "invalidates": invalidates,
        "do_nothing_risk": do_nothing_risk,
        "capital_priority_reason": capital_priority_reason,
        "compare_against": compare_against,
        "account_placement_summary": account_placement_summary,
        "account_placement_why": account_placement_why,
    }.items():
        if value:
            row[key] = value
    if capital_priority_score is not None:
        row["capital_priority_score"] = capital_priority_score
    if isinstance(account_placement, dict) and account_placement:
        row["account_placement"] = account_placement
    return row


def build_market_open_packet(feed: dict[str, Any]) -> dict[str, Any]:
    actions = [row for row in (feed.get("actions") or []) if isinstance(row, dict)]
    key_now = [row for row in actions if row.get("decision_group") == "key_now"]
    rechecks = [row for row in actions if row.get("decision_group") == "recheck_before_acting"]
    backlog = [row for row in actions if row.get("decision_group") == "important_backlog"]
    dark_lanes = _dark_lanes(feed)
    reallocation = feed.get("reallocation_brief") or {}
    social = feed.get("social_watch") or {}
    uw_runbook = feed.get("uw_action_runbook") or {}
    uw_rows = uw_runbook.get("rows") or []
    uw_proof = uw_runbook.get("endpoint_proof") or feed.get("uw_endpoint_proof") or {}
    uw_proof_status = str(uw_proof.get("status") or "")
    uw_proof_blockers = [str(item) for item in (uw_proof.get("blockers") or []) if str(item or "").strip()]
    uw_proof_blocking = bool(uw_rows) and (uw_proof_status != "has_data" or bool(uw_proof_blockers))
    uw_proof_gap = (
        "Endpoint result proof not captured; runbook is instructions only."
        if uw_proof_blocking and uw_proof_status not in {"failed", "has_data"}
        else "Endpoint result proof is malformed or failed; do not promote without clean proof."
        if uw_proof_blocking and uw_proof_status == "failed"
        else f"UW endpoint proof has blocker: {uw_proof_blockers[0]}"
        if uw_proof_blocking and uw_proof_blockers
        else ""
    )
    rows: list[dict[str, Any]] = []
    priority = 1

    def next_priority() -> int:
        nonlocal priority
        value = priority
        priority += 1
        return value

    for action in rechecks:
        freshness = action.get("freshness_judgment") or {}
        disconfirmation = action.get("disconfirmation") or {}
        refresh = action.get("assumption_refresh") or {}
        metadata = _action_packet_metadata(action)
        rows.append(_packet_row(
            priority=next_priority(),
            kind="recheck_first",
            label=f"Re-check: {_action_label(action)}",
            why=str(freshness.get("judgment") or action.get("why_this_matters") or action.get("why") or ""),
            next_step=_first_instruction(disconfirmation.get("confirm_before_acting") or [])
            or str(refresh.get("next_step") or "")
            or _first_text(action.get("missing_evidence") or [])
            or "Refresh same-session evidence before any capital move.",
            blocks=str(disconfirmation.get("summary") or "Do not act until fast-moving evidence is fresh."),
            source=str(action.get("source") or ""),
            refresh_status=str(refresh.get("status") or ""),
            what_changed=_first_text(refresh.get("what_changed") or []),
            **metadata,
        ))

    for action in key_now:
        capital = action.get("capital_efficiency") or {}
        disconfirmation = action.get("disconfirmation") or {}
        refresh = action.get("assumption_refresh") or {}
        metadata = _action_packet_metadata(action)
        rows.append(_packet_row(
            priority=next_priority(),
            kind="gate_key_now",
            label=f"Gate Key Now: {_action_label(action)}",
            why=str(capital.get("summary") or action.get("why_this_matters") or action.get("why") or ""),
            next_step=str(action.get("your_move") or "Run the pre-action gate and decide explicitly."),
            blocks=_first_text(disconfirmation.get("invalidates_if") or action.get("missing_evidence") or []),
            source=str(action.get("source") or ""),
            refresh_status=str(refresh.get("status") or ""),
            what_changed=_first_text(refresh.get("what_changed") or []),
            **metadata,
        ))

    if reallocation.get("status") == "test_data_only":
        rows.append(_packet_row(
            priority=next_priority(),
            kind="positions_blocker",
            label="Reallocation waits for current positions",
            why=str(reallocation.get("line") or "Reallocation brief is test-data only."),
            next_step="Supply current positions before treating trim/add legs as current.",
            blocks=_first_text(reallocation.get("blockers") or []),
            source="reallocation_brief",
            command=str(reallocation.get("command") or ""),
        ))
    elif reallocation.get("status") == "candidate_only":
        rows.append(_packet_row(
            priority=next_priority(),
            kind="reallocation_review",
            label="Review current-position reallocation candidates",
            why=str(reallocation.get("line") or "Same-day positions are available for candidate reallocation."),
            next_step="Review funded add/trim legs, then run same-session UW/price and tax/account gates before acting.",
            blocks=_first_text(reallocation.get("blockers") or []),
            source="reallocation_brief",
            command=str(reallocation.get("command") or ""),
            refresh_status="changed_recheck" if reallocation.get("blockers") else "still_valid",
            what_changed="Current SnapTrade positions replaced stale PDF-era position assumptions.",
        ))

    for action in backlog:
        refresh = action.get("assumption_refresh") or {}
        disconfirmation = action.get("disconfirmation") or {}
        metadata = _action_packet_metadata(action)
        rows.append(_packet_row(
            priority=next_priority(),
            kind="important_backlog",
            label=f"Review backlog: {_action_label(action)}",
            why=str(action.get("why_this_matters") or action.get("why") or ""),
            next_step=str(action.get("your_move") or refresh.get("next_step") or "Decide whether to defer, keep watching, or promote after fresh checks."),
            blocks=_first_text((refresh.get("invalidates_if") or []) + (disconfirmation.get("invalidates_if") or [])),
            source=str(action.get("source") or ""),
            refresh_status=str(refresh.get("status") or ""),
            what_changed=_first_text(refresh.get("what_changed") or []),
            **metadata,
        ))

    for uw in [row for row in uw_rows if isinstance(row, dict)]:
        blocks = str(uw.get("blocks_action_if") or "")
        if uw_proof_gap:
            blocks = f"{blocks}; {uw_proof_gap}" if blocks else uw_proof_gap
        rows.append(_packet_row(
            priority=next_priority(),
            kind="uw_check",
            label=f"Run UW check set: {uw.get('label') or uw.get('mode') or 'UW'}",
            why=str(uw.get("operator_question") or uw.get("why") or ""),
            next_step=(
                "Capture endpoint results, then use the listed endpoint group before promoting any capital-sized action."
                if uw_proof_status != "has_data" else
                "Use the captured endpoint result proof before promoting any capital-sized action."
            ),
            blocks=blocks,
            source="uw_action_runbook",
            command=str(uw_runbook.get("command") or ""),
        ))

    if social.get("status") == "not_checked":
        rows.append(_packet_row(
            priority=next_priority(),
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
            priority=next_priority(),
            kind="open_reviews",
            label=f"Open reviews: {open_actions.get('count')} item(s)",
            why=str(open_actions.get("line") or ""),
            next_step="Keep visible; resolve only after act, invalidate, defer, ignore, or miss is explicit.",
            blocks="Open reviews are not build blockers unless due or stale.",
            source="action_memory",
        ))

    rows = sorted(rows, key=lambda row: int(row.get("priority") or 99))
    blocker_kinds = {"recheck_first", "positions_blocker", "dark_lane"}
    if uw_proof_blocking:
        blocker_kinds.add("uw_check")
    blockers = [
        row.get("blocks") for row in rows
        if row.get("blocks") and row.get("kind") in blocker_kinds
    ]
    urgent_count = len(key_now) + len(rechecks) + len(backlog)
    status = "recheck_first" if rechecks else "ready_with_blockers" if blockers else "ready"
    line = (
        f"Market-open packet: {len(key_now)} key, {len(rechecks)} re-check, "
        f"{len(backlog)} backlog, {urgent_count} urgent visible; {len(blockers)} blocker(s)."
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
            "urgent_visible": urgent_count,
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
        if row.get("refresh_status"):
            lines.append(f"   refresh: {str(row.get('refresh_status')).replace('_', ' ')}")
        if row.get("what_changed"):
            lines.append(f"   changed: {row.get('what_changed')}")
        if row.get("freshness_label") or row.get("evidence_date") or row.get("decay_window"):
            lines.append(
                "   freshness: "
                f"{row.get('freshness_label') or 'n/a'}; "
                f"evidence {row.get('evidence_date') or 'n/a'}; "
                f"checked {row.get('last_checked') or 'n/a'}; "
                f"decays {row.get('decay_window') or 'source dependent'}"
            )
        if row.get("key_assumptions"):
            lines.append(f"   assumptions: {row.get('key_assumptions')}")
        if row.get("why"):
            lines.append(f"   why: {row.get('why')}")
        if row.get("capital_priority_score") is not None or row.get("capital_priority_reason"):
            score = row.get("capital_priority_score")
            prefix = f"priority {score}: " if score is not None else "priority: "
            lines.append(f"   {prefix}{row.get('capital_priority_reason') or 'compare against better current uses of capital'}")
        if row.get("do_nothing_risk"):
            lines.append(f"   do nothing: {row.get('do_nothing_risk')}")
        if row.get("next_step"):
            lines.append(f"   next: {row.get('next_step')}")
        if row.get("invalidates"):
            lines.append(f"   invalidates: {row.get('invalidates')}")
        if row.get("compare_against"):
            lines.append(f"   compare: {row.get('compare_against')}")
        if row.get("account_placement_summary"):
            lines.append(f"   account: {row.get('account_placement_summary')}")
        if row.get("account_placement_why"):
            lines.append(f"   account why: {row.get('account_placement_why')}")
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
