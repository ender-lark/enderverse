from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cloud_routine_drill
import cloud_routine_receipts


def test_drill_writes_scheduled_temp_receipts_without_touching_real_store(tmp_path):
    real = tmp_path / "real_receipts.json"
    cloud_routine_receipts.append_receipt(
        path=real,
        routine_id="investing-os-post-close-refresh",
        status="success",
        run_source="manual",
        summary="manual rehearsal",
        recorded_at="2026-06-05T12:00:00Z",
    )
    before = real.read_text(encoding="utf-8")

    report = cloud_routine_drill.run_drill(real_receipt_path=real)

    assert report["valid"] is True
    assert report["routine_id"] == "all_expected"
    assert report["routine_count"] == len(cloud_routine_drill.cloud_ops_status.DEFAULT_EXPECTED_AUTOMATIONS)
    assert report["real_receipt_untouched"] is True
    assert report["temp_receipt_count"] == 20
    assert report["scheduled_success_count"] == 10
    assert report["failed_latest_count"] == 0
    assert real.read_text(encoding="utf-8") == before


def test_drill_can_limit_to_one_routine(tmp_path):
    real = tmp_path / "real_receipts.json"

    report = cloud_routine_drill.run_drill(
        routine_id="investing-os-post-close-refresh",
        real_receipt_path=real,
    )

    assert report["valid"] is True
    assert report["routine_id"] == "investing-os-post-close-refresh"
    assert report["routine_count"] == 1
    assert report["temp_receipt_count"] == 2
    assert report["scheduled_success_count"] == 1


def test_drill_reports_missing_real_store_as_untouched(tmp_path):
    real = tmp_path / "missing_receipts.json"

    report = cloud_routine_drill.run_drill(real_receipt_path=real)

    assert report["valid"] is True
    assert report["real_receipt_untouched"] is True
    assert not real.exists()


def test_drill_cli_text(tmp_path):
    real = tmp_path / "real_receipts.json"
    script = os.path.join(os.path.dirname(__file__), "cloud_routine_drill.py")

    proc = subprocess.run(
        [sys.executable, script, "--real-receipts", str(real), "--format", "text", "--strict"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    assert "Cloud routine drill valid: True" in proc.stdout
    assert "Routines checked: 10" in proc.stdout
    assert "Real receipt store untouched: True" in proc.stdout


def test_drill_cli_json(tmp_path):
    real = tmp_path / "real_receipts.json"
    script = os.path.join(os.path.dirname(__file__), "cloud_routine_drill.py")

    proc = subprocess.run(
        [sys.executable, script, "--real-receipts", str(real)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["routine_id"] == "all_expected"
    assert payload["scheduled_success_count"] == 10
