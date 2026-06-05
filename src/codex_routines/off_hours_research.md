# Off-Hours Research Queue Routine

## Objective

Process queued research outside market hours and produce structured candidates
that can surface in the cockpit.

This routine is active as a safe intake/normalization lane. It does not perform
autonomous research or create trade recommendations. It only converts explicit
Research Queue exports into `src/research_queue.json`, which the existing engine
can then surface as From-Research rows or ACT_NOW research reviews.

## Inputs

- Research Queue rows from Notion or exported JSON.
- Optional CSV exports of the same queue.
- Fundstrat source-call candidates.
- Top Prospects cache.
- Existing theses and positions.

## Expected Outputs

- Updated `src/research_queue.json` when queue rows were actually supplied.
- Candidate dossiers with:
  - ticker
  - thesis
  - catalyst
  - time window
  - missing evidence
  - proposed action state: `ACT_NOW`, `WATCH`, `RESEARCH`, or `MONITOR`

## Rules

- If no Research Queue export/input is available, do not overwrite
  `src/research_queue.json`; report Research Queue as not checked.
- Run `python src/research_queue_intake.py <export.json|export.csv> --out src/research_queue.json --merge-existing`.
- Validate with `python src/research_queue_intake.py --validate src/research_queue.json`.
- The intake runner may preserve explicit `ACT_NOW` / urgent labels from the
  queue, but it must not invent them.
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

Active safe-intake routine. Full autonomous off-hours research generation remains
out of scope until there is a separate reviewed research writer and Notion update
contract.
