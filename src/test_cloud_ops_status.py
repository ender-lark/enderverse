from __future__ import annotations

import json
from pathlib import Path

import cloud_ops_status


def test_cloud_ops_status_reports_missing_automation(monkeypatch, tmp_path):
    src = tmp_path / "src"
    src.mkdir()

    monkeypatch.setattr(cloud_ops_status, "_manifest_summary", lambda _src: {
        "valid": True,
        "problems": [],
        "summary": {"routines": 9, "active": 9},
    })
    monkeypatch.setattr(cloud_ops_status.live_status_mod, "live_status", lambda src_dir: {
        "go_live_ready": True,
        "dark_lanes": {"count": 0, "details": []},
        "open_actions": {"count": 0, "tickers": []},
    })

    report = cloud_ops_status.cloud_ops_status(
        src_dir=src,
        automations_dir=tmp_path / "missing_automations",
    )

    assert report["ready_for_unattended_daily_run"] is False
    assert report["cloud_automation"]["installed"] is False
    assert "Daily Codex cloud automation is not installed." in report["gaps"]


def test_cloud_ops_status_accepts_active_named_automation(monkeypatch, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    automation_dir = tmp_path / "automations" / "daily"
    automation_dir.mkdir(parents=True)
    (automation_dir / "automation.toml").write_text(
        "\n".join([
            'name = "Investing OS Daily Cloud Refresh"',
            'status = "ACTIVE"',
            'prompt = "Run the Investing OS Daily Cloud Refresh."',
        ]),
        encoding="utf-8",
    )

    monkeypatch.setattr(cloud_ops_status, "_manifest_summary", lambda _src: {
        "valid": True,
        "problems": [],
        "summary": {"routines": 9, "active": 9},
    })
    monkeypatch.setattr(cloud_ops_status.live_status_mod, "live_status", lambda src_dir: {
        "go_live_ready": True,
        "dark_lanes": {"count": 0, "details": []},
        "open_actions": {"count": 0, "tickers": []},
    })

    report = cloud_ops_status.cloud_ops_status(
        src_dir=src,
        automations_dir=tmp_path / "automations",
    )

    assert report["ready_for_unattended_daily_run"] is True
    assert report["cloud_automation"]["installed"] is True
    assert report["cloud_automation"]["active"] is True
    assert report["gaps"] == []


def test_cloud_ops_status_keeps_dark_lanes_visible(monkeypatch, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    automation_dir = tmp_path / "automations" / "daily"
    automation_dir.mkdir(parents=True)
    (automation_dir / "automation.toml").write_text(
        'name = "Investing OS Daily Cloud Refresh"\nstatus = "ACTIVE"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(cloud_ops_status, "_manifest_summary", lambda _src: {
        "valid": True,
        "problems": [],
        "summary": {"routines": 9, "active": 9},
    })
    monkeypatch.setattr(cloud_ops_status.live_status_mod, "live_status", lambda src_dir: {
        "go_live_ready": True,
        "dark_lanes": {
            "count": 1,
            "details": [{
                "label": "Signal Log",
                "next_step": "Supply the Morning Scan or Signal Log JSON.",
            }],
        },
        "open_actions": {"count": 0, "tickers": []},
    })

    report = cloud_ops_status.cloud_ops_status(
        src_dir=src,
        automations_dir=tmp_path / "automations",
    )
    text = cloud_ops_status.format_text(report)

    assert report["ready_for_unattended_daily_run"] is True
    assert "Signal Log remains dark" in json.dumps(report["gaps"])
    assert "Signal Log remains dark" in text
