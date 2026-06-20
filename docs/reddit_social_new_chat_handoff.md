# Reddit/Social Feed New Chat Handoff

Use this prompt to start a separate Codex chat for the Reddit/social feed
workstream without interfering with the main Monday go-live build.

## Copy/Paste Prompt

You are working in repo `ender-lark/enderverse` on the Investing OS
Reddit/social feed workstream only.

Workspace path on this machine:
`C:\Users\suraj\Documents\Codex\2026-06-04\confirm-you-can-access-my-github\work\enderverse`

Start by reading:

- `AGENTS.md` if present.
- `docs/monday_go_live_build_plan.md`
- `docs/reddit_feed_design.md`
- `docs/codex_build_queue.md`
- `src/social_watch.py`
- `src/test_social_watch.py` if present.
- `src/latest_cockpit_feed.json` only as current dashboard context, not as a
  file to overwrite unless explicitly asked.

Primary operating principle:

- Do not miss the forest for the trees. The ultimate Investing OS goal is early
  retirement, not more data or a prettier feed. Social/reddit work should help
  identify asymmetric opportunities, risk warnings, or useful research prompts
  that improve capital decisions, risk control, time saved, or confidence in
  acting/not acting.

Scope:

- Work only on the Reddit/social lane.
- Keep it isolated from the main dashboard build unless the user explicitly
  asks to merge.
- Do not modify live action-promotion, reallocation, SnapTrade, cloud-routine,
  or core dashboard logic without explicit approval.
- Do not make social data a trade trigger. It is an early-signal/research lane
  that requires independent confirmation before any capital action.
- Keep missing social input dark/not_checked. Absence of Reddit/social data is
  not a no-signal read.

Desired output shape:

- Ranked social anomaly/research prompts.
- Each prompt should include:
  - ticker/topic
  - source type and timestamp
  - why it might matter
  - portfolio implication
  - confidence
  - decay speed
  - confirmation needed
  - blocker before action
  - suggested next research/check command

Implementation boundaries:

- Prefer staged/cache-only outputs such as `src/social_watch.json` or
  `tmp/social_watch_*.json` until the main build accepts the lane.
- Update or add focused tests for normalization, ranking, dark-lane handling,
  and no-trade-promotion guardrails.
- Do not commit secrets. Do not print API keys.
- Avoid scraping or policy-risky collection paths. Use compliant APIs,
  user-supplied exports, or staged manual cache files.
- If live API credentials are needed, ask where they are stored; do not invent
  them.

Acceptance for this separate workstream:

- A staged social lane can normalize supplied or API/cache data.
- It ranks useful prompts without promoting trades.
- It preserves dark/not_checked honesty when no data is available.
- Tests pass for the social lane.
- A merge note explains exactly what would need to change before the main
  cockpit should display the lane as more than dark/staged.

Recommended first task:

Audit `docs/reddit_feed_design.md` and `src/social_watch.py`, then propose the
smallest staged implementation slice that produces useful ranked social prompts
without touching the main Monday go-live build.

## Paused Critical-Minerals Prototype

The first later prototype should focus on `r/criticalmineralstocks` as a
staged/cache-only discovery lane because Meridian is stale/dead as current
critical-minerals and nuclear context after March 2026.

Read `docs/reddit_critical_minerals_prototype_plan.md` before implementing.
It records the OAuth/API-only intake plan, required dark-lane behavior, review
prompt contract, initial critical-minerals ticker/term universe, and resume
checklist.

Current staged implementation note:

- `src/reddit_collector.py --source-group critical_minerals_nuclear` selects the
  detachable `r/criticalmineralstocks` + `r/UraniumSqueeze` scout group and adds
  the critical-minerals/nuclear ticker universe.
- `src/reddit_collector.py --source-group retail_risk_wsb` selects a detachable
  WSB-only retail-risk scout group; keep it separate from the critical-minerals
  lane because it is high-noise crowding/risk evidence.
- `src/reddit_collector.py --source-group trump_trade_watch` selects a
  detachable `r/unusual_whales`-led scout for Trump/political-trade discussion.
  It is secondary to `src/political_trade_watch.py`, which captures UW
  political-disclosure rows into `src/political_trade_watch.json`.
- Keep outputs in `tmp/` until explicitly accepted:
  `python src/reddit_collector.py --source-group critical_minerals_nuclear --input <manual-snapshot.json> --out tmp/critical_minerals_social_watch.json --report-out tmp/reddit_daily_scout.md --weekly-report-out tmp/reddit_weekly_patterns.md --format text`.
- Manual/Chrome-visible snapshots can use simple rows with `subreddit`, `title`,
  `body` or `snippet`, `permalink` or `url`, visible time or `created_utc`,
  `score`, `comments` or `num_comments`, and `flair`. Do not store authors,
  copied raw comment archives, screenshots, cookies, credentials, or long raw
  Reddit text.
- Snapshot rows can also carry `members`, `online`, `source_sort`,
  `scan_window`, `captured_at`, `visible_rank`, and `subreddit_health` so source
  health can be classified before post usefulness is ranked.
- Source-health labels are `active`, `thin_but_current`, `stale`, and `fringe`.
  `stale` or `fringe` boards are link/catalyst scouts only, not sentiment or
  crowding evidence.
- Weekly pattern reports should surface recurring topics, louder/fading themes,
  cross-subreddit spread, counter-thesis/risk warnings, and destroy/noise.
- Missing/blocked fetches must stay `not_checked`.
- The main cockpit should display this lane as more than dark/staged only after
  the user explicitly accepts the source group, confirmation gates, and cache
  freshness behavior.
