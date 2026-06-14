import copy
import os
import json
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import timing_engine as te
from timing_engine import GatesMissingError, compute_timing, evaluate_gate, load_gates
from tunables import load_conviction_weights, load_goal_tunables

TODAY = "2026-06-10"
W = load_conviction_weights()
G = load_goal_tunables()

def _gate(state="red_but_tested"):
    return {
        "gate_id": "QQQ-TEST", "symbol": "QQQ", "kind": "support_band",
        "level_low": 695.0, "level_high": 705.0, "state": state,
        "source": "newton", "stated": "2026-06-08",
        "note": "695-705 should contain pullbacks",
        "confirm_rule": "full size when today's session holds above ~705",
        "applies_to": ["ai_semis"], "blocks_full_size": True,
    }

def _zone(price=348.0):
    return {"zone_low": 341.0, "zone_high": 350.0, "price": price,
            "source": "FS", "date": TODAY}

def test_repo_gates_load_and_missing_is_honest(tmp_path):
    gates = load_gates()
    qqq = next(g for g in gates if g["gate_id"] == "QQQ-NEWTON-BAND")
    assert qqq["gate_type"] == "close"
    docs = json.loads(te.GATES_PATH.read_text(encoding="utf-8"))["gate_type_docs"]
    assert {"close", "touch", "near_certain", "context"} <= set(docs)
    with pytest.raises(GatesMissingError):
        load_gates(tmp_path / "absent.json")

def test_evaluate_gate_transitions():
    below = evaluate_gate(_gate(state="red"), 690.0)
    assert below["suggested_state"] == "red" and below["changed"] is False
    inside = evaluate_gate(_gate(state="red"), 700.0)
    assert inside["suggested_state"] == "red_but_tested" and inside["changed"] is True
    confirm = evaluate_gate(_gate(state="red_but_tested"), 706.0)
    assert confirm["suggested_state"] == "green" and "confirm rule satisfied" in confirm["why"]
    reclaim = evaluate_gate(_gate(state="red"), 706.0)
    assert reclaim["suggested_state"] == "red_but_tested" and "awaiting confirm" in reclaim["why"]
    ctx = evaluate_gate({"kind": "context", "state": "context"}, 700.0)
    assert ctx["changed"] is False and "no evaluable" in ctx["why"]

def test_close_gate_requires_close_not_intraday_touch():
    gate = {
        "gate_id": "QQQ-NEWTON-BAND",
        "symbol": "QQQ",
        "kind": "support_band",
        "gate_type": "close",
        "level_low": 717.5,
        "level_high": 717.5,
        "state": "red_but_tested",
        "source": "newton",
        "stated": "2026-06-11",
        "note": "QQQ must close/hold above 717.50",
        "confirm_rule": "full size only after QQQ closes/holds above 717.50",
        "applies_to": ["ai_semis", "tech", "growth", "*BUY*"],
        "blocks_full_size": True,
    }
    intraday_touch = evaluate_gate(gate, 718.4, price_type="live")
    assert intraday_touch["suggested_state"] == "red_but_tested"
    assert intraday_touch["changed"] is False
    assert "close required" in intraday_touch["why"]

    trap_close = evaluate_gate(gate, 717.22, price_type="close")
    assert trap_close["suggested_state"] == "red_but_tested"
    assert trap_close["changed"] is False
    assert "remains unconfirmed" in trap_close["why"]

    confirmed_close = evaluate_gate(gate, 718.4, price_type="close")
    assert confirmed_close["suggested_state"] == "green"
    assert confirmed_close["changed"] is True

def test_near_certain_gate_requires_buffer_for_live_confirmation():
    gate = _gate(state="red_but_tested") | {
        "gate_type": "near_certain",
        "near_certain_buffer_abs": 1.0,
    }
    marginal = evaluate_gate(gate, 705.5, price_type="live")
    assert marginal["suggested_state"] == "red_but_tested"
    assert "near-certain" in marginal["why"]

    decisive = evaluate_gate(gate, 706.1, price_type="live")
    assert decisive["suggested_state"] == "green"

def test_red_gate_blocks_full_size():
    out = compute_timing("NVDA", direction="BUY", sleeves=["ai_semis"],
                         gates=[_gate(state="red")], weights=W, goal=G, today=TODAY)
    assert out["class"] == "GATED" and out["gate_red"] is True
    assert out["flips"][0] == _gate()["confirm_rule"]

