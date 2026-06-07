# Codex Build Queue

Canonical repo queue for Investing OS rebuild work. GitHub files are canonical
until the core logic is stable; Notion sync comes later.

## Active Slice

- No active implementation slice.
  - Promote the next slice from fresh audit/user evidence before editing.
  - Cloud routine proof remains end-of-queue background monitoring. Let normal
    schedules produce remaining `run_source=scheduled` receipts unless the user
    explicitly asks to accelerate again.
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

- Pre-market crash-triage UW routing.
  - `uw_routing_recommendations.py` now activates the `pre_market_crash_triage`
    profile when the feed is in a high-volatility or re-check posture.
  - `uw_action_runbook.py` now scopes that profile to event-risk tickers, top
    portfolio exposure, and current action tickers, with explicit broad-tape,
    sector, owned-name flow, and vol/gamma checks.
  - The Market-Open Packet now keeps up to three UW check sets visible so crash
    triage, event-risk macro, and portfolio reallocation can all appear before
    Social Watch/open-review cleanup.
- Market-Open Packet.
  - Added `market_open_packet.py` to sequence the current dashboard state into a
    compact market-open review order: re-check first, gate Key Now, unblock
    current positions, run UW check sets, keep dark lanes visible, and preserve
    open reviews.
  - Wired `feed.market_open_packet` through full-build output, canonical JSX,
    HTML summary/export, and dashboard parity classification.
  - The packet is a capital-efficiency operator aid only. It helps compare
    better uses of scarce capital and avoid both stale action and over-precise
    timing, but it never executes or recommends an un-gated trade.
- Social Watch dashboard lane.
  - Added `social_watch.py` to normalize future Reddit/social API output or a
    supplied cache into a watch-only `feed.social_watch` block.
  - Wired `social_watch` through full-build convention inputs, lane-status dark
    lane handling, canonical JSX, HTML summary/export, source ownership, and
    dashboard parity classification.
  - Added validation so Social Watch rows cannot escalate directly to buy, sell,
    trade, or Key Now; independent non-social confirmation is required before
    any action-lane promotion elsewhere.
- Candidate reallocation brief.
  - Added `reallocation_brief.py` to wrap the existing funded-rotation planner
    into a dashboard feed block with candidate adds, funding trims, funding
    summary, blockers, disconfirmation, and UW reallocation check linkage.
  - The brief is explicitly candidate-only and labels non-same-session position
    snapshots as test-data only until current positions are supplied.
  - Added stale-sequence blockers for old catalyst dates such as "after
    2026-06-03" so outdated planner sequencing cannot read like current timing
    guidance.
  - Added capital-efficiency judgment to every enriched action so the cockpit
    distinguishes "good opportunity" from "best use of capital now" and favors
    staged exposure over indefinite perfect-entry timing when evidence is fresh.
- UW action runbook.
  - Added `uw_action_runbook.py` to turn the current cockpit feed into
    scenario-specific UW check sets with ticker scopes, market checks, ticker
    checks, promotion rules, downgrade rules, and action blockers.
  - Fixed UW routing build order so Fundstrat source-audit evidence can
    correctly trigger the Fundstrat-confirmation profile.
  - Rendered the runbook in the canonical dashboard and HTML summary/export,
    while keeping the honesty rule explicit: this is endpoint/check routing,
    not proof that UW endpoint results were fetched.
- UW routing surfaced in Source Proof.
  - Added `uw_routing_recommendations.py` to translate the current feed state
    into next UW scenario profiles, such as event-risk macro, portfolio
    reallocation, Fundstrat confirmation, and asymmetric discovery.
  - The block is explicit that routing recommends endpoint groups only and is
    not proof that those endpoints were fetched.
  - Source Proof now renders the UW routing line and compact "UW next checks"
    endpoint list in both generated HTML and canonical JSX.
