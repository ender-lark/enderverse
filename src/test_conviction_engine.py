import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import conviction_engine as ce
from tunables import load_conviction_weights, load_goal_tunables

TODAY = "2026-06-10"
W = load_conviction_weights()
G = load_goal_tunables()

def _item(source="newton", tier="A", date=TODAY, direction="bullish", note="call"):
    return {"source": source, "tier": tier, "date": date, "direction": direction, "note": note}

def _insights(ticker="GOOGL"):
    return {"insights": [{
        "insight_id": "INSIGHT-950", "statement": "s", "polarity": "bullish",
        "belief_strength": 50, "status": "ACTIVE", "stated": TODAY,
        "last_reviewed": TODAY, "sectors": [], "keywords": [],
        "tickers_mapped": [ticker], "tickers_adjacent": [], "watch_tickers": [],
        "factor_tags": [], "evidence_for": [], "evidence_against": [],
    }]}

def test_tier_d_is_track_only_never_scores():
    out = ce.score_item(_item(tier="D"), weights=W, today=TODAY)
    assert out["weight"] == 0.0 and out["track_only"] is True
    assert "doctrine" in out["reason"]

def test_undated_item_is_track_only():
    out = ce.score_item(_item(date=None), weights=W, today=TODAY)
    assert out["track_only"] is True and "undated" in out["reason"]

def test_fresh_tier_a_scores_full_weight():
    out = ce.score_item(_item(), weights=W, today=TODAY)
    assert out["weight"] == 1.0 and out["fresh"] == 1.0
    assert out["calibration_band"] == "INSUFFICIENT_DATA" and out["expired"] is False

def test_linear_decay_and_expiry():
    half = ce.score_item(_item(date="2026-06-03"), weights=W, today=TODAY)  # age 7 of 14
    assert half["fresh"] == 0.5 and half["weight"] == 0.5
    dead = ce.score_item(_item(date="2026-05-25"), weights=W, today=TODAY)  # age 16 > 14
    assert dead["expired"] is True and dead["weight"] == 0.0

def test_bearish_direction_flips_sign():
    out = ce.score_item(_item(direction="bearish"), weights=W, today=TODAY)
    assert out["weight"] == -1.0 and out["direction"] == "bearish"

def test_calibration_bands_with_sufficient_n():
    def mult(win_rate, n=20):
        rates = {"newton": {"A": {"n": n, "win_rate": win_rate}}}
        return ce.score_item(_item(), weights=W, rates=rates, today=TODAY)["calibration"]
    assert mult(35) == 0.25 and mult(45) == 0.5 and mult(65) == 1.0 and mult(80) == 1.25
    assert mult(80, n=5) == 1.0  # below min_n -> INSUFFICIENT_DATA

def test_same_cluster_repetition_is_capped():
    items = [_item(source=s, date=TODAY) for s in ("newton", "lee", "farrell")]
    fs = ce.fs_group(items, weights=W, today=TODAY)
    assert fs["raw"] == 3.0 and fs["points"] == 1.5  # group cap
    assert fs["capped"] is True and fs["n_live"] == 3

def test_uw_interpretation_semantics_verbatim():
    assert ce.uw_group({"interpretation": "supports"}, weights=W)["points"] == 1.0
    assert ce.uw_group({"interpretation": "supports", "battery_complete": True}, weights=W)["points"] == 1.25
    inconclusive = ce.uw_group({"interpretation": "inconclusive"}, weights=W)
    assert inconclusive["points"] == 0.0 and "not a direction" in inconclusive["why"]
    contra = ce.uw_group({"interpretation": "contradicts"}, weights=W)
    assert contra["points"] == -1.0 and contra["force_recheck"] is True
    single = ce.uw_group({"single_day_flow": True}, weights=W)
    assert single["points"] == 0.5 and "unconfirmed" in single["why"]
    assert ce.uw_group({}, weights=W)["points"] == 0.0

def test_institutional_stub_is_honest_and_capped():
    stub = ce.institutional_group(None, weights=W)
    assert stub["points"] == 0.0 and stub["status"] == "not_checked"
    assert "not checked" in stub["why"]
    live = ce.institutional_group({"points": 2.5, "why": "x"}, weights=W)
    assert live["points"] == 1.0  # cap

