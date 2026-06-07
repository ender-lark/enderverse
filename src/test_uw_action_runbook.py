import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from uw_action_runbook import build_uw_action_runbook


def test_uw_action_runbook_scopes_current_dashboard_scenarios():
    feed = {
        "actions": [
            {"ticker": "NVDA", "kind": "conviction_gap", "source": "target_drift"},
            {"ticker": "ANET", "kind": "lean_in", "source": "lean_in"},
        ],
        "event_risk": [
            {"tickers": ["XOP", "XLE", "TNX"], "severity": "high"},
        ],
        "target_drift": {
            "rows": [
                {"ticker": "NVDA", "drift_absolute_pct": -5.4, "flags": ["ALARM_DRIFT"]},
                {"ticker": "SMH", "drift_absolute_pct": 4.4, "flags": ["ALARM_DRIFT"]},
            ],
        },
        "asymmetric_opportunities": {
            "count": 2,
            "rows": [
                {"ticker": "GOOGL", "score": 80},
                {"ticker": "AVGO", "score": 75},
            ],
        },
        "source_audits": {
            "fundstrat": {"status": "has_data", "line": "Fundstrat intake present."},
        },
        "operator_hardening": {
            "condition_checklist": {
                "rows": [
                    {"source": "fundstrat_daily", "ticker": "QQQ, RSP"},
                ]
            }
        },
    }

    block = build_uw_action_runbook(feed)

    assert block["status"] == "has_data"
    assert "endpoint results not claimed" in block["line"]
    modes = [row["mode"] for row in block["rows"]]
    assert modes == [
        "event_risk_political_macro",
        "portfolio_reallocation",
        "fundstrat_signal_confirmation",
        "asymmetric_discovery",
    ]
    by_mode = {row["mode"]: row for row in block["rows"]}
    assert {"XOP", "XLE", "TNX"}.issubset(set(by_mode["event_risk_political_macro"]["ticker_scope"]))
    assert {"NVDA", "SMH", "ANET"}.issubset(set(by_mode["portfolio_reallocation"]["ticker_scope"]))
    assert {"QQQ", "RSP", "NVDA"}.issubset(set(by_mode["fundstrat_signal_confirmation"]["ticker_scope"]))
    assert {"GOOGL", "AVGO"}.issubset(set(by_mode["asymmetric_discovery"]["ticker_scope"]))
    assert "MARKET_TIDE" in by_mode["event_risk_political_macro"]["market_checks"]
    assert "TICKER_FLOW_RECENT" in by_mode["portfolio_reallocation"]["ticker_checks"]
    assert "not proof" in block["honesty_rule"]


def test_uw_action_runbook_is_checked_clear_without_active_scenario():
    block = build_uw_action_runbook({"actions": [], "asymmetric_opportunities": {"count": 0}})

    assert block["status"] == "checked_clear"
    assert block["rows"] == []
