import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import completion_audit


def _live(*, ready=True, open_tickers=None):
    tickers = ["ANET", "GOOGL"] if open_tickers is None else open_tickers
    return {
        "go_live_ready": ready,
        "actions": 5,
        "research_actions": 0,
        "data_flow": {"generated_at": "2026-06-05T23:30:00+00:00"},
        "open_actions": {
            "tickers": tickers,
            "due_count": 0,
            "stale_count": 0,
            "oldest_age_days": 0,
        },
        "dark_lanes": {"keys": ["account_positions"]},
    }


def _checklist(*, blockers=None, waiting_on_source=None, waiting_on_schedule=None):
    blockers = blockers or []
    waiting_on_source = ["Account Positions"] if waiting_on_source is None else waiting_on_source
    waiting_on_schedule = ["Cloud automation proof"] if waiting_on_schedule is None else waiting_on_schedule
    return {
        "fail_count": len(blockers),
        "operator_summary": {
            "build_blocker_count": len(blockers),
            "build_blockers": blockers,
            "waiting_on_source_count": len(waiting_on_source),
            "waiting_on_source": waiting_on_source,
            "waiting_on_schedule_count": len(waiting_on_schedule),
            "waiting_on_schedule": waiting_on_schedule,
            "monitoring_warning_count": 0,
        },
    }


def _cloud(*, scheduled=3, expected=10, live_run=False, overdue=0):
    return {
        "first_scheduled_run_proven": scheduled > 0,
        "live_run_proven": live_run,
        "routine_receipts": {
            "summary": {
                "scheduled_success_count": scheduled,
                "expected_count": expected,
                "missing_scheduled_success_count": max(expected - scheduled, 0),
                "failed_latest_count": 0,
            }
        },
        "routine_receipt_due": {
            "overdue_count": overdue,
            "due_waiting_count": 0,
            "next_due": {
                "routine_name": "Investing OS Off-Hours Worker",
                "next_due_at": "2026-06-06T01:45:00-04:00",
            },
        },
    }


def _queue(status="done"):
    return {
        "items": [
            {
                "id": "slice",
                "title": "Slice",
                "priority": "P1",
                "status": status,
                "area": "ops",
                "why": "because",
                "done_when": "done",
            }
        ]
    }


def _patch(monkeypatch, *, live=None, checklist=None, cloud=None, queue=None):
    monkeypatch.setattr(completion_audit.live_status, "live_status", lambda **kwargs: live or _live())
    monkeypatch.setattr(
        completion_audit.go_live_checklist,
        "build_go_live_checklist",
        lambda **kwargs: checklist or _checklist(),
    )
    monkeypatch.setattr(completion_audit.cloud_ops_status, "cloud_ops_status", lambda **kwargs: cloud or _cloud())
    monkeypatch.setattr(completion_audit.system_improvement_queue, "load_queue", lambda path: queue or _queue())


def test_completion_audit_reports_clear_build_with_external_waits(monkeypatch, tmp_path):
    _patch(monkeypatch)

    report = completion_audit.build_completion_audit(src_dir=tmp_path)
    text = completion_audit.format_text(report)

    assert report["state"] == "build_clear_waiting_external"
    assert report["build_clear"] is True
    assert report["all_clear"] is False
    assert report["build_blocker_count"] == 0
    assert report["waiting_on_source"] == ["Account Positions"]
    assert report["cloud"]["scheduled_success"] == 3
    assert report["system_queue"]["valid"] is True
    assert report["open_review_tickers"] == ["ANET", "GOOGL"]
    assert report["open_review_due_count"] == 0
    assert report["open_review_stale_count"] == 0
    assert "Completion audit: BUILD_CLEAR_WAITING_EXTERNAL" in text
    assert "Build clear: True | all clear: False" in text
    assert "Cloud proof: 3/10 scheduled" in text
    assert "Open reviews: ANET, GOOGL | due=0 | stale=0 | oldest=0d" in text
    assert "Queue: valid=True" in text
    assert "Next: No code blocker; wait for or supply source input: Account Positions." in text


def test_completion_audit_prioritizes_build_blocker(monkeypatch, tmp_path):
    _patch(
        monkeypatch,
        live=_live(ready=False, open_tickers=[]),
        checklist=_checklist(blockers=["Live data flow"]),
    )

    report = completion_audit.build_completion_audit(src_dir=tmp_path)

    assert report["state"] == "blocked"
    assert report["build_clear"] is False
    assert report["next_recommended_action"] == "Fix build blocker(s): Live data flow."


def test_completion_audit_promotes_active_queue_before_external_waits(monkeypatch, tmp_path):
    _patch(monkeypatch, queue=_queue(status="queued"))

    report = completion_audit.build_completion_audit(src_dir=tmp_path)

    assert report["state"] == "needs_build_work"
    assert report["build_clear"] is False
    assert report["next_recommended_action"] == "Promote queued slice: slice - Slice."


def test_completion_audit_reports_all_clear_when_external_waits_are_done(monkeypatch, tmp_path):
    live = _live(open_tickers=[])
    live["dark_lanes"] = {"keys": []}
    _patch(
        monkeypatch,
        live=live,
        checklist=_checklist(waiting_on_source=[], waiting_on_schedule=[]),
        cloud=_cloud(scheduled=10, expected=10, live_run=True),
    )

    report = completion_audit.build_completion_audit(src_dir=tmp_path)
    text = completion_audit.format_text(report)

    assert report["state"] == "build_clear"
    assert report["build_clear"] is True
    assert report["all_clear"] is True
    assert "Build clear: True | all clear: True" in text


def test_completion_audit_cli_text_runs_against_current_repo():
    rc = completion_audit.main(["--format", "text"])

    assert rc == 0


def test_completion_audit_cli_require_all_clear_fails_current_repo():
    rc = completion_audit.main(["--require-all-clear"])

    assert rc == 3
