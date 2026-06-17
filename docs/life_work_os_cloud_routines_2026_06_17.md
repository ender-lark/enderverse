# Life/Work OS Cloud Routines - 2026-06-17

## Reconciliation

Starting point:
- The wrapper path `C:\Users\suraj\OneDrive\Old\Documents\Investing OS (2.0)` is not a git repo.
- Existing installed Codex automations did not contain Life OS or Work OS briefing/review jobs.
- This repo did not contain Life/Work prompt files, status entries, or Briefing & Review Log helpers before this slice.
- The repo support slice was committed and pushed first, then the app automations were created after the final set was shown.
- App scheduling status: all six Codex app automations are ACTIVE as of 2026-06-17 15:27 ET, pointed at the canonical main checkout `C:\Users\suraj\Documents\Codex\2026-06-17\auto-loose-thread-sweep\enderverse`.
- Proof status: manual read-only proof passed for all six routines on 2026-06-17, with receipts written as `run_source=manual`. Those proofs exercised live Notion reads and output generation without Briefing Log writes, Pushover sends, or hygiene mutations. First real scheduled receipts are still pending and must land on main before scheduled proof is complete.
- Manual proof fixes landed in the same slice: Drift Flags uses `Status = Active` instead of invalid task-style `Done/Cancelled` filters; Work Operations uses positive live statuses; text output is ASCII-safe for the Windows scheduled console path; safe hygiene skips settlement/retaliation/constructive-discharge case content.
- Notion mirror: verified live on the Life OS page `Cloud Routines - Operations Reference` (`378c5031-4bb6-810f-a2bd-d806a4b2a015`) after fetchback at 2026-06-17T19:35Z.

Final planned set:

| routine | status | repo prompt | owned output |
| --- | --- | --- | --- |
| `life-os-daily-briefing` | CREATED/ACTIVE | `src/codex_routines/Life_OS_Daily_Briefing_Routine_Prompt_v1.md` | `src/life_os_daily_briefing_last_run.json` |
| `work-os-daily-briefing` | CREATED/ACTIVE | `src/codex_routines/Work_OS_Daily_Briefing_Routine_Prompt_v1.md` | `src/work_os_daily_briefing_last_run.json` |
| `life-os-weekly-review` | CREATED/ACTIVE | `src/codex_routines/Life_OS_Weekly_Review_Routine_Prompt_v1.md` | `src/life_os_weekly_review_last_run.json` |
| `work-os-weekly-review` | CREATED/ACTIVE | `src/codex_routines/Work_OS_Weekly_Review_Routine_Prompt_v1.md` | `src/work_os_weekly_review_last_run.json` |
| `life-work-os-heartbeat-watch` | CREATED/ACTIVE | `src/codex_routines/Life_Work_OS_Heartbeat_Watcher_Routine_Prompt_v1.md` | `src/life_work_os_heartbeat.json` |
| `life-work-os-safe-hygiene` | CREATED/ACTIVE | `src/codex_routines/Life_Work_OS_Safe_Hygiene_Routine_Prompt_v1.md` | `src/life_work_os_hygiene_receipt.json` |

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

- Confirm a real scheduled run inherits `NOTION_TOKEN`, `PUSHOVER_TOKEN`, and `PUSHOVER_USER`. Manual read-only proofs confirmed the local runner env and live Notion access on 2026-06-17, but the first scheduled app execution is the authoritative scheduled-env proof.
- Provide or configure `SYSTEM_CHANGELOG_DATA_SOURCE_ID`; safe-hygiene apply fails closed without it.
- Wait for real scheduled receipts on main for all six routines. Manual recovery receipts can support readiness, but do not count as scheduled proof.

