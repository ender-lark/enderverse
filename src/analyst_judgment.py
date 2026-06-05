"""Conviction Engine — Layer 3 Analyst: JUDGMENT reads (A3a: ① ②).

The Claude-judgment reads, encoded as deterministic procedures for v1 so the
discrete answer (the grade, the direction word) is unit-testable NOW and the
golden-master (A6) can run in-sandbox; the prose is templated; the production
routine's Claude refines edge cases (the judgment seam). Tested by boundary
asserts here + the golden-master against the corrected v4 oracle (A6).

A3a:
  ① conviction_read            — quality grade Strong/Promising/Mixed/Weak/— (cockpit `cv`)
  ② conviction_direction_read  — EVENT-driven up/flat/down + dated trail (cockpit `cd`/`cdNote`)
A3b:
  ③ net_read                   — the plain "what to do" reconciliation headline (cockpit `nr`)
  ⑦ fresh_signal_read          — the Actions strip: "is this a BUY now?" + ⏳/👁 urgency

That completes the 4 judgment reads (① ② ③ ⑦). Next: A4 Contract-C validator → A5
golden freeze → A6 golden-master.

Output alignment (reconciled against conviction_cockpit_v4.jsx, the oracle):
  cv ∈ {Strong, Promising, Mixed, Weak, —}      cd ∈ {up, flat, down}
NB the Build Plan's ▲/▬/▼ are display glyphs; the machine value is up/flat/down.
NB cockpit `ty` = risk class (Core/Tactical/Speculative/Hedge), NOT tier·lane —
   that ④→`ty` mapping is a K1 reconciliation, not done here.

Boundary (mechanical vs judgment): the mechanical reads (A2) state config facts;
these reads INTERPRET (grade quality, detect a directional change, reconcile).
They consume the analyst-call / stance / what_to_own cards for a name + its
thesis; model_trade cards are excluded (a Meridian paper trade is not a live
signal). Echo-chamber collapse (independence groups) means the two Fundstrat
plugs on one name count as ONE corroborating voice, not two.
"""
from __future__ import annotations

import re
from datetime import date

from analyst_config import (
    CONVICTION_WINDOW_DAYS,
    CONVICTION_DIRECTION_DEADBAND,
    HIGH_CONFIDENCE_FACTOR_TAGS,
    BULLISH_WORDS,
    BEARISH_WORDS,
    BULLISH_EVENTS,
    BEARISH_EVENTS,
    CATCH_UP_ROTATION_LABELS,
    ACT_NOW_EVENTS,
    FRESH_SIGNAL_EVENTS,
    CV_RANK,
    LEAN_IN_MIN_CONVICTION,
    LEAN_IN_ROTATION_POSITIVE,
    LEAN_IN_CATCHUP_LABELS,
    LEAN_IN_ROTATION_NEGATIVE,
    LEAN_IN_ALREADY_MOVED_LABELS,
    LEAN_IN_REQUIRE_CD_UP,
    LEAN_IN_INDEPENDENCE_MIN_SOURCES,
    LEAN_IN_OPP_COST_PROXY,
    LEAN_IN_MAX_ITEMS,
    UW_OPP_FRESH_DAYS,
    UW_OPP_MAX_EVIDENCE,
    theses_by_ticker,
)
from goal_impact import (
    CAPITAL_EFFECTS,
    GOAL_CHANNELS,
    GOAL_IMPACTS,
    TIME_WINDOWS,
    annotate_actions,
)
from uw_opportunity import UW_OPP_KIND

GRADE_UNASSESSED = "—"
# kinds that count as a directional endorsement of a name (model_trade excluded)
ENDORSEMENT_KINDS = {"analyst_call", "stance", "what_to_own"}


# --------------------------------------------------------------------------- #
# shared helpers
# --------------------------------------------------------------------------- #
def _for_ticker(cards, ticker):
    return [c for c in cards if getattr(c, "subject", None) == ticker]


def _is_model(card) -> bool:
    return (getattr(card, "kind", None) == "model_trade"
            or (card.data or {}).get("is_model") is True)


def _sentiment(card) -> str:
    """bullish / bearish / neutral from the card's own `direction` word.
    Being in a 'What to Own' list is itself a bullish stance."""
    if getattr(card, "kind", None) == "what_to_own":
        return "bullish"
    d = (card.data or {}).get("direction")
    if not d:
        return "neutral"
    w = str(d).lower()
    if any(b in w for b in BULLISH_WORDS):
        return "bullish"
    if any(b in w for b in BEARISH_WORDS):
        return "bearish"
    return "neutral"


def _voice_name(card) -> str:
    data = getattr(card, "data", None) or {}
    return str(data.get("analyst") or getattr(card, "source", None)
               or getattr(card, "independence_group", None) or "source")


def _conflict_profile(cards) -> dict:
    bull = [c for c in cards if _sentiment(c) == "bullish"]
    bear = [c for c in cards if _sentiment(c) == "bearish"]
    bull_groups = {getattr(c, "independence_group", None) for c in bull}
    bear_groups = {getattr(c, "independence_group", None) for c in bear}
    cross_source = any(bg != rg for bg in bull_groups for rg in bear_groups)
    left = _voice_name(bull[0]) if bull else "bullish voice"
    right = _voice_name(bear[0]) if bear else "bearish voice"
    scope = "cross_source" if cross_source else "same_source"
    label = "cross-source split" if cross_source else "same-source split"
    return {"scope": scope, "label": label, "detail": f"{left} vs {right}"}


# =========================================================================== #
# ① Conviction (quality) — Strong / Promising / Mixed / Weak / —  (cockpit `cv`)
# =========================================================================== #
def _has_durable_anchor(thesis, endorsements) -> bool:
    """A named DURABLE anchor: an FS Top-5 pick, a Meridian structural thesis, or
    a (bullish) fundstrat endorsement on a name in the high-confidence (AI)
    sleeve. Operator-only theses are NOT durable without external corroboration."""
    tags = set((thesis or {}).get("factor_tags") or [])
    high_conf = bool(tags & HIGH_CONFIDENCE_FACTOR_TAGS)
    for c in endorsements:
        grp = getattr(c, "independence_group", None)
        direction = str((c.data or {}).get("direction") or "").lower()
        if "top_5" in direction or "top5" in direction:      # FS Top-5 anywhere
            return True
        if grp == "thematic_research":                       # Meridian structural thesis
            return True
        if high_conf and grp == "fundstrat" and _sentiment(c) == "bullish":
            return True                                      # FS endorsement on an AI name
    return False


def conviction_read(ticker, thesis, cards) -> dict:
    """① quality grade for one held name. Encoded procedure (Build Plan Part-2b):
      • no backing (no thesis, no endorsement)          → "—"  (never fabricate)
      • source conflict (a bull AND a bear voice)        → Mixed
      • durable anchor, not burned                       → Strong
      • durable anchor, burned: ≥2 streams Strong else   → Promising  (burned cap)
      • real named backing (a thesis or endorsement)     → Promising
      • thin / lottery (no thesis, only a low-trust card)→ Weak
    Echo-chamber-collapsed by independence group. Returns cockpit-aligned `cv`.
    """
    endorsements = [c for c in _for_ticker(cards, ticker)
                    if getattr(c, "kind", None) in ENDORSEMENT_KINDS and not _is_model(c)]

    has_backing = thesis is not None or len(endorsements) > 0
    if not has_backing:
        return {"ticker": ticker, "cv": GRADE_UNASSESSED, "streams": 0,
                "conflict": False, "burned": False, "durable": False,
                "reason": "no documented thesis — give me a line (unassessed)"}

    streams = len({getattr(c, "independence_group", None) for c in endorsements})
    sentiments = {_sentiment(c) for c in endorsements}
    conflict = "bullish" in sentiments and "bearish" in sentiments
    conflict_profile = _conflict_profile(endorsements) if conflict else {}
    burned = bool(thesis and thesis.get("stance") == "MONITOR")
    durable = _has_durable_anchor(thesis, endorsements)
    src = (thesis or {}).get("source")

    if conflict:
        cv = "Mixed"
        reason = ("real but offsetting — " + conflict_profile.get("label", "source split")
                  + (" (burned sleeve)" if burned else "") + "; hold, no add")
    elif durable and not burned:
        # a durable anchor resting on a SINGLE correlated source with no thesis of
        # your own caps at Promising — Strong needs your own thesis, a structural
        # thesis, or ≥2 independent streams (don't size up large on one analyst pick)
        if thesis is None and streams < 2:
            cv = "Promising"
            reason = "single external pick (no thesis on file, one source) — adopt it before sizing up"
        else:
            cv = "Strong"
            reason = f"named durable anchor ({src or 'source'}), no live conflict — can support size"
    elif durable and burned:
        cv = "Strong" if streams >= 2 else "Promising"
        reason = ("durable anchor + multi-source though burned — supports size"
                  if streams >= 2 else
                  "durable anchor but burned sleeve + single source — capped from Strong")
    elif thesis is not None:
        cv = "Promising"
        reason = f"real named backing ({src or 'source'}), not fully proven / single-source — moderate"
    else:
        max_trust = max((getattr(c, "trust_weight", 0.0) or 0.0) for c in endorsements)
        cv = "Promising" if max_trust >= 0.6 else "Weak"
        reason = ("external pick, no thesis on file — moderate, give me a line"
                  if cv == "Promising" else "thin / low-trust signal only — small or skip")

    return {"ticker": ticker, "cv": cv, "streams": streams, "conflict": conflict,
            "conflict_scope": conflict_profile.get("scope", ""),
            "conflict_label": conflict_profile.get("label", ""),
            "conflict_detail": conflict_profile.get("detail", ""),
            "burned": burned, "durable": durable, "reason": reason}


