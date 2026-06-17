# TODAY/DECIDE Action-Forcing Handoff - 2026-06-17

This is the implementation handoff for making TODAY/DECIDE action-forcing under
the canonical Investing OS doctrine. It is written so Codex or Claude Code can
continue after chat compaction without losing the exact guardrails, current
branch state, or slice order.

## Canonical Doctrine

Read `docs/investing_os_primary_goals.md` before changing the system.

The doctrine is not "make the dashboard look bullish." It is:

- Fight passivity, not by faking urgency, but by surfacing the strongest real,
  high-conviction, well-timed, right-sized opportunity before it rots.
- Decide and direct, not merely display data.
- Sizing is part of direction. Under-sizing a real converging opportunity is a
  failure.
- Synthesis must be honestly weighted. Independent confirmation builds
  conviction; correlated echoes count once; conflicts must be shown with what
  would settle them.
- Strength loud, weakness quiet, risk always visible.
- No build-and-forget: if a detector matters, it must surface in daily flow and
  outcomes must feed back.

Every change must pass this test: does it make a real, high-conviction,
well-timed, right-sized opportunity more likely to reach the operator, clearly
recommended, shown like a decision, one tap from action or one tap from the
question the system needs answered, and get acted on before the window closes,
without faking urgency or quietly loosening discipline?

## Current Git State

Canonical repo:

`C:\Users\suraj\Documents\Codex\2026-06-04\confirm-you-can-access-my-github\work\enderverse-held-decisions-strip`

Landed on `origin/main`:

- `9a26075 Allow heartbeat automations in prompt audit`
  - Fixed a verifier false positive: thread heartbeat automations are monitored
    but do not get cron/workspace safety requirements that they cannot carry.
  - Verified with `python src/verify_standard.py`.
- `0a480ed Document Investing OS primary goals and decision plan`
  - Added `docs/investing_os_primary_goals.md`.
  - Added `docs/decision_surface_consolidation_plan_2026_06_17.md`.
  - Updated `AGENTS.md`.
  - Updated `docs/decision_surface_architecture.md`.
  - Verified with `python src/verify_standard.py`.

Current implementation branch:

`codex/today-decide-command-state-slice1-20260617`

Current uncommitted state:

- `src/today_decide.py` has partial Slice 1 edits. They are not complete and
  have not been verified.
- `docs/WORKBOARD.md` has unrelated pre-existing dirty DEFERRED rows. Do not
  stage or revert it unless the operator explicitly asks.

Partial Slice 1 code already added in `src/today_decide.py`:

- `COMMAND_STATES = ("ACT", "DECIDE", "RESOLVE", "WATCH")`
- render-only command-state metadata and copy
- `_has_named_resolve_blocker`
- `_card_command_state`
- `_annotate_command_states`
- `_command_action_label`
- `_primary_command_title`
- `_primary_leverage_score`
- revised `_primary_capital_decision`
- `_source_decide_prompts`
- `_build_command_strip`
- `_command_button_for_state`
- `_primary_button_model` now blocks non-ACT command states from emitting ACT

Still incomplete:

- command states are not yet called from `build_today_decide_payload`
- `command_strip` is not yet added to the payload
- HTML and JSX renderers do not yet render the command strip
- first viewport does not yet use `_primary_command_title`
- regular card rails still need to be tied to `command_state`
- tests have not been added or updated
- standard verification has not run after the partial edits

## What Claude's Plan Gets Right

- The next phase is subtraction and consolidation, not another stack of panels.
- Every candidate must resolve to one mutually exclusive state:
  `ACT`, `DECIDE`, `RESOLVE`, or `WATCH`.
- Blocked cards must never render ACT-shaped controls.
- The trust/status layer must distinguish routine fired from boundary artifact
  freshness and interpreted decision evidence.
- WATCH/research rows should remain quiet unless they become high-impact,
  timely, and decision-relevant.
- Both renderers must stay in lockstep.

## Codex Corrections To Preserve

Do not implement Claude's plan as hardcoded UI text.

Required corrections:

1. Counts must be computed from live payload state, not hardcoded examples like
   `0 ACT - 4 DECIDE - 6 RESOLVE - 14 WATCH`.
2. Any new command, readiness, or delta artifact is render-only. It must not
   feed scoring, sizing, gates, ranking, trade eligibility, or dispositions.
3. `DECIDE` is not executable. It means operator yes/no/recheck is needed.
4. `ACT` requires all render-visible survival rails clear. If there is an
   unmet blocker, stale/uninterpreted proof, cap room issue, cash/funding issue,
   account eligibility issue, event-risk block, or research/disconfirmation gap,
   it is not ACT.
5. WATCH promotion is not Slice 1. It belongs in Slice 3 with a narrow, honest
   threshold. Do not visually promote thin research rows into trade-like cards.
6. Both HTML and JSX should consume shared payload fields rather than recompute
   different command-state logic in separate renderers.
