import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from today_recommendation_brief import (  # noqa: E402
    build_today_recommendation_brief,
    format_today_recommendation_text,
)


def test_brief_leads_with_defensive_rechecks_and_dark_lanes():
    feed = {
        "as_of": "2026-07-01",
        "generated_at": "2026-07-01T13:00:00Z",
        "market_open_packet": {
            "rows": [
                {
                    "priority": 1,
                    "kind": "recheck_first",
                    "label": "Re-check: EVENT: oil shock",
                    "why": "Fast-moving evidence is stale.",
                    "next_step": "Refresh the event-risk lane.",
                    "blocks": "Do not add risk until refreshed.",
                    "source": "event_risk",
                }
            ]
        },
        "lane_status": {
            "rows": [
                {
                    "key": "social_watch",
                    "label": "Social Watch",
                    "status": "not_checked",
                    "missing_impact": "Social anomalies are not checked.",
                    "next_step": "Supply social_watch.json.",
                }
            ]
        },
        "social_watch": {"status": "not_checked", "line": "Social watch not checked."},
    }

    block = build_today_recommendation_brief(feed)

    assert block["status"] == "defensive_recheck"
    assert block["as_of"] == "2026-07-01"
    assert block["line"].startswith("Today: start defensively")
    assert block["do_today"][0]["kind"] == "defensive_recheck"
    assert block["options"]["status"] == "not_checked"
    assert any(row["key"] == "social_watch" for row in block["not_checked"])
    assert any(row["key"] == "options_expression" for row in block["not_checked"])


def test_brief_surfaces_options_act_with_max_loss_when_no_defensive_blocker():
    feed = {
        "as_of": "2026-07-01",
        "market_open_packet": {"rows": []},
        "social_watch": {"status": "checked_clear", "line": "Social watch checked clear."},
        "options_expression": {
            "status": "has_data",
            "line": "1 options idea ready to act now.",
            "rows": [
                {
                    "ticker": "NVDA",
                    "disposition": "ACT",
                    "action": "Buy 1x NVDA call",
                    "reason": "Defined-risk upside expression.",
                    "risk_amount_usd": 1750,
                    "risk_pct_book": 0.1,
                    "iv_environment": "cheap",
                    "the_catch": "Long options can go to zero.",
                    "legs": [{"expiry": "2026-08-21", "dte": 51}],
                    "source": "options_surface",
                }
            ],
        },
    }

    block = build_today_recommendation_brief(feed)
    text = format_today_recommendation_text(block)

    assert block["status"] == "options_review"
    assert block["do_today"][0]["kind"] == "options_act_review"
    assert block["options"]["rows"][0]["risk"] == "$1,750 / 0.1%"
    assert block["push_candidates"][0]["kind"] == "options_act_review"
    assert "Long options can go to zero" in text


def test_social_rows_remain_watch_only_not_push_candidates():
    feed = {
        "market_open_packet": {"rows": []},
        "social_watch": {
            "status": "has_data",
            "line": "Social watch: 1 anomaly candidate.",
            "promotion_rule": "Key Now only after independent non-social confirmation.",
            "rows": [
                {
                    "ticker": "MU",
                    "source": "reddit",
                    "subreddits": ["TrumpsTrades"],
                    "summary": "Trump/Micron account chatter.",
                    "escalation": "Quiet Watch",
                    "risk": "Pump/chase risk.",
                    "independent_confirmation": [],
                }
            ],
        },
    }

    block = build_today_recommendation_brief(feed)

    assert block["status"] == "social_watch_only"
    assert block["social"]["rows"][0]["watch_only"] is True
    assert block["social"]["rows"][0]["push_candidate"] is False
    assert block["push_candidates"] == []


def test_alert_rows_become_review_only_push_candidates():
    feed = {
        "market_open_packet": {"rows": []},
        "social_watch": {"status": "checked_clear", "line": "Social clear."},
        "alert_policy": {
            "rows": [
                {
                    "severity": "high",
                    "kind": "critical_event_risk",
                    "title": "Critical event risk",
                    "why": "Oil shock can change new-buy timing.",
                    "next_step": "Review hedges before adding risk.",
                    "delivery": "eligible_review_only",
                }
            ]
        },
    }

    block = build_today_recommendation_brief(feed)

    assert block["status"] == "alert_review"
    assert block["do_today"][0]["push_candidate"] is True
    assert block["push_candidates"][0]["delivery"] == "eligible_review_only"


def test_text_keeps_opportunities_visible_when_defense_leads():
    feed = {
        "generated_at": "2026-07-01T13:00:00Z",
        "market_open_packet": {
            "rows": [
                {
                    "priority": 1,
                    "kind": "recheck_first",
                    "label": "Re-check: event risk",
                    "next_step": "Refresh event risk.",
                },
                {
                    "priority": 2,
                    "kind": "gate_key_now",
                    "label": "Gate Key Now: HOOD sell-fast review",
                    "why": "Key Now item still exists.",
                    "next_step": "Run the pre-action gate.",
                },
            ]
        },
        "social_watch": {"status": "checked_clear", "line": "Social clear."},
    }

    block = build_today_recommendation_brief(feed)
    text = format_today_recommendation_text(block)

    assert block["as_of"] == "2026-07-01"
    assert block["opportunities"]["count"] == 1
    assert "Opportunities/reallocation: 1 review item" in text
    assert "HOOD sell-fast review" in text
