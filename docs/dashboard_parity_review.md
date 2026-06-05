# Dashboard Parity Review

Generated: 2026-06-05

Last refreshed: 2026-06-05 after the repo-evidence Daily Synthesis refresh.

## Decision

The canonical dashboard path is the Contract-C FEED rendered through
`src/conviction_cockpit_v5.jsx`, with live data injected by
`src/render_cockpit.py`.

`docs/index.html` / `src/cockpit_html_gen.py` is a generated GitHub Pages
summary, not the canonical dashboard. It is useful as a lightweight public
snapshot, but it currently omits too many live feed blocks to be trusted as the
operator cockpit.

Reason:

- `src/conviction_cockpit_v5.jsx` consumes a passed `feed` prop and falls back
  only to its baked example FEED.
- `src/render_cockpit.py` is the tested injection path for replacing the baked
  FEED with a live feed while preserving the renderer.
- `src/cockpit_html_gen.py` directly generates a smaller HTML dashboard. It now
  includes a summary/export caveat, lane-status counts/rows, and compact
  feedback-loop context, but it still omits newer action-clarity blocks such as
  `research_actions`, `bullish_flow`, `prospects`, `radar`, or
  `portfolio_views`.

## Current Feed Baseline

Local command used for parity evidence:

```powershell
python src\full_build_runner.py --src-dir src --feed-out tmp\dashboard_parity_feed.json
```

Result summary:

- Build succeeded.
- `actions`: 3
- `research_actions`: 0
- `lane_status.counts.not_checked`: 2
- Dark lane keys: `catalysts`, `signal_log`.
- Daily Synthesis is supplied from repo-evidence synthesis. It summarizes
  existing cockpit feed evidence and does not create structured action rows.
- Event Risk is supplied and has data; one conservative exposure-review action
  is promoted from the oil/rates shock row.
- FS Daily is supplied and has data from compact full-body-derived Fundstrat
  rows; the richer raw-body parser remains preferred when safe connector JSON
  can be piped locally.
- Not-checked rows carry structured `next_step` and `missing_impact` guidance.
- Emitted feed keys: `generated_at`, `staleness`, `lane_status`, `hero`,
  `actions`, `fresh_signals`, `signal_log`, `event_risk`, `holdings`,
  `rotation`, `macro`, `catalysts`, `questions`, `research`,
  `research_actions`, `heartbeat`, `synthesis`, `radar`, `lean_in`,
  `bullish_flow`, `prospects`, `feedback`, `target_drift`
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
| `fresh_signals` | `fresh_signal_read` | Fresh signals / action context | Not rendered as its own lane | Missing in HTML |
| `signal_log` | Morning Scan convention file `signal_log.json` / `morning_signal_log.json` | Signal Log watch-only lane | Not rendered | Missing in HTML; acceptable because it is watch-only context |
| `event_risk` | Supplied Event Risk convention file `event_risks.json` / `event_risk.json` | Lane status plus promoted Today's Actions review prompts and dark-lane next-step tooltip | Lane-status summary plus next-step text; promoted actions render in Today's actions | Partial in HTML; acceptable because actions are review-only and lane status carries not-checked honesty |
| `holdings` | Portfolio source + thesis reads | Book tab holdings with conviction/detail expanders | Book table | Partial in HTML because details are truncated |
| `rotation` | `rotation_read` | Market read and sleeve badges | Rotation table | Full enough in both |
| `macro` | `macro_read` | Market read macro panel | Macro panel | Full enough in both |
| `catalysts` | Catalyst intake -> `runtime_adapters` -> `catalyst_needs_you` | Upcoming catalysts and action promotion | Catalyst list only when non-empty | Partial in HTML because empty/not-checked distinction is weak |
| `questions` | Currently emitted empty by assembler | Static `CURATED.questions` only | Not rendered | Static/unwired in JSX, missing in HTML |
| `research` | Research queue intake | Research panel with live fallback, else curated fallback | Pending research only | Partial in both; JSX has fallback, HTML omits completed/significant findings |
| `research_actions` | `research_actions_read` + ACT_NOW promotion | From Research lane | Not rendered | Missing in HTML |
| `heartbeat` | Routine status cache | Heartbeat strip | System layers strip | Full enough in both, but HTML lacks lane-status relationship |
| `synthesis` | Daily synthesis cache | Synthesis panel | Today's read | Full enough in both |
| `radar` | Fundstrat daily endorsed-not-owned calls | Radar lane | Not rendered | Missing in HTML |
| `lean_in` | `lean_in_read` | Lean In lane and promotion source | Lean-in watchlist | Partial in HTML because gate/detail fields are thinner |
| `bullish_flow` | UW opportunity cache | Bullish flow lane | Not rendered | Missing in HTML |
| `prospects` | Top prospects cache | Top Prospects lane and action promotion | Not rendered | Missing in HTML |
| `feedback` | `feedback_summary.py` | Feedback loops panel | Compact feedback lines and recommendations | Partial in HTML; detailed rows remain canonical JSX |
| `portfolio_views` | `account_positions.json` -> `portfolio_views.py` | Book tab account views plus effective ETF look-through estimates when present | Not rendered | Missing in HTML |

## Static, Sample, Or Stale Surfaces

- `src/conviction_cockpit_v5.jsx` contains a baked FEED literal dated
  2026-05-29. That literal is sample data only; it is not current dashboard
  state.
- `src/render_cockpit.py` is the correct way to replace that baked sample with a
  live feed.
- `docs/index.html` is a static generated artifact. Its current checked-in
  header shows a 2026-06-04 build stamp, but it only updates when regenerated
  and committed/published.
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
  rates, policy, or volatility shocks.
- `heartbeat` and `lane_status` overlap operational health. `heartbeat` says
  which routines ran; `lane_status` says which data lanes were checked, stale,
  failed, or dark. Both should stay; generated HTML now mirrors lane-status
  counts/top rows as summary context.
- `docs/index.html` duplicates a subset of the JSX dashboard. Because it omits
  newer surfaces, this duplicate path can create conflicting operator truth.
- The command/navigation tab in generated HTML is static utility content, not a
  feed-backed dashboard surface.

## Missing Surfaces That Can Block Action Clarity

Highest impact gaps:

- HTML now shows `lane_status` summary counts/top rows and dark-lane next-step
  guidance, but the canonical JSX remains the full source for lane diagnostics.
- HTML now shows compact `feedback` lines and recommendations, but detailed
  source-call rows and clusters remain canonical JSX.
- HTML omits `research_actions`, `prospects`, `bullish_flow`, and `radar`. These
  are candidate-action and timing lanes; hiding them reduces buy/research
  clarity.
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
