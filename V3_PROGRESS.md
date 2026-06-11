# V3 Progress Log

## Current task
- Push branch + open PR to main (do not merge)

## Tasks done
- ab2fd4a — v2-stable anchor (baseline retained, not modified).
- 62cb71f — v3(task-1): integrate C1-C4 + C5 modules; add `docs/v3_handoff/` and this progress file.
- Task 2 done (hash 31da7d2): inserted `today_decide.build_and_render(...)` as the FIRST section in `cockpit_html_gen.py`; performed golden/parity refreeze (`src/golden_feed.json`, `docs/index.html`, `src/rendered/conviction_cockpit_v5.jsx`) and updated `src/cockpit_html_gen.py`.
- Task 3 done (hash 3cb1fb4): added `src/disposition_log.py`, refactored `today_decide.py` to use the C6 disposition readers, and added `src/test_disposition_log.py` + today-decide last-disposition coverage.
- Task 4 done (hash dd478c8): added `src/pattern_engine.py` (ENDORSED-DIP, EXPLICIT-ADD, DRUMBEAT, prediction_signals stub) + `src/test_pattern_engine.py` (23 tests). Pure detectors → cards-only; conviction via `conviction_engine`, timing via `timing_engine`; Tier-D counts toward drumbeat mention threshold but adds 0 conviction points (doctrine); prediction_signals.json honest "not_checked" when absent.
- Task 5 done (hash 31b6bc8): added `src/orphan_wiring.py` (MONITOR-RE-ENTRY cards with defined-risk gate, GRNY-DELTA evidence items, 13F+insider→inst_state adapter, unified runner) + `src/test_orphan_wiring.py` (16 tests). Threaded `extra_cards` / `extra_fs_items` / `inst_states` kwargs through `directive_recs.build_directive_cards` and `today_decide.build_today_decide_payload` so orphan-wiring outputs flow into the feed build additively. Institutional honesty line flips from "not wired" → "wired via orphan_wiring (13F + insider lanes)" when an inst_state map is supplied. Golden checked drift-free at task boundary (no oracle change since wiring is purely additive).
- Task 6 done (hash 48531e0): extended `src/pattern_engine.py` with wave-2 detectors (STALE-LEAPS, OVEREXPOSURE-ROTATION, TIER-B-SIDE-PLAY) and two non-card guards (`apply_factor_overlap_caveat` mutates BUY cards in place above the `factor_overlap_warn_pct` floor; `apply_parabolic_chase_dampener` caps OPEN-NOW → STAGE-ONLY for tickers flagged in `parabolic_setups`). `detect_patterns` extended with optional `held_options`, `drift_rows`, `sleeve_states`, `smid_top5` inputs and emits an honest "not_checked" status when each cache is absent. Tests in `src/test_pattern_engine.py` extended to cover all five (now 42 tests total). Golden drift-free at Task-5/6 boundary (no oracle change; all wave-2 wiring is additive).
- Task 7 done (hash 0ac4756): added `src/conviction_cockpit_v6.jsx` (artifact-cockpit shell that imports `TodayDecide` and renders it on a payload, with an honest-absence path when the payload is missing) and `src/test_jsx_parity.py` (10 tests) enforcing the parity contract — identical sets of `(card_id, ticker, window.class, conviction.read, priority)` between the HTML renderer and JSX component, and identical rail copy strings (`ACT <card_id>` / `PASS <card_id> — reason: ` / `RECHECK <card_id> resurface <recheck_date>` / `UNDO <card_id>`). Static contract checks read the JSX source to assert it references every canonical payload field. Mojibake-em-dash form (`â€”`) normalized at read time so the HTML and JSX render-strings compare equal.
- Task 8 done: extended `src/cloud_routine_commit.DEFAULT_ALLOWED_PATHS` with `dispositions.jsonl`, `timing_gates.json`, and `prediction_signals.json` so scheduled cloud routines may commit them. Added `src/post_open_evidence_gate.py` (9:40 ET routine: `evaluate_all_gates(price_fn, writer)` runs `timing_engine.evaluate_gate` per gate, proposes + stamps state changes, and optionally rewrites `timing_gates.json` via the supplied writer). Added `src/morning_scan.py` (8:35 ET routine: `run_morning_scan(...)` runs `pattern_engine.detect_patterns` + applies `apply_parabolic_chase_dampener` and `apply_factor_overlap_caveat`; flags parabolic tickers loaded from `parabolic_setups.json`). Added `src/test_v3_routines.py` (16 tests). Registered `dispositions` and `prediction_signals` in `src/state_ownership_map.json`. Updated `src/ARCHITECTURE.md` (new §12 V3 decision-layer module map + payload contract + honesty rails + routine flow) and `AGENTS.md` (new "V3 Decision Layer" guidance section).

## Next action
- Push branch `v3-decision-layer` to origin and open a PR to `main` titled "V3 decision layer". DO NOT merge.

## Gates / invariants
- Current branch gate after Task 8 is **1372 passed / 5 failed / 6 skipped** (+14 from Task 8 coverage: +16 routine tests, –2 from a calendar-roll deviation documented below; skip set unchanged).
- New calendar-roll deviation logged (2026-06-11): `test_insider_unstub.py::test_preflight_normalizes_raw_catalyst_rows_for_insider_scan` and `test_orchestrator_normalizes_wrapped_catalyst_cache` flipped to FAIL when 2026-06-10 became a past date. Both tests use a hard-coded catalyst date of "2026-06-10"; `runtime_adapters.catalysts_from_calendar_rows` correctly filters past catalysts (`days_out < 0`), so the FLAGGED insider classification can no longer fire. Failures confirmed to exist at HEAD `26d2a0b` (Task-7 progress) BEFORE any Task-8 changes — they are not regressions introduced by V3 work. Fix is a one-line catalyst-date adjustment in those fixtures; intentionally left for a follow-up since it is outside V3 scope.
- ZERO new failures introduced; failures remain subset of documented baseline failures.
- Current failed set:
  - `test_go_live_checklist_cli_runs_against_current_repo` (baseline)
  - `test_go_live_checklist_cli_text_format_runs_against_current_repo` (baseline)
  - `test_cloud_routine_manual_run` (baseline)
  - `test_insider_unstub::test_preflight_normalizes_raw_catalyst_rows_for_insider_scan` (calendar-roll 2026-06-11)
  - `test_insider_unstub::test_orchestrator_normalizes_wrapped_catalyst_cache` (calendar-roll 2026-06-11)
- Deviation logged: `test_rendered_cockpit_keeps_operator_status_card` flipped to PASS after regenerated render artifacts.
- Skips must remain exactly 6 (env/platform conditional) with identical reasons.
  - `src/test_broker_pdf_extractor.py`: missing `pypdf` (`could not import 'pypdf'`)
  - `src/test_render_cockpit.py`: pinned renderer not present in this environment (`set COCKPIT_TEMPLATE` to run)
  - `src/test_render_cockpit.py` (5 additional skips): same pinned renderer constraint.
- Golden + parity refreeze occurs only at Task-2 and Task-5/6 boundaries.
- Full `python -m pytest src/ -q` before each commit.

## Recovery rule
- Never reset. Never re-extract zips. Resume from this file.
