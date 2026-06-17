from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from life_work_os_briefing import (
    SourceRequest,
    deadline_warning_ladder,
    effective_routine,
    filter_for_source,
    _item_from_page,
    _format_text,
)
from life_work_os_config import DAILY_LIFE, DAILY_WORK
from life_work_os_heartbeat import evaluate_staleness
from life_work_os_hygiene import (
    _format_text as _hygiene_format_text,
    plan_duplicate_cancellations,
    plan_finance_source_project_backfill,
    plan_orphan_inbox_recovery,
    plan_past_event_closures,
)
from life_work_os_notion import NotionRestClient, env_status


ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[1]


def _schema(**types):
    return {name: {"type": prop_type} for name, prop_type in types.items()}


def _status_schema(name, options):
    return {
        name: {
            "type": "status",
            "status": {"options": [{"name": option} for option in options]},
        }
    }


def _page(page_id, title, **props):
    properties = {
        "Name": {
            "type": "title",
            "title": [{"plain_text": title}],
        }
    }
    for name, value in props.items():
        if isinstance(value, bool):
            properties[name] = {"type": "checkbox", "checkbox": value}
        elif name in {"Due Date", "Date"}:
            properties[name] = {"type": "date", "date": {"start": value}}
        else:
            properties[name] = {"type": "rich_text", "rich_text": [{"plain_text": value}]}
    return {"id": page_id, "properties": properties, "url": f"https://notion.test/{page_id}"}


def test_life_task_filter_excludes_work_and_investing_project():
    schema = _schema(Status="status", Domain="select", **{"Source Project": "select", "Due Date": "date", "Push On": "date"})

    filter_, issues, sorts = filter_for_source(
        SourceRequest("tasks", "Tasks", "tasks"),
        schema,
        routine=DAILY_LIFE,
        now=datetime(2026, 6, 17, tzinfo=ET),
    )

    assert issues == []
    assert {"property": "Domain", "select": {"does_not_equal": "Work"}} in filter_["and"]
    assert {"property": "Source Project", "select": {"does_not_equal": "Investing 2026"}} in filter_["and"]
    assert {"property": "Push On", "direction": "ascending"} in sorts


def test_drift_filter_does_not_require_domain_for_work():
    schema = _schema(Status="status", Domain="select")

    filter_, issues, _sorts = filter_for_source(
        SourceRequest("drift", "Drift", "drift"),
        schema,
        routine=DAILY_WORK,
        now=datetime(2026, 6, 17, tzinfo=ET),
    )

    assert issues == []
    assert "Domain" not in str(filter_)
    assert filter_ == {"property": "Status", "status": {"equals": "Active"}}


def test_briefing_text_output_is_ascii_safe_for_windows_console():
    report = {
        "routine": {"name": "Life OS Daily Briefing"},
        "valid": True,
        "summary": "Belle May 13 \u2192 May 15 \u2014 checked",
        "write_result": {"created": False, "verified": False, "skipped": True},
        "push_result": {"sent": False, "skipped": True},
    }

    text = _format_text(report)

    assert "May 13 -> May 15 - checked" in text
    text.encode("cp1252")


def test_work_operations_filter_uses_live_status_options():
    schema = _status_schema(
        "Status",
        ["Idea", "Active", "In Progress", "In Review", "Delivered", "Blocked", "Archived", "Recurring"],
    )

    filter_, issues, _sorts = filter_for_source(
        SourceRequest("work_ops", "Work Operations", "work-ops"),
        schema,
        routine=DAILY_WORK,
        now=datetime(2026, 6, 17, tzinfo=ET),
    )

    assert issues == []
    assert {"property": "Status", "status": {"equals": "Active"}} in filter_["or"]
    assert {"property": "Status", "status": {"equals": "Delivered"}} not in filter_["or"]
    assert "Done" not in str(filter_)


def test_work_items_are_hat_labeled():
    claimant = _item_from_page(
        _page("claim", "EEOC evidence packet", Domain="Work", Status="Pending"),
        SourceRequest("tasks", "Work Tasks", "tasks"),
        work=True,
    )
    employee = _item_from_page(
        _page("employee", "Submit weekly roadmap", Domain="Work", Status="In progress"),
        SourceRequest("tasks", "Work Tasks", "tasks"),
        work=True,
    )

    assert claimant.hat == "claimant"
    assert employee.hat == "employee"


def test_life_weekly_first_saturday_becomes_monthly_deep():
    routine = effective_routine("life_weekly", datetime(2026, 7, 4, 13, 0, tzinfo=ET))

    assert routine.name == "Life OS Monthly Deep"
    assert routine.report_type == "Monthly Deep"


def test_deadline_warning_ladder():
    now = datetime(2026, 6, 17, tzinfo=ET)

    assert deadline_warning_ladder(datetime(2026, 9, 1, tzinfo=ET), now, action_logged=False) == "hidden"
    assert deadline_warning_ladder(datetime(2026, 8, 1, tzinfo=ET), now, action_logged=False) == "neutral"
    assert deadline_warning_ladder(datetime(2026, 7, 10, tzinfo=ET), now, action_logged=False) == "yellow_weekly"
    assert deadline_warning_ladder(datetime(2026, 6, 20, tzinfo=ET), now, action_logged=False) == "red_daily"
    assert deadline_warning_ladder(datetime(2026, 6, 20, tzinfo=ET), now, action_logged=True) == "gray_in_progress"


class PagingClient(NotionRestClient):
    def __init__(self):
        super().__init__(token="fake")
        self.calls = []

    def _request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if len(self.calls) == 1:
            return {"results": [{"id": "a"}], "has_more": True, "next_cursor": "cursor-1"}
        return {"results": [{"id": "b"}], "has_more": False}


