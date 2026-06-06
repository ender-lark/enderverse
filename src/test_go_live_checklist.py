import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import go_live_checklist


def _fake_cloud(first_proven=False, schedule_ready=True):
    return {
        "schedule_ready_for_unattended_run": schedule_ready,
        "first_scheduled_run_proven": first_proven,
        "cloud_operating_state": "partial_live_run_proven" if first_proven else "ready_pending_first_success",
        "routine_receipts": {
            "summary": {
                "scheduled_success_count": 1 if first_proven else 0,
                "expected_count": 10,
            }
        },
        "routine_receipt_due": {
            "next_due": {
                "routine_name": "Investing OS Post-Close Refresh",
                "next_due_at": "2026-06-05T16:30:00-04:00",
            }
        },
    }


@pytest.fixture(autouse=True)
def _patch_cloud_status(monkeypatch):
    monkeypatch.setattr(go_live_checklist.cloud_ops_status, "cloud_ops_status", lambda **kwargs: _fake_cloud())


def _fake_status(open_count=0, ready=True):
    return {
        "go_live_ready": ready,
        "live_data_ready": ready,
        "live_summary": "live_clear" if ready else "blocked",
        "actions": 4,
        "research_actions": 0,
        "preview": {
            "preview_exists": True,
            "server_running": True,
            "url": "http://127.0.0.1:8765/dashboard_preview.html",
        },
        "system_queue": {
            "valid": True,
            "items": 21,
            "active_or_queued": 0,
        },
        "dark_lanes": {
            "count": 1,
            "keys": ["catalysts"],
            "details": [
                {
                    "key": "catalysts",
                    "label": "Catalysts",
                    "next_step": "Supply Catalyst Calendar rows.",
                }
            ],
        },
        "open_actions": {
            "count": open_count,
            "tickers": ["ANET"] if open_count else [],
        },
        "data_flow": {
            "feed_present": ready,
            "generated_at": "2026-06-05T10:03:31+00:00" if ready else "",
            "lanes_with_data": 11 if ready else 0,
            "dark_lanes": 2,
            "top_action": {"kind": "event_risk"} if ready else {},
            "event_watch": {
                "active": True,
                "title": "Oil shock",
                "severity": "high",
                "channels": ["oil", "rates"],
                "tickers": ["XOP", "TNX"],
                "trigger": "WTI spike",
            } if ready else {},
        },
        "source_calls": {
            "status": "not_checked",
            "line": "Source-call calibration not checked; 3 unscored daily call(s) are flowing.",
            "observed_count": 3,
            "pending_count": 0,
            "overdue_count": 0,
        },
        "source_capability": {
            "valid": True,
            "present_inputs": 19,
            "total_inputs": 21,
            "missing_live_capable_count": 2,
            "missing_live_capable_keys": ["account_positions", "meridian"],
            "live_source_config": {
                "configured": False,
                "configured_count": 0,
                "total_count": 1,
                "missing_count": 1,
                "missing": [{"key": "uw_api_key", "label": "Unusual Whales API key"}],
            },
        },
    }


