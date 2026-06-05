# Codex Build Queue

Canonical repo queue for Investing OS rebuild work. GitHub files are canonical
until the core logic is stable; Notion sync comes later.

## Active Slice

- No active implementation slice.
  - Promote the next slice from fresh audit/user evidence before editing.
  - Keep dashboard parity classification current before committing any new
    dashboard/feed meaning or UI work.
  - Prioritize system/routine/dashboard work over stock-specific research.
  - Do not promote Fundstrat Core List table ingestion; it is out of scope for
    the current system build and may never be needed.

## External Queue Audit

2026-06-05 Notion/Claude queued-upgrade audit:

- `build_positions_cache -> outcome_logger.flatten_extractor_snapshot()` was the
  one small repo-local system upgrade still worth shipping from the old Claude
  queue. It is now complete.
- CI/routine prompt push items from the 2026-06-03 Notion handoff are not active
  repo work here because `ci/` and `routines/` folders are not present in this
  checkout, and the current repo-owned routine manifest/docs already cover the
  Codex-operated build paths.
- Catalyst Calendar duplicate-DB resolution is an external Notion/database
  cleanup, not a code blocker. Keep the lane dark until real catalyst rows are
  supplied.
- Principles/SKB authoring items are operator-side framework writing, not part
  of the working-system build.
- No additional Notion/Claude queued upgrade should be promoted without fresh
  evidence that it increases actionability, conviction, usability, or data-flow
  reliability.

## Recently Completed

- Codex cloud routine stack.
  - Replaced the single generic daily cloud-refresh assumption with a split
    Codex app automation stack: Pre-Market Source Intake (8:10 ET), Morning
    Scan (8:35), Daily Synthesis (9:30), UW Opportunity Cache (10:00),
    Parabolic Cache (10:05), Full Cockpit Build (10:30), Post-Close Refresh
    (4:30 PM), Off-Hours Worker (1:45 AM daily), Deep Synthesis (Sunday
    1:00 PM), and Weekly Pilot Run (Sunday 6:00 PM).
  - Paused the old generic `investing-os-daily-cloud-refresh` automation as
    superseded by the split routine stack.
  - Updated `src/cloud_automation_status.json` to record the app-created
    routine ids and updated `cloud_ops_status.py` so cloud readiness requires
    the full expected stack to be installed and active.
  - Missing connector/source pulls still remain visible as dark lanes instead
    of checked clear; current optional dark lane remains Catalyst Calendar.
- Cloud routine run receipts.
  - Added `src/cloud_routine_receipts.py` and
    `src/cloud_routine_receipts.json` so scheduled jobs can append auditable
    started/success/failed receipts after they run.
  - `python src/cloud_ops_status.py --format text` now reports both the active
    routine stack and the current run-receipt proof count. A newly installed
    routine stack can be ready before first run, but no live run should be
    treated as proven until a success receipt appears.
  - `cloud_ops_status.py` distinguishes `Cloud schedule ready` from
    `Cloud live-run proven`; the current first-run-pending state should be
    read as ready to run, not yet proven with live scheduled execution.
  - Latest failed receipts surface as operator gaps; first-run-pending receipts
    stay visible without marking a source lane checked clear.
- Cloud routine runner.
  - Added `src/cloud_routine_runner.py` so deterministic repo-local cloud jobs
    can wrap their command with guaranteed started/final receipts instead of
    relying on prompt-only bookkeeping.
  - Full Cockpit Build and Post-Close Refresh should use
    `python src/cloud_routine_runner.py --routine-id <id> -- python src/live_dashboard_refresh.py`
    as their core command before committing/pushing changed artifacts.
- Signal Log / Morning Scan lane populated.
  - Used Notion search/fetch against the Signal Log data source, not the failed
    SQL query path, to source recent macro, oil/Hormuz, Iran escalation, and
    metals-tariff rows.
  - Normalized six compact watch-only rows into `src/signal_log.json` via
    `python src/signal_log_intake.py tmp\signal_log_notion_compact_2026-06-05.json --out src/signal_log.json --summary src/signal_log_intake_summary.json --merge-existing`.
  - Preserved distinct row notes in `signal_log_intake.py` so the dashboard can
    show why each watch item matters without promoting direct buy/sell actions.
  - Refreshed the live dashboard package. Current status shows 12 lanes with
    data and 1 dark lane (`catalysts`); Signal Log is checked as has-data, while
    Catalyst remains dark/not checked.
