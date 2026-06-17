# Decision Surface Consolidation Plan - 2026-06-17

This plan applies the canonical Investing OS primary goals in
`docs/investing_os_primary_goals.md` to the current dashboard. It incorporates
Claude's external-review suggestion that the next phase is subtraction and
consolidation, not another stacked layer.

## North Star

The dashboard must decide and direct, not just display. The strongest real
move should be the loudest thing on screen, one tap from action, while weak
signals stay quiet and risk remains visible. If the system is starved, the
screen must say so plainly and surface the highest-leverage unblock instead of
presenting a blocked trade as an action.

## Live Problem Statement

The 2026-06-17 15:20 ET build successfully added an action-first hero, but the
dashboard still behaves like three dashboards stacked together:

- TODAY/DECIDE first viewport and ownership buckets.
- Legacy trust, material-decision, action, opportunity, runbook, and status
  panels.
- Evidence/context lanes such as watchlist, asymmetric opportunities, sleeve
  rotation, macro, UW runbook, and reallocation brief.

The same names recur across panels with different labels and levels of urgency.
That redundancy raises decision cost, which is directly opposed to the primary
goal. The live first viewport also presents `TRIM GRNY` as an action-shaped
primary even though the system says it is blocked, low-conviction, and not
operator-actionable yet.

## What Claude Got Right

- The next phase should subtract and consolidate. Repeating the same names in
  five lenses is itself drift.
- A blocked trade must not be the loudest action-shaped element. If nothing is
  actionable, the hero should become the highest-leverage unblock.
- Surface redesign and feed readiness are one effort. A clean screen cannot
  prescribe while core feeds are inconclusive, uninterpreted, or not checked.
- Progressive disclosure should be the spine: recommendation first, supporting
  data one tap deeper.

## Codex Additions

- Use an explicit command-state model: `ACT`, `DECIDE`, `RESOLVE`, `WATCH`.
- Add a data-readiness ladder: `routine fired`, `boundary artifact fresh`,
  `signal interpreted`, `decision eligible`, `trade executable`.
- Keep the honesty rails: neutral UW stays inconclusive, source scoring stays
  off until real graded outcomes exist, and watch/research rows do not become
  capital actions by visual promotion alone.
- Make high-impact non-trade items force explicit dispositions when they are
  decision-relevant: `PASS`, `RECHECK`, `SIZE`, `KEEP WATCH`, or `ASK OPERATOR`.

## Target Information Architecture

One screen, one ranked command surface:

1. **Command strip** - counts and top action by state:
   `ACT now`, `DECIDE today`, `RESOLVE to unlock action`, `WATCH/research`.
2. **Primary command** - the single strongest real move, or the highest-leverage
   unblock when no action is executable.
3. **Merged decision list** - one row per ticker/decision, with all source
   lenses fused into one read.
4. **Evidence drawer** - source detail, rotation, macro, UW, FS, conflicts, and
   runbook proof behind a deliberate expansion.
5. **System honesty footer** - build, branch, feed freshness, routine proof,
   and not-checked lanes, never competing visually with a capital decision.

## Panel Consolidation Map

| Current panel | Target treatment |
| --- | --- |
| TODAY/DECIDE hero | Keep, but drive from `ACT/DECIDE/RESOLVE/WATCH`; no blocked trade gets an ACT-shaped button. |
| Ownership-aware passivity | Compress into command strip and daily latency counts. |
| Disposition coverage | Keep as a footer/audit until dispositions are fully wired into every surfaced decision. |
| Trust panel | Replace with data-readiness ladder; separate fired proof from boundary data and interpretation. |
| "Nothing actionable yet" verdict | Replace with starved-state or unblock hero when applicable. |
| Material Decisions | Merge into unified decision list. |
| Funding / paired sells | Keep only as attached funding legs under the buy/add they fund. |
| Watchlist / pullback queue | Feed into WATCH or DECIDE/RECHECK when high impact and timely; rest stays drill-down. |
| Do-not-touch / research-only guardrails | Move to per-card rails plus global footer. |
| Portfolio thesis context | Evidence drawer unless it changes the ranked command. |
| System honesty / data caveats | Data-readiness footer. |
| Held for you | Promote overdue reviews into DECIDE/RESOLVE; otherwise collapsed review rail. |
| Market-open packet | Feed pre-action checks and starved-state unblocks. |
| Today's Actions | Merge into unified decision list. |
| Source Conflicts | Per-candidate conflict badge with "what settles it." |
| Opportunity Context | Feed the unified list; no standalone duplicate panel. |
| Asymmetric Opportunities | Candidate scorer feeding the unified list; keep "one row per ticker" principle. |
| Candidate Reallocation Brief | Decision/funding source for buy/add rows, not a competing summary. |
| Operator Status | Footer/status utility only; must not say PASS if decisions remain unresolved. |
| UW Action Runbook | Evidence drawer and readiness ladder; checks are not proof of support. |
| Sleeve Rotation / Macro | Context signals feeding candidate rows; standalone only when they change sizing, timing, hedge, or watch priority. |

## Implementation Roadmap

### Slice 1 - Doctrine And Plan Persistence

Land `docs/investing_os_primary_goals.md`, update `AGENTS.md`, mirror to Notion,
and publish this consolidation plan. No dashboard behavior change.

### Slice 2 - Command-State Contract

Add render-only command states to TODAY/DECIDE:

- `ACT`: executable now, right-sized, evidence-backed, survival rails clear.
- `DECIDE`: operator must choose yes/no/recheck, but execution is not auto-clear.
- `RESOLVE`: meaningful candidate blocked by named data/evidence/risk gaps.
- `WATCH`: weak, early, context-only, or research-only.

First-viewport button copy must follow state. A blocked `TRIM GRNY` becomes
`RESOLVE GRNY trim` / `RECHECK`, not `ACT TRIM`.

### Slice 3 - Single Merged Decision List

Build a unified view-model that takes current cards, actions, market-open rows,
asymmetric opportunities, target drift, reallocation, watchlist, and held-review
items and emits one row per ticker/decision. This is initially display-only and
must preserve existing scoring, gates, and safety semantics.

### Slice 4 - Data-Readiness Ladder

Replace broad trust copy with explicit readiness states:

- routine fired
- boundary artifact fresh
- signal interpreted
- decision eligible
- trade executable

This fixes false green from `scheduled proof 14/14` and false red from lanes
that are fresh but not interpreted.

### Slice 5 - Feed And Unblock Audit

Audit surviving feed inputs against the boundary artifacts they need:

- UW opportunity signals vs UW endpoint proof vs explicit interpretation.
- FS inbox/intake checked status vs render consumption.
- source scoring `n>=15` threshold and graded outcome backlog.
- cash/buying-power and account eligibility.
- timing gates: stated date vs evaluated date.

The starved-state hero should recommend the highest-leverage unblock, not a
blocked trade.

### Slice 6 - Outcome Loop

Ensure every ACT/PASS/RECHECK/SIZE/KEEP-WATCH decision writes an outcome path
or a due recheck. Detectors that never surface and outcomes that never feed
back are removed or wired.

## Verification Expectations

- No auto-promotion of neutral/inconclusive UW to support.
- No lowering source-scoring thresholds or backfilling fake graded outcomes.
- No new urgency language that is not tied to real evidence and timing.
- Focused TODAY/DECIDE tests plus `python src/verify_standard.py`.
- Desktop/mobile visual checks that the strongest real command is visible in
  the first viewport and blocked candidates do not look executable.
