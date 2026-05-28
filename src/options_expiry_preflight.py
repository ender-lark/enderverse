"""
options_expiry_preflight.py
============================
v11.16 Patch 2 Options-Expiry Pre-Flight Surface script.

Operationalizes the v11.16 Patch 2 framework: on every session-open / continuation-
autopilot turn, scan Latest Portfolio for option positions <30 DTE, compute intrinsic
value, classify action-band, and surface ACTION REQUIRED flags for options <5 DTE.

Would have caught IVES $30 calls (1 DTE deep ITM, $2.7K intrinsic) automatically
on 5/14/26 without operator-side surfacing.

Architecture:
- Pure-logic core (parse_option_symbol, compute_dte, classify_action_band) is
  testable without API access. Tests in test_options_expiry_preflight.py.
- CLI wrapper at __main__ takes Latest Portfolio JSON + optional UW price overrides
  and outputs pre-flight digest.

CLI usage:
  python options_expiry_preflight.py --portfolio latest_portfolio.json
  python options_expiry_preflight.py --portfolio latest_portfolio.json \
      --prices '{"IVES":36.84,"BMNR":21.91,"LEU":192.32}'
  python options_expiry_preflight.py --portfolio latest_portfolio.json \
      --as-of 2026-05-14 --max-dte 30

Author: Investing 2026 framework v11.16
Date: 2026-05-14
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# OCC option symbol format: SYMBOL[Spaces]YYMMDDC|P[strike8d]
# e.g. "IVES250516C00030000" = IVES, 2025-05-16, Call, $30.00 strike
OCC_PATTERN = re.compile(
    r"^([A-Z0-9.]{1,6})\s*"     # underlying (1-6 chars)
    r"(\d{2})(\d{2})(\d{2})"     # YY MM DD
    r"([CP])"                    # Call or Put
    r"(\d{8})$"                  # strike × 1000 (8 digits)
)

DEFAULT_MAX_DTE = 30
ACTION_REQUIRED_DTE = 5
DEEP_ITM_DELTA_PROXY = 0.85       # If intrinsic/(intrinsic+time) > 0.85
ATM_DELTA_BAND = (0.35, 0.65)
OTM_DELTA_PROXY = 0.20


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ParsedOption:
    """Parsed OCC option symbol with derived fields."""
    raw_symbol: str
    underlying: str
    expiry: date
    option_type: str  # 'C' or 'P'
    strike: float

    @property
    def is_call(self) -> bool:
        return self.option_type == "C"

    @property
    def is_put(self) -> bool:
        return self.option_type == "P"


@dataclass
class OptionPosition:
    """Option position from Latest Portfolio + scan results."""
    symbol: str
    contracts: int                          # signed (+ long, - short)
    cost_basis: Optional[float] = None
    current_value: Optional[float] = None
    parsed: Optional[ParsedOption] = None
    account: Optional[str] = None

    # Computed
    dte: Optional[int] = None
    underlying_price: Optional[float] = None
    intrinsic: Optional[float] = None       # per contract
    moneyness: Optional[str] = None         # 'ITM', 'ATM', 'OTM'
    action_band: Optional[str] = None       # 'ACTION_REQUIRED' | 'WATCH' | 'OK'
    recommendation: Optional[str] = None    # human-readable next-step
    flags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pure-logic core
# ---------------------------------------------------------------------------

def parse_option_symbol(symbol: str) -> Optional[ParsedOption]:
    """Parse OCC option symbol into structured fields.

    Returns None for malformed inputs rather than raising — caller can flag.
    """
    if not symbol:
        return None
    cleaned = symbol.strip().upper().replace(" ", "")
    m = OCC_PATTERN.match(cleaned)
    if not m:
        return None
    underlying, yy, mm, dd, otype, strike_raw = m.groups()
    try:
        # OCC: years 1990-2089 — anything ≥90 is 19xx, else 20xx
        year = int(yy) + (1900 if int(yy) >= 90 else 2000)
        expiry = date(year, int(mm), int(dd))
        strike = int(strike_raw) / 1000.0
    except (ValueError, OverflowError):
        return None
    return ParsedOption(
        raw_symbol=symbol,
        underlying=underlying,
        expiry=expiry,
        option_type=otype,
        strike=strike,
    )


def compute_dte(expiry: date, as_of: date) -> int:
    """Days to expiration. Can be negative for expired options."""
    return (expiry - as_of).days


def compute_intrinsic(
    option_type: str,
    strike: float,
    underlying: float
) -> float:
    """Per-share intrinsic value. Times 100 for per-contract notional."""
    if option_type == "C":
        return max(0.0, underlying - strike)
    elif option_type == "P":
        return max(0.0, strike - underlying)
    return 0.0


def classify_moneyness(
    option_type: str,
    strike: float,
    underlying: float,
    atm_pct: float = 0.02
) -> str:
    """Classify ITM / ATM / OTM based on strike-vs-underlying distance.

    ATM = within ±atm_pct of underlying (default 2%).
    """
    if not underlying or underlying <= 0:
        return "UNKNOWN"
    pct_from_atm = (strike - underlying) / underlying
    if abs(pct_from_atm) <= atm_pct:
        return "ATM"
    if option_type == "C":
        return "ITM" if pct_from_atm < 0 else "OTM"
    elif option_type == "P":
        return "ITM" if pct_from_atm > 0 else "OTM"
    return "UNKNOWN"


def classify_action_band(
    dte: int,
    moneyness: str,
    max_dte: int = DEFAULT_MAX_DTE,
    action_dte: int = ACTION_REQUIRED_DTE
) -> str:
    """ACTION_REQUIRED / WATCH / OK based on DTE + moneyness.

    Rules:
    - DTE < 0: EXPIRED (post-expiry; should not be in portfolio)
    - DTE <= action_dte: ACTION_REQUIRED (any moneyness)
    - DTE <= max_dte: WATCH
    - DTE > max_dte: OK
    """
    if dte < 0:
        return "EXPIRED"
    if dte <= action_dte:
        return "ACTION_REQUIRED"
    if dte <= max_dte:
        return "WATCH"
    return "OK"


def recommendation_for(pos: OptionPosition) -> str:
    """Build human-readable action recommendation."""
    if pos.action_band == "EXPIRED":
        return "EXPIRED — verify settled out of portfolio"
    if pos.action_band == "OK":
        return "OK — re-evaluate per v11.10 7-rule cadence on next regular check"
    if pos.action_band == "WATCH":
        return f"WATCH — {pos.dte} DTE, monitor for action_dte threshold"

    # ACTION_REQUIRED
    if pos.moneyness == "ITM":
        # Sub-classify by depth
        if pos.parsed and pos.underlying_price:
            depth_pct = abs(pos.parsed.strike - pos.underlying_price) / pos.underlying_price
            if depth_pct >= 0.05:
                return ("DEEP-ITM <5 DTE → SELL-TO-CLOSE (capture intrinsic) "
                        "OR ROLL (if thesis intact) OR EXERCISE (if equity-add desired)")
        return "ITM <5 DTE → SELL-TO-CLOSE or ROLL or EXERCISE decision required"
    if pos.moneyness == "ATM":
        return "ATM <5 DTE → CLOSE or ROLL (gamma risk high)"
    if pos.moneyness == "OTM":
        return ("OTM <5 DTE → LET EXPIRE worthless "
                "OR CLOSE for tax-loss harvest if cost basis material")
    return "ACTION_REQUIRED but moneyness unknown — verify underlying price"


def scan_positions(
    positions: list[OptionPosition],
    underlying_prices: dict[str, float],
    as_of: date,
    max_dte: int = DEFAULT_MAX_DTE,
    action_dte: int = ACTION_REQUIRED_DTE,
) -> list[OptionPosition]:
    """Enrich each position with parsed symbol + DTE + intrinsic + action band.

    Modifies positions in-place AND returns them. Underlying prices not in dict
    are left as None; recommendation falls back to "needs underlying price".
    """
    for pos in positions:
        pos.parsed = parse_option_symbol(pos.symbol)
        if not pos.parsed:
            pos.flags.append("UNPARSEABLE_SYMBOL")
            continue

        pos.dte = compute_dte(pos.parsed.expiry, as_of)
        underlying_px = underlying_prices.get(pos.parsed.underlying)
        if underlying_px is None:
            pos.flags.append("MISSING_UNDERLYING_PRICE")
            pos.action_band = classify_action_band(pos.dte, "UNKNOWN", max_dte, action_dte)
            pos.recommendation = (
                f"{pos.action_band} — underlying price for {pos.parsed.underlying} needed"
            )
            continue

        pos.underlying_price = underlying_px
        pos.intrinsic = compute_intrinsic(pos.parsed.option_type, pos.parsed.strike, underlying_px)
        pos.moneyness = classify_moneyness(pos.parsed.option_type, pos.parsed.strike, underlying_px)
        pos.action_band = classify_action_band(pos.dte, pos.moneyness, max_dte, action_dte)
        pos.recommendation = recommendation_for(pos)

    return positions


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_positions_from_portfolio(portfolio_json: dict) -> list[OptionPosition]:
    """Extract option positions from Latest Portfolio JSON.

    Expects portfolio in schema produced by portfolio-pdf-extractor:
    {
      "accounts": [{"positions": [{...}, ...]}, ...],
      "positions": [{...}, ...]  // top-level fallback
    }
    Option detection heuristic: symbol matches OCC pattern OR contains type field "option".
    """
    raw_positions = []
    accounts = portfolio_json.get("accounts", [])
    for acct in accounts:
        for p in acct.get("positions", []):
            raw_positions.append((p, acct.get("account_id") or acct.get("name")))
    # Top-level fallback
    for p in portfolio_json.get("positions", []):
        raw_positions.append((p, p.get("account") or "unknown"))

    out = []
    for p, account in raw_positions:
        symbol = p.get("symbol") or p.get("ticker") or ""
        # Filter to options
        is_option = (
            p.get("type", "").lower() in ("option", "options", "call", "put") or
            p.get("asset_class", "").lower() == "option" or
            bool(OCC_PATTERN.match(symbol.strip().upper().replace(" ", "")))
        )
        if not is_option:
            continue
        out.append(OptionPosition(
            symbol=symbol,
            contracts=int(p.get("quantity") or p.get("contracts") or 0),
            cost_basis=p.get("cost_basis") or p.get("avg_cost"),
            current_value=p.get("current_value") or p.get("market_value"),
            account=account,
        ))
    return out


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def render_markdown(
    positions: list[OptionPosition],
    as_of: date,
) -> str:
    lines = []
    lines.append("# 🛎️ Options Expiry Pre-Flight")
    lines.append(f"\n**As of: {as_of.isoformat()}**")
    total = len(positions)
    under_30 = [p for p in positions if p.dte is not None and 0 <= p.dte <= 30]
    action_required = [p for p in positions if p.action_band == "ACTION_REQUIRED"]
    expired = [p for p in positions if p.action_band == "EXPIRED"]

    lines.append(f"Scanned: {total} option positions")
    lines.append(f"Within 30 DTE: {len(under_30)} · "
                 f"ACTION REQUIRED (<5 DTE): {len(action_required)} · "
                 f"EXPIRED: {len(expired)}\n")

    if action_required:
        lines.append("\n## 🚨 ACTION REQUIRED (<5 DTE)\n")
        for p in sorted(action_required, key=lambda x: x.dte or 99):
            lines.append(_render_position(p))

    if expired:
        lines.append("\n## ⚠️ EXPIRED (DTE < 0)\n")
        for p in expired:
            lines.append(_render_position(p))

    watch = [p for p in positions if p.action_band == "WATCH"]
    if watch:
        lines.append("\n## 👀 WATCH (5-30 DTE)\n")
        for p in sorted(watch, key=lambda x: x.dte or 99):
            lines.append(_render_position(p))

    if not action_required and not expired and not watch:
        lines.append("\n✅ No options within 30 DTE — pre-flight clean.\n")

    return "\n".join(lines)


def _render_position(p: OptionPosition) -> str:
    if not p.parsed:
        return f"- **{p.symbol}** · UNPARSEABLE · {p.contracts} contracts · {p.account or ''}"
    px_str = f"${p.underlying_price:.2f}" if p.underlying_price else "?"
    intr_str = f"${p.intrinsic * 100:.0f}/ct" if p.intrinsic is not None else "?"
    return (
        f"- **{p.parsed.underlying} {p.parsed.expiry.isoformat()} "
        f"{p.parsed.option_type} ${p.parsed.strike:.2f}** "
        f"({p.contracts} ct, account: {p.account or '?'})\n"
        f"  · DTE {p.dte} · Underlying {px_str} · {p.moneyness or '?'} "
        f"· Intrinsic {intr_str}\n"
        f"  · **{p.recommendation}**"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="v11.16 Patch 2 Options-Expiry Pre-Flight Surface"
    )
    parser.add_argument(
        "--portfolio",
        required=True,
        help="Path to Latest Portfolio JSON (from portfolio-pdf-extractor or Notion export)"
    )
    parser.add_argument(
        "--prices",
        default="{}",
        help='JSON dict of underlying ticker → price (e.g. \'{"IVES":36.84}\')'
    )
    parser.add_argument(
        "--as-of",
        default=date.today().isoformat()
    )
    parser.add_argument(
        "--max-dte",
        type=int,
        default=DEFAULT_MAX_DTE
    )
    parser.add_argument(
        "--action-dte",
        type=int,
        default=ACTION_REQUIRED_DTE
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown"
    )
    args = parser.parse_args()

    with open(args.portfolio) as f:
        portfolio = json.load(f)
    prices = json.loads(args.prices)
    as_of = datetime.fromisoformat(args.as_of).date()

    positions = load_positions_from_portfolio(portfolio)
    scan_positions(positions, prices, as_of, args.max_dte, args.action_dte)

    if args.format == "json":
        out = []
        for p in positions:
            d = asdict(p)
            # ParsedOption nested dataclass needs special handling
            if d.get("parsed") and isinstance(d["parsed"], dict):
                if "expiry" in d["parsed"] and isinstance(d["parsed"]["expiry"], date):
                    d["parsed"]["expiry"] = d["parsed"]["expiry"].isoformat()
            out.append(d)
        print(json.dumps(out, indent=2, default=str))
    else:
        print(render_markdown(positions, as_of))


if __name__ == "__main__":
    main()
