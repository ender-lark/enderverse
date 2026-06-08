# Monday Go-Live Build Plan

Status: active source-of-truth plan for the Investing OS v1 go-live build.

Notion mirror:
`https://app.notion.com/p/378c50314bb681afb39bcb82efce9d47`

Repo/GitHub docs are the implementation source of truth. Notion is the readable
mirror for future rebuilds, upgrades, and troubleshooting.

## Primary Goals

- Do not miss the forest for the trees: the ultimate goal is early retirement,
  not a prettier dashboard or more data. Every build, design, and operating
  choice should improve capital decisions, risk control, time saved, or
  confidence in acting/not acting.
- Surface every important decision that matters, while making today's key items
  especially hard to miss.
- Give the recommendation, rationale, evidence freshness, decay speed, and what
  could invalidate the action.
- Keep missing or stale source lanes honest as dark, stale, or not checked.
- Continuously synthesize sources so the user does not have to monitor
  everything manually.
- Automatically surface asymmetric opportunities only when they have
  evidence-backed review prompts.
- Optimize for efficient use of capital without overfitting market timing or
  missing major up days.

## Operating Protocol

- Test and validate on the canonical local JSX cockpit:
  `http://127.0.0.1:8765/cockpit_jsx_preview.html`.
- Treat generated HTML and GitHub Pages as mirror/export surfaces until v1 is
  finalized.
- Store source-of-truth implementation state in repo docs first, then mirror
  important material to Notion when useful.
- Capture both misses and improvements as reusable implementation learnings.
  This is not only an error-prevention rule; it is how the system should
  compound what worked.
- Commit after each clean verified slice.
- Keep cloud proof on natural schedule unless the user explicitly asks to
  accelerate again.
- Keep Reddit/social queued and dark until the rest of the system is working.
- Keep `ANET` and `GOOGL` open until explicitly resolved.

## User Decisions Captured

- Dashboard default: use the JSX cockpit by default during v1 testing. Do not
  show the HTML preview as the primary dashboard unless explicitly checking
  parity/export.
- First screen: show portfolio impact, blunt blockers, Key Now, and top
  Re-check Before Acting items first. The rest of the backlog should be
  collapsible.
- Sections: every major cockpit section should be minimizable. Mostly-green
  layers/checks should not consume prime screen space.
- Macro/risk: do not show rates, oil, or volatility as raw standalone
  distraction. Compact them into a "what this means for my portfolio/actions"
  read.
- Book: default to the combined household portfolio first. Account/category
  drilldowns should be available behind it.
- Allocation guidance: show working-model target allocation and Fundstrat
  category cues next to current exposure as guidance, not as an instruction to
  follow.
- Positions: SnapTrade is the preferred live read-only position source after
  staged validation. Old PDF/text extraction stays as backup.
- Taxes: ignore tax optimization for v1 planning.
- Options: allow only simple, defined-risk, review-only alternatives when they
  are clearly useful. Do not force options recommendations.
- Alerts: only for blockers or urgent invalidation, not routine dashboard
  updates.
- Research/social: Reddit/social feed stays queued and dark until the core
  system works.

## Detailed Build Order

1. Stage 0 continuity.
   - Save the full plan in repo docs and Notion.
   - Update `docs/codex_new_chat_handoff.md`,
     `docs/codex_build_queue.md`, and architecture docs.
   - Make GitHub/repo docs the implementation source of truth and Notion the
     readable mirror.

2. Stage 1 cockpit usability.
   - Make the JSX cockpit the default status/checklist/command target.
   - Add persistent minimizable sections.
   - Collapse status/check strips by default.
   - Add compact portfolio-impact event/risk summary.
   - Keep backlog, re-check, and important sections accessible but not
     screen-clogging.

