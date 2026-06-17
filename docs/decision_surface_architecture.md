# Decision Surface Architecture

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