- Action-card disconfirmation surfacing.
  - `decision_support.enrich_actions()` now adds a structured
    `disconfirmation` block to every action, including what could make the item
    wrong, what must be confirmed before acting, and where to downgrade the item
    when evidence fails.
  - The generated HTML summary and canonical JSX action drawer now render
    "What could make this wrong?" alongside why/freshness/rationale so Key Now
    and Re-check items have explicit invalidation pressure.
  - Added focused coverage for event-risk, target-drift/funding/gate
    disconfirmation, HTML rendering, and full-build feed integration.
- External-review, UW-routing, Reddit, and reallocation design slice.
  - Added `docs/system_improvement_external_review.md` with a high-level system
    reassessment, gap list, Claude/Gemini critique prompt, immediate priorities,
    and user clarifying questions for the future reallocation plan.
  - Added `src/uw_endpoint_router.py` as the scenario-aware UW endpoint router
    for crash triage, Fundstrat confirmation, asymmetric discovery, portfolio
    reallocation, post-close review, event-risk macro, and Reddit escalation
    vetting.
  - Added router tests that validate all routed paths against the approved UW
    endpoint catalog and assert the required crash-triage, reallocation, and
    Reddit-vetting lanes.
  - Added `docs/reddit_feed_design.md` to keep Reddit as compliant,
    watch-only early-signal intake with minimal retention and independent
    confirmation before action escalation.
  - Added `docs/reallocation_workflow.md` so the final current-positions plan
    can be produced as candidate-only output once the user supplies positions.
- Dashboard hardening and Fundstrat safety routines.
  - Added operator-hardening dashboard panels for freshness downgrades,
    stale-action cleanup, pre-action condition checks, and watch-only
    why-not-acting context.
  - Added a Notion collision audit convention file and dashboard audit row for
    shared Notion surfaces that may have been written by other agents.
  - Added two active Codex automations: Fundstrat Pre-Market Safety Sweep
    (7:45 AM ET market weekdays) and Fundstrat After-Hours Catch-Up (7:00 PM ET
    market weekdays). Both require scheduled receipts, full-body-derived
    compact evidence, validation, safe commit/push, and dark-lane honesty.
  - Updated Notion-writing active routine prompts so Notion write success
    requires live page readback before page status/write status is reported as
    successful.
  - Added source-call candidate fallback from current Fundstrat radar rows so
    fresh dated/quoted radar calls can enter calibration instead of remaining
    passive context.
  - Cloud status now expects 12 active routines and reports the two new
    Fundstrat routines as expected since 2026-06-07, so old windows before
    creation are not counted as missed receipts.
- Account Positions source wait resolved.
  - Current 7-file Drive proof extracted 225 broker rows across Fidelity,
    Schwab, and Robinhood with `failed_files=0`, then refreshed
    `src/positions.json`, `src/account_positions.json`, and
    `src/position_reconciliation.json`.
  - `live_dashboard_refresh.py` now reports `dark_lanes=0`; Account Positions
    is checked through the source cache instead of remaining a source wait.
  - `go_live_checklist.py --format text` reports `PASS`, 0 failures, and 0
    warnings. Remaining cloud routine proof is background natural-schedule
    monitoring only.
- Broker position extractor hardening.
  - `broker_pdf_extractor.py` now prefers true symbol-before-quantity matches
    over company-name text, blocks Fidelity disclosure/value-table prose from
    becoming fake ticker rows, and validates symbols through the same stricter
    ticker gate used by parsing.
  - Added narrow selectable-text parsers for Robinhood `Name Symbol Shares`
    rows and Schwab wrapped/compact account rows, including compact
    ticker/name strings such as `SMHVANECK...`.
  - Added Fidelity separated value/symbol page pairing that succeeds only when
    every page/account group has matching value-row and symbol-row counts.
- Background cloud-proof wording.
  - Cloud proof remains tracked and auditable, but the visible dashboard,
    go-live checklist, and completion audit now label incomplete routine proof
    as background natural-schedule monitoring instead of a foreground build
    task.
  - The go-live checklist summary now separates `schedule waits` from
    `background monitors`, so ordinary unproven cloud receipts do not read like
    foreground work. Overdue or failed scheduled receipts still warn as
    monitoring issues.
  - Account Positions manual live-source drop was re-verified: the shape
    template validates, `--validate-only` does not write, and existing tests
    cover Account Positions/Meridian apply and validation behavior.