- Daily cloud-ops readiness status.
  - Added `python src/cloud_ops_status.py --format text` to separate local
    go-live readiness from actual scheduled Codex cloud automation readiness.
  - The command validates the routine manifest, live dashboard status, optional
    dark source lanes, open action reviews, and whether a named daily Codex
    automation is installed and active.
  - The app-created automation id
    `investing-os-daily-cloud-refresh` is now recorded in
    `src/cloud_automation_status.json`, so
    `python src/cloud_ops_status.py --format text` reports installed=true,
    active=true, and cloud ops ready=true even when the app scheduler has not
    written a local `$CODEX_HOME/automations` TOML file.
  - Missing Catalyst pulls remain visible as a dark lane instead of being
    treated as checked clear. Open action reviews remain visible as warnings,
    not cloud-ops blockers.
- Go-live checklist event-watch parity.
  - `python src/go_live_checklist.py --format text` now includes an Active
    Event Watch row derived from the same live-status/feed evidence as the
    dashboard Operator Status card.
  - If no supplied event watch is present, the checklist warns instead of
    implying that sudden-event risk was checked clear.
- Active event-watch visibility.
  - The live status readout and dashboard Operator Status cards now derive an
    active event watch from the supplied Event Risk lane.
  - The current preview shows the Middle East oil/rates watch, impacted
    channels/tickers, and trigger evidence alongside the sudden-event refresh
    command.
  - This reduces sudden-event workflow fragility without scraping headlines or
    inventing unsourced market narrative.
- Dashboard sudden-event utility command.
  - The canonical JSX cockpit and generated HTML preview now surface the
    `sudden_event_refresh.py` command in Operator Status alongside the go-live
    checklist command.
  - This makes the fast supplied-headline workflow visible in the dashboard
    itself without changing feed semantics or creating event-risk rows.
- Sudden-event command visibility.
  - `python src/live_status.py --format text` and
    `python src/go_live_checklist.py --format text` now show the
    `sudden_event_refresh.py` command template for fast supplied
    war/oil/rates/policy shock handling.
  - This keeps the sudden-event lane actionable during go-live without adding
    automated scraping or unsourced market narrative.
- Live refresh source-call tracking.
  - `python src/live_dashboard_refresh.py` now runs
    `source_call_candidate_draft.py --merge-existing --merge-cache` after the
    first feed build and before the final dashboard build.
  - This keeps newly observed Fundstrat daily calls tracked as pending source
    calls without requiring a separate operator command, while still not scoring
    outcomes early or inventing market content.
- Position-cache normalizer convergence.
  - `build_positions_cache.py` now uses
    `outcome_logger.flatten_extractor_snapshot()` for the extractor-to-flat
    schema bridge before applying the cockpit-specific thesis filter and account
    aggregation rules.
  - This closes the older Notion/Claude queue item to wire broker position
    ingest to the same normalized snapshot seam used by trade-outcome logging.
- Dark-lane intake command surfacing.
  - `python src/live_status.py --format text` now shows exact intake commands
    for Catalyst Calendar, Signal Log, and manual source-drop validation when
    those optional lanes are dark.
  - `python src/go_live_checklist.py --format text` now points the dark-lane
    warning at the manual source-drop validation command instead of only
    sending the operator back to status.
- Source-call candidate draft helper.
  - Added `python src/source_call_candidate_draft.py` to draft pending
    source-call candidates from compact daily-call observations already present
    in the latest cockpit feed.
  - The helper can merge those candidates into `source_calls.json` and
    `log_call_dates.json` without scoring outcomes.
  - Pending source-call rows are now shown as tracked/pending, not as a warning
    unless calibration is stale or a scoring window is overdue.
- Dashboard Operator Status source-call parity.
  - Added a Source calls pill to the generated HTML preview and canonical JSX
    Operator Status card.
  - The pill warns when Fundstrat daily calls are flowing but source-call
    calibration is still not checked.
- Source-call calibration status in operator checks.
  - `python src/live_status.py --format text` now reports source-call
    calibration status, observed daily call count, and overdue count.
  - `python src/go_live_checklist.py --format text` now includes a
    Source-call calibration row, warning when unscored daily calls are flowing.
- Open-review command visibility.
  - `python src/live_status.py --format text` now includes the review-report
    command and per-ticker defer/ignore/acted commands for open
    action-memory items.
  - The go-live checklist now points status/data-flow/dark-lane rows at the
    human-readable live-status command.
