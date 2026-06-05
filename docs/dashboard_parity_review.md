# Dashboard Parity Review

Generated: 2026-06-05

Last refreshed: 2026-06-05 after the dashboard decision grouping,
freshness/rationale, source-audit, asymmetric-opportunity, and Meridian archive
updates.

## Decision

The canonical dashboard path is the Contract-C FEED rendered through
`src/conviction_cockpit_v5.jsx`, with live data injected by
`src/render_cockpit.py`.

`docs/index.html` / `src/cockpit_html_gen.py` is a generated GitHub Pages
summary/export, not the canonical dashboard. It is useful as a lightweight
snapshot and now mirrors the core action, source-proof, event-watch,
opportunity, and missing-source context, but the canonical JSX remains the
operator cockpit for full detail.

Reason:

- `src/conviction_cockpit_v5.jsx` consumes a passed `feed` prop and falls back
  only to its baked example FEED.
- `src/render_cockpit.py` is the tested injection path for replacing the baked
  FEED with a live feed while preserving the renderer.
- `src/cockpit_html_gen.py` directly generates a smaller HTML dashboard. It now
  includes a summary/export caveat, grouped action cards with rationale
  drawers, lane-status counts/rows, Operator Status with active event watch,
  compact feedback-loop context, source proof/audits, asymmetric opportunities,
  capped Opportunity Context rows, and compact cards for research actions,
  fresh signals, Signal Log, and portfolio views when present.

## Current Feed Baseline

Local command used for parity evidence:

```powershell
python src\full_build_runner.py --src-dir src --feed-out tmp\dashboard_parity_feed.json
```

Result summary:

- Build succeeded.
- `actions`: 5
- `research_actions`: 0
- `lane_status.counts.not_checked`: 1
- Dark lane keys: `account_positions`.
- Action decision groups: Key Now 3, Important Backlog 2, Re-check Before
  Acting 0, Quiet Watch 0.
- Asymmetric opportunities: 8 deduped ticker rows.
- Source audits include cloud routine proof, connector evidence, Fundstrat
  intake, and Notion/writeback audit.
- Daily Synthesis is supplied from repo-evidence synthesis. It summarizes
  existing cockpit feed evidence and does not create structured action rows.
- Target Drift promotes the current held NVDA undersize into a conservative
  `conviction_gap` action; missing target names remain context-only.
- Event Risk is supplied and has data; one conservative exposure-review action
  is promoted from the oil/rates shock row.
- Operator Status derives the active event watch from the supplied Event Risk
  lane in both canonical JSX and the generated HTML summary. The go-live
  checklist also surfaces that same watch, and warns when no supplied active
  event watch exists.
- FS Daily is supplied and has data from compact full-body-derived Fundstrat
  rows; the richer raw-body parser remains preferred when safe connector JSON
  can be piped locally.
- Not-checked rows carry structured `next_step` and `missing_impact` guidance.
- Emitted feed keys: `generated_at`, `staleness`, `lane_status`, `hero`,
  `actions`, `fresh_signals`, `signal_log`, `event_risk`, `holdings`,
  `rotation`, `macro`, `catalysts`, `questions`, `research`,
  `research_actions`, `heartbeat`, `synthesis`, `radar`, `lean_in`,
  `bullish_flow`, `prospects`, `feedback`, `target_drift`,
  `action_decision_groups`, `asymmetric_opportunities`,
  `live_source_config`, and `source_audits`.
- Every emitted feed key was already classified in
  `docs/dashboard_feed_block_classification.json`.
- `portfolio_views` was absent in this local build because
  `account_positions.json` was not present/resolved for the run.

## Feed Block Parity

