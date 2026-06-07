import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from market_open_packet import build_market_open_packet


def _feed():
    return {
        "actions": [
            {
                "rank": 1,
                "ticker": None,
                "kind": "event_risk",
                "what": "Oil/rates shock can change new-buy timing",
                "your_move": "Re-check crude, yields, and headlines before adding risk.",
                "why_this_matters": "Fast macro shocks can overpower normal thesis signals.",
                "source": "event_risk",
                "decision_group": "recheck_before_acting",
                "freshness_judgment": {
                    "judgment": "Fast-moving tape; same-session confirmation required.",
                    "evidence_date": "2026-06-05",
                    "decay_window": "intraday",
                },
                "disconfirmation": {
                    "summary": "Do not act until oil/yield/headline evidence is current.",
                    "confirm_before_acting": ["Refresh WTI, 10Y, and current headlines."],
                    "invalidates_if": ["Headlines de-escalate or yields reverse."],
                },
            },
            {
                "rank": 2,
                "ticker": "NVDA",
                "kind": "conviction_gap",
                "what": "NVDA is under target",
                "your_move": "Decide whether to stage an add after the gate clears.",
                "why_this_matters": "A high-conviction target gap can make the right thesis too small.",
                "source": "target_drift",
                "decision_group": "key_now",
                "capital_efficiency": {
                    "summary": "Compare against higher-ranked uses of capital before adding.",
                },
                "disconfirmation": {
                    "invalidates_if": ["The target weight is outdated."],
                },
            },
        ],
        "action_decision_groups": {
            "counts": {
                "key_now": 1,
                "recheck_before_acting": 1,
                "important_backlog": 0,
            }
        },
        "reallocation_brief": {
            "status": "test_data_only",
            "line": "Reallocation brief: test data only from stale positions.",
            "blockers": ["current positions are missing"],
            "command": "python src/reallocation_brief.py --format text",
        },
        "social_watch": {
            "status": "not_checked",
            "line": "Social Watch not checked.",
            "command": "python src/social_watch.py --format text",
        },
        "lane_status": {
            "rows": [
                {
                    "key": "social_watch",
                    "status": "not_checked",
                    "missing_impact": "social anomaly lane not inspected",
                }
            ]
        },
        "uw_action_runbook": {
            "command": "python src/uw_action_runbook.py --format text",
            "rows": [
                {
                    "label": "Event-risk and political macro",
                    "operator_question": "Do same-session macro endpoints confirm or refute the event risk?",
                    "blocks_action_if": "same-session macro evidence is missing",
                },
                {
                    "label": "Portfolio reallocation",
                    "operator_question": "Do current positions and flow support the leg?",
                    "blocks_action_if": "current positions are missing",
                },
            ],
        },
        "feedback": {
            "open_actions": {
                "count": 2,
                "line": "Open action backlog: 2 open; 0 due; 0 stale.",
            }
        },
    }


def test_market_open_packet_sequences_recheck_capital_and_dark_lanes():
    packet = build_market_open_packet(_feed())

    assert packet["status"] == "recheck_first"
    assert packet["line"] == "Market-open packet: 1 key, 1 re-check, 0 backlog; 5 blocker(s)."
    assert packet["counts"]["key_now"] == 1
    assert packet["counts"]["recheck"] == 1
    assert "un-gated trades" in packet["honesty_rule"]

    kinds = [row["kind"] for row in packet["rows"]]
    assert kinds == [
        "recheck_first",
        "gate_key_now",
        "positions_blocker",
        "uw_check",
        "uw_check",
        "dark_lane",
        "open_reviews",
    ]
    assert packet["rows"][0]["label"].startswith("Re-check first: EVENT")
    assert packet["rows"][1]["why"] == "Compare against higher-ranked uses of capital before adding."
    assert packet["rows"][2]["blocks"] == "current positions are missing"
    assert "runbook is instructions only" in packet["rows"][3]["blocks"]
    assert "runbook is instructions only" in packet["rows"][4]["blocks"]
    assert packet["rows"][5]["source"] == "social_watch"