- Sudden-event dashboard refresh command.
  - Added `python src/sudden_event_refresh.py` to append one supplied
    headline/event-risk row, run the live dashboard refresh, and print
    `python src/live_status.py --format text`.
  - This keeps fast war/oil/rates/policy shock handling supplied and
    auditable, while avoiding scraping or invented market narrative.
- Human-readable live status.
  - Added `python src/live_status.py --format text` for a fast operator readout
    of live readiness, data-flow proof, open-review tickers, preview state,
    blockers, dark-lane next inputs, and queue state.
  - Kept the default JSON output unchanged for scripts and checks.
- Actionable checklist warning detail.
  - `python src/go_live_checklist.py --format text` now names open-review
    tickers in the warning row.
  - Optional dark-lane warnings now include the next source input for each lane
    instead of only listing lane keys.
- HTML preview opportunity-context summary.
  - Added a compact `Opportunity context` card to the generated summary/preview
    dashboard using existing feed lanes only: Target Drift, Prospects, Radar,
    and Bullish Flow.
  - Feedback loops now show the open action-review tickers inline so the
    remaining warning is actionable from the preview.
  - Open-review rows include a ticker-specific `deferred` command hint for
    explicitly keeping a name on watch after review.
  - The card is explicitly labeled `context, not orders` and caps rows to keep
    the preview scan-friendly.
  - Refreshed the live dashboard package; the local preview now shows build
    `2026-06-05 10:20 ET` with the new context card and open-review rows.
- Live data-flow proof in operator status.
  - Extended `python src/live_status.py` with a `data_flow` section showing
    the current feed timestamp, source dates, lanes with data, dark/stale lane
    counts, action counts, and top action.
  - Added a `Live data flow` PASS/WARN row to
    `python src/go_live_checklist.py --format text`.
  - Current proof shows feed `2026-06-05T10:20:13.403157+00:00`, 11 lanes with
    data, 2 dark lanes, 4 actions, and top action `event_risk`.
- Canonical dashboard operator-status parity.
  - Added the compact Operator Status read to the canonical JSX cockpit, not
    only the generated HTML preview.
  - The card uses live feed health only: Today's Actions, open action-memory
    reviews, dark/stale/failed source lanes, and the go-live checklist command.
  - Refreshed the live dashboard package; the local preview at
    `http://127.0.0.1:8765/dashboard_preview.html` now shows build
    `2026-06-05 10:20 ET` with 4 actions, 2 open reviews, and 2 dark lanes.
- Fundstrat Daily compact live refresh.
  - Ingested three compact, full-body-derived Fundstrat daily calls from Gmail
    evidence: `XOP`, `RYF`, and `TNX`.
  - FS Daily is now a `has_data` lane, while raw email bodies remain uncommitted
    and audit entries remain redacted.
  - The rows surface as daily source/radar context; they do not create direct
    buy/sell orders.
- Compact Fundstrat Daily intake path.
  - Added `fundstrat_daily_compact_intake.py` for full-body-derived compact
    daily call rows when Gmail connector bodies cannot be safely piped into a
    local JSON file.
  - The compact path rejects raw-body-sized quotes, writes redacted audit/state
    files, and makes FS Daily checkable without storing raw publication bodies.
  - It intentionally does not update source-call calibration or top prospects;
    the full raw-body parser remains the richer path when safe connector JSON is
    available.
- Fundstrat Daily full-body honesty.
  - Changed full-build source registration so snippet-only Fundstrat discovery
    does not mark FS Daily as checked clear.
  - Empty daily calls can be checked clear only after
    `fundstrat_intake_summary.json` proves at least one full-body email was
    parsed.
  - Prioritized FS Daily in readiness next steps because daily Fundstrat emails
    are a primary source lane.
- Fundstrat-derived Event Risk live refresh.
  - Used Gmail full-body Fundstrat reads as supplied source evidence to write a
    compact `event_risks.json` cache without storing raw email bodies.
  - Captured only actionable event-risk metadata: oil/rates shock, Financials
    breadth weakness, and narrow AI leadership/rotation risk.
  - Event Risk is now a `has_data` lane with one conservative Today's Actions
    exposure-review prompt; no buy/sell order is implied.
