from __future__ import annotations

import json

import cloud_routine_receipts


EXPECTED = [
    {
        "automation_id": "investing-os-morning-scan",
        "automation_name": "Investing OS Morning Scan",
        "role": "morning_scan",
        "schedule": "market weekdays 8:35 AM ET",
    },
    {
        "automation_id": "investing-os-full-cockpit-build",
        "automation_name": "Investing OS Full Cockpit Build",
        "role": "full_cockpit_build",
        "schedule": "market weekdays 10:30 AM ET",
    },
]


def test_append_receipt_writes_valid_store(tmp_path):
    path = tmp_path / "receipts.json"

    receipt = cloud_routine_receipts.append_receipt(
        path=path,
        routine_id="investing-os-morning-scan",
        status="success",
        run_source="scheduled",
        summary="Signal Log rows landed.",
        recorded_at="2026-06-05T12:00:00Z",
    )

    payload = cloud_routine_receipts.load_receipts(path)
    assert receipt["status"] == "success"
    assert receipt["run_source"] == "scheduled"
    assert payload["receipts"][0]["routine_id"] == "investing-os-morning-scan"
    assert cloud_routine_receipts.validate_receipts(payload) == []


def test_load_receipts_accepts_legacy_cp1252_then_normalizes_utf8(tmp_path):
    path = tmp_path / "receipts.json"
    payload = {
        "schema_version": 1,
        "receipts": [
            {
                "routine_id": "investing-os-parabolic-cache",
                "status": "success",
                "run_source": "scheduled",
                "recorded_at": "2026-06-16T14:37:00Z",
                "summary": "PARABOLIC SETUP SCREENER \u2014 2026-06-16",
            }
        ],
    }
    path.write_bytes(json.dumps(payload, indent=2, ensure_ascii=False).encode("cp1252"))

    assert cloud_routine_receipts.load_receipts(path)["receipts"][0]["summary"].startswith("PARABOLIC")
    assert cloud_routine_receipts.validate_receipt_file_encoding(path)

    cloud_routine_receipts.normalize_receipts_file(path)

    assert cloud_routine_receipts.validate_receipt_file_encoding(path) == []
    assert cloud_routine_receipts.load_receipts(path)["receipts"][0]["summary"].endswith("2026-06-16")


def test_summarize_receipts_reports_missing_and_failed(tmp_path):
    path = tmp_path / "receipts.json"
    cloud_routine_receipts.append_receipt(
        path=path,
        routine_id="investing-os-morning-scan",
        status="success",
        run_source="scheduled",
        summary="Rows landed.",
        recorded_at="2026-06-05T12:00:00Z",
    )
    cloud_routine_receipts.append_receipt(
        path=path,
        routine_id="investing-os-full-cockpit-build",
        status="failed",
        run_source="scheduled",
        summary="Connector failed.",
        recorded_at="2026-06-05T14:30:00Z",
    )

    summary = cloud_routine_receipts.summarize_receipts(
        cloud_routine_receipts.load_receipts(path),
        expected_automations=EXPECTED,
    )
    text = cloud_routine_receipts.format_text(summary)

    assert summary["success_count"] == 1
    assert summary["scheduled_success_count"] == 1
    assert summary["failed_latest_count"] == 1
    assert summary["missing_scheduled_success_count"] == 1
    assert summary["failed_latest"][0]["routine_id"] == "investing-os-full-cockpit-build"
    assert "Investing OS Full Cockpit Build: Connector failed." in text


