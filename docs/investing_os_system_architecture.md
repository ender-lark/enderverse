# Investing OS System Architecture

Status: living reference for the Codex-operated Investing OS build.

This document explains the current production path: what is gathered, what is
synthesized, what is committed, and what the dashboard shows. `src/ARCHITECTURE.md`
remains the lower-level reference for the deterministic feed engine. This file
covers the surrounding operating system: source routines, cloud receipts,
safe write-back, live status, and dashboard publishing.

Notion mirror:
`https://app.notion.com/p/376c50314bb681d4b04cda8e73d6c34b`

Active build plan:
`docs/monday_go_live_build_plan.md`

Monday plan Notion mirror:
`https://app.notion.com/p/378c50314bb681afb39bcb82efce9d47`

Current audit note:
`docs/architecture_audit_2026_06_16.md`

## Current Audit Snapshot - 2026-06-16

Use the live commands in Section 12 before relying on these counts, but this is
the latest repo-verified architecture snapshot:

- Canonical checkout:
  `C:\Users\suraj\Documents\Codex\2026-06-04\confirm-you-can-access-my-github\work\enderverse`.
  The OneDrive Investing OS folder can be only a wrapper and should not be
  edited until the git root is verified.
- `live_status.py --format text` reports `live_clear`: local
  readiness, publish readiness, and live-data readiness are true; the feed stamp
  is `2026-06-16T05:19:05.446825+00:00`; the dashboard has 4 actions, 1
  research action, and 0 open reviews.
- The only dark source lane is deferred optional `social_watch`. It is visible
  as not checked, but it is not a core go-live source wait.
- `cloud_ops_status.py --format text` reports cloud ops `not_ready`: core
  scheduled proof is complete at 14/14, support scheduled proof is 7/12, and
  full live-run proof is false because receipt freshness/support proof still
  lags.
- `completion_audit.py --format text` reports `BUILD_CLEAR_WAITING_EXTERNAL`:
  local go-live ready with 0 build blockers and no active/queued
  system-improvement items after the Fundstrat transcript closeout.
- `state_ownership_map.py` and `codex_routine_manifest.py` are valid.
- The refreshed integration-debt sweep is `warn` with 1 warning and 14 total
  findings.

## 1. Operating Principle

The Investing OS is built to surface actionable buy/sell/hold/research reviews
with timing, conviction, sizing, risk, and early-retirement impact. It is not a
generic market-news collector.

Capital efficiency is a first-class decision rule. A good opportunity is not
automatically the right use of money if a better current use, funding leg,
hedge, or risk-reduction move ranks higher. The system should also avoid false
precision on timing: when fresh evidence confirms a high-impact setup, staged
exposure is preferred over waiting indefinitely for a perfect entry.

The system separates gather, normalize, decide, and display:

1. Source routines gather connector or supplied evidence.
2. Intake modules normalize that evidence into repo convention files under
   `src/`.
3. The pure feed engine reads only those convention files and builds
   `src/latest_cockpit_feed.json`.
4. Synthesis and action readers promote only conservative, evidence-backed
   actions.
5. Renderers push the feed into dashboard artifacts that the user can inspect.
6. Cloud receipts prove whether scheduled automations actually ran.

Missing source pulls are never treated as checked clear. They remain visible as
dark `not_checked` lanes with next steps.

## 2. Current Data Flow

```text
Connectors / supplied files / repo caches
  -> intake normalizers
  -> src/*.json convention files
  -> src/full_build_runner.py
  -> src/latest_cockpit_feed.json
  -> src/live_dashboard_refresh.py second pass
  -> src/rendered/conviction_cockpit_v5.jsx
  -> tmp/cockpit_jsx_preview.html as the JSX validation surface
  -> docs/index.html and tmp/dashboard_preview.html as HTML dashboards
  -> http://127.0.0.1:8765/dashboard_preview.html
```

The live dashboard is a view of the latest feed and routine state. It is not a
separate source of truth. The source of truth for engine-consumed state is the
repo convention files plus the ownership contract in
`src/state_ownership_map.json`.

The default operator/testing surface is the local HTML dashboard. The JSX
cockpit remains useful for parity and internal validation, but it should not be
opened by default for user requests for the dash, dashboard, cockpit, or
conviction cockpit.

## 3. System Layers

| Layer | Owns | Key files |
|---|---|---|
| Source access | Connector reads, browser reads, supplied drops, manual exports, and private-source-vault inputs when implemented | Gmail, Notion, Unusual Whales app/API, authenticated Fundstrat Chrome session, SnapTrade read-only broker pulls, broker uploads, manual JSON drops, planned private `INVESTING_OS_SOURCE_VAULT` |
| Intake | Normalize and validate external evidence | `fundstrat_email_intake.py`, `fundstrat_web_intake.py`, `signal_log_intake.py`, `catalyst_calendar_intake.py`, `daily_synthesis_intake.py`, `event_risk_intake.py`, `live_source_config_update.py` |
| Convention state | Machine-readable source facts | `src/*.json` convention files, `state_ownership_map.json`, `codex_routine_manifest.json` |
| Feed engine | Deterministic read/assembly/validation | `full_build_runner.py`, `feed_assembler.py`, `analyst_judgment.py`, `validators.py`, `publish_gate.py` |
| Synthesis/action surfacing | Conservative promotion into operator-visible actions | `daily_synthesis_from_feed.py`, `daily_synthesis_intake.py`, `source_call_candidate_draft.py`, `action_memory_resolve.py` |
| Dashboard | Render the latest feed and operator status | `live_dashboard_refresh.py`, `render_cockpit.py`, `cockpit_html_gen.py`, `dashboard_preview_server.py`, `live_status.py` |
| Cloud ops | Schedule proof, receipts, safe write-back | `cloud_ops_status.py`, `cloud_routine_receipts.py`, `cloud_routine_runner.py`, `cloud_routine_manual_run.py`, `cloud_routine_commit.py`, `cloud_automation_status.json` |

