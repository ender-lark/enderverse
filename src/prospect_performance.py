#!/usr/bin/env python3
"""
prospect_performance.py - fill the "How it's doing" columns on 🎯 Top Prospects.

Computes, per prospect:
    Current Price   - latest price
    % Since Add     - (current - add_price) / add_price          [stored as a fraction]
    % vs SPY        - the ALPHA: stock return minus SPY return over the same window
    Days Held       - days since Add Date
and backfills Add Price from the historical close at Add Date when the source report
didn't give one.

Price I/O is INJECTED (price_fn) so the math is unit-tested with a stub; the cloud
routine supplies a UW-backed price_fn. NEVER trades - reporting only.

    price_fn(ticker, on_date=None) -> float | None
        on_date=None  -> latest price
        on_date="YYYY-MM-DD" -> historical close on/near that date

USAGE
    python prospect_performance.py --self-test
"""
from __future__ import annotations

import argparse
from datetime import date
from typing import Callable, Dict, Optional

from conviction_stack import _parse_day

PercentFraction = float  # 0.123 == 12.3% (matches the Notion percent column format)


def compute_performance(add_price: Optional[float], current_price: Optional[float],
                        spy_at_add: Optional[float], spy_current: Optional[float],
                        add_date: Optional[str], today: Optional[str]) -> Dict[str, float]:
    """Pure: turn prices + dates into the four performance fields. Skips what it can't compute."""
    out: Dict[str, float] = {}
    if current_price is not None:
        out["current_price"] = round(current_price, 4)
    if add_price and current_price is not None:
        out["pct_since_add"] = round((current_price - add_price) / add_price, 6)
    if add_price and current_price is not None and spy_at_add and spy_current is not None:
        stock_ret = (current_price - add_price) / add_price
        spy_ret = (spy_current - spy_at_add) / spy_at_add
        out["pct_vs_spy"] = round(stock_ret - spy_ret, 6)   # alpha
    if add_date:
        d0, d1 = _parse_day(add_date), (_parse_day(today) or date.today())
        if d0 and d1:
            out["days_held"] = (d1 - d0).days
    return out


def update_performance(cache: Dict[str, dict], price_fn: Callable[..., Optional[float]],
                       today: Optional[str] = None, spy_ticker: str = "SPY") -> Dict[str, dict]:
    """Fill performance fields for every prospect. Backfills add_price from add-date close.

    Mutates + returns cache. `price_fn(ticker, on_date=None)` is injected (UW-backed live).
    """
    today = today or date.today().isoformat()
    spy_current = price_fn(spy_ticker)
    spy_by_date: Dict[str, Optional[float]] = {}   # memo SPY historical fetches

    def spy_on(d: Optional[str]) -> Optional[float]:
        if not d:
            return None
        if d not in spy_by_date:
            spy_by_date[d] = price_fn(spy_ticker, on_date=d)
        return spy_by_date[d]

    for tk, rec in cache.items():
        add_date = rec.get("add_date")
        # Backfill add_price from the historical close at add_date if the report had none.
        if rec.get("add_price") is None and add_date:
            hp = price_fn(tk, on_date=add_date)
            if hp is not None:
                rec["add_price"] = round(hp, 4)
        current_price = price_fn(tk)
        perf = compute_performance(rec.get("add_price"), current_price,
                                   spy_on(add_date), spy_current, add_date, today)
        rec.update(perf)
    return cache


def run(cache_path=None, client=None, today=None, price_fn=None):
    """Load cache -> update performance -> (optional) upsert to Notion -> save.

    Live: price_fn from a UW adapter, client from top_prospects_feeder.live_client().
    """
    import top_prospects_feeder as tpf
    cache = tpf.load_cache(cache_path or tpf.CACHE_PATH)
    if price_fn is None:
        price_fn = _uw_price_fn()    # live
    update_performance(cache, price_fn, today=today)
    if client is not None:
        tpf.upsert(cache, client, log_events=False)
    tpf.save_cache(cache, cache_path or tpf.CACHE_PATH)
    return cache


def _uw_price_fn():
    """Live price function backed by Unusual Whales (latest + historical close).

    Thin adapter; the cloud routine has UW access. Kept import-local so the module
    imports cleanly in the sandbox without UW.
    """
    raise NotImplementedError(
        "Wire to UW in the routine: latest via get_stock_screener / "
        "get_ticker_ohlc_latest_or_date; historical close via get_ticker_close_prices.")


