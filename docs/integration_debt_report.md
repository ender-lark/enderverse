# Integration Debt Report

Generated: 2026-06-28T22:02:07Z

Status: warn | warnings: 3 | findings: 18

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
3. [INFO] automation_prompt_audit.py has no visible wiring
   - Area: module_wiring
   - Line: automation_prompt_audit.py has no non-test import and no routine/prompt command reference.
   - Next: Either wire it through a routine/surface, document it as standalone/manual, or retire it.
   - Evidence: src/automation_prompt_audit.py
4. [INFO] benchmark_overlay.py has no visible wiring
   - Area: module_wiring
   - Line: benchmark_overlay.py has no non-test import and no routine/prompt command reference.
   - Next: Either wire it through a routine/surface, document it as standalone/manual, or retire it.
   - Evidence: src/benchmark_overlay.py
5. [INFO] build_golden.py has no visible wiring
   - Area: module_wiring
   - Line: build_golden.py has no non-test import and no routine/prompt command reference.
   - Next: Either wire it through a routine/surface, document it as standalone/manual, or retire it.
   - Evidence: src/build_golden.py
6. [INFO] cloud_routine_drill.py has no visible wiring
   - Area: module_wiring
   - Line: cloud_routine_drill.py has no non-test import and no routine/prompt command reference.
   - Next: Either wire it through a routine/surface, document it as standalone/manual, or retire it.
   - Evidence: src/cloud_routine_drill.py
7. [INFO] cloud_routine_manual_run.py has no visible wiring
   - Area: module_wiring
   - Line: cloud_routine_manual_run.py has no non-test import and no routine/prompt command reference.
   - Next: Either wire it through a routine/surface, document it as standalone/manual, or retire it.
   - Evidence: src/cloud_routine_manual_run.py
8. [INFO] cockpit_html_gen.py has no visible wiring
   - Area: module_wiring
   - Line: cockpit_html_gen.py has no non-test import and no routine/prompt command reference.
   - Next: Either wire it through a routine/surface, document it as standalone/manual, or retire it.
   - Evidence: src/cockpit_html_gen.py
9. [INFO] cockpit_jsx_preview.py has no visible wiring
   - Area: module_wiring
   - Line: cockpit_jsx_preview.py has no non-test import and no routine/prompt command reference.
   - Next: Either wire it through a routine/surface, document it as standalone/manual, or retire it.
   - Evidence: src/cockpit_jsx_preview.py
10. [INFO] completion_audit.py has no visible wiring
   - Area: module_wiring
   - Line: completion_audit.py has no non-test import and no routine/prompt command reference.
   - Next: Either wire it through a routine/surface, document it as standalone/manual, or retire it.
   - Evidence: src/completion_audit.py
11. [INFO] correlation_matrix.py has no visible wiring
   - Area: module_wiring
   - Line: correlation_matrix.py has no non-test import and no routine/prompt command reference.
   - Next: Either wire it through a routine/surface, document it as standalone/manual, or retire it.
   - Evidence: src/correlation_matrix.py
12. [INFO] decision_dossier_sync.py has no visible wiring
   - Area: module_wiring
   - Line: decision_dossier_sync.py has no non-test import and no routine/prompt command reference.
   - Next: Either wire it through a routine/surface, document it as standalone/manual, or retire it.
   - Evidence: src/decision_dossier_sync.py
13. [WARN] disconfirmation_registry.json carries candidates but is not surfaced
   - Area: build_without_wire
   - Line: disconfirmation_registry.json carries ticker/candidate rows but has no decision-path reader, ownership feed_path, or non-surfacing allowlist entry.
   - Next: Wire it through the decision path, declare a real state_ownership_map feed_path, or add a justified non_surfacing_reason to src/non_surfacing_allowlist.json.
   - Evidence: src/disconfirmation_registry.json
14. [WARN] fundstrat_deep_crawl_summary.json carries candidates but is not surfaced
   - Area: build_without_wire
   - Line: fundstrat_deep_crawl_summary.json carries ticker/candidate rows but has no decision-path reader, ownership feed_path, or non-surfacing allowlist entry.
   - Next: Wire it through the decision path, declare a real state_ownership_map feed_path, or add a justified non_surfacing_reason to src/non_surfacing_allowlist.json.
   - Evidence: src/fundstrat_deep_crawl_summary.json
15. [INFO] research_action_promotion prompt is not visibly scheduled
   - Area: routine_schedule
   - Line: src/codex_routines/research_action_promotion.md is not referenced by the manifest or active cloud schedules.
   - Next: Register it, mark it retired, or document why it is manual-only.
16. [INFO] federal_funding_midday_watch lacks repo prompt coverage
   - Area: routine_schedule
   - Line: federal_funding_midday_watch is scheduled but has no repo prompt/manifest doc match.
   - Next: Add a repo prompt/doc or map the schedule to an existing manifest entry.
   - Evidence: investing-os-federal-funding-midday-watch; market weekdays 11:20 AM ET
17. [INFO] federal_funding_post_close_sweep lacks repo prompt coverage
   - Area: routine_schedule
   - Line: federal_funding_post_close_sweep is scheduled but has no repo prompt/manifest doc match.
   - Next: Add a repo prompt/doc or map the schedule to an existing manifest entry.
   - Evidence: investing-os-federal-funding-post-close-sweep; market weekdays 5:35 PM ET
18. [WARN] Notion System Update Queue not checked
   - Area: notion_queue
   - Line: Notion queue rows were not supplied to this read-only sweep; repo-local queue state cannot prove live Notion status.
   - Next: Run with a Notion queue export/connector snapshot when doing the weekly debt review.

## Section Summary

### options_exit_cadence

Options-exit cadence: v11.10 7-rule cadence has visible routine or STALE-LEAPS wiring.

### module_wiring

Module wiring sweep: 36 candidate orphan module(s); 0 priority warning(s).

### build_without_wire

Build-without-wire sweep: 33 candidate-bearing artifact(s); 2 unwired warning(s).

### routine_schedule

Routine schedule sweep: 1 prompt-only file(s), 2 scheduled routine(s) without repo prompt/doc coverage.

### notion_queue

Notion queue sweep: not_checked; repo-local system queue has 4 active/queued item(s).

