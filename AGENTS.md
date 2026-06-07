# AGENTS.md

Repo-local operating protocol for Codex agents working on the Investing OS.

## Source Of Truth

- `docs/monday_go_live_build_plan.md` is the active source of truth for the
  Monday go-live build.
- Repo/GitHub docs are canonical for implementation state. Notion is the
  readable mirror for recovery, rebuilds, upgrades, and troubleshooting.
- Treat older CI, Notion, Claude, or chat handoffs as context only until they
  are reconciled against the current repo state.

## Primary Objective

The product goal is early retirement through better capital decisions, risk
control, time saved, and confidence in acting or not acting. Architecture,
tests, dashboard design, and source routing should serve that outcome before
technical elegance.

## Build Protocol

- Work in small, clean, verified slices.
- Commit after each clean verified slice.
- Prefer the existing repo patterns and helpers before adding new abstractions.
- Keep important operating decisions in repo docs; do not rely on chat memory.
- Use `python src/verify_standard.py` as the standard verification command
  unless a narrower focused check is explicitly appropriate before it.

## Dashboard Protocol

- During v1 build/testing, validate the local canonical JSX cockpit first:
  `http://127.0.0.1:8765/cockpit_jsx_preview.html`.
- Generated HTML and GitHub Pages are mirror/export surfaces until v1 is
  finalized.
- Major cockpit sections should be minimizable when they can clutter the first
  screen.
- Show portfolio impact, action validity, capital efficiency, freshness,
  rationale, and blockers ahead of raw data.

## Data Honesty

- Missing, stale, or failed lanes remain dark, stale, or `not_checked`; they are
  never treated as checked clear.
- Meridian is stale thesis archive context after March 2026, not live tactical
  evidence.
- SnapTrade is the preferred read-only Account Positions source after staged
  validation. Manual PDF/text extraction remains a fallback.
- If SnapTrade fails and no fallback validates, Account Positions should become
  stale or `not_checked`, not silently fresh.

## Decision Safety

- The system surfaces review prompts and decision support only. It does not
  execute trades.
- Promoted actions need rationale, evidence freshness, decay speed, assumption
  refresh status, and invalidation triggers.
- A good opportunity is not enough; compare it against better current uses of
  capital while avoiding over-precise timing that misses major up days.
- Keep `ANET` and `GOOGL` open unless the user explicitly asks to resolve them.

## Out Of Scope For Main Build

- Do not work on Reddit/social in the main build except through
  `docs/reddit_social_new_chat_handoff.md`.
- Do not accelerate cloud routine proof unless the user explicitly asks. Let
  normal scheduled receipts accumulate in the background.
