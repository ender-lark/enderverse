# Broker Position Intake Routine

## Objective

Refresh current portfolio state and a clear change report before the daily
cockpit/preflight uses the book.

## Inputs

- Preferred live source: SnapTrade read-only account API, using
  `src/snaptrade_profiles.local.json` plus SnapTrade secrets from the local
  environment.
- Uploaded broker PDFs or screenshots rendered to PDF.
- Fallback normalized extractor output: `combined.json` with
  `files[].positions[]` rows containing `symbol`, `market_value`, `quantity`,
  and `account_name` when available.
- Prior account cache, when available: `src/account_positions.json`.

## Procedure

### Preferred SnapTrade Path

Use this daily on market days and whenever the operator says trades were made:

```bash
python src/snaptrade_book_refresh.py --refresh-dashboard
```

This command stages the raw SnapTrade pull, validates the combined position
shape, builds `src/positions.json`, `src/account_positions.json`, and
`src/position_reconciliation.json`, and only promotes validated outputs. With
`--refresh-dashboard`, the cockpit is rebuilt after successful promotion.

For stage-only inspection without changing the live book:

```bash
python src/snaptrade_book_refresh.py --no-promote
```

### Broker PDF / Export Fallback

1. Extract uploaded PDFs/text exports into a combined extractor JSON:

   ```bash
   python src/broker_pdf_extractor.py <pdfs-or-text-files> --out combined.json
   python src/broker_pdf_extractor.py --validate combined.json
   ```

   For PDFs, this extractor requires selectable PDF text and the `pypdf`
   package. It handles high-confidence generic ticker rows, Robinhood
   `Name Symbol Shares` rows, Schwab wrapped/compact selectable-text rows, and
   Fidelity separated value/symbol pages when every page/account group pairs
   exactly by row count. If `python` cannot import `pypdf`, run it with the
   bundled Codex dependency Python. If extraction reports failed files, do not
   continue to cache refresh; report position extraction as not checked.

   If a stronger external extractor has already produced a valid `combined.json`,
   use that instead.

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
   python -m pytest src/test_broker_pdf_extractor.py src/test_build_positions_cache.py src/test_build_positions_golden.py src/test_position_reconciliation.py src/test_positions_freshness.py -q
   ```

## Output Files

- `src/positions.json`: thesis-filtered combined cache for the engine.
- `src/account_positions.json`: account-level holdings plus combined views.
- `src/position_reconciliation.json`: NEW / EXIT / ADD / TRIM / VALUE_CHANGE rows since the prior account cache.

## Rules

- Prefer SnapTrade for daily book refresh and post-trade refresh. Use PDF/text
  extraction only when SnapTrade is unavailable or stale.
- Do not overwrite `positions.json` from a failed extractor validation when
  `--strict` fails.
- Do not overwrite `positions.json`, `account_positions.json`, or
  `position_reconciliation.json` from a failed SnapTrade validation; leave the
  existing book in place and report Account Positions as stale/not checked.
- The repo-owned PDF extractor is selectable-text-table only. Image-only PDFs
  are not checked until OCR or a stronger external extractor is added.
- Do not treat partial broker extraction as a clean Account Positions refresh.
  A file may have accurate rows while another file fails; strict cache refresh
  must still stop in that state.
- Account-level output may include untracked holdings; engine-facing
  `positions.json` remains thesis-filtered.
- A share change is a trade diff. A market-value-only change is reported as
  `VALUE_CHANGE`, not treated as a buy or sell.
- If no prior account cache exists, write account holdings and report that trade
  diff is not checked.