def test_summarize_receipts_adds_boundary_outcomes_without_changing_success_counts(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "old.json").write_text(
        json.dumps({"generated_at": "2026-06-05T12:01:00Z"}),
        encoding="utf-8",
    )
    (src / "cockpit_artifact_boundaries.json").write_text(
        json.dumps({
            "schema_version": 1,
            "artifacts": {
                "src/old.json": {
                    "owner_routine_ids": ["old-v1"],
                    "as_of_field": "generated_at",
                    "freshness": "same_et_session_day",
                }
            },
        }),
        encoding="utf-8",
    )
    expected = [
        {"automation_id": "produced", "automation_name": "Produced", "role": "", "schedule": ""},
        {"automation_id": "noop", "automation_name": "Noop", "role": "", "schedule": ""},
        {"automation_id": "stale", "automation_name": "Stale", "role": "", "schedule": ""},
        {"automation_id": "missing", "automation_name": "Missing", "role": "", "schedule": ""},
        {"automation_id": "old-v1", "automation_name": "Old V1", "role": "", "schedule": ""},
    ]
    payload = {
        "schema_version": 1,
        "receipts": [
            {
                "routine_id": "produced",
                "status": "success",
                "run_source": "scheduled",
                "recorded_at": "2026-06-05T12:00:00Z",
                "details": {
                    "artifact_boundaries": [{
                        "path": "src/produced.json",
                        "present": True,
                        "missing": False,
                        "fresh": True,
                        "changed": True,
                        "content_hash": "new",
                        "previous_content_hash": "old",
                    }]
                },
            },
            {
                "routine_id": "noop",
                "status": "success",
                "run_source": "scheduled",
                "recorded_at": "2026-06-05T12:00:00Z",
                "details": {
                    "artifact_boundaries": [{
                        "path": "src/noop.json",
                        "present": True,
                        "missing": False,
                        "fresh": True,
                        "changed": False,
                        "content_hash": "same",
                        "previous_content_hash": "same",
                    }]
                },
            },
            {
                "routine_id": "stale",
                "status": "success",
                "run_source": "scheduled",
                "recorded_at": "2026-06-05T12:00:00Z",
                "details": {
                    "artifact_boundaries": [{
                        "path": "src/stale.json",
                        "present": True,
                        "missing": False,
                        "fresh": False,
                        "changed": True,
                    }]
                },
            },
            {
                "routine_id": "missing",
                "status": "success",
                "run_source": "scheduled",
                "recorded_at": "2026-06-05T12:00:00Z",
                "details": {
                    "artifact_boundaries": [{
                        "path": "src/missing.json",
                        "present": False,
                        "missing": True,
                        "fresh": False,
                        "changed": False,
                    }]
                },
            },
            {
                "routine_id": "old-v1",
                "status": "success",
                "run_source": "scheduled",
                "recorded_at": "2026-06-05T12:00:00Z",
                "summary": "legacy success with no artifact metadata",
            },
        ],
    }

    summary = cloud_routine_receipts.summarize_receipts(
        payload,
        expected_automations=expected,
        repo_root=tmp_path,
    )

    assert summary["success_count"] == 5
    assert summary["scheduled_success_count"] == 5
    assert summary["produced_fresh_count"] == 1
    assert summary["no_op_count"] == 1
    assert summary["stale_boundary_count"] == 1
    assert summary["missing_count"] == 1
    assert summary["fired_unknown_count"] == 1
    by_id = {row["routine_id"]: row for row in summary["rows"]}
    assert by_id["old-v1"]["last_boundary_outcome"] == "fired_unknown"
    assert "Boundary outcomes: produced_fresh=1/5" in cloud_routine_receipts.format_text(summary)


def test_validate_rejects_bad_status():
    problems = cloud_routine_receipts.validate_receipts({
        "schema_version": 1,
        "receipts": [{"routine_id": "x", "status": "done", "recorded_at": "2026-06-05T12:00:00Z"}],
    })

    assert any("status must be one of" in problem for problem in problems)


def test_manual_success_does_not_count_as_scheduled_success(tmp_path):
    path = tmp_path / "receipts.json"
    cloud_routine_receipts.append_receipt(
        path=path,
        routine_id="investing-os-morning-scan",
        status="success",
        run_source="manual",
        summary="manual rehearsal",
        recorded_at="2026-06-05T12:00:00Z",
    )

    summary = cloud_routine_receipts.summarize_receipts(
        cloud_routine_receipts.load_receipts(path),
        expected_automations=EXPECTED,
    )

    assert summary["success_count"] == 1
    assert summary["scheduled_success_count"] == 0
    assert summary["missing_scheduled_success"][0]["routine_id"] == "investing-os-morning-scan"


