from __future__ import annotations

import sys

import cloud_routine_receipts
import cloud_routine_runner


def test_runner_records_started_and_success(tmp_path):
    receipt_path = tmp_path / "receipts.json"

    result = cloud_routine_runner.run_cloud_routine(
        routine_id="investing-os-post-close-refresh",
        command=[sys.executable, "-c", "print('ok')"],
        receipt_path=receipt_path,
        success_summary="refresh succeeded",
        run_source="scheduled",
    )

    payload = cloud_routine_receipts.load_receipts(receipt_path)
    assert result["returncode"] == 0
    assert [row["status"] for row in payload["receipts"]] == ["started", "success"]
    assert [row["run_source"] for row in payload["receipts"]] == ["scheduled", "scheduled"]
    assert payload["receipts"][1]["summary"] == "refresh succeeded"


def test_runner_records_failure(tmp_path):
    receipt_path = tmp_path / "receipts.json"

    result = cloud_routine_runner.run_cloud_routine(
        routine_id="investing-os-post-close-refresh",
        command=[sys.executable, "-c", "raise SystemExit(3)"],
        receipt_path=receipt_path,
        failure_summary="refresh failed",
        run_source="scheduled",
    )

    payload = cloud_routine_receipts.load_receipts(receipt_path)
    assert result["returncode"] == 3
    assert [row["status"] for row in payload["receipts"]] == ["started", "failed"]
    assert payload["receipts"][1]["run_source"] == "scheduled"
    assert payload["receipts"][1]["details"]["returncode"] == 3


def test_runner_dry_run_records_only_started(tmp_path):
    receipt_path = tmp_path / "receipts.json"

    result = cloud_routine_runner.run_cloud_routine(
        routine_id="investing-os-post-close-refresh",
        command=[sys.executable, "-c", "raise SystemExit(3)"],
        receipt_path=receipt_path,
        dry_run=True,
    )

    payload = cloud_routine_receipts.load_receipts(receipt_path)
    assert result["dry_run"] is True
    assert payload["receipts"] == []
