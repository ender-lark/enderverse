import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import live_status


def _readiness(**overrides):
    base = {
        "go_live_ready": True,
        "rehearsal_ready": True,
        "publish_ready": True,
        "required_inputs_ready": True,
        "live_data_ready": True,
        "actions": 4,
        "research_actions": 0,
        "dark_lane_keys": ["catalysts"],
        "dark_lane_details": [{"key": "catalysts", "next_step": "Supply Catalyst Calendar."}],
        "missing_required_inputs": [],
        "stale_required_inputs": [],
        "missing_minimum_live_inputs": [],
        "invalid_minimum_live_inputs": [],
        "publish_gate_problems": [],
        "build_problem": "",
        "source_capability": {
            "present_inputs": 18,
            "total_inputs": 21,
            "connector_or_api_count": 5,
            "supplied_or_export_count": 8,
            "missing_live_capable_count": 1,
            "missing_live_capable_keys": ["account_positions"],
            "rows": [{
                "key": "account_positions",
                "present": False,
                "source": "broker_position_intake",
                "routine_title": "Broker Position Intake",
                "primary_mode": "supplied_or_export",
                "candidate_paths": ["src/account_positions.json"],
                "missing_behavior": "Account views are not checked; do not imply no account-level breakdown.",
            }],
        },
        "next_steps": ["Review dark lanes."],
    }
    base.update(overrides)
    return base


def _queue(status="done"):
    return {
        "items": [
            {
                "id": "slice",
                "title": "Slice",
                "priority": "P1",
                "status": status,
                "area": "ops",
                "why": "because",
                "done_when": "done",
            }
        ]
    }


def test_build_status_summary_reports_live_with_open_reviews():
    status = live_status.build_status_summary(
        readiness=_readiness(),
        preview={"preview_exists": True, "server_running": True},
        open_store={"opportunities": [{"ticker": "ANET", "status": "open", "first_flagged": "2026-06-05"}]},
        queue=_queue(),
        feed={
            "generated_at": "2026-06-05T10:03:31+00:00",
            "staleness": {
                "stamp": "sourced: uw_price 06-05",
                "entries": [{"source": "uw_price", "date": "2026-06-05"}],
            },
            "lane_status": {"counts": {"has_data": 11}},
            "actions": [{"kind": "event_risk", "what": "Review oil shock", "action_state": "ACT_NOW"}],
            "event_risk": [
                {
                    "title": "Oil shock",
                    "severity": "high",
                    "channels": ["oil"],
                    "tickers": ["XOP"],
                    "source": "Manual",
                    "trigger": "WTI spike",
                }
            ],
            "feedback": {
                "source_calls": {
                    "status": "not_checked",
                    "line": "Source-call calibration not checked; 3 unscored daily call(s) are flowing.",
                    "observed_count": 3,
                    "pending_count": 0,
                }
            },
        },
    )

    assert status["live_summary"] == "live_with_open_reviews"
    assert status["go_live_ready"] is True
    assert status["open_actions"]["tickers"] == ["ANET"]
    assert status["dark_lanes"]["keys"] == ["catalysts"]
    assert status["data_flow"]["feed_present"] is True
    assert status["data_flow"]["lanes_with_data"] == 11
    assert status["data_flow"]["source_dates"]["uw_price"] == "2026-06-05"
    assert status["data_flow"]["top_action"]["kind"] == "event_risk"
    assert status["data_flow"]["event_watch"]["title"] == "Oil shock"
    assert status["source_calls"]["status"] == "not_checked"
    assert status["source_calls"]["observed_count"] == 3
    assert status["source_capability"]["connector_or_api_count"] == 5


def test_build_status_summary_prioritizes_blocked_state():
    status = live_status.build_status_summary(
        readiness=_readiness(
            go_live_ready=False,
            missing_minimum_live_inputs=[{"key": "macro"}],
        ),
        preview={"preview_exists": True, "server_running": False},
        open_store={"opportunities": []},
        queue=_queue(status="queued"),
    )

    assert status["live_summary"] == "blocked"
    assert status["blockers"]["missing_minimum_live_inputs"] == ["macro"]
    assert status["system_queue"]["active_or_queued"] == 1
    assert status["data_flow"]["feed_present"] is False


def test_build_status_summary_reports_queue_when_live():
    status = live_status.build_status_summary(
        readiness=_readiness(),
        preview={"preview_exists": True, "server_running": True},
        open_store={"opportunities": []},
        queue=_queue(status="queued"),
    )

    assert status["live_summary"] == "live_with_build_queue"
    assert status["system_queue"]["next"][0]["id"] == "slice"