def test_build_go_live_checklist_warns_for_open_reviews(monkeypatch, tmp_path):
    monkeypatch.setattr(go_live_checklist.live_status, "live_status", lambda **kwargs: _fake_status(open_count=1))
    monkeypatch.setattr(
        go_live_checklist.action_memory_resolve,
        "review_report",
        lambda **kwargs: {
            "open_count": 1,
            "oldest_age_days": 2,
            "due_count": 1,
            "stale_count": 0,
            "rows": [{"ticker": "ANET"}],
        },
    )

    report = go_live_checklist.build_go_live_checklist(src_dir=tmp_path)

    assert report["status"] == "warn"
    assert report["go_live_ready"] is True
    assert report["operator_summary"]["state"] == "build_ready_with_waits"
    assert report["operator_summary"]["build_blocker_count"] == 0
    assert report["operator_summary"]["waiting_on_source_count"] >= 1
    assert report["operator_summary"]["review_backlog_count"] == 1
    assert any(
        row["key"] == "open_reviews"
        and row["status"] == "warn"
        and "ANET" in row["detail"]
        and "1 due; 0 stale" in row["detail"]
        for row in report["rows"]
    )
    assert any(
        row["key"] == "dark_lanes" and "Supply Catalyst Calendar rows." in row["detail"]
        for row in report["rows"]
    )
    assert any(row["key"] == "data_flow" and row["status"] == "pass" for row in report["rows"])
    assert any(
        row["key"] == "source_capability"
        and row["status"] == "warn"
        and "account_positions, meridian" in row["detail"]
        for row in report["rows"]
    )
    assert any(
        row["key"] == "live_source_config"
        and row["status"] == "warn"
        and "Unusual Whales API key" in row["detail"]
        for row in report["rows"]
    )
    assert any(
        row["key"] == "manual_drop"
        and row["status"] == "warn"
        and "docs/manual_live_source_drop.template.json" in row["detail"]
        and "validate: python src/manual_source_drop.py manual-live-source-drop.json --src-dir src --validate-only" in row["command"]
        and "apply: python src/manual_source_drop.py manual-live-source-drop.json --src-dir src" in row["command"]
        and "<manual-live-source-drop.json>" not in row["command"]
        and "apply: python src/manual_source_drop.py docs/manual_live_source_drop.template.json" not in row["command"]
        for row in report["rows"]
    )
    assert any(
        row["key"] == "cloud_ops"
        and row["status"] == "warn"
        and row["category"] == "natural_schedule"
        and "first_scheduled_proof=False" in row["detail"]
        for row in report["rows"]
    )
    assert any(
        row["key"] == "event_watch" and row["status"] == "pass" and "Oil shock" in row["detail"]
        for row in report["rows"]
    )
    assert any(row["key"] == "source_calls" and row["status"] == "warn" for row in report["rows"])


def test_build_go_live_checklist_keeps_new_open_reviews_visible_without_warning(monkeypatch, tmp_path):
    monkeypatch.setattr(go_live_checklist.live_status, "live_status", lambda **kwargs: _fake_status(open_count=1))
    monkeypatch.setattr(
        go_live_checklist.action_memory_resolve,
        "review_report",
        lambda **kwargs: {
            "open_count": 1,
            "oldest_age_days": 0,
            "due_count": 0,
            "stale_count": 0,
            "rows": [{"ticker": "ANET"}],
        },
    )

    report = go_live_checklist.build_go_live_checklist(src_dir=tmp_path)
    row = next(row for row in report["rows"] if row["key"] == "open_reviews")

    assert row["status"] == "pass"
    assert "ANET" in row["detail"]
    assert "0 due; 0 stale" in row["detail"]
    assert report["operator_summary"]["review_backlog_count"] == 0


def test_build_go_live_checklist_fails_when_readiness_blocked(monkeypatch, tmp_path):
    monkeypatch.setattr(go_live_checklist.live_status, "live_status", lambda **kwargs: _fake_status(ready=False))
    monkeypatch.setattr(
        go_live_checklist.action_memory_resolve,
        "review_report",
        lambda **kwargs: {"open_count": 0, "oldest_age_days": 0},
    )

    report = go_live_checklist.build_go_live_checklist(src_dir=tmp_path)

    assert report["status"] == "fail"
    assert report["fail_count"] >= 1
    assert report["operator_summary"]["state"] == "blocked"
    assert report["operator_summary"]["build_blocker_count"] >= 1


def test_build_go_live_checklist_passes_after_first_cloud_proof(monkeypatch, tmp_path):
    monkeypatch.setattr(go_live_checklist.live_status, "live_status", lambda **kwargs: _fake_status())
    monkeypatch.setattr(
        go_live_checklist.cloud_ops_status,
        "cloud_ops_status",
        lambda **kwargs: _fake_cloud(first_proven=True),
    )
    monkeypatch.setattr(
        go_live_checklist.action_memory_resolve,
        "review_report",
        lambda **kwargs: {"open_count": 0, "oldest_age_days": 0},
    )

    report = go_live_checklist.build_go_live_checklist(src_dir=tmp_path)

    assert any(
        row["key"] == "cloud_ops"
        and row["status"] == "pass"
        and "scheduled_success=1/10" in row["detail"]
        for row in report["rows"]
    )