- Completion-audit review pressure parity.
  - `python src/completion_audit.py --format text` now prints open-review
    due/stale/oldest-age counts, matching `live_status.py` and the go-live
    checklist.
  - Current ANET/GOOGL review rows remain visible as open reviews, but the audit
    now states `due=0 | stale=0 | oldest=0d` so fresh prompts are not confused
    with stale backlog.
- Open-review warning severity parity.
  - Fresh same-day open reviews now remain visible without becoming a warning
    bucket. Due or stale reviews still warn.
  - The go-live checklist now reports `review backlog=0` when open reviews are
    only new and have `0 due; 0 stale`, while still listing the review-report
    command and tickers.
  - The generated HTML dashboard and canonical JSX Operator Status card now
    show `2 new` in pass styling for same-day ANET/GOOGL reviews. Overall
    operator status remains `WARN` only because Account Positions and natural
    cloud proof are still waits.
- Open-review backlog hygiene.
  - Added a shared action-memory review-age policy: new, review due, and stale
    review states based on trading-day age.
  - `action_memory_resolve.py --review-report` now reports due/stale counts,
    cleanup priority, next-step language, and fuller resolution commands
    including invalidated and missed, while keeping all resolutions audited in
    `open_opportunities.json` history.
  - The cockpit feedback block now shows open-action cleanup pressure inline:
    open count, due count, stale count, review label, priority, and the next
    cleanup step. Same-day ANET/GOOGL prompts correctly show as new, not stale.
  - `live_status.py --format text` and the go-live checklist now separate
    open-review count from due/stale cleanup pressure, so backlog warnings are
    actionable without implying a build blocker.
- Eastern-date freshness correctness for evening builds.
  - Full cockpit builds now derive the operator-facing operating day from the
    run timestamp in America/New_York, so an evening ET build that crosses
    midnight UTC does not create next-day evidence dates or negative source
    ages.
  - UW price and macro staleness entries keep ET-aware datetime stamps, which
    preserves publish-gate freshness checks while rendering source ages against
    the correct ET session day.
  - Action freshness, open-opportunity memory, repo-evidence synthesis,
    generated HTML, and canonical JSX render caveats now format midnight-UTC
    builds as the prior evening ET build time.
  - Added regression coverage for the full-build source stamps,
    decision-support freshness, action-memory as-of date, repo-evidence
    synthesis date, generated HTML header, and canonical JSX render caveat.
- Dashboard manual-drop template guidance.
  - The generated Lane Status command block now shows
    `docs/manual_live_source_drop.template.json` as shape-only guidance before
    the Account Positions validate/apply commands. The apply command still
    points at a filled `manual-live-source-drop.json` file, not the template.
- Source-call scoring wording clarity.
  - `live_status.py --format text` now labels source-call counts as
    `new=<latest observations>` and `scoring=<stored calls awaiting outcome>`
    instead of mixing `observed` and `pending`.
  - The generated dashboard quick link and Operator Status pill now show
    `3 scoring` for stored source-call candidates awaiting future scoring
    windows, so the count is not mistaken for a source-intake blocker.
- Account Positions source-wait usability.
  - `live_status.py --format text` now shows both the no-write validation
    command and the apply command for live-source dark lanes, so the remaining
    Account Positions wait is actionable without implying the lane is checked.
    The template is only a starting shape; validate/apply commands point at a
    filled `manual-live-source-drop.json` file to avoid writing placeholder
    data.
  - `go_live_checklist.py --format text` now presents the manual live-source
    drop as explicit `validate:` and `apply:` steps instead of only a
    validation command.
  - The generated HTML dashboard Lane Status section now renders compact
    validate/apply command rows for dark, stale, or failed lanes. Browser
    verification confirmed the local preview shows Account Positions validate
    and apply commands.
