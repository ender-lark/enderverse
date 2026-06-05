# Codex Build Queue

Canonical repo queue for Investing OS rebuild work. GitHub files are canonical
until the core logic is stable; Notion sync comes later.

## Active Slice

- No active implementation slice.
  - Run completion audit / next-slice discovery before starting the next change.
  - Keep dashboard parity classification current before committing any new
    dashboard/feed meaning.

## Recently Completed

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
  - Documented the known retired `src/test_reallocate.py` failure and optional JSX bundle check.
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
