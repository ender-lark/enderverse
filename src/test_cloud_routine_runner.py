from __future__ import annotations

import json
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


def test_runner_records_boundary_artifact_metadata(tmp_path):
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    receipt_path = src / "cloud_routine_receipts.json"
    (src / "cockpit_artifact_boundaries.json").write_text(
        json.dumps({
            "schema_version": 1,
            "artifacts": {
                "src/boundary.json": {
                    "owner_routine_ids": ["boundary-routine"],
                    "as_of_field": "generated_at",
                    "freshness": "same_et_session_day",
                }
            },
        }),
        encoding="utf-8",
    )

    result = cloud_routine_runner.run_cloud_routine(
        routine_id="boundary-routine",
        command=[
            sys.executable,
            "-c",
            (
                "import datetime, json, pathlib; "
                "pathlib.Path('src/boundary.json').write_text("
                "json.dumps({'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}), "
                "encoding='utf-8')"
            ),
        ],
        cwd=repo,
        receipt_path=receipt_path,
        success_summary="boundary succeeded",
        run_source="scheduled",
    )

    payload = cloud_routine_receipts.load_receipts(receipt_path)
    final = payload["receipts"][1]
    artifact = final["details"]["artifact_boundaries"][0]
    assert result["boundary_outcome"] == "produced_fresh"
    assert final["boundary_outcome"] == "produced_fresh"
    assert artifact["path"] == "src/boundary.json"
    assert artifact["changed"] is True
    assert artifact["fresh"] is True
    assert artifact["content_hash"]
