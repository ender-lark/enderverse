#!/usr/bin/env python3
"""
uw_bundle_merge.py - normalized per-ticker files -> scorer bundle.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .worker import atomic_write_json


def load_entries(entries_dir: str | Path) -> list[dict]:
    entries = []
    for path in sorted(Path(entries_dir).glob("*.json")):
        with open(path) as fh:
            row = json.load(fh)
        if isinstance(row, dict):
            entries.append(row)
    return entries


def merge_parabolic(entries: list[dict], as_of: str) -> dict:
    tickers = {}
    skipped = []
    for row in entries:
        tk = str(row.get("ticker") or "").upper()
        if row.get("ok") and isinstance(row.get("entry"), dict):
            tickers[tk] = row["entry"]
        elif tk:
            skipped.append({"ticker": tk, "error": row.get("error") or "missing entry"})
    return {"as_of": as_of, "tickers": tickers, "skipped": skipped}


def merge_opportunity(entries: list[dict], as_of: str) -> dict:
    observations = {}
    skipped = []
    for row in entries:
        tk = str(row.get("ticker") or "").upper()
        if row.get("ok") and isinstance(row.get("observation"), dict) and row["observation"]:
            observations[tk] = row["observation"]
        elif tk:
            skipped.append({"ticker": tk, "error": row.get("error") or "empty normalized observation"})
    return {"as_of": as_of, "universe": sorted(observations), "observations": observations,
            "skipped": skipped}


def main() -> int:
    p = argparse.ArgumentParser(description="Merge UW normalized per-ticker entries into a scorer bundle.")
    p.add_argument("--mode", choices=("parabolic", "opportunity"), required=True)
    p.add_argument("--entries-dir", required=True)
    p.add_argument("--emit-bundle", required=True)
    p.add_argument("--as-of", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    args = p.parse_args()

    entries = load_entries(args.entries_dir)
    bundle = merge_parabolic(entries, args.as_of) if args.mode == "parabolic" else merge_opportunity(entries, args.as_of)
    atomic_write_json(args.emit_bundle, bundle)
    ok_count = len(bundle.get("tickers") or bundle.get("observations") or {})
    skipped = len(bundle.get("skipped") or [])
    print(f"merged {ok_count} {args.mode} entr{'y' if ok_count == 1 else 'ies'}; skipped {skipped} -> {args.emit_bundle}")
    return 0 if ok_count else 2


if __name__ == "__main__":
    raise SystemExit(main())
