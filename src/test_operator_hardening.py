import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import operator_hardening as hardening


def _feed():
    return {
        "actions": [
            {
                "ticker": "QQQ",
                "kind": "event_risk_review",
                "what": "Re-check QQQ support before acting",
                "action_label": "RE-CHECK",
                "action_state": "WATCH",
                "freshness_judgment": {
                    "label": "stale",
                    "evidence_date": "2026-06-05",
                    "last_checked": "2026-06-05T16:00:00-04:00",
                    "decay_window": "next market session",
                    "judgment": "Re-check before capital action.",
                },
            }
        ],
        "feedback": {
            "open_actions": {
                "items": [
                    {"ticker": "ANET", "kind": "review", "age_days": 6},
                    {"ticker": "GOOGL", "kind": "review", "age_days": 3},
                    {"ticker": "NVDA", "kind": "review", "age_days": 1},
                ]
            }
        },
        "event_risk": [
            {
                "date": "2026-06-07",
                "title": "Rates/oil shock",
                "trigger": "10Y or WTI breaks Monday levels",
            }
        ],
        "radar": [
            {
                "ticker": "SOX",
                "direction": "support",
                "author": "Newton",
                "date": "2026-06-05",
                "quote": "Re-check support before chasing semis.",
            }
        ],
        "signal_log": [
            {"ticker": "AI", "signal": "AI leadership still narrow"},
        ],
    }


def test_operator_hardening_groups_rechecks_and_cleanup_items():
    block = hardening.build_operator_hardening(_feed())

    assert block["freshness_downgrades"]["count"] == 1
    assert block["freshness_downgrades"]["rows"][0]["ticker"] == "QQQ"
    assert block["stale_action_cleanup"]["count"] == 2
    states = {row["ticker"]: row["state"] for row in block["stale_action_cleanup"]["rows"]}
    assert states == {"ANET": "stale", "GOOGL": "due"}


def test_operator_hardening_builds_condition_and_watch_only_lanes():
    block = hardening.build_operator_hardening(_feed())

    checks = block["condition_checklist"]["rows"]
    assert any(row["source"] == "event_risk" for row in checks)
    assert any(row["ticker"] == "SOX" for row in checks)
    watch_rows = block["watch_only_why"]["rows"]
    assert any(row["source"] == "signal_log" for row in watch_rows)
    assert any(row["source"] == "fundstrat_daily" for row in watch_rows)