- Fundstrat snippet-to-full-body state hardening.
  - Fixed daily Fundstrat email intake state so snippet-only Gmail discovery no
    longer marks message IDs as full-body processed.
  - Added `processed_full_body_message_ids` and `snippet_discovery_message_ids`
    semantics, preserving the ability to later upgrade the same Gmail message
    through `batch_read_email`.
  - Migrated the current snippet-only state so the 10 previously discovered
    messages remain discovery audit rows but are no longer blocked from
    full-body ingestion.
- Retired duplicate HTML generator path.
  - Removed the stale tracked `src/cockpit html gen.py` copy so generated
    dashboard summary work has a single canonical module:
    `src/cockpit_html_gen.py`.
  - Confirmed tests and docs already reference the canonical underscore path.
- Dark-lane next-step guidance.
  - Added structured `next_step` and `missing_impact` metadata to not-checked
    lane-status rows so dark lanes explain what source to supply next.
  - Prioritized sudden-event lanes in live-readiness next steps; Event Risk now
    names the daily/weekly event scan route for war, oil, rates, policy, or
    volatility shocks.
  - Mirrored the guidance into heartbeat notes, the canonical cockpit check-row
    tooltips, and the generated summary preview.
  - Closed the post-basic queued-upgrade triage item after promoting the useful
    upgrades and leaving low-signal complexity out of the basic build.
- Fundstrat monthly PDF data-flow refresh.
  - Ingested the direct May 28, 2026 Fundstrat monthly PDF into compact
    `fundstrat_bible.json` state.
  - Stored only useful monthly state: clean what-to-own themes, Top 5, and
    Bottom 5; Core List tables, chart/table clutter, and local source paths are
    excluded.
  - Fed monthly Top 5/Bottom 5 into `top_prospects.json` while keeping
    uncorroborated quiet Bottom 5 rows out of Today's Actions.
- High-conviction catalyst offensive review framing.
  - Promoted the useful part of the Notion System Update Queue catalyst
    playbook without adding options/IV automation tonight.
  - Near-term catalysts on T1/T2 non-MONITOR holdings now frame Today's Actions
    as an offensive review: add-to-target, defined-risk upside, and post-event
    dip ladder, while still requiring the gate and never auto-buying.
  - MONITOR-stance catalyst rows remain watch/risk only.
- Supplied Event Risk intake and action surfacing.
  - Added `event_risk_intake.py` for supplied daily/weekly event-risk JSON so
    sudden market-moving headlines can be checked without scraping or inventing
    market narrative.
  - Wired optional `event_risks.json` / `event_risk.json` through the full
    build, lane status, feed validation, dashboard parity classification, and
    Today's Actions promotion path.
  - High/critical supplied events now promote to conservative exposure-review
    actions only; missing scans stay not checked and empty supplied scans are
    checked clear.
- Published feed dashboard render refresh.
  - Rendered `src/latest_cockpit_feed.json` through the canonical JSX injector
    into `src/rendered/conviction_cockpit_v5.jsx`.
  - Fixed `render_cockpit.py` console caveat output so the render path is
    ASCII-safe on Windows consoles.
  - Added a regression test for Windows-console-safe caveat output.
  - Verified `render_cockpit.py --selftest` plus focused render/parity tests.
- Live launch rehearsal and first publish.
  - Populated validated minimum live market inputs:
    `src/uw_closes.json` plus `src/uw_price_cache_summary.json`, and
    `src/macro_state.json` plus `src/macro_pulse_summary.json`.
  - Re-ran `heartbeat_status.py`; heartbeat now has 0 down, 4 ok, and 1 stale
    optional-lane row.
  - `live_readiness.py --src-dir src` now reports `go_live_ready: true`.
  - Ran the publish path successfully:
    `python src/full_build_runner.py --src-dir src --feed-out src/latest_cockpit_feed.json --publish`.
  - Published `src/latest_cockpit_feed.json` and updated
    `src/open_opportunities.json`; the current live refresh now surfaces 4
    action rows and 0 research-action rows.
- Heartbeat cache snapshot.
  - Ran `heartbeat_status.py` against current repo-local readiness evidence and
    wrote `src/heartbeat.json` plus `src/heartbeat_summary.json`.
  - The generated heartbeat is valid; after the live market cache refresh,
    Required Inputs, Minimum Market Data, Publish Gate, and Daily Full Build are
    `ok`, while Optional Source Lanes remain `stale` for dark optional lanes.
