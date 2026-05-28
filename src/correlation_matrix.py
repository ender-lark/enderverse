#!/usr/bin/env python3
"""
correlation_matrix.py — sector ETF correlation matrix pipeline
Candidate I (v11.9)

Computes rolling pairwise correlations across the 11 SPDR sectors plus
operator-relevant thematic ETFs. Output feeds into:
  - position_sizer.py N_eff correlation discount (live ρ_avg per factor bucket)
  - Launcher delta-output (correlation shifts >0.10 over rolling window)
  - Operator-facing "factor neighborhood" reads on individual names

Inputs:
  - Price history JSON: {"TICKER": [{"date": "YYYY-MM-DD", "close": float}, ...]}
  - Window (default 60 trading days)

Output:
  - N×N correlation matrix as nested dict
  - Per-ticker mean correlation to its sector
  - Identifies "ρ shifts" between current and prior window (decay tracking)

Stdlib-only — no numpy/pandas dependency.

Usage:
  python3 correlation_matrix.py --test-fixture
  python3 correlation_matrix.py --prices path/to/prices.json --window 60 --json
"""

from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import dataclass, field
from typing import Optional


# ============================================================================
# SPDR sectors + operator thematic ETFs
# ============================================================================

SPDR_SECTORS = [
    "XLB",  # Materials
    "XLC",  # Communication Services
    "XLE",  # Energy
    "XLF",  # Financials
    "XLI",  # Industrials
    "XLK",  # Technology
    "XLP",  # Consumer Staples
    "XLRE", # Real Estate
    "XLU",  # Utilities
    "XLV",  # Health Care
    "XLY",  # Consumer Discretionary
]

THEMATIC_ETFS = [
    "SMH",   # Semis
    "MAGS",  # Mag 7
    "IVES",  # AI Wedbush
    "IGV",   # Software
    "GRNY",  # Granny Shots
    "GRNJ",  # Granny Junior
    "GDX",   # Gold miners
    "ITA",   # Defense
]


# ============================================================================
# Stats helpers (stdlib-only)
# ============================================================================

