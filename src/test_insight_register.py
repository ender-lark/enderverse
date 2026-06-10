import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import insight_register as ir
from insight_register import (
    InsightsInvalidError,
    InsightsMissingError,
    add_evidence,
    conviction_points,
    discovery_boost,
    load_insights,
    match,
    research_scope,
    set_status,
    validate_insights,
)

TODAY = "2026-06-10"

def _ins(iid="INSIGHT-901", status="ACTIVE", polarity="bullish", mapped=None,
         adjacent=None, watch=None, sectors=None, keywords=None):
    return {
        "insight_id": iid,
        "statement": "test thesis statement",
        "polarity": polarity,
        "belief_strength": 80,
        "status": status,
        "stated": "2026-06-01",
        "last_reviewed": "2026-06-01",
        "sectors": sectors or ["power", "nuclear"],
        "keywords": keywords or ["grid", "megawatt"],
        "tickers_mapped": mapped if mapped is not None else ["GEV", "BE"],
        "tickers_adjacent": adjacent if adjacent is not None else ["VRT"],
        "watch_tickers": watch if watch is not None else ["TLN"],
        "factor_tags": ["ai_power"],
        "evidence_for": [],
        "evidence_against": [],
        "history": [],
    }

def _payload():
    return {
        "updated": TODAY,
        "insights": [
            _ins(),
            _ins(iid="INSIGHT-902", status="RETIRED", mapped=["TSM"], adjacent=[],
                 watch=["INTC"], sectors=["semiconductors"], keywords=["foundry"]),
        ],
    }

def _weights(cap=1.0):
    return {
        "insight_match_points": 1.0,
        "insight_triage_boost": 15,
        "group_caps": {"operator_insight": cap},
        "insight_stale_days": 60,
    }

def test_repo_register_loads_seeds_and_staleness():
    payload = load_insights()
    ids = {i["insight_id"] for i in payload["insights"]}
    assert {"INSIGHT-001", "INSIGHT-002"} <= ids
    assert validate_insights(payload) == []
    far = ir.active_insights(_payload(), today="2026-09-01", stale_days=60)
    assert far and all(r["stale"] for r in far)
    near = ir.active_insights(_payload(), today="2026-06-10", stale_days=60)
    assert near and not any(r["stale"] for r in near)

def test_missing_file_is_honest_absence(tmp_path):
    with pytest.raises(InsightsMissingError):
        load_insights(tmp_path / "nope.json")

def test_validate_rejects_bad_rows():
    bad = _payload()
    bad["insights"][0]["tickers_mapped"] = ["gev"]  # lowercase
    bad["insights"][0]["status"] = "MAYBE"
    bad["insights"][0]["evidence_for"] = [{"kind": "vibes", "note": "x"}]
    problems = validate_insights(bad)
    assert any("uppercase" in p for p in problems)
    assert any("status" in p for p in problems)
    assert any("kind" in p for p in problems)

def test_max_active_cap_is_surfaced_not_silent():
    payload = {"insights": [_ins(iid=f"INSIGHT-9{i:02d}") for i in range(3)]}
    problems = validate_insights(payload, max_active=2)
    assert any("insight_max_active" in p for p in problems)
    assert validate_insights(payload, max_active=3) == []

def test_match_strength_ladder_and_scope():
    p = _payload()
    assert match(p, ticker="GEV")[0]["strength"] == "direct"
    assert match(p, ticker="VRT")[0]["strength"] == "adjacent"
    assert match(p, ticker="TLN")[0]["strength"] == "watch"
    assert match(p, sectors=["Nuclear"])[0]["strength"] == "thematic"
    assert match(p, text="the grid buildout accelerates")[0]["strength"] == "thematic"
    scope = research_scope(p)
    assert "GEV" in scope["tickers"] and "TLN" in scope["tickers"]
    assert "power" in scope["sectors"]

def test_non_active_insights_never_match():
    assert match(_payload(), ticker="TSM") == []  # RETIRED
    assert match(_payload(), ticker="INTC") == []

def test_conviction_points_max_not_sum():
    matches = [
        {"insight_id": "A", "strength": "direct"},
        {"insight_id": "B", "strength": "adjacent"},
    ]
    out = conviction_points(matches, _weights())
    assert out["points"] == 1.0  # max(1.0, 0.5), never 1.5
    assert out["compounded"] is False
    assert set(out["matched"]) == {"A", "B"}
    assert conviction_points([{"insight_id": "B", "strength": "adjacent"}], _weights())["points"] == 0.5
    assert conviction_points([{"insight_id": "C", "strength": "watch"}], _weights())["points"] == 0.25

def test_conviction_points_group_cap():
    out = conviction_points([{"insight_id": "A", "strength": "direct"}], _weights(cap=0.75))
    assert out["points"] == 0.75

def test_discovery_boost_tickers_only_no_keyword_noise():
    assert discovery_boost(_payload(), "GEV", _weights()) == {"boost": 15.0, "matches": ["INSIGHT-901"]}
    assert discovery_boost(_payload(), "ZZZZ", _weights())["boost"] == 0.0

def test_confirmation_changes_nothing_change_marks_review():
    p = _payload()
    ins = p["insights"][0]
    before = (ins["belief_strength"], ins["status"])
    add_evidence(p, "INSIGHT-901", kind="confirmation", note="Lee repeated the thesis", on=TODAY)
    assert (ins["belief_strength"], ins["status"]) == before
    assert "needs_review" not in ins
    assert len(ins["evidence_for"]) == 1 and ins["history"][-1]["event"] == "evidence:confirmation"
    add_evidence(p, "INSIGHT-901", kind="change", note="new datapoint", on=TODAY)
    assert ins["needs_review"] is True
    with pytest.raises(InsightsInvalidError):
        add_evidence(p, "INSIGHT-901", kind="vibes", note="x")

def test_set_status_requires_reason_and_stamps_history():
    p = _payload()
    with pytest.raises(InsightsInvalidError):
        set_status(p, "INSIGHT-901", "WEAKENED", reason="   ")
    ins = set_status(p, "INSIGHT-901", "WEAKENED", reason="counter-evidence landed", on=TODAY)
    assert ins["status"] == "WEAKENED" and ins["last_reviewed"] == TODAY
    assert "ACTIVE->WEAKENED" in ins["history"][-1]["event"]
    with pytest.raises(InsightsInvalidError):
        set_status(p, "INSIGHT-999", "RETIRED", reason="x")
