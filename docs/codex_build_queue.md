# Codex Build Queue

Canonical repo queue for Investing OS rebuild work. GitHub files are canonical
until the core logic is stable; Notion sync comes later.

## Active Slice

- Dashboard parity review.
  - Decide the canonical dashboard path: generated HTML or JSX.
  - Map every feed block to its dashboard surface.
  - List missing, partial, duplicate, and obsolete surfaces before more UI work.

## Recently Completed

- Feedback/source-call tracking surfacing.
  - Make overdue source-call scoring visible.
  - Make repeated source-call persistence clusters durable in the feed/dashboard.
  - Keep stale or not-checked calibration visibly provisional.

## Queued Slices

- Reallocation and target drift.
  - Make target weights machine-readable.
  - Surface undersized/oversized AI allocation gaps at preflight and dashboard.
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