- Build-readiness and completion-audit clarity.
  - Added `python src/completion_audit.py --format text` as the non-mutating
    current-state audit for build blockers, source/user waits, natural cloud
    proof waits, open-review backlog, and the next recommended action.
  - Added an explicit `all_clear` audit field and `--require-all-clear` gate so
    local build readiness cannot be mistaken for complete external/source/cloud
    clearance.
  - Updated the go-live checklist and dashboard Operator Status card so `WARN`
    no longer implies a code blocker. Current status is build-clear with waits:
    0 build blockers, Account Positions source wait, partial cloud proof
    `3/10`, and deferred `ANET`/`GOOGL` reviews.
- Dashboard decision surfacing build completion.
  - Added action grouping into Key Now, Important Backlog, Re-check Before
    Acting, and Quiet Watch so the dashboard can surface every important
    decision while pushing the most time-sensitive items harder.
  - Tightened the grouping so fast-moving evidence whose evidence date predates
    the current build lands in Re-check Before Acting, while same-day
    fast-moving evidence can remain Key Now.
  - Added freshness/rationale judgment on action cards: evidence date, last
    checked, decay speed, freshness label, and why the recommendation still
    matters.
  - Added asymmetric-opportunity surfacing with one row per ticker and merged
    evidence sources across target drift, lean-in, prospects/radar context, and
    bullish flow.
  - Added source proof/audit dashboard blocks for cloud routine proof,
    connector evidence, Fundstrat intake, and Notion/writeback audit.
  - Reclassified Meridian as stale thesis archive context, not live tactical
    evidence. Missing Meridian archive data no longer creates a live dark lane;
    current live-capable dark lane is Account Positions only.
  - Browser-verified `http://127.0.0.1:8765/dashboard_preview.html`: grouped
    action sections, five expandable rationale drawers, asymmetric
    opportunities, source proof/audits, Account Positions dark lane, and no
    Meridian live-lane row.
  - `python src\verify_standard.py` passed with 1022 tests, 6 skips, plus the
    reallocation direct check, cockpit injector self-test, and broker extractor
    self-test.
- Cloud proof pivot.
  - Pre-Market Source Intake, Post-Close Refresh, and Morning Scan now have
    real scheduled success receipts, so `cloud_ops_status.py --format text`
    reports `scheduled_success=3/10`.
  - Morning Scan was temporarily accelerated once, completed, committed, and
    restored to its normal 8:35 AM ET weekday schedule.
  - Daily Synthesis was restored to its normal 9:30 AM ET weekday schedule
    before any proof was counted.
  - All active routines are back on their normal schedules; remaining proof is
    deferred to natural runs at the end of the build queue.
- System architecture reference.
  - Added `docs/investing_os_system_architecture.md` as the durable map of the
    current Investing OS operating system: source routines, convention files,
    cloud receipts, safe write-back, live-source honesty, synthesis/action
    promotion, dashboard refresh, and the module/function map.
  - Linked the architecture reference from the new-chat handoff so future
    Codex/Claude sessions start from the current cloud/dashboard design instead
    of reconstructing it from scattered queue notes.
- Dashboard summary-preview action usability.
  - Made the generated `dashboard_preview.html` action-first instead of
    status-first: Today's Actions now render immediately below the caveat with
    ticker/portfolio/event labels, move text, rationale, source, confidence,
    goal impact, and gate context visible without hidden drill-downs.
  - Added jump links from the top summary/status pills to Today's Actions,
    Operator Status, open reviews/source calls, and lane-status gaps, so the
    action count is no longer a dead metric in the local preview.
  - Kept missing/dark source lanes visible and below the action surface, so the
    preview supports the core goal: see what needs a decision first, then check
    data-quality caveats before acting.
