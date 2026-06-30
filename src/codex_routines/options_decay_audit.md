# Investing OS Options Decay Audit

Purpose: run a daily review-only audit for owned option positions that can lose value quickly through time decay, stale marks, or unattended material premium. The routine must surface same-day operator review prompts; it must never place trades or convert missing source data into checked-clear status.

## Runtime Contract

- Work from the canonical runtime checkout: `C:\Users\suraj\Documents\Codex\2026-06-24\automation-runtime-main`.
- Start only from `main` after a clean fast-forward from `origin/main`.
- Append cloud-routine receipts through `src/cloud_routine_runner.py` with `--run-source scheduled`.
- Write only `src/options_decay_audit.json` plus routine receipts during the audit.
- Persist routine-owned changes through `src/cloud_routine_commit.py`; do not commit unrelated dirty files.

## Scheduled Command

Run this sequence:

```powershell
git fetch origin main --prune
git pull --ff-only origin main
python src/cloud_routine_runner.py --run-source scheduled --routine-id investing-os-options-decay-audit --owns-artifacts src/options_decay_audit.json --success-summary "options decay audit succeeded" --failure-summary "options decay audit failed" -- python src/options_decay_audit.py --send --out src/options_decay_audit.json --format text
python src/cloud_routine_commit.py --message "Options decay audit scheduled run" --push --format text
```

## Data Rules

- Required input: `src/account_positions.json`, the promoted broker account-position book.
- Optional enrichment: `src/options_chain_cache.json`, only when fresh under the audit's max-age rule.
- If `src/account_positions.json` is missing or unreadable, fail the run and leave `account_positions_not_checked` visible.
- If the options chain cache is missing, stale, partial, or does not match a held contract, keep that lane `not_checked`.
- If no option positions are held, write a quiet success payload and send no alert.
- If material option premium is inside the decay window, near expiry, mostly extrinsic, or has meaningful theta when checked from a fresh chain cache, send a Pushover review prompt.

## Operator Semantics

- Alerts mean "review this option today," not "sell now" or "trade automatically."
- Keep account labels in the alert so the operator knows where the option is held.
- Include data gaps in the alert; stale chain data is itself part of the risk.
- Do not suppress HOOD-like material premium just because the chain cache is stale.

## Verification

```powershell
python src/options_decay_audit.py --self-test
python -m pytest src/test_options_decay_audit.py -q
```
