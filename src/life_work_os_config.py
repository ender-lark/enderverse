#!/usr/bin/env python3
"""Shared configuration for Life OS and Work OS cloud routines."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Any


NOTION_VERSION = "2025-09-03"
TIMEZONE = "America/New_York"
ACTIVATED_AT = "2026-06-17T15:27:23-04:00"

TASKS_DATA_SOURCE_ID = "f5f573dd-8c8f-4f6b-bad5-e09d9e772e7f"
INBOX_DATA_SOURCE_ID = "86e7a254-2d47-4f82-bed1-081e05ea57d5"
DRIFT_FLAGS_DATA_SOURCE_ID = "4d42834a-da9e-4fde-aefe-395f92a48cf4"
INSIGHTS_GROWTH_DATA_SOURCE_ID = "36fe8048-9d1a-4ed8-b20b-a06d54e5221e"
WORK_OPERATIONS_DATA_SOURCE_ID = "651cf84e-0429-4bf1-aa54-0be80e7abff7"
EVIDENCE_FACT_LEDGER_DATA_SOURCE_ID = "b274dbea-f46a-4bc4-be78-996a88fc2216"
BRIEFING_REVIEW_LOG_DATA_SOURCE_ID = "f34019b1-b66f-4022-b3a1-e1ac15085ae4"
BRIEFING_REVIEW_LOG_DB_PAGE_ID = "8414dca0-3089-4448-81b5-a65af529cf7f"
AFTER_HOURS_QUEUE_DATA_SOURCE_ID = "cbed1875-56c4-46de-b983-275d1454b484"

LEGACY_INBOX_PARENT_PAGE_ID = "343c50314bb681128b26e00491df0b4a"
EEOC_FILING_DEADLINE_PAGE_ID = "382c5031-4bb6-8177-9b8a-e8b774e1a333"

# The live System Changelog is an append-only Notion page. A data-source id can
# override this when one exists, but the page fallback is the canonical path.
SYSTEM_CHANGELOG_DATA_SOURCE_ENV = "SYSTEM_CHANGELOG_DATA_SOURCE_ID"
SYSTEM_CHANGELOG_PAGE_ENV = "SYSTEM_CHANGELOG_PAGE_ID"
SYSTEM_CHANGELOG_PAGE_ID = "351c5031-4bb6-813a-876b-f2a4835f65fb"


@dataclass(frozen=True)
class RoutineSpec:
    automation_id: str
    name: str
    os_name: str
    report_type: str
    schedule: str
    days: tuple[int, ...]
    slot: time
    prompt: str
    model: str = "gpt-5.5"
    reasoning_effort: str = "xhigh"
    proof_scope: str = "support"

    @property
    def role(self) -> str:
        return self.automation_id.replace("-", "_")


DAILY_LIFE = RoutineSpec(
    automation_id="life-os-daily-briefing",
    name="Life OS Daily Briefing",
    os_name="Life OS",
    report_type="Daily Briefing",
    schedule="daily 7:30 AM ET",
    days=(0, 1, 2, 3, 4, 5, 6),
    slot=time(7, 30),
    prompt="src/codex_routines/Life_OS_Daily_Briefing_Routine_Prompt_v1.md",
)

DAILY_WORK = RoutineSpec(
    automation_id="work-os-daily-briefing",
    name="Work OS Daily Briefing",
    os_name="Work",
    report_type="Daily Briefing",
    schedule="market weekdays 8:00 AM ET",
    days=(0, 1, 2, 3, 4),
    slot=time(8, 0),
    prompt="src/codex_routines/Work_OS_Daily_Briefing_Routine_Prompt_v1.md",
)

WEEKLY_LIFE = RoutineSpec(
    automation_id="life-os-weekly-review",
    name="Life OS Weekly Review",
    os_name="Life OS",
    report_type="Weekly Review",
    schedule="Saturday 1:00 PM ET; first Saturday emits Monthly Deep",
    days=(5,),
    slot=time(13, 0),
    prompt="src/codex_routines/Life_OS_Weekly_Review_Routine_Prompt_v1.md",
    reasoning_effort="max",
)

WEEKLY_WORK = RoutineSpec(
    automation_id="work-os-weekly-review",
    name="Work OS Weekly Review",
    os_name="Work",
    report_type="Weekly Review",
    schedule="Friday 4:00 PM ET",
    days=(4,),
    slot=time(16, 0),
    prompt="src/codex_routines/Work_OS_Weekly_Review_Routine_Prompt_v1.md",
)

HEARTBEAT = RoutineSpec(
    automation_id="life-work-os-heartbeat-watch",
    name="Life/Work OS Heartbeat Watch",
    os_name="Life/Work OS",
    report_type="Heartbeat Watch",
    schedule="daily 9:15 AM and 9:15 PM ET",
    days=(0, 1, 2, 3, 4, 5, 6),
    slot=time(9, 15),
    prompt="src/codex_routines/Life_Work_OS_Heartbeat_Watcher_Routine_Prompt_v1.md",
    reasoning_effort="medium",
)

SAFE_HYGIENE = RoutineSpec(
    automation_id="life-work-os-safe-hygiene",
    name="Life/Work OS Safe Hygiene",
    os_name="Life/Work OS",
    report_type="Safe Hygiene",
    schedule="daily 2:30 AM ET",
    days=(0, 1, 2, 3, 4, 5, 6),
    slot=time(2, 30),
    prompt="src/codex_routines/Life_Work_OS_Safe_Hygiene_Routine_Prompt_v1.md",
    reasoning_effort="high",
)

BRIEFING_ROUTINES = {
    "life_daily": DAILY_LIFE,
    "work_daily": DAILY_WORK,
    "life_weekly": WEEKLY_LIFE,
    "work_weekly": WEEKLY_WORK,
}

ALL_ROUTINES = (
    DAILY_LIFE,
    DAILY_WORK,
    WEEKLY_LIFE,
    WEEKLY_WORK,
    HEARTBEAT,
    SAFE_HYGIENE,
)


def automation_status_rows(status: str = "PLANNED") -> list[dict[str, Any]]:
    return [
        {
            "automation_id": routine.automation_id,
            "automation_name": routine.name,
            "status": status,
            "role": routine.role,
            "schedule": routine.schedule,
            "expected_since": ACTIVATED_AT,
            "proof_scope": routine.proof_scope,
            "prompt": routine.prompt,
            "writes_to": (
                "Briefing & Review Log, Pushover"
                if routine in (DAILY_LIFE, DAILY_WORK, WEEKLY_LIFE, WEEKLY_WORK)
                else "Briefing & Review Log/Pushover status"
            ),
            "model": routine.model,
            "reasoning_effort": routine.reasoning_effort,
        }
        for routine in ALL_ROUTINES
    ]


def cloud_expected_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for routine in ALL_ROUTINES:
        rows.append(
            {
                "automation_id": routine.automation_id,
                "automation_name": routine.name,
                "role": routine.role,
                "schedule": routine.schedule,
                "days": list(routine.days),
                "hour": routine.slot.hour,
                "minute": routine.slot.minute,
                "expected_since": ACTIVATED_AT,
                "proof_scope": routine.proof_scope,
            }
        )
    return rows

