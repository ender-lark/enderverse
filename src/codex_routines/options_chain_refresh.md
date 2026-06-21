# Options Chain Refresh Routine

## Objective

Refresh the options-chain cache (`src/options_chain_cache.json`) that feeds the
options-expression surface. The surface expresses an EXISTING conviction as a
sized, defined-risk options idea; it is never a standalone trade signal and never
auto-executes. A missing/partial cache leaves `feed.options_expression` omitted
(additive) — never "no options expression."

Same boundary as `uw_cache_refresh`: the token-heavy live pulls happen here (a
cloud/chat session with the Unusual Whales MCP); the build (`full_build_runner`)
stays pure and only reads the cache. Keep raw UW JSON inside per-ticker worker
files; do not paste raw API JSON into routine summaries.

## Procedure

1. Pick the bounded conviction universe and the target expiry (the standard
   monthly opex ~45 DTE — `get_options_chain` returns an EMPTY chain for a date
   that is not a real listed expiration, so do not pass a raw calendar date):

   ```bash
   cd src && python -c "import json,options_chain_refresh as o; t=json.load(open('theses.json')); print(' '.join(o.select_universe(t, cap=16))); print(o.target_expiry('<as_of YYYY-MM-DD>', dte=45))"
   ```

   `select_universe` keeps ACTIVE thesis names and drops no-add sleeves
   (MONITOR/BURNED/EXIT/TRIM); pass `extra=[...]` for watchlist / lean-in /
   Fundstrat names if desired.

2. For EACH name in the universe, pull two cheap UW reads with bounded
   concurrency and keep the RAW responses verbatim:

   - `get_stock_screener(ticker=T, limit=1)` — iv_rank, iv30d,
     implied_move_perc, next_earnings_date, close, prev_close, 52w high/low.
   - `get_options_chain(ticker=T, expiry=<monthly opex from step 1>, limit=50)` —
     strikes + greeks. If the monthly returns no contracts, retry once with
     `expiry="init"` (nearest listed expiry) and report the fallback.

   Assemble a responses map `{TICKER: {"screener": <raw>, "chain": <raw>}}` and
   write it to a worker file under `tmp/` (raw payloads stay out of summaries).

3. Assemble + write the cache from the captured responses (pure, token-safe):

   ```bash
   python src/options_chain_refresh.py --from-responses <tmp/options_responses.json> --out src/options_chain_cache.json --as-of <as_of> --expiry <monthly opex>
   ```

   The intake drops any name with no usable screener/chain, stamps `_meta`
   (source, as_of, expiry_target, count, tickers), and writes atomically.

4. The next `daily_full_build` reads the cache and surfaces the options
   expressions (loud block in TODAY-DECIDE + `optionsExpressionRows` in the
   cockpit). The build also appends near-misses to `src/options_shadow_log.jsonl`
   for later dial-tuning — do not hand-edit that log.

## Verification

```bash
python src/options_chain_refresh.py --self-test
python -m pytest src/test_options_chain_refresh.py src/test_full_build_runner.py src/test_options_surface.py -q
```

## Rules

- Keep raw UW JSON inside per-ticker worker files; do not paste raw API JSON into
  routine summaries.
- Bounded concurrency only; report skipped or failed tickers explicitly.
- A name that returns no usable chain is reported and dropped from the cache (the
  surface shows it as a data-gap, never a fabricated illiquid idea) — it must not
  silently disappear.
- Do not write a partial cache that implies more coverage than was pulled; the
  `_meta.count`/`tickers` must match what actually landed.
- The surface never originates, blocks, or auto-executes a decision; max-loss is
  shown in $ AND %, and the sized idea is never an order (the operator trades).
- If the UW connector/API is unavailable, leave the prior cache in place and
  report the options lane as not checked rather than publishing an empty cache.
