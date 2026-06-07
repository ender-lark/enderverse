# Portfolio Reallocation Workflow

Last updated: 2026-06-07.

## Purpose

Turn latest account positions plus current source evidence into a candidate-only
portfolio plan: trim, add, hold, hedge, research, or re-check. The workflow should
optimize for early-retirement impact, time sensitivity, conviction, sizing, leverage,
risk, and user attention.

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

## Monday Readiness Checklist

- Latest positions loaded and reconciled.
- Fundstrat latest full-body calls ingested and date-labeled.
- UW crash-triage and Fundstrat-confirmation profiles available.
- Event-risk watch checked for rates/oil/policy/geopolitical shocks.
- Stale action cleanup run.
- Dashboard shows Key Now, Important Backlog, Re-check Before Acting, Quiet Watch,
  Asymmetric Opportunities, and source/audit proof.
- Final reallocation plan remains candidate-only until the user approves any action.
