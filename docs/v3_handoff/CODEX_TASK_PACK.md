# CODEX TASK PACK v1 — finish the V3 build (authored 2026-06-10)

*Authored 2026-06-10 by Claude. Audience: Codex 5.3 working in `ender-lark/enderverse` with full GitHub access. Purpose: finish the V3 decision layer. The judgment-dense design is DONE and encoded in C1–C4 code + the design pages; your job is integration + the spec'd remainder. Follow [AGENTS.md](http://AGENTS.md) conventions: small verified slices, run verify before every commit, never weaken an honesty rail.*

**Ground rules (binding):** (1) Honesty rails are not tunable and not removable — the §3.4 guard in `tunables.py` must pass untouched. (2) Tier-D never scores; UW `inconclusive` = 0; OPEN-NOW requires a named trigger — these invariants have tests; keep them green. (3) Idea inputs enter the Today surface ONLY as cards through the action-implication contract — never new parallel panels, never gate bypass. (4) Additive everywhere: V2 sections, validators, and feeds keep working. (5) Doctrine sources of truth: the **Evidence & Timing Engine design v2** page and the **Build Plan** progress log (both siblings/parents of this page). Read them before Task 2.

# TASK 0 — Kickoff: obtain the C1–C4 code + establish the baseline

Three recovery routes, in preference order:

- **A (preferred):** Claude's container returns → Claude hands you a zip of `/tmp/enderverse/src/` new files. Skip to Task 1.
- **B:** Operator exports the build conversation (2026-06-10). Every file's COMPLETE contents are embedded verbatim in the tool calls (`create_file` bodies and `bash` heredocs). Extract the Task-1 file list exactly as written.
- **C (last resort):** Re-implement from the acceptance tests + contracts in this pack and the design pages. Only if A and B are both impossible.

**Baseline after integration:** `python -m pytest src/ -q` → exactly **1,280 passed, 4 failed**, the 4 being the documented pre-existing state-dependent failures (`test_go_live_checklist` CLI ×2, `test_cockpit_operator_status`, +1). They fail identically on a clean clone; they are NOT yours to fix in this pack.

# TASK 1 — Integrate C1–C4 (file inventory)

Config/state (in `src/`): `goal_tunables.json` (Mandate v1.2, 23 params) · `conviction_weights.json` · `tunables_changelog.jsonl` · `insights.json` (INSIGHT-001/002 seeded) · `timing_gates.json` (QQQ Newton band) · `account_rules.json` (PCRA ETF-only).

Modules + tests: `tunables.py`/`test_tunables.py` (27) · `decision_card.py`/`test_decision_card.py` · `insight_register.py`/`test_insight_register.py` + `congruence.py`/`test_congruence.py` (19) · `conviction_engine.py`/`test_conviction_engine.py` (16) · `timing_engine.py`/`test_timing_engine.py` + `execution_plan.py`/`test_execution_plan.py` + `directive_recs.py`/`test_directive_recs.py` (25).

Register every new state file in `state_ownership_map.json` (additive). Commit as one slice: `v3: integrate C1-C4 decision layer (87 new tests)`.

# TASK 2 — C5: the TODAY—DECIDE surface in `cockpit_html_gen.py`

New FIRST section, all existing V2 sections preserved below unchanged. Data calls: `directive_recs.build_directive_cards(weights, goal, today)` · `congruence.congruence_from_repo(insights, weights)` · `insight_register.active_insights`.

Render order: **(1) Goal anchor** — combined book value → `fi_target` ($3,000,000), % there, pace line strictly DISPLAY-ONLY (add a test asserting the pace string/value appears in no ranking or urgency computation). **(2) Plan line** — funding pool / shortfall / positions-as-of from the brief. **(3) Gate banner** — each `timing_gates.json` gate: state, note, confirm rule. **(4) Ranked cards** (max `daily_card_max`): all five `decision_card` fields; conviction badge w/ per-group points + "what raises it"; window class + named trigger + flips; execution block (suggested account, PCRA exclusions verbatim, transfer/PCRA-trapped flags); **ACT / PASS / RECHECK rails** — buttons copy `ACT <card_id>` / `PASS <card_id> — reason:`  / `RECHECK <card_id> resurface <today+recheck_default_days>` to clipboard, with visible undo (second tap reverts), zero network calls. **(5) Source-conflict chip** — when a card's ticker appears in `lean_in` actions with opposing direction (live case: MAGS lean-in vs full-sell trim), render SOURCE-CONFLICT with both claims. **(6) Congruence strip** — one line per ACTIVE insight + 🚩 flag (live: INSIGHT-002 TSM 0.23%). **(7) Backlog** — collapsed ranked list. **(8) Honesty footer** — merge existing V2 footer + new not_checked: cash, institutional, uw_same_session, dark lanes.

Tests: today-decide section present · card count ≤ tunable · PCRA exclusion rendered on stock buys · conflict chip renders for the MAGS fixture · pace-isolation test · **golden + parity REFROZEN** via the existing freeze-script pattern (regenerate golden, then parity vs the `docs/index.html` build path). Commit per slice.

# TASK 3 — C6: disposition spine

`src/dispositions.jsonl` (append-only: `{ts, et_date, card_id, ticker, verb, reason?, resurface_date?, source:"chat"}`) + `disposition_log.py`: `append_disposition` (verb ∈ ACT/PASS/RECHECK; PASS requires reason; RECHECK default resurface = today + `recheck_default_days`) · `load_open_cards` (cards w/o disposition) · `orphan_escalation` (trading-days-open ≥ `orphan_escalate_days` → escalate; ≥ `orphan_pin_days` → pin; reuse an existing trading-day helper if present, else document weekday approximation) · `map_to_action_memory` (verbs → the existing `action_memory_resolve` statuses — integrate ADDITIVELY, do not rewrite that module) · `lookback_30d` (ACTs scored %-since + %-vs-SPY via the existing add_price machinery; PASSes shadow-tracked the same way). Cards render their last disposition + date. Tests: round-trip, PASS-requires-reason, escalation day math, lookback joins, golden additive.

