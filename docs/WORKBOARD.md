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
| C1 | Codex | Post-close Positions Sync wrapper at 4:45 PM ET plus one manual 6/12 reconciliation run | `src/codex_routines/Positions_Sync_Routine_Prompt_v1.md`; `src/cloud_ops_status.py`; `src/cloud_automation_status.json`; `src/cloud_routine_commit.py`; position refresh artifacts | PR#12 | 2026-06-12 19:37 ET |
| C1A | Codex | Account-map semantics: executable tax_status plus PCRA/crypto placement flags from 6/12 SnapTrade handoff | `src/account_rules.json`; `src/execution_plan.py`; `src/test_execution_plan.py`; `src/state_ownership_map.json` | PR#12 | 2026-06-12 19:49 ET |
| C2 | Codex | Gate semantics: close/touch/near-certain with 6/11 QQQ trap test | `src/timing_gates.json`; `src/timing_engine.py`; related tests | CLAIMED | 2026-06-12 19:25 ET |
| C3 | Codex | Look-through auto-disclosure for wrapper ETFs on add/trim cards | look-through map/config; `src/today_decide.py`; execution/render tests | CLAIMED | 2026-06-12 19:25 ET |
| C4 | Codex | Bible tactical extension: tactical top/bottom and named levels; full-text monthly checklist | `src/fundstrat_bible.json`; `src/fundstrat_sector_stances.py`; FundStrat intake docs/tests | CLAIMED | 2026-06-12 19:25 ET |
| C5 | Codex | June catalyst additions and Notion Catalyst Calendar mirror | `src/catalysts.json`; catalyst intake outputs; Notion Catalyst Calendar | CLAIMED | 2026-06-12 19:25 ET |
| D | Codex | AUTO-OK lane design: analysis/code/docs only, never trades/doctrine/honesty rails | design doc; queue row `37dc5031-4bb6-8141-890b-cf4aa9d27625` | CLAIMED | 2026-06-12 19:25 ET |
| P2-2 | Codex | FS ingestion completeness guard and inventory backfill for active Bible layers | `src/fs_ingest_inventory.json`; `src/fs_ingest_guard.py`; FundStrat dashboard/morning warning channel | CLAIMED | 2026-06-12 19:25 ET |
| P2-3 | Codex | Cadence-aware overdue alerts by extending receipts/heartbeat stack | `src/cloud_routine_receipts.py`; `src/cloud_ops_status.py`; `src/heartbeat_status.py`; dashboard/preflight warnings | CLAIMED | 2026-06-12 19:25 ET |
| P2-4 | Codex | Insider feed live unstub plus stale Patch-F row audit/closure | `src/session_orchestrator.py`; insider cache/intake path; Notion rows `36dc5031-4bb6-81f8-b2ec` and `36dc5031-4bb6-8124` | CLAIMED | 2026-06-12 19:25 ET |
| CLOUD-FS-DAYTIME | cloud routines | Fundstrat Daytime Watch scheduled run | `src/fundstrat_*`; `src/source_calls.json`; `src/cloud_routine_receipts.json`; dashboard artifacts | MERGED | 2026-06-12 19:25 ET |
| CLOUD-BROKER-INTAKE | cloud routines | Existing 8:20 AM ET SnapTrade broker intake; remains owner of core position files | `src/positions.json`; `src/account_positions.json`; `src/position_reconciliation.json` | MERGED | 2026-06-12 19:25 ET |
| CLAUDE-SNAPTRADE-CONVERTER | Claude | Withdrawn `snaptrade_to_combined.py` converter; do not import. If compatibility CLI is ever needed, build a thin wrapper over `build_combined_from_snaptrade`; possible low-priority account-map semantics may fold into SnapTrade profiles later. | none | SUPERSEDED | 2026-06-12 19:25 ET |
