#!/usr/bin/env python3
"""Normalize federal funding move scans into Investing OS source caches.

The federal funding monitor is source-intake only. It stores compact award rows
and derives watch/research rows through existing Signal Log and Research Queue
contracts. It does not create trades, sizes, or direct buy/sell calls.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import research_queue_intake
import signal_log_intake


SRC = Path(__file__).resolve().parent
DEFAULT_OUT = SRC / "federal_funding_moves.json"
DEFAULT_SUMMARY = SRC / "federal_funding_intake_summary.json"
DEFAULT_SIGNAL_LOG_OUT = SRC / "signal_log.json"
DEFAULT_RESEARCH_OUT = SRC / "research_queue.json"
DEFAULT_THESES = SRC / "theses.json"

PRIORITIES = {"high", "medium", "low"}
DIRECTNESS_VALUES = {
    "direct_public",
    "public_read_through",
    "private_read_through",
    "contract_backlog",
    "watch_only",
    "ignore",
}
RESEARCH_ACTIONABILITY = {"review_now", "research_review", "urgent_review"}
WATCH_ACTIONABILITY = {"watch", "monitor", "ignore", "research_review", "review_now", "urgent_review"}
MONITOR_TICKERS = {"BMNR", "LEU", "UUUU", "MP"}

DATE_ALIASES = ("date", "as_of", "announced_at", "published_at", "created_at")
AGENCY_ALIASES = ("agency", "department", "source_agency", "office")
PROGRAM_ALIASES = ("program", "funding_program", "office", "award_program")
RECIPIENT_ALIASES = ("recipient", "awardee", "company", "entity", "name")
DETAIL_ALIASES = ("award_details", "award_detail", "award_text", "award", "funding", "amount", "value")
TICKER_ALIASES = ("ticker", "tickers", "symbol", "symbols", "public_ticker", "public_tickers")
ANGLE_ALIASES = ("trade_angle", "investor_trade_angle", "investing_angle", "angle", "so_what")
TRIGGER_ALIASES = ("next_trigger", "trigger", "watch_for", "next_evidence")
RISK_ALIASES = ("risks", "risk", "risk_checklist", "blockers")
SOURCE_URL_ALIASES = ("source_urls", "source_url", "urls", "url", "links", "link")
TITLE_ALIASES = ("title", "headline", "signal", "summary")

MONEY_RE = re.compile(
    r"\$?\s*([0-9]+(?:\.[0-9]+)?)\s*"
    r"(billion|bn|b|million|mn|m|thousand|k)?",
    re.IGNORECASE,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.is_file():
        return default
    with p.open(encoding="utf-8-sig") as fh:
        return json.load(fh)


def _atomic_write_json(path: str | Path, payload: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".federal_funding.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def _first(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for key in keys:
        if key in row and row[key] not in (None, "", [], {}):
            return row[key]
        value = lowered.get(key.lower())
        if value not in (None, "", [], {}):
            return value
    return None


def _text(value: Any) -> str:
    return str(value).strip() if value not in (None, "", [], {}) else ""


def _string_list(value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, dict):
        value = value.get("name") or value.get("text") or value.get("plain_text") or ""
    if isinstance(value, str):
        text = value.replace("\n", ",").replace(";", ",").replace("|", ",")
        parts = []
        for chunk in text.split(","):
            chunk = chunk.strip().strip("*")
            if chunk:
                parts.append(chunk)
        return parts
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            out.extend(_string_list(item))
        return out
    return [str(value).strip()]


def _ticker_list(value: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in _string_list(value):
        cleaned = (
            raw.replace("read-through to", "")
            .replace("read through to", "")
            .replace("No direct ticker", "")
            .replace("public ticker(s)", "")
            .strip(" :*-")
        )
        for token in re.split(r"\s+|/", cleaned):
            token = token.strip("()[]{}.,;:*").upper()
            if not token or token in {"TO", "AS", "BACKER", "PRIVATE", "READ", "THROUGH"}:
                continue
            if ":" in token:
                token = token.replace(":", ":")
            if len(token.replace(".", "").replace(":", "")) > 12:
                continue
            if not re.match(r"^[A-Z][A-Z0-9.:-]{0,11}$", token):
                continue
            if token not in seen:
                seen.add(token)
                out.append(token)
    return out


def _source_urls(value: Any) -> list[str]:
    urls: list[str] = []
    for raw in _string_list(value):
        if isinstance(raw, str):
            urls.extend(re.findall(r"https?://[^\s)\]]+", raw))
            if raw.startswith("http://") or raw.startswith("https://"):
                urls.append(raw)
    out: list[str] = []
    seen: set[str] = set()
    for url in urls:
        clean = url.rstrip(".,")
        if clean and clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def parse_award_value_usd(value: Any) -> int | None:
    """Best-effort parse of compact award strings such as '$725M'."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "")
    if not text or "not disclosed" in text.lower():
        return None
    match = MONEY_RE.search(text.replace(",", ""))
    if not match:
        return None
    number = float(match.group(1))
    unit = (match.group(2) or "").lower()
    multiplier = 1
    if unit in {"billion", "bn", "b"}:
        multiplier = 1_000_000_000
    elif unit in {"million", "mn", "m"}:
        multiplier = 1_000_000
    elif unit in {"thousand", "k"}:
        multiplier = 1_000
    return int(number * multiplier)


