# Codex New Chat Handoff

Use this prompt to restart the Investing OS rebuild in a fresh Codex chat.

## Copy/Paste Prompt

You are continuing the Investing OS rebuild in repo `ender-lark/enderverse`.

Workspace path on this machine:
`C:\Users\suraj\Documents\Codex\2026-06-04\confirm-you-can-access-my-github\work\enderverse`

Start by reading these files:

- `AGENTS.md` if present in the workspace root.
- `docs/codex_build_queue.md`
- `src/state_ownership_map.json`
- `src/full_build_runner.py`
- `src/feed_assembler.py`
- `src/conviction_cockpit_v5.jsx`
- `src/feedback_summary.py`

Current priority:

1. Read `docs/codex_build_queue.md` and promote only evidence-backed slices.
2. Prioritize system/routine/dashboard buildout over stock-specific research.
3. Keep dashboard parity classification current before any feed/dashboard UI work.
4. Use `python src/verify_standard.py` as the standard verification command.
5. Commit and push after each clean verified slice.

Important recent state:

- Latest completed slice before this handoff refresh: Dark-lane next-step
  guidance.
- `docs/codex_build_queue.md` is the canonical queue.
- The user explicitly said to focus on building the working system first and not
  spend time on stock research such as AVGO.
- Dashboard parity review is complete; JSX injection is canonical, generated HTML is a summary/export path.
- Fundstrat daily email intake and direct monthly PDF/text/JSON upload intake are supported.
- Monthly Core List tables are intentionally not stored. Treat Core List table
  ingestion as out of scope for the current system build and do not assume it is
  a future requirement; only a new explicit user request should reopen it.
  Top-5/Bottom-5 and separate Consider List rows are the monthly
  prospect-signal path.
- AVGO remains unassessed until an actual thesis is written, but its timing
  catalyst has passed; it is now a low-priority queued Research Queue item, not
  an immediate From Research action.
- The stale retired `src/test_reallocate.py` workaround has been removed; plain full-suite pytest passes.
- `src/codex_routine_manifest.json` now records all 20 convention inputs read
  by `daily_full_build`, including required versus optional status and
  missing-input behavior.
- `src/codex_routine_manifest.py` validates that every
  `full_build_runner.DEFAULT_FILES` key has daily routine-manifest coverage.
- `src/state_ownership_map.py` validates that every
  `full_build_runner.DEFAULT_FILES` key has state-ownership feed-path coverage.
- `src/full_build_runner.py` now reports `dark_lane_keys`,
  `missing_required_inputs`, and `missing_optional_inputs` in dry-run CLI
  output, using the manifest convention-input contract.
- `src/live_readiness.py --src-dir src` reports current go/no-go status without
  fetching or publishing. It distinguishes a runnable rehearsal build from a
  live-ready build and treats missing UW price/macro caches as minimum
  market-data blockers. If those files are present, it validates them with the
  existing UW price and macro validators before `live_data_ready` can turn true.
- `src/live_readiness.py` also validates present required convention inputs
  before live/publish readiness. It reuses the existing positions freshness
  rule: `positions.json` `snapshot_date` is fresh through 7 days; stale,
  missing-date, unparseable, future-dated, or bare-list snapshots block
  `go_live_ready` while still allowing rehearsal when the build itself can run.
- Current `positions.json` snapshot is `2026-05-31`; under the 2026-06-05
  clock it is fresh at 5 days old.
- Source lane status now requires delivered dated items for `has_data`; a
  cleanly registered but empty source is `checked_clear`, not data.
- Not-checked lane-status rows now carry structured `next_step` and
  `missing_impact` metadata. The readiness report prioritizes Event Risk,
  Catalysts, and Daily Synthesis in its next steps so fast-moving war/oil/rates
  shocks do not get buried in optional-lane bookkeeping.
- `src/heartbeat_status.py` writes `src/heartbeat.json` and
  `src/heartbeat_summary.json` from repo-local readiness evidence. It reports
  required-input, minimum-market-data, publish-gate, optional-lane, and daily
  build status; it does not fetch sources or create trade actions.
- The current repo has a valid `src/heartbeat.json` and
  `src/heartbeat_summary.json` snapshot. It shows Required Inputs, Minimum
  Market Data, Publish Gate, and Daily Full Build as `ok`; Optional Source Lanes
  remain `stale` because optional lanes such as Fundstrat Bible, Catalysts,
  Synthesis, Signal Log, and Top Prospects are dark.
