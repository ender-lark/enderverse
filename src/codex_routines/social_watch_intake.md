# Social Watch Intake Routine

## Objective

Refresh `src/social_watch.json` from a Chrome-browsed Reddit/social market-signal
check. This is an early-signal anomaly lane only. It never creates BUY, SELL,
trade, sizing, leverage, or execution cards.

## Start Of Run

1. Append a started receipt:
   `python src/cloud_routine_receipts.py --routine-id investing-os-social-watch-intake --status started --run-source scheduled --summary "social watch intake started"`
2. Read the source-of-truth contracts:
   - `docs/reddit_feed_design.md`
   - `src/reddit_collector.py`
   - `src/social_watch.py`
   - `src/reddit_signal_core.py`
3. Treat missing, blocked, rate-limited, malformed, or stale Reddit fetches as
   `not_checked`. Do not infer no social anomalies from a failed fetch.

## Source Boundary

- Use Chrome browsing for the configured subreddit set:
  `stocks, investing, SecurityAnalysis, wallstreetbets, options, thetagang,
  ValueInvesting, StockMarket`.
- Store only minimal rows: post/comment id, subreddit, timestamp, ticker/entity
  matches, derived scores, permalink, and short snippets.
- Do not store author names, handles, profiles, votes by user, cookies, local
  storage, credentials, raw page payloads, or raw Reddit bodies.
- Stored social snippets expire after 48 hours. Fresh runs should replace stale
  snippets rather than accumulating raw user content.
- If Reddit blocks, rate-limits, or returns unusable pages, write a dated
  `not_checked` cache with failures and freshness stamp.

## Run Command

Preferred after Chrome has exported or saved subreddit JSON payloads:

`python src/cloud_routine_runner.py --run-source scheduled --routine-id investing-os-social-watch-intake --success-summary "social watch intake succeeded" --failure-summary "social watch intake failed" -- python src/reddit_collector.py --input <reddit-json-file-or-dir> --out src/social_watch.json`

Fallback for a manual/operator-approved public listing refresh when a browser
export is unavailable:

`python src/cloud_routine_runner.py --run-source scheduled --routine-id investing-os-social-watch-intake --success-summary "social watch intake succeeded" --failure-summary "social watch intake failed" -- python src/reddit_collector.py --fetch-live --out src/social_watch.json`

## Confirmation And Routing

- Reddit anomalies without non-social confirmation stay `Quiet Watch`.
- Pass a confirmation map only when UW, price/news, Fundstrat, catalyst, or
  source-call evidence has actually been checked:
  `--confirmations <non-social-confirmation-json>`.
- Confirmed fired anomalies may append repo-local Research Queue candidates with:
  `--research-queue-out src/research_queue.json`.
- When Notion connector write access is available, write confirmed fired
  anomalies to the Notion Research Queue after the cache validates. Include the
  independent-confirmation note, the blocker before action, and the Social Watch
  permalink. Fetch the Notion row after writing and verify title, ticker, status,
  and confirmation text before reporting success.
- Never route Reddit alone to Key Now or a decision card. Key Now requires
  Reddit not be primary evidence plus same-day independent proof.

## Validate

Run:

`python src/social_watch.py --cache src/social_watch.json --format text`

For code changes, run:

`python -m pytest src/test_reddit_collector.py src/test_social_watch.py src/test_full_build_runner.py -q`

## End Of Run

Append a success or failed receipt with `--run-source scheduled` and a compact
summary of subreddits checked, anomalies found, failures/rate limits, Research
Queue/Notion writes, cache validation, and dark lanes.

If routine-owned files changed, commit and push with the safe helper. If push
fails, report the failure and leave unrelated dirty files untouched:

`python src/cloud_routine_commit.py --message "Social watch intake scheduled run" --push --format text`
