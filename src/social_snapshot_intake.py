#!/usr/bin/env python3
"""Normalize supplied Reddit/UW-news/social snapshots into social_watch.json.

This is a bridge, not a fetcher. OAuth/API/connector reads happen upstream and
hand this module compact rows. The output is the convention cache consumed by
social_watch.py and full_build_runner.py.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TRUMP_TRADE_SUBREDDITS = {"trumpstrades"}
TRUMP_SOCIAL_SOURCES = {"truth_social", "trump_truth", "uw_news_truth_social"}
ENTITY_TICKER_ALIASES = {
    "MICRON": "MU",
    "MICRON TECHNOLOGY": "MU",
    "NVIDIA": "NVDA",
    "BROADCOM": "AVGO",
    "PALANTIR": "PLTR",
    "TESLA": "TSLA",
}
TICKER_STOPWORDS = {
    "A", "AI", "AM", "AND", "ANY", "ARE", "AS", "AT", "BE", "BIG", "CEO",
    "DO", "FOR", "GET", "GO", "HAS", "HOT", "I", "IN", "IS", "IT", "MY",
    "NO", "OF", "ON", "OR", "OUR", "REAL", "THE", "THIS", "TO", "US",
    "USA", "WE",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


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
        text = _text(item)
        if text:
            rows.append(text.upper() if upper else text)
    return rows[:limit] if limit is not None else rows


def _candidate_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("items", "rows", "posts", "signals", "news", "headlines"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _iso(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.isoformat()
    except ValueError:
        return text


def _summary(row: dict[str, Any]) -> str:
    for key in ("summary", "title", "headline", "text", "body", "content"):
        text = _text(row.get(key))
        if text:
            return text[:280]
    return ""


def _body_text(row: dict[str, Any]) -> str:
    return " ".join(
        _text(row.get(key))
        for key in ("title", "headline", "summary", "body", "selftext", "text", "content")
        if _text(row.get(key))
    )


def _extract_tickers(row: dict[str, Any]) -> list[str]:
    explicit = _text_list(row.get("tickers") or row.get("ticker") or row.get("symbols"), upper=True, limit=8)
    if explicit:
        return explicit
    text = _body_text(row)
    found: list[str] = []
    seen: set[str] = set()
    upper_text = text.upper()
    for alias, ticker in ENTITY_TICKER_ALIASES.items():
        if alias in upper_text and ticker not in seen:
            seen.add(ticker)
            found.append(ticker)
    for token in re.findall(r"(?:\$)?\b[A-Z]{1,5}\b", text):
        ticker = token.replace("$", "").upper()
        if ticker in TICKER_STOPWORDS or ticker in seen:
            continue
        seen.add(ticker)
        found.append(ticker)
    return found[:8]


def _source(row: dict[str, Any]) -> str:
    source = _text(row.get("source") or row.get("platform"))
    if source:
        return source
    if _text(row.get("subreddit")):
        return "reddit"
    if row.get("is_trump_ts") or row.get("truth_social"):
        return "uw_news_truth_social"
    return "social_snapshot"


def _source_group(row: dict[str, Any], source: str, subreddits: list[str]) -> str:
    lowered_subs = {sub.lower().lstrip("r/") for sub in subreddits}
    lowered_source = source.lower()
    if lowered_subs & TRUMP_TRADE_SUBREDDITS:
        return "trump_trade_watch"
    if lowered_source in TRUMP_SOCIAL_SOURCES or row.get("is_trump_ts") or row.get("truth_social"):
        return "trump_trade_watch"
    return _text(row.get("source_group") or "social_watch")


def normalize_snapshot_row(row: dict[str, Any]) -> dict[str, Any]:
    source = _source(row)
    subreddits = _text_list(row.get("subreddits") or row.get("subreddit"), limit=8)
    tickers = _extract_tickers(row)
    summary = _summary(row)
    body = _text(row.get("body") or row.get("selftext") or row.get("text") or row.get("content"))
    title = _text(row.get("title") or row.get("headline"))
    evidence = _text_list(row.get("evidence") or row.get("snippets"), limit=5)
    if title and title not in evidence:
        evidence.insert(0, title[:180])
    if body and body not in evidence:
        evidence.append(body[:180])
    created = _iso(row.get("created_at") or row.get("created_utc") or row.get("published_at"))
    ingested = _iso(row.get("ingested_at") or row.get("checked_at")) or datetime.now(timezone.utc).isoformat()
    return {
        "id": _text(row.get("id") or row.get("post_id") or row.get("url") or row.get("permalink")),
        "source": source,
        "source_group": _source_group(row, source, subreddits),
        "subreddit": subreddits[0] if subreddits else "",
        "subreddits": subreddits,
        "ticker": tickers[0] if tickers else "",
        "tickers": tickers,
        "entity": _text(row.get("entity") or row.get("author") or row.get("account")),
        "created_at": created,
        "ingested_at": ingested,
        "last_seen": ingested,
        "summary": summary,
        "title_snippet": title[:180],
        "body_snippet": body[:240],
        "evidence": evidence[:5],
        "mentions": row.get("mentions") or row.get("score") or row.get("ups") or "",
        "score": row.get("social_score") or row.get("score") or "",
        "independent_confirmation": _text_list(row.get("independent_confirmation") or row.get("confirmed_by"), limit=6),
        "risk": _text(row.get("risk") or "Watch-only social/Trump snapshot; confirm outside social before any capital action."),
        "permalink": _text(row.get("permalink") or row.get("url")),
    }


def build_social_snapshot_cache(
    payload: Any,
    *,
    generated_at: str | None = None,
    source: str = "social_snapshot_intake",
) -> dict[str, Any]:
    rows = []
    for row in _candidate_rows(payload):
        normalized = normalize_snapshot_row(row)
        if normalized.get("summary") or normalized.get("ticker") or normalized.get("entity"):
            rows.append(normalized)
    return {
        "schema_version": 1,
        "source": source,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "items": rows,
        "count": len(rows),
        "honesty_rule": "Snapshot bridge only; social rows remain watch-only until independently confirmed.",
    }


def write_cache(path: str | Path, cache: dict[str, Any]) -> Path:
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(cache, indent=2, sort_keys=False), encoding="utf-8")
    tmp.replace(path)
    return path


def _format_text(cache: dict[str, Any]) -> str:
    lines = [
        f"Social snapshot intake: {cache.get('count') or 0} row(s) normalized.",
        str(cache.get("honesty_rule") or ""),
    ]
    for row in cache.get("items") or []:
        label = row.get("ticker") or row.get("entity") or "SOCIAL"
        subs = ", ".join(row.get("subreddits") or [])
        lines.append(f"- {label}: {row.get('source_group')} | {row.get('summary')}")
        if subs:
            lines.append(f"  subreddits: {subs}")
        if row.get("evidence"):
            lines.append(f"  evidence: {'; '.join(row.get('evidence') or [])}")
    return "\n".join(line for line in lines if line)


def _self_test() -> int:
    sample = {
        "items": [
            {
                "source": "reddit",
                "subreddit": "TrumpsTrades",
                "title": "Trump + MU",
                "body": "Micron announced a Trump Accounts investment.",
                "url": "https://reddit.example/post",
            }
        ]
    }
    cache = build_social_snapshot_cache(sample, generated_at="2026-07-01T12:00:00Z")
    row = cache["items"][0]
    assert cache["count"] == 1
    assert row["ticker"] == "MU"
    assert row["source_group"] == "trump_trade_watch"
    assert row["subreddits"] == ["TrumpsTrades"]
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalize supplied social snapshots into social_watch.json.")
    parser.add_argument("input", nargs="?", help="JSON file containing rows/items/posts. Use '-' for stdin.")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent / "social_watch.json"))
    parser.add_argument("--generated-at")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()
    if not args.input:
        raise SystemExit("input JSON path is required unless --self-test is used")
    if args.input == "-":
        import sys

        payload = json.loads(sys.stdin.read())
    else:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    cache = build_social_snapshot_cache(payload, generated_at=args.generated_at)
    if not args.dry_run:
        write_cache(args.out, cache)
    if args.format == "json":
        print(json.dumps(cache, indent=2, sort_keys=True))
    else:
        print(_format_text(cache))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
