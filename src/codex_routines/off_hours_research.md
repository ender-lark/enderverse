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

- Research Queue rows from Notion (data source
  `cab89576-0933-40b0-ad2e-6f9a6188e804`), pulled Notion-first.
- Exported JSON/CSV of the same queue, used as a fallback when Notion is
  unreachable.
- Fundstrat source-call candidates.
- Top Prospects cache.
- Existing theses and positions (`src/positions.json`, `src/theses.json`,
  `src/trigger_registry.json`) as the freshness source of truth for triage.

## Feed: Notion-first with export fallback

The Research Queue feed is Notion-first, then export file, then not-checked:

1. **Notion-first.** Pull the Research Queue data source through the Notion MCP
   and hand the rows to the intake in Notion mode:
   `python src/research_queue_intake.py --from-notion --notion-export <pull.json> --out src/research_queue.json --merge-existing`.
   This maps Notion `Topic/Ticker/Priority/Status/Reason/Findings` into the
   normalized schema, routes `Killed`/`Refiled` rows out of `pending` into a
   `killed` bucket (never silently dropped), and stamps
   `source: research_queue_intake:notion` plus the `data_source_id`.
2. **Export fallback.** If Notion is unavailable, fall back to an exported
   JSON/CSV of the same queue (positional input), which produces the identical
   schema.
3. **Not-checked.** If neither Notion nor an export yields rows, do **not**
   overwrite `src/research_queue.json`; the intake reports
   `not_checked: true` and leaves the cache untouched. Report Research Queue as
   not checked — never as empty/all-clear.

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
  `src/research_queue.json`; report Research Queue as not checked (see the
  Notion-first feed section above for the Notion → export → not-checked order).
- Notion-first: `python src/research_queue_intake.py --from-notion --notion-export <pull.json> --out src/research_queue.json --merge-existing`.
  Export fallback: `python src/research_queue_intake.py <export.json|export.csv> --out src/research_queue.json --merge-existing`.
- Validate with `python src/research_queue_intake.py --validate src/research_queue.json`.
- The intake runner may preserve explicit `ACT_NOW` / urgent labels from the
  queue, but it must not invent them.

## Triage Gate (run FIRST, before any research)

Spend zero research effort on dead rows. For each candidate row, verify against
repo truth (`src/positions.json`, `src/theses.json`,
`src/trigger_registry.json`) — never from prose — and propose **KILL** when ANY
of these hold:

- (a) the underlying position was exited or the question is already decided and
  nothing forward-looking remains;
- (b) the row's catalyst/date passed more than 14 days ago with no registered
  trigger and no Live Thesis link;
- (c) a Live Thesis or a newer row already covers it (e.g. a generic
  "needs a thesis" row when a Live Thesis with an armed trigger already exists).

Split the surviving candidates into **PROPOSED-KILL** (operator approves before
any Notion status change — never flip Status yourself), **UNCERTAIN** (mini
dossier, ends in a keep/kill question), and **RELEVANT** (full dossier). When a
data point conflicts with a stated assumption (e.g. a name described as exited
but still present in `positions.json`), surface the conflict — do not silently
follow the prose.
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

## 7:30 PM ET Weekday Delta Routine (Off-Hours Research Queue)

Routine id `investing-os-off-hours-research-queue` runs market weekdays at
7:30 PM ET. It is registered in the cadence-aware overdue-alert stack
(`cloud_ops_status.DEFAULT_EXPECTED_AUTOMATIONS`), so a silent death pages the
dashboard. Each run is a delta pass, not a full re-burn:

1. **Refresh the feed** Notion-first with export fallback (see above). If
   nothing is available, report not-checked and continue — do not overwrite.
2. **Delta triage** — apply the Triage Gate above to only the new/edited rows
   since the last run (same KILL rubric). Leave already-dispositioned rows alone.
3. **Dossiers for new RELEVANT rows** — write
   `docs/research_dossiers/<slug>_<YYYY-MM-DD>.md` for each newly RELEVANT row,
   each evidence point as-of-stamped; UNCERTAIN rows get a mini-dossier only.
4. **Refresh stale stamps** — for existing dossiers whose evidence is older than
   5 trading days, re-pull price/technical/flow and update the as-of stamps
   (T4 deepdive modules if present, else `deepdive_runner` / existing UW tooling;
   mark deeper pulls as missing evidence rather than rebuilding T4's battery).
5. **Write the pending set** with `dossier_path` per item into the
   `src/research_queue.json` research block, and rebuild
   `docs/research_dossiers/INDEX.md` ranked time-sensitive first.
6. **Receipt every run** — append a `cloud_routine_receipts.json` receipt with
   `run_source=scheduled` and counts (rows read · proposed kills · new dossiers ·
   stamps refreshed), even on a no-op/not-checked run, so a missing receipt is a
   real signal. Notion write-back is additive only (append
   "Dossier drafted <date>: <repo path>"); never delete a row or change Status.

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
