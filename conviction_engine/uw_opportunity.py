#!/usr/bin/env python3
"""
uw_opportunity.py — Strand 3, Chunk 1: the opportunity-signal CONSUMER contract.

The cockpit's "UW options as a daily opportunity radar" (Opportunity-Engine pivot,
strand 3) splits on the 2.0 line exactly like the parabolic cache:

  • SCOUT (cloud routine — built in Chunk 3) — a daily UW scan that pulls bullish
    call flow / sweeps / OI build / dark-pool accumulation / gamma for the watchlist
    and writes an opportunity-signals CACHE (JSON) to the repo. Pure gather; it
    never decides, sizes, tiers, or trades.
  • CONSUMER (this module + the engine) — turns that cache into conviction-trail
    CARDS (SourceItem-shaped) so the conviction reads can treat fresh bullish flow
    as confirmation / timing on names you ALREADY have conviction on.

THIS FILE IS THE CONSUMER'S CONTRACT + ADAPTER ONLY (Chunk 1). It does NOT fetch
from UW (that is the scout) and it does NOT yet move conviction (that is Chunk 2).
The cards it emits carry kind ``uw_opportunity`` and — deliberately — NO ``event``
marker, so ``conviction_direction_read`` and ``conviction_read`` IGNORE them today
(proven by the inert-seam test in test_uw_opportunity.py). Chunk 2 is the single
hook that turns a fresh bullish ``uw_opportunity`` card into an up-event on the
direction trail + a lean-in evidence row — gated, never an auto-buy.

THE CACHE SCHEMA  (what the scout writes / this adapter reads)
-------------------------------------------------------------
  {
    "as_of":        "2026-05-29",                # the session date the scan covers
    "generated_at": "2026-05-29T10:30:00Z",      # when the scout ran
    "source":       "uw_opportunity_scan",       # producer label (free text)
    "signals": [
      {
        "ticker":      "ANET",                   # REQUIRED
        "signal_type": "sweep",                  # REQUIRED ∈ SIGNAL_TYPES
        "direction":   "bullish",                # REQUIRED ∈ {bullish, bearish}
        "strength":    "strong",                 # optional ∈ {strong,moderate,weak}; default "moderate"
        "evidence":    "ask-side call sweeps $2.1M, 3:1 c/p",   # optional one-liner
        "as_of":       "2026-05-29T15:30:00Z",   # optional; the signal's data time; default cache.generated_at
        "detail":      {"premium": 2100000}      # optional structured numbers (free)
      }
    ]
  }

A bare LIST of signal dicts is also accepted (treated as ``signals``). The adapter
is TOLERANT — malformed / unknown rows are skipped, never raised (the scout is
upstream and may emit junk), so a bad scan degrades to "no opportunity cards", it
never poisons the conviction trail.

WHY independence_group = "uw_flow"
----------------------------------
All flow signals on a name share ONE echo-chamber bucket, so the conviction read's
stream-count (and the lean-in "clustered" flag) treat five sweeps on ANET as ONE
independent confirmation, not five — decision-kernel #7: correlated weak signals ≠
independent confirmation. Named endorsements (FS / Meridian) stay their own groups,
so an endorsement + a flow confirmation = TWO streams, which is exactly the point.
"""
from __future__ import annotations

from analyst_config import UW_OPP_STRENGTH_TRUST

# ── contract identity (the card's fixed labels — not dials) ──
UW_OPP_KIND = "uw_opportunity"
UW_OPP_SOURCE = "uw_opportunity"
UW_OPP_INDEPENDENCE_GROUP = "uw_flow"
UW_OPP_DEFAULT_STRENGTH = "moderate"

# ── contract enums (validated at the boundary; the scout must emit one of these) ──
SIGNAL_TYPES = frozenset({"call_flow", "sweep", "oi_build", "dark_pool_accum", "gamma"})
DIRECTIONS = frozenset({"bullish", "bearish"})


def _coerce_signals(cache):
    """Accept a {signals:[...], generated_at} cache dict OR a bare list of signals.
    Returns (signals_list, cache_timestamp_or_None)."""
    if isinstance(cache, dict):
        return (cache.get("signals") or []), (cache.get("generated_at") or cache.get("as_of"))
    if isinstance(cache, list):
        return cache, None
    return [], None


def uw_opportunity_cards(cache) -> list[dict]:
    """Map an opportunity-signals cache → SourceItem-shaped card dicts (kind
    ``uw_opportunity``).

    The returned dicts are the SAME 8-field shape as every other snapshot item, so
    ``assemble_feed`` wraps them through ``_ns`` alongside the Fundstrat / macro /
    position cards. They carry NO ``event`` marker → inert until Chunk 2.

    Tolerant by contract: a row missing a ticker, or with a signal_type / direction
    outside the enums, is skipped (not raised). Returns ``[]`` for an empty / None
    cache.
    """
    signals, cache_ts = _coerce_signals(cache)
    cards: list[dict] = []
    for s in signals:
        if not isinstance(s, dict):
            continue
        ticker = s.get("ticker")
        stype = s.get("signal_type")
        direction = s.get("direction")
        if not ticker or stype not in SIGNAL_TYPES or direction not in DIRECTIONS:
            continue  # contract violation → skip, don't poison the trail
        strength = s.get("strength")
        if strength not in UW_OPP_STRENGTH_TRUST:
            strength = UW_OPP_DEFAULT_STRENGTH
        ts = s.get("as_of") or s.get("timestamp") or cache_ts or ""
        evidence = s.get("evidence") or f"{direction} {stype.replace('_', ' ')}"
        detail = s.get("detail") if isinstance(s.get("detail"), dict) else {}
        cards.append({
            "source": UW_OPP_SOURCE,
            "kind": UW_OPP_KIND,
            "subject": ticker,
            "content": evidence,
            "timestamp": ts,
            "trust_weight": UW_OPP_STRENGTH_TRUST[strength],
            "independence_group": UW_OPP_INDEPENDENCE_GROUP,
            # `data` carries the opportunity semantics. NO "event" key in Chunk 1 —
            # that is the Chunk-2 hook that turns a fresh bullish signal into an
            # up-event on the conviction-direction trail (+ a lean-in evidence row).
            "data": {"signal_type": stype, "direction": direction,
                     "strength": strength, **detail},
        })
    return cards


def sample_opportunity_cache() -> dict:
    """A representative cache — used by the tests and as the in-code contract
    example. Mirrors sample_opportunity_signals.json (the scout's target shape)."""
    return {
        "as_of": "2026-05-29",
        "generated_at": "2026-05-29T10:30:00Z",
        "source": "uw_opportunity_scan",
        "signals": [
            {"ticker": "ANET", "signal_type": "sweep", "direction": "bullish",
             "strength": "strong",
             "evidence": "ask-side call sweeps $2.1M, 3:1 c/p (0-7DTE)",
             "as_of": "2026-05-29T15:30:00Z",
             "detail": {"premium": 2100000, "call_put_ratio": 3.0, "side": "ask"}},
            {"ticker": "NVDA", "signal_type": "oi_build", "direction": "bullish",
             "strength": "moderate",
             "evidence": "call OI +38% at 1300/1350 strikes, Jun expiry",
             "detail": {"oi_change_pct": 38, "strikes": [1300, 1350]}},
            {"ticker": "MU", "signal_type": "dark_pool_accum", "direction": "bullish",
             "strength": "moderate",
             "evidence": "dark-pool blocks $14M above VWAP, 4 sessions",
             "detail": {"notional": 14000000, "sessions": 4}},
        ],
    }
