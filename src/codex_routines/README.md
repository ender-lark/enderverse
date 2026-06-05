# Codex Investing OS Routines

These are repo-owned routine definitions for replacing Claude-only cloud prompts.
They describe what the recurring Codex automations should do and which repo
entry points they should call.

Core rule: routines gather and write convention files; the engine remains pure.

## Machine-Readable Manifest

`src/codex_routine_manifest.json` is the automation control plane. It records
each routine's doc, cadence, input boundary, owned output files, allowed
commands, verification command, and no-input behavior. The `daily_full_build`
entry also records every `full_build_runner.DEFAULT_FILES` convention input it
can consume, whether that input is required, and how absence should surface.

Validate and list it with:

```bash
python src/codex_routine_manifest.py
python src/codex_routine_manifest.py --list
```

Automation should read the manifest first, then the linked routine doc. The
manifest is intentionally not a live runner: source acquisition still requires
the relevant connector/drop-folder context, and missing inputs must remain
not-checked instead of being treated as clear.

## Routine Order

1. Fundstrat intake
   - Parse forwarded/exported Fundstrat emails, or Gmail search results when the
     connector is available.
   - Parse direct monthly Fundstrat PDF/text/JSON uploads into the compact
     `fundstrat_bible.json` deck shape: useful summary sections only, not raw
     stock-price chart text or Core List tables. Do not reopen Core List table
     parsing unless the user makes a new explicit request after the working
     system is in place. Top-5/Bottom-5 and separate Consider List rows can
     feed `top_prospects.json`.
   - Write `fundstrat_daily_calls.json`, `fundstrat_inbox_entries.json`,
     `inbox_call_dates.json`, and `source_call_candidates.json`.
   - Merge full-body action-like daily calls into `top_prospects.json` so the
     prospects lane is produced before the full build.
   - In the same full-body intake run, merge classified candidates into
     `source_calls.json` and `log_call_dates.json`. Use
     `source_call_cache_merge.py` only for manual remerge of existing
     candidates.

2. Catalyst intake
   - Parse exported/uploaded Catalyst Calendar rows.
   - Write `catalysts.json` only when catalyst rows were actually fetched or
     supplied.
   - Held-name near-term catalysts surface through the full build as ACT_NOW
     pre-catalyst review actions.

3. Broker position intake
   - Convert uploaded text-based broker-position PDFs into extractor
     `combined.json` with `broker_pdf_extractor.py`, or consume a stronger
     externally generated `combined.json`.
   - Refresh `positions.json` for the engine.
   - Refresh `account_positions.json` and `position_reconciliation.json` for
     account-level holdings and trade diffs.

4. UW cache refresh
   - Normalize supplied UW close-price responses into `uw_closes.json` with
     `uw_price_cache_intake.py`; the intake refuses incomplete default rotation
     coverage unless an operator explicitly allows partial output.
   - Build and validate `macro_state.json` from supplied yield-curve and
     cross-asset macro inputs; the cache must work for both session preflight
     freshness and the full-build macro lane.
   - Refresh `uw_opportunity_signals.json` and, when scheduled, `parabolic_setups.json`.
   - Run the UW orchestrator as a module from `src`.

5. Daily Synthesis intake
   - Normalize supplied Daily Synthesis JSON into `daily_synthesis.json`.
   - Preserve structured action metadata without inventing market content.
   - Missing supplied synthesis remains not checked.

6. Signal Log intake
   - Normalize supplied Signal Log or Morning Scan JSON into `signal_log.json`.
   - Preserve watch-only context; this routine never promotes actions directly.
   - Missing supplied signal log remains not checked.

7. Daily full build
   - Run `full_build_runner.py`.
   - Publish only through the publish gate.
   - Update action memory only after the feed is publish-safe.

8. Off-hours research queue
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
- The daily full-build routine's `convention_inputs` list is the source of
  truth for required versus optional convention files. A missing required file
  is a build failure; a missing optional file is a not-checked/dark-lane fact,
  not an all-clear read.
- `TARGET DRIFT` compares `positions.json` against the explicit AI working model
  in `reallocate_config.py` through `position_drift_check.target_weight_drift`.
- Target drift is a sizing-gap surface. It can make "right idea, wrong size"
  visible at session open, but it is not an automatic trade instruction.

## Improvement Queue

- Deferred and lower-priority build items live in `system_improvement_queue.json`.
- Validate the queue with `python src/system_improvement_queue.py`.
- Keep the queue for product/system improvements, not live market calls.

## State Ownership

- Storage and surfacing ownership rules live in `state_ownership_map.json`.
- Validate the map with `python src/state_ownership_map.py`.
- A state object should not be added to Notion, GitHub, Gmail intake, or a cache
  routine unless its dashboard/preflight surface and not-checked behavior are
  explicit.
