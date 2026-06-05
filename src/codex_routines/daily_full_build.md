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
   python src/heartbeat_status.py --src-dir src --out src/heartbeat.json --summary src/heartbeat_summary.json
   python src/heartbeat_status.py --validate src/heartbeat.json
   ```

5. The heartbeat strip is operational status only. A `down` or `stale` heartbeat
   row does not create a trade; it tells the dashboard why live confidence is
   limited.
6. Run:

   ```bash
   python src/live_readiness.py --src-dir src
   ```

7. If `go_live_ready` is false, treat the report as the current status and do
   not force-publish. `rehearsal_ready` means the build can run, not that the
   live market/source lanes are populated.
8. When the readiness report is clean, run:

   ```bash
   python src/full_build_runner.py --src-dir src --feed-out src/latest_cockpit_feed.json --publish
   ```

   For the local live dashboard path, prefer the one-command refresh:

   ```bash
   python src/live_dashboard_refresh.py
   ```

   This writes heartbeat status, publishes a feed, refreshes repo-evidence
   Daily Synthesis from that feed, republishes, and renders both the canonical
   JSX artifact and the summary/preview HTML. The final JSON summary is the
   operator readout: it includes `go_live_ready`, required-input status, live
   market-data status, action count/top actions, data-lane count, dark lanes,
   source-call calibration status, and the preview path.

   Current local preview:

   ```text
   http://127.0.0.1:8765/dashboard_preview.html
   ```

9. If publish fails, do not force-write a feed. Report the publish-gate problems.
10. Run focused checks:

   ```bash
   python -m pytest src/test_full_build_runner.py src/test_live_readiness.py src/test_heartbeat_status.py src/test_runtime_full.py src/test_cockpit_blocks.py src/test_live_dashboard_refresh.py -q
   ```

11. Summarize:
   - action count
   - ACT_NOW names
   - research-action count
   - dark-lane count
   - stale/failed source count
   - `go_live_ready`
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