def test_build_go_live_checklist_passes_when_live_source_coverage_complete(monkeypatch, tmp_path):
    status = _fake_status()
    status["source_capability"] = {
        "valid": True,
        "present_inputs": 21,
        "total_inputs": 21,
        "missing_live_capable_count": 0,
        "missing_live_capable_keys": [],
        "live_source_config": {
            "configured": True,
            "configured_count": 1,
            "total_count": 1,
            "missing_count": 0,
            "missing": [],
        },
    }
    monkeypatch.setattr(go_live_checklist.live_status, "live_status", lambda **kwargs: status)
    monkeypatch.setattr(
        go_live_checklist.action_memory_resolve,
        "review_report",
        lambda **kwargs: {"open_count": 0, "oldest_age_days": 0},
    )

    report = go_live_checklist.build_go_live_checklist(src_dir=tmp_path)

    assert any(
        row["key"] == "source_capability"
        and row["status"] == "pass"
        and "missing_live_capable=0" in row["detail"]
        for row in report["rows"]
    )


def test_build_go_live_checklist_passes_manual_drop_when_no_source_gaps(monkeypatch, tmp_path):
    status = _fake_status()
    status["dark_lanes"] = {"count": 0, "keys": [], "details": []}
    status["source_capability"] = {
        "valid": True,
        "present_inputs": 21,
        "total_inputs": 21,
        "missing_live_capable_count": 0,
        "missing_live_capable_keys": [],
        "live_source_config": {
            "configured": True,
            "configured_count": 1,
            "total_count": 1,
            "missing_count": 0,
            "missing": [],
        },
    }
    monkeypatch.setattr(go_live_checklist.live_status, "live_status", lambda **kwargs: status)
    monkeypatch.setattr(
        go_live_checklist.action_memory_resolve,
        "review_report",
        lambda **kwargs: {"open_count": 0, "oldest_age_days": 0},
    )

    report = go_live_checklist.build_go_live_checklist(src_dir=tmp_path)

    assert any(
        row["key"] == "manual_drop"
        and row["status"] == "pass"
        and "no dark lanes or missing live-capable inputs" in row["detail"]
        for row in report["rows"]
    )


def test_build_go_live_checklist_warns_when_no_event_watch(monkeypatch, tmp_path):
    status = _fake_status()
    status["data_flow"]["event_watch"] = {}
    monkeypatch.setattr(go_live_checklist.live_status, "live_status", lambda **kwargs: status)
    monkeypatch.setattr(
        go_live_checklist.action_memory_resolve,
        "review_report",
        lambda **kwargs: {"open_count": 0, "oldest_age_days": 0},
    )

    report = go_live_checklist.build_go_live_checklist(src_dir=tmp_path)

    assert any(
        row["key"] == "event_watch"
        and row["status"] == "warn"
        and "No supplied active event watch" in row["detail"]
        for row in report["rows"]
    )


def test_build_go_live_checklist_passes_tracked_pending_source_calls(monkeypatch, tmp_path):
    status = _fake_status()
    status["source_calls"] = {
        "status": "has_data",
        "line": "SCORING LAG: clean - no calls past window-end awaiting a score.",
        "observed_count": 0,
        "pending_count": 3,
        "overdue_count": 0,
        "calibration": {"status": "checked_fresh"},
    }
    monkeypatch.setattr(go_live_checklist.live_status, "live_status", lambda **kwargs: status)
    monkeypatch.setattr(
        go_live_checklist.action_memory_resolve,
        "review_report",
        lambda **kwargs: {"open_count": 0, "oldest_age_days": 0},
    )

    report = go_live_checklist.build_go_live_checklist(src_dir=tmp_path)

    assert any(row["key"] == "source_calls" and row["status"] == "pass" for row in report["rows"])


