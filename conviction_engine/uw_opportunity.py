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

THIS FILE IS THE CONSUMER'S CONTRACT + ADAPTER (it does NOT fetch from UW — that is
the scout). The cards it emits carry kind ``uw_opportunity`` and — deliberately — NO
``event`` key; the Chunk-2 hook is LIVE in the READERS (not via an event marker):
``conviction_direction_read`` derives a DIRECTION event straight from ``data.direction``
(gated by the short ``UW_OPP_FRESH_DAYS`` window; ``uw_flow`` independence group), so a
fresh bullish signal moves a name's ``cd`` to ``up`` and surfaces a lean-in evidence
row — gated, never an auto-buy. It moves DIRECTION only: ``conviction_read`` (QUALITY)
still IGNORES it (``uw_opportunity`` is not in ``ENDORSEMENT_KINDS``), so flow can never
manufacture a lean-in or bump conviction — ``lean_in_read`` gates on the conviction
floor, which flow does not raise. (Enforced by ``test_fresh_bullish_flow_is_up_event``,
``test_quality_read_ignores_flow``, ``test_flow_is_not_an_independence_stream``.)

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
            # `data` carries the opportunity semantics. NO "event" key by design —
            # the Chunk-2 hook is LIVE: conviction_direction_read derives a fresh
            # DIRECTION up/down event straight from data.direction (no marker needed).
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


def uw_opportunity_surface(cache, monitor_tickers=None) -> dict:
    """Read-only DISPLAY shaping of the opportunity cache for the cockpit's
    "Bullish flow" WATCH lane (Strand-3 surfacing / B1). Groups signals by ticker
    (``uw_flow`` = one name, one bucket -- 5 sweeps on ANET = one row, not five;
    decision-kernel #7), strongest first, bullish first. Tolerant: malformed rows
    are skipped (never raised). Does NOT move conviction -- that is the gated
    Chunk-2 hook, deliberately separate. Returns ``{}`` for an empty / None cache.
    """
    signals, cache_ts = _coerce_signals(cache)
    monitor = set(monitor_tickers or ())   # 🔒 parked/burned MONITOR sleeves -> caution tag
    groups: dict[str, dict] = {}
    for s in signals:
        if not isinstance(s, dict):
            continue
        ticker = s.get("ticker")
        stype = s.get("signal_type")
        direction = s.get("direction")
        if not ticker or stype not in SIGNAL_TYPES or direction not in DIRECTIONS:
            continue  # contract violation -> skip
        strength = s.get("strength")
        if strength not in UW_OPP_STRENGTH_TRUST:
            strength = UW_OPP_DEFAULT_STRENGTH
        g = groups.setdefault(ticker, {"ticker": ticker, "direction": direction,
                                       "strength": strength, "signal_types": [],
                                       "n": 0, "evidence": [], "parked": ticker in monitor})
        g["n"] += 1
        if stype not in g["signal_types"]:
            g["signal_types"].append(stype)
        if UW_OPP_STRENGTH_TRUST[strength] > UW_OPP_STRENGTH_TRUST.get(g["strength"], 0):
            g["strength"] = strength  # strongest in the bucket leads the header
        ev = s.get("evidence")
        if ev and ev not in g["evidence"] and len(g["evidence"]) < 3:
            g["evidence"].append(ev)
    rows = sorted(groups.values(),
                  key=lambda r: (0 if r["direction"] == "bullish" else 1,
                                 -UW_OPP_STRENGTH_TRUST.get(r["strength"], 0),
                                 -r["n"], r["ticker"]))
    if not rows:
        return {}
    as_of = (cache.get("as_of") if isinstance(cache, dict) else None) or cache_ts or ""
    return {"as_of": as_of, "count": sum(r["n"] for r in rows),
            "tickers": len(rows), "rows": rows}
