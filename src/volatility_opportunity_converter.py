#!/usr/bin/env python3
"""
volatility_opportunity_converter.py — turn an AI/semis volatility event into ONE
staged, sized, time-stamped command instead of a passive "here's why to wait" wall.

This is the anti-passivity fusion layer. A sharp selloff/rebound regime (e.g. the
2026-06-23 semis −7% day + the 2026-06-24 MU beat) throws off six independent
signals that are usually shown in six different tiles. The operator is left to
fuse them in their head — which is exactly where under-sizing and "maybe later"
creep in. This module fuses them deterministically into a single command:

    Fundstrat compact calls   (buy-the-dip / reclaim-watch / hold-recheck)
  + live tape                 (did the index/semis RECLAIM yet? IV capitulation?)
  + current holdings          (what do we actually own; what is held vs untracked)
  + target-weight gaps        (the FIXED target-drift read — held-but-untracked too)
  + flow / UW proof           (independent confirmation ONLY; neutral never = support)
  + event-risk state          (oil / rates / Hormuz — supportive, elevated, blocking)
  → a STAGED command          (STAGE-NOW / STAGE / CONFIRM-HOLD / FUND / HOLD / AVOID-NEW)

DOCTRINE RAILS (enforced by construction; mirrors options_surface.py):
  • LEAD WITH THE MOVE. Each row's first line is the sized action, not a score.
  • STRENGTH LOUD, WEAKNESS QUIET, RISK ALWAYS VISIBLE. A genuinely strong,
    researched, under-sized add is the loudest thing; a weak signal reads quiet;
    the funding leg + what-blocks-it stay visible.
  • DON'T CHASE. A name that is ALREADY at/over target does not become an ADD just
    because its thesis got confirmed (the MU-beat trap). Confirmation ≠ chase.
  • NEUTRAL ≠ SUPPORT. Inconclusive/neutral/not-checked flow never lifts conviction
    and never manufactures a confirmation it didn't earn (honest-synthesis rail).
  • HONEST ABSENCE. A lane that wasn't checked (e.g. Social Watch) stays
    not_checked — never silently treated as "all clear".
  • NEVER SILENT. The roll-up always speaks, even when the gate is shut.
  • PURE CORE + SEPARATE IO. convert()/from_feed() do no file IO and never raise on
    one malformed input — the producer's contract is to never go dark.
  • NO TRADE EXECUTION. Every move is a sized review prompt with a named trigger and
    a funding leg; it is never an order. The operator owns the call.

Engine reuse: this consumes position_drift_check.target_weight_drift_summary's
output verbatim (the target-drift block already in the feed) and the cockpit feed's
already-assembled lanes — it pulls nothing live itself (the live pulls happen
upstream in the build/chat), matching the repo's producer/bundle pattern.
"""
from __future__ import annotations

import html
import math
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

SOURCE = "volatility_opportunity_converter"

# ── disposition vocabulary (loudest first) ──────────────────────────────────
# STAGE-LEAD  : the highest-priority staged adds — under-target quality names that HELD UP
#               through the selloff (structural underweight, not tape-driven). They fire on
#               the SAME reclaim gate as everything else — nothing jumps the operator's gate —
#               but they sort loudest and carry an explicit "you MAY start tranche 1 ahead of the
#               reclaim because this underweight isn't tape-dependent — operator's call" note.
# STAGE       : gated add (semis / wrapper dip) — armed, FIRES on the named reclaim trigger.
# CONFIRM-HOLD: thesis confirmed by the event but already at/over target -> do NOT chase.
# FUND        : over-target sleeve that finances the staged adds (trim into strength).
# HOLD        : in-band; no action (kept so "no move" is an explicit, honest answer).
# AVOID-NEW   : no position; an avoid-new-exposure note kept quiet as new-buy-timing context.
# WATCH       : honest data gap / not-checked lane.
DISPOSITIONS = ("STAGE-LEAD", "STAGE", "CONFIRM-HOLD", "FUND", "HOLD", "AVOID-NEW", "WATCH")
_DISP_ORDER = {d: i for i, d in enumerate(DISPOSITIONS)}

# sell-flavoured action kinds whose loud version we quiet when we hold no position
_SELL_KINDS = {"sell", "sell_fast", "trim", "reduce", "exit", "avoid", "avoid_new",
               "liquidate", "dump", "unload"}

# ── tiny coercion helpers (a malformed field degrades; it never raises) ──────

