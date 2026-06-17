# Life/Work OS Cloud Routines - 2026-06-17

## Reconciliation

Starting point:
- The wrapper path `C:\Users\suraj\OneDrive\Old\Documents\Investing OS (2.0)` is not a git repo.
- Existing installed Codex automations did not contain Life OS or Work OS briefing/review jobs.
- This repo did not contain Life/Work prompt files, status entries, or Briefing & Review Log helpers before this slice.
- The current implementation status is repo support only. App scheduling is still pending explicit confirmation of the final set.

Final planned set:

| routine | status | repo prompt | owned output |
| --- | --- | --- | --- |
| `life-os-daily-briefing` | CREATE | `src/codex_routines/Life_OS_Daily_Briefing_Routine_Prompt_v1.md` | `src/life_os_daily_briefing_last_run.json` |
| `work-os-daily-briefing` | CREATE | `src/codex_routines/Work_OS_Daily_Briefing_Routine_Prompt_v1.md` | `src/work_os_daily_briefing_last_run.json` |
| `life-os-weekly-review` | CREATE | `src/codex_routines/Life_OS_Weekly_Review_Routine_Prompt_v1.md` | `src/life_os_weekly_review_last_run.json` |
| `work-os-weekly-review` | CREATE | `src/codex_routines/Work_OS_Weekly_Review_Routine_Prompt_v1.md` | `src/work_os_weekly_review_last_run.json` |
| `life-work-os-heartbeat-watch` | CREATE | `src/codex_routines/Life_Work_OS_Heartbeat_Watcher_Routine_Prompt_v1.md` | `src/life_work_os_heartbeat.json` |
| `life-work-os-safe-hygiene` | CREATE | `src/codex_routines/Life_Work_OS_Safe_Hygiene_Routine_Prompt_v1.md` | `src/life_work_os_hygiene_receipt.json` |

## Schedule Proposal

| routine | cron intent | tz | model | writes-to | push |
| --- | --- | --- | --- | --- | --- |
| Life OS Daily Briefing | daily 7:30 AM | America/New_York | `gpt-5.5`, `xhigh` | Briefing & Review Log | yes |
| Work OS Daily Briefing | weekdays 8:00 AM | America/New_York | `gpt-5.5`, `xhigh` | Briefing & Review Log | yes |
| Life OS Weekly Review | Saturday 1:00 PM; first Saturday emits Monthly Deep | America/New_York | `gpt-5.5`, `max` for monthly-capable review | Briefing & Review Log | yes |
| Work OS Weekly Review | Friday 4:00 PM | America/New_York | `gpt-5.5`, `xhigh` | Briefing & Review Log | yes |
| Life/Work OS Heartbeat Watch | daily 9:15 AM and 9:15 PM | America/New_York | `gpt-5.5`, `medium` | heartbeat status artifact, Pushover alarms | alarm only |
| Life/Work OS Safe Hygiene | daily 2:30 AM | America/New_York | `gpt-5.5`, `high` | hygiene receipt, Notion task/inbox/queue mutations, System Changelog when configured | summary/alarm only |

## Architecture Rules

- Reuse the Investing OS rail: scheduled receipts, UTF-8 normalization, and `src/cloud_routine_commit.py`.
- Use a clean main checkout for app automation cwd. Do not point new jobs at feature worktrees.
- Use env-only secrets: `NOTION_TOKEN`, `PUSHOVER_TOKEN`, and `PUSHOVER_USER`. Never read the deprecated Routine Secrets Notion page.
- Use Notion REST data-source queries with server-side filters and full pagination. No agentic search for counts.
- Every Notion write must be fetched back before success is claimed.
- Keep missing, stale, schema-mismatched, or blocked lanes visible as `not_checked` / dark.
- Safe hygiene may only mutate mechanical Tasks/Inbox/After-Hours Queue data. Work case-file content remains scout-only.

## Open Before Scheduling

- Confirm the Codex scheduled environment has `NOTION_TOKEN`, `PUSHOVER_TOKEN`, and `PUSHOVER_USER`.
- Provide or configure `SYSTEM_CHANGELOG_DATA_SOURCE_ID`; safe-hygiene apply fails closed without it.
- After app automations are created, update `src/cloud_automation_status.json` rows from `PLANNED` to `ACTIVE` and wait for real scheduled receipts on main.

