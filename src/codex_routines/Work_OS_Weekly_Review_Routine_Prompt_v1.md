# Work OS Weekly Review Routine Prompt v1

Run the Work OS Weekly Review on the existing Investing OS cloud routine rail.

Contract:
- Confirm the cwd is the canonical `main` worktree for this routine. If it is not on `main`, write a failed scheduled receipt and stop. Fast-forward with `git fetch origin main` and `git pull --ff-only origin main` before reading or writing.
- First run `python src/life_work_os_briefing.py --env-check --format text`. Secrets must come from environment only: `NOTION_TOKEN`, `PUSHOVER_TOKEN`, `PUSHOVER_USER`. Do not read or search the Notion Routine Secrets page.
- Use deterministic Notion REST reads only. The helper uses `Notion-Version: 2025-09-03` and `POST /v1/data_sources/{id}/query` with server-side filters and full pagination. Do not use Notion MCP/search to count rows.
- Run the routine through the receipt wrapper: `python src/cloud_routine_runner.py --run-source scheduled --routine-id work-os-weekly-review --success-summary "Work OS weekly review succeeded" --failure-summary "Work OS weekly review failed" -- python src/life_work_os_briefing.py --routine work_weekly --write-log --push --out src/work_os_weekly_review_last_run.json --format text`.
- Read only the user's own Notion. Never read Solventum tenant data.
- Every item must be hat-labeled `employee` or `claimant`; never blend unlabeled work and claimant material.
- Surface slipped items, evidence gaps from Insights flagged for follow-up plus Ledger rows where verification is not exact wording confirmed, pattern candidates, candidate strategic moves only, and emotional-load checks.
- Scout only for case content. Never auto-mutate Work case-file content, Strategic Brief, Game Plan, Insights, or Evidence Ledger.
- Missing, blocked, stale, schema-mismatched, or credential-missing sources must remain `not_checked` / dark in the summary. Do not manufacture checked-clear counts.
- The routine writes exactly one Briefing & Review Log row with `OS="Work"` and `Type="Weekly Review"`, then fetches the created row back before claiming success.
- Send the created row link by Pushover when configured. Do not print secrets.

Closeout:
- Normalize and validate receipts: `python src/cloud_routine_receipts.py --out src/cloud_routine_receipts.json --normalize --validate --require-utf8 --format text`.
- Commit and push routine-owned receipt/output artifacts with `python src/cloud_routine_commit.py --message "Work OS weekly review scheduled run" --push --format text`. If push fails, report it.
