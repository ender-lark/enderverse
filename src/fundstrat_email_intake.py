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
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from email import policy
from email.parser import Parser
from email.utils import parsedate_to_datetime
from html import unescape
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
    "breakdown", "resistance", "risk", "profit", "profits", "harvest",
    "harvesting",
)
ACTION_WORDS = BULLISH_WORDS + BEARISH_WORDS + (
    "entry", "stop", "target", "tgt", "price objective", "upside",
    "taking profits", "take profits", "rebalance", "rotation", "rotate",
    "shift",
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


def _first_value(raw: dict, names: tuple[str, ...]) -> Any:
    for name in names:
        if name in raw and raw[name] not in (None, ""):
            return raw[name]
    return None


def _stringify_body(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, list):
        return "\n".join(_stringify_body(v) for v in value if v not in (None, ""))
    if isinstance(value, dict):
        for key in ("plain", "text", "body", "content", "html"):
            if key in value and value[key] not in (None, ""):
                return _stringify_body(value[key])
        return json.dumps(value, sort_keys=True)
    text = str(value)
    if "<" in text and ">" in text:
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        text = unescape(text)
    return " ".join(text.split())


def _stringify_sender(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, dict):
        name = value.get("name") or value.get("display_name") or ""
        email = value.get("email") or value.get("address") or value.get("value") or ""
        return " ".join(str(v) for v in (name, email) if v).strip()
    if isinstance(value, list):
        return ", ".join(_stringify_sender(v) for v in value if v not in (None, ""))
    return str(value)


def _unwrap_connector_row(raw: dict) -> dict:
    """Unwrap common Gmail connector batch-read envelopes.

    Search rows are usually direct message dicts. Batch-read rows may wrap the
    email under keys such as `email`, `message`, `result`, or `data`, sometimes
    alongside a success/error flag. Keep direct rows intact when no wrapper is
    present.
    """
    for key in ("email", "message", "result", "data"):
        nested = raw.get(key)
        if isinstance(nested, dict):
            merged = {k: v for k, v in raw.items() if k not in {"email", "message", "result", "data"}}
            merged.update(nested)
            return merged
    return raw


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
        raw = _unwrap_connector_row(raw)
        message_id = _first_value(raw, ("id", "message_id", "messageId", "gmail_id", "gmailId"))
        thread_id = _first_value(raw, ("thread_id", "threadId"))
        subject = _first_value(raw, ("subject", "title")) or ""
        direct_body = _first_value(raw, (
            "body", "text", "plain", "plain_text", "text_plain", "body_text",
            "content", "html", "body_html",
        ))
        if direct_body:
            body = _stringify_body(direct_body)
            body_source = "body"
        else:
            body = _stringify_body(_first_value(raw, ("snippet", "preview", "summary")))
            body_source = "snippet" if body else "missing"
        sender = _stringify_sender(_first_value(raw, (
            "from", "from_", "sender", "author", "from_email", "fromEmail",
        )))
        date_s = parse_date(
            _first_value(raw, (
                "date", "timestamp", "email_ts", "internalDate", "internal_date",
                "received_at", "receivedAt",
            )),
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
            "body_source": body_source,
            "body_fetched": body_source in {"body", "text"},
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
        "body_source": "email" if message_id else "text",
        "body_fetched": True,
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
        rows = None
        for key in ("responses", "emails", "messages", "results", "items"):
            if isinstance(payload.get(key), list):
                rows = payload[key]
                break
        if rows is None:
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
    state = state or {}
    processed = set(state.get("processed_full_body_message_ids") or state.get("processed_message_ids") or [])
    snippet_seen = set(state.get("snippet_discovery_message_ids") or [])
    if not processed and not snippet_seen:
        return entries
    out = []
    for entry in entries:
        msg_id = str(entry.get("message_id") or "").strip()
        if msg_id and msg_id in processed:
            continue
        if msg_id and msg_id in snippet_seen and not entry.get("body_fetched", True):
            continue
        out.append(entry)
    return out


def update_state(state: dict | None, entries: list[dict], *, generated_at: str) -> dict:
    prior = state if isinstance(state, dict) else {}
    processed = set(prior.get("processed_full_body_message_ids") or prior.get("processed_message_ids") or [])
    snippet_seen = set(prior.get("snippet_discovery_message_ids") or [])
    for entry in entries:
        msg_id = str(entry.get("message_id") or "").strip()
        if not msg_id:
            continue
        if entry.get("body_fetched", True):
            processed.add(msg_id)
        else:
            snippet_seen.add(msg_id)
    full_body_dates = sorted({
        e.get("date") for e in entries
        if e.get("date") and e.get("body_fetched", True)
    })
    discovery_dates = sorted({e.get("date") for e in entries if e.get("date")})
    last_discovery = max(discovery_dates) if discovery_dates else prior.get("last_discovery_date", "")
    return {
        "last_run_at": generated_at,
        "last_inbox_date": max(full_body_dates) if full_body_dates else prior.get("last_inbox_date", ""),
        "last_discovery_date": last_discovery,
        "processed_message_ids": sorted(processed),
        "processed_full_body_message_ids": sorted(processed),
        "snippet_discovery_message_ids": sorted(snippet_seen),
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
    fallback = ""
    for chunk in RE_SENTENCE_SPLIT.split(text):
        if ticker_re.search(chunk):
            context = " ".join(chunk.split())[:500]
            if _has_action_language(context):
                return context
            if not fallback:
                fallback = context
    return fallback


def _has_action_language(text: str) -> bool:
    low = text.lower()
    return any(word in low for word in ACTION_WORDS)


def infer_direction(text: str) -> str | None:
    low = text.lower()
    if any(phrase in low for phrase in ("taking profits", "take profits", "harvest gains", "harvesting gains")):
        return "sell"
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
    full_body_entries = [e for e in entries if e.get("body_fetched", True)]
    snippet_entries = [e for e in entries if not e.get("body_fetched", True)]
    daily_calls, mentions = extract_daily_calls(full_body_entries, universe=universe)
    dates = sorted({c.get("date") for c in daily_calls if c.get("date")})
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
            "full_body_entries": len(full_body_entries),
            "snippet_only_entries": len(snippet_entries),
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


def _body_sha256(body: Any) -> str:
    if not body:
        return ""
    return hashlib.sha256(str(body).encode("utf-8")).hexdigest()


def redact_entry_body(entry: dict) -> dict:
    """Remove raw email body text from saved audit rows."""
    out = dict(entry)
    body = out.pop("body", "")
    out["body_redacted"] = bool(body)
    out["body_chars"] = len(str(body or ""))
    out["body_sha256"] = _body_sha256(body)
    return out


def redact_entry_bodies(entries: list[dict]) -> list[dict]:
    return [redact_entry_body(e) if isinstance(e, dict) else e for e in entries]


def _prospect_direction(direction: str | None) -> str | None:
    if direction in {"sell", "avoid"}:
        return "avoid"
    if direction == "buy":
        return "long"
    return None


def update_top_prospects_cache(daily_calls: list[dict], path: str | Path, *,
                               generated_at: str | None = None) -> dict:
    """Merge full-body Fundstrat daily calls into top_prospects.json.

    This intentionally consumes only `daily_calls`, never snippet-only discovery
    rows. It stores ticker/source/date/direction events and avoids storing raw
    publication body text in the prospects cache.
    """
    picks = []
    for call in daily_calls or []:
        direction = _prospect_direction(call.get("direction"))
        ticker = str(call.get("ticker") or "").strip().upper()
        if not direction or not ticker:
            continue
        try:
            from top_prospects_feeder import (
                Pick,
                load_cache,
                merge_picks,
                recompute,
                save_cache,
            )
        except Exception as exc:
            return {"updated": False, "picks": 0, "error": str(exc)}
        picks.append(Pick(
            ticker=ticker,
            analyst=call.get("author") or "Fundstrat",
            date=call.get("date") or "",
            direction=direction,
            report_type="note",
            provenance=call.get("subject") or "Fundstrat daily call",
            substantive=bool(call.get("entry") or call.get("stop") or call.get("target")),
        ))
    if not picks:
        return {"updated": False, "picks": 0}

    cache_path = Path(path)
    cache = load_cache(cache_path)
    cache = merge_picks(cache, picks)
    cache = recompute(cache, now=(generated_at or "")[:10] or None)
    save_cache(cache, cache_path)
    return {"updated": True, "picks": len(picks), "path": str(cache_path)}


def update_source_call_cache(candidates: list[dict], source_calls_path: str | Path, *,
                             log_dates_path: str | Path | None = None,
                             summary_path: str | Path | None = None,
                             generated_at: str | None = None) -> dict:
    """Merge classified candidates into source_calls/log_call_dates.

    The caller passes `source_call_candidates`, which are produced only from
    full-body daily calls. Snippet-only discovery therefore cannot update source
    call calibration state through this helper.
    """
    candidate_rows = [c for c in candidates or [] if isinstance(c, dict)]
    if not candidate_rows:
        return {"updated": False, "candidates": 0}
    try:
        from source_call_cache_merge import (
            _atomic_write_json as _write_source_call_json,
            _read_json as _read_source_call_json,
            merge_source_calls,
        )
    except Exception as exc:
        return {"updated": False, "candidates": len(candidate_rows), "error": str(exc)}

    source_path = Path(source_calls_path)
    log_path = Path(log_dates_path) if log_dates_path else source_path.with_name("log_call_dates.json")
    summary_out = (
        Path(summary_path)
        if summary_path
        else source_path.with_name("source_call_cache_summary.json")
    )
    existing = _read_source_call_json(source_path, default=[])
    merged, summary = merge_source_calls(
        existing,
        candidate_rows,
        generated_at=generated_at,
    )
    _write_source_call_json(source_path, merged)
    _write_source_call_json(log_path, summary["log_call_dates"])
    _write_source_call_json(summary_out, summary)
    return {
        "updated": summary["added"] > 0,
        "candidates": summary["candidates"],
        "added": summary["added"],
        "stored": summary["stored"],
        "log_call_dates": len(summary["log_call_dates"]),
        "path": str(source_path),
        "log_dates_path": str(log_path),
        "summary_path": str(summary_out),
    }


def write_convention_files(payload: dict, out_dir: str | Path, *,
                           merge_existing: bool = False,
                           state: dict | None = None,
                           redact_bodies: bool = True,
                           top_prospects_path: str | Path | None = None,
                           source_calls_path: str | Path | None = None,
                           log_dates_path: str | Path | None = None,
                           source_call_summary_path: str | Path | None = None) -> dict:
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
        "bodies_redacted": bool(redact_bodies),
        "stored_entries": len(entries),
        "stored_daily_calls": len(daily_calls),
        "stored_source_call_candidates": len(candidates),
    }
    entries_to_write = redact_entry_bodies(entries) if redact_bodies else entries
    written = {
        "fundstrat_inbox_entries": _atomic_write_json(out / "fundstrat_inbox_entries.json",
                                                      entries_to_write),
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
    if top_prospects_path:
        top_summary = update_top_prospects_cache(
            daily_calls,
            top_prospects_path,
            generated_at=payload.get("generated_at"),
        )
        summary["top_prospects"] = top_summary
        payload["summary"]["top_prospects"] = top_summary
        _atomic_write_json(out / "fundstrat_intake_summary.json", summary)
        if top_summary.get("updated"):
            written["top_prospects"] = Path(top_summary["path"])
    if source_calls_path:
        source_call_summary = update_source_call_cache(
            candidates,
            source_calls_path,
            log_dates_path=log_dates_path,
            summary_path=source_call_summary_path,
            generated_at=payload.get("generated_at"),
        )
        summary["source_calls"] = source_call_summary
        payload["summary"]["source_calls"] = source_call_summary
        _atomic_write_json(out / "fundstrat_intake_summary.json", summary)
        if source_call_summary.get("candidates"):
            written["source_calls"] = Path(source_call_summary.get("path") or source_calls_path)
            written["log_call_dates"] = Path(source_call_summary.get("log_dates_path") or log_dates_path or out / "log_call_dates.json")
            written["source_call_cache_summary"] = Path(source_call_summary.get("summary_path") or source_call_summary_path or out / "source_call_cache_summary.json")
    return {k: str(v) for k, v in written.items()}


def validate_intake_outputs(out_dir: str | Path) -> list[str]:
    out = Path(out_dir)
    problems: list[str] = []
    expected = {
        "fundstrat_inbox_entries.json": list,
        "fundstrat_daily_calls.json": list,
        "inbox_call_dates.json": list,
        "source_call_candidates.json": list,
        "fundstrat_intake_summary.json": dict,
    }
    for name, typ in expected.items():
        path = out / name
        if not path.is_file():
            problems.append(f"{name} missing")
            continue
        data = _read_json(path, default=None)
        if not isinstance(data, typ):
            problems.append(f"{name} must be {typ.__name__}")
            continue
        if name == "fundstrat_inbox_entries.json":
            for idx, row in enumerate(data):
                if isinstance(row, dict) and "body" in row:
                    problems.append(f"{name}[{idx}] contains raw body")
    return problems


def _self_test() -> int:
    import tempfile as _tempfile

    with _tempfile.TemporaryDirectory() as d:
        entry = normalize_email_entry("\n".join([
            "From: Mark Newton mark.newton@fundstratdirect.com",
            "Date: Fri, 05 Jun 2026 09:30:00 -0400",
            "Subject: Daily Technical Strategy",
            "",
            "Buy NVDA near 170, stop 160, target 200.",
        ]))
        payload = build_intake_payload(
            [entry],
            universe={"NVDA"},
            generated_at="2026-06-05T14:00:00+00:00",
        )
        write_convention_files(payload, d)
        problems = validate_intake_outputs(d)
        assert not problems, problems
        calls = _read_json(Path(d) / "fundstrat_daily_calls.json", default=[])
        assert calls and calls[0]["ticker"] == "NVDA"
    print("fundstrat_email_intake self-test: PASS")
    return 0


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
    parser.add_argument("--keep-bodies", action="store_true",
                        help="Write raw email bodies to fundstrat_inbox_entries.json")
    parser.add_argument("--top-prospects", nargs="?", const=str(Path(__file__).resolve().parent / "top_prospects.json"),
                        help="Also merge full-body daily calls into top_prospects.json")
    parser.add_argument("--source-calls", nargs="?", const=str(Path(__file__).resolve().parent / "source_calls.json"),
                        help="Also merge full-body source-call candidates into source_calls.json")
    parser.add_argument("--log-call-dates", default=str(Path(__file__).resolve().parent / "log_call_dates.json"),
                        help="Path for log_call_dates.json when --source-calls is used")
    parser.add_argument("--source-call-summary", default=str(Path(__file__).resolve().parent / "source_call_cache_summary.json"),
                        help="Path for source_call_cache_summary.json when --source-calls is used")
    parser.add_argument("--validate", help="Validate an output directory without writing")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()
    if args.validate:
        problems = validate_intake_outputs(args.validate)
        print(json.dumps({"valid": not problems, "problems": problems}, indent=2))
        return 0 if not problems else 2

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
        redact_bodies=not args.keep_bodies,
        top_prospects_path=args.top_prospects,
        source_calls_path=args.source_calls,
        log_dates_path=args.log_call_dates,
        source_call_summary_path=args.source_call_summary,
    )
    print(json.dumps({
        "parsed": True,
        **payload["summary"],
        "bodies_redacted": not args.keep_bodies,
        "state_updated": bool(next_state),
        "written": written,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
