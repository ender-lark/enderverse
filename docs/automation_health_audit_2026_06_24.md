# Automation Health Audit - 2026-06-24

## Findings

1. The OneDrive `Investing OS (2.0)` folder is a wrapper, not a git checkout.
2. Several active Codex app automations still pointed at
   `C:\Users\suraj\Documents\Codex\2026-06-17\auto-loose-thread-sweep\enderverse`.
   That checkout was on `main` but had accumulated local failed-receipt commits
   and was `ahead 33, behind 102` versus `origin/main`, so routines with the
   required fast-forward gate stopped before env checks, Notion reads, Pushover
   sends, or useful repo work.
3. `origin/main` still had a real Daily Synthesis failure because
   `verify_standard.py` failed `test_efficacy_harness` on
   `googl-tranche-2-2026-06-19`. The live GOOGL date-event trigger had already
   fired legitimately, and the historical replay helper reused that terminal
   status instead of replaying an armed copy.

## Fixes

1. Created a clean current-main automation target checkout:
   `C:\Users\suraj\Documents\Codex\2026-06-24\automation-main`.
2. Updated the repo-local canonical checkout note in `AGENTS.md` away from the
   divergent June 17 checkout.
3. Made the efficacy harness normalize copied real-registry replay rows to
   `armed` and clear terminal fire metadata, while leaving the live registry
   untouched.

## Verification

- Before fix, `python src/verify_standard.py` failed only the GOOGL tranche-2
  date-event replay.
- After fix, run `python src/verify_standard.py` and
  `python src/automation_prompt_audit.py --format text`.

## Remaining Expected Dark Lanes

These are not fixed by checkout repair and should stay visible until their
own source evidence lands:

- Dossier Keeper still needs its first scheduled success receipt.
- Social Watch remains dark/not_checked.
- Some source boundary artifacts are stale until their next source-specific
  scheduled runs produce fresh boundary data.