def _priority(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("low-medium", "medium").replace("low-medium", "medium")
    text = text.replace("low/medium", "medium").replace("low-medium", "medium")
    if "high" in text:
        return "high"
    if "medium" in text or "med" in text:
        return "medium"
    if "low" in text:
        return "low"
    return "medium"


def _directness(value: Any, *, tickers: list[str], recipient: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "direct": "direct_public",
        "public_direct": "direct_public",
        "public": "direct_public",
        "private": "private_read_through",
        "read_through": "private_read_through",
        "contract": "contract_backlog",
        "backlog": "contract_backlog",
        "watch": "watch_only",
    }
    directness = aliases.get(text, text)
    if directness in DIRECTNESS_VALUES:
        return directness
    if tickers and recipient and "private" not in recipient.lower():
        return "direct_public"
    if tickers:
        return "public_read_through"
    return "watch_only"


def _actionability(value: Any, *, directness: str, priority: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if text in WATCH_ACTIONABILITY:
        return text
    if directness == "direct_public" and priority == "high":
        return "research_review"
    if directness == "direct_public" and priority == "medium":
        return "research_review"
    return "watch"


def _rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("federal_funding_moves", "funding_moves", "moves", "watchlist", "rows", "items", "results", "data"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return [payload] if any(payload.get(key) for key in (*RECIPIENT_ALIASES, *TITLE_ALIASES)) else []


def _payload_default(payloads: list[Any], key: str, fallback: str = "") -> str:
    for payload in payloads:
        if isinstance(payload, dict) and payload.get(key) not in (None, ""):
            return str(payload[key]).strip()
    return fallback


def normalize_funding_row(row: dict[str, Any], *, default_date: str = "") -> dict[str, Any] | None:
    title = _text(_first(row, TITLE_ALIASES))
    recipient = _text(_first(row, RECIPIENT_ALIASES))
    agency = _text(_first(row, AGENCY_ALIASES))
    award_text = _text(_first(row, DETAIL_ALIASES))
    if not (title or recipient or award_text):
        return None
    tickers = _ticker_list(_first(row, TICKER_ALIASES))
    priority = _priority(row.get("priority") or row.get("rank") or row.get("urgency"))
    directness = _directness(row.get("directness") or row.get("market_exposure"), tickers=tickers, recipient=recipient)
    actionability = _actionability(row.get("actionability") or row.get("route"), directness=directness, priority=priority)
    source_urls = _source_urls(_first(row, SOURCE_URL_ALIASES))
    risks = _string_list(_first(row, RISK_ALIASES))
    program = _text(_first(row, PROGRAM_ALIASES))
    date_text = _text(_first(row, DATE_ALIASES) or default_date)[:10]
    out: dict[str, Any] = {
        "date": date_text or default_date,
        "priority": priority,
        "agency": agency or "Federal funding source",
        "program": program,
        "recipient": recipient or title,
        "title": title or recipient or award_text,
        "award_text": award_text or title,
        "award_value_usd": parse_award_value_usd(row.get("award_value_usd") or award_text),
        "tickers": tickers,
        "directness": directness,
        "actionability": actionability,
        "investing_angle": _text(_first(row, ANGLE_ALIASES)),
        "risks": risks,
        "next_trigger": _text(_first(row, TRIGGER_ALIASES)),
        "source_urls": source_urls,
        "source_quality": _text(row.get("source_quality") or row.get("source_type") or "primary_or_verified"),
    }
    notes = _text(row.get("notes") or row.get("note"))
    if notes:
        out["notes"] = notes
    return out


def normalize_funding_payload(payloads: list[Any], *, as_of: str | None = None, generated_at: str | None = None) -> dict[str, Any]:
    as_of = as_of or _payload_default(payloads, "as_of", date.today().isoformat())[:10]
    generated_at = generated_at or _payload_default(payloads, "generated_at", _utc_now_iso())
    rows: list[dict[str, Any]] = []
    for payload in payloads:
        for raw in _rows_from_payload(payload):
            normalized = normalize_funding_row(raw, default_date=as_of)
            if normalized:
                rows.append(normalized)
    rows = _dedupe_rows(rows)
    rows.sort(key=lambda row: ({"high": 0, "medium": 1, "low": 2}.get(row.get("priority"), 9), row.get("date") or "", row.get("recipient") or ""))
    return {
        "schema_version": 1,
        "source": "federal_funding_intake",
        "generated_at": generated_at,
        "as_of": as_of,
        "scan_status": "has_data" if rows else "checked_clear",
        "rows": rows,
        "summary": _summary(rows),
    }


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in rows:
        key = (
            str(row.get("date") or ""),
            str(row.get("agency") or "").lower(),
            str(row.get("recipient") or "").lower(),
            str(row.get("award_text") or "").lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _merge_cache(existing: dict[str, Any] | None, new: dict[str, Any]) -> dict[str, Any]:
    existing_rows = []
    if isinstance(existing, dict) and isinstance(existing.get("rows"), list):
        existing_rows = [row for row in existing["rows"] if isinstance(row, dict)]
    rows = _dedupe_rows([*existing_rows, *(new.get("rows") or [])])
    rows.sort(key=lambda row: ({"high": 0, "medium": 1, "low": 2}.get(row.get("priority"), 9), row.get("date") or "", row.get("recipient") or ""))
    return {
        **new,
        "scan_status": "has_data" if rows else new.get("scan_status") or "checked_clear",
        "rows": rows,
        "summary": {**_summary(rows), "merged": bool(existing_rows)},
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    direct_public = sum(1 for row in rows if row.get("directness") == "direct_public")
    high = sum(1 for row in rows if row.get("priority") == "high")
    research_candidates = sum(1 for row in rows if row.get("actionability") in RESEARCH_ACTIONABILITY)
    top_signal = ""
    if rows:
        top = rows[0]
        top_signal = f"{top.get('recipient')}: {top.get('award_text') or top.get('title')}"
    return {
        "stored": len(rows),
        "high": high,
        "direct_public": direct_public,
        "research_candidates": research_candidates,
        "top_signal": top_signal,
    }


def validate_funding_cache(cache: Any) -> list[str]:
    if not isinstance(cache, dict):
        return ["top-level must be an object"]
    problems: list[str] = []
    if cache.get("schema_version") != 1:
        problems.append("schema_version must be 1")
    rows = cache.get("rows")
    if not isinstance(rows, list):
        return problems + ["rows must be a list"]
    for idx, row in enumerate(rows):
        label = f"rows[{idx}]"
        if not isinstance(row, dict):
            problems.append(f"{label} must be an object")
            continue
        for field in ("date", "agency", "recipient", "award_text", "priority", "directness", "actionability"):
            if not isinstance(row.get(field), str) or not row.get(field, "").strip():
                problems.append(f"{label}.{field} must be a non-empty string")
        if row.get("priority") not in PRIORITIES:
            problems.append(f"{label}.priority must be one of {sorted(PRIORITIES)}")
        if row.get("directness") not in DIRECTNESS_VALUES:
            problems.append(f"{label}.directness must be one of {sorted(DIRECTNESS_VALUES)}")
        if row.get("directness") == "direct_public" and not row.get("tickers"):
            problems.append(f"{label}.tickers must include at least one ticker for direct_public rows")
        for field in ("tickers", "risks", "source_urls"):
            if field in row and not isinstance(row.get(field), list):
                problems.append(f"{label}.{field} must be a list")
        if row.get("award_value_usd") is not None and not isinstance(row.get("award_value_usd"), int):
            problems.append(f"{label}.award_value_usd must be an integer when present")
    return problems


def _theses_by_ticker(path: str | Path) -> dict[str, dict[str, Any]]:
    payload = _read_json(path, default=[])
    if not isinstance(payload, list):
        return {}
    return {
        str(row.get("ticker") or "").strip().upper(): row
        for row in payload
        if isinstance(row, dict) and row.get("ticker")
    }


def _is_monitor_ticker(ticker: str, theses: dict[str, dict[str, Any]]) -> bool:
    tk = ticker.strip().upper()
    thesis = theses.get(tk) or {}
    return tk in MONITOR_TICKERS or str(thesis.get("stance") or "").upper() == "MONITOR"


def _primary_ticker(row: dict[str, Any]) -> str:
    for ticker in row.get("tickers") or []:
        if ":" not in ticker and ticker.isascii():
            return ticker
    return (row.get("tickers") or [""])[0]


def build_signal_rows(cache: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in cache.get("rows") or []:
        if (
            not isinstance(row, dict)
            or row.get("directness") == "ignore"
            or row.get("actionability") == "ignore"
        ):
            continue
        ticker = _primary_ticker(row)
        award = row.get("award_text") or row.get("title") or "federal funding move"
        recipient = row.get("recipient") or row.get("title") or "recipient"
        risks = "; ".join(row.get("risks") or [])
        trigger = row.get("next_trigger") or ""
        note_parts = [
            f"{row.get('directness')} / {row.get('actionability')}",
            str(row.get("investing_angle") or ""),
            f"Risks: {risks}" if risks else "",
            f"Next: {trigger}" if trigger else "",
        ]
        source_bits = row.get("source_urls") or [row.get("agency") or "Federal funding monitor"]
        signal = f"Federal funding: {recipient} - {award}"
        out = {
            "signal": signal[:220],
            "date": row.get("date") or cache.get("as_of") or "",
            "priority": row.get("priority") or "medium",
            "source": "; ".join(source_bits),
            "note": " | ".join(part for part in note_parts if part),
        }
        if ticker:
            out["ticker"] = ticker
        rows.append(out)
    return rows


def build_research_rows(cache: dict[str, Any], *, theses_path: str | Path = DEFAULT_THESES) -> list[dict[str, Any]]:
    theses = _theses_by_ticker(theses_path)
    rows: list[dict[str, Any]] = []
    for row in cache.get("rows") or []:
        if not isinstance(row, dict):
            continue
        if row.get("actionability") not in RESEARCH_ACTIONABILITY:
            continue
        ticker = _primary_ticker(row)
        if not ticker or ":" in ticker:
            continue
        monitor = _is_monitor_ticker(ticker, theses)
        award = row.get("award_text") or row.get("title") or "federal funding move"
        recipient = row.get("recipient") or ticker
        risks = "; ".join(row.get("risks") or [])
        trigger = row.get("next_trigger") or "fresh price reaction, source confirmation, and execution-risk check"
        notes = (
            f"{recipient}: {award}. Agency/program: {row.get('agency')}"
            + (f" / {row.get('program')}" if row.get("program") else "")
            + f". Check materiality, tape reaction, dilution/funding terms, execution risk, and whether this changes current hold/research posture. Missing evidence: {trigger}."
            + (f" Risks: {risks}." if risks else "")
        )
        if monitor:
            notes += " MONITOR sleeve guardrail: no add path unless a defined-risk re-entry trigger is separately confirmed."
        out = {
            "ticker": ticker,
            "r": f"{ticker} - federal funding catalyst review: {recipient} ({award})",
            "pr": "high" if row.get("priority") == "high" else "med",
            "status": "Working",
            "source": "federal_funding_monitor",
            "notes": notes,
        }
        if row.get("actionability") in {"review_now", "urgent_review"} and not monitor:
            out["urgency"] = "today"
        rows.append(out)
    return rows


def _write_signal_log(rows: list[dict[str, Any]], *, out: str | Path, merge_existing: bool) -> dict[str, Any]:
    if not rows:
        return {"written": False, "rows": 0, "reason": "no derived signal rows"}
    existing = signal_log_intake.normalize_signal_log([_read_json(out, default=[])]) if merge_existing and Path(out).is_file() else []
    normalized = signal_log_intake.normalize_signal_log([{"signals": rows}])
    merged = signal_log_intake.merge_rows(existing, normalized) if existing else normalized
    problems = signal_log_intake.validate_signal_log(merged)
    if problems:
        return {"written": False, "rows": len(normalized), "problems": problems}
    signal_log_intake._atomic_write_json(out, merged)
    return {"written": True, "rows": len(normalized), "stored": len(merged)}


def _write_research_queue(rows: list[dict[str, Any]], *, out: str | Path, merge_existing: bool, as_of: str | None, generated_at: str | None) -> dict[str, Any]:
    if not rows:
        return {"written": False, "rows": 0, "reason": "no derived research rows"}
    queue = research_queue_intake.build_research_queue(rows, as_of=as_of, generated_at=generated_at)
    if merge_existing:
        queue = research_queue_intake.merge_queues(_read_json(out, default={}), queue)
    problems = research_queue_intake.validate_research_queue(queue)
    if problems:
        return {"written": False, "rows": len(rows), "problems": problems}
    _atomic_write_json(out, queue)
    return {
        "written": True,
        "rows": len(rows),
        "pending": len(queue.get("pending") or []),
        "done": len(queue.get("done") or []),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Normalize federal funding move scan rows")
    parser.add_argument("inputs", nargs="*", help="Federal funding move JSON files")
    parser.add_argument("--stdin-json", action="store_true")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--signal-log-out", default=str(DEFAULT_SIGNAL_LOG_OUT))
    parser.add_argument("--research-out", default=str(DEFAULT_RESEARCH_OUT))
    parser.add_argument("--theses", default=str(DEFAULT_THESES))
    parser.add_argument("--as-of")
    parser.add_argument("--generated-at")
    parser.add_argument("--merge-existing", action="store_true")
    parser.add_argument("--no-derived", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--validate", metavar="FEDERAL_FUNDING_JSON")
    args = parser.parse_args(argv)

    if args.validate:
        cache = _read_json(args.validate, default={})
        problems = validate_funding_cache(cache)
        print(json.dumps({"valid": not problems, "problems": problems, "rows": len(cache.get("rows") or []) if isinstance(cache, dict) else 0}, indent=2))
        return 0 if not problems else 2

    if not args.inputs and not args.stdin_json:
        parser.error("provide at least one JSON input or --stdin-json")

    payloads = [_read_json(path) for path in args.inputs]
    if args.stdin_json:
        payloads.append(json.load(sys.stdin))
    cache = normalize_funding_payload(payloads, as_of=args.as_of, generated_at=args.generated_at)
    if args.merge_existing and Path(args.out).is_file():
        cache = _merge_cache(_read_json(args.out, default={}), cache)
    problems = validate_funding_cache(cache)
    signal_report = {"written": False, "reason": "not run"}
    research_report = {"written": False, "reason": "not run"}
    if not problems and not args.no_derived:
        signal_report = _write_signal_log(
            build_signal_rows(cache),
            out=args.signal_log_out,
            merge_existing=args.merge_existing,
        ) if not args.dry_run else {"written": None, "dry_run": True, "rows": len(build_signal_rows(cache))}
        research_report = _write_research_queue(
            build_research_rows(cache, theses_path=args.theses),
            out=args.research_out,
            merge_existing=args.merge_existing,
            as_of=cache.get("as_of"),
            generated_at=cache.get("generated_at"),
        ) if not args.dry_run else {"written": None, "dry_run": True, "rows": len(build_research_rows(cache, theses_path=args.theses))}

    report = {
        "valid": not problems,
        "problems": problems,
        "written": False,
        "out": args.out,
        "rows": len(cache.get("rows") or []),
        "signal_log": signal_report,
        "research_queue": research_report,
    }
    if problems:
        _atomic_write_json(args.summary, report)
        print(json.dumps(report, indent=2))
        return 2
    if not args.dry_run:
        _atomic_write_json(args.out, cache)
        report["written"] = True
        _atomic_write_json(args.summary, report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