# =========================================================================== #
# ② Conviction-direction — up / flat / down (EVENT-driven)  (cockpit `cd`)
# =========================================================================== #
def _in_window(card_date_str, as_of_d, window_days) -> bool:
    if not card_date_str:
        return False
    try:
        d = date.fromisoformat(str(card_date_str)[:10])
    except (ValueError, TypeError):
        return False
    return 0 <= (as_of_d - d).days <= window_days


def _event_sentiment(card):
    """bullish / bearish / None for a card carrying an `event` marker (a NEW or
    CHANGED call set by the prose-extraction step). No marker → None (steady)."""
    ev = (card.data or {}).get("event")
    if not ev:
        return None
    e = str(ev).lower()
    if e in BULLISH_EVENTS:
        return "bullish"
    if e in BEARISH_EVENTS:
        return "bearish"
    return None


def _fmt_event(e) -> str:
    d = str(e["date"])[5:10] if e.get("date") and len(str(e["date"])) >= 10 else (e.get("date") or "")
    src = e.get("source") or "?"
    label = e.get("event") or e.get("sentiment")
    return f"{d} {src} {label}".strip()


def _build_cdnote(cd, bull, bear) -> str:
    if cd == "up":
        return " · ".join(_fmt_event(e) for e in bull)
    if cd == "down":
        return " · ".join(_fmt_event(e) for e in bear)
    parts = [_fmt_event(e) for e in (bull + bear)]
    return (" vs ".join(parts) + " — net flat") if parts else "No recent change."


def conviction_direction_read(ticker, cards, as_of,
                              window_days: int = CONVICTION_WINDOW_DAYS) -> dict:
    """② EVENT-driven direction (cockpit `cd`): up / flat / down + a dated trail
    (`cdNote`). up/down fire ONLY on a genuine NEW-or-CHANGED event inside the
    window; steady-state — even steadily strong — = flat (the calibration fix:
    the AI core is flat, not up, when nothing changed). Conflicting events net by
    (trust × recency) with a deadband. NOT moved by price/rotation.
    """
    asof_d = date.fromisoformat(str(as_of)[:10])

    events = []
    for c in _for_ticker(cards, ticker):
        if _is_model(c):
            continue
        # ── Strand 3 (Chunk 2): a FRESH UW opportunity signal is a DIRECTION event
        #    — confirmation / timing on a name you already hold a view on. Sentiment
        #    is the signal's own direction; the date is the card's timestamp; gated
        #    by the SHORTER UW_OPP_FRESH_DAYS (flow goes stale fast). It moves
        #    DIRECTION only — never conviction QUALITY (uw_opportunity is not in
        #    ENDORSEMENT_KINDS, so conviction_read ignores it). It cannot, by itself,
        #    manufacture a lean-in: lean_in_read still gates on the conviction floor,
        #    which flow does not raise. ──
        if getattr(c, "kind", None) == UW_OPP_KIND:
            d = c.data or {}
            direction = d.get("direction")
            if direction not in ("bullish", "bearish"):
                continue
            cdate = d.get("date") or getattr(c, "timestamp", None)
            if not _in_window(cdate, asof_d, UW_OPP_FRESH_DAYS):
                continue
            events.append({
                "date": cdate, "sentiment": direction,
                "event": d.get("signal_type"),       # e.g. "sweep" — reads in the cdNote
                "source": getattr(c, "source", None),
                "trust": getattr(c, "trust_weight", 0.0) or 0.0,
                "content": getattr(c, "content", None),
            })
            continue
        sent = _event_sentiment(c)
        if sent is None:
            continue
        cdate = (c.data or {}).get("date")
        if not _in_window(cdate, asof_d, window_days):
            continue
        events.append({
            "date": cdate, "sentiment": sent, "event": (c.data or {}).get("event"),
            "source": getattr(c, "source", None),
            "trust": getattr(c, "trust_weight", 0.0) or 0.0,
            "content": getattr(c, "content", None),
        })

    if not events:
        return {"ticker": ticker, "cd": "flat", "cdNote": "No recent change.", "events": []}

    def weight(e):  # trust × recency (newer = heavier; floored so old still counts a little)
        try:
            age = (asof_d - date.fromisoformat(str(e["date"])[:10])).days
        except (ValueError, TypeError):
            age = window_days
        recency = max(0.1, 1.0 - age / max(window_days, 1))
        return e["trust"] * recency

    bull = [e for e in events if e["sentiment"] == "bullish"]
    bear = [e for e in events if e["sentiment"] == "bearish"]
    bull_w = sum(weight(e) for e in bull)
    bear_w = sum(weight(e) for e in bear)

    if bull and bear:
        if abs(bull_w - bear_w) <= CONVICTION_DIRECTION_DEADBAND:
            cd = "flat"
        elif bull_w > bear_w:
            cd = "up"
        else:
            cd = "down"
    elif bull:
        cd = "up"
    else:
        cd = "down"

    return {"ticker": ticker, "cd": cd, "cdNote": _build_cdnote(cd, bull, bear),
            "events": events}


# =========================================================================== #
# ③ Net-read — the plain "what to do" headline (cockpit `nr`)
# =========================================================================== #
def _conflict_label(conviction: dict) -> str:
    return conviction.get("conflict_label") or "cross-source split"


def _conflict_detail(weighted, conviction: dict | None = None) -> str:
    """A short 'X vs Y' naming the two sides of a source split.

    Prefer the conviction profile because it preserves same-source analyst
    splits before ⑩ weighting collapses voices by independence group. Falls back
    gracefully to weighted voices when older callers don't provide that profile.
    """
    if conviction and conviction.get("conflict_detail"):
        return conviction["conflict_detail"]
    if not weighted:
        return "two sides"
    voices = weighted.get("voices") or []
    names = [v.get("source") or v.get("group") for v in voices if (v.get("source") or v.get("group"))]
    return " vs ".join(str(n) for n in names[:2]) if names else "two sides"


def net_read(ticker, thesis, conviction, rotation_label=None,
             weighted=None, parabolic=False, underweight=False) -> dict:
    """③ the plain 'what to do' headline (cockpit `nr`) — THE reconciliation.

    Reconciles ① conviction + sleeve rotation + source stance + burned/lock via
    the principle ladder (Build Plan Part-2b), FIRST MATCH WINS:
      1. no documented thesis            → "give me a line"
      2. burned sleeve (stance MONITOR)  → watch-YOUR-trigger  (🔒-override beats
                                           catch-up; surfaces the split if conflicted)
      3. parabolic                       → don't-trim-on-the-move (a trim is your
                                           de-concentration call, not weakness)
      4. source conflict                 → hold, the split is X, no add
      5. endorsed + lagging              → catch-up, favorable entry, no rush  (lagging ≠ bearish)
      6. endorsed + leading              → ride it (+ under-sizing lens on the AI sleeve)

    NB burned (stance==MONITOR) is the ③/⑦ override flag; it is DISTINCT from ④'s
    `lock` (lane==Generational). BMNR/LEU are both. Returns cockpit-aligned `nr` +
    a `basis` (which rung fired) for testability.
    """
    cv = conviction.get("cv")
    burned = bool(conviction.get("burned") or (thesis or {}).get("stance") == "MONITOR")
    conflict = bool(conviction.get("conflict"))
    src = (thesis or {}).get("source") or "source"

    if cv == GRADE_UNASSESSED:
        return {"ticker": ticker, "basis": "no_thesis",
                "nr": "Core hold but undocumented — give me a line."}

    if burned:
        split = _conflict_detail(weighted, conviction) if conflict else None
        label = _conflict_label(conviction)
        nr = ("Hold light — burned sleeve"
              + (f" + {label} ({split})" if split else "")
              + "; watch for YOUR re-entry trigger, no add on a source call.")
        return {"ticker": ticker, "basis": "burned_override", "nr": nr}

    if parabolic:
        return {"ticker": ticker, "basis": "parabolic",
                "nr": "Hold — parabolic; do NOT trim on the move, only on a named break (your rule)."}

    if conflict:
        split = _conflict_detail(weighted, conviction)
        label = _conflict_label(conviction)
        return {"ticker": ticker, "basis": "conflict",
                "nr": f"Hold — {label} ({split}); no add until it resolves."}

    if rotation_label in CATCH_UP_ROTATION_LABELS:
        return {"ticker": ticker, "basis": "catch_up",
                "nr": f"Catch-up — {src}-endorsed laggard; favorable entry, no rush."}

    tags = set((thesis or {}).get("factor_tags") or [])
    lens = (" You're underweight to conviction here — the gap is the flag."
            if underweight and (tags & HIGH_CONFIDENCE_FACTOR_TAGS) else "")
    return {"ticker": ticker, "basis": "ride_it",
            "nr": f"Core hold — {src}-endorsed, leading; ride it.{lens}"}