## 4. What Is Synthesized

The system synthesizes only from explicit source or repo evidence:

- Daily Synthesis: `src/daily_synthesis.json`
  - Supplied structured synthesis is normalized by `daily_synthesis_intake.py`.
  - Repo-evidence synthesis is generated by `daily_synthesis_from_feed.py` from
    `src/latest_cockpit_feed.json`.
  - `--merge-existing` preserves explicit synthesis actions during later
    dashboard refreshes, so a repo-evidence refresh does not erase an earlier
    Daily Synthesis action.
  - Vague prose does not become a trade. Structured actions and ticker-led
    actionable rows can promote conservatively.

- Signal Log / Morning Scan: `src/signal_log.json`
  - Normalized by `signal_log_intake.py`.
  - Watch-only context. It can explain the tape, risks, and setup background,
    but it does not directly create buy/sell actions.

- Social Watch / Reddit: `src/social_watch.json`
  - Normalized by `social_watch.py` from a future compliant API/OAuth intake or
    supplied normalized cache.
  - Watch-only anomaly context. It can identify something to vet, but cannot
    create buy/sell actions and cannot reach Key Now unless non-social evidence
    confirms the setup through another lane.

- Source-call candidates: `src/source_call_candidates.json`
  - Drafted from current feed observations by `source_call_candidate_draft.py`.
  - Merged into source-call calibration only through the explicit merge path.

- Fundstrat web and video transcript policy:
  - Authenticated Fundstrat website content can be read through the user's
    Chrome session, then reduced to compact full-content-derived rows through
    `fundstrat_web_intake.py`.
  - Fundstrat video transcript sweeps are Chrome-driven. Codex opens Fundstrat
    in the user's logged-in Chrome session, navigates Latest Videos and detail
    pages, and checks player transcript/caption controls itself. The operator
    normally only keeps Chrome logged in.
  - Video-only cards remain discovery-only unless a visible transcript,
    captions, companion article, or supplied compact notes are available.
  - Login prompts, CAPTCHA, unavailable Chrome session, permission prompts, or
    missing player transcript/caption tracks are honest blocker states and stay
    `not_checked`; they are not converted into short synthetic notes.
  - Full transcript review packs now go through
    `fundstrat_transcript_vault.py`; raw transcript/caption text is written
    only to the private source vault named by `INVESTING_OS_SOURCE_VAULT`.
  - `fundstrat_transcript_synthesis.py` reads private vault packs and emits
    compact Notion-ready review notes without raw transcript text.
  - Public repo state is limited to safe metadata, hashes, short synthesis,
    compact derived rows, `vault://...` references, and existing Fundstrat
    compact caches.

- Event Risk: `src/event_risks.json`
  - Normalized by `event_risk_intake.py` or `sudden_event_refresh.py`.
  - High or critical sudden event risk can create exposure-review actions.
  - It must not create autonomous buy/sell orders.

- UW and macro caches:
  - `uw_opportunity_signals.json`, `parabolic_setups.json`, `macro_state.json`,
    `uw_closes.json`, and `live_source_config.json` provide market-data and
    connector-proof context.
  - These confirm or challenge timing and risk. They are not standalone capital
    allocation instructions.

- Account Positions / SnapTrade:
  - SnapTrade is the preferred read-only Account Positions source once staged,
    owner-labeled, validated, and promoted.
  - The manual PDF/text broker extractor remains the fallback path.
  - As of the 2026-06-07 build, the promoted live source is SnapTrade:
    one household SnapTrade user with 11 visible accounts across Parents
    Fidelity, Parents Schwab, SKB Fidelity, SKB Schwab, and Robinhood,
    including Robinhood Crypto. The promoted caches are
    `src/positions.json`, `src/account_positions.json`, and
    `src/position_reconciliation.json`.
  - `snaptrade_positions_import.py` writes staged raw and combined outputs under
    `tmp/`; it must not directly replace `src/positions.json`,
    `src/account_positions.json`, or `src/position_reconciliation.json`.
  - Promotion still runs through the existing strict broker-position cache and
    reconciliation path so dashboard reallocation never treats an unvalidated
    pull as live portfolio truth.
  - Option valuation is broker-aware. SnapTrade Fidelity/Schwab option rows
    observed in this system use per-underlying-share option prices, so value is
    `contracts * price * multiplier`. SnapTrade Robinhood option rows observed
    in this system use contract-level prices, so value is `contracts * price`;
    applying the multiplier again overstates those option values by 100x.
  - Account-level option rows preserve option metadata. Combined Book views
    group options by ticker plus option series/description, not ticker alone,
    so common shares and separate option contracts do not collapse into one
    misleading row.
  - `src/snaptrade_profiles.local.json` is local-only and ignored. It holds
    account-owner overrides for labels such as `Parents` and `SKB`.
  - `src/snaptrade_profiles.example.json` documents the shape that can be
    committed. SnapTrade credentials stay in Windows user environment and are
    not printed or committed.
  - If SnapTrade fails and no fallback extract validates, Account Positions
    remains stale or `not_checked`; it must not be marked checked clear from old
    PDF-era cache data.
  - Include Robinhood Crypto in the Investing OS account universe when the
    staged pull validates.
  - `account_trade_placement.py` derives account-placement guidance from the
    current account-position rows. It is guidance for review prompts, not an
    execution instruction.
  - Current hard account rule: Parents Schwab / PCRA Trust is ETF-only. ETF add
    candidates should prioritize that account where possible so stock-capable
    accounts remain available for individual names. Individual stock add
    candidates must avoid Parents Schwab / PCRA Trust and prefer an existing
    non-PCRA holding account when available.
  - Account placement is intentionally simple until more constraints are
    supplied. It does not check cash, tax lots, wash-sale rules, account-level
    permissions, or final sizing; those remain pre-trade/operator gates.

  Preferred daily/post-trade refresh:

  ```powershell
  python src\snaptrade_book_refresh.py --refresh-dashboard
  ```

  Stage-only inspection without replacing the live book:

  ```powershell
  python src\snaptrade_book_refresh.py --no-promote
  ```

  Lower-level staged pull and validation sequence:

  ```powershell
  python src\snaptrade_positions_import.py --pull --profiles src\snaptrade_profiles.local.json --raw-out tmp\snaptrade_raw.json --combined-out tmp\snaptrade_combined.json
  python src\broker_pdf_extractor.py --validate tmp\snaptrade_combined.json
  python src\build_positions_cache.py --combined tmp\snaptrade_combined.json --theses src\theses.json --stdout
  python src\position_reconciliation.py --combined tmp\snaptrade_combined.json --theses src\theses.json --prior-account-positions src\account_positions.json --account-out tmp\snaptrade_account_positions.json --reconcile-out tmp\snaptrade_position_reconciliation.json
  ```

