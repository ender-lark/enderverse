# Investing OS External Review Prompt

Last updated: 2026-06-07.

## Project Goal

The Investing OS should continuously synthesize the user's investing sources and
surface all important buy, sell, hold, hedge, research, and reallocation decisions
that matter. Some days there may be no action; on volatile days there may be many.
The dashboard should surface key time-sensitive decisions extra hard, while still
keeping the full important backlog visible, rationalized, and auditable.

The core user constraint is scarce attention. The system must monitor sources,
detect high-impact asymmetric opportunities or risks, explain why the recommendation
matters, show how fresh the evidence is, and avoid implying that missing or stale
data is checked clear.

## Current System Snapshot

- Canonical repo: `ender-lark/enderverse`.
- Canonical UI: `src/rendered/conviction_cockpit_v5.jsx`; HTML is a summary/export
  mirror, not the source of truth.
- Live dashboard: `https://ender-lark.github.io/enderverse/`.
- Current cockpit has grouped action lanes: Key Now, Important Backlog, Re-check
  Before Acting, and Quiet Watch.
- Action cards include freshness/rationale fields: evidence date, last checked,
  decay speed, freshness label, and why the recommendation still matters.
- Opportunity lane dedupes Radar, Lean-In, Prospects, target drift, and bullish flow
  into evidence-backed asymmetric review prompts.
- Source/audit panels include cloud routine status, connector evidence, Fundstrat
  intake audit, Notion writeback audit, Meridian archive handling, and Notion
  collision risk.
- Meridian is stale thesis archive only. It can inform thesis context, but must not
  count as fresh tactical evidence.
- Cloud routine proof is background monitoring. Missing natural scheduled receipts
  are audit items, not foreground build blockers unless they are overdue or failed.
- Existing reallocation engine is candidate-only and does not place trades.
- The Market-Open Packet now sits above Today's Actions. It sequences re-check
  work, Key Now gating, reallocation blockers, UW check sets, dark lanes, and
  open reviews so scarce morning attention goes to the right next action.
- Reddit/social is a watch-only dashboard lane backed by a normalized cache shape;
  the repo still does not fetch Reddit live data until compliant OAuth/API intake
  is added. Missing Social Watch is visible as `not_checked`, not as "no signal."
- Existing Unusual Whales endpoint catalog prevents common hallucinated endpoint
  paths. Scenario-specific routing now exists in `src/uw_endpoint_router.py` and
  dashboard runbooks now activate profiles such as pre-market crash triage,
  event-risk macro, portfolio reallocation, Fundstrat confirmation, asymmetric
  discovery, post-close review, and Reddit-signal vetting.
- Current live build after commit `09058cd`: go-live ready, publish ready, live
  data ready; 4 actions, 2 open reviews, 1 dark lane (`social_watch`), and no
  build blockers. Standard verification passed with 1078 tests and 6 skipped.

## High-Level Reassessment

The system is much closer to an operator cockpit than a static portfolio report.
It now shows important decisions and audit state instead of hiding dark lanes. The
next constraint is not more data volume; it is better routing, prioritization, and
interaction design during high-volatility periods.

Highest-value gaps:

1. UW endpoint utilization has a routing map, but the next gap is proof and
   result capture: after a runbook says which endpoints to use, the system should
   know which endpoint results actually landed, their timestamps, and whether
   they confirmed or contradicted the action.
2. Dashboard interaction still needs more operator compression. The user should be
   able to answer: what changed, what matters now, why, how fresh, what disconfirms
   it, what condition would flip it, and what action is blocked by missing evidence.
3. Reallocation should become a first-class workflow. It should take current account
   positions, current source state, thesis strength, drawdown/risk, Fundstrat calls,
   UW confirmation, and funding constraints, then output candidate trim/add/hold
   plans with timing and disconfirmation.
4. Reddit/social should remain watch-only early-signal intake. It can propose
   things to vet, but should not promote trades without independent confirmation.
5. Disconfirmation needs to be explicit. Every Key Now action should show the fastest
   way it could be wrong, the evidence that would invalidate it, and the trigger
   that changes the recommendation.
6. Market-open crash triage should be first-class during high-volatility regimes:
   broad tape, factor pressure, owned-name flow, dealer/volatility context, and
   live price state should be checked before single-name conviction dominates.
7. Stale-action cleanup needs an operating ritual. After a volatile backlog build-up,
   the system should run a one-time review to expire old prompts, downgrade stale
   opportunities, and keep open ANET/GOOGL-style reviews visible without treating
   them as build blockers.

## Prompt For Claude Or Gemini

Use this prompt verbatim when asking another model to critique or improve the
system:

