#!/usr/bin/env python3
"""Resolve open action-memory items without rebuilding the cockpit feed."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

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