- Required input freshness validation for live readiness.
  - Extended `live_readiness.py` so present required convention inputs are
    validated before live/publish readiness.
  - Reused the existing positions freshness rule: `positions.json`
    `snapshot_date` is fresh through 7 days, while stale, missing,
    unparseable, future-dated, or bare-list snapshots block `go_live_ready`.
  - Kept `rehearsal_ready` separate from required-input freshness so a build can
    still rehearse while stale required inputs remain visibly blocking live use.
  - Updated heartbeat Required Inputs rows so stale/unverified required inputs
    show as `stale`, not `ok`.
- Minimum live input validation.
  - Extended `live_readiness.py` so present UW price and macro caches must pass
    their existing validators before `live_data_ready` can turn true.
  - Added regression coverage for incomplete `uw_closes.json` and malformed
    `macro_state.json` so file presence alone cannot unlock go-live.
- Heartbeat status writer.
  - Added `heartbeat_status.py` to produce dashboard heartbeat rows from
    repo-local live-readiness evidence without fetching or publishing.
  - Wired `heartbeat.json` and `heartbeat_summary.json` into the daily
    full-build routine manifest/docs.
  - Reports required inputs, minimum market data, publish gate, optional source
    lanes, and daily build readiness as operational status only.
- Empty source lane status guardrail.
  - Changed source lane status so a cleanly registered but empty source is
    `checked_clear`, not `has_data`.
  - Added regression coverage for empty source rows so an empty Fundstrat daily
    cache cannot look like real delivered data.
- Live readiness report.
  - Added `live_readiness.py` to turn current convention-file/build evidence
    into a machine-readable go/no-go report without fetching or publishing.
  - Distinguishes `rehearsal_ready`, `publish_ready`, `live_data_ready`, and
    `go_live_ready` so a valid dry run cannot be mistaken for a live-ready day.
  - Treats UW price and macro caches as minimum live market inputs while keeping
    other missing optional lanes visible as dark lanes.
- Macro state refresh routine wiring.
  - Extended `macro_pulse_scan.py --emit-state` so `macro_state.json` carries
    both session-preflight regime/freshness fields and the UW macro snapshot
    shape consumed by the full cockpit build.
  - Added `macro_pulse_scan.py --validate` and an atomic summary-writing path
    for supplied yield-curve/cross-asset macro inputs.
  - Wired `macro_state.json` and `macro_pulse_summary.json` into the UW market
    data refresh routine manifest/docs and state ownership map.
- Signal Log intake routine.
  - Added `signal_log_intake.py` to normalize supplied Signal Log or Morning
    Scan JSON into `src/signal_log.json`.
  - Validates watch-only row shape and rejects empty/textless rows instead of
    publishing a false checked lane.
  - Added `signal_log_intake` as an active safe-intake routine in the
    manifest/docs.
- Daily Synthesis intake routine.
  - Added `daily_synthesis_intake.py` to normalize supplied Daily Synthesis JSON
    into `src/daily_synthesis.json`.
  - Preserves conservative structured action metadata without generating market
    content or promoting vague prose inside the intake routine.
  - Added `daily_synthesis_intake` as an active safe-intake routine in the
    manifest/docs.
- UW price cache intake.
  - Added `uw_price_cache_intake.py` to normalize supplied UW close-price
    responses or close arrays into `src/uw_closes.json`.
  - Validates all default rotation tickers have enough close history before
    writing unless an operator explicitly allows partial output.
  - Wired the command, validation path, and owned outputs into the UW cache
    refresh routine manifest/docs.
- Daily full-build input status summary.
  - Extended full-build CLI output so successful dry runs name dark lane keys
    and missing convention inputs instead of only counting them.
  - Used the routine-manifest convention-input contract for required/optional
    status, source, and missing-input behavior.
  - Fixed absent optional price cache handling so `uw_price` stays not checked
    instead of registering an empty source as `has_data`.
- Daily full-build convention input contract.
  - Added a `daily_full_build.convention_inputs` contract covering all 20
    `full_build_runner.DEFAULT_FILES` keys.
  - Recorded required versus optional convention inputs plus missing-input
    behavior so optional files stay not checked/dark instead of reading clear.
  - Added a routine-manifest validator guardrail so future full-build inputs
    require routine-manifest coverage.
