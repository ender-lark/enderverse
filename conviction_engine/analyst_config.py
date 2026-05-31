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


# --------------------------------------------------------------------------- #
# CONVICTION reads config (A3 judgment — ① ② ③ ⑦). v1 lexicons + dials. The
# discrete grade/arrow is produced deterministically from these (so it's unit-
# testable now AND the golden-master can run); the prose is templated; the
# production routine's Claude refines edge cases (the judgment seam). All values
# are v1 starting points → 6/28 retrospective (same refinement backlog as above).
# --------------------------------------------------------------------------- #

# ② how far back a dated call still counts as a "recent event" that can move the
# arrow. Steady-state (no in-window event) = flat.
CONVICTION_WINDOW_DAYS = 14

# ② when bullish AND bearish events both fire, the arrow stays flat unless one
# side's (trust × recency) weight beats the other by more than this margin — so a
# small Lee-0.70 vs Farrell-0.65 split nets flat, not up.
CONVICTION_DIRECTION_DEADBAND = 0.15

# ① the operator's designated HIGH-CONFIDENCE durable sleeve (memory: under-sizing
# is the failure mode for AI). A named fundstrat endorsement on a name in this
# sleeve, no conflict, not burned → Strong; the same endorsement OUTSIDE it →
# Promising (this is the SMH-Strong vs XLF-Promising split).
HIGH_CONFIDENCE_FACTOR_TAGS = {"ai_complex"}

# ①/② sentiment of a card's own `direction` word (lower-cased substring match).
BULLISH_WORDS = {"top_5", "top5", "buy", "own", "overweight", "ow", "long",
                 "bullish", "breakout", "bottom_in", "add", "upgrade", "favor"}
BEARISH_WORDS = {"bottom_5", "bottom5", "sell", "underweight", "uw", "short",
                 "bearish", "struggling", "avoid", "downgrade", "trim", "cut"}

# ② event markers (set by the prose-extraction step when a call is NEW/CHANGED,
# not a steady-state restatement). Steady-state cards carry no marker → flat.
BULLISH_EVENTS = {"new_pick", "upgrade", "new_top5", "breakout", "beat",
                  "favorable_shift", "bottom_in"}
BEARISH_EVENTS = {"downgrade", "new_bottom5", "miss", "thesis_break",
                  "unfavorable_shift"}


# --------------------------------------------------------------------------- #
# NET-READ ③ + FRESH-SIGNAL ⑦ tunables (A3b). v1 starting points → 6/28.
# --------------------------------------------------------------------------- #

# ③ rotation labels that read as an "endorsed laggard → catch-up, favorable
# entry" (lagging ≠ bearish) rather than a "leading → ride it".
CATCH_UP_ROTATION_LABELS = {"LAGGING", "TURNING UP"}

# ⑦ event markers that mean the ENTRY TRIGGER fired → ⏳ act now (vs an
# endorsement with no confirmed entry → 👁 watch). A re-entry-zone touch and an
# explicit buyable_now also force ⏳ act.
ACT_NOW_EVENTS = {"breakout"}

# ⑦ which event markers are discrete NAME-LEVEL buy triggers that earn a place
# on the Actions strip. A sector/stance shift (favorable_shift) drives DIRECTION
# (cd=up) and the net-read "catch-up" on the holding row, but is NOT an act/watch
# fresh signal — only these are:
FRESH_SIGNAL_EVENTS = {"breakout", "new_pick", "new_top5", "upgrade", "bottom_in"}
