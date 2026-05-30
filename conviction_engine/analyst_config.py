"""Conviction Engine — Layer 3 Analyst: CONFIG (A1).

The brain's tunable surface, in one place. The reads (A2 mechanical, A3 judgment)
import their thresholds from here so tuning never means hunting through logic.

Contents:
  - ROTATION_BANDS         re-exported from uw_price (SINGLE SOURCE OF TRUTH — the
                           plug emits the mechanical label with these same bands;
                           the Analyst ⑤ read reuses them, no divergent copy)
  - MACRO_ALERTS           the P-MACRO-CONTEXT alert thresholds (A2 ⑥ fires them)
  - STALENESS_BUDGET_DAYS  freshness budget per source CADENCE — the payoff of the
                           5/30 cadence work: a `static` source (frozen Meridian)
                           has budget None, so it reads "baseline (date)" instead
                           of false-alarming "stale" every day
  - name_source_map()      {ticker: backing source} parsed from theses.json
  - theses_by_ticker()     {ticker: full thesis} for the ④ type/why/break read

REFINEMENT BACKLOG (tune at the 6/28 retrospective, v1 = sensible defaults):
  rotation bands · macro-alert levels · staleness budgets · the name→source map
  grows as theses.json grows. All values here are starting points, not final.
"""
from __future__ import annotations

from uw_price import ROTATION_BANDS  # noqa: F401 — re-export (single source of truth)


# --------------------------------------------------------------------------- #
# Macro-alert thresholds (P-MACRO-CONTEXT). A2 ⑥ evaluates a macro card against
# these; `kind` tells it how. Heterogeneous by design (levels / changes / cross).
# --------------------------------------------------------------------------- #
MACRO_ALERTS = {
    "10y_above":       {"subject": "10Y",      "kind": "level_above",
                        "threshold": 4.75, "note": "Newton resistance"},
    "2s10s_flip":      {"subject": "2s10s",    "kind": "sign_cross",
                        "level": 0.0, "note": "curve inversion/disinversion"},
    "move_above":      {"subject": "MOVE",     "kind": "level_above",
                        "threshold": 120, "note": "bond-vol stress"},
    "dxy_5d_move":     {"subject": "DXY",      "kind": "abs_change_above",
                        "threshold": 2.0, "unit": "pt_5d", "note": "dollar surge/drop"},
    "vix_above":       {"subject": "VIX",      "kind": "level_above",
                        "threshold": 25, "note": "equity-vol stress"},
    "wti_5d_move_pct": {"subject": "WTI",      "kind": "abs_change_pct_above",
                        "threshold": 5.0, "note": "oil shock"},
    "real10y_5d_bp":   {"subject": "Real 10Y", "kind": "abs_change_bp_above",
                        "threshold": 25, "note": "real-rate shock"},
}


# --------------------------------------------------------------------------- #
# Staleness budgets by source cadence (days). None = never stale (a frozen
# baseline). Maps to sources.DEFAULT_CADENCE: daily / on_refresh / monthly / static.
# --------------------------------------------------------------------------- #
STALENESS_BUDGET_DAYS: dict[str, int | None] = {
    "daily":      2,     # rotation / macro / daily notes -> stale after >2d
    "on_refresh": 7,     # portfolio -> flag >7d (matches #PORTFOLIO-READ-LEAD)
    "monthly":    35,    # the FS bible deck -> stale after >35d
    "static":     None,  # frozen baseline (Meridian) -> NEVER "stale": "baseline (date)"
}


def staleness_budget_for(cadence: str) -> int | None:
    """Budget in days for a cadence. None = no staleness alarm (a baseline).
    Unknown cadence -> the conservative daily budget."""
    return STALENESS_BUDGET_DAYS.get(cadence, STALENESS_BUDGET_DAYS["daily"])


def is_stale(age_days: float, cadence: str) -> bool:
    """True iff a source of `cadence` is past its freshness budget at `age_days`.
    A `static` source is NEVER stale (it's a frozen base, by design)."""
    budget = staleness_budget_for(cadence)
    if budget is None:
        return False
    return age_days > budget


# --------------------------------------------------------------------------- #
# name -> source map, parsed from theses.json (list of
# {ticker, tier, lane, source, factor_tags, ...}).
# --------------------------------------------------------------------------- #
def name_source_map(theses) -> dict:
    """{ticker: backing source} — which source's calls back each held name
    (e.g. SMH/Granny→Lee, LEU/MP/UUUU→Meridian, BMNR/VOLT→operator). The Analyst
    matches held tickers to that source's calls. Entries without a ticker are
    skipped."""
    out: dict = {}
    for t in theses or []:
        ticker = t.get("ticker")
        if not ticker:
            continue
        out[ticker] = t.get("source")
    return out


def theses_by_ticker(theses) -> dict:
    """{ticker: full thesis dict} — for the ④ type/lock/why/break read to look up
    tier / lane / factor_tags per name."""
    return {t["ticker"]: t for t in (theses or []) if t.get("ticker")}
