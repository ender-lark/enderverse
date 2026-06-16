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
SNAPSHOT_HISTORY_SCHEMA = "reddit_snapshot_history_v1"
DEFAULT_HISTORY_WINDOW_DAYS = 14
SOURCE_ROLE_SPECIALIZED_CATALYST = "specialized_catalyst_scout"
SOURCE_ROLE_RETAIL_CROWDING = "retail_crowding_risk"
SOURCE_ROLE_SPECIALIZED_RESEARCH = "specialized_research"
SOURCE_ROLE_BROAD_ATTENTION = "broad_market_attention"
SOURCE_ROLE_TICKER_ECHO = "ticker_echo_chamber"
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
        "role": SOURCE_ROLE_BROAD_ATTENTION,
        "subreddits": DEFAULT_SUBREDDITS,
        "tickers": sorted(DEFAULT_TICKERS),
    },
    "critical_minerals_nuclear": {
        "description": (
            "Detachable critical-minerals and nuclear scout lane. Designed to replace "
            "stale Meridian context with low-trust research prompts only."
        ),
        "role": SOURCE_ROLE_SPECIALIZED_CATALYST,
        "subreddits": ["criticalmineralstocks", "UraniumSqueeze"],
        "tickers": sorted(CRITICAL_MINERALS_TICKERS),
    },
    "retail_risk_wsb": {
        "description": (
            "Detachable WallStreetBets scout lane for retail crowding, reflexive risk, "
            "and high-noise topic discovery. Not a signal or trade trigger."
        ),
        "role": SOURCE_ROLE_RETAIL_CROWDING,
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


def _parse_observed_count(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().lower().replace(",", "")
    if not text:
        return None
    multiplier = 1
    if text.endswith("k"):
        multiplier = 1_000
        text = text[:-1]
    elif text.endswith("m"):
        multiplier = 1_000_000
        text = text[:-1]
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return int(float(match.group(0)) * multiplier)
    except ValueError:
        return None


def _parse_relative_age(value: Any, *, anchor: datetime) -> datetime | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    text = text.replace("·", " ").replace(".", " ")
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days|w|week|weeks|mo|mon|month|months|y|yr|year|years)\s+ago",
        text,
    )
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2)
    if unit.startswith("m") and unit not in {"mo", "mon", "month", "months"}:
        delta = timedelta(minutes=amount)
    elif unit.startswith("h"):
        delta = timedelta(hours=amount)
    elif unit.startswith("d"):
        delta = timedelta(days=amount)
    elif unit.startswith("w"):
        delta = timedelta(weeks=amount)
    elif unit in {"mo", "mon", "month", "months"}:
        delta = timedelta(days=30 * amount)
    else:
        delta = timedelta(days=365 * amount)
    return anchor - delta


def _item_created_dt(item: dict[str, Any], *, generated: datetime) -> datetime:
    parsed = _parse_dt(item.get("created_utc"))
    if parsed:
        return parsed
    parsed = _parse_relative_age(item.get("source_time_label"), anchor=generated.astimezone(UTC))
    if parsed:
        return parsed
    return generated.astimezone(UTC)


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
        "members_observed": _parse_observed_count(data.get("members") or data.get("member_count")),
        "online_observed": _parse_observed_count(data.get("online") or data.get("online_count")),
        "source_sort": str(data.get("source_sort") or data.get("sort") or "").strip(),
        "scan_window": str(data.get("scan_window") or "").strip(),
        "captured_at": data.get("captured_at") or data.get("ingested_at") or "",
        "visible_rank": _parse_observed_count(data.get("visible_rank") or data.get("rank")),
        "subreddit_health_override": str(data.get("subreddit_health") or "").strip(),
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


def source_group_role(name: str | None) -> str:
    config = source_group_config(name)
    return str(config.get("role") or SOURCE_ROLE_SPECIALIZED_RESEARCH)


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


def _median_int(values: list[int]) -> int:
    nums = sorted(int(v) for v in values)
    if not nums:
        return 0
    mid = len(nums) // 2
    if len(nums) % 2:
        return nums[mid]
    return int(round((nums[mid - 1] + nums[mid]) / 2))


def _has_external_link(item: dict[str, Any]) -> bool:
    text = " ".join([
        str(item.get("title") or ""),
        str(item.get("body") or ""),
        str(item.get("permalink") or ""),
    ]).lower()
    links = re.findall(r"https?://[^\s)]+", text)
    return any("reddit.com" not in link for link in links)


def _is_counter_thesis(item: dict[str, Any]) -> bool:
    text = " ".join([str(item.get("title") or ""), str(item.get("body") or "")]).lower()
    return any(term in text for term in (
        "underperformance",
        "bearish",
        "risk",
        "scam",
        "skeptic",
        "skeptical",
        "concern",
        "problem",
        "short thesis",
        "avoid",
        "overvalued",
    ))


def _is_noise_like(item: dict[str, Any], *, source_type: str | None = None) -> bool:
    flair = str(item.get("flair") or "").strip().lower()
    text = " ".join([str(item.get("title") or ""), str(item.get("body") or "")]).lower()
    if source_type == "possible_promotion":
        return True
    if flair in {"meme", "gain", "loss", "yolo"}:
        return True
    return any(term in text for term in (
        "yolo",
        "gain",
        "loss",
        "am i cooked",
        "buy this",
        "to the moon",
        "moonshot",
        "diamond hands",
    ))