3. Stage 1.5 synthesis quality.
   - Audit synthesis output for usefulness, not just data availability.
   - Convert raw facts into action implications wherever possible.
   - Require every promoted synthesis item to say what it changes:
     `act`, `wait`, `re-check`, `research`, `trim`, `hedge`, `size`, or
     `no capital yet`.
   - Reuse the existing action-row shape for useful synthesis: goal impact,
     time window, capital effect, missing evidence, freshness, disconfirmation,
     and capital efficiency.
   - Add source-conflict handling that shows bull/bear reads and resulting
     action posture.
   - End every conflict read in a decision group: `Key Now`,
     `Re-check Before Acting`, `Important Backlog`, or `Quiet Watch`.
   - Pull capital efficiency into synthesis ranking so a merely good idea loses
     priority to a better use of capital, downside protection, or a
     higher-conviction sizing gap.
   - Strengthen assumption-refresh logic so old actions can become invalid,
     recheck-first, or lower priority when price/source/risk context changes.

4. Stage 2 Book and allocation.
   - Add working-model targets and gaps to category views.
   - Add Fundstrat category cues with source dates and caveats.
   - Keep combined household first, then owner/account drilldowns.
   - Ensure options valuation stays correct and option notional/market value
     semantics are unambiguous.

5. Stage 3 capital-efficiency/action validity.
   - Prioritize better uses of capital over merely good opportunities.
   - Show consequence of doing nothing and risk of over-waiting.
   - Require same-session price/flow/source gates for capital-sized action.
   - Keep all promoted outputs as review prompts, not execution.

6. Stage 4 ops, alerts, and proof.
   - Continue source-proof, connector-evidence, Fundstrat audit, Notion
     writeback audit, and SnapTrade validation surfaces.
   - Add blocker-only alerting after the dashboard is stable.