# =========================================================================== #
# ⑦ Fresh-signal detection — "is this a BUY now?" + urgency  (cockpit `fresh_signals`)
# =========================================================================== #
def _signal_urgency(event, buyable_now, is_reentry) -> str:
    """⏳ act = the entry trigger fired (a breakout, a re-entry-zone touch, or
    explicitly buyable now); 👁 watch = endorsed but the entry isn't confirmed."""
    if is_reentry or buyable_now or (event and str(event).lower() in ACT_NOW_EVENTS):
        return "act"
    return "watch"


def fresh_signal_read(direction_reads, theses, reentry_touches=None,
                      high_conf_reentry=None) -> dict:
    """⑦ the Actions strip (cockpit `fresh_signals` + the per-name `fresh` flag).

    Candidates = bullish ② events (a name whose conviction-direction is `up` on a
    NEW event) + re-entry-zone touches. Classify ⏳ act vs 👁 watch via the entry
    trigger. **Burned-sleeve names (stance MONITOR) are EXCLUDED** unless a high-
    confidence re-entry fired (source-convergence ≥3 / strong catalyst / regime-
    turn) — that's the 🔒-override that keeps crypto/nuclear/minerals off the
    add-now surface. Build Plan Part-2b. (Held vs watchlist agnostic — a newly-
    named non-held pick like FN surfaces here too.)
    """
    reentry_touches = reentry_touches or []
    high_conf_reentry = set(high_conf_reentry or [])
    by_ticker = theses_by_ticker(theses)

    def _burned(tk):
        th = by_ticker.get(tk)
        return bool(th and th.get("stance") == "MONITOR")

    signals, seen = [], set()

    # (a) bullish ② events that are discrete NAME-LEVEL buy triggers
    for dr in direction_reads:
        tk = dr.get("ticker")
        if not tk or tk in seen or dr.get("cd") != "up" or not dr.get("events"):
            continue
        # a stance/sector shift drives cd=up + the net-read catch-up on the row,
        # but only a discrete buy trigger earns an Actions-strip signal
        ev = next((e for e in dr["events"]
                   if str(e.get("event")).lower() in FRESH_SIGNAL_EVENTS), None)
        if ev is None:
            continue
        if _burned(tk) and tk not in high_conf_reentry:
            continue  # 🔒 burned-sleeve exclusion (reached only by a real trigger)
        signals.append({
            "ticker": tk,
            "urgency": _signal_urgency(ev.get("event"), ev.get("buyable_now"), False),
            "what": ev.get("event") or "bullish event",
            "why": ev.get("content") or dr.get("cdNote"),
            "when": ev.get("date"),
            "detail": dr.get("cdNote"),
        })
        seen.add(tk)

    # (b) re-entry-zone touches → ⏳ act candidates
    for t in reentry_touches:
        tk = t.get("ticker") if isinstance(t, dict) else t
        if not tk or tk in seen:
            continue
        if _burned(tk) and tk not in high_conf_reentry:
            continue
        signals.append({
            "ticker": tk, "urgency": "act", "what": "re-entry zone touch",
            "why": (t.get("note") if isinstance(t, dict) else None) or "price entered your re-entry zone",
            "when": (t.get("date") if isinstance(t, dict) else None),
            "detail": "re-entry zone",
        })
        seen.add(tk)

    return {
        "fresh_signals": signals,
        "fresh_tickers": sorted(seen),
        "act_count": sum(1 for s in signals if s["urgency"] == "act"),
        "watch_count": sum(1 for s in signals if s["urgency"] == "watch"),
    }


# =========================================================================== #
# ⑦b Actions read — the prioritized "what to do today" surface (cockpit `actions`)
#     ADDITIVE: derived from already-assembled reads (⑦ fresh_signals + ⑧ hero
#     needs_you); never mutates them. Forward-compat: `synthesis_actions`
#     defaults empty — the seam the Daily-Synthesis brain fills later, with no
#     change to this shape. The engine returns the FULL priority-ranked list;
#     the cockpit panel shows the top 5 + a "+N more" count (capping is a
#     DISPLAY concern, so the feed stays complete).
# =========================================================================== #

# kind -> display priority (lower = shown first). A real ranking, not a rename.
_ACTION_PRIORITY = {
    "red_gate": 0,         # a RED pre-trade flag — a hard stop you must see
    "sell_fast": 0,        # an avoid/sell-fast source call on a tracked name
    "event_risk": 1,       # fast exogenous risk: review exposure before acting
    "buy_now": 1,          # a discrete entry trigger fired (⏳ act)
    "synthesis": 1,        # v1 placeholder: curated synthesis action (tune when wired)
    "top_prospect": 1,     # an external ACT_NOW candidate that must not stay buried
    "research_act_now": 1,  # time-sensitive research must not stay buried
    "reentry_zone": 2,     # a re-entry-zone touch (⏳ act, non-burned)
    "catalyst_imminent": 2,  # a near-term dated event on a HELD name (review-before)
    "decision_aging": 2,   # an open, aging, un-acted opportunity (E2) — decide, don't let it run
    "monitor_reentry": 3,  # a burned-sleeve re-entry candidate (watch YOUR trigger)
    "lean_in": 3,          # a promoted lean-in — looks good, size it yourself (no trigger yet)
    "macro_alert": 4,      # a firing macro alert (regime-level)
    "watch_entry": 5,      # endorsed, entry not confirmed (👁 watch)
    "stale_critical": 6,   # a stale critical source (a data-trust gap)
}
_ACTION_CONFIDENCE = {
    "red_gate": "High", "buy_now": "High", "reentry_zone": "High",
    "sell_fast": "High", "top_prospect": "High", "research_act_now": "High",
    "event_risk": "Moderate",
    "monitor_reentry": "Moderate", "macro_alert": "Moderate", "lean_in": "Moderate",
    "watch_entry": "Moderate", "stale_critical": "Low",
    "decision_aging": "Moderate",
}
_CONFIDENCE_RANK = {"High": 0, "Moderate": 1, "Low": 2}
_ACTION_STATE_BY_KIND = {
    "red_gate": "ACT_NOW",
    "sell_fast": "ACT_NOW",
    "event_risk": "ACT_NOW",
    "buy_now": "ACT_NOW",
    "top_prospect": "ACT_NOW",
    "research_act_now": "ACT_NOW",
    "reentry_zone": "ACT_NOW",
    "catalyst_imminent": "ACT_NOW",
    "decision_aging": "ACT_NOW",
    "synthesis": "ACT_NOW",
    "monitor_reentry": "MONITOR",
    "lean_in": "WATCH",
    "macro_alert": "WATCH",
    "watch_entry": "WATCH",
    "stale_critical": "MONITOR",
    "research_review": "RESEARCH",
}

_SYNTH_TICKER_LEAD = re.compile(r"^\s*([A-Z]{1,6}(?:\.[A-Z]{1,4})?)\s*[\u2014\u2013:\- ]")
_SYNTH_ACTION_WORDS = (
    "act", "buy", "add", "start", "size", "sell", "trim", "exit", "reduce",
    "review", "decide", "gate", "time-sensitive", "urgent",
)


def _synthesis_ticker(text):
    if not isinstance(text, str):
        return None
    m = _SYNTH_TICKER_LEAD.match(text)
    return m.group(1) if m else None


def _synthesis_is_actionish(text):
    low = str(text or "").lower()
    return any(w in low for w in _SYNTH_ACTION_WORDS)


def _synthesis_confidence(row, text):
    raw = row.get("confidence") if isinstance(row, dict) else None
    if raw in _CONFIDENCE_RANK:
        return raw
    urgency = str((row or {}).get("urgency") or (row or {}).get("action_state") or "").upper() if isinstance(row, dict) else ""
    if urgency == "ACT_NOW":
        return "High"
    if urgency in ("WATCH", "MONITOR", "RESEARCH"):
        return "Low"
    priority = str((row or {}).get("priority") or (row or {}).get("pr") or "").lower() if isinstance(row, dict) else ""
    low = str(text or "").lower()
    if priority == "high" or any(w in low for w in ("urgent", "time-sensitive", "act now", "sell", "trim", "exit")):
        return "High"
    if priority in ("low", "monitor"):
        return "Low"
    return "Moderate"


def _first_present(row, keys):
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _as_string_list(value):
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v not in (None, "")]
    return []


