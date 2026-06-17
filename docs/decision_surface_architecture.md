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
