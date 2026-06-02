#!/usr/bin/env python3
"""
uw_opportunity_scan.py — Strand 3, Chunk 3: the SCOUT (producer).

The "UW options as a daily opportunity radar" strand splits on the 2.0 line just
like the parabolic cache:

  • SCOUT  (THIS module + its cloud routine) — a daily UW scan that pulls the
    options tape (bullish/bearish call flow, sweeps, OI build, dark-pool
    accumulation; gamma/IV as modifiers) for the conviction universe and writes
    an opportunity-signals CACHE (JSON) to the repo. PURE GATHER: it never
    decides, sizes, tiers, or trades — it only writes the cache the engine reads.
  • CONSUMER (uw_opportunity.py + the engine, Chunks 1-2 — already committed) —
    reads that cache into conviction-trail CARDS → direction events + lean-in
    evidence, gated, never an auto-buy.

This file is the PRODUCER ONLY. The locked output contract is owned by
``uw_opportunity.py`` (the consumer); we import its enums so the producer can
never drift from it (``test_uw_opportunity_scan.py`` round-trips every emitted
cache back through ``uw_opportunity.uw_opportunity_cards``).

ARCHITECTURE (mirrors parabolic_setup_screener: pure core + injected adapters)
------------------------------------------------------------------------------
  scan(universe, as_of, *, adapters) -> cache_dict
      PURE + fully unit-testable with canned data. No network, no credential,
      no src/ import. For each ticker it asks ``adapters`` for NORMALIZED
      observations and turns them into contract signals via the classification
      dials below.

  Adapters (duck-typed: .flow/.oi/.dark_pool/.gamma/.iv, each -> obs|None):
    • BundleAdapters   — reads PRE-NORMALIZED observations from a bundle dict.
                          Token-safe, no network. Used by --from-bundle + tests.
    • UWLiveAdapters   — live UW REST per-ticker via the route-arounds, normalized
                          on the way in (uses gamma_positioning / uw_iv_context,
                          lazily imported from ../src ONLY at live-run time).
                          Standalone-with-token path.

  The cloud routine does NOT use UWLiveAdapters' REST paths — it fetches raw via
  the UW MCP tools, assembles a bundle with ``observation_from_uw(...)``, then runs
  ``--from-bundle --emit`` (deterministic, token-safe scoring). Same shape as the
  parabolic routine (raw MCP pulls -> bundle_entry_from_uw -> --from-bundle).

ROUTE-AROUNDS HONORED (CI known-broken)
---------------------------------------
  call_flow / sweep   -> get_flow_alerts            (per-ticker CURRENT)
  oi_build            -> get_open_interest_changes  (multi-day OI)
  dark_pool_accum     -> get_dark_pool_trades       ($-blocks; prints lag ~3 sessions, depth ~12d)
  gamma (modifier)    -> gamma_positioning.analyze  (reused, pure)
  IV (modifier)       -> uw_iv_context.classify_iv  (reused, pure; IVR + IV-vs-RV)
  NEVER get_option_trades (ignores ticker AND date filters).
  per-ticker HISTORICAL flow -> get_interval_flow --date (not needed for the v1 current-tape scan).
  get_stock_screener ticker filter is COMMA-delimited (pipe -> empty) -> --universe is comma-delimited.

FIELD MAPS — confirmation status:
  • normalize_flow / normalize_oi / normalize_dark_pool (the three REQUIRED signal
    sources) are CONFIRMED against live get_flow_alerts / get_open_interest_changes /
    get_dark_pool_trades pulls (NVDA) on 2026-06-02. The per-function ⚠ notes record the
    real shapes (string premiums + total_ask_side_prem; OCC-encoded side/strike + a
    fractional oi_change; NBBO-mid sign with no VWAP field).
  • ⚠ STILL DRY-RUN: ``UWClient``'s REST endpoint PATHS (the standalone-with-token path;
    the routine uses MCP tools, not these) and the OPTIONAL gamma/IV modifier shapes
    (normalize_gamma's greek rows into gamma_positioning.analyze; normalize_iv's IV
    inputs). These only temper strength and degrade to "no modifier" if the shape is off
    — never a crash, never a bad signal. Confirm them when wiring the modifier pulls.
  All field access is isolated at this producer boundary, so any correction is a
  one-spot change; the pure core and the round-trip test are solid regardless.

EMPTY-DAY HONESTY: a scan with no qualifying signals writes ``"signals": []`` — the
engine reads that as "no flow," never "all clear" (dark-lane discipline). The scout
never omits the file and never fabricates a signal.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ── contract enums: imported from the CONSUMER so the producer can't drift ──
try:
    from uw_opportunity import (  # same dir (conviction_engine/)
        SIGNAL_TYPES,
        DIRECTIONS,
        UW_OPP_DEFAULT_STRENGTH,
    )
except Exception:  # standalone use outside the engine tree — keep in lock-step manually
    SIGNAL_TYPES = frozenset({"call_flow", "sweep", "oi_build", "dark_pool_accum", "gamma"})
    DIRECTIONS = frozenset({"bullish", "bearish"})
    UW_OPP_DEFAULT_STRENGTH = "moderate"

CACHE_SOURCE = "uw_opportunity_scan"
DEFAULT_CACHE_PATH = "uw_opportunity_signals.json"   # live sibling of sample_opportunity_signals.json
DEFAULT_THESES_PATH = "theses.json"                  # the conviction universe (committed)

# ── strength ladder ──
_STRENGTH_ORDER = ["weak", "moderate", "strong"]
DEFAULT_MIN_STRENGTH = "weak"   # v1 emits weak signals too (consistent with single-event engine behavior);
#                                 raise via --min-strength. Refinement-backlog dial (see build reference §4).

# ════════════════════════════════════════════════════════════════════════════
# CLASSIFICATION DIALS  (v1 STARTING POINTS — calibrate from the Source Call Log
# once the scout has fired enough scans, same convention as UW_OPP_STRENGTH_TRUST.
# All thresholds are NAMED here — never inline magic numbers.)
# ════════════════════════════════════════════════════════════════════════════
# call_flow / sweep — dominant aggressive-side premium (USD).
STRENGTH_PREMIUM_STRONG = 2_000_000      # >= this -> strong
STRENGTH_PREMIUM_MODERATE = 500_000      # >= this -> moderate; else weak
# oi_build — |OI change %| on the dominant side.
OI_PCT_STRONG = 30.0
OI_PCT_MODERATE = 10.0
# dark_pool_accum — |notional| above/below VWAP (USD) over the window.
DP_NOTIONAL_STRONG = 10_000_000
DP_NOTIONAL_MODERATE = 3_000_000
DP_WINDOW_SESSIONS = 10                   # default window (prints lag ~3 sessions; depth ~12d)

# Live REST base + endpoints (standalone-with-token path only — see ⚠ above).
UW_API_BASE = "https://api.unusualwhales.com/api"
ENDPOINT_FLOW_ALERTS = "/stock/{ticker}/flow-alerts"
ENDPOINT_OI_CHANGES = "/stock/{ticker}/oi-change"
ENDPOINT_DARK_POOL = "/darkpool/{ticker}"
ENDPOINT_GREEK_STRIKE = "/stock/{ticker}/greek-exposure/strike"
ENDPOINT_IV_RANK = "/stock/{ticker}/volatility/realized"
ENDPOINT_COMPANY_INFO = "/stock/{ticker}/info"


# ────────────────────────────── small helpers ──────────────────────────────
def _arr(x) -> list:
    """Unwrap the common UW envelopes ({data:[...]} / {results:[...]} / {signals:[...]})."""
    if isinstance(x, dict):
        return x.get("data") or x.get("results") or x.get("signals") or []
    return x or []


def _first(d, *keys):
    """First non-None value among ``keys`` in dict ``d`` (alias-tolerant field access)."""
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _f(x) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _truthy(x) -> bool:
    return bool(x) and str(x).lower() not in ("0", "false", "no", "")


# OCC option-symbol parser: the OI-change feed encodes call/put + strike in the
# contract symbol (e.g. NVDA260605C00230000 -> call, 230) with no separate type/strike
# field, so we parse it. ⚠ confirmed against live get_open_interest_changes (NVDA) 2026-06-02.
_OCC_RE = re.compile(r"([CP])(\d{8})$")


def _occ_side_strike(symbol):
    if not isinstance(symbol, str):
        return (None, None)
    m = _OCC_RE.search(symbol.strip())
    if not m:
        return (None, None)
    return ("call" if m.group(1) == "C" else "put", int(m.group(2)) / 1000.0)


def _clean_strike(s):
    f = _f(s)
    if f is None:
        return s
    return int(f) if f == int(f) else f


def _bump(strength: str, notch: int) -> str:
    """Move ``strength`` along [weak, moderate, strong] by ``notch``, clamped."""
    i = _STRENGTH_ORDER.index(strength) if strength in _STRENGTH_ORDER else _STRENGTH_ORDER.index(UW_OPP_DEFAULT_STRENGTH)
    i = max(0, min(len(_STRENGTH_ORDER) - 1, i + notch))
    return _STRENGTH_ORDER[i]


def _meets_min(strength: str, min_strength: str) -> bool:
    return _STRENGTH_ORDER.index(strength) >= _STRENGTH_ORDER.index(min_strength)


def _modifier_notch(gamma_obs: Optional[dict], iv_obs: Optional[dict]) -> int:
    """gamma/IV STRENGTH modifier (v1, conservative): short-gamma/trending confirms
    momentum (+1); long-gamma/pinned tempers (-1); expensive IV tempers a flow read
    (-1). Net clamped to [-1, +1] so a modifier never swings strength more than one
    notch. Starting point — calibrate later."""
    notch = 0
    if gamma_obs:
        regime = gamma_obs.get("regime")
        if regime == "short_gamma":
            notch += 1
        elif regime == "long_gamma":
            notch -= 1
    if iv_obs and iv_obs.get("classification") == "expensive":
        notch -= 1
    return max(-1, min(1, notch))


def _attach_modifier_provenance(detail: dict, gamma_obs: Optional[dict], iv_obs: Optional[dict]) -> None:
    if gamma_obs and gamma_obs.get("regime") in ("long_gamma", "short_gamma"):
        detail["gamma_regime"] = gamma_obs["regime"]
    if iv_obs and iv_obs.get("classification") in ("cheap", "normal", "expensive"):
        detail["iv_classification"] = iv_obs["classification"]


def _fmt_cp(ratio) -> str:
    if ratio is None:
        return ""
    if ratio >= 1:
        return f", {ratio:.0f}:1 c/p"
    return f", c/p {ratio:.2f}"


def _premium_strength(p: float) -> str:
    if p >= STRENGTH_PREMIUM_STRONG:
        return "strong"
    if p >= STRENGTH_PREMIUM_MODERATE:
        return "moderate"
    return "weak"


def _oi_strength(pct: float) -> str:
    if pct >= OI_PCT_STRONG:
        return "strong"
    if pct >= OI_PCT_MODERATE:
        return "moderate"
    return "weak"


def _dp_strength(n: float) -> str:
    if n >= DP_NOTIONAL_STRONG:
        return "strong"
    if n >= DP_NOTIONAL_MODERATE:
        return "moderate"
    return "weak"


def _valid_signal(sig: dict) -> bool:
    return bool(sig.get("ticker")) and sig.get("signal_type") in SIGNAL_TYPES and sig.get("direction") in DIRECTIONS


# ──────────────── observation -> contract-signal builders (pure) ────────────────
def _signal_from_flow(tk: str, obs: dict, gamma_obs, iv_obs) -> Optional[dict]:
    """Normalized flow obs -> a call_flow/sweep signal. direction = dominant
    aggressive side (ask-side calls vs ask-side puts); strength = dominant premium
    band, gamma/IV-modified."""
    bull = _f(_first(obs, "ask_side_call_premium", "call_premium")) or 0.0
    bear = _f(_first(obs, "ask_side_put_premium", "put_premium")) or 0.0
    if bull <= 0 and bear <= 0:
        return None
    direction = "bullish" if bull >= bear else "bearish"
    dominant = max(bull, bear)
    strength = _bump(_premium_strength(dominant), _modifier_notch(gamma_obs, iv_obs))
    is_sweep = _truthy(obs.get("is_sweep"))
    stype = "sweep" if is_sweep else "call_flow"
    ratio = _f(obs.get("call_put_ratio"))
    side_word = "call" if direction == "bullish" else "put"
    verb = "sweeps" if is_sweep else "flow"
    evidence = f"ask-side {side_word} {verb} ${dominant / 1e6:.1f}M" + _fmt_cp(ratio)
    detail: dict = {"premium": dominant, "side": "ask"}
    if ratio is not None:
        detail["call_put_ratio"] = ratio
    _attach_modifier_provenance(detail, gamma_obs, iv_obs)
    sig = {"ticker": tk, "signal_type": stype, "direction": direction,
           "strength": strength, "evidence": evidence, "detail": detail}
    dt = obs.get("data_time")
    if dt:
        sig["as_of"] = dt
    return sig


def _signal_from_oi(tk: str, obs: dict, gamma_obs, iv_obs) -> Optional[dict]:
    """Normalized OI-change obs -> an oi_build signal. direction = building side
    (call -> bullish, put -> bearish); strength = |OI change %| band, modified."""
    pct = _f(obs.get("oi_change_pct"))
    if pct is None:
        return None
    side = (obs.get("side") or "call").lower()
    direction = "bullish" if side.startswith("c") else "bearish"
    strength = _bump(_oi_strength(abs(pct)), _modifier_notch(gamma_obs, iv_obs))
    strikes = obs.get("strikes") or []
    side_word = "call" if direction == "bullish" else "put"
    evidence = f"{side_word} OI {'+' if pct >= 0 else ''}{pct:.0f}%"
    if strikes:
        evidence += " at " + "/".join(str(s) for s in strikes) + " strikes"
    expiry = obs.get("expiry")
    if expiry:
        evidence += f", {expiry} expiry"
    detail: dict = {"oi_change_pct": pct}
    if strikes:
        detail["strikes"] = strikes
    _attach_modifier_provenance(detail, gamma_obs, iv_obs)
    sig = {"ticker": tk, "signal_type": "oi_build", "direction": direction,
           "strength": strength, "evidence": evidence, "detail": detail}
    dt = obs.get("data_time")
    if dt:
        sig["as_of"] = dt
    return sig


def _signal_from_dark_pool(tk: str, obs: dict, gamma_obs, iv_obs) -> Optional[dict]:
    """Normalized dark-pool obs -> a dark_pool_accum signal. direction = sign of
    notional vs VWAP (accumulation above -> bullish, distribution below -> bearish);
    strength = |notional| band, modified."""
    notional = _f(obs.get("notional_signed"))
    if notional is None or notional == 0:
        return None
    direction = "bullish" if notional >= 0 else "bearish"
    strength = _bump(_dp_strength(abs(notional)), _modifier_notch(gamma_obs, iv_obs))
    sessions = int(_f(obs.get("sessions")) or DP_WINDOW_SESSIONS)
    lean = "net buy" if notional >= 0 else "net sell"
    evidence = f"dark-pool blocks ${abs(notional) / 1e6:.0f}M {lean}, {sessions} sessions"
    detail: dict = {"notional": notional, "sessions": sessions}
    _attach_modifier_provenance(detail, gamma_obs, iv_obs)
    sig = {"ticker": tk, "signal_type": "dark_pool_accum", "direction": direction,
           "strength": strength, "evidence": evidence, "detail": detail}
    dt = obs.get("data_time")
    if dt:
        sig["as_of"] = dt
    return sig


_SIGNAL_BUILDERS = (
    ("flow", _signal_from_flow),
    ("oi", _signal_from_oi),
    ("dark_pool", _signal_from_dark_pool),
)


def _safe_obs(adapters, method: str, ticker: str, *, verbose: bool = False) -> Optional[dict]:
    """Call one adapter method tolerantly: a missing method or a raised exception
    logs + degrades to None for that ticker/signal — it NEVER aborts the scan."""
    fn = getattr(adapters, method, None)
    if fn is None:
        return None
    try:
        return fn(ticker)
    except Exception as exc:  # noqa: BLE001 — tolerant by contract
        if verbose:
            print(f"  [skip] {ticker}.{method}: {exc}", file=sys.stderr)
        return None


# ════════════════════════════════════════════════════════════════════════════
# THE PURE CORE
# ════════════════════════════════════════════════════════════════════════════
def scan(universe, as_of, *, adapters, generated_at: Optional[str] = None,
         min_strength: str = DEFAULT_MIN_STRENGTH, verbose: bool = False) -> dict:
    """Pure scan core: a universe + injected adapters -> the locked cache dict.

    NO network, NO credential, NO src/ import — fully testable with canned
    adapters. ``adapters`` is any object exposing ``.flow/.oi/.dark_pool/.gamma/.iv``
    (each ticker -> a normalized observation dict, or None). Output is exactly the
    Chunk-1 contract that ``uw_opportunity.uw_opportunity_cards`` reads.

    Deterministic: signals are emitted in (universe-order, flow->oi->dark_pool)
    order, so the same inputs always produce a byte-identical cache.
    """
    gen = generated_at or datetime.now(timezone.utc).isoformat()
    signals: list[dict] = []
    for raw_tk in (universe or []):
        tk = str(raw_tk).strip().upper()
        if not tk:
            continue
        gamma_obs = _safe_obs(adapters, "gamma", tk, verbose=verbose)
        iv_obs = _safe_obs(adapters, "iv", tk, verbose=verbose)
        for key, builder in _SIGNAL_BUILDERS:
            obs = _safe_obs(adapters, key, tk, verbose=verbose)
            if not obs:
                continue
            try:
                sig = builder(tk, obs, gamma_obs, iv_obs)
            except Exception as exc:  # noqa: BLE001 — a junk obs never aborts the scan
                if verbose:
                    print(f"  [skip] {tk}.{key} build: {exc}", file=sys.stderr)
                continue
            if sig and _valid_signal(sig) and _meets_min(sig["strength"], min_strength):
                signals.append(sig)
    return {"as_of": as_of, "generated_at": gen, "source": CACHE_SOURCE, "signals": signals}


# ════════════════════════════════════════════════════════════════════════════
# RAW-UW -> NORMALIZED-OBSERVATION normalizers (the PRODUCER BOUNDARY)
# ⚠ field names below are CONFIRM-AT-DRY-RUN. They are the ONLY place raw UW field
# shapes are touched; the scoring core stays pure.
# ════════════════════════════════════════════════════════════════════════════
def normalize_flow(raw) -> Optional[dict]:
    """Raw get_flow_alerts -> {call/put premium, ask-side split, c/p ratio, is_sweep}.
    Aggregates aggressive (ask-side) call vs put premium across alert rows.

    ⚠ confirmed against live get_flow_alerts (NVDA) 2026-06-02: the feed is a bare
    array of alert rows; premium fields are STRINGS; the aggressive slice is given
    directly per row as total_ask_side_prem / total_bid_side_prem (there is NO row-level
    'side' field); sweep is the boolean has_sweep and/or alert_rule containing 'Sweep'.
    """
    rows = _arr(raw)
    if not rows:
        return None
    call_all = put_all = call_ask = put_ask = 0.0
    sweep = False
    for r in rows:
        if not isinstance(r, dict):
            continue
        typ = str(_first(r, "type", "option_type", "put_call") or "").lower()
        total = _f(_first(r, "total_premium", "premium", "value")) or 0.0
        ask = _f(_first(r, "total_ask_side_prem", "ask_side_premium", "ask_premium")) or 0.0
        rule = str(_first(r, "alert_rule", "rule_name") or "").lower()
        if _truthy(_first(r, "has_sweep", "is_sweep", "sweep")) or "sweep" in rule:
            sweep = True
        if typ.startswith("c"):
            call_all += total
            call_ask += ask
        elif typ.startswith("p"):
            put_all += total
            put_ask += ask
    if call_all == 0 and put_all == 0:
        return None
    ratio = round(call_all / put_all, 2) if put_all else None
    return {
        "call_premium": call_all,
        "put_premium": put_all,
        "ask_side_call_premium": call_ask or call_all,   # degrade to total if no ask split
        "ask_side_put_premium": put_ask or put_all,
        "call_put_ratio": ratio,
        "is_sweep": sweep,
    }


def normalize_oi(raw) -> Optional[dict]:
    """Raw get_open_interest_changes -> {oi_change_pct, side, strikes}. Picks the
    dominant side by summed absolute OI change; uses the max change-% on that side.
    Returns None if no percentage is available (can't honestly grade strength).

    ⚠ confirmed against live get_open_interest_changes (NVDA) 2026-06-02: rows carry
    NO type/strike field — call/put + strike are parsed from the OCC option_symbol; the
    absolute change is oi_diff_plain; and oi_change is a FRACTION (0.71 == 71%), so it is
    scaled x100 (an explicit oi_change_pct, if ever present, is taken as already-percent).
    """
    rows = _arr(raw)
    if not rows:
        return None
    call_chg = put_chg = 0.0
    call_strikes: list = []
    put_strikes: list = []
    pcts: list = []  # (side, pct)
    for r in rows:
        if not isinstance(r, dict):
            continue
        # side + strike: explicit fields first, else parse the OCC option symbol
        side = str(_first(r, "type", "option_type", "put_call") or "").lower()
        strike = _first(r, "strike", "strike_price")
        if not side.startswith(("c", "p")) or strike is None:
            occ_side, occ_strike = _occ_side_strike(_first(r, "option_symbol", "option_chain", "symbol"))
            if not side.startswith(("c", "p")):
                side = occ_side or ""
            if strike is None:
                strike = occ_strike
        # change %: oi_change_pct is already a percent; UW's oi_change is a fraction -> x100
        pct = _f(_first(r, "oi_change_pct", "pct_change", "oi_pct"))
        if pct is None:
            frac = _f(_first(r, "oi_change", "oi_change_perc"))
            pct = frac * 100.0 if frac is not None else None
        abs_chg = _f(_first(r, "oi_diff_plain", "oi_change_abs", "oi_diff", "change")) or 0.0
        if side.startswith("c"):
            call_chg += abs_chg
            if abs_chg > 0 and strike is not None:
                call_strikes.append(_clean_strike(strike))
            if pct is not None:
                pcts.append(("call", pct))
        elif side.startswith("p"):
            put_chg += abs_chg
            if abs_chg > 0 and strike is not None:
                put_strikes.append(_clean_strike(strike))
            if pct is not None:
                pcts.append(("put", pct))
    if call_chg == 0 and put_chg == 0:
        return None
    side = "call" if call_chg >= put_chg else "put"
    side_pcts = [p for s, p in pcts if s == side]
    if not side_pcts:
        return None
    strikes = (call_strikes if side == "call" else put_strikes)[:3]
    return {"oi_change_pct": max(side_pcts), "side": side, "strikes": strikes}


def normalize_dark_pool(raw, *, window_sessions: int = DP_WINDOW_SESSIONS) -> Optional[dict]:
    """Raw get_dark_pool_trades -> {notional_signed, sessions}. Sums signed block notional
    (buyer-initiated accumulation positive, seller-initiated distribution negative) and
    counts distinct print sessions.

    ⚠ confirmed against live get_dark_pool_trades (NVDA) 2026-06-02: prints are a bare
    array; notional is the STRING premium (fallback size*price); timestamp is executed_at;
    there is NO VWAP/above-VWAP field, so the sign is inferred from price vs the NBBO
    midpoint (price >= mid -> accumulation +, else distribution -). A vwap-relative flag,
    if ever present, is honored first. Sign is a lean, not a VWAP claim — hence the
    'net buy/sell' wording, not 'above VWAP'.
    """
    rows = _arr(raw)
    if not rows:
        return None
    notional = 0.0
    dates: set = set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        n = _f(_first(r, "premium", "notional", "value"))
        if n is None:
            sz = _f(_first(r, "size", "volume", "quantity")) or 0.0
            px = _f(_first(r, "price", "px", "fill_price")) or 0.0
            n = sz * px
        n = abs(n or 0.0)
        sign = 1.0
        rel = _first(r, "above_vwap", "vwap_side")
        if isinstance(rel, bool):
            sign = 1.0 if rel else -1.0
        elif isinstance(rel, str):
            sign = -1.0 if rel.lower() in ("below", "under", "sell") else 1.0
        else:
            price = _f(_first(r, "price", "px", "fill_price"))
            ask = _f(_first(r, "nbbo_ask", "ask"))
            bid = _f(_first(r, "nbbo_bid", "bid"))
            if price is not None and ask is not None and bid is not None:
                sign = 1.0 if price >= (ask + bid) / 2.0 else -1.0
        notional += sign * n
        d = _first(r, "executed_at", "date", "timestamp", "created_at")
        if d:
            dates.add(str(d)[:10])
    if notional == 0:
        return None
    return {"notional_signed": notional, "sessions": (len(dates) or window_sessions)}


def normalize_gamma(raw_rows, spot, ticker, *, analyze=None) -> Optional[dict]:
    """Raw get_greek_exposure_by_strike rows + spot -> {regime, strength, implication}
    via the reused, pure ``gamma_positioning.analyze``. ``analyze`` is injectable
    (tests pass a fake; live resolves it lazily from ../src). Tolerant -> None."""
    if analyze is None or spot is None:
        return None
    rows = _arr(raw_rows)
    if not rows:
        return None
    try:
        res = analyze({"ticker": ticker, "spot": spot, "strikes": rows})
    except Exception:
        return None
    if not isinstance(res, dict):
        return None
    return {"regime": res.get("regime"), "strength": res.get("strength"),
            "implication": res.get("implication")}


def normalize_iv(raw, ticker, *, classify=None) -> Optional[dict]:
    """Raw IV inputs -> {classification, iv_rank} via the reused, pure
    ``uw_iv_context.classify_iv``. ``classify`` is injectable. Tolerant -> None."""
    if classify is None or not raw:
        return None
    iv_rank = _f(_first(raw if isinstance(raw, dict) else {}, "iv_rank", "ivr", "iv_rank_30d"))
    atm = _f(_first(raw if isinstance(raw, dict) else {}, "atm_iv", "atm_iv_current", "iv30"))
    mean30 = _f(_first(raw if isinstance(raw, dict) else {}, "atm_iv_30d_mean", "iv30_mean"))
    if iv_rank is None:
        return None
    try:
        ctx = classify(ticker, iv_rank=iv_rank, atm_iv_current=atm, atm_iv_30d_mean=mean30)
    except Exception:
        return None
    return {"classification": getattr(ctx, "classification", None),
            "iv_rank": getattr(ctx, "iv_rank", None)}


def observation_from_uw(*, flow=None, oi=None, dark_pool=None, greek=None, iv=None,
                        spot=None, ticker=None, gamma_analyze=None, iv_classify=None) -> dict:
    """Assemble ONE ticker's normalized observation from raw UW responses (the shape
    the cloud routine saves per MCP tool). The bundle assembler the routine calls so
    the SCORING step runs token-safe via --from-bundle. ⚠ raw shapes confirm-at-dry-run.
    """
    obs: dict = {}
    f = normalize_flow(flow)
    if f:
        obs["flow"] = f
    o = normalize_oi(oi)
    if o:
        obs["oi"] = o
    d = normalize_dark_pool(dark_pool)
    if d:
        obs["dark_pool"] = d
    g = normalize_gamma(greek, spot, ticker, analyze=gamma_analyze or _lazy_gamma())
    if g:
        obs["gamma"] = g
    v = normalize_iv(iv, ticker, classify=iv_classify or _lazy_iv())
    if v:
        obs["iv"] = v
    return obs


# ─────────────────────────────── adapters ───────────────────────────────────
class BundleAdapters:
    """Token-safe adapters reading PRE-NORMALIZED observations from a bundle.

    bundle["observations"] = {ticker: {flow:{...}, oi:{...}, dark_pool:{...},
                                       gamma:{...}, iv:{...}}}  (each key optional)
    NO network. Used by --from-bundle and the tests.
    """
    def __init__(self, observations: Optional[dict]):
        self._obs = observations or {}

    def _get(self, ticker: str, key: str):
        row = self._obs.get(ticker) or self._obs.get(str(ticker).upper()) or {}
        return row.get(key) if isinstance(row, dict) else None

    def flow(self, t):
        return self._get(t, "flow")

    def oi(self, t):
        return self._get(t, "oi")

    def dark_pool(self, t):
        return self._get(t, "dark_pool")

    def gamma(self, t):
        return self._get(t, "gamma")

    def iv(self, t):
        return self._get(t, "iv")


def _ensure_src_on_path() -> None:
    """Add the repo's src/ to sys.path so the reused pure blocks import at LIVE-run
    time only. Never invoked by the pure core or the tests."""
    here = Path(__file__).resolve().parent
    for cand in (here.parent / "src", here / ".." / "src"):
        try:
            if cand.exists():
                p = str(cand.resolve())
                if p not in sys.path:
                    sys.path.insert(0, p)
        except OSError:
            continue


def _lazy_gamma():
    try:
        _ensure_src_on_path()
        from gamma_positioning import analyze  # type: ignore
        return analyze
    except Exception:
        return None


def _lazy_iv():
    try:
        _ensure_src_on_path()
        from uw_iv_context import classify_iv  # type: ignore
        return classify_iv
    except Exception:
        return None


class UWClient:
    """Minimal UW REST client (standalone-with-token path only — ⚠ paths
    confirm-at-dry-run). The cloud routine uses the UW MCP tools instead."""
    def __init__(self, api_key: str, verbose: bool = False):
        import requests  # lazy: the module imports fine without requests installed
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {api_key}",
                                      "Accept": "application/json"})
        self.verbose = verbose

    def _get(self, path: str, params: Optional[dict] = None):
        url = UW_API_BASE + path
        if self.verbose:
            print(f"  GET {url} params={params}", file=sys.stderr)
        r = self.session.get(url, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def flow_alerts(self, t):
        return self._get(ENDPOINT_FLOW_ALERTS.format(ticker=t))

    def oi_changes(self, t):
        return self._get(ENDPOINT_OI_CHANGES.format(ticker=t))

    def dark_pool(self, t):
        return self._get(ENDPOINT_DARK_POOL.format(ticker=t), params={"limit": 500})

    def greek_strike(self, t):
        return self._get(ENDPOINT_GREEK_STRIKE.format(ticker=t))

    def iv_inputs(self, t):
        return self._get(ENDPOINT_IV_RANK.format(ticker=t))

    def spot(self, t):
        info = self._get(ENDPOINT_COMPANY_INFO.format(ticker=t))
        # UW returns price as a TOP-LEVEL sibling of "data" (per parabolic's confirmed note)
        if isinstance(info, dict):
            return _f(info.get("price")) or _f((info.get("data") or {}).get("price"))
        return None


class UWLiveAdapters:
    """LIVE adapters: UW REST per-ticker via the route-arounds, normalized on the way
    in. Standalone-with-token path; gamma/IV blocks lazily imported from ../src.
    Each method may raise (network); ``scan`` tolerates it per-ticker/per-signal."""
    def __init__(self, client: UWClient, *, gamma_analyze=None, iv_classify=None, verbose: bool = False):
        self.c = client
        self._gamma = gamma_analyze
        self._iv = iv_classify
        self.verbose = verbose

    def flow(self, t):
        return normalize_flow(self.c.flow_alerts(t))

    def oi(self, t):
        return normalize_oi(self.c.oi_changes(t))

    def dark_pool(self, t):
        return normalize_dark_pool(self.c.dark_pool(t))

    def gamma(self, t):
        return normalize_gamma(self.c.greek_strike(t), self.c.spot(t), t,
                               analyze=self._gamma or _lazy_gamma())

    def iv(self, t):
        return normalize_iv(self.c.iv_inputs(t), t, classify=self._iv or _lazy_iv())


# ─────────────────────────── universe loaders ───────────────────────────────
def universe_from_theses(path: str = DEFAULT_THESES_PATH) -> list[str]:
    """The conviction universe (committed theses.json) — the guardrail that flow
    only matters on names you already have conviction on. Dedup, preserve order."""
    with open(path) as fh:
        data = json.load(fh)
    rows = data if isinstance(data, list) else (data.get("theses") or data.get("rows") or [])
    out: list[str] = []
    seen: set = set()
    for r in rows:
        t = (r.get("ticker") if isinstance(r, dict) else r)
        if not t:
            continue
        t = str(t).upper()
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def universe_from_bundle(bundle) -> list[str]:
    if isinstance(bundle, dict):
        u = bundle.get("universe")
        if u:
            return [str(t).upper() for t in u]
        obs = bundle.get("observations") or {}
        return [str(t).upper() for t in obs.keys()]
    return []


# ───────────────────────────────── self-test ────────────────────────────────
def _self_test() -> int:
    fails: list[str] = []

    def check(cond: bool, label: str) -> None:
        if not cond:
            fails.append(label)

    # Canned normalized observations mirroring sample_opportunity_cache's signals.
    observations = {
        "ANET": {"flow": {"ask_side_call_premium": 2_100_000, "put_premium": 700_000,
                          "call_put_ratio": 3.0, "is_sweep": True}},
        "NVDA": {"oi": {"oi_change_pct": 38.0, "side": "call", "strikes": [1300, 1350]}},
        "MU": {"dark_pool": {"notional_signed": 14_000_000, "sessions": 4}},
    }
    cache = scan(["ANET", "NVDA", "MU"], "2026-05-29",
                 adapters=BundleAdapters(observations),
                 generated_at="2026-05-29T10:30:00Z")
    check(cache["source"] == CACHE_SOURCE, "source label")
    check(cache["as_of"] == "2026-05-29", "as_of preserved")
    check(len(cache["signals"]) == 3, "3 signals emitted")
    by = {s["ticker"]: s for s in cache["signals"]}
    check(by.get("ANET", {}).get("signal_type") == "sweep"
          and by["ANET"]["direction"] == "bullish"
          and by["ANET"]["strength"] == "strong", "ANET sweep/bullish/strong")
    check(by.get("NVDA", {}).get("signal_type") == "oi_build"
          and by["NVDA"]["direction"] == "bullish", "NVDA oi_build/bullish")
    check(by.get("MU", {}).get("signal_type") == "dark_pool_accum"
          and by["MU"]["direction"] == "bullish", "MU dark_pool/bullish")

    # Round-trip through the LOCKED consumer.
    try:
        from uw_opportunity import uw_opportunity_cards
        cards = uw_opportunity_cards(cache)
        check(len(cards) == 3, "round-trip 3 cards")
        check({c["subject"] for c in cards} == {"ANET", "NVDA", "MU"}, "round-trip subjects")
        check(all(c["kind"] == "uw_opportunity" for c in cards), "round-trip kind")
        check(all(c["independence_group"] == "uw_flow" for c in cards), "round-trip independence_group")
    except ImportError:
        print("  (uw_opportunity not importable — round-trip check skipped)", file=sys.stderr)

    # Empty day -> [] (never omit/fabricate).
    check(scan(["ANET"], "2026-05-29", adapters=BundleAdapters({}),
               generated_at="x")["signals"] == [], "empty day -> []")

    # Tolerant: a raising adapter degrades to no signal, never aborts.
    class _Boom:
        def flow(self, t):
            raise RuntimeError("boom")

    check(scan(["ANET"], "x", adapters=_Boom(), generated_at="x")["signals"] == [],
          "tolerant skip on adapter error")

    if fails:
        print("uw_opportunity_scan self-test: FAIL", file=sys.stderr)
        for f in fails:
            print("  -", f, file=sys.stderr)
        return 1
    print("uw_opportunity_scan self-test: PASS")
    return 0


# ───────────────────────────────────── CLI ──────────────────────────────────
def main() -> int:
    p = argparse.ArgumentParser(
        description="UW opportunity-signals scout (Strand 3, Chunk 3) — writes the "
                    "opportunity-signals cache the conviction engine reads.")
    p.add_argument("--universe", help="Comma-separated tickers (overrides --theses). COMMA-delimited.")
    p.add_argument("--theses", default=DEFAULT_THESES_PATH,
                   help=f"Universe source JSON (default {DEFAULT_THESES_PATH})")
    p.add_argument("--from-bundle",
                   help="Score a token-safe bundle JSON {as_of, universe, observations} — NO live UW.")
    p.add_argument("--as-of", help="Session date the scan covers (YYYY-MM-DD; default today UTC)")
    p.add_argument("--emit", nargs="?", const=DEFAULT_CACHE_PATH,
                   help=f"Write the cache JSON (default path {DEFAULT_CACHE_PATH})")
    p.add_argument("--min-strength", choices=_STRENGTH_ORDER, default=DEFAULT_MIN_STRENGTH,
                   help="Drop signals below this strength (default weak = emit all)")
    p.add_argument("--json", action="store_true", help="Print the cache JSON to stdout")
    p.add_argument("--verbose", action="store_true", help="Log skipped pulls to stderr")
    p.add_argument("--self-test", action="store_true",
                   help="Run the built-in self-test (round-trips the contract) and exit")
    args = p.parse_args()

    if args.self_test:
        return _self_test()

    as_of = args.as_of or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if args.from_bundle:  # token-safe path (no UW_API_KEY)
        with open(args.from_bundle) as fh:
            bundle = json.load(fh)
        cache = scan(universe_from_bundle(bundle), bundle.get("as_of") or as_of,
                     adapters=BundleAdapters(bundle.get("observations") or {}),
                     min_strength=args.min_strength, verbose=args.verbose)
    else:  # live path (requires token)
        api_key = os.environ.get("UW_API_KEY")
        if not api_key:
            print("ERROR: UW_API_KEY not set (or use --from-bundle for the token-safe path)",
                  file=sys.stderr)
            return 1
        if args.universe:
            universe = [t.strip().upper() for t in args.universe.split(",") if t.strip()]
        else:
            universe = universe_from_theses(args.theses)
        adapters = UWLiveAdapters(UWClient(api_key, verbose=args.verbose), verbose=args.verbose)
        cache = scan(universe, as_of, adapters=adapters,
                     min_strength=args.min_strength, verbose=args.verbose)

    if args.emit:
        with open(args.emit, "w") as fh:
            json.dump(cache, fh, indent=2)
        print(f"Emitted {len(cache['signals'])} signal(s) -> {args.emit}", file=sys.stderr)
    if args.json or not args.emit:
        print(json.dumps(cache, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
