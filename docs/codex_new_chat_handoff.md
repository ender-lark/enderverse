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

- Latest completed slice before this handoff refresh: open action resolver and
  dashboard preview server helper.
- `docs/codex_build_queue.md` is the canonical queue.
- The user explicitly said to focus on building the working system first and not
  spend time on stock research such as AVGO.
- Dashboard parity review is complete; JSX injection is canonical, generated HTML is a summary/export path.
- Fundstrat daily email intake and direct monthly PDF/text/JSON upload intake are supported.
- Fundstrat Gmail snippet discovery and full-body ingestion now use separate
  state fields. Snippet-only rows are tracked in
  `snippet_discovery_message_ids`; only full-body rows are tracked in
  `processed_full_body_message_ids` / `processed_message_ids`. The current
  state was migrated so the 10 old snippet-only messages are not blocked from a
  later `batch_read_email` full-body intake.
- Event Risk now has supplied data from compact Fundstrat-derived full-body
  evidence. `src/event_risks.json` stores only metadata/brief summaries, not raw
  email bodies. The lane promotes one conservative exposure-review action for
  oil/rates shock risk; no buy/sell order is implied.
- `src/event_risk_intake.py` now also accepts a one-line supplied sudden-event
  row via CLI flags (`--title`, `--channels`, `--tickers`, `--why`,
  `--trigger`). Use this when a fast headline such as Iran/oil/rates risk needs
  to enter the dashboard before a full JSON event scan exists.
- `src/manual_source_drop.py` can route one supplied JSON file with explicit
  `event_risks`, `signal_log`, and/or `catalysts` sections through the existing
  intake normalizers. It supports dry-run checks and rejects ambiguous generic
  `events` rows rather than guessing the lane.
- `docs/manual_drop.template.json` is a tested starting template for manual
  source drops. Validate without writing via:
  `python src/manual_source_drop.py docs/manual_drop.template.json --src-dir src --validate-only`.
- FS Daily now has compact full-body-derived data from Gmail evidence. The
  compact intake wrote `XOP`, `RYF`, and `TNX` daily-call rows, redacted audit
  entries, inbox dates, and state without committing raw email bodies. Empty
  daily calls remain checked clear only after at least one full-body daily email
  is parsed.
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
- `src/daily_synthesis_from_feed.py` can also build a conservative
  repo-evidence synthesis from `src/latest_cockpit_feed.json`. It writes no
  structured synthesis actions and keeps missing Catalyst Calendar / Signal Log
  lanes visible as unresolved.
- `src/signal_log_intake.py` can normalize supplied Signal Log or Morning Scan
  JSON into `src/signal_log.json`; rows are watch-only and never promote actions
  directly.
- `src/codex_routine_manifest.json` now has nine active routines, including
  `daily_synthesis_intake` and `signal_log_intake`; the current repo has a
  populated repo-evidence `src/daily_synthesis.json` and still has no populated
  `src/signal_log.json`.
- Current live-readiness probe on the repo reports `rehearsal_ready: true`,
  `required_inputs_ready: true`, `live_data_ready: true`,
  `publish_ready: true`, and `go_live_ready: true`.
- Current dark lanes are `catalysts` and `signal_log`. These are
  not hard go-live blockers, but the dashboard now shows what input to supply
  next for each.
- Target Drift now promotes held, materially undersized names into conservative
  `conviction_gap` actions. The current feed surfaces NVDA as a funded
  add/rotation review (`6.6%` actual versus `12.0%` target), while missing
  target names and MONITOR sleeves stay out of Today's Actions.
- The first publish path succeeded:
  `python src/full_build_runner.py --src-dir src --feed-out src/latest_cockpit_feed.json --publish`.
  It wrote `src/latest_cockpit_feed.json`; current daily action memory is now
  maintained by the live refresh and can be inspected with
  `python src/action_memory_resolve.py --list`.
- The local one-command live dashboard refresh is now:
  `python src/live_dashboard_refresh.py`.
  It writes heartbeat status, publishes a feed, refreshes repo-evidence Daily
  Synthesis from that feed, republishes, renders
  `src/rendered/conviction_cockpit_v5.jsx`, writes `docs/index.html`, refreshes
  `tmp/dashboard_preview.html`, writes `tmp/dashboard_parity_feed.json`, and
  prints a final operator summary with actions, data lanes, dark lanes,
  source-call status, `go_live_ready`, and local preview-server status.
- The local preview helper is:
  `python src/dashboard_preview_server.py --check` to inspect status, or
  `python src/dashboard_preview_server.py` to serve `tmp/dashboard_preview.html`
  on `http://127.0.0.1:8765/dashboard_preview.html`.
- The compact non-rebuilding live status helper is:
  `python src/live_status.py`.
  It combines live readiness, preview-server state, unresolved action-memory
  rows, data-flow proof, and the system-improvement queue into one JSON
  readout. Its `data_flow` section shows feed timestamp, source dates, lanes
  with data, dark/stale lane counts, action counts, and top action.
- The go-live checklist helper is:
  `python src/go_live_checklist.py`.
  It is non-mutating and summarizes refresh/status, live data flow, preview,
  manual source-drop validation, open action reviews, queue state, and optional
  dark lanes. With the current repo it reports `go_live_ready: true` and
  checklist status `warn` because open reviews and optional dark lanes remain.
  Use `python src/go_live_checklist.py --format text` for the human-readable
  PASS/WARN command checklist.
- The open action-memory resolver is:
  `python src/action_memory_resolve.py --list` to inspect unresolved items, or
  `python src/action_memory_resolve.py --review-report` to inspect age,
  review prompts, and suggested resolution commands, or
  `python src/action_memory_resolve.py --ticker <TICKER> --status deferred --reason "..."`
  to resolve an item into history after operator review.
- The published feed has been rendered through the canonical JSX injector:
  `python src/render_cockpit.py src/latest_cockpit_feed.json --out src/rendered/conviction_cockpit_v5.jsx`.
  The rendered artifact contains generated_at
  `2026-06-05T10:03:31.604897+00:00`.
- The canonical JSX cockpit and generated summary/preview dashboard both have
  an Operator Status card near the top. It summarizes action count, open
  reviews, source-lane warning state, and the
  `python src/go_live_checklist.py --format text` command.
- Current `src/open_opportunities.json` has 2 open watch/review items:
  `ANET` and `GOOGL`.
- Current `python src/live_status.py` reports `live_summary:
  live_with_open_reviews`, `go_live_ready: true`, 4 actions, 0 research
  actions, 2 dark optional lanes (`catalysts`, `signal_log`), 2 open
  action-memory reviews (`ANET`, `GOOGL`), preview server running, and 0
  active/queued system-improvement items. Its data-flow proof shows feed
  `2026-06-05T10:03:31.604897+00:00`, 11 lanes with data, 2 dark lanes, and
  top action `event_risk`.
- `render_cockpit.py` console caveat output is ASCII-safe for Windows; a
  regression test covers cp1252 encoding of the caveat line.

Current verification baseline:

- `python -m pytest src -q` -> `941 passed, 6 skipped`.
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
