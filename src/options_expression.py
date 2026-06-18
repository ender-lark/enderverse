#!/usr/bin/env python3
"""
options_expression.py — Phase 1 of the Options Opportunity Surfacing mission.

Turn a conviction we ALREADY hold (watchlist / lean-in / Fundstrat / theses) into
ONE concrete, DEFINED-RISK options idea — structure + strike + expiry + estimated
premium + max-loss + size — written in PLAIN LANGUAGE, with the down-day IV-tax
"brake" front and center.

Scope + doctrine: docs/codex_tasks/options_opportunity_surfacing_scope_2026_06_18.md
Queue item: `options-opportunity-surfacing` (src/system_improvement_queue.json).

DESIGN PRINCIPLES (operator-set)
--------------------------------
1. LEAD WITH THE MOVE. The first thing the card says is the trade + size + when —
   never a score or an analysis dump. A score must never masquerade as a recommendation.
2. DEFINED RISK ONLY. Long calls/puts or debit spreads. Max loss is known and shown
   (in $ AND % of book) at entry. Never naked / undefined risk. Never auto-execute.
3. CONVICTION-GATED WEAKNESS. "Down day = buy" ONLY when the thesis is intact. A down
   move that coincides with a thesis BREAK is NOT a buy — it routes to a thesis check
   (honors `sell = thesis break, not tape`).
4. THE IV-TAX BRAKE. A dip usually inflates the option's premium (price down -> IV up).
   So when IV is rich (especially rich BECAUSE the name fell) we do NOT yell "buy the
   call" — we route to a debit spread (sells some of the rich IV) or "wait for IV to
   settle". This turns "buy weakness" from a gas pedal into a guardrail.
5. WIDE NET, THEN FILTER — NO BRIGHT LINES. Every candidate gets a graded disposition
   (ACT / WAIT / WATCH / SKIP) with a reason, never a silent hard cutoff. WATCH/SKIP
   rows carry a `filter_reason` so the misses can be logged and the dials tuned later
   from real missed opportunities. Cast wide; rank + brake handle precision.
6. EVERYTHING ADJUSTABLE. Every threshold is a NAMED dial in DEFAULTS, overridable via
   the `cfg` argument (and, later, an `options_tunables.json` override) — change a value,
   not the code.
7. PLAIN LANGUAGE. Every term used on the card is defined in `glossary` in one plain
   sentence. Risk is loud. Honesty: we never say "most options expire worthless" (false);
   we say "a 100% loss of the premium is a realistic outcome — sized for it."

PURITY: this is a pure core. No network, no MCP, no src import at module load. It takes a
normalized `subject` dict (a live adapter — Claude via the UW MCP — assembles it from the
options chain + IV + price) and returns the idea dict. Fully unit-testable with canned data.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any, Optional

SCHEMA_VERSION = "1.0"

# ════════════════════════════════════════════════════════════════════════════
# TUNABLE DIALS  (every threshold NAMED — override via cfg; no inline magic numbers)
# Starting points; calibrate from the shadow log of WATCH/SKIP near-misses over time.
# ════════════════════════════════════════════════════════════════════════════
DEFAULTS: dict[str, Any] = {
    # --- liquidity gate (research: illiquid chains silently destroy edge) ---
    "min_open_interest": 100,          # contracts; ideal is thousands
    "spread_pct_soft": 0.10,           # round-trip spread <=10% of mid = clean
    "spread_pct_hard": 0.25,           # >25% of mid = too wide to trade (SKIP)
    # --- IV environment bands (soft; these are reads, not cutoffs) ---
    "iv_rank_cheap_max": 30.0,         # IV rank <= this = premium relatively cheap
    "iv_rank_rich_min": 50.0,          # IV rank >= this = premium rich -> prefer spread/wait
    # --- down-day weakness: WIDE net, graded, NOT a hard trigger ---
    "weakness_notice_return": -0.015,  # start *noticing* weakness here (wide on purpose)
    "weakness_strong_return": -0.05,   # a clearly large down day (for ranking, not a gate)
    # --- structure / expiry / strike selection ---
    "min_dte": 30,                     # avoid very short-dated long premium (theta/gamma brutal)
    "target_delta_single": 0.58,       # slightly ITM long call/put (leverage vs decay balance)
    "target_delta_leaps": 0.72,        # deeper ITM "stock replacement" for long horizons
    "leaps_horizon_days": 270,         # thesis horizon >= this -> prefer LEAPS
    "spread_long_delta": 0.58,         # debit-spread long leg
    "spread_short_delta": 0.30,        # debit-spread short leg (sells rich IV)
    # --- expected move / edge ---
    "expected_move_straddle_factor": 0.85,  # EM ~= 0.85 x ATM straddle (tastytrade heuristic)
    # --- sizing (operator-locked 2026-06-18: ~2% / ~10%) ---
    "per_trade_cap_pct": 0.02,         # max premium-at-risk per trade, % of total portfolio
    "aggregate_cap_pct": 0.10,         # max total open long-premium, % of total portfolio
    # --- earnings / IV-crush ---
    "earnings_block": True,            # block long premium into a known earnings event by default
}

# Plain-English, one-sentence definitions. We only attach the terms a given card uses.
GLOSSARY: dict[str, str] = {
    "premium": "What you pay for the option. For a long option this is also the most you can lose.",
    "max loss": "The worst case in real dollars (and % of your portfolio) if it goes to zero. For these, plan on it as a real outcome.",
    "defined risk": "The loss is capped and known up front — you can't lose more than the premium you put in.",
    "IV rank": "How expensive options are right now versus this name's own past year — 0 = cheapest, 100 = most expensive.",
    "IV tax": "On a down day the option usually gets MORE expensive (fear rises), so the dip can cost you on the option even though the stock is cheaper.",
    "delta": "Roughly how stock-like the option is, and a rough chance it finishes in-the-money. ~0.70 acts a lot like the stock; ~0.30 is cheaper but more of a long shot.",
    "expected move": "How far the options market is pricing the stock to move by expiry. Your idea needs more than this to pay off.",
    "break-even": "Where the stock has to be at expiry for you to make money back on the option.",
    "debit spread": "Buy one option and sell a further-out one against it. Costs less, caps both your risk and your upside, and sells off some of the expensive IV.",
    "LEAPS": "A long-dated option (many months to a couple years out) — used like a cheaper stand-in for owning the shares.",
    "DTE": "Days until the option expires.",
}


# ─────────────────────────────── small helpers ───────────────────────────────
def _f(x) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def _first(d, *keys):
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _cfg(cfg: Optional[dict], key: str):
    if cfg and key in cfg and cfg[key] is not None:
        return cfg[key]
    return DEFAULTS[key]


def _round_money(x: Optional[float]) -> Optional[float]:
    return None if x is None else round(x, 2)


def _strike_label(s) -> str:
    f = _f(s)
    if f is None:
        return str(s)
    return str(int(f)) if f == int(f) else f"{f:g}"


# ─────────────────────────── chain reading (pure) ────────────────────────────
def _mid(c: dict) -> Optional[float]:
    bid, ask = _f(c.get("bid")), _f(c.get("ask"))
    if bid is not None and ask is not None and ask >= bid >= 0:
        return (bid + ask) / 2.0
    return _f(_first(c, "mid", "mark", "last", "price"))


def _spread_pct(c: dict) -> Optional[float]:
    bid, ask = _f(c.get("bid")), _f(c.get("ask"))
    m = _mid(c)
    if bid is None or ask is None or not m:
        return None
    return (ask - bid) / m if m else None


def _is_liquid(c: dict, cfg) -> bool:
    oi = _f(_first(c, "oi", "open_interest")) or 0.0
    if oi < _cfg(cfg, "min_open_interest"):
        return False
    sp = _spread_pct(c)
    if sp is not None and sp > _cfg(cfg, "spread_pct_hard"):
        return False
    return True


def _contract_type(c: dict) -> str:
    t = str(_first(c, "type", "option_type", "put_call") or "").lower()
    return "put" if t.startswith("p") else "call"


def _liquid_contracts(chain, side: str, cfg) -> list[dict]:
    out = []
    for c in chain or []:
        if not isinstance(c, dict):
            continue
        if _contract_type(c) != side:
            continue
        if _is_liquid(c, cfg):
            out.append(c)
    return out


def _pick_expiry_dte(contracts, *, thesis_horizon_days, earnings_dte, cfg) -> Optional[int]:
    """Pick the nearest DTE that (a) clears min_dte, (b) reaches the thesis horizon,
    and (c) sits past a known earnings event. Wide-net: if nothing clears the horizon
    we fall back to the longest available rather than dropping the name."""
    dtes = sorted({int(d) for d in (_f(c.get("dte")) for c in contracts) if d is not None})
    if not dtes:
        return None
    min_dte = _cfg(cfg, "min_dte")
    need = max(min_dte, thesis_horizon_days or 0)
    if earnings_dte is not None:
        need = max(need, int(earnings_dte) + 1)
    for d in dtes:
        if d >= need:
            return d
    return dtes[-1]  # fall back to the longest we have (flagged downstream)


def _pick_by_delta(contracts, dte, target_delta) -> Optional[dict]:
    pool = [c for c in contracts if _f(c.get("dte")) is not None and int(c["dte"]) == int(dte)]
    best, best_gap = None, None
    for c in pool:
        d = _f(c.get("delta"))
        if d is None:
            continue
        gap = abs(abs(d) - target_delta)
        if best_gap is None or gap < best_gap:
            best, best_gap = c, gap
    return best


# ──────────────────────────── reads (pure) ───────────────────────────────────
def classify_iv(iv_rank: Optional[float], cfg) -> str:
    if iv_rank is None:
        return "unknown"
    if iv_rank <= _cfg(cfg, "iv_rank_cheap_max"):
        return "cheap"
    if iv_rank >= _cfg(cfg, "iv_rank_rich_min"):
        return "rich"
    return "normal"


def expected_move_pct(atm_iv: Optional[float], dte: Optional[int]) -> Optional[float]:
    """Expected move to expiry as a fraction of spot: atm_iv * sqrt(dte/365)."""
    if atm_iv is None or dte is None or dte <= 0:
        return None
    return atm_iv * math.sqrt(dte / 365.0)


def iv_tax_engaged(one_day_return: Optional[float], iv_env: str, cfg) -> bool:
    """The brake: the name is weak AND options are rich -> the dip is taxing the premium."""
    if one_day_return is None:
        return False
    return one_day_return <= _cfg(cfg, "weakness_notice_return") and iv_env == "rich"


# ─────────────────────────── sizing (pure) ───────────────────────────────────
def size_position(premium_per_unit, *, portfolio_value, open_premium_at_risk, cfg) -> dict:
    """Size by PREMIUM-AT-RISK (max loss = premium). Honors per-trade and aggregate caps.
    premium_per_unit is the per-contract debit in DOLLARS (mid * 100, or net debit * 100)."""
    out: dict[str, Any] = {"contracts": None, "max_loss_dollars": None, "max_loss_pct_book": None,
                           "size_note": None}
    if not premium_per_unit or premium_per_unit <= 0:
        out["size_note"] = "No tradeable price — size unknown."
        return out
    if not portfolio_value or portfolio_value <= 0:
        out["max_loss_dollars"] = _round_money(premium_per_unit)
        out["size_note"] = "Tell me your portfolio value and I'll size it; this is the cost of ONE contract."
        return out
    per_trade_budget = portfolio_value * _cfg(cfg, "per_trade_cap_pct")
    remaining_aggregate = portfolio_value * _cfg(cfg, "aggregate_cap_pct") - (open_premium_at_risk or 0.0)
    budget = max(0.0, min(per_trade_budget, remaining_aggregate))
    contracts = int(budget // premium_per_unit)
    if contracts < 1:
        out["contracts"] = 0
        if remaining_aggregate < per_trade_budget:
            out["size_note"] = ("Your options budget is nearly used up — at the ~"
                                f"{_cfg(cfg, 'aggregate_cap_pct') * 100:.0f}% total cap there isn't room "
                                "for a full position right now.")
        else:
            out["size_note"] = ("One contract costs more than your ~"
                                f"{_cfg(cfg, 'per_trade_cap_pct') * 100:.0f}% per-trade cap allows — "
                                "consider a cheaper (further-out-of-the-money or spread) structure.")
        return out
    max_loss = contracts * premium_per_unit
    out["contracts"] = contracts
    out["max_loss_dollars"] = _round_money(max_loss)
    out["max_loss_pct_book"] = round(100.0 * max_loss / portfolio_value, 2)
    return out


# ─────────────────────── structure construction (pure) ───────────────────────
def _build_single_leg(contracts, *, side, dte, target_delta, spot):
    c = _pick_by_delta(contracts, dte, target_delta)
    if not c:
        return None
    mid = _mid(c)
    if not mid:
        return None
    strike = _f(c.get("strike"))
    legs = [{"action": "buy", "type": side, "strike": strike, "dte": int(dte),
             "expiry": c.get("expiry"), "delta": _f(c.get("delta")), "mid": _round_money(mid)}]
    # break-even at expiry: call -> strike + premium; put -> strike - premium
    be = (strike + mid) if side == "call" else (strike - mid)
    be_pct = ((be - spot) / spot) if (spot and strike is not None) else None
    return {"structure": "long_call" if side == "call" else "long_put",
            "legs": legs, "premium_per_unit": mid * 100.0,
            "break_even": _round_money(be), "break_even_pct": be_pct}


def _build_debit_spread(contracts, *, side, dte, long_delta, short_delta, spot):
    lo = _pick_by_delta(contracts, dte, long_delta)
    sh = _pick_by_delta(contracts, dte, short_delta)
    if not lo or not sh:
        return None
    lo_mid, sh_mid = _mid(lo), _mid(sh)
    lo_k, sh_k = _f(lo.get("strike")), _f(sh.get("strike"))
    if not lo_mid or not sh_mid or lo_k is None or sh_k is None or lo_k == sh_k:
        return None
    net_debit = lo_mid - sh_mid
    if net_debit <= 0:
        return None
    structure = "debit_call_spread" if side == "call" else "debit_put_spread"
    legs = [
        {"action": "buy", "type": side, "strike": lo_k, "dte": int(dte),
         "expiry": lo.get("expiry"), "delta": _f(lo.get("delta")), "mid": _round_money(lo_mid)},
        {"action": "sell", "type": side, "strike": sh_k, "dte": int(dte),
         "expiry": sh.get("expiry"), "delta": _f(sh.get("delta")), "mid": _round_money(sh_mid)},
    ]
    width = abs(sh_k - lo_k)
    be = (lo_k + net_debit) if side == "call" else (lo_k - net_debit)
    be_pct = ((be - spot) / spot) if spot else None
    return {"structure": structure, "legs": legs, "premium_per_unit": net_debit * 100.0,
            "break_even": _round_money(be), "break_even_pct": be_pct,
            "max_gain_per_unit": _round_money((width - net_debit) * 100.0)}


# ════════════════════════════════════════════════════════════════════════════
# THE PURE CORE
# ════════════════════════════════════════════════════════════════════════════
def build_expression(subject: dict, *, cfg: Optional[dict] = None) -> dict:
    """A normalized `subject` -> one defined-risk options idea dict (see module docstring
    for the subject shape). Pure + deterministic. Never raises on a thin/odd subject — it
    degrades to a WATCH/SKIP row with a plain `filter_reason` (wide-net-then-filter)."""
    tk = str(_first(subject, "ticker", "symbol") or "").upper()
    as_of = subject.get("as_of")
    base: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "ticker": tk, "as_of": as_of,
        "disposition": "SKIP", "move": None, "when": None, "timing": None, "tripwire_note": None,
        "structure": None, "legs": None,
        "iv_environment": "unknown", "iv_tax_brake": False, "brake_reason": None,
        "why": None, "the_catch": None, "filter_reason": None, "glossary": {},
        "honesty": "A 100% loss of the premium is a realistic outcome — this is sized for that.",
    }

    if not tk:
        base["filter_reason"] = "No ticker on the subject."
        return base

    # --- conviction gate: weakness is only a buy if the thesis is intact ---
    if subject.get("thesis_break") is True:
        base["disposition"] = "SKIP"
        base["filter_reason"] = ("Price is down but this looks like a THESIS change, not just weak tape — "
                                 "that's a reason to re-check the thesis, not to buy the dip.")
        base["why"] = "We never buy weakness into a broken thesis (sell = thesis break, not tape)."
        return base
    if not subject.get("conviction_intact", True):
        base["disposition"] = "SKIP"
        base["filter_reason"] = "We don't hold an intact conviction on this name, so there's nothing to express."
        return base

    side = "put" if str(subject.get("direction") or "bullish").lower().startswith("bear") else "call"
    spot = _f(subject.get("spot"))
    iv_rank = _f(subject.get("iv_rank"))
    atm_iv = _f(subject.get("atm_iv"))
    one_day_return = _f(subject.get("one_day_return"))
    horizon = subject.get("thesis_horizon_days")
    horizon = int(horizon) if horizon is not None else None
    iv_env = classify_iv(iv_rank, cfg)
    base["iv_environment"] = iv_env

    # --- earnings / IV-crush awareness: earnings_dte STEERS expiry selection (try to land past
    #     the event); the crush flag itself is only set later, once we know the chosen expiry
    #     actually SPANS the event (earnings on/before expiry). Earnings after expiry = no crush. ---
    earnings_dte = _earnings_dte(subject)

    # --- liquidity gate (the hard disqualifier, but stated as a reason, not silent) ---
    liquid = _liquid_contracts(subject.get("chain"), side, cfg)
    if not liquid:
        base["disposition"] = "SKIP"
        base["filter_reason"] = ("The options on this name are too illiquid right now (thin open interest / "
                                 "wide bid-ask) — the spread would eat the edge. Better expressed in shares.")
        base["the_catch"] = "Illiquid options quietly cost you on entry and exit."
        base["glossary"] = {"defined risk": GLOSSARY["defined risk"]}
        return base

    # --- the IV-tax brake: weak + rich IV -> route to a spread or wait ---
    brake = iv_tax_engaged(one_day_return, iv_env, cfg)
    base["iv_tax_brake"] = brake
    use_spread = (iv_env == "rich") or brake

    # --- pick expiry ---
    dte = _pick_expiry_dte(liquid, thesis_horizon_days=horizon, earnings_dte=earnings_dte, cfg=cfg)
    if dte is None:
        base["disposition"] = "WATCH"
        base["filter_reason"] = "No usable expiry in the chain I was given — re-pull the option chain."
        return base
    # crush risk only if the chosen expiry actually SPANS earnings (earnings on/before expiry)
    earnings_before = earnings_dte is not None and earnings_dte <= dte

    # --- build the structure (decision tree) ---
    long_horizon = horizon is not None and horizon >= _cfg(cfg, "leaps_horizon_days")
    built = None
    if use_spread:
        built = _build_debit_spread(liquid, side=side, dte=dte,
                                    long_delta=_cfg(cfg, "spread_long_delta"),
                                    short_delta=_cfg(cfg, "spread_short_delta"), spot=spot)
        structure_kind = "debit spread"
    else:
        target = _cfg(cfg, "target_delta_leaps") if long_horizon else _cfg(cfg, "target_delta_single")
        built = _build_single_leg(liquid, side=side, dte=dte, target_delta=target, spot=spot)
        structure_kind = "LEAPS" if long_horizon else "long option"
    if built is None and not use_spread:
        # fall back to a spread if we couldn't form a clean single leg
        built = _build_debit_spread(liquid, side=side, dte=dte,
                                    long_delta=_cfg(cfg, "spread_long_delta"),
                                    short_delta=_cfg(cfg, "spread_short_delta"), spot=spot)
        structure_kind = "debit spread"
        use_spread = True
    if built is None:
        base["disposition"] = "WATCH"
        base["filter_reason"] = "Couldn't form a clean defined-risk structure from the chain (missing deltas/quotes)."
        return base

    base.update({k: built[k] for k in ("structure", "legs")})
    em_pct = expected_move_pct(atm_iv, dte)
    be_pct = built.get("break_even_pct")
    base["expected_move_pct"] = round(em_pct * 100, 2) if em_pct is not None else None
    base["break_even_pct"] = round(be_pct * 100, 2) if be_pct is not None else None

    # --- sizing ---
    sizing = size_position(built["premium_per_unit"],
                           portfolio_value=_f(subject.get("portfolio_value")),
                           open_premium_at_risk=_f(subject.get("open_premium_at_risk")), cfg=cfg)
    base.update({k: sizing[k] for k in ("contracts", "max_loss_dollars", "max_loss_pct_book", "size_note")})

    # --- disposition (graded; ACT / WAIT / WATCH — never a silent drop) ---
    disposition, timing, filter_reason = _grade(
        side=side, iv_env=iv_env, brake=brake, use_spread=use_spread,
        earnings_before=earnings_before, earnings_dte=earnings_dte,
        em_pct=em_pct, be_pct=be_pct, contracts=sizing.get("contracts"), cfg=cfg)
    base["disposition"] = disposition
    base["timing"] = timing
    base["when"] = timing["label"]
    if filter_reason:
        base["filter_reason"] = filter_reason

    # --- plain-language assembly (LEAD WITH THE MOVE) ---
    base["move"] = _move_sentence(tk, side, built, sizing, structure_kind, disposition)
    base["why"], base["the_catch"], base["brake_reason"] = _why_and_catch(
        tk, side, iv_env, brake, use_spread, earnings_before, earnings_dte,
        em_pct, be_pct, one_day_return, cfg)
    base["glossary"] = _glossary_for(base, built, use_spread, long_horizon)
    # --- minimal loss-chasing tripwire (light-touch, never a block) ---
    if subject.get("recent_options_loss"):
        base["tripwire_note"] = ("Heads up — you've taken a recent options loss. Make sure this is conviction, "
                                 "not making-it-back; the size above already assumes a 100% loss is possible.")
    return base


# ───────────────────────── grading + language (pure) ─────────────────────────
def _earnings_dte(subject) -> Optional[int]:
    ed = subject.get("earnings_dte")
    if ed is not None:
        return int(ed) if _f(ed) is not None else None
    es, aso = subject.get("earnings_date"), subject.get("as_of")
    if es and aso:
        try:
            return (date.fromisoformat(str(es)[:10]) - date.fromisoformat(str(aso)[:10])).days
        except ValueError:
            return None
    return None


def _grade(*, side, iv_env, brake, use_spread, earnings_before, earnings_dte,
           em_pct, be_pct, contracts, cfg):
    """Graded disposition + a FIRST-CLASS timing verdict carrying a NAMED flip-condition
    (the specific thing that turns a WAIT into an ACT — so 'wait' is never open-ended
    passivity). Wide net: liquid, conviction-intact names ACT; brake/earnings route to
    WAIT; thin edge stays WATCH. Nothing is silently dropped."""
    cheap_max = _cfg(cfg, "iv_rank_cheap_max")
    if contracts == 0:
        return ("WATCH",
                {"verdict": "WAIT", "label": "When there's room in the budget",
                 "flip_condition": "your options budget frees up (an existing position closes)"},
                "No budget room for a full position right now.")
    if earnings_before and _cfg(cfg, "earnings_block") and not use_spread:
        return ("WAIT",
                {"verdict": "WAIT", "label": f"After earnings (~{earnings_dte}d), or take the spread now",
                 "flip_condition": f"earnings (~{earnings_dte}d) passes — or act now via a spread if you mean to play the event"},
                "Earnings before expiry — long premium can get crushed even if you're right on direction.")
    if brake:
        return ("WAIT",
                {"verdict": "WAIT", "label": "Give IV ~1–2 days to cool, or take the spread now",
                 "flip_condition": f"IV rank settles back below {cheap_max:g} (the dip-premium cools) — or act now via the spread"},
                "Down day + rich IV: the option is pricey because the stock fell (the IV tax).")
    # thin-edge note: expected move smaller than the break-even move required
    if em_pct is not None and be_pct is not None and em_pct < abs(be_pct):
        return ("WATCH",
                {"verdict": "WAIT", "label": "Only if you expect a bigger move than the market",
                 "flip_condition": "your target move clears the option's break-even (premium cheapens or the expected move widens)"},
                "The market is already pricing a move past your break-even — thin edge here.")
    return "ACT", {"verdict": "ACT_NOW", "label": "Now", "flip_condition": None}, None


def _money(x):
    return "?" if x is None else (f"${x:,.0f}" if abs(x) >= 100 else f"${x:,.2f}")


def _move_sentence(tk, side, built, sizing, structure_kind, disposition):
    legs = built["legs"]
    n = sizing.get("contracts")
    qty = f"{n}x " if n else ""
    verb = "Buy" if disposition in ("ACT",) else ("Set up" if disposition == "WAIT" else "Watch")
    if built["structure"] in ("long_call", "long_put"):
        lg = legs[0]
        body = f"{qty}{tk} {lg.get('expiry') or str(lg['dte']) + 'DTE'} ${_strike_label(lg['strike'])} {side}s (~${lg['mid']:.2f} each)"
    else:
        lo, sh = legs[0], legs[1]
        body = (f"{qty}{tk} {lo.get('expiry') or str(lo['dte']) + 'DTE'} ${_strike_label(lo['strike'])}/"
                f"${_strike_label(sh['strike'])} {side} debit spread (~${built['premium_per_unit'] / 100:.2f} net)")
    tail = ""
    if sizing.get("max_loss_dollars") is not None and sizing.get("max_loss_pct_book") is not None:
        tail = f" — most you can lose: {_money(sizing['max_loss_dollars'])} ({sizing['max_loss_pct_book']:.1f}% of book)"
    elif sizing.get("size_note"):
        tail = f" — {sizing['size_note']}"
    return f"{verb} {body}{tail}."


def _why_and_catch(tk, side, iv_env, brake, use_spread, earnings_before, earnings_dte,
                   em_pct, be_pct, one_day_return, cfg):
    dirn = "upside" if side == "call" else "downside"
    why_bits = [f"You already have conviction on {tk}; this expresses the {dirn} with defined, capped risk."]
    if one_day_return is not None and one_day_return <= _cfg(cfg, "weakness_notice_return"):
        why_bits.append(f"It's down {abs(one_day_return) * 100:.1f}% — a better entry on a name you believe in.")
    if iv_env == "cheap":
        why_bits.append("Options are relatively cheap here (low IV rank), so buying premium is more defensible.")
    catch = None
    brake_reason = None
    if brake:
        brake_reason = ("The drop pushed the option's price UP (the IV tax), so a plain call would mean "
                        "overpaying. A debit spread sells back some of that expensive premium — or wait a "
                        "day or two for it to settle.")
        catch = brake_reason
    elif iv_env == "rich":
        catch = "Options are expensive right now (high IV rank) — the spread keeps you from overpaying for that."
    elif earnings_before:
        catch = f"Earnings land in ~{earnings_dte} days; option prices can drop hard right after, so mind the timing."
    elif em_pct is not None and be_pct is not None and em_pct < abs(be_pct):
        catch = "The market already expects a move near your break-even, so the edge is thin unless you expect more."
    else:
        catch = "Long options lose value as time passes; a 100% loss is on the table, so keep the size small."
    return " ".join(why_bits), catch, brake_reason


def _glossary_for(base, built, use_spread, long_horizon):
    used = ["premium", "max loss", "defined risk"]
    if base.get("iv_environment") in ("cheap", "normal", "rich"):
        used.append("IV rank")
    if base.get("iv_tax_brake"):
        used.append("IV tax")
    if use_spread:
        used.append("debit spread")
    if long_horizon and built["structure"] in ("long_call", "long_put"):
        used.append("LEAPS")
    if base.get("expected_move_pct") is not None:
        used.append("expected move")
    if base.get("break_even_pct") is not None:
        used.append("break-even")
    if any(_f(l.get("delta")) is not None for l in (built.get("legs") or [])):
        used.append("delta")
    return {t: GLOSSARY[t] for t in dict.fromkeys(used) if t in GLOSSARY}


# ───────────────────── run roll-up (anti-passivity, honest-empty) ─────────────
def summarize_run(results, *, cfg: Optional[dict] = None) -> dict:
    """Roll a batch of build_expression() results into an honest, plain-language summary.
    NEVER goes silent: if nothing is ACT-able it says so and names the closest call, so an
    empty day reads as 'we checked and we're clean/starved', never as a broken/inert screen."""
    results = [r for r in (results or []) if isinstance(r, dict)]
    acted = [r for r in results if r.get("disposition") == "ACT"]
    waiting = [r for r in results if r.get("disposition") == "WAIT"]
    near = [r for r in results if r.get("disposition") in ("WAIT", "WATCH") and r.get("structure")]
    checked = len(results)
    if acted:
        headline = (f"{len(acted)} options idea(s) ready to act now"
                    f"{f'; {len(waiting)} waiting on a trigger' if waiting else ''}; {checked} names checked.")
    elif near:
        n0 = near[0]
        reason = n0.get("filter_reason") or n0.get("the_catch") or "waiting on a trigger"
        headline = (f"No options idea clears the bar to act right now ({checked} names checked) — "
                    f"closest is {n0.get('ticker')}: {reason}")
    else:
        headline = (f"{checked} conviction name(s) checked — none have a clean, liquid options setup today. "
                    "Nothing hidden.")
    return {"checked": checked, "act": acted, "waiting": waiting, "near_misses": near,
            "honest_empty": not acted, "headline": headline}


