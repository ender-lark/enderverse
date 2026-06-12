from __future__ import annotations

import json
import sys

import cloud_routine_manual_run
import cloud_ops_status
import cloud_routine_receipts


def test_manual_stack_records_manual_success_receipts(tmp_path):
    receipts = tmp_path / "receipts.json"
    routine = cloud_routine_manual_run.Routine(
        "test-routine",
        "test routine completed",
        [cloud_routine_manual_run.Step("ok", [sys.executable, "-c", "raise SystemExit(0)"])],
    )

    report = cloud_routine_manual_run.run_manual_stack(
        routines=[routine],
        receipt_path=receipts,
        repo=tmp_path,
    )

    payload = cloud_routine_receipts.load_receipts(receipts)
    assert report["valid"] is True
    assert report["success_count"] == 1
    assert [row["status"] for row in payload["receipts"]] == ["started", "success"]
    assert [row["run_source"] for row in payload["receipts"]] == ["manual", "manual"]


def test_manual_stack_records_failed_routine(tmp_path):
    receipts = tmp_path / "receipts.json"
    routine = cloud_routine_manual_run.Routine(
        "test-routine",
        "test routine completed",
        [cloud_routine_manual_run.Step("bad", [sys.executable, "-c", "raise SystemExit(3)"])],
    )

    report = cloud_routine_manual_run.run_manual_stack(
        routines=[routine],
        receipt_path=receipts,
        repo=tmp_path,
    )

    payload = cloud_routine_receipts.load_receipts(receipts)
    assert report["valid"] is False
    assert report["failed_count"] == 1
    assert payload["receipts"][-1]["status"] == "failed"
    assert payload["receipts"][-1]["run_source"] == "manual"
    assert payload["receipts"][-1]["details"]["steps"][0]["returncode"] == 3


def test_manual_stack_stops_after_required_failure(tmp_path):
    marker = tmp_path / "should_not_run.txt"
    routine = cloud_routine_manual_run.Routine(
        "test-routine",
        "test routine completed",
        [
            cloud_routine_manual_run.Step("bad", [sys.executable, "-c", "raise SystemExit(3)"]),
            cloud_routine_manual_run.Step(
                "must not run",
                [sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')"],
            ),
        ],
    )

    report = cloud_routine_manual_run.run_manual_stack(
        routines=[routine],
        receipt_path=tmp_path / "receipts.json",
        repo=tmp_path,
    )

    assert report["valid"] is False
    assert len(report["routines"][0]["steps"]) == 1
    assert not marker.exists()


def test_manual_stack_unknown_routine_id_fails_without_receipts(tmp_path):
    receipts = tmp_path / "receipts.json"
    routine = cloud_routine_manual_run.Routine(
        "known",
        "known completed",
        [cloud_routine_manual_run.Step("ok", [sys.executable, "-c", "raise SystemExit(0)"])],
    )

    report = cloud_routine_manual_run.run_manual_stack(
        routine_ids=["missing"],
        routines=[routine],
        receipt_path=receipts,
        repo=tmp_path,
    )

    assert report["valid"] is False
    assert "unknown routine id: missing" in json.dumps(report["problems"])
    assert not receipts.exists()


def test_manual_stack_optional_step_does_not_fail_routine(tmp_path):
    routine = cloud_routine_manual_run.Routine(
        "test-routine",
        "test routine completed",
        [
            cloud_routine_manual_run.Step(
                "optional missing bundle",
                check=lambda _repo: {"valid": False, "skipped": True},
                optional=True,
            )
        ],
    )

    report = cloud_routine_manual_run.run_manual_stack(
        routines=[routine],
        receipt_path=tmp_path / "receipts.json",
        repo=tmp_path,
    )

    assert report["valid"] is True
    assert report["success_count"] == 1


def test_empty_uw_bundle_is_not_a_scoring_source(tmp_path):
    empty = tmp_path / "opportunity_bundle.json"
    populated = tmp_path / "parabolic_bundle.json"
    empty.write_text('{"as_of":"2026-06-05","universe":[],"observations":{}}\n', encoding="utf-8")
    populated.write_text('{"as_of":"2026-06-05","tickers":{"NVDA":{}}}\n', encoding="utf-8")

    assert cloud_routine_manual_run._bundle_has_observations(empty) is False
    assert cloud_routine_manual_run._bundle_has_observations(populated, key="tickers") is True


def test_default_manual_routines_cover_expected_cloud_stack():
    manual_ids = {routine.routine_id for routine in cloud_routine_manual_run.default_routines()}
    expected_ids = {row["automation_id"] for row in cloud_ops_status.DEFAULT_EXPECTED_AUTOMATIONS}

    assert expected_ids <= manual_ids
