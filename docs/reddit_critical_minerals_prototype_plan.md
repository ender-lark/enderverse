# Reddit Critical-Minerals / Nuclear Prototype Plan

Last updated: 2026-06-15.

## Purpose

This is the first staged Reddit/social prototype candidate because the Meridian
critical-minerals/nuclear source is stale as current context. The lane should
surface low-trust research prompts from Reddit that can improve capital
decisions, risk control, time saved, or confidence in acting/not acting.

This lane is not a trade trigger. It must not promote buy/sell/size changes from
Reddit alone.

## Detachable Shape

The implementation is intentionally a source group, not a cockpit dependency:

- Source group: `critical_minerals_nuclear`
- Initial subreddits: `r/criticalmineralstocks`, `r/UraniumSqueeze`
- Command shape:
  - `python src/reddit_collector.py --source-group critical_minerals_nuclear --input <payload-or-dir> --out tmp/critical_minerals_social_watch.json --format text`
  - `python src/reddit_collector.py --source-group critical_minerals_nuclear --input <manual-snapshot.json> --out tmp/critical_minerals_social_watch.json --report-out tmp/critical_minerals_reddit_scout.md --format text`
  - `python src/reddit_collector.py --source-group critical_minerals_nuclear --fetch-live --out tmp/critical_minerals_social_watch.json --format text`
- Output: normal `social_watch` cache shape, staged in `tmp/` unless the main
  build explicitly accepts it.
- Optional report: Markdown scout report in `tmp/`, for human review before any
  cockpit display.
- Optional weekly pattern report:
  `python src/reddit_collector.py --source-group critical_minerals_nuclear --input <manual-snapshot.json> --out tmp/critical_minerals_social_watch.json --report-out tmp/reddit_daily_scout.md --weekly-report-out tmp/reddit_weekly_patterns.md --format text`
- Repeat-snapshot report for day-over-day pattern detection:
  `python src/reddit_collector.py --source-group critical_minerals_nuclear --input <manual-snapshot.json> --out tmp/critical_minerals_social_watch.json --report-out tmp/reddit_daily_scout.md --weekly-report-out tmp/reddit_weekly_patterns.md --snapshot-history tmp/reddit_history/critical_minerals_nuclear.jsonl --format text`
- Disable path: stop supplying this cache. The main dashboard remains dark /
  `not_checked` for Social Watch.

No live action-promotion, reallocation, SnapTrade, cloud-routine, or core
dashboard logic should depend on this source group.

## Deep-Pass Findings

### `r/criticalmineralstocks`

Best use: company and policy catalyst scout for rare earths, domestic processing,
DoD deadlines, allied supply-chain partnerships, and small-cap critical-mineral
names.

Observed useful post types:

- Ucore / Sumitomo rare-earth supply-chain collaboration.
- USA Rare Earth commissioning hydrometallurgical demonstration facility.
- REalloys / domestic heavy rare-earth supply and Russell 3000 inclusion.
- Critical Mineral Monday open discussion thread.
- China rare-earth deadline and DoD 2027 ban analysis.

Observed risk:

- Small community and low comment counts.
- Some posts are crossposts or promotional in tone.
- Company tickers and entity names need careful mapping.

Interpretation rule: five to thirty comments can be meaningful in this small
subreddit, but never sufficient for action.

### `r/UraniumSqueeze`

Best use: uranium/nuclear equity narrative, AI-data-center power-demand thesis,
uranium miner sentiment, and crowding/risk warnings.

Observed useful post types:

- AI and data-center power demand causing nuclear bullishness.
- UUUU underperformance discussion.
- X-energy / advanced nuclear skepticism and HALEU constraints.
- SPUT / uranium vehicle discussion.
- EnCore Energy and uranium producer discussion.
- NNE risk/counter-thesis posts.

Observed risk:

- More active than `criticalmineralstocks`, but crowding-heavy.
- Some posts are thesis-like but uncited.
- Good for narrative and risk warnings, not for timing by itself.

## Prompt Contract

Each normalized candidate should preserve:

- `ticker/topic`
- `source_group`
- `source_type`
- `subreddit`
- `source/time`
- `why_it_matters`
- `portfolio_implication`
- `confidence`
- `decay_speed`
- `confirmation_needed`
- `blocker_before_action`
- `suggested_next_check`

The required blocker remains:

> Reddit is not a trade trigger; no buy/sell/size change from Reddit alone.

## Source Types

Use these labels before trying to score fine-grained sentiment:

- `company_or_policy_catalyst`
- `ai_power_nuclear_narrative`
- `daily_room_tone`
- `positioning_or_crowding`
- `research_prompt`
- `possible_promotion`

## Initial Ticker / Entity Universe

The code adds a detachable critical-minerals/nuclear ticker universe including:

- `MP`, `LEU`, `UUUU`, `UURAF`, `ALOY`, `CRML`
- `CCJ`, `NXE`, `DNN`, `UEC`, `URG`, `UROY`
- `URA`, `URNM`, `SPUT`
- `NNE`, `SMR`, `OKLO`, `XE`, `LTBR`