```text
You are reviewing an investing decision-support system for a user whose primary
constraint is scarce attention and whose goal is early-retirement impact through
high-conviction, asymmetric opportunities while avoiding catastrophic risk.

System description:
- The system is an Investing OS built around a canonical GitHub repo
  (`ender-lark/enderverse`) and a live dashboard called Conviction Cockpit.
- It ingests/synthesizes Fundstrat, Unusual Whales, broker/account positions,
  market/macro data, catalysts, Notion research queues, source-call calibration,
  and watch-only social/research signals.
- It does not execute trades. It surfaces review prompts and candidate actions:
  buy/add, sell/trim, hold, hedge, research, re-check, or quiet watch.
- Dashboard action groups are Key Now, Important Backlog, Re-check Before Acting,
  and Quiet Watch.
- Every promoted action should explain why it matters, evidence date, last checked,
  decay speed, freshness label, rationale, disconfirmation, and what condition
  would change the recommendation.
- Missing/stale lanes must remain visible. Missing data must never be treated as
  checked clear.
- Meridian is archived thesis context only, stale after March 2026, and cannot count
  as fresh tactical evidence.
- Fundstrat calls are important but must be time-stamped and checked against current
  market/flow evidence before time-sensitive action.
- Unusual Whales data should be routed by scenario, not queried as one generic bundle:
  crash triage, Fundstrat confirmation, asymmetric discovery, portfolio reallocation,
  post-close review, event-risk macro, and Reddit-signal vetting.
- Reddit, if added, should be a watch-only early-signal module using compliant API
  access and independent confirmation before anything reaches an action lane.
- The user may have no time to inspect long lists. The dashboard should compress
  complexity into the few decisions that matter now while preserving an expandable
  audit trail.
- The current urgency is preparing for the next market open after a fast AI/crypto
  drawdown where delayed Fundstrat sell-signal handling caused real portfolio pain.
- Current dashboard state: 4 actions, including one Re-check Before Acting event
  risk row and one Key Now NVDA sizing-gap row; 2 fresh open reviews (ANET/GOOGL);
  Social Watch dark; reallocation candidate brief remains test-data-only until
  current positions are supplied.
- The Market-Open Packet should be treated as the first operator surface:
  re-check fast-moving event risk, gate Key Now, unblock current positions, run
  UW check sets, keep dark lanes visible, then resolve open reviews.

Please critique this system and propose improvements.

Questions to answer:
1. What are the most likely ways this system could produce harmful false confidence?
2. What explicit disconfirmation checks should exist before any Key Now action is
   promoted?
3. What dashboard interaction design would best help a busy user act on only the
   highest-impact decisions while still seeing all important backlog items?
4. How should Unusual Whales endpoints be routed by scenario, and what endpoint
   groups or result-capture proofs are missing from the current design?
5. How should a portfolio reallocation workflow rank trim/add/hold/hedge candidates
   using current positions, Fundstrat, UW, source-call history, catalysts, and risk?
6. How should Reddit or other social feeds be used without creating pump/chase risk?
7. What should the system do differently during high-volatility regimes versus quiet
   regimes?
8. What one-time stale-action cleanup should run before Monday's open?
9. What are the top five implementation changes that would most improve decision
   quality before market open?
10. What should the system refuse to do or downgrade automatically because the data
    is stale, missing, contradictory, or too noisy?

Output format:
- Start with the biggest failure modes.
- Then list highest-value system changes in priority order.
- Then give a proposed dashboard layout/interaction model.
- Then give a UW endpoint-routing matrix.
- Then give a reallocation workflow.
- Then give a Reddit/social-feed design.
- Keep trade execution out of scope; all outputs are review prompts or candidate
  actions only.
```

## Immediate Improvement Priorities

1. Use `src/uw_endpoint_router.py` and `src/uw_action_runbook.py` as the canonical
   scenario routing map for UW endpoint selection, then add endpoint-result proof
   so the dashboard knows what actually ran.
2. Add a dashboard affordance for "what would invalidate this?" on every Key Now
   and Re-check Before Acting item.
3. Run a stale-action cleanup pass before Monday open: expire old prompts, downgrade
   stale opportunities, and keep fresh unresolved reviews visible without warning
   severity inflation.
4. Add portfolio reallocation mode that waits for latest positions, then ranks
   candidate legs by impact, risk, time sensitivity, thesis strength, source
   confirmation, and funding constraints.
5. Add Reddit API intake only as watch-only anomaly detection feeding the existing
   Social Watch lane, Research Queue, or Quiet Watch unless UW/Fundstrat/news
   confirmation exists.

## Clarifying Questions For The User

These improve the reallocation plan but should not block other build work:

1. Are options or defined-risk hedges allowed, or should the plan be equity/ETF only?
2. Any tax/account restrictions, such as no realizing gains in taxable accounts?
3. What is the maximum number of actions the user can realistically review Monday
   morning?
4. Should BMNR/crypto be treated as a long-term thesis to defend, a tactical exposure
   to reduce, or undecided until fresh evidence arrives?
5. What is the maximum acceptable single-name and AI-factor concentration after
   reallocation?
