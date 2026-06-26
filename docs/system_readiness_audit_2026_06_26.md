# System Readiness Audit - 2026-06-26

Purpose: verify the automation/runtime/trade-plan system before the planned June 27 morning trade-plan pass. June 27, 2026 is a Saturday, so this supports a weekend trade plan and prep list; any executable trade sizing still needs a same-session market check before orders.

## Current State

- Local go-live readiness is green with warnings: `Ready: True`, zero hard failures, and the dashboard preview running at `http://127.0.0.1:8765/dashboard_preview.html`.
- Live status is `live_with_build_queue`: publish-ready, live-data-ready, 12 actions, 7 research actions, and 1 open review.
- Dashboard/feed artifacts were rebuilt at `2026-06-26T04:48:31.647804+00:00`; data flow is `portfolio 06-26`, `uw_price 06-26`, `uw_macro 06-26`, `fundstrat_bible 06-11`, and `fundstrat_daily 06-25`.
- Source-call calibration is clean: no calls past window-end awaiting a score.
- Broker positions were refreshed from SnapTrade for `2026-06-26`; current-position reallocation now uses the fresh broker snapshot rather than stale PDF-era assumptions.
- Push alerts are quiet for market/action items. The only alert-policy warning is an Ops/system-health warning for one old failed cloud receipt.

## Repairs Applied

- Scored three overdue Newton-family source calls as `Loss` after checking the target windows against live market data:
  - EWY downside call dated 2026-06-10, window ending 2026-06-24.
  - QQQ downside/support call dated 2026-06-10, window ending 2026-06-24.
  - QQQ/SPX conditional constructive call dated 2026-06-11, window ending 2026-06-25.
- Regenerated `src/source_rates.json`; the source-call scoring lag is now zero.
- Refreshed the dashboard, daily pullback packet, synthesis artifact, heartbeat, latest feed, and JSX/HTML render outputs.
- Recovered the stale alert feed count so it reports one failed latest receipt instead of the pre-recovery two.
- Updated the Today/Decide trust-panel smoke test to accept either the old no-scoring state or the current partial-scoring state.

## Remaining Honest Gaps

- `Investing OS Daily Synthesis` still has the latest scheduled receipt marked failed from 2026-06-25. The underlying blocker was the standard verification regression, which now passes; the natural scheduled rerun should clear the cloud proof.
- Cloud operating state remains `run_failed` because of that old Daily Synthesis receipt and stale/not-checked background boundary lanes. Local go-live readiness remains separate and green.
- `Life OS Weekly Review` has no scheduled success receipt yet.
- `Social Watch` remains a deferred optional dark lane. Missing social input is not evidence of no social anomalies.
- Boundary lanes still show stale/not-checked status for pre-market source intake, Fundstrat safety/daytime/after-hours intake, morning scan, positions-sync proof, and post-open evidence.
- `MSFT` has one open review due; oldest age is 3 trading days.
- Trigger checks have no fired triggers, but four quote-dependent triggers are not checked: EWRE weekly close above 38, ASTS reentry 65-70, RKLB reentry 85-90, and MU parabolic acceleration.
- SnapTrade refresh surfaced two stated-balance warnings. No share-change mismatch was reported, but these account-level balance differences should stay visible.

## Tomorrow Morning Trade-Plan Sequence

1. Re-check active event risk first: Middle East oil/rates shock, Iran/Hormuz escalation, and Fundstrat mixed peace-flow risk.
2. Gate the HOOD sell-fast review: confirm whether it is held, then decide trim/exit or log the explicit override.
3. Review current-position reallocation candidates from the 2026-06-26 SnapTrade snapshot; run same-session UW/price, account, and tax gates before acting.
4. Resolve or explicitly defer the MSFT lean-in review.
5. Run the UW check sets for pre-market crash triage, event-risk/political macro, Fundstrat signal confirmation, and asymmetric discovery.
6. Keep Social Watch, quote triggers, and stale boundary lanes visible as not checked.

## Verification

- Focused Today/Decide trust-panel test: passed.
- Standard verification: passed with `1869 passed, 6 skipped`.
- Go-live checklist: `WARN`, `Ready: True`, `failures: 0`, `warnings: 3`.
- Live status: `live_with_build_queue`, `Ready: True`, `publish: True`, `live data: True`.
- Cloud ops status: schedule ready, core scheduled success `14/14`, failed latest `1`, overdue `0`.
- Trigger check: fired `0`, not checked `4`, armed `4`, expired `0`.
- Alert policy: quiet for market/action push alerts.
