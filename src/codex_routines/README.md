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

2. UW cache refresh
   - Refresh `uw_opportunity_signals.json` and, when scheduled, `parabolic_setups.json`.
   - Run the UW orchestrator as a module from `src`.

3. Daily full build
   - Run `full_build_runner.py`.
   - Publish only through the publish gate.
   - Update action memory only after the feed is publish-safe.

4. Off-hours research queue
   - Process queued research only after the daily action surface is trustworthy.
   - No trade actions from UW alone.

## Shared Paths

- Repo: `C:\Users\suraj\Documents\Codex\2026-06-04\confirm-you-can-access-my-github\work\enderverse`
- Fundstrat drop folder: `G:\My Drive\Codex\Investing OS Context\03_Inbox\Fundstrat_Email_Drop`
- Working notes: `G:\My Drive\Codex\Investing OS Context\06_Working_Notes`

## Activation State

The first Codex automations should be created paused until we confirm schedules
and output routing. The code paths are ready; the live data acquisition layer is
still being expanded.
