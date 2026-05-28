#!/usr/bin/env python3
"""
stale_leaps_scan.py — W8 / Game C: Post-move LEAPS hunt on conviction names (v1.0)

Codifies the "stale-quote on long-dated chain" thesis: after a fast move on a
conviction name, some long-dated LEAPS strikes don't reprice immediately. The
ask sits below fair value (Black-Scholes theoretical at current spot + current
chain IV) for 24-72 hours while MMs and the wider market catch up. This is the
NBIS Sep-2025 8-K pattern — the contract-anchor 8-K dropped, the equity gapped,
but $80-$100 strikes at 12mo+ expiries took 48-72 hours to reflect new fair value.

Trigger conditions (any fires → operator can invoke this scan):
  - Conviction-name move ≥10% in 5 trading days
  - Conviction-name move ≥7% in 1 trading day on catalyst (8-K, earnings, news)
  - Launcher Step 5 (SEC 8-K hyperscaler-anchor scan) fires on a held/watchlist name
  - Thesis-strengthening event on Tier A or Generational held name (per v11.8)

Scan logic:
  1. Fetch underlying current price (from UW get_stock_screener or close-prices)
  2. Fetch options chain for target expiry range (default 365-730 DTE)
  3. For each strike on call side: compute Black-Scholes theoretical price using
     current spot + chain IV + time-to-expiry + 4.5% risk-free + 0 dividend
  4. Flag strikes where: ask < theoretical × DISCOUNT_THRESHOLD (default 0.85)
                     AND volume_5d < VOLUME_FLOOR (default 50, ensures no MM has
                     repriced; high-volume contracts are likely fair-marked already)
  5. Output: ranked list of stale strikes with $ ask vs $ theoretical + % discount

Defined-risk long-side only per v11.10 (no naked-short suggestions).

Env vars:
  UW_API_KEY  Required. Unusual Whales bearer token.

Usage:
  python stale_leaps_scan.py --ticker LEU --trigger move
  python stale_leaps_scan.py --ticker NBIS --trigger 8k --expiry-min 365 --expiry-max 730
  python stale_leaps_scan.py --ticker NVDA --trigger thesis --discount 0.80 --volume-floor 20
  python stale_leaps_scan.py --ticker LEU --trigger move --json

Exit codes:
  0  scan completed (with or without hits)
  1  config / API key error
  2  ticker fetch failed
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, date, timezone
from typing import Any

import requests

# ============================================================================
# CONFIGURATION
# ============================================================================

UW_API_BASE = "https://api.unusualwhales.com/api"

# Default scan parameters
DEFAULT_EXPIRY_MIN_DTE = 365   # 12 months out
DEFAULT_EXPIRY_MAX_DTE = 730   # 24 months out
DEFAULT_DISCOUNT_THRESHOLD = 0.85   # Flag strikes where ask < theo × 0.85
DEFAULT_VOLUME_FLOOR = 50      # Ignore strikes with >50 contract volume (already repriced)
DEFAULT_RISK_FREE_RATE = 0.045   # Proxy for current 3M T-bill / SOFR
DEFAULT_DIVIDEND_YIELD = 0.0     # Proxy; non-dividend-payers dominant in conviction list

# Trigger types (informational only — operator decides when to invoke)
TRIGGER_TYPES = {
    "move":   "Underlying moved ≥10% in 5d or ≥7% in 1d",
    "8k":     "SEC 8-K hyperscaler/sovereign-anchor scan (Launcher Step 5) hit",
    "thesis": "Thesis-strengthening event on Tier A / Generational name (v11.8)",
    "manual": "Operator-invoked scan; no specific trigger",
}


# ============================================================================
# BLACK-SCHOLES PRICING
# ============================================================================

def _norm_cdf(x: float) -> float:
    """Standard normal CDF using math.erf (no scipy dependency)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black_scholes_call(
    spot: float,
    strike: float,
    time_years: float,
    iv: float,
    risk_free: float = DEFAULT_RISK_FREE_RATE,
    div_yield: float = DEFAULT_DIVIDEND_YIELD,
) -> float:
    """
    European call option theoretical price.

    Uses dividend-adjusted Black-Scholes-Merton.
    All inputs in decimal form (IV 0.45 = 45%, risk_free 0.045 = 4.5%).
    Returns price per share (multiply by 100 for contract dollar value).
    """
    if time_years <= 0 or iv <= 0 or spot <= 0 or strike <= 0:
        return max(0.0, spot - strike)

    sigma_sqrt_t = iv * math.sqrt(time_years)
    d1 = (math.log(spot / strike) + (risk_free - div_yield + 0.5 * iv * iv) * time_years) / sigma_sqrt_t
    d2 = d1 - sigma_sqrt_t

    return (
        spot * math.exp(-div_yield * time_years) * _norm_cdf(d1)
        - strike * math.exp(-risk_free * time_years) * _norm_cdf(d2)
    )


