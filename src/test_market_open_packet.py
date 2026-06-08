import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from market_open_packet import build_market_open_packet, _format_text


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
                "assumption_refresh": {
                    "status": "changed_recheck",
                    "what_changed": ["Fast-moving evidence must be refreshed."],
                    "next_step": "Refresh assumptions before acting.",
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
                    "priority_reason": "Sizing gap beats ordinary research only if current entry and funding still work.",
                    "do_nothing_risk": "Doing nothing could leave NVDA too small if the gate confirms.",
                    "compare_against": ["higher-ranked Key Now actions", "funded reallocation legs"],
                },
                "freshness_judgment": {
                    "label": "fresh",
                    "evidence_date": "2026-06-05",
                    "last_checked": "2026-06-05",
                    "decay_window": "until position, price, thesis, or target changes",
                },
                "capital_priority_score": 117,
                "disconfirmation": {
                    "invalidates_if": ["The target weight is outdated."],
                },
                "assumption_refresh": {
                    "status": "still_valid",
                    "what_changed": ["No material assumption break detected."],
                    "checked_at": "2026-06-05",
                    "snapshot": {
                        "evidence_date": "2026-06-05",
                        "freshness": "fresh",
                        "decay_window": "until position, price, thesis, or target changes",
                        "time_window": "1-3 trading days",
                        "capital_label": "compare and stage",
                    },
                    "invalidates_if": ["Current positions, target weights, or funding legs changed."],
                    "next_step": "Keep in current group.",
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
    assert packet["line"] == "Market-open packet: 1 key, 1 re-check, 0 backlog, 2 urgent visible; 5 blocker(s)."
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
    assert packet["rows"][0]["label"].startswith("Re-check: EVENT")
    assert packet["rows"][0]["refresh_status"] == "changed_recheck"
    assert packet["rows"][0]["what_changed"] == "Fast-moving evidence must be refreshed."
    assert packet["rows"][1]["why"] == "Compare against higher-ranked uses of capital before adding."
    assert packet["rows"][1]["refresh_status"] == "still_valid"
    assert packet["rows"][1]["capital_priority_score"] == 117
    assert packet["rows"][1]["capital_priority_reason"].startswith("Sizing gap")
    assert packet["rows"][1]["do_nothing_risk"].startswith("Doing nothing")
    assert packet["rows"][1]["freshness_label"] == "fresh"
    assert packet["rows"][1]["evidence_date"] == "2026-06-05"
    assert packet["rows"][1]["last_checked"] == "2026-06-05"
    assert "time window 1-3 trading days" in packet["rows"][1]["key_assumptions"]
    assert packet["rows"][1]["invalidates"] == "Current positions, target weights, or funding legs changed."
    assert "funded reallocation legs" in packet["rows"][1]["compare_against"]
    assert packet["rows"][2]["blocks"] == "current positions are missing"
    assert "runbook is instructions only" in packet["rows"][3]["blocks"]
    assert "runbook is instructions only" in packet["rows"][4]["blocks"]
    assert packet["rows"][5]["source"] == "social_watch"
    text = _format_text(packet)
    assert "priority 117: Sizing gap beats ordinary research" in text
    assert "do nothing: Doing nothing could leave NVDA too small" in text
    assert "invalidates: Current positions, target weights, or funding legs changed." in text
