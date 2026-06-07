#!/usr/bin/env python3
"""Watch-only social/Reddit anomaly surface.

This module does not fetch Reddit. It normalizes a repo convention cache into a
dashboard block that can be populated later by an OAuth/API intake routine.
Social rows are early-signal context only and never promote trades by themselves.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reddit_signal_core import detect_signal


def _parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _iso(value: Any) -> str:
    parsed = _parse_dt(value)
    return parsed.isoformat() if parsed else str(value or "")


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [value]


def _text_list(value: Any, *, upper: bool = False, limit: int | None = None) -> list[str]:
    rows = []
    for item in _as_list(value):
        text = str(item or "").strip()
        if text:
            rows.append(text.upper() if upper else text)
    if limit is not None:
        rows = rows[:limit]
    return rows


def _candidate_rows(cache: Any) -> list[dict[str, Any]]:
    if isinstance(cache, list):
        return [row for row in cache if isinstance(row, dict)]
    if not isinstance(cache, dict):
        return []
    for key in ("rows", "items", "signals", "anomalies", "reddit_items"):
        rows = cache.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _velocity(row: dict[str, Any]) -> dict[str, Any]:
    series = row.get("mention_series") or row.get("mentions_series") or row.get("series")
    if isinstance(series, list):
        try:
            return detect_signal([int(float(v)) for v in series])
        except (TypeError, ValueError):
            return {}
    z = row.get("velocity_z") or row.get("zscore") or row.get("mention_zscore")
    current = row.get("mentions") or row.get("current_mentions") or row.get("mention_count")
    fired = bool(row.get("fired") or row.get("eligible"))
    return {
        "current": current,
        "zscore": z,
        "eligible": bool(current or fired),
        "fired": fired,
    }


def _summary(row: dict[str, Any]) -> str:
    for key in ("summary", "thesis", "claim", "title_snippet", "title"):
        text = str(row.get(key) or "").strip()
        if text:
            return text[:280]
    body = str(row.get("body_snippet") or row.get("body") or "").strip()
    return body[:280]


def _independent_confirmation(row: dict[str, Any]) -> list[str]:
    confirmations = (
        row.get("independent_confirmation")
        or row.get("confirmations")
        or row.get("confirmed_by")
        or []
    )
    return _text_list(confirmations, limit=6)


def _risk_note(row: dict[str, Any], confirmations: list[str]) -> str:
    explicit = str(row.get("risk") or row.get("risk_note") or "").strip()
    if explicit:
        return explicit
    if confirmations:
        return "Still watch-only; confirmation must come from non-social evidence before any action lane."
    return "Pump/chase and echo risk; treat as a lead to vet, not a trade signal."


def _escalation(row: dict[str, Any], ticker: str, confirmations: list[str], material_tickers: set[str]) -> str:
    requested = str(row.get("escalation") or row.get("route") or "").strip()
    if requested:
        return requested
    if confirmations and ticker and ticker in material_tickers:
        return "Re-check Before Acting candidate"
    if confirmations:
        return "Research Queue candidate"
    return "Quiet Watch"


def _score(row: dict[str, Any], velocity: dict[str, Any]) -> float:
    explicit = row.get("score")
    try:
        if explicit is not None:
            return round(float(explicit), 2)
    except (TypeError, ValueError):
        pass
    z = velocity.get("zscore")
    current = velocity.get("current")
    try:
        z_part = max(float(z or 0.0), 0.0) * 10.0
    except (TypeError, ValueError):
        z_part = 0.0
    try:
        count_part = min(float(current or 0.0), 100.0) / 5.0
    except (TypeError, ValueError):
        count_part = 0.0
    return round(z_part + count_part, 2)


def normalize_social_watch_row(row: dict[str, Any], *, material_tickers: set[str] | None = None) -> dict[str, Any]:
    material = material_tickers or set()
    tickers = _text_list(row.get("tickers") or row.get("ticker"), upper=True, limit=8)
    ticker = tickers[0] if tickers else ""
    confirmations = _independent_confirmation(row)
    velocity = _velocity(row)
    subreddits = _text_list(row.get("subreddits") or row.get("subreddit"), limit=8)
    evidence = _text_list(
        row.get("evidence")
        or row.get("snippets")
        or row.get("matched_terms")
        or row.get("terms"),
        limit=5,
    )
    first_seen = _iso(row.get("first_seen") or row.get("created_utc") or row.get("created_at"))
    last_seen = _iso(row.get("last_seen") or row.get("ingested_at") or row.get("updated_at") or first_seen)
    return {
        "ticker": ticker,
        "tickers": tickers,
        "entity": str(row.get("entity") or row.get("entities") or "").strip(),
        "source": str(row.get("source") or "reddit").strip(),
        "subreddits": subreddits,
        "first_seen": first_seen,
        "last_seen": last_seen,
        "mentions": velocity.get("current") or row.get("mentions") or row.get("mention_count") or "",
        "velocity_z": velocity.get("zscore"),
        "eligible": bool(velocity.get("eligible")),
        "fired": bool(velocity.get("fired")),
        "score": _score(row, velocity),
        "summary": _summary(row),
        "evidence": evidence,
        "independent_confirmation": confirmations,
        "escalation": _escalation(row, ticker, confirmations, material),
        "risk": _risk_note(row, confirmations),
        "confirmation_required": (
            "Needs non-social confirmation from UW, price/news, Fundstrat, catalyst, or source-call evidence."
        ),
        "permalink": str(row.get("permalink") or row.get("url") or "").strip(),
    }


def build_social_watch(
    cache: Any,
    *,
    material_tickers: set[str] | None = None,
) -> dict[str, Any]:
    if cache is None:
        return {
            "status": "not_checked",
            "line": "Social watch not checked: no Reddit/social cache supplied.",
            "rows": [],
            "count": 0,
            "honesty_rule": "Watch-only until independently confirmed; never a standalone trade signal.",
            "command": "python src/social_watch.py --cache src/social_watch.json --format text",
        }
    rows = [
        normalize_social_watch_row(row, material_tickers=material_tickers)
        for row in _candidate_rows(cache)
    ]
    rows = [row for row in rows if row.get("summary") or row.get("ticker") or row.get("entity")]
    rows.sort(key=lambda row: (float(row.get("score") or 0.0), str(row.get("last_seen") or "")), reverse=True)
    generated_at = ""
    if isinstance(cache, dict):
        generated_at = _iso(cache.get("generated_at") or cache.get("checked_at") or cache.get("ingested_at"))
    status = "has_data" if rows else "checked_clear"
    line = (
        f"Social watch: {len(rows)} anomaly candidate(s); watch-only until independently confirmed."
        if rows
        else "Social watch checked clear: no eligible social anomalies in the supplied cache."
    )
    return {
        "status": status,
        "line": line,
        "generated_at": generated_at,
        "count": len(rows),
        "rows": rows[:12],
        "top": rows[:3],
        "honesty_rule": "Watch-only until independently confirmed; never a standalone trade signal.",
        "promotion_rule": (
            "Key Now is allowed only when Reddit is not primary evidence and same-day UW, price/news, "
            "Fundstrat, catalyst, or source-call evidence confirms the setup."
        ),
        "command": "python src/social_watch.py --cache src/social_watch.json --format text",
    }


def _format_text(block: dict[str, Any]) -> str:
    lines = [block.get("line") or "Social watch"]
    if block.get("honesty_rule"):
        lines.append(f"honesty: {block['honesty_rule']}")
    if block.get("promotion_rule"):
        lines.append(f"promotion: {block['promotion_rule']}")
    for row in block.get("rows") or []:
        label = row.get("ticker") or row.get("entity") or "SOCIAL"
        subs = ", ".join(row.get("subreddits") or [])
        evidence = "; ".join(row.get("evidence") or [])
        confirm = "; ".join(row.get("independent_confirmation") or [])
        lines.append(f"- {label}: score {row.get('score')} | {row.get('escalation')} | {row.get('summary')}")
        if subs:
            lines.append(f"  subreddits: {subs}")
        if evidence:
            lines.append(f"  evidence: {evidence}")
        if confirm:
            lines.append(f"  independent confirmation: {confirm}")
        lines.append(f"  risk: {row.get('risk')}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize a social/Reddit watch cache.")
    parser.add_argument("--cache", default=str(Path(__file__).resolve().parent / "social_watch.json"))
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    path = Path(args.cache)
    cache = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    block = build_social_watch(cache)
    if args.format == "json":
        print(json.dumps(block, indent=2, sort_keys=True))
    else:
        print(_format_text(block))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
