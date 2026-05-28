#!/usr/bin/env python3
"""
uw_signal_aggregator.py — Launcher Step 1 signal aggregator (v11.11 Tier 1)

Pulls three high-signal, currently-unused UW endpoints in parallel and surfaces
the subset that intersects operator portfolio (`fs_holdings.json`):

  1. Trump activity (past 24h)
       -> match against `thesis_keywords` per ticker
       -> surface posts that touch held/watchlist names
  2. Trading states (latest session)
       -> filter to halts / pauses / quote-only-period
       -> intersect with held tickers
  3. Insider open-market buys (past 7 days)
       -> filter: transaction_code=P, value >= $500K, is_officer=True
       -> intersect with operator sectors

Why these three:
  - Operator framework explicitly weights Trump-allied positioning + Trump policy
    factor in P-FACTOR. There was no automated feed for this.
  - Halts on held names are immediate-action events; no current launcher step
    surfaces them.
  - Insider open-market buys >$500K are explicitly named in CI as bullish signal;
    no script currently aggregates the firehose for them.

Output: text report or JSON. Designed to be called at session open alongside
fs_ranker.py and rationale_decay.py, or cron'd daily pre-market (8am ET).

Env vars:
  UW_API_KEY        Required. Unusual Whales API bearer token. Get from
                    https://unusualwhales.com/settings/api-dashboard

Endpoints used:
  GET /api/socials/trump-tweets        (Trump activity, sorted by timestamp desc)
  GET /api/stock-state                 (latest trading-state events)
  GET /api/insider/transactions        (Form 4 with filters)

  Endpoint paths are best-guess based on UW MCP tool naming. If you hit 404s on
  first run, adjust the ENDPOINT_* constants at the top. The orchestration,
  filtering, and output logic does not depend on the exact paths.

Usage:
  python uw_signal_aggregator.py                     # text report
  python uw_signal_aggregator.py --json              # JSON output
  python uw_signal_aggregator.py --dry-run           # show what would be called
  python uw_signal_aggregator.py --holdings PATH     # override fs_holdings.json
  python uw_signal_aggregator.py --insider-min 1000000  # raise insider threshold
  python uw_signal_aggregator.py --skip trump        # skip one component
  python uw_signal_aggregator.py --verbose           # print HTTP debug

Exit codes:
  0  — clean run (may have zero signals)
  1  — config error (missing fs_holdings.json, missing API key)
  2  — at least one endpoint failed (other components still ran)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

# ============================================================================
# CONFIGURATION
# ============================================================================

UW_API_BASE = "https://api.unusualwhales.com/api"

# Endpoint paths — VERIFY ON FIRST RUN. Adjust if 404. See module docstring.
ENDPOINT_TRUMP_ACTIVITY = "/socials/trump-tweets"
ENDPOINT_TRADING_STATES = "/stock-state"
ENDPOINT_INSIDER_TRANSACTIONS = "/insider/transactions"

# Operator-relevant sectors. Excludes Utilities + Real Estate (low priors in
# operator framework — adjust if XLF / XLU sleeve expands).
OPERATOR_SECTORS = {
    "Basic Materials",
    "Communication Services",
    "Consumer Cyclical",
    "Consumer Defensive",
    "Energy",
    "Financial Services",
    "Healthcare",
    "Industrials",
    "Technology",
}

# Insider buy threshold (CI baseline: "C-suite open-market buys >$500K = bullish")
DEFAULT_MIN_INSIDER_BUY_VALUE = 500_000
INSIDER_LOOKBACK_DAYS = 7

# Trump activity lookback (24h surfaces a typical post cycle)
TRUMP_LOOKBACK_HOURS = 24

# Trading-state filter: what counts as actionable for held names
ACTIONABLE_TRADING_STATES = {"halt", "pause", "quote_only_period"}

# Form 4 transaction codes for open-market purchases (NOT exercise, RSU, etc.)
OPEN_MARKET_BUY_CODES = {"P"}

# HTTP request timeout
REQUEST_TIMEOUT = 30


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class TrumpHit:
    """A Trump post that matched one or more portfolio tickers."""
    timestamp: str
    text: str
    matched_tickers: list[str]
    matched_keywords: dict[str, list[str]]  # ticker -> matched keyword list
    url: str | None = None


@dataclass
class TradingHalt:
    """An actionable trading-state event on a held ticker."""
    ticker: str
    state: str
    reason: str | None
    executed_at: str | None
    last_price: float | None
    is_held: bool


@dataclass
class InsiderBuy:
    """A discretionary C-suite open-market buy that cleared the value threshold."""
    ticker: str
    owner_name: str | None
    transaction_date: str | None
    transaction_code: str | None
    shares: float | None
    price: float | None
    value: float | None
    is_officer: bool
    is_director: bool
    sector: str | None
    in_portfolio: bool  # held or watchlist


@dataclass
class SignalReport:
    """Top-level container for all three signal types."""
    timestamp: str
    trump_hits: list[TrumpHit] = field(default_factory=list)
    trading_halts: list[TradingHalt] = field(default_factory=list)
    insider_buys: list[InsiderBuy] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def total_hits(self) -> int:
        return len(self.trump_hits) + len(self.trading_halts) + len(self.insider_buys)


# ============================================================================
# HTTP CLIENT
# ============================================================================

def uw_headers() -> dict[str, str]:
    token = os.environ.get("UW_API_KEY")
    if not token:
        sys.exit("ERROR: UW_API_KEY env var not set. Get one at "
                 "https://unusualwhales.com/settings/api-dashboard")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }


def uw_get(path: str, params: dict[str, Any] | None = None,
           verbose: bool = False) -> dict[str, Any]:
    """GET against UW REST API. Raises on non-200."""
    url = UW_API_BASE + path
    if verbose:
        print(f"  HTTP GET {url}  params={params}", file=sys.stderr)
    resp = requests.get(url, headers=uw_headers(), params=params,
                        timeout=REQUEST_TIMEOUT)
    if resp.status_code == 404:
        raise RuntimeError(f"404 on {path} — endpoint path likely wrong; "
                           f"check UW API docs and update constant")
    if resp.status_code == 401:
        raise RuntimeError("401 unauthorized — check UW_API_KEY value")
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} on {path}: {resp.text[:200]}")
    return resp.json()


# ============================================================================
# HOLDINGS LOADER
# ============================================================================

def load_holdings(path: Path) -> dict[str, Any]:
    """Load fs_holdings.json. Required keys: 'held', 'watchlist', 'thesis_keywords'."""
    if not path.exists():
        sys.exit(f"ERROR: holdings file not found at {path}")
    with path.open() as f:
        data = json.load(f)
    for key in ("held", "watchlist", "thesis_keywords"):
        if key not in data:
            sys.exit(f"ERROR: holdings file missing required key {key!r}")
    return data


def all_portfolio_tickers(holdings: dict[str, Any]) -> set[str]:
    """Union of held + watchlist + thesis_keywords keys."""
    return (
        set(holdings.get("held", [])) |
        set(holdings.get("watchlist", [])) |
        set(holdings.get("thesis_keywords", {}).keys())
    )


# ============================================================================
# COMPONENT 1: TRUMP ACTIVITY SCANNER
# ============================================================================

def fetch_trump_activity(verbose: bool = False, dry_run: bool = False) -> list[dict[str, Any]]:
    """Pull recent Trump posts. Returns raw list of post dicts.

    Real UW response shape (confirmed against live MCP May 14 2026):
      {"schedule": [...], "ts_posts": [{"timestamp": <epoch_ms>, "post": "..."}]}
    """
    if dry_run:
        return []
    params = {"limit": 50}
    data = uw_get(ENDPOINT_TRUMP_ACTIVITY, params=params, verbose=verbose)
    # UW Trump endpoint wraps posts in "ts_posts" key
    if isinstance(data, dict):
        return data.get("ts_posts", data.get("posts", data.get("data", [])))
    return data if isinstance(data, list) else []


def _parse_timestamp(ts: Any) -> datetime | None:
    """Parse various timestamp formats: ISO-8601 string OR epoch milliseconds (int/float).
    Returns None on failure.

    UW Trump endpoint uses epoch_ms; other endpoints use ISO. Both supported.
    """
    if ts is None:
        return None
    # Epoch milliseconds (UW Trump endpoint format — confirmed against live MCP)
    if isinstance(ts, (int, float)):
        try:
            # UW uses milliseconds (13 digits); guard against seconds (10 digits)
            seconds = ts / 1000 if ts > 1e12 else ts
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None
    # ISO-8601 string formats
    if not isinstance(ts, str):
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(ts, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def match_trump_posts_to_portfolio(
    posts: list[dict[str, Any]],
    holdings: dict[str, Any],
    lookback_hours: int = TRUMP_LOOKBACK_HOURS,
) -> list[TrumpHit]:
    """Filter posts to (a) last `lookback_hours` and (b) keyword-matched to portfolio."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    thesis_keywords = holdings.get("thesis_keywords", {})

    # Build keyword -> ticker reverse index (lowercase for case-insensitive match)
    keyword_to_ticker: dict[str, list[str]] = {}
    for ticker, kws in thesis_keywords.items():
        for kw in kws:
            keyword_to_ticker.setdefault(kw.lower(), []).append(ticker)
    # Also add tickers themselves as keywords (a post mentioning "NVDA" or "Nvidia")
    for ticker in all_portfolio_tickers(holdings):
        keyword_to_ticker.setdefault(ticker.lower(), []).append(ticker)

    # Pre-compile word-boundary patterns to avoid substring false positives
    # (e.g. "mp" matching inside "imports", "ev" matching inside "reflective").
    # Word boundaries (\b) require alphanumeric chars at the edge — works for
    # both single tokens and multi-word phrases.
    keyword_patterns: list[tuple[re.Pattern, str, list[str]]] = []
    for kw, tickers in keyword_to_ticker.items():
        try:
            pat = re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE)
            keyword_patterns.append((pat, kw, tickers))
        except re.error:
            continue

    hits: list[TrumpHit] = []
    for post in posts:
        # Tolerant field extraction. UW Trump endpoint uses `post` field;
        # fall back to other names in case of schema drift.
        ts_raw = post.get("timestamp") or post.get("created_at") or post.get("date")
        text = (post.get("post") or post.get("text") or post.get("content")
                or post.get("body") or "").strip()
        url = post.get("url") or post.get("permalink")
        if not text:
            continue

        ts_parsed = _parse_timestamp(ts_raw)
        if ts_parsed and ts_parsed < cutoff:
            continue

        matched_tickers_set: set[str] = set()
        matched_keywords: dict[str, list[str]] = {}
        for pat, kw, tickers in keyword_patterns:
            if pat.search(text):
                for t in tickers:
                    matched_tickers_set.add(t)
                    matched_keywords.setdefault(t, []).append(kw)

        if matched_tickers_set:
            # Convert epoch_ms timestamp to ISO string for display consistency
            ts_display = ts_parsed.isoformat() if ts_parsed else str(ts_raw)
            hits.append(TrumpHit(
                timestamp=ts_display,
                text=text[:500],  # truncate very long posts
                matched_tickers=sorted(matched_tickers_set),
                matched_keywords={t: sorted(set(kws))
                                  for t, kws in matched_keywords.items()},
                url=url,
            ))
    return hits