## 5. What Is Pushed To The Dashboard

The dashboard shows the feed plus operator state:

- Layout contract:
  - Validate the local HTML dashboard first. The JSX cockpit remains an
    internal parity/validation surface and must not be the default operator
    target.
  - The Action surface is scan-first by default. Major categories render as
    compact rows with a useful summary, then expand independently for details.
    The first screen should answer what matters today, what assumptions need a
    refresh, what capital-allocation opportunities exist, and what evidence is
    missing.
  - Time-sensitive and capital-allocation sections stay high in this order:
    Market-Open Packet, Today's Actions, Top Prospects, Asymmetric
    Opportunities, UW/reallocation/target-drift gates, then research/watch/proof
    context.
  - Reddit/social remains last until the compliant feed is implemented. Missing
    social data is still visible as `not_checked`, but it should not compete for
    first-screen attention or promote an action without independent proof.
  - Social Watch is a deferred optional live-capable lane while the compliant
    Reddit/social feed remains queued. It must stay visible as `not_checked`,
    but it does not create a core go-live source wait, manual-drop wait, or build
    warning. This lets the rest of the system be ready without pretending the
    social lane has been checked.
  - The HTML dashboard includes a Commands view with current operator actions,
    system checks, source links, and the Social Watch queued/dark rule. JSX may
    mirror commands for internal validation, but it must not be the only place
    current commands live.
  - Today/Decide is action-first, not top-N-first. Its decision queue separates
    Material decisions, Other rechecks, and Funding / paired sells; funding
    helper legs never outrank standalone material decisions. Remaining
    impact-ranked decisions render as full cards rather than raw backlog rows.
  - The daily pullback/reallocation packet feeds Today/Decide only as visible
    decision context and a rail-free `watch_queue`. The queue keeps
    deep-discount and pullback candidates visible with disconfirmation text, but
    it does not add ACT/PASS/RECHECK affordances and does not change conviction,
    ranking, sizing, gates, or execution posture.
  - Daily pullback packet freshness is explicit. A packet is current only when
    `as_of` equals the build date. Stale packets remain visible as research
    context with STALE/not_checked labels and stale price wording; absent
    packets create no fabricated rows and add an honesty note.

- Today's Actions: `feed.actions`
  - Includes engine actions, catalyst/event-risk review prompts, and
    conservative synthesis actions.
  - Every enriched action carries freshness, disconfirmation, and
    capital-efficiency judgment so the dashboard compares "good idea" against
    "best use of scarce capital now" before any review prompt is promoted.
  - Cards can carry optional `card.dossier` context from
    `src/decision_dossiers.json`. Dossiers mirror Live Theses through
    `src/decision_dossier_sync.py`. The dashboard refresh path runs
    `src/decision_dossier_refresh.py` before card assembly so ticker-matched
    cached UW price/opportunity/battery evidence can refresh the dynamic
    `price` and `timing` reads. Dossiers stay context-only: they do not change
    conviction scoring, ranking, sizing, gates, or trade posture. Missing
    ticker-matched evidence leaves the prior stale/not-checked read in place.
    Stale or not-checked price/timing reads render as `UNKNOWN`; for
    capital-action cards they also enter the shared `data_health` staleness
    guard as ticker/card-scoped blockers. `alert_policy` can surface those
    blockers only as review-only alert candidates when the blocked Today card
    is otherwise alert-actionable.
  - Capital-using review prompts can also carry `account_placement`: candidate
    account, why that account, and caveats. Parent Schwab/PCRA Trust is treated
    as ETF-only; this still does not place or size trades.
  - Every important action also carries `assumption_refresh`, a refresh-time
    snapshot and revalidation result with status `still_valid`,
    `changed_recheck`, `invalidated`, `stale`, or `upgraded`. This is how an
    old buy/add/review idea is downgraded when price, flow, funding, thesis,
    event-risk, or source freshness no longer supports the original setup.
  - Missing live evidence or fast-moving stale evidence moves an `ACT_NOW`
    action into Re-check Before Acting instead of leaving stale urgency in Key
    Now. The action stays visible, but the dashboard tells the operator what
    changed and what would invalidate it.
  - The top action is shown immediately in the preview summary and in
    `live_status.py`.

- Market-Open Packet: `feed.market_open_packet`
  - Sequences the current operator work before the action list: re-check stale
    or fast-moving evidence first, gate Key Now items, identify reallocation
    blockers, route UW check sets, keep dark lanes visible, and preserve open
    review pressure.
  - It shows all urgent items from Key Now, Re-check Before Acting, and
    Important Backlog rather than capping the packet to the top few rows.
    Rows include refresh status and what changed when assumptions are stale,
    missing, or still valid.
  - The first-screen hero derives its attention state from packet/action state,
    not only from the legacy `needs_you` feed field. If there are Key Now items,
    re-checks, visible actions, or backlog items, the hero must not say the
    dashboard is quiet.
  - The packet is a capital-efficiency and timing-balance aid. It helps avoid
    parking money in a merely good opportunity when a better use is live, while
    also discouraging indefinite waiting for a perfect entry when fresh evidence
    supports staged exposure.
  - For action-derived rows, the packet must carry the same decision-grade
    metadata as the action card: freshness label, evidence date, last checked
    date, decay window, key assumptions, invalidation trigger, capital-priority
    score/reason, compare-against list, and consequence of doing nothing. This
    is the first-screen proof that a top action is still valid or must be
    re-checked before capital moves.
  - It never executes trades and never treats dark or stale evidence as checked.

