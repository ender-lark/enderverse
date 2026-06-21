#!/usr/bin/env python3
"""
options_uw_adapter.py — the live Unusual Whales adapter for the options-expression engine.

Assembles the normalized `subject` dict that options_expression.build_expression() consumes,
from real UW MCP responses. Field shapes were CONFIRMED against live pulls on 2026-06-18:

  get_stock_screener(ticker=T, limit=1) -> {"result":[{ iv_rank, iv30d, implied_move_perc,
      next_earnings_date, close, prev_close, week_52_high, week_52_low, realized_volatility, ... }]}
  get_options_chain(ticker=T, expiry=...) -> {"result":[{ option_symbol:"NVDA260618C00210000",
      implied_volatility:"1.48..", open_interest:98480, nbbo_bid:"0.38", nbbo_ask:"0.51",
      volume:..., ... }]}   ⚠ NOTE: NO delta/greek and NO separate strike/type/expiry fields —
      they are parsed from the OCC option_symbol, and delta is approximated from IV (Black-Scholes).

ARCHITECTURE (mirrors the repo convention: pure normalizers + caller-fetches-via-MCP):
  • PURE normalizers (no network, no src import) turn raw UW responses into normalized pieces.
  • assemble_subject(...) merges the UW market/chain pieces with the CONVICTION-side fields
    (direction, conviction_intact, thesis_break, horizon, recent_options_loss) and the ACCOUNT-side
    fields (portfolio_value, open_premium_at_risk) into the engine's subject.
  • The actual MCP calls happen UPSTREAM (chat session / routine), exactly like uw_iv_context /
    uw_opportunity_scan — this module stays pure + unit-testable with canned fixtures.

The conviction/account fields are NOT UW's to give — they come from the conviction system
(theses / case_file / dossier) and the account layer. The adapter never invents them; missing
conviction => the engine's conviction gate handles it.
"""
from __future__ import annotations

import math
import re
from datetime import date
from typing import Any, Optional

# OCC option symbol tail: 6-digit yymmdd + C/P + 8-digit strike (x1000).
_OCC_RE = re.compile(r"(\d{6})([CP])(\d{8})$")


def _arr(x) -> list:
    """Unwrap a UW response to a list of rows. Handles both confirmed chain shapes:
    nearest-expiry returns {"result":[...]}; an explicit-expiry returns {"states":[...]}.
    Also tolerates {data|results:[...]} and a bare list."""
    if isinstance(x, dict):
        inner = x.get("result") or x.get("states") or x.get("data") or x.get("results")
        return _arr(inner) if isinstance(inner, dict) else (inner or [])
    return x or []


def _f(x) -> Optional[float]:
    try:
        if x is None or x == "":
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def _first(d, *keys):
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d and d[k] is not None and d[k] != "":
            return d[k]
    return None


def occ_parse(symbol) -> tuple[Optional[str], Optional[float], Optional[str]]:
    """OCC option_symbol -> (side, strike, expiry 'YYYY-MM-DD'). Tolerant -> (None, None, None)."""
    if not isinstance(symbol, str):
        return (None, None, None)
    m = _OCC_RE.search(symbol.strip())
    if not m:
        return (None, None, None)
    yymmdd, cp, strike8 = m.groups()
    try:
        expiry = f"20{yymmdd[0:2]}-{yymmdd[2:4]}-{yymmdd[4:6]}"
        date.fromisoformat(expiry)  # validate
    except ValueError:
        expiry = None
    side = "call" if cp == "C" else "put"
    return (side, int(strike8) / 1000.0, expiry)


def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def approx_delta(side: str, spot: Optional[float], strike: Optional[float],
                 iv: Optional[float], dte: Optional[int]) -> Optional[float]:
    """Black-Scholes delta (r=0, no div) from IV — because the UW chain carries no greeks.
    Falls back to a moneyness proxy if IV/DTE are missing, so strike selection still works."""
    spot, strike, iv = _f(spot), _f(strike), _f(iv)
    if not spot or not strike or spot <= 0 or strike <= 0:
        return None
    if iv and iv > 0 and dte and dte > 0:
        T = dte / 365.0
        d1 = (math.log(spot / strike) + 0.5 * iv * iv * T) / (iv * math.sqrt(T))
        dc = _ncdf(d1)
        return round(dc if side == "call" else dc - 1.0, 4)
    # fallback: crude moneyness proxy in [~0.05, ~0.95]
    money = max(-0.6, min(0.6, (spot - strike) / spot))
    dc = max(0.05, min(0.95, 0.5 + money))
    return round(dc if side == "call" else dc - 1.0, 4)


