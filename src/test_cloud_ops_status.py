from __future__ import annotations

import json
from pathlib import Path

import cloud_ops_status
import cloud_routine_receipts


def _write_active_stack_proof(src: Path) -> None:
    (src / "cloud_automation_status.json").write_text(
        json.dumps({
            "schema_version": 2,
            "verified_at": "2026-06-05T12:16:06-04:00",
            "routines": [
                {
                    "automation_id": row["automation_id"],
                    "automation_name": row["automation_name"],
                    "status": "ACTIVE",
                    "role": row["role"],
                    "schedule": row["schedule"],
                }
                for row in cloud_ops_status.DEFAULT_EXPECTED_AUTOMATIONS
            ],
        }),
        encoding="utf-8",
    )


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
        now="2026-06-05T12:20:00-04:00",
    )

    assert report["ready_for_unattended_daily_run"] is False
    assert report["cloud_automation"]["installed"] is False
    assert any("routine stack is incomplete" in gap for gap in report["gaps"])


def test_automation_summary_accepts_active_named_automation(monkeypatch, tmp_path):
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

    report = cloud_ops_status._automation_summary(
        automations_dir=tmp_path / "automations",
        expected_automations=[{
            "automation_id": "investing-os-daily-cloud-refresh",
            "automation_name": "Investing OS Daily Cloud Refresh",
            "role": "daily_cloud_refresh",
            "schedule": "",
        }],
    )

    assert report["installed"] is True
    assert report["active"] is True


def test_automation_summary_defaults_to_codex_home_when_env_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    automation_dir = tmp_path / ".codex" / "automations" / "daily"
    automation_dir.mkdir(parents=True)
    (automation_dir / "automation.toml").write_text(
        "\n".join([
            'name = "Investing OS Daily Cloud Refresh"',
            'status = "ACTIVE"',
        ]),
        encoding="utf-8",
    )

    report = cloud_ops_status._automation_summary(
        expected_automations=[{
            "automation_id": "investing-os-daily-cloud-refresh",
            "automation_name": "Investing OS Daily Cloud Refresh",
            "role": "daily_cloud_refresh",
            "schedule": "",
        }],
    )

    assert report["automations_dir"] == str(tmp_path / ".codex" / "automations")
    assert report["active"] is True