- From Research: `feed.research_actions`
  - Separate from Today's Actions so research does not blend with sharper
    catalyst or event drivers.

- Source lanes and dark lanes: `feed.lane_status`
  - Lanes with data are marked `has_data`.
  - Missing source pulls are `not_checked` and visible as dark lanes.
  - Current status may be go-live ready while still showing optional dark lanes.
  - Deferred optional lanes such as Social Watch are reported separately from
    actionable missing source inputs: they stay dark/not checked, but they do
    not block go-live or create a source wait.

- Synthesis panel: `feed.synthesis`
  - Shows state of play, delta, hanging items, and any structured synthesis
    actions that were preserved.

- Signal Log panel: `feed.signal_log`
  - Watch-only rows from Morning Scan / Signal Log.

- Social Watch panel: `feed.social_watch`
  - Watch-only Reddit/social anomaly rows with subreddit mix, velocity/score,
    independent-confirmation requirements, and pump/chase risk.
  - Missing cache remains visible as `not_checked`, not as no social signal.

- Event Risk / Active Watch:
  - Sudden market risks and trigger conditions are visible in dashboard status.

- Operator Status:
  - Live-source configuration, missing inputs, go-live readiness, open reviews,
    source-call status, cloud proof, and emergency command hints.

- Operator Hardening:
  - `feed.operator_hardening` surfaces freshness downgrades, stale action
    cleanup, pre-action condition checks, and watch-only reasons.
  - These panels are not new trade engines. They show what needs a re-check,
    what should be resolved or deferred, and why some important signals remain
    context rather than action.

- Source proof and audits:
  - `feed.source_audits` shows cloud routine proof, connector evidence,
    Fundstrat intake proof, Notion writeback evidence, and Notion collision
    risk when shared pages may have been written by another agent.
  - `integration_debt_sweep.py` includes a `build_without_wire` check for
    committed candidate-bearing `src/*.json` artifacts. A candidate artifact is
    acceptable only when it is read by a decision-path module, declared with a
    real feed path in `state_ownership_map.json`, or documented in
    `src/non_surfacing_allowlist.json` with a concrete non-surfacing reason.

- UW routing and action runbook:
  - `feed.uw_routing` and `feed.uw_action_runbook` translate dashboard state
    into scenario-specific Unusual Whales endpoint groups.
  - High-volatility or Re-check Before Acting posture activates pre-market crash
    triage first, before single-name conviction or reallocation decisions.
  - Routing/runbook rows are endpoint instructions only; they are not proof that
    the endpoints were fetched or confirmed the action.
  - `feed.uw_endpoint_proof` is the separate proof layer. It reads captured
    result caches such as `src/uw_endpoint_results.json` or
    `src/uw_endpoint_result_proof.json`, validates mode/endpoint/status/date
    fields, and maps raw endpoint statuses into decision interpretations:
    `supports`, `contradicts`, `inconclusive`, and `missing`.
  - Raw `neutral` fetch success becomes `inconclusive`. It proves that an
    endpoint was fetched, but it cannot promote a capital action. The
    Market-Open Packet treats inconclusive or missing rows as blockers until an
    explicit interpretation supports the action.
  - If no captured result proof exists, UW remains visible as `not_checked`.
    The Market-Open Packet treats the runbook as instructions only and blocks
    capital-sized promotion until clean endpoint proof is captured.
  - Malformed proof files fail closed in Source Proof instead of counting as
    successful UW endpoint evidence.
  - `src/uw_endpoint_result_capture.py` is the bounded live capture runner. It
    reads the current runbook, calls only approved UW endpoint constants through
    `codex_uw.rest_client.UWRestClient`, and writes redacted proof rows to
    `src/uw_endpoint_results.json`.
  - Captured rows prove endpoint fetch status only. Successful fetches remain
    inconclusive until interpretation explicitly supports or contradicts the
    dashboard thesis; they never auto-promote trades.
  - On Windows, `UWRestClient` can read `UW_API_KEY` from the current user's
    saved environment variable when the running Codex process did not inherit
    it. The key is not printed or committed.

- Preview/export artifacts:
  - Canonical injected JSX: `src/rendered/conviction_cockpit_v5.jsx`
  - JSX validation surface: `tmp/cockpit_jsx_preview.html`
  - Local HTML dashboard: `tmp/dashboard_preview.html`
  - Default local dashboard URL:
    `http://127.0.0.1:8765/dashboard_preview.html`
  - Published dashboard HTML: `docs/index.html`

- Candidate Reallocation Brief: `feed.reallocation_brief`
  - Uses current promoted positions when available. With SnapTrade current, it
    is `candidate_only`, not `test_data_only`.
  - Ranks funded add/trim candidates by target gap, thesis impact, funding
    source, risk transformation, UW/price gates, and capital-efficiency
    context. It does not execute trades.
  - Every add row now includes capital-efficiency rationale, consequence of
    doing nothing, blockers, disconfirmation, and a defined-risk options review
    prompt. Options are review-only: max loss, liquidity, expiry, sizing, and
    thesis/flow confirmation gates must all be written before any option idea
    can be considered.
  - BMNR and the crypto complex are kept in a special `undecided_recheck` lane
    until fresh evidence resolves defend versus reduce. Stale or split crypto
    evidence must not promote an add or trim.

## 6. Cloud Routine Stack

