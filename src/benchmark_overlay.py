#!/usr/bin/env python3
"""
benchmark_overlay.py — Benchmark Overlay helper for the 📊 Trade Outcomes DB.

Investing 2026 framework  ·  v0 build, Part 1  ·  pure-logic, deterministic.

WHY THIS EXISTS
---------------
The framework logs whether a trade made money. It has never logged whether
the trade beat simply buying the index over the same window. That blind spot
means no principle and no source has ever been measured against the cheapest
possible alternative. This helper closes it.

WHAT IT DOES
------------
Given one closed trade (entry date, exit date, the trade's own % return) and
daily close series for the benchmark indices, it computes:
  - each index's date-matched return over the trade window
  - the trade's excess return vs QQQ  (alpha over beta)
  - a beat/miss flag

Date-matching handles weekends and market holidays: a trade date with no
index close is matched back to the most recent prior trading day.

HOW IT IS USED
--------------
Called at outcome-logging time (the existing outcome / PDF-ingest step).
Index closes are fetched via UW get_ticker_close_prices and passed in as
JSON. This module does only the deterministic math — it does not touch UW
or Notion.

OUTPUT KEY  ->  📊 Trade Outcomes FIELD
---------------------------------------
  entry_date            ->  Date Entry
  qqq_return_pct        ->  QQQ Return Pct
  spy_return_pct        ->  SPY Return Pct
  sector_benchmark_pct  ->  Sector Benchmark Pct
  excess_vs_qqq_pct     ->  Excess vs QQQ Pct
  beat_qqq              ->  Beat QQQ
( trade input `return_pct` maps from the trade's Realized PnL Pct. )

Percentages are plain numbers — 16.18 means 16.18% — matching the
"Realized PnL Pct" convention (25.0 = 25%).

CLI
---
  python benchmark_overlay.py --self-test
  python benchmark_overlay.py --trade trade.json --indices indices.json

trade.json    {"entry_date":"2026-04-14","exit_date":"2026-05-26",
               "return_pct":65.3,"sector_etf":"SMH"}
indices.json  {"QQQ":[{"date":"2026-04-14","c":628.60}, ...],
               "SPY":[...], "SMH":[...]}
"""

import argparse
import json
import sys


def _sorted_series(series):
    """Return the close series sorted ascending by date string."""
    return sorted(series, key=lambda r: r["date"])


def _close_on_or_before(sorted_series, target_date):
    """Find the close for target_date, or the most recent trading day before
    it (handles weekends / holidays). Expects an ascending-sorted series.
    Returns (date, close) or None if target_date precedes the whole series."""
    best = None
    for row in sorted_series:
        if row["date"] <= target_date:
            best = (row["date"], row["c"])
        else:
            break
    return best


def index_return_pct(series, entry_date, exit_date):
    """% return of an index between entry and exit, date-matched to the most
    recent trading day on-or-before each date. Returns (pct, flags)."""
    flags = []
    s = _sorted_series(series)
    if not s:
        return None, ["empty_series"]
    e = _close_on_or_before(s, entry_date)
    x = _close_on_or_before(s, exit_date)
    if e is None:
        return None, ["entry_before_series"]
    if x is None:
        return None, ["exit_before_series"]
    if e[0] != entry_date:
        flags.append(f"entry_matched_to_{e[0]}")
    if x[0] != exit_date:
        flags.append(f"exit_matched_to_{x[0]}")
    if e[1] == 0:
        return None, flags + ["zero_entry_close"]
    return round((x[1] / e[1] - 1.0) * 100.0, 2), flags


