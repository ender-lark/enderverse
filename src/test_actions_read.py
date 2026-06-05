"""Tests for ⑦b actions_read (the prioritized Actions surface) + the optional
Contract-C `actions` validator.

actions_read is ADDITIVE: it derives the Top-5 "what to do today" list from the
already-assembled ⑦ fresh_signals + ⑧ hero needs_you items, never mutating them.
These tests pin: the kind→confidence ladder, the priority ranking, the gate
ROUTING HOOK (Option A — provisional badge, T1 vs non-T1), fresh_act dedup, the
forward-compat synthesis seam, and that the validator treats `actions` as
optional (absent → still valid) but shape-checks it when present.

Run:  python -m pytest test_actions_read.py -q
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analyst_judgment import actions_read, synthesis_actions_read, target_drift_actions_read
from feed_assembler import assemble_feed
from goal_impact import annotate_action
from validators import validate_cockpit_feed

HERE = os.path.dirname(os.path.abspath(__file__))

# theses with one T1 name (NVDA) and one non-T1 (SOFI) for the gate-hook test
THESES = [
    {"ticker": "NVDA", "tier": "T1", "stance": "ACTIVE", "factor_tags": ["AI_complex"]},
    {"ticker": "SOFI", "tier": "T3", "stance": "ACTIVE", "factor_tags": ["fintech"]},
    {"ticker": "BMNR", "tier": "T1", "stance": "MONITOR", "factor_tags": ["crypto"]},
]


def _act(ticker, urgency="act", what="breakout", why="broke out on volume"):
    return {"ticker": ticker, "urgency": urgency, "what": what, "why": why,
            "when": "2026-06-01", "detail": why}


# --------------------------------------------------------------------------- #
# empties
# --------------------------------------------------------------------------- #
def test_empty_inputs_yield_no_actions():
    r = actions_read([], [], THESES)
    assert r["actions"] == []
    assert r["total_candidates"] == 0


# --------------------------------------------------------------------------- #
# fresh_signals → buy_now / watch_entry, confidence ladder, gate hook
# --------------------------------------------------------------------------- #
def test_buy_now_non_t1_gets_size_gate_hook():
    r = actions_read([_act("SOFI", "act")], [], THESES)
    a = r["actions"][0]
    assert a["kind"] == "buy_now"
    assert a["action_state"] == "ACT_NOW"
    assert a["confidence"] == "High"
    assert a["source"] == "fresh_signal"
    assert a["gate"]["needs_gate"] is True
    assert a["gate"]["preview"] == "🟡 size → gate"
    assert a["gate"]["default_action"] == "ADD"
    assert a["gate"]["ticker"] == "SOFI"


def test_buy_now_t1_gets_deepwork_lock_hook():
    r = actions_read([_act("NVDA", "act")], [], THESES)
    a = r["actions"][0]
    assert a["kind"] == "buy_now"
    assert a["gate"]["preview"] == "🔒 T1 — runs Deepwork"


def test_watch_entry_is_moderate_and_ungated():
    r = actions_read([_act("SOFI", "watch")], [], THESES)
    a = r["actions"][0]
    assert a["kind"] == "watch_entry"
    assert a["action_state"] == "WATCH"
    assert a["confidence"] == "Moderate"
    assert a["gate"] is None          # nothing to gate until it becomes a buy


def test_reentry_zone_touch_detected():
    sig = {"ticker": "SOFI", "urgency": "act", "what": "re-entry zone touch",
           "why": "entered zone", "when": "2026-06-01", "detail": "re-entry zone"}
    r = actions_read([sig], [], THESES)
    a = r["actions"][0]
    assert a["kind"] == "reentry_zone"
    assert a["confidence"] == "High"
    assert a["gate"]["needs_gate"] is True


# --------------------------------------------------------------------------- #
# hero needs_you items
# --------------------------------------------------------------------------- #
def test_red_gate_item_is_high_and_first():
    items = [{"reason": "red_gate", "detail": "BMNR", "note": "factor concentration RED"}]
    r = actions_read([_act("SOFI", "act")], items, THESES)
    # red_gate (priority 0) must rank ABOVE buy_now (priority 1)
    first = r["actions"][0]
    assert first["kind"] == "red_gate"
    assert first["rank"] == 1
    assert first["confidence"] == "High"
    assert first["ticker"] == "BMNR"
    assert first["gate"]["preview"] == "🔴 RED — clear first"
    assert first["gate"]["default_action"] == "REVIEW"


def test_macro_alert_has_no_ticker_and_no_gate():
    items = [{"reason": "macro_alert", "detail": "VIX", "note": "vol spike"}]
    r = actions_read([], items, THESES)
    a = r["actions"][0]
    assert a["kind"] == "macro_alert"
    assert a["ticker"] is None
    assert a["gate"] is None
    assert "VIX" in a["what"]


def test_monitor_reentry_burned_sleeve_language_and_gate():
    items = [{"reason": "monitor_reentry", "detail": "BMNR", "note": ""}]
    r = actions_read([], items, THESES)
    a = r["actions"][0]
    assert a["kind"] == "monitor_reentry"
    assert a["confidence"] == "Moderate"
    assert "burned sleeve" in a["your_move"]
    assert a["gate"]["needs_gate"] is True   # an add is the implied (gated) action


def test_stale_critical_is_low_and_last():
    items = [{"reason": "stale_critical", "detail": "uw_price", "note": ""}]
    r = actions_read([_act("SOFI", "act")], items, THESES)
    last = r["actions"][-1]
    assert last["kind"] == "stale_critical"
    assert last["confidence"] == "Low"
    assert last["gate"] is None


# --------------------------------------------------------------------------- #
# dedup + priority ordering
# --------------------------------------------------------------------------- #
def test_fresh_act_item_is_deduped_against_its_signal():
    # hero emits a fresh_act needs_you item for every act signal; it must NOT
    # produce a second action for the same name.
    items = [{"reason": "fresh_act", "detail": "SOFI"}]
    r = actions_read([_act("SOFI", "act")], items, THESES)
    sofi = [a for a in r["actions"] if a["ticker"] == "SOFI"]
    assert len(sofi) == 1
    assert sofi[0]["source"] == "fresh_signal"   # the signal won, not the pointer


def test_priority_ordering_across_all_kinds():
    fresh = [_act("SOFI", "act"), _act("ORCL", "watch")]
    items = [
        {"reason": "stale_critical", "detail": "uw_price"},
        {"reason": "macro_alert", "detail": "DXY"},
        {"reason": "red_gate", "detail": "BMNR"},
    ]
    r = actions_read(fresh, items, THESES)
    kinds = [a["kind"] for a in r["actions"]]
    assert kinds == ["red_gate", "buy_now", "macro_alert", "watch_entry", "stale_critical"]
    assert [a["rank"] for a in r["actions"]] == [1, 2, 3, 4, 5]


# --------------------------------------------------------------------------- #
# forward-compat synthesis seam
# --------------------------------------------------------------------------- #
def test_synthesis_actions_seam_passes_through():
    syn = [{"ticker": "GOOGL", "what": "Add on the synthesis call",
            "confidence": "High", "your_move": "Open a starter and run the gate."}]
    r = actions_read([], [], THESES, synthesis_actions=syn)
    syn_rows = [a for a in r["actions"] if a["source"] == "daily_synthesis"]
    assert len(syn_rows) == 1
    assert syn_rows[0]["kind"] == "synthesis"
    assert syn_rows[0]["ticker"] == "GOOGL"


def test_synthesis_bad_confidence_defaults_moderate():
    syn = [{"what": "x", "confidence": "Maybe"}]
    r = actions_read([], [], THESES, synthesis_actions=syn)
    assert r["actions"][0]["confidence"] == "Moderate"


def test_synthesis_actions_read_promotes_structured_actions():
    synthesis = {"source": "Daily Synthesis", "actions": [
        {"ticker": "NVDA", "what": "Add NVDA on confirmed setup", "confidence": "High",
         "your_move": "Size and run the gate."}
    ]}
    rows = synthesis_actions_read(synthesis)
    assert rows[0]["ticker"] == "NVDA"
    assert rows[0]["confidence"] == "High"
    r = actions_read([], [], THESES, synthesis_actions=rows)
    assert r["actions"][0]["kind"] == "synthesis"
    assert r["actions"][0]["action_state"] == "ACT_NOW"
    assert r["actions"][0]["gate"]["ticker"] == "NVDA"


def test_synthesis_actions_read_accepts_richer_structured_fields():
    synthesis = {"source": "Daily Synthesis", "actions": [{
        "symbol": "NVDA",
        "recommendation": "Add NVDA while setup is live",
        "urgency": "ACT_NOW",
        "next_step": "Size the add and run the gate.",
        "capital_effect": "add",
        "time_window": "today",
        "sizing": "$25K starter",
        "goal_channels": ["upside", "opportunity_cost", "bad-channel"],
        "missing_evidence": "confirm exact size",
        "evidence": "Daily synthesis found a live setup.",
    }]}
    rows = synthesis_actions_read(synthesis)
    assert rows[0]["ticker"] == "NVDA"
    assert rows[0]["confidence"] == "High"
    assert rows[0]["capital_effect"] == "add"
    assert rows[0]["time_window"] == "today"
    assert rows[0]["sizing"] == "$25K starter"
    assert rows[0]["goal_channels"] == ["upside", "opportunity_cost"]
    assert rows[0]["missing_evidence"] == ["confirm exact size"]

    r = actions_read([], [], THESES, synthesis_actions=rows)
    row = r["actions"][0]
    assert row["ticker"] == "NVDA"
    assert row["capital_effect"] == "add"
    assert row["time_window"] == "today"
    assert row["sizing"] == "$25K starter"
    assert row["missing_evidence"] == ["confirm exact size"]
    assert validate_cockpit_feed({**_minimal_feed(), "actions": r["actions"]}) == []


def test_synthesis_actions_read_ignores_invalid_structured_metadata():
    synthesis = {"actions": [{
        "ticker": "NVDA",
        "what": "Add NVDA if setup clears",
        "time_window": "someday",
        "capital_effect": "YOLO",
        "goal_channels": ["bad"],
        "goal_score": 999,
    }]}
    rows = synthesis_actions_read(synthesis)
    assert "time_window" not in rows[0]
    assert "capital_effect" not in rows[0]
    assert "goal_channels" not in rows[0]
    assert "goal_score" not in rows[0]


def test_synthesis_actions_read_promotes_actionable_hanging_items_only():
    synthesis = {"source": "Daily Synthesis", "hanging": [
        "FN buy-on-pullback not yet acted.",
        "XLF rationale still undocumented.",
        "No ticker process note.",
    ]}
    rows = synthesis_actions_read(synthesis)
    assert [r["ticker"] for r in rows] == ["FN"]
    assert "buy-on-pullback" in rows[0]["what"]


# --------------------------------------------------------------------------- #
# Top Prospects promotion
# --------------------------------------------------------------------------- #
def test_act_now_top_prospect_promotes_to_actions():
    prospects = {"hot": [
        {"ticker": "NVDA", "urgency": "ACT_NOW", "corroboration": "Vetted-Buy",
         "summary": "FS Top-5 plus confirmation"},
        {"ticker": "ANET", "urgency": "HOT", "corroboration": "Uncorroborated",
         "summary": "watch but not act-now"},
    ], "sell_fast": []}
    r = actions_read([], [], THESES, prospect_items=prospects)
    rows = {a["ticker"]: a for a in r["actions"]}
    assert rows["NVDA"]["kind"] == "top_prospect"
    assert rows["NVDA"]["action_state"] == "ACT_NOW"
    assert rows["NVDA"]["confidence"] == "High"
    assert "ANET" not in rows


def test_sell_fast_promotes_above_buy_now():
    prospects = {"hot": [], "sell_fast": [
        {"ticker": "SOFI", "summary": "source says avoid"}
    ]}
    r = actions_read([_act("NVDA", "act")], [], THESES, prospect_items=prospects)
    assert [a["kind"] for a in r["actions"][:2]] == ["sell_fast", "buy_now"]
    assert r["actions"][0]["action_state"] == "ACT_NOW"


def test_uncorroborated_quiet_sell_fast_stays_in_prospects_not_actions():
    prospects = {"hot": [], "sell_fast": [
        {
            "ticker": "DE",
            "summary": "monthly bottom-5 avoid",
            "urgency": "QUIET",
            "corroboration": "Uncorroborated",
        }
    ]}

    r = actions_read([], [], THESES, prospect_items=prospects)

    assert all(a.get("kind") != "sell_fast" for a in r["actions"])


# --------------------------------------------------------------------------- #
# Target-drift conviction-gap promotion
# --------------------------------------------------------------------------- #
def test_target_drift_actions_promotes_held_undersized_only():
    target_drift = {"rows": [
        {
            "ticker": "NVDA",
            "direction": "UNDERSIZED",
            "actual_pct": 6.6,
            "target_pct": 12.0,
            "flags": ["P_UNDERSIZE_CANDIDATE", "ALARM_DRIFT"],
        },
        {
            "ticker": "AVGO",
            "direction": "MISSING",
            "actual_pct": 0.0,
            "target_pct": 6.0,
            "flags": ["P_UNDERSIZE_CANDIDATE", "MISSING_TARGET"],
        },
        {
            "ticker": "BMNR",
            "direction": "UNDERSIZED",
            "actual_pct": 3.5,
            "target_pct": 10.0,
            "flags": ["P_UNDERSIZE_CANDIDATE", "ALARM_DRIFT"],
        },
    ]}

    promoted = target_drift_actions_read(target_drift, THESES)

    assert [row["ticker"] for row in promoted] == ["NVDA"]
    assert promoted[0]["confidence"] == "High"
    assert "funded add/rotation" in promoted[0]["your_move"]
    assert promoted[0]["gate"]["ticker"] == "NVDA"


def test_actions_read_promotes_conviction_gap_without_duplicate_ticker():
    target_drift = {"rows": [{
        "ticker": "NVDA",
        "direction": "UNDERSIZED",
        "actual_pct": 6.6,
        "target_pct": 12.0,
        "flags": ["P_UNDERSIZE_CANDIDATE", "ALARM_DRIFT"],
    }]}

    promoted = target_drift_actions_read(target_drift, THESES)
    out = actions_read([], [], THESES, target_drift_actions=promoted)

    row = out["actions"][0]
    assert row["kind"] == "conviction_gap"
    assert row["ticker"] == "NVDA"
    assert row["action_state"] == "ACT_NOW"
    assert row["capital_effect"] == "rotate"
    assert row["sizing"].startswith("Gap to target")
    assert validate_cockpit_feed({**_minimal_feed(), "actions": [row]}) == []


def test_actions_read_skips_conviction_gap_when_ticker_already_surfaced():
    target_drift = {"rows": [{
        "ticker": "NVDA",
        "direction": "UNDERSIZED",
        "actual_pct": 6.6,
        "target_pct": 12.0,
        "flags": ["P_UNDERSIZE_CANDIDATE", "ALARM_DRIFT"],
    }]}

    promoted = target_drift_actions_read(target_drift, THESES)
    out = actions_read([_act("NVDA", "act")], [], THESES, target_drift_actions=promoted)

    assert [row["ticker"] for row in out["actions"]].count("NVDA") == 1
    assert out["actions"][0]["kind"] == "buy_now"


# --------------------------------------------------------------------------- #
# validator: optional block
# --------------------------------------------------------------------------- #
def _minimal_feed():
    return {"generated_at": "2026-06-01T16:00:00", "staleness": {}, "hero": {},
            "macro": {}, "fresh_signals": [], "holdings": [], "rotation": []}


def _legacy_valid_action_row():
    return {"rank": 1, "kind": "buy_now", "ticker": "NVDA",
            "what": "Buy trigger fired", "confidence": "High",
            "your_move": "Size it and run the gate.",
            "gate": {"needs_gate": True, "preview": "🔒 T1 — runs Deepwork",
                     "ticker": "NVDA", "default_action": "ADD"},
            "source": "fresh_signal", "why": "breakout"}


def _valid_action_row():
    return annotate_action({
        "rank": 1, "kind": "buy_now", "ticker": "NVDA",
        "what": "Buy trigger fired", "confidence": "High",
        "your_move": "Size it and run the gate.",
        "gate": {"needs_gate": True, "preview": "T1 runs Deepwork",
                 "ticker": "NVDA", "default_action": "ADD"},
        "source": "fresh_signal", "why": "breakout",
    })


def test_validator_absent_actions_still_valid():
    assert validate_cockpit_feed(_minimal_feed()) == []   # optional → no error


def test_validator_accepts_valid_actions_list():
    feed = _minimal_feed()
    feed["actions"] = [_valid_action_row()]
    assert validate_cockpit_feed(feed) == []


def test_validator_catches_bad_confidence():
    feed = _minimal_feed()
    bad = _valid_action_row()
    bad["confidence"] = "Maybe"
    feed["actions"] = [bad]
    probs = validate_cockpit_feed(feed)
    assert any("confidence must be one of" in p for p in probs)


def test_validator_catches_bad_action_state():
    feed = _minimal_feed()
    bad = _valid_action_row()
    bad["action_state"] = "MAYBE"
    feed["actions"] = [bad]
    probs = validate_cockpit_feed(feed)
    assert any("action_state must be one of" in p for p in probs)


def test_validator_catches_non_list_actions():
    feed = _minimal_feed()
    feed["actions"] = {"not": "a list"}
    probs = validate_cockpit_feed(feed)
    assert any("actions must be a list" in p for p in probs)


# --------------------------------------------------------------------------- #
# integration: assemble_feed now emits a valid `actions` block
# --------------------------------------------------------------------------- #
def test_assemble_feed_emits_valid_actions_block():
    with open(os.path.join(HERE, "golden_snapshot.json")) as f:
        bundle = json.load(f)
    feed = assemble_feed(bundle, parabolic={"MU"})
    assert "actions" in feed
    assert isinstance(feed["actions"], list)
    assert validate_cockpit_feed(feed) == []
    # every emitted row carries the canonical fields + a confidence read
    for a in feed["actions"]:
        assert a["confidence"] in ("High", "Moderate", "Low")
        assert "rank" in a and isinstance(a["rank"], int)
