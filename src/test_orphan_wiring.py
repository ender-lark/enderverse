"""Orphan-wiring adapter tests (Task 5 / C8).

Covers MONITOR-RE-ENTRY defined-risk gate, GRNY-DELTA item shapes,
13F + insider → inst_state aggregation, the unified runner's honest-empty
fallbacks, and additive integration through directive_recs.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import decision_card as dc
import directive_recs as dr
import orphan_wiring as ow
from tunables import load_conviction_weights, load_goal_tunables

TODAY = "2026-06-10"
W = load_conviction_weights()
G = load_goal_tunables()


def _validate_card(card):
    inner = card["decision_card"]
    problems = dc.validate_decision_card(inner)
    assert not problems, f"invalid card: {problems}"


# ---------------------------------------------------------------------------
# MONITOR-RE-ENTRY
# ---------------------------------------------------------------------------
def _mp_zone(**overrides):
    z = {
        "zone_lo": 55.0, "zone_hi": 58.0,
        "intraday_low": 56.2, "intraday_high": 58.4,
        "last_close": 57.8,
        "stop_loss": 53.5, "risk_band": "$1k defined",
        "max_loss_usd": 1000.0,
        "source": "Meridian buy-on-noise rule, Jan 23",
        "tier": "B",
    }
    z.update(overrides)
    return z


def test_monitor_reentry_emits_when_fired_and_defined_risk_present():
    cards = ow.build_monitor_reentry_cards(
        {"MP": _mp_zone()},
        weights=W, goal=G, today=TODAY, gates=[],
    )
    assert len(cards) == 1
    card = cards[0]
    assert card["pattern"] == "MONITOR-RE-ENTRY"
    assert card["ticker"] == "MP"
    assert card["sleeve"] == "monitor"
    assert card["defined_risk"]["stop_loss"] == 53.5
    assert card["defined_risk"]["max_loss_usd"] == 1000.0
    _validate_card(card)


def test_monitor_reentry_does_not_emit_without_defined_risk_fields():
    # Missing stop_loss
    cards = ow.build_monitor_reentry_cards(
        {"MP": _mp_zone(stop_loss=None)},
        weights=W, goal=G, today=TODAY, gates=[],
    )
    assert cards == [], "stop_loss required"
    # Missing risk_band
    cards = ow.build_monitor_reentry_cards(
        {"MP": _mp_zone(risk_band="")},
        weights=W, goal=G, today=TODAY, gates=[],
    )
    assert cards == [], "risk_band required"
    # Missing max_loss_usd
    cards = ow.build_monitor_reentry_cards(
        {"MP": _mp_zone(max_loss_usd=None)},
        weights=W, goal=G, today=TODAY, gates=[],
    )
    assert cards == [], "max_loss_usd required"


def test_monitor_reentry_does_not_emit_when_range_misses_zone():
    cards = ow.build_monitor_reentry_cards(
        {"MP": _mp_zone(intraday_low=60.0, intraday_high=62.0)},
        weights=W, goal=G, today=TODAY, gates=[],
    )
    assert cards == []


def test_monitor_reentry_only_for_monitor_sleeve_tickers():
    cards = ow.build_monitor_reentry_cards(
        {"NVDA": _mp_zone()},   # not in sleeve
        weights=W, goal=G, today=TODAY, gates=[],
    )
    assert cards == []


def test_monitor_reentry_allowed_tickers_override():
    cards = ow.build_monitor_reentry_cards(
        {"NVDA": _mp_zone()},
        weights=W, goal=G, today=TODAY, gates=[],
        allowed_tickers={"NVDA"},
    )
    assert len(cards) == 1


# ---------------------------------------------------------------------------
# GRNY-DELTA
# ---------------------------------------------------------------------------
def test_grny_delta_named_not_held_emits_tier_a_lee_row():
    findings = {
        "lee_named_not_held": [
            {"ticker": "ROOT", "etf": "GRNJ", "rank": 3, "weight_pct": 3.2,
             "on_watchlist": False},
        ],
    }
    rows = ow.build_grny_delta_items(findings, today=TODAY)
    assert len(rows) == 1
    r = rows[0]
    assert r["ticker"] == "ROOT"
    assert r["tier"] == "A"
    assert r["source"] == "lee"
    assert r["direction"] == "bullish"
    assert r["date"] == TODAY
    assert "GRNY-DELTA" in r["verbatim_quote"]


def test_grny_delta_additions_vs_baseline_when_operator_does_not_hold():
    findings = {
        "additions_vs_baseline": [
            {"ticker": "AAA", "etf": "GRNY", "weight_pct": 2.7,
             "operator_holds": False},
            {"ticker": "BBB", "etf": "GRNY", "weight_pct": 2.7,
             "operator_holds": True},   # held → no row
        ],
    }
    rows = ow.build_grny_delta_items(findings, today=TODAY)
    tickers = [r["ticker"] for r in rows]
    assert tickers == ["AAA"]
    assert rows[0]["tier"] == "B"


def test_grny_delta_dropped_held_becomes_bearish_context_row():
    findings = {
        "dropped_held": [
            {"ticker": "ZZZ", "etf": "GRNY", "prior_weight": 2.4},
        ],
    }
    rows = ow.build_grny_delta_items(findings, today=TODAY)
    assert len(rows) == 1
    assert rows[0]["direction"] == "bearish"
    assert rows[0]["tier"] == "C"


def test_grny_delta_no_double_count_when_ticker_in_named_and_additions():
    findings = {
        "lee_named_not_held": [
            {"ticker": "DUP", "etf": "GRNY", "rank": 1, "weight_pct": 4.0,
             "on_watchlist": False},
        ],
        "additions_vs_baseline": [
            {"ticker": "DUP", "etf": "GRNY", "weight_pct": 4.0,
             "operator_holds": False},
        ],
    }
    rows = ow.build_grny_delta_items(findings, today=TODAY)
    assert len(rows) == 1
    assert rows[0]["tier"] == "A", "named-not-held takes precedence"


def test_grny_delta_weight_change_direction_follows_sign():
    findings = {
        "weight_changes": [
            {"ticker": "UP", "etf": "GRNY", "prior_weight": 2.0,
             "current_weight": 3.0, "change_pct": 1.0},
            {"ticker": "DN", "etf": "GRNY", "prior_weight": 3.0,
             "current_weight": 2.0, "change_pct": -1.0},
        ],
    }
    rows = ow.build_grny_delta_items(findings, today=TODAY)
    by_ticker = {r["ticker"]: r for r in rows}
    assert by_ticker["UP"]["direction"] == "bullish"
    assert by_ticker["DN"]["direction"] == "bearish"


# ---------------------------------------------------------------------------
# inst_state adapter
# ---------------------------------------------------------------------------
@dataclass
class _StubSignal:
    ticker: str
    classification: str = "BULLISH"
    bullish_count: int = 0
    bearish_count: int = 0
    cluster_count: int = 0


@dataclass
class _StubReport:
    bullish: list = field(default_factory=list)
    bearish: list = field(default_factory=list)
    cluster: list = field(default_factory=list)
    flagged: list = field(default_factory=list)
    noise: list = field(default_factory=list)


def test_build_inst_states_aggregates_13f_band_to_points():
    records = [
        {"ticker": "AAA", "band": "High", "n_managers": 5, "lane": "Best-Ideas"},
        {"ticker": "BBB", "band": "Moderate", "n_managers": 2, "lane": "Best-Ideas"},
        {"ticker": "CCC", "band": "Watch", "n_managers": 1, "lane": "Activist"},
    ]
    out = ow.build_inst_states(weights=W, holdings_13f=records)
    assert out["AAA"]["points"] == 1.0
    assert out["BBB"]["points"] == 0.6
    # CCC: Watch (0.25) + Activist (0.25)
    assert out["CCC"]["points"] == 0.5
    assert "Watch" in out["CCC"]["why"]
    assert "activist" in out["CCC"]["why"]


def test_build_inst_states_includes_insider_signals():
    report = _StubReport(
        bullish=[_StubSignal("AAA", "BULLISH", bullish_count=2)],
        cluster=[_StubSignal("BBB", "CLUSTER", cluster_count=4)],
        bearish=[_StubSignal("CCC", "BEARISH", bearish_count=1)],
        flagged=[_StubSignal("DDD", "FLAGGED")],
    )
    out = ow.build_inst_states(weights=W, insider_report=report)
    assert out["AAA"]["points"] == 0.4
    assert out["BBB"]["points"] == 0.5
    assert out["CCC"]["points"] == -0.3
    assert out["DDD"]["points"] == -0.5
    for ticker in ("AAA", "BBB", "CCC", "DDD"):
        assert "insider" in out[ticker]["why"].lower()


def test_inst_state_flows_through_conviction_engine_via_directive_recs():
    """The institutional honesty line should flip when inst_states is supplied."""
    feed = {
        "portfolio_views": {"views": {"combined": {"rows": [], "total_value": 1_000_000}}},
        "actions": [], "reallocation_brief": {"rows": [], "trims": []},
        "target_drift": {"rows": []}, "event_risk": {"rows": []},
    }
    insights = {"insights": []}
    out = dr.build_directive_cards(
        feed=feed, weights=W, goal=G,
        insights_payload=insights, accounts=[], gates=[],
        inst_states={"NVDA": {"points": 0.7, "status": "ok", "why": "13F High"}},
        today=TODAY,
    )
    assert "wired via orphan_wiring" in out["honesty"]["institutional"]


# ---------------------------------------------------------------------------
# Unified runner
# ---------------------------------------------------------------------------
def test_compute_orphan_wiring_packs_all_three_lanes():
    findings = {
        "lee_named_not_held": [{"ticker": "ROOT", "etf": "GRNJ", "rank": 1,
                                "weight_pct": 3.2, "on_watchlist": False}],
    }
    holdings_13f = [
        {"ticker": "ROOT", "band": "High", "n_managers": 4, "lane": "Best-Ideas"},
    ]
    insider_report = _StubReport(
        cluster=[_StubSignal("MP", "CLUSTER", cluster_count=3)],
    )
    out = ow.compute_orphan_wiring(
        monitor_zones={"MP": _mp_zone()},
        granny_findings=findings,
        holdings_13f=holdings_13f,
        insider_report=insider_report,
        weights=W, goal=G, today=TODAY, gates=[],
    )
    assert out["inst_states"]["ROOT"]["points"] == 1.0
    assert out["inst_states"]["MP"]["points"] == 0.5
    assert len(out["grny_delta_items"]) == 1
    assert out["grny_delta_by_ticker"]["ROOT"][0]["tier"] == "A"
    assert len(out["monitor_reentry_cards"]) == 1
    _validate_card(out["monitor_reentry_cards"][0])
    # No "not checked" entries when all four caches are supplied.
    assert "granny_diff" not in out["honesty"]
    assert "institutional" not in out["honesty"]
    assert "monitor_zones" not in out["honesty"]


def test_compute_orphan_wiring_honest_empty_when_all_caches_absent():
    out = ow.compute_orphan_wiring(weights=W, goal=G, today=TODAY)
    assert out["inst_states"] == {}
    assert out["grny_delta_items"] == []
    assert out["monitor_reentry_cards"] == []
    h = out["honesty"]
    assert "not checked" in h["granny_diff"]
    assert "not checked" in h["institutional"]
    assert "not checked" in h["monitor_zones"]


def test_compute_orphan_wiring_grouped_grny_items_match_flat_list():
    findings = {
        "lee_named_not_held": [
            {"ticker": "AAA", "etf": "GRNJ", "rank": 1, "weight_pct": 3.0,
             "on_watchlist": False},
            {"ticker": "BBB", "etf": "GRNY", "rank": 2, "weight_pct": 2.7,
             "on_watchlist": False},
        ],
    }
    out = ow.compute_orphan_wiring(
        granny_findings=findings, weights=W, goal=G, today=TODAY,
    )
    flat = out["grny_delta_items"]
    grouped = out["grny_delta_by_ticker"]
    assert sum(len(v) for v in grouped.values()) == len(flat)
    assert set(grouped) == {"AAA", "BBB"}
