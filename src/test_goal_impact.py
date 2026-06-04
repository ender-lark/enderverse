"""Tests for goal-impact metadata on surfaced cockpit actions."""
from goal_impact import annotate_action, annotate_actions


def test_buy_now_is_high_goal_impact_capital_add():
    row = annotate_action({
        "kind": "buy_now",
        "ticker": "NVDA",
        "confidence": "High",
        "what": "Buy trigger fired",
    })
    assert row["goal_impact"] == "High"
    assert row["capital_effect"] == "add"
    assert row["action_label"] == "BUY/ADD"
    assert "upside" in row["goal_channels"]
    assert 0 <= row["goal_score"] <= 100


def test_act_now_top_prospect_is_start_validate_with_missing_evidence():
    row = annotate_action({
        "kind": "top_prospect",
        "ticker": "AVGO",
        "confidence": "Moderate",
    })
    assert row["goal_impact"] == "High"
    assert row["capital_effect"] == "start"
    assert row["action_label"] == "START/VALIDATE"
    assert row["time_window"] == "1-3 trading days"
    assert "size through gate" in row["missing_evidence"]


def test_monitor_reentry_cannot_move_capital_yet():
    row = annotate_action({
        "kind": "monitor_reentry",
        "ticker": "BMNR",
        "confidence": "Moderate",
    })
    assert row["capital_effect"] == "no_capital_yet"
    assert row["action_label"] == "WATCH"
    assert "confirm re-entry trigger" in row["missing_evidence"]


def test_stale_critical_is_data_quality_not_trade_signal():
    row = annotate_action({
        "kind": "stale_critical",
        "ticker": "ITA",
        "confidence": "Low",
    })
    assert row["goal_impact"] == "Low"
    assert row["capital_effect"] == "no_capital_yet"
    assert "data_quality" in row["goal_channels"]


def test_catalyst_today_tightens_time_window():
    row = annotate_action({
        "kind": "catalyst_imminent",
        "ticker": "TSLA",
        "confidence": "Moderate",
        "days_to_catalyst": 0,
    })
    assert row["time_window"] == "today"


def test_annotate_actions_handles_empty_input():
    assert annotate_actions(None) == []
