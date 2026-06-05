import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import go_live_checklist


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
        },
        "source_calls": {
            "status": "not_checked",
            "line": "Source-call calibration not checked; 3 unscored daily call(s) are flowing.",
            "observed_count": 3,
            "pending_count": 0,
            "overdue_count": 0,
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
            "rows": [{"ticker": "ANET"}],
        },
    )

    report = go_live_checklist.build_go_live_checklist(src_dir=tmp_path)

    assert report["status"] == "warn"
    assert report["go_live_ready"] is True
    assert any(
        row["key"] == "open_reviews" and row["status"] == "warn" and "ANET" in row["detail"]
        for row in report["rows"]
    )
    assert any(
        row["key"] == "dark_lanes" and "Supply Catalyst Calendar rows." in row["detail"]
        for row in report["rows"]
    )
    assert any(row["key"] == "data_flow" and row["status"] == "pass" for row in report["rows"])
    assert any(row["key"] == "source_calls" and row["status"] == "warn" for row in report["rows"])


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
            "rows": [{"ticker": "ANET"}],
        },
    )
    report = go_live_checklist.build_go_live_checklist(src_dir=tmp_path)

    text = go_live_checklist.format_text(report)

    assert "Go-live checklist: WARN" in text
    assert "[PASS] Live data flow" in text
    assert "[WARN] Source-call calibration" in text
    assert "[WARN] Open action reviews" in text
    assert "ANET" in text
    assert "Supply Catalyst Calendar rows." in text
    assert "python src/live_status.py --format text" in text
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