The old single daily refresh was replaced by a split routine stack so source
timing matches how the investment day works.

Core proof routines gate unattended operator readiness. They directly protect
portfolio truth, Fundstrat/timing intake, market-open decision quality,
opportunity/risk caches, dashboard publication, and post-close account refresh.

| Core routine id | Role | Normal schedule |
|---|---|---|
| `investing-os-fundstrat-pre-market-safety-sweep` | Last safety sweep for overnight / early Fundstrat timing calls before the main pre-market stack | Market weekdays 7:45 AM ET |
| `investing-os-pre-market-source-intake` | Pre-market source intake, including valid supplied broker uploads | Market weekdays 8:10 AM ET |
| `investing-os-broker-position-intake` | SnapTrade-first read-only broker position refresh | Market weekdays 8:20 AM ET |
| `investing-os-morning-scan` | Morning Signal Log / macro scan validation | Market weekdays 8:35 AM ET |
| `investing-os-early-cockpit-build` | Earliest useful cockpit using overnight, pre-market, Morning Scan, and cached source state; later lanes remain visibly pending/stale when not run yet | Market weekdays 8:50 AM ET |
| `investing-os-daily-synthesis` | Daily Synthesis after the Morning Scan | Market weekdays 9:30 AM ET |
| `investing-os-post-open-evidence-gate` | Same-session UW endpoint proof from the current action runbook; inconclusive proof stays blocking | Market weekdays 9:40 AM ET |
| `investing-os-fundstrat-daytime-watch` | Hourly daytime Fundstrat watch; lands only action-relevant compact rows and pushes only urgent/action-changing alerts | Market weekdays hourly 9:45 AM-3:45 PM ET |
| `investing-os-uw-opportunity-cache` | UW opportunity cache and non-secret connector proof | Market weekdays 10:00 AM ET |
| `investing-os-parabolic-cache` | Parabolic/chase-risk cache | Market weekdays 10:05 AM ET |
| `investing-os-full-cockpit-build` | Full dashboard build after source/synthesis/UW buffer | Market weekdays 10:30 AM ET |
| `investing-os-post-close-refresh` | Post-close dashboard refresh and proof path | Market weekdays 4:30 PM ET |
| `investing-os-positions-sync` | Post-close SnapTrade-first position sync | Market weekdays 4:45 PM ET |
| `investing-os-fundstrat-after-hours-catch-up` | After-hours Fundstrat catch-up for late notes and next-session prep | Market weekdays 7:00 PM ET |

Support-monitored routines remain useful, but they do not gate core unattended
readiness by themselves. Their missed scheduled receipts stay visible as
support proof gaps, but the dashboard should not imply the whole operator
cockpit is unready solely because one of those helper lanes has only manual
support.

| Support routine id | Role | Normal schedule |
|---|---|---|
| `investing-os-fs-inbox-catch-up-preopen` | Fundstrat inbox catch-up slot | Market weekdays 8:20 AM ET |
| `investing-os-fs-inbox-catch-up-midday` | Fundstrat inbox catch-up slot | Market weekdays 12:30 PM ET |
| `investing-os-fs-inbox-catch-up-postclose` | Fundstrat inbox catch-up slot | Market weekdays 4:35 PM ET |
| `investing-os-off-hours-research-queue` | Off-hours Research Queue intake when live Notion/export rows are available | Market weekdays 7:30 PM ET |
| `investing-os-top-prospects-auto-research` | Top prospects auto-research support | Daily 8:45 PM ET |
| `investing-os-fs-inbox-catch-up-evening` | Fundstrat inbox catch-up slot | Market weekdays 8:45 PM ET |
| `investing-os-off-hours-alt-data-scout` | Off-hours alternative-data scout | Daily 9:15 PM ET |
| `investing-os-off-hours-worker` | Overnight status/research support checks | Daily 1:45 AM ET |
| `investing-os-off-hours-queue-buffer` | Off-hours queue buffer | Daily 4:45 AM ET |
| `investing-os-deep-synthesis` | Weekly deeper synthesis support | Sunday 1:00 PM ET |
| `investing-os-weekly-pilot-run` | Weekly pilot/status run | Sunday 6:00 PM ET |

The Fundstrat late-evening web/transcript sweep has repo prompt coverage in
`src/codex_routines/fundstrat_late_evening_web_transcript_sweep.md`. It should
navigate Fundstrat in Chrome during the routine, including Latest Videos,
detail pages, embedded transcript/caption controls, and companion text when
available. Missing transcript/caption/companion evidence, login/CAPTCHA blocks,
or inaccessible Chrome state must remain not checked; video-only discovery does
not update compact caches or Notion review notes.

`src/cloud_automation_status.json` records the expected app-created automation
ids, superseded legacy routines, and the schedule basis. `cloud_ops_status.py`
compares that proof file with local app automation TOML files when available.

## 7. Receipt Model

Cloud readiness has three separate states:

- Schedule ready: expected routines are installed, active, prompt-checked, and
  live-source config is fresh enough.
- First scheduled proof: at least one expected scheduled routine has written a
  success receipt.
- Full live-run proof: every core proof routine has at least one scheduled
  success receipt and no core routine is overdue.

The proof store is `src/cloud_routine_receipts.json`.

Receipt rules:

- Scheduled app automations must write receipts with `run_source=scheduled`.
- Manual runs write `run_source=manual` and do not satisfy scheduled proof.
- Status surfaces must display manual support separately from scheduled proof.
  Manual support can prove the local routine path still works, but it cannot
  make an overdue scheduled routine look current.
- A routine normally writes `started`, then `success` or `failed`.
- `cloud_ops_status.py --require-first-proof` fails until first scheduled proof.
- `cloud_ops_status.py --require-live-run` fails until all core proof routines
  have scheduled success receipts. Support-monitored routines are displayed
  separately.

The wrapper for scheduled commands is:

```powershell
python src/cloud_routine_runner.py --run-source scheduled --routine-id <id> -- <command>
```

The manual test path is:

```powershell
python src/cloud_routine_manual_run.py --format text --strict
```

Manual runs prove that local command paths execute now. They do not prove that
the cloud scheduler fired at the scheduled time.

Dashboard build windows:

- The 8:50 AM ET Early Cockpit Build is the first operator surface. It is
  intentionally allowed to publish before Daily Synthesis, UW Opportunity Cache,
  and Parabolic Cache have run. Those later inputs must remain visible as
  pending, stale, or not checked when applicable.
- The 10:30 AM ET Full Cockpit Build remains the more complete mid-morning
  refresh after the synthesis/UW buffer.

Fundstrat-specific safety windows:

- The after-hours catch-up looks for late Fundstrat notes after the close so the
  next dashboard does not wait until the main morning stack.
- The pre-market safety sweep looks for overnight and early-morning Fundstrat
  notes before the normal 8:10 AM source intake.
- The daytime watch looks hourly for new Fundstrat notes while the market is
  open and can send Pushover only for fresh, time-sensitive, action-changing
  evidence.
- These routines must use full-body Gmail evidence or compact full-body-derived
  rows, must redact raw email bodies from repo files, and must run the same
  source-call merge/validation path before their data can count as checked.
- Low-value Fundstrat content is suppressed across the whole Fundstrat path.
  Webinars, replays, promotional notes, and broad context that does not change
  action posture, timing, sizing, risk, or research priority can remain
  audit/discovery context, but must not become a dashboard daily-call row,
  action prompt, or Pushover alert.
- Fundstrat publication format is a first-class routing signal. Monthly Bible,
  What-to-Own, Top-5/Bottom-5, Consider List, and Granny-style list content is
  baseline/prospect context; daily technicals are timing evidence only when
  specific; macro/First Word items are risk/sizing/event gates only when they
  change posture; weekly reviews are audit-only unless they change timing,
  risk, sizing, hedge posture, or named-ticker research priority.

Fundstrat evidence should be preserved as separate lanes instead of collapsed
into one generic source:

- Tom Lee / Fundstrat macro is the primary macro baseline, but still needs
  freshness, live-tape checks, and explicit invalidation conditions.
- Mark Newton / technical is timing and technical evidence. Its weight should
  vary with the confidence of the specific call and should not automatically
  dominate thesis, macro, or portfolio evidence.
- The Fundstrat crypto analyst lane is crypto-specific evidence for the crypto
  complex and related exposures.
- Counterintuitive Fundstrat calls should be tested through assumptions,
  source freshness, and invalidation triggers rather than rejected simply
  because they conflict with normal market logic.
- Macro/news signals should surface only after being distilled into the
  portfolio implication: what changes about sizing, timing, risk, hold/add/trim
  decisions, or research priority.

Low-level implementation:

- `src/fundstrat_lanes.py` is the shared classifier for Fundstrat lane metadata
  and publication capture policy: publication type, capture policy, use case,
  decision usefulness, and capture reason.
- `src/fundstrat_daily_compact_intake.py` filters compact manual/connector rows
  so low-value Fundstrat fluff is not promoted into daily calls, then keeps
  source-call candidates/log dates in sync for accepted full-body-derived
  compact rows.
- `src/fundstrat_daytime_alert.py` evaluates compact daily calls for urgent
  Pushover delivery and uses `fundstrat_daytime_alert_state.json` to suppress
  duplicates.
- `src/pushover_notify.py` sends Pushover messages using redacted environment
  configuration and never prints or commits secrets.
- `src/fundstrat_daily.py` attaches `fundstrat_lane`, `source_domain`,
  `author_role`, `source_weight_note`, and `confidence_policy` to daily
  Fundstrat evidence cards.
- `src/source_call_candidate_draft.py` attaches the same lane metadata when
  feed observations become pending source-call calibration candidates.
- Lane metadata affects interpretation and trust notes, but Fundstrat rows
  still share the single `fundstrat` independence group so multiple Fundstrat
  notes cannot masquerade as independent confirmation.
- Mark Newton calls with specific levels/timing keep normal Fundstrat weight;
  soft technical context is intentionally lower weight until it becomes a
  confident or falsifiable setup.

Source-conflict outcome contract:

- `src/feed_assembler.py` emits `feed.source_conflicts` only when the conviction
  engine finds a real bull/bear split on a current holding.
- Each conflict row must include the ticker, scope, bull read, bear read,
  action posture, and decision effect.
- Conflict posture is review-only and should normally downgrade toward hold,
  no-add, re-check, watch, or research. A conflict view without posture is not
  decision-useful enough to promote.
- The HTML dashboard and JSX validation surface render a collapsed Source
  Conflicts section near Today's Actions; when there are no conflicts, it stays
  visible as a quiet zero-state check.

Synthesis usefulness contract:

- `src/analyst_judgment.py` requires every promoted Daily Synthesis action to
  declare or imply `synthesis_changes`: `act`, `wait`, `re-check`, `research`,
  `trim`, `hedge`, `size`, or `no capital yet`.
- Synthesis rows that cannot say what they change are collapsed into context
  and do not enter `feed.actions`.
- Synthesis posture controls action state: `size`, `trim`, `hedge`, and `act`
  can be loud review prompts; `re-check`, `research`, `wait`, and
  `no capital yet` stay in non-execution posture.
- `src/decision_support.py` uses `synthesis_changes` in the outcome ladder:
  `re-check` routes to Re-check Before Acting, `research` to Important Backlog,
  and `wait`/`no capital yet` to Quiet Watch.
- `capital_priority_score` ranks items inside their decision group using goal
  score, goal impact, downside protection, sizing gaps, opportunity cost,
  capital effect, synthesis posture, and assumption-refresh status.
- The HTML dashboard and JSX validation surface show compact `changes:` and
  `priority:` tags on action cards. These are explanation/ranking metadata
  only; they do not execute trades or bypass gates.
