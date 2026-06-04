#!/usr/bin/env python3
"""Publish a validated cockpit feed and update persistent action memory.

This is the side-effecting routine/operator boundary. The engine still builds a
pure feed; this runner takes that finished feed JSON, runs the publish gate, and
only then writes artifacts such as the latest feed copy and open_opportunities.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile

from publish_gate import validate_publish_gate
from runtime_skeleton import update_action_memory_after_publish


DEFAULT_STORE_PATH = "open_opportunities.json"


def _load_json(path, default):
    if not path:
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _atomic_write_json(path, payload):
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".cockpit_feed.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def publish_cockpit_feed(
    feed: dict,
    *,
    feed_out: str | None = None,
    store_path: str = DEFAULT_STORE_PATH,
    prices: dict | None = None,
    monitor_tickers=None,
    invalidations=None,
    resolutions=None,
    max_age_days=None,
    update_memory: bool = True,
) -> dict:
    """Validate, publish optional feed copy, and update action memory.

    Returns a summary. On publish-gate failure no files are written.
    """
    problems = validate_publish_gate(feed)
    if problems:
        return {
            "published": False,
            "reason": "publish_gate_failed",
            "problems": problems,
            "feed_out": feed_out,
            "memory": {"updated": False, "reason": "publish_gate_failed"},
        }

    written_feed = _atomic_write_json(feed_out, feed) if feed_out else None
    memory = {"updated": False, "reason": "disabled", "store_path": store_path}
    if update_memory:
        memory = update_action_memory_after_publish(
            feed,
            store_path=store_path,
            prices=prices,
            monitor_tickers=monitor_tickers,
            invalidations=invalidations,
            resolutions=resolutions,
            max_age_days=max_age_days,
            require_publish_gate=False,
        )

    return {
        "published": True,
        "reason": "published",
        "feed_out": written_feed,
        "memory": {k: v for k, v in memory.items() if k != "store"},
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Validate a cockpit FEED, write the publish artifact, and update action memory."
    )
    p.add_argument("--feed", required=True, help="Finished cockpit FEED JSON path")
    p.add_argument("--feed-out", help="Optional validated feed artifact path to write")
    p.add_argument("--store", default=DEFAULT_STORE_PATH, help="open_opportunities.json path")
    p.add_argument("--prices", help="Optional {ticker: price} JSON path")
    p.add_argument("--resolutions", help="Optional explicit resolutions JSON path")
    p.add_argument("--invalidations", help="Optional invalidated tickers JSON path")
    p.add_argument("--monitor-tickers", help="Optional monitor tickers JSON path")
    p.add_argument("--max-age-days", type=int)
    p.add_argument("--no-memory", action="store_true", help="Only publish the feed; do not update action memory")
    args = p.parse_args(argv)

    feed = _load_json(args.feed, {})
    prices = _load_json(args.prices, {}) if args.prices else {}
    resolutions = _load_json(args.resolutions, []) if args.resolutions else []
    invalidations = _load_json(args.invalidations, []) if args.invalidations else []
    monitor_tickers = _load_json(args.monitor_tickers, []) if args.monitor_tickers else []

    summary = publish_cockpit_feed(
        feed,
        feed_out=args.feed_out,
        store_path=args.store,
        prices=prices,
        monitor_tickers=monitor_tickers,
        invalidations=invalidations,
        resolutions=resolutions,
        max_age_days=args.max_age_days,
        update_memory=not args.no_memory,
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["published"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
