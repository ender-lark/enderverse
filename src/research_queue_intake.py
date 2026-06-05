#!/usr/bin/env python3
"""Normalize Research Queue exports into research_queue.json.

This is a safe routine runner: it does not perform research, write theses, or
create trade actions. It only turns explicit Research Queue rows into the
external `research` block consumed by full_build_runner / feed_assembler.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_OUT = Path(__file__).resolve().parent / "research_queue.json"
TICKER_RE = re.compile(r"^\s*([A-Z]{1,6}(?:\.[A-Z]{1,4})?)\s*(?:[-:\u2014\u2013]|$)")
PENDING_STATUSES = {"working", "queued", "in progress", "active", "research", "todo", "to do"}
DONE_STATUSES = {"done", "complete", "completed", "closed"}
PRIORITY_MAP = {
    "high": "high",
    "urgent": "high",
    "p1": "high",
    "med": "med",
    "medium": "med",
    "normal": "med",
    "p2": "med",
    "low": "low",
    "p3": "low",
    "monitor": "low",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _days_out(value: Any, *, as_of: str | None = None) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    parsed = _parse_date(value)
    if parsed is None:
        try:
            return int(str(value).strip())
        except ValueError:
            return None
    base = _parse_date(as_of) or date.today()
    return (parsed - base).days


def _first(row: dict[str, Any], *keys: str) -> Any:
    lower = {str(k).strip().lower(): v for k, v in row.items()}
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
        lk = key.lower()
        if lk in lower and lower[lk] not in (None, ""):
            return lower[lk]
    return None


def _priority(value: Any) -> str:
    text = str(value or "").strip().lower()
    return PRIORITY_MAP.get(text, text if text in {"high", "med", "low"} else "med")


def _bucket(value: Any) -> str:
    status = str(value or "").strip().lower()
    if status in DONE_STATUSES:
        return "done"
    return "pending"


def _ticker_from(row: dict[str, Any], text: str) -> str:
    direct = _first(row, "ticker", "symbol")
    if direct:
        return str(direct).strip().upper()
    m = TICKER_RE.match(text or "")
    return m.group(1).upper() if m else ""


def normalize_row(row: dict[str, Any], *, as_of: str | None = None) -> dict[str, Any] | None:
    """Normalize one Research Queue row into the engine-friendly row shape."""
    if not isinstance(row, dict):
        return None
    title = str(_first(row, "r", "title", "name", "task", "summary", "research") or "").strip()
    notes = str(_first(row, "notes", "note", "description", "thesis") or "").strip()
    text = title or notes
    if not text:
        return None
    ticker = _ticker_from(row, text)
    if ticker and not TICKER_RE.match(text):
        text = f"{ticker} - {text}"
    pr = _priority(_first(row, "pr", "priority"))
    status = str(_first(row, "status", "state") or "Working").strip()
    days = _days_out(_first(row, "days_out", "days out", "catalyst_days", "catalyst days",
                            "catalyst_date", "catalyst date", "date"),
                     as_of=as_of)
    out = {
        "r": text,
        "pr": pr,
        "status": status,
    }
    if ticker:
        out["ticker"] = ticker
    if notes and notes != title:
        out["notes"] = notes
    if days is not None:
        out["days_out"] = days
    urgency = _first(row, "urgency", "action_state", "action state", "action", "recommendation")
    if urgency:
        out["urgency"] = str(urgency).strip()
    source = _first(row, "source", "provenance")
    if source:
        out["source"] = str(source).strip()
    return out


def _rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        if isinstance(payload.get("pending"), list) or isinstance(payload.get("done"), list):
            rows: list[dict[str, Any]] = []
            for bucket, bucket_rows in (("Working", payload.get("pending") or []),
                                        ("Done", payload.get("done") or [])):
                for row in bucket_rows:
                    if not isinstance(row, dict):
                        rows.append(row)
                        continue
                    copy = dict(row)
                    copy.setdefault("status", bucket)
                    rows.append(copy)
            return rows
        for key in ("rows", "items", "results", "research", "messages"):
            if isinstance(payload.get(key), list):
                return payload[key]
        return [payload]
    if isinstance(payload, list):
        return payload
    return []


def load_rows(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if p.suffix.lower() == ".csv":
        with p.open(newline="", encoding="utf-8-sig") as fh:
            return list(csv.DictReader(fh))
    with p.open(encoding="utf-8-sig") as fh:
        return _rows_from_payload(json.load(fh))


def load_rows_from_stdin() -> list[dict[str, Any]]:
    text = sys.stdin.read()
    if not text.strip():
        return []
    return _rows_from_payload(json.loads(text))


def build_research_queue(rows: list[dict[str, Any]], *,
                         as_of: str | None = None,
                         generated_at: str | None = None) -> dict[str, Any]:
    pending: list[dict[str, Any]] = []
    done: list[dict[str, Any]] = []
    skipped = 0
    for row in rows:
        norm = normalize_row(row, as_of=as_of)
        if norm is None:
            skipped += 1
            continue
        if _bucket(norm.get("status")) == "done":
            done.append(norm)
        else:
            pending.append(norm)
    return {
        "generated_at": generated_at or _utc_now_iso(),
        "source": "research_queue_intake",
        "pending": pending,
        "done": done,
        "summary": {
            "input_rows": len(rows),
            "pending": len(pending),
            "done": len(done),
            "skipped": skipped,
        },
    }


def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    seen = set()
    for row in rows or []:
        key = (row.get("ticker") or "", row.get("r") or "", row.get("status") or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def merge_queues(existing: dict[str, Any] | None, new: dict[str, Any]) -> dict[str, Any]:
    existing = existing if isinstance(existing, dict) else {}
    merged = {
        **new,
        "pending": _dedupe(list(existing.get("pending") or []) + list(new.get("pending") or [])),
        "done": _dedupe(list(existing.get("done") or []) + list(new.get("done") or [])),
    }
    merged["summary"] = {
        **new.get("summary", {}),
        "merged": True,
        "stored_pending": len(merged["pending"]),
        "stored_done": len(merged["done"]),
    }
    return merged


def validate_research_queue(queue: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if not isinstance(queue, dict):
        return ["top-level must be an object"]
    for key in ("pending", "done"):
        rows = queue.get(key)
        if not isinstance(rows, list):
            problems.append(f"{key} must be a list")
            continue
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                problems.append(f"{key}[{idx}] must be an object")
                continue
            if not isinstance(row.get("r"), str) or not row.get("r"):
                problems.append(f"{key}[{idx}].r must be non-empty")
            if row.get("pr") not in {"high", "med", "low"}:
                problems.append(f"{key}[{idx}].pr must be high/med/low")
            if "days_out" in row and not isinstance(row.get("days_out"), int):
                problems.append(f"{key}[{idx}].days_out must be int when present")
    return problems


def _read_json(path: str | Path, default=None):
    p = Path(path)
    if not p.is_file():
        return default
    with p.open(encoding="utf-8") as fh:
        return json.load(fh)


def _atomic_write_json(path: str | Path, payload: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".research_queue_intake.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def _self_test() -> int:
    rows = [
        {"Ticker": "AVGO", "Name": "post-print dossier", "Priority": "High", "Status": "Working", "Catalyst Date": "2026-06-07"},
        {"Name": "Research process cleanup", "Priority": "Low", "Status": "Done"},
    ]
    queue = build_research_queue(rows, as_of="2026-06-05", generated_at="2026-06-05T14:00:00Z")
    assert validate_research_queue(queue) == []
    assert queue["pending"][0]["r"].startswith("AVGO - ")
    assert queue["pending"][0]["days_out"] == 2
    assert queue["done"][0]["r"] == "Research process cleanup"
    print("research_queue_intake self-test: PASS")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Normalize Research Queue export rows into research_queue.json")
    parser.add_argument("inputs", nargs="*", help="Research Queue JSON/CSV exports")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--as-of")
    parser.add_argument("--generated-at")
    parser.add_argument("--merge-existing", action="store_true")
    parser.add_argument("--validate", help="Validate an existing research_queue.json")
    parser.add_argument("--stdin-json", action="store_true",
                        help="Read a Research Queue JSON payload from stdin")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate and summarize without writing the output file")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()
    if args.validate:
        problems = validate_research_queue(_read_json(args.validate, {}))
        if problems:
            print(json.dumps({"valid": False, "problems": problems}, indent=2))
            return 2
        print(json.dumps({"valid": True}, indent=2))
        return 0
    rows: list[dict[str, Any]] = []
    if args.stdin_json:
        rows.extend(load_rows_from_stdin())
    for path in args.inputs:
        rows.extend(load_rows(path))
    if not rows and not args.inputs and not args.stdin_json:
        parser.error("provide at least one JSON/CSV input, --stdin-json, or use --self-test/--validate")
    queue = build_research_queue(rows, as_of=args.as_of, generated_at=args.generated_at)
    if args.merge_existing:
        queue = merge_queues(_read_json(args.out, {}), queue)
    problems = validate_research_queue(queue)
    if problems:
        print(json.dumps({"valid": False, "problems": problems}, indent=2))
        return 2
    if not args.dry_run:
        _atomic_write_json(args.out, queue)
    print(json.dumps({
        "written": None if args.dry_run else args.out,
        "dry_run": bool(args.dry_run),
        "pending": len(queue["pending"]),
        "done": len(queue["done"]),
        "skipped": queue.get("summary", {}).get("skipped", 0),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