def normalize_chain(raw, *, spot: Optional[float], as_of: str) -> list[dict]:
    """Raw get_options_chain -> list of engine-shaped contract dicts. Handles BOTH confirmed
    shapes: prefers explicit strike/option_type/expires + REAL greeks (delta) when present
    (explicit-expiry shape), else parses the OCC option_symbol and approximates delta from IV
    (nearest-expiry shape). Maps `theo` -> mid and `last_price` -> last when NBBO bid/ask are
    absent. Tolerant: a row that fails to parse is skipped, never raised."""
    try:
        as_of_d = date.fromisoformat(str(as_of)[:10])
    except (ValueError, TypeError):
        as_of_d = None
    out: list[dict] = []
    for r in _arr(raw):
        if not isinstance(r, dict):
            continue
        # explicit fields first (explicit-expiry shape), else OCC parse (nearest-expiry shape)
        side = str(_first(r, "option_type", "type", "put_call") or "").lower()
        side = "call" if side.startswith("c") else ("put" if side.startswith("p") else None)
        strike = _f(_first(r, "strike", "strike_price"))
        expiry = _first(r, "expires", "expiry", "expiration")
        if side is None or strike is None or expiry is None:
            o_side, o_strike, o_exp = occ_parse(_first(r, "option_symbol", "option_chain", "symbol"))
            side = side or o_side
            strike = strike if strike is not None else o_strike
            expiry = expiry or o_exp
        if side is None or strike is None or expiry is None:
            continue
        expiry = str(expiry)[:10]
        dte = None
        if as_of_d is not None:
            try:
                dte = (date.fromisoformat(expiry) - as_of_d).days
            except ValueError:
                dte = None
        iv = _f(_first(r, "iv", "implied_volatility", "implied_vol"))
        delta = _f(_first(r, "delta"))           # REAL greek when present (explicit-expiry shape)
        if delta is None:
            delta = approx_delta(side, spot, strike, iv, dte)
        contract = {
            "expiry": expiry, "dte": dte, "strike": strike, "type": side, "delta": delta, "iv": iv,
            "bid": _f(_first(r, "nbbo_bid", "bid")), "ask": _f(_first(r, "nbbo_ask", "ask")),
            "oi": _f(_first(r, "open_interest", "oi")) or 0,
            "volume": _f(_first(r, "volume")) or 0,
        }
        mid = _f(_first(r, "theo", "mid", "mark"))   # theoretical mid when there's no NBBO
        if mid is not None:
            contract["mid"] = mid
        last = _f(_first(r, "last_price", "last", "price"))
        if last is not None:
            contract["last"] = last
        out.append(contract)
    return out


def normalize_market(row) -> dict:
    """Raw get_stock_screener / ohlc row -> normalized market context for the subject."""
    rows = _arr(row)
    row = rows[0] if rows else (row if isinstance(row, dict) else {})
    spot = _f(_first(row, "close", "last", "price"))
    prev = _f(_first(row, "prev_close", "previous_close"))
    one_day_return = (spot / prev - 1.0) if (spot and prev and prev > 0) else None
    em = _f(_first(row, "implied_move_perc", "implied_move_perc_30"))
    return {
        "spot": spot,
        "prev_close": prev,
        "one_day_return": round(one_day_return, 4) if one_day_return is not None else None,
        "iv_rank": _f(_first(row, "iv_rank")),
        "atm_iv": _f(_first(row, "iv30d", "iv_30d", "atm_iv")),
        "expected_move_pct": em,
        "earnings_date": _first(row, "next_earnings_date", "earnings_date"),
        "week_52_high": _f(_first(row, "week_52_high")),
        "week_52_low": _f(_first(row, "week_52_low")),
        "realized_vol": _f(_first(row, "realized_volatility", "volatility_30")),
        "as_of": _first(row, "date"),
    }


def assemble_subject(*, ticker: str, market: dict, chain_contracts: list[dict],
                     conviction: Optional[dict] = None, account: Optional[dict] = None,
                     as_of: Optional[str] = None) -> dict:
    """Merge the UW market + chain pieces with conviction-side and account-side fields into the
    engine subject. Conviction defaults to an intact bullish view (the caller should pass the real
    conviction from theses/case_file); account fields are optional (engine degrades to per-contract
    sizing if portfolio_value is absent)."""
    conviction = conviction or {}
    account = account or {}
    as_of = as_of or market.get("as_of")
    subject: dict[str, Any] = {
        "ticker": str(ticker).upper(),
        "as_of": as_of,
        "spot": market.get("spot"),
        "iv_rank": market.get("iv_rank"),
        "atm_iv": market.get("atm_iv"),
        "one_day_return": market.get("one_day_return"),
        "earnings_date": market.get("earnings_date"),
        "chain": chain_contracts or [],
        # --- conviction-side (NOT UW's to give) ---
        "direction": conviction.get("direction", "bullish"),
        "conviction_intact": conviction.get("conviction_intact", True),
        "thesis_break": conviction.get("thesis_break", False),
        "thesis_horizon_days": conviction.get("thesis_horizon_days", 90),
        "conviction_strength": conviction.get("conviction_strength"),
        "recent_options_loss": conviction.get("recent_options_loss", False),
        # --- account-side ---
        "portfolio_value": account.get("portfolio_value"),
        "open_premium_at_risk": account.get("open_premium_at_risk"),
    }
    return subject


