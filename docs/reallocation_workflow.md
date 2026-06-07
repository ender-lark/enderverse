# Portfolio Reallocation Workflow

Last updated: 2026-06-07.

## Purpose

Turn latest account positions plus current source evidence into a candidate-only
portfolio plan: trim, add, hold, hedge, research, or re-check. The workflow should
optimize for early-retirement impact, time sensitivity, conviction, sizing, leverage,
risk, efficient capital use, and user attention.

No trade execution is added. The output is a review plan.

## Inputs

Required:

- Latest account positions and account-level market values.
- Current `positions.json` / `account_positions.json` snapshot and freshness.
- Target model from `reallocate_config.py`.
- Current price state for material holdings and target candidates.
- Fundstrat latest full-body-derived calls with dates and authors.
- UW scenario-routed evidence from `src/uw_endpoint_router.py`.
- Current dashboard actions, target drift, bullish flow, source calls, event risk,
  catalysts, and open action memory.

Helpful:

- Account/tax constraints from the user.
- Whether options/defined-risk hedges are allowed.
- Maximum number of actions the user can review.
- Whether BMNR/crypto exposure is strategic, tactical, or undecided.

## Workflow

1. Validate position freshness.
   - If latest positions are missing, keep Account Positions dark and do not produce
     a final reallocation plan.
   - If positions are supplied, reconcile account-level and aggregate book values.

2. Build current exposure map.
   - Direct ticker weights.
   - ETF/wrapper look-through where available.
   - AI/semis/software/crypto/rates/oil/event-risk factor exposure.
   - Drawdown and recent move context.

3. Build thesis and source map.
   - Fundstrat stance and dates.
   - Thesis state from repo/Notion.
   - Source-call calibration where available.
   - Catalyst timing and event-risk flags.
   - Meridian only as archived thesis context, never fresh tactical proof.

4. Route UW evidence by scenario.
   - Crash triage if broad tape is unstable.
   - Fundstrat confirmation for time-sensitive FS calls.
   - Portfolio reallocation for planned leg ranking.
   - Asymmetric discovery for new candidates.
   - Reddit escalation vetting only if a social anomaly exists.

5. Score candidate legs.
   - Impact: expected contribution to early-retirement objective.
   - Capital efficiency: whether this is the best current use of scarce capital,
     not merely whether the individual opportunity is good.
   - Risk: downside, concentration, leverage, factor crowding, gap risk.
   - Time sensitivity: decay speed, catalyst timing, market regime.
   - Conviction: thesis quality, source agreement, source-call history.
   - Sizing gap: distance from target after look-through.
   - Entry quality: live price/flow/vol/dealer context.
   - Disconfirmation: strongest evidence against the action.

6. Build funded plan.
   - Prefer factor-flat rotations where possible.
   - Identify funding source for each add.
   - Separate fully funded from partially funded actions.
   - Avoid increasing the same factor through both wrapper and single-name exposure
     without an explicit risk label.

7. Sequence actions.
   - `Act Now`: fresh evidence, high impact, clear trigger, acceptable risk.
   - `Stage`: good thesis but timing/entry still needs a level or confirmation.
     Use staging to avoid both extremes: parking capital in a lower-ranked idea
     and waiting so long for a perfect entry that a major up move is missed.
   - `Re-check`: evidence is stale, contradictory, or fast-moving.
   - `Hold`: existing sizing is acceptable.
   - `Trim`: thesis weakened, risk too high, or better funding use exists.
   - `Research`: potentially asymmetric but not yet decision-grade.

8. Render operator output.
   - Top actions first, but include the full important backlog.
   - For every action: what, why, ticker/account, notional or percent, source dates,
     decay speed, disconfirmation, trigger, and what happens if the user does
     nothing.
   - Keep all stale or missing lanes visible.

## Test-Data Run

Before the user supplies current positions, use current repo positions only as test
data:

- Do not present the result as the final plan.
- Use it to validate planner mechanics, dashboard formatting, and source routing.
- Clearly label any output as `test-data only`.

## Dashboard Brief

`src/reallocation_brief.py` wraps the existing funded-rotation planner into a
dashboard feed block called `reallocation_brief`. It shows candidate adds, funding
trims, funding summary, blockers, disconfirmation, and the UW portfolio-reallocation
checks from the current action runbook.

The brief is not the final reallocation plan. If the position snapshot is not the
same operating day as the dashboard build, it is labeled `test_data_only` and every
add candidate carries a current-position blocker. Old planner sequencing dates are
also blocked explicitly, so a stale catalyst label such as `after 2026-06-03` cannot
read as current timing guidance.

### 2026-06-07 Sanity Pass

Repo snapshot used:

- `src/positions.json`
- `snapshot_date`: 2026-05-31
- `sleeve_value`: $1,909,537

Result:

- 15 candidate legs: 9 adds, 6 trims.
- Funding pool: $679,812.
- Allocated: $679,812.
- Funding shortfall: $69,635.
- Warnings:
  - No run-up data supplied, so chase-gate timing is inactive.
  - Entries must be verified live before acting.
  - Not every target gap can be funded from the convertible pool while keeping the
    rotation AI-flat.

Top test-data adds:

- GOOGL: $152,763, sequence now, AMBER.
- NVDA: $83,974, sequence after 2026-06-03, AMBER.
- MSFT: $95,477, sequence now, AMBER.
- AMZN: $76,381, sequence now, AMBER.
- AVGO: $106,934, sequence after 2026-06-03, AMBER.
- TSM: $65,879, sequence after 2026-06-03, AMBER.
- ANET: $57,286, sequence now, AMBER.
- FN: $38,191, sequence now, AMBER.

Top test-data trims:

- MAGS: $172,152, funding GOOGL/NVDA.
- GRNJ: $139,887, funding AVGO/TSM.
- GRNY: $110,367, funding TSM/ANET/FN/VRT.
- IGV: $98,106, funding NVDA/MSFT.
- SMH: $84,812, funding MSFT/AMZN.
- IVES: $74,487, funding AMZN/AVGO.

Important caveat: this was a mechanics test only. It is stale for Monday planning
because the snapshot predates the Friday AI/crypto drawdown and uses no current
run-up, live price, UW, Fundstrat-confirmation, tax/account, or hedge constraints.

## Monday Readiness Checklist

- Latest positions loaded and reconciled.
- Fundstrat latest full-body calls ingested and date-labeled.
- UW crash-triage and Fundstrat-confirmation profiles available.
- Event-risk watch checked for rates/oil/policy/geopolitical shocks.
- Stale action cleanup run.
- Dashboard shows Key Now, Important Backlog, Re-check Before Acting, Quiet Watch,
  Asymmetric Opportunities, and source/audit proof.
- Final reallocation plan remains candidate-only until the user approves any action.
