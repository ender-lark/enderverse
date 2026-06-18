#!/usr/bin/env python3
"""Build the daily pullback/reallocation packet.

The packet is candidate-only. It combines the existing reallocation brief with
current broker exposure, UW endpoint proof, 52-week-high chart data, and
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
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from execution_plan import funding_reality_check, load_accounts, plan_buy
from open_opportunities import compute_move_since
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
MODEL_REFERENCE_BANDS = {
    "GOOGL": (100_000.0, 155_000.0),
    "MSFT": (25_000.0, 40_000.0),
}
FED_DAY_UPDATED_BANDS = {
    "GOOGL": (60_000.0, 110_000.0),
    "MSFT": (15_000.0, 30_000.0),
}
DEFAULT_AMBER_STARTER_BAND = {"low": 25_000, "high": 60_000}
FED_DAY_AMBER_STARTER_BAND = {"low": 20_000, "high": 45_000}

CASH_LIKE = {"CASH", "FCASH", "FDRXX", "SPAXX"}
NON_EQUITY = {"BTC", "ETH", "SOL", "AAVE", "HYPE", "TRUMP"}

LIVE_NOTION_RESEARCH = {
    "BMNR": {
        "status": "Working",
        "priority": "High",
        "state": "MONITOR",
        "line": "Live Research Queue keeps BMNR monitor-first until mNAV, ETH-per-share, preferred coverage, and settlement-era price/flow are resolved.",
        "url": "https://app.notion.com/p/37ac50314bb681c09354df955c2e491d",
        "fetched_at": "2026-06-17T17:16:00Z",
    },
    "GOOGL": {
        "status": "Working",
        "priority": "High",
        "state": "WATCH",
        "line": "Live Research Queue keeps GOOGL staged around the tranche-2 trigger; today's synthesis shows a target gap, but pre-FOMC tape keeps adds reduced and gated.",
        "url": "https://app.notion.com/p/37ac50314bb68100b6ecda51e1a8479e",
        "fetched_at": "2026-06-17T17:16:00Z",
    },
    "AVGO": {
        "status": "Working",
        "priority": "Med",
        "state": "STAGE",
        "line": "Live AVGO diligence supports a high-quality pullback/swap candidate; move it up only if post-Fed semi tape and flow beat GOOGL/MSFT.",
        "url": "https://app.notion.com/p/381c50314bb681a7a124cc8abf0fe78f",
        "fetched_at": "2026-06-17T17:16:00Z",
    },
}

FED_DAY_MARKET_UPDATE = {
    "observed_at": "2026-06-17 13:16 ET",
    "stance": "AMBER_PRE_FOMC_ROTATION",
    "headline": "Mixed pre-FOMC tape and Fundstrat broadening work argue for reduced, staged deployment instead of the full model band before the Fed reaction is known.",
    "facts": [
        "Federal Reserve calendar confirms the June 16-17 meeting is SEP-associated, with the June 17 decision still the gating event.",
        "Same-day market/news scan showed mixed indexes before the Fed: Dow/small caps firmer, Nasdaq/AI softer, and Treasury yields slightly higher.",
        "Fundstrat latest research keeps near-term equity trends intact and says tech leadership has not cracked, but also highlights growth-to-value broadening and warns against chasing stretched tech.",
        "Notion Daily Synthesis keeps Middle East oil/rates event risk on top, Social Watch dark, and Research Queue focus on BMNR, GOOGL, and AVGO.",
        "Oil is below the panic trigger in today's news tape, but the repo trigger still watches WTI near 99-101 and 10Y yields near 4.55-4.59.",
    ],
    "implication": "Keep the GOOGL/MSFT rotation alive, but reduce today's actionable bands, stage only if amber, and let AVGO become the top secondary swap review rather than a primary pre-Fed add.",
}

MARKET_SOURCE_LINKS = {
    "qqq": "https://finance.yahoo.com/quote/QQQ",
    "spy": "https://finance.yahoo.com/quote/SPY",
    "ten_year_yield": "https://finance.yahoo.com/quote/%5ETNX",
    "crude_oil": "https://finance.yahoo.com/quote/CL%3DF",
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


def _today_iso() -> str:
    return date.today().isoformat()


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
    conviction: dict[str, Any] = {}
    research_status = ""
    thesis = ""
    size = ""
    size_band_usd = None
    trigger_date = ""
    trigger = ""
    source = ""
    first_flagged = ""
    flag_price = None
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
            row_tags = [str(tag).strip() for tag in (row.get("source_tags") or []) if str(tag).strip()]
            tags.extend(row_tags)
            row_source = str(row.get("source") or "").strip()
            if row_source:
                tags.append(row_source)
            stance = str(row.get("stance") or "").strip().upper()
            read = str(row.get("conviction") or row.get("conviction_read") or "").strip().upper()
            groups = [str(group).strip() for group in (row.get("source_groups") or []) if str(group).strip()]
            try:
                n_groups = int(row.get("n_groups") or len(groups) or 0)
            except (TypeError, ValueError):
                n_groups = len(groups)
            if stance:
                research_status = stance
            if stance in {"BUY", "ADD"} and read:
                tags.append(f"Research Queue {stance} {read}")
                if read in {"HIGH", "MODERATE"} and n_groups >= 2:
                    tags.append("trusted BUY verdict")
                conviction = {
                    "stance": stance,
                    "direction": "BUY",
                    "read": read,
                    "score": row.get("conviction_score"),
                    "n_groups": n_groups,
                    "source_groups": groups,
                    "conflicted": False,
                }
            if row.get("thesis") and not thesis:
                thesis = str(row.get("thesis") or "").strip()
            if row.get("size") and not size:
                size = str(row.get("size") or "").strip()
            if row.get("size_band_usd") and size_band_usd is None:
                size_band_usd = row.get("size_band_usd")
            if row.get("trigger_date") and not trigger_date:
                trigger_date = str(row.get("trigger_date") or "").strip()
            if row.get("trigger") and not trigger:
                trigger = str(row.get("trigger") or "").strip()
            if row_source and not source:
                source = row_source
            if row.get("first_flagged") and not first_flagged:
                first_flagged = str(row.get("first_flagged") or "").strip()
            if row.get("flag_price") is not None and flag_price is None:
                flag_price = row.get("flag_price")
    live = LIVE_NOTION_RESEARCH.get(ticker)
    if live:
        tags.append(f"Notion {live['status']} {live['state']}")
        research_status = research_status or str(live.get("state") or "")
    return {
        "tags": sorted(set(tags)),
        "flags": sorted(set(flags)),
        "top_prospect_direction": direction or "",
        "notion": live or {},
        "research_status": research_status,
        "conviction": conviction,
        "thesis": thesis,
        "size": size,
        "size_band_usd": size_band_usd,
        "trigger_date": trigger_date,
        "trigger": trigger,
        "source": source,
        "first_flagged": first_flagged,
        "flag_price": flag_price,
    }


def _open_opportunity_memory(ticker: str, open_opportunities: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(open_opportunities, dict):
        return {}
    for row in open_opportunities.get("opportunities") or []:
        if not isinstance(row, dict):
            continue
        if _ticker(row.get("ticker")) == ticker and str(row.get("status") or "open").lower() == "open":
            return row
    return {}


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
        "AVGO": "Advance only if post-Fed semi tape and fresh flow beat GOOGL/MSFT on capital efficiency; prefer swap-funded review before net-new AI.",
        "FN": "Advance only if optical/AI infrastructure evidence and flow beat the base packet.",
        "VRT": "Advance only if power/cooling flow and entry quality beat the base packet.",
        "AMZN": "Secondary add only if live source review is stronger than the funded GOOGL/MSFT packet.",
        "NVDA": "Already large; pullback is not enough unless target/sizing room and flow support it.",
        "GOOGL": "Do not deploy if QQQ/SPY, yields, oil, source review, or flow contradict the staged add after the Fed reaction.",
        "MSFT": "Do not deploy if the laggard thesis remains only valuation-based without post-Fed live confirmation.",
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
    open_opportunities: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        quote = quotes.get(ticker) or {}
        if quote.get("status") != "has_data":
            continue
        exposure = float((positions_by_ticker.get(ticker) or {}).get("market_value") or 0.0)
        context = _source_context(ticker, top_prospects=top_prospects, source_calls=source_calls, research_queue=research_queue)
        memory = _open_opportunity_memory(ticker, open_opportunities)
        first_flagged = context.get("first_flagged") or memory.get("first_flagged") or ""
        flag_price = context.get("flag_price")
        if flag_price is None:
            flag_price = memory.get("flag_price")
        move_since = compute_move_since(flag_price, quote.get("price")) if first_flagged else ""
        row = {
            **quote,
            "current_exposure_usd": round(exposure, 2),
            "current_exposure_pct": round(exposure / total_book_value * 100.0, 2) if total_book_value else 0.0,
            "source_tags": context["tags"],
            "source_flags": context["flags"],
            "disconfirmation": _disconfirmation(ticker, context),
            "research_status": context.get("research_status") or "",
            "rank_score": _score_discount({**quote, "current_exposure_usd": exposure}, context),
            "conviction": context.get("conviction") or {},
            "thesis": context.get("thesis") or "",
            "size": context.get("size") or "",
            "size_band_usd": context.get("size_band_usd"),
            "trigger_date": context.get("trigger_date") or "",
            "trigger": context.get("trigger") or "",
            "first_flagged": first_flagged,
            "flag_price": flag_price,
            "move_since_flagged": move_since,
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
    model_reference_band: tuple[float, float],
    market_stance: str,
    amber_starter_band: dict[str, int],
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
        "gate_status": market_stance,
        "dollar_band": {"low": band[0], "high": band[1]},
        "model_reference_band": {"low": model_reference_band[0], "high": model_reference_band[1]},
        "green_first_tranche": {"low": round(band[0] * 0.5, 2), "high": round(band[1] * 0.7, 2)},
        "amber_starter_context": (
            f"Use the combined {_fmt_usd(amber_starter_band['low'])}-{_fmt_usd(amber_starter_band['high'])} "
            "amber starter cap across GOOGL/MSFT, not this full band."
        ),
        "current_update_reason": (
            "Reduced from the model reference band while the June 17 pre-Fed tape is mixed and Fundstrat/Notion context favors staged confirmation."
            if market_stance == "AMBER_PRE_FOMC_ROTATION"
            else "Uses the model reference band only after same-day market/source context is refreshed."
        ),
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
            f"{ticker} can still re-rate if the Fed reaction and AI tape turn green, but waiting avoids forcing a full add "
            "into mixed breadth, slightly higher yields, and unresolved source/flow checks."
        ),
        "disconfirmation": _disconfirmation(ticker, _source_context(ticker, top_prospects={}, source_calls=[], research_queue={})),
        "options_status": "review_only",
        "execution_status": "not_executed",
    }


def _current_market_update(as_of: str) -> dict[str, Any]:
    if as_of == "2026-06-17":
        return FED_DAY_MARKET_UPDATE
    return {
        "observed_at": "",
        "stance": "STAGE_UNTIL_LIVE_TAPE_CONFIRMS",
        "headline": "No event-specific same-day overlay is loaded for this date; refresh current market, Fundstrat, and Notion context before action.",
        "facts": [],
        "implication": "Use the model reference bands only as staged candidates until live evidence is refreshed.",
    }


def _action_bands(as_of: str) -> dict[str, tuple[float, float]]:
    if as_of == "2026-06-17":
        return FED_DAY_UPDATED_BANDS
    return MODEL_REFERENCE_BANDS


def _amber_starter_band(as_of: str) -> dict[str, int]:
    if as_of == "2026-06-17":
        return FED_DAY_AMBER_STARTER_BAND
    return DEFAULT_AMBER_STARTER_BAND


def _market_gates(market_update: dict[str, Any]) -> dict[str, Any]:
    stance = str(market_update.get("stance") or "STAGE_UNTIL_LIVE_TAPE_CONFIRMS")
    return {
        "current_status": stance,
        "green": [
            "After the Fed statement and press conference, QQQ/SPY hold up and AI/semi tape is not rejecting the move.",
            "Yields and oil are not spiking against duration/growth exposure; 10Y is not moving toward the 4.55-4.59 trigger zone.",
            "UW price/flow fetches are present and not manually interpreted as contradictory.",
            "Current source review does not contradict the staged add.",
        ],
        "stage": [
            "Pre-Fed or post-Fed tape is mixed, growth-to-value broadening is outpacing mega-cap AI, or UW/source rows remain incomplete.",
            "Use only the deliberately reviewed starter cap; keep the rest staged as tickets, not trades.",
        ],
        "red": [
            "No net-new AI concentration if QQQ/SPY, rates/oil, source review, or same-session flow breaks down after the Fed reaction.",
            "Refresh the packet and review defensive trims/hedges separately.",
        ],
    }


def build_packet(
    *,
    quote_provider: Callable[[str], dict[str, Any]] = fetch_yahoo_quote,
    as_of: str | None = None,
    max_tickers: int | None = None,
) -> dict[str, Any]:
    as_of = as_of or _today_iso()
    feed = _load_json(SRC / "latest_cockpit_feed.json", {})
    positions = _load_json(SRC / "positions.json", {})
    account_positions = _load_json(SRC / "account_positions.json", {})
    top_prospects = _load_json(SRC / "top_prospects.json", {})
    research_queue = _load_json(SRC / "research_queue.json", {})
    source_calls = _load_json(SRC / "source_call_candidates.json", [])
    uw_results = _load_json(SRC / "uw_endpoint_results.json", {})
    open_opportunities = _load_json(SRC / "open_opportunities.json", {})

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

    market_update = _current_market_update(as_of)
    action_bands = _action_bands(as_of)
    amber_band = _amber_starter_band(as_of)
    quotes = {ticker: quote_provider(ticker) for ticker in tickers}
    discount_rows = _build_discount_rows(
        tickers,
        quotes,
        positions_by_ticker=positions_by_ticker,
        total_book_value=total_book_value,
        top_prospects=top_prospects,
        source_calls=source_calls,
        research_queue=research_queue,
        open_opportunities=open_opportunities,
    )
    deep = [row for row in discount_rows if row["ticker"] in DEEP_DISCOUNT_FOCUS]
    pullbacks = [row for row in discount_rows if row["ticker"] in QUALITY_PULLBACK_FOCUS]
    pullbacks = sorted(pullbacks, key=lambda row: row["ticker"] not in BASE_ADD_TICKERS)

    accounts = load_accounts(SRC / "account_positions.json", SRC / "account_rules.json")
    action_rows = [
        _action_row(
            "GOOGL",
            band=action_bands["GOOGL"],
            model_reference_band=MODEL_REFERENCE_BANDS["GOOGL"],
            market_stance=str(market_update.get("stance") or "STAGE_UNTIL_LIVE_TAPE_CONFIRMS"),
            amber_starter_band=amber_band,
            reallocation=reallocation,
            positions_by_ticker=positions_by_ticker,
            total_book_value=total_book_value,
            accounts=accounts,
        ),
        _action_row(
            "MSFT",
            band=action_bands["MSFT"],
            model_reference_band=MODEL_REFERENCE_BANDS["MSFT"],
            market_stance=str(market_update.get("stance") or "STAGE_UNTIL_LIVE_TAPE_CONFIRMS"),
            amber_starter_band=amber_band,
            reallocation=reallocation,
            positions_by_ticker=positions_by_ticker,
            total_book_value=total_book_value,
            accounts=accounts,
        ),
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
            "line": "Chrome-authenticated latest research review supports staged confirmation: tech trend intact, but broadening/value rotation argues against chasing full mega-cap AI size pre-Fed.",
        },
        "uw": _uw_status(uw_results),
        "notion_research_queue": {
            "status": "fetched",
            "rows": LIVE_NOTION_RESEARCH,
            "today_daily_synthesis": "2026-06-17 synthesis keeps Middle East oil/rates event risk on top, Social Watch dark, and BMNR/GOOGL/AVGO in live research focus.",
            "writeback": "not_needed_no_new_notion_write",
        },
        "social_watch": _social_watch_status(feed),
        "market_timing": {
            "status": "checked",
            "links": MARKET_SOURCE_LINKS,
            "line": market_update.get("headline") or "Packet rows require current tape/source confirmation before any capital action.",
        },
    }

    return {
        "schema_version": "1.0",
        "packet_kind": "daily_pullback_reallocation",
        "display_label": "Daily pullback packet",
        "as_of": as_of,
        "generated_at": _utc_now(),
        "candidate_only": True,
        "honesty_rule": "No trades executed. No option contracts selected. Stale/dark lanes remain visible.",
        "total_book_value_usd": total_book_value,
        "source_status": source_status,
        "current_market_update": market_update,
        "gates": _market_gates(market_update),
        "base_packet": {
            "summary": (
                "Keep the GOOGL/MSFT rotation live, but today's updated plan reduces the actionable bands and stages deployment "
                "until the Fed reaction, market breadth, rates, oil, UW flow, and source review confirm."
            ),
            "actions": action_rows,
            "funding_reality_check": funding_check,
        },
        "act_if_green": action_rows,
        "stage_if_amber": {
            "total_starter_band_usd": amber_band,
            "preferred_sequence": [
                "Before the Fed reaction is known, stage tickets without action or use only the reduced starter cap.",
                "If amber persists after the Fed, favor a smaller GOOGL starter before MSFT; do not force both names.",
                "Elevate AVGO to top secondary swap review only if post-Fed semi tape and flow beat GOOGL/MSFT; FN/VRT/AMZN remain secondary.",
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
    label = str(packet.get("display_label") or "Daily pullback packet")
    lines: list[str] = [
        f"# {label} - {packet.get('as_of') or 'not_checked'}",
        "",
        "Candidate-only packet. No trades executed. No option contracts selected.",
        "",
        "## Current Market Update",
        f"- Stance: {packet['current_market_update']['stance']} ({packet['current_market_update'].get('observed_at') or 'not time stamped'}).",
        f"- Read: {packet['current_market_update']['headline']}",
    ]
    for fact in packet["current_market_update"].get("facts") or []:
        lines.append(f"- {fact}")
    lines.extend([
        f"- Plan impact: {packet['current_market_update']['implication']}",
        "",
        "## Source Status",
        f"- Positions: {packet['source_status']['positions']['status']} from {packet['source_status']['positions']['snapshot_date']} on {_fmt_usd(packet['total_book_value_usd'])}.",
        f"- UW: {packet['source_status']['uw']['line']}",
        f"- Fundstrat: {packet['source_status']['fundstrat']['line']}",
        f"- Notion Research Queue: {packet['source_status']['notion_research_queue']['status']}; no writeback needed.",
        f"- Social Watch: {packet['source_status']['social_watch']['status']} - {packet['source_status']['social_watch']['line']}",
        f"- Market timing: {packet['source_status']['market_timing']['line']}",
        "",
        "## Act If Green",
        "| Ticker | Updated band | Model ref | First tranche | Existing exposure | Post-band exposure | Funding | Placement candidate | Do-nothing cost |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |",
    ])
    for row in packet["act_if_green"]:
        funding = ", ".join(f"{item['ticker']} {_fmt_usd(item.get('notional_usd'))}" for item in row.get("funding_source") or [])
        placement = row.get("account_placement_candidate") or {}
        placement_text = " / ".join(_clean_text(part) for part in [placement.get("broker"), placement.get("account"), placement.get("tax_status")] if part)
        lines.append(
            "| {ticker} | {band} | {model_ref} | {tranche} | {existing} ({existing_pct}) | {post_low}-{post_high} | {funding} | {placement} | {cost} |".format(
                ticker=row["ticker"],
                band=f"{_fmt_usd(row['dollar_band']['low'])}-{_fmt_usd(row['dollar_band']['high'])}",
                model_ref=f"{_fmt_usd(row['model_reference_band']['low'])}-{_fmt_usd(row['model_reference_band']['high'])}",
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
        "Green gate: deploy only after the Fed reaction if QQQ/SPY hold, yields/oil are not hostile, and live UW/source review is not contradictory.",
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
        "TLDR: Current plan is amber pre-Fed: keep the GOOGL/MSFT rotation live, use reduced bands only if gates turn green, and treat AVGO as the top secondary swap review.",
        "YOUR MOVE: Do not execute until execution mode and green/amber/red gates are explicitly reviewed.",
        "NEXT STEP: Re-check current tape/source evidence, then choose green tranche, staged starter, or red no-new-concentration.",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the daily pullback/reallocation packet.")
    parser.add_argument("--as-of", default=None, help="ISO date for packet freshness; defaults to today's local date.")
    parser.add_argument("--json-out", default=str(SRC / "fed_day_reallocation_packet.json"))
    parser.add_argument("--md-out", default=str(ROOT / "docs" / "daily_pullback_packet.md"))
    parser.add_argument("--max-tickers", type=int, default=None)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    packet = build_packet(as_of=args.as_of, max_tickers=args.max_tickers)
    _atomic_write_json(Path(args.json_out), packet)
    markdown = render_markdown(packet)
    _atomic_write_text(Path(args.md_out), markdown)
    if args.format == "json":
        print(json.dumps(packet, indent=2, sort_keys=True))
    else:
        print(f"Daily pullback packet written: {args.json_out}; {args.md_out}")
        print(f"Act-if-green: {len(packet['act_if_green'])}; deep-discount rows: {len(packet['deep_discount_research'])}; watchlist rows: {packet['watchlist_discount_screen']['row_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
