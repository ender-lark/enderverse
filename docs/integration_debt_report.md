# Integration Debt Report

Generated: 2026-06-16T04:42:35Z

Status: warn | warnings: 4 | findings: 6

## Findings

1. [WARN] v11.10 options-exit cadence is not fully wired
   - Area: options_exit
   - Line: Options-exit cadence: STALE-LEAPS surface exists, but v11.10 7-rule cadence is not visibly wired into a routine or the STALE-LEAPS path.
   - Next: Wire rationale_decay_v3/options_expiry_preflight into Weekly Pilot, a routine, or STALE-LEAPS; otherwise document it as manual-only.
   - Evidence: src/rationale_decay_v3.py present; src/pattern_engine.py STALE-LEAPS present; src/morning_scan.py held_options defaults to caller-supplied/not_checked
2. [WARN] options_expiry_preflight.py has no visible wiring
   - Area: module_wiring
   - Line: options_expiry_preflight.py has no non-test import and no routine/prompt command reference.
   - Next: Either wire it through a routine/surface, document it as standalone/manual, or retire it.
   - Evidence: src/options_expiry_preflight.py
3. [WARN] stale_leaps_scan.py has no visible wiring
   - Area: module_wiring
   - Line: stale_leaps_scan.py has no non-test import and no routine/prompt command reference.
   - Next: Either wire it through a routine/surface, document it as standalone/manual, or retire it.
   - Evidence: src/stale_leaps_scan.py
4. [INFO] research_action_promotion prompt is not visibly scheduled
   - Area: routine_schedule
   - Line: src/codex_routines/research_action_promotion.md is not referenced by the manifest or active cloud schedules.
   - Next: Register it, mark it retired, or document why it is manual-only.
5. [INFO] fundstrat_late_evening_web_transcript_sweep lacks repo prompt coverage
   - Area: routine_schedule
   - Line: fundstrat_late_evening_web_transcript_sweep is scheduled but has no repo prompt/manifest doc match.
   - Next: Add a repo prompt/doc or map the schedule to an existing manifest entry.
   - Evidence: investing-os-fundstrat-late-evening-web-transcript-sweep; market weekdays 10:45 PM ET
6. [WARN] Notion System Update Queue not checked
   - Area: notion_queue
   - Line: Notion queue rows were not supplied to this read-only sweep; repo-local queue state cannot prove live Notion status.
   - Next: Run with a Notion queue export/connector snapshot when doing the weekly debt review.

## Section Summary

### options_exit_cadence

Options-exit cadence: STALE-LEAPS surface exists, but v11.10 7-rule cadence is not visibly wired into a routine or the STALE-LEAPS path.

### module_wiring

Module wiring sweep: 36 candidate orphan module(s); 2 priority warning(s).

### routine_schedule

Routine schedule sweep: 1 prompt-only file(s), 1 scheduled routine(s) without repo prompt/doc coverage.

### notion_queue

Notion queue sweep: not_checked; repo-local system queue has 1 active/queued item(s).

