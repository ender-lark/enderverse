"""Conviction Engine — the `uw_price` real fetcher (Stage 1, S2).

This is the deterministic logic behind the first real source plug: given close
prices for the sleeve proxies + the benchmarks, compute each proxy's
RELATIVE STRENGTH vs SPY and vs SMH, and attach a mechanical rotation label
(LEADING / IN LINE / LAGGING / TURNING UP / TURNING DOWN).

Boundary (per Build Plan "Sources vs Analyst — RECORD"): a *fixed calculation*
and a *mechanical threshold label* belong to the plug; the *judgment*
(catch-up-vs-broken, net-reads) is the Analyst. So the rel-strength math AND the
threshold label live here; the Analyst's read ⑤ stays the canonical owner of the
*tunable* thresholds + the catch-up interpretation, and reuses `classify_rotation`
(single source of truth — no divergent band definitions).

Pure-logic + injectable: the fetcher takes a `closes_by_ticker` mapping, so it is
fully testable with FAKE close arrays (known input -> known rel%), no live UW
calls. The Collection layer (Stage 2) wires the real UW close-price pull in.

Method (from the 5/29 by-hand rotation read):
    return       = (latest_close - reference_close) / reference_close
    rel strength = proxy_return - benchmark_return     (per lookback)
    abs_3m       = the proxy's own 3-month return
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sources import BaseSource, make_price_source


# Lookbacks in TRADING days (≈21/mo). Tunable; the Collection pull supplies a
# close series long enough to satisfy lookback_3m.
LOOKBACK_1M = 21
LOOKBACK_3M = 63

# The ~9 sleeve proxies the by-hand read covered (Build Plan P2 roster).
DEFAULT_PROXIES = ["SMH", "IGV", "GRNY", "IBIT", "URA", "REMX", "XLF", "GDX", "VOLT"]

# v1 mechanical classification bands (rel strength vs SPY, as fractions).
# REFINEMENT BACKLOG: tune at the 6/28 retrospective once real rotation cases
# accumulate; the Analyst ⑤ may override these per its tunable config.
ROTATION_BANDS = {
    "lead_3m": 0.05,    # rel_3m >= +5% vs benchmark  -> leadership
    "lag_3m": -0.05,    # rel_3m <= -5% vs benchmark  -> lagging
    "turn_1m": 0.03,    # |rel_1m| inflection threshold for TURNING UP/DOWN
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def pct_return(closes: Iterable[float], lookback: int) -> float:
    """Simple return from `lookback` bars ago to the latest close.

    Raises ValueError if there aren't enough closes or the reference is zero —
    so a too-short / broken series fails loudly rather than returning a bogus 0.
    """
    seq = list(closes) if closes is not None else []
    if len(seq) <= lookback:
        raise ValueError(f"need > {lookback} closes, got {len(seq)}")
    latest = seq[-1]
    ref = seq[-1 - lookback]
    if ref == 0:
        raise ValueError("reference close is zero")
    return (latest - ref) / ref


def relative_strength(proxy_closes, bench_closes, lookback: int) -> float:
    """Proxy return minus benchmark return over the same lookback."""
    return pct_return(proxy_closes, lookback) - pct_return(bench_closes, lookback)


def classify_rotation(rel_1m, rel_3m, bands: dict = ROTATION_BANDS) -> str:
    """Mechanical rotation label from rel strength vs the benchmark.

    LEADING / LAGGING are set by the 3M band; TURNING UP / DOWN flag a 1M
    inflection against the 3M trend (e.g. led 3M but rolling over last month =>
    TURNING DOWN; lagged 3M but inflecting up last month => TURNING UP).
    NOTE: this is the mechanical label only — NOT the catch-up-vs-broken read.
    """
    if rel_1m is None or rel_3m is None:
        return "NO DATA"
    lead, lag, turn = bands["lead_3m"], bands["lag_3m"], bands["turn_1m"]
    if rel_3m >= lead:
        return "TURNING DOWN" if rel_1m <= -turn else "LEADING"
    if rel_3m <= lag:
        return "TURNING UP" if rel_1m >= turn else "LAGGING"
    return "IN LINE"


def uw_price_rotation_reader(
    closes_by_ticker: dict,
    proxies: list[str] | None = None,
    benchmark: str = "SPY",
    ai_benchmark: str = "SMH",
    lookback_1m: int = LOOKBACK_1M,
    lookback_3m: int = LOOKBACK_3M,
    as_of: str | None = None,
    bands: dict = ROTATION_BANDS,
) -> list[dict]:
    """Compute one rotation row per proxy from a close-price mapping.

    `closes_by_ticker`: {ticker -> [oldest .. newest] closes}; must include the
    benchmark (and ai_benchmark, for the vs-SMH leg).

    Per-proxy resilience: if a proxy's own series (or the SPY benchmark) is too
    short/broken, that proxy emits an honest "NO DATA" row instead of crashing or
    faking a number. The vs-SMH leg is best-effort: if SMH is missing it goes
    None without sinking the vs-SPY card.
    """
    proxies = list(proxies) if proxies is not None else list(DEFAULT_PROXIES)
    ts = as_of or _utc_now_iso()
    bench = closes_by_ticker.get(benchmark)
    ai_bench = closes_by_ticker.get(ai_benchmark)

    rows: list[dict] = []
    for proxy in proxies:
        pc = closes_by_ticker.get(proxy)
        row = {"proxy": proxy, "timestamp": ts}

        # --- primary: relative strength vs SPY (governs the card) ---
        try:
            rel_1m = relative_strength(pc, bench, lookback_1m)
            rel_3m = relative_strength(pc, bench, lookback_3m)
            abs_3m = pct_return(pc, lookback_3m)
            label = classify_rotation(rel_1m, rel_3m, bands)
        except (ValueError, TypeError) as exc:
            row.update({
                "rel_1m": None, "rel_3m": None, "abs_3m": None,
                "rel_1m_vs_smh": None, "rel_3m_vs_smh": None,
                "label": "NO DATA", "note": str(exc),
            })
            rows.append(row)
            continue

        # --- best-effort: relative strength vs SMH (AI-leadership leg) ---
        if proxy == ai_benchmark:
            rel_1m_vs_smh = rel_3m_vs_smh = 0.0      # a proxy vs itself
        else:
            try:
                rel_1m_vs_smh = relative_strength(pc, ai_bench, lookback_1m)
                rel_3m_vs_smh = relative_strength(pc, ai_bench, lookback_3m)
            except (ValueError, TypeError):
                rel_1m_vs_smh = rel_3m_vs_smh = None

        row.update({
            "rel_1m": rel_1m, "rel_3m": rel_3m, "abs_3m": abs_3m,
            "rel_1m_vs_smh": rel_1m_vs_smh, "rel_3m_vs_smh": rel_3m_vs_smh,
            "label": label,
        })
        rows.append(row)

    return rows


def build_uw_price_source(
    closes_by_ticker: dict, name: str = "uw_price", **reader_kwargs
) -> BaseSource:
    """Wire the real rotation reader into the uniform `uw_price` plug.

    Returns a BaseSource (trust 0.95, group market_data via the dials) whose
    fetch() emits validated kind="rotation" SourceItems. In production the
    Collection layer supplies a live `closes_by_ticker`; in tests, fake closes.
    """
    def reader() -> list[dict]:
        return uw_price_rotation_reader(closes_by_ticker, **reader_kwargs)

    return make_price_source(reader, name=name)
