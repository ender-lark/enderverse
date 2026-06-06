#!/usr/bin/env python3
"""Resolve open action-memory items without rebuilding the cockpit feed."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import action_memory_writer as amw
import open_opportunities as oo


DEFAULT_STORE = Path(__file__).resolve().parent / "open_opportunities.json"


def open_action_rows(store: dict) -> list[dict]:
    rows = []
    for row in (store or {}).get("opportunities") or []:
        clean = oo._clean_opp(row)  # tolerant normalizer already used by writer/reader
        if clean and clean.get("status") == "open":
            rows.append(clean)
    rows.sort(key=lambda r: (r.get("first_flagged") or "", r.get("ticker") or ""))
    return rows


def resolve_open_actions(
    *,
    store_path: str | Path = DEFAULT_STORE,
    resolutions: list[dict] | None = None,
    as_of: str | None = None,
    dry_run: bool = False,
) -> dict:
    path = Path(store_path)
    store = oo.load_open_opportunities(path)
    today = str(as_of or date.today().isoformat())[:10]
    new_store, dropped = oo.update_open_opportunities(
        store,
        todays_candidates=[],
        held_tickers=set(),
        prices={},
        as_of=today,
        resolutions=resolutions or [],
    )
    if not dry_run:
        amw._atomic_write_json(str(path), new_store)
    return {
        "store_path": str(path),
        "as_of": today,
        "dry_run": dry_run,
        "open_count": len(new_store.get("opportunities") or []),
        "history_count": len(new_store.get("history") or []),
        "resolved": dropped,
        "open": open_action_rows(new_store),
    }


def review_rows(store: dict, *, as_of: str | None = None) -> list[dict[str, Any]]:
    today = str(as_of or date.today().isoformat())[:10]
    rows: list[dict[str, Any]] = []
    for row in open_action_rows(store):
        ticker = row.get("ticker") or ""
        age = oo.age_business_days(row.get("first_flagged"), today)
        age_days = age if age is not None else 0
        age_state = oo.review_age_state(age_days)
        rows.append({
            "ticker": ticker,
            "kind": row.get("kind") or "",
            "source": row.get("source") or "",
            "first_flagged": row.get("first_flagged") or "",
            "last_seen": row.get("last_seen") or "",
            "age_days": age_days,
            **age_state,
            "review_prompt": (
                f"{age_state['review_label']}: decide whether {ticker} was acted, "
                "invalidated, ignored, deferred, missed, expired, or dropped."
            ),
            "commands": {
                "defer": f"python src/action_memory_resolve.py --ticker {ticker} --status deferred --reason \"keep watching\"",
                "ignore": f"python src/action_memory_resolve.py --ticker {ticker} --status ignored --reason \"no edge\"",
                "acted": f"python src/action_memory_resolve.py --ticker {ticker} --status acted --reason \"operator acted\"",
                "invalidated": f"python src/action_memory_resolve.py --ticker {ticker} --status invalidated --reason \"setup invalidated\"",
                "missed": f"python src/action_memory_resolve.py --ticker {ticker} --status missed --reason \"missed before action\"",
            },
        })
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    rows.sort(key=lambda r: (
        priority_rank.get(str(r.get("cleanup_priority") or "low"), 9),
        -int(r.get("age_days") or 0),
        r.get("ticker") or "",
    ))
    return rows


def review_report(
    *,
    store_path: str | Path = DEFAULT_STORE,
    as_of: str | None = None,
) -> dict[str, Any]:
    path = Path(store_path)
    store = oo.load_open_opportunities(path)
    rows = review_rows(store, as_of=as_of)
    stale_count = sum(1 for row in rows if row.get("review_state") == "stale")
    due_count = sum(1 for row in rows if row.get("due"))
    oldest = max([int(row.get("age_days") or 0) for row in rows], default=0)
    return {
        "store_path": str(path),
        "as_of": str(as_of or date.today().isoformat())[:10],
        "open_count": len(rows),
        "oldest_age_days": oldest,
        "due_count": due_count,
        "stale_count": stale_count,
        "rows": rows,
        "line": (
            f"Open action reviews: {len(rows)} open; {due_count} due; "
            f"{stale_count} stale; oldest {oldest} trading day(s)."
        ),
        "next_step": (
            "Resolve stale rows first; use deferred only when the watch remains intentional."
            if stale_count else
            "Review due rows; use deferred only when the watch remains intentional."
            if due_count else
            "No stale reviews; keep new rows visible until the review window."
            if rows else
            "No open action-memory reviews."
        ),
    }


def _resolution_from_args(args) -> list[dict]:
    if not args.ticker:
        return []
    return [{
        "ticker": args.ticker.upper(),
        "status": args.status,
        "reason": args.reason or args.status,
    }]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="List or resolve open action-memory items")
    parser.add_argument("--store", default=str(DEFAULT_STORE))
    parser.add_argument("--as-of")
    parser.add_argument("--list", action="store_true", help="List open items without writing")
    parser.add_argument("--review-report", action="store_true", help="Show open items with suggested resolution commands")
    parser.add_argument("--ticker", help="Ticker to resolve")
    parser.add_argument(
        "--status",
        default="deferred",
        choices=list(oo.RESOLVED_STATUS),
        help="Resolution status to write when --ticker is supplied",
    )
    parser.add_argument("--reason", default="", help="Short resolution reason")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.review_report:
        print(json.dumps(review_report(store_path=args.store, as_of=args.as_of), indent=2))
        return 0

    if args.list or not args.ticker:
        store = oo.load_open_opportunities(args.store)
        print(json.dumps({
            "store_path": args.store,
            "open_count": len(open_action_rows(store)),
            "open": open_action_rows(store),
        }, indent=2))
        return 0

    summary = resolve_open_actions(
        store_path=args.store,
        resolutions=_resolution_from_args(args),
        as_of=args.as_of,
        dry_run=args.dry_run,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
