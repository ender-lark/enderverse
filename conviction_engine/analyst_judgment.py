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
    theses_by_ticker,
)

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
      • cross-source conflict (a bull AND a bear voice)  → Mixed
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
    burned = bool(thesis and thesis.get("stance") == "MONITOR")
    durable = _has_durable_anchor(thesis, endorsements)
    src = (thesis or {}).get("source")

    if conflict:
        cv = "Mixed"
        reason = ("real but offsetting — cross-source split"
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
def _conflict_detail(weighted) -> str:
    """A short 'X vs Y' naming the two sides of a cross-source split, from the
    ⑩ weighted voices. Falls back gracefully when voices aren't supplied."""
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
      4. cross-source conflict           → hold, the split is X, no add
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
        split = _conflict_detail(weighted) if conflict else None
        nr = ("Hold light — burned sleeve"
              + (f" + cross-source split ({split})" if split else "")
              + "; watch for YOUR re-entry trigger, no add on a source call.")
        return {"ticker": ticker, "basis": "burned_override", "nr": nr}

    if parabolic:
        return {"ticker": ticker, "basis": "parabolic",
                "nr": "Hold — parabolic; do NOT trim on the move, only on a named break (your rule)."}

    if conflict:
        split = _conflict_detail(weighted)
        return {"ticker": ticker, "basis": "conflict",
                "nr": f"Hold — cross-source split ({split}); no add until it resolves."}

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
    "buy_now": 1,          # a discrete entry trigger fired (⏳ act)
    "synthesis": 1,        # v1 placeholder: curated synthesis action (tune when wired)
    "reentry_zone": 2,     # a re-entry-zone touch (⏳ act, non-burned)
    "monitor_reentry": 3,  # a burned-sleeve re-entry candidate (watch YOUR trigger)
    "macro_alert": 4,      # a firing macro alert (regime-level)
    "watch_entry": 5,      # endorsed, entry not confirmed (👁 watch)
    "stale_critical": 6,   # a stale critical source (a data-trust gap)
}
_ACTION_CONFIDENCE = {
    "red_gate": "High", "buy_now": "High", "reentry_zone": "High",
    "monitor_reentry": "Moderate", "macro_alert": "Moderate",
    "watch_entry": "Moderate", "stale_critical": "Low",
}
_CONFIDENCE_RANK = {"High": 0, "Moderate": 1, "Low": 2}


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


def actions_read(fresh_signals, needs_you_items, theses,
                 *, synthesis_actions=None) -> dict:
    """⑦b the prioritized Actions surface (cockpit `actions`).

    Pool = ⑦ fresh_signals (act/watch) + ⑧ hero needs_you items (red_gate /
    macro_alert / monitor_reentry / stale_critical). `fresh_act` needs_you items
    are SKIPPED — they only point back to a fresh_signal already in the pool
    (dedup, not a second action). Each row leads with a CONFIDENCE read
    (High/Moderate/Low), NOT a tier letter, and carries the gate hook the
    in-session drill uses. Returns the full priority-ranked list + counts.
    """
    synthesis_actions = synthesis_actions or []
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
        # unknown reasons are ignored — never fabricate an action

    # (c) forward-compat seam: Daily-Synthesis actions (empty until that brain
    #     lands). Accept light dicts; normalize into the row shape. v1 slotting.
    for sa in synthesis_actions:
        if not isinstance(sa, dict):
            continue
        conf = sa.get("confidence")
        rows.append({
            "kind": "synthesis", "ticker": sa.get("ticker"),
            "what": sa.get("what") or "Synthesis action",
            "confidence": conf if conf in _CONFIDENCE_RANK else "Moderate",
            "your_move": sa.get("your_move") or "Review this synthesis action.",
            "gate": sa.get("gate"),  # pass through if supplied
            "source": "daily_synthesis", "why": sa.get("why") or "",
        })

    # (d) priority sort — kind tier, then confidence, then stable insertion order
    for idx, r in enumerate(rows):
        r["_order"] = idx
    rows.sort(key=lambda r: (_ACTION_PRIORITY.get(r["kind"], 9),
                             _CONFIDENCE_RANK.get(r["confidence"], 9),
                             r["_order"]))

    actions = []
    for rank, r in enumerate(rows, start=1):
        actions.append({          # canonical field order (stable golden output)
            "rank": rank, "kind": r["kind"], "ticker": r["ticker"],
            "what": r["what"], "confidence": r["confidence"],
            "your_move": r["your_move"], "gate": r["gate"],
            "source": r["source"], "why": r["why"],
        })

    return {
        "actions": actions,
        "total_candidates": len(actions),
        "act_like": sum(1 for a in actions if a["kind"] in ("buy_now", "reentry_zone")),
    }
