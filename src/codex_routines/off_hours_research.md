# Off-Hours Research Queue Routine

## Objective

Process queued research outside market hours and produce structured candidates
that can surface in the cockpit.

This routine is active as a safe intake, normalization, and off-hours research
drafting lane. It does not create trade recommendations. It converts explicit
Research Queue exports into `src/research_queue.json` and, during worker runs,
drafts or updates as many queued dossiers as can be completed with verified
source/write quality before trading hours.

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

## Queue Drain Policy

Normal weeks are throughput-first: drain the Research Queue as quickly as
possible during off-hours, starting with high priority, then medium, then low.
Do not artificially cap work at one or two items when off-hours usage is
available.

Stop or defer remaining items only when:

- Notion/source access blocks live verification.
- The item needs operator input or a source that is not available.
- The draft would require inventing market/source data.
- The run is too close to trading hours to write and verify cleanly.
- The user has declared a temporary usage-constrained week.

When usage is temporarily constrained, handle at least the top one or two
highest-impact queued items and leave an explicit count of what remains.

## Current Status

Active research drafting lane with verified Notion writeback. Autonomous output
is limited to research dossiers, Findings updates, and conservative queue
status notes; trade actions, sizing, and execution remain out of scope.

## Buffer Pass

The active `investing-os-off-hours-worker` begins draining the Research Queue at
1:45 AM ET. A separate conditional buffer routine runs later in the early
morning and continues the backlog if meaningful queued work remains after that
worker has had time to run.

The buffer is not a trickle cap. It should no-op only when no queued items need
safe research work, or when all remaining items are blocked/recently handled. If
queued items remain, it should draft or update as many as can be completed and
verified before the pre-market routines start, using the contract in
`src/codex_routines/off_hours_queue_buffer.md`.
