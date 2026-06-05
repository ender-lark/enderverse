#!/usr/bin/env python3
"""Merge classified source-call candidates into the repo source-call cache."""
from __future__ import annotations

import argparse
import hashlib
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
    fd, tmp = tempfile.mkstemp(prefix=".source_call_cache.", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return p


def _call_id(row: dict) -> str:
    raw = "|".join(str(row.get(k) or "") for k in (
        "source", "ticker", "date", "tier", "verbatim_quote", "call_summary"
    ))
    return "repo_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _norm_call(row: dict) -> dict | None:
    if not isinstance(row, dict):
        return None
    source = str(row.get("source") or "").strip().lower()
    if not source:
        return None
    ticker = row.get("ticker") or row.get("named_ticker")
    ticker = str(ticker).strip().upper() if ticker else None
    out = {
        "source": source,
        "ticker": ticker or None,
        "tier": str(row.get("tier") or "").strip().upper() or None,
        "confidence_in_tier": row.get("confidence_in_tier") or row.get("confidence"),
        "verbatim_quote": row.get("verbatim_quote") or row.get("text") or "",
        "falsification_condition": row.get("falsification_condition") or row.get("falsification"),
        "date": str(row.get("date") or row.get("call_date") or "")[:10],
        "window_end": str(row.get("window_end") or row.get("scoring_deadline") or "")[:10],
        "window_days": row.get("window_days"),
        "outcome": row.get("outcome") or "Pending",
        "backfill": bool(row.get("backfill", False)),
        "classified_at": row.get("classified_at"),
        "call_summary": row.get("call_summary"),
        "repo_cache_only": bool(row.get("repo_cache_only", True)),
    }
    out["id"] = row.get("id") or _call_id(out)
    return out


def _key(row: dict) -> tuple:
    return (
        row.get("source"),
        row.get("ticker"),
        row.get("date"),
        row.get("tier"),
        row.get("verbatim_quote") or row.get("call_summary") or row.get("id"),
    )


def merge_source_calls(existing: list[dict] | None, candidates: list[dict] | None,
                       *, generated_at: str | None = None) -> tuple[list[dict], dict]:
    generated_at = generated_at or _utc_now_iso()
    rows: list[dict] = []
    seen: set[tuple] = set()
    existing_n = 0
    added_n = 0

    for raw in existing or []:
        row = _norm_call(raw)
        if not row:
            continue
        key = _key(row)
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
        existing_n += 1

    for raw in candidates or []:
        row = _norm_call({**raw, "repo_cache_only": True} if isinstance(raw, dict) else raw)
        if not row:
            continue
        key = _key(row)
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
        added_n += 1

    dates = sorted({r.get("date") for r in rows if r.get("date")})
    summary = {
        "generated_at": generated_at,
        "existing": existing_n,
        "candidates": len([c for c in (candidates or []) if isinstance(c, dict)]),
        "added": added_n,
        "stored": len(rows),
        "log_call_dates": dates,
    }
    return rows, summary


def main(argv=None) -> int:
    src = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Merge source-call candidates into source_calls.json")
    parser.add_argument("--candidates", default=str(src / "source_call_candidates.json"))
    parser.add_argument("--source-calls", default=str(src / "source_calls.json"))
    parser.add_argument("--log-dates", default=str(src / "log_call_dates.json"))
    parser.add_argument("--summary", default=str(src / "source_call_cache_summary.json"))
    parser.add_argument("--generated-at")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    candidates = _read_json(args.candidates, default=[])
    existing = _read_json(args.source_calls, default=[])
    merged, summary = merge_source_calls(existing, candidates, generated_at=args.generated_at)
    if not args.dry_run:
        _atomic_write_json(args.source_calls, merged)
        _atomic_write_json(args.log_dates, summary["log_call_dates"])
        _atomic_write_json(args.summary, summary)
    print(json.dumps({"merged": True, **summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
