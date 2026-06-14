# Queue Audit - 2026-06-12 Dispositions

Audit date: 2026-06-14
Owner: Codex
Scope: T6 hygiene, Notion queue execution, and integration-debt closeout.

## Source of Truth

- Repo workboard: `docs/WORKBOARD.md`
- Repo queue mirror: `src/system_improvement_queue.json`
- Canonical Notion queues:
  - System Update Queue data source: `968cfff4-369c-40bb-b748-5633b9ff7685`
  - CI Update Queue data source: `840a74bb-2d47-451c-bf2a-a1edafc55585`
  - Research Queue data source: `cab89576-0933-40b0-ad2e-6f9a6188e804`
- Duplicate CI Update Queue database archived: `d0024aba-c88f-43af-8370-84d8ddc26c45`

## Repo Dispositions

The 2026-06-12 through 2026-06-14 workboard audit found the following rows already merged before T6 final closeout:

- `A1`, `A2`, `B1`, `C1`, `C1A`, `P2-2`, `P2-3`, `T1`, `T2`, `T3`, `T4`, `T5`, `T7`, `T9`.
- Can-wait burndown rows now merged before this T6 pass: `C2`, `C3`, `C4`, `C5`, `P2-4`, `T8`.
- Operating-protocol row now merged: `OPS-RULES-2026-06-14`.

Rows deliberately not closed by this audit:

- `D` / AUTO-OK lane design remains deferred; no implementation in this slice.
- `PARABOLIC-TRIGGER` remains a separate `PR#29` row; T6 did not mutate that row.

## Hygiene Dedupe

Already shipped before this T6 implementation:

- Source Call Log scoring-lag sweep: covered by `source_call_tracker.py --scoring-lag` and source-calibration sibling tests.
- Source-calibration staleness guard: covered by the calibration-chain guard in preflight/orchestrator paths and related tests.
- UW comma-delimiter doc fix: repo documentation/tests use comma-delimited ticker filters, not pipe-delimited filters.
- Quality-ladder rename: repo source-calibration surfaces use the call-quality ladder without the prior overloaded operator-facing tier wording.

Implemented in this T6 branch:

- Canonical-prior enforcement: `outcome_logger.py` and `conviction_sizing_calibrator.py` now reject `sample_inputs/` paths before reading canonical portfolio, thesis, macro, rationale, and source-rate inputs.
- Added focused tests in `src/test_t6_hygiene_guards.py`.

## Notion Execution

Done-flips applied:

- `36dc5031-4bb6-8170-bd16-c40e5b1eafb5` - Canonical-prior enforcement - CI Update Queue - `Done`.
- `36ec5031-4bb6-81b3-bdef-f59c6491d041` - Source-call quality-ladder rename - CI Update Queue - `Done`.
- `36dc5031-4bb6-8176-b48a-fa0733e69740` - UW get_stock_screener delimiter syntax - System Update Queue - `Done`.
- `36ec5031-4bb6-81d1-bde1-ed721c38943a` - Source Call Log scoring-lag sweep - System Update Queue - `Done`.
- `36ec5031-4bb6-8184-920c-d5b35a4f60ad` - Log-to-cache source-calibration staleness guard - System Update Queue - `Done`.
- `37dc5031-4bb6-81ac-a303-ef237564a13c` - Gate semantics close/touch/near-certain - System Update Queue - `Done`.
- `37dc5031-4bb6-816f-bfeb-c315e5aad3fb` - Full-text monthly ingestion and tactical-picks extension - System Update Queue - `Done`.
- `37dc5031-4bb6-81c7-a7ad-e333cc21979e` - 6/12 housekeeping catalyst/Fundstrat row - System Update Queue - `Done`.
- `37dc5031-4bb6-8144-9bcc-cee5e97aab60` - Look-through auto-disclosure on add/trim cards - System Update Queue - `Done`.

Working mark applied:

- `372c5031-4bb6-81d4-9905-e38369749e7a` - Patch-cadence / integration-debt governor - refiled from Research Queue to System Update Queue and kept `Working`.

Archive action applied:

- Moved duplicate CI Update Queue database `d0024aba-c88f-43af-8370-84d8ddc26c45` under `Investing - Archive` (`36dc5031-4bb6-813d-a5ff-d8bcb6b84b53`).
- Canonical CI Update Queue remains `840a74bb-2d47-451c-bf2a-a1edafc55585`.

Rows intentionally left untouched:

- `37dc5031-4bb6-8141-890b-cf4aa9d27625` - AUTO-OK lane, deferred by operator instruction.
- `37cc5031-4bb6-8170-b0ca-c628b6456264` - broader approximate posture look-through display, not identical to the C3 card disclosure slice.
- Research/ticker rows without direct T6 or merged-workboard coverage.

## Integration-Debt Closeout

Initial sweep showed warnings for:

- `options_exit`: v11.10 options-exit cadence was not visibly wired.
- `module_wiring`: `options_expiry_preflight.py` orphan.
- `module_wiring`: `stale_leaps_scan.py` orphan.
- `notion_queue`: Notion queue rows not supplied to the read-only sweep.

T6 wiring decision:

- Weekly Pilot now owns the manual review surface for the v11.10 options-exit cadence.
- `options_expiry_preflight.py` is referenced as the portfolio/options-export expiry preflight.
- `stale_leaps_scan.py` is referenced as the ticker-specific follow-up for stale long-dated contracts.
- `rationale_decay_v3.py` remains the rule engine; missing option exports are `not_checked`, not clean.

Post-fix sweep result:

- Requested `options_exit`, `options_expiry_preflight.py`, and `stale_leaps_scan.py` warnings dropped.
- Remaining warning is only the expected `notion_queue` not-checked warning when the sweep is run without a connector/export snapshot.

## Verification

- Focused tests: `25 passed`.
- Integration debt sweep after wiring: `1 warning(s), 14 total finding(s)` with no requested options-exit/orphan warnings remaining.
