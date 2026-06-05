#!/usr/bin/env python3
"""Fundstrat email intake.

First-mile parser for forwarded/exported Fundstrat emails. It turns raw email
text or Gmail-like JSON into convention files the full build can consume:

- fundstrat_daily_calls.json
- fundstrat_inbox_entries.json
- inbox_call_dates.json
- source_call_candidates.json

This module is intentionally conservative. It emits daily-call rows only when a
ticker appears in action-like context. Non-action mentions remain in the audit
entries so the run is inspectable without polluting conviction.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from email import policy
from email.parser import Parser
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from full_build_runner import normalize_positions_cache


AUTHOR_PATTERNS = (
    ("Newton", re.compile(r"\b(mark\s+)?newton\b", re.I)),
    ("Lee", re.compile(r"\b(tom\s+)?lee\b", re.I)),
    ("Farrell", re.compile(r"\b(sean\s+)?farrell\b", re.I)),
)

BLACKLIST = {
    "AI", "API", "CEO", "CFO", "CPI", "ETF", "EPS", "EU", "FOMC", "GDP",
    "IPO", "PMI", "QOQ", "SEC", "THE", "USA", "USD", "VIX", "YOY",
    "BUY", "SELL", "LONG", "SHORT", "CALL", "PUT", "PUTS", "CALLS",
}

RE_CASHTAG = re.compile(r"\$([A-Z]{1,6}(?:\.[A-Z]{1,4})?)\b")
RE_HEADER_TICKERS = re.compile(
    r"Tickers?(?:\s+in\s+(?:this\s+)?(?:Report|Video|Note))?\s*:\s*([A-Z0-9,; /\.$-]{1,160})",
    re.I,
)
RE_VERB_TICKER = re.compile(
    r"\b(?:buy|add|accumulate|long|own|hold|sell|trim|reduce|short|avoid|watch)\s+"
    r"\$?([A-Z]{1,6}(?:\.[A-Z]{1,4})?)\b",
    re.I,
)
RE_BARE = re.compile(r"\b([A-Z]{2,6}(?:\.[A-Z]{1,4})?)\b")
RE_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")

BULLISH_WORDS = (
    "buy", "add", "accumulate", "long", "overweight", "bullish",
    "constructive", "breakout", "support", "bottom", "reversal",
)
BEARISH_WORDS = (
    "sell", "trim", "reduce", "avoid", "short", "underweight", "bearish",
    "breakdown", "resistance", "risk",
)
ACTION_WORDS = BULLISH_WORDS + BEARISH_WORDS + (
    "entry", "stop", "target", "tgt", "price objective", "upside",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_comments(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_comments(v) for k, v in obj.items()
                if not (isinstance(k, str) and k.startswith("_"))}
    if isinstance(obj, list):
        return [_strip_comments(x) for x in obj]
    return obj


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    with path.open(encoding="utf-8-sig") as fh:
        return _strip_comments(json.load(fh))


def _atomic_write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".fundstrat_intake.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def _body_from_message(msg) -> str:
    if msg.is_multipart():
        parts = []
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    parts.append(part.get_content())
                except Exception:  # pragma: no cover - defensive for odd emails
                    pass
        return "\n".join(parts).strip()
    try:
        return msg.get_content().strip()
    except Exception:  # pragma: no cover
        return str(msg.get_payload() or "").strip()


def parse_date(value: Any, fallback: str | None = None) -> str:
    if value in (None, ""):
        return fallback or datetime.now(timezone.utc).date().isoformat()
    if isinstance(value, (int, float)) or str(value).isdigit():
        n = int(value)
        if n > 10_000_000_000:
            return datetime.fromtimestamp(n / 1000, timezone.utc).date().isoformat()
    text = str(value).strip()
    m = re.search(r"\d{4}-\d{2}-\d{2}", text)
    if m:
        return m.group(0)
    try:
        return parsedate_to_datetime(text).date().isoformat()
    except Exception:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return fallback or datetime.now(timezone.utc).date().isoformat()


def detect_author(*parts: str) -> str:
    text = "\n".join(p or "" for p in parts)
    for author, pat in AUTHOR_PATTERNS:
        if pat.search(text):
            return author
    return "Fundstrat"


def normalize_email_entry(raw: Any, *, fallback_date: str | None = None,
                          source_path: str = "") -> dict:
    """Normalize one raw text or Gmail-like dict into {subject, body, date, ...}."""
    if isinstance(raw, dict):
        message_id = raw.get("id") or raw.get("message_id")
        thread_id = raw.get("thread_id")
        subject = raw.get("subject") or raw.get("title") or ""
        body = raw.get("body") or raw.get("text") or raw.get("snippet") or ""
        sender = raw.get("from") or raw.get("from_") or raw.get("sender") or raw.get("author") or ""
        date_s = parse_date(
            raw.get("date") or raw.get("timestamp") or raw.get("email_ts") or raw.get("internalDate"),
            fallback=fallback_date,
        )
        author = raw.get("analyst") or detect_author(subject, body, sender)
        return {
            "subject": str(subject),
            "body": str(body),
            "from": str(sender),
            "date": date_s,
            "author": str(author),
            "source_path": source_path,
            "message_id": str(message_id or ""),
            "thread_id": str(thread_id or ""),
        }

    text = str(raw or "")
    msg = Parser(policy=policy.default).parsestr(text)
    message_id = msg.get("Message-ID") or ""
    if msg.get("subject") or msg.get("from") or msg.get("date"):
        subject = msg.get("subject") or ""
        sender = msg.get("from") or ""
        body = _body_from_message(msg)
        date_s = parse_date(msg.get("date"), fallback=fallback_date)
        author = detect_author(subject, body, sender)
    else:
        subject = ""
        sender = ""
        body = text
        date_s = parse_date(None, fallback=fallback_date)
        author = detect_author(body)
    return {
        "subject": str(subject),
        "body": str(body),
        "from": str(sender),
        "date": date_s,
        "author": author,
        "source_path": source_path,
        "message_id": str(message_id),
        "thread_id": "",
    }


def load_entries(paths: list[str | Path], *, fallback_date: str | None = None) -> list[dict]:
    entries: list[dict] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.suffix.lower() == ".json":
            payload = _read_json(path, default=[])
            entries.extend(entries_from_payload(payload, fallback_date=fallback_date,
                                                source_path=str(path)))
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
            entries.append(normalize_email_entry(text, fallback_date=fallback_date,
                                                 source_path=str(path)))
    return entries


def entries_from_payload(payload: Any, *, fallback_date: str | None = None,
                         source_path: str = "stdin") -> list[dict]:
    """Normalize a Gmail-like JSON payload into intake entries.

    Accepts a list, `{messages:[...]}`, `{emails:[...]}`, `{responses:[...]}`, or
    a single message dict. This matches the common Gmail connector result shapes.
    """
    if isinstance(payload, dict):
        if isinstance(payload.get("messages"), list):
            rows = payload["messages"]
        elif isinstance(payload.get("emails"), list):
            rows = payload["emails"]
        elif isinstance(payload.get("responses"), list):
            rows = payload["responses"]
        else:
            rows = [payload]
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = []
    return [
        normalize_email_entry(row, fallback_date=fallback_date, source_path=source_path)
        for row in rows
    ]


def _entry_key(entry: dict) -> str:
    msg_id = str(entry.get("message_id") or "").strip()
    if msg_id:
        return f"id:{msg_id}"
    return "|".join([
        str(entry.get("date") or ""),
        str(entry.get("from") or ""),
        str(entry.get("subject") or ""),
    ])


def dedupe_entries(entries: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for entry in entries:
        key = _entry_key(entry)
        if key in seen:
            continue
        seen.add(key)
        out.append(entry)
    return out


def filter_new_entries(entries: list[dict], state: dict | None) -> list[dict]:
    processed = set((state or {}).get("processed_message_ids") or [])
    if not processed:
        return entries
    out = []
    for entry in entries:
        msg_id = str(entry.get("message_id") or "").strip()
        if msg_id and msg_id in processed:
            continue
        out.append(entry)
    return out


def update_state(state: dict | None, entries: list[dict], *, generated_at: str) -> dict:
    prior = state if isinstance(state, dict) else {}
    processed = set(prior.get("processed_message_ids") or [])
    for entry in entries:
        msg_id = str(entry.get("message_id") or "").strip()
        if msg_id:
            processed.add(msg_id)
    dates = sorted({e.get("date") for e in entries if e.get("date")})
    return {
        "last_run_at": generated_at,
        "last_inbox_date": max(dates) if dates else prior.get("last_inbox_date", ""),
        "processed_message_ids": sorted(processed),
    }


def load_ticker_universe(theses_path: str | Path | None = None,
                         positions_path: str | Path | None = None) -> set[str]:
    tickers: set[str] = set()
    theses = _read_json(Path(theses_path), default=[]) if theses_path else []
    for row in theses or []:
        if isinstance(row, dict) and row.get("ticker"):
            tickers.add(str(row["ticker"]).strip().upper())
    if positions_path:
        positions_cache = _read_json(Path(positions_path), default={})
        positions, _ = normalize_positions_cache(positions_cache)
        tickers.update(p["ticker"] for p in positions if p.get("ticker"))
    return tickers


def _ordered_add(out: list[str], seen: set[str], ticker: str) -> None:
    ticker = ticker.strip().upper()
    if ticker and ticker not in BLACKLIST and ticker not in seen:
        out.append(ticker)
        seen.add(ticker)


def extract_tickers(text: str, *, universe: set[str] | None = None) -> list[str]:
    universe = universe or set()
    out: list[str] = []
    seen: set[str] = set()

    for m in RE_CASHTAG.finditer(text):
        _ordered_add(out, seen, m.group(1))

    for m in RE_HEADER_TICKERS.finditer(text):
        for tk in RE_BARE.findall(m.group(1)):
            _ordered_add(out, seen, tk)

    for m in RE_VERB_TICKER.finditer(text):
        _ordered_add(out, seen, m.group(1))

    for m in RE_BARE.finditer(text):
        tk = m.group(1).upper()
        if tk in universe:
            _ordered_add(out, seen, tk)

    return out


def _context_for_ticker(text: str, ticker: str) -> str:
    ticker_re = re.compile(rf"(?<![A-Z])\$?{re.escape(ticker)}(?![A-Z])", re.I)
    for chunk in RE_SENTENCE_SPLIT.split(text):
        if ticker_re.search(chunk):
            return " ".join(chunk.split())[:500]
    return ""


def _has_action_language(text: str) -> bool:
    low = text.lower()
    return any(word in low for word in ACTION_WORDS)


def infer_direction(text: str) -> str | None:
    low = text.lower()
    if any(word in low for word in BEARISH_WORDS):
        if any(word in low for word in ("sell", "trim", "reduce")):
            return "sell"
        return "avoid"
    if any(word in low for word in BULLISH_WORDS):
        return "buy"
    return None


def _level(text: str, names: tuple[str, ...]) -> float | None:
    name_re = "|".join(re.escape(n) for n in names)
    m = re.search(rf"\b(?:{name_re})\b\s*(?:at|near|=|:)?\s*\$?([0-9]+(?:\.[0-9]+)?)",
                  text, re.I)
    return float(m.group(1)) if m else None


def _near_level(text: str) -> float | None:
    m = re.search(r"\b(?:near|at)\s*\$?([0-9]+(?:\.[0-9]+)?)", text, re.I)
    return float(m.group(1)) if m else None


def extract_daily_calls(entries: list[dict], *, universe: set[str] | None = None) -> tuple[list[dict], list[dict]]:
    daily_calls: list[dict] = []
    mentions: list[dict] = []
    seen_calls: set[tuple[str, str, str, str]] = set()

    for entry in entries:
        text = f"{entry.get('subject', '')}\n{entry.get('body', '')}"
        tickers = extract_tickers(text, universe=universe)
        for ticker in tickers:
            context = _context_for_ticker(text, ticker)
            mentions.append({
                "ticker": ticker,
                "author": entry.get("author") or "Fundstrat",
                "date": entry.get("date"),
                "subject": entry.get("subject", ""),
                "action_like": _has_action_language(context),
                "quote": context,
            })
            if not context or not _has_action_language(context):
                continue
            call = {
                "author": entry.get("author") or "Fundstrat",
                "ticker": ticker,
                "direction": infer_direction(context),
                "entry": _level(context, ("entry", "buy", "add")) or _near_level(context),
                "stop": _level(context, ("stop", "risk")),
                "target": _level(context, ("target", "tgt", "objective")),
                "window": None,
                "quote": context,
                "date": entry.get("date"),
                "subject": entry.get("subject", ""),
            }
            key = (call["date"] or "", call["author"], ticker, call["quote"])
            if key in seen_calls:
                continue
            seen_calls.add(key)
            daily_calls.append(call)
    return daily_calls, mentions


def classify_source_call_candidates(daily_calls: list[dict], *, now: str | None = None) -> list[dict]:
    try:
        import source_call_tracker as sct
    except Exception:
        return []
    raw = [
        {
            "source": c.get("author") or "Fundstrat",
            "ticker": c.get("ticker"),
            "date": c.get("date"),
            "text": c.get("quote") or c.get("subject") or "",
        }
        for c in daily_calls
    ]
    return sct.batch_classify(raw, now=now)


def build_intake_payload(entries: list[dict], *, universe: set[str] | None = None,
                         generated_at: str | None = None) -> dict:
    generated_at = generated_at or _utc_now_iso()
    entries = dedupe_entries(entries)
    daily_calls, mentions = extract_daily_calls(entries, universe=universe)
    dates = sorted({e.get("date") for e in entries if e.get("date")})
    source_call_candidates = classify_source_call_candidates(
        daily_calls,
        now=generated_at[:10],
    )
    return {
        "generated_at": generated_at,
        "source": "fundstrat_email_intake",
        "entries": entries,
        "mentions": mentions,
        "daily_calls": daily_calls,
        "inbox_call_dates": dates,
        "source_call_candidates": source_call_candidates,
        "summary": {
            "entries": len(entries),
            "mentions": len(mentions),
            "daily_calls": len(daily_calls),
            "source_call_candidates": len(source_call_candidates),
        },
    }


def _merge_by_key(existing: list[dict], new: list[dict], keys: tuple[str, ...]) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple] = set()
    for row in list(existing or []) + list(new or []):
        if not isinstance(row, dict):
            continue
        key = tuple(row.get(k) for k in keys)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def write_convention_files(payload: dict, out_dir: str | Path, *,
                           merge_existing: bool = False,
                           state: dict | None = None) -> dict:
    out = Path(out_dir)
    entries = payload["entries"]
    daily_calls = payload["daily_calls"]
    inbox_dates = payload["inbox_call_dates"]
    candidates = payload["source_call_candidates"]
    if merge_existing:
        entries = _merge_by_key(
            _read_json(out / "fundstrat_inbox_entries.json", default=[]),
            entries,
            ("message_id", "date", "subject"),
        )
        daily_calls = _merge_by_key(
            _read_json(out / "fundstrat_daily_calls.json", default=[]),
            daily_calls,
            ("date", "author", "ticker", "quote"),
        )
        prior_dates = _read_json(out / "inbox_call_dates.json", default=[])
        inbox_dates = sorted({*(d for d in prior_dates or [] if d), *(d for d in inbox_dates if d)})
        candidates = _merge_by_key(
            _read_json(out / "source_call_candidates.json", default=[]),
            candidates,
            ("date", "source", "ticker", "verbatim_quote"),
        )
    summary = {
        **payload["summary"],
        "merged": bool(merge_existing),
        "stored_entries": len(entries),
        "stored_daily_calls": len(daily_calls),
        "stored_source_call_candidates": len(candidates),
    }
    written = {
        "fundstrat_inbox_entries": _atomic_write_json(out / "fundstrat_inbox_entries.json",
                                                      entries),
        "fundstrat_daily_calls": _atomic_write_json(out / "fundstrat_daily_calls.json",
                                                    daily_calls),
        "inbox_call_dates": _atomic_write_json(out / "inbox_call_dates.json",
                                               inbox_dates),
        "source_call_candidates": _atomic_write_json(out / "source_call_candidates.json",
                                                     candidates),
        "fundstrat_intake_summary": _atomic_write_json(out / "fundstrat_intake_summary.json",
                                                       summary),
    }
    if state is not None:
        written["fundstrat_intake_state"] = _atomic_write_json(out / "fundstrat_intake_state.json",
                                                               state)
    return {k: str(v) for k, v in written.items()}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Parse forwarded/exported Fundstrat emails into convention files."
    )
    parser.add_argument("inputs", nargs="*", help="Email .txt/.eml files or Gmail-like JSON files")
    parser.add_argument("--out-dir", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--theses", default=str(Path(__file__).resolve().parent / "theses.json"))
    parser.add_argument("--positions", default=str(Path(__file__).resolve().parent / "positions.json"))
    parser.add_argument("--as-of", help="Fallback date for raw text with no email Date header")
    parser.add_argument("--generated-at")
    parser.add_argument("--stdin-json", action="store_true",
                        help="Read Gmail-like message JSON from stdin")
    parser.add_argument("--state", help="Optional processed-message state JSON path")
    parser.add_argument("--include-seen", action="store_true",
                        help="Do not filter messages already listed in --state")
    parser.add_argument("--merge-existing", action="store_true",
                        help="Merge emitted rows with existing convention files")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    state = _read_json(Path(args.state), default={}) if args.state else {}
    entries = []
    if args.stdin_json:
        entries.extend(entries_from_payload(json.load(os.sys.stdin), fallback_date=args.as_of))
    if args.inputs:
        entries.extend(load_entries(args.inputs, fallback_date=args.as_of))
    if not entries:
        parser.error("provide at least one input file or --stdin-json")
    entries = dedupe_entries(entries)
    if args.state and not args.include_seen:
        entries = filter_new_entries(entries, state)
    universe = load_ticker_universe(args.theses, args.positions)
    payload = build_intake_payload(entries, universe=universe,
                                   generated_at=args.generated_at)
    next_state = update_state(state, entries, generated_at=payload["generated_at"]) if args.state else None
    written = {} if args.dry_run else write_convention_files(
        payload,
        args.out_dir,
        merge_existing=args.merge_existing,
        state=next_state,
    )
    print(json.dumps({
        "parsed": True,
        **payload["summary"],
        "state_updated": bool(next_state),
        "written": written,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
