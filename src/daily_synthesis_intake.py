#!/usr/bin/env python3
"""Normalize supplied Daily Synthesis JSON into daily_synthesis.json.

This routine does not generate synthesis or market calls. It accepts supplied
structured synthesis output, validates the shape the cockpit consumes, and
writes the repo convention file only when the payload is useful.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any


DEFAULT_OUT = Path(__file__).resolve().parent / "daily_synthesis.json"
DEFAULT_SUMMARY = Path(__file__).resolve().parent / "daily_synthesis_intake_summary.json"

TEXT_FIELDS = ("source", "date", "state_of_play", "delta", "tone", "as_of")
LIST_FIELDS = ("hanging", "actions", "action_items", "recommendations")


def _read_json(path: str | Path) -> Any:
    with Path(path).open(encoding="utf-8") as fh:
        return json.load(fh)


def _atomic_write_json(path: str | Path, payload: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".daily_synthesis.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def _unwrap(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    for key in ("daily_synthesis", "synthesis", "result", "payload"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return payload


def _text(value: Any) -> str:
    return str(value).strip() if value not in (None, "") else ""


def _list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if item not in (None, "", {}, [])]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_action(row: Any) -> Any:
    if isinstance(row, str):
        return row.strip()
    if not isinstance(row, dict):
        return None
    out: dict[str, Any] = {}
    for key, value in row.items():
        if value in (None, "", [], {}):
            continue
        out[str(key)] = value
    return out or None


def normalize_synthesis(payload: Any, *, default_date: str | None = None) -> dict:
    data = _unwrap(payload)
    if not isinstance(data, dict):
        return {}
    out: dict[str, Any] = {}
    for field in TEXT_FIELDS:
        value = _text(data.get(field))
        if value:
            out[field] = value
    if "date" not in out and default_date:
        out["date"] = default_date
    if "source" not in out:
        out["source"] = "Daily Synthesis"

    hanging = _list(data.get("hanging") or data.get("followups") or data.get("follow_ups"))
    if hanging:
        out["hanging"] = hanging

    raw_actions = (
        data.get("actions")
        or data.get("action_items")
        or data.get("recommendations")
        or []
    )
    actions = [
        normalized
        for normalized in (_normalize_action(row) for row in _list(raw_actions))
        if normalized
    ]
    if actions:
        out["actions"] = actions

    notes = _list(data.get("notes") or data.get("observations"))
    if notes:
        out["notes"] = notes
    return out


def validate_synthesis(payload: Any) -> list[str]:
    problems: list[str] = []
    if not isinstance(payload, dict):
        return ["daily synthesis must be an object"]
    if not any(payload.get(field) for field in ("state_of_play", "delta", "hanging", "actions")):
        problems.append("daily synthesis must include state_of_play, delta, hanging, or actions")
    for field in ("source", "date", "state_of_play", "delta"):
        if field in payload and not isinstance(payload[field], str):
            problems.append(f"{field} must be a string")
    for field in ("hanging", "actions", "notes"):
        if field in payload and not isinstance(payload[field], list):
            problems.append(f"{field} must be a list")
    for idx, row in enumerate(payload.get("actions") or []):
        if not isinstance(row, (dict, str)):
            problems.append(f"actions[{idx}] must be an object or string")
        elif isinstance(row, dict) and not any(row.get(k) for k in ("ticker", "symbol", "what", "action", "recommendation", "next_step")):
            problems.append(f"actions[{idx}] must include ticker/symbol or action text")
    return problems


def merge_synthesis(existing: dict, incoming: dict) -> dict:
    out = dict(existing or {})
    out.update({k: v for k, v in incoming.items() if k not in ("hanging", "actions", "notes")})
    for field in ("hanging", "actions", "notes"):
        merged = []
        for item in (existing or {}).get(field) or []:
            if item not in merged:
                merged.append(item)
        for item in incoming.get(field) or []:
            if item not in merged:
                merged.append(item)
        if merged:
            out[field] = merged
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Normalize supplied Daily Synthesis JSON")
    parser.add_argument("files", nargs="*")
    parser.add_argument("--stdin-json", action="store_true")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--merge-existing", action="store_true")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--validate", metavar="SYNTHESIS_JSON")
    args = parser.parse_args(argv)

    if args.validate:
        if not Path(args.validate).is_file():
            print(json.dumps({"valid": False, "path": args.validate, "problems": ["cache file not found"]}, indent=2))
            return 2
        payload = normalize_synthesis(_read_json(args.validate))
        problems = validate_synthesis(payload)
        print(json.dumps({"valid": not problems, "problems": problems}, indent=2))
        return 0 if not problems else 2

    if not args.files and not args.stdin_json:
        print("no input files or --stdin-json supplied", file=sys.stderr)
        return 2

    payloads = [_read_json(path) for path in args.files]
    if args.stdin_json:
        payloads.append(json.load(sys.stdin))

    normalized: dict[str, Any] = {}
    if args.merge_existing and Path(args.out).is_file():
        normalized = normalize_synthesis(_read_json(args.out), default_date=args.date)
    for payload in payloads:
        next_payload = normalize_synthesis(payload, default_date=args.date)
        normalized = merge_synthesis(normalized, next_payload) if normalized else next_payload

    problems = validate_synthesis(normalized)
    summary = {
        "valid": not problems,
        "problems": problems,
        "out": args.out,
        "written": False,
        "hanging_count": len(normalized.get("hanging") or []),
        "action_count": len(normalized.get("actions") or []),
    }
    if problems:
        _atomic_write_json(args.summary, summary)
        print(json.dumps(summary, indent=2))
        return 2

    _atomic_write_json(args.out, normalized)
    summary["written"] = True
    _atomic_write_json(args.summary, summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