| Feed block | Producer / source path | JSX surface | Generated HTML surface | Status |
| --- | --- | --- | --- | --- |
| `generated_at` | `full_build_runner.py` / `assemble_feed` | Header stamp via `toCockpit` | Header stamp | Full in both |
| `staleness` | `collect` + `staleness_read` | Header stamp source dates | Header source line and stale warning | Full in both |
| `lane_status` | `build_lane_status` | Header dark/stale lane counters, lane status rows, and dark-lane next-step tooltips | Summary caveat plus lane-status counts, top rows, and next-step text | Partial in HTML; enough to avoid all-clear ambiguity |
| `hero` | `hero_needs_you_read` | Hero banner | Hero banner | Full in both |
| `actions` | `actions_read` + decision aging + promoted research/prospects | Today's Actions | Today's actions when non-empty; summary caveat when empty/dark | Full enough in HTML for summary/export use |
| `action_decision_groups` | `decision_support.enrich_actions` | Today's Actions grouped into Key Now, Important Backlog, Re-check Before Acting, and Quiet Watch | Grouped action sections with expandable rationale drawers | Full enough in HTML for summary/export use |
| `fresh_signals` | `fresh_signal_read` | Fresh signals / action context | Fresh Signals card when non-empty, capped to summary rows | Full enough in HTML for summary/export use |
| `signal_log` | Morning Scan convention file `signal_log.json` / `morning_signal_log.json` | Signal Log watch-only lane | Signal Log watch-only card when non-empty, capped to summary rows | Full enough in HTML for summary/export use |
| `event_risk` | Supplied Event Risk convention file `event_risks.json` / `event_risk.json` | Lane status plus promoted Today's Actions review prompts, active event-watch summary in Operator Status, and dark-lane next-step tooltip | Lane-status summary plus next-step text; promoted actions render in Today's actions; active event-watch summary appears in Operator Status | Partial in HTML; acceptable because actions are review-only and lane status carries not-checked honesty |
| `holdings` | Portfolio source + thesis reads | Book tab holdings with conviction/detail expanders | Book table | Partial in HTML because details are truncated |
| `rotation` | `rotation_read` | Market read and sleeve badges | Rotation table | Full enough in both |
| `macro` | `macro_read` | Market read macro panel | Macro panel | Full enough in both |
| `catalysts` | Catalyst intake -> `runtime_adapters` -> `catalyst_needs_you` | Upcoming catalysts and action promotion | Catalyst list only when non-empty | Partial in HTML because empty/not-checked distinction is weak |
| `questions` | Currently emitted empty by assembler | Static `CURATED.questions` only | Not rendered | Static/unwired in JSX, missing in HTML |
| `research` | Research queue intake | Research panel with live fallback, else curated fallback | Pending research only | Partial in both; JSX has fallback, HTML omits completed/significant findings |
| `research_actions` | `research_actions_read` + ACT_NOW promotion | From Research lane | From Research card when non-empty, using action-card summary rendering | Full enough in HTML for summary/export use |
| `heartbeat` | Routine status cache | Heartbeat strip | System layers strip | Full enough in both, but HTML lacks lane-status relationship |
| `synthesis` | Daily synthesis cache | Synthesis panel | Today's read | Full enough in both |
| `radar` | Fundstrat daily endorsed-not-owned calls | Radar lane | Opportunity Context summary, capped top rows | Partial in HTML |
| `lean_in` | `lean_in_read` | Lean In lane and promotion source | Lean-in watchlist | Partial in HTML because gate/detail fields are thinner |
| `bullish_flow` | UW opportunity cache | Bullish flow lane | Opportunity Context summary, capped top rows | Partial in HTML |
| `prospects` | Top prospects cache | Top Prospects lane and action promotion | Opportunity Context summary, capped top rows | Partial in HTML |
| `asymmetric_opportunities` | `decision_support.build_asymmetric_opportunities` | Asymmetric Opportunities lane | Asymmetric Opportunities card, one deduped row per ticker | Full enough in HTML for summary/export use |
| `feedback` | `feedback_summary.py` | Feedback loops panel | Compact feedback lines and recommendations | Partial in HTML; detailed rows remain canonical JSX |
| `target_drift` | Reallocation target model versus actual holdings | Target Drift panel | Opportunity Context summary, capped top rows | Partial in HTML |
| `portfolio_views` | `account_positions.json` -> `portfolio_views.py` | Book tab account views plus effective ETF look-through estimates when present | Portfolio Views card when account-position views are present | Summary only; full account diagnostics remain canonical JSX |
| `live_source_config` | `live_source_capability.py` / `live_source_config.json` | Operator Status live-fetch configuration pill and warning panel | Operator Status live-fetch configuration pill and warning panel | Full enough in HTML for summary/export use |
| `source_audits` | `full_build_runner._build_source_audits` | Source Proof panel | Source proof and audits card | Full enough in HTML for summary/export use |

## Static, Sample, Or Stale Surfaces

- `src/conviction_cockpit_v5.jsx` contains a baked FEED literal dated
  2026-05-29. That literal is sample data only; it is not current dashboard
  state.