# ============================================================================
# COMPONENT 2: TRADING STATES (HALTS / PAUSES) ON HELD NAMES
# ============================================================================

def fetch_trading_states(
    tickers: Iterable[str],
    verbose: bool = False,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Pull latest trading-state events. Returns raw event list."""
    if dry_run:
        return []
    # Endpoint may accept ticker_symbol filter (comma-sep) per MCP tool docs
    ticker_param = ",".join(sorted(tickers))[:256]  # API may have length cap
    params = {"limit": 100}
    if ticker_param:
        params["ticker_symbol"] = ticker_param
    try:
        data = uw_get(ENDPOINT_TRADING_STATES, params=params, verbose=verbose)
    except RuntimeError:
        # Fallback: pull unfiltered, we filter client-side
        if verbose:
            print("  (server-side filter failed; pulling unfiltered)",
                  file=sys.stderr)
        data = uw_get(ENDPOINT_TRADING_STATES, params={"limit": 100},
                      verbose=verbose)
    if isinstance(data, dict):
        return data.get("data", [])
    return data if isinstance(data, list) else []


def filter_trading_halts(
    events: list[dict[str, Any]],
    held: set[str],
    watchlist: set[str],
) -> list[TradingHalt]:
    """Keep only actionable states on portfolio tickers."""
    out: list[TradingHalt] = []
    relevant = held | watchlist
    for ev in events:
        ticker = ev.get("symbol") or ev.get("ticker")
        if not ticker or ticker not in relevant:
            continue
        state = (ev.get("state") or "").lower()
        if state not in ACTIONABLE_TRADING_STATES:
            continue
        out.append(TradingHalt(
            ticker=ticker,
            state=state,
            reason=ev.get("reason"),
            executed_at=ev.get("executed_at") or ev.get("timestamp"),
            last_price=_safe_float(ev.get("last_price") or ev.get("price")),
            is_held=ticker in held,
        ))
    return out


def _safe_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ============================================================================
# COMPONENT 3: INSIDER OPEN-MARKET BUYS
# ============================================================================

def fetch_insider_buys(
    min_value: int = DEFAULT_MIN_INSIDER_BUY_VALUE,
    lookback_days: int = INSIDER_LOOKBACK_DAYS,
    verbose: bool = False,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Pull Form 4 open-market buys with value/officer/date filters."""
    if dry_run:
        return []
    start = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).date().isoformat()
    params = {
        "transaction_codes": "P",       # Open-market purchase
        "is_officer": "true",
        "min_value": str(min_value),
        "start_date": start,
        "limit": 50,
        "common_stock_only": "true",
        "exclude_10b5_1": "true",       # Filter planned trades
    }
    data = uw_get(ENDPOINT_INSIDER_TRANSACTIONS, params=params, verbose=verbose)
    if isinstance(data, dict):
        return data.get("data", [])
    return data if isinstance(data, list) else []


