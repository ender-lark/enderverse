#!/usr/bin/env python3
"""Draft source-call candidates from existing feed observations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import source_call_cache_merge
import source_call_tracker as tracker


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = ROOT / "src"


def _read_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.is_file():
        return default
    with p.open(encoding="utf-8-sig") as fh:
        return json.load(fh)


def observations_from_feed(feed: dict[str, Any]) -> list[dict[str, Any]]:
    """Return source-call observations already present in the cockpit feed."""
    feedback = feed.get("feedback") if isinstance(feed, dict) else {}
    source_calls = (feedback or {}).get("source_calls") if isinstance(feedback, dict) else {}
    observations = source_calls.get("observations") if isinstance(source_calls, dict) else []
    rows: list[dict[str, Any]] = []
    for row in observations or []:
        if not isinstance(row, dict):
            continue
        quote = str(row.get("quote") or row.get("call_summary") or row.get("verbatim_quote") or "").strip()
        source = str(row.get("author") or row.get("source") or "").strip()
        ticker = str(row.get("ticker") or "").strip().upper()
        if not quote or not source:
            continue
        rows.append({
            "source": source,
            "ticker": ticker or None,
            "text": quote,
            "date": str(row.get("date") or "")[:10],
        })
    return rows


def merge_candidates(existing: list[dict] | None, incoming: list[dict]) -> list[dict]:
    rows: list[dict] = []
    seen: set[tuple] = set()
    for row in [*(existing or []), *incoming]:
        if not isinstance(row, dict):
            continue
        key = (
            str(row.get("source") or "").strip().lower(),
            str(row.get("ticker") or "").strip().upper(),
            str(row.get("date") or "")[:10],
            str(row.get("verbatim_quote") or row.get("text") or "").strip(),
        )
        if not key[0] or not key[3] or key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return rows


def draft_candidates_from_feed(
    feed: dict[str, Any],
    *,
    existing_candidates: list[dict] | None = None,
    classified_at: str | None = None,
) -> tuple[list[dict], dict[str, Any]]:
    observations = observations_from_feed(feed)
    drafted = tracker.batch_classify(observations, now=classified_at)
    rows = merge_candidates(existing_candidates, drafted)
    summary = {
        "observations": len(observations),
        "drafted": len(drafted),
        "existing": len([r for r in (existing_candidates or []) if isinstance(r, dict)]),
        "stored": len(rows),
        "tickers": sorted({str(r.get("ticker")) for r in drafted if r.get("ticker")}),
    }
    return rows, summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Draft source-call candidates from latest feed observations")
    parser.add_argument("--feed", default=str(DEFAULT_SRC / "latest_cockpit_feed.json"))
    parser.add_argument("--out", default=str(DEFAULT_SRC / "source_call_candidates.json"))
    parser.add_argument("--merge-existing", action="store_true")
    parser.add_argument("--classified-at")
    parser.add_argument("--merge-cache", action="store_true", help="Also merge candidates into source_calls/log dates")
    parser.add_argument("--source-calls", default=str(DEFAULT_SRC / "source_calls.json"))
    parser.add_argument("--log-dates", default=str(DEFAULT_SRC / "log_call_dates.json"))
    parser.add_argument("--summary", default=str(DEFAULT_SRC / "source_call_cache_summary.json"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    feed = _read_json(args.feed, default={})
    existing = _read_json(args.out, default=[]) if args.merge_existing else []
    candidates, summary = draft_candidates_from_feed(
        feed if isinstance(feed, dict) else {},
        existing_candidates=existing if isinstance(existing, list) else [],
        classified_at=args.classified_at,
    )
    result = {
        "valid": bool(candidates) or summary["observations"] == 0,
        "out": args.out,
        "written": False,
        "cache_merged": False,
        **summary,
    }
    if not args.dry_run:
        source_call_cache_merge._atomic_write_json(args.out, candidates)
        result["written"] = True
    if args.merge_cache:
        if not args.dry_run:
            merged, cache_summary = source_call_cache_merge.merge_source_calls(
                _read_json(args.source_calls, default=[]),
                candidates,
                generated_at=args.classified_at,
            )
            source_call_cache_merge._atomic_write_json(args.source_calls, merged)
            source_call_cache_merge._atomic_write_json(args.log_dates, cache_summary["log_call_dates"])
            source_call_cache_merge._atomic_write_json(args.summary, cache_summary)
            result["cache_merged"] = True
            result["cache_summary"] = cache_summary
        else:
            result["cache_merged"] = False
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