def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _stdev(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def _pearson(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation coefficient. Returns 0 on degenerate input."""
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    mx, my = _mean(xs), _mean(ys)
    sx, sy = _stdev(xs), _stdev(ys)
    if sx == 0 or sy == 0:
        return 0.0
    n = len(xs)
    cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / (n - 1)
    return cov / (sx * sy)


def _log_returns(closes: list[float]) -> list[float]:
    """Daily log returns from a close-price series."""
    out = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0 and closes[i] > 0:
            out.append(math.log(closes[i] / closes[i - 1]))
        else:
            out.append(0.0)
    return out


# ============================================================================
# Data model
# ============================================================================

@dataclass
class CorrelationMatrix:
    tickers: list[str]
    matrix: dict[str, dict[str, float]]  # ticker -> ticker -> rho
    window_days: int
    n_observations: int

    def get(self, t1: str, t2: str) -> float:
        return self.matrix.get(t1, {}).get(t2, 0.0)

    def mean_corr_to_others(self, ticker: str) -> float:
        row = self.matrix.get(ticker, {})
        others = [v for k, v in row.items() if k != ticker]
        return _mean(others) if others else 0.0


# ============================================================================
# Pipeline
# ============================================================================

def build_correlation_matrix(
    price_history: dict[str, list[dict]],
    window: int = 60,
) -> CorrelationMatrix:
    """
    Build correlation matrix from {ticker: [{date, close}, ...]} input.

    Uses the last `window` observations per ticker. Aligns on date intersection
    across all tickers (drops dates where any ticker is missing).
    """
    tickers = sorted(price_history.keys())
    if not tickers:
        return CorrelationMatrix(tickers=[], matrix={}, window_days=window, n_observations=0)

    # Build {date: {ticker: close}} index
    by_date: dict[str, dict[str, float]] = {}
    for t in tickers:
        for row in price_history[t]:
            by_date.setdefault(row["date"], {})[t] = row["close"]

    # Keep only dates that have ALL tickers
    all_tickers_set = set(tickers)
    aligned_dates = sorted([
        d for d, vals in by_date.items() if all_tickers_set.issubset(vals.keys())
    ])

    # Use last `window+1` dates so we get `window` returns
    n_dates_needed = window + 1
    if len(aligned_dates) > n_dates_needed:
        aligned_dates = aligned_dates[-n_dates_needed:]

    if len(aligned_dates) < 3:
        return CorrelationMatrix(
            tickers=tickers, matrix={}, window_days=window,
            n_observations=len(aligned_dates),
        )

    # Per-ticker returns vector aligned to dates
    returns: dict[str, list[float]] = {}
    for t in tickers:
        closes = [by_date[d][t] for d in aligned_dates]
        returns[t] = _log_returns(closes)

    # Pairwise Pearson on log returns
    matrix: dict[str, dict[str, float]] = {}
    for t1 in tickers:
        matrix[t1] = {}
        for t2 in tickers:
            if t1 == t2:
                matrix[t1][t2] = 1.0
            else:
                matrix[t1][t2] = _pearson(returns[t1], returns[t2])

    return CorrelationMatrix(
        tickers=tickers, matrix=matrix, window_days=window,
        n_observations=len(returns[tickers[0]]),
    )


# ============================================================================
# Synthetic fixture for testing
# ============================================================================

def _synthesize_fixture(n_days: int = 80, seed: int = 42) -> dict[str, list[dict]]:
    """
    Generate synthetic price history for 11 SPDR sectors that mimics realistic
    cross-correlation structure. Used by --test-fixture validation.

    Designed to produce correlations roughly in the 0.45-0.85 range across
    sectors (consistent with empirical SPDR sector correlations during
    risk-on regimes).
    """
    import random
    random.seed(seed)

    tickers = SPDR_SECTORS
    base_date = "2026-01-01"
    # Common market factor (drives ~60% of variance across sectors)
    market = [0.0]
    for _ in range(n_days):
        market.append(market[-1] + random.gauss(0.0005, 0.012))

    # Generate per-ticker series with shared market + idiosyncratic noise
    out: dict[str, list[dict]] = {}
    for ticker in tickers:
        beta = random.uniform(0.75, 1.25)
        idio_vol = random.uniform(0.005, 0.012)
        start_price = random.uniform(60, 160)
        series = [start_price]
        for i in range(1, n_days + 1):
            mkt_ret = market[i] - market[i - 1]
            idio_ret = random.gauss(0.0, idio_vol)
            ret = beta * mkt_ret + idio_ret
            series.append(series[-1] * math.exp(ret))

        rows = []
        for i, close in enumerate(series):
            yr, mo, day = 2026, 1, 1
            # Approximate trading-day date generation (good enough for fixture)
            jd = i + 1
            mo = ((jd - 1) // 30) % 12 + 1
            day = ((jd - 1) % 30) + 1
            rows.append({"date": f"2026-{mo:02d}-{day:02d}", "close": round(close, 2)})
        out[ticker] = rows
    return out


# ============================================================================
# CLI
# ============================================================================

def _format_matrix(cm: CorrelationMatrix) -> str:
    lines = []
    if not cm.tickers:
        return "Empty matrix (no data)"
    # Header
    lines.append(
        f"Correlation matrix ({len(cm.tickers)}×{len(cm.tickers)}, "
        f"{cm.n_observations} obs, window={cm.window_days})"
    )
    lines.append("")
    header = "        " + "  ".join(f"{t:>5}" for t in cm.tickers)
    lines.append(header)
    for t1 in cm.tickers:
        row = f"{t1:>6}  " + "  ".join(
            f"{cm.get(t1, t2):>5.2f}" for t2 in cm.tickers
        )
        lines.append(row)
    return "\n".join(lines)


def _main_cli():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--test-fixture", action="store_true",
                    help="Run on synthetic 11×11 SPDR-sector fixture")
    ap.add_argument("--prices", type=str,
                    help="Path to price-history JSON")
    ap.add_argument("--window", type=int, default=60,
                    help="Rolling window in trading days (default 60)")
    ap.add_argument("--json", action="store_true",
                    help="Output JSON instead of formatted matrix")
    args = ap.parse_args()

    if args.test_fixture:
        prices = _synthesize_fixture()
        cm = build_correlation_matrix(prices, window=args.window)
        print(_format_matrix(cm))
        print()
        print(f"Matrix shape: {len(cm.tickers)}×{len(cm.tickers)}")
        print(f"Observations: {cm.n_observations}")
        if cm.tickers:
            xlk_mean = cm.mean_corr_to_others("XLK")
            print(f"XLK mean ρ to other sectors: {xlk_mean:.3f}")
        return 0

    if args.prices:
        if not os.path.exists(args.prices):
            print(f"ERROR: {args.prices} not found", file=sys.stderr)
            return 1
        with open(args.prices) as f:
            prices = json.load(f)
        cm = build_correlation_matrix(prices, window=args.window)
        if args.json:
            print(json.dumps({
                "tickers": cm.tickers,
                "matrix": cm.matrix,
                "window_days": cm.window_days,
                "n_observations": cm.n_observations,
            }, indent=2))
        else:
            print(_format_matrix(cm))
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(_main_cli())
