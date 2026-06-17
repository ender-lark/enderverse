import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from alert_policy import build_alert_policy


def test_alert_policy_stays_quiet_for_routine_rechecks_and_optional_social():
    block = build_alert_policy({
        "actions": [
            {
                "ticker": "NVDA",
                "what": "Re-check before adding",
                "action_state": "WATCH",
                "assumption_refresh": {
                    "status": "changed_recheck",
                    "blockers": ["same-session refresh"],
                },
            }
        ],
        "lane_status": {
            "rows": [
                {"key": "social_watch", "label": "Social Watch", "status": "not_checked"}
            ]
        },
        "feedback": {"open_actions": {"count": 2, "items": [{"ticker": "ANET", "age_days": 0}]}},
        "source_audits": {
            "cloud_routines": {
                "missing_scheduled_success_count": 4,
                "failed_latest_count": 0,
            }
        },
    })

    assert block["status"] == "quiet"
    assert block["rows"] == []
    reasons = {row["reason"] for row in block["suppressed"]}
    assert {"dashboard_recheck", "optional_dark_lane", "fresh_open_reviews", "background_cloud_proof"} <= reasons


def test_alert_policy_allows_only_blockers_and_urgent_invalidations():
    block = build_alert_policy({
        "actions": [
            {
                "ticker": "QQQ",
                "what": "Add QQQ",
                "action_state": "ACT_NOW",
                "source": "target_drift",
                "assumption_refresh": {
                    "status": "still_valid",
                    "blockers": ["pre-trade gate"],
                },
            },
            {
                "ticker": "BMNR",
                "what": "Old setup",
                "action_state": "WATCH",
                "source": "synthesis",
                "assumption_refresh": {
                    "status": "invalidated",
                    "next_step": "Remove from action lane.",
                },
            },
        ],
        "lane_status": {"rows": [{"key": "uw_price", "label": "Prices", "status": "failed"}]},
        "event_risk": [{"severity": "critical", "title": "Critical oil shock", "summary": "Risk changed."}],
        "feedback": {"open_actions": {"items": [{"ticker": "GOOGL", "age_days": 6}]}},
        "source_audits": {"cloud_routines": {"failed_latest_count": 1, "line": "latest routine failed"}},
    })

    assert block["status"] == "notify"
    kinds = {row["kind"] for row in block["rows"]}
    assert {
        "blocked_key_action",
        "urgent_invalidation",
        "source_failed",
        "critical_event_risk",
        "stale_open_review",
    } <= kinds
    assert "cloud_routine_failed" not in kinds
    assert {
        row["kind"] for row in block["system_health"]
    } == {"cloud_routine_failed"}
    assert all(row["delivery"] == "eligible_review_only" for row in block["rows"])


def test_alert_policy_flags_stale_fundstrat_calibration_chain():
    block = build_alert_policy({
        "feedback": {
            "source_calls": {
                "calibration": {
                    "status": "stale",
                    "line": "Calibration chain stale: 3d behind; SOURCE CALIB output is provisional.",
                    "worst_days_behind": 3,
                    "stale_hops": ["inbox_log"],
                }
            }
        }
    })

    assert block["status"] == "notify"
    row = block["rows"][0]
    assert row["kind"] == "source_call_calibration_stale"
    assert row["severity"] == "high"
    assert row["source"] == "source_call_calibration"
    assert row["title"] == "Fundstrat source-call chain is stale"
    assert "SOURCE CALIB output is provisional" in row["why"]
    assert "days_behind=3" in row["trigger"]
    assert "Source Call Log" in row["next_step"]


def test_alert_policy_uses_today_dossier_blockers_for_open_now_cards_only():
    block = build_alert_policy({
        "today_decide": {
            "data_health": {
                "items": [
                    {
                        "source": "decision_dossier",
                        "label": "AVGO dossier",
                        "status": "stale",
                        "detail": "AVGO dossier cannot support a capital-action card: price not_checked, timing stale.",
                        "blocks": True,
                        "ticker": "AVGO",
                        "card_ids": ["AVGO-ADD-2026-06-16"],
                    },
                    {
                        "source": "decision_dossier",
                        "label": "MAGS dossier",
                        "status": "stale",
                        "detail": "MAGS dossier is stale.",
                        "blocks": True,
                        "ticker": "MAGS",
                        "card_ids": ["MAGS-ADD-2026-06-16"],
                    },
                ]
            },
            "cards": [
                {
                    "card_id": "AVGO-ADD-2026-06-16",
                    "ticker": "AVGO",
                    "direction": "BUY",
                    "window": {"class": "OPEN-NOW"},
                },
                {
                    "card_id": "MAGS-ADD-2026-06-16",
                    "ticker": "MAGS",
                    "direction": "BUY",
                    "window": {"class": "STAGE-ONLY"},
                },
            ],
        }
    })

    assert block["status"] == "notify"
    rows = [row for row in block["rows"] if row["kind"] == "decision_dossier_freshness_blocker"]
    assert len(rows) == 1
    assert rows[0]["ticker"] == "AVGO"
    assert rows[0]["source"] == "decision_dossier"
    assert "stale/not-checked dossier reads must stay UNKNOWN" in rows[0]["next_step"]
    suppressed = [row for row in block["suppressed"] if row["reason"] == "dossier_dashboard_blocker"]
    assert suppressed and suppressed[0]["count"] == 1
