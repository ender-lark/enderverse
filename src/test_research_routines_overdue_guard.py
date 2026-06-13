"""Regression guard for the two off-hours research routines (R2 ghost-routine audit).

Audit finding (2026-06-13): "Off-Hours Research Queue" (weekdays 7:30 PM ET) and
"Top Prospects Auto-Research" (daily 8:45 PM ET) are NOT ghosts. Both are listed
ACTIVE in cloud_automation_status.json, both are wired into the cadence-aware
overdue-alert stack (cloud_ops_status.DEFAULT_EXPECTED_AUTOMATIONS), and both have
emitted scheduled started+success receipts.

This guard locks that wiring in so a future edit cannot silently drop either
routine from the expected-automations list — which would stop overdue detection
and let a silent death go unpaged. It also exercises the real
summarize_due_receipts path to prove that a missing receipt surfaces as overdue.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cloud_ops_status
import cloud_routine_receipts

SRC_DIR = os.path.dirname(os.path.abspath(__file__))

OFF_HOURS_ID = "investing-os-off-hours-research-queue"
TOP_PROSPECTS_ID = "investing-os-top-prospects-auto-research"


def _expected_by_id():
    return {
        str(row.get("automation_id")): row
        for row in cloud_ops_status.DEFAULT_EXPECTED_AUTOMATIONS
    }


def test_both_routines_are_wired_into_overdue_stack():
    expected = _expected_by_id()
    for routine_id in (OFF_HOURS_ID, TOP_PROSPECTS_ID):
        assert routine_id in expected, f"{routine_id} dropped from overdue-alert stack"
        row = expected[routine_id]
        # Cadence fields are what summarize_due_receipts needs to page a silent death.
        assert row.get("days"), f"{routine_id} missing scheduled days"
        assert "hour" in row and "minute" in row, f"{routine_id} missing schedule time"
        assert row.get("expected_since"), f"{routine_id} missing expected_since anchor"


def test_both_routines_are_active_in_automation_status():
    with open(os.path.join(SRC_DIR, "cloud_automation_status.json"), encoding="utf-8") as fh:
        status = json.load(fh)
    by_id = {row.get("automation_id"): row for row in status.get("routines", [])}
    for routine_id in (OFF_HOURS_ID, TOP_PROSPECTS_ID):
        assert by_id.get(routine_id, {}).get("status") == "ACTIVE"


def test_missing_scheduled_receipt_surfaces_as_overdue():
    """A silent death (no scheduled success receipt) must page as overdue."""
    expected = _expected_by_id()
    rows = [expected[OFF_HOURS_ID], expected[TOP_PROSPECTS_ID]]

    # No receipts at all + a clock past Monday's evening slots and grace windows.
    due = cloud_routine_receipts.summarize_due_receipts(
        {"rows": []},
        rows,
        activated_at="2026-06-10T00:00:00-04:00",
        now="2026-06-15T22:30:00-04:00",
    )

    overdue_ids = {row["routine_id"] for row in due["overdue"]}
    assert OFF_HOURS_ID in overdue_ids
    assert TOP_PROSPECTS_ID in overdue_ids


def test_fresh_scheduled_receipt_clears_overdue():
    """A scheduled success after the last due slot clears the overdue state."""
    expected = _expected_by_id()
    rows = [expected[OFF_HOURS_ID]]
    receipt_summary = {
        "rows": [
            {
                "routine_id": OFF_HOURS_ID,
                "last_scheduled_success_at": "2026-06-15T19:31:00-04:00",
                "last_recorded_at": "2026-06-15T19:31:00-04:00",
                "last_status": "success",
            }
        ]
    }

    due = cloud_routine_receipts.summarize_due_receipts(
        receipt_summary,
        rows,
        activated_at="2026-06-10T00:00:00-04:00",
        now="2026-06-15T20:30:00-04:00",
    )

    overdue_ids = {row["routine_id"] for row in due["overdue"]}
    assert OFF_HOURS_ID not in overdue_ids
