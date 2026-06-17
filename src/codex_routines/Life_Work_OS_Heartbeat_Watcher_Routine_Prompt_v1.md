# Life/Work OS Heartbeat Watcher Routine Prompt v1

Run the independent Life/Work OS heartbeat watcher on the existing Investing OS cloud routine rail.

Contract:
- Confirm the cwd is the canonical `main` worktree for this routine. If it is not on `main`, write a failed scheduled receipt and stop. Fast-forward with `git fetch origin main` and `git pull --ff-only origin main` before reading or writing.
- First run `python src/life_work_os_briefing.py --env-check --format text`. Secrets must come from environment only: `NOTION_TOKEN`, `PUSHOVER_TOKEN`, `PUSHOVER_USER`. Do not read or search the Notion Routine Secrets page.
- Use deterministic Notion REST reads only. The helper uses `Notion-Version: 2025-09-03` and `POST /v1/data_sources/{id}/query` with server-side filters and full pagination. Do not use Notion MCP/search to count rows.
- Run the watcher through the receipt wrapper: `python src/cloud_routine_runner.py --run-source scheduled --routine-id life-work-os-heartbeat-watch --success-summary "Life/Work OS heartbeat watch succeeded" --failure-summary "Life/Work OS heartbeat watch failed" -- python src/life_work_os_heartbeat.py --push --out src/life_work_os_heartbeat.json --format text`.
- Check the Briefing & Review Log for the expected Life OS Daily Briefing and Work OS Daily Briefing rows. If either has no row more than 36 hours past its expected slot, send a Pushover alarm: `Routine X has not run since DATE`.
- This watcher is independent of weekly reviews; do not rely on weekly staleness checks to detect daily outages.
- Missing, blocked, stale, schema-mismatched, or credential-missing sources must remain `not_checked` / dark in the summary. Do not manufacture checked-clear counts.

Closeout:
- Normalize and validate receipts: `python src/cloud_routine_receipts.py --out src/cloud_routine_receipts.json --normalize --validate --require-utf8 --format text`.
- Commit and push routine-owned receipt/output artifacts with `python src/cloud_routine_commit.py --message "Life/Work OS heartbeat watch scheduled run" --push --format text`. If push fails, report it.
