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
            "count": 0,
            "keys": [],
        },
        "open_actions": {
            "count": open_count,
            "tickers": ["ANET"] if open_count else [],
        },
    }


def test_build_go_live_checklist_warns_for_open_reviews(monkeypatch, tmp_path):
    monkeypatch.setattr(go_live_checklist.live_status, "live_status", lambda **kwargs: _fake_status(open_count=1))
    monkeypatch.setattr(
        go_live_checklist.action_memory_resolve,
        "review_report",
        lambda **kwargs: {"open_count": 1, "oldest_age_days": 2},
    )

    report = go_live_checklist.build_go_live_checklist(src_dir=tmp_path)

    assert report["status"] == "warn"
    assert report["go_live_ready"] is True
    assert any(row["key"] == "open_reviews" and row["status"] == "warn" for row in report["rows"])


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
