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

## Watchdog Guardrail

Follow-up hardening added `src/automation_health_watchdog.py` and focused
tests. The watchdog checks the installed Codex app automation records, verifies
proof-critical routine workspaces are usable git checkouts on clean/current
`main`, and summarizes failed or overdue routine receipts from
`cloud_ops_status.py`.

The auto-fix path is intentionally narrow:

- It can rewrite unhealthy key automation `cwds` to a supplied canonical runtime
  checkout.
- The supplied runtime checkout must itself be a clean/current `main` checkout
  with the safe commit helper present.
- It does not edit receipts, fabricate scheduled success proof, or turn failed,
  overdue, missing, stale, or unsupported lanes green.
- Pushover sends are opt-in with `--send-alert`; dry runs can validate the alert
  payload with `--dry-run-alert`.

The current clean runtime checkout for local app automations is:

`C:\Users\suraj\Documents\Codex\2026-06-24\automation-runtime-main`

Validation on 2026-06-24 found 34 proof-critical installed automations with bad
workspace state, including many still pointing at the older June 4 checkout and
several pointing at the dirty/stale June 24 `automation-main` checkout. Running
the watchdog with `--apply` rewrote those 34 local Codex automation records to
the clean runtime checkout. A post-fix dry run reported zero automation
workspace problems and preserved six real cloud-proof attention items for
failed/overdue receipts.

Operator commands:

```powershell
python src\automation_health_watchdog.py --canonical-cwd C:\Users\suraj\Documents\Codex\2026-06-24\automation-runtime-main --dry-run-alert --format text
python src\automation_health_watchdog.py --canonical-cwd C:\Users\suraj\Documents\Codex\2026-06-24\automation-runtime-main --apply --dry-run-alert --format text
```

## Verification

- Before fix, `python src/verify_standard.py` failed only the GOOGL tranche-2
  date-event replay.
- After fix, run `python src/verify_standard.py` and
  `python src/automation_prompt_audit.py --format text`.
- Focused watchdog verification:
  `python -m pytest src\test_automation_health_watchdog.py`.
- Live watchdog validation after local auto-fix:
  `python src\automation_health_watchdog.py --canonical-cwd C:\Users\suraj\Documents\Codex\2026-06-24\automation-runtime-main --dry-run-alert --format text`
  reported zero automation workspace problems and kept real receipt failures
  visible.

## Remaining Expected Dark Lanes

These are not fixed by checkout repair and should stay visible until their
own source evidence lands:

- Dossier Keeper still needs its first scheduled success receipt.
- Social Watch remains dark/not_checked.
- Some source boundary artifacts are stale until their next source-specific
  scheduled runs produce fresh boundary data.
