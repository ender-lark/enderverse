import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import decision_card as dc
from directive_recs import build_directive_cards
from tunables import load_conviction_weights, load_goal_tunables

TODAY = "2026-06-10"
W = load_conviction_weights()
G = load_goal_tunables()

def _gate():
    return {
        "gate_id": "QQQ-TEST", "symbol": "QQQ", "kind": "support_band",
        "level_low": 695.0, "level_high": 705.0, "state": "red_but_tested",
        "source": "newton", "stated": "2026-06-08", "note": "band",
        "confirm_rule": "holds above ~705", "applies_to": ["ai_semis"],
        "blocks_full_size": True,
    }

def _accounts():
    base = {"crypto_only": False, "tax_type": "taxable",
            "tax_flag": "TAXABLE â€” gains realize", "option_value": 0.0}
    return [
        {**base, "owner": "Parents", "broker": "Fidelity", "account": "Joint WROS",
         "etf_only": False, "total_value": 612000.0,
         "holdings": {"NVDA": 50000.0, "MAGS": 20000.0}},
        {**base, "owner": "Parents", "broker": "Schwab", "account": "PCRA Trust",
         "etf_only": True, "total_value": 368000.0,
         "holdings": {"MAGS": 19710.0}, "tax_type": "traditional_ira",
         "tax_flag": "tax-advantaged (no cap-gains)"},
        {**base, "owner": "SKB", "broker": "Robinhood", "account": "Trad IRA",
         "etf_only": False, "total_value": 180000.0,
         "holdings": {"GOOGL": 10000.0}, "tax_type": "traditional_ira",
         "tax_flag": "tax-advantaged (no cap-gains)"},
    ]

def _insights():
    return {"insights": [{
        "insight_id": "INSIGHT-950", "statement": "s", "polarity": "bullish",
        "belief_strength": 50, "status": "ACTIVE", "stated": TODAY,
        "last_reviewed": TODAY, "sectors": [], "keywords": [],
        "tickers_mapped": ["GOOGL"], "tickers_adjacent": [], "watch_tickers": [],
        "factor_tags": [], "evidence_for": [], "evidence_against": [],
    }]}

def _feed():
    return {
        "portfolio_views": {"views": {"combined": {
            "rows": [{"ticker": "NVDA", "market_value": 50000}],
            "total_value": 1890000,
        }}},
        "actions": [
            {"ticker": "GOOGL", "goal_score": 80, "kind": "lean_in"},
            {"ticker": "MAGS", "goal_score": 70, "kind": "trim"},
        ],
        "reallocation_brief": {
            "positions_snapshot_date": "2026-06-09",
            "rows": [
                {"ticker": "GOOGL", "notional_usd": 151266, "current_pct": 0.0,
                 "target_pct": 8.0, "sequence": "now", "entry_note": "x", "gate": "QQQ"},
                {"ticker": "NVDA", "notional_usd": 56609, "current_pct": 5.0,
                 "target_pct": 8.0},
            ],
            "trims": [
                {"ticker": "MAGS", "notional_usd": 70216, "current_pct": 3.7,
                 "target_pct": 0.0,
                 "funds": [{"ticker": "NVDA", "notional_usd": 51500}]},
            ],
            "funding": {"pool_usd": 503646, "shortfall_usd": 211916},
        },
        "target_drift": {"rows": [{"ticker": "MAGS", "direction": "OVERSIZED"}]},
        "event_risk": {"rows": []},
    }

def _build():
    return build_directive_cards(
        feed=_feed(), weights=W, goal=G, insights_payload=_insights(),
        accounts=_accounts(), gates=[_gate()], uw_states={}, entry_zones={},
        today=TODAY,
    )

def test_stack_builds_and_respects_card_max():
    out = _build()
    assert out["built"] == TODAY
    assert len(out["cards"]) <= G["daily_card_max"]
    assert len(out["cards"]) + len(out["backlog"]) == 3

def test_every_card_carries_a_valid_decision_card():
    out = _build()
    for card in out["cards"] + out["backlog"]:
        assert dc.validate_decision_card(card["decision_card"]) == []
        assert set(dc.CARD_FIELDS) <= set(card["decision_card"])

def test_buy_adds_are_gate_capped_stage_only():
    out = _build()
    buys = [c for c in out["cards"] + out["backlog"] if c["direction"] == "BUY"]
    assert buys
    for c in buys:
        assert c["window"]["class"] == "STAGE-ONLY"
        assert c["window"]["stage_fraction"] == W["timing"]["stage_only_fraction"]

def test_oversized_trim_opens_now_with_named_trigger():
    out = _build()
    mags = [c for c in out["cards"] + out["backlog"] if c["ticker"] == "MAGS"][0]
    assert mags["direction"] == "SELL"  # target 0%
    assert mags["window"]["class"] == "OPEN-NOW"
    assert "overexposed" in mags["window"]["named_trigger"]
    assert "NVDA" in mags["funds"]

def test_priority_blend_orders_the_stack():
    out = _build()
    ranked = out["cards"] + out["backlog"]
    assert [c["priority"] for c in ranked] == sorted(
        (c["priority"] for c in ranked), reverse=True
    )
    googl = [c for c in ranked if c["ticker"] == "GOOGL"][0]
    nvda = [c for c in ranked if c["ticker"] == "NVDA"][0]
    assert googl["priority"] > nvda["priority"]  # goal_score 80 + 'now' bump vs default
    assert ranked[0]["ticker"] == "GOOGL"
    assert googl["impact"]["material"] is True

def test_execution_blocks_surface_pcra_and_cash_honesty():
    out = _build()
    buys = [c for c in out["cards"] + out["backlog"] if c["direction"] == "BUY"]
    for c in buys:
        assert any("ETF-ONLY" in e["why_not"] for e in c["execution"]["excluded"])
        assert c["execution"]["cash"].startswith("not_checked")
    mags = [c for c in out["cards"] + out["backlog"] if c["ticker"] == "MAGS"][0]
    pcra_legs = [l for l in mags["execution"]["legs"] if "PCRA" in l["account"]]
    assert pcra_legs and "proceeds_constraint" in pcra_legs[0]

def test_buy_cards_carry_caps_sizing_payload():
    out = _build()
    buys = [c for c in out["cards"] + out["backlog"] if c["direction"] in {"BUY", "ADD"}]
    assert buys
    for card in buys:
        sizing = card.get("sizing")
        assert sizing["source"] == "caps"
        assert isinstance(sizing["suggested_usd"], (int, float))
        assert sizing["heat"]
        assert sizing["cap_basis"]

def test_honesty_footer_and_funding_passthrough():
    out = _build()
    h = out["honesty"]
    assert h["cash"].startswith("not_checked")
    assert "not wired" in h["institutional"]
    assert h["gates_as_of"] == "2026-06-08"
    assert h["positions_as_of"] == "2026-06-09"
    assert out["funding"]["pool_usd"] == 503646
