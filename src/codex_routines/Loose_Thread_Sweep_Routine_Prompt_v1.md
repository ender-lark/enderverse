# Loose Thread Sweep Routine

## Objective

Capture loose threads from Codex's own recent Investing OS work before they
stale or disappear into chat. This is a backstop for the end-of-session rule in
`AGENTS.md`; it does not replace the agent's direct end-of-session sweep.

This routine is capture-only. It never executes parked work, stages work as
done, marks rows complete, auto-disposes decisions, recommends trades, sizes
positions, or treats missing source/queue reads as checked clear.

## Schedule

Run once daily at about 10:15 PM ET, after the evening queue/prospect routines
and before the late Fundstrat web/transcript sweep.

Automation id: `investing-os-loose-thread-sweep`

## Start Of Run

1. Confirm the cwd is the main worktree for this routine. If the checkout is
   not on `main`, write a failed scheduled receipt and stop.
2. Fast-forward before reading local history:

   ```bash
   git fetch origin main
   git pull --ff-only origin main
   ```

   If the pull cannot fast-forward, write a failed scheduled receipt and stop.
3. Append a started receipt:

   ```bash
   python src/cloud_routine_receipts.py --routine-id investing-os-loose-thread-sweep --status started --run-source scheduled --summary "loose-thread sweep started"
   ```

Use `--run-source scheduled` on every started, success, and failed receipt
written by this scheduled automation.

## Candidate Scope

Scope each run to Codex's own recent activity since the last
`investing-os-loose-thread-sweep` receipt. If no prior sweep receipt exists,
use the last 24 hours.

Candidate sources:

- new local commits on `main`
- merged/open PR references visible in recent commit messages or Workboard rows
- `docs/WORKBOARD.md` rows touched by Codex
- deferred, TODO, FOLLOW-UP, punted, or "do later" markers in
  `docs/codex_tasks/` and task-note files

Run the extractor:

```bash
python src/loose_thread_sweep.py --format json
```

Use the extractor output as a candidate list only. It does not prove that a row
should be written. The scheduled agent must still perform live dedupe and
content-based staleness review before writing anything.

## Routing

For each candidate that is genuinely new and still timely, write exactly one
new queued/review row to the correct live Notion target:

- research items and decisions-to-make -> Research Queue
  `cab89576-0933-40b0-ad2e-6f9a6188e804`
- system/tooling tasks -> System Update Queue
  `968cfff4-369c-40bb-b748-5633b9ff7685`
- analyst/source calls -> Source Call Log
  `e7def40e-1492-458a-9de8-bd77cd3f8471`
- firm decisions -> Decisions Log
  `632c97f1-192a-4933-8682-60c730446caf`

Use the target's existing schema. Prefer `Status=Queued` for queues when the
schema supports it. If the target uses a different title field (`Topic`, `Name`,
or similar), adapt to the live schema instead of forcing a mismatched property.

## Dedupe And Staleness Rules

- Read the target queue/log before writing.
- Dedupe by title/topic, ticker, source file, PR/commit reference, and normalized
  substance. Do not write near-duplicates.
- If Notion read/search is unavailable and candidates exist, write no rows,
  leave the target lane not checked, and record the blocker in a failed receipt.
- If there are no candidates, write no Notion rows and exit quickly.
- If a candidate is stale by content, already resolved, already represented in a
  target queue/log, or too vague to be useful, write nothing for it.
- After any Notion write, fetch the created page/row back and verify the title,
  route, and source reference landed before reporting it captured.

## Capture Row Minimum

Each written row should include:

- concise title/topic
- source reference: commit, PR, Workboard id, file path, or marker line
- why it still matters
- route/reason
- status `Queued` or the target's equivalent review state

Do not include secrets, raw paywalled Fundstrat text, browser profile data,
cookies, local storage, or raw transcript text.

## End Of Run

Append a success or failed receipt with `--run-source scheduled`.

Success summary must say exactly one of:

- `loose-thread sweep captured <N>: <short titles>`
- `loose-thread sweep nothing new`

Failed summary must name the blocker, such as Notion dedupe unavailable, git
fast-forward failed, or write verification failed.

Use details JSON when practical to preserve:

- candidate count
- captured count
- skipped duplicate count
- skipped stale/too-vague count
- target read/write verification status
- captured page ids or URLs

Use the safe helper when routine-owned files changed:

```bash
python src/cloud_routine_commit.py --message "Loose-thread sweep scheduled run" --push --format text
```

The helper stages only allowed routine-owned files and leaves unrelated dirty
files untouched; if push fails, report it.