def test_due_summary_marks_killed_scheduled_routine_overdue():
    expected = [{
        "automation_id": "investing-os-post-close-refresh",
        "automation_name": "Investing OS Post-Close Refresh",
        "role": "post_close_refresh",
        "schedule": "market weekdays 4:30 PM ET",
    }]
    summary = cloud_routine_receipts.summarize_receipts(
        {"schema_version": 1, "receipts": []},
        expected_automations=expected,
    )

    due = cloud_routine_receipts.summarize_due_receipts(
        summary,
        expected,
        activated_at="2026-06-05T12:00:00-04:00",
        now="2026-06-05T17:10:00-04:00",
    )

    assert due["overdue_count"] == 1
    row = due["overdue"][0]
    assert row["routine_id"] == "investing-os-post-close-refresh"
    assert row["last_due_at"] == "2026-06-05T16:30:00-04:00"
    assert row["last_ran_label"] == "never"
    assert row["overdue_line"] == "overdue: Investing OS Post-Close Refresh, last scheduled success never"


def test_due_summary_keeps_manual_support_separate_from_scheduled_proof(tmp_path):
    path = tmp_path / "receipts.json"
    expected = [{
        "automation_id": "investing-os-post-close-refresh",
        "automation_name": "Investing OS Post-Close Refresh",
        "role": "post_close_refresh",
        "schedule": "market weekdays 4:30 PM ET",
    }]
    cloud_routine_receipts.append_receipt(
        path=path,
        routine_id="investing-os-post-close-refresh",
        status="success",
        run_source="manual",
        summary="manual support repaired the cache",
        recorded_at="2026-06-05T20:55:00Z",
    )
    summary = cloud_routine_receipts.summarize_receipts(
        cloud_routine_receipts.load_receipts(path),
        expected_automations=expected,
    )

    due = cloud_routine_receipts.summarize_due_receipts(
        summary,
        expected,
        activated_at="2026-06-05T12:00:00-04:00",
        now="2026-06-05T17:10:00-04:00",
    )

    row = due["overdue"][0]
    assert summary["manual_support_only_count"] == 1
    assert row["last_scheduled_success_label"] == "never"
    assert row["latest_manual_support_label"] == "2026-06-05T20:55:00Z"
    assert (
        row["overdue_line"]
        == "overdue: Investing OS Post-Close Refresh, last scheduled success never; latest manual support 2026-06-05T20:55:00Z"
    )


def test_due_summary_respects_per_routine_max_age():
    expected = [{
        "automation_id": "investing-os-post-close-refresh",
        "automation_name": "Investing OS Post-Close Refresh",
        "role": "post_close_refresh",
        "schedule": "market weekdays 4:30 PM ET",
        "max_age_minutes": 60,
    }]
    summary = cloud_routine_receipts.summarize_receipts(
        {"schema_version": 1, "receipts": []},
        expected_automations=expected,
    )

    due = cloud_routine_receipts.summarize_due_receipts(
        summary,
        expected,
        activated_at="2026-06-05T12:00:00-04:00",
        now="2026-06-05T17:10:00-04:00",
    )

    assert due["overdue_count"] == 0
    assert due["due_waiting_count"] == 1
    assert due["due_waiting"][0]["overdue_after"] == "2026-06-05T17:30:00-04:00"


def test_validate_rejects_bad_run_source():
    problems = cloud_routine_receipts.validate_receipts({
        "schema_version": 1,
        "receipts": [{"routine_id": "x", "status": "success", "run_source": "local", "recorded_at": "2026-06-05T12:00:00Z"}],
    })

    assert any("run_source must be one of" in problem for problem in problems)


def test_cli_records_receipt(tmp_path, capsys):
    path = tmp_path / "receipts.json"

    rc = cloud_routine_receipts.main([
        "--out", str(path),
        "--routine-id", "investing-os-morning-scan",
        "--status", "started",
        "--run-source", "scheduled",
        "--summary", "started run",
        "--format", "json",
    ])

    captured = capsys.readouterr().out
    assert rc == 0
    assert json.loads(captured)["valid"] is True
    assert cloud_routine_receipts.load_receipts(path)["receipts"][0]["status"] == "started"
    assert cloud_routine_receipts.load_receipts(path)["receipts"][0]["run_source"] == "scheduled"