- Absent optional price cache now leaves `uw_price` not checked instead of
  registering an empty price source as `has_data`.
- `src/uw_price_cache_intake.py` can normalize supplied UW close-price responses
  or close arrays into `src/uw_closes.json` and validates all default rotation
  tickers have enough history before writing.
- `src/macro_pulse_scan.py --emit-state` writes a `src/macro_state.json` cache
  that works for both session preflight regime/freshness checks and the full
  cockpit `uw_macro` lane; `--validate` reports structured failures for absent
  or malformed macro caches.
- The UW cache refresh routine manifest/docs own `src/uw_closes.json`,
  `src/uw_price_cache_summary.json`, `src/macro_state.json`, and
  `src/macro_pulse_summary.json`. The current repo now has validated populated
  versions of all four files.
- `src/daily_synthesis_intake.py` can normalize supplied Daily Synthesis JSON
  into `src/daily_synthesis.json`, preserving structured action metadata without
  generating market content.
- `src/signal_log_intake.py` can normalize supplied Signal Log or Morning Scan
  JSON into `src/signal_log.json`; rows are watch-only and never promote actions
  directly.
- `src/codex_routine_manifest.json` now has eight active routines, including
  `daily_synthesis_intake` and `signal_log_intake`; the current repo still has
  no populated `src/daily_synthesis.json` or `src/signal_log.json`.
- Current live-readiness probe on the repo reports `rehearsal_ready: true`,
  `required_inputs_ready: true`, `live_data_ready: true`,
  `publish_ready: true`, and `go_live_ready: true`.
- Current dark lanes are `catalysts`, `synthesis`, `signal_log`, and
  `event_risk`. These are not hard go-live blockers, but the dashboard now
  shows what input to supply next for each.
- The first publish path succeeded:
  `python src/full_build_runner.py --src-dir src --feed-out src/latest_cockpit_feed.json --publish`.
  It wrote `src/latest_cockpit_feed.json` and updated
  `src/open_opportunities.json` with 0 open action-memory items.
- The published feed has been rendered through the canonical JSX injector:
  `python src/render_cockpit.py src/latest_cockpit_feed.json --out src/rendered/conviction_cockpit_v5.jsx`.
  The rendered artifact contains generated_at
  `2026-06-05T07:01:39.270529+00:00`.
- `render_cockpit.py` console caveat output is ASCII-safe for Windows; a
  regression test covers cp1252 encoding of the caveat line.

Current verification baseline:

- `python -m pytest src -q` -> `881 passed, 6 skipped`.
- `python src\test_reallocate_rebuild.py` -> passed.
- `python src\verify_standard.py` passed with the full pytest tree plus the standalone self-tests.

Working rules:

- One implementation slice per turn.
- Commit and push after every clean slice.
- Do not do more UI work until dashboard parity review is complete.
- GitHub JSON/docs are canonical for now; Notion sync can come later.
- Treat any short non-conflicting user reply as continue; explicit stop/pause/change-direction overrides.
- Focus on the user's core goal: early retirement through asymmetric opportunities, high conviction, and clear durable actions.

Recommended next command sequence:

```powershell
cd C:\Users\suraj\Documents\Codex\2026-06-04\confirm-you-can-access-my-github\work\enderverse
git fetch origin
git status --short
git log origin/main -5 --oneline
```

Then read `docs/codex_build_queue.md`; there is currently no queued
implementation slice. `src/system_improvement_queue.json` is also clean after
post-basic queued-upgrade triage. Promote the next slice only from fresh
audit/user evidence.

Do not start with stock-specific research. If no concrete implementation slice
is queued, run a fresh completion audit and promote the next system/routine/UI
gap from current repo evidence.

## Dashboard Parity Status

The dashboard parity review and guardrail are complete:

- `src/conviction_cockpit_v5.jsx` via JSX injection is canonical.
- `docs/index.html` is a generated summary/export path.
- `docs/dashboard_feed_block_classification.json` classifies feed blocks.
- `src/test_dashboard_parity_guardrail.py` protects feed-block classification.

Before any future feed/dashboard meaning or UI work, refresh the parity review
and classification first.
