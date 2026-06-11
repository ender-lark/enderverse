# V3 Progress Log

## Current task
- Task 7: JSX parity port (next)

## Tasks done
- ab2fd4a — v2-stable anchor (baseline retained, not modified).
- 62cb71f — v3(task-1): integrate C1-C4 + C5 modules; add `docs/v3_handoff/` and this progress file.
- Task 2 done (hash 31da7d2): inserted `today_decide.build_and_render(...)` as the FIRST section in `cockpit_html_gen.py`; performed golden/parity refreeze (`src/golden_feed.json`, `docs/index.html`, `src/rendered/conviction_cockpit_v5.jsx`) and updated `src/cockpit_html_gen.py`.
- Task 3 done (hash 3cb1fb4): added `src/disposition_log.py`, refactored `today_decide.py` to use the C6 disposition readers, and added `src/test_disposition_log.py` + today-decide last-disposition coverage.
- Task 4 done (hash dd478c8): added `src/pattern_engine.py` (ENDORSED-DIP, EXPLICIT-ADD, DRUMBEAT, prediction_signals stub) + `src/test_pattern_engine.py` (23 tests). Pure detectors → cards-only; conviction via `conviction_engine`, timing via `timing_engine`; Tier-D counts toward drumbeat mention threshold but adds 0 conviction points (doctrine); prediction_signals.json honest "not_checked" when absent.
- Task 5 done (hash 31b6bc8): added `src/orphan_wiring.py` (MONITOR-RE-ENTRY cards with defined-risk gate, GRNY-DELTA evidence items, 13F+insider→inst_state adapter, unified runner) + `src/test_orphan_wiring.py` (16 tests). Threaded `extra_cards` / `extra_fs_items` / `inst_states` kwargs through `directive_recs.build_directive_cards` and `today_decide.build_today_decide_payload` so orphan-wiring outputs flow into the feed build additively. Institutional honesty line flips from "not wired" → "wired via orphan_wiring (13F + insider lanes)" when an inst_state map is supplied. Golden checked drift-free at task boundary (no oracle change since wiring is purely additive).
- Task 6 done (hash 48531e0): extended `src/pattern_engine.py` with wave-2 detectors (STALE-LEAPS, OVEREXPOSURE-ROTATION, TIER-B-SIDE-PLAY) and two non-card guards (`apply_factor_overlap_caveat` mutates BUY cards in place above the `factor_overlap_warn_pct` floor; `apply_parabolic_chase_dampener` caps OPEN-NOW → STAGE-ONLY for tickers flagged in `parabolic_setups`). `detect_patterns` extended with optional `held_options`, `drift_rows`, `sleeve_states`, `smid_top5` inputs and emits an honest "not_checked" status when each cache is absent. Tests in `src/test_pattern_engine.py` extended to cover all five (now 42 tests total). Golden drift-free at Task-5/6 boundary (no oracle change; all wave-2 wiring is additive).

## Next action
- Continue to Task 7 (JSX parity port: TODAY—DECIDE into the artifact cockpit; same feed JSON in → same fields out; rails-with-undo + congruence bars per v3_recommendations_cockpit prototype).
- Keep the exact same skip reasons as baseline unless operator changes environment.

## Gates / invariants
- Current branch gate after Task 6 is **1348 passed / 3 failed / 6 skipped** (+19 from Task 6 detector+guard coverage; baseline failures + skip set unchanged).
- ZERO new failures introduced; failures remain subset of documented baseline failures.
- Current failed set:
  - `test_go_live_checklist_cli_runs_against_current_repo`
  - `test_go_live_checklist_cli_text_format_runs_against_current_repo`
  - `test_cloud_routine_manual_run`
- Deviation logged: `test_rendered_cockpit_keeps_operator_status_card` flipped to PASS after regenerated render artifacts.
- Skips must remain exactly 6 (env/platform conditional) with identical reasons.
  - `src/test_broker_pdf_extractor.py`: missing `pypdf` (`could not import 'pypdf'`)
  - `src/test_render_cockpit.py`: pinned renderer not present in this environment (`set COCKPIT_TEMPLATE` to run)
  - `src/test_render_cockpit.py` (5 additional skips): same pinned renderer constraint.
- Golden + parity refreeze occurs only at Task-2 and Task-5/6 boundaries.
- Full `python -m pytest src/ -q` before each commit.

## Recovery rule
- Never reset. Never re-extract zips. Resume from this file.
