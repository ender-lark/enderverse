# Off-Hours Queue Buffer Routine

## Objective

Add a conditional early-morning buffer after the 1:45 AM Off-Hours Worker. This
routine prevents Research Queue backlog from spilling into trading hours. Normal
weeks are throughput-first: if queued work remains and can be handled safely, the
buffer should continue draining it rather than limiting itself to one item.

This is research-only. It drafts or updates focused dossiers when needed. It
does not trade, size positions, recommend direct buy/sell execution, or invent
missing source data.

## Start Of Run

1. Append a started receipt:
   `python src/cloud_routine_receipts.py --routine-id investing-os-off-hours-queue-buffer --status started --run-source scheduled --summary "off-hours queue buffer started"`
2. Check current Research Queue state from live Notion first. If Notion query
   tooling is unavailable, use Notion search/fetch fallback. Use
   `src/research_queue.json` only as a fallback mirror and label it as fallback
   evidence.
3. Count queued items after the 1:45 AM worker has had time to run, split by
   High, Med, and Low priority.

## Trigger

- If no queued Research Queue item can be safely advanced, no-op:
  - do not create new research output
  - do not change queue status
  - append a success receipt that says the buffer skipped and reports the queue
    counts plus the reason
- If queued items remain and can be safely advanced, process as many as possible
  before pre-market routines start:
  - choose by priority, age, portfolio impact, time sensitivity, and whether the
    item was already updated by the 1:45 AM worker
  - handle High before Med before Low unless a lower-priority item is unusually
    quick and unblocks the queue
  - produce focused dossiers or Findings updates
  - leave an explicit remaining count and blocker reason for anything not
    completed

## Dossier Contract

Each processed item must answer:

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

## Throughput Rules

- Normal target: clear all queued High and Med items that can be completed with
  verified writes before trading hours; continue into Low items if time remains.
- Temporary usage-constrained weeks may fall back to top one or two highest
  impact items, but the receipt must label this as a temporary cap and report the
  remaining backlog.
- Do not trade completeness for sloppy writes. A smaller verified set beats a
  larger unverified set.
- If a source is missing, leave that source lane dark/not_checked and move to the
  next item that can be advanced.

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
- medium- and low-priority queued count
- whether the buffer skipped or processed items
- selected items, if any
- remaining queued count and why anything remains
- write verification status
- dark/stale lanes and blockers

Use the safe helper when routine-owned files changed:
`python src/cloud_routine_commit.py --message "Off-hours queue buffer scheduled run" --push --format text`
