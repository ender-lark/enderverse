# Codex Build Queue

Canonical repo queue for Investing OS rebuild work. GitHub files are canonical
until the core logic is stable; Notion sync comes later.

## Active Slice

- Reallocation and target drift.
  - Make target weights machine-readable.
  - Surface undersized/oversized AI allocation gaps at preflight and dashboard.

## Recently Completed

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

- PDF holdings ingest.
  - Improve broker position extraction when selectable text is available.
  - Keep screenshot/OCR PDFs honest-fail until OCR tooling exists.
- Verification command.
  - Add one repo-owned command for the standard focused checks.
  - Document any known expected failures explicitly.
- Codex-owned cloud routines.
  - Replace prompt-only Claude routines with repo-owned routine docs and app automations.
  - Keep Gmail/Fundstrat intake and UW cache refresh separated from full-build synthesis.
- Fundstrat intake expansion.
  - Prefer Gmail connector email ingestion first.
  - Later add direct source/archive routes only if needed.
- ETF look-through sleeves.
  - Add holdings overlap and sleeve exposure only after dashboard parity and action surfacing are stable.

## Working Rules

- One implementation slice per turn.
- Commit and push after every clean slice.
- Do not do more UI work until dashboard parity review is complete.
- Treat any short non-conflicting user reply as continue; explicit stop/pause/change-direction overrides.
