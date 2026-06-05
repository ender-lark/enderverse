# Codex Build Queue

Canonical repo queue for Investing OS rebuild work. GitHub files are canonical
until the core logic is stable; Notion sync comes later.

## Active Slice

- Completion audit and next-slice discovery.
  - Re-check older refinement notes after the From-Research priority-label slice.
  - Promote the next self-contained repo slice if one remains.

## Recently Completed

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