def test_tested_gate_caps_at_stage_only():
    out = compute_timing("GOOGL", direction="BUY", sleeves=["ai_semis"],
                         gates=[_gate()], entry_zone=_zone(),
                         weights=W, goal=G, today=TODAY)
    assert out["class"] == "STAGE-ONLY"
    assert out["stage_fraction"] == W["timing"]["stage_only_fraction"]
    assert out["named_trigger"] and "entry zone" in out["named_trigger"]
    assert any("red-but-tested" in r for r in out["reasons"])

def test_open_now_invariant_requires_named_trigger():
    quiet = compute_timing("GOOGL", direction="BUY", weights=W, goal=G, today=TODAY)
    assert quiet["class"] == "WAIT" and quiet["named_trigger"] is None
    assert quiet["reasons"] == ["no named positive trigger today â€” quiet is a valid state"]
    outside = compute_timing("GOOGL", direction="BUY", entry_zone=_zone(price=380.0),
                             weights=W, goal=G, today=TODAY)
    assert outside["class"] == "WAIT"
    assert any("pullback into" in f for f in outside["flips"])
    live = compute_timing("GOOGL", direction="BUY", entry_zone=_zone(),
                          weights=W, goal=G, today=TODAY)
    assert live["class"] == "OPEN-NOW" and live["named_trigger"]
    for out in (quiet, outside, live):
        assert (out["class"] == "OPEN-NOW") == bool(out["named_trigger"])

def test_uw_contradicts_forces_wait_despite_trigger():
    out = compute_timing("GOOGL", direction="BUY", entry_zone=_zone(),
                         uw_state={"interpretation": "contradicts", "date": TODAY},
                         weights=W, goal=G, today=TODAY)
    assert out["class"] == "WAIT" and "CONTRADICTS" in out["reasons"][0]

def test_event_risk_downgrades_open_now_one_notch():
    risks = [{"name": "FOMC", "note": "FOMC decision", "date": "2026-06-17"}]
    out = compute_timing("GOOGL", direction="BUY", entry_zone=_zone(),
                         event_risks=risks, weights=W, goal=G, today=TODAY)
    assert out["class"] == "STAGE-ONLY"
    assert any("downgraded" in r for r in out["reasons"])
    assert any("event passes" in f for f in out["flips"])
    w2 = copy.deepcopy(W)
    w2["timing"]["event_risk_downgrade"] = False
    out2 = compute_timing("GOOGL", direction="BUY", entry_zone=_zone(),
                          event_risks=risks, weights=w2, goal=G, today=TODAY)
    assert out2["class"] == "OPEN-NOW"

def test_catalyst_inside_horizon_sets_trigger_and_deadline():
    near = compute_timing("AVGO", direction="BUY",
                          catalyst={"name": "earnings", "date": "2026-06-15"},
                          weights=W, goal=G, today=TODAY)
    assert near["class"] == "OPEN-NOW" and "catalyst earnings in 5td" in near["named_trigger"]
    assert near["deadline"] == "2026-06-15"
    far = compute_timing("AVGO", direction="BUY",
                         catalyst={"name": "earnings", "date": "2026-09-01"},
                         weights=W, goal=G, today=TODAY)
    assert far["class"] == "WAIT"

def test_sell_lane_scoped_triggers_only():
    turning = compute_timing("SMH", direction="TRIM",
                             rotation={"state": "TURNING DOWN"},
                             weights=W, goal=G, today=TODAY)
    assert turning["class"] == "OPEN-NOW" and "TURNING DOWN" in turning["named_trigger"]
    over = compute_timing("MAGS", direction="SELL",
                          rotation={"overexposed": True},
                          weights=W, goal=G, today=TODAY)
    assert over["class"] == "OPEN-NOW" and "overexposed" in over["named_trigger"]
    plain = compute_timing("IVES", direction="TRIM", weights=W, goal=G, today=TODAY)
    assert plain["class"] == "STAGE-ONLY"
    assert "paired" in plain["reasons"][0]
    assert plain["stage_fraction"] == W["timing"]["stage_only_fraction"]

def test_uw_supports_trigger_and_sleeve_scoping():
    out = compute_timing("GOOGL", direction="BUY",
                         uw_state={"interpretation": "supports", "date": TODAY},
                         weights=W, goal=G, today=TODAY)
    assert out["class"] == "OPEN-NOW" and "UW evidence supports" in out["named_trigger"]
    scoped = compute_timing("BMNR", direction="BUY", sleeves=["crypto"],
                            gates=[_gate(state="red")], entry_zone=_zone(),
                            weights=W, goal=G, today=TODAY)
    assert scoped["class"] == "OPEN-NOW"  # ai_semis gate does not apply to crypto sleeve
