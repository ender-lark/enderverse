#!/usr/bin/env python3
"""Catalyst Calendar intake.

Converts exported/uploaded catalyst rows into the repo convention file
`catalysts.json`, which full_build_runner then normalizes into cockpit catalyst
rows and ACT_NOW pre-catalyst actions for held names.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_comments(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_comments(v) for k, v in obj.items()
                if not (isinstance(k, str) and k.startswith("_"))}
    if isinstance(obj, list):
        return [_strip_comments(x) for x in obj]
    return obj


def _read_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.is_file():
        return default
    with p.open(encoding="utf-8-sig") as fh:
        return _strip_comments(json.load(fh))


def _atomic_write_json(path: str | Path, payload: Any) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".catalyst_intake.", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return p


def _date_text(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("start") or value.get("date") or value.get("plain_text")
    text = str(value or "").strip()
    return text[:10] if text else ""


def _first(row: dict, keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return row.get(key)
        for actual in row:
            if str(actual).strip().lower() == key.lower() and row.get(actual) not in (None, ""):
                return row.get(actual)
    return None


def normalize_catalyst_row(row: dict, *, default_source: str = "Catalyst Calendar") -> dict | None:
    if not isinstance(row, dict):
        return None
    ticker = _first(row, ("ticker", "tickers", "symbol", "symbols"))
    date = _date_text(_first(row, ("date", "event_date", "event date", "catalyst_date",
                                   "catalyst date", "when", "start")))
    label = _first(row, ("label", "name", "title", "catalyst", "event", "type"))
    source = _first(row, ("source", "calendar", "origin")) or default_source
    if not ticker or not date:
        return None
    return {
        "ticker": str(ticker).strip().upper(),
        "date": date,
        "label": str(label or "Catalyst").strip() or "Catalyst",
        "source": str(source).strip() or default_source,
    }


def _rows_from_payload(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("catalysts", "events", "rows", "results", "data"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [r for r in rows if isinstance(r, dict)]
        return [payload]
    return []


def load_catalyst_rows(paths: list[str | Path]) -> list[dict]:
    rows: list[dict] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.suffix.lower() == ".csv":
            with path.open(newline="", encoding="utf-8-sig") as fh:
                rows.extend(dict(r) for r in csv.DictReader(fh))
        else:
            rows.extend(_rows_from_payload(_read_json(path, default=[])))
    return rows


def merge_catalysts(existing: list[dict] | None, new_rows: list[dict] | None,
                    *, default_source: str = "Catalyst Calendar",
                    generated_at: str | None = None) -> tuple[list[dict], dict]:
    generated_at = generated_at or _utc_now_iso()
    out: list[dict] = []
    seen: set[tuple] = set()
    existing_n = 0
    added_n = 0

    for raw in existing or []:
        row = normalize_catalyst_row(raw, default_source=default_source)
        if not row:
            continue
        key = (row["ticker"], row["date"], row["label"], row["source"])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        existing_n += 1

    for raw in new_rows or []:
        row = normalize_catalyst_row(raw, default_source=default_source)
        if not row:
            continue
        key = (row["ticker"], row["date"], row["label"], row["source"])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        added_n += 1

    out.sort(key=lambda r: (r["date"], r["ticker"], r["label"]))
    summary = {
        "generated_at": generated_at,
        "existing": existing_n,
        "input_rows": len([r for r in (new_rows or []) if isinstance(r, dict)]),
        "added": added_n,
        "stored": len(out),
        "dates": sorted({r["date"] for r in out if r.get("date")}),
    }
    return out, summary


def main(argv=None) -> int:
    src = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Build catalysts.json from exported Catalyst Calendar rows")
    parser.add_argument("inputs", nargs="*", help="Catalyst JSON/CSV exports")
    parser.add_argument("--out", default=str(src / "catalysts.json"))
    parser.add_argument("--summary", default=str(src / "catalyst_intake_summary.json"))
    parser.add_argument("--merge-existing", action="store_true")
    parser.add_argument("--default-source", default="Catalyst Calendar")
    parser.add_argument("--generated-at")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not args.inputs:
        parser.error("provide at least one Catalyst Calendar JSON/CSV input")
    incoming = load_catalyst_rows(args.inputs)
    existing = _read_json(args.out, default=[]) if args.merge_existing else []
    merged, summary = merge_catalysts(
        existing,
        incoming,
        default_source=args.default_source,
        generated_at=args.generated_at,
    )
    if not args.dry_run:
        _atomic_write_json(args.out, merged)
        _atomic_write_json(args.summary, summary)
    print(json.dumps({"parsed": True, **summary, "written": not args.dry_run}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