def _synthesis_default_action(item):
    raw = str(item.get("default_action") or item.get("capital_effect") or "").lower()
    if raw in ("sell", "trim", "reduce", "exit"):
        return "SELL"
    if raw in ("hedge", "rotate", "review"):
        return "REVIEW"
    return item.get("default_action") or "ADD"


def synthesis_actions_read(synthesis, *, max_items=5) -> list[dict]:
    """Extract durable action rows from the Daily Synthesis read.

    Prefer explicit structured `actions`/`action_items` rows. As a fallback,
    promote only ticker-led `hanging` lines that contain action language. This is
    intentionally conservative: prose stays in the synthesis panel unless it can
    be made into a concrete ticker/action candidate.
    """
    if not isinstance(synthesis, dict):
        return []
    rows = []
    source = synthesis.get("source") or "Daily Synthesis"

    explicit = synthesis.get("actions") or synthesis.get("action_items") or synthesis.get("recommendations") or []
    if isinstance(explicit, dict):
        explicit = [explicit]
    for item in explicit if isinstance(explicit, list) else []:
        if isinstance(item, str):
            text = item
            ticker = _synthesis_ticker(text)
            if not ticker or not _synthesis_is_actionish(text):
                continue
            rows.append({
                "ticker": ticker,
                "what": text,
                "confidence": _synthesis_confidence({}, text),
                "your_move": f"Decide on {ticker}: {text}",
                "why": f"{source}: {text}",
            })
        elif isinstance(item, dict):
            text = _first_present(item, ("what", "action", "recommendation", "text", "summary", "title")) or ""
            ticker = _first_present(item, ("ticker", "symbol")) or _synthesis_ticker(text)
            if not ticker and not _first_present(item, ("what", "action", "recommendation")):
                continue
            your_move = _first_present(item, ("your_move", "move", "operator_move", "next_step"))
            if not your_move:
                your_move = f"Review synthesis action for {ticker}." if ticker else "Review synthesis action."
            row = {
                "ticker": ticker,
                "what": text or "Synthesis action",
                "confidence": _synthesis_confidence(item, text),
                "your_move": your_move,
                "why": _first_present(item, ("why", "reason", "evidence")) or f"{source}: {text}",
                "gate": item.get("gate"),
                "default_action": _synthesis_default_action(item),
            }
            if item.get("time_window") in TIME_WINDOWS:
                row["time_window"] = item["time_window"]
            if item.get("capital_effect") in CAPITAL_EFFECTS:
                row["capital_effect"] = item["capital_effect"]
            if item.get("goal_impact") in GOAL_IMPACTS:
                row["goal_impact"] = item["goal_impact"]
            if isinstance(item.get("goal_score"), int) and 0 <= item["goal_score"] <= 100:
                row["goal_score"] = item["goal_score"]
            for src_key in ("sizing", "action_label", "why_it_moves_goal"):
                if isinstance(item.get(src_key), str) and item.get(src_key).strip():
                    row[src_key] = item[src_key]
            channels = _as_string_list(item.get("goal_channels") or item.get("goal_channel"))
            channels = [c for c in channels if c in GOAL_CHANNELS]
            if channels:
                row["goal_channels"] = channels
            missing = _as_string_list(item.get("missing_evidence") or item.get("missing") or item.get("needs"))
            if missing:
                row["missing_evidence"] = missing
            rows.append(row)

    for text in synthesis.get("hanging") or []:
        ticker = _synthesis_ticker(text)
        if not ticker or not _synthesis_is_actionish(text):
            continue
        rows.append({
            "ticker": ticker,
            "what": f"Synthesis follow-up: {text}",
            "confidence": _synthesis_confidence({}, text),
            "your_move": f"Decide on {ticker}: {text}",
            "why": f"{source} hanging item: {text}",
        })

    out = []
    seen = set()
    for row in rows:
        key = (row.get("ticker"), row.get("what"))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= max_items:
            break
    return out


def _gate_hook(ticker, by_ticker, default_action="ADD") -> dict:
    """The Option-A gate ROUTING HOOK — a provisional, advisory badge only.
    The authoritative GREEN/AMBER/RED comes from pretrade_gate.evaluate(...) run
    IN-SESSION when the operator drills + names the $ size (machinery fires on
    act, not in the static render). A T1 ADD always runs Deepwork regardless of
    size; for everything else the gate requirement depends on the size — so the
    badge never claims a verdict on a size that was never chosen."""
    tier = (by_ticker.get(ticker) or {}).get("tier")
    preview = "🔒 T1 — runs Deepwork" if tier == "T1" else "🟡 size → gate"
    return {"needs_gate": True, "preview": preview,
            "ticker": ticker, "default_action": default_action}


def _prospect_confidence(row) -> str:
    if row.get("urgency") == "ACT_NOW" and row.get("corroboration") == "Vetted-Buy":
        return "High"
    if row.get("urgency") == "ACT_NOW":
        return "Moderate"
    return "Low"


def catalyst_needs_you(catalysts, held_tickers, theses, *, horizon_days=7):
    """⑧ enrichment — surface near-term CATALYSTS on HELD names as needs_you
    items (reason "catalyst_imminent"). This is the EVENT-DRIVEN act-now path:
    it makes a time-sensitive hold visible on the surface REGARDLESS of daily
    price movement (the gap where a flat-price day -> empty actions hid AVGO's
    2-days-out print on 6/1).

    Scope (v1): HELD names only, with a catalyst 0..horizon_days out. A
    non-held / research-complete candidate is the research_ready path (deferred).
    A MONITOR-stance hold (burned sleeve) surfaces as a WATCH/RISK flag, never an
    ADD nudge (the conviction-posture rule) — tagged stance="MONITOR" so the
    action row renders watch-only.

    Returns pre-formed needs_you item dicts (reason/detail/days_out/label/stance/
    note), deterministically sorted by (days_out, ticker) for a stable feed.
    """
    by_tk = theses_by_ticker(theses)
    held = set(held_tickers or [])
    items = []
    for c in (catalysts or []):
        if not isinstance(c, dict):
            continue
        tk = c.get("ticker")
        days = c.get("days_out")
        if not tk or tk not in held:
            continue
        if not isinstance(days, int) or days < 0 or days > horizon_days:
            continue
        stance = (by_tk.get(tk) or {}).get("stance")
        label = c.get("label") or "a catalyst"
        items.append({
            "reason": "catalyst_imminent",
            "detail": tk,
            "days_out": days,
            "label": label,
            "stance": stance,
            "note": f"{label} in ~{days}d"
                    + (" on a MONITOR-stance hold" if stance == "MONITOR" else ""),
        })
    items.sort(key=lambda it: (it["days_out"], it["detail"]))
    return items