- Codex cloud routine stack.
  - Replaced the single generic daily cloud-refresh assumption with a split
    Codex app automation stack: Pre-Market Source Intake (8:10 ET), Morning
    Scan (8:35), Daily Synthesis (9:30), UW Opportunity Cache (10:00),
    Parabolic Cache (10:05), Full Cockpit Build (10:30), Post-Close Refresh
    (4:30 PM), Off-Hours Worker (1:45 AM daily), Deep Synthesis (Sunday
    1:00 PM), and Weekly Pilot Run (Sunday 6:00 PM).
  - Schedule basis was cross-checked against Notion's "Scheduled Cloud
    Routines - Master Reference" and the 2026-06-02 "Routine schedule
    reconcile" note. The reconcile note says Daily Synthesis must not run
    before the 8:35 Morning Scan, 9:15-9:30 is acceptable, UW Opportunity
    Cache should not move before roughly 9:45, and the full cockpit build
    should move to 10:30 to give UW/Synthesis more buffer. The current active
    stack follows those constraints.
  - Paused the old generic `investing-os-daily-cloud-refresh` automation as
    superseded by the split routine stack.
  - Paused six older unreceipted local cron jobs as superseded by the active
    receipt-tracked stack: Broker Position Intake, Catalyst Intake, Daily Full
    Build, Fundstrat Intake, Off-Hours Research Queue, and UW Cache Refresh.
    Supplied broker-position uploads now belong to Pre-Market Source Intake;
    missing/invalid broker input keeps positions stale/not refreshed instead
    of checked clear.
  - `cloud_ops_status.py` now reads the default Codex app automation folder
    when `CODEX_HOME` is unset and fails the cloud schedule if a superseded
    legacy automation is still active.
  - The cloud-ops check also validates active local automation prompts for
    routine-specific scheduled receipt protocol, safe write-back via
    `cloud_routine_commit.py`, and missing-source honesty guards. Current app
    state reports
    `Cloud receipt protocol: checked=10 | ok=10 | missing=0`.
  - Tightened the prompt checker and patched the active Deep Synthesis
    automation prompt after the stricter check found it had receipt/write-back
    instructions but lacked an explicit missing-source honesty guard. The
    stack is ready again after the prompt update.
  - Added `src/cloud_routine_commit.py` so scheduled routines can commit and
    push only allowlisted routine-owned outputs while leaving unrelated dirty
    generated files untouched. Active routine prompts now call this helper for
    write-back instead of relying on generic git staging.
  - The helper reports git status/add/commit/push failures as structured
    output, preserving a successful commit id when only the push fails, so
    scheduled routines can report write-back problems without hiding them in a
    stack trace.
  - Updated `src/cloud_automation_status.json` to record the app-created
    routine ids and updated `cloud_ops_status.py` so cloud readiness requires
    the full expected stack to be installed and active.
  - Missing connector/source pulls still remain visible as dark lanes instead
    of checked clear; current optional dark lane remains Catalyst Calendar.
