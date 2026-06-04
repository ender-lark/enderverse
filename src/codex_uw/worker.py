#!/usr/bin/env python3
"""
uw_bundle_worker.py - one ticker -> one normalized UW entry file.

Designed for isolated subprocess/sub-agent use. Raw UW payloads stay inside this
process; the output file contains only normalized scorer input plus source counts.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from .acquisition import build_opportunity_observation, build_parabolic_entry
from .rest_client import UWRestClient


def atomic_write_json(path: str | Path, payload: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main() -> int:
    p = argparse.ArgumentParser(description="Fetch one UW ticker and write a normalized bundle entry.")
    p.add_argument("--mode", choices=("parabolic", "opportunity"), required=True)
    p.add_argument("--ticker", required=True)
    p.add_argument("--emit-entry", required=True)
    p.add_argument("--include-modifiers", action="store_true",
                   help="For opportunity mode, include gamma/IV modifier pulls.")
    p.add_argument("--price-timeframe", default="5Y")
    p.add_argument("--price-limit", type=int, default=1400)
    p.add_argument("--flow-limit", type=int, default=100)
    p.add_argument("--oi-limit", type=int, default=100)
    p.add_argument("--dark-pool-limit", type=int, default=500)
    p.add_argument("--retries", type=int, default=1)
    p.add_argument("--timeout", type=float, default=30.0)
    args = p.parse_args()

    client = UWRestClient(retries=args.retries, timeout=args.timeout)
    if args.mode == "parabolic":
        pull = build_parabolic_entry(client, args.ticker,
                                     price_timeframe=args.price_timeframe,
                                     price_limit=args.price_limit)
    else:
        pull = build_opportunity_observation(client, args.ticker,
                                             flow_limit=args.flow_limit,
                                             oi_limit=args.oi_limit,
                                             dark_pool_limit=args.dark_pool_limit,
                                             include_modifiers=args.include_modifiers)
    payload = pull.to_jsonable()
    atomic_write_json(args.emit_entry, payload)
    if pull.ok:
        print(f"{pull.ticker} {args.mode} ok counts={payload.get('source_counts', {})}")
        return 0
    print(f"{pull.ticker} {args.mode} failed: {pull.error}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
