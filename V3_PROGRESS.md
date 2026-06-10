# V3 Progress Log

## Current task
- Task 4: Task-4 wiring + disposition summary surfaces (next)

## Tasks done
- ab2fd4a — v2-stable anchor (baseline retained, not modified).
- 62cb71f — v3(task-1): integrate C1-C4 + C5 modules; add `docs/v3_handoff/` and this progress file.
- Task 2 done (hash 31da7d2): inserted `today_decide.build_and_render(...)` as the FIRST section in `cockpit_html_gen.py`; performed golden/parity refreeze (`src/golden_feed.json`, `docs/index.html`, `src/rendered/conviction_cockpit_v5.jsx`) and updated `src/cockpit_html_gen.py`.
- Task 3 done (hash 3cb1fb4): added `src/disposition_log.py`, refactored `today_decide.py` to use the C6 disposition readers, and added `src/test_disposition_log.py` + today-decide last-disposition coverage.

## Next action
- Continue to Task 4 and preserve the exact same 6 skipped tests and skip reasons.
- Keep the exact same skip reasons as baseline unless operator changes environment.

## Gates / invariants
- Current branch gate after Task 3 is **1290 passed / 3 failed / 6 skipped**.
- ZERO new failures introduced; failures remain subset of documented baseline failures.
- Current failed set:
  - `test_go_live_checklist_cli_runs_against_current_repo`
  - `test_go_live_checklist_cli_text_format_runs_against_current_repo`
  - `test_cloud_routine_manual_run`
- Deviation logged: `test_rendered_cockpit_keeps_operator_status_card` flipped to PASS after regenerated render artifacts.
- Skips must remain exactly 6 (env/platform conditional) with identical reasons.
  - `src/test_broker_pdf_extractor.py`: missing `pypdf` (`could not import 'pypdf'`)
  - `src/test_render_cockpit.py`: pinned renderer not present in this environment (`set COCKPIT_TEMPLATE` to run)
  - `src/test_render_cockpit.py` (5 additional skips): same pinned renderer constraint.
- Golden + parity refreeze occurs only at Task-2 and Task-5/6 boundaries.
- Full `python -m pytest src/ -q` before each commit.

## Recovery rule
- Never reset. Never re-extract zips. Resume from this file.
