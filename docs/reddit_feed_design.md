# Reddit Feed Design

Last updated: 2026-06-07.

## Purpose

Reddit is an early-signal and anomaly-discovery feed, not a trading signal. It
should find posts, comments, and mention-velocity changes that deserve vetting,
then route them to Research Queue, Quiet Watch, or a re-check prompt only after
independent confirmation.

## Source Rules

The official Reddit Data API documentation says Reddit requires OAuth, a unique
descriptive User-Agent, and rate-limit monitoring. The current public help page
lists response headers for rate limits and a free-access limit of 100 queries per
minute per OAuth client id, averaged over a time window. It also says stored user
content that has been deleted must be removed, and recommends routinely deleting
stored user data/content within 48 hours.

Design implications:

- Store minimal snippets, post ids, subreddit, timestamp, ticker/entity matches,
  and derived scores.
- Avoid storing author-identifying data unless it is strictly needed.
- Keep a deletion/expiry process for stored raw Reddit content.
- Use OAuth credentials and a unique User-Agent.
- Read and respect `X-Ratelimit-Used`, `X-Ratelimit-Remaining`, and
  `X-Ratelimit-Reset`.
- Never scrape around API rules when API access is unavailable.

References:

- https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki
- https://www.reddit.com/dev/api/

## Candidate Subreddits

Initial broad watch-only set:

- `r/stocks`
- `r/investing`
- `r/SecurityAnalysis`
- `r/wallstreetbets`
- `r/options`
- `r/thetagang`
- `r/ValueInvesting`
- `r/StockMarket`
- Sector-specific or ticker-specific subreddits only after review, because they
  can be more promotional and less representative.

Crypto/BMNR-adjacent feeds should be separate from equity feeds because reflexivity,
promotion, and echo risk are higher.

### Detachable Source Groups

Do not make one generic Reddit signal carry every job. Keep source groups
detachable so they can be added or removed without disturbing the main cockpit.

Current source groups:

- `broad_social`: the broad watch-only set above.
- `critical_minerals_nuclear`: `r/criticalmineralstocks` and
  `r/UraniumSqueeze`, designed as the first staged replacement scout for stale
  Meridian critical-minerals/nuclear context.

The source group is a collector/cache concern. If its cache is absent, Social
Watch remains dark / `not_checked`; the dashboard should not infer checked-clear
or no-signal.

Read `docs/reddit_critical_minerals_prototype_plan.md` before changing or
promoting the critical-minerals/nuclear group.

## Intake Shape

Each fetched item should normalize to:

```json
{
  "id": "reddit fullname or stable post/comment id",
  "source": "reddit",
  "subreddit": "stocks",
  "created_utc": "2026-06-07T13:00:00Z",
  "kind": "post_or_comment",
  "title_snippet": "short redacted title",
  "body_snippet": "short redacted body",
  "tickers": ["NVDA"],
  "entities": ["AI chips"],
  "permalink": "https://www.reddit.com/...",
  "score_observed": 123,
  "comment_count_observed": 45,
  "matched_terms": ["NVDA", "Blackwell"],
  "ingested_at": "2026-06-07T13:05:00Z",
  "expires_at": "2026-06-09T13:05:00Z"
}
```

## Scoring

Use the existing `src/reddit_signal_core.py` logic as the measurement contract:

- Mention velocity is a z-score versus trailing baseline plus an absolute mention
  floor.
- Lead-time should be measured only versus low-latency sources such as Fundstrat
  Inbox, news, price action, and catalysts. Lagged sources like 13F should not be
  credited as Reddit lead-time.
- Score fixed-percentile cohorts so live threshold tuning does not distort hit
  rate.
- Score multiple horizons so social reflexivity and reversal can be seen.
- Kill criterion should require poor accuracy, not merely lack of user action.

## Escalation Rules

Reddit item -> Quiet Watch when:

- Ticker/entity velocity is unusual but no independent confirmation exists.
- The item appears after a large price move and may be a lagging echo.
- The subreddit/source quality is weak or promotional.

Reddit item -> Research Queue when:

- Velocity is eligible and high.
- Mentions contain a specific factual claim, catalyst, product, regulatory event,
  or channel-check style detail.
- There is at least one independent clue from news, Fundstrat, UW, price action,
  or catalyst calendars.

Reddit item -> Re-check Before Acting when:

- It touches an existing material holding or under-owned target.
- UW/news/price evidence partially confirms the signal.
- The action would be high-impact but the evidence is not yet sufficient.

Reddit item -> Key Now only when:

- Reddit is not the primary evidence.
- Same-day UW/price/news/Fundstrat evidence confirms the risk or opportunity.
- The action has a clear trigger, disconfirmation, freshness label, and rationale.

## Dashboard Surface

Add a "Social Watch" block under opportunity discovery:

- Count of new eligible anomalies.
- Top three anomalies by impact-adjusted score.
- Ticker/entity, subreddit mix, first seen, last seen, velocity, and freshness.
- A clear label: `watch-only until independently confirmed`.
- Buttons or commands for "send to Research Queue", "quiet watch", and "dismiss".

Current repo state:

- `src/social_watch.py` normalizes a future Reddit/social cache into
  `feed.social_watch`.
- `src/reddit_collector.py` writes `src/social_watch.json` from Chrome-browsed
  or supplied Reddit-shaped payloads, using `reddit_signal_core.detect_signal`
  for mention velocity and preserving `not_checked` on fetch failure.
- `src/reddit_collector.py --source-group critical_minerals_nuclear` selects the
  detachable `r/criticalmineralstocks` + `r/UraniumSqueeze` prototype watchlist
  and adds the critical-minerals/nuclear ticker universe without changing the
  dashboard contract.
- `src/full_build_runner.py` loads `src/social_watch.json`, `src/reddit_watch.json`,
  or `src/reddit_signals.json`.
- The dashboard renders Social Watch in the Action view and summary export.
- If no cache exists, the lane is visible as `not_checked`; this is not a
  no-social-signal read.
- Social rows fail validation if they attempt direct buy/sell/trade escalation.

## Failure Modes

- Pump/chase risk: a spike can be promotional or late.
- Reflexivity: Reddit can cause the move it observes.
- Selection bias: only looking at fired signals can overstate usefulness.
- Stale content: deleted or old content must not persist as current evidence.
- Ticker ambiguity: common words and meme tickers can false-match.
- Echo risk: if Reddit repeats Fundstrat/news after the fact, it is not an early
  signal.

## Implementation Order

1. Watch-only dashboard block and normalizer. Done 2026-06-07.
2. Credential and compliance config: User-Agent, rate-limit/failure tracking,
   and content expiry. Browser-browsed public payload path added 2026-06-14;
   do not store credentials or author-identifying data.
3. Read-only fetcher for a small subreddit allowlist. Added 2026-06-14 as
   `src/reddit_collector.py`.
4. Ticker/entity matching and snippet redaction upstream of `social_watch.py`.
   Added 2026-06-14.
5. Research Queue escalation command. Repo-local candidate generation added
   2026-06-14; Notion write remains gated on independent confirmation and live
   write verification.
6. Backtest/calibration log before any Key Now promotion path.
