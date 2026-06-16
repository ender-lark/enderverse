#!/usr/bin/env python3
"""Collect minimal Reddit market-anomaly rows for Social Watch.

This collector feeds ``social_watch.py``. It is watch-only: Reddit can create a
research prompt or quiet-watch row, but it never creates buy/sell/action cards.
Live tests should use saved fixtures; live runs may use public subreddit JSON
payloads gathered by a browser or supplied on disk.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from reddit_signal_core import (
    DEFAULT_BASELINE_WINDOW,
    detect_signal,
    kill_criterion_check,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = Path(__file__).resolve().parent / "social_watch.json"
ET = ZoneInfo("America/New_York")
UTC = timezone.utc
DEFAULT_SUBREDDITS = [
    "stocks",
    "investing",
    "SecurityAnalysis",
    "wallstreetbets",
    "options",
    "thetagang",
    "ValueInvesting",
    "StockMarket",
]
DEFAULT_LIMIT = 50
USER_AGENT = "enderverse-social-watch/0.1 watch-only research collector"
RETENTION_HOURS = 48
COMMON_WORD_FALSE_POSITIVES = {
    "A",
    "AI",
    "ALL",
    "ARE",
    "ATH",
    "BE",
    "CEO",
    "CFO",
    "DD",
    "DM",
    "DO",
    "EPS",
    "ETF",
    "FOR",
    "GDP",
    "IMO",
    "IPO",
    "IR",
    "IT",
    "IV",
    "LOL",
    "ME",
    "NEW",
    "NO",
    "ON",
    "OR",
    "PE",
    "PM",
    "PR",
    "PT",
    "Q",
    "SEC",
    "TA",
    "THE",
    "TO",
    "USA",
    "YOLO",
}
DEFAULT_TICKERS = {
    "AAPL",
    "AMD",
    "AMZN",
    "ANET",
    "ARM",
    "AVGO",
    "BMNR",
    "COIN",
    "GOOG",
    "GOOGL",
    "LEU",
    "META",
    "MP",
    "MSFT",
    "MU",
    "NVDA",
    "PLTR",
    "QQQ",
    "SMH",
    "SPY",
    "TSLA",
    "UUUU",
}
CRITICAL_MINERALS_TICKERS = {
    "ALOY",
    "CCJ",
    "CRML",
    "DNN",
    "LEU",
    "LTBR",
    "MP",
    "NNE",
    "NXE",
    "OKLO",
    "SMR",
    "SPUT",
    "URA",
    "URG",
    "URNM",
    "UROY",
    "UURAF",
    "UUUU",
    "XE",
}
RETAIL_RISK_WSB_TICKERS = {
    "AMD",
    "AMZN",
    "AVGO",
    "COIN",
    "GOOGL",
    "META",
    "MSFT",
    "MU",
    "NVDA",
    "PLTR",
    "QQQ",
    "RIVN",
    "SMCI",
    "SPY",
    "TSLA",
}
NAME_TO_TICKER = {
    "alphabet": "GOOGL",
    "amazon": "AMZN",
    "apple": "AAPL",
    "bitmine": "BMNR",
    "broadcom": "AVGO",
    "coinbase": "COIN",
    "google": "GOOGL",
    "meta": "META",
    "microsoft": "MSFT",
    "micron": "MU",
    "nvidia": "NVDA",
    "palantir": "PLTR",
    "tesla": "TSLA",
    "centrus": "LEU",
    "energy fuels": "UUUU",
    "mp materials": "MP",
    "ucore": "UURAF",
    "ucore rare metals": "UURAF",
}
REDDIT_SOURCE_GROUPS = {
    "broad_social": {
        "description": "Broad retail and research Reddit watchlist.",
        "subreddits": DEFAULT_SUBREDDITS,
        "tickers": sorted(DEFAULT_TICKERS),
    },
    "critical_minerals_nuclear": {
        "description": (
            "Detachable critical-minerals and nuclear scout lane. Designed to replace "
            "stale Meridian context with low-trust research prompts only."
        ),
        "subreddits": ["criticalmineralstocks", "UraniumSqueeze"],
        "tickers": sorted(CRITICAL_MINERALS_TICKERS),
    },
    "retail_risk_wsb": {
        "description": (
            "Detachable WallStreetBets scout lane for retail crowding, reflexive risk, "
            "and high-noise topic discovery. Not a signal or trade trigger."
        ),
        "subreddits": ["wallstreetbets"],
        "tickers": sorted(RETAIL_RISK_WSB_TICKERS),
    },
}

CASHTAG_RE = re.compile(r"(?<![A-Za-z0-9_])\$([A-Z]{1,6}(?:\.[A-Z]{1,4})?)\b")
UPPER_RE = re.compile(r"\b[A-Z]{2,6}(?:\.[A-Z]{1,4})?\b")


def _now_et() -> datetime:
    return datetime.now(ET).replace(microsecond=0)


def _parse_dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), UTC)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _snippet(text: Any, *, limit: int = 240) -> str:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    return clean[:limit]


def _clean_subreddit(value: Any) -> str:
    text = str(value or "").strip()
    return text[2:] if text.lower().startswith("r/") else text


def _manual_row_id(data: dict[str, Any], subreddit: str, title: str, body: str, permalink: str) -> str:
    explicit = str(data.get("name") or data.get("id") or "").strip()
    if explicit:
        return explicit
    seed = "|".join([
        subreddit,
        str(data.get("created_utc") or data.get("created_at") or data.get("visible_time") or data.get("time") or ""),
        permalink,
        title,
        body[:160],
    ])
    digest = hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"manual-{digest}"


def _manual_snapshot_item(data: dict[str, Any], *, fallback_subreddit: str = "") -> dict[str, Any] | None:
    title = data.get("title") or data.get("headline") or ""
    body = data.get("selftext") or data.get("body") or data.get("snippet") or data.get("text") or ""
    if not title and not body:
        return None
    subreddit = _clean_subreddit(data.get("subreddit") or fallback_subreddit)
    permalink = str(data.get("permalink") or data.get("url") or "").strip()
    visible_time = str(
        data.get("visible_time")
        or data.get("source_time")
        or data.get("age")
        or data.get("time")
        or ""
    ).strip()
    created = (
        data.get("created_utc")
        or data.get("created_at")
        or data.get("posted_at")
        or data.get("timestamp")
        or visible_time
    )
    return {
        "id": _manual_row_id(data, subreddit, str(title), str(body), permalink),
        "source": "reddit",
        "subreddit": subreddit,
        "created_utc": created,
        "source_time_label": visible_time,
        "kind": str(data.get("kind") or "post").strip(),
        "title": title,
        "body": body,
        "permalink": permalink,
        "score_observed": data.get("score") or data.get("upvotes"),
        "comment_count_observed": (
            data.get("num_comments")
            or data.get("comment_count")
            or data.get("comments")
        ),
        "flair": str(data.get("flair") or data.get("link_flair_text") or "").strip(),
    }


def _load_json(path: str | Path) -> Any:
    with Path(path).open(encoding="utf-8-sig") as fh:
        return json.load(fh)


def _atomic_write_json(path: str | Path, payload: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".reddit_collector.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def _atomic_write_text(path: str | Path, text: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".reddit_collector.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            if not text.endswith("\n"):
                fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def load_ticker_universe(paths: list[str] | None = None) -> set[str]:
    tickers = set(DEFAULT_TICKERS)
    for path in paths or []:
        p = Path(path)
        if not p.is_file():
            continue
        payload = _load_json(p)
        stack = [payload]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                for key, value in item.items():
                    if str(key).lower() in {"ticker", "symbol"} and isinstance(value, str):
                        token = value.strip().upper()
                        if token and token not in COMMON_WORD_FALSE_POSITIVES:
                            tickers.add(token)
                    elif re.fullmatch(r"[A-Z]{1,6}(?:\.[A-Z]{1,4})?", str(key)):
                        tickers.add(str(key).upper())
                    if isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(item, list):
                stack.extend(item)
    return tickers


def source_group_names() -> list[str]:
    return sorted(REDDIT_SOURCE_GROUPS)


def source_group_config(name: str | None) -> dict[str, Any]:
    if not name:
        return {}
    key = str(name).strip()
    if key not in REDDIT_SOURCE_GROUPS:
        raise ValueError(f"unknown Reddit source group: {key}")
    return dict(REDDIT_SOURCE_GROUPS[key])


def ticker_universe_for_group(base: set[str], source_group: str | None) -> set[str]:
    tickers = set(base)
    config = source_group_config(source_group)
    tickers.update(str(t).upper() for t in config.get("tickers") or [])
    return tickers


def extract_mentions(text: str, *, ticker_universe: set[str] | None = None) -> dict[str, list[str]]:
    universe = ticker_universe or DEFAULT_TICKERS
    found: dict[str, set[str]] = defaultdict(set)
    for match in CASHTAG_RE.finditer(text or ""):
        ticker = match.group(1).upper()
        if ticker not in COMMON_WORD_FALSE_POSITIVES:
            found[ticker].add(f"${ticker}")
    for token in UPPER_RE.findall(text or ""):
        ticker = token.upper()
        if ticker in universe and ticker not in COMMON_WORD_FALSE_POSITIVES:
            found[ticker].add(ticker)
    lower = (text or "").lower()
    for name, ticker in NAME_TO_TICKER.items():
        if ticker in universe and re.search(rf"\b{re.escape(name)}\b", lower):
            found[ticker].add(name)
    return {ticker: sorted(terms) for ticker, terms in sorted(found.items())}


def _source_type_for_item(item: dict[str, Any]) -> str:
    text = " ".join([
        str(item.get("title") or ""),
        str(item.get("body") or ""),
        str(item.get("subreddit") or ""),
    ]).lower()
    if "daily" in text and "discussion" in text:
        return "daily_room_tone"
    if any(term in text for term in (
        "announce", "commission", "memorandum", "framework", "collaboration",
        "department", "contract", "facility", "supply chain", "deadline",
        "rare earth", "critical mineral", "uranium", "nuclear",
    )):
        return "company_or_policy_catalyst"
    if any(term in text for term in ("ai", "data center", "datacentre", "power demand", "electricity")):
        return "ai_power_nuclear_narrative"
    if any(term in text for term in ("underperformance", "price action", "squeeze", "bullish", "bearish")):
        return "positioning_or_crowding"
    if any(term in text for term in ("yolo", "gain", "loss", "short interest", "short squeeze", "meme")):
        return "possible_promotion"
    return "research_prompt"


def _review_prompt_fields(
    *,
    ticker: str,
    latest: dict[str, Any],
    source_group: str | None,
    confirmations: list[str],
) -> dict[str, str]:
    title = _snippet(latest.get("title") or latest.get("body"), limit=180)
    source_type = _source_type_for_item(latest)
    if source_group == "critical_minerals_nuclear":
        why = (
            "Critical-minerals/nuclear Reddit scout item that may indicate a company catalyst, "
            "policy/supply-chain change, AI power-demand narrative, or crowding shift."
        )
        implication = (
            "Quiet Watch or Research Queue only. Relevant to critical-minerals/nuclear exposure "
            "and adjacent AI-power infrastructure theses after non-social confirmation."
        )
        next_check = (
            "Verify company release/filing or reliable news, then check price-volume/UW flow and "
            "whether the item changes MP/LEU/UUUU/URA/URNM or nuclear-power research priority."
        )
    elif source_group == "retail_risk_wsb":
        why = (
            "WSB scout item that may reveal retail crowding, reflexive chase risk, sentiment extremes, "
            "or a noisy topic that needs independent vetting."
        )
        implication = (
            "Risk-control or research prompt only. Useful for checking crowding, late-entry risk, "
            "and whether a high-beta holding or target is becoming socially crowded."
        )
        next_check = (
            "Check price-volume, UW options flow, reliable news, and whether the setup is already late "
            "before using it for risk posture or research priority."
        )
    else:
        why = "Reddit scout item that may point to an unusual ticker/topic cluster or external headline echo."
        implication = "Research prompt only; no capital action without independent evidence and portfolio context."
        next_check = "Verify with news/filing, UW, price action, Fundstrat, or catalyst calendar before use."
    return {
        "source_group": source_group or "custom",
        "source_type": source_type,
        "why_it_matters": f"{why} Latest observed item: {title}",
        "portfolio_implication": implication,
        "confidence": "low scout" if not confirmations else "medium-low scout after independent confirmation",
        "decay_speed": "fast for company/news catalysts; medium for policy or structural supply-chain themes",
        "confirmation_needed": (
            "Independent non-social confirmation from news, filings, UW/price action, Fundstrat, "
            "catalyst calendars, or primary company/source material."
        ),
        "blocker_before_action": "Reddit is not a trade trigger; no buy/sell/size change from Reddit alone.",
        "suggested_next_check": next_check,
    }


def _children(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("children"), list):
            return [row for row in data["children"] if isinstance(row, dict)]
        if isinstance(payload.get("children"), list):
            return [row for row in payload["children"] if isinstance(row, dict)]
    return []


def iter_reddit_items(payload: Any, *, fallback_subreddit: str = "") -> list[dict[str, Any]]:
    """Flatten listing/comment JSON into minimal item dicts.

    Supports standard listing payloads, comment-thread arrays, and already
    normalized fixture rows. Author fields are deliberately ignored.
    """
    out: list[dict[str, Any]] = []
    if isinstance(payload, list):
        for part in payload:
            out.extend(iter_reddit_items(part, fallback_subreddit=fallback_subreddit))
        return out
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        nested_fallback = _clean_subreddit(payload.get("subreddit") or fallback_subreddit)
        for row in payload["items"]:
            if isinstance(row, dict):
                out.extend(iter_reddit_items(row, fallback_subreddit=nested_fallback))
        return out
    if isinstance(payload, dict):
        manual = _manual_snapshot_item(payload, fallback_subreddit=fallback_subreddit)
        if manual:
            out.append(manual)
            return out
    if isinstance(payload, dict) and {"id", "created_utc"} & set(payload):
        data = payload
        subreddit = _clean_subreddit(data.get("subreddit") or fallback_subreddit)
        title = data.get("title") or ""
        body = data.get("selftext") or data.get("body") or ""
        kind = str(data.get("kind") or "post").strip()
        out.append({
            "id": str(data.get("name") or data.get("id") or "").strip(),
            "source": "reddit",
            "subreddit": subreddit,
            "created_utc": data.get("created_utc") or data.get("created_at"),
            "kind": kind,
            "title": title,
            "body": body,
            "permalink": data.get("permalink") or data.get("url") or "",
            "score_observed": data.get("score"),
            "comment_count_observed": data.get("num_comments") or data.get("comment_count"),
            "flair": data.get("flair") or data.get("link_flair_text") or "",
        })
        return out
    for child in _children(payload):
        data = child.get("data") if isinstance(child.get("data"), dict) else child
        kind_raw = str(child.get("kind") or data.get("kind") or "").strip()
        if kind_raw == "more":
            continue
        subreddit = _clean_subreddit(data.get("subreddit") or fallback_subreddit)
        title = data.get("title") or ""
        body = data.get("selftext") or data.get("body") or ""
        if not title and not body:
            continue
        out.append({
            "id": str(data.get("name") or data.get("id") or "").strip(),
            "source": "reddit",
            "subreddit": subreddit,
            "created_utc": data.get("created_utc") or data.get("created_at"),
            "kind": "comment" if kind_raw == "t1" or data.get("body") else "post",
            "title": title,
            "body": body,
            "permalink": data.get("permalink") or data.get("url") or "",
            "score_observed": data.get("score"),
            "comment_count_observed": data.get("num_comments") or data.get("comment_count"),
            "flair": data.get("flair") or data.get("link_flair_text") or "",
        })
        replies = data.get("replies")
        if isinstance(replies, (dict, list)):
            out.extend(iter_reddit_items(replies, fallback_subreddit=subreddit))
    return out


def fetch_subreddit_payload(subreddit: str, *, limit: int = DEFAULT_LIMIT) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    url = f"https://www.reddit.com/r/{subreddit}/new.json?limit={int(limit)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    meta: dict[str, Any] = {"subreddit": subreddit, "url": url}
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            meta["status"] = getattr(resp, "status", None)
            meta["rate_limit"] = {
                "used": resp.headers.get("X-Ratelimit-Used"),
                "remaining": resp.headers.get("X-Ratelimit-Remaining"),
                "reset": resp.headers.get("X-Ratelimit-Reset"),
            }
            body = resp.read().decode("utf-8")
            return json.loads(body), meta
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        meta.update({"error": f"{type(exc).__name__}: {exc}"})
        return None, meta


def _load_confirmation_map(path: str | None) -> dict[str, list[str]]:
    if not path:
        return {}
    payload = _load_json(path)
    out: dict[str, list[str]] = defaultdict(list)
    if isinstance(payload, dict):
        rows = payload.get("rows") or payload.get("items") or payload.get("confirmations")
        if rows is None:
            for ticker, value in payload.items():
                if isinstance(value, list):
                    out[str(ticker).upper()].extend(str(v) for v in value if str(v).strip())
                elif isinstance(value, str) and value.strip():
                    out[str(ticker).upper()].append(value.strip())
            return dict(out)
    else:
        rows = payload
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
        if not ticker:
            continue
        confirmations = row.get("independent_confirmation") or row.get("confirmations") or row.get("confirmed_by")
        if isinstance(confirmations, str):
            confirmations = [confirmations]
        for value in confirmations or []:
            text = str(value or "").strip()
            if text:
                out[ticker].append(text)
    return dict(out)


def _load_kill_state(path: str | None) -> dict[str, Any]:
    if not path:
        return {"status": "CLEAR", "source": "default_no_performance_history"}
    payload = _load_json(path)
    if not isinstance(payload, dict):
        return {"status": "WATCH", "source": path, "reason": "invalid_kill_state"}
    status = kill_criterion_check(
        int(payload.get("n_scored") or 0),
        float(payload.get("hit_rate") or 0.0),
        int(payload.get("days_since_actionable") or 0),
        bool(payload.get("any_positive_signal")),
    )
    return {"status": status, "source": path, **payload}


def _mention_series(counter: Counter[str], *, end_date: datetime, days: int) -> list[int]:
    dates = [
        (end_date.date() - timedelta(days=offset)).isoformat()
        for offset in range(days - 1, -1, -1)
    ]
    return [int(counter.get(day, 0)) for day in dates]


def _collector_score(row: dict[str, Any]) -> float:
    score = 0.0
    if row.get("fired"):
        score += 50.0
    try:
        score += max(float(row.get("velocity_z") or 0.0), 0.0) * 10.0
    except (TypeError, ValueError):
        pass
    try:
        score += min(float(row.get("mentions") or 0.0), 50.0)
    except (TypeError, ValueError):
        pass
    try:
        score += min(float(row.get("comment_count_observed") or 0.0), 100.0) / 10.0
    except (TypeError, ValueError):
        pass
    return round(score, 2)


def build_cache(
    payloads: list[Any],
    *,
    subreddits: list[str] | None = None,
    source_group: str | None = None,
    failures: list[dict[str, Any]] | None = None,
    generated_at: datetime | None = None,
    ticker_universe: set[str] | None = None,
    confirmation_map: dict[str, list[str]] | None = None,
    kill_state: dict[str, Any] | None = None,
    baseline_window: int = DEFAULT_BASELINE_WINDOW,
) -> dict[str, Any]:
    generated = (generated_at or _now_et()).astimezone(ET).replace(microsecond=0)
    ingested_utc = generated.astimezone(UTC)
    expires = ingested_utc + timedelta(hours=RETENTION_HOURS)
    ticker_universe = ticker_universe_for_group(ticker_universe or DEFAULT_TICKERS, source_group)
    confirmation_map = confirmation_map or {}
    failure_rows = failures or []
    raw_items: list[dict[str, Any]] = []
    for payload in payloads:
        fallback = ""
        if isinstance(payload, dict):
            fallback = str(payload.get("subreddit") or "").strip()
        raw_items.extend(iter_reddit_items(payload, fallback_subreddit=fallback))

    if not raw_items and failure_rows:
        return {
            "generated_at": _iso(generated),
            "checked_at": _iso(generated),
            "source": "reddit_chrome_collector",
            "status": "not_checked",
            "line": "Social watch not checked: Reddit fetch failed or returned no readable payloads.",
            "source_group": source_group or "custom",
            "subreddits_checked": subreddits or [],
            "failures": failure_rows,
            "rows": [],
            "retention_hours": RETENTION_HOURS,
            "honesty_rule": "Fetch failure is not no-signal evidence; keep Social Watch dark/not_checked.",
        }

    per_ticker_counts: dict[str, Counter[str]] = defaultdict(Counter)
    per_ticker_items: dict[str, list[dict[str, Any]]] = defaultdict(list)
    scanned_subreddits: set[str] = set()
    for item in raw_items:
        created = _parse_dt(item.get("created_utc")) or ingested_utc
        subreddit = str(item.get("subreddit") or "").strip()
        if subreddit:
            scanned_subreddits.add(subreddit)
        text = " ".join([str(item.get("title") or ""), str(item.get("body") or "")])
        mentions = extract_mentions(text, ticker_universe=ticker_universe)
        if not mentions:
            continue
        day = created.astimezone(ET).date().isoformat()
        for ticker, terms in mentions.items():
            per_ticker_counts[ticker][day] += 1
            per_ticker_items[ticker].append({**item, "created_dt": created, "matched_terms": terms})

    rows: list[dict[str, Any]] = []
    series_len = baseline_window + 1
    kill = kill_state or {"status": "CLEAR", "source": "default_no_performance_history"}
    for ticker, counts in sorted(per_ticker_counts.items()):
        items = sorted(per_ticker_items[ticker], key=lambda row: row["created_dt"])
        if not items:
            continue
        series = _mention_series(counts, end_date=generated, days=series_len)
        signal = detect_signal(series, baseline_window=baseline_window)
        subs = sorted({str(row.get("subreddit") or "").strip() for row in items if row.get("subreddit")})
        terms = sorted({term for row in items for term in row.get("matched_terms", [])})
        latest = items[-1]
        confirmations = list(dict.fromkeys(confirmation_map.get(ticker, [])))
        fired = bool(signal.get("fired")) and kill.get("status") != "TRIGGERED"
        escalation = "Quiet Watch"
        if fired and confirmations:
            escalation = "Research Queue candidate"
        review_fields = _review_prompt_fields(
            ticker=ticker,
            latest=latest,
            source_group=source_group,
            confirmations=confirmations,
        )
        row = {
            "id": f"reddit-{ticker}-{generated.date().isoformat()}",
            "source": "reddit",
            "source_group": review_fields["source_group"],
            "source_type": review_fields["source_type"],
            "subreddit": subs[0] if subs else "",
            "subreddits": subs,
            "created_utc": _iso(items[0]["created_dt"].astimezone(UTC)),
            "kind": "post_or_comment",
            "title_snippet": _snippet(latest.get("title")),
            "body_snippet": _snippet(latest.get("body")),
            "tickers": [ticker],
            "entities": [],
            "permalink": str(latest.get("permalink") or "").strip(),
            "score_observed": latest.get("score_observed"),
            "comment_count_observed": latest.get("comment_count_observed"),
            "flair": str(latest.get("flair") or "").strip(),
            "source_time_label": str(latest.get("source_time_label") or "").strip(),
            "matched_terms": terms,
            "ingested_at": _iso(ingested_utc),
            "expires_at": _iso(expires),
            "first_seen": _iso(items[0]["created_dt"].astimezone(UTC)),
            "last_seen": _iso(items[-1]["created_dt"].astimezone(UTC)),
            "mention_series": series,
            "mentions": signal.get("current"),
            "current_mentions": signal.get("current"),
            "velocity_z": signal.get("zscore"),
            "baseline_mean": signal.get("baseline_mean"),
            "baseline_sd": signal.get("baseline_sd"),
            "eligible": bool(signal.get("eligible")),
            "fired": fired,
            "kill_switch_status": kill.get("status"),
            "summary": _snippet(latest.get("title") or latest.get("body")),
            "evidence": terms[:5],
            "snippets": [_snippet((row.get("title") or row.get("body")), limit=160) for row in items[-3:]],
            "independent_confirmation": confirmations,
            "escalation": escalation,
            "risk": (
                "Watch-only social anomaly; route to Research Queue only after non-social confirmation."
                if confirmations
                else "Pump/chase and echo risk; no independent confirmation yet."
            ),
            "confirmation_required": (
                "Needs non-social confirmation from UW, price/news, Fundstrat, catalyst, or source-call evidence."
            ),
            "why_it_matters": review_fields["why_it_matters"],
            "portfolio_implication": review_fields["portfolio_implication"],
            "confidence": review_fields["confidence"],
            "decay_speed": review_fields["decay_speed"],
            "confirmation_needed": review_fields["confirmation_needed"],
            "blocker_before_action": review_fields["blocker_before_action"],
            "suggested_next_check": review_fields["suggested_next_check"],
        }
        row["collector_score"] = _collector_score(row)
        rows.append(row)

    rows.sort(key=lambda row: float(row.get("collector_score") or 0.0), reverse=True)
    status = "has_data" if rows else "checked_clear"
    line = (
        f"Social watch collector: {len(rows)} ticker mention candidate(s); watch-only until independently confirmed."
        if rows
        else "Social watch collector checked clear: no ticker mention candidates in fetched Reddit payloads."
    )
    return {
        "generated_at": _iso(generated),
        "checked_at": _iso(generated),
        "source": "reddit_chrome_collector",
        "status": status,
        "line": line,
        "source_group": source_group or "custom",
        "subreddits_checked": sorted(scanned_subreddits or set(subreddits or [])),
        "failures": failure_rows,
        "retention_hours": RETENTION_HOURS,
        "expires_at": _iso(expires),
        "kill_switch": kill,
        "rows": rows,
        "research_queue_candidates": build_research_queue_rows(rows),
        "honesty_rule": "Watch-only until independently confirmed; never a standalone trade signal.",
    }


def build_research_queue_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        confirmations = row.get("independent_confirmation") or []
        if not row.get("fired") or not confirmations:
            continue
        ticker = (row.get("tickers") or [""])[0]
        out.append({
            "ticker": ticker,
            "r": f"{ticker} - Vet Reddit social anomaly before any action",
            "pr": "med",
            "status": "Working",
            "source": "reddit_social_watch",
            "notes": (
                f"Watch-only Reddit velocity signal. Confirmation: {'; '.join(confirmations)}. "
                f"Blocker before action: verify non-social evidence and disconfirmation trigger."
            ),
        })
    return out


def _report_value(value: Any, fallback: str = "not supplied") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def build_scout_report(cache: dict[str, Any], *, max_rows: int = 12) -> str:
    generated = _report_value(cache.get("generated_at"))
    source_group = _report_value(cache.get("source_group"))
    status = _report_value(cache.get("status"))
    lines = [
        "# Reddit Scout Report",
        "",
        f"- Generated: {generated}",
        f"- Source group: {source_group}",
        f"- Status: {status}",
        "- Rule: Reddit is low-trust scout evidence, never a standalone trade trigger.",
        "",
    ]
    if cache.get("status") == "not_checked":
        lines.extend([
            "## Not Checked",
            "",
            _report_value(cache.get("line"), "Reddit fetch failed or returned no readable payloads."),
            "",
            "Missing or blocked Reddit data is not checked; do not treat it as no social signal.",
        ])
        return "\n".join(lines)

    rows = sorted(
        [row for row in cache.get("rows") or [] if isinstance(row, dict)],
        key=lambda row: float(row.get("collector_score") or 0.0),
        reverse=True,
    )
    if not rows:
        lines.extend([
            "## Checked Clear",
            "",
            _report_value(cache.get("line"), "No ticker/topic candidates in the supplied snapshot."),
        ])
        return "\n".join(lines)

    lines.extend([
        "## Ranked Prompts",
        "",
    ])
    for idx, row in enumerate(rows[:max_rows], 1):
        ticker = (row.get("tickers") or [""])[0] or row.get("ticker") or "SOCIAL"
        subreddit = ", ".join(row.get("subreddits") or [row.get("subreddit") or ""])
        source_time = row.get("source_time_label") or row.get("last_seen") or row.get("created_utc")
        link = _report_value(row.get("permalink"), "not supplied")
        lines.extend([
            f"### {idx}. {ticker} - {_report_value(row.get('summary'), 'untitled Reddit prompt')}",
            "",
            f"- Source/time: r/{_report_value(subreddit, 'unknown')} | {_report_value(source_time)}",
            f"- Collector score: {_report_value(row.get('collector_score'), '0')} | mentions {_report_value(row.get('mentions'), '0')} | z {_report_value(row.get('velocity_z'), 'n/a')}",
            f"- Source type: {_report_value(row.get('source_type'))}",
            f"- Why it matters: {_report_value(row.get('why_it_matters'))}",
            f"- Portfolio implication: {_report_value(row.get('portfolio_implication'))}",
            f"- Confidence: {_report_value(row.get('confidence'))}",
            f"- Decay speed: {_report_value(row.get('decay_speed'))}",
            f"- Confirmation needed: {_report_value(row.get('confirmation_needed'))}",
            f"- Blocker before action: {_report_value(row.get('blocker_before_action'))}",
            f"- Suggested next check: {_report_value(row.get('suggested_next_check'))}",
            f"- Link: {link}",
            "",
        ])
    return "\n".join(lines)


def write_scout_report(cache: dict[str, Any], *, out: str) -> Path:
    return _atomic_write_text(out, build_scout_report(cache))


def write_research_queue(rows: list[dict[str, Any]], *, out: str, merge_existing: bool = True) -> dict[str, Any]:
    from research_queue_intake import (
        build_research_queue,
        merge_queues,
        validate_research_queue,
    )

    queue = build_research_queue(rows, generated_at=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"))
    if merge_existing and Path(out).is_file():
        queue = merge_queues(_load_json(out), queue)
    problems = validate_research_queue(queue)
    if problems:
        return {"written": False, "problems": problems, "path": out}
    _atomic_write_json(out, queue)
    return {"written": True, "path": out, "pending": len(queue.get("pending") or [])}


def _payloads_from_inputs(paths: list[str]) -> list[Any]:
    payloads = []
    for path in paths:
        p = Path(path)
        if p.is_dir():
            for child in sorted(p.glob("*.json")):
                payloads.append(_load_json(child))
        else:
            payloads.append(_load_json(p))
    return payloads


def collect_live(subreddits: list[str], *, limit: int = DEFAULT_LIMIT) -> tuple[list[Any], list[dict[str, Any]]]:
    payloads: list[Any] = []
    failures: list[dict[str, Any]] = []
    for subreddit in subreddits:
        payload, meta = fetch_subreddit_payload(subreddit, limit=limit)
        if payload is None:
            failures.append(meta)
        else:
            payloads.append({"subreddit": subreddit, "items": [payload], "fetch_meta": meta})
    return payloads, failures


def format_text(cache: dict[str, Any]) -> str:
    lines = [cache.get("line") or "Reddit collector"]
    if cache.get("status") == "not_checked":
        lines.append("status: not_checked")
    if cache.get("failures"):
        lines.append(f"fetch failures: {len(cache['failures'])}")
    for row in cache.get("rows") or []:
        ticker = (row.get("tickers") or ["SOCIAL"])[0]
        lines.append(
            f"- {ticker}: mentions {row.get('mentions')} z={row.get('velocity_z')} "
            f"fired={row.get('fired')} route={row.get('escalation')} subs={','.join(row.get('subreddits') or [])}"
        )
    candidates = cache.get("research_queue_candidates") or []
    if candidates:
        lines.append(f"research queue candidates after confirmation: {len(candidates)}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build src/social_watch.json from Reddit payloads.")
    parser.add_argument(
        "--source-group",
        choices=source_group_names(),
        help="Named detachable subreddit/ticker group. Overrides --subreddits when supplied.",
    )
    parser.add_argument("--subreddits", default=",".join(DEFAULT_SUBREDDITS))
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--input", action="append", default=[], help="Reddit JSON file or directory of JSON fixtures/exports")
    parser.add_argument("--fetch-live", action="store_true", help="Fetch public subreddit JSON listings directly")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--report-out", help="Optional Markdown scout report path, usually under tmp/")
    parser.add_argument("--confirmations", help="Optional non-social confirmation map JSON")
    parser.add_argument("--ticker-universe", action="append", default=[], help="Optional JSON cache to mine ticker symbols from")
    parser.add_argument("--kill-switch-state", help="Optional historical performance JSON for reddit_signal_core.kill_criterion_check")
    parser.add_argument("--research-queue-out", help="Optional repo-local Research Queue cache to append confirmed fired anomalies to")
    parser.add_argument("--no-merge-research-queue", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    if args.source_group:
        config = source_group_config(args.source_group)
        subreddits = list(config.get("subreddits") or [])
    else:
        subreddits = [_clean_subreddit(part) for part in args.subreddits.split(",") if part.strip()]
    payloads = _payloads_from_inputs(args.input)
    failures: list[dict[str, Any]] = []
    if args.fetch_live:
        live_payloads, failures = collect_live(subreddits, limit=args.limit)
        payloads.extend(live_payloads)
    if not payloads and not failures:
        parser.error("provide --input, --fetch-live, or both")

    cache = build_cache(
        payloads,
        subreddits=subreddits,
        source_group=args.source_group,
        failures=failures,
        ticker_universe=ticker_universe_for_group(load_ticker_universe(args.ticker_universe), args.source_group),
        confirmation_map=_load_confirmation_map(args.confirmations),
        kill_state=_load_kill_state(args.kill_switch_state),
    )
    rq_report = None
    if args.research_queue_out and cache.get("research_queue_candidates"):
        rq_report = write_research_queue(
            cache["research_queue_candidates"],
            out=args.research_queue_out,
            merge_existing=not args.no_merge_research_queue,
        )
        cache["research_queue_write"] = rq_report
    report_path = None
    if args.report_out and not args.dry_run:
        report_path = str(write_scout_report(cache, out=args.report_out))
        cache["scout_report"] = report_path
    if not args.dry_run:
        _atomic_write_json(args.out, cache)
    if args.format == "json":
        print(json.dumps({
            "cache": cache,
            "written": None if args.dry_run else args.out,
            "research_queue": rq_report,
            "report": report_path,
        }, indent=2, sort_keys=True))
    else:
        print(format_text(cache))
        if not args.dry_run:
            print(f"wrote: {args.out}")
        if report_path:
            print(f"report: {report_path}")
    return 0 if cache.get("status") != "not_checked" or failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