def actions_read(fresh_signals, needs_you_items, theses,
                 *, synthesis_actions=None, lean_in_items=None,
                 prospect_items=None, event_risk_actions=None) -> dict:
    """⑦b the prioritized Actions surface (cockpit `actions`).

    Pool = ⑦ fresh_signals (act/watch) + ⑧ hero needs_you items (red_gate /
    macro_alert / monitor_reentry / stale_critical). `fresh_act` needs_you items
    are SKIPPED — they only point back to a fresh_signal already in the pool
    (dedup, not a second action). High-priority Top Prospects may also promote
    here so an ACT_NOW candidate cannot remain visible only in a secondary lane.
    Each row leads with a CONFIDENCE read (High/Moderate/Low), NOT a tier letter,
    and carries the gate hook the in-session drill uses. Returns the full
    priority-ranked list + counts.
    """
    synthesis_actions = synthesis_actions or []
    event_risk_actions = event_risk_actions or []
    by_ticker = theses_by_ticker(theses)
    rows = []

    # (a) fresh_signals -> buy_now / reentry_zone / watch_entry
    for s in (fresh_signals or []):
        tk = s.get("ticker")
        urg = s.get("urgency")
        is_reentry = (s.get("detail") == "re-entry zone"
                      or s.get("what") == "re-entry zone touch")
        if urg == "act":
            kind = "reentry_zone" if is_reentry else "buy_now"
        else:
            kind = "watch_entry"
        if kind == "buy_now":
            what = "Buy trigger fired"
            your_move = f"Size {tk} and run the pre-trade gate before you buy."
            gate = _gate_hook(tk, by_ticker)
        elif kind == "reentry_zone":
            what = "Re-entry zone touched"
            your_move = f"{tk} entered your re-entry zone — confirm the setup, size, run the gate."
            gate = _gate_hook(tk, by_ticker)
        else:  # watch_entry — nothing to gate until it becomes a buy
            what = "Endorsed — watch for entry"
            your_move = f"{tk} is endorsed but the entry isn't confirmed — set an alert, no buy yet."
            gate = None
        rows.append({
            "kind": kind, "ticker": tk, "what": what,
            "confidence": _ACTION_CONFIDENCE[kind], "your_move": your_move,
            "gate": gate, "source": "fresh_signal",
            "why": s.get("why") or s.get("detail") or "",
        })

    # (b) hero needs_you items.  fresh_act is dedup'd against (a).
    for it in (needs_you_items or []):
        reason = it.get("reason")
        detail = it.get("detail")
        note = it.get("note") or ""
        if reason == "fresh_act":
            continue  # already represented by its fresh_signal (dedup)
        if reason == "red_gate":
            tk = detail if isinstance(detail, str) else None
            rows.append({
                "kind": "red_gate", "ticker": tk, "what": "RED pre-trade flag",
                "confidence": "High",
                "your_move": (f"Clear the RED flag on {tk} before any action."
                              if tk else "Clear the RED pre-trade flag before any action."),
                "gate": {"needs_gate": True, "preview": "🔴 RED — clear first",
                         "ticker": tk, "default_action": "REVIEW"},
                "source": "needs_you:red_gate",
                "why": note or "a red pre-trade flag is active",
            })
        elif reason == "macro_alert":
            rows.append({
                "kind": "macro_alert", "ticker": None,
                "what": "Macro alert" + (f": {detail}" if detail else ""),
                "confidence": "Moderate",
                "your_move": "Re-check the macro read before any Tier-A/B action today.",
                "gate": None, "source": "needs_you:macro_alert",
                "why": note or "a macro alert is firing",
            })
        elif reason == "monitor_reentry":
            tk = detail if isinstance(detail, str) else None
            rows.append({
                "kind": "monitor_reentry", "ticker": tk,
                "what": "Re-entry candidate (burned sleeve)",
                "confidence": "Moderate",
                "your_move": (f"{tk} is a burned sleeve — confirm YOUR re-entry trigger "
                              "(≥3-source convergence / named catalyst / regime turn) before "
                              "any add; prefer defined-risk options."),
                "gate": _gate_hook(tk, by_ticker) if tk else None,
                "source": "needs_you:monitor_reentry",
                "why": note or "a burned-sleeve re-entry candidate surfaced",
            })
        elif reason == "stale_critical":
            rows.append({
                "kind": "stale_critical", "ticker": None,
                "what": "Stale critical source" + (f": {detail}" if detail else ""),
                "confidence": "Low",
                "your_move": (f"Refresh {detail} — a critical source is stale; trust is "
                              "degraded until you do." if detail else
                              "Refresh the stale critical source; trust is degraded until you do."),
                "gate": None, "source": "needs_you:stale_critical",
                "why": note or "a critical source is past its freshness window",
            })
        elif reason == "catalyst_imminent":
            tk = detail if isinstance(detail, str) else None
            days = it.get("days_out")
            label = it.get("label") or "a catalyst"
            cd = f"~{days}d" if isinstance(days, int) else "soon"
            if it.get("stance") == "MONITOR":
                # burned sleeve: a catalyst is a WATCH/RISK flag, NEVER an add nudge
                rows.append({
                    "kind": "catalyst_imminent", "ticker": tk,
                    "what": f"Catalyst on a burned-sleeve hold ({cd})",
                    "confidence": "Low",
                    "your_move": (f"{tk}: {label} in {cd} on a MONITOR-stance hold — "
                                  "watch / risk-check only; no add absent YOUR re-entry "
                                  "trigger (\u22653-source convergence / named catalyst / regime turn)."),
                    "gate": None, "source": "needs_you:catalyst_imminent",
                    "why": note or f"{label} is within the act-now horizon",
                    "days_to_catalyst": days if isinstance(days, int) else None,
                })
            else:
                # a dated event on a HELD name: a DECISION PROMPT, not a buy trigger
                rows.append({
                    "kind": "catalyst_imminent", "ticker": tk,
                    "what": f"Pre-catalyst review ({cd})",
                    "confidence": "Moderate",
                    "your_move": (f"{tk}: {label} in {cd} — review the held position before it: "
                                  "confirm thesis, size, and whether to hedge or hold. "
                                  "A decision prompt, not a buy trigger."),
                    "gate": (_gate_hook(tk, by_ticker, default_action="REVIEW")
                             if tk else None),
                    "source": "needs_you:catalyst_imminent",
                    "why": note or f"{label} is within the act-now horizon",
                    "days_to_catalyst": days if isinstance(days, int) else None,
                })
        # unknown reasons are ignored — never fabricate an action

    # (b2) PROMOTED lean-ins — the strongest opportunity reads (lean == "lean_in")
    #      brought front-and-center onto the Actions strip (the opportunity mirror
    #      of the act-now triggers). Only "lean_in" is promoted — `build` /
    #      `still_lagging` / `cooling` stay in the lean-in panel, never the act
    #      strip. Deduped against names already represented above (a confirmed
    #      buy_now / watch already says it), so a name appears once. SURFACE only:
    #      a gate hook for sizing, never an executed buy.
    promoted_seen = {r["ticker"] for r in rows if r.get("ticker")}
    for li in (lean_in_items or []):
        if li.get("lean") != "lean_in":
            continue
        tk = li.get("ticker")
        if not tk or tk in promoted_seen:
            continue
        cvq = li.get("conviction")
        conf = "High" if cvq == "Strong" else ("Moderate" if cvq == "Promising" else "Low")
        rot = li.get("rotation")
        rows.append({
            "kind": "lean_in", "ticker": tk,
            "what": "Lean-in — looks good",
            "confidence": conf,
            "your_move": (f"{tk} looks good ({cvq}{', ' + rot if rot else ''}) — size it "
                          "yourself and run the pre-trade gate. No auto-buy."),
            "gate": _gate_hook(tk, by_ticker),
            "source": "lean_in",
            "why": li.get("headline") or "",
        })
        promoted_seen.add(tk)

    # (b3) PROMOTED Top Prospects — ACT_NOW candidates and sell-fast warnings
    #      become durable actions, not just a lower candidate lane. HOT/BUILDING
    #      names remain in the Top Prospects surface until they cross ACT_NOW.
    prospects = prospect_items or {}
    prospect_seen = {r["ticker"] for r in rows if r.get("ticker")}
    for sf in (prospects.get("sell_fast") or []):
        if not isinstance(sf, dict):
            continue
        tk = sf.get("ticker")
        if not tk or tk in prospect_seen:
            continue
        rows.append({
            "kind": "sell_fast", "ticker": tk,
            "what": "Sell-fast review",
            "confidence": "High",
            "your_move": (f"{tk}: source says avoid / sell-fast — check whether you hold it, "
                          "then decide trim/exit or log why you are overriding it."),
            "gate": _gate_hook(tk, by_ticker, default_action="REVIEW"),
            "source": "top_prospects:sell_fast",
            "why": sf.get("summary") or sf.get("provenance") or "sell-fast prospect warning",
        })
        prospect_seen.add(tk)
    for p in (prospects.get("hot") or []):
        if not isinstance(p, dict) or p.get("urgency") != "ACT_NOW":
            continue
        tk = p.get("ticker")
        if not tk or tk in prospect_seen:
            continue
        conf = _prospect_confidence(p)
        rows.append({
            "kind": "top_prospect", "ticker": tk,
            "what": "Top prospect ACT_NOW",
            "confidence": conf,
            "your_move": (f"{tk}: ACT_NOW prospect — vet the thesis now; if it still clears, "
                          "size it and run the pre-trade gate. Not a buy by itself."),
            "gate": _gate_hook(tk, by_ticker, default_action="REVIEW"),
            "source": "top_prospects",
            "why": p.get("summary") or p.get("provenance") or "top prospect urgency is ACT_NOW",
        })
        prospect_seen.add(tk)

    # (c) forward-compat seam: Daily-Synthesis actions (empty until that brain
    #     lands). Accept light dicts; normalize into the row shape. v1 slotting.
    for sa in synthesis_actions:
        if not isinstance(sa, dict):
            continue
        conf = sa.get("confidence")
        tk = sa.get("ticker")
        gate = sa.get("gate")
        if gate is None and tk and _synthesis_is_actionish(
            " ".join(str(sa.get(k) or "") for k in ("what", "your_move"))
        ):
            default_action = sa.get("default_action") or (
                "SELL" if any(w in str(sa.get("what") or "").lower() for w in ("sell", "trim", "exit", "reduce"))
                else "ADD"
            )
            gate = _gate_hook(tk, by_ticker, default_action=default_action)
        row = {
            "kind": "synthesis", "ticker": tk,
            "what": sa.get("what") or "Synthesis action",
            "confidence": conf if conf in _CONFIDENCE_RANK else "Moderate",
            "your_move": sa.get("your_move") or "Review this synthesis action.",
            "gate": gate,
            "source": "daily_synthesis", "why": sa.get("why") or "",
        }
        for optional in (
            "time_window", "capital_effect", "sizing", "goal_channels",
            "goal_impact", "goal_score", "action_label", "why_it_moves_goal",
            "missing_evidence",
        ):
            if sa.get(optional) not in (None, "", []):
                row[optional] = sa[optional]
        rows.append(row)

    # (c2) supplied Event Risk rows: high/critical exogenous shocks become a
    # review action so oil/war/rates shocks cannot stay buried in prose. These
    # are exposure-review prompts only; no buy/sell order is implied.
    for er in event_risk_actions:
        if not isinstance(er, dict):
            continue
        row = {
            "kind": "event_risk", "ticker": er.get("ticker"),
            "what": er.get("what") or "Event risk review",
            "confidence": er.get("confidence") if er.get("confidence") in _CONFIDENCE_RANK else "Moderate",
            "your_move": er.get("your_move") or "Review exposure before acting.",
            "gate": er.get("gate"),
            "source": er.get("source") or "event_risk",
            "why": er.get("why") or "",
        }
        for optional in (
            "time_window", "capital_effect", "sizing", "goal_channels",
            "goal_impact", "goal_score", "action_label", "why_it_moves_goal",
            "missing_evidence",
        ):
            if er.get(optional) not in (None, "", []):
                row[optional] = er[optional]
        rows.append(row)

    # (d) priority sort — kind tier, then confidence, then stable insertion order
    for idx, r in enumerate(rows):
        r["_order"] = idx
    rows.sort(key=lambda r: (_ACTION_PRIORITY.get(r["kind"], 9),
                             _CONFIDENCE_RANK.get(r["confidence"], 9),
                             r["_order"]))

    actions = []
    for rank, r in enumerate(rows, start=1):
        row = {                   # canonical field order (stable golden output)
            "rank": rank, "kind": r["kind"], "ticker": r["ticker"],
            "action_state": _ACTION_STATE_BY_KIND.get(r["kind"], "WATCH"),
            "what": r["what"], "confidence": r["confidence"],
            "your_move": r["your_move"], "gate": r["gate"],
            "source": r["source"], "why": r["why"],
        }
        for optional in (
            "time_window", "capital_effect", "sizing", "goal_channels",
            "goal_impact", "goal_score", "action_label", "why_it_moves_goal",
            "missing_evidence",
        ):
            if r.get(optional) not in (None, "", []):
                row[optional] = r[optional]
        # additive, only on rows carrying a countdown -> pre-catalyst feeds stay
        # byte-identical (no golden drift); the renderer reads days_to_catalyst.
        if r.get("days_to_catalyst") is not None:
            row["days_to_catalyst"] = r["days_to_catalyst"]
        actions.append(row)

    actions = annotate_actions(actions)
    return {
        "actions": actions,
        "total_candidates": len(actions),
        "act_like": sum(1 for a in actions if a["kind"] in ("buy_now", "reentry_zone")),
    }


