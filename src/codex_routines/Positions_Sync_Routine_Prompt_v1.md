# Positions Sync routine prompt v1

You are running the post-close Positions Sync for the Investing OS system.
This routine refreshes the read-only portfolio book after the market close so
the next dashboard build has current holdings, account rows, cash positions,
and trade-diff context.

This is read-only. Do not place trades, route orders, modify broker accounts,
recommend buys or sells, or expose secrets in chat, logs, commits, or Notion.
SnapTrade keys and local profile details live only in the routine environment.

Scheduling target: market weekdays around 4:45 PM ET, after Post-Close Refresh
and FS Inbox Catch-up Postclose.

## Procedure

1. Start from the repo main branch.
   Confirm the checkout is on `main` tracking `origin/main`, then pull the
   latest commits. If the branch is not main, switch to main and pull before
   touching files.

2. Append the started receipt.

   ```bash
   python src/cloud_routine_receipts.py --routine-id investing-os-positions-sync --status started --run-source scheduled --summary "positions sync started"
   ```

3. Run the existing validated SnapTrade book refresh.

   ```bash
   python src/snaptrade_book_refresh.py --refresh-dashboard
   ```

   This is the canonical path. It stages the raw SnapTrade pull, validates the
   combined book, promotes only valid outputs, writes `src/positions.json`,
   `src/account_positions.json`, and `src/position_reconciliation.json`, and
   rebuilds the dashboard after successful promotion.

4. Run orphan triage after a successful promotion.

   ```bash
   python src/orphan_triage.py
   ```

   The triage is an account-book audit only. It should write
   `src/orphan_triage.json` and `src/orphan_triage.md` from the promoted
   account cache. It must not create trades.

5. Validate the position outputs and triage.

   ```bash
   python -m pytest src/test_snaptrade_book_refresh.py src/test_position_reconciliation.py src/test_positions_freshness.py src/test_orphan_triage.py -q
   ```

6. Inspect and report the reconciliation.
   Read `src/position_reconciliation.json` and report snapshot date, account
   count, raw position count, diff counts, warnings, and dashboard refresh
   status. On the first post-2026-06-12 run, explicitly say whether the diff saw
   the expected 2026-06-12 trade fills: MAGS exit, NVDA/GOOGL adds, PCRA basket,
   and possible MU trim. If a fill is not visible, say it is not visible rather
   than inferring it happened.

7. Confirm account-position shape.
   `src/account_positions.json` should include a snapshot date, per-account
   rows, combined rows, tracked combined rows, and cash rows such as SPAXX/FDRXX
   if SnapTrade returns them. Do not fabricate cash rows if SnapTrade omits
   them.

8. Mirror a one-paragraph Latest Portfolio summary to Notion when the Notion
   connector is available.
   Include snapshot date, total sleeve/book value, account row count,
   share-change counts, notable changes, orphan count, warnings, and dashboard
   refresh status. If Notion is unavailable, report "Notion mirror not checked"
   and continue; do not fail the repo refresh if the promoted repo outputs are
   valid.

9. Append the final receipt.
   On success:

   ```bash
   python src/cloud_routine_receipts.py --routine-id investing-os-positions-sync --status success --run-source scheduled --summary "positions sync succeeded: <snapshot/date/account count/diff summary>"
   ```

   On failure:

   ```bash
   python src/cloud_routine_receipts.py --routine-id investing-os-positions-sync --status failed --run-source scheduled --summary "positions sync failed: <specific blocker>"
   ```

10. Commit and push routine-owned changes.

    ```bash
    python src/cloud_routine_commit.py --message "Positions sync scheduled run" --push --format text
    ```

    This helper should stage only allowlisted routine-owned outputs. If push
    fails, report the commit hash and push failure; do not retry with broad git
    adds.

## Failure and honesty rules

- If SnapTrade credentials, the local profile, connector access, validation, or
  promotion fails, do not overwrite or promote position caches. Append a failed
  receipt, preserve the last promoted book, and report Account Positions as
  stale/not_checked.
- Missing data stays dark/not_checked, never checked clear.
- A market-value-only change is `VALUE_CHANGE`, not a buy/sell.
- A drafted plan, orphan triage row, or reconciliation diff is not an executed
  trade. The operator decides.
- Never print SnapTrade secrets, tokens, account credentials, raw profile
  details, or broker auth payloads.
