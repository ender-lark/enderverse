#!/usr/bin/env python3
"""Normalize supplied Signal Log JSON into signal_log.json.

Signal Log rows are watch-only cockpit context. This routine validates and
writes supplied rows; it does not promote actions or infer trades.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_OUT = Path(__file__).resolve().parent / "signal_log.json"
DEFAULT_SUMMARY = Path(__file__).resolve().parent / "signal_log_intake_summary.json"

TEXT_ALIASES = ("signal", "title", "what", "summary", "note", "notes", "description")
TICKER_ALIASES = ("ticker", "symbol", "name")
DATE_ALIASES = ("date", "as_of", "created_at", "timestamp")
PRIORITY_ALIASES = ("priority", "urgency", "rank")


def _read_json(path: str | Path) -> Any:
    with Path(path).open(encoding="utf-8") as fh:
        return json.load(fh)


def _atomic_write_json(path: str | Path, payload: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".signal_log.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def _first(row: dict, keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _unwrap(payload: Any) -> list:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("signal_log", "signals", "rows", "items", "results", "morning_scan"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return [payload] if any(payload.get(key) for key in TEXT_ALIASES) else []


def normalize_signal_log(payloads: list[Any]) -> list[dict]:
    rows: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for payload in payloads:
        for raw in _unwrap(payload):
            if isinstance(raw, str):
                raw = {"signal": raw}
            if not isinstance(raw, dict):
                continue
            text = _first(raw, TEXT_ALIASES)
            if text is None:
                continue
            row: dict[str, Any] = {"signal": str(text).strip()}
            ticker = _first(raw, TICKER_ALIASES)
            if ticker:
                row["ticker"] = str(ticker).strip().upper()
            date = _first(raw, DATE_ALIASES)
            if date:
                row["date"] = str(date).strip()[:10]
            priority = _first(raw, PRIORITY_ALIASES)
            if priority:
                row["priority"] = str(priority).strip().lower()
            source = raw.get("source")
            if source:
                row["source"] = str(source).strip()
            key = (row.get("ticker", ""), row.get("date", ""), row["signal"])
            if key not in seen:
                seen.add(key)
                rows.append(row)
    return rows


def validate_signal_log(rows: Any) -> list[str]:
    problems: list[str] = []
    if not isinstance(rows, list):
        return ["signal log must be a list"]
    if not rows:
        problems.append("signal log must include at least one row")
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            problems.append(f"rows[{idx}] must be an object")
            continue
        if not any(isinstance(row.get(key), str) and row.get(key).strip() for key in ("signal", "title", "what", "summary")):
            problems.append(f"rows[{idx}] must include non-empty signal/title/what/summary")
        ticker = row.get("ticker")
        if ticker is not None and not isinstance(ticker, str):
            problems.append(f"rows[{idx}].ticker must be a string when present")
    return problems


def merge_rows(existing: list[dict], incoming: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for row in [*(existing or []), *(incoming or [])]:
        if not isinstance(row, dict):
            continue
        key = (
            str(row.get("ticker") or ""),
            str(row.get("date") or ""),
            str(row.get("signal") or row.get("title") or row.get("what") or row.get("summary") or ""),
        )
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Normalize supplied Signal Log JSON")
    parser.add_argument("files", nargs="*")
    parser.add_argument("--stdin-json", action="store_true")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--merge-existing", action="store_true")
    parser.add_argument("--validate", metavar="SIGNAL_LOG_JSON")
    args = parser.parse_args(argv)

    if args.validate:
        if not Path(args.validate).is_file():
            print(json.dumps({"valid": False, "path": args.validate, "problems": ["cache file not found"]}, indent=2))
            return 2
        rows = normalize_signal_log([_read_json(args.validate)])
        problems = validate_signal_log(rows)
        print(json.dumps({"valid": not problems, "problems": problems, "rows": len(rows)}, indent=2))
        return 0 if not problems else 2

    if not args.files and not args.stdin_json:
        print("no input files or --stdin-json supplied", file=sys.stderr)
        return 2

    payloads = [_read_json(path) for path in args.files]
    if args.stdin_json:
        payloads.append(json.load(sys.stdin))
    rows = normalize_signal_log(payloads)
    if args.merge_existing and Path(args.out).is_file():
        rows = merge_rows(normalize_signal_log([_read_json(args.out)]), rows)

    problems = validate_signal_log(rows)
    summary = {
        "valid": not problems,
        "problems": problems,
        "out": args.out,
        "written": False,
        "rows": len(rows),
    }
    if problems:
        _atomic_write_json(args.summary, summary)
        print(json.dumps(summary, indent=2))
        return 2

    _atomic_write_json(args.out, rows)
    summary["written"] = True
    _atomic_write_json(args.summary, summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