def apply_decision_aging(actions, aging_records, by_ticker):
    """E2 — fold the open-opportunity aging store into the Actions strip.

    Two moves:
      (a) ENRICH any existing action row whose ticker is an open aging idea with
          age_days / first_flagged / move_since (additive — like days_to_catalyst
          it never perturbs rows without it; the renderer draws the 🕒 chip).
      (b) EMIT a standalone `decision_aging` row for an aging idea NOT already on
          the strip, so a flagged-but-ignored name never silently drops off.

    Any aging row (enriched or standalone) is sort-boosted to priority <= 2 so a
    name that's been ignored + is moving surfaces LOUD — without changing its kind
    label. MONITOR names are already excluded upstream (open_opportunity_aging).

    `aging_records`: the open_opportunity_aging() output. EMPTY -> the actions list
    is returned UNCHANGED (no copy, no re-rank) so feeds without the store stay
    byte-identical (golden-safe).
    """
    if not aging_records:
        return actions
    aging_by_tk = {r["ticker"]: r for r in aging_records if r.get("ticker")}
    rows = [dict(a) for a in (actions or [])]
    present = {a.get("ticker") for a in rows if a.get("ticker")}

    # (a) ENRICH existing rows
    for a in rows:
        rec = aging_by_tk.get(a.get("ticker"))
        if not rec:
            continue
        a.setdefault("age_days", rec.get("age_days"))
        a.setdefault("first_flagged", rec.get("first_flagged"))
        if not a.get("move_since"):
            a["move_since"] = rec.get("move_since", "")

    # (b) EMIT standalone decision_aging rows for aging names not already present
    for tk, rec in aging_by_tk.items():
        if tk in present:
            continue
        age = rec.get("age_days")
        ms = rec.get("move_since") or ""
        ff = rec.get("first_flagged")
        conf = "High" if isinstance(age, int) and age >= 5 else "Moderate"
        span = f"({ms})" if ms else (f"(open {age}d)" if age is not None else "")
        rows.append({
            "rank": 10_000 + len(rows),   # sort after same-priority existing; renumbered below
            "kind": "decision_aging", "ticker": tk,
            "action_state": _ACTION_STATE_BY_KIND["decision_aging"],
            "what": f"Flagged {ff} — still un-acted",
            "confidence": conf,
            "your_move": (f"You flagged {tk} on {ff} and still haven't acted {span} — "
                          "decide now: size it and run the gate, or log why you're "
                          "passing. Don't let it keep running away."),
            "gate": _gate_hook(tk, by_ticker),
            "source": "decision_aging",
            "why": f"open {age} trading days since {ff}" + (f"; {ms}" if ms else ""),
            "age_days": age, "first_flagged": ff, "move_since": ms,
        })

    def _eff_pri(a):
        base = _ACTION_PRIORITY.get(a["kind"], 9)
        return min(base, 2) if a.get("age_days") is not None else base  # aging → loud

    rows.sort(key=lambda a: (_eff_pri(a),
                             _CONFIDENCE_RANK.get(a.get("confidence"), 9),
                             a.get("rank", 9_999)))
    for i, a in enumerate(rows, start=1):
        a["rank"] = i
        a.setdefault("action_state", _ACTION_STATE_BY_KIND.get(a.get("kind"), "WATCH"))
    return annotate_actions(rows)


def promote_research_act_now_actions(actions, research_actions):
    """Copy urgent research rows into Today's Actions without removing the lane."""
    urgent = [
        r for r in (research_actions or [])
        if isinstance(r, dict)
        and (r.get("kind") == "research_act_now" or r.get("action_state") == "ACT_NOW")
        and r.get("ticker")
    ]
    if not urgent:
        return actions

    rows = [dict(a) for a in (actions or [])]
    present = {a.get("ticker") for a in rows if a.get("ticker")}
    for r in urgent:
        tk = r.get("ticker")
        if tk in present:
            continue
        row = dict(r)
        row["kind"] = "research_act_now"
        row["action_state"] = _ACTION_STATE_BY_KIND["research_act_now"]
        row["source"] = "research_queue:act_now"
        row["what"] = row.get("what") or "Research ACT_NOW"
        row["your_move"] = row.get("your_move") or (
            f"{tk}: finish the research now, then size/decide through the gate."
        )
        row["confidence"] = (
            row.get("confidence") if row.get("confidence") in _CONFIDENCE_RANK else "High"
        )
        rows.append(row)
        present.add(tk)

    rows.sort(key=lambda a: (_ACTION_PRIORITY.get(a.get("kind"), 9),
                             _CONFIDENCE_RANK.get(a.get("confidence"), 9),
                             a.get("rank", 9_999)))
    for i, a in enumerate(rows, start=1):
        a["rank"] = i
        a.setdefault("action_state", _ACTION_STATE_BY_KIND.get(a.get("kind"), "WATCH"))
    return annotate_actions(rows)


# =========================================================================== #
# ⑦c Research-actions read — the SEPARATE "From Research" surface (cockpit
#     `research_actions`). Ticker-specific Research Queue items surfaced as
#     their OWN candidate-action category — NEVER blended into ⑦b `actions` or
#     the catalyst list (operator decision 2026-06-02). Built routine-side from
#     the external `research` read; the live session ranks + gates on drill (a
#     research_action >= $25K -> pretrade_gate fires in-session). Rows reuse the
#     action-row shape (kind "research_review") so the renderer's actionRow
#     mapper is reused unchanged.
#
#     Filter (v1): a structured or parsed ticker AND (priority high/med OR a
#     structured near-term date within horizon). Ticker-specific rows should
#     carry an explicit `ticker`/`symbol`; legacy rows still fall back to the
#     leading "TICKER - ..." token. Non-ticker process/governance items are NOT
#     surfaced here (they stay in the Research panel).
#
#     Dedup (catalyst-precedence): an item whose ticker is already in the action
#     OR catalyst lane is DROPPED -- so a name surfaces exactly once and
#     research_actions YIELDS to the sharper dated driver. The caller passes that
#     union as `taken_tickers`.
# =========================================================================== #

import re as _re

_RESEARCH_PR_CONFIDENCE = {"high": "High", "med": "Moderate", "medium": "Moderate",
                           "low": "Low"}
_RESEARCH_PR_RANK = {"high": 0, "med": 1, "medium": 1, "low": 2}
_RESEARCH_INCLUDE_PR = frozenset({"high", "med", "medium"})
_RESEARCH_ACT_NOW_VALUES = frozenset({
    "act_now", "act now", "act-now", "urgent", "time-sensitive", "time_sensitive",
    "today", "now",
})
# leading all-caps ticker (1-6, optional .SUFFIX) immediately followed by a dash/colon
_TICKER_LEAD = _re.compile(r"^\s*([A-Z]{1,6}(?:\.[A-Z]{1,4})?)\s*[\u2014\u2013:\-]")


