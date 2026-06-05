# Codex Build Queue

Canonical repo queue for Investing OS rebuild work. GitHub files are canonical
until the core logic is stable; Notion sync comes later.

## Active Slice

- Fundstrat intake expansion.
  - Prefer Gmail connector email ingestion first.
  - Later add direct source/archive routes only if needed.

## Recently Completed

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

- ETF look-through sleeves.
  - Add holdings overlap and sleeve exposure only after dashboard parity and action surfacing are stable.

## Working Rules

- One implementation slice per turn.
- Commit and push after every clean slice.
- Do not do more UI work until dashboard parity review is complete.
- Treat any short non-conflicting user reply as continue; explicit stop/pause/change-direction overrides.
