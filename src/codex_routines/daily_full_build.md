# Daily Full Build Routine

## Objective

Build the cockpit feed from repo convention files, publish only if the feed
passes the publish gate, and keep unresolved actions durable.

This is the main replacement for Claude's FULL-build prompt.

## Procedure

1. Check the repo is on `main` and up to date.
2. Do not erase or overwrite convention files merely because a source was not
   fetched. Missing sources must remain dark lanes, not checked-clear lanes.
3. Read the `daily_full_build.convention_inputs` list in
   `src/codex_routine_manifest.json` before the build:
   - required inputs such as `positions` and `theses` must exist or the build
     should fail;
   - optional inputs such as Fundstrat, UW, catalysts, synthesis, Signal Log,
     Meridian, and calibration dates should remain not checked when absent.
4. Run:

   ```bash
   python src/full_build_runner.py --src-dir src --feed-out src/latest_cockpit_feed.json --publish
   ```

5. If publish fails, do not force-write a feed. Report the publish-gate problems.
6. Run focused checks:

   ```bash
   python -m pytest src/test_full_build_runner.py src/test_runtime_full.py src/test_cockpit_blocks.py -q
   ```

7. Summarize:
   - action count
   - ACT_NOW names
   - research-action count
   - dark-lane count
   - stale/failed source count
   - whether `open_opportunities.json` was updated

## Rules

- Action clarity beats architectural elegance.
- A buy, sell, trim, or time-sensitive warning must surface as a durable action
  row until acted, invalidated, or aged out by explicit logic.
- The manifest convention-input contract must stay in sync with
  `full_build_runner.DEFAULT_FILES`; `codex_routine_manifest.py` validates this.
- UW flow can raise timing/confirmation, but never creates a standalone capital
  action.
- Missing source inputs are not checked; they are not quiet tape.