def test_query_data_source_uses_data_source_endpoint_and_full_pagination():
    client = PagingClient()

    result = client.query_data_source("ds-test", filter_={"x": 1})

    assert [row["id"] for row in result.rows] == ["a", "b"]
    assert result.pages_fetched == 2
    assert client.calls[0][1] == "/data_sources/ds-test/query"
    assert client.calls[1][2]["start_cursor"] == "cursor-1"


def test_heartbeat_marks_missing_rows_stale_after_threshold():
    now = datetime(2026, 6, 18, 22, 0, tzinfo=ET)

    rows = evaluate_staleness(latest_rows={}, now=now, threshold_hours=36)

    stale = {row.automation_id: row for row in rows if row.state == "stale"}
    assert "life-os-daily-briefing" in stale
    assert "has not run since never" in stale["life-os-daily-briefing"].alarm


def test_hygiene_plans_conservative_past_event_closure():
    rows = [
        _page("past", "Confirm May 5 surgery time", **{"Due Date": "2026-05-05", "Recurring": "false"}),
        _page("future", "Confirm July appointment", **{"Due Date": "2026-07-05"}),
        _page("case", "EEOC evidence follow-up", **{"Due Date": "2026-05-05", "Domain": "Work"}),
        _page("settlement", "Schedule Anthony + Neelu strategic follow-up (settlement strategy)", **{"Due Date": "2026-05-05"}),
    ]

    ops = plan_past_event_closures(rows, now=datetime(2026, 6, 17, tzinfo=ET), cap=10)

    assert [op.page_id for op in ops] == ["past"]
    assert ops[0].target_status == "Cancelled"


def test_hygiene_duplicate_planner_skips_case_content_and_keeps_richer_row():
    rows = [
        _page("thin", "Alexa speakers"),
        _page("rich", "Alexa speakers", Notes="keep this row with more detail"),
        _page("case1", "EEOC evidence", Domain="Work"),
        _page("case2", "EEOC evidence", Domain="Work"),
    ]

    ops = plan_duplicate_cancellations(rows, cap=10)

    assert [op.page_id for op in ops] == ["thin"]
    assert "kept richer row rich" in ops[0].reason


def test_finance_source_project_backfill_is_bounded_and_specific():
    rows = [
        _page("finance", "Finance task - rebalance account", **{"Source Project": "", "Domain": "Finance"}),
        _page("cancelled", "[CANCELLED] Investing task", **{"Source Project": "", "Domain": "Finance"}),
        _page("done", "Investing task already closed", **{"Source Project": "", "Domain": "Finance", "Status": "Done"}),
        _page("other", "Buy neck heater", **{"Source Project": ""}),
    ]

    ops = plan_finance_source_project_backfill(rows, cap=10)

    assert [op.page_id for op in ops] == ["finance"]
    assert ops[0].properties == {"Source Project": "Investing 2026"}


def test_hygiene_text_output_is_ascii_safe_for_windows_console():
    report = {
        "valid": True,
        "planned_count": 1,
        "apply_result": {"applied": False},
        "operations": [{
            "op": "backfill_investing_source_project",
            "title": "Build canonical \U0001f4d2 Positions page \u2014 setup",
            "reason": "Backfill Source Project \u2192 Investing 2026.",
        }],
    }

    text = _hygiene_format_text(report)

    assert "[notebook] Positions page - setup" in text
    assert "Source Project -> Investing 2026" in text
    text.encode("cp1252")


def test_orphan_inbox_recovery_dedupes_existing_source_blocks():
    blocks = [
        {"id": "block-1", "type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "raw capture"}]}},
        {"id": "block-2", "type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "already captured"}]}},
    ]

    ops = plan_orphan_inbox_recovery(blocks, existing_source_ids={"block-2"}, cap=10)

    assert [op.page_id for op in ops] == ["block-1"]
    assert ops[0].properties["Raw Content"] == "raw capture"
    assert ops[0].properties["Source"] == "recovered"


def test_env_status_reports_presence_without_values():
    report = env_status({
        "NOTION_TOKEN": "secret-notion",
        "PUSHOVER_TOKEN": "secret-push",
        "PUSHOVER_USER": "secret-user",
    })

    assert report == {
        "notion_token": True,
        "pushover_token": True,
        "pushover_user": True,
        "notion_version": "2025-09-03",
        "secrets_source": "environment_only",
    }


def test_life_work_prompt_files_carry_scheduled_receipt_and_secret_guardrails():
    prompt_paths = [
        ROOT / "src/codex_routines/Life_OS_Daily_Briefing_Routine_Prompt_v1.md",
        ROOT / "src/codex_routines/Work_OS_Daily_Briefing_Routine_Prompt_v1.md",
        ROOT / "src/codex_routines/Life_OS_Weekly_Review_Routine_Prompt_v1.md",
        ROOT / "src/codex_routines/Work_OS_Weekly_Review_Routine_Prompt_v1.md",
        ROOT / "src/codex_routines/Life_Work_OS_Heartbeat_Watcher_Routine_Prompt_v1.md",
        ROOT / "src/codex_routines/Life_Work_OS_Safe_Hygiene_Routine_Prompt_v1.md",
    ]

    for path in prompt_paths:
        text = path.read_text(encoding="utf-8")
        assert "--run-source scheduled" in text
        assert "cloud_routine_commit.py" in text
        assert "Notion-Version: 2025-09-03" in text
        assert "POST /v1/data_sources/{id}/query" in text
        assert "Do not read or search the Notion Routine Secrets page" in text
        assert "checked-clear" in text or "checked clear" in text