This is a starting point only. Do not assume every entity is investable,
liquid, or valid for the user's portfolio. Unknown companies should remain
entity/topic prompts until confirmed.

## Confirmation Gates

Before any Reddit item can matter to capital decisions, confirm with at least
one non-social source and ideally two:

- company press release or SEC/issuer filing
- reliable news
- UW price/options flow
- price-volume / relative-strength check
- Fundstrat or other trusted research alignment
- catalyst calendar
- portfolio exposure / sizing relevance

## What To Store

Store structured distillation, not raw comment archives:

- title snippet
- body snippet
- matched terms
- subreddit(s)
- timestamps
- score/comment counts observed
- source type
- prompt fields above
- short evidence snippets
- expiry timestamp

Avoid author storage. Keep expiry/deletion behavior at the normal 48-hour
retention boundary for stored Reddit content.

## Manual / Chrome-Visible Snapshot Input

When Reddit API access or public JSON is blocked, the collector can consume a
manual JSON snapshot captured from a visible Reddit page. This is an interim
bridge, not a separate source of truth.

Accepted shapes:

```json
[
  {
    "subreddit": "criticalmineralstocks",
    "title": "Visible Reddit post title",
    "snippet": "Short visible body or note",
    "permalink": "/r/criticalmineralstocks/comments/example/",
    "visible_time": "2h ago",
    "score": 18,
    "comments": 6,
    "flair": "Discussion"
  }
]
```

or:

```json
{
  "subreddit": "UraniumSqueeze",
  "items": [
    {
      "title": "Visible Reddit post title",
      "body": "Short visible body or note",
      "url": "https://www.reddit.com/r/UraniumSqueeze/comments/example/",
      "created_utc": "2026-06-16T13:30:00+00:00",
      "num_comments": 41
    }
  ]
}
```

Supported row fields are `subreddit`, `title`, `body` or `snippet`,
`permalink` or `url`, `created_utc` or visible time, `score`, `num_comments` or
`comments`, and `flair`. Author fields, copied raw transcripts, credentials,
cookies, screenshots, and long raw comment archives must not be stored.

Optional source-health fields:

- `members`
- `online`
- `source_sort`
- `scan_window`
- `captured_at`
- `visible_rank`
- `subreddit_health`

The collector classifies source health as `active`, `thin_but_current`,
`stale`, or `fringe`. For small/stale/fringe boards, posts can remain useful as
primary-source/link scouts, but must not be treated as sentiment, crowding, or
conviction evidence.

## Pattern Reports

Daily scout report:

- ranks useful prompts by source health and item usefulness
- includes subreddit health caveats
- keeps Reddit as watch-only
- includes a destroy/noise bucket

Weekly pattern report:

- recurring tickers/topics
- themes getting louder
- themes fading
- cross-subreddit spread
- counter-thesis/risk warnings
- destroy/noise bucket

The weekly report can be generated from the current cache alone or with prior
staged cache files via `--pattern-input <cache.json>`. It remains a research
prompt report, not a dashboard or trade trigger.

For repeatable scans, prefer `--snapshot-history tmp/reddit_history/<group>.jsonl`.
That file stores one compact normalized record per run: source group, scan date,
source-health summary, topic, subreddit spread, attention score, confirmation
blocker, and suggested next check. It does not store authors, raw comment
archives, credentials, screenshots, or long copied text. When a history file is
supplied, the daily report gains a "Repeat Snapshot Comparison" section and the
weekly report uses scan dates to detect `getting_louder`, `fading`, new topics,
and new cross-subreddit spread.

## What Not To Do

- Do not feed this into `actions` as a direct action source.
- Do not route to Key Now unless Reddit is explicitly secondary evidence.
- Do not treat missing data as checked clear.
- Do not infer a ticker when the company/entity mapping is uncertain.
- Do not let microcap/resource-stock promotion bypass confirmation gates.

## First Prototype Acceptance

- `--source-group critical_minerals_nuclear` resolves to the two initial
  subreddits and the extra ticker universe.
- Supplied/cache payloads normalize into `social_watch` rows with the full prompt
  contract.
- Source health is advisory and travels with rows/reports so thin or stale
  subreddits do not look like sentiment proof.
- Live/public fetch failure remains `not_checked`.
- Research Queue candidates still require fired velocity and independent
  confirmation.
- Focused tests pass.
- Main cockpit logic stays untouched until explicitly accepted.

## Recommended Next Build Slice

Build a repeatable scout export for `critical_minerals_nuclear` that can consume:

1. Reddit API/OAuth payloads when available.
2. Browser-visible/manual JSON exports when API access is blocked. Added
   2026-06-16 through the existing `--input` path plus `--report-out`.
3. Prebuilt fixtures for tests.

Then run the same command on consecutive scan days with `--snapshot-history` so
the second and later reports can distinguish one-off headlines from topics that
are genuinely spreading, fading, or crossing into larger boards. Keep all
outputs in `tmp/` before any dashboard display is enabled.
