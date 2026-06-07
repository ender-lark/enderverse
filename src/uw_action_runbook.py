#!/usr/bin/env python3
"""Build a no-fetch UW action runbook from the current cockpit feed.

The runbook turns active dashboard scenarios into specific UW endpoint groups
and ticker scopes. It does not fetch data and must not be treated as proof that
any endpoint result exists.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from uw_endpoint_router import profile_for_mode
from uw_routing_recommendations import build_uw_routing_recommendations


def _ticker(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    if "," in text:
        return ""
    if len(text) > 12:
        return ""
    if not all(ch.isalnum() or ch in {".", "-"} for ch in text):
        return ""
    return text


def _extend_unique(out: list[str], values: list[Any], *, limit: int) -> None:
    seen = set(out)
    for value in values:
        ticker = _ticker(value)
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        out.append(ticker)
        if len(out) >= limit:
            return


def _extend_label_unique(out: list[str], values: list[Any], *, limit: int) -> None:
    seen = set(out)
    for value in values:
        label = str(value or "").strip()
        if not label or label in seen:
            continue
        seen.add(label)
        out.append(label)
        if len(out) >= limit:
            return


def _split_ticker_text(value: Any) -> list[str]:
    text = str(value or "")
    return [_ticker(part) for part in text.replace(";", ",").split(",") if _ticker(part)]


def _action_tickers(feed: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for row in feed.get("actions") or []:
        if isinstance(row, dict):
            _extend_unique(out, [row.get("ticker")], limit=12)
    return out


def _event_tickers(feed: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for row in feed.get("event_risk") or []:
        if not isinstance(row, dict):
            continue
        _extend_unique(out, row.get("tickers") or [], limit=12)
    return out


def _target_drift_tickers(feed: dict[str, Any]) -> list[str]:
    rows = [row for row in (feed.get("target_drift") or {}).get("rows") or [] if isinstance(row, dict)]

    def sort_key(row: dict[str, Any]) -> tuple[int, float]:
        flags = set(row.get("flags") or [])
        alarm = 1 if "ALARM_DRIFT" in flags else 0
        try:
            drift = abs(float(row.get("drift_absolute_pct") or 0.0))
        except (TypeError, ValueError):
            drift = 0.0
        return (-alarm, -drift)

    out: list[str] = []
    for row in sorted(rows, key=sort_key):
        _extend_unique(out, [row.get("ticker")], limit=12)
    return out


def _asymmetric_tickers(feed: dict[str, Any]) -> list[str]:
    rows = [row for row in (feed.get("asymmetric_opportunities") or {}).get("rows") or [] if isinstance(row, dict)]
    rows = sorted(rows, key=lambda row: -(float(row.get("score") or 0.0)))
    out: list[str] = []
    for row in rows:
        _extend_unique(out, [row.get("ticker")], limit=12)
    return out


def _portfolio_tickers(feed: dict[str, Any]) -> list[str]:
    rows = (((feed.get("portfolio_views") or {}).get("views") or {}).get("combined") or {}).get("rows") or []
    rows = [row for row in rows if isinstance(row, dict)]
    rows = sorted(rows, key=lambda row: -(float(row.get("pct") or 0.0)))
    out: list[str] = []
    for row in rows:
        _extend_unique(out, [row.get("ticker")], limit=12)
    return out


def _fundstrat_tickers(feed: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for row in feed.get("fresh_signals") or []:
        if isinstance(row, dict):
            _extend_unique(out, [row.get("ticker")], limit=12)
    for row in ((feed.get("operator_hardening") or {}).get("condition_checklist") or {}).get("rows") or []:
        if isinstance(row, dict) and str(row.get("source") or "").startswith("fundstrat"):
            _extend_unique(out, _split_ticker_text(row.get("ticker")), limit=12)
    return out


def _reddit_tickers(feed: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for row in feed.get("actions") or []:
        if isinstance(row, dict) and row.get("source") == "reddit":
            _extend_unique(out, [row.get("ticker")], limit=12)
    watch = feed.get("reddit_watch") or {}
    for row in watch.get("rows") or []:
        if isinstance(row, dict):
            _extend_unique(out, row.get("tickers") or [row.get("ticker")], limit=12)
    return out


def _endpoints_by_scope(mode: str) -> tuple[list[str], list[str]]:
    profile = profile_for_mode(mode)
    market: list[str] = []
    ticker: list[str] = []
    for group in sorted(profile.get("groups") or [], key=lambda row: row.get("priority") or 99):
        names = [endpoint.get("name") for endpoint in group.get("endpoints") or [] if endpoint.get("name")]
        scope = str(group.get("scope") or "")
        if "ticker" in scope or "company" in scope:
            _extend_label_unique(ticker, names, limit=16)
        else:
            _extend_label_unique(market, names, limit=16)
    return market[:10], ticker[:14]


def _rules_for_mode(mode: str) -> dict[str, str]:
    rules = {
        "event_risk_political_macro": {
            "blocks_action_if": "same-session headlines, rates/oil levels, or sector tape are missing or contradictory",
            "promote_when": "macro tape and affected factor checks confirm the risk is changing sizing or new-buy timing",
            "downgrade_when": "the shock is stale, headlines reverse, or affected sectors stabilize against the warning",
        },
        "portfolio_reallocation": {
            "blocks_action_if": "latest positions, same-session price/flow, or funding source are missing",
            "promote_when": "current positions, factor wrapper context, and ticker flow support the trim/add leg",
            "downgrade_when": "the target gap is stale, already funded, or live flow/price argues for waiting",
        },
        "fundstrat_signal_confirmation": {
            "blocks_action_if": "Fundstrat evidence is dated and same-day UW/price confirmation is missing",
            "promote_when": "Fundstrat call and live market structure point in the same direction",
            "downgrade_when": "price/flow contradicts the call or the call was already absorbed by the tape",
        },
        "asymmetric_discovery": {
            "blocks_action_if": "the setup is only flow/social/context without independent confirmation",
            "promote_when": "fresh flow plus thesis, sponsor, price, or news evidence creates review-worthy skew",
            "downgrade_when": "the anomaly is late, promotional, or unsupported by follow-up endpoints",
        },
        "reddit_escalation_vetting": {
            "blocks_action_if": "Reddit is the primary evidence or the source appears promotional/late",
            "promote_when": "same-day UW/news/price evidence independently confirms the anomaly",
            "downgrade_when": "the spike is a lagging echo, ticker match is ambiguous, or IV/price shows chase risk",
        },
    }
    return rules.get(mode, {
        "blocks_action_if": "fresh confirming evidence is missing",
        "promote_when": "the routed checks confirm the dashboard action thesis",
        "downgrade_when": "fresh evidence contradicts or fails to support the action",
    })


def _scope_for_mode(mode: str, feed: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if mode == "event_risk_political_macro":
        _extend_unique(out, _event_tickers(feed), limit=12)
        _extend_unique(out, _portfolio_tickers(feed)[:5], limit=12)
    elif mode == "portfolio_reallocation":
        _extend_unique(out, _target_drift_tickers(feed), limit=12)
        _extend_unique(out, _action_tickers(feed), limit=12)
    elif mode == "fundstrat_signal_confirmation":
        _extend_unique(out, _fundstrat_tickers(feed), limit=12)
        _extend_unique(out, _action_tickers(feed), limit=12)
    elif mode == "asymmetric_discovery":
        _extend_unique(out, _asymmetric_tickers(feed), limit=12)
    elif mode == "reddit_escalation_vetting":
        _extend_unique(out, _reddit_tickers(feed), limit=12)
    else:
        _extend_unique(out, _action_tickers(feed), limit=12)
    return out


def build_uw_action_runbook(feed: dict[str, Any]) -> dict[str, Any]:
    routing = build_uw_routing_recommendations(feed)
    rows: list[dict[str, Any]] = []
    for routing_row in routing.get("rows") or []:
        mode = routing_row.get("mode") or ""
        if not mode:
            continue
        profile = profile_for_mode(mode)
        market_checks, ticker_checks = _endpoints_by_scope(mode)
        scope = _scope_for_mode(mode, feed)
        rules = _rules_for_mode(mode)
        rows.append({
            "mode": mode,
            "label": profile.get("label") or mode,
            "priority": routing_row.get("priority") or len(rows) + 1,
            "why": routing_row.get("reason") or profile.get("purpose") or "",
            "operator_question": profile.get("operator_question") or "",
            "freshness_requirement": profile.get("freshness_requirement") or "",
            "ticker_scope": scope,
            "market_checks": market_checks,
            "ticker_checks": ticker_checks,
            **rules,
        })
    rows = sorted(rows, key=lambda row: row["priority"])
    scoped = sorted({ticker for row in rows for ticker in row.get("ticker_scope") or []})
    status = "has_data" if rows else "checked_clear"
    return {
        "status": status,
        "line": (
            f"UW action runbook: {len(rows)} check set(s), {len(scoped)} scoped ticker(s); endpoint results not claimed."
            if rows else
            "UW action runbook: no active UW check set from current feed."
        ),
        "rows": rows,
        "scoped_tickers": scoped,
        "command": "python src/uw_action_runbook.py --feed src/latest_cockpit_feed.json --format text",
        "honesty_rule": "Runbook recommends UW checks from dashboard state only; it is not proof any endpoint was fetched.",
    }


def _format_text(block: dict[str, Any]) -> str:
    lines = [block.get("line") or "UW action runbook"]
    if block.get("honesty_rule"):
        lines.append(f"honesty: {block['honesty_rule']}")
    for row in block.get("rows") or []:
        lines.append("")
        lines.append(f"{row.get('priority')}. {row.get('label')} ({row.get('mode')})")
        lines.append(f"   why: {row.get('why')}")
        lines.append(f"   question: {row.get('operator_question')}")
        lines.append(f"   freshness: {row.get('freshness_requirement')}")
        if row.get("ticker_scope"):
            lines.append(f"   tickers: {', '.join(row['ticker_scope'])}")
        if row.get("market_checks"):
            lines.append(f"   market checks: {', '.join(row['market_checks'])}")
        if row.get("ticker_checks"):
            lines.append(f"   ticker checks: {', '.join(row['ticker_checks'])}")
        lines.append(f"   blocks action if: {row.get('blocks_action_if')}")
        lines.append(f"   promote when: {row.get('promote_when')}")
        lines.append(f"   downgrade when: {row.get('downgrade_when')}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Print UW action runbook from a cockpit feed.")
    parser.add_argument("--feed", default=str(Path(__file__).resolve().parent / "latest_cockpit_feed.json"))
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    feed = json.loads(Path(args.feed).read_text(encoding="utf-8"))
    block = build_uw_action_runbook(feed)
    if args.format == "json":
        print(json.dumps(block, indent=2, sort_keys=True))
    else:
        print(_format_text(block))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