# ─────────────────────────────────── self-test ───────────────────────────────
def _self_test() -> int:
    """Uses TRIMMED REAL UW shapes captured 2026-06-18 (NVDA) so the field maps stay honest."""
    fails: list[str] = []

    def chk(c, label):
        if not c:
            fails.append(label)

    # OCC parsing against the real symbol shape
    side, strike, expiry = occ_parse("NVDA260618C00210000")
    chk(side == "call" and strike == 210.0 and expiry == "2026-06-18", f"occ parse ({side},{strike},{expiry})")
    side2, strike2, _ = occ_parse("NVDA260618P00207500")
    chk(side2 == "put" and strike2 == 207.5, "occ parse put/strike")

    # delta approximation: ITM call > 0.5, OTM call < 0.5
    chk(approx_delta("call", 210.0, 200.0, 0.4, 60) > 0.5, "ITM call delta > 0.5")
    chk(0 < approx_delta("call", 210.0, 230.0, 0.4, 60) < 0.5, "OTM call delta < 0.5")
    chk(approx_delta("put", 210.0, 230.0, 0.4, 60) < 0, "put delta negative")

    # real screener row (trimmed)
    screener = {"result": [{
        "ticker": "NVDA", "iv_rank": "23.6105", "iv30d": "0.358", "implied_move_perc": "0.070000",
        "next_earnings_date": "2026-08-26", "close": "210.69", "prev_close": "204.65",
        "week_52_high": "236.54", "week_52_low": "142.03", "realized_volatility": "0.444176",
        "date": "2026-06-18"}]}
    m = normalize_market(screener)
    chk(m["spot"] == 210.69 and m["iv_rank"] == 23.6105, "market spot/iv_rank")
    chk(abs(m["one_day_return"] - 0.0295) < 0.001, f"1-day return (+{m['one_day_return']})")
    chk(m["atm_iv"] == 0.358 and m["earnings_date"] == "2026-08-26", "atm_iv/earnings")

    # real chain rows (trimmed) -> normalized contracts with delta
    chain = {"result": [
        {"option_symbol": "NVDA260821C00200000", "implied_volatility": "0.40",
         "open_interest": 5000, "nbbo_bid": "22.0", "nbbo_ask": "22.6", "volume": 1200},
        {"option_symbol": "NVDA260821C00230000", "implied_volatility": "0.42",
         "open_interest": 4000, "nbbo_bid": "8.0", "nbbo_ask": "8.4", "volume": 900},
    ]}
    contracts = normalize_chain(chain, spot=210.69, as_of="2026-06-18")
    chk(len(contracts) == 2 and contracts[0]["type"] == "call", "chain normalized")
    chk(contracts[0]["dte"] and contracts[0]["dte"] > 50, "dte computed from expiry")
    chk(contracts[0]["delta"] is not None and contracts[0]["delta"] > contracts[1]["delta"],
        "ITM strike has higher delta than OTM")

    # explicit-expiry "states" shape (REAL greeks + theo mid, no NBBO) — confirmed 2026-06-18
    states = {"states": [
        {"option_symbol": "NVDA260821C00210000", "strike": "210", "option_type": "call",
         "expires": "2026-08-21", "iv": 0.4091, "delta": 0.5432, "theo": 14.775,
         "last_price": "14.70", "open_interest": 18035, "volume": 3825}],
        "price_data": {"price": "210.69"}}
    sc = normalize_chain(states, spot=210.69, as_of="2026-06-18")
    chk(len(sc) == 1 and sc[0]["delta"] == 0.5432, "states shape: real delta passed through")
    chk(sc[0].get("mid") == 14.775 and sc[0]["strike"] == 210.0, "states shape: theo->mid + explicit strike")

    # assemble_subject merges market + chain + conviction + account
    subj = assemble_subject(ticker="NVDA", market=m, chain_contracts=contracts,
                            conviction={"direction": "bullish", "thesis_horizon_days": 60},
                            account={"portfolio_value": 100000})
    chk(subj["ticker"] == "NVDA" and subj["spot"] == 210.69 and subj["chain"], "subject assembled")
    chk(subj["conviction_intact"] is True and subj["thesis_horizon_days"] == 60, "conviction merged")

    if fails:
        print("options_uw_adapter self-test: FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("options_uw_adapter self-test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
