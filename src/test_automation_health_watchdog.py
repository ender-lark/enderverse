from __future__ import annotations

import tomllib
from pathlib import Path

import automation_health_watchdog


def _empty_cloud_report() -> dict:
    return {
        "routine_receipts": {"summary": {"failed_latest": []}},
        "support_routine_receipts": {"summary": {"failed_latest": []}},
        "routine_receipt_due": {"overdue": []},
        "support_routine_receipt_due": {"overdue": []},
    }


def _write_automation(
    automations_dir: Path,
    automation_id: str,
    *,
    cwd: Path,
    status: str = "ACTIVE",
    prompt: str = "Run Investing OS cloud_routine automation.",
) -> Path:
    automation_dir = automations_dir / automation_id
    automation_dir.mkdir(parents=True)
    automation_file = automation_dir / "automation.toml"
    escaped_cwd = str(cwd).replace("\\", "\\\\")
    automation_file.write_text(
        "\n".join(
            [
                "version = 1",
                f'id = "{automation_id}"',
                'kind = "cron"',
                f'name = "{automation_id}"',
                f'prompt = "{prompt}"',
                f'status = "{status}"',
                f'cwds = ["{escaped_cwd}"]',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return automation_file


def _canonical_checkout(tmp_path: Path) -> Path:
    canonical = tmp_path / "automation-main"
    safe_helper = canonical / "src" / "cloud_routine_commit.py"
    safe_helper.parent.mkdir(parents=True)
    safe_helper.write_text("# helper marker\n", encoding="utf-8")
    return canonical


def test_watchdog_autofixes_missing_key_cwd(monkeypatch, tmp_path):
    automations_dir = tmp_path / "automations"
    canonical = _canonical_checkout(tmp_path)
    monkeypatch.setattr(
        automation_health_watchdog,
        "_canonical_ready",
        lambda canonical_cwd, fetch=False: {
            "ok": True,
            "cwd": str(canonical_cwd),
        },
    )
    stale_cwd = tmp_path / "missing-stale-checkout"
    automation_file = _write_automation(
        automations_dir,
        "investing-os-morning-scan",
        cwd=stale_cwd,
    )

    report = automation_health_watchdog.audit_automation_health(
        automations_dir=automations_dir,
        canonical_cwd=canonical,
        apply=True,
        cloud_report=_empty_cloud_report(),
    )

    assert report["status"] == "fixed"
    assert report["fixes_applied"][0]["automation_id"] == "investing-os-morning-scan"
    data = tomllib.loads(automation_file.read_text(encoding="utf-8"))
    assert data["cwds"] == [str(canonical.resolve())]


def test_watchdog_does_not_autofix_non_key_automation(monkeypatch, tmp_path):
    automations_dir = tmp_path / "automations"
    canonical = _canonical_checkout(tmp_path)
    monkeypatch.setattr(
        automation_health_watchdog,
        "_canonical_ready",
        lambda canonical_cwd, fetch=False: {
            "ok": True,
            "cwd": str(canonical_cwd),
        },
    )
    stale_cwd = tmp_path / "missing-stale-checkout"
    automation_file = _write_automation(
        automations_dir,
        "custom-investing-os-monitor",
        cwd=stale_cwd,
    )

    report = automation_health_watchdog.audit_automation_health(
        automations_dir=automations_dir,
        canonical_cwd=canonical,
        apply=True,
        include_all_active=True,
        cloud_report=_empty_cloud_report(),
    )

    assert report["status"] == "needs_attention"
    assert report["fixes_applied"] == []
    data = tomllib.loads(automation_file.read_text(encoding="utf-8"))
    assert data["cwds"] == [str(stale_cwd)]


def test_watchdog_reports_failed_and_overdue_receipts(tmp_path):
    automations_dir = tmp_path / "automations"
    canonical = _canonical_checkout(tmp_path)
    cloud_report = _empty_cloud_report()
    cloud_report["routine_receipts"]["summary"]["failed_latest"] = [
        {
            "routine_id": "investing-os-daily-synthesis",
            "status": "failed",
            "completed_at": "2026-06-24T09:02:00-04:00",
        }
    ]
    cloud_report["support_routine_receipt_due"]["overdue"] = [
        {
            "routine_id": "life-os-daily-briefing",
            "age_hours": 30,
            "max_age_hours": 28,
        }
    ]

    report = automation_health_watchdog.audit_automation_health(
        automations_dir=automations_dir,
        canonical_cwd=canonical,
        cloud_report=cloud_report,
    )
    text = automation_health_watchdog.format_text(report)

    assert report["status"] == "needs_attention"
    assert len(report["cloud_attention"]) == 2
    assert "failed latest core: investing-os-daily-synthesis" in text
    assert "overdue support: life-os-daily-briefing" in text


def test_watchdog_dry_run_alert_is_opt_in(monkeypatch, tmp_path):
    calls: list[dict] = []

    def fake_send_message(**kwargs):
        calls.append(kwargs)
        return {"dry_run": kwargs["dry_run"]}

    monkeypatch.setattr(
        automation_health_watchdog.pushover_notify,
        "send_message",
        fake_send_message,
    )
    automations_dir = tmp_path / "automations"
    canonical = _canonical_checkout(tmp_path)
    cloud_report = _empty_cloud_report()
    cloud_report["routine_receipts"]["summary"]["failed_latest"] = [
        {
            "routine_id": "investing-os-daily-synthesis",
            "status": "failed",
            "completed_at": "2026-06-24T09:02:00-04:00",
        }
    ]

    no_alert = automation_health_watchdog.audit_automation_health(
        automations_dir=automations_dir,
        canonical_cwd=canonical,
        cloud_report=cloud_report,
    )
    dry_run = automation_health_watchdog.audit_automation_health(
        automations_dir=automations_dir,
        canonical_cwd=canonical,
        dry_run_alert=True,
        cloud_report=cloud_report,
    )

    assert no_alert["pushover"]["attempted"] is False
    assert dry_run["pushover"]["attempted"] is True
    assert calls[0]["dry_run"] is True


def test_default_receipt_attention_path_skips_live_status(monkeypatch, tmp_path):
    def fail_live_status(**_kwargs):
        raise AssertionError("watchdog should not call live_status")

    monkeypatch.setattr(
        automation_health_watchdog.cloud_ops_status.live_status_mod,
        "live_status",
        fail_live_status,
    )
    monkeypatch.setattr(
        automation_health_watchdog.cloud_ops_status,
        "_receipt_summary",
        lambda *_args, **_kwargs: {"summary": {"failed_latest": []}},
    )
    monkeypatch.setattr(
        automation_health_watchdog.cloud_ops_status,
        "_receipt_due_summary",
        lambda *_args, **_kwargs: {"overdue": []},
    )
    monkeypatch.setattr(
        automation_health_watchdog.cloud_ops_status,
        "_proof_metadata",
        lambda _path: {"verified_at": "2026-06-24T00:00:00-04:00"},
    )

    report = automation_health_watchdog.audit_automation_health(
        automations_dir=tmp_path / "automations",
        canonical_cwd=_canonical_checkout(tmp_path),
        src_dir=tmp_path / "src",
    )

    assert report["status"] == "ok"
    assert report["cloud_attention"] == []


def test_replace_cwds_line_adds_missing_field(tmp_path):
    canonical = tmp_path / "automation-main"
    raw = 'name = "Watchdog"\nstatus = "ACTIVE"\n'

    updated = automation_health_watchdog.replace_cwds_line(raw, [canonical])

    data = tomllib.loads(updated)
    assert data["cwds"] == [str(canonical)]