- Live-source capability status.
  - Added `python src/live_source_capability.py --format text` as a
    non-fetching operator proof of which daily build inputs are
    connector/API-capable, supplied/export-capable, or repo-local/cache inputs.
  - `python src/live_status.py --format text` and
    `python src/cloud_ops_status.py --format text` now include the source
    capability counts alongside existing live-data readiness, so a valid local
    cache cannot be mistaken for proof that every source was freshly fetched.
  - Updated the routine manifest source-boundary text for Catalyst, Daily
    Synthesis, and Signal Log connector paths; missing source inputs still
    remain missing/dark rather than checked clear.
  - The text readout now prints missing live-capable inputs with source/routine
    ownership, missing-data behavior, and expected repo paths. Current missing
    live-capable input is `account_positions`; Meridian is thesis archive
    context and must not count as fresh tactical evidence or a live-source miss.
  - `python src/live_status.py --format text` and
    `python src/cloud_ops_status.py --format text` also surface those detailed
    missing live-source lines, so operator/cloud checks do not require a
    separate command to know which source file is absent.
  - Missing optional live-source convention inputs that do not otherwise render
    as cockpit lanes are now appended to the feed `lane_status` as dark
    `not_checked` rows. Current dashboard dark lanes are `account_positions`
    and `meridian`; they stay visible in `live_status`, `cloud_ops_status`,
    the go-live checklist, and the generated dashboard until the actual source
    files are supplied.
  - Live-source configuration is now tracked separately from cached/local
    readiness. `live_source_capability.py`, `live_status.py`,
    `cloud_ops_status.py`, `go_live_checklist.py`, and the dashboard Operator
    Status card read `src/live_source_config.json` plus `UW_API_KEY` to decide
    whether UW live fetch is configured. The current app connector proof
    verifies the Unusual Whales connector without storing a secret, so the
    dashboard shows `Live fetch 1/1`; existing UW caches are still not treated
    as proof that a specific cache was freshly rebuilt.
  - Connector-only live-fetch proof is now time-bounded. Without `UW_API_KEY`,
    the UW connector proof must be fresh within the configured proof window or
    `live_source_capability.py`, `live_status.py`, and `cloud_ops_status.py`
    show it as stale/missing instead of leaving `Live fetch 1/1` permanently
    green. `src/live_source_config.json` is now a routine-owned safe-commit
    path so scheduled routines can persist refreshed non-secret proof metadata.
  - Added `python src/live_source_config_update.py <uw-market-state-or-market-tide-json> --out src/live_source_config.json`
    so UW routines can refresh that proof from connector output without storing
    raw market payload rows, premiums, or volume fields.
  - Cloud schedule readiness now requires that live-source configuration be
    present and fresh. A stale connector-only proof can leave cached dashboard
    artifacts renderable, but it no longer counts as unattended cloud-ready
    live operation.
  - `live_status.py` points the Account Positions dark lane at
    `docs/manual_live_source_drop.template.json`, while source-specific lanes
    such as Catalyst Calendar and Signal Log keep their specialized intake
    commands. Meridian is archived thesis context, not a live dark lane.
- Cloud routine run receipts.
  - Added `src/cloud_routine_receipts.py` and
    `src/cloud_routine_receipts.json` so scheduled jobs can append auditable
    started/success/failed receipts after they run.
  - Receipts now carry `run_source` (`scheduled` or `manual`). Cloud live-run
    proof counts only scheduled success receipts, so a manual local rehearsal
    cannot accidentally satisfy `Cloud live-run proven`.
  - Updated all active Codex app routine prompts to use
    `--run-source scheduled`; current cloud status reports
    `scheduled_success=3/10` after Post-Close Refresh, Pre-Market Source
    Intake, and Morning Scan scheduled successes.
  - `cloud_ops_status.py` distinguishes first scheduled proof from full-stack
    proof: one scheduled success moves the state to `partial_live_run_proven`,
    while `Cloud live-run proven` remains false until every expected routine has
    a scheduled success receipt.
  - `python src/cloud_ops_status.py --format text` now reports both the active
    routine stack and the current run-receipt proof count. A newly installed
    routine stack can be ready before first run, but no live run should be
    treated as proven until a success receipt appears.
  - `cloud_ops_status.py` distinguishes `Cloud schedule ready` from
    `Cloud live-run proven`; the current partial-proof state should be read as
    ready to run with some scheduled proof, not yet full-stack live proof.
  - It also computes the next expected receipt from the automation activation
    time and marks a due routine overdue after a 30-minute grace window. After
    the proof pivot, the next natural expected receipt is Off-Hours Worker at
    2026-06-06 1:45 AM ET.
  - The status readout now separates due states into `overdue`,
    `due_waiting`, `not_due_yet`, and `current`, and prints an explicit
    first-scheduled-proof-pending line before the first expected receipt window.
  - `cloud_ops_status.py --strict` remains the schedule-readiness gate.
    Use `--require-first-proof` to fail until at least one scheduled success
    receipt exists, and `--require-live-run` to fail until every expected
    routine has a scheduled success receipt.
  - Latest failed receipts surface as operator gaps; first-run-pending receipts
    stay visible without marking a source lane checked clear.
