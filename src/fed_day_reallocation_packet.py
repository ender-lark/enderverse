#!/usr/bin/env python3
"""Build the June 17 Fed-day reallocation packet.

The packet is candidate-only. It combines the existing reallocation brief with
same-day broker exposure, UW endpoint proof, live 52-week-high chart data, and
research queue context. It never executes trades or selects option contracts.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from execution_plan import funding_reality_check, load_accounts, plan_buy
from reallocation_brief import build_reallocation_brief

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent

MANUAL_WATCHLIST = {
    "AMZN",
    "AVAV",
    "AVGO",
    "BMNR",
    "ELF",
    "FN",
    "GOOGL",
    "HOOD",
    "KTOS",
    "LEU",
    "MP",
    "MSFT",
    "NVDA",
    "SOFI",
    "UUUU",
    "VRT",
    "GRNY",
    "IVES",
    "MAGS",
    "GRNJ",
    "SMH",
    "QQQ",
    "SPY",
    "XLE",
    "XOP",
    "XLU",
    "XLRE",
}

DEEP_DISCOUNT_FOCUS = ["BMNR", "LEU", "AVAV", "KTOS", "ELF", "SOFI", "UUUU", "MP", "HOOD"]
QUALITY_PULLBACK_FOCUS = ["MSFT", "AVGO", "FN", "VRT", "AMZN", "NVDA", "GOOGL"]
BASE_ADD_TICKERS = ["GOOGL", "MSFT"]
FUNDING_ORDER = ["IVES", "GRNY", "MAGS", "SMH"]

CASH_LIKE = {"CASH", "FCASH", "FDRXX", "SPAXX"}
NON_EQUITY = {"BTC", "ETH", "SOL", "AAVE", "HYPE", "TRUMP"}

LIVE_NOTION_RESEARCH = {
    "BMNR": {
        "status": "Working",
        "priority": "High",
        "state": "MONITOR",
        "line": "Live Research Queue keeps BMNR monitor-first until mNAV, ETH-per-share, preferred coverage, and settlement-era price/flow are resolved.",
        "url": "https://app.notion.com/p/37ac50314bb681c09354df955c2e491d",
        "fetched_at": "2026-06-17T05:09:00Z",
    },
    "GOOGL": {
        "status": "Working",
        "priority": "High",
        "state": "WATCH",
        "line": "Live Research Queue keeps GOOGL staged around the tranche-2 trigger; financing is mixed-positive but still needs price/flow and dilution discipline.",
        "url": "https://app.notion.com/p/37ac50314bb68100b6ecda51e1a8479e",
        "fetched_at": "2026-06-17T05:09:00Z",
    },
    "AVGO": {
        "status": "Working",
        "priority": "Med",
        "state": "STAGE",
        "line": "Live AVGO diligence supports a high-quality pullback/swap candidate, but says stage during anti-semis rotation and FOMC risk.",
        "url": "https://app.notion.com/p/381c50314bb681a7a124cc8abf0fe78f",
        "fetched_at": "2026-06-17T05:10:00Z",
    },
}

FED_SOURCE_LINKS = {
    "federal_reserve_calendar": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
    "cme_fedwatch": "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html",
}


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            if not text.endswith("\n"):
                fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _ticker(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text or text in CASH_LIKE or text in NON_EQUITY:
        return ""
    if len(text) > 12:
        return ""
    if not all(ch.isalnum() or ch in {".", "-"} for ch in text):
        return ""
    return text


def _fmt_usd(value: Any) -> str:
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "$0"


def _fmt_pct(value: Any) -> str:
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def _clean_text(value: Any) -> str:
    text = str(value or "")
    return (
        text.replace("Ã¢â‚¬Â¦", "...")
        .replace("â€¦", "...")
        .replace("Ã¢â‚¬â€�", "-")
        .replace("â€”", "-")
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _date_from_ts(ts: Any) -> str:
    try:
        return datetime.fromtimestamp(int(ts), timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def _combined_positions(account_positions: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for key in ("combined_positions", "tracked_combined_positions"):
        for row in account_positions.get(key) or []:
            if not isinstance(row, dict):
                continue
            ticker = _ticker(row.get("ticker"))
            if not ticker:
                continue
            current = out.setdefault(
                ticker,
                {"ticker": ticker, "market_value": 0.0, "shares": 0.0, "tracked": False, "accounts": set(), "owners": set()},
            )
            current["market_value"] = max(float(current["market_value"]), float(row.get("market_value") or 0.0))
            current["shares"] = max(float(current["shares"]), float(row.get("shares") or 0.0))
            current["tracked"] = bool(current["tracked"] or row.get("tracked"))
            if row.get("account"):
                current["accounts"].add(str(row.get("account")))
            for owner in row.get("owners") or []:
                current["owners"].add(str(owner))
    for row in out.values():
        row["accounts"] = sorted(row["accounts"])
        row["owners"] = sorted(row["owners"])
    return out


def _collect_from_feed(feed: dict[str, Any]) -> set[str]:
    tickers: set[str] = set()
    for row in feed.get("actions") or []:
        if isinstance(row, dict):
            tickers.add(_ticker(row.get("ticker")))
    for row in feed.get("fresh_signals") or []:
        if isinstance(row, dict):
            tickers.add(_ticker(row.get("ticker")))
    for row in feed.get("event_risk") or []:
        if not isinstance(row, dict):
            continue
        for ticker in row.get("tickers") or []:
            tickers.add(_ticker(ticker))
    for row in ((feed.get("target_drift") or {}).get("rows") or []):
        if isinstance(row, dict):
            tickers.add(_ticker(row.get("ticker")))
    for row in ((feed.get("asymmetric_opportunities") or {}).get("rows") or []):
        if isinstance(row, dict):
            tickers.add(_ticker(row.get("ticker")))
    combined_rows = (((feed.get("portfolio_views") or {}).get("views") or {}).get("combined") or {}).get("rows") or []
    for row in combined_rows:
        if isinstance(row, dict):
            tickers.add(_ticker(row.get("ticker")))
    return {ticker for ticker in tickers if ticker}


def _collect_watchlist(
    *,
    feed: dict[str, Any],
    account_positions: dict[str, Any],
    top_prospects: dict[str, Any],
    research_queue: dict[str, Any],
    source_calls: list[dict[str, Any]],
) -> list[str]:
    tickers = set(MANUAL_WATCHLIST)
    tickers.update(_combined_positions(account_positions))
    tickers.update(_collect_from_feed(feed))
    tickers.update(_ticker(key) for key in top_prospects.keys())
    for row in research_queue.get("pending") or []:
        if isinstance(row, dict):
            tickers.add(_ticker(row.get("ticker")))
    for row in source_calls or []:
        if isinstance(row, dict):
            tickers.add(_ticker(row.get("ticker")))
    return sorted(ticker for ticker in tickers if ticker)


def fetch_yahoo_quote(ticker: str) -> dict[str, Any]:
    encoded = urllib.parse.quote(ticker)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=1y&interval=1d"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    checked_at = _utc_now()
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "ticker": ticker,
            "status": "not_checked",
            "checked_at": checked_at,
            "error": str(exc)[:180],
        }

    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not isinstance(result, dict):
        return {"ticker": ticker, "status": "not_checked", "checked_at": checked_at, "error": "no chart result"}

    meta = result.get("meta") or {}
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    highs = [float(v) for v in quote.get("high") or [] if isinstance(v, (int, float))]
    closes = [float(v) for v in quote.get("close") or [] if isinstance(v, (int, float))]
    timestamps = result.get("timestamp") or []

    price = meta.get("regularMarketPrice")
    if not isinstance(price, (int, float)) and closes:
        price = closes[-1]
    high = meta.get("fiftyTwoWeekHigh")
    if not isinstance(high, (int, float)) and highs:
        high = max(highs)
    if not isinstance(price, (int, float)) or not isinstance(high, (int, float)) or high <= 0:
        return {"ticker": ticker, "status": "not_checked", "checked_at": checked_at, "error": "missing price or 52-week high"}

    high_date = ""
    if highs and timestamps:
        max_high = max(highs)
        for idx, value in enumerate(highs):
            if value == max_high and idx < len(timestamps):
                high_date = _date_from_ts(timestamps[idx])
                break
    latest_ts = timestamps[-1] if timestamps else meta.get("regularMarketTime")
    return {
        "ticker": ticker,
        "status": "has_data",
        "checked_at": checked_at,
        "price": round(float(price), 4),
        "fifty_two_week_high": round(float(high), 4),
        "pct_below_high": round((float(price) / float(high) - 1.0) * 100.0, 2),
        "latest_price_date": _date_from_ts(latest_ts),
        "high_date": high_date,
        "currency": meta.get("currency") or "USD",
        "source": "Yahoo Finance chart endpoint",
    }


def _source_context(
    ticker: str,
    *,
    top_prospects: dict[str, Any],
    source_calls: list[dict[str, Any]],
    research_queue: dict[str, Any],
) -> dict[str, Any]:
    tags: list[str] = []
    flags: list[str] = []
    prospect = top_prospects.get(ticker) or {}
    direction = str(prospect.get("direction") or "").lower()
    if prospect:
        label = "Fundstrat top-list" if direction == "long" else ("Fundstrat bottom/avoid-list" if direction == "avoid" else "Fundstrat watch")
        tags.append(label)
        if direction == "avoid":
            flags.append("source_disagreement")
    for row in source_calls or []:
        if not isinstance(row, dict) or _ticker(row.get("ticker")) != ticker:
            continue
        source = str(row.get("source") or row.get("fundstrat_lane") or "source_call")
        tier = str(row.get("tier") or "")
        tags.append(f"{source} {tier}".strip())
        if "avoid" in str(row.get("direction") or "").lower():
            flags.append("source_disagreement")
    for row in research_queue.get("pending") or []:
        if isinstance(row, dict) and _ticker(row.get("ticker")) == ticker:
            tags.append(f"repo research queue {row.get('status') or 'pending'}")
    live = LIVE_NOTION_RESEARCH.get(ticker)
    if live:
        tags.append(f"Notion {live['status']} {live['state']}")
    return {
        "tags": sorted(set(tags)),
        "flags": sorted(set(flags)),
        "top_prospect_direction": direction or "",
        "notion": live or {},
    }


def _disconfirmation(ticker: str, source_context: dict[str, Any]) -> str:
    specific = {
        "BMNR": "Do not add until financing impact, mNAV, ETH-per-share, preferred coverage, and crypto tape resolve.",
        "LEU": "Needs uranium/HALEU flow and policy confirmation; size is already meaningful.",
        "UUUU": "Critical-minerals pullback is not enough while Fundstrat source context remains avoid/bottom-list.",
        "MP": "Needs rare-earth policy/order-flow confirmation; discount alone is not a buy signal.",
        "AVAV": "Deep pullback needs defense order, margin, and flow confirmation before capital competes with GOOGL/MSFT.",
        "KTOS": "Fundstrat bottom-list conflict means discount is research-only until source reconciliation changes.",
        "ELF": "Fundstrat bottom-list conflict means no promotion without business-quality reversal evidence.",
        "SOFI": "Fundstrat bottom-list conflict and small current exposure make this research-only.",
        "HOOD": "Fundstrat bottom-list conflict; crypto/broker beta must confirm before any add review.",
        "AVGO": "Advance only if post-FOMC tape and fresh flow beat GOOGL/MSFT on capital efficiency.",
        "FN": "Advance only if optical/AI infrastructure evidence and flow beat the base packet.",
        "VRT": "Advance only if power/cooling flow and entry quality beat the base packet.",
        "AMZN": "Secondary add only if live source review is stronger than the funded GOOGL/MSFT packet.",
        "NVDA": "Already large; pullback is not enough unless target/sizing room and flow support it.",
        "GOOGL": "Do not deploy if Fed reaction, QQQ/SPY, yields, oil, or flow contradict the staged add.",
        "MSFT": "Do not deploy if the laggard thesis remains only valuation-based without live confirmation.",
    }
    if ticker in specific:
        return specific[ticker]
    if "source_disagreement" in source_context.get("flags", []):
        return "Source disagreement present; keep research-only until reconciled."
    return "Needs same-session price/flow and thesis confirmation before promotion."


def _score_discount(row: dict[str, Any], source_context: dict[str, Any]) -> float:
    discount = abs(float(row.get("pct_below_high") or 0.0))
    exposure = float(row.get("current_exposure_usd") or 0.0)
    source_bonus = 8.0 if any("top-list" in tag for tag in source_context.get("tags", [])) else 0.0
    source_penalty = 10.0 if "source_disagreement" in source_context.get("flags", []) else 0.0
    exposure_penalty = min(exposure / 100_000.0, 5.0)
    return round(discount + source_bonus - source_penalty - exposure_penalty, 2)


def _build_discount_rows(
    tickers: list[str],
    quotes: dict[str, dict[str, Any]],
    *,
    positions_by_ticker: dict[str, dict[str, Any]],
    total_book_value: float,
    top_prospects: dict[str, Any],
    source_calls: list[dict[str, Any]],
    research_queue: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        quote = quotes.get(ticker) or {}
        if quote.get("status") != "has_data":
            continue
        exposure = float((positions_by_ticker.get(ticker) or {}).get("market_value") or 0.0)
        context = _source_context(ticker, top_prospects=top_prospects, source_calls=source_calls, research_queue=research_queue)
        row = {
            **quote,
            "current_exposure_usd": round(exposure, 2),
            "current_exposure_pct": round(exposure / total_book_value * 100.0, 2) if total_book_value else 0.0,
            "source_tags": context["tags"],
            "source_flags": context["flags"],
            "disconfirmation": _disconfirmation(ticker, context),
            "research_status": (context.get("notion") or {}).get("state") or "",
            "rank_score": _score_discount({**quote, "current_exposure_usd": exposure}, context),
        }
        rows.append(row)
    return sorted(rows, key=lambda row: (float(row.get("pct_below_high") or 0.0), row.get("ticker") or ""))


def _uw_status(uw_results: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in uw_results.get("rows") or [] if isinstance(row, dict)]
    tickers = sorted({_ticker(row.get("ticker")) for row in rows if _ticker(row.get("ticker"))})
    return {
        "status": uw_results.get("status") or ("has_data" if rows else "not_checked"),
        "line": f"UW endpoint proof: {len(rows)} captured row(s); neutral/inconclusive rows do not promote trades.",
        "counts": uw_results.get("counts") or {},
        "checked_tickers": tickers,
        "honesty_rule": uw_results.get("honesty_rule") or "Neutral rows are proof of fetch only.",
        "newest_checked_at": uw_results.get("generated_at") or "",
    }


def _social_watch_status(feed: dict[str, Any]) -> dict[str, Any]:
    block = feed.get("social_watch")
    if isinstance(block, dict):
        return {
            "status": block.get("status") or "not_checked",
            "line": block.get("line") or "Social Watch present but not promoted.",
            "honesty_rule": block.get("honesty_rule") or "Watch-only.",
        }
    return {
        "status": "not_checked",
        "line": "Social Watch remains dark/deferred optional; no compliant cache supplied.",
        "honesty_rule": "Never turn social anomalies into trade cards.",
    }


def _find_add(reallocation: dict[str, Any], ticker: str) -> dict[str, Any]:
    for row in reallocation.get("rows") or []:
        if row.get("ticker") == ticker:
            return row
    return {}


def _find_trim(reallocation: dict[str, Any], ticker: str) -> dict[str, Any]:
    for row in reallocation.get("trims") or []:
        if row.get("ticker") == ticker:
            return row
    return {}


def _funding_band(reallocation: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ticker in FUNDING_ORDER:
        row = _find_trim(reallocation, ticker)
        if not row:
            continue
        out.append({
            "ticker": ticker,
            "candidate_trim_usd": row.get("notional_usd") or 0.0,
            "gate": row.get("gate") or "",
            "reason": row.get("rationale") or "",
        })
    return out


def _placement_candidate(ticker: str, dollars: float, accounts: list[dict[str, Any]]) -> dict[str, Any]:
    plan = plan_buy(ticker, dollars, accounts=accounts, is_etf=False)
    suggested = plan.get("suggested") or {}
    return {
        "account": suggested.get("account") or "",
        "broker": suggested.get("broker") or "",
        "owner": suggested.get("owner") or "",
        "tax_status": suggested.get("tax_status") or "",
        "tax_flag": suggested.get("tax_flag") or "",
        "cash_status": plan.get("cash") or "",
        "hard_flags": plan.get("hard_flags") or [],
    }


def _action_row(
    ticker: str,
    *,
    band: tuple[float, float],
    reallocation: dict[str, Any],
    positions_by_ticker: dict[str, dict[str, Any]],
    total_book_value: float,
    accounts: list[dict[str, Any]],
) -> dict[str, Any]:
    existing = float((positions_by_ticker.get(ticker) or {}).get("market_value") or 0.0)
    mid = sum(band) / 2.0
    model_row = _find_add(reallocation, ticker)
    return {
        "ticker": ticker,
        "status": "candidate_only",
        "gate_status": "AMBER_PRE_FOMC",
        "dollar_band": {"low": band[0], "high": band[1]},
        "green_first_tranche": {"low": round(band[0] * 0.5, 2), "high": round(band[1] * 0.7, 2)},
        "amber_starter_context": "Use the combined $25k-$60k amber starter cap across GOOGL/MSFT, not this full band.",
        "existing_exposure_usd": round(existing, 2),
        "existing_exposure_pct": round(existing / total_book_value * 100.0, 2) if total_book_value else 0.0,
        "post_band_exposure_pct": {
            "low": round((existing + band[0]) / total_book_value * 100.0, 2) if total_book_value else 0.0,
            "high": round((existing + band[1]) / total_book_value * 100.0, 2) if total_book_value else 0.0,
        },
        "model_notional_usd": model_row.get("notional_usd") or 0.0,
        "funded_by_model": model_row.get("funded_by") or [],
        "funding_source": model_row.get("funded_by") or [],
        "funding_pool_context": _funding_band(reallocation),
        "account_placement_candidate": _placement_candidate(ticker, mid, accounts),
        "do_nothing_cost": (
            f"{ticker} stays under the intended AI-core exposure if the thesis is right and Fed/tape gates confirm; "
            "cash/funding avoids churn if the Fed reaction is red."
        ),
        "disconfirmation": _disconfirmation(ticker, _source_context(ticker, top_prospects={}, source_calls=[], research_queue={})),
        "options_status": "review_only",
        "execution_status": "not_executed",
    }


def _fed_gates() -> dict[str, Any]:
    return {
        "current_pre_event_status": "AMBER_PRE_FOMC",
        "green": [
            "FOMC statement and press conference do not create a hawkish shock.",
            "QQQ/SPY hold up and AI/semi tape is not rejecting the move.",
            "Yields and oil are not spiking against duration/growth exposure.",
            "UW price/flow fetches are present and not manually interpreted as contradictory.",
        ],
        "amber": [
            "Tape is mixed, breadth/rates/oil conflict, or UW rows remain inconclusive.",
            "Deploy only a $25k-$60k total starter or stage orders without action.",
        ],
        "red": [
            "No net-new AI concentration if Fed/tape reaction breaks down.",
            "Refresh after the statement/press conference and review defensive trims/hedges separately.",
        ],
    }


def build_packet(
    *,
    quote_provider: Callable[[str], dict[str, Any]] = fetch_yahoo_quote,
    as_of: str = "2026-06-17",
    max_tickers: int | None = None,
) -> dict[str, Any]:
    feed = _load_json(SRC / "latest_cockpit_feed.json", {})
    positions = _load_json(SRC / "positions.json", {})
    account_positions = _load_json(SRC / "account_positions.json", {})
    top_prospects = _load_json(SRC / "top_prospects.json", {})
    research_queue = _load_json(SRC / "research_queue.json", {})
    source_calls = _load_json(SRC / "source_call_candidates.json", [])
    uw_results = _load_json(SRC / "uw_endpoint_results.json", {})

    reallocation = build_reallocation_brief(feed, positions, as_of=as_of)
    positions_by_ticker = _combined_positions(account_positions)
    total_book_value = float(positions.get("sleeve_value") or account_positions.get("sleeve_value") or reallocation.get("total_book_value") or 0.0)
    tickers = _collect_watchlist(
        feed=feed,
        account_positions=account_positions,
        top_prospects=top_prospects,
        research_queue=research_queue,
        source_calls=source_calls,
    )
    if max_tickers:
        must_keep = list(MANUAL_WATCHLIST | set(positions_by_ticker) | set(BASE_ADD_TICKERS))
        tickers = sorted(set(tickers[:max_tickers]) | {_ticker(t) for t in must_keep if _ticker(t)})

    quotes = {ticker: quote_provider(ticker) for ticker in tickers}
    discount_rows = _build_discount_rows(
        tickers,
        quotes,
        positions_by_ticker=positions_by_ticker,
        total_book_value=total_book_value,
        top_prospects=top_prospects,
        source_calls=source_calls,
        research_queue=research_queue,
    )
    deep = [row for row in discount_rows if row["ticker"] in DEEP_DISCOUNT_FOCUS]
    pullbacks = [row for row in discount_rows if row["ticker"] in QUALITY_PULLBACK_FOCUS]
    pullbacks = sorted(pullbacks, key=lambda row: row["ticker"] not in BASE_ADD_TICKERS)

    accounts = load_accounts(SRC / "account_positions.json", SRC / "account_rules.json")
    action_rows = [
        _action_row("GOOGL", band=(100_000.0, 155_000.0), reallocation=reallocation, positions_by_ticker=positions_by_ticker, total_book_value=total_book_value, accounts=accounts),
        _action_row("MSFT", band=(25_000.0, 40_000.0), reallocation=reallocation, positions_by_ticker=positions_by_ticker, total_book_value=total_book_value, accounts=accounts),
    ]
    funding_check = funding_reality_check(
        reallocation.get("trims") or [],
        reallocation.get("rows") or [],
        accounts=accounts,
        etf_tickers={"GRNY", "GRNJ", "IVES", "MAGS", "SMH", "SOXX"},
    )

    source_status = {
        "positions": {
            "status": "has_data" if positions.get("snapshot_date") == as_of else "stale_or_dark",
            "snapshot_date": positions.get("snapshot_date") or "",
            "book_value_usd": total_book_value,
            "warnings": _load_json(SRC / "position_reconciliation.json", {}).get("warnings") or [],
        },
        "fundstrat": {
            "status": "checked_no_new_action_row",
            "line": "Chrome session was logged in; visible June 16 Fed/XLU/SPX items did not add a new posture-changing compact row beyond existing cache.",
        },
        "uw": _uw_status(uw_results),
        "notion_research_queue": {
            "status": "fetched",
            "rows": LIVE_NOTION_RESEARCH,
            "writeback": "not_needed_no_new_notion_write",
        },
        "social_watch": _social_watch_status(feed),
        "fed_sources": {
            "status": "checked",
            "links": FED_SOURCE_LINKS,
            "line": "Federal Reserve calendar marks June 16-17, 2026 with an SEP asterisk; CME FedWatch remains the rate-probability reference.",
        },
    }

    return {
        "schema_version": "1.0",
        "as_of": as_of,
        "generated_at": _utc_now(),
        "candidate_only": True,
        "honesty_rule": "No trades executed. No option contracts selected. Stale/dark lanes remain visible.",
        "total_book_value_usd": total_book_value,
        "source_status": source_status,
        "gates": _fed_gates(),
        "base_packet": {
            "summary": "Gated rotation into GOOGL/MSFT if Fed/tape gates pass, funded primarily by GRNY/IVES with small MAGS/SMH cleanup only if useful.",
            "actions": action_rows,
            "funding_reality_check": funding_check,
        },
        "act_if_green": action_rows,
        "stage_if_amber": {
            "total_starter_band_usd": {"low": 25_000, "high": 60_000},
            "preferred_sequence": [
                "Stage GOOGL first because it is the larger model gap and has live Research Queue support.",
                "Add MSFT only as a smaller laggard/capital-efficiency complement.",
                "Keep AVGO/FN/VRT/AMZN secondary unless live price/flow and source review beat GOOGL/MSFT.",
            ],
            "execution_status": "not_executed",
        },
        "do_not_touch_yet": [
            "GRNJ remains protected unless explicit thesis break or operator override.",
            "BMNR stays monitor-first until financing/mNAV/ETH-per-share work clears.",
            "LEU/UUUU/MP require critical-minerals and flow checks before any add review.",
            "KTOS/ELF/SOFI/HOOD require Fundstrat top/bottom-list reconciliation.",
            "Social Watch remains dark/watch-only.",
            "Options remain review-only with no contract selection.",
        ],
        "deep_discount_research": deep,
        "higher_quality_pullbacks": pullbacks,
        "watchlist_discount_screen": {
            "status": "has_data",
            "source": "Yahoo Finance chart endpoint, 1y daily range",
            "row_count": len(discount_rows),
            "rows": discount_rows,
            "not_checked": [ticker for ticker, quote in quotes.items() if quote.get("status") != "has_data"],
        },
    }


def _table(rows: list[dict[str, Any]], *, limit: int | None = None) -> list[str]:
    selected = rows[:limit] if limit else rows
    lines = [
        "| Ticker | Price | 52w high | Discount | Exposure | Sources | Disconfirmation |",
        "| --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in selected:
        sources = ", ".join(row.get("source_tags") or []) or "chart only"
        lines.append(
            "| {ticker} | {price} | {high} | {discount} | {exposure} | {sources} | {disconfirmation} |".format(
                ticker=row.get("ticker"),
                price=_fmt_usd(row.get("price")),
                high=_fmt_usd(row.get("fifty_two_week_high")),
                discount=_fmt_pct(row.get("pct_below_high")),
                exposure=_fmt_usd(row.get("current_exposure_usd")),
                sources=sources.replace("|", "/"),
                disconfirmation=str(row.get("disconfirmation") or "").replace("|", "/"),
            )
        )
    return lines


def render_markdown(packet: dict[str, Any]) -> str:
    lines: list[str] = [
        "# Fed-Day Reallocation Packet - 2026-06-17",
        "",
        "Candidate-only packet. No trades executed. No option contracts selected.",
        "",
        "## Source Status",
        f"- Positions: {packet['source_status']['positions']['status']} from {packet['source_status']['positions']['snapshot_date']} on {_fmt_usd(packet['total_book_value_usd'])}.",
        f"- UW: {packet['source_status']['uw']['line']}",
        f"- Fundstrat: {packet['source_status']['fundstrat']['line']}",
        f"- Notion Research Queue: {packet['source_status']['notion_research_queue']['status']}; no writeback needed.",
        f"- Social Watch: {packet['source_status']['social_watch']['status']} - {packet['source_status']['social_watch']['line']}",
        f"- Fed source: Federal Reserve calendar and CME FedWatch links are in JSON source_status.fed_sources.",
        "",
        "## Act If Green",
        "| Ticker | Band | First tranche | Existing exposure | Post-band exposure | Funding | Placement candidate | Do-nothing cost |",
        "| --- | ---: | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for row in packet["act_if_green"]:
        funding = ", ".join(f"{item['ticker']} {_fmt_usd(item.get('notional_usd'))}" for item in row.get("funding_source") or [])
        placement = row.get("account_placement_candidate") or {}
        placement_text = " / ".join(_clean_text(part) for part in [placement.get("broker"), placement.get("account"), placement.get("tax_status")] if part)
        lines.append(
            "| {ticker} | {band} | {tranche} | {existing} ({existing_pct}) | {post_low}-{post_high} | {funding} | {placement} | {cost} |".format(
                ticker=row["ticker"],
                band=f"{_fmt_usd(row['dollar_band']['low'])}-{_fmt_usd(row['dollar_band']['high'])}",
                tranche=f"{_fmt_usd(row['green_first_tranche']['low'])}-{_fmt_usd(row['green_first_tranche']['high'])}",
                existing=_fmt_usd(row["existing_exposure_usd"]),
                existing_pct=_fmt_pct(row["existing_exposure_pct"]),
                post_low=_fmt_pct(row["post_band_exposure_pct"]["low"]),
                post_high=_fmt_pct(row["post_band_exposure_pct"]["high"]),
                funding=funding or "GRNY/IVES first",
                placement=placement_text or "cash not checked",
                cost=row["do_nothing_cost"],
            )
        )
    lines.extend([
        "",
        "Green gate: deploy only if FOMC/tape reaction is constructive, QQQ/SPY hold, yields/oil are not hostile, and live UW/source review is not contradictory.",
        "",
        "## Stage If Amber",
        f"- Starter only: {_fmt_usd(packet['stage_if_amber']['total_starter_band_usd']['low'])}-{_fmt_usd(packet['stage_if_amber']['total_starter_band_usd']['high'])} total across GOOGL/MSFT.",
    ])
    lines.extend(f"- {item}" for item in packet["stage_if_amber"]["preferred_sequence"])
    lines.extend([
        "",
        "## Do Not Touch Yet",
    ])
    lines.extend(f"- {item}" for item in packet["do_not_touch_yet"])
    lines.extend([
        "",
        "## Deep Discount Research",
    ])
    lines.extend(_table(packet["deep_discount_research"]))
    lines.extend([
        "",
        "## Higher Quality Pullbacks",
    ])
    lines.extend(_table(packet["higher_quality_pullbacks"]))
    lines.extend([
        "",
        "## Full Watchlist Screen",
        f"- Screened rows with chart data: {packet['watchlist_discount_screen']['row_count']}.",
        f"- Not checked: {', '.join(packet['watchlist_discount_screen']['not_checked']) or 'none'}.",
        "",
        "TLDR: Base plan is a gated GOOGL/MSFT rotation, but current broker exposure and Fed reaction determine whether to deploy, stage, or do nothing.",
        "YOUR MOVE: Do not execute until execution mode and green/amber/red gates are explicitly reviewed.",
        "NEXT STEP: Re-check after the Fed statement and press conference reaction, then choose green tranche, amber starter, or red no-new-concentration.",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Fed-day reallocation packet.")
    parser.add_argument("--json-out", default=str(SRC / "fed_day_reallocation_packet.json"))
    parser.add_argument("--md-out", default=str(ROOT / "docs" / "fed_day_reallocation_packet_2026_06_17.md"))
    parser.add_argument("--max-tickers", type=int, default=None)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    packet = build_packet(max_tickers=args.max_tickers)
    _atomic_write_json(Path(args.json_out), packet)
    markdown = render_markdown(packet)
    _atomic_write_text(Path(args.md_out), markdown)
    if args.format == "json":
        print(json.dumps(packet, indent=2, sort_keys=True))
    else:
        print(f"Fed-day packet written: {args.json_out}; {args.md_out}")
        print(f"Act-if-green: {len(packet['act_if_green'])}; deep-discount rows: {len(packet['deep_discount_research'])}; watchlist rows: {packet['watchlist_discount_screen']['row_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
