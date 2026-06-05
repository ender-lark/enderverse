"""Unit tests for the Analyst JUDGMENT reads (A3a: ① conviction, ② direction).

Boundary-covered asserts on the discrete enums (cv / cd) against the Build Plan's
worked examples + synthetic boundaries. The full held-book grades get frozen at
A5 (golden_feed) and checked by the golden-master (A6); these tests pin the RULE.

Run:  python -m pytest test_analyst_judgment.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sources import SourceItem
from analyst_judgment import (
    conviction_read, conviction_direction_read, GRADE_UNASSESSED,
)


def _card(kind, subject, content="", data=None, ts="2026-05-29",
          source="src", trust=0.70, grp="fundstrat"):
    return SourceItem(source, kind, subject, content, ts, trust, grp, data or {})


def _call(subject, direction, source="fundstrat_bible", trust=0.70,
          grp="fundstrat", event=None, date_="2026-05-28", kind="analyst_call"):
    data = {"direction": direction, "date": date_}
    if event:
        data["event"] = event
    return _card(kind, subject, f"{source}: {subject} {direction}", data,
                 source=source, trust=trust, grp=grp)


def _thesis(ticker, source="Lee", lane="BuyAndHold", tier="T2",
            stance="ACTIVE", tags=("ai_complex",)):
    return {"ticker": ticker, "tier": tier, "lane": lane, "source": source,
            "stance": stance, "factor_tags": list(tags)}


# =========================================================================== #
# ① conviction_read  (cockpit `cv`)
# =========================================================================== #
def test_conviction_no_backing_is_dash():
    # held but no thesis + no cards -> "—" (never fabricate)   [AMZN/COST/MSFT]
    out = conviction_read("AMZN", None, [])
    assert out["cv"] == GRADE_UNASSESSED
    assert "give me a line" in out["reason"]


def test_conviction_strong_ai_named_anchor():
    # ai_complex sleeve + fundstrat bullish endorsement, not burned -> Strong   [SMH]
    th = _thesis("SMH", source="Lee", tags=("ai_complex", "semiconductors"))
    out = conviction_read("SMH", th, [_call("SMH", "own", kind="what_to_own")])
    assert out["cv"] == "Strong" and out["durable"] is True and out["burned"] is False


def test_conviction_promising_named_not_ai_sleeve():
    # named "What to Own" but OUTSIDE the high-confidence sleeve -> Promising   [XLF]
    th = _thesis("XLF", lane="BuyAndHold", tier="T3", tags=("financials", "cyclicals"))
    out = conviction_read("XLF", th, [_call("XLF", "own", kind="what_to_own")])
    assert out["cv"] == "Promising" and out["durable"] is False


def test_conviction_mixed_on_cross_source_conflict():
    # Meridian bullish vs FS Bottom-5 bearish -> conflict -> Mixed   [UUUU]
    th = _thesis("UUUU", source="Meridian", lane="Speed", tier="T3",
                 stance="MONITOR", tags=("critical_minerals", "uranium"))
    cards = [
        _call("UUUU", "buy", source="meridian", grp="thematic_research", trust=0.75),
        _call("UUUU", "bottom_5", source="fundstrat_bible", grp="fundstrat"),
    ]
    out = conviction_read("UUUU", th, cards)
    assert out["cv"] == "Mixed" and out["conflict"] is True
    assert out["conflict_scope"] == "cross_source"
    assert "cross-source split" in out["reason"]


def test_conviction_mixed_same_source_conflict_is_not_cross_source():
    # Lee vs Farrell are two Fundstrat voices inside one independence group.
    th = _thesis("BMNR", source="operator", lane="Generational", tier="T1",
                 stance="MONITOR", tags=("crypto",))
    cards = [
        _call("BMNR", "bottom_in", source="fundstrat_daily", grp="fundstrat",
              trust=0.70, event="bottom_in"),
        _call("BMNR", "struggling", source="fundstrat_daily", grp="fundstrat",
              trust=0.65, event="unfavorable_shift"),
    ]
    cards[0].data["analyst"] = "Lee"
    cards[1].data["analyst"] = "Farrell"
    out = conviction_read("BMNR", th, cards)
    assert out["cv"] == "Mixed" and out["conflict"] is True
    assert out["conflict_scope"] == "same_source"
    assert out["conflict_detail"] == "Lee vs Farrell"
    assert "same-source split" in out["reason"]
    assert "cross-source split" not in out["reason"]


def test_conviction_burned_single_source_capped_from_strong():
    # durable Meridian anchor BUT burned + single source -> capped to Promising   [LEU]
    th = _thesis("LEU", source="Meridian", lane="Generational", tier="T1",
                 stance="MONITOR", tags=("nuclear", "uranium"))
    out = conviction_read("LEU", th,
                          [_call("LEU", "buy", source="meridian",
                                 grp="thematic_research", trust=0.75)])
    assert out["cv"] == "Promising" and out["durable"] is True and out["burned"] is True


def test_conviction_burned_multi_source_keeps_strong():
    # same name but TWO independent streams -> burned cap doesn't apply -> Strong
    th = _thesis("LEU", source="Meridian", lane="Generational", tier="T1",
                 stance="MONITOR", tags=("nuclear", "uranium"))
    cards = [
        _call("LEU", "buy", source="meridian", grp="thematic_research", trust=0.75),
        _call("LEU", "top_5", source="fundstrat_bible", grp="fundstrat", trust=0.70),
    ]
    out = conviction_read("LEU", th, cards)
    assert out["cv"] == "Strong" and out["streams"] == 2


def test_conviction_operator_thesis_no_endorsement_is_promising():
    # operator thesis, ai_complex, but NO external endorsement -> Promising   [IVES]
    th = _thesis("IVES", source="operator", lane="Speed", tier="T3", tags=("ai_complex",))
    out = conviction_read("IVES", th, [])
    assert out["cv"] == "Promising" and out["durable"] is False


def test_conviction_echo_chamber_collapses_streams():
    # the two Fundstrat plugs on one name = ONE stream, not two
    th = _thesis("XLF", tags=("financials",))
    cards = [
        _call("XLF", "own", source="fundstrat_bible", grp="fundstrat"),
        _call("XLF", "own", source="fundstrat_daily", grp="fundstrat"),
    ]
    assert conviction_read("XLF", th, cards)["streams"] == 1


def test_conviction_weak_thin_lottery():
    # no thesis, one thin low-trust bullish card -> Weak (lottery)
    out = conviction_read("LIT", None,
                          [_call("LIT", "buy", source="reddit", grp="social", trust=0.35)])
    assert out["cv"] == "Weak"


def test_conviction_external_nonanchor_pick_is_promising():
    # no thesis, a single decent-trust bullish call that is NOT a durable anchor
    # (a plain "buy", not Top-5) -> Promising (the else branch), ask for a line.
    # NB a bare FS *Top-5* with no thesis of your own + one stream now also caps at
    # Promising (the single-source cap); ANET (a tiny Top-5 starter) is that case —
    # that spec-vs-oracle divergence is reconciled at A5/A6, not asserted here.
    out = conviction_read("WDAY", None,
                          [_call("WDAY", "buy", source="fundstrat_daily",
                                 grp="fundstrat", trust=0.70)])
    assert out["cv"] == "Promising"


def test_conviction_excludes_model_trades():
    # a Meridian MODEL trade is not a live endorsement -> no backing -> "—"
    card = _card("model_trade", "TLOFF", "[Meridian model] long TLOFF",
                 {"is_model": True, "direction": "buy"},
                 source="meridian", grp="thematic_research", trust=0.75)
    assert conviction_read("TLOFF", None, [card])["cv"] == GRADE_UNASSESSED


# =========================================================================== #
# ② conviction_direction_read  (cockpit `cd`: up / flat / down)
# =========================================================================== #
AS_OF = "2026-05-29"


def test_direction_steady_state_is_flat():
    # steadily strong, NO new event -> flat (the calibration fix: not "up")   [SMH/NVDA/MAGS]
    out = conviction_direction_read("SMH", [_call("SMH", "own", kind="what_to_own")], AS_OF)
    assert out["cd"] == "flat" and out["cdNote"] == "No recent change."


def test_direction_up_on_bullish_event():
    # Newton 5/28 breakout -> up   [ITA]
    out = conviction_direction_read(
        "ITA", [_call("ITA", "breakout", source="fundstrat_daily",
                      event="breakout", date_="2026-05-28")], AS_OF)
    assert out["cd"] == "up" and "breakout" in out["cdNote"]


def test_direction_down_on_bearish_event():
    # new FS Bottom-5 5/28 -> down   [UUUU]
    out = conviction_direction_read(
        "UUUU", [_call("UUUU", "bottom_5", source="fundstrat_bible",
                       event="new_bottom5", date_="2026-05-28")], AS_OF)
    assert out["cd"] == "down"


def test_direction_conflict_near_tie_is_flat():
    # bullish + bearish events of near-equal weight -> flat (deadband)   [BMNR Lee/Farrell]
    cards = [
        _call("BMNR", "bottom_in", source="fundstrat_daily", event="bottom_in",
              trust=0.70, date_="2026-05-28"),
        _call("BMNR", "struggling", source="fundstrat_daily", event="unfavorable_shift",
              trust=0.65, date_="2026-05-28"),
    ]
    out = conviction_direction_read("BMNR", cards, AS_OF)
    assert out["cd"] == "flat"


def test_direction_conflict_clear_margin_resolves():
    # fresh strong bullish vs old weak bearish -> up (deadband exceeded)
    cards = [
        _call("XYZ", "upgrade", source="fundstrat_daily", event="upgrade",
              trust=0.70, date_="2026-05-29"),                  # fresh, full weight
        _call("XYZ", "downgrade", source="fundstrat_daily", event="downgrade",
              trust=0.65, date_="2026-05-16"),                  # 13d old, decayed
    ]
    out = conviction_direction_read("XYZ", cards, AS_OF, window_days=14)
    assert out["cd"] == "up"


def test_direction_event_out_of_window_ignored():
    # a bullish event 70d ago is not "recent" -> flat
    out = conviction_direction_read(
        "OLD", [_call("OLD", "breakout", event="breakout", date_="2026-03-20")],
        AS_OF, window_days=14)
    assert out["cd"] == "flat"


def test_direction_ignores_model_and_other_tickers():
    cards = [
        _card("model_trade", "ZZ", "[model]",
              {"is_model": True, "event": "new_pick", "date": "2026-05-28"}),  # model -> skip
        _call("OTHER", "breakout", event="breakout", date_="2026-05-28"),     # wrong ticker
    ]
    assert conviction_direction_read("ZZ", cards, AS_OF)["cd"] == "flat"


# =========================================================================== #
# ③ net_read  (cockpit `nr` + basis)
# =========================================================================== #
from analyst_judgment import net_read, fresh_signal_read


def _conv(cv, conflict=False, burned=False, durable=False, conflict_scope="", conflict_label="", conflict_detail=""):
    return {"ticker": "X", "cv": cv, "streams": 1, "conflict": conflict,
            "burned": burned, "durable": durable, "reason": "",
            "conflict_scope": conflict_scope, "conflict_label": conflict_label,
            "conflict_detail": conflict_detail}


def test_net_no_thesis_asks_for_a_line():
    out = net_read("AMZN", None, _conv(GRADE_UNASSESSED))
    assert out["basis"] == "no_thesis" and "give me a line" in out["nr"]


def test_net_burned_override_beats_catch_up():
    # burned sleeve fires FIRST, regardless of endorsement/rotation   [BMNR/LEU]
    th = _thesis("LEU", source="Meridian", lane="Generational", tier="T1", stance="MONITOR")
    out = net_read("LEU", th, _conv("Promising", burned=True),
                   rotation_label="LAGGING")   # would be catch-up if not burned
    assert out["basis"] == "burned_override" and "trigger" in out["nr"]


def test_net_burned_surfaces_split_when_conflicted():
    # burned + cross-source conflict -> still burned_override, but names the split  [UUUU]
    th = _thesis("UUUU", source="Meridian", lane="Speed", tier="T3", stance="MONITOR")
    weighted = {"voices": [{"source": "meridian"}, {"source": "fundstrat_bible"}]}
    out = net_read("UUUU", th, _conv("Mixed", conflict=True, burned=True), weighted=weighted)
    assert out["basis"] == "burned_override" and "split" in out["nr"]


def test_net_burned_same_source_split_uses_same_source_wording():
    th = _thesis("BMNR", source="operator", lane="Generational", tier="T1", stance="MONITOR")
    conv = _conv("Mixed", conflict=True, burned=True,
                 conflict_scope="same_source",
                 conflict_label="same-source split",
                 conflict_detail="Lee vs Farrell")
    out = net_read("BMNR", th, conv, weighted={"voices": [{"source": "fundstrat_daily"}]})
    assert out["basis"] == "burned_override"
    assert "same-source split (Lee vs Farrell)" in out["nr"]
    assert "cross-source split" not in out["nr"]


def test_net_parabolic_dont_trim_on_move():
    # not burned + parabolic -> don't-trim special   [MU]
    th = _thesis("MU", source="Lee", tier="T2", tags=("ai_complex",))
    out = net_read("MU", th, _conv("Strong"), rotation_label="LEADING", parabolic=True)
    assert out["basis"] == "parabolic" and "not trim" in out["nr"].lower()


def test_net_nonburned_conflict_holds():
    th = _thesis("ZZ", source="Lee", tier="T3", tags=("misc",))
    out = net_read("ZZ", th, _conv("Mixed", conflict=True))
    assert out["basis"] == "conflict" and "split" in out["nr"]


def test_net_endorsed_lagging_is_catch_up():
    # endorsed laggard -> catch-up (lagging != bearish)   [XLF]
    th = _thesis("XLF", source="Lee", tier="T3", tags=("financials",))
    out = net_read("XLF", th, _conv("Promising"), rotation_label="LAGGING")
    assert out["basis"] == "catch_up" and "Catch-up" in out["nr"]


def test_net_endorsed_leading_is_ride_it():
    # endorsed + leading -> ride it   [SMH]
    th = _thesis("SMH", source="Lee", tags=("ai_complex",))
    out = net_read("SMH", th, _conv("Strong"), rotation_label="LEADING")
    assert out["basis"] == "ride_it" and "ride it" in out["nr"]


def test_net_undersizing_lens_on_ai_sleeve():
    # leading AI name flagged underweight -> the under-sizing lens fires
    th = _thesis("SMH", source="Lee", tags=("ai_complex",))
    out = net_read("SMH", th, _conv("Strong"), rotation_label="LEADING", underweight=True)
    assert out["basis"] == "ride_it" and "underweight" in out["nr"]


# =========================================================================== #
# ⑦ fresh_signal_read  (cockpit `fresh_signals` + per-name fresh)
# =========================================================================== #
def _dr(ticker, cd, event=None, date_="2026-05-28", content=None):
    events = []
    if event:
        events = [{"date": date_, "sentiment": "bullish", "event": event,
                   "source": "fundstrat_daily", "content": content}]
    return {"ticker": ticker, "cd": cd, "cdNote": content or "", "events": events}


def test_fresh_act_on_breakout():
    # Newton 5/28 breakout, not burned -> ⏳ act   [ITA]
    out = fresh_signal_read([_dr("ITA", "up", event="breakout")], theses=[])
    assert out["act_count"] == 1 and out["fresh_signals"][0]["urgency"] == "act"


def test_fresh_watch_on_new_pick():
    # new FS Top-5 (no confirmed entry, near ATH) -> 👁 watch   [FN]
    out = fresh_signal_read([_dr("FN", "up", event="new_top5")], theses=[])
    assert out["watch_count"] == 1 and out["fresh_signals"][0]["urgency"] == "watch"


def test_fresh_burned_sleeve_excluded():
    # crypto bullish event but burned + no high-conf re-entry -> EXCLUDED   [IBIT/crypto]
    th = _thesis("IBIT", source="operator", lane="Generational", tier="T2",
                 stance="MONITOR", tags=("crypto",))
    out = fresh_signal_read([_dr("IBIT", "up", event="breakout")], theses=[th])
    assert out["fresh_signals"] == [] and out["act_count"] == 0


def test_fresh_burned_surfaces_on_high_conf_reentry():
    # same burned name, but a high-confidence re-entry fired -> surfaced
    th = _thesis("IBIT", source="operator", lane="Generational", tier="T2",
                 stance="MONITOR", tags=("crypto",))
    out = fresh_signal_read([_dr("IBIT", "up", event="breakout")], theses=[th],
                            high_conf_reentry={"IBIT"})
    assert len(out["fresh_signals"]) == 1


def test_fresh_reentry_zone_touch_is_act():
    out = fresh_signal_read([], theses=[], reentry_touches=[{"ticker": "MP", "note": "hit zone"}])
    assert out["act_count"] == 1 and out["fresh_signals"][0]["what"] == "re-entry zone touch"


def test_fresh_flat_or_no_event_not_a_candidate():
    # steady-state (cd flat) or up-without-event -> not surfaced
    out = fresh_signal_read([_dr("SMH", "flat"), _dr("NVDA", "up", event=None)], theses=[])
    assert out["fresh_signals"] == []


def test_fresh_stance_shift_not_surfaced():
    # a held name with a sector/stance shift (favorable_shift) drives cd=up but is
    # NOT an Actions-strip signal — it lives on the holding row as catch-up   [XLF]
    out = fresh_signal_read([_dr("XLF", "up", event="favorable_shift")], theses=[])
    assert out["fresh_signals"] == []


def test_conviction_single_source_toptier_pick_capped_to_promising():
    # a bare FS Top-5 (durable) with NO thesis of your own + one stream caps at
    # Promising — Strong needs your own thesis or a 2nd independent source   [ANET]
    out = conviction_read("ANET", None, [_call("ANET", "top_5")])
    assert out["cv"] == "Promising" and out["durable"] is True


def test_conviction_single_source_cap_lifts_with_second_stream():
    # same bare Top-5 but a 2nd independent stream lifts the cap -> Strong
    cards = [_call("ANET", "top_5"),
             _call("ANET", "buy", source="meridian", grp="thematic_research")]
    out = conviction_read("ANET", None, cards)
    assert out["cv"] == "Strong" and out["streams"] == 2