def benchmark_trade(trade, indices):
    """Compute the full benchmark overlay for one closed trade.

    trade   : {entry_date, exit_date, return_pct, sector_etf?}
    indices : {ticker: [{date, c}, ...]}
    """
    out = {
        "entry_date": trade.get("entry_date"),
        "exit_date": trade.get("exit_date"),
        "trade_return_pct": trade.get("return_pct"),
        "qqq_return_pct": None,
        "spy_return_pct": None,
        "sector_etf": trade.get("sector_etf"),
        "sector_benchmark_pct": None,
        "excess_vs_qqq_pct": None,
        "beat_qqq": None,
        "flags": [],
    }

    if not out["entry_date"] or not out["exit_date"]:
        out["flags"].append("missing_dates")
        return out

    entry, exit_ = out["entry_date"], out["exit_date"]

    if "QQQ" in indices:
        q, qf = index_return_pct(indices["QQQ"], entry, exit_)
        out["qqq_return_pct"] = q
        out["flags"] += [f"QQQ:{f}" for f in qf]
    else:
        out["flags"].append("QQQ:missing")

    if "SPY" in indices:
        sp, spf = index_return_pct(indices["SPY"], entry, exit_)
        out["spy_return_pct"] = sp
        out["flags"] += [f"SPY:{f}" for f in spf]

    sec = trade.get("sector_etf")
    if sec and sec in indices:
        se, sef = index_return_pct(indices[sec], entry, exit_)
        out["sector_benchmark_pct"] = se
        out["flags"] += [f"{sec}:{f}" for f in sef]

    tr = out["trade_return_pct"]
    if tr is not None and out["qqq_return_pct"] is not None:
        out["excess_vs_qqq_pct"] = round(tr - out["qqq_return_pct"], 2)
        out["beat_qqq"] = out["excess_vs_qqq_pct"] > 0.0

    return out


def _self_test():
    # QQQ 4/14 -> 5/26 = +16.18% ; SMH 4/14 -> 5/26 = +33.22%
    qqq = [
        {"date": "2026-04-13", "c": 617.39},
        {"date": "2026-04-14", "c": 628.60},
        {"date": "2026-05-22", "c": 717.54},
        {"date": "2026-05-26", "c": 730.28},
    ]
    smh = [
        {"date": "2026-04-14", "c": 452.00},
        {"date": "2026-05-26", "c": 602.14},
    ]
    indices = {"QQQ": qqq, "SMH": smh}
    passed = failed = 0

    def check(name, cond):
        nonlocal passed, failed
        if cond:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {name}")

    # 1. exact-date QQQ return
    q, _ = index_return_pct(qqq, "2026-04-14", "2026-05-26")
    check("qqq 4/14->5/26 == 16.18", q == 16.18)

    # 2. weekend exit (5/24 Sun) matches back to 5/22 Fri
    _, f2 = index_return_pct(qqq, "2026-04-14", "2026-05-24")
    check("weekend exit matched back", any("matched_to_2026-05-22" in x for x in f2))

    # 3. entry before the series -> None
    q3, f3 = index_return_pct(qqq, "2026-01-01", "2026-05-26")
    check("entry before series -> None", q3 is None and "entry_before_series" in f3)

    # 4. full overlay — a big winner
    res = benchmark_trade(
        {"entry_date": "2026-04-14", "exit_date": "2026-05-26",
         "return_pct": 213.0, "sector_etf": "SMH"}, indices)
    check("excess vs qqq", res["excess_vs_qqq_pct"] == round(213.0 - 16.18, 2))
    check("beat qqq true", res["beat_qqq"] is True)
    check("sector benchmark SMH == 33.22", res["sector_benchmark_pct"] == 33.22)

    # 5. a trade that lagged QQQ, no sector ETF
    res2 = benchmark_trade(
        {"entry_date": "2026-04-14", "exit_date": "2026-05-26",
         "return_pct": 5.0}, indices)
    check("beat qqq false", res2["beat_qqq"] is False)
    check("missing sector ok", res2["sector_benchmark_pct"] is None)

    # 6. missing exit date -> graceful flag
    res3 = benchmark_trade({"entry_date": "2026-04-14", "return_pct": 10.0}, indices)
    check("missing dates flagged", "missing_dates" in res3["flags"])

    # 7. empty series
    q7, f7 = index_return_pct([], "2026-04-14", "2026-05-26")
    check("empty series -> None", q7 is None and "empty_series" in f7)

    print(f"\nbenchmark_overlay self-test: {passed} passed, {failed} failed")
    return failed == 0


def main():
    ap = argparse.ArgumentParser(description="Benchmark Overlay helper (v0 Part 1)")
    ap.add_argument("--self-test", action="store_true", help="run the self-test suite")
    ap.add_argument("--trade", help="path to trade JSON")
    ap.add_argument("--indices", help="path to index close-series JSON")
    args = ap.parse_args()

    if args.self_test:
        sys.exit(0 if _self_test() else 1)

    if args.trade and args.indices:
        with open(args.trade) as fh:
            trade = json.load(fh)
        with open(args.indices) as fh:
            indices = json.load(fh)
        print(json.dumps(benchmark_trade(trade, indices), indent=2))
        return

    ap.print_help()


if __name__ == "__main__":
    main()