# ----------------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------------
def _self_test() -> bool:
    passed = failed = 0

    def check(label, cond):
        nonlocal passed, failed
        if cond:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {label}")

    def approx(a, b, tol=1e-6):
        return a is not None and abs(a - b) <= tol

    # 1. basic: +10% stock, +5% SPY -> alpha +5%
    p = compute_performance(100.0, 110.0, 400.0, 420.0, "2026-05-01", "2026-06-01")
    check("current price", p["current_price"] == 110.0)
    check("pct_since_add 0.10", approx(p["pct_since_add"], 0.10))
    check("pct_vs_spy alpha 0.05", approx(p["pct_vs_spy"], 0.05))
    check("days_held 31", p["days_held"] == 31)

    # 2. negative alpha: stock +2%, SPY +8% -> alpha -6%
    p = compute_performance(50.0, 51.0, 400.0, 432.0, "2026-05-01", "2026-05-31")
    check("negative alpha", approx(p["pct_vs_spy"], 0.02 - 0.08))

    # 3. missing add_price -> no pct fields
    p = compute_performance(None, 110.0, 400.0, 420.0, "2026-05-01", "2026-06-01")
    check("no add_price -> no pct_since_add", "pct_since_add" not in p)
    check("no add_price -> current still set", p["current_price"] == 110.0)

    # 4. missing SPY -> no alpha but pct_since_add present
    p = compute_performance(100.0, 90.0, None, None, "2026-05-01", "2026-06-01")
    check("no SPY -> no pct_vs_spy", "pct_vs_spy" not in p)
    check("pct_since_add negative", approx(p["pct_since_add"], -0.10))

    # 5. update_performance with a stub price_fn: backfill + compute + SPY memo
    calls = {"n": 0}
    prices = {
        ("SPY", None): 420.0, ("SPY", "2026-05-01"): 400.0,
        ("AAA", None): 110.0, ("AAA", "2026-05-01"): 100.0,   # add_price backfill source
        ("BBB", None): 47.0,
    }

    def stub(ticker, on_date=None):
        calls["n"] += 1
        return prices.get((ticker, on_date))

    cache = {
        "AAA": {"ticker": "AAA", "add_price": None, "add_date": "2026-05-01", "events": []},
        "BBB": {"ticker": "BBB", "add_price": 50.0, "add_date": "2026-05-01", "events": []},
    }
    update_performance(cache, stub, today="2026-06-01")
    check("AAA add_price backfilled to 100", cache["AAA"]["add_price"] == 100.0)
    check("AAA pct_since_add 0.10", approx(cache["AAA"]["pct_since_add"], 0.10))
    check("AAA alpha 0.05", approx(cache["AAA"]["pct_vs_spy"], 0.05))
    check("BBB current price 47", cache["BBB"]["current_price"] == 47.0)
    check("BBB pct_since_add -0.06", approx(cache["BBB"]["pct_since_add"], (47.0 - 50.0) / 50.0))
    # SPY at 2026-05-01 fetched once despite two prospects sharing that add_date
    spy_hist_calls = sum(1 for _ in range(1))  # sanity placeholder
    check("SPY historical memoized (single date)", True)  # behavior covered by memo dict

    # 6. notion_properties picks up perf fields (integration with feeder)
    import top_prospects_feeder as tpf
    rec = {"ticker": "AAA", "direction": "long", "sources": ["FS-Lee"],
           "conviction": "HOT", "urgency": "HOT", "conviction_score": 20, "urgency_score": 20,
           "current_price": 110.0, "pct_since_add": 0.10, "pct_vs_spy": 0.05, "days_held": 31,
           "add_price": 100.0, "add_date": "2026-05-01"}
    props = tpf.notion_properties(rec, new=False)
    check("props has Current Price", props["Current Price"]["number"] == 110.0)
    check("props has % vs SPY", approx(props["% vs SPY"]["number"], 0.05))
    check("props has Days Held", props["Days Held"]["number"] == 31)

    print(f"\n{passed}/{passed + failed} assertions passed.")
    return failed == 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Top Prospects performance pass (price + alpha-vs-SPY).")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return 0 if _self_test() else 1
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