- Full-build state ownership coverage.
  - Added explicit ownership entries for `inbox_call_dates`, `log_call_dates`,
    `meridian`, and `signal_log`.
  - Added a state ownership validator guardrail requiring every
    `full_build_runner.DEFAULT_FILES` key to appear in an ownership feed path.
  - Kept the new coverage system-focused; no Core List storage or stock-specific
    research was added.
- AVGO research priority downgrade.
  - Lowered the AVGO thesis item from high-priority Working to low-priority
    Queued because the important timing date has passed.
  - Kept the thesis task durable in `research_queue.json` without surfacing it
    as an immediate From Research action.
  - Updated repo notes/handoff so AVGO is no longer described as high priority.
- Fundstrat monthly state ownership map.
  - Added `fundstrat_bible` to the state ownership map as the compact monthly
    Fundstrat deck artifact.
  - Updated `top_prospects` producer/freshness wording to include
    `fundstrat_bible_intake.py` for monthly Top-5/Bottom-5 and separate
    Consider List rows.
  - Kept Core List tables explicitly excluded from the monthly ownership
    contract; do not assume they are a future requirement.
- Retired stale reallocation test workaround.
  - Removed the retired Chunk 1 `src/test_reallocate.py` artifact that blocked
    plain full-suite pytest collection.
  - Updated `src/verify_standard.py` and `docs/verification.md` so the standard
    verifier runs `python -m pytest src -q` directly.
  - Kept `src/test_reallocate_rebuild.py` as the canonical target-weight
    planner coverage.
- Monthly Top/Bottom idea extraction and core-list deferral.
  - Left Fundstrat monthly Core List tables out of stored state to avoid
    overclutter and bad row extraction; do not revive this unless the user
    makes a new explicit request after the working system is in place.
  - Added a PDF-text fallback for monthly Large-cap Top-5/Bottom-5 pages where
    extraction places labels after ticker blocks.
  - Added an explicit low-pressure `consider_list` category for separate
    monthly Consider List rows.
- AVGO thesis Research Queue seed.
  - Added `src/research_queue.json` with an AVGO thesis/sizing research item
    from the README backlog note.
  - Kept AVGO unassessed in source/golden logic; no thesis was invented.
  - Validated the queue so the item can be tracked without hand-grading the
    thesis.
- Fundstrat monthly/Bible direct upload intake.
  - Added `fundstrat_bible_intake.py` for direct monthly PDF/text/JSON uploads.
  - Writes compact `fundstrat_bible.json` deck shape for useful summary lists:
    stance, What-to-Own, separate consider list, Top-5, and Bottom-5.
  - Can merge monthly Top-5/Bottom-5 and separate consider-list names into
    `top_prospects.json` without storing raw PDF text or stock-price chart
    clutter.
- Fundstrat source-call upsert automation.
  - Added optional one-step source-call cache/log-date merge to
    `fundstrat_email_intake.py`.
  - Updated the Fundstrat routine manifest/docs so full-body intake can write
    daily calls, top prospects, source calls, and log dates in one path.
  - Kept snippet-only discovery from updating source-call calibration state.
- Dashboard parity refresh.
  - Re-ran the full build parity baseline after the synthesis metadata slice.
  - Confirmed every emitted feed block is classified before more UI work.
  - Updated `docs/dashboard_parity_review.md` for current `target_drift`
    emission and conditional `portfolio_views` absence.
- Daily Synthesis structured action metadata.
  - Added aliases for structured synthesis action rows such as `symbol`,
    `recommendation`, `next_step`, and `urgency`.
  - Preserved explicit timing, capital effect, sizing, goal-channel, and missing
    evidence metadata when valid.
  - Kept free-form prose conservative: ticker-led actionable hanging items only.
- Conflict wording refinement.
  - Preserved `Mixed` conflict handling while adding source-scope/detail to the
    conviction read.
  - Cross-source examples still say cross-source split; same-source Lee/Farrell
    disagreement now says same-source split.
  - Refreshed the golden feed so BMNR no longer reads like independent-source
    disagreement.
- Generated HTML summary safety.
  - Added a summary/export caveat to the generated GitHub Pages dashboard.
  - Rendered lane-status counts/top rows and compact feedback-loop lines.
  - Added focused generator tests so empty actions plus dark lanes cannot read
    as all clear.
- Signal Log watch lane and parity classification.
  - Added optional `signal_log.json` / `morning_signal_log.json` intake through
    the full-build convention path.
  - Rendered Signal Log as a watch-only canonical dashboard lane separate from
    Today's Actions.
  - Classified the new feed block in the dashboard parity guardrail and
    documented that generated HTML remains a summary/export path.