7. Stage 5 optional upgrades. [don't execute]
   - Reddit/social feed and escalation workflow.[working on in parallel chat]
   - Deeper source-conflict scoring.
   - More visual allocation/target charts.
   - Faster live-check buttons/runbooks.
   - Additional Notion writeback automation.

## Stage 0 - Source of Truth and Continuity

- Save this plan in repo docs and Notion.
- Update the new-chat handoff and build queue so a new chat can resume from
  files.
- Make the JSX cockpit the default operator/testing surface in status and
  command surfaces.
- Keep the repo docs current as the plan changes; do not rely on chat memory for
  project state.

## Stage 1 - Core Cockpit Usability

- Make every major section minimizable, with persistent open/closed state where
  possible.
- Collapse mostly-green status layers and checks by default.
- Keep the first screen focused on portfolio impact, blockers, and top
  urgent/recheck items.
- Show full backlog in expandable sections, not as a wall of items.
- Make blocker language blunt: do not act, why, and what check unblocks.
- Compact rates, oil, volatility, and other macro feeds into a portfolio-impact
  read: what it means for sizing, timing, hedge, hold/add/trim, or research
  priority.

## Stage 1.5 - Synthesis Quality Review

- Reconsider how cloud routines, local feed builders, and dashboard renderers
  synthesize information before adding more surface area.
- Hard usefulness contract: every promoted synthesis item must say what it
  changes: `act`, `wait`, `re-check`, `research`, `trim`, `hedge`, `size`, or
  `no capital yet`. If it does not change one of those, collapse it into
  context instead of surfacing it as an action.
- Emit structured action implications, not just better prose. Useful synthesis
  should reuse the action-row contract already used by the cockpit:
  recommendation/action state, goal impact, time window, capital effect,
  missing evidence, freshness/decay, disconfirmation, capital efficiency, and
  assumption refresh.
- Add an explicit usefulness filter: if a fact does not affect action, timing,
  sizing, risk, hedge, hold/add/trim, or research priority, collapse or
  deprioritize it.
- Show bull and bear/source-conflict views where disagreement matters, then
  translate them into action implications.
- Bull/bear conflict outcome ladder: every conflict view must end in one of
  `Key Now`, `Re-check Before Acting`, `Important Backlog`, or `Quiet Watch`.
  A conflict panel without action posture is not useful enough to promote.
- Capital-efficiency ranking belongs in synthesis, not only explanation. A good
  opportunity should lose priority to a better current use of capital, downside
  protection, or a higher-conviction sizing gap.
- Refresh or invalidate action assumptions when price, source, thesis, or risk
  context changes.
- Keep candidate actions separate from execution.
- Acceptance scenarios:
  - A stale Friday action after a Monday price move becomes `re-check`,
    invalidated, or lower priority instead of staying blindly actionable.
  - Missing Social Watch remains dark/not checked and never becomes a no-signal
    read.
  - Conflicted Fundstrat/live-tape evidence becomes watch/research/re-check, not
    buy.
  - The top action shows freshness, invalidation trigger, consequence of doing
    nothing, and the reason it beats other current uses of capital.

## Stage 2 - Book and Allocation Usability

- Default to combined household view first, with Parents/SKB/account drilldowns
  behind it.
- Add account view by category with target allocation guidance from the working
  model.
- Show Fundstrat category cues next to current exposure as visual guidance, not
  as an instruction to follow.
- Keep old PDF/manual position intake as fallback, but prefer SnapTrade once
  strict staged validation passes.
- Ignore taxes for this v1 planning layer.

## Stage 3 - Action Validity and Assumption Refresh

- Important actions must have a refresh path.
- If a Friday action was based on a low price and Monday price spikes, the
  action should become invalid, recheck-first, or lower priority rather than
  staying blindly actionable.
- Each promoted action should carry key assumptions, last checked time,
  evidence date, freshness label, and invalidation triggers.

## Stage 4 - Opportunity and Capital Efficiency

- Prioritize opportunities by asymmetric payoff, evidence quality, time
  sensitivity, and sizing gap.
- Compare good opportunities against better current uses of capital.
- Balance efficient capital allocation with the risk of over-timing and missing
  major up days.
- Options may appear only as simple, defined-risk, review-only alternatives when
  useful; do not force options recommendations.

## Stage 5 - Alerts and Ops

- Alerts should fire only for blockers or urgent invalidation, not routine
  dashboard content.
- Keep cloud routine proof honest: scheduled success only counts from real
  scheduled receipts.
- Keep source lanes honest: dark/not-checked data cannot be treated as checked
  clear.
- Keep Meridian as stale thesis archive context after March 2026, not fresh
  tactical evidence.

## Separate-Chat Workstream: Reddit/Social Feed

Reddit/social remains queued and dark in the main cockpit until the core system
is stable. A separate chat can work on discovery and design if it follows these
boundaries:

- Do not modify live dashboard, action-promotion, or trading-decision logic
  without an explicit merge request back into the main build chat.
- Build in a small isolated slice around `src/social_watch.py`,
  `docs/reddit_feed_design.md`, focused tests, and staged/cache-only outputs.
- Social evidence is an early-signal lane only. It cannot promote buy/sell
  actions without independent price/source/thesis confirmation.
- Missing social data must remain `not_checked` or dark; absence of Reddit data
  is never a no-signal read.
- Output should be ranked review prompts with why it matters, source/time,
  confidence, decay speed, confirmation needed, and portfolio implication.
- Any live API work must avoid scraping policy problems and must not expose or
  commit secrets.

## Acceptance

- `python src/verify_standard.py` passes.
- Browser check uses the JSX cockpit first.
- Dashboard shows grouped decisions, compact portfolio-impact synthesis,
  collapsible sections, action freshness/rationale, source honesty, Book
  allocation guidance, and current useful commands.
- Stage 1.5 usefulness is proven by structured action implications and
  acceptance tests for stale-action recheck, dark social lane honesty,
  conflict-to-watch/research posture, and capital-priority ranking.
- Repo docs and Notion mirror are updated so a new chat can continue without
  losing the plan.
