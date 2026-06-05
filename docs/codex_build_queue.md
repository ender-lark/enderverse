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

## Recently Completed

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
- Feedback/source-call tracking surfacing.
  - Make overdue source-call scoring visible.
  - Make repeated source-call persistence clusters durable in the feed/dashboard.
  - Keep stale or not-checked calibration visibly provisional.

## Queued Slices

No additional queued implementation slices. Add new deferred work here before starting another slice.

## Working Rules

- One implementation slice per turn.
- Commit and push after every clean slice.
- Do not do more UI work until dashboard parity review is complete.
- Treat any short non-conflicting user reply as continue; explicit stop/pause/change-direction overrides.
