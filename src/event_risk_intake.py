#!/usr/bin/env python3
"""Normalize supplied daily/weekly event-risk rows into event_risks.json."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from event_risk import normalize_event_risks, validate_event_risks


DEFAULT_OUT = Path(__file__).resolve().parent / "event_risks.json"
DEFAULT_SUMMARY = Path(__file__).resolve().parent / "event_risk_intake_summary.json"


def _read_json(path: str | Path) -> Any:
    with Path(path).open(encoding="utf-8-sig") as fh:
        return json.load(fh)


def _atomic_write_json(path: str | Path, payload: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".event_risk.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def _merge(existing: list[dict], incoming: list[dict]) -> list[dict]:
    out = []
    seen = set()
    for row in [*(existing or []), *(incoming or [])]:
        key = (row.get("date"), row.get("title"), row.get("source"))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    out.sort(key=lambda r: (r.get("severity"), r.get("date"), r.get("title")))
    return out


def supplied_event_from_args(args) -> dict | None:
    """Build one supplied event-risk row from CLI flags.

    This is intentionally just a shape helper. The normal event-risk normalizer
    still owns aliases, defaults, validation, and promotion rules.
    """
    if not args.title:
        return None
    return {
        "date": args.date,
        "title": args.title,
        "severity": args.severity,
        "horizon": args.horizon,
        "channels": args.channels,
        "tickers": args.tickers,
        "affected": args.affected,
        "source": args.source,
        "summary": args.why,
        "trigger": args.trigger,
        "direction": args.direction,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Normalize supplied Event Risk JSON")
    parser.add_argument("files", nargs="*")
    parser.add_argument("--stdin-json", action="store_true")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--merge-existing", action="store_true")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--title", help="One supplied sudden-event headline/title to append")
    parser.add_argument("--severity", default="high", choices=["critical", "high", "medium", "low"])
    parser.add_argument("--horizon", default="daily")
    parser.add_argument("--channels", default="", help="Comma/semicolon separated affected channels")
    parser.add_argument("--tickers", default="", help="Comma/semicolon separated symbols or ETFs")
    parser.add_argument("--affected", default="", help="Comma/semicolon separated affected sleeves")
    parser.add_argument("--source", default="Supplied sudden-event note")
    parser.add_argument("--why", default="", help="Why this matters for exposure, hedges, or new-buy timing")
    parser.add_argument("--trigger", default="", help="What to watch next")
    parser.add_argument("--direction", default="risk_watch")
    parser.add_argument("--validate", metavar="EVENT_RISKS_JSON")
    args = parser.parse_args(argv)

    if args.validate:
        if not Path(args.validate).is_file():
            print(json.dumps({"valid": False, "problems": ["cache file not found"]}, indent=2))
            return 2
        rows = normalize_event_risks(_read_json(args.validate), default_date=args.date)
        problems = validate_event_risks(rows)
        print(json.dumps({"valid": not problems, "problems": problems, "rows": len(rows)}, indent=2))
        return 0 if not problems else 2

    supplied_event = supplied_event_from_args(args)
    if not args.files and not args.stdin_json and supplied_event is None:
        print("no input files, --stdin-json, or --title supplied", file=sys.stderr)
        return 2

    payloads = [_read_json(path) for path in args.files]
    if args.stdin_json:
        payloads.append(json.load(sys.stdin))
    if supplied_event is not None:
        payloads.append(supplied_event)

    incoming: list[dict] = []
    for payload in payloads:
        incoming.extend(normalize_event_risks(payload, default_date=args.date))
    existing = normalize_event_risks(_read_json(args.out), default_date=args.date) if args.merge_existing and Path(args.out).is_file() else []
    rows = _merge(existing, incoming) if existing else incoming
    problems = validate_event_risks(rows)
    summary = {
        "valid": not problems,
        "problems": problems,
        "out": args.out,
        "written": False,
        "input_rows": len(incoming),
        "stored": len(rows),
        "promoted": sum(1 for row in rows if row.get("severity") in {"critical", "high"}),
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