7. Key by `ticker|lane`, not card id, date, rank, or UI position.
8. Funding-only legs attach to the buy/add they fund. They should not outrank a
   real capital decision as standalone sells.
9. No automation stream changes in this dashboard UI work. Avoid
   `src/full_build_runner.py` and `src/cloud_routine_commit.py` unless the
   operator explicitly expands scope.
10. Do not commit generated dashboard/feed artifacts from manual local rebuilds
    unless a slice explicitly owns those artifacts.

## Global Guardrails

Hard constraints for every slice:

- Display-only unless explicitly stated otherwise.
- No scoring changes.
- No sizing model changes.
- No gate logic changes.
- No trade execution changes.
- Do not auto-promote UW `neutral` or `inconclusive` to `supports`.
- Do not lower the source-scoring threshold.
- Do not backfill fake graded source outcomes.
- Missing, stale, blocked, optional, watch-only, or unsupported lanes remain
  visible as dark/not_checked/stale, not smoothed green.
- No manufactured urgency words: avoid phrases such as `act now`, `don't miss`,
  `or lose`, `hurry`, `last chance`.
- Mobile and desktop must fit; no text overlap.
- Both renderers in lockstep.
- `python src/verify_standard.py` green before each commit.

## Slice 1 - Command Strip And Primary Slot Correction

Goal:

Make the first viewport honestly action-forcing without making a blocked trade
look executable.

Target behavior:

- Top command strip renders from shared payload:
  - `ACT`: executable now, all survival rails clear.
  - `DECIDE`: real operator yes/no/recheck needed, not executable.
  - `RESOLVE`: important but blocked by named gap.
  - `WATCH`: weak, early, context-only, research-only.
- Command strip includes:
  - live counts
  - goal/doctrine anchor
  - honest system state: `confident` if an ACT exists, `starved` if none
  - caveat from trust/readiness if the system is starved or data is blocked
- Primary slot uses the highest-leverage real command:
  - state priority: ACT > DECIDE > RESOLVE > WATCH
  - within state: prefer non-funding, material, larger dollar/leverage impact
  - a system-level unblock can be primary once represented as a command item,
    but Slice 1 can start with card/action-derived commands only
- Blocked `TRIM GRNY` or equivalent must read like:
  - `Resolve GRNY trim`
  - button `RESOLVE` or `RECHECK`
  - never `ACT`, never action-shaped trade execution
- Existing regular cards also must not show ACT controls when command_state is
  not ACT.

Implementation steps:

1. Finish Python payload model.
   - Call `_annotate_command_states(all_cards)` after
     `_annotate_blocker_taxonomy(all_cards)`.
   - Build `trust_panel = _build_trust_panel(data_health)` once.
   - Build `command_strip = _build_command_strip(feed, all_cards, watch_queue,
     trust_panel)`.
   - Add `command_strip` to the returned payload.
   - Return `trust_panel` using the local variable, not a second recomputation.
2. Fix first viewport.
   - Add `command_state` and `command_state_detail` to the first viewport model.
   - Use `_primary_command_title(card, state)` for the visible title.
   - Keep size/tranche, blocker, changed, risk rail, and can-wait cells.
   - Button comes from `_primary_button_model`, which must never return ACT for
     non-ACT states.
3. Fix normal card rails.
   - In `_render_card`, if `card["command_state"] != "ACT"`, override the
     primary rail with `_command_button_for_state` instead of local posture.
   - Preserve PASS and RECHECK rails, but the primary button must not look like
     executable action unless state is ACT.
4. Add HTML renderer support.
   - Add `_render_command_strip(payload)`.
   - Render it above `_render_first_viewport(payload)`.
   - Keep compact/mobile stable dimensions.
5. Add JSX renderer support.
   - Add `CommandStrip({ payload })`.
   - Render it above `FirstViewport`.
   - FirstViewport consumes shared payload fields only.
   - Do not reimplement command-state logic in JSX.
6. Update tests.
   - `test_today_decide.py`: payload includes `command_strip`; primary title for
     blocked sample is `Resolve ...` or non-ACT command title.
   - `test_today_decide_ux_guardrails.py`:
     - command counts are present and computed
     - blocked cards have `command_state == "RESOLVE"`
     - no card with unmet `blocker_taxonomy` emits `data-copy="ACT ..."`
     - command_state and command_strip are absent from engine/scoring/gate files
     - no banned urgency words
     - decision keys remain `ticker|lane`
7. Verify.
   - `python -m pytest src/test_today_decide.py src/test_today_decide_ux_guardrails.py -q`
   - `python src/verify_standard.py --include-js`
   - If visual QA is needed, run local dashboard refresh, inspect desktop/mobile,
     and do not commit generated feed/HTML artifacts unless explicitly scoped.
8. Commit and push Slice 1.
   - Stage only code/tests/docs for this slice.
   - Do not stage `docs/WORKBOARD.md` unrelated edits.

## Slice 2 - Readiness Layers And RESOLVE Checklist

Goal:

Replace false-green routine proof with boundary-data honesty.

