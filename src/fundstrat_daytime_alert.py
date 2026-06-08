#!/usr/bin/env python3
"""Classify compact Fundstrat updates and send only action-worthy daytime alerts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pushover_notify


ET = ZoneInfo("America/New_York")
DEFAULT_SRC = Path(__file__).resolve().parent
DEFAULT_CALLS = DEFAULT_SRC / "fundstrat_daily_calls.json"
DEFAULT_FEED = DEFAULT_SRC / "latest_cockpit_feed.json"
DEFAULT_STATE = DEFAULT_SRC / "fundstrat_daytime_alert_state.json"

ACTION_DIRECTIONS = {"buy", "add", "accumulate", "sell", "trim", "reduce", "avoid"}
DEFENSIVE_DIRECTIONS = {"sell", "trim", "reduce", "avoid"}
OPPORTUNITY_DIRECTIONS = {"buy", "add", "accumulate"}
TIME_SENSITIVE_TOKENS = {
    "today",
    "intraday",
    "this morning",
    "this afternoon",
    "now",
    "near-term",
    "short-term",
    "tactical",
    "breakout",
    "breakdown",
    "break above",
    "break below",
    "above",
    "below",
    "support",
    "resistance",
    "trigger",
    "stop",
    "target",
    "risk",
    "hedge",
}
MACRO_RISK_TOKENS = {
    "oil",
    "wti",
    "rates",
    "yield",
    "10-year",
    "volatility",
    "vix",
    "war",
    "middle east",
    "fed",
    "cpi",
    "crypto",
    "bitcoin",
}
FLUFF_TOKENS = {
    "webinar",
    "podcast",
    "replay",
    "survey",
    "registration",
    "register",
    "event invite",
    "join us",
    "subscribe",
    "promotion",
    "sponsored",
}


def _now_et(value: str | None = None) -> datetime:
    if value:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(ET) if parsed.tzinfo else parsed.replace(tzinfo=ET)
    return datetime.now(ET)


def _read_json(path: str | Path, default: Any) -> Any:
    path = Path(path)
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _atomic_write_json(path: str | Path, payload: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".fundstrat_alert.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _date_from_row(row: dict[str, Any]) -> str:
    return _text(row.get("date") or row.get("published_at"))[:10]


def _row_date(row: dict[str, Any]) -> datetime | None:
    date = _date_from_row(row)
    if not date:
        return None
    try:
        return datetime.fromisoformat(date).replace(tzinfo=ET)
    except ValueError:
        return None


def _fingerprint(row: dict[str, Any]) -> str:
    parts = [
        _date_from_row(row),
        _text(row.get("author")),
        _text(row.get("ticker")).upper(),
        _text(row.get("subject")),
        _text(row.get("quote")),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _contains_any(text: str, tokens: set[str]) -> list[str]:
    lowered = text.lower()
    return sorted(token for token in tokens if token in lowered)


def _has_numeric_level(text: str) -> bool:
    return any(char.isdigit() for char in text) and any(
        token in text.lower()
        for token in ("above", "below", "support", "resistance", "target", "stop", "$", "%", "level")
    )


def _load_held_tickers(feed: dict[str, Any]) -> set[str]:
    tickers: set[str] = set()
    candidates = []
    for key in ("positions", "portfolio", "book"):
        value = feed.get(key)
        if isinstance(value, dict):
            candidates.extend(value.get("rows") or value.get("positions") or value.get("items") or [])
        elif isinstance(value, list):
            candidates.extend(value)
    for row in candidates:
        if not isinstance(row, dict):
            continue
        ticker = _text(row.get("ticker") or row.get("symbol")).upper()
        if ticker:
            tickers.add(ticker)
    return tickers


def classify_call(
    row: dict[str, Any],
    *,
    now: datetime | str | None = None,
    held_tickers: set[str] | None = None,
    max_age_days: int = 1,
) -> dict[str, Any]:
    now = _now_et(now) if isinstance(now, str) or now is None else now.astimezone(ET)
    held_tickers = held_tickers or set()
    ticker = _text(row.get("ticker") or row.get("symbol")).upper()
    quote = _text(row.get("quote") or row.get("summary") or row.get("call"))
    subject = _text(row.get("subject") or row.get("source_title"))
    author = _text(row.get("author") or row.get("analyst") or "Fundstrat")
    direction = _text(row.get("direction") or row.get("bias")).lower()
    combined = f"{subject} {quote}"
    time_hits = _contains_any(combined, TIME_SENSITIVE_TOKENS)
    macro_hits = _contains_any(combined, MACRO_RISK_TOKENS)
    fluff_hits = _contains_any(combined, FLUFF_TOKENS)
    row_dt = _row_date(row)
    age_days = (now.date() - row_dt.date()).days if row_dt else None
    fresh_enough = age_days is None or age_days <= max_age_days

    score = 0
    if direction in DEFENSIVE_DIRECTIONS:
        score += 3
    elif direction in OPPORTUNITY_DIRECTIONS:
        score += 2
    if time_hits:
        score += min(2, len(time_hits))
    if macro_hits:
        score += 1
    if _has_numeric_level(combined):
        score += 1
    if ticker in held_tickers and direction in DEFENSIVE_DIRECTIONS:
        score += 1
    if fluff_hits:
        score -= 4
    if not fresh_enough:
        score -= 3

    if direction in DEFENSIVE_DIRECTIONS:
        posture = "trim/hedge/re-check"
    elif macro_hits and time_hits:
        posture = "hedge/re-check"
    elif direction in OPPORTUNITY_DIRECTIONS:
        posture = "re-check/size"
    elif time_hits:
        posture = "research/re-check"
    else:
        posture = "context"

    qualifies = fresh_enough and score >= 3 and not fluff_hits and bool(ticker or macro_hits)
    if not qualifies:
        reason = "context_only"
        if fluff_hits:
            reason = "fluff_or_low_value"
        elif not fresh_enough:
            reason = "not_fresh_enough_for_intraday_alert"
        elif score < 3:
            reason = "does_not_change_action_posture"
    else:
        reason = ""

    return {
        "fingerprint": _fingerprint(row),
        "qualifies": qualifies,
        "score": score,
        "reason": reason,
        "ticker": ticker,
        "author": author,
        "subject": subject,
        "quote": quote,
        "direction": direction,
        "date": _date_from_row(row),
        "age_days": age_days,
        "posture": posture,
        "why": _alert_why(direction=direction, time_hits=time_hits, macro_hits=macro_hits, held=ticker in held_tickers),
        "time_sensitive_terms": time_hits[:5],
        "macro_terms": macro_hits[:5],
        "held": ticker in held_tickers,
    }


def _alert_why(*, direction: str, time_hits: list[str], macro_hits: list[str], held: bool) -> str:
    if direction in DEFENSIVE_DIRECTIONS and held:
        return "Fundstrat flagged a defensive change on a held/exposed name; re-check before adding risk."
    if direction in DEFENSIVE_DIRECTIONS:
        return "Fundstrat flagged a defensive or avoid posture; check whether it affects current exposure or new-buy timing."
    if macro_hits and time_hits:
        return "Fundstrat content points to a fast-moving macro/tape issue that can change sizing, hedging, or timing."
    if direction in OPPORTUNITY_DIRECTIONS:
        return "Fundstrat flagged an opportunity; compare it against better current uses of capital before acting."
    return "Fundstrat item may change research priority or an existing action assumption."


def build_alert_report(
    calls: list[dict[str, Any]],
    *,
    feed: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
    now: str | datetime | None = None,
    max_age_days: int = 1,
) -> dict[str, Any]:
    now_dt = _now_et(now) if isinstance(now, str) or now is None else now.astimezone(ET)
    feed = feed if isinstance(feed, dict) else {}
    state = state if isinstance(state, dict) else {}
    alerted = set(state.get("alerted_fingerprints") or [])
    held_tickers = _load_held_tickers(feed)
    classified = [
        classify_call(row, now=now_dt, held_tickers=held_tickers, max_age_days=max_age_days)
        for row in calls
        if isinstance(row, dict)
    ]
    fresh_alerts = [
        row for row in classified
        if row.get("qualifies") and row.get("fingerprint") not in alerted
    ]
    duplicate_alerts = [
        row for row in classified
        if row.get("qualifies") and row.get("fingerprint") in alerted
    ]
    suppressed = [row for row in classified if not row.get("qualifies")]
    status = "notify" if fresh_alerts else "quiet"
    return {
        "schema_version": 1,
        "checked_at": now_dt.isoformat(),
        "status": status,
        "line": (
            f"Fundstrat daytime watch: {len(fresh_alerts)} new urgent/action-changing alert(s)."
            if fresh_alerts
            else "Fundstrat daytime watch: quiet - no new time-sensitive/action-changing Fundstrat item."
        ),
        "alerts": fresh_alerts[:5],
        "duplicates": duplicate_alerts[:5],
        "suppressed": suppressed[:12],
        "counts": {
            "calls_seen": len(calls),
            "alert_candidates": len(fresh_alerts),
            "duplicates": len(duplicate_alerts),
            "suppressed": len(suppressed),
        },
        "policy": (
            "Push only when a compact full-body-derived Fundstrat item changes act, wait, "
            "re-check, research, trim, hedge, or size posture. Fluff/context updates stay quiet."
        ),
    }


def build_push_message(report: dict[str, Any]) -> tuple[str, str]:
    alerts = [row for row in report.get("alerts") or [] if isinstance(row, dict)]
    title = f"Fundstrat intraday: {len(alerts)} action check"
    lines = [report.get("line") or title]
    for row in alerts[:3]:
        ticker = row.get("ticker") or "MARKET"
        lines.append(
            f"{ticker}: {row.get('posture')} - {row.get('quote') or row.get('subject')}"
        )
        if row.get("why"):
            lines.append(f"Why: {row.get('why')}")
        if row.get("date"):
            lines.append(f"Evidence date: {row.get('date')}")
    lines.append("Open the cockpit before acting; no trade is executed by this alert.")
    return title, "\n".join(lines)


def update_state_for_alerts(state: dict[str, Any] | None, report: dict[str, Any]) -> dict[str, Any]:
    state = state if isinstance(state, dict) else {}
    existing = list(state.get("alerted_fingerprints") or [])
    seen = set(existing)
    added: list[str] = []
    for row in report.get("alerts") or []:
        if not isinstance(row, dict):
            continue
        fingerprint = str(row.get("fingerprint") or "")
        if fingerprint and fingerprint not in seen:
            seen.add(fingerprint)
            added.append(fingerprint)
    return {
        "schema_version": 1,
        "updated_at": report.get("checked_at") or _now_et().isoformat(),
        "alerted_fingerprints": sorted(seen),
        "last_alert_count": len(report.get("alerts") or []),
        "last_added_fingerprints": added,
        "last_line": report.get("line") or "",
        "policy": report.get("policy") or "",
    }


def _format_text(report: dict[str, Any]) -> str:
    lines = [
        report.get("line") or "Fundstrat daytime watch",
        f"policy: {report.get('policy') or ''}",
        f"counts: {report.get('counts') or {}}",
    ]
    for row in report.get("alerts") or []:
        lines.append(f"- ALERT {row.get('ticker') or 'MARKET'}: {row.get('posture')} | {row.get('quote')}")
        lines.append(f"  why: {row.get('why')}")
    for row in report.get("suppressed") or []:
        lines.append(f"- quiet {row.get('ticker') or 'MARKET'}: {row.get('reason')}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate compact Fundstrat rows for urgent daytime Pushover alerts.")
    parser.add_argument("--calls", default=str(DEFAULT_CALLS))
    parser.add_argument("--feed", default=str(DEFAULT_FEED))
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument("--now")
    parser.add_argument("--max-age-days", type=int, default=1)
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write-state", action="store_true", help="Write duplicate-suppression state after a sent alert or dry-run.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    calls = _read_json(args.calls, [])
    calls = calls if isinstance(calls, list) else []
    feed = _read_json(args.feed, {})
    feed = feed if isinstance(feed, dict) else {}
    state = _read_json(args.state, {})
    state = state if isinstance(state, dict) else {}
    report = build_alert_report(
        calls,
        feed=feed,
        state=state,
        now=args.now,
        max_age_days=args.max_age_days,
    )
    send_report: dict[str, Any] | None = None
    if report["status"] == "notify" and args.send:
        title, message = build_push_message(report)
        send_report = pushover_notify.send_message(
            title=title,
            message=message,
            priority=1,
            dry_run=args.dry_run,
        )
        report["delivery"] = send_report
        if send_report.get("sent") or (args.dry_run and args.write_state):
            new_state = update_state_for_alerts(state, report)
            _atomic_write_json(args.state, new_state)
            report["state_written"] = True
        else:
            report["state_written"] = False
    else:
        report["delivery"] = {"sent": False, "dry_run": args.dry_run, "reason": "quiet or --send not requested"}
        report["state_written"] = False

    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_format_text(report))
    if send_report and not (send_report.get("sent") or send_report.get("dry_run")):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
