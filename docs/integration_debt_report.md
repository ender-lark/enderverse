# Integration Debt Report

Generated: 2026-06-16T04:59:40Z

Status: warn | warnings: 1 | findings: 14

## Findings

1. [INFO] 13f_best_ideas.py has no visible wiring
   - Area: module_wiring
   - Line: 13f_best_ideas.py has no non-test import and no routine/prompt command reference.
   - Next: Either wire it through a routine/surface, document it as standalone/manual, or retire it.
   - Evidence: src/13f_best_ideas.py
2. [INFO] 13f_quarterly_pull.py has no visible wiring
   - Area: module_wiring
   - Line: 13f_quarterly_pull.py has no non-test import and no routine/prompt command reference.
   - Next: Either wire it through a routine/surface, document it as standalone/manual, or retire it.
   - Evidence: src/13f_quarterly_pull.py
3. [INFO] benchmark_overlay.py has no visible wiring
   - Area: module_wiring
   - Line: benchmark_overlay.py has no non-test import and no routine/prompt command reference.
   - Next: Either wire it through a routine/surface, document it as standalone/manual, or retire it.
   - Evidence: src/benchmark_overlay.py
4. [INFO] build_golden.py has no visible wiring
   - Area: module_wiring
   - Line: build_golden.py has no non-test import and no routine/prompt command reference.
   - Next: Either wire it through a routine/surface, document it as standalone/manual, or retire it.
   - Evidence: src/build_golden.py
5. [INFO] cloud_routine_drill.py has no visible wiring
   - Area: module_wiring
   - Line: cloud_routine_drill.py has no non-test import and no routine/prompt command reference.
   - Next: Either wire it through a routine/surface, document it as standalone/manual, or retire it.
   - Evidence: src/cloud_routine_drill.py
6. [INFO] cloud_routine_manual_run.py has no visible wiring
   - Area: module_wiring
   - Line: cloud_routine_manual_run.py has no non-test import and no routine/prompt command reference.
   - Next: Either wire it through a routine/surface, document it as standalone/manual, or retire it.
   - Evidence: src/cloud_routine_manual_run.py
7. [INFO] cockpit_html_gen.py has no visible wiring
   - Area: module_wiring
   - Line: cockpit_html_gen.py has no non-test import and no routine/prompt command reference.
   - Next: Either wire it through a routine/surface, document it as standalone/manual, or retire it.
   - Evidence: src/cockpit_html_gen.py
8. [INFO] cockpit_jsx_preview.py has no visible wiring
   - Area: module_wiring
   - Line: cockpit_jsx_preview.py has no non-test import and no routine/prompt command reference.
   - Next: Either wire it through a routine/surface, document it as standalone/manual, or retire it.
   - Evidence: src/cockpit_jsx_preview.py
9. [INFO] completion_audit.py has no visible wiring
   - Area: module_wiring
   - Line: completion_audit.py has no non-test import and no routine/prompt command reference.
   - Next: Either wire it through a routine/surface, document it as standalone/manual, or retire it.
   - Evidence: src/completion_audit.py
10. [INFO] correlation_matrix.py has no visible wiring
   - Area: module_wiring
   - Line: correlation_matrix.py has no non-test import and no routine/prompt command reference.
   - Next: Either wire it through a routine/surface, document it as standalone/manual, or retire it.
   - Evidence: src/correlation_matrix.py
11. [INFO] deepdive_runner.py has no visible wiring
   - Area: module_wiring
   - Line: deepdive_runner.py has no non-test import and no routine/prompt command reference.
   - Next: Either wire it through a routine/surface, document it as standalone/manual, or retire it.
   - Evidence: src/deepdive_runner.py
12. [INFO] disconfirmation_registry.py has no visible wiring
   - Area: module_wiring
   - Line: disconfirmation_registry.py has no non-test import and no routine/prompt command reference.
   - Next: Either wire it through a routine/surface, document it as standalone/manual, or retire it.
   - Evidence: src/disconfirmation_registry.py
13. [INFO] research_action_promotion prompt is not visibly scheduled
   - Area: routine_schedule
   - Line: src/codex_routines/research_action_promotion.md is not referenced by the manifest or active cloud schedules.
   - Next: Register it, mark it retired, or document why it is manual-only.
14. [WARN] Notion System Update Queue not checked
   - Area: notion_queue
   - Line: Notion queue rows were not supplied to this read-only sweep; repo-local queue state cannot prove live Notion status.
   - Next: Run with a Notion queue export/connector snapshot when doing the weekly debt review.

## Section Summary

### options_exit_cadence

Options-exit cadence: v11.10 7-rule cadence has visible routine or STALE-LEAPS wiring.

### module_wiring

Module wiring sweep: 34 candidate orphan module(s); 0 priority warning(s).

### routine_schedule

Routine schedule sweep: 1 prompt-only file(s), 0 scheduled routine(s) without repo prompt/doc coverage.

### notion_queue

Notion queue sweep: not_checked; repo-local system queue has 1 active/queued item(s).