def _source_health_note(status: str) -> str:
    if status == "active":
        return "Source appears active enough for current-topic scouting, still low trust."
    if status == "thin_but_current":
        return "Source is current but thin; use as link/catalyst scout, not sentiment proof."
    if status == "fringe":
        return "Source is low-activity and promotion/noise-heavy; treat only as a prompt to verify elsewhere."
    return "Source is stale or too sparse; do not infer sentiment or crowding from it."


def _interpretation_limit(status: str, source_role: str) -> str:
    if status in {"stale", "fringe"}:
        return "primary-source/link scout only; no sentiment or crowding conclusion"
    if source_role == SOURCE_ROLE_RETAIL_CROWDING:
        return "crowding/risk temperature only; not thesis quality"
    if source_role == SOURCE_ROLE_SPECIALIZED_CATALYST:
        return "company/policy catalyst scout; verify outside Reddit"
    return "research prompt only; verify outside Reddit"


def build_source_health(
    raw_items: list[dict[str, Any]],
    *,
    subreddits: list[str] | None,
    generated: datetime,
) -> dict[str, dict[str, Any]]:
    by_subreddit: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in raw_items:
        subreddit = _clean_subreddit(item.get("subreddit"))
        if subreddit:
            by_subreddit[subreddit].append(item)
    for subreddit in subreddits or []:
        by_subreddit.setdefault(_clean_subreddit(subreddit), [])

    out: dict[str, dict[str, Any]] = {}
    generated_utc = generated.astimezone(UTC)
    for subreddit, items in sorted(by_subreddit.items()):
        created_rows = [_item_created_dt(item, generated=generated) for item in items]
        ages = [
            max((generated_utc - created.astimezone(UTC)).total_seconds() / 86400.0, 0.0)
            for created in created_rows
        ]
        posts_24h = sum(1 for age in ages if age <= 1)
        posts_7d = sum(1 for age in ages if age <= 7)
        posts_30d = sum(1 for age in ages if age <= 30)
        newest_age_days = round(min(ages), 2) if ages else None
        upvotes = [
            count for count in (_parse_observed_count(item.get("score_observed")) for item in items)
            if count is not None
        ]
        comments = [
            count for count in (_parse_observed_count(item.get("comment_count_observed")) for item in items)
            if count is not None
        ]
        noise_count = sum(1 for item in items if _is_noise_like(item, source_type=_source_type_for_item(item)))
        total = len(items)
        noise_ratio = round(noise_count / total, 2) if total else 0.0
        observed_members = [
            count for count in (_parse_observed_count(item.get("members_observed")) for item in items)
            if count is not None
        ]
        observed_online = [
            count for count in (_parse_observed_count(item.get("online_observed")) for item in items)
            if count is not None
        ]
        override = next((str(item.get("subreddit_health_override") or "").strip() for item in items if item.get("subreddit_health_override")), "")
        if override in {"active", "thin_but_current", "stale", "fringe"}:
            status = override
        elif total and noise_ratio >= 0.5 and posts_7d < 5:
            status = "fringe"
        elif newest_age_days is None:
            status = "stale"
        elif newest_age_days <= 1 and posts_7d >= 5:
            status = "active"
        elif newest_age_days <= 2 and posts_7d >= 2:
            status = "thin_but_current"
        elif newest_age_days > 7 or posts_30d < 3:
            status = "stale"
        else:
            status = "stale"
        out[subreddit] = {
            "status": status,
            "note": _source_health_note(status),
            "members_observed": max(observed_members) if observed_members else None,
            "online_observed": max(observed_online) if observed_online else None,
            "newest_meaningful_post_age_days": newest_age_days,
            "posts_seen_24h": posts_24h,
            "posts_seen_7d": posts_7d,
            "posts_seen_30d": posts_30d,
            "median_score_observed": _median_int(upvotes),
            "median_comments_observed": _median_int(comments),
            "promo_noise_ratio": noise_ratio,
            "visible_posts_scanned": total,
        }
    return out