- `feed.market_open_packet` repeats the key action-validity fields for urgent
  action-derived rows so the first-screen operator path does not depend on
  opening a deeper action drawer before seeing freshness, invalidation,
  capital-priority, and do-nothing risk.

Book allocation guidance contract:

- `src/portfolio_views.py` builds direct account category views from
  `account_positions.json` and overlays the working-model category target,
  target gap, and Fundstrat cue/date when available.
- The Book tab labels these as an allocation guide, not an instruction to trade.
  Fundstrat currently contributes cue/direction context, while the working model
  supplies the numeric target/gap view.
- The HTML dashboard Book view shows the guide above each account table, and
  the JSX validation surface shows the same guide beside Combined, Parents,
  and SKB account category views.
- Effective exposure remains separate from direct book weight; ETF
  look-through estimates are useful context but are not additive to direct
  account percentages.

## 8.1 Notion Writeback And Collision Rules

Notion pages can be touched by scheduled Codex routines and by other agents.
The repo must therefore separate three states:

- Local cache updated: a repo JSON file changed.
- Connector write attempted: a routine tried to write to Notion.
- Live write verified: the routine fetched the live Notion page after the write
  and confirmed the content landed.

Only live write verification should be treated as a proven Notion writeback.
If Claude or another routine may have written the same Notion surface, the
dashboard's Notion collision audit should stay visible until the relevant live
page is searched/fetched and reconciled.

The active scheduled prompts that write or may write to Notion now require live
page readback before reporting write success or updating page status.

Decision Dossier sync follows the same proof rule. `decision_dossier_sync.py`
can use the repo Notion API client when `NOTION_API_TOKEN` is available; when
row-query tooling is unavailable, use verified Notion page search/fetch readback
or leave the ticker `pending_sync`. Dossier alert/watch wiring consumes merged
staleness guard PR#57: stale or not-checked dynamic reads use `data_health` and
`alert_policy`, not a separate dossier freshness policy.
`decision_dossier_refresh.py` is the cached-evidence dynamic read path. It runs
before dashboard builds, performs no live fetches, and updates only
ticker-matched price/timing evidence. It must not convert absent UW evidence
into a checked-clear dossier read.
`decision_dossier_coverage.py` is the Source Proof coverage audit. It surfaces
current action/material tickers that lack a repo dossier row as coverage debt
only. Missing dossiers must not enter `data_health`, card blockers, alert
policy, scoring, sizing, gates, or trade posture; stale/not-checked reads on an
existing dossier remain the staleness guard's responsibility.

## 8. Safe Write-Back

Scheduled routines may run while unrelated generated files are dirty. They must
not blindly commit the whole worktree.

`src/cloud_routine_commit.py` stages and commits only an allowlist of
routine-owned outputs. It reports unrelated dirty paths and leaves them
untouched. This is the expected write-back path for scheduled app automations.

Important owned outputs include:

- `src/cloud_routine_receipts.json`
- `src/live_source_config.json`
- `src/latest_cockpit_feed.json`
- `src/rendered/conviction_cockpit_v5.jsx`
- `docs/index.html`
- `tmp/dashboard_preview.html`
- `tmp/dashboard_parity_feed.json`
- `src/heartbeat.json`
- `src/daily_synthesis.json`
- `src/source_call_candidates.json`
- `src/source_rates.json`
- `src/uw_endpoint_results.json`
- redacted Fundstrat intake/alert state such as `fundstrat_daily_calls.json`,
  `fundstrat_inbox_entries.json`, `fundstrat_intake_state.json`,
  `fundstrat_intake_summary.json`, and `fundstrat_daytime_alert_state.json`
- lane caches such as `signal_log.json`, `catalysts.json`,
  `event_risks.json`, `uw_opportunity_signals.json`, and
  `parabolic_setups.json`

Generated Fundstrat files should be committed only by Fundstrat-owned validated
routine runs. They should not be committed as a side effect of unrelated
cloud/dashboard work, and raw Fundstrat bodies should never be committed.

## 9. Live Source Honesty

`live_source_capability.py` separates three questions:

1. Is a convention input present?
2. Is the source connector/API-capable, supplied/export-capable, or repo-local?
3. Is required live-fetch configuration present and fresh?

`live_status.py` and `cloud_ops_status.py` include this report so a valid local
cache is not mistaken for proof that every source was freshly fetched.

Dark-lane rules:

- Missing optional source inputs remain visible as dark lanes.
- Missing source pulls are never converted into checked-clear rows.
- `checked_clear` is valid only after a source was actually checked and found
  empty under that lane's contract.
- A deferred optional source lane can be dark without being a core source wait.
  Current deferred key: `social_watch`.
- Operator surfaces (`live_status.py`, `go_live_checklist.py`,
  `completion_audit.py`, HTML dashboard, and JSX validation card) split deferred
  optional dark lanes from actionable dark lanes. Deferred Social Watch should
  show as visible/not checked without producing a core manual-drop instruction.
- The heartbeat/layer strip follows the same rule: actionable dark source lanes
  can mark Optional Source Lanes stale, but deferred-only Social Watch should
  keep the layer green with a deferred/not-checked note.
- Account Positions is live-capable through SnapTrade when the staged pull
  validates and is promoted through the broker-position cache. If SnapTrade
  fails and the fallback extractor is not validated, Account Positions should
  revert to stale or `not_checked`, not checked clear.
- Meridian is stale thesis archive context after March 2026, not live tactical
  evidence. Missing Meridian archive data should not count as a live-source
  dark lane or a checked-clear signal.

## 10. Dashboard Refresh Sequence

`src/live_dashboard_refresh.py` is the repeatable dashboard package builder.

It runs, in order:

1. `heartbeat_status.py` before synthesis.
2. `decision_dossier_refresh.py` to refresh dossier dynamic reads from checked
   repo evidence.