def test_build_go_live_checklist_validates_manual_drop(monkeypatch, tmp_path):
    drop = tmp_path / "manual_drop.json"
    drop.write_text(json.dumps({
        "event_risks": [{"title": "Oil shock", "severity": "high", "source": "Manual"}]
    }), encoding="utf-8")
    monkeypatch.setattr(go_live_checklist.live_status, "live_status", lambda **kwargs: _fake_status())
    monkeypatch.setattr(
        go_live_checklist.action_memory_resolve,
        "review_report",
        lambda **kwargs: {"open_count": 0, "oldest_age_days": 0},
    )

    report = go_live_checklist.build_go_live_checklist(src_dir=tmp_path, manual_drop=drop)

    assert report["manual_drop_checked"] is True
    assert any(row["key"] == "manual_drop" and row["status"] == "pass" for row in report["rows"])
    assert not (tmp_path / "event_risks.json").exists()


def test_format_text_is_human_scannable(monkeypatch, tmp_path):
    monkeypatch.setattr(go_live_checklist.live_status, "live_status", lambda **kwargs: _fake_status(open_count=1))
    monkeypatch.setattr(
        go_live_checklist.action_memory_resolve,
        "review_report",
        lambda **kwargs: {
            "open_count": 1,
            "oldest_age_days": 2,
            "due_count": 1,
            "stale_count": 0,
            "rows": [{"ticker": "ANET"}],
        },
    )
    report = go_live_checklist.build_go_live_checklist(src_dir=tmp_path)

    text = go_live_checklist.format_text(report)

    assert "Go-live checklist: WARN" in text
    assert "Build status: build_ready_with_waits | no build blockers" in text
    assert "source waits=" in text
    assert "schedule waits=1" in text
    assert "review backlog=1" in text
    assert "[PASS] Live data flow" in text
    assert "[WARN] Live source coverage" in text
    assert "[WARN] Live source configuration" in text
    assert "python src/live_source_capability.py --format text" in text
    assert "[WARN] Cloud automation proof" in text
    assert "python src/cloud_ops_status.py --format text" in text
    assert "[WARN] Source-call calibration" in text
    assert "[PASS] Sudden event refresh" in text
    assert "[PASS] Active event watch" in text
    assert "Oil shock" in text
    assert "trigger=WTI spike" in text
    assert "[WARN] Open action reviews" in text
    assert "ANET" in text
    assert "Supply Catalyst Calendar rows." in text
    assert "python src/live_status.py --format text" in text
    assert "python src/sudden_event_refresh.py --title \"<event headline>\"" in text
    assert "validate: python src/manual_source_drop.py manual-live-source-drop.json --src-dir src --validate-only" in text
    assert "apply: python src/manual_source_drop.py manual-live-source-drop.json --src-dir src" in text
    assert "<manual-live-source-drop.json>" not in text
    assert "apply: python src/manual_source_drop.py docs/manual_live_source_drop.template.json" not in text
    assert "python src/action_memory_resolve.py --review-report" in text


def test_go_live_checklist_cli_runs_against_current_repo():
    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / "go_live_checklist.py"),
            "--manual-drop",
            str(Path(__file__).resolve().parents[1] / "docs" / "manual_drop.template.json"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode in {0, 1}
    report = json.loads(proc.stdout)
    assert "rows" in report
    assert any(row["key"] == "manual_drop" for row in report["rows"])


def test_go_live_checklist_cli_text_format_runs_against_current_repo():
    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / "go_live_checklist.py"),
            "--manual-drop",
            str(Path(__file__).resolve().parents[1] / "docs" / "manual_drop.template.json"),
            "--format",
            "text",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    assert "Go-live checklist: WARN" in proc.stdout
    assert "Dashboard preview" in proc.stdout