def test_cross_group_convergence_reaches_high():
    out = ce.conviction(
        "GOOGL",
        fs_items=[_item(source=s) for s in ("newton", "lee", "farrell")],
        uw_state={"interpretation": "supports", "battery_complete": True},
        insight_payload=_insights(),
        inst_state={"points": 1.0, "why": "13F overlap"},
        weights=W, goal=G, today=TODAY,
    )
    assert out["points"] == 4.75 and out["read"] == "HIGH" and out["n_groups"] == 4

def test_moderate_and_low_reads():
    low = ce.conviction("GOOGL", fs_items=[_item(source=s) for s in ("newton", "lee")],
                        weights=W, goal=G, today=TODAY)
    assert low["read"] == "LOW"
    mod = ce.conviction(
        "GOOGL", fs_items=[_item(source=s) for s in ("newton", "lee")],
        uw_state={"interpretation": "supports"},
        inst_state={"points": 0.6, "why": "x"},
        weights=W, goal=G, today=TODAY,
    )
    assert mod["points"] == pytest.approx(3.1) and mod["read"] == "MODERATE"

def test_contradictions_collected_and_recheck_forced():
    out = ce.conviction(
        "GOOGL",
        fs_items=[_item(), _item(source="lee", direction="bearish", note="trim call")],
        uw_state={"interpretation": "contradicts"},
        weights=W, goal=G, today=TODAY,
    )
    assert out["force_recheck"] is True
    assert any("bearish" in c for c in out["contradictions"])
    assert any("CONTRADICTS" in c for c in out["contradictions"])

def test_raises_names_tier_a_upgrade_path():
    out = ce.conviction("GOOGL", fs_items=[_item(tier="B")], weights=W, goal=G, today=TODAY)
    joined = " | ".join(out["raises"])
    assert "Tier A" in joined and "Tier B exists" in joined
    out_a = ce.conviction("GOOGL", fs_items=[_item(tier="A")], weights=W, goal=G, today=TODAY)
    joined_a = " | ".join(out_a["raises"])
    assert "Tier A" not in joined_a

def test_not_checked_lanes_are_explicit():
    out = ce.conviction("GOOGL", fs_items=[_item()], weights=W, goal=G, today=TODAY)
    assert "institutional" in out["not_checked"]
    assert "uw_same_session" in out["not_checked"]
    joined = " | ".join(out["raises"])
    assert "9:40" in joined and "13F" in joined

def test_source_calls_adapter_filters_ticker_and_cluster():
    calls = [
        {"ticker": "GOOGL", "source": "newton", "tier": "A", "date": TODAY,
         "direction": "bullish", "verbatim_quote": "buy zone 341-350"},
        {"ticker": "GOOGL", "source": "meridian", "tier": "A", "date": TODAY},
        {"ticker": "NVDA", "source": "lee", "tier": "B", "date": TODAY},
    ]
    items = ce.fs_items_from_source_calls("GOOGL", calls)
    assert len(items) == 1
    assert items[0]["source"] == "newton" and items[0]["kind"] == "source_call"
    assert "buy zone" in items[0]["note"]

def test_membership_and_feed_adapters():
    prospects = {"GOOGL": {"add_date": "2026-05-28", "conviction": "top5", "direction": "long"}}
    m = ce.fs_membership_item("GOOGL", prospects)
    assert m["tier"] == "C" and m["date"] == "2026-05-28"
    assert m["direction"] == "bullish" and m["kind"] == "monthly_membership"
    assert ce.fs_membership_item("ZZZZ", prospects) is None
    avoid = ce.fs_membership_item("X", {"X": {"add_date": TODAY, "direction": "avoid"}})
    assert avoid["direction"] == "bearish"
    feed = {"uw_endpoint_result_proof": {"rows": [
        {"ticker": "GOOGL", "decision_interpretation": "supports", "note": "flow", "date": TODAY},
    ]}}
    state = ce.uw_state_from_feed("GOOGL", feed)
    assert state["interpretation"] == "supports" and state["date"] == TODAY
    assert ce.uw_state_from_feed("GOOGL", {}) == {}