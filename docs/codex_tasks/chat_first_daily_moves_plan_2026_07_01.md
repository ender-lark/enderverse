# Chat-First Daily Moves Plan - 2026-07-01

Notion mirror: https://app.notion.com/p/390c50314bb681bd9946d4050a9a0951

## Mission

Make Investing OS answer the operator's common chat question, "What should I do today?", with the same rigor as the dashboard. The answer must rank defensive moves first, then opportunity candidates, options expressions, Trump/social watch signals, push-worthy alerts, blockers, and dark/not-checked lanes.

The packet must be built from the canonical feed, not from a separate chat memory or branch-local collector. It should be reusable by chat, dashboard, and alert policy.

## Current Findings

- Canonical runtime is `C:\Users\suraj\Documents\Codex\2026-06-24\automation-runtime-main` on `main`.
- `social_watch.py` already normalizes `social_watch.json`, `reddit_watch.json`, or `reddit_signals.json`, but the canonical producer is still missing. Social Watch remains dark/not_checked in the live feed when no cache is supplied.
- `r/TrumpsTrades` was added to the separate Reddit collector workflow, but canonical main needs a normalized bridge before that signal can affect daily recommendations.
- `options_surface.py` and `full_build_runner.py` already surface options expressions from `options_chain_cache.json`.
- `options_chain_refresh.py` already supports the wider doctrine universe through `doctrine_extra`, `priority`, `universe_coverage`, and `target_expiries`, but the routine manifest still prints a thesis-only cap-16 command.
- `if_i_were_you` exists, but it is a Fundstrat/dashboard block. It is not a direct chat-first "do this today" artifact.

## Red-Team Plan

### 1. Operator Chat UX

Risk: The dashboard can be right while chat remains generic or misses the strongest move.

Mitigation:
- Add `src/today_recommendation_brief.py`.
- Produce both JSON and text.
- First line must answer directly: act, defend/recheck, or stand down.
- Feed block should include defensive, opportunity, options, social, alerts, blockers, not_checked, and commands.

### 2. Portfolio Risk And Survival Rails

Risk: Cash pressure turns options into undisciplined leverage.

Mitigation:
- Defensive/recheck rows outrank new-risk rows.
- Options rows must show max loss/risk, IV/catch, DTE/expiry when present, and keep "defined risk only" visible.
- Missing or stale source data must say not_checked instead of reading as clear.

### 3. Data And Source Architecture

Risk: Reddit collector scans one branch while canonical main still says Social Watch is dark.

Mitigation:
- Canonical main consumes only normalized `social_watch.json` shapes.
- `r/TrumpsTrades` and future Reddit snapshots remain watch-only until independent confirmation exists.
- Prefer Unusual Whales news/Truth Social metadata for direct Trump/market-moving post capture when available, with Reddit as corroboration and crowd-amplification context.

### 4. UW Endpoint And Options Edge

Risk: A narrow endpoint set misses asymmetric opportunities or overweights noisy flow.

Mitigation:
- Use stock screener, option chains, option-contract screener, option trades, flow alerts, lit flow, dark pool, Greek/GEX, news/Truth Social flags, congress/politician, correlations, and optional prediction/crypto context according to evidence weight and availability.
- Treat Advanced/websocket-only endpoints as optional/tier-gated until proven.
- Update the manifest command to use held names, top prospects, lean-in/watch names, priority-down names, and multi-expiry targets.

### 5. Automation, Alerts, And Feedback

Risk: Good rows land in JSON but do not interrupt the operator or feed back outcomes.

Mitigation:
- Add review-only `push_candidates` metadata to the daily brief.
- Actual sending remains gated through existing alert/Pushover routines after quality is validated.
- Keep outcome/shadow logging as a follow-up rather than adding noisy writes in this first slice.

## Build Slices

1. Ship the chat-first daily recommendation packet and feed/dashboard/CLI wiring.
2. Align `options_chain_refresh` routine manifest with the already-shipped wider universe functions.
3. Document UW endpoint roles and tier gates.
4. Add a canonical social snapshot intake bridge for `r/TrumpsTrades` and UW Truth Social/news snapshots.
5. Expand review-only alert policy into actual push candidates only after brief quality is proven.

## Acceptance Criteria

- `latest_cockpit_feed.json` includes `today_recommendation_brief`.
- `python src/today_recommendation_brief.py --feed src/latest_cockpit_feed.json --format text` gives a direct "today" answer.
- If options/social are absent, the brief says not_checked/dark, not clear.
- If options ACT rows are present, they are surfaced with max loss and catch.
- Social/Trump rows are surfaced as watch-only unless independently confirmed.
- Dashboard summary renders the new packet.
- Focused tests and standard verification pass, or any unrelated blocker is named exactly.
