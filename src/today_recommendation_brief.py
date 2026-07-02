#!/usr/bin/env python3
"""Chat-first daily recommendation packet.

This module compresses the existing feed into the answer the operator usually
asks for in chat: "What should I do today?" It does not score trades, fetch
data, or place orders. It sequences already-built blocks and keeps dark lanes
visible.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return [value]


def _clean_list(value: Any, *, limit: int | None = None) -> list[str]:
    rows = [_text(item) for item in _as_list(value) if _text(item)]
    return rows[:limit] if limit is not None else rows


def _money(value: Any) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return ""
    if amount >= 1000:
        return f"${amount:,.0f}"
    return f"${amount:,.2f}"


def _pct(value: Any) -> str:
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return ""


def _packet_rows(feed: dict[str, Any]) -> list[dict[str, Any]]:
    packet = feed.get("market_open_packet") or {}
    return [row for row in packet.get("rows") or [] if isinstance(row, dict)]


def _feed_as_of(feed: dict[str, Any]) -> str:
    for value in (
        feed.get("as_of"),
        feed.get("book_as_of"),
        (feed.get("today_decide") or {}).get("as_of") if isinstance(feed.get("today_decide"), dict) else "",
        (feed.get("fed_day_reallocation_packet") or {}).get("as_of")
        if isinstance(feed.get("fed_day_reallocation_packet"), dict)
        else "",
    ):
        text = _text(value)
        if text:
            return text[:10]
    generated = _text(feed.get("generated_at"))
    return generated[:10] if generated else ""


def _alert_rows(feed: dict[str, Any]) -> list[dict[str, Any]]:
    alert = feed.get("alert_policy") or {}
    return [row for row in alert.get("rows") or [] if isinstance(row, dict)]


def _row_from_packet(row: dict[str, Any], *, kind: str | None = None) -> dict[str, Any]:
    return {
        "rank": int(row.get("priority") or 0) or None,
        "kind": kind or _text(row.get("kind")) or "packet",
        "title": _text(row.get("label")),
        "ticker": _text(row.get("ticker")),
        "why": _text(row.get("why")),
        "next_step": _text(row.get("next_step")),
        "blocks": _text(row.get("blocks")),
        "source": _text(row.get("source")),
        "command": _text(row.get("command")),
        "freshness": {
            "label": _text(row.get("freshness_label")),
            "evidence_date": _text(row.get("evidence_date")),
            "last_checked": _text(row.get("last_checked")),
            "decay_window": _text(row.get("decay_window")),
        },
        "capital_priority_score": row.get("capital_priority_score"),
        "capital_priority_reason": _text(row.get("capital_priority_reason")),
        "do_nothing_risk": _text(row.get("do_nothing_risk")),
    }


def _row_from_alert(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": _text(row.get("kind")) or "alert",
        "severity": _text(row.get("severity")) or "warn",
        "title": _text(row.get("title")),
        "ticker": _text(row.get("ticker")),
        "why": _text(row.get("why")),
        "trigger": _text(row.get("trigger")),
        "next_step": _text(row.get("next_step")),
        "source": _text(row.get("source")),
        "push_candidate": True,
        "delivery": _text(row.get("delivery")) or "eligible_review_only",
    }


def _option_expiry(row: dict[str, Any]) -> str:
    legs = [leg for leg in row.get("legs") or [] if isinstance(leg, dict)]
    expiries = [_text(leg.get("expiry")) for leg in legs if _text(leg.get("expiry"))]
    return expiries[0] if expiries else ""


def _option_dte(row: dict[str, Any]) -> str:
    legs = [leg for leg in row.get("legs") or [] if isinstance(leg, dict)]
    for leg in legs:
        value = leg.get("dte")
        if value is not None:
            return str(value)
    return ""


def _option_rows(feed: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    block = feed.get("options_expression")
    if not isinstance(block, dict):
        options = {
            "status": "not_checked",
            "line": "Options not checked: no options_expression block was built from options_chain_cache.json.",
            "rows": [],
            "count": 0,
            "next_step": (
                "Refresh the bounded UW options cache before treating the daily options "
                "scan as checked."
            ),
            "command": "python src/options_chain_refresh.py --self-test",
            "honesty_rule": "Missing options data is not a clear read; no leverage edge is inferred.",
        }
        return options, []

    rows = []
    for raw in block.get("rows") or []:
        if not isinstance(raw, dict):
            continue
        risk_amount = _money(raw.get("risk_amount_usd"))
        risk_pct = _pct(raw.get("risk_pct_book"))
        risk = " / ".join(part for part in (risk_amount, risk_pct) if part)
        rows.append({
            "ticker": _text(raw.get("ticker")),
            "disposition": _text(raw.get("disposition")),
            "action": _text(raw.get("action")),
            "reason": _text(raw.get("reason")),
            "risk": risk,
            "risk_amount_usd": raw.get("risk_amount_usd"),
            "risk_pct_book": raw.get("risk_pct_book"),
            "expiry": _option_expiry(raw),
            "dte": _option_dte(raw),
            "iv_environment": _text(raw.get("iv_environment")),
            "expected_move_pct": raw.get("expected_move_pct"),
            "break_even_pct": raw.get("break_even_pct"),
            "the_catch": _text(raw.get("the_catch") or raw.get("evidence")),
            "defined_risk": True,
            "source": _text(raw.get("source") or "options_expression"),
        })
    act_rows = [row for row in rows if row.get("disposition") == "ACT"]
    options = {
        "status": _text(block.get("status")) or ("has_data" if rows else "checked_clear"),
        "line": _text(block.get("line")) or f"Options scan: {len(rows)} row(s).",
        "count": len(rows),
        "act_count": len(act_rows),
        "rows": rows[:8],
        "top": rows[:3],
        "command": _text(block.get("command") or "python src/options_chain_refresh.py --self-test"),
        "honesty_rule": (
            "Defined-risk review only. Max loss is real; options flow or cheap IV "
            "does not bypass thesis, liquidity, event-risk, or sizing gates."
        ),
    }
    return options, act_rows


def _social_block(feed: dict[str, Any]) -> dict[str, Any]:
    source = feed.get("social_watch") if isinstance(feed.get("social_watch"), dict) else {}
    if not source:
        return {
            "status": "not_checked",
            "line": "Social/Trump watch not checked: no social_watch block in the feed.",
            "rows": [],
            "count": 0,
            "watch_only": True,
            "next_step": "Populate social_watch.json from a compliant Reddit/UW-news intake before treating social anomalies as checked.",
        }
    rows = []
    for raw in source.get("rows") or []:
        if not isinstance(raw, dict):
            continue
        confirmations = _clean_list(raw.get("independent_confirmation"), limit=4)
        rows.append({
            "ticker": _text(raw.get("ticker")),
            "tickers": _clean_list(raw.get("tickers"), limit=8),
            "source": _text(raw.get("source")),
            "subreddits": _clean_list(raw.get("subreddits"), limit=8),
            "summary": _text(raw.get("summary")),
            "escalation": _text(raw.get("escalation") or "Quiet Watch"),
            "risk": _text(raw.get("risk")),
            "independent_confirmation": confirmations,
            "confirmation_required": _text(raw.get("confirmation_required")),
            "watch_only": True,
            "push_candidate": False,
        })
    return {
        "status": _text(source.get("status")) or "not_checked",
        "line": _text(source.get("line")),
        "count": len(rows),
        "rows": rows[:6],
        "watch_only": True,
        "promotion_rule": _text(source.get("promotion_rule")),
        "honesty_rule": _text(source.get("honesty_rule")) or "Watch-only until independently confirmed.",
        "command": _text(source.get("command")),
    }


def _not_checked_rows(feed: dict[str, Any], *, options: dict[str, Any], social: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in ((feed.get("lane_status") or {}).get("rows") or []):
        if not isinstance(row, dict):
            continue
        if row.get("status") not in {"not_checked", "stale", "failed"}:
            continue
        rows.append({
            "key": _text(row.get("key")),
            "label": _text(row.get("label") or row.get("key")),
            "status": _text(row.get("status")),
            "why": _text(row.get("missing_impact") or row.get("detail")),
            "next_step": _text(row.get("next_step")),
        })
    if options.get("status") == "not_checked" and not any(row.get("key") == "options_expression" for row in rows):
        rows.append({
            "key": "options_expression",
            "label": "Options Opportunity Scan",
            "status": "not_checked",
            "why": _text(options.get("line")),
            "next_step": _text(options.get("next_step")),
        })
    if social.get("status") == "not_checked" and not any(row.get("key") == "social_watch" for row in rows):
        rows.append({
            "key": "social_watch",
            "label": "Social Watch",
            "status": "not_checked",
            "why": _text(social.get("line")),
            "next_step": _text(social.get("next_step") or "Populate social_watch.json from compliant intake."),
        })
    return rows[:10]


def _opportunity_rows(packet_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    opportunity_kinds = {"gate_key_now", "important_backlog", "reallocation_review"}
    rows = [_row_from_packet(row, kind="opportunity_review") for row in packet_rows if row.get("kind") in opportunity_kinds]
    return rows[:6]


def _defensive_rows(packet_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    defensive_kinds = {"recheck_first", "positions_blocker"}
    rows = [_row_from_packet(row, kind="defensive_recheck") for row in packet_rows if row.get("kind") in defensive_kinds]
    return rows[:6]


def _push_candidates(alerts: list[dict[str, Any]], option_act_rows: list[dict[str, Any]], *, defensive_count: int) -> list[dict[str, Any]]:
    rows = [_row_from_alert(row) for row in alerts]
    for option in option_act_rows[:3]:
        rows.append({
            "kind": "options_act_review",
            "severity": "review",
            "ticker": option.get("ticker"),
            "title": f"{option.get('ticker')}: defined-risk options ACT candidate",
            "why": option.get("reason") or option.get("action"),
            "next_step": (
                "Review after clearing defensive rechecks."
                if defensive_count else
                "Confirm live chain/liquidity/event risk before acting."
            ),
            "source": "options_expression",
            "push_candidate": True,
            "delivery": "review_only_candidate",
            "blocked_by": "defensive_rechecks" if defensive_count else "",
        })
    return rows[:8]


def _headline(
    *,
    alerts: list[dict[str, Any]],
    defensive: list[dict[str, Any]],
    opportunities: list[dict[str, Any]],
    option_act_rows: list[dict[str, Any]],
    social: dict[str, Any],
) -> tuple[str, str]:
    if alerts:
        return (
            "alert_review",
            f"Today: review {len(alerts)} push-eligible blocker(s) before adding risk.",
        )
    if defensive:
        return (
            "defensive_recheck",
            f"Today: start defensively - clear {len(defensive)} re-check/blocker item(s) before adding new risk.",
        )
    if option_act_rows:
        first = option_act_rows[0].get("ticker") or "the top option setup"
        return (
            "options_review",
            f"Today: {len(option_act_rows)} defined-risk options candidate(s) are ready for review; start with {first}.",
        )
    if opportunities:
        return (
            "opportunity_review",
            f"Today: review {len(opportunities)} opportunity/reallocation item(s); start with {opportunities[0].get('title') or 'the top item'}.",
        )
    if social.get("status") == "has_data":
        return (
            "social_watch_only",
            "Today: social/Trump chatter is watch-only; do not make a capital move from it without independent confirmation.",
        )
    return (
        "quiet",
        "Today: no clean capital-sized move is proven by the current feed; preserve optionality and refresh dark lanes.",
    )


def build_today_recommendation_brief(feed: dict[str, Any]) -> dict[str, Any]:
    packet_rows = _packet_rows(feed)
    alerts = _alert_rows(feed)
    defensive = _defensive_rows(packet_rows)
    opportunities = _opportunity_rows(packet_rows)
    options, option_act_rows = _option_rows(feed)
    social = _social_block(feed)
    status, line = _headline(
        alerts=alerts,
        defensive=defensive,
        opportunities=opportunities,
        option_act_rows=option_act_rows,
        social=social,
    )

    do_today: list[dict[str, Any]] = []
    do_today.extend(_row_from_alert(row) for row in alerts[:3])
    do_today.extend(defensive[:3])
    if not do_today:
        do_today.extend({
            "kind": "options_act_review",
            "ticker": row.get("ticker"),
            "title": row.get("action"),
            "why": row.get("reason"),
            "next_step": "Confirm live chain/liquidity/event risk and size before acting.",
            "risk": row.get("risk"),
            "source": "options_expression",
        } for row in option_act_rows[:3])
    if not do_today:
        do_today.extend(opportunities[:3])
    if not do_today:
        do_today.append({
            "kind": "stand_down",
            "title": "Stand down from new risk until a sourced setup clears the gates.",
            "why": "No action, options, or social row currently has enough clean evidence to lead.",
            "next_step": "Refresh sources, then re-run the brief.",
            "source": "today_recommendation_brief",
        })

    not_checked = _not_checked_rows(feed, options=options, social=social)
    push_candidates = _push_candidates(alerts, option_act_rows, defensive_count=len(defensive))
    commands = [
        "python src/today_recommendation_brief.py --feed src/latest_cockpit_feed.json --format text",
        _text(options.get("command")),
        _text(social.get("command")),
        _text((feed.get("alert_policy") or {}).get("command")),
    ]
    commands = [cmd for cmd in commands if cmd]

    return {
        "status": status,
        "line": line,
        "as_of": _feed_as_of(feed),
        "generated_at": _text(feed.get("generated_at")),
        "do_today": do_today[:5],
        "defensive": {
            "count": len(defensive),
            "rows": defensive,
        },
        "opportunities": {
            "count": len(opportunities),
            "rows": opportunities,
        },
        "options": options,
        "social": social,
        "push_candidates": push_candidates,
        "not_checked": not_checked,
        "commands": commands,
        "source_blocks": [
            "market_open_packet",
            "today_decide",
            "options_expression",
            "social_watch",
            "alert_policy",
            "lane_status",
        ],
        "honesty_rule": (
            "Recommendation packet only. It does not execute trades, bypass gates, "
            "or promote Reddit/social evidence without independent confirmation."
        ),
    }


def _format_item(row: dict[str, Any], idx: int) -> list[str]:
    title = _text(row.get("title") or row.get("action") or row.get("ticker") or "item")
    lines = [f"{idx}. {title}"]
    if row.get("risk"):
        lines.append(f"   risk: {row.get('risk')}")
    if row.get("why"):
        lines.append(f"   why: {row.get('why')}")
    if row.get("next_step"):
        lines.append(f"   next: {row.get('next_step')}")
    if row.get("blocks"):
        lines.append(f"   blocks: {row.get('blocks')}")
    return lines


def format_today_recommendation_text(block: dict[str, Any]) -> str:
    lines = ["TODAY RECOMMENDATION", block.get("line") or ""]
    lines.append("")
    lines.append("Do today:")
    for idx, row in enumerate(block.get("do_today") or [], start=1):
        lines.extend(_format_item(row, idx))

    opportunities = (block.get("opportunities") or {}).get("rows") or []
    lines.append("")
    lines.append(f"Opportunities/reallocation: {len(opportunities)} review item(s).")
    for idx, row in enumerate(opportunities[:3], start=1):
        lines.extend(_format_item(row, idx))

    options = block.get("options") or {}
    lines.append("")
    lines.append(f"Options: {options.get('line') or options.get('status') or 'not checked'}")
    for idx, row in enumerate((options.get("rows") or [])[:3], start=1):
        label = row.get("action") or row.get("ticker") or "option"
        lines.append(f"{idx}. {label}")
        if row.get("risk"):
            lines.append(f"   max loss: {row.get('risk')}")
        if row.get("the_catch"):
            lines.append(f"   catch: {row.get('the_catch')}")

    social = block.get("social") or {}
    lines.append("")
    lines.append(f"Social/Trump: {social.get('line') or social.get('status') or 'not checked'}")
    for row in (social.get("rows") or [])[:3]:
        label = row.get("ticker") or ", ".join(row.get("tickers") or []) or "SOCIAL"
        lines.append(f"- {label}: {row.get('escalation') or 'watch'} | {row.get('summary') or ''}")
        if row.get("risk"):
            lines.append(f"  risk: {row.get('risk')}")

    push = block.get("push_candidates") or []
    lines.append("")
    lines.append(f"Push candidates: {len(push)} review-only candidate(s).")
    for row in push[:4]:
        lines.append(f"- {row.get('severity') or 'review'}: {row.get('title') or row.get('ticker') or row.get('kind')}")

    dark = block.get("not_checked") or []
    if dark:
        lines.append("")
        lines.append("Not checked/stale:")
        for row in dark[:6]:
            lines.append(f"- {row.get('label') or row.get('key')}: {row.get('status')} - {row.get('why') or row.get('next_step')}")

    if block.get("honesty_rule"):
        lines.append("")
        lines.append(f"Honesty: {block.get('honesty_rule')}")
    return "\n".join(line for line in lines if line is not None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print the chat-first daily recommendation brief.")
    parser.add_argument("--feed", default=str(Path(__file__).resolve().parent / "latest_cockpit_feed.json"))
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    feed = json.loads(Path(args.feed).read_text(encoding="utf-8"))
    block = build_today_recommendation_brief(feed)
    if args.format == "json":
        print(json.dumps(block, indent=2, sort_keys=True))
    else:
        print(format_today_recommendation_text(block))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