def _parse_research_ticker(text):
    """Pull the leading 'TICKER - ...' symbol from a Research-Queue item's text.
    Returns the ticker string, or None for a non-ticker (process/governance) item."""
    if not isinstance(text, str):
        return None
    m = _TICKER_LEAD.match(text)
    return m.group(1) if m else None


def _research_ticker_from_item(item, text):
    for key in ("ticker", "symbol"):
        raw = item.get(key)
        if raw in (None, ""):
            continue
        ticker = str(raw).strip().upper()
        if _re.fullmatch(r"[A-Z]{1,6}(?:\.[A-Z]{1,4})?", ticker):
            return ticker
    return _parse_research_ticker(text)


def _research_is_act_now(item, dated_ok: bool) -> bool:
    if dated_ok:
        return True
    for key in ("action_state", "urgency", "action", "recommendation", "status"):
        raw = item.get(key)
        if raw is None:
            continue
        norm = str(raw).strip().lower().replace("-", "_")
        if norm in _RESEARCH_ACT_NOW_VALUES:
            return True
    return False


def research_actions_read(research, theses, taken_tickers=None,
                          *, horizon_days=7, include_priorities=_RESEARCH_INCLUDE_PR):
    """⑦c the SEPARATE "From Research" candidate-action surface.

    `research` is the external Research-Queue read: a dict {pending:[...],
    done:[...]} (or a bare list, treated as `pending`). Each pending item is
    {ticker: "TICKER", r: "<summary>", pr: "high"|"med"|"low", ...}; legacy
    ticker-led `r` values are still accepted. A structured `days_out` (int) is
    honored if present.

    Returns {research_actions:[...], total_candidates:n}. Each row is the
    canonical action-row shape with kind "research_review", so the renderer's
    actionRow mapper renders it unchanged. Deterministic order: priority, then
    confidence, then first-seen.
    """
    taken = set(taken_tickers or [])
    by_ticker = theses_by_ticker(theses)
    if isinstance(research, dict):
        pending = research.get("pending") or []
    elif isinstance(research, list):
        pending = research
    else:
        pending = []

    rows = []
    for idx, it in enumerate(pending):
        if not isinstance(it, dict):
            continue
        text = it.get("r") or it.get("text") or ""
        ticker = _research_ticker_from_item(it, text)
        if not ticker:
            continue  # v1: ticker-specific research only (process items stay in the panel)
        pr = str(it.get("pr") or it.get("priority") or "").lower()
        days = it.get("days_out")
        dated_ok = isinstance(days, int) and 0 <= days <= horizon_days  # dormant today
        if not (pr in include_priorities or dated_ok):
            continue
        if ticker in taken:
            continue  # dedup -- the action/catalyst lane already carries it (catalyst-precedence)
        stance = (by_ticker.get(ticker) or {}).get("stance")
        confidence = _RESEARCH_PR_CONFIDENCE.get(pr, "Moderate")
        cd = f" (~{days}d)" if dated_ok else ""
        act_now = stance != "MONITOR" and _research_is_act_now(it, dated_ok)
        if stance == "MONITOR":
            # burned sleeve: review/watch only -- never an add nudge
            your_move = (f"{ticker}: burned-sleeve research -- review / risk-check only; "
                         "no add absent YOUR re-entry trigger (\u22653-source convergence / "
                         "named catalyst / regime turn).")
            gate = None
            confidence = "Low"
        else:
            your_move = (f"{ticker}: review the Off-Hours dossier{cd} -- confirm the thesis, "
                         "then size / decide (run the pre-trade gate if you act). "
                         "A research item, not a fired trigger.")
            gate = _gate_hook(ticker, by_ticker, default_action="REVIEW")
        kind = "research_act_now" if act_now else "research_review"
        what = "Research ACT_NOW -- review" + cd if act_now else "Research dossier -- review" + cd
        rows.append({
            "kind": kind, "ticker": ticker,
            "what": what,
            "confidence": confidence, "your_move": your_move,
            "gate": gate, "source": "research_queue", "why": text,
            "_pr_rank": _RESEARCH_PR_RANK.get(pr, 1), "_order": idx,
        })

    rows.sort(key=lambda r: (r["_pr_rank"], _CONFIDENCE_RANK.get(r["confidence"], 9),
                             r["_order"]))

    research_actions = []
    for rank, r in enumerate(rows, start=1):
        research_actions.append({
            "rank": rank, "kind": r["kind"], "ticker": r["ticker"],
            "action_state": _ACTION_STATE_BY_KIND.get(r["kind"], "RESEARCH"),
            "what": r["what"], "confidence": r["confidence"],
            "your_move": r["your_move"], "gate": r["gate"],
            "source": r["source"], "why": r["why"],
        })

    research_actions = annotate_actions(research_actions)
    return {"research_actions": research_actions,
            "total_candidates": len(research_actions)}
# --------------------------------------------------------------------------- #
# ⑩ LEAN-IN read — the opportunity mirror of risk surfacing (Opportunity-Engine
# pivot, Chunk A). Reconciles ① conviction QUALITY (the permissive size ceiling)
# + ② conviction DIRECTION + sleeve rotation into a SYMMETRIC lean read, off the
# SAME computed structures the other reads use. Surfaces a lean with its
# evidence, an opportunity-cost read, the sizing ceiling (risk class), what would
# RAISE conviction, and honesty caveats. NEVER decides / auto-buys (action=NONE).
# All thresholds are dials (analyst_config LEAN_IN_*), overridable here for
# tuning/tests. Deterministic: same inputs -> same lane.
# --------------------------------------------------------------------------- #
_LEAN_PRIORITY = {"lean_in": 0, "build": 1, "still_lagging": 2, "cooling": 3}


def _cv_rank(cv) -> int:
    return CV_RANK.get(cv, 0)


def _lean_classify(cv_rank, cd, label, owned, underweight, parabolic, act, watch, *,
                   floor_rank, positive_labels, catchup_labels,
                   negative_labels, moved_labels, require_cd_up):
    """The SYMMETRIC lean word for one name, or None (quiet). Negatives checked
    FIRST (anti-avoidance: willing to print the bad read). Positives gate at/above
    the conviction floor. `act`/`watch` are the ⑦ fresh-signal urgencies, kept
    CONSISTENT with the Actions strip: a confirmed act trigger -> lean_in; an
    endorsement whose entry isn't confirmed (watch) -> build. Otherwise a working
    tape + room to add -> lean_in; an endorsed laggard that hasn't turned ->
    still_lagging; rising-but-unconfirmed or under-conviction -> build. Parabolic
    demotes lean_in -> build (don't chase the move)."""
    # --- negatives first (allowed even below the positive floor) ---
    if cd == "down" or label in negative_labels:
        return "cooling"
    if cv_rank < floor_rank:
        return None                                       # no conviction to lean on

    has_room = (not owned) or underweight
    positive_tape = label in positive_labels
    rising = (cd == "up")

    # a confirmed entry trigger (⏳ act) -> lean_in (consistent with its buy_now action)
    if act:
        return "build" if parabolic else "lean_in"
    # a working tape with room to add -> lean_in
    tape_ok = (positive_tape and rising) if require_cd_up else positive_tape
    if tape_ok and has_room:
        return "build" if parabolic else "lean_in"
    # endorsed but entry NOT confirmed (👁 watch) -> build (watch for the trigger)
    if watch:
        return "build"
    # endorsed laggard that hasn't turned -> the honest "still lagging"
    if label in catchup_labels and not rising:
        return "still_lagging"
    # rising conviction (non-trigger event), or under-conviction on a Strong name -> build
    if rising or (underweight and cv_rank >= CV_RANK["Strong"]):
        return "build"
    return None                                           # sized + flat + leading core -> quiet


def _lean_opp_cost(ticker, sleeve, proxy) -> str:
    if not isinstance(sleeve, dict) or not sleeve:
        return "No sleeve rotation on file — opportunity cost vs the book not measured."
    if sleeve.get("subject") == proxy:
        return f"This IS the {proxy} opportunity-cost benchmark."
    rel = sleeve.get("rel_3m_vs_smh")
    if rel is None:
        return f"Opportunity cost vs {proxy} not measured."
    if rel >= 0:
        return f"Gaining on {proxy} ({rel:+.0%}/3M vs the capital benchmark) — leaning in keeps pace."
    return (f"Still lagging {proxy} ({rel:+.0%}/3M) — leaning in trades the benchmark for this name; "
            "size only as the relative trend turns.")


def _lean_evidence(conv, dr, label) -> list:
    ev = []
    if conv.get("reason"):
        ev.append(f"Conviction: {conv['reason']}")
    note = dr.get("cdNote")
    if note and note != "No recent change.":
        ev.append(f"Direction: {note}")
    if label:
        ev.append(f"Rotation: {label}")
    return ev