# TASK 4 — C7: pattern wave 1 (`pattern_engine.py`, pure detectors → cards only)

- **ENDORSED-DIP** (operator pattern): `top_prospects` name whose current price is ≥ `endorsed_dip_pct` below `add_price` within `endorsed_dip_lookback_days`, AND no thesis-break (no bearish `source_calls` row, `source_conflicts` clean) → same-day BUY-review card; conviction from the engine; timing through the normal gates.
- **EXPLICIT-ADD**: fresh Tier-A `source_calls` row → auto Top-5-candidate card (mechanizes the standing rule).
- **DRUMBEAT**: one source × one ticker mention count ≥ `drumbeat_min_mentions` within `drumbeat_window_days` (Tier-D rows COUNT toward the drumbeat but add zero conviction points) → flagged review card.
- **prediction_signals stub**: optional `src/prediction_signals.json` lane — validate-if-present, honest "not checked" when absent (seam for the parallel prediction-markets exploration; pattern slot #11).

Tests: threshold edges, conflict veto, D-counts-no-points, stub honest-empty. Every detector output passes `validate_decision_card`.

# TASK 5 — C8: orphan wiring wave (into the feed build, try/except honest-empty)

- `re_entry_zone_scan` → **MONITOR-RE-ENTRY** cards — the ONLY Action path for MONITOR-sleeve names (BMNR/LEU/UUUU/MP); card must carry defined-risk fields or it does not emit.
- `granny_diff` → **GRNY-DELTA** evidence items: Lee's actual ETF adds/removes → fs-group near-Tier-A items (tier A, dated the diff) for adds of non-held names; context rows otherwise.
- `13f_best_ideas` + `insider_activity_scan` → an `inst_state` adapter for `conviction_engine` (points for manager-overlap / insider buys, cap 1.0) — the institutional group goes from honest stub to live.

Validators additive; absent source caches render "not checked"; refreeze golden ONCE at the end of this task.

# TASK 6 — C9: pattern wave 2 + guards

**STALE-LEAPS** (held options DTE < `stale_leaps_warn_dte` vs thesis window → roll/close review; logic per `options_roll_decision_matrix.md`) · **FACTOR-OVERLAP guard** (`portfolio_factor_exposure` ≥ `factor_overlap_warn_pct` → sizing caveat ON the existing buy card — a field, never a new card) · **OVEREXPOSURE-ROTATION** (scoped: target_drift OVERSIZED + sleeve TURNING DOWN, or an explicit Tier-A/B FS sector call → trim review) · **PARABOLIC-CHASE** (parabolic cache flag → timing dampener: class capped at STAGE-ONLY with reason) · **Tier-B side-plays**: FS SMID Top-5 + prospects with conviction BUILDING enter the ranked backlog with sleeve-base materiality.

# TASK 7 — JSX parity port

Port TODAY—DECIDE into the artifact cockpit (v6) for in-chat rendering: same feed JSON in → same fields out (write the parity test). Interaction pattern (rails w/ undo, congruence bars) per the v3_recommendations_cockpit prototype in the build conversation.

# TASK 8 — Routines, registration, docs

Add new state files written by routines (`dispositions.jsonl`, `timing_gates.json` state updates) to the cloud commit allowlist. Extend the **9:40 ET Post-Open Evidence Gate** routine: for each gate call `timing_engine.evaluate_gate(gate, live_price)` → propose + stamp state changes (the QQQ confirm/re-red flow). Morning Scan consumes `pattern_engine` outputs. Update `ARCHITECTURE.md` + `AGENTS.md` with additive V3 sections.

# DONE CRITERIA (whole pack)

Full suite green except the 4 documented pre-existing · golden+parity refrozen exactly at Task-2 and Task-5/6 boundaries · §3.4 guard + doctrine-lock tests untouched and green · every card path passes `validate_decision_card` · OPEN-NOW-needs-trigger invariant green · pace-isolation test green · commit per slice with verify before each, push at the end · final note in the repo: file-level changelog for the operator.

[src/today_[decide.py](http://decide.py) (C5 exact fragment)](src%20today_decide%20py%20(C5%20exact%20fragment)%2037bc50314bb6813e9a55c1faaa375e01.md)

[src/test_today_[decide.py](http://decide.py) (C5 exact fragment)](src%20test_today_decide%20py%20(C5%20exact%20fragment)%2037bc50314bb681c287fce8d72c9fc541.md)

[TodayDecide.jsx fragment + wiring notes + Task-3 UNDO addendum](TodayDecide%20jsx%20fragment%20+%20wiring%20notes%20+%20Task-3%20U%2037bc50314bb6818ca524c550fe84b8dd.md)

---

**📎 ADDENDUM (2026-06-10): Task 2 & Task 7 are now PASTE-AND-WIRE.** Three child pages below this one carry exact fragments written against the verbatim Recovery-Archive modules: `src/today_decide.py` (payload builder + scoped HTML renderer, pace-isolated by construction), `src/test_today_decide.py` (10 tests covering every Task-2 required test), and the `TodayDecide.jsx` parity component + wiring notes. Task 2 reduces to: drop in the two src files, insert `today_decide.build_and_render(...)` as the FIRST section of `cockpit_html_gen.py`, refreeze golden+parity once. **Task 3 contract addition (binding):** rails emit `UNDO <card_id>` on second tap — `append_disposition` must accept verb UNDO (append-only void row, no reason required); a card whose latest row is UNDO counts as open/no-disposition.