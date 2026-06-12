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

- When the user asks for the dash, dashboard, cockpit, or conviction cockpit,
  open the local HTML dashboard first:
  `http://127.0.0.1:8765/dashboard_preview.html`.
- Treat `http://127.0.0.1:8765/cockpit_jsx_preview.html` as an internal
  JSX parity/validation surface, not the default operator dashboard.
- Major cockpit sections should be minimizable when they can clutter the first
  screen.
- Show portfolio impact, action validity, capital efficiency, freshness,
  rationale, and blockers ahead of raw data.

## Data Honesty

- Missing, stale, or failed lanes remain dark, stale, or `not_checked`; they are
  never treated as checked clear.
- Macro and news inputs should be distilled into portfolio and action
  implications before surfacing. Raw signals are useful only when they change
  decision timing, sizing, risk, or research priority.
- Treat Fundstrat as the primary baseline, but question it with evidence and
  invalidation checks rather than blindly following it or dismissing
  counterintuitive calls because they conflict with normal market logic.
- Treat Fundstrat as separate lanes: Tom Lee for macro, Mark Newton for
  technical/timing with variable confidence, and the crypto analyst lane for
  crypto-specific analysis. Weight each lane by its domain, freshness, and
  stated confidence instead of treating Fundstrat as one undifferentiated
  source.
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

## V3 Decision Layer (TODAY—DECIDE)

- The V3 decision layer is **additive** to V2. Never remove a V2 section, lane,
  validator, or feed key when extending V3. New cards enter the cockpit ONLY
  through the action-implication contract — no parallel panels, no gate
  bypass.
- §3.4 honesty rails are **not** tunable. `tunables.py` hard-fails if a config
  file tries to define one. Tier D never scores; UW `inconclusive` = 0;
  OPEN-NOW requires a named positive trigger. Pace lives in the goal-anchor
  block only and is display-only.
- Every emitted card must pass `decision_card.validate_decision_card`.
  Missing fields are stamped UNKNOWN — never omitted.
- The MONITOR sleeve (`BMNR / LEU / UUUU / MP`) has exactly one Action path:
  MONITOR-RE-ENTRY cards from `orphan_wiring`. Those cards REQUIRE
  defined-risk fields (`stop_loss`, `risk_band`, `max_loss_usd`); without
  them no card emits. Do not add an alternate buy path.
- ACT / PASS / RECHECK rails ship as clipboard copies, second-tap UNDO is
  binding. `disposition_log.append_disposition` accepts the UNDO verb; PASS
  still requires a reason, UNDO does not.
- The 9:40 ET Post-Open Evidence Gate is mechanized by
  `post_open_evidence_gate.evaluate_all_gates`. The 8:35 ET Morning Scan is
  mechanized by `morning_scan.run_morning_scan`. Both modules are pure; the
  L5 wrapper supplies the price-lookup and writer callbacks.
- The cloud commit allowlist for routines now covers `dispositions.jsonl`,
  `timing_gates.json`, and `prediction_signals.json`. Routines may write
  these; ad-hoc edits should still go through the operator.
- The JSX parity contract between the Python HTML renderer and the React
  cockpit (`TodayDecide.jsx` / `conviction_cockpit_v6.jsx`) is enforced by
  `src/test_jsx_parity.py`. If a payload field changes shape, update BOTH
  renderers before committing.