- Cloud routine runner.
  - Added `src/cloud_routine_runner.py` so deterministic repo-local cloud jobs
    can wrap their command with guaranteed started/final receipts instead of
    relying on prompt-only bookkeeping.
  - Added `python src/cloud_routine_drill.py --format text --strict` as a
    safe non-mutating full-stack drill. By default it runs every expected cloud
    routine id through scheduled-style receipt mechanics in a temp store and
    verifies the real `src/cloud_routine_receipts.json` proof store is
    untouched; it validates mechanics but does not prove a scheduled run.
  - Added `python src/cloud_routine_manual_run.py --format text --strict` as
    the repeatable "run the routines now" path. It runs the active stack with
    `run_source=manual` receipts, so it proves the routine paths can execute
    immediately without satisfying scheduled cloud proof. Empty local UW
    bundles are treated as skipped validation evidence instead of overwriting a
    populated UW cache with a false checked-clear day.
  - Full Cockpit Build and Post-Close Refresh should use
    `python src/cloud_routine_runner.py --run-source scheduled --routine-id <id> -- python src/live_dashboard_refresh.py`
    as their core command before committing/pushing changed artifacts.
- Signal Log / Morning Scan lane populated.
  - Used Notion search/fetch against the Signal Log data source, not the failed
    SQL query path, to source recent macro, oil/Hormuz, Iran escalation, and
    metals-tariff rows.
  - Normalized six compact watch-only rows into `src/signal_log.json` via
    `python src/signal_log_intake.py tmp\signal_log_notion_compact_2026-06-05.json --out src/signal_log.json --summary src/signal_log_intake_summary.json --merge-existing`.
  - Preserved distinct row notes in `signal_log_intake.py` so the dashboard can
    show why each watch item matters without promoting direct buy/sell actions.
  - Refreshed the live dashboard package. At that slice, status showed 12 lanes with
    data and 1 dark lane (`catalysts`); Signal Log is checked as has-data, while
    Catalyst remains dark/not checked.
- Catalyst Calendar lane populated.
  - Fetched the Notion Catalyst Calendar database/page and used exact
    future-dated rows only from the page source
    `35fc5031-4bb6-81c5-ae90-d8a84919999b`.
  - Normalized eight compact Catalyst Calendar rows into `src/catalysts.json`
    with `catalyst_calendar_intake.py`; vague/TBD rows were skipped rather than
    guessed.
  - Refreshed the live dashboard package. At that slice, status showed 13 lanes with
    data and 2 dark lanes (`account_positions`, `meridian`); those missing
    optional source inputs are visible as not checked, not checked-clear
    claims.
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
- Go-live checklist cloud proof row.
  - `python src/go_live_checklist.py --format text` now includes a Cloud
    automation proof row derived from `cloud_ops_status.py`.
  - The row warns until scheduled proof is complete; current proof is partial
    at `scheduled_success=3/10`, not full-stack live proof.
- Go-live checklist live-source coverage row.
  - `python src/go_live_checklist.py --format text` now includes a Live source
    coverage row derived from live-source capability status.
  - The row warns on missing live-capable optional inputs such as
    `account_positions` and `meridian`, even when dashboard source lanes are
    otherwise populated.
- Manual live-source drop support.
  - `manual_source_drop.py` now accepts and validates explicit
    `account_positions` and `meridian` sections, writing
    `src/account_positions.json` and `src/meridian_items.json` only when the
    supplied JSON is structurally valid.
  - `docs/manual_live_source_drop.template.json` shows the expected shape and
    validates with `python src/manual_source_drop.py docs/manual_live_source_drop.template.json --src-dir <tmp-or-src> --validate-only`.
  - The go-live checklist manual-drop row now points at
    `docs/manual_live_source_drop.template.json` when the active source coverage
    gap is `account_positions`/`meridian`, instead of warning generically about
    event/signal/catalyst source drops.
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
  - That slice proof showed feed `2026-06-05T10:20:13.403157+00:00`, 11 lanes with
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
