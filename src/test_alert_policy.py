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
        "cloud_routine_failed",
    } <= kinds
    assert all(row["delivery"] == "eligible_review_only" for row in block["rows"])
