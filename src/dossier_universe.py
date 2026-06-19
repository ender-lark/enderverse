#!/usr/bin/env python3
"""Dossier keeper - the going-forward universe + coverage engine.

Makes the per-ticker thesis-of-record store (docs/research_dossiers/, read by
case_file.py) a LIVING system instead of a one-time backfill. It answers two
questions deterministically, so a scheduled keeper routine (or the agent in
conversation) knows what to draft or refresh - rather than the store quietly
going stale (every verdict self-degrades to UNKNOWN at case_file.VERDICT_MAX_AGE_DAYS):

  1) interest_universe(...) - every ticker "of interest" right now, not just
     current holdings: action/material names + lean-in / open opportunities +
     recent source-call (Fundstrat/analyst) names + top prospects + parabolic
     setups + source-call candidates. Macro/index/crypto proxies and cash sweeps
     are excluded (they get no equity thesis-of-record).

  2) keeper_report(...) - for each interest ticker, is there a thesis-of-record
     that is present AND fresh? Classifies missing / stale / refresh_soon (fresh
     but within a lead window of going stale) / covered, reusing case_file's
     verdict parse + freshness so the staleness rail is the single source of truth.
     Returns to_draft / to_refresh worklists for the keeper.

Source-proof only (blocks=False): this tells the keeper/agent WHAT to draft or
refresh; it never blocks a card, raises an alert, or implies a trade.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import case_file as cf
import decision_dossiers as dd
from decision_dossier_coverage import current_action_material_tickers


SRC = Path(__file__).resolve().parent
OPEN_OPPS_PATH = SRC / "open_opportunities.json"
SOURCE_CALLS_PATH = SRC / "source_calls.json"
TOP_PROSPECTS_PATH = SRC / "top_prospects.json"
PARABOLIC_PATH = SRC / "parabolic_setups.json"
SOURCE_CALL_CANDIDATES_PATH = SRC / "source_call_candidates.json"

# Cash / money-market sweeps: tracked positions, but never an equity thesis.
CASH_TICKERS = {"SPAXX", "FDRXX", "FZFXX", "FCASH", "FNSXX", "FGXX"}

DEFAULT_RECENT_CALL_DAYS = 45
DEFAULT_MAX_VERDICT_AGE_DAYS = cf.VERDICT_MAX_AGE_DAYS
DEFAULT_REFRESH_LEAD_DAYS = 10


def _ticker(value: Any) -> str:
    return str(value or "").strip().upper()


def _load(path: Path | str, default: Any) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def _excluded(tick: str) -> bool:
    """Macro/index/crypto proxies and cash sweeps never get an equity dossier."""
    return (not tick) or (tick in cf.MACRO_TICKERS) or (tick in CASH_TICKERS)


def _add(universe: dict[str, dict[str, Any]], ticker: Any, reason: str) -> None:
    tick = _ticker(ticker)
    if _excluded(tick):
        return
    row = universe.setdefault(tick, {"ticker": tick, "reasons": []})
    if reason and reason not in row["reasons"]:
        row["reasons"].append(reason)


def interest_universe(
    *,
    feed: dict[str, Any] | None = None,
    open_opportunities: dict | None = None,
    source_calls: list | None = None,
    top_prospects: dict | None = None,
    parabolic: Any | None = None,
    source_call_candidates: list | None = None,
    recent_call_days: int = DEFAULT_RECENT_CALL_DAYS,
    today: str | date | None = None,
) -> list[dict[str, Any]]:
    """Union every current 'ticker of interest' with the reasons it qualifies."""
    universe: dict[str, dict[str, Any]] = {}
    today_d = dd._today(today)

    # 1) current holdings + action/material names (BUY/ADD/TRIM/SELL/reallocation/>=1% book)
    if feed is not None:
        for row in current_action_material_tickers(feed):
            _add(universe, row["ticker"], "; ".join(row.get("reasons") or []) or "action/material")

    # 2) lean-in / open opportunities
    oo = open_opportunities if open_opportunities is not None else _load(OPEN_OPPS_PATH, {})
    if isinstance(oo, dict):
        for row in oo.get("opportunities") or []:
            if isinstance(row, dict):
                _add(universe, row.get("ticker"), f"open opportunity ({row.get('kind') or row.get('source') or 'flagged'})")
        for row in oo.get("history") or []:
            if isinstance(row, dict) and (row.get("kind") == "lean_in" or row.get("source") == "lean_in"):
                _add(universe, row.get("ticker"), "lean-in (history)")

    # 3) recent source / analyst calls (within the lookback window)
    sc = source_calls if source_calls is not None else _load(SOURCE_CALLS_PATH, [])
    if isinstance(sc, list):
        cutoff = (today_d - timedelta(days=int(recent_call_days))).isoformat()
        for row in sc:
            if isinstance(row, dict) and str(row.get("date") or "") >= cutoff:
                _add(universe, row.get("ticker"), "recent source call")

    # 4) top prospects (ticker-keyed cache)
    tp = top_prospects if top_prospects is not None else _load(TOP_PROSPECTS_PATH, {})
    if isinstance(tp, dict):
        for key, val in tp.items():
            if isinstance(val, dict):  # a prospect record; skip any metadata scalars
                _add(universe, key, "top prospect")

    # 5) parabolic setups
    pb = parabolic if parabolic is not None else _load(PARABOLIC_PATH, {})
    pb_rows = pb.get("results") if isinstance(pb, dict) else (pb if isinstance(pb, list) else [])
    for row in pb_rows or []:
        if isinstance(row, dict):
            _add(universe, row.get("ticker"), "parabolic setup")

    # 6) source-call candidates (watchlist-ish)
    scc = source_call_candidates if source_call_candidates is not None else _load(SOURCE_CALL_CANDIDATES_PATH, [])
    if isinstance(scc, list):
        for row in scc:
            if isinstance(row, dict):
                _add(universe, row.get("ticker"), "source-call candidate")

    return sorted(universe.values(), key=lambda r: r["ticker"])


def keeper_report(
    universe: list[dict[str, Any]] | None = None,
    *,
    feed: dict[str, Any] | None = None,
    dossier_dir: Path | str | None = None,
    today: str | date | None = None,
    max_verdict_age_days: int = DEFAULT_MAX_VERDICT_AGE_DAYS,
    refresh_lead_days: int = DEFAULT_REFRESH_LEAD_DAYS,
    **universe_kwargs: Any,
) -> dict[str, Any]:
    """Classify every of-interest ticker as missing / stale / refresh_soon / covered."""
    if universe is None:
        universe = interest_universe(feed=feed, today=today, **universe_kwargs)
    refresh_floor = int(max_verdict_age_days) - int(refresh_lead_days)
    rows: list[dict[str, Any]] = []
    for item in universe:
        tick = item["ticker"]
        verdict = cf.load_verdict(tick, today, dossier_dir=dossier_dir)
        status = verdict["status"]  # fresh | stale | missing | unparsed
        age = verdict.get("age_days")
        if status in ("missing", "unparsed"):
            klass = "missing"
        elif status == "stale":
            klass = "stale"
        elif status == "fresh" and isinstance(age, int) and age >= refresh_floor:
            klass = "refresh_soon"
        else:
            klass = "covered"
        rows.append({
            **item,
            "verdict_status": status,
            "age_days": age,
            "klass": klass,
            "verdict_line": (verdict.get("line") or "")[:140],
        })

    counts = {k: sum(1 for r in rows if r["klass"] == k) for k in ("covered", "refresh_soon", "stale", "missing")}
    to_draft = [r["ticker"] for r in rows if r["klass"] == "missing"]
    to_refresh = [r["ticker"] for r in rows if r["klass"] in ("stale", "refresh_soon")]
    total = len(rows)
    status = "missing" if counts["missing"] else "needs_review" if (counts["stale"] or counts["refresh_soon"]) else "covered"
    line = (
        f"Dossier keeper: {counts['covered']}/{total} of-interest ticker(s) have a fresh thesis-of-record; "
        f"missing={counts['missing']}, stale={counts['stale']}, refresh_soon={counts['refresh_soon']}."
    )
    return {
        "status": status,
        "line": line,
        "total": total,
        "counts": counts,
        "to_draft": to_draft,
        "to_refresh": to_refresh,
        "rows": rows,
        "blocks": False,
        "alert_eligible": False,
        "honesty_rule": (
            "Coverage/keeper debt only; identifies dossiers to draft or refresh. "
            "It never blocks a card, raises an alert, or implies a trade/no-trade decision."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dossier_universe",
        description="Compute the of-interest universe and the dossier draft/refresh worklist.",
    )
    parser.add_argument("--feed", help="path to a cockpit feed JSON (e.g. latest_cockpit_feed.json)")
    parser.add_argument("--today")
    parser.add_argument("--dossier-dir")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    args = parser.parse_args(argv)

    feed = json.loads(Path(args.feed).read_text(encoding="utf-8-sig")) if args.feed else None
    report = keeper_report(feed=feed, today=args.today, dossier_dir=args.dossier_dir)
    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(report["line"])
        if report["to_draft"]:
            print("  DRAFT (missing):  " + ", ".join(report["to_draft"]))
        if report["to_refresh"]:
            print("  REFRESH (stale/soon): " + ", ".join(report["to_refresh"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