def black_scholes_put(
    spot: float,
    strike: float,
    time_years: float,
    iv: float,
    risk_free: float = DEFAULT_RISK_FREE_RATE,
    div_yield: float = DEFAULT_DIVIDEND_YIELD,
) -> float:
    """European put option theoretical price via put-call parity."""
    if time_years <= 0 or iv <= 0 or spot <= 0 or strike <= 0:
        return max(0.0, strike - spot)

    sigma_sqrt_t = iv * math.sqrt(time_years)
    d1 = (math.log(spot / strike) + (risk_free - div_yield + 0.5 * iv * iv) * time_years) / sigma_sqrt_t
    d2 = d1 - sigma_sqrt_t

    return (
        strike * math.exp(-risk_free * time_years) * _norm_cdf(-d2)
        - spot * math.exp(-div_yield * time_years) * _norm_cdf(-d1)
    )


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class StaleStrikeFlag:
    """One stale-strike flag with all the context needed for operator decision."""
    ticker: str
    option_type: str          # "call" | "put"
    strike: float
    expiry: str               # YYYY-MM-DD
    dte: int

    # Pricing
    ask: float
    last_price: float
    theoretical: float        # BS theoretical at current spot + chain IV
    discount_pct: float       # (theoretical - ask) / theoretical, positive = underpriced

    # Greeks/IV (for sizing context downstream)
    iv: float
    delta: float | None
    volume: int               # Current-session volume
    open_interest: int

    # Underlying context
    spot: float
    last_tape_time: str | None    # When option last traded (staleness proxy)

    notes: list[str] = field(default_factory=list)


@dataclass
class ScanResult:
    ticker: str
    trigger: str
    timestamp: str
    spot: float
    expiry_range: tuple[int, int]
    discount_threshold: float
    volume_floor: int
    risk_free_rate: float

    flagged_strikes: list[StaleStrikeFlag] = field(default_factory=list)
    scanned_count: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


# ============================================================================
# UW API CLIENT
# ============================================================================

