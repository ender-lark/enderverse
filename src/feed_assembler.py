"""Conviction Engine · Layer 3 (Analyst) — feed assembler (the OUTPUT step).

Runs the Analyst reads over a CollectedSnapshot bundle and arranges their
outputs into ONE Contract-C CockpitFeed (the boundary Layer 4 consumes).
Deterministic: same inputs -> same feed. Used by the golden freeze (A5), the
golden-master test (A6), and the live runtime (A7).

A read never grades or fabricates; this step only ARRANGES read outputs into the
cockpit shape. The only transforms here are mechanical and named:
  • tier -> risk-class (ty)                         TIER_RISK
  • tier-band floor -> under-sized flag             TIER_FLOOR
  • ticker -> rotation-proxy sleeve                 NAME_SLEEVE
Catalysts / questions are cockpit-curated (not data-derived), so the assembler
emits them empty — they are layered in at Layer 4, not invented here.
"""
from __future__ import annotations

from types import SimpleNamespace

from analyst import (rotation_read, macro_read, staleness_read,
                     type_read, hero_needs_you_read, weight_read)
from analyst_judgment import (conviction_read, conviction_direction_read,
                              net_read, fresh_signal_read, actions_read,
                              catalyst_needs_you, lean_in_read, research_actions_read,
                              apply_decision_aging, synthesis_actions_read,
                              target_drift_actions_read,
                              promote_research_act_now_actions)
from analyst_config import theses_by_ticker
from feedback_summary import build_feedback_summary
from lane_status import build_lane_status
from event_risk import event_risk_actions_read, normalize_event_risks
from uw_opportunity import uw_opportunity_cards, uw_opportunity_surface
from prospect_surface import build_prospects_lane
from open_opportunities import open_opportunity_aging

# ── name -> rotation-proxy sleeve (the leaderboard subject that stands in for a
#    single name's relative strength). v1 glue, tunable. A name with no proxy
#    falls to "_other" and simply carries no rotation label. ──
NAME_SLEEVE = {
    # AI / Semiconductors (SMH proxy) — incl. mega-cap AI + semis ETFs + photonics
    "SMH": "SMH", "MAGS": "SMH", "NVDA": "SMH", "MU": "SMH", "AVGO": "SMH",
    "ANET": "SMH", "IVES": "SMH", "GOOGL": "SMH", "MSFT": "SMH", "AMZN": "SMH",
    "ASML": "SMH", "NBIS": "SMH", "SOXX": "SMH", "FTXL": "SMH", "LITE": "SMH",
    "POET": "SMH",
    # Software (IGV proxy)
    "IGV": "IGV", "ORCL": "IGV", "RDDT": "IGV", "PLTR": "IGV", "CIBR": "IGV",
    # Quality core (GRNY proxy)
    "GRNY": "GRNY", "GRNJ": "GRNY", "COST": "GRNY", "RPG": "GRNY",
    # Financials (XLF proxy)
    "XLF": "XLF", "GS": "XLF", "JPM": "XLF", "SOFI": "XLF",
    # Nuclear (URA proxy)
    "LEU": "URA", "UUUU": "URA", "CCJ": "URA", "BWXT": "URA", "UURAF": "URA",
    # Critical minerals (REMX proxy)
    "MP": "REMX", "LYSDY": "REMX", "LIT": "REMX",
    # Crypto (IBIT proxy)
    "BMNR": "IBIT", "IBIT": "IBIT", "ETHA": "IBIT", "MSTR": "IBIT",
    "COIN": "IBIT", "HYPE": "IBIT",
    # Electrification (VOLT proxy)
    "VOLT": "VOLT", "GEV": "VOLT", "PWR": "VOLT", "STRL": "VOLT", "IESC": "VOLT",
    "BE": "VOLT", "NXT": "VOLT", "FIX": "VOLT", "DRIV": "VOLT", "PBW": "VOLT",
    # Gold / Hedge (GDX proxy)
    "GDX": "GDX", "SIL": "GDX", "WPM": "GDX", "NUE": "GDX",
}
# sleeve -> display category (cat) for the holdings groups
SLEEVE_CAT = {
    "SMH": "AI / Semiconductors", "IGV": "Software", "GRNY": "Quality core",
    "XLF": "Financials", "URA": "Nuclear", "REMX": "Critical minerals",
    "IBIT": "Crypto", "VOLT": "Electrification", "GDX": "Gold / Hedge",
    "_other": "Other holdings",
}
# tier -> cockpit risk-class (ty). A real transform, not a rename.
TIER_RISK = {"T1": "Core", "T2": "Core", "T3": "Tactical", "T4": "Probe"}
# tier -> position-size floor (% of book). Below floor on a high-confidence name
# trips the under-sizing lens inside ③ — the canonical "right but too small".
TIER_FLOOR = {"T1": 8.0, "T2": 4.0, "T3": 1.5, "T4": 0.0}