def _usefulness_for_item(
    item: dict[str, Any],
    *,
    source_type: str,
    source_role: str,
    health_status: str,
) -> dict[str, str]:
    if health_status in {"stale", "fringe"}:
        if _has_external_link(item) or source_type == "company_or_policy_catalyst":
            return {
                "usefulness": "medium",
                "signal_kind": "primary-source/link scout",
                "destroy_reason": "",
            }
        return {
            "usefulness": "low",
            "signal_kind": "destroy/noise",
            "destroy_reason": "Subreddit is stale/fringe and item lacks outside evidence.",
        }
    if source_role == SOURCE_ROLE_RETAIL_CROWDING:
        if _is_noise_like(item, source_type=source_type):
            return {
                "usefulness": "low",
                "signal_kind": "crowding/noise temperature",
                "destroy_reason": "High-noise WSB item; useful only as crowding or mania temperature.",
            }
        return {
            "usefulness": "medium",
            "signal_kind": "retail crowding/risk",
            "destroy_reason": "",
        }
    if source_type == "company_or_policy_catalyst" or _has_external_link(item):
        return {"usefulness": "high", "signal_kind": "specific catalyst/link scout", "destroy_reason": ""}
    if _is_counter_thesis(item):
        return {"usefulness": "medium", "signal_kind": "counter-thesis/risk warning", "destroy_reason": ""}
    if _is_noise_like(item, source_type=source_type):
        return {
            "usefulness": "low",
            "signal_kind": "destroy/noise",
            "destroy_reason": "Promotion, meme, gain/loss, or unsupported buy-this framing.",
        }
    return {"usefulness": "medium", "signal_kind": "theme/research prompt", "destroy_reason": ""}


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
            "Crowding/risk-control or research prompt only. Useful for checking crowding, late-entry risk, "
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
        inherited = {
            key: payload.get(key)
            for key in (
                "members",
                "member_count",
                "online",
                "online_count",
                "source_sort",
                "sort",
                "scan_window",
                "captured_at",
                "subreddit_health",
            )
            if payload.get(key) not in (None, "")
        }
        for row in payload["items"]:
            if isinstance(row, dict):
                out.extend(iter_reddit_items({**inherited, **row}, fallback_subreddit=nested_fallback))
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
    if row.get("usefulness") == "high":
        score += 15.0
    elif row.get("usefulness") == "medium":
        score += 6.0
    elif row.get("usefulness") == "low":
        score -= 8.0
    if row.get("source_health_status") == "active":
        score += 5.0
    elif row.get("source_health_status") == "thin_but_current":
        score += 2.0
    elif row.get("source_health_status") in {"stale", "fringe"}:
        score -= 8.0
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
    source_role = source_group_role(source_group)
    ticker_universe = ticker_universe_for_group(ticker_universe or DEFAULT_TICKERS, source_group)
    confirmation_map = confirmation_map or {}
    failure_rows = failures or []
    raw_items: list[dict[str, Any]] = []
    for payload in payloads:
        fallback = ""
        if isinstance(payload, dict):
            fallback = str(payload.get("subreddit") or "").strip()
        raw_items.extend(iter_reddit_items(payload, fallback_subreddit=fallback))
    source_health = build_source_health(raw_items, subreddits=subreddits, generated=generated)

    if not raw_items and failure_rows:
        return {
            "generated_at": _iso(generated),
            "checked_at": _iso(generated),
            "source": "reddit_chrome_collector",
            "status": "not_checked",
            "line": "Social watch not checked: Reddit fetch failed or returned no readable payloads.",
            "source_group": source_group or "custom",
            "source_role": source_role,
            "subreddits_checked": subreddits or [],
            "source_health": source_health,
            "failures": failure_rows,
            "rows": [],
            "retention_hours": RETENTION_HOURS,
            "honesty_rule": "Fetch failure is not no-signal evidence; keep Social Watch dark/not_checked.",
        }

    per_ticker_counts: dict[str, Counter[str]] = defaultdict(Counter)
    per_ticker_items: dict[str, list[dict[str, Any]]] = defaultdict(list)
    scanned_subreddits: set[str] = set()
    for item in raw_items:
        created = _item_created_dt(item, generated=generated)
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
        health_rows = [source_health.get(sub) for sub in subs if source_health.get(sub)]
        health_status = "stale"
        if health_rows:
            order = {"active": 0, "thin_but_current": 1, "fringe": 2, "stale": 3}
            health_status = sorted(health_rows, key=lambda row: order.get(str(row.get("status")), 9))[0]["status"]
        interpretation_limit = _interpretation_limit(str(health_status), source_role)
        usefulness = _usefulness_for_item(
            latest,
            source_type=review_fields["source_type"],
            source_role=source_role,
            health_status=str(health_status),
        )
        row = {
            "id": f"reddit-{ticker}-{generated.date().isoformat()}",
            "source": "reddit",
            "source_group": review_fields["source_group"],
            "source_role": source_role,
            "source_type": review_fields["source_type"],
            "signal_kind": usefulness["signal_kind"],
            "usefulness": usefulness["usefulness"],
            "destroy_reason": usefulness["destroy_reason"],
            "subreddit": subs[0] if subs else "",
            "subreddits": subs,
            "source_health_status": str(health_status),
            "source_health_note": _source_health_note(str(health_status)),
            "source_interpretation_limit": interpretation_limit,
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
        "source_role": source_role,
        "subreddits_checked": sorted(scanned_subreddits or set(subreddits or [])),
        "source_health": source_health,
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
    source_role = _report_value(cache.get("source_role"))
    status = _report_value(cache.get("status"))
    lines = [
        "# Reddit Daily Scout Report",
        "",
        f"- Generated: {generated}",
        f"- Source group: {source_group}",
        f"- Source role: {source_role}",
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

    health = cache.get("source_health") or {}
    if health:
        lines.extend([
            "## Source Health",
            "",
        ])
        for subreddit, row in sorted(health.items()):
            lines.append(
                f"- r/{subreddit}: {row.get('status')} | posts 24h/7d/30d "
                f"{row.get('posts_seen_24h')}/{row.get('posts_seen_7d')}/{row.get('posts_seen_30d')} | "
                f"median upvotes/comments {row.get('median_score_observed')}/{row.get('median_comments_observed')} | "
                f"noise {row.get('promo_noise_ratio')}"
            )
        lines.append("")

    repeat = cache.get("repeat_snapshot") or {}
    if repeat:
        lines.extend([
            "## Repeat Snapshot Comparison",
            "",
            f"- Status: {_report_value(repeat.get('status'))}",
            f"- Prior compact snapshots: {_report_value(repeat.get('prior_snapshot_count'), '0')}",
            f"- Window: {_report_value(repeat.get('window_days'), str(DEFAULT_HISTORY_WINDOW_DAYS))} days",
            f"- Note: {_report_value(repeat.get('message'))}",
            "",
        ])
        latest_prior = repeat.get("latest_prior_snapshot") or {}
        if latest_prior:
            lines.append(
                f"- Latest prior: {_report_value(latest_prior.get('scan_date'))} | "
                f"status {_report_value(latest_prior.get('status'))} | "
                f"topics {_report_value(latest_prior.get('topic_count'), '0')}"
            )
            lines.append("")
        for title, key, empty in (
            ("New Topics", "new_topics", "No new topics versus the latest prior snapshot."),
            ("Getting Louder", "getting_louder", "No topic is materially louder versus the latest prior snapshot."),
            ("Fading", "fading", "No prior topic faded materially in this scan."),
            ("New Cross-Subreddit Spread", "cross_subreddit_spread", "No new cross-subreddit spread versus the latest prior snapshot."),
        ):
            rows_for_section = repeat.get(key) or []
            lines.extend([f"### {title}", ""])
            if not rows_for_section:
                lines.append(empty)
            for row in rows_for_section[:8]:
                lines.append(
                    f"- {_report_value(row.get('topic'), 'SOCIAL')}: "
                    f"now {_report_value(row.get('current_attention'), '0')} attention / "
                    f"prior {_report_value(row.get('prior_attention'), '0')} | "
                    f"subs {', '.join(row.get('subreddits') or []) or 'none'} | "
                    f"{_report_value(row.get('summary'), '')}"
                )
            lines.append("")

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

    ranked = [row for row in rows if row.get("signal_kind") != "destroy/noise"]
    destroyed = [row for row in rows if row.get("signal_kind") == "destroy/noise" or row.get("destroy_reason")]

    lines.extend([
        "## Ranked Prompts",
        "",
    ])
    for idx, row in enumerate(ranked[:max_rows], 1):
        ticker = (row.get("tickers") or [""])[0] or row.get("ticker") or "SOCIAL"
        subreddit = ", ".join(row.get("subreddits") or [row.get("subreddit") or ""])
        source_time = row.get("source_time_label") or row.get("last_seen") or row.get("created_utc")
        link = _report_value(row.get("permalink"), "not supplied")
        lines.extend([
            f"### {idx}. {ticker} - {_report_value(row.get('summary'), 'untitled Reddit prompt')}",
            "",
            f"- Source/time: r/{_report_value(subreddit, 'unknown')} | {_report_value(source_time)}",
            f"- Collector score: {_report_value(row.get('collector_score'), '0')} | mentions {_report_value(row.get('mentions'), '0')} | z {_report_value(row.get('velocity_z'), 'n/a')}",
            f"- Source health: {_report_value(row.get('source_health_status'))} | {_report_value(row.get('source_interpretation_limit'))}",
            f"- Source type: {_report_value(row.get('source_type'))}",
            f"- Signal kind: {_report_value(row.get('signal_kind'))} | usefulness {_report_value(row.get('usefulness'))}",
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
    if destroyed:
        lines.extend([
            "## Destroy / Noise",
            "",
        ])
        for row in destroyed[:max_rows]:
            ticker = (row.get("tickers") or [""])[0] or row.get("ticker") or "SOCIAL"
            lines.append(
                f"- {ticker}: {_report_value(row.get('summary'))} | "
                f"{_report_value(row.get('destroy_reason'), 'demoted as low-usefulness social noise')}"
            )
        lines.append("")
    return "\n".join(lines)


def write_scout_report(cache: dict[str, Any], *, out: str) -> Path:
    return _atomic_write_text(out, build_scout_report(cache))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _snapshot_date(value: Any) -> str:
    parsed = _parse_dt(value)
    return parsed.astimezone(ET).date().isoformat() if parsed else "unknown"


def _row_snapshot_mentions(row: dict[str, Any]) -> int:
    series = row.get("mention_series")
    if isinstance(series, list):
        series_total = sum(int(_safe_float(value)) for value in series)
    else:
        series_total = 0
    current = int(_safe_float(row.get("current_mentions") or row.get("mentions")))
    snippets = row.get("snippets") if isinstance(row.get("snippets"), list) else []
    return max(series_total, current, len(snippets), 1)


def _row_attention_score(row: dict[str, Any]) -> float:
    mentions = _row_snapshot_mentions(row)
    score = max(_safe_float(row.get("score_observed")), 0.0)
    comments = max(_safe_float(row.get("comment_count_observed")), 0.0)
    collector = max(_safe_float(row.get("collector_score")), 0.0)
    attention = (
        mentions * 3.0
        + min(score, 5_000.0) / 500.0
        + min(comments, 1_000.0) / 100.0
        + collector / 25.0
    )
    if row.get("signal_kind") == "destroy/noise":
        attention *= 0.5
    return round(attention, 2)


def _history_topic_from_row(row: dict[str, Any]) -> dict[str, Any]:
    topic = _row_topic(row)
    return {
        "topic": topic,
        "tickers": row.get("tickers") or ([topic] if topic != "SOCIAL" else []),
        "summary": _snippet(row.get("summary") or row.get("title_snippet") or row.get("body_snippet"), limit=180),
        "signal_kind": row.get("signal_kind") or row.get("source_type") or "research_prompt",
        "usefulness": row.get("usefulness") or "medium",
        "source_type": row.get("source_type") or "research_prompt",
        "source_health_status": row.get("source_health_status") or "unknown",
        "source_interpretation_limit": row.get("source_interpretation_limit") or "",
        "subreddits": sorted({
            str(sub)
            for sub in (row.get("subreddits") or [row.get("subreddit") or ""])
            if str(sub).strip()
        }),
        "snapshot_mentions": _row_snapshot_mentions(row),
        "attention_score": _row_attention_score(row),
        "collector_score": _safe_float(row.get("collector_score")),
        "score_observed": _parse_observed_count(row.get("score_observed")) or 0,
        "comment_count_observed": _parse_observed_count(row.get("comment_count_observed")) or 0,
        "destroy_reason": row.get("destroy_reason") or "",
        "blocker_before_action": row.get("blocker_before_action") or "Reddit is not a trade trigger.",
        "suggested_next_check": row.get("suggested_next_check") or "",
        "permalink": row.get("permalink") or "",
    }


def build_snapshot_history_record(cache: dict[str, Any]) -> dict[str, Any]:
    generated = cache.get("generated_at") or cache.get("checked_at") or _iso(_now_et())
    topics = [_history_topic_from_row(row) for row in cache.get("rows") or [] if isinstance(row, dict)]
    topics.sort(key=lambda row: (float(row.get("attention_score") or 0.0), row.get("topic") or ""), reverse=True)
    seed = json.dumps(
        {
            "generated_at": generated,
            "source_group": cache.get("source_group") or "custom",
            "status": cache.get("status") or "",
            "topics": [
                {
                    "topic": topic.get("topic"),
                    "attention_score": topic.get("attention_score"),
                    "snapshot_mentions": topic.get("snapshot_mentions"),
                }
                for topic in topics
            ],
        },
        sort_keys=True,
    )
    return {
        "schema": SNAPSHOT_HISTORY_SCHEMA,
        "scan_id": hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()[:16],
        "generated_at": generated,
        "scan_date": _snapshot_date(generated),
        "source_group": cache.get("source_group") or "custom",
        "source_role": cache.get("source_role") or "",
        "status": cache.get("status") or "unknown",
        "subreddits_checked": cache.get("subreddits_checked") or [],
        "source_health": cache.get("source_health") or {},
        "topic_count": len(topics),
        "topics": topics,
        "failure_count": len(cache.get("failures") or []),
        "honesty_rule": "Compact Reddit history is for scout trend comparison only; never a trade trigger.",
    }


def load_snapshot_history(path: str | Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    p = Path(path)
    if not p.is_file():
        return []
    records: list[dict[str, Any]] = []
    with p.open(encoding="utf-8-sig") as fh:
        text = fh.read().strip()
    if not text:
        return []
    if text.startswith("["):
        payload = json.loads(text)
        if isinstance(payload, list):
            records.extend(row for row in payload if isinstance(row, dict))
        return records
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def append_snapshot_history(path: str | Path, record: dict[str, Any]) -> dict[str, Any]:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = load_snapshot_history(p)
    existing_ids = {str(row.get("scan_id") or "") for row in existing}
    appended = str(record.get("scan_id") or "") not in existing_ids
    if appended:
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True))
            fh.write("\n")
    return {
        "path": str(p),
        "appended": appended,
        "scan_id": record.get("scan_id"),
        "records_before": len(existing),
        "records_after": len(existing) + (1 if appended else 0),
    }


def _record_generated_dt(record: dict[str, Any]) -> datetime | None:
    return _parse_dt(record.get("generated_at") or record.get("checked_at"))


def _latest_records_by_day(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_day: dict[str, dict[str, Any]] = {}
    for record in records:
        day = str(record.get("scan_date") or _snapshot_date(record.get("generated_at")))
        if day == "unknown":
            continue
        existing = by_day.get(day)
        if not existing:
            by_day[day] = record
            continue
        existing_dt = _record_generated_dt(existing)
        record_dt = _record_generated_dt(record)
        if record_dt and (not existing_dt or record_dt > existing_dt):
            by_day[day] = record
    return [by_day[day] for day in sorted(by_day)]


def _topic_map(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for topic in record.get("topics") or []:
        if not isinstance(topic, dict):
            continue
        key = str(topic.get("topic") or "").strip().upper()
        if not key:
            continue
        prior = out.get(key)
        if not prior:
            out[key] = dict(topic)
            continue
        prior["attention_score"] = round(
            _safe_float(prior.get("attention_score")) + _safe_float(topic.get("attention_score")),
            2,
        )
        prior["snapshot_mentions"] = int(_safe_float(prior.get("snapshot_mentions"))) + int(_safe_float(topic.get("snapshot_mentions")))
        prior["subreddits"] = sorted(set(prior.get("subreddits") or []) | set(topic.get("subreddits") or []))
    return out


def _brief_topic(topic: dict[str, Any], *, prior: dict[str, Any] | None = None) -> dict[str, Any]:
    prior = prior or {}
    return {
        "topic": topic.get("topic"),
        "summary": topic.get("summary") or "",
        "current_attention": topic.get("attention_score") or 0,
        "prior_attention": prior.get("attention_score") or 0,
        "current_mentions": topic.get("snapshot_mentions") or 0,
        "prior_mentions": prior.get("snapshot_mentions") or 0,
        "subreddits": topic.get("subreddits") or [],
        "prior_subreddits": prior.get("subreddits") or [],
        "signal_kind": topic.get("signal_kind") or "",
        "usefulness": topic.get("usefulness") or "",
        "suggested_next_check": topic.get("suggested_next_check") or "",
    }


def build_repeat_snapshot_comparison(
    current_cache: dict[str, Any],
    history_records: list[dict[str, Any]],
    *,
    window_days: int = DEFAULT_HISTORY_WINDOW_DAYS,
) -> dict[str, Any]:
    current_record = build_snapshot_history_record(current_cache)
    current_dt = _record_generated_dt(current_record) or _now_et()
    current_group = current_record.get("source_group")
    cutoff = current_dt.astimezone(UTC) - timedelta(days=max(int(window_days), 1))
    prior_records = []
    for record in history_records:
        if record.get("source_group") != current_group:
            continue
        if record.get("scan_id") == current_record.get("scan_id"):
            continue
        record_dt = _record_generated_dt(record)
        if not record_dt or record_dt.astimezone(UTC) < cutoff:
            continue
        if record_dt.astimezone(UTC) >= current_dt.astimezone(UTC):
            continue
        prior_records.append(record)
    prior_daily = _latest_records_by_day(prior_records)
    current_topics = _topic_map(current_record)
    if not prior_daily:
        return {
            "status": "baseline_started",
            "source_group": current_group,
            "window_days": window_days,
            "prior_snapshot_count": 0,
            "current_snapshot": {
                "generated_at": current_record.get("generated_at"),
                "topic_count": current_record.get("topic_count"),
                "status": current_record.get("status"),
            },
            "message": "No prior compact snapshots for this source group. This run starts the baseline; the next scan can show new/louder/fading topics.",
            "new_topics": [],
            "getting_louder": [],
            "fading": [],
            "cross_subreddit_spread": [],
        }

    previous = prior_daily[-1]
    previous_topics = _topic_map(previous)
    previous_days = [record.get("scan_date") for record in prior_daily if record.get("scan_date")]
    baseline_scores: dict[str, list[float]] = defaultdict(list)
    for record in prior_daily:
        topic_map = _topic_map(record)
        for topic in set(topic_map) | set(current_topics):
            baseline_scores[topic].append(_safe_float(topic_map.get(topic, {}).get("attention_score")))

    new_topics = []
    louder = []
    fading = []
    cross_spread = []
    for topic, current in sorted(current_topics.items()):
        prior = previous_topics.get(topic)
        current_attention = _safe_float(current.get("attention_score"))
        prior_attention = _safe_float((prior or {}).get("attention_score"))
        baseline = sum(baseline_scores.get(topic, [])) / max(len(baseline_scores.get(topic, [])), 1)
        current_subs = set(current.get("subreddits") or [])
        prior_subs = set((prior or {}).get("subreddits") or [])
        if not prior:
            new_topics.append(_brief_topic(current))
        elif current_attention > prior_attention and (
            current_attention >= prior_attention * 1.5
            or current_attention - prior_attention >= 2.0
            or (baseline and current_attention >= baseline * 1.5)
        ):
            louder.append(_brief_topic(current, prior=prior))
        if len(current_subs) > 1 and (not prior_subs or len(current_subs) > len(prior_subs)):
            cross_spread.append(_brief_topic(current, prior=prior))

    for topic, prior in sorted(previous_topics.items()):
        current = current_topics.get(topic)
        prior_attention = _safe_float(prior.get("attention_score"))
        current_attention = _safe_float((current or {}).get("attention_score"))
        if not current or (prior_attention > 0 and current_attention <= prior_attention * 0.5 and prior_attention - current_attention >= 2.0):
            fading.append(_brief_topic(current or {"topic": topic, "subreddits": []}, prior=prior))

    rank_key = lambda row: float(row.get("current_attention") or row.get("prior_attention") or 0.0)
    return {
        "status": "compared",
        "source_group": current_group,
        "window_days": window_days,
        "prior_snapshot_count": len(prior_daily),
        "prior_scan_dates": previous_days,
        "latest_prior_snapshot": {
            "generated_at": previous.get("generated_at"),
            "scan_date": previous.get("scan_date"),
            "status": previous.get("status"),
            "topic_count": previous.get("topic_count"),
        },
        "current_snapshot": {
            "generated_at": current_record.get("generated_at"),
            "scan_date": current_record.get("scan_date"),
            "status": current_record.get("status"),
            "topic_count": current_record.get("topic_count"),
        },
        "new_topics": sorted(new_topics, key=rank_key, reverse=True)[:10],
        "getting_louder": sorted(louder, key=rank_key, reverse=True)[:10],
        "fading": sorted(fading, key=rank_key, reverse=True)[:10],
        "cross_subreddit_spread": sorted(cross_spread, key=rank_key, reverse=True)[:10],
        "message": "Comparison is based on compact per-scan topic presence and attention, not Reddit truth or trade evidence.",
    }


def _history_record_to_cache(record: dict[str, Any]) -> dict[str, Any]:
    rows = []
    generated = record.get("generated_at")
    for topic in record.get("topics") or []:
        if not isinstance(topic, dict):
            continue
        rows.append({
            "_snapshot_generated_at": generated,
            "tickers": topic.get("tickers") or ([topic.get("topic")] if topic.get("topic") else []),
            "summary": topic.get("summary") or topic.get("topic") or "",
            "signal_kind": topic.get("signal_kind") or "research_prompt",
            "source_type": topic.get("source_type") or "research_prompt",
            "subreddits": topic.get("subreddits") or [],
            "collector_score": topic.get("collector_score") or 0,
            "attention_score": topic.get("attention_score") or 0,
            "current_mentions": topic.get("snapshot_mentions") or 0,
            "mentions": topic.get("snapshot_mentions") or 0,
            "score_observed": topic.get("score_observed") or 0,
            "comment_count_observed": topic.get("comment_count_observed") or 0,
            "destroy_reason": topic.get("destroy_reason") or "",
        })
    return {
        "generated_at": generated,
        "checked_at": generated,
        "source_group": record.get("source_group") or "custom",
        "source_role": record.get("source_role") or "",
        "status": record.get("status") or "unknown",
        "rows": rows,
    }


def _cache_rows(caches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cache in caches:
        if cache.get("schema") == SNAPSHOT_HISTORY_SCHEMA:
            cache = _history_record_to_cache(cache)
        snapshot_generated_at = cache.get("generated_at") or cache.get("checked_at")
        for row in cache.get("rows") or []:
            if isinstance(row, dict):
                copied = dict(row)
                copied.setdefault("_snapshot_generated_at", snapshot_generated_at)
                rows.append(copied)
    return rows


def _row_topic(row: dict[str, Any]) -> str:
    ticker = (row.get("tickers") or [""])[0] or row.get("ticker")
    if ticker:
        return str(ticker).upper()
    summary = str(row.get("summary") or "").strip()
    return _snippet(summary, limit=60) or "SOCIAL"


def _row_date(row: dict[str, Any]) -> str:
    parsed = _parse_dt(row.get("_snapshot_generated_at") or row.get("last_seen") or row.get("created_utc") or row.get("first_seen"))
    return parsed.astimezone(UTC).date().isoformat() if parsed else "unknown"


def build_weekly_pattern_report(caches: list[dict[str, Any]] | dict[str, Any], *, max_topics: int = 10) -> str:
    cache_list = [caches] if isinstance(caches, dict) else list(caches)
    rows = _cache_rows(cache_list)
    generated = _iso(_now_et())
    lines = [
        "# Reddit Weekly Pattern Report",
        "",
        f"- Generated: {generated}",
        "- Rule: weekly Reddit patterns are research prompts only; no trade trigger.",
        "",
    ]
    if not rows:
        lines.extend([
            "## No Pattern Data",
            "",
            "No staged Reddit rows were supplied. Missing Reddit remains not_checked, not checked clear.",
        ])
        return "\n".join(lines)

    by_day_topic: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        topic = _row_topic(row)
        day = _row_date(row)
        by_topic[topic].append(row)
        bucket = by_day_topic[day].setdefault(
            topic,
            {
                "attention": 0.0,
                "rows": 0,
                "subreddits": set(),
                "signal_kinds": Counter(),
                "destroy_count": 0,
                "counter_count": 0,
                "score": 0.0,
            },
        )
        attention = _safe_float(row.get("attention_score"))
        if attention <= 0:
            attention = _row_attention_score(row)
        bucket["attention"] = round(float(bucket["attention"]) + attention, 2)
        bucket["rows"] = int(bucket["rows"]) + 1
        bucket["subreddits"].update(
            sub for sub in row.get("subreddits") or [row.get("subreddit") or ""] if sub
        )
        signal_kind = str(row.get("signal_kind") or row.get("source_type") or "research_prompt")
        bucket["signal_kinds"][signal_kind] += 1
        if row.get("destroy_reason") or row.get("signal_kind") == "destroy/noise":
            bucket["destroy_count"] = int(bucket["destroy_count"]) + 1
        if "counter" in signal_kind.lower():
            bucket["counter_count"] = int(bucket["counter_count"]) + 1
        bucket["score"] = round(float(bucket["score"]) + _safe_float(row.get("collector_score")), 2)

    all_days = sorted(day for day in by_day_topic if day != "unknown")
    if not all_days:
        all_days = ["unknown"]
    summaries = []
    for topic, topic_rows in by_topic.items():
        subreddit_set = sorted({sub for row in topic_rows for sub in row.get("subreddits") or [row.get("subreddit") or ""] if sub})
        midpoint = max(len(all_days) // 2, 1)
        first_half = all_days[:midpoint]
        second_half = all_days[midpoint:] or all_days[-1:]
        early_values = [
            _safe_float(by_day_topic.get(day, {}).get(topic, {}).get("attention"))
            for day in first_half
        ]
        late_values = [
            _safe_float(by_day_topic.get(day, {}).get(topic, {}).get("attention"))
            for day in second_half
        ]
        early = round(sum(early_values) / max(len(early_values), 1), 2)
        late = round(sum(late_values) / max(len(late_values), 1), 2)
        if early <= 0 and late > 0:
            trend = "getting_louder"
        elif late > early and (late >= early * 1.5 or late - early >= 2.0):
            trend = "getting_louder"
        elif early > 0 and (late <= 0 or (late <= early * 0.5 and early - late >= 2.0)):
            trend = "fading"
        else:
            trend = "persistent"
        signal_kinds = Counter(str(row.get("signal_kind") or row.get("source_type") or "research_prompt") for row in topic_rows)
        destroy_count = sum(1 for row in topic_rows if row.get("destroy_reason") or row.get("signal_kind") == "destroy/noise")
        counter_count = sum(1 for row in topic_rows if "counter" in str(row.get("signal_kind") or "").lower())
        score = round(sum(_safe_float(row.get("collector_score")) for row in topic_rows), 2)
        summaries.append({
            "topic": topic,
            "rows": topic_rows,
            "subreddits": subreddit_set,
            "dates": [day for day in all_days if topic in by_day_topic.get(day, {})],
            "early": early,
            "late": late,
            "trend": trend,
            "signal_kind": signal_kinds.most_common(1)[0][0] if signal_kinds else "research_prompt",
            "destroy_count": destroy_count,
            "counter_count": counter_count,
            "score": score,
        })
    summaries.sort(key=lambda item: (item["trend"] == "getting_louder", len(item["subreddits"]), item["score"]), reverse=True)

    lines.extend(["## Recurring Topics", ""])
    for item in summaries[:max_topics]:
        lines.append(
            f"- {item['topic']}: {len(item['rows'])} staged item(s), "
            f"{item['trend']} (early {item['early']} -> late {item['late']}), "
            f"subreddits {', '.join(item['subreddits']) or 'unknown'}, "
            f"signal {item['signal_kind']}, score {item['score']}"
        )
    lines.append("")

    louder = [item for item in summaries if item["trend"] == "getting_louder"]
    fading = [item for item in summaries if item["trend"] == "fading"]
    cross = [item for item in summaries if len(item["subreddits"]) > 1]
    counters = [item for item in summaries if item["counter_count"]]
    destroyed = [row for row in rows if row.get("destroy_reason") or row.get("signal_kind") == "destroy/noise"]

    sections = [
        ("Themes Getting Louder", louder, "No getting-louder theme in supplied staged rows."),
        ("Themes Fading", fading, "No fading theme in supplied staged rows."),
        ("Cross-Subreddit Spread", cross, "No topic crossed multiple subreddits in supplied staged rows."),
        ("Counter-Thesis / Risk Warnings", counters, "No counter-thesis cluster in supplied staged rows."),
    ]
    for title, items, empty in sections:
        lines.extend([f"## {title}", ""])
        if not items:
            lines.append(empty)
        for item in items[:max_topics]:
            lines.append(
                f"- {item['topic']}: {item['trend']} "
                f"(early {item['early']} -> late {item['late']}) across "
                f"{', '.join(item['subreddits']) or 'unknown'}; "
                "verify with non-social sources before changing research priority."
            )
        lines.append("")

    lines.extend(["## Destroy / Noise Bucket", ""])
    if not destroyed:
        lines.append("No explicit destroy/noise rows in supplied staged rows.")
    for row in destroyed[:max_topics]:
        lines.append(
            f"- {_row_topic(row)}: {_report_value(row.get('summary'))} | "
            f"{_report_value(row.get('destroy_reason'), 'low-usefulness social noise')}"
        )
    return "\n".join(lines)


def write_weekly_pattern_report(caches: list[dict[str, Any]] | dict[str, Any], *, out: str) -> Path:
    return _atomic_write_text(out, build_weekly_pattern_report(caches))


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
    parser.add_argument("--weekly-report-out", help="Optional Markdown weekly pattern report path, usually under tmp/")
    parser.add_argument("--pattern-input", action="append", default=[], help="Optional prior staged social_watch cache JSON for weekly pattern reports")
    parser.add_argument("--snapshot-history", help="Optional compact JSONL history path for repeat-snapshot louder/fading comparison")
    parser.add_argument("--history-window-days", type=int, default=DEFAULT_HISTORY_WINDOW_DAYS, help="Lookback window for compact snapshot comparisons")
    parser.add_argument("--no-history-append", action="store_true", help="Read snapshot history for reports but do not append the current scan")
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
    history_records: list[dict[str, Any]] = []
    history_append_report = None
    if args.snapshot_history:
        history_records = load_snapshot_history(args.snapshot_history)
        cache["repeat_snapshot"] = build_repeat_snapshot_comparison(
            cache,
            history_records,
            window_days=args.history_window_days,
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
    weekly_report_path = None
    if args.weekly_report_out and not args.dry_run:
        pattern_caches = [cache]
        pattern_caches.extend(_load_json(path) for path in args.pattern_input)
        if history_records:
            current_dt = _parse_dt(cache.get("generated_at")) or _now_et()
            cutoff = current_dt.astimezone(UTC) - timedelta(days=max(int(args.history_window_days), 1))
            for record in history_records:
                record_dt = _record_generated_dt(record)
                if record.get("source_group") != cache.get("source_group"):
                    continue
                if record_dt and record_dt.astimezone(UTC) < cutoff:
                    continue
                pattern_caches.append(record)
        weekly_report_path = str(write_weekly_pattern_report(pattern_caches, out=args.weekly_report_out))
        cache["weekly_pattern_report"] = weekly_report_path
    if args.snapshot_history:
        if not args.dry_run and not args.no_history_append:
            history_append_report = append_snapshot_history(
                args.snapshot_history,
                build_snapshot_history_record(cache),
            )
        else:
            history_append_report = {
                "path": args.snapshot_history,
                "appended": False,
                "records_before": len(history_records),
                "records_after": len(history_records),
                "reason": "dry_run" if args.dry_run else "no_history_append",
            }
        cache["snapshot_history"] = history_append_report
    if not args.dry_run:
        _atomic_write_json(args.out, cache)
    if args.format == "json":
        print(json.dumps({
            "cache": cache,
            "written": None if args.dry_run else args.out,
            "research_queue": rq_report,
            "report": report_path,
            "weekly_report": weekly_report_path,
            "snapshot_history": history_append_report,
        }, indent=2, sort_keys=True))
    else:
        print(format_text(cache))
        if not args.dry_run:
            print(f"wrote: {args.out}")
        if report_path:
            print(f"report: {report_path}")
        if weekly_report_path:
            print(f"weekly report: {weekly_report_path}")
        if history_append_report:
            state = "appended" if history_append_report.get("appended") else "not appended"
            print(f"snapshot history: {state} {history_append_report.get('path')}")
    return 0 if cache.get("status") != "not_checked" or failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
