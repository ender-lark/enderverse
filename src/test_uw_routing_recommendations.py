import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from uw_routing_recommendations import build_uw_routing_recommendations


def test_uw_routing_recommends_profiles_from_current_feed_state():
    feed = {
        "actions": [
            {"kind": "event_risk", "source": "event_risk"},
            {"kind": "conviction_gap", "ticker": "NVDA", "source": "target_drift"},
        ],
        "event_risk": [{"title": "Oil/rates shock"}],
        "asymmetric_opportunities": {"count": 2},
        "source_audits": {"fundstrat": {"line": "Fundstrat intake has data."}},
    }

    block = build_uw_routing_recommendations(feed)
    modes = [row["mode"] for row in block["rows"]]

    assert block["status"] == "has_data"
    assert modes[:4] == [
        "event_risk_political_macro",
        "portfolio_reallocation",
        "fundstrat_signal_confirmation",
        "asymmetric_discovery",
    ]
    assert "Routing recommends endpoint groups only" in block["honesty_rule"]
    assert "MARKET_TIDE" in block["rows"][0]["top_endpoints"]
    assert "TICKER_OHLC" in block["rows"][1]["top_endpoints"]


def test_uw_routing_is_checked_clear_when_no_scenario_is_active():
    block = build_uw_routing_recommendations({"actions": []})

    assert block["status"] == "checked_clear"
    assert block["rows"] == []
    assert "no scenario profile" in block["line"]