Target behavior:

Each relevant lane/card displays a readiness ladder:

1. routine fired
2. boundary artifact fresh
3. signal interpreted
4. decision eligible
5. trade executable

Rules:

- `scheduled proof 14/14` can appear only as routine-fired proof, never as
  proof that fresh interpreted data landed.
- An item cannot be ACT unless it climbs all five layers.
- Top item gets a compact checklist row:
  - UW interpreted
  - cash/buying-power
  - account eligibility
  - cap room
  - research/disconfirmation
  - event-risk
- Green/red/unknown row, not prose.
- Unknown stays unknown/dark.

Implementation notes:

- Source freshness from actual artifacts and current payload fields, not receipt
  summaries alone.
- UW neutral/inconclusive remains not-supportive until an explicit interpreter
  says supports or contradicts.
- Source scoring remains off until real graded outcomes meet threshold.

Verification:

- Tests proving routine-fired without fresh artifact is not executable.
- Tests proving `ACT` requires all readiness layers clear.
- Tests proving stale/not_checked remains visible.

## Slice 3 - Force Dispositions On Real Decisions And Promote Overdue Held

Goal:

Turn high-impact timely prompts into explicit yes/no/recheck decisions without
turning weak research into fake urgency.

Target behavior:

- High-impact, converging-evidence WATCH items can move into DECIDE, never ACT,
  when threshold is met.
- Example prompts:
  - `Size MAGS now / pass / recheck after gate`
  - `Avoid new RYF exposure? yes/no/recheck`
- Overdue `Held for you` items enter a labeled review-due sublane just below
  fresh items, not below utility panels.
- Thin/early items remain WATCH.

Required before coding:

- Define the promotion threshold in docs/tests first:
  - impact score
  - honestly weighted conviction
  - freshness window
  - independence/correlation handling
- Decide how review-due items key into `ticker|lane` when they are not ticker
  specific.

Verification:

- WATCH promotion is narrow and test-covered.
- Research-only rows do not become capital actions.
- Overdue held items appear above utility/status panels.

## Slice 4 - Collapse Stacked Dashboards Into Feeders

Goal:

Make the page shorter and reduce duplicate decision cost.

Target behavior:

- One merged command list, one row per `ticker|lane`.
- Current panels become feeders or drill-down evidence:
  - sleeve rotation
  - macro lean-in watchlist
  - asymmetric opportunities
  - UW runbook
  - reallocation brief
  - opportunity context
  - today's actions
  - watch queue
- Funding legs attach under the buy/add they fund.
- Source conflicts render on the candidate with what would settle them.
- Correlated echoes count once.

Implementation notes:

- Build a unified candidate view-model before deleting panels.
- Keep old panels behind drill-downs during transition if needed, then remove
  redundant visual sections once parity is proven.

Verification:

- One merged row per `ticker|lane`.
- No duplicate top-level rows for same name/lane.
- Independent vs correlated source counting is explicit and tested.
- Page is materially shorter in first-pass visual inspection.

## Slice 5 - Close The Loop

Goal:

No build-and-forget. Every surfaced decision can feed outcome logging.

Target behavior:

- Each ACT/PASS/RECHECK/SIZE/KEEP-WATCH disposition records or queues an
  after-action outcome path.
- Each open item shows:
  - last disposition
  - age
  - next review
  - still-open status
- Outcomes feed source grading when real outcomes close.
- Source scoring still stays off until the real threshold is met.

Implementation notes:

- Do not fabricate outcomes.
- Do not create fake Win/Loss rows to turn scoring on.
- First source-scoring window expected to remain insufficient until real closed
  outcomes accumulate.

Verification:

- Disposition write/readback tests.
- Outcome logging tests.
- Source scoring threshold unchanged.

## Suggested Claude Code Prompt

Use this exact framing if handing off:

```
Continue in the canonical Investing OS repo:
C:\Users\suraj\Documents\Codex\2026-06-04\confirm-you-can-access-my-github\work\enderverse-held-decisions-strip

Read first:
- AGENTS.md
- docs/investing_os_primary_goals.md
- docs/decision_surface_consolidation_plan_2026_06_17.md
- docs/today_decide_action_forcing_handoff_2026_06_17.md

Current branch:
codex/today-decide-command-state-slice1-20260617

Do Slice 1 only. Finish the render-only command state model and command strip,
make blocked primary cards render as RESOLVE/RECHECK rather than ACT, keep HTML
and JSX in lockstep, add tests, and run:

python -m pytest src/test_today_decide.py src/test_today_decide_ux_guardrails.py -q
python src/verify_standard.py --include-js

Hard guardrails:
- display-only
- no scoring/sizing/gate/trade changes
- no UW neutral -> supports promotion
- no source-scoring threshold changes
- no fake graded outcomes
- no generated feed/HTML commits
- do not stage unrelated docs/WORKBOARD.md edits
- ACT only when all visible survival rails are clear
- both renderers consume shared payload fields, not separate logic
```