- Shared ActionCard refactor.
  - Extracted the duplicated Today's Actions and From Research row renderer into
    a shared `ActionCard` component in the canonical dashboard.
  - Preserved lane-specific footer copy, aging/sizing chips, and From Research
    priority badge labeling.
  - Kept Contract-C action row shape unchanged.
- Connector-shaped Catalyst intake.
  - `catalyst_calendar_intake.py` now accepts live connector/stdin JSON
    envelopes as well as exported JSON/CSV files.
  - Notion-style `properties` rows are flattened for ticker/date/label/source
    fields.
  - Catalyst rows still flow through `catalysts.json`; full build owns action
    promotion and MONITOR guardrails.
- L2-to-L3 collection gate.
  - Added `collection_gate.py` as the Collection-to-Analyst handoff validator.
  - Layered Contract-B shape, parseable run/source stamps, critical-source
    fail-closed behavior, and staleness/source-failure consistency checks.
  - Wired the gate into both full-build and runtime skeleton paths before L3
    feed assembly.
- Structured Research Queue ticker field.
  - Research action promotion now trusts explicit dossier tickers before legacy
    title parsing.
  - Plain-title, dated, low-priority ticker dossiers can activate the near-term
    date clause.
  - Existing ticker-led research rows and process-item filtering remain intact.
- From-Research priority label clarity.
  - Added explicit `confBadgeLabel` display mapping in the canonical dashboard.
  - From Research now labels queue priority separately from Today's Actions confidence.
  - Kept the Contract-C action row shape unchanged.
- Completion audit and next-slice discovery.
  - Added `docs/completion_audit.md`.
  - Verified queues, routine manifest, dashboard guardrail, and standard verification command.
  - Promoted the next self-contained refinement slice from older architecture backlog notes.
- ETF look-through sleeves.
  - Added separate effective ETF look-through exposure to `portfolio_views`.
  - Rendered effective sleeve estimates and top overlap rows in the canonical Book tab.
  - Kept direct account rows/categories direct-only and labeled estimates clearly.
- Fundstrat intake expansion.
  - Hardened `fundstrat_email_intake.py` for Gmail connector search and batch-read shapes.
  - Preserved snippet-only discovery as not full-body checked.
  - Added regression tests for nested batch-read envelopes, `threadId`/`internalDate`, and HTML body normalization.
- Codex-owned cloud routines.
  - Added `src/codex_routine_manifest.json` as the machine-readable routine control plane.
  - Added `src/codex_routine_manifest.py` validation/listing command and manifest tests.
  - Preserved separation between source intake/cache refresh routines and daily full-build publishing.
- Verification command.
  - Added `src/verify_standard.py` as the repo-owned standard verification command.
  - GitHub Actions now runs the same command.
  - Supports the full repo pytest tree and optional JSX bundle check.
- PDF holdings ingest.
  - `broker_pdf_extractor.py` now handles ticker-led and description-before-symbol selectable text rows.
  - Added focused text-export and optional selectable-PDF tests.
  - Image-only/OCR-needed inputs still fail honestly until OCR tooling exists.
- Reallocation and target drift.
  - Target weights are machine-readable through `reallocate_config.py`.
  - `position_drift_check.py` emits a structured `target_drift` feed block.
  - Full builds mark Target Drift in lane status and render it in the dashboard Action view.
- Dashboard canonicalization guardrail.
  - Added `docs/dashboard_feed_block_classification.json`.
  - Added `src/test_dashboard_parity_guardrail.py`.
  - Documented JSX injection as canonical and `docs/index.html` as summary/export.
- Dashboard parity review.
  - Added `docs/dashboard_parity_review.md`.
  - Decided JSX injection is canonical; generated HTML is summary/export.
  - Mapped feed blocks to JSX and generated HTML surfaces.
- Repo-evidence Daily Synthesis.
  - Added `daily_synthesis_from_feed.py` to build a conservative synthesis
    cache from the already-built cockpit feed.
  - Kept Catalyst Calendar and Signal Log as visible dark lanes; Daily
    Synthesis no longer needs separate supplied JSON just to show the current
    repo-evidence read.
  - The repo-evidence path writes no structured synthesis actions.
