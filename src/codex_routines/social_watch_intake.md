# Social Watch Intake Routine

## Objective

Refresh `src/social_watch.json` only from a Chrome-visible Reddit/social
market-signal check or a supplied compact manual snapshot. This is an
early-signal anomaly lane only. It never creates BUY, SELL, trade, sizing,
leverage, or execution cards.

The scheduled automation is intentionally paused until the operator asks for a
Chrome scan. Do not use Reddit API, public `.json` endpoints, or
`reddit_collector.py --fetch-live`; those routes are blocked and create noisy
`403` / `not_checked` receipts.

## Start Of Run

1. Append a started receipt:
   `python src/cloud_routine_receipts.py --routine-id investing-os-social-watch-intake --status started --run-source scheduled --summary "social watch intake started"`
2. Read the source-of-truth contracts:
   - `docs/reddit_feed_design.md`
   - `src/reddit_collector.py`
   - `src/social_watch.py`
   - `src/reddit_signal_core.py`
3. Treat missing, unavailable, malformed, or stale Chrome/manual snapshots as
   `not_checked`. Do not infer no social anomalies from missing input.

## Source Boundary

- Use the Codex Chrome extension/current Chrome session for the configured
  subreddit set:
  `stocks, investing, SecurityAnalysis, wallstreetbets, options, thetagang,
  ValueInvesting, StockMarket`.
- Prefer visible Reddit pages, including `old.reddit.com` when modern Reddit
  pages are hard to scan.
- Store only compact visible rows: subreddit, title, short snippet/body when
  useful, permalink/url, visible time or `created_utc`, score/upvotes, comments,
  flair, source sort, scan window, capture time, visible rank, and member/online
  counts if visible.
- Do not store author names, handles, profiles, votes by user, cookies, local
  storage, credentials, screenshots, raw page payloads, raw comment archives, or
  long copied Reddit text.
- Stored social snippets expire after 48 hours. Fresh runs should replace stale
  snippets rather than accumulating raw user content.
- If no fresh Chrome/manual snapshot is available, write or preserve a dated
  `not_checked` cache with the blocker and stop. Do not attempt the public live
  Reddit fallback.

## Run Command

Preferred after Chrome has exported or saved compact manual snapshot rows:

`python src/reddit_collector.py --input <manual-snapshot.json> --out src/social_watch.json --report-out tmp/reddit_daily_scout.md --weekly-report-out tmp/reddit_weekly_patterns.md --snapshot-history tmp/reddit_history/broad_social.jsonl --format text`

For critical-minerals/nuclear scans:

`python src/reddit_collector.py --source-group critical_minerals_nuclear --input <manual-snapshot.json> --out tmp/critical_minerals_social_watch.json --report-out tmp/reddit_daily_scout.md --weekly-report-out tmp/reddit_weekly_patterns.md --snapshot-history tmp/reddit_history/critical_minerals_nuclear.jsonl --format text`

For WSB-only retail crowding scans:

`python src/reddit_collector.py --source-group retail_risk_wsb --input <manual-snapshot.json> --out tmp/wsb_social_watch.json --report-out tmp/wsb_daily_scout.md --weekly-report-out tmp/wsb_weekly_patterns.md --snapshot-history tmp/reddit_history/retail_risk_wsb.jsonl --format text`

No fallback command exists for public Reddit `.json` refreshes.

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

If a scheduled run is explicitly re-enabled later, append a success or failed
receipt with `--run-source scheduled` and a compact summary of subreddits
checked, anomalies found, missing snapshot blockers, Research Queue/Notion
writes, cache validation, and dark lanes.

If routine-owned files changed, commit and push with the safe helper. If push
fails, report the failure and leave unrelated dirty files untouched:

`python src/cloud_routine_commit.py --message "Social watch intake scheduled run" --push --format text`