def test_cloud_ops_status_accepts_app_created_routine_stack_proof(monkeypatch, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _write_active_stack_proof(src)

    monkeypatch.setattr(cloud_ops_status, "_manifest_summary", lambda _src: {
        "valid": True,
        "problems": [],
        "summary": {"routines": 9, "active": 9},
    })
    monkeypatch.setattr(cloud_ops_status.live_status_mod, "live_status", lambda src_dir: {
        "go_live_ready": True,
        "dark_lanes": {"count": 0, "details": []},
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
        "open_actions": {"count": 0, "tickers": []},
    })

    report = cloud_ops_status.cloud_ops_status(
        src_dir=src,
        automations_dir=tmp_path / "missing_automations",
    )
    text = cloud_ops_status.format_text(report)

    assert report["ready_for_unattended_daily_run"] is True
    assert report["schedule_ready_for_unattended_run"] is True
    assert report["first_scheduled_run_proven"] is False
    assert report["live_run_proven"] is False
    assert report["cloud_operating_state"] == "ready_pending_first_success"
    assert report["routine_receipt_due"]["overdue_count"] == 0
    assert report["routine_receipt_due"]["next_due"]["routine_id"] == "investing-os-post-close-refresh"
    assert report["cloud_automation"]["installed"] is True
    assert report["cloud_automation"]["active"] is True
    assert report["cloud_automation"]["expected_count"] == len(cloud_ops_status.DEFAULT_EXPECTED_AUTOMATIONS)
    assert report["cloud_automation"]["active_count"] == len(cloud_ops_status.DEFAULT_EXPECTED_AUTOMATIONS)
    assert report["cloud_automation"]["matches"][0]["evidence_type"] == "repo_proof"
    assert report["source_capability"]["connector_or_api_count"] == 5
    assert "Live source capability: inputs=18/21 | connector_or_api=5 | supplied_or_export=8 | missing_live_capable=1" in text
    assert "- account_positions: Broker Position Intake | supplied_or_export | broker_position_intake" in text
    assert "missing behavior: Account views are not checked" in text
    assert "Cloud runner drill: python src/cloud_routine_drill.py --format text --strict" in text
    assert report["gaps"] == []


def test_cloud_ops_status_requires_live_source_config_for_schedule_ready(monkeypatch, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _write_active_stack_proof(src)

    monkeypatch.setattr(cloud_ops_status, "_manifest_summary", lambda _src: {
        "valid": True,
        "problems": [],
        "summary": {"routines": 9, "active": 9},
    })
    monkeypatch.setattr(cloud_ops_status.live_status_mod, "live_status", lambda src_dir: {
        "go_live_ready": True,
        "dark_lanes": {"count": 0, "details": []},
        "source_capability": {
            "present_inputs": 19,
            "total_inputs": 21,
            "connector_or_api_count": 14,
            "supplied_or_export_count": 18,
            "missing_live_capable_count": 0,
            "live_source_config": {
                "total_count": 1,
                "configured_count": 0,
                "missing_count": 1,
                "stale_count": 1,
                "missing": [{
                    "key": "uw_api_key",
                    "label": "Unusual Whales live access",
                    "env_var": "UW_API_KEY",
                    "connector_key": "unusual_whales",
                    "connector_available": True,
                    "connector_proof_fresh": False,
                    "connector_proof_age_hours": 48.0,
                    "connector_proof_max_age_hours": 36,
                    "affected_inputs": ["uw_opportunity", "parabolic"],
                    "impact": "Live UW opportunity/parabolic fetches cannot run.",
                }],
            },
            "rows": [],
        },
        "open_actions": {"count": 0, "tickers": []},
    })

    report = cloud_ops_status.cloud_ops_status(
        src_dir=src,
        automations_dir=tmp_path / "missing_automations",
        now="2026-06-05T12:20:00-04:00",
    )
    text = cloud_ops_status.format_text(report)

    assert report["ready_for_unattended_daily_run"] is False
    assert report["schedule_ready_for_unattended_run"] is False
    assert report["cloud_operating_state"] == "not_ready"
    assert "Live source config: configured=0/1 | missing=1 | stale=1" in text
    assert "Unusual Whales live access configuration missing" in "\n".join(report["gaps"])


def test_cloud_ops_status_rejects_active_superseded_automation(monkeypatch, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _write_active_stack_proof(src)
    payload = json.loads((src / "cloud_automation_status.json").read_text(encoding="utf-8"))
    payload["superseded"] = [{
        "automation_id": "investing-os-daily-full-build",
        "automation_name": "Investing OS Daily Full Build",
        "status": "PAUSED",
        "role": "legacy_unreceipted_full_build",
    }]
    (src / "cloud_automation_status.json").write_text(json.dumps(payload), encoding="utf-8")
    automation_dir = tmp_path / "automations" / "investing-os-daily-full-build"
    automation_dir.mkdir(parents=True)
    (automation_dir / "automation.toml").write_text(
        "\n".join([
            'id = "investing-os-daily-full-build"',
            'name = "Investing OS Daily Full Build"',
            'status = "ACTIVE"',
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
        now="2026-06-05T12:20:00-04:00",
    )
    text = cloud_ops_status.format_text(report)

    assert report["ready_for_unattended_daily_run"] is False
    assert report["cloud_automation"]["active_superseded_count"] == 1
    assert any("schedule conflicts" in gap for gap in report["gaps"])
    assert "active_superseded=1" in text


def test_cloud_ops_status_rejects_active_prompt_without_receipt_protocol(monkeypatch, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _write_active_stack_proof(src)
    automation_dir = tmp_path / "automations" / "investing-os-morning-scan"
    automation_dir.mkdir(parents=True)
    (automation_dir / "automation.toml").write_text(
        "\n".join([
            'id = "investing-os-morning-scan"',
            'name = "Investing OS Morning Scan"',
            'status = "ACTIVE"',
            'prompt = "Run the morning scan."',
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
        now="2026-06-05T12:20:00-04:00",
    )
    text = cloud_ops_status.format_text(report)

    assert report["ready_for_unattended_daily_run"] is False
    assert report["cloud_automation"]["prompt_protocol"]["missing_count"] == 1
    assert any("Investing OS Morning Scan is missing cloud receipt protocol" in gap for gap in report["gaps"])
    assert "Cloud receipt protocol: checked=1 | ok=0 | missing=1" in text


def test_cloud_ops_status_validates_prompt_writeback_and_source_honesty(tmp_path):
    automation_dir = tmp_path / "automations" / "investing-os-morning-scan"
    automation_dir.mkdir(parents=True)
    good_prompt = (
        "First append a started receipt with: python src/cloud_routine_receipts.py "
        "--routine-id investing-os-morning-scan --status started --run-source scheduled "
        "--summary \"started\". At the end append a success or failed receipt. "
        "Do not invent missing data; missing pulls stay dark/not_checked, never checked clear. "
        "Commit and push src/cloud_routine_receipts.json plus output files if changed with "
        "python src/cloud_routine_commit.py --message \"run\" --push --format text; "
        "if push fails, report it."
    )
    (automation_dir / "automation.toml").write_text(
        "\n".join([
            'id = "investing-os-morning-scan"',
            'name = "Investing OS Morning Scan"',
            'status = "ACTIVE"',
            f"prompt = {json.dumps(good_prompt)}",
        ]),
        encoding="utf-8",
    )

    report = cloud_ops_status._automation_summary(
        automations_dir=tmp_path / "automations",
        expected_automations=[{
            "automation_id": "investing-os-morning-scan",
            "automation_name": "Investing OS Morning Scan",
            "role": "morning_scan",
            "schedule": "",
        }],
    )

    protocol = report["prompt_protocol"]["rows"][0]
    assert protocol["ok"] is True
    assert protocol["has_writeback"] is True
    assert protocol["has_safe_commit_helper"] is True
    assert protocol["has_source_honesty"] is True


def test_cloud_ops_status_rejects_prompt_without_writeback_or_source_honesty(tmp_path):
    automation_dir = tmp_path / "automations" / "investing-os-morning-scan"
    automation_dir.mkdir(parents=True)
    prompt = (
        "First append a started receipt with: python src/cloud_routine_receipts.py "
        "--routine-id investing-os-morning-scan --status started --run-source scheduled "
        "--summary \"started\". At the end append a success or failed receipt."
    )
    (automation_dir / "automation.toml").write_text(
        "\n".join([
            'id = "investing-os-morning-scan"',
            'name = "Investing OS Morning Scan"',
            'status = "ACTIVE"',
            f"prompt = {json.dumps(prompt)}",
        ]),
        encoding="utf-8",
    )

    report = cloud_ops_status._automation_summary(
        automations_dir=tmp_path / "automations",
        expected_automations=[{
            "automation_id": "investing-os-morning-scan",
            "automation_name": "Investing OS Morning Scan",
            "role": "morning_scan",
            "schedule": "",
        }],
    )

    protocol = report["prompt_protocol"]["rows"][0]
    assert protocol["ok"] is False
    assert protocol["has_writeback"] is False
    assert protocol["has_safe_commit_helper"] is False
    assert protocol["has_source_honesty"] is False
    assert "commit/push write-back protocol" in protocol["problem"]
    assert "safe routine-owned commit helper" in protocol["problem"]
    assert "missing-source honesty guard" in protocol["problem"]


def test_cloud_ops_status_reports_live_run_proven_after_all_success_receipts(monkeypatch, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _write_active_stack_proof(src)
    for row in cloud_ops_status.DEFAULT_EXPECTED_AUTOMATIONS:
        cloud_routine_receipts.append_receipt(
            path=src / "cloud_routine_receipts.json",
            routine_id=row["automation_id"],
            status="success",
            run_source="scheduled",
            summary=f"{row['automation_name']} succeeded.",
            recorded_at="2026-06-05T12:00:00Z",
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
        automations_dir=tmp_path / "missing_automations",
        now="2026-06-05T12:20:00-04:00",
    )
    text = cloud_ops_status.format_text(report)

    assert report["ready_for_unattended_daily_run"] is True
    assert report["first_scheduled_run_proven"] is True
    assert report["live_run_proven"] is True
    assert report["cloud_operating_state"] == "live_run_proven"
    assert "Cloud first scheduled run proven: True" in text
    assert "Cloud live-run proven: True" in text


def test_cloud_ops_status_reports_partial_live_run_after_first_scheduled_success(monkeypatch, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _write_active_stack_proof(src)
    cloud_routine_receipts.append_receipt(
        path=src / "cloud_routine_receipts.json",
        routine_id="investing-os-post-close-refresh",
        status="success",
        run_source="scheduled",
        summary="post-close refresh succeeded",
        recorded_at="2026-06-05T20:35:00Z",
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
        automations_dir=tmp_path / "missing_automations",
        now="2026-06-05T16:40:00-04:00",
    )
    text = cloud_ops_status.format_text(report)

    assert report["ready_for_unattended_daily_run"] is True
    assert report["first_scheduled_run_proven"] is True
    assert report["live_run_proven"] is False
    assert report["cloud_operating_state"] == "partial_live_run_proven"
    assert report["routine_receipts"]["summary"]["scheduled_success_count"] == 1
    assert "Cloud first scheduled run proven: True" in text
    assert "Cloud live-run proven: False" in text


def test_cloud_ops_status_cli_can_require_first_scheduled_proof(monkeypatch, capsys):
    monkeypatch.setattr(cloud_ops_status, "cloud_ops_status", lambda **kwargs: {
        "ready_for_unattended_daily_run": True,
        "first_scheduled_run_proven": False,
        "live_run_proven": False,
    })

    rc = cloud_ops_status.main(["--require-first-proof"])

    assert rc == 2
    assert '"first_scheduled_run_proven": false' in capsys.readouterr().out


def test_cloud_ops_status_cli_can_require_full_live_run(monkeypatch):
    monkeypatch.setattr(cloud_ops_status, "cloud_ops_status", lambda **kwargs: {
        "ready_for_unattended_daily_run": True,
        "first_scheduled_run_proven": True,
        "live_run_proven": False,
    })

    assert cloud_ops_status.main(["--require-live-run"]) == 3
    assert cloud_ops_status.main(["--require-first-proof"]) == 0


def test_cloud_ops_status_does_not_treat_manual_receipts_as_live_run_proof(monkeypatch, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _write_active_stack_proof(src)
    for row in cloud_ops_status.DEFAULT_EXPECTED_AUTOMATIONS:
        cloud_routine_receipts.append_receipt(
            path=src / "cloud_routine_receipts.json",
            routine_id=row["automation_id"],
            status="success",
            run_source="manual",
            summary=f"{row['automation_name']} manual rehearsal succeeded.",
            recorded_at="2026-06-05T12:00:00Z",
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
        automations_dir=tmp_path / "missing_automations",
        now="2026-06-05T12:20:00-04:00",
    )
    text = cloud_ops_status.format_text(report)

    assert report["ready_for_unattended_daily_run"] is True
    assert report["first_scheduled_run_proven"] is False
    assert report["live_run_proven"] is False
    assert report["cloud_operating_state"] == "ready_pending_first_success"
    assert report["routine_receipts"]["summary"]["success_count"] == len(cloud_ops_status.DEFAULT_EXPECTED_AUTOMATIONS)
    assert report["routine_receipts"]["summary"]["scheduled_success_count"] == 0
    assert report["routine_receipt_due"]["not_due_yet_count"] == len(cloud_ops_status.DEFAULT_EXPECTED_AUTOMATIONS)
    assert "Cloud run receipts: scheduled_success=0/" in text
    assert "not_due_yet=" in text
    assert "First scheduled proof pending: Investing OS Post-Close Refresh" in text


def test_cloud_ops_status_reports_due_waiting_before_grace_expires(monkeypatch, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _write_active_stack_proof(src)

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
        now="2026-06-05T16:40:00-04:00",
    )
    text = cloud_ops_status.format_text(report)

    assert report["ready_for_unattended_daily_run"] is True
    assert report["routine_receipt_due"]["due_waiting_count"] == 1
    assert report["routine_receipt_due"]["due_waiting"][0]["routine_id"] == "investing-os-post-close-refresh"
    assert "Due receipt waiting: Investing OS Post-Close Refresh due at 2026-06-05T16:30:00-04:00" in text
    assert "First scheduled proof pending: waiting for Investing OS Post-Close Refresh scheduled receipt." in text
    assert "has not reached its next scheduled receipt window yet" not in text


def test_cloud_ops_status_keeps_dark_lanes_visible(monkeypatch, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _write_active_stack_proof(src)

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
        automations_dir=tmp_path / "missing_automations",
    )
    text = cloud_ops_status.format_text(report)

    assert report["ready_for_unattended_daily_run"] is True
    assert "Signal Log remains dark" in json.dumps(report["gaps"])
    assert "Signal Log remains dark" in text


def test_cloud_ops_status_surfaces_failed_run_receipt(monkeypatch, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _write_active_stack_proof(src)
    cloud_routine_receipts.append_receipt(
        path=src / "cloud_routine_receipts.json",
        routine_id="investing-os-morning-scan",
        status="failed",
        run_source="scheduled",
        summary="Signal Log connector write failed.",
        recorded_at="2026-06-05T12:00:00Z",
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
        automations_dir=tmp_path / "missing_automations",
        now="2026-06-05T17:10:00-04:00",
    )
    text = cloud_ops_status.format_text(report)

    assert any("Investing OS Morning Scan latest run receipt failed" in gap for gap in report["gaps"])
    assert "Cloud run receipts: scheduled_success=0/" in text
    assert "failed_latest=1" in text


def test_cloud_ops_status_marks_due_receipt_overdue(monkeypatch, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _write_active_stack_proof(src)

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
        now="2026-06-05T17:10:00-04:00",
    )
    text = cloud_ops_status.format_text(report)

    assert report["ready_for_unattended_daily_run"] is False
    assert report["routine_receipt_due"]["overdue_count"] == 1
    assert report["routine_receipt_due"]["overdue"][0]["routine_id"] == "investing-os-post-close-refresh"
    assert any("Investing OS Post-Close Refresh run receipt is overdue" in gap for gap in report["gaps"])
    assert "Cloud receipt due state: overdue=1" in text
