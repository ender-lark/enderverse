# Life OS Weekly Review Routine Prompt v1

Run the Life OS Weekly Review on the existing Investing OS cloud routine rail.

Contract:
- Confirm the cwd is the canonical `main` worktree for this routine. If it is not on `main`, write a failed scheduled receipt and stop. Fast-forward with `git fetch origin main` and `git pull --ff-only origin main` before reading or writing.
- First run `python src/life_work_os_briefing.py --env-check --format text`. Secrets must come from environment only: `NOTION_TOKEN`, `PUSHOVER_TOKEN`, `PUSHOVER_USER`. Do not read or search the Notion Routine Secrets page.
- Use deterministic Notion REST reads only. The helper uses `Notion-Version: 2025-09-03` and `POST /v1/data_sources/{id}/query` with server-side filters and full pagination. Do not use Notion MCP/search to count rows.
- Run the routine through the receipt wrapper: `python src/cloud_routine_runner.py --run-source scheduled --routine-id life-os-weekly-review --success-summary "Life OS weekly review succeeded" --failure-summary "Life OS weekly review failed" -- python src/life_work_os_briefing.py --routine life_weekly --write-log --push --out src/life_os_weekly_review_last_run.json --format text`.
- On the first Saturday of a month, treat the output as the Monthly Deep pass and use the stronger configured model/effort in the app automation.
- Surface slipped open Tasks past Due Date or Push On with no recent activity, pattern candidates across recent Insights, synthesis candidates only, structural health, hygiene-backlog count, capture-volume delta, and days with no Life OS Daily Briefing.
- Synthesis candidates are candidates only; do not author final synthesis or ratify conclusions automatically.
- Missing, blocked, stale, schema-mismatched, or credential-missing sources must remain `not_checked` / dark in the summary. Do not manufacture checked-clear counts.
- The routine writes exactly one Briefing & Review Log row with `OS="Life OS"` and `Type="Weekly Review"` or `Type="Monthly Deep"` when the monthly condition applies, then fetches the created row back before claiming success.
- Send the created row link by Pushover when configured. Do not print secrets.

Closeout:
- Normalize and validate receipts: `python src/cloud_routine_receipts.py --out src/cloud_routine_receipts.json --normalize --validate --require-utf8 --format text`.
- Commit and push routine-owned receipt/output artifacts with `python src/cloud_routine_commit.py --message "Life OS weekly review scheduled run" --push --format text`. If push fails, report it.
