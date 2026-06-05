#!/usr/bin/env python3
"""Normalize supplied UW close-price responses into uw_closes.json.

No network calls happen here. The UW/cache routine supplies close-price
responses or normalized close arrays; this command validates and writes the
repo convention file consumed by full_build_runner.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from runtime_adapters import UW_ROTATION_TICKERS, closes_by_ticker_from_uw
from uw_price import LOOKBACK_3M


DEFAULT_OUT = Path(__file__).resolve().parent / "uw_closes.json"
DEFAULT_SUMMARY = Path(__file__).resolve().parent / "uw_price_cache_summary.json"
MIN_CLOSES = LOOKBACK_3M + 1


def _read_json(path: str | Path) -> Any:
    with Path(path).open(encoding="utf-8") as fh:
        return json.load(fh)


def _atomic_write_json(path: str | Path, payload: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".uw_price_cache.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def _num(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except ValueError:
        return None


def _series_from_value(value: Any) -> list[float]:
    if isinstance(value, dict) and isinstance(value.get("data"), list):
        return closes_by_ticker_from_uw({"_": value}).get("_", [])
    if not isinstance(value, list):
        return []
    if value and all(isinstance(row, dict) for row in value):
        points = []
        for row in value:
            close = _num(row.get("c") or row.get("close"))
            if close is None:
                continue
            points.append((str(row.get("date") or ""), close))
        points.sort(key=lambda dc: dc[0])
        return [float(close) for _, close in points]
    return [float(num) for num in (_num(row) for row in value) if num is not None]


def _unwrap_payload(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    for key in ("responses_by_ticker", "uw_price_responses", "responses", "prices", "closes"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return payload


def normalize_price_cache(payloads: list[Any]) -> dict[str, list[float]]:
    """Return {ticker: [oldest..newest closes]} from supplied payloads."""
    out: dict[str, list[float]] = {}
    for payload in payloads:
        data = _unwrap_payload(payload)
        if not isinstance(data, dict):
            continue
        for ticker, value in data.items():
            tk = str(ticker or "").strip().upper()
            if not tk:
                continue
            series = _series_from_value(value)
            if series:
                out[tk] = series
    return out


def validate_price_cache(cache: dict[str, list[float]], *, required_tickers=None) -> dict:
    required = [str(t).upper() for t in (required_tickers or UW_ROTATION_TICKERS)]
    missing = [ticker for ticker in required if ticker not in cache]
    too_short = {
        ticker: len(cache.get(ticker) or [])
        for ticker in required
        if ticker in cache and len(cache.get(ticker) or []) < MIN_CLOSES
    }
    present = sorted(cache)
    valid = not missing and not too_short
    return {
        "valid": valid,
        "tickers": present,
        "ticker_count": len(present),
        "required_tickers": required,
        "missing_tickers": missing,
        "too_short": too_short,
        "min_closes_required": MIN_CLOSES,
    }


def build_cache_from_inputs(paths: list[str], *, stdin_payload: Any = None,
                            merge_existing: str | Path | None = None) -> dict[str, list[float]]:
    payloads = []
    if merge_existing and Path(merge_existing).is_file():
        payloads.append(_read_json(merge_existing))
    payloads.extend(_read_json(path) for path in paths)
    if stdin_payload is not None:
        payloads.append(stdin_payload)
    return normalize_price_cache(payloads)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Normalize UW close responses into uw_closes.json")
    parser.add_argument("files", nargs="*", help="UW close response JSON files")
    parser.add_argument("--stdin-json", action="store_true", help="read a JSON payload from stdin")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--merge-existing", action="store_true",
                        help="merge with the current --out cache before validation/write")
    parser.add_argument("--allow-partial", action="store_true",
                        help="write even when default rotation tickers are missing/short")
    parser.add_argument("--validate", metavar="CACHE", help="validate an existing normalized cache")
    args = parser.parse_args(argv)

    if args.validate:
        if not Path(args.validate).is_file():
            print(json.dumps({
                "valid": False,
                "path": args.validate,
                "problems": ["cache file not found"],
            }, indent=2))
            return 2
        cache = normalize_price_cache([_read_json(args.validate)])
        summary = validate_price_cache(cache)
        print(json.dumps(summary, indent=2))
        return 0 if summary["valid"] else 2

    if not args.files and not args.stdin_json:
        print("no input files or --stdin-json supplied", file=sys.stderr)
        return 2

    stdin_payload = json.load(sys.stdin) if args.stdin_json else None
    cache = build_cache_from_inputs(
        args.files,
        stdin_payload=stdin_payload,
        merge_existing=args.out if args.merge_existing else None,
    )
    summary = validate_price_cache(cache)
    summary["out"] = args.out
    summary["written"] = False

    if not summary["valid"] and not args.allow_partial:
        _atomic_write_json(args.summary, summary)
        print(json.dumps(summary, indent=2))
        return 2

    _atomic_write_json(args.out, cache)
    summary["written"] = True
    _atomic_write_json(args.summary, summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
