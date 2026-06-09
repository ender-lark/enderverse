# Off-Hours Queue Buffer Routine

## Objective

Add a conditional early-morning buffer after the 1:45 AM Off-Hours Worker. This
routine prevents high-priority Research Queue backlog from spilling into trading
hours, without creating distracting output when the queue is already under
control.

This is research-only. It drafts or updates one focused dossier when needed. It
does not trade, size positions, recommend direct buy/sell execution, or invent
missing source data.

## Start Of Run

1. Append a started receipt:
   `python src/cloud_routine_receipts.py --routine-id investing-os-off-hours-queue-buffer --status started --run-source scheduled --summary "off-hours queue buffer started"`
2. Check current Research Queue state from live Notion first. If Notion query
   tooling is unavailable, use Notion search/fetch fallback. Use
   `src/research_queue.json` only as a fallback mirror and label it as fallback
   evidence.
3. Count queued high-priority items after the 1:45 AM worker has had time to
   run.

## Trigger

- If queued high-priority Research Queue items are `<= 2`, no-op:
  - do not create new research output
  - do not change queue status
  - append a success receipt that says the buffer skipped and reports the count
- If queued high-priority Research Queue items are `> 2`, process exactly one
  remaining high-priority item:
  - choose by priority, age, portfolio impact, and time sensitivity
  - prefer items not already updated by the 1:45 AM worker
  - produce one focused dossier or Findings update

## Dossier Contract

The one processed item must answer:

- what decision this affects
- current conviction effect: supports, contradicts, mixed, or inconclusive
- time window
- sizing, leverage, risk, or early-retirement impact if relevant
- disconfirmation trigger
- missing evidence
- next action state: research, watch, defer, invalidate, or candidate review

Do not create ACT_NOW, buy, sell, trim, hedge, or sizing instructions unless the
source record already explicitly supports that action and the operator-facing
system has the required confirmation.

## Write And Verify

- Write back to Notion only when connector write succeeds.
- After any Notion write, fetch the live page and verify the content landed
  before reporting success or changing status.
- Keep statuses conservative. Do not mark an item Done/Killed unless the live
  page verification supports that change.
- If Notion is unavailable, include the full compact dossier in the receipt
  summary or committed routine-owned artifact and leave the write lane dark.
- Missing source pulls stay dark/not_checked; never checked clear.

## End Of Run

Append a success or failed receipt with `--run-source scheduled`, including:

- high-priority queued count
- whether the buffer skipped or processed one item
- selected item, if any
- write verification status
- dark/stale lanes and blockers

Use the safe helper when routine-owned files changed:
`python src/cloud_routine_commit.py --message "Off-hours queue buffer scheduled run" --push --format text`