# ─────────────────────────────────── self-test ───────────────────────────────
def _chain(side="call", base=100.0):
    """A small synthetic liquid chain around `base` for two expiries (45 / 300 DTE)."""
    rows = []
    for dte in (45, 300):
        for k in range(int(base * 0.85), int(base * 1.2), 5):
            intrinsic = max(0.0, base - k) if side == "call" else max(0.0, k - base)
            extr = max(0.5, base * 0.05 * math.sqrt(dte / 365.0))
            mid = intrinsic + extr
            # crude delta: deeper ITM -> higher
            delta = 0.5 + (base - k) / (base * 0.6) if side == "call" else -(0.5 + (k - base) / (base * 0.6))
            delta = max(-0.95, min(0.95, delta))
            rows.append({"expiry": f"D{dte}", "dte": dte, "strike": float(k), "type": side,
                         "delta": round(delta, 2), "bid": round(mid - 0.05, 2),
                         "ask": round(mid + 0.05, 2), "oi": 1500, "volume": 400})
    return rows


def _self_test() -> int:
    fails: list[str] = []

    def chk(cond, label):
        if not cond:
            fails.append(label)

    # 1) cheap IV, intact conviction, modest dip -> ACT, long option, sized, plain move
    r = build_expression({
        "ticker": "NVDA", "as_of": "2026-06-18", "spot": 100.0, "direction": "bullish",
        "conviction_intact": True, "iv_rank": 20.0, "atm_iv": 0.45, "one_day_return": -0.02,
        "thesis_horizon_days": 60, "portfolio_value": 100000, "open_premium_at_risk": 0,
        "chain": _chain("call", 100.0)})
    chk(r["disposition"] == "ACT", f"cheap-IV ACT (got {r['disposition']})")
    chk(r["structure"] in ("long_call",), f"cheap-IV long_call (got {r['structure']})")
    chk(r["contracts"] and r["contracts"] >= 1, "cheap-IV sized >=1 contract")
    chk(r["max_loss_pct_book"] is not None and r["max_loss_pct_book"] <= 2.01, "cheap-IV max loss <= ~2% book")
    chk(r["move"] and r["move"].startswith("Buy "), "cheap-IV move leads with Buy")
    chk("premium" in r["glossary"], "glossary attached")

    # 2) down day + RICH IV -> brake engaged -> WAIT + debit spread
    r2 = build_expression({
        "ticker": "AVGO", "as_of": "2026-06-18", "spot": 100.0, "direction": "bullish",
        "conviction_intact": True, "iv_rank": 70.0, "atm_iv": 0.6, "one_day_return": -0.06,
        "thesis_horizon_days": 60, "portfolio_value": 100000,
        "chain": _chain("call", 100.0)})
    chk(r2["iv_tax_brake"] is True, "rich-IV down day -> brake on")
    chk(r2["disposition"] == "WAIT", f"brake -> WAIT (got {r2['disposition']})")
    chk(r2["structure"] == "debit_call_spread", f"brake -> debit spread (got {r2['structure']})")

    # 3) thesis break -> SKIP with a thesis-check reason (never buy the dip)
    r3 = build_expression({"ticker": "XLRE", "as_of": "2026-06-18", "spot": 40.0, "direction": "bullish",
                           "conviction_intact": True, "thesis_break": True, "one_day_return": -0.05,
                           "chain": _chain("call", 40.0)})
    chk(r3["disposition"] == "SKIP" and "THESIS" in (r3["filter_reason"] or "").upper(),
        "thesis break -> SKIP/thesis-check")

    # 4) illiquid chain -> SKIP with a liquidity reason (stated, not silent)
    thin = [dict(c, oi=5) for c in _chain("call", 100.0)]
    r4 = build_expression({"ticker": "ZZZ", "as_of": "2026-06-18", "spot": 100.0, "direction": "bullish",
                           "conviction_intact": True, "iv_rank": 20.0, "chain": thin})
    chk(r4["disposition"] == "SKIP" and "illiquid" in (r4["filter_reason"] or "").lower(),
        "illiquid -> SKIP/liquidity")

    # 5) long horizon + cheap IV -> LEAPS (deep ITM)
    r5 = build_expression({"ticker": "MU", "as_of": "2026-06-18", "spot": 100.0, "direction": "bullish",
                           "conviction_intact": True, "iv_rank": 15.0, "atm_iv": 0.4,
                           "thesis_horizon_days": 300, "portfolio_value": 250000,
                           "chain": _chain("call", 100.0)})
    chk(r5["structure"] == "long_call" and "LEAPS" in r5["glossary"], "long horizon -> LEAPS glossary")

    # 6) no portfolio value -> sized note, not a crash; still leads with the move
    r6 = build_expression({"ticker": "FN", "as_of": "2026-06-18", "spot": 100.0, "direction": "bullish",
                           "conviction_intact": True, "iv_rank": 20.0, "atm_iv": 0.4,
                           "thesis_horizon_days": 60, "chain": _chain("call", 100.0)})
    chk(r6["contracts"] is None and r6["size_note"], "no-portfolio -> size note")
    chk(r6["move"] and "lose" not in r6["move"].split("—")[0], "no-portfolio still has a move")

    # 7) timing is first-class: ACT -> ACT_NOW; brake -> WAIT with a NAMED flip-condition
    chk(r["timing"]["verdict"] == "ACT_NOW" and r["timing"]["flip_condition"] is None, "ACT timing verdict")
    chk(r2["timing"]["verdict"] == "WAIT" and r2["timing"]["flip_condition"]
        and "IV" in r2["timing"]["flip_condition"], "brake timing names an IV flip-condition")

    # 8) loss-chasing tripwire note appears only when flagged
    r7 = build_expression({**{"ticker": "NVDA", "as_of": "2026-06-18", "spot": 100.0, "direction": "bullish",
                              "conviction_intact": True, "iv_rank": 20.0, "atm_iv": 0.45,
                              "thesis_horizon_days": 60, "portfolio_value": 100000,
                              "chain": _chain("call", 100.0)}, "recent_options_loss": True})
    chk(bool(r7["tripwire_note"]), "tripwire note on recent loss")
    chk(r["tripwire_note"] is None, "no tripwire when not flagged")

    # 9) summarize_run is never silent
    summ = summarize_run([r, r2, r3])
    chk(summ["headline"] and summ["act"], "summary surfaces the ACT idea")
    empty = summarize_run([r3, r4])
    chk(empty["honest_empty"] and "Nothing hidden" in empty["headline"], "honest-empty summary speaks up")

    if fails:
        print("options_expression self-test: FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("options_expression self-test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