- One-command live dashboard refresh.
  - Added `live_dashboard_refresh.py` as the repo-local live refresh runner.
  - It writes heartbeat status, publishes a feed, refreshes repo-evidence Daily
    Synthesis from that feed, republishes, renders canonical JSX plus
    summary/preview HTML, writes the parity feed, and prints readiness plus
    preview-server status.
  - Added routine-manifest coverage and focused tests for the refresh sequence.
- Dashboard preview server helper.
  - Added `dashboard_preview_server.py` so the repo can check or serve
    `tmp/dashboard_preview.html` at the local preview URL without relying on an
    unknown external server process.
  - Wired preview-server status into the live dashboard refresh summary.
- Open action resolver.
  - Added `action_memory_resolve.py` so unresolved action-memory items can be
    listed or resolved into history after operator review without rebuilding the
    feed.
  - Current open action-memory items are `ANET` and `GOOGL`.
- Conviction-gap action surfacing.
  - Promoted the useful part of the Notion System Update Queue E1 item.
  - Target Drift now emits conservative `conviction_gap` action prompts for
    held names materially below the working-model target.
  - Missing target names stay context-only; MONITOR sleeves remain suppressed;
    every prompt requires a funded add/rotation review and pre-trade gate.
- Feedback/source-call tracking surfacing.
  - Make overdue source-call scoring visible.
  - Make repeated source-call persistence clusters durable in the feed/dashboard.
  - Keep stale or not-checked calibration visibly provisional.
- Compact live-status readout.
  - Added `live_status.py` as a non-rebuilding operator check for live
    readiness, preview-server state, unresolved action-memory rows, and the
    system-improvement queue.
  - Current readout reports `go_live_ready: true`, 4 actions, 0 research
    actions, 1 dark optional lane (`catalysts`), 2 open action-memory reviews,
    preview server running, and 0 active/queued system-improvement items.
- One-line sudden-event risk intake.
  - Extended `event_risk_intake.py` so a supplied headline can be appended with
    CLI flags instead of pre-shaped JSON.
  - This starts fixing the sudden-event fragility: Iran/oil/rates-style shocks
    can enter `event_risks.json` directly, then promote through the existing
    conservative exposure-review action path.
  - It still does not scrape headlines, invent market narratives, or create
    automatic buy/sell orders.
- Unified manual source-drop helper.
  - Added `manual_source_drop.py` so one supplied JSON file can route explicit
    `event_risks`, `signal_log`, and `catalysts` sections through the existing
    safe intake normalizers.
  - Ambiguous generic `events` rows are intentionally rejected instead of
    guessed into a lane.
  - The helper supports dry-run checks and merge-existing behavior for local
    operating flow.
- Manual source-drop template and validation-only mode.
  - Added `docs/manual_drop.template.json` as a tested starting point for
    supplied event-risk, signal-log, and catalyst rows.
  - Added `manual_source_drop.py --validate-only` as a clearer no-write check
    before committing source-cache updates.
  - Regression tests prove the template validates and does not write cache files.
- Open action review report.
  - Extended `action_memory_resolve.py` with `--review-report` so open action
    memory rows include age, review prompt, and ready-to-run defer/ignore/acted
    commands.
  - This keeps the operator decision explicit while making the resolution loop
    easier to complete.
- Go-live checklist command.
  - Added `go_live_checklist.py` as a non-mutating operator checklist across
    live refresh, live status, preview, manual source-drop validation, open
    action reviews, queue state, and optional dark lanes.
  - Current checklist is `warn`, not blocked: live readiness is green, with
    warnings for open reviews and optional dark lanes.
- Human-readable go-live checklist output.
  - Added `go_live_checklist.py --format text` so the go-live check is
    scannable without reading JSON.
  - JSON remains the default for automation/backward compatibility.
- Dashboard operator-status card.
  - Added a compact Operator Status card to the generated dashboard
    summary/preview HTML.
  - It surfaces action count, open review count, dark/stale/failed lane status,
    and the human-readable go-live checklist command near the top of the
    preview.

## Queued Slices

- No active queued implementation slice.
  - The current system-improvement queue is valid with 21 done items and 0
    active or queued items.
  - Promote the next slice only from fresh repo evidence or a new explicit user
    request, and keep Core List ingestion out of scope.

## Working Rules

- One implementation slice per turn.
- Commit and push after every clean slice.
- Do not do more UI work until dashboard parity review is complete.
- Treat any short non-conflicting user reply as continue; explicit stop/pause/change-direction overrides.