def normalize_insider_buys(
    raw: list[dict[str, Any]],
    portfolio: set[str],
) -> list[InsiderBuy]:
    """Convert raw insider rows into typed InsiderBuy. Flag portfolio overlap.

    Real UW shape (confirmed against live MCP May 14 2026):
      `amount` = shares, `price` = per-share, no `value` field — must compute.
    """
    out: list[InsiderBuy] = []
    for r in raw:
        ticker = r.get("ticker") or r.get("symbol")
        if not ticker:
            continue
        sector = r.get("sector")
        # Default sector filter: keep if in operator sectors OR if in portfolio
        in_portfolio = ticker in portfolio
        if sector and sector not in OPERATOR_SECTORS and not in_portfolio:
            continue
        # UW returns amount (shares) + price separately; compute dollar value
        shares = _safe_float(r.get("amount") or r.get("shares"))
        price = _safe_float(r.get("price"))
        value = _safe_float(r.get("value"))  # fall back to explicit field if present
        if value is None and shares is not None and price is not None:
            value = shares * price
        out.append(InsiderBuy(
            ticker=ticker,
            owner_name=r.get("owner_name") or r.get("insider_name"),
            transaction_date=r.get("transaction_date") or r.get("date"),
            transaction_code=r.get("transaction_code") or r.get("code"),
            shares=shares,
            price=price,
            value=value,
            is_officer=bool(r.get("is_officer", True)),
            is_director=bool(r.get("is_director", False)),
            sector=sector,
            in_portfolio=in_portfolio,
        ))
    # Sort by value descending so biggest buys surface first
    out.sort(key=lambda b: -(b.value or 0))
    return out