3. `full_build_runner.py --publish` to build/publish a pre-synthesis feed.
4. `source_call_candidate_draft.py` to update source-call candidates from feed
   observations.
5. `fed_day_reallocation_packet.py` to regenerate the daily pullback packet for
   the final Today/Decide watch queue.
6. `daily_synthesis_from_feed.py --merge-existing` to refresh repo-evidence
   synthesis without deleting explicit synthesis actions.
7. `heartbeat_status.py` after synthesis.
8. `full_build_runner.py --publish` again for the final feed.
9. `render_cockpit.py` to inject the feed into the JSX validation surface.
10. `cockpit_jsx_preview.py` for the JSX preview shell.
11. `cockpit_html_gen.py` for `docs/index.html`.
12. `cockpit_html_gen.py` for `tmp/dashboard_preview.html`.
13. `full_build_runner.py` for `tmp/dashboard_parity_feed.json`.

This two-pass flow matters because the first feed creates evidence that
synthesis/source-call tracking can use, and the second feed shows the resulting
operator-facing synthesis/action state.

## 11. Key Module Reference

Cloud ops:

- `cloud_ops_status.py`: operator proof for routine stack, receipts, dark lanes,
  live-source config, due/overdue schedule state, and open gaps.
- `cloud_automation_status.json`: repo record of active/superseded automation
  ids, roles, schedules, and schedule rationale.
- `cloud_routine_receipts.py`: append, validate, and summarize routine receipts.
- `cloud_routine_runner.py`: wraps one routine command with started/final
  receipts.
- `cloud_routine_manual_run.py`: runs the whole routine stack immediately with
  manual receipts.
- `cloud_routine_drill.py`: non-mutating receipt-mechanics drill.
- `cloud_routine_commit.py`: allowlist-only commit/push helper for scheduled
  routine outputs.

Source capability and intake:

- `live_source_capability.py`: non-fetching report of source coverage and
  live-fetch configuration.
- `live_source_config_update.py`: writes compact non-secret connector proof.
- `manual_source_drop.py`: routes explicitly supplied source-drop JSON through
  lane intake modules.
- `fundstrat_email_intake.py`: parses full-body Fundstrat evidence without
  storing raw bodies.
- `fundstrat_daily_compact_intake.py`: writes compact full-body-derived or
  screenshot/text-derived Fundstrat rows while suppressing low-value content.
- `fundstrat_daytime_alert.py`: sends duplicate-suppressed Pushover review
  prompts for urgent/action-changing Fundstrat evidence.
- `pushover_notify.py`: redacted Pushover delivery helper.
- `signal_log_intake.py`: normalizes Morning Scan / Signal Log rows as
  watch-only context.
- `catalyst_calendar_intake.py`: normalizes exact-dated catalyst rows.
- `daily_synthesis_intake.py`: normalizes supplied Daily Synthesis.
- `daily_synthesis_from_feed.py`: builds conservative repo-evidence synthesis.
- `event_risk_intake.py`: normalizes supplied event-risk rows and one-line
  sudden-event rows.

Feed and dashboard:

- `full_build_runner.py`: reads convention files, reports dark/missing inputs,
  builds the feed, and optionally publishes through the gate.
- `feed_assembler.py`: pure feed assembly.
- `analyst_judgment.py`: pure read/action logic.
- `validators.py`: feed and action-row structural validation.
- `publish_gate.py`: live publish safety gate.
- `live_dashboard_refresh.py`: standard dashboard refresh package.
- `live_status.py`: concise operator status for dashboard/live health.
- `render_cockpit.py`: injects feed JSON into the JSX validation surface.
- `cockpit_html_gen.py`: builds dashboard HTML summary/preview.
- `dashboard_preview_server.py`: local preview server status.

## 12. Standard Operator Commands

Fast live status:

```powershell
python src/live_status.py --format text
```

Cloud schedule and first proof:

```powershell
python src/cloud_ops_status.py --format text --require-first-proof
```

Full cloud proof:

```powershell
python src/cloud_ops_status.py --format text --require-live-run
```

Refresh the dashboard package:

```powershell
python src/live_dashboard_refresh.py
```

Run all local routine paths now with manual receipts:

```powershell
python src/cloud_routine_manual_run.py --format text --strict
```

Standard repo verification:

```powershell
python src/verify_standard.py
```

## 13. Current Known Gaps

As of the 2026-06-16 architecture audit:

- Local operator readiness is true, but unattended cloud operations are not
  healthy. `cloud_ops_status.py --format text` reports core scheduled proof at
  14/14, support scheduled proof at 7/12, stale/overdue routine windows, and
  `Cloud live-run proven: False`.
- The dashboard feed is from `2026-06-16T05:19:05.446825+00:00`. Future agents
  should rerun `live_status.py` and refresh the dashboard when current-session
  market posture matters.
- Social Watch is the only dark lane and remains deferred optional. Its absence
  is not a no-signal read and should not block core go-live.
- The system-improvement queue has no active/queued items after the Fundstrat
  transcript closeout.
- Integration debt is still `warn`: the clean 2026-06-16 sweep reports 14
  findings, including `research_action_promotion` as prompt-only, 12
  info-level module-wiring candidates, and the live Notion queue not checked.
- Notion row-level certainty is unavailable unless a live Notion search/fetch
  or export snapshot is supplied. Repo mirrors are fallback evidence only.
- Meridian can remain absent as archived thesis context; it is not a live
  tactical source gap after March 2026.
- Core List ingestion remains out of scope unless the user makes a new explicit
  request after the working system needs it.

## 14. Update Policy

Update this document when any of these change:

- Routine ids, schedules, or receipt rules.
- Source lane ownership or missing-source behavior.
- Dashboard refresh order or artifact paths.
- Action-promotion rules for synthesis, Signal Log, Event Risk, Research, or
  source calls.
- Verification commands or publish gates.
