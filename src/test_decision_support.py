import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from decision_support import enrich_actions, build_asymmetric_opportunities


def test_enrich_actions_groups_and_adds_freshness_judgment():
    actions = [
        {
            "rank": 1,
            "kind": "event_risk",
            "ticker": None,
            "action_state": "ACT_NOW",
            "source": "event_risk",
            "time_window": "today",
            "goal_impact": "Medium",
            "goal_channels": ["downside_protection"],
            "why_it_moves_goal": "Fast shocks change sizing.",
            "missing_evidence": ["WTI trigger"],
        },
        {
            "rank": 2,
            "kind": "lean_in",
            "ticker": "NVDA",
            "action_state": "WATCH",
            "source": "lean_in",
            "time_window": "1-2 weeks",
            "goal_impact": "High",
            "goal_channels": ["sizing_gap", "upside"],
            "missing_evidence": [],
        },
    ]
    enriched, groups = enrich_actions(
        actions,
        staleness={"entries": [{"source": "uw_price", "date": "2026-06-05"}], "stale": []},
        event_risk=[{"date": "2026-06-05", "title": "Oil shock"}],
        generated_at="2026-06-05T20:00:00+00:00",
    )

    assert enriched[0]["decision_group"] == "key_now"
    assert enriched[0]["freshness_judgment"]["label"] == "fast-moving"
    assert enriched[0]["freshness_judgment"]["evidence_date"] == "2026-06-05"
    assert enriched[1]["decision_group"] == "important_backlog"
    assert groups["counts"]["key_now"] == 1
    assert groups["counts"]["important_backlog"] == 1


def test_asymmetric_opportunities_dedupes_to_strongest_source():
    feed = {
        "actions": [
            {
                "rank": 1,
                "ticker": "NVDA",
                "source": "lean_in",
                "goal_score": 76,
                "goal_channels": ["upside", "sizing_gap"],
                "why_it_moves_goal": "Sizing gap matters.",
                "what": "Lean in",
                "freshness_judgment": {"decay_window": "1-2 weeks"},
            }
        ],
        "target_drift": {
            "rows": [
                {
                    "ticker": "NVDA",
                    "direction": "UNDERSIZED",
                    "drift_absolute_pct": -8.0,
                }
            ]
        },
        "bullish_flow": {
            "rows": [
                {
                    "ticker": "NVDA",
                    "direction": "bullish",
                    "strength": "strong",
                    "evidence": ["call sweep"],
                }
            ]
        },
    }

    block = build_asymmetric_opportunities(feed)

    assert block["count"] == 1
    assert block["rows"][0]["ticker"] == "NVDA"
    assert "target_drift" in block["rows"][0]["source"]
    assert block["rows"][0]["score"] >= 70