- `src/render_cockpit.py` is the correct way to replace that baked sample with a
  live feed.
- `docs/index.html` is a static generated artifact. Its current checked-in
  header shows the latest committed generated build stamp, but it only updates
  when regenerated and committed/published.
- `CURATED.questions` in JSX is still static. The assembler emits
  `questions: []`, and the UI still reads the curated fallback instead of live
  feed questions.
- `CURATED.research` remains a JSX fallback when the feed has no research rows.
  This is useful for old feeds, but it can blur "not checked" versus "empty" if
  lane status is ignored.
- `src/feed_to_cockpit.js` is a tested mapper for the older common subset, but
  the JSX renderer has grown additional inline mapping for newer blocks. That is
  a coverage drift risk.

## Duplicate Or Overlapping Surfaces

- `actions` and `research_actions` intentionally duplicate the action-card row
  shape but remain separate surfaces. This is good because Today's Actions keep
  rank priority while From Research keeps research provenance visible.
- `fresh_signals`, `lean_in`, `prospects`, `catalysts`, and `feedback` can all
  promote or explain action pressure. This is acceptable if the top strip stays
  ranked and the supporting lanes remain visibly separate.
- `signal_log` is deliberately watch-only external context. It can explain why a
  name deserves attention, but it must not promote directly into `actions`
  without a sharper action source.
- `event_risk` is deliberately supplied-data-only external context. High and
  critical rows can promote into `actions`, but only as exposure-review prompts;
  no buy/sell order is implied. When it is dark, lane status now tells the
  operator to supply the daily/weekly Event Risk scan for sudden war, oil,
  rates, policy, or volatility shocks. Operator Status and the go-live
  checklist now derive an active event-watch summary from the supplied rows, but
  they do not create or fetch events.
- `heartbeat` and `lane_status` overlap operational health. `heartbeat` says
  which routines ran; `lane_status` says which data lanes were checked, stale,
  failed, or dark. Both should stay; generated HTML now mirrors lane-status
  counts/top rows as summary context.
- Operator Status is a derived readiness surface, not a separate feed block.
  It must remain sourced from existing `actions`, `feedback.open_actions`, and
  `lane_status` health in both canonical JSX and generated HTML. Active
  event-watch text is the one Event Risk detail allowed in Operator Status
  because it is directly sourced from `feed.event_risk` and makes sudden-event
  workflow status visible.
- `docs/index.html` duplicates a subset of the JSX dashboard. It mirrors the
  main action/source-proof surfaces now, but it is still a summary/export path
  and should not become the only surface for new operator meaning.
- The command/navigation tab in generated HTML is static utility content, not a
  feed-backed dashboard surface.

## Missing Surfaces That Can Block Action Clarity

Highest impact gaps:

- HTML now shows `lane_status` summary counts/top rows and dark-lane next-step
  guidance, but the canonical JSX remains the full source for lane diagnostics.
- HTML now shows compact `feedback` lines and recommendations, but detailed
  source-call rows and clusters remain canonical JSX.
- HTML now shows capped Opportunity Context rows for `prospects`,
  `bullish_flow`, `radar`, and `target_drift`, plus research actions,
  asymmetric opportunities, fresh signals, Signal Log, and portfolio views
  when those blocks are present. Detailed lane diagnostics remain canonical JSX.
- HTML now shows a summary/export caveat. `actions: []` plus dark lanes should
  no longer read as "all clear."
- JSX questions are static/unwired. This is lower priority than action lanes,
  but it is still not feed-backed.

## Canonical Path Rule

Future dashboard work should target this order:

1. FEED contract and validation in Python.
2. `src/conviction_cockpit_v5.jsx` rendering of the feed block.
3. `src/render_cockpit.py --selftest` and focused tests.
4. Generated HTML only as a summary/export path after the canonical JSX surface
   is correct.

Do not add new operator meaning only to `docs/index.html`. If the generated page
needs a feature, add or confirm the canonical JSX surface first, then decide
whether the HTML summary should mirror it.

## Minimal Next Slice

Recommended next implementation slice:

Run next-slice discovery from the completion audit rather than starting more UI
work. The old canonicalization guardrail and previously queued product slices
are complete; current parity evidence says the dashboard contract is classified
and the canonical JSX path remains the operator surface.

No stale dashboard-specific follow-up is promoted from this parity review. Next
dashboard work should come from fresh feed evidence or a new completion audit.
