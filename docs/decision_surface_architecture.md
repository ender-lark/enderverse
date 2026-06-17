# Decision Surface Architecture

## 2026-06-17 - Canonical Primary Goals

Investing OS system and dashboard work now uses
`docs/investing_os_primary_goals.md` as the first-read doctrine. The primary
failure mode is passivity: right ideas under-sized, good setups rotting in
queues, acting too slowly, or system-detected signals never reaching the
operator. The dashboard must decide and direct, not merely display. Strength
gets loud, weakness stays quiet, risk remains visible, and no UI change may
manufacture urgency or loosen discipline.

The next decision-surface phase is documented in
`docs/decision_surface_consolidation_plan_2026_06_17.md`: consolidate stacked
panels into one command surface, use `ACT` / `DECIDE` / `RESOLVE` / `WATCH`
states, and show a data-readiness ladder so routine proof never masquerades as
fresh interpreted decision evidence.

## 2026-06-17 - TODAY/DECIDE Action-First Readability

TODAY/DECIDE remains display-only: ranking, scoring, sizing, gates, dispositions,
and trade behavior are unchanged. The renderer now annotates cards with stable
display keys based on `(ticker, lane)` and adds first-viewport fields that make
the primary capital/risk decision, tranche, blocker, change state, risk rail,
and safe-wait bucket visible before routine plumbing.

Ownership-aware passivity is explicit:

- `operator_owned_actionable_now` is the only bucket that counts as operator
  latency and may show an open-days label.
- Market/tape gates, source/data freshness, research/watch-only state,
  cap/risk/cash constraints, and system/not_checked blockers are reported as
  waiting on rails or the world, not as operator delay.

The copy must not manufacture urgency. Banned latency language includes
`act now`, `don't miss`, `or lose`, `hurry`, and `last chance`.

## 2026-06-17 - Safe Change Delta

The first viewport's `Changed` cell is fed by `change_delta`, a render-only
comparison against the committed `src/latest_cockpit_feed.json` at `HEAD`. It
does not create or track `dashboard_view_state.json`, and it is labeled
`since last committed build` so the UI does not overclaim a per-user lookback.

The delta compares display identities only: new decision keys `(ticker,lane)`,
new watch names, gate state flips, and data-health lanes that moved into
stale/dark statuses. The value is not imported by scoring, ranking, timing
gates, sizing, or dispositions.

## 2026-06-17 - Blocker Taxonomy

`blocker_taxonomy` is attached to each card as display metadata. It maps visible
unmet blockers into the real categories the operator can act on or wait for:
price/tape gates, source freshness, flow/evidence conflicts, cap room,
cash/funding, concentration/leverage rails, account/sleeve eligibility, and
research/disconfirmation gaps.

The UI only renders `0 of N blockers cleared` when `N` is the count of visible
unmet categories in `blocker_taxonomy.unmet`. If a blocker is visible but not
cleanly enumerable, the renderer shows the blocker text without an M-of-N
count. The count is never a readiness score.

## 2026-06-17 - Size To Goal With Rails

Buy/add cards get `size_to_goal` display metadata. The line may show the
tranche as a percentage of the FI goal gap, but only in the same sentence as
the survival rails: cap room, funding or cash source, concentration rail,
account eligibility, and leverage/margin assumption. Goal-gap percentage alone
is forbidden because it can make an oversized or unfunded trade look more
actionable than it is.

## 2026-06-17 - Disposition Coverage And After-Action Loop

`disposition_coverage` counts visible non-card candidate rows that do not have
ACT/PASS/RECHECK rails. Uncovered feed action rows can be marked
`could_promote_to_today_decide`; watch queues, Social Watch, prospects, and
research-only rows stay `intentionally_watch_research_only` and are not
promoted by the renderer.

Each card also gets `after_action`, a display-only read of the latest
disposition row. It shows the last verb/date, age, next review date when one is
known, and whether the card is still open. This does not change disposition
semantics; it only makes prior action state visible to the returning operator.
