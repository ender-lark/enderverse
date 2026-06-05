# UW Cache Refresh Routine

## Objective

Refresh Unusual Whales derived caches used by the conviction engine.

UW is a conviction/timing augmenter, not a standalone trade signal.

## Procedure

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
python -m pytest src/test_uw_opportunity_scan.py src/test_full_build_runner.py -q
```

## Rules

- Keep raw UW JSON inside per-ticker worker files.
- Do not paste raw API JSON into routine summaries.
- Bounded concurrency only.
- Report skipped or failed tickers explicitly.
- Empty/near-empty output with successful source data is a field-map mismatch
  until proven otherwise.
