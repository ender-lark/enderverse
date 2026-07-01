# Trump Trade Watch Routine

## Objective

Capture Donald J Trump political/executive trade disclosures into
`src/political_trade_watch.json` quickly enough that Investing OS can review the
tickers, sectors, policy links, and portfolio overlap. This is a watch-only
research lane. It never creates BUY, SELL, sizing, leverage, or execution cards.

Primary source is Unusual Whales political-disclosure data. Reddit is only a
secondary scout for discussion around the disclosures, especially
`r/unusual_whales` and `r/TrumpsTrades`; Reddit never substitutes for a UW/OGE
filing row.

## Start Of Run

1. Append a started receipt:
   `python src/cloud_routine_receipts.py --routine-id investing-os-trump-trade-watch --status started --run-source scheduled --summary "trump trade watch started"`
2. Read the source-of-truth contracts:
   - `src/political_trade_watch.py`
   - `src/reddit_collector.py`
   - `docs/reddit_feed_design.md`
   - `src/codex_routine_manifest.json`
3. Missing, blocked, malformed, or stale source data is `not_checked`, not
   checked clear.

## Source Boundary

- Preferred path: use the Unusual Whales connector
  `get_congress_trades` with `politician="Trump"` or `politician="Donald J Trump"`,
  `chamber="executive"`, `ordering_option="filing_date_desc"`, and a bounded
  limit.
- Fallback path: run the repo REST intake only when `UW_API_KEY` is available:
  `python src/political_trade_watch.py --fetch-live --out src/political_trade_watch.json --format text`
- Supplied/exported connector rows should be piped or saved and normalized with:
  `python src/political_trade_watch.py --stdin-json --out src/political_trade_watch.json --format text`
- Store only normalized disclosure fields: target/reporter, ticker, issuer,
  transaction type/date, filed date, amount range, source filing URL, disclosure
  lag, and watch-only routing fields.
- Do not store secrets, raw API credentials, browser cookies, or unrelated raw
  payloads.

## Secondary Reddit Scout

Use Reddit only to catch discussion that may point to a disclosure, headline
echo, or market rumor that still needs primary-source verification.

Manual/Chrome-visible snapshot command:

`python src/reddit_collector.py --source-group trump_trade_watch --input <manual-snapshot.json> --out tmp/trump_trade_social_watch.json --report-out tmp/trump_trade_reddit_scout.md --snapshot-history tmp/reddit_history/trump_trade_watch.jsonl --format text`

The configured source group starts with `r/unusual_whales`, `r/TrumpsTrades`,
`r/stocks`, `r/StockMarket`, and `r/investing`. It is secondary, staged, and
watch-only.

## Confirmation And Routing

- A UW political-disclosure row with a ticker can become a Research Queue
  candidate, not a trade card.
- A disclosure without a ticker stays Quiet Watch until mapped to a tradable
  instrument and independently verified.
- Action surfacing requires filing verification plus same-session UW flow,
  price/news, Fundstrat, catalyst evidence, portfolio fit, account fit, and the
  pre-trade gate.
- Never copy-trade from a political disclosure. Disclosure lag and incomplete
  prices make it unsuitable as standalone timing evidence.

## Validate

Run:

`python src/political_trade_watch.py --cache src/political_trade_watch.json --format text`

For code changes, run:

`python -m pytest src/test_political_trade_watch.py src/test_reddit_collector.py src/test_full_build_runner.py -q`

## End Of Run

Append a terminal success or failed receipt with `--run-source scheduled` and a
compact summary: rows captured, newest filing date, tickers, Research Queue
candidates, source blockers, and whether the cache validated.

Commit and push only routine-owned artifacts with:

`python src/cloud_routine_commit.py --message "Trump trade watch scheduled run" --push --format text`

If push fails, report the failure and leave unrelated dirty files untouched.
