# Life/Work OS Safe Hygiene Routine Prompt v1

Run the Life/Work OS safe-hygiene routine on the existing Investing OS cloud routine rail.

Contract:
- Confirm the cwd is the canonical `main` worktree for this routine. If it is not on `main`, write a failed scheduled receipt and stop. Fast-forward with `git fetch origin main` and `git pull --ff-only origin main` before reading or writing.
- First run `python src/life_work_os_briefing.py --env-check --format text`. Secrets must come from environment only: `NOTION_TOKEN`, `PUSHOVER_TOKEN`, `PUSHOVER_USER`. Do not read or search the Notion Routine Secrets page.
- Use deterministic Notion REST reads only. The helper uses `Notion-Version: 2025-09-03` and `POST /v1/data_sources/{id}/query` with server-side filters and full pagination. Do not use Notion MCP/search to count rows.
- Run the routine through the receipt wrapper: `python src/cloud_routine_runner.py --run-source scheduled --routine-id life-work-os-safe-hygiene --success-summary "Life/Work OS safe hygiene succeeded" --failure-summary "Life/Work OS safe hygiene failed" -- python src/life_work_os_hygiene.py --apply --max-mutations 10 --out src/life_work_os_hygiene_receipt.json --format text`.
- The helper may only perform bounded, guardrailed mechanical hygiene writes:
  - Recover orphaned legacy Inbox child-page captures from page `343c50314bb681128b26e00491df0b4a` into Inbox DB rows verbatim, preserving Raw Content and tagging source=recovered.
  - Close clearly past one-time event Tasks by setting Status=Cancelled with a note. Never delete.
  - Backfill Finance/Investing tasks with null Source Project to `Investing 2026`.
  - Cancel conservative exact-title duplicate Task rows, keeping the richer row.
  - Drain autonomous-safe After-Hours Queue items and mark them Done with a closeout note.
- Hard guardrails: idempotent, never delete, cap mutations per run, log every mutation in receipt + briefing summary + System Changelog, and never auto-mutate Work case-file content including Strategic Brief, Game Plan, Insights, or Evidence Ledger.
- If `SYSTEM_CHANGELOG_DATA_SOURCE_ID` is not configured, the helper must fail before applying mutations so mutation logging is never skipped.
- Missing, blocked, stale, schema-mismatched, or credential-missing sources must remain `not_checked` / dark in the summary. Do not manufacture checked-clear counts.

Closeout:
- Normalize and validate receipts: `python src/cloud_routine_receipts.py --out src/cloud_routine_receipts.json --normalize --validate --require-utf8 --format text`.
- Commit and push routine-owned receipt/output artifacts with `python src/cloud_routine_commit.py --message "Life/Work OS safe hygiene scheduled run" --push --format text`. If push fails, report it.
