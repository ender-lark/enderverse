#!/usr/bin/env python3
"""Routine-side writer hook for action memory.

Call this after a fresh cockpit feed has passed validation/publish-gate. It reads
the prior open-opportunity store, updates it from today's feed actions, records
explicit resolutions, and writes the store back atomically.

This module is side-effecting by design; feed assembly stays pure.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import date

import open_opportunities as oo


DEFAULT_STORE_PATH = "open_opportunities.json"


def _as_of(feed, fallback=None):
    stamp = (feed or {}).get("generated_at") or fallback or date.today().isoformat()
    return str(stamp)[:10]


def _atomic_write_json(path, payload):
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".open_opportunities.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def update_action_memory_from_feed(
    feed: dict,
    *,
    store_path: str = DEFAULT_STORE_PATH,
    prices: dict | None = None,
    monitor_tickers=None,
    invalidations=None,
    resolutions=None,
    max_age_days=None,
    as_of: str | None = None,
) -> dict:
    """Update and persist action memory from one validated cockpit feed.

    Returns a summary dict with the new store and dropped/resolved rows so the
    routine can surface what changed without reparsing the file.
    """
    store = oo.load_open_opportunities(store_path)
    today = _as_of(feed, as_of)
    candidates = oo.candidates_from_feed(feed)
    held = oo.held_tickers_from_feed(feed)
    new_store, dropped = oo.update_open_opportunities(
        store,
        candidates,
        held,
        prices or {},
        today,
        monitor_tickers=monitor_tickers,
        invalidations=invalidations,
        resolutions=resolutions,
        max_age_days=max_age_days,
    )
    _atomic_write_json(store_path, new_store)
    return {
        "store_path": store_path,
        "as_of": today,
        "open_count": len(new_store.get("opportunities") or []),
        "history_count": len(new_store.get("history") or []),
        "dropped": dropped,
        "store": new_store,
    }


def _load_json(path, default):
    if not path:
        return default
    with open(path) as fh:
        return json.load(fh)


def main(argv=None):
    p = argparse.ArgumentParser(description="Update open_opportunities.json from a cockpit feed.")
    p.add_argument("--feed", required=True, help="Cockpit feed JSON path")
    p.add_argument("--store", default=DEFAULT_STORE_PATH, help="Action memory JSON path")
    p.add_argument("--prices", help="Optional {ticker: price} JSON path")
    p.add_argument("--resolutions", help="Optional explicit resolutions JSON path")
    p.add_argument("--invalidations", help="Optional invalidated tickers JSON path")
    p.add_argument("--monitor-tickers", help="Optional monitor tickers JSON path")
    p.add_argument("--max-age-days", type=int)
    args = p.parse_args(argv)

    feed = _load_json(args.feed, {})
    prices = _load_json(args.prices, {}) if args.prices else {}
    resolutions = _load_json(args.resolutions, []) if args.resolutions else []
    invalidations = _load_json(args.invalidations, []) if args.invalidations else []
    monitor_tickers = _load_json(args.monitor_tickers, []) if args.monitor_tickers else []
    summary = update_action_memory_from_feed(
        feed,
        store_path=args.store,
        prices=prices,
        monitor_tickers=monitor_tickers,
        invalidations=invalidations,
        resolutions=resolutions,
        max_age_days=args.max_age_days,
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "store"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
