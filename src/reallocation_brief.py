#!/usr/bin/env python3
"""Dashboard-facing candidate reallocation brief.

This wraps the existing funded-rotation planner into a feed block that is easy
to read in the cockpit. It never executes trades and labels stale/cache-only
position data as test-data only.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reallocate import ADD, TRIM, reallocate


def _parse_date(value: Any):
    if not value:
        return None
    text = str(value)
    try:
        if "T" in text:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _asof_date(feed: dict[str, Any], as_of: str | None = None):
    return _parse_date(as_of) or _parse_date(feed.get("generated_at")) or datetime.now(timezone.utc).date()


def _positions_payload(positions_cache: dict[str, Any]) -> tuple[list[dict[str, Any]], float]:
    rows = positions_cache.get("positions") or []
    total = positions_cache.get("sleeve_value")
    if not total:
        total = sum(float(row.get("market_value") or 0.0) for row in rows if isinstance(row, dict))
    return rows, float(total or 0.0)


def _uw_reallocation_checks(feed: dict[str, Any]) -> dict[str, Any]:
    for row in (feed.get("uw_action_runbook") or {}).get("rows") or []:
        if row.get("mode") == "portfolio_reallocation":
            return row
    return {}


def _funded_by(rows: list[tuple[str, float]]) -> list[dict[str, Any]]:
    return [{"ticker": ticker, "notional_usd": round(float(notional), 2)} for ticker, notional in rows]


def _funds(rows: list[tuple[str, float]]) -> list[dict[str, Any]]:
    return [{"ticker": ticker, "notional_usd": round(float(notional), 2)} for ticker, notional in rows]


def _past_sequence_date(sequence: str, operating_day) -> bool:
    if not sequence.startswith("after "):
        return False
    date_part = sequence.replace("after ", "", 1).strip().split()[0]
    seq_date = _parse_date(date_part)
    return bool(seq_date and seq_date < operating_day)


def _add_row(leg, *, stale_positions: bool, uw_checks: dict[str, Any], operating_day) -> dict[str, Any]:
    blockers = [
        "latest current positions" if stale_positions else "",
        "same-session UW price/flow",
        "funding source confirmation",
        "pre-trade gate",
    ]
    blockers = [item for item in blockers if item]
    sequence_state = "past_gate" if _past_sequence_date(str(leg.sequence or ""), operating_day) else "current_or_unspecified"
    if sequence_state == "past_gate":
        blockers.append("legacy catalyst sequencing date has passed; verify current post-catalyst setup")

    return {
        "ticker": leg.ticker,
        "rank": leg.rank,
        "action": "ADD_CANDIDATE",
        "notional_usd": round(float(leg.notional_usd), 2),
        "current_pct": leg.current_pct,
        "target_pct": leg.target_pct,
        "effective_current_pct": leg.effective_current_pct,
        "delta_pct": leg.delta_pct,
        "sequence": leg.sequence,
        "sequence_state": sequence_state,
        "entry_note": leg.entry_note,
        "gate": leg.gate,
        "gate_reason": leg.gate_reason,
        "funded_by": _funded_by(leg.funded_by),
        "rationale": leg.rationale,
        "caveats": list(leg.caveats),
        "blockers": blockers,
        "disconfirmation": (
            uw_checks.get("downgrade_when")
            or "live price, flow, funding, or thesis evidence argues for waiting"
        ),
        "uw_ticker_checks": (uw_checks.get("ticker_checks") or [])[:8],
    }


def _trim_row(leg) -> dict[str, Any]:
    return {
        "ticker": leg.ticker,
        "action": "TRIM_FUNDING_CANDIDATE",
        "notional_usd": round(float(leg.notional_usd), 2),
        "current_pct": leg.current_pct,
        "target_pct": leg.target_pct,
        "delta_pct": leg.delta_pct,
        "gate": leg.gate,
        "gate_reason": leg.gate_reason,
        "funds": _funds(leg.funds),
        "rationale": leg.rationale,
        "caveats": list(leg.caveats),
    }


def build_reallocation_brief(
    feed: dict[str, Any],
    positions_cache: dict[str, Any] | None,
    *,
    as_of: str | None = None,
) -> dict[str, Any]:
    if not positions_cache:
        return {
            "status": "not_checked",
            "line": "Reallocation brief not checked: positions cache missing.",
            "rows": [],
            "trims": [],
            "blockers": ["latest positions required"],
        }

    positions, total = _positions_payload(positions_cache)
    if not positions or total <= 0:
        return {
            "status": "not_checked",
            "line": "Reallocation brief not checked: positions cache has no usable market values.",
            "rows": [],
            "trims": [],
            "blockers": ["usable positions and total book value required"],
        }

    operating_day = _asof_date(feed, as_of)
    snapshot_date = _parse_date(positions_cache.get("snapshot_date"))
    age_days = (operating_day - snapshot_date).days if snapshot_date else None
    stale_positions = snapshot_date is None or age_days is None or age_days > 0
    status = "test_data_only" if stale_positions else "candidate_only"

    result, _markdown = reallocate(
        positions=positions,
        total_book_value=total,
        as_of=str(operating_day),
    )
    uw_checks = _uw_reallocation_checks(feed)
    adds = [
        _add_row(leg, stale_positions=stale_positions, uw_checks=uw_checks, operating_day=operating_day)
        for leg in result.legs
        if leg.action == ADD
    ]
    trims = [_trim_row(leg) for leg in result.legs if leg.action == TRIM]

    blockers = []
    if stale_positions:
        date_text = str(positions_cache.get("snapshot_date") or "unknown")
        age_text = f"{age_days} day(s) old" if age_days is not None else "unknown age"
        blockers.append(f"positions snapshot {date_text} is {age_text}; use as test-data only until current positions are supplied")
    blockers.append("same-session UW price/flow confirmation required before any capital action")
    blockers.append("tax/account constraints and user max-action capacity not supplied")

    funding = result.funding
    line = (
        f"Reallocation brief: {status.replace('_', ' ')} from "
        f"{positions_cache.get('snapshot_date') or 'unknown-date'} positions; "
        f"{len(adds)} add candidate(s), {len(trims)} funding trim(s)"
    )
    if funding:
        line += (
            f"; allocated ${funding.allocated_usd:,.0f}; "
            f"shortfall ${funding.shortfall_usd:,.0f}."
        )
    else:
        line += "."

    honesty_rule = "Candidate reallocation brief only; no trades are executed."
    if stale_positions:
        honesty_rule += " Stale positions remain test-data only."
    else:
        honesty_rule += " Same-day positions still require gates before action."

    return {
        "status": status,
        "line": line,
        "positions_snapshot_date": positions_cache.get("snapshot_date") or "",
        "positions_age_days": age_days,
        "total_book_value": total,
        "candidate_only": True,
        "counts": {
            "adds": len(adds),
            "trims": len(trims),
            "sequence_now": len(result.sequence_now),
            "sequence_later": len(result.sequence_later),
        },
        "funding": {
            "pool_total_usd": funding.pool_total_usd if funding else 0,
            "allocated_usd": funding.allocated_usd if funding else 0,
            "remaining_usd": funding.remaining_usd if funding else 0,
            "shortfall_usd": funding.shortfall_usd if funding else 0,
        },
        "rows": adds[:10],
        "trims": trims[:8],
        "blockers": blockers,
        "warnings": list(result.warnings),
        "notes": list(result.notes),
        "uw_market_checks": (uw_checks.get("market_checks") or [])[:8],
        "uw_ticker_checks": (uw_checks.get("ticker_checks") or [])[:10],
        "command": "python src/reallocation_brief.py --feed src/latest_cockpit_feed.json --positions src/positions.json --format text",
        "honesty_rule": honesty_rule,
    }


def _fmt_usd(value: Any) -> str:
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "$0"


def _format_text(block: dict[str, Any]) -> str:
    lines = [block.get("line") or "Reallocation brief"]
    if block.get("honesty_rule"):
        lines.append(f"honesty: {block['honesty_rule']}")
    if block.get("blockers"):
        lines.append("blockers:")
        for blocker in block["blockers"]:
            lines.append(f"- {blocker}")
    if block.get("rows"):
        lines.append("")
        lines.append("candidate adds:")
        for row in block["rows"]:
            funded = ", ".join(f"{f['ticker']} {_fmt_usd(f['notional_usd'])}" for f in row.get("funded_by") or [])
            lines.append(
                f"{row.get('rank')}. {row.get('ticker')} add {_fmt_usd(row.get('notional_usd'))} "
                f"| {row.get('sequence')} | gate {row.get('gate') or 'n/a'}"
            )
            if funded:
                lines.append(f"   funded by: {funded}")
            lines.append(f"   blocks: {', '.join(row.get('blockers') or [])}")
    if block.get("trims"):
        lines.append("")
        lines.append("funding trims:")
        for row in block["trims"]:
            funds = ", ".join(f"{f['ticker']} {_fmt_usd(f['notional_usd'])}" for f in row.get("funds") or [])
            lines.append(f"- {row.get('ticker')} trim {_fmt_usd(row.get('notional_usd'))} -> {funds}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Print candidate reallocation brief.")
    parser.add_argument("--feed", default=str(Path(__file__).resolve().parent / "latest_cockpit_feed.json"))
    parser.add_argument("--positions", default=str(Path(__file__).resolve().parent / "positions.json"))
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    feed = json.loads(Path(args.feed).read_text(encoding="utf-8"))
    positions = json.loads(Path(args.positions).read_text(encoding="utf-8"))
    block = build_reallocation_brief(feed, positions)
    if args.format == "json":
        print(json.dumps(block, indent=2, sort_keys=True))
    else:
        print(_format_text(block))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
