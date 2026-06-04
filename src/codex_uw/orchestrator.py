#!/usr/bin/env python3
"""
uw_cache_orchestrator.py - bounded UW cache bundle runner.

This is the big coordinator, but it keeps raw data out of the coordinator by
delegating each ticker to uw_bundle_worker.py. The coordinator only sees worker
exit codes, normalized per-ticker files, merged bundles, and scorer summaries.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from parabolic_setup_screener import CANDIDATE_PROFILES
from .merge import load_entries, merge_opportunity, merge_parabolic
from .worker import atomic_write_json


def _src_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_tickers(mode: str) -> list[str]:
    if mode == "parabolic":
        return list(CANDIDATE_PROFILES)
    theses = _src_root() / "theses.json"
    if not theses.exists():
        return []
    from uw_opportunity_scan import universe_from_theses
    return universe_from_theses(str(theses))


def _parse_tickers(raw: str | None, mode: str) -> list[str]:
    if raw:
        return [t.strip().upper() for t in raw.split(",") if t.strip()]
    return [t.upper() for t in _default_tickers(mode)]


def _run_worker(args, ticker: str, entry_path: Path) -> dict:
    cmd = [
        sys.executable,
        "-m",
        "codex_uw.worker",
        "--mode", args.mode,
        "--ticker", ticker,
        "--emit-entry", str(entry_path),
        "--retries", str(args.retries),
        "--timeout", str(args.timeout),
    ]
    if args.mode == "parabolic":
        cmd += ["--price-timeframe", args.price_timeframe, "--price-limit", str(args.price_limit)]
    else:
        cmd += ["--flow-limit", str(args.flow_limit),
                "--oi-limit", str(args.oi_limit),
                "--dark-pool-limit", str(args.dark_pool_limit)]
        if args.include_modifiers:
            cmd.append("--include-modifiers")

    last = None
    for attempt in range(args.retry_failed + 1):
        proc = subprocess.run(cmd, cwd=str(_src_root()), text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        last = proc
        if proc.returncode == 0:
            return {"ticker": ticker, "ok": True, "attempts": attempt + 1,
                    "stdout": proc.stdout.strip()}
    return {"ticker": ticker, "ok": False, "attempts": args.retry_failed + 1,
            "stdout": (last.stdout or "").strip() if last else "",
            "stderr": (last.stderr or "").strip() if last else "",
            "returncode": last.returncode if last else None}


def _score_cache(mode: str, bundle_path: Path, emit_cache: str | None) -> int:
    if not emit_cache:
        return 0
    if mode == "parabolic":
        cmd = [sys.executable, str(_src_root() / "parabolic_setup_screener.py"),
               "--from-bundle", str(bundle_path), "--emit", emit_cache]
    else:
        cmd = [sys.executable, str(_src_root() / "uw_opportunity_scan.py"),
               "--from-bundle", str(bundle_path), "--emit", emit_cache]
    proc = subprocess.run(cmd, cwd=str(_src_root()), text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.stdout:
        print(proc.stdout.strip())
    if proc.stderr:
        print(proc.stderr.strip(), file=sys.stderr)
    return proc.returncode


def _csv_set(raw: str | None) -> set[str]:
    return {x.strip() for x in (raw or "").split(",") if x.strip()}


def _availability(entries: list[dict], required_sources: set[str],
                  required_normalized_keys: set[str], *, min_source_count: int) -> dict:
    dark_sources: dict[str, list[str]] = {s: [] for s in sorted(required_sources)}
    missing_normalized: dict[str, list[str]] = {k: [] for k in sorted(required_normalized_keys)}
    failed_entries = []
    for row in entries:
        tk = str(row.get("ticker") or "").upper()
        if not tk:
            continue
        if not row.get("ok"):
            failed_entries.append(tk)
            continue
        counts = row.get("source_counts") or {}
        for src in required_sources:
            try:
                n = int(counts.get(src) or 0)
            except (TypeError, ValueError):
                n = 0
            if n < min_source_count:
                dark_sources[src].append(tk)
        container = row.get("entry") if isinstance(row.get("entry"), dict) else row.get("observation")
        container = container if isinstance(container, dict) else {}
        for key in required_normalized_keys:
            val = container.get(key)
            if val in (None, "", []) or val == {}:
                missing_normalized[key].append(tk)
    return {
        "dark_sources": {k: v for k, v in dark_sources.items() if v},
        "missing_normalized": {k: v for k, v in missing_normalized.items() if v},
        "failed_entries": failed_entries,
    }


def _print_availability(summary: dict) -> bool:
    any_dark = False
    for src, tickers in summary["dark_sources"].items():
        any_dark = True
        print(f"dark source {src}: {len(tickers)} ticker(s) {','.join(tickers[:12])}")
    for key, tickers in summary["missing_normalized"].items():
        any_dark = True
        print(f"missing normalized {key}: {len(tickers)} ticker(s) {','.join(tickers[:12])}")
    if summary["failed_entries"]:
        any_dark = True
        print(f"failed entries: {len(summary['failed_entries'])} ticker(s) {','.join(summary['failed_entries'][:12])}")
    if not any_dark:
        print("availability: required sources/normalized keys present")
    return any_dark


def main() -> int:
    p = argparse.ArgumentParser(description="Build UW normalized bundles with bounded per-ticker workers.")
    p.add_argument("--mode", choices=("parabolic", "opportunity"), required=True)
    p.add_argument("--tickers", help="Comma-separated ticker override. Defaults to mode universe.")
    p.add_argument("--entries-dir", required=True)
    p.add_argument("--emit-bundle", required=True)
    p.add_argument("--emit-cache", help="Optional final cache path scored from the merged bundle.")
    p.add_argument("--as-of", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    p.add_argument("--max-workers", type=int, default=5)
    p.add_argument("--retries", type=int, default=1, help="HTTP retries inside each worker.")
    p.add_argument("--retry-failed", type=int, default=1, help="Whole-worker retry count.")
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--force", action="store_true", help="Re-fetch even if entry file already exists.")
    p.add_argument("--price-timeframe", default="5Y")
    p.add_argument("--price-limit", type=int, default=1400)
    p.add_argument("--flow-limit", type=int, default=100)
    p.add_argument("--oi-limit", type=int, default=100)
    p.add_argument("--dark-pool-limit", type=int, default=500)
    p.add_argument("--include-modifiers", action="store_true")
    p.add_argument("--require-sources",
                   help="Comma-separated source_count keys that must be present per successful ticker.")
    p.add_argument("--require-normalized-keys",
                   help="Comma-separated normalized entry/observation keys that must be present per successful ticker.")
    p.add_argument("--min-source-count", type=int, default=1)
    p.add_argument("--fail-on-dark", action="store_true",
                   help="Return non-zero when required sources or normalized keys are missing.")
    args = p.parse_args()

    tickers = _parse_tickers(args.tickers, args.mode)
    if not tickers:
        print("No tickers resolved for run", file=sys.stderr)
        return 1

    entries_dir = Path(args.entries_dir)
    entries_dir.mkdir(parents=True, exist_ok=True)
    to_fetch = []
    skipped_existing = []
    for tk in tickers:
        entry_path = entries_dir / f"{tk}.json"
        if entry_path.exists() and not args.force:
            skipped_existing.append(tk)
        else:
            to_fetch.append((tk, entry_path))

    print(f"{args.mode}: tickers={len(tickers)} fetch={len(to_fetch)} existing={len(skipped_existing)} max_workers={args.max_workers}")

    failures = []
    if to_fetch:
        with cf.ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as pool:
            futs = [pool.submit(_run_worker, args, tk, path) for tk, path in to_fetch]
            for fut in cf.as_completed(futs):
                res = fut.result()
                if res["ok"]:
                    print(f"ok {res['ticker']} attempts={res['attempts']}")
                else:
                    print(f"failed {res['ticker']} attempts={res['attempts']}", file=sys.stderr)
                    failures.append(res)

    entries = load_entries(entries_dir)
    bundle = merge_parabolic(entries, args.as_of) if args.mode == "parabolic" else merge_opportunity(entries, args.as_of)
    atomic_write_json(args.emit_bundle, bundle)
    ok_count = len(bundle.get("tickers") or bundle.get("observations") or {})
    skipped = len(bundle.get("skipped") or [])
    print(f"bundle: ok_entries={ok_count} skipped_entries={skipped} worker_failures={len(failures)} -> {args.emit_bundle}")

    availability = _availability(entries, _csv_set(args.require_sources),
                                 _csv_set(args.require_normalized_keys),
                                 min_source_count=args.min_source_count)
    any_dark = _print_availability(availability)
    if any_dark and args.fail_on_dark:
        print("availability gate failed", file=sys.stderr)
        return 3

    score_rc = _score_cache(args.mode, Path(args.emit_bundle), args.emit_cache)
    if score_rc:
        return score_rc
    return 0 if ok_count else 2


if __name__ == "__main__":
    raise SystemExit(main())
