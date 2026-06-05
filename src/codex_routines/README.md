# Codex Investing OS Routines

These are repo-owned routine definitions for replacing Claude-only cloud prompts.
They describe what the recurring Codex automations should do and which repo
entry points they should call.

Core rule: routines gather and write convention files; the engine remains pure.

## Routine Order

1. Fundstrat intake
   - Parse forwarded/exported Fundstrat emails, or Gmail search results when the
     connector is available.
   - Write `fundstrat_daily_calls.json`, `fundstrat_inbox_entries.json`,
     `inbox_call_dates.json`, and `source_call_candidates.json`.
   - Merge full-body action-like daily calls into `top_prospects.json` so the
     prospects lane is produced before the full build.
   - After a full-body parse, merge classified candidates into `source_calls.json`
     and `log_call_dates.json` with `source_call_cache_merge.py`.

2. Catalyst intake
   - Parse exported/uploaded Catalyst Calendar rows.
   - Write `catalysts.json` only when catalyst rows were actually fetched or
     supplied.
   - Held-name near-term catalysts surface through the full build as ACT_NOW
     pre-catalyst review actions.

3. Broker position intake
   - Convert uploaded broker-position PDFs into extractor `combined.json`.
   - Refresh `positions.json` for the engine.
   - Refresh `account_positions.json` and `position_reconciliation.json` for
     account-level holdings and trade diffs.

4. UW cache refresh
   - Refresh `uw_opportunity_signals.json` and, when scheduled, `parabolic_setups.json`.
   - Run the UW orchestrator as a module from `src`.

5. Daily full build
   - Run `full_build_runner.py`.
   - Publish only through the publish gate.
   - Update action memory only after the feed is publish-safe.

6. Off-hours research queue
   - Normalize supplied/exported Research Queue rows with
     `research_queue_intake.py`.
   - Write `research_queue.json` only when queue rows were actually supplied.
   - No trade actions from UW alone.

## Shared Paths

- Repo: `C:\Users\suraj\Documents\Codex\2026-06-04\confirm-you-can-access-my-github\work\enderverse`
- Fundstrat drop folder: `G:\My Drive\Codex\Investing OS Context\03_Inbox\Fundstrat_Email_Drop`
- Catalyst drop folder: `G:\My Drive\Codex\Investing OS Context\03_Inbox\Catalyst_Calendar_Drop`
- Broker PDF drop folder: `G:\My Drive\Codex\Investing OS Context\03_Inbox\Broker_Position_Drop`
- Research Queue drop folder: `G:\My Drive\Codex\Investing OS Context\03_Inbox\Research_Queue_Drop`
- Working notes: `G:\My Drive\Codex\Investing OS Context\06_Working_Notes`

## Activation State

The first Codex automations are active on the local workspace. Routines must keep
dark-lane honesty: search snippets are discovery-only, missing sources are not
checked, and generated convention files should only be updated when the relevant
source was actually fetched or supplied.

## Preflight Surfacing

- `daily_preflight.py` runs `session_orchestrator.orchestrate(...)`.
- `TARGET DRIFT` compares `positions.json` against the explicit AI working model
  in `reallocate_config.py` through `position_drift_check.target_weight_drift`.
- Target drift is a sizing-gap surface. It can make "right idea, wrong size"
  visible at session open, but it is not an automatic trade instruction.

## Improvement Queue

- Deferred and lower-priority build items live in `system_improvement_queue.json`.
- Validate the queue with `python src/system_improvement_queue.py`.
- Keep the queue for product/system improvements, not live market calls.