def test_format_text_is_operator_scannable():
    status = live_status.build_status_summary(
        readiness=_readiness(
            dark_lane_keys=["catalysts", "signal_log"],
            dark_lane_details=[
                {"key": "catalysts", "label": "Catalysts", "next_step": "Supply Catalyst Calendar rows."},
                {"key": "signal_log", "label": "Signal Log", "next_step": "Supply Morning Scan JSON."},
            ],
        ),
        preview={
            "preview_exists": True,
            "server_running": True,
            "url": "http://127.0.0.1:8765/dashboard_preview.html",
        },
        open_store={"opportunities": [{"ticker": "ANET", "status": "open", "first_flagged": "2026-06-05"}]},
        queue=_queue(),
        feed={
            "generated_at": "2026-06-05T10:03:31+00:00",
            "lane_status": {"counts": {"has_data": 11}},
            "actions": [{"kind": "event_risk", "what": "Review oil shock"}],
            "event_risk": [
                {
                    "title": "Oil shock",
                    "severity": "high",
                    "channels": ["oil", "rates"],
                    "tickers": ["XOP", "TNX"],
                    "source": "Manual",
                    "trigger": "WTI spike",
                }
            ],
            "feedback": {
                "source_calls": {
                    "status": "not_checked",
                    "line": "Source-call calibration not checked; 3 unscored daily call(s) are flowing.",
                    "observed_count": 3,
                    "pending_count": 0,
                }
            },
        },
    )

    text = live_status.format_text(status)

    assert "Live status: live_with_open_reviews" in text
    assert "Ready: True" in text
    assert "Data flow: feed=2026-06-05T10:03:31+00:00" in text
    assert "top_action=event_risk: Review oil shock" in text
    assert "Source calls: not_checked | new=3 | scoring=0 | overdue=0" in text
    assert "Live source capability: inputs=18/21 | connector_or_api=5 | supplied_or_export=8 | missing_live_capable=1" in text
    assert "- account_positions: Broker Position Intake | supplied_or_export | broker_position_intake" in text
    assert "missing behavior: Account views are not checked" in text
    assert "expected path: src/account_positions.json" in text
    assert "Active event watch: high | Oil shock | channels=oil, rates | tickers=XOP, TNX | trigger=WTI spike" in text
    assert "Sudden event command:" in text
    assert "python src/sudden_event_refresh.py --title \"<event headline>\"" in text
    assert "Open review tickers: ANET" in text
    assert "Open review commands:" in text
    assert "python src/action_memory_resolve.py --review-report" in text
    assert 'python src/action_memory_resolve.py --ticker ANET --status deferred --reason "keep watching"' in text
    assert 'python src/action_memory_resolve.py --ticker ANET --status ignored --reason "no edge"' in text
    assert 'python src/action_memory_resolve.py --ticker ANET --status acted --reason "operator acted"' in text
    assert "- Catalysts: Supply Catalyst Calendar rows." in text
    assert "- Signal Log: Supply Morning Scan JSON." in text
    assert "Dark lane intake commands:" in text
    assert "- Start template: docs/manual_drop.template.json" in text
    assert "Catalysts apply: python src/catalyst_calendar_intake.py <catalyst-calendar.json> --out src/catalysts.json --summary src/catalyst_intake_summary.json --merge-existing" in text
    assert "Signal Log apply: python src/signal_log_intake.py <signal-log.json> --out src/signal_log.json --summary src/signal_log_intake_summary.json --merge-existing" in text
    assert "Catalysts validate: python src/manual_source_drop.py <manual-drop.json> --src-dir src --validate-only" in text
    assert "Catalysts apply: python src/manual_source_drop.py <manual-drop.json> --src-dir src" in text


def test_format_text_points_live_source_dark_lanes_at_live_template():
    status = live_status.build_status_summary(
        readiness=_readiness(
            dark_lane_keys=["account_positions", "meridian"],
            dark_lane_details=[
                {
                    "key": "account_positions",
                    "label": "Account Positions",
                    "next_step": "Supply src/account_positions.json.",
                },
                {
                    "key": "meridian",
                    "label": "Meridian",
                    "next_step": "Supply src/meridian_items.json.",
                },
            ],
        ),
        preview={
            "preview_exists": True,
            "server_running": True,
            "url": "http://127.0.0.1:8765/dashboard_preview.html",
        },
        open_store={"opportunities": []},
        queue=_queue(),
    )

    text = live_status.format_text(status)

    assert "- Start template: docs/manual_live_source_drop.template.json" in text
    assert "docs/manual_drop.template.json" not in text
    assert "Account Positions validate: python src/manual_source_drop.py docs/manual_live_source_drop.template.json --src-dir src --validate-only" in text
    assert "Account Positions apply: python src/manual_source_drop.py docs/manual_live_source_drop.template.json --src-dir src" in text
    assert "Meridian validate: python src/manual_source_drop.py docs/manual_live_source_drop.template.json --src-dir src --validate-only" in text
    assert "Meridian apply: python src/manual_source_drop.py docs/manual_live_source_drop.template.json --src-dir src" in text