ENDORSEMENT_KINDS = ("analyst_call", "what_to_own", "stance")


def _ns(items):
    return [SimpleNamespace(**it) for it in items]


def assemble_feed(bundle: dict, parabolic=None, generated_at=None,
                  heartbeat=None, synthesis=None, research=None, radar=None,
                  catalysts=None, lean_in=None, uw_opportunity=None,
                  signal_log=None,
                  event_risk=None,
                  open_opportunities=None, opp_prices=None,
                  top_prospects=None, source_calls=None,
                  inbox_call_dates=None, log_call_dates=None,
                  target_drift=None,
                  aging_threshold_days=3) -> dict:
    """bundle = {as_of, snapshot:<CollectedSnapshot>, theses:[...with stance]}.
    Returns a Contract-C CockpitFeed (passes validate_cockpit_feed).

    heartbeat / synthesis / research / catalysts are EXTERNAL reads (Notion —
    layer run-times, the latest Daily Synthesis, the live Research Queue, and the
    Catalyst Calendar near-term events), supplied by the cockpit-build step like
    the Fundstrat/macro plugs. They are threaded through ADDITIVELY (default to
    empty), never derived from the snapshot here.

    radar is the one additive block DERIVED here (block ⑨): the endorsed-but-not-
    owned watch surface, read off the fundstrat_daily analyst-call cards. It
    defaults to the engine-derived list (empty when no qualifying call exists);
    pass an explicit list to override that derivation, same additive seam as the
    three reads above."""
    as_of = bundle["as_of"]
    snap = bundle["snapshot"]
    theses = bundle["theses"]
    parabolic = set(parabolic or [])
    # ── Strand 3 (Chunk 1): fold the daily UW opportunity-signals cache into the
    #    card stream as kind="uw_opportunity" cards (the conviction trail). ADDITIVE
    #    and default-None — inert today (no `event` marker → the conviction reads
    #    ignore them); Chunk 2 is the hook that turns a fresh bullish signal into an
    #    up-event + a lean-in evidence row. Tolerant: a bad cache yields no cards. ──
    _items = snap["items"]
    uw_cards = []
    if uw_opportunity:
        uw_cards = uw_opportunity_cards(uw_opportunity)
        _items = list(_items) + uw_cards
    cards = _ns(_items)
    by_tk = theses_by_ticker(theses)

    # ── sleeve-level mechanical reads ──
    rot = rotation_read(cards)
    rot_label = {s["subject"]: s["label"] for s in rot["sleeves"]}
    macro = macro_read(cards)
    stale = staleness_read(snap["staleness"], as_of)
    position_cards = [c for c in cards if getattr(c, "kind", None) == "position"]
    type_r = type_read(position_cards, theses)
    type_by_tk = {x["ticker"]: x for x in (type_r["tracked"] + type_r["untracked"])}

    # ── held names (dedup, first-seen order) ──
    held, seen = [], set()
    for c in position_cards:
        if c.subject and c.subject not in seen:
            held.append(c)
            seen.add(c.subject)

    # ── direction reads for held names + any name carrying endorsement cards
    #    (watchlist picks like FN feed the Actions strip) ──
    endorsement_subjects = {c.subject for c in cards
                            if getattr(c, "kind", None) in ENDORSEMENT_KINDS and c.subject}
    dir_reads = {tk: conviction_direction_read(tk, cards, as_of)
                 for tk in sorted(seen | endorsement_subjects)}

    fresh = fresh_signal_read(list(dir_reads.values()), theses)
    fresh_set = set(fresh["fresh_tickers"])
    wt = weight_read([c for c in cards
                      if getattr(c, "kind", None) in ENDORSEMENT_KINDS])

    # ── per-name pos rows, grouped by sleeve ──
    pos_by_sleeve: dict = {}
    underweight_set: set = set()   # held names under their tier floor (lean-in input)
    for c in held:
        tk = c.subject
        th = by_tk.get(tk)
        conv = conviction_read(tk, th, cards)
        cd = dir_reads[tk]
        d = c.data or {}
        pct = d.get("pct")
        tier = (th or {}).get("tier")
        underweight = pct is not None and pct < TIER_FLOOR.get(tier, 0.0)
        if underweight:
            underweight_set.add(tk)
        nr = net_read(tk, th, conv,
                      rotation_label=rot_label.get(NAME_SLEEVE.get(tk)),
                      weighted=wt.get(tk), parabolic=(tk in parabolic),
                      underweight=underweight)
        t4 = type_by_tk.get(tk, {})
        pos = {
            "t": tk, "n": d.get("name", tk), "pct": pct, "st": "Owned",
            "cv": conv["cv"], "ty": TIER_RISK.get(tier, "Tactical"),
            "own": d.get("owner", ""), "lock": t4.get("lock", ""),
            "fresh": tk in fresh_set, "cd": cd["cd"], "cdNote": cd["cdNote"],
            "nr": nr["nr"], "dr": [[t4.get("why", "—")]], "be": t4.get("break", "—"),
        }
        pos_by_sleeve.setdefault(NAME_SLEEVE.get(tk, "_other"), []).append(pos)

    holdings = [{"cat": SLEEVE_CAT.get(s, "Other holdings"),
                 "rot": {"w": rot_label.get(s, "")}, "pos": ps}
                for s, ps in pos_by_sleeve.items()]

    # ── ⑧ enrichment: near-term CATALYSTS on held names (the event-driven
    #    act-now path — surfaces a time-sensitive hold regardless of price
    #    movement). MONITOR holds surface as watch/risk, never an add. `seen`
    #    is the held-ticker set built above. ──
    cat_items = catalyst_needs_you(catalysts, seen, theses)

    hero = hero_needs_you_read(rot, macro, stale, type_r,
                               fresh_signals=fresh["fresh_signals"],
                               catalyst_imminent=cat_items)

    # ── ⑩ LEAN-IN lane (computed BEFORE Actions so the strongest lean-ins can be
    #    promoted onto the act strip). ADDITIVE — the opportunity mirror of risk
    #    surfacing; reconciles conviction quality + direction + sleeve rotation off
    #    the SAME computed structures (dir_reads / rotation / type / stance). Never
    #    decides/auto-buys. Override via `lean_in=` (same seam as radar). The
    #    burned-sleeve (MONITOR) re-entry gate stays closed here (no high-conf
    #    re-entry set passed by default), so the lane never lifts the gate itself. ──
    if lean_in is None:
        rot_by_subject = {s["subject"]: s for s in rot["sleeves"]}
        rot_by_name = {tk: rot_by_subject.get(NAME_SLEEVE.get(tk)) for tk in dir_reads}
        risk_by_tk = {tk: TIER_RISK.get((by_tk.get(tk) or {}).get("tier"), "Tactical")
                      for tk in dir_reads}
        fresh_act = {s["ticker"] for s in fresh["fresh_signals"] if s.get("urgency") == "act"}
        fresh_watch = {s["ticker"] for s in fresh["fresh_signals"] if s.get("urgency") == "watch"}
        lean_block = lean_in_read(list(dir_reads.values()), theses, cards, as_of,
                                  rotation_by_name=rot_by_name, risk_by_tk=risk_by_tk,
                                  held=seen, underweight=underweight_set, parabolic=parabolic,
                                  fresh_act=fresh_act, fresh_watch=fresh_watch)["lean_in"]
    else:
        lean_block = lean_in

    # ── Top Prospects lane (item 5): shape the raw prospects cache before Actions
    #    so ACT_NOW/sell-fast candidates can promote to the top strip while the
    #    full candidate lane remains available below. ──
    prospects = build_prospects_lane(top_prospects) if isinstance(top_prospects, dict) and top_prospects else {}

    # ── ⑦b prioritized Actions surface (ADDITIVE — ⑦ fresh_signals + ⑧ hero
    #    needs_you + PROMOTED ⑩ lean_ins + ACT_NOW prospects, the "what to do
    #    today" strip on top of the book). Only lean=="lean_in" items promote,
    #    deduped against fresh-signal actions; synthesis actions are extracted
    #    conservatively from structured rows or ticker-led actionable lines. ──
    synthesis_action_items = synthesis_actions_read(synthesis)
    event_risk_block = normalize_event_risks(event_risk) if event_risk is not None else None
    event_risk_action_items = event_risk_actions_read(event_risk_block)
    target_drift_action_items = target_drift_actions_read(target_drift, theses)
    actions = actions_read(fresh["fresh_signals"], hero["needs_you"]["items"], theses,
                           lean_in_items=lean_block,
                           prospect_items=prospects,
                           synthesis_actions=synthesis_action_items,
                           event_risk_actions=event_risk_action_items,
                           target_drift_actions=target_drift_action_items)["actions"]

    # ── ⑦b-aging (E2): age the open-opportunity store into the Actions strip.
    #    ENRICH any action row that's an open aging idea with age / first-flagged /
    #    move-since (renderer draws the 🕒 chip), and EMIT a standalone
    #    `decision_aging` row for an aging idea that didn't re-surface today — so a
    #    flagged-but-ignored name never silently falls off. MONITOR names are
    #    excluded inside open_opportunity_aging (guardrail). No store → no-op. ──
    if open_opportunities is not None:
        _monitor = {tk for tk, th in by_tk.items() if (th or {}).get("stance") == "MONITOR"}
        _aging = open_opportunity_aging(open_opportunities, opp_prices or {}, as_of,
                                        threshold_days=aging_threshold_days,
                                        monitor_tickers=_monitor)
        actions = apply_decision_aging(actions, _aging, by_tk)

    # ── ⑦c research_actions: ticker-specific Research-Queue items as their OWN
    #    candidate-action category (SEPARATE from `actions`; never blended).
    #    Deduped against the action + catalyst lanes by ticker (catalyst-
    #    precedence) so a name surfaces exactly once. ──
    _taken = {a["ticker"] for a in actions if a.get("ticker")}
    _taken |= {c.get("ticker") for c in (catalysts or [])
               if isinstance(c, dict) and c.get("ticker")}
    research_actions = research_actions_read(research or {}, theses, _taken)["research_actions"]
    actions = promote_research_act_now_actions(actions, research_actions)

    # ── ⑨ Radar — endorsed, not owned. The fundstrat_daily analyst-call cards
    #    name external picks; keep ONLY the ones absent from the book whose thesis
    #    (if any) isn't a parked MONITOR sleeve — i.e. live endorsements you don't
    #    hold yet. Source-scoped to the daily plug so the row carries its real
    #    author + structured levels (bible/meridian endorsements are a different
    #    shape and surface elsewhere). Dedup first-seen; ADDITIVE — empty is fine.
    #    A caller may pass `radar` to override this derivation (see docstring). ──
    derived_radar: list = []
    if radar is None:
        radar_seen: set = set()
        for c in cards:
            if (getattr(c, "kind", None) != "analyst_call"
                    or getattr(c, "source", None) != "fundstrat_daily"):
                continue
            tk = c.subject
            if not tk or tk in seen or tk in radar_seen:
                continue
            if (by_tk.get(tk) or {}).get("stance") == "MONITOR":
                continue
            d = c.data or {}
            derived_radar.append({
                "ticker": tk,
                "author": d.get("author", ""),
                "direction": d.get("direction"),
                "entry": d.get("entry"), "stop": d.get("stop"),
                "target": d.get("target"), "window": d.get("window"),
                "date": getattr(c, "timestamp", ""),
                "quote": d.get("verbatim") or getattr(c, "content", ""),
            })
            radar_seen.add(tk)

    # ── B1 (Strand-3 surfacing): read-only "Bullish flow" watch lane from the UW
    #    opportunity cache (grouped by ticker; NOT conviction — the gated Chunk-2
    #    hook is separate). ──
    _monitor_all = {tk for tk, th in by_tk.items() if (th or {}).get("stance") == "MONITOR"}
    bullish_flow = uw_opportunity_surface(uw_opportunity, monitor_tickers=_monitor_all) if uw_opportunity else {}
    lane_status = build_lane_status(
        snap, stale,
        catalysts=catalysts,
        research=research,
        synthesis=synthesis,
        uw_opportunity=(uw_cards if uw_opportunity is not None else None),
        signal_log=signal_log,
        event_risk=event_risk_block,
        top_prospects=top_prospects,
        target_drift=target_drift,
    )
    feedback = build_feedback_summary(
        source_calls=source_calls,
        open_opportunities=open_opportunities,
        prices=opp_prices,
        as_of=as_of,
        core_tickers={
            (t.get("ticker") or "").upper()
            for t in theses
            if (t.get("stance") or "").upper() != "MONITOR"
            and (t.get("tier") or "").upper() in ("T1", "T2")
        },
        inbox_call_dates=inbox_call_dates,
        log_call_dates=log_call_dates,
    )
    feed = {
        "generated_at": generated_at or f"{as_of}T16:00:00",
        "staleness": stale,
        "lane_status": lane_status,
        "hero": hero,
        "actions": actions,
        "fresh_signals": fresh["fresh_signals"],
        "signal_log": signal_log or [],
        "event_risk": event_risk_block or [],
        "holdings": holdings,
        "rotation": rot["sleeves"],
        "macro": macro,
        "catalysts": catalysts or [],
        "questions": [],
        "research": research or {},
        "research_actions": research_actions,
        "heartbeat": heartbeat or [],
        "synthesis": synthesis or {},
        "radar": derived_radar if radar is None else radar,
        "lean_in": lean_block,
        "bullish_flow": bullish_flow,
        "prospects": prospects,
        "feedback": feedback,
    }
    if target_drift is not None:
        feed["target_drift"] = target_drift
    return feed