# ============================================================================
# ORCHESTRATION
# ============================================================================

def run(
    holdings_path: Path,
    skip: set[str],
    insider_min: int,
    dry_run: bool,
    verbose: bool,
) -> SignalReport:
    holdings = load_holdings(holdings_path)
    held = set(holdings.get("held", []))
    watchlist = set(holdings.get("watchlist", []))
    portfolio = all_portfolio_tickers(holdings)

    report = SignalReport(timestamp=datetime.now(timezone.utc).isoformat())

    # ---------- Component 1: Trump ----------
    if "trump" in skip:
        report.skipped.append("trump")
    else:
        try:
            posts = fetch_trump_activity(verbose=verbose, dry_run=dry_run)
            report.trump_hits = match_trump_posts_to_portfolio(posts, holdings)
        except Exception as e:
            report.errors.append(f"trump: {e}")

    # ---------- Component 2: Trading states ----------
    if "halts" in skip:
        report.skipped.append("halts")
    else:
        try:
            events = fetch_trading_states(
                tickers=portfolio, verbose=verbose, dry_run=dry_run,
            )
            report.trading_halts = filter_trading_halts(events, held, watchlist)
        except Exception as e:
            report.errors.append(f"halts: {e}")

    # ---------- Component 3: Insider buys ----------
    if "insider" in skip:
        report.skipped.append("insider")
    else:
        try:
            raw = fetch_insider_buys(
                min_value=insider_min,
                verbose=verbose,
                dry_run=dry_run,
            )
            report.insider_buys = normalize_insider_buys(raw, portfolio)
        except Exception as e:
            report.errors.append(f"insider: {e}")

    return report


# ============================================================================
# OUTPUT FORMATTING
# ============================================================================

