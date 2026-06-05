# Off-Hours Research Queue Routine

## Objective

Process queued research outside market hours and produce structured candidates
that can surface in the cockpit.

This routine should stay paused until the Research Queue reader/writer is fully
repo-owned.

## Inputs

- Research Queue rows from Notion or exported JSON.
- Fundstrat source-call candidates.
- Top Prospects cache.
- Existing theses and positions.

## Expected Outputs

- Updated `research_queue.json` or Notion Research Queue rows.
- Candidate dossiers with:
  - ticker
  - thesis
  - catalyst
  - time window
  - missing evidence
  - proposed action state: `ACT_NOW`, `WATCH`, `RESEARCH`, or `MONITOR`

## Rules

- Do not create buy/sell actions from research alone unless the dossier has a
  clear source, catalyst, and action reason.
- MONITOR names stay gated unless a named re-entry condition is present.
- Every promoted candidate must answer:
  - What opportunity or risk does this reveal?
  - Is there a clear action?
  - Is it time-sensitive?
  - Does it affect sizing, conviction, leverage, or risk?
  - What evidence is still missing?

## Current Status

Definition only. Do not activate as a recurring automation until the repo has a
safe Research Queue intake/update runner.
