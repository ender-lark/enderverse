# Work OS Daily Briefing Routine Prompt v1

Run the Work OS Daily Briefing on the existing Investing OS cloud routine rail.

Contract:
- Confirm the cwd is the canonical `main` worktree for this routine. If it is not on `main`, write a failed scheduled receipt and stop. Fast-forward with `git fetch origin main` and `git pull --ff-only origin main` before reading or writing.
- First run `python src/life_work_os_briefing.py --env-check --format text`. Secrets must come from environment only: `NOTION_TOKEN`, `PUSHOVER_TOKEN`, `PUSHOVER_USER`. Do not read or search the Notion Routine Secrets page.
- Use deterministic Notion REST reads only. The helper uses `Notion-Version: 2025-09-03` and `POST /v1/data_sources/{id}/query` with server-side filters and full pagination. Do not use Notion MCP/search to count rows.
- Run the routine through the receipt wrapper: `python src/cloud_routine_runner.py --run-source scheduled --routine-id work-os-daily-briefing --success-summary "Work OS daily briefing succeeded" --failure-summary "Work OS daily briefing failed" -- python src/life_work_os_briefing.py --routine work_daily --write-log --push --out src/work_os_daily_briefing_last_run.json --format text`.
- Read only the user's own Notion. Never read Solventum tenant data.
- Every item must be hat-labeled `employee` or `claimant`; never blend unlabeled work and claimant material.
- Read `Domain = Work` Tasks, Work Operations, Evidence & Fact Ledger rows with `Preservation = Pending/Blocked`, recent Work Insights, and active Drift Flags. Drift Flags have no Domain property, so do not apply a Domain filter there; tag work relevance inline.
- Use the deadline-warning ladder, not raw countdowns: more than two months hidden, two months neutral first appearance, one month yellow, weekly through final month, daily through final week, red if no action logged, gray if a linked Task is in progress or Done. Canonical deadline surface is the EEOC Filing Deadline page `382c5031-4bb6-8177-9b8a-e8b774e1a333`.
- Missing, blocked, stale, schema-mismatched, or credential-missing sources must remain `not_checked` / dark in the summary. Do not manufacture checked-clear counts.
- The routine writes exactly one dated Briefing & Review Log row with `OS="Work"`, `Type="Daily Briefing"`, `Date`, `Summary`, and `Push Sent`, then fetches the created row back before claiming success.
- Send the created row link by Pushover when configured. Do not print secrets.

Closeout:
- Normalize and validate receipts: `python src/cloud_routine_receipts.py --out src/cloud_routine_receipts.json --normalize --validate --require-utf8 --format text`.
- Commit and push routine-owned receipt/output artifacts with `python src/cloud_routine_commit.py --message "Work OS daily briefing scheduled run" --push --format text`. If push fails, report it.