def format_text_report(report: SignalReport, insider_min: int) -> str:
    lines = []
    lines.append("=" * 72)
    lines.append(f" UW SIGNAL AGGREGATOR — {report.timestamp}")
    lines.append("=" * 72)

    if report.errors:
        lines.append("")
        lines.append("⚠️  ERRORS")
        for e in report.errors:
            lines.append(f"   {e}")
    if report.skipped:
        lines.append("")
        lines.append(f"⏭  SKIPPED: {', '.join(report.skipped)}")

    # ---------- Trump section ----------
    lines.append("")
    lines.append(f"🔔 TRUMP ACTIVITY (past {TRUMP_LOOKBACK_HOURS}h, portfolio-matched)")
    lines.append("-" * 72)
    if not report.trump_hits:
        lines.append("   No portfolio-relevant Trump posts in window.")
    else:
        for h in report.trump_hits:
            tickers_str = ", ".join(h.matched_tickers)
            lines.append(f"   [{h.timestamp}] → {tickers_str}")
            lines.append(f"      {h.text[:200]}{'…' if len(h.text) > 200 else ''}")
            for ticker, kws in h.matched_keywords.items():
                lines.append(f"      • {ticker}: matched on {', '.join(kws)}")
            if h.url:
                lines.append(f"      {h.url}")
            lines.append("")

    # ---------- Halts section ----------
    lines.append(f"🛑 TRADING HALTS / PAUSES (latest session, held + watchlist)")
    lines.append("-" * 72)
    if not report.trading_halts:
        lines.append("   No halts/pauses on portfolio tickers.")
    else:
        for h in report.trading_halts:
            held_tag = "HELD" if h.is_held else "WATCH"
            price_str = f" @ ${h.last_price:.2f}" if h.last_price else ""
            lines.append(f"   [{held_tag}] {h.ticker:6s} {h.state.upper():18s}"
                         f"{price_str}")
            if h.reason:
                lines.append(f"           reason: {h.reason}")
            if h.executed_at:
                lines.append(f"           at: {h.executed_at}")

    # ---------- Insider section ----------
    lines.append("")
    lines.append(f"💼 INSIDER OPEN-MARKET BUYS (past {INSIDER_LOOKBACK_DAYS}d, "
                 f">${insider_min:,}, officers, non-10b5-1)")
    lines.append("-" * 72)
    if not report.insider_buys:
        lines.append(f"   No insider buys above ${insider_min:,} threshold.")
    else:
        for b in report.insider_buys:
            portfolio_tag = "★" if b.in_portfolio else " "
            value_str = f"${b.value:>11,.0f}" if b.value else "$       —  "
            sector_str = f" [{b.sector}]" if b.sector else ""
            lines.append(f"  {portfolio_tag} {b.ticker:6s} {value_str}  "
                         f"{b.owner_name or '?':30s} {b.transaction_date or '?'}"
                         f"{sector_str}")
        lines.append("")
        lines.append("  ★ = in operator portfolio (held or watchlist)")

    lines.append("")
    lines.append("=" * 72)
    lines.append(f" Total signals surfaced: {report.total_hits}")
    if report.errors:
        lines.append(f" Errors: {len(report.errors)} (see above)")
    lines.append("=" * 72)
    return "\n".join(lines)


def format_json_report(report: SignalReport) -> str:
    return json.dumps(asdict(report), indent=2, default=str)


# ============================================================================
# CLI
# ============================================================================

def main() -> int:
    p = argparse.ArgumentParser(
        description="UW signal aggregator — Trump posts, halts, insider buys",
    )
    p.add_argument("--holdings", default="./fs_holdings.json",
                   help="Path to fs_holdings.json (default: ./fs_holdings.json)")
    p.add_argument("--insider-min", type=int,
                   default=DEFAULT_MIN_INSIDER_BUY_VALUE,
                   help=f"Min insider buy $ (default ${DEFAULT_MIN_INSIDER_BUY_VALUE:,})")
    p.add_argument("--skip", action="append", choices=["trump", "halts", "insider"],
                   default=[], help="Skip a component (repeatable)")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--dry-run", action="store_true",
                   help="Print plan, no HTTP calls")
    p.add_argument("--verbose", action="store_true", help="Print HTTP debug")
    args = p.parse_args()

    if args.dry_run:
        print("DRY RUN — would call:", file=sys.stderr)
        for name, ep, skip_key in [
            ("Trump", ENDPOINT_TRUMP_ACTIVITY, "trump"),
            ("Halts", ENDPOINT_TRADING_STATES, "halts"),
            ("Insider", ENDPOINT_INSIDER_TRANSACTIONS, "insider"),
        ]:
            status = "SKIP" if skip_key in args.skip else "GET"
            print(f"  {status:4s} {UW_API_BASE}{ep}  ({name})", file=sys.stderr)
        return 0

    report = run(
        holdings_path=Path(args.holdings),
        skip=set(args.skip),
        insider_min=args.insider_min,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    if args.json:
        print(format_json_report(report))
    else:
        print(format_text_report(report, args.insider_min))

    return 2 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
