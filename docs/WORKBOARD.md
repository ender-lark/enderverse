# Shared Workboard

Shared coordination board for Claude, Codex, Claude Code, and scheduled cloud
routines. Update this file at the start and end of every implementation slice.
Claim work here before editing so agents do not duplicate each other.

Allowed statuses: `CLAIMED`, `IN-PROGRESS`, `PR#<n>`, `MERGED`, `SUPERSEDED`.

| id | agent | scope | files-or-state-owned | status | stamp |
| --- | --- | --- | --- | --- | --- |
| A1 | Codex | Holdings tab: render all account positions with tracked/untracked flag and stale banner | `src/cockpit_html_gen.py`; `src/test_cockpit_html_gen.py`; `docs/index.html` | MERGED PR#9 | 2026-06-12 19:25 ET |
| A2 | Codex | Orphan triage: classify untracked holdings and emit JSON/MD summary | `src/orphan_triage.py`; `src/test_orphan_triage.py`; `src/orphan_triage.json`; `src/orphan_triage.md` | MERGED PR#10 | 2026-06-12 19:25 ET |
| B1 | Codex | FundStrat tab: Bible layers plus latest dailies; retire News UI label | `src/cockpit_html_gen.py`; `src/test_cockpit_html_gen.py`; `docs/index.html` | MERGED PR#11 | 2026-06-12 19:25 ET |
| C1 | Codex | Post-close Positions Sync wrapper at 4:45 PM ET plus one manual 6/12 reconciliation run | `src/codex_routines/Positions_Sync_Routine_Prompt_v1.md`; `src/cloud_ops_status.py`; `src/cloud_automation_status.json`; `src/cloud_routine_commit.py`; position refresh artifacts | MERGED PR#12 | 2026-06-12 19:55 ET |
| C1A | Codex | Account-map semantics: executable tax_status plus PCRA/crypto placement flags from 6/12 SnapTrade handoff | `src/account_rules.json`; `src/execution_plan.py`; `src/test_execution_plan.py`; `src/state_ownership_map.json` | MERGED PR#12 | 2026-06-12 19:55 ET |
| C2 | Codex | Gate semantics: close/touch/near-certain with 6/11 QQQ trap test | `src/timing_gates.json`; `src/timing_engine.py`; related tests | IN-PROGRESS | 2026-06-14 15:55 ET |
| C3 | Codex | Look-through auto-disclosure for wrapper ETFs on add/trim cards | look-through map/config; `src/today_decide.py`; execution/render tests | MERGED PR#26 | 2026-06-14 15:36 ET |
| C4 | Codex | Bible tactical extension: tactical top/bottom and named levels; full-text monthly checklist | `src/fundstrat_bible.json`; `src/fundstrat_sector_stances.py`; FundStrat intake docs/tests | CLAIMED | 2026-06-12 19:25 ET |
| C5 | Codex | June catalyst additions and Notion Catalyst Calendar mirror | `src/catalysts.json`; catalyst intake outputs; Notion Catalyst Calendar | MERGED PR#28 | 2026-06-14 15:44 ET |
| D | Codex | AUTO-OK lane design: analysis/code/docs only, never trades/doctrine/honesty rails | design doc; queue row `37dc5031-4bb6-8141-890b-cf4aa9d27625` | CLAIMED | 2026-06-12 19:25 ET |
| P2-2 | Codex | FS ingestion completeness guard and inventory backfill for active Bible layers | `src/fs_ingest_inventory.json`; `src/fs_ingest_guard.py`; FundStrat dashboard/morning warning channel | MERGED PR#13 | 2026-06-12 20:20 ET |
| P2-3 | Codex | Cadence-aware overdue alerts by extending receipts/heartbeat stack | `src/cloud_routine_receipts.py`; `src/cloud_ops_status.py`; `src/heartbeat_status.py`; dashboard/preflight warnings | MERGED PR#14 | 2026-06-12 20:55 ET |
| P2-4 | Codex | Insider feed live unstub plus stale Patch-F row audit/closure | `src/session_orchestrator.py`; insider cache/intake path; Notion rows `36dc5031-4bb6-81f8-b2ec` and `36dc5031-4bb6-8124` | CLAIMED | 2026-06-12 19:25 ET |
| T1 | Codex | Trigger registry and push spine for missed ASTS/MU/EWRE/tactical trigger class | `src/trigger_registry.json`; `src/trigger_check.py`; existing routine prompts/wrappers; dashboard warnings; receipts | MERGED PR#15 | 2026-06-12 21:07 ET |
| T2 | Codex | Restore caps-based sizing block on BUY/ADD decision cards across HTML and JSX parity | `src/directive_recs.py`; `src/today_decide.py`; `src/conviction_cockpit_v6.jsx`; sizing/parity tests; `src/ARCHITECTURE.md` | MERGED PR#18 | 2026-06-12 21:40 ET |
| T7 | Codex | Stated-balance assertion for SnapTrade staged book validation | `src/snaptrade_book_refresh.py`; `src/snaptrade_positions_import.py`; `src/build_positions_cache.py`; reconciliation tests | MERGED PR#16 | 2026-06-12 21:22 ET |
| T4 | Codex | Deepdive evidence battery: multi-day OI build plus 10-day dark-pool blocks | `src/deepdive_runner.py`; UW response adapters/tests; Notion rows `36ec5031-4bb6-814b` and `36ec5031-4bb6-81dd` | MERGED PR#17 | 2026-06-12 21:31 ET |
| T3 | Codex | Integration-debt sweep and Sunday Weekly Pilot Run hook | `src/integration_debt_sweep.py`; `docs/integration_debt_report.md`; weekly pilot prompt; dashboard warning count | MERGED PR#20 | 2026-06-13 13:18 ET |
| T5 | Codex | Outcome-pattern loop for Trade Outcomes plus Decisions Log exports | `src/outcome_patterns.py`; Sunday Deep Synthesis prompt; outcome/decision export tests | MERGED PR#23 | 2026-06-13 18:11 ET |
| T6 | Codex | Hygiene batch plus Notion queue execution and queue-audit doc | `docs/queue_audit_2026-06-12.md`; outcome/source-call/calibration docs and guards; Notion queue rows | CLAIMED | 2026-06-12 20:35 ET |
| T8 | Codex | Account semantics absorb for executable tax_status and account flags | `src/account_rules.json`; SnapTrade profile/semantics path; execution-plan placement tests | MERGED PR#27 | 2026-06-14 15:40 ET |
| T9 | Codex | Held-decisions strip for operator-parked decision packets with review-by triggers | `src/held_decisions.json`; `src/held_decisions.py`; `src/test_held_decisions.py`; `src/cockpit_html_gen.py`; `src/trigger_registry.json`; `docs/codex_tasks/held_decisions_strip.md` | MERGED PR#19 | 2026-06-13 00:05 ET |
| CLOUD-FS-DAYTIME | cloud routines | Fundstrat Daytime Watch scheduled run | `src/fundstrat_*`; `src/source_calls.json`; `src/cloud_routine_receipts.json`; dashboard artifacts | MERGED | 2026-06-12 19:25 ET |
| CLOUD-BROKER-INTAKE | cloud routines | Existing 8:20 AM ET SnapTrade broker intake; remains owner of core position files | `src/positions.json`; `src/account_positions.json`; `src/position_reconciliation.json` | MERGED | 2026-06-12 19:25 ET |
| CLAUDE-SNAPTRADE-CONVERTER | Claude | Withdrawn `snaptrade_to_combined.py` converter; do not import. If compatibility CLI is ever needed, build a thin wrapper over `build_combined_from_snaptrade`; possible low-priority account-map semantics may fold into SnapTrade profiles later. | none | SUPERSEDED | 2026-06-12 19:25 ET |
| EFFICACY-HARNESS | Claude Code | regression proof the trigger spine + sizing block catch the documented misses | `src/test_efficacy_harness.py`; `src/efficacy_scenarios.json`; `docs/efficacy_gaps.md` (new files only) | MERGED PR#22 | 2026-06-13 |
| CC-C | Claude Code | Per-thesis disconfirmation registry + gaps report (sidecar; no card surfacing) | `src/disconfirmation_registry.json`; `src/disconfirmation_registry.py`; `src/test_disconfirmation_registry.py`; `docs/disconfirmation_gaps.md` | MERGED PR#21 | 2026-06-13 13:32 ET |
| MERGE-AUTH | Codex | Codex merge authority policy: operator-explicit only, green/accepted checks only, no bypassing conflicts or protection | `AGENTS.md`; `docs/WORKBOARD.md` | MERGED PR#25 | 2026-06-13 18:18 ET |
