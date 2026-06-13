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
4. If a manual event/signal/catalyst drop is supplied, ingest it before the
   heartbeat/readiness check:

   ```bash
   python src/manual_source_drop.py <manual-drop.json> --src-dir src
   ```

   The drop must use explicit top-level keys: `event_risks`, `signal_log`,
   and/or `catalysts`. Do not route ambiguous generic `events` rows.
   Start from `docs/manual_drop.template.json` and validate before writing when
   the drop is new:

   ```bash
   python src/manual_source_drop.py <manual-drop.json> --src-dir src --validate-only
   ```
5. Run:

   ```bash
   python src/heartbeat_status.py --src-dir src --out src/heartbeat.json --summary src/heartbeat_summary.json
   python src/heartbeat_status.py --validate src/heartbeat.json
   ```

6. The heartbeat strip is operational status only. A `down` or `stale` heartbeat
   row does not create a trade; it tells the dashboard why live confidence is
   limited.
7. Run:

   ```bash
   python src/live_readiness.py --src-dir src
   ```

8. If `go_live_ready` is false, treat the report as the current status and do
   not force-publish. `rehearsal_ready` means the build can run, not that the
   live market/source lanes are populated.
9. For a compact status readout before or after the full refresh, run:

   ```bash
   python src/live_status.py
   python src/go_live_checklist.py
   python src/go_live_checklist.py --format text
   ```

   This does not rebuild or publish. It combines live readiness, preview-server
   state, unresolved action-memory rows, the system-improvement queue, and the
   go-live operating checklist.
10. When the readiness report is clean, run:

   ```bash
   python src/full_build_runner.py --src-dir src --feed-out src/latest_cockpit_feed.json --publish
   ```

   For the local live dashboard path, prefer the one-command refresh:

   ```bash
   python src/trigger_check.py --write --send --routine-id investing-os-post-close-refresh --format text
   python src/live_dashboard_refresh.py
   ```

   The trigger check should run before the render when this is the 4:30 PM ET
   post-close refresh, so `trigger_check_summary.json` is visible in the
   dashboard source-audit row. The dashboard refresh writes heartbeat status,
   publishes a feed, refreshes repo-evidence Daily Synthesis from that feed,
   republishes, and renders both the canonical JSX artifact and the
   summary/preview HTML. The final JSON summary is the operator readout: it
   includes `go_live_ready`, required-input status, live market-data status,
   action count/top actions, data-lane count, dark lanes, source-call
   calibration status, trigger-check status, and the preview path.

   Current default local dashboard:

   ```text
   http://127.0.0.1:8765/dashboard_preview.html
   ```

   JSX remains an internal parity/validation preview:

   ```text
   http://127.0.0.1:8765/cockpit_jsx_preview.html
   ```

   If the preview URL is not already being served, run:

   ```bash
   python src/dashboard_preview_server.py
   ```

11. If publish fails, do not force-write a feed. Report the publish-gate problems.
12. Run focused checks:

   ```bash
   python -m pytest src/test_full_build_runner.py src/test_live_readiness.py src/test_heartbeat_status.py src/test_runtime_full.py src/test_cockpit_blocks.py src/test_live_dashboard_refresh.py -q
   ```

13. Summarize:
   - action count
   - ACT_NOW names
   - research-action count
   - dark-lane count
   - stale/failed source count
   - trigger-check fired/not_checked count
   - `go_live_ready`
   - whether `open_opportunities.json` was updated
14. If open action-memory items remain after operator review, list or resolve
    them explicitly:

   ```bash
   python src/action_memory_resolve.py --list
   python src/action_memory_resolve.py --review-report
   python src/action_memory_resolve.py --ticker ANET --status deferred --reason "wait for setup"
   ```

## Rules

- Action clarity beats architectural elegance.
- A buy, sell, trim, or time-sensitive warning must surface as a durable action
  row until acted, invalidated, or aged out by explicit logic.
- The manifest convention-input contract must stay in sync with
  `full_build_runner.DEFAULT_FILES`; `codex_routine_manifest.py` validates this.
- UW flow can raise timing/confirmation, but never creates a standalone capital
  action.
- Missing source inputs are not checked; they are not quiet tape.