def _lean_headline(lean, tk, cv, label, owned, underweight) -> str:
    own = "you own it" if owned else "not owned"
    if lean == "lean_in":
        gap = ("under your conviction — room to add" if (owned and underweight)
               else ("a place to start" if not owned else "room toward the ceiling"))
        return f"{tk}: {cv} and the tape's with it ({label or 'no sleeve'}) — {gap}."
    if lean == "build":
        if not owned:
            return (f"{tk}: {cv}, endorsed — watch for the entry trigger before starting "
                    f"({label or 'no sleeve'}).")
        if label in ("LAGGING", "TURNING UP"):
            return (f"{tk}: {cv}, conviction up but the sleeve's still lagging — "
                    f"research deeper / hold, watch for the rotation to turn.")
        return (f"{tk}: {cv}, conviction building, tape not yet confirmed — "
                f"hold, watch for the turn.")
    if lean == "still_lagging":
        return (f"{tk}: {cv} and endorsed, but still lagging — favorable entry only "
                f"once the rotation turns ({own}).")
    if lean == "cooling":
        return (f"{tk}: the case is cooling ({label or 'direction down'}) — "
                f"watch / reassess, don't add ({own}).")
    return f"{tk}: {cv}."


def _lean_next_evidence(lean, label) -> str:
    if lean == "lean_in":
        return ("Size toward the ceiling on conviction; if via options, a defined-risk "
                "structure. Raises it further: a 2nd independent source or a held rotation turn.")
    if lean == "build":
        return "Graduates it: the sleeve rotation turning up and holding, or a fresh independent catalyst."
    if lean == "still_lagging":
        return "Clears it: the rotation turning up (lagging -> turning up), confirming the catch-up."
    if lean == "cooling":
        return "Re-opens it: the direction turning back up on a fresh event, or the rotation re-leading."
    return ""


def _lean_ceiling(risk_class) -> str:
    if not risk_class:
        return "Tactical (default) — size as a catalyst/cycle position with an exit."
    guide = {
        "Core": "durable — can be a large position; conviction sizes toward the upper end.",
        "Tactical": "catalyst/cycle — medium, with a defined exit.",
        "Speculative": "high-risk — small, capped.",
        "Probe": "high-risk — small, capped.",
        "Hedge": "protection — sized by portfolio role, not its own upside.",
    }.get(risk_class, "size within the risk class.")
    return f"{risk_class} — {guide}"


def _uw_opp_evidence(cards, tk, as_of, *, fresh_days=UW_OPP_FRESH_DAYS,
                     max_lines=UW_OPP_MAX_EVIDENCE):
    """The FRESH UW opportunity signals on a name, as lean-in evidence lines
    (newest first), plus whether any fresh signal is bullish (makes the 'already
    moved' caveat flow-aware). Reads the SAME uw_opportunity cards
    conviction_direction_read consumes, gated by the same freshness window — so the
    evidence shown matches the signal that moved the direction."""
    asof_d = date.fromisoformat(str(as_of)[:10])
    sigs = []
    for c in _for_ticker(cards, tk):
        if getattr(c, "kind", None) != UW_OPP_KIND:
            continue
        d = c.data or {}
        cdate = d.get("date") or getattr(c, "timestamp", None)
        if not _in_window(cdate, asof_d, fresh_days):
            continue
        try:
            age = (asof_d - date.fromisoformat(str(cdate)[:10])).days
        except (ValueError, TypeError):
            age = 999
        sigs.append((age, d.get("direction"), getattr(c, "content", "") or ""))
    sigs.sort(key=lambda s: s[0])
    has_bull = any(direction == "bullish" for _, direction, _ in sigs)
    lines = []
    for age, direction, content in sigs[:max_lines]:
        arrow = "▲" if direction == "bullish" else "▼" if direction == "bearish" else "•"
        agestr = f" ({age}d)" if age != 999 else ""
        lines.append(f"UW {arrow} {content}{agestr}")
    return lines, has_bull


def lean_in_read(direction_reads, theses, cards, as_of, *,
                 rotation_by_name=None, risk_by_tk=None,
                 held=None, underweight=None, parabolic=None,
                 fresh_act=None, fresh_watch=None,
                 high_conf_reentry=None,
                 min_conviction=LEAN_IN_MIN_CONVICTION,
                 positive_labels=LEAN_IN_ROTATION_POSITIVE,
                 catchup_labels=LEAN_IN_CATCHUP_LABELS,
                 negative_labels=LEAN_IN_ROTATION_NEGATIVE,
                 moved_labels=LEAN_IN_ALREADY_MOVED_LABELS,
                 require_cd_up=LEAN_IN_REQUIRE_CD_UP,
                 independence_min=LEAN_IN_INDEPENDENCE_MIN_SOURCES,
                 opp_cost_proxy=LEAN_IN_OPP_COST_PROXY,
                 max_items=LEAN_IN_MAX_ITEMS) -> dict:
    """⑩ the LEAN-IN lane (cockpit `lean_in`) — the opportunity mirror of risk
    surfacing.

    HARD invariants (by construction):
      • action == "NONE" on EVERY item — a SURFACE, never an order.
      • burned sleeves (stance MONITOR) surface ONLY when a high-confidence
        re-entry has cleared (tk in high_conf_reentry); otherwise skipped — the
        conviction-GATED MONITOR reframe. Never lean_in on a bare source call.
      • SYMMETRIC — willing to print `cooling` / `still_lagging`; quiet by
        default (a sized, flat, leading core name returns no item).
    """
    rotation_by_name = rotation_by_name or {}
    risk_by_tk = risk_by_tk or {}
    held = set(held or [])
    underweight = set(underweight or [])
    parabolic = set(parabolic or [])
    fresh_act = set(fresh_act or [])
    fresh_watch = set(fresh_watch or [])
    high_conf_reentry = set(high_conf_reentry or [])
    by_tk = theses_by_ticker(theses)
    floor_rank = CV_RANK.get(min_conviction, CV_RANK["Promising"])

    items = []
    for dr in direction_reads:
        tk = dr.get("ticker")
        if not tk:
            continue
        thesis = by_tk.get(tk)
        burned = bool(thesis and thesis.get("stance") == "MONITOR")
        if burned and tk not in high_conf_reentry:
            continue                         # 🔒 conviction-gate -> the monitor path owns it

        conv = conviction_read(tk, thesis, cards)
        cv = conv.get("cv")
        streams = conv.get("streams", 0)
        cd = dr.get("cd", "flat")

        sleeve = rotation_by_name.get(tk) or {}
        label = sleeve.get("label", "") if isinstance(sleeve, dict) else (sleeve or "")
        owned = tk in held
        is_uw = tk in underweight
        is_para = tk in parabolic
        act = tk in fresh_act
        watch = tk in fresh_watch

        lean = _lean_classify(_cv_rank(cv), cd, label, owned, is_uw, is_para, act, watch,
                              floor_rank=floor_rank, positive_labels=positive_labels,
                              catchup_labels=catchup_labels, negative_labels=negative_labels,
                              moved_labels=moved_labels, require_cd_up=require_cd_up)
        if lean is None:
            continue

        uw_lines, uw_fresh_bull = _uw_opp_evidence(cards, tk, as_of)
        caveats = []
        if streams and streams < independence_min and lean in ("lean_in", "build"):
            caveats.append(f"clustered: {streams} independent source"
                           f"{'s' if streams != 1 else ''} — not independent confirmation")
        if (label in moved_labels or is_para) and lean in ("lean_in", "build"):
            why = " (parabolic)" if is_para else " (sleeve leading)"
            if uw_fresh_bull:
                why += " — flow is confirming a move already underway, not front-running it"
            caveats.append("already moved: entry less asymmetric" + why)
        if burned:
            caveats.append("burned sleeve: re-entry only on a strong signal; "
                           "prefer defined-risk options")

        items.append({
            "ticker": tk,
            "owned": owned,
            "stance_gate": "monitor" if burned else "open",
            "conviction": cv,
            "cd": cd,
            "rotation": label,
            "lean": lean,
            "headline": _lean_headline(lean, tk, cv, label, owned, is_uw),
            "evidence": _lean_evidence(conv, dr, label) + uw_lines,
            "next_evidence": _lean_next_evidence(lean, label),
            "opportunity_cost": _lean_opp_cost(tk, sleeve, opp_cost_proxy),
            "ceiling": _lean_ceiling(risk_by_tk.get(tk)),
            "caveats": caveats,
            "freshness": f"as-of {str(as_of)[:10]}",
            "action": "NONE",
        })

    items.sort(key=lambda it: (_LEAN_PRIORITY.get(it["lean"], 9),
                               -_cv_rank(it["conviction"]), it["ticker"]))
    if isinstance(max_items, int) and max_items >= 0:
        items = items[:max_items]
    return {
        "lean_in": items,
        "lean_count": len(items),
        "positive_count": sum(1 for i in items if i["lean"] in ("lean_in", "build")),
        "negative_count": sum(1 for i in items if i["lean"] in ("cooling", "still_lagging")),
    }
