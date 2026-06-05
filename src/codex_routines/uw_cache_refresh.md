# UW Cache Refresh Routine

## Objective

Refresh Unusual Whales derived caches used by the conviction engine.

UW is a conviction/timing augmenter, not a standalone trade signal.

## Procedure

First, record non-secret proof that the live UW connector is available from
the market-wide connector outputs. This keeps `Live fetch` freshness auditable
without storing raw market payloads:

```bash
python src/live_source_config_update.py <uw-market-state-or-market-tide-json> --out src/live_source_config.json
python src/live_source_config_update.py --validate src/live_source_config.json
```

For the rotation/price cache, supply UW close-price responses for the default
rotation tickers and write the normalized convention file:

```bash
python src/uw_price_cache_intake.py <uw-close-response-json> --out src/uw_closes.json --summary src/uw_price_cache_summary.json
python src/uw_price_cache_intake.py --validate src/uw_closes.json
```

The supplied response file may contain a top-level ticker map or a wrapper such
as `responses`, `responses_by_ticker`, `uw_price_responses`, `prices`, or
`closes`. The intake writes only when all default rotation tickers have enough
history for the 3-month rotation read, unless an operator explicitly uses
`--allow-partial`.

For the macro cache, supply the yield-curve JSON and cross-asset macro JSON.
The emitted `macro_state.json` must contain both the session-preflight regime
fields and the UW macro snapshot fields consumed by the full cockpit build:

```bash
python src/macro_pulse_scan.py --yield-data <yield-curve-json> --cross-asset <cross-asset-json> --emit-state src/macro_state.json --summary src/macro_pulse_summary.json
python src/macro_pulse_scan.py --validate src/macro_state.json
```

If macro inputs are missing or validation fails, leave `macro_state.json`
unchanged and report the macro lane as not checked.

Run the orchestrator as a module from `src`:

```bash
cd src
python -m codex_uw.orchestrator --mode opportunity --entries-dir ../tmp/uw/opportunity_entries --emit-bundle ../tmp/uw/opportunity_bundle.json --emit-cache uw_opportunity_signals.json --max-workers 5 --retry-failed 1
```

For the parabolic cache, run only when scheduled or explicitly requested:

```bash
cd src
python -m codex_uw.orchestrator --mode parabolic --entries-dir ../tmp/uw/parabolic_entries --emit-bundle ../tmp/uw/parabolic_bundle.json --emit-cache parabolic_setups.json --max-workers 5 --retry-failed 1
```

## Verification

```bash
python src/uw_opportunity_scan.py --self-test
python src/parabolic_setup_screener.py --self-test
python src/macro_pulse_scan.py --self-test
python -m pytest src/test_live_source_config_update.py src/test_uw_price_cache_intake.py src/test_macro_freshness.py src/test_uw_macro.py src/test_uw_macro_adapter.py src/test_uw_opportunity_scan.py src/test_full_build_runner.py -q
```

## Rules

- Keep raw UW JSON inside per-ticker worker files.
- Store only connector proof metadata in `src/live_source_config.json`; do not
  store market-tide rows, premiums, volumes, or other raw UW payload fields.
- Do not paste raw API JSON into routine summaries.
- Bounded concurrency only.
- Report skipped or failed tickers explicitly.
- Do not write `uw_closes.json` from incomplete rotation inputs; leave
  `uw_price` not checked instead of publishing a partial cache by accident.
- Do not write `macro_state.json` unless it validates for both regime/freshness
  fields and full-build UW macro snapshot fields.
- Empty/near-empty output with successful source data is a field-map mismatch
  until proven otherwise.