def _num(x: Any) -> Optional[float]:
    if x is None or isinstance(x, bool) or x == "":
        return None
    try:
        v = float(x) if isinstance(x, (int, float)) else float(
            str(x).replace("$", "").replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None
    # Reject NaN / ±inf: they parse cleanly but `round()` raises on them downstream, which would
    # take the whole producer dark (never-silent rail). Funnel them into honest-absence instead.
    return v if math.isfinite(v) else None


def _money(x: Any) -> str:
    v = _num(x)
    if v is None:
        return "?"
    return f"${v:,.0f}"


def _tk(x: Any) -> str:
    return str(x or "").strip().upper()


def _esc(x: Any) -> str:
    return html.escape("" if x is None else str(x))


def _is_dict(x: Any) -> dict:
    return x if isinstance(x, dict) else {}


def _as_list(x: Any) -> list:
    """Coerce ANY value into a safe list to iterate — the never-raise rail for the ~half-dozen
    `for row in lane` sites. None->[]; a str/bytes->[x] (never char-iterate — the GRNJ foot-gun);
    a dict->its values; list/tuple/set->list; any other scalar->[x] (never `for x in 5` TypeError)."""
    if x is None:
        return []
    if isinstance(x, (str, bytes)):
        return [x]
    if isinstance(x, dict):
        return list(x.values())
    if isinstance(x, (list, tuple, set)):
        return list(x)
    return [x]


def _flat_tokens(x: Any) -> set[str]:
    """Normalise a `protected`/list-ish config of ANY shape into a clean ticker set: flattens one
    level of nesting and stringifies each item so a protected sleeve can neither crash the producer
    nor silently slip out of the set (dict->values, nested list, scalar, bare string all handled)."""
    out: set[str] = set()
    for item in _as_list(x):
        if isinstance(item, (list, tuple, set)):
            out.update(_tk(i) for i in item)
        else:
            out.add(_tk(item))
    return {t for t in out if t}


_TRUE_TOKENS = {"true", "1", "yes", "y", "on", "reclaim", "reclaimed", "confirmed"}


def _affirmative(x: Any) -> bool:
    """Fail-CLOSED truthiness for the reclaim gate. ONLY an explicit positive token (or real True /
    a number >= 1) reads True; every other string ("false", "no", "pending", "not reclaimed", "-1",
    "0.0"), every container (dict/list), and anything unknown reads False. The gate must never open
    on doubt — a denylist (treat-unknown-as-true) is the wrong default here (it flipped OPEN on
    "not reclaimed"); an allowlist fails safely toward 'not reclaimed yet'."""
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return math.isfinite(float(x)) and float(x) >= 1.0
    if isinstance(x, str):
        return x.strip().lower() in _TRUE_TOKENS
    return False


def _pct_pair(a: Optional[float], t: Optional[float]) -> str:
    """A '3.8%→8%' label, or an honest fallback when either side is missing. Interpolating
    None into a `%.1f` f-string would raise and take the whole producer down (never-silent rail)."""
    if a is None or t is None:
        return "target gap"
    return f"{a:.1f}%→{t:.0f}%"


# ── regime + gate ────────────────────────────────────────────────────────────

def classify_regime(tape: dict, fundstrat_calls: Iterable[dict]) -> dict:
    """Name the regime from the index/semis tape + the Fundstrat posture.

    Deliberately conservative: a regime label never *adds* conviction — it only
    routes (selloff → stage-the-dip, rebound-confirmed → fire). The actual size
    still comes from the target gap, never from how dramatic the day was.
    """
    smh = _is_dict(tape.get("SMH"))
    qqq = _is_dict(tape.get("QQQ"))
    smh_1d = _num(smh.get("pct_1d"))
    qqq_1d = _num(qqq.get("pct_1d"))
    buy_dip = any(_norm_stance(c.get("stance")) == "BUY_DIP" for c in fundstrat_calls or [])

    selloff = (smh_1d is not None and smh_1d <= -3.0) or (qqq_1d is not None and qqq_1d <= -1.5)
    reclaimed = _affirmative(smh.get("reclaimed")) and _affirmative(qqq.get("reclaimed"))

    if reclaimed:
        label, summary = "SELLOFF_REBOUND_CONFIRMED", "Index/semis reclaimed — rebound confirmed."
    elif selloff or buy_dip:
        label, summary = "SEMIS_SELLOFF_REBOUND_PENDING", (
            "Sharp semis/AI selloff; buy-the-dip posture, reclaim not yet confirmed."
        )
    else:
        label, summary = "NEUTRAL", "No volatility regime detected from the tape."
    return {"label": label, "summary": summary, "buy_dip_posture": buy_dip,
            "reclaimed": reclaimed}


def gate_state(tape: dict, event_risk: Optional[dict]) -> dict:
    """The single gate every *tape-dependent* add fires on: index+semis RECLAIM
    AND a supportive macro (oil/rates) backdrop. Held-support-but-not-reclaimed is
    ARMED, not OPEN — that distinction is the whole point (stage, don't chase)."""
    er = _is_dict(event_risk)
    er_state = str(er.get("state") or "NOT_CHECKED").upper()
    smh = _is_dict(tape.get("SMH"))
    qqq = _is_dict(tape.get("QQQ"))
    reclaimed = _affirmative(smh.get("reclaimed")) and _affirmative(qqq.get("reclaimed"))
    held = _affirmative(smh.get("held_support")) or _affirmative(qqq.get("held_support"))
    supportive = er_state == "SUPPORTIVE"

    if er_state == "BLOCKING":
        status, line = "BLOCKED", "Macro event-risk is blocking — do not add new exposure."
    elif reclaimed and supportive:
        status, line = "OPEN", "QQQ/SMH reclaimed and macro supportive — staged adds may fire."
    elif reclaimed and not supportive:
        status, line = "ARMED", "QQQ/SMH reclaimed but macro not confirmed supportive — size light."
    elif held and supportive:
        status, line = "ARMED", "Support held, macro supportive — armed; fires on QQQ/SMH reclaim."
    else:
        status, line = "PENDING", "Reclaim not confirmed — staged adds stay armed, not fired."
    trigger = "QQQ and SMH reclaim prior-session highs while oil stays soft and long-end yields ease"
    return {"status": status, "line": line, "named_trigger": trigger,
            "event_risk_state": er_state, "event_risk_note": er.get("note"),
            "reclaimed": reclaimed, "support_held": held, "macro_supportive": supportive}


# ── normalisation of the fused inputs ────────────────────────────────────────

_STANCE_ALIASES = {
    "BUY_DIP": "BUY_DIP", "BUYDIP": "BUY_DIP", "BUY-THE-DIP": "BUY_DIP", "BUY": "BUY_DIP",
    "RECLAIM_WATCH": "RECLAIM_WATCH", "RECLAIM": "RECLAIM_WATCH", "SUPPORT_WATCH": "RECLAIM_WATCH",
    "HOLD_RECHECK": "HOLD_RECHECK", "HOLD": "HOLD_RECHECK", "WATCH": "HOLD_RECHECK",
    "RECHECK": "HOLD_RECHECK",
    "AVOID": "AVOID", "AVOID_NEW": "AVOID", "SELL": "AVOID",
    "BULLISH": "BULLISH", "BEARISH": "BEARISH", "NEUTRAL": "NEUTRAL",
}


def _norm_stance(stance: Any) -> str:
    return _STANCE_ALIASES.get(str(stance or "").strip().upper().replace(" ", "_"), "NEUTRAL")


def _held_value_by_ticker(holdings: Any) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in _as_list(holdings):
        if not isinstance(row, dict):
            continue
        tk = _tk(row.get("ticker") or row.get("symbol"))
        mv = _num(row.get("market_value")) or _num(row.get("current_value")) or _num(row.get("value"))
        if tk and mv:
            out[tk] = out.get(tk, 0.0) + mv
    return out


def _uw_verdict(uw_proof: Any, ticker: str) -> str:
    """Independent flow read, normalised to BULLISH/BEARISH/NEUTRAL/NOT_CHECKED.

    NEUTRAL and NOT_CHECKED are NEVER allowed to become support downstream — that
    is the honest-synthesis rail (three echoes of one prior are still one signal;
    an inconclusive read is not a confirmation)."""
    proof = _is_dict(uw_proof).get(ticker)
    if proof is None:
        return "NOT_CHECKED"
    if isinstance(proof, str):
        v = proof.strip().upper()
        return v if v in ("BULLISH", "BEARISH", "NEUTRAL") else "NEUTRAL"
    proof = _is_dict(proof)
    explicit = str(proof.get("verdict") or "").strip().upper()
    if explicit in ("BULLISH", "BEARISH", "NEUTRAL", "NOT_CHECKED"):
        return explicit
    net = _num(proof.get("net_premium"))
    if net is None:
        return "NOT_CHECKED"
    # Require a MATERIAL one-sided print before calling it support; small nets are noise.
    if net >= 5_000_000:
        return "BULLISH"
    if net <= -5_000_000:
        return "BEARISH"
    return "NEUTRAL"


# ── positions-freshness guard ────────────────────────────────────────────────

def _to_date(s: Any):
    """Parse a YYYY-MM-DD (or ISO timestamp) into a date; None on anything else."""
    if not s:
        return None
    text = str(s)[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def positions_staleness(positions_as_of: Any, today: Any, stale_after_days: int = 3) -> Optional[dict]:
    """The 'stale data is stamped, never presented as current' rail. If the positions snapshot is
    more than `stale_after_days` older than `today`, return a loud flag; else None. Sizing computed
    off a stale book is the failure that put a 6/17 snapshot behind a 6/25 call — this makes it loud."""
    d0, d1 = _to_date(positions_as_of), _to_date(today)
    if d0 is None or d1 is None:
        return None
    days = (d1 - d0).days
    if days > stale_after_days:
        return {"stale": True, "days_old": days, "as_of": str(d0),
                "note": (f"positions snapshot is {days} days old (as of {d0}) — dollar sizing is "
                         f"computed off a stale book; refresh the broker sync before acting")}
    return {"stale": False, "days_old": days, "as_of": str(d0)}


# ── the converter ────────────────────────────────────────────────────────────

def convert(
    *,
    target_drift: Optional[dict],
    holdings: Any = None,
    book_value: Optional[float] = None,
    fundstrat_calls: Optional[list] = None,
    tape: Optional[dict] = None,
    uw_proof: Optional[dict] = None,
    event_risk: Optional[dict] = None,
    social_watch: Optional[dict] = None,
    funding_policy: Optional[dict] = None,
    tranches: int = 3,
    positions_as_of: Optional[str] = None,
    today: Optional[str] = None,
    stale_after_days: int = 3,
    as_of: Optional[str] = None,
    generated_at: Optional[str] = None,
) -> dict:
    """Fuse the lanes into one staged command. Pure: no IO, never raises on a single
    malformed lane (a bad lane degrades to honest-absence, the rest still speak)."""
    target_drift = _is_dict(target_drift)
    tape = _is_dict(tape)
    fundstrat_calls = [c for c in _as_list(fundstrat_calls) if isinstance(c, dict)]
    funding_policy = _is_dict(funding_policy) or {
        "protected": ["GRNJ"], "conditional": {"NVDA": "concentration_rail"}}
    tranches = max(1, int(_num(tranches) or 3))  # never let a junk tranches crash the size math
    # `protected` of ANY shape (bare string, dict, nested list, scalar) is normalised so a protected
    # sleeve can neither char-iterate into {'G','R','N','J'} nor crash the producer (never-dark rail).
    protected = _flat_tokens(funding_policy.get("protected"))
    conditional = {_tk(k): v for k, v in _is_dict(funding_policy.get("conditional")).items()}

    held = _held_value_by_ticker(holdings)
    held_set = set(held)
    book_derived = False
    if book_value is None and held:
        _summed = _num(sum(held.values()))
        if _summed and _summed > 0:  # a non-positive derived book is garbage → honest absence
            book_value = _summed
            book_derived = True
    book_value = _num(book_value)
    if book_value is not None and book_value <= 0:
        book_value = None  # never size off a zero/negative book

    drift_rows = [r for r in _as_list(target_drift.get("rows")) if isinstance(r, dict)]
    fs_by_ticker = {_tk(c.get("ticker")): c for c in fundstrat_calls}
    regime = classify_regime(tape, fundstrat_calls)
    gate = gate_state(tape, event_risk)

    # Numeric truth: a ticker is "over target" when its OWN numbers say so (actual >= target) OR any
    # row labels it OVERSIZED (even with a missing number). This (a) refuses to STAGE a name that is
    # really at/over target even if a row mislabels it UNDERSIZED — the MU-beat chase trap — and
    # (b) de-dupes a ticker so it can never occupy both the add loop and the funding loop.
    over_target_tickers = set()
    for r in drift_rows:
        a, t = _num(r.get("actual_pct")), _num(r.get("target_pct"))
        if str(r.get("direction") or "").upper() == "OVERSIZED" or (a is not None and t is not None and a >= t):
            over_target_tickers.add(_tk(r.get("ticker")))
    # Conflicted tickers: an UNDERSIZED row whose ticker is ALSO over-target somewhere. The add is
    # suppressed (we don't add to an over-target name), but it must surface in honesty, never vanish.
    conflicted_tickers = sorted({
        _tk(r.get("ticker")) for r in drift_rows
        if str(r.get("direction") or "").upper() == "UNDERSIZED" and _tk(r.get("ticker")) in over_target_tickers
    })
    missing_tickers = [
        _tk(r.get("ticker")) for r in drift_rows
        if str(r.get("direction") or "").upper() == "MISSING" and _tk(r.get("ticker"))
    ]

    command: list[dict] = []
    funding: list[dict] = []

    def _gap_usd(pct: Optional[float]) -> Optional[float]:
        if pct is None or book_value is None:
            return None
        return round(pct / 100.0 * book_value)

    # ---- under-target held names → staged adds (the loud, action-pulling rows) ----
    for r in drift_rows:
        tk = _tk(r.get("ticker"))
        if r.get("direction") != "UNDERSIZED":
            continue
        actual, target = _num(r.get("actual_pct")), _num(r.get("target_pct"))
        # Guards: never STAGE a protected sleeve; never STAGE a name whose own numbers prove it is
        # at/over target (a mislabeled row must not become an ADD); de-dupe vs the over-target loop.
        if tk in protected:
            continue
        if tk in over_target_tickers or (actual is not None and target is not None and actual >= target):
            continue
        gap_pct = None if (actual is None or target is None) else max(0.0, target - actual)
        gap_usd = _gap_usd(gap_pct)
        tk_tape = _is_dict(tape.get(tk))
        verdict = _uw_verdict(uw_proof, tk)
        stance = _norm_stance(fs_by_ticker.get(tk, {}).get("stance"))
        # "structural" = the underweight is independent of the selloff: the name held
        # up (shallow drawdown) OR it is a single name (not the semis/wrapper dip trade).
        is_wrapper = bool(tk_tape.get("is_wrapper"))
        held_up = tk_tape.get("held_up")
        drawdown = _num(tk_tape.get("pct_1d"))
        if held_up is None and drawdown is not None:
            held_up = drawdown > -3.0
        structural = (not is_wrapper) and bool(held_up)
        disposition = "STAGE-LEAD" if structural else "STAGE"
        tranche_usd = round(gap_usd / max(1, tranches)) if gap_usd else None

        support_note = None
        if verdict == "BULLISH":
            support_note = "independent flow confirms (bullish net premium)"
        elif verdict in ("NEUTRAL", "NOT_CHECKED"):
            support_note = f"flow {verdict.lower().replace('_', ' ')} — NOT counted as confirmation"

        if disposition == "STAGE-LEAD":
            move = (f"Stage {tk} add ≈ {_money(gap_usd)} to target — highest-priority staged add "
                    f"({tk} held up in the selloff; the {_pct_pair(actual, target)} gap is structural, "
                    f"not a bounce chase). Fires on the reclaim like the rest — but because this "
                    f"underweight isn't tape-dependent, you MAY start tranche 1 ≈ {_money(tranche_usd)} "
                    f"ahead of the reclaim. Operator's call.")
            gate_text = ("fires on " + gate["named_trigger"]
                         + "; optional early tranche 1 is an operator choice (structural underweight)")
        else:
            move = (f"Stage {tk} add ≈ {_money(gap_usd)} to target — ARMED, fires on the reclaim "
                    f"(buy-the-dip exposure, tape-dependent).")
            gate_text = "fires on " + gate["named_trigger"]
        command.append({
            "ticker": tk, "disposition": disposition,
            "move": move,
            "size_to_target_usd": gap_usd, "tranche_usd": tranche_usd, "structural": structural,
            "actual_pct": actual, "target_pct": target, "gap_pct": gap_pct,
            "fundstrat_stance": stance, "uw_verdict": verdict, "support_note": support_note,
            "gate": gate_text,
            "risk_note": "sized to the target gap, inside survival rails; a staged prompt, never an order",
            "held": tk in held_set,
            "_rank": _DISP_ORDER[disposition],
        })

    # ---- over-target held names → don't-chase + funding ----
    for r in drift_rows:
        tk = _tk(r.get("ticker"))
        if r.get("direction") != "OVERSIZED":
            continue
        actual, target = _num(r.get("actual_pct")), _num(r.get("target_pct"))
        if tk in protected:
            continue  # never auto-funded; surfaced in honesty below
        # PROVEN over-target only: an OVERSIZED row whose numbers are missing or say at/under target
        # must not become a trim/funding candidate (no unproven excess).
        if actual is None or target is None or actual <= target:
            continue
        # never recommend trimming / confirm-holding a name we can't confirm we OWN. Fail closed:
        # an empty/stale positions lane is the highest-risk state, so it must SKIP, never assume held.
        if tk not in held_set:
            continue
        excess_pct = max(0.0, actual - target)
        excess_usd = _gap_usd(excess_pct)
        stance = _norm_stance(fs_by_ticker.get(tk, {}).get("stance"))
        note = fs_by_ticker.get(tk, {}).get("note") or ""
        # "Confirmed" must be EARNED, never manufactured (NEUTRAL/negative != support). Use the same
        # affirmative-allowlist as the gate for the flag (so event_confirmation="false" can't confirm),
        # and require a word-boundary "beat" with no negation in the note (so a bearish "couldn't beat"
        # / "no beat" / "heartbeat" never reads as a confirming beat).
        _note_l = note.lower()
        _beat = " beat " in f" {_note_l} " and not any(
            neg in _note_l for neg in ("not", "miss", "no beat", "couldn't", "could not", "fail", "below", "weak"))
        confirmed = _affirmative(_is_dict(tape.get(tk)).get("event_confirmation")) or _beat
        # A name the operator has marked CONDITIONAL (e.g. NVDA — only trim if a concentration rail is
        # breached) must NOT become a routine trim/CONFIRM-HOLD even when it's over target. Surface it
        # as funding-of-last-resort with its real excess, ranked last, never auto-used.
        is_conditional = tk in conditional

        if confirmed and not is_conditional:
            over_txt = (f"≈ {_money(excess_usd)} OVER target ({actual:.1f}% vs {target:.1f}%)"
                        if actual is not None and target is not None
                        else f"OVER target by {_money(excess_usd)}")
            command.append({
                "ticker": tk, "disposition": "CONFIRM-HOLD",
                "move": (f"Do NOT chase {tk} — the event confirms the thesis but you are already "
                         f"{over_txt}. Use the beat as confirmation; the excess is a funding "
                         f"candidate into strength."),
                "actual_pct": actual, "target_pct": target, "excess_usd": excess_usd,
                "fundstrat_stance": stance,
                "risk_note": "trimming into post-event STRENGTH (not weakness) honours the sell-gate",
                "held": tk in held_set, "_rank": _DISP_ORDER["CONFIRM-HOLD"],
            })
        funding.append({
            "ticker": tk, "excess_usd": excess_usd, "excess_pct": excess_pct,
            "is_wrapper": bool(_is_dict(tape.get(tk)).get("is_wrapper")),
            "confirmed_strength": confirmed, "conditional": is_conditional,
            "note": (f"OVER target by {_money(excess_usd)} — funding ONLY if {conditional[tk]} breached, "
                     f"not used by default" if is_conditional
                     else "trim into post-event strength" if confirmed
                     else "over-target excess — trim candidate"),
        })

    # conditional funding (e.g. NVDA only if a concentration rail is breached) — surfaced, not auto-used
    for tk, why in conditional.items():
        if tk in protected:
            continue  # a protected sleeve is never funded, even via the conditional path
        if tk in held_set and not any(f["ticker"] == tk for f in funding):
            funding.append({"ticker": tk, "excess_usd": None, "excess_pct": None,
                            "is_wrapper": False, "confirmed_strength": False,
                            "note": f"funding ONLY if {why} is breached — not used by default"})

    # rank funding: conditional (last-resort) sinks to the bottom; then wrapper excess first,
    # then biggest over-target, strength before weakness.
    funding.sort(key=lambda f: (bool(f.get("conditional")), not f.get("is_wrapper"),
                                -(_num(f.get("excess_usd")) or 0)))

    command.sort(key=lambda c: (c["_rank"], -(_num(c.get("size_to_target_usd")) or
                                              _num(c.get("excess_usd")) or 0), c["ticker"]))
    for c in command:
        c.pop("_rank", None)

    staleness = positions_staleness(positions_as_of, today, stale_after_days)
    honesty = _build_honesty(social_watch, uw_proof, drift_rows, protected, gate, book_value,
                             missing_tickers=missing_tickers, book_derived=book_derived,
                             conflicted_tickers=conflicted_tickers, holdings_known=bool(held_set),
                             staleness=staleness)
    summary = _summarize(command, funding, gate, regime, staleness=staleness)
    return {
        "source": SOURCE,
        "as_of": as_of or target_drift.get("as_of"),
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "regime": regime,
        "gate": gate,
        "book_value": book_value,
        "positions_as_of": positions_as_of,
        "positions_freshness": staleness,
        "command": command,
        "funding": funding,
        "honesty": honesty,
        "summary": summary,
    }


def _build_honesty(social_watch, uw_proof, drift_rows, protected, gate, book_value,
                   *, missing_tickers=None, book_derived=False, conflicted_tickers=None,
                   holdings_known=True, staleness=None) -> dict:
    h: dict[str, Any] = {}
    if isinstance(staleness, dict) and staleness.get("stale"):
        h["positions_freshness"] = staleness.get("note")
    sw = _is_dict(social_watch)
    sw_status = str(sw.get("status") or "not_checked")
    if sw_status not in ("has_data", "checked", "checked_clear"):
        h["social_watch"] = f"not checked ({sw_status}) — absent, not 'all clear'"
    neutral = [t for t in (_is_dict(uw_proof).keys()) if _uw_verdict(uw_proof, t) in ("NEUTRAL", "NOT_CHECKED")]
    if neutral:
        h["uw_proof"] = ("neutral/inconclusive for " + ", ".join(sorted(neutral))
                         + " — explicitly NOT counted as confirmation")
    if protected:
        h["protected_sleeves"] = (", ".join(sorted(protected))
                                  + " excluded from funding (protected diversified sleeve)")
    if book_value is None:
        h["book_value"] = "not readable — gaps shown in % only, dollar sizing withheld"
    elif book_derived:
        h["book_value"] = (f"derived by summing holdings (${book_value:,.0f}) — verify it is the "
                           f"FULL book before sizing")
    if missing_tickers:
        h["missing_targets"] = (", ".join(sorted(set(missing_tickers)))
                                + " held at 0% vs a model target — new-position research candidate(s), "
                                "not staged here (out of scope for gap-to-target adds)")
    if conflicted_tickers:
        h["conflicted_drift"] = (", ".join(conflicted_tickers)
                                 + " carry BOTH under- and over-target rows — add suppressed (never "
                                 "add to an over-target name); resolve the drift feed upstream")
    if not holdings_known and any(str(r.get("direction") or "").upper() == "OVERSIZED" for r in drift_rows):
        h["funding"] = ("positions lane empty/unconfirmed — over-target funding/trim WITHHELD "
                        "(can't confirm holdings; never trim a name we can't prove we own)")
    if not drift_rows:
        h["target_drift"] = "no drift rows supplied — adds/funding not computed"
    er_state = gate.get("event_risk_state")
    if er_state == "NOT_CHECKED":
        h["event_risk"] = "event-risk lane not checked — gate treats macro as unconfirmed"
    elif er_state == "ELEVATED":
        h["event_risk"] = ("event-risk ELEVATED (populated but not confirmed supportive) — staged "
                           "adds sized light; risk stays visible, not hidden")
    elif er_state == "BLOCKING":
        h["event_risk"] = "event-risk BLOCKING — no new exposure until the macro clears"
    return h


def _summarize(command, funding, gate, regime, *, staleness=None) -> dict:
    acts = [c for c in command if c["disposition"] in ("STAGE-LEAD", "STAGE")]
    lead_rows = [c for c in command if c["disposition"] == "STAGE-LEAD"]
    holds = [c for c in command if c["disposition"] == "CONFIRM-HOLD"]
    # conditional funders (last-resort) don't count toward the headline's funding total — they're
    # not used by default, so adding them would overstate the capital actually freed.
    total_add = sum(_num(c.get("size_to_target_usd")) or 0 for c in acts)
    total_fund = sum(_num(f.get("excess_usd")) or 0 for f in funding if not f.get("conditional"))
    if acts:
        headline = (f"{regime['summary']} {len(acts)} staged add(s) "
                    f"(≈ {_money(total_add)} to target), funded ≈ {_money(total_fund)} from over-target sleeves. "
                    f"Gate: {gate['status']}.")
    elif holds:
        headline = (f"{regime['summary']} No new adds clear the gate; "
                    f"{len(holds)} confirmed-but-at-target name(s) — do not chase.")
    else:
        headline = f"{regime['summary']} No staged adds and no funding flagged — nothing hidden."
    # STAMP staleness first (loudest), so a stale book is never presented as current sizing.
    if isinstance(staleness, dict) and staleness.get("stale"):
        headline = f"⚠ STALE POSITIONS ({staleness.get('days_old')}d old, as of {staleness.get('as_of')}) — refresh before sizing. " + headline
    return {
        "headline": headline,
        "stage_count": len(acts), "stage_lead_count": len(lead_rows),
        "confirm_hold_count": len(holds), "funding_count": len(funding),
        "total_add_usd": round(total_add) if total_add else 0,
        "total_funding_usd": round(total_fund) if total_fund else 0,
        "decide_not_watch": bool(acts or holds),  # the surface PULLS to a decision, not a passive watch
    }


# ── demote no-position sell-fast rows ────────────────────────────────────────

def demote_no_position_sells(actions: Any, held: Any) -> list[dict]:
    """Quiet down loud SELL/sell-fast rows on names we don't own.

    A 'sell fast' on a ticker with no position is noise that crowds out the real
    decision — UNLESS it is (a) a held ticker, or (b) an avoid-new-exposure note
    that gates a real new-buy choice. Held sells stay loud; avoid-new rows stay as
    quiet new-buy-timing CONTEXT; pure no-position sells are demoted to backlog.
    Returns a NEW list (never mutates the caller's rows)."""
    # "Held" is about OWNERSHIP, not size: a position with market_value 0 (written-down, halted,
    # unpriced, stale quote) is still HELD. Derive held-set from ticker PRESENCE, never from a
    # positive market value (that would silently bury a real held name's sell).
    if isinstance(held, set):
        held_set = {_tk(t) for t in held if _tk(t)}
    else:
        held_set = {
            _tk(r.get("ticker") or r.get("symbol"))
            for r in _as_list(held)
            if isinstance(r, dict) and (r.get("ticker") or r.get("symbol"))
        }
    out: list[dict] = []
    for a in _as_list(actions):
        if not isinstance(a, dict):
            continue
        row = dict(a)
        kind = str(row.get("kind") or "").strip().lower()
        tk = _tk(row.get("ticker"))
        what = str(row.get("what") or "")
        is_sell = kind in _SELL_KINDS or "sell" in kind
        if not is_sell:
            out.append(row)
            continue
        if tk and tk in held_set:
            out.append(row)  # affects a held ticker → stays loud
            continue
        avoid_new = ("avoid-new" in what.lower() or "avoid new" in what.lower()
                     or kind in ("avoid", "avoid_new"))
        # Quiet the row to the schema's lowest-prominence state (WATCH) — never invent a new
        # action_state (Contract-C only permits ACT_NOW/MONITOR/RESEARCH/WATCH). The demotion
        # semantics ride on our own fields so the surface/render can style them distinctly.
        row.setdefault("original_action_state", a.get("action_state"))
        row["demoted"] = True
        row["action_state"] = "WATCH"
        if avoid_new:
            row["demote_reason"] = "no position — kept as quiet avoid-new-exposure context, not a sell"
            row["surface_role"] = "context"
        else:
            row["demote_reason"] = "no position and not an avoid-new choice — demoted to backlog"
            row["surface_role"] = "backlog"
        out.append(row)
    return out


# ── feed adapter (build the inputs from an already-assembled cockpit feed) ────

def from_feed(feed: Any, *, as_of: Optional[str] = None, today: Optional[str] = None,
              generated_at: Optional[str] = None) -> dict:
    """Build convert()'s inputs from the assembled feed — no NEW live pulls. Best-effort
    and defensive: any absent lane degrades to honest-absence, never an exception."""
    feed = _is_dict(feed)
    target_drift = _is_dict(feed.get("target_drift"))
    pv = _is_dict(feed.get("portfolio_views"))
    combined = _is_dict(_is_dict(pv.get("views")).get("combined"))
    book_value = _num(combined.get("total_value"))
    holdings = combined.get("rows") or feed.get("holdings") or []
    # Positions snapshot date for the staleness guard: prefer the reallocation brief's stamp, then
    # the portfolio view's, then the target-drift as_of. `today` defaults to the feed's as-of date.
    rb = _is_dict(feed.get("reallocation_brief"))
    positions_as_of = (rb.get("positions_snapshot_date") or combined.get("snapshot_date")
                       or combined.get("as_of") or target_drift.get("as_of"))
    today = today or str(feed.get("as_of") or feed.get("generated_at") or "")[:10] or None

    fundstrat_calls = _fundstrat_calls_from_feed(feed)
    tape = _tape_from_feed(feed)
    event_risk = _event_risk_from_feed(feed)
    return convert(
        target_drift=target_drift, holdings=holdings, book_value=book_value,
        fundstrat_calls=fundstrat_calls, tape=tape, event_risk=event_risk,
        social_watch=feed.get("social_watch"), positions_as_of=positions_as_of, today=today,
        as_of=as_of or feed.get("generated_at"), generated_at=generated_at,
    )


def _fundstrat_calls_from_feed(feed: dict) -> list[dict]:
    calls: list[dict] = []
    for row in _as_list(feed.get("lean_in")):
        if isinstance(row, dict) and row.get("ticker"):
            calls.append({"ticker": row["ticker"], "stance": "BULLISH",
                          "note": row.get("what") or row.get("why") or "", "source": "lean_in"})
    fn = _is_dict(feed.get("fundstrat_news"))
    for row in _as_list(fn.get("rows")):
        if isinstance(row, dict) and row.get("ticker"):
            calls.append({"ticker": row["ticker"], "stance": row.get("stance") or "NEUTRAL",
                          "note": row.get("headline") or row.get("note") or "", "source": "fundstrat_news"})
    return calls


def _tape_from_feed(feed: dict) -> dict:
    tape: dict[str, dict] = {}
    for row in _as_list(feed.get("radar")):
        if isinstance(row, dict) and row.get("ticker"):
            tape[_tk(row["ticker"])] = {"pct_1d": _num(row.get("pct_1d") or row.get("change_pct"))}
    return tape


def _event_risk_from_feed(feed: dict) -> dict:
    er = feed.get("event_risk")
    rows = er if isinstance(er, list) else (_is_dict(er).get("rows") or [])
    if not rows:
        return {"state": "NOT_CHECKED"}
    blob = " ".join(str(_is_dict(r).get("what") or _is_dict(r).get("note") or r) for r in rows).lower()
    # Map genuine blocking language to BLOCKING (so the no-add-into-a-blocking-macro gate is
    # actually reachable in production); otherwise a populated risk lane is ELEVATED, never
    # silently SUPPORTIVE — the adapter never invents support (a scored SUPPORTIVE must come
    # from upstream). Explicit parentheses avoid the and/or precedence trap.
    blocking = any(k in blob for k in (
        "do not add", "do-not-add", "halt", "block new", "no new exposure", "risk-off", "risk off"))
    state = "BLOCKING" if blocking else "ELEVATED"
    return {"state": state, "note": (rows[0] if isinstance(rows[0], str)
                                     else _is_dict(rows[0]).get("what"))}


# ════════════════════════════════════════════════════════════════════════════
# SURFACE — LOUD, plain-language renders (text + html). Never silent; risk visible.
# ════════════════════════════════════════════════════════════════════════════

def render_command_text(result: Optional[dict]) -> str:
    r = _is_dict(result)
    lines = ["\U0001f6a6 VOLATILITY OPPORTUNITY — STAGED COMMAND"]
    summary = _is_dict(r.get("summary"))
    gate = _is_dict(r.get("gate"))
    lines.append(summary.get("headline") or "No command produced.")
    lines.append(f"  Gate [{gate.get('status', '?')}]: {gate.get('line', '')}")
    if gate.get("named_trigger"):
        lines.append(f"  Trigger: {gate['named_trigger']}")
    for c in r.get("command") or []:
        lines.append(f"▶ [{c.get('disposition')}] {c.get('move')}")
        if c.get("support_note"):
            lines.append(f"    · {c['support_note']}")
        if c.get("risk_note"):
            lines.append(f"    · {c['risk_note']}")
    funding = r.get("funding") or []
    if funding:
        lines.append("  Funding (in order):")
        for f in funding:
            amt = _money(f.get("excess_usd")) if f.get("excess_usd") is not None else "—"
            lines.append(f"    · {f.get('ticker')}: {amt} — {f.get('note')}")
    for k, v in _is_dict(r.get("honesty")).items():
        lines.append(f"  ⓘ {k}: {v}")
    lines.append(f"(as of {r.get('as_of')}; built {r.get('generated_at')}; a staged prompt, never an order)")
    return "\n".join(lines).rstrip()


_DISP_COLOR = {"STAGE-LEAD": "#34d399", "STAGE": "#fbbf24", "CONFIRM-HOLD": "#fb923c",
               "FUND": "#94a3b8", "HOLD": "#94a3b8", "AVOID-NEW": "#94a3b8", "WATCH": "#94a3b8"}
_GATE_COLOR = {"OPEN": "#34d399", "ARMED": "#fbbf24", "PENDING": "#fbbf24", "BLOCKED": "#f87171"}


def render_command_html(result: Optional[dict]) -> str:
    """A LOUD 'VOLATILITY OPPORTUNITY' block for the Today-Decide surface. Self-contained
    inline styles; leads with each sized move; gate + funding + honesty always visible;
    labelled even when empty (never silent)."""
    title = ('<div class="td-section-title" style="font-size:14px;letter-spacing:.04em;'
             'margin:14px 0 6px 0;color:#e2e8f0">\U0001f6a6 VOLATILITY OPPORTUNITY — STAGED COMMAND</div>')
    r = _is_dict(result)
    if not result:
        body = ('<div style="color:#94a3b8;font-size:13px">volatility converter: not run this build '
                '— no regime fused.</div>')
        return f'<div class="td-vol">{title}{body}</div>'
    summary = _is_dict(r.get("summary"))
    gate = _is_dict(r.get("gate"))
    gcolor = _GATE_COLOR.get(str(gate.get("status")), "#94a3b8")
    parts = [f'<div class="td-vol">{title}']
    parts.append(f'<div style="font-size:13px;color:#e2e8f0;margin:2px 0 6px 0">{_esc(summary.get("headline"))}</div>')
    parts.append(f'<div style="font-size:12px;color:{gcolor};font-weight:600">Gate [{_esc(gate.get("status"))}]: '
                 f'{_esc(gate.get("line"))}</div>')
    if gate.get("named_trigger"):
        parts.append(f'<div style="font-size:11px;color:#94a3b8">trigger: {_esc(gate.get("named_trigger"))}</div>')
    for c in r.get("command") or []:
        color = _DISP_COLOR.get(str(c.get("disposition")), "#94a3b8")
        parts.append(f'<div class="td-vol-card" style="border-left:3px solid {color};padding:2px 0 4px 10px;margin:8px 0">')
        parts.append(f'<div style="font-size:14px;font-weight:700;color:#e2e8f0">▶ '
                     f'<span style="color:{color}">[{_esc(c.get("disposition"))}]</span> {_esc(c.get("move"))}</div>')
        if c.get("support_note"):
            parts.append(f'<div style="font-size:12px;color:#cbd5e1">{_esc(c.get("support_note"))}</div>')
        if c.get("risk_note"):
            parts.append(f'<div style="font-size:11px;color:#f87171">{_esc(c.get("risk_note"))}</div>')
        parts.append('</div>')
    funding = r.get("funding") or []
    if funding:
        fl = "; ".join(f'{_esc(f.get("ticker"))} {_money(f.get("excess_usd")) if f.get("excess_usd") is not None else "—"} '
                       f'({_esc(f.get("note"))})' for f in funding)
        parts.append(f'<div style="font-size:12px;color:#cbd5e1;margin-top:4px"><b>Funding:</b> {fl}</div>')
    for k, v in _is_dict(r.get("honesty")).items():
        parts.append(f'<div style="font-size:11px;color:#94a3b8">ⓘ {_esc(k)}: {_esc(v)}</div>')
    parts.append('<div style="color:#64748b;font-size:11px;margin-top:6px">'
                 f'as of {_esc(r.get("as_of"))} · built {_esc(r.get("generated_at"))} · '
                 'a sized, staged prompt — never an order; you place the trade.</div>')
    parts.append('</div>')
    return "".join(parts)


# ─────────────────────────────────── self-test ───────────────────────────────

def _self_test() -> int:
    """The 2026-06-23/24 semis-selloff + MU-beat regime through the full converter."""
    fails: list[str] = []

    def chk(c, label):
        if not c:
            fails.append(label)

    target_drift = {"status": "has_data", "rows": [
        {"ticker": "GOOGL", "direction": "UNDERSIZED", "actual_pct": 3.76, "target_pct": 8.0},
        {"ticker": "AVGO", "direction": "UNDERSIZED", "actual_pct": 2.12, "target_pct": 6.0},
        {"ticker": "MSFT", "direction": "UNDERSIZED", "actual_pct": 1.55, "target_pct": 5.0},
        {"ticker": "GRNY", "direction": "OVERSIZED", "actual_pct": 9.56, "target_pct": 3.0},
        {"ticker": "GRNJ", "direction": "OVERSIZED", "actual_pct": 8.58, "target_pct": 3.0},
        {"ticker": "MU", "direction": "OVERSIZED", "actual_pct": 3.67, "target_pct": 3.0},
    ]}
    holdings = [{"ticker": t, "market_value": 1} for t in ("GOOGL", "AVGO", "MSFT", "GRNY", "GRNJ", "MU", "NVDA")]
    tape = {
        "QQQ": {"pct_1d": -0.4, "reclaimed": False, "held_support": True},
        "SMH": {"pct_1d": -0.5, "reclaimed": False, "held_support": True, "is_wrapper": True},
        "GOOGL": {"pct_1d": -0.2, "held_up": True},
        "AVGO": {"pct_1d": 0.5, "held_up": True},
        "MSFT": {"pct_1d": -2.3, "held_up": True},
        "MU": {"pct_1d": -0.3, "event_confirmation": True},
    }
    fundstrat_calls = [
        {"ticker": "SMH", "stance": "BUY_DIP", "note": "buy the 7% dip"},
        {"ticker": "MU", "stance": "HOLD_RECHECK", "note": "MU beat, bounce for miners"},
    ]
    uw_proof = {"GOOGL": {"verdict": "NEUTRAL"}, "AVGO": {"net_premium": 336571}}
    event_risk = {"state": "SUPPORTIVE", "note": "oil soft, long-end yields easing"}
    social_watch = {"status": "not_checked"}

    res = convert(target_drift=target_drift, holdings=holdings, book_value=1_923_513,
                  fundstrat_calls=fundstrat_calls, tape=tape, uw_proof=uw_proof,
                  event_risk=event_risk, social_watch=social_watch,
                  funding_policy={"protected": ["GRNJ"], "conditional": {"NVDA": "concentration_rail"}},
                  as_of="2026-06-24", generated_at="2026-06-25T00:00:00Z")

    cmd = {c["ticker"]: c for c in res["command"]}
    chk(res["summary"]["decide_not_watch"], "produces a DECIDE/STAGE surface, not WATCH-only")
    chk(cmd["GOOGL"]["disposition"] == "STAGE-LEAD", "GOOGL (held up) -> STAGE-LEAD")
    chk(res["command"][0]["disposition"] == "STAGE-LEAD", "a STAGE-LEAD add sorts loudest")
    chk("Operator's call" in cmd["GOOGL"]["move"], "early tranche is surfaced as an operator choice, not auto-fired")
    chk(cmd["MU"]["disposition"] == "CONFIRM-HOLD", "MU overweight + beat -> CONFIRM-HOLD, not ADD")
    chk("Do NOT chase MU" in cmd["MU"]["move"], "MU move says do-not-chase")
    chk(cmd["GOOGL"]["uw_verdict"] == "NEUTRAL"
        and "NOT counted" in (cmd["GOOGL"]["support_note"] or ""), "neutral UW != support")
    fund = {f["ticker"]: f for f in res["funding"]}
    chk("GRNY" in fund and fund["GRNY"]["is_wrapper"] is False, "GRNY is a funding source")
    chk(res["funding"][0]["ticker"] == "GRNY", "GRNY (biggest over-target) funds first")
    chk("GRNJ" not in fund, "GRNJ protected — never a funding source")
    chk(res["honesty"].get("social_watch", "").startswith("not checked"), "social watch stays not_checked")
    chk(res["gate"]["status"] in ("ARMED", "PENDING"), "gate not OPEN (reclaim not confirmed)")
    chk("OVER target" in cmd["MU"]["move"], "MU shows it is over target")

    # demotion: RYF sell_fast with no position -> demoted; held name sell stays loud
    actions = [
        {"ticker": "RYF", "kind": "sell_fast", "what": "Avoid-new-exposure watch"},
        {"ticker": "XOP", "kind": "sell_fast", "what": "Sell fast"},
        {"ticker": "GRNY", "kind": "trim", "what": "Trim overweight"},
        {"ticker": "MAGS", "kind": "lean_in", "what": "Lean-in"},
    ]
    dem = {a["ticker"]: a for a in demote_no_position_sells(actions, {"GRNY", "MU"})}
    chk(dem["RYF"].get("surface_role") == "context", "RYF avoid-new -> quiet context (kept)")
    chk(dem["XOP"].get("surface_role") == "backlog", "XOP no-position sell -> demoted to backlog")
    chk("demoted" not in dem["GRNY"], "held GRNY trim stays loud")
    chk("demoted" not in dem["MAGS"], "non-sell lean-in untouched")

    # never silent / never raises
    chk(render_command_text(res).startswith("\U0001f6a6"), "text render leads loud")
    chk("VOLATILITY OPPORTUNITY" in render_command_html(res), "html render labelled")
    empty = convert(target_drift=None, holdings=None)
    chk(empty["summary"]["headline"] and not empty["summary"]["decide_not_watch"], "empty -> honest, non-silent")
    junk = convert(target_drift=[1, 2], holdings="x", fundstrat_calls="y", tape=5, uw_proof=7)
    chk(junk["source"] == SOURCE, "malformed inputs -> degrade, never raise")

    if fails:
        print("volatility_opportunity_converter self-test: FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("volatility_opportunity_converter self-test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
