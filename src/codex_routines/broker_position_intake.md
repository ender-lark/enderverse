# Broker Position Intake Routine

## Objective

Turn uploaded broker-position PDFs into current portfolio state and a clear
change report before the daily cockpit/preflight uses the book.

## Inputs

- Uploaded broker PDFs or screenshots rendered to PDF.
- Preferred normalized extractor output: `combined.json` with
  `files[].positions[]` rows containing `symbol`, `market_value`, `quantity`,
  and `account_name` when available.
- Prior account cache, when available: `src/account_positions.json`.

## Procedure

1. Extract the uploaded PDFs into a combined extractor JSON.
2. Build the engine-facing combined cache:

   ```bash
   python src/build_positions_cache.py --combined combined.json --theses src/theses.json --out src/positions.json --strict
   ```

3. Build account-level holdings and a trade-diff report:

   ```bash
   python src/position_reconciliation.py --combined combined.json --theses src/theses.json --prior-account-positions src/account_positions.json --account-out src/account_positions.json --reconcile-out src/position_reconciliation.json
   ```

4. Validate both outputs:

   ```bash
   python src/build_positions_cache.py --validate src/positions.json
   python src/position_reconciliation.py --validate src/account_positions.json
   ```

5. Run focused checks:

   ```bash
   python -m pytest src/test_build_positions_cache.py src/test_build_positions_golden.py src/test_position_reconciliation.py src/test_positions_freshness.py -q
   ```

## Output Files

- `src/positions.json`: thesis-filtered combined cache for the engine.
- `src/account_positions.json`: account-level holdings plus combined views.
- `src/position_reconciliation.json`: NEW / EXIT / ADD / TRIM / VALUE_CHANGE rows since the prior account cache.

## Rules

- Do not overwrite `positions.json` from a failed extractor validation when
  `--strict` fails.
- Account-level output may include untracked holdings; engine-facing
  `positions.json` remains thesis-filtered.
- A share change is a trade diff. A market-value-only change is reported as
  `VALUE_CHANGE`, not treated as a buy or sell.
- If no prior account cache exists, write account holdings and report that trade
  diff is not checked.
