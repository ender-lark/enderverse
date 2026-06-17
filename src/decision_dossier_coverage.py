#!/usr/bin/env python3
"""Decision Dossier coverage audit for current action/material names.

This module is source-proof only. Missing dossier rows are coverage debt, not a
card blocker, alert trigger, sizing input, or trade signal.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import decision_dossiers as dd


ACTION_DIRECTIONS = {"BUY", "ADD", "TRIM", "SELL", "REDUCE", "HEDGE"}
DEFAULT_MATERIAL_PCT = 1.0


def _ticker(value: Any) -> str:
    return str(value or "").strip().upper()


def _num(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("$", "").replace(",", "").replace("%", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _card_direction(card: dict[str, Any]) -> str:
    move = (card.get("decision_card") or {}).get("move") or {}
    direction = _ticker(move.get("direction") or card.get("direction"))
    return "TRIM" if direction == "REDUCE" else direction


def _add_target(
    targets: dict[str, dict[str, Any]],
    ticker: str,
    *,
    reason: str,
    source: str,
    detail: str = "",
    market_value: float | None = None,
    pct: float | None = None,
) -> None:
    tick = _ticker(ticker)
    if not tick:
        return
    row = targets.setdefault(tick, {
        "ticker": tick,
        "reasons": [],
        "sources": [],
        "details": [],
        "market_value": None,
        "pct": None,
    })
    if reason and reason not in row["reasons"]:
        row["reasons"].append(reason)
    if source and source not in row["sources"]:
        row["sources"].append(source)
    if detail and detail not in row["details"]:
        row["details"].append(detail)
    if market_value is not None:
        row["market_value"] = max(float(market_value), float(row["market_value"] or 0.0))
    if pct is not None:
        row["pct"] = max(float(pct), float(row["pct"] or 0.0))


def current_action_material_tickers(
    feed: dict[str, Any],
    *,
    min_material_pct: float = DEFAULT_MATERIAL_PCT,
) -> list[dict[str, Any]]:
    """Return tickers that should have a dossier because they are current."""
    targets: dict[str, dict[str, Any]] = {}
    today = feed.get("today_decide") or {}
    for section, source in (("cards", "today_decide.cards"), ("backlog", "today_decide.backlog")):
        for card in today.get(section) or []:
            if not isinstance(card, dict):
                continue
            direction = _card_direction(card)
            if direction not in ACTION_DIRECTIONS:
                continue
            ticker = _ticker(card.get("ticker"))
            if not ticker:
                continue
            _add_target(
                targets,
                ticker,
                reason=f"{direction.lower()} card",
                source=source,
                detail=str(card.get("card_id") or "").strip(),
            )

    rb = feed.get("reallocation_brief") or {}
    for row in rb.get("rows") or []:
        if not isinstance(row, dict):
            continue
        _add_target(
            targets,
            _ticker(row.get("ticker")),
            reason="reallocation add candidate",
            source="reallocation_brief.rows",
            market_value=_num(row.get("notional_usd")),
            pct=_num(row.get("target_pct")),
        )
    for row in rb.get("trims") or []:
        if not isinstance(row, dict):
            continue
        _add_target(
            targets,
            _ticker(row.get("ticker")),
            reason="funding trim candidate",
            source="reallocation_brief.trims",
            market_value=_num(row.get("notional_usd")),
            pct=_num(row.get("current_pct")),
        )

    combined = (
        ((feed.get("portfolio_views") or {}).get("views") or {}).get("combined") or {}
    )
    for row in combined.get("rows") or []:
        if not isinstance(row, dict):
            continue
        pct = _num(row.get("pct"))
        if pct is None or pct < float(min_material_pct):
            continue
        _add_target(
            targets,
            _ticker(row.get("ticker")),
            reason=f"material holding >= {float(min_material_pct):g}% book",
            source="portfolio_views.combined.rows",
            market_value=_num(row.get("market_value")),
            pct=pct,
        )

    return sorted(targets.values(), key=lambda row: row["ticker"])


def _dossier_status(ticker: str, dossiers: dict[str, dict[str, Any]], today: str | None) -> dict[str, Any]:
    dossier = dd.card_dossier(ticker, dossiers=dossiers, today=today)
    if not dossier:
        return {
            "status": "missing_dossier",
            "summary": "no repo Decision Dossier row",
            "read_statuses": {},
            "notion_url": "",
        }
    read_statuses = {
        key: ((read.get("freshness") or {}).get("status") or "not_checked")
        for key, read in (dossier.get("reads") or {}).items()
        if isinstance(read, dict)
    }
    stale_reads = {
        key: value for key, value in read_statuses.items()
        if value != "fresh"
    }
    if str(dossier.get("status") or "").strip() != "fresh" or stale_reads:
        detail_bits = [f"{key} {value}" for key, value in sorted(stale_reads.items())]
        return {
            "status": "stale_dossier",
            "summary": "; ".join(detail_bits) or f"status {dossier.get('status')}",
            "read_statuses": read_statuses,
            "notion_url": dossier.get("notion_url") or "",
        }
    return {
        "status": "covered",
        "summary": "fresh repo Decision Dossier row",
        "read_statuses": read_statuses,
        "notion_url": dossier.get("notion_url") or "",
    }


def _load_dossiers(dossiers: dict[str, dict[str, Any]] | None, dossier_path: Path | str | None) -> dict[str, dict[str, Any]]:
    if dossiers is not None:
        return {_ticker(ticker): row for ticker, row in dossiers.items() if isinstance(row, dict)}
    if dossier_path is not None:
        return dd.load_dossiers(dossier_path)
    return dd.load_dossiers()


def build_decision_dossier_coverage(
    feed: dict[str, Any],
    *,
    dossiers: dict[str, dict[str, Any]] | None = None,
    dossier_path: Path | str | None = None,
    today: str | None = None,
    min_material_pct: float = DEFAULT_MATERIAL_PCT,
) -> dict[str, Any]:
    """Build a Source Proof audit block for dossier coverage."""
    dossier_rows = _load_dossiers(dossiers, dossier_path)
    targets = current_action_material_tickers(feed, min_material_pct=min_material_pct)
    rows: list[dict[str, Any]] = []
    for target in targets:
        tick = target["ticker"]
        status = _dossier_status(tick, dossier_rows, today)
        rows.append({
            **target,
            **status,
            "next_step": (
                "Create/sync a compact repo Decision Dossier row before relying on dossier context."
                if status["status"] == "missing_dossier"
                else "Refresh stale/not-checked dossier reads through the existing staleness guard."
                if status["status"] == "stale_dossier"
                else "No coverage action."
            ),
        })

    missing = [row for row in rows if row["status"] == "missing_dossier"]
    stale = [row for row in rows if row["status"] == "stale_dossier"]
    covered = [row for row in rows if row["status"] == "covered"]
    if not rows:
        status = "covered"
        line = "Decision dossier coverage: no current action/material ticker(s) to audit."
    else:
        status = "missing" if missing else "needs_review" if stale else "covered"
        bits = [
            f"{len(covered)}/{len(rows)} current action/material ticker(s) covered",
            f"missing={len(missing)}",
            f"stale={len(stale)}",
        ]
        if missing:
            bits.append("missing tickers " + ", ".join(row["ticker"] for row in missing[:8]))
        line = "Decision dossier coverage: " + "; ".join(bits) + "."
    return {
        "status": status,
        "line": line,
        "total_count": len(rows),
        "covered_count": len(covered),
        "missing_count": len(missing),
        "stale_count": len(stale),
        "rows": rows,
        "blocks": False,
        "alert_eligible": False,
        "honesty_rule": (
            "Coverage debt only; missing dossiers do not block cards, generate alerts, "
            "or imply a trade/no-trade decision."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Decision Dossier coverage for a cockpit feed.")
    parser.add_argument("--feed", required=True)
    parser.add_argument("--dossiers", default=str(dd.DEFAULT_DOSSIERS_PATH))
    parser.add_argument("--today")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    args = parser.parse_args(argv)

    feed = json.loads(Path(args.feed).read_text(encoding="utf-8-sig"))
    audit = build_decision_dossier_coverage(feed, dossier_path=args.dossiers, today=args.today)
    if args.format == "json":
        print(json.dumps(audit, indent=2))
    else:
        print(audit["line"])
        for row in audit.get("rows") or []:
            print(f"- {row['ticker']}: {row['status']} ({', '.join(row.get('reasons') or [])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