class UWClient:
    def __init__(self, api_key: str, verbose: bool = False):
        self.api_key = api_key
        self.verbose = verbose
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        })

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        url = UW_API_BASE + path
        if self.verbose:
            print(f"  GET {url}  params={params}", file=sys.stderr)
        r = self.session.get(url, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def stock_screener_one(self, ticker: str) -> dict:
        """Get one ticker's snapshot — used for current price."""
        data = self._get("/screener/stocks", params={"ticker": ticker, "limit": 1})
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data.get("data", [{}])[0] if isinstance(data.get("data"), list) else data
        return {}

    def expirations(self, ticker: str) -> list[str]:
        """Fetch available expiration dates for the ticker."""
        data = self._get(f"/stock/{ticker}/expiry-breakdown")
        rows = data.get("data", data) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            return []
        # Return list of YYYY-MM-DD expiry strings
        return sorted({r.get("expiry") for r in rows if r.get("expiry")})

    def chain_for_expiry(self, ticker: str, expiry: str, limit: int = 100) -> dict:
        """Pull the full chain at one expiration date."""
        path = f"/stock/{ticker}/option-contracts"
        return self._get(path, params={"expiry": expiry, "limit": limit})


# ============================================================================
# CORE SCAN
# ============================================================================

def _days_to_expiry(expiry_str: str, today: date | None = None) -> int:
    today = today or datetime.now(timezone.utc).date()
    try:
        exp = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    except ValueError:
        return 0
    return (exp - today).days


def evaluate_chain_for_stale_strikes(
    ticker: str,
    spot: float,
    chain_rows: list[dict],
    expiry: str,
    discount_threshold: float,
    volume_floor: int,
    risk_free: float,
    today: date | None = None,
) -> list[StaleStrikeFlag]:
    """
    Pure-logic evaluation of one chain's worth of strikes for staleness.

    Pulled out as a standalone function so tests can drive it without UW.
    """
    flags: list[StaleStrikeFlag] = []
    today = today or datetime.now(timezone.utc).date()
    dte = _days_to_expiry(expiry, today)
    if dte <= 0:
        return flags
    time_years = dte / 365.0

    for row in chain_rows:
        # Extract fields with defensive parsing
        try:
            strike = float(row.get("strike", 0))
            iv = float(row.get("iv", 0) or row.get("implied_volatility", 0) or 0)
            ask = float(row.get("nbbo_ask", 0) or row.get("ask", 0) or 0)
            last = float(row.get("last_price", 0) or 0)
            volume = int(row.get("volume", 0) or 0)
            oi = int(row.get("open_interest", 0) or 0)
            opt_type = row.get("option_type", "call")
            delta = row.get("delta")
            delta = float(delta) if delta is not None else None
            last_tape = row.get("last_tape_time")
        except (TypeError, ValueError):
            continue

        if strike <= 0 or iv <= 0 or ask <= 0:
            continue

        # Compute theoretical price
        if opt_type == "call":
            theo = black_scholes_call(spot, strike, time_years, iv, risk_free)
        else:
            theo = black_scholes_put(spot, strike, time_years, iv, risk_free)

        if theo <= 0:
            continue

        discount = (theo - ask) / theo

        # Stale criteria:
        # 1. ask materially below theoretical
        # 2. low volume (no one has bid the contract up; quote may be stale)
        if discount < (1 - discount_threshold):
            continue
        if volume > volume_floor:
            continue

        notes: list[str] = []
        if volume == 0:
            notes.append("zero volume today")
        if oi < 10:
            notes.append(f"low OI ({oi})")
        if last > 0 and last < ask * 0.5:
            notes.append(f"last trade ${last:.2f} <<< ask ${ask:.2f} (stale last)")

        flags.append(StaleStrikeFlag(
            ticker=ticker,
            option_type=opt_type,
            strike=strike,
            expiry=expiry,
            dte=dte,
            ask=ask,
            last_price=last,
            theoretical=theo,
            discount_pct=discount * 100,
            iv=iv,
            delta=delta,
            volume=volume,
            open_interest=oi,
            spot=spot,
            last_tape_time=last_tape,
            notes=notes,
        ))

    return flags


def scan_stale_leaps(
    client: UWClient,
    ticker: str,
    trigger: str,
    expiry_min_dte: int = DEFAULT_EXPIRY_MIN_DTE,
    expiry_max_dte: int = DEFAULT_EXPIRY_MAX_DTE,
    discount_threshold: float = DEFAULT_DISCOUNT_THRESHOLD,
    volume_floor: int = DEFAULT_VOLUME_FLOOR,
    risk_free: float = DEFAULT_RISK_FREE_RATE,
) -> ScanResult:
    """Main scan entry point. Returns ScanResult."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = ScanResult(
        ticker=ticker,
        trigger=trigger,
        timestamp=ts,
        spot=0.0,
        expiry_range=(expiry_min_dte, expiry_max_dte),
        discount_threshold=discount_threshold,
        volume_floor=volume_floor,
        risk_free_rate=risk_free,
    )

    try:
        # Get current spot
        info = client.stock_screener_one(ticker)
        spot = float(info.get("close", 0) or info.get("price", 0) or 0)
        if spot <= 0:
            result.error = "could not fetch spot price"
            return result
        result.spot = spot

        # Get expirations in window
        all_expirations = client.expirations(ticker)
        today = datetime.now(timezone.utc).date()
        target_expirations = []
        for exp_str in all_expirations:
            dte = _days_to_expiry(exp_str, today)
            if expiry_min_dte <= dte <= expiry_max_dte:
                target_expirations.append(exp_str)

        if not target_expirations:
            result.error = f"no expirations in {expiry_min_dte}-{expiry_max_dte} DTE window"
            return result

        # Iterate target expirations + evaluate each chain
        scanned_count = 0
        all_flags: list[StaleStrikeFlag] = []
        for exp in target_expirations:
            chain_data = client.chain_for_expiry(ticker, exp, limit=100)
            chain_rows = chain_data.get("data", []) if isinstance(chain_data, dict) else chain_data
            if not isinstance(chain_rows, list):
                continue
            scanned_count += len(chain_rows)
            flags = evaluate_chain_for_stale_strikes(
                ticker=ticker,
                spot=spot,
                chain_rows=chain_rows,
                expiry=exp,
                discount_threshold=discount_threshold,
                volume_floor=volume_floor,
                risk_free=risk_free,
                today=today,
            )
            all_flags.extend(flags)

        result.scanned_count = scanned_count
        # Sort flags by discount % descending (most underpriced first)
        all_flags.sort(key=lambda f: -f.discount_pct)
        result.flagged_strikes = all_flags

    except requests.HTTPError as e:
        result.error = f"HTTP {e.response.status_code}"
    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"

    return result


# ============================================================================
# OUTPUT FORMATTING
# ============================================================================

def render_text_report(result: ScanResult, verbose: bool = False) -> str:
    out: list[str] = []
    out.append("=" * 78)
    out.append(f"STALE LEAPS SCAN v1.0 — {result.ticker}")
    out.append("=" * 78)
    out.append(f"  Trigger:       {result.trigger}  ({TRIGGER_TYPES.get(result.trigger, 'custom')})")
    out.append(f"  Timestamp:     {result.timestamp}")
    out.append(f"  Spot:          ${result.spot:.2f}")
    out.append(f"  Expiry range:  {result.expiry_range[0]}-{result.expiry_range[1]} DTE")
    out.append(f"  Discount cap:  {result.discount_threshold*100:.0f}% (flag ask < theo × {result.discount_threshold:.2f})")
    out.append(f"  Volume floor:  {result.volume_floor} contracts today")
    out.append("")

    if result.error:
        out.append(f"  ⚠️  ERROR: {result.error}")
        out.append("=" * 78)
        return "\n".join(out)

    if not result.flagged_strikes:
        out.append(f"  No stale strikes found ({result.scanned_count} scanned)")
        out.append("=" * 78)
        return "\n".join(out)

    out.append(f"  FLAGGED STRIKES ({len(result.flagged_strikes)} of {result.scanned_count} scanned)")
    out.append("  " + "-" * 74)
    out.append(f"  {'Strike':>8s}  {'Exp':>10s}  {'DTE':>4s}  {'Ask':>7s}  {'Theo':>7s}  {'Disc%':>6s}  {'IV':>5s}  {'Vol':>4s}  {'OI':>5s}")
    for f in result.flagged_strikes:
        out.append(
            f"  {f.option_type[:1].upper()}{f.strike:>7.1f}  {f.expiry}  {f.dte:>4d}  "
            f"${f.ask:>6.2f}  ${f.theoretical:>6.2f}  {f.discount_pct:>5.1f}%  "
            f"{f.iv*100:>4.0f}%  {f.volume:>4d}  {f.open_interest:>5d}"
        )
        if verbose and f.notes:
            for n in f.notes:
                out.append(f"           · {n}")
    out.append("")
    out.append("  INTERPRETATION")
    out.append("  " + "-" * 74)
    out.append("  Strikes above are priced below Black-Scholes theoretical at current")
    out.append("  spot + current chain IV. Consistent with stale-quote pattern: MMs")
    out.append("  have not requoted these contracts since the underlying moved.")
    out.append("  Edge typically closes in 24-72h as MMs catch up.")
    out.append("  Defined-risk LONG only per v11.10 (no naked short suggestions).")
    out.append("=" * 78)
    return "\n".join(out)


# ============================================================================
# CLI
# ============================================================================

def main() -> int:
    p = argparse.ArgumentParser(description="Stale long-dated chain scanner (W8/Game C v1.0)")
    p.add_argument("--ticker", required=True, help="Ticker symbol to scan")
    p.add_argument("--trigger", choices=list(TRIGGER_TYPES.keys()), default="manual",
                   help="Why this scan was invoked (informational)")
    p.add_argument("--expiry-min", type=int, default=DEFAULT_EXPIRY_MIN_DTE,
                   help=f"Min DTE for chains scanned (default {DEFAULT_EXPIRY_MIN_DTE})")
    p.add_argument("--expiry-max", type=int, default=DEFAULT_EXPIRY_MAX_DTE,
                   help=f"Max DTE for chains scanned (default {DEFAULT_EXPIRY_MAX_DTE})")
    p.add_argument("--discount", type=float, default=DEFAULT_DISCOUNT_THRESHOLD,
                   help=f"Flag strikes where ask < theo × this (default {DEFAULT_DISCOUNT_THRESHOLD})")
    p.add_argument("--volume-floor", type=int, default=DEFAULT_VOLUME_FLOOR,
                   help=f"Skip strikes with > this volume today (default {DEFAULT_VOLUME_FLOOR})")
    p.add_argument("--risk-free", type=float, default=DEFAULT_RISK_FREE_RATE,
                   help=f"Risk-free rate for BS calc (default {DEFAULT_RISK_FREE_RATE})")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--verbose", action="store_true", help="Per-strike notes")
    args = p.parse_args()

    api_key = os.environ.get("UW_API_KEY")
    if not api_key:
        print("ERROR: UW_API_KEY env var not set", file=sys.stderr)
        return 1

    client = UWClient(api_key=api_key, verbose=args.verbose)
    result = scan_stale_leaps(
        client=client,
        ticker=args.ticker.upper(),
        trigger=args.trigger,
        expiry_min_dte=args.expiry_min,
        expiry_max_dte=args.expiry_max,
        discount_threshold=args.discount,
        volume_floor=args.volume_floor,
        risk_free=args.risk_free,
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(render_text_report(result, verbose=args.verbose))

    return 0 if result.error is None else 2


if __name__ == "__main__":
    sys.exit(main())
