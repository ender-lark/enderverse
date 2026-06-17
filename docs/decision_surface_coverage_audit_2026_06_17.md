# Decision-Surface Coverage Audit — 2026-06-17

> **SUPERSEDED IN PART (verified against origin/main `c6a059c`, then updated by
> `codex/decision-surface-v2-delta`).** This audit was written against a local checkout 4 commits
> behind `origin/main`. The action-first Today/Decide rewrite (`f097e05`) has since merged: the
> fed-day packet IS now wired into the feed and surfaced as a visible, legible `watch_queue` (the
> 9 deep-discount + 7 pullback names render expanded with their disconfirmations); immaterial
> funding legs are demoted out of hero ranking into a "Funding / paired sells" lane; rail-safety was
> adversarially verified. The follow-up delta adds the Phase-C `build_without_wire` guardrail and the
> fed-packet staleness honesty gate. The miss-type taxonomy below remains the durable lesson.
>
> **Still deferred, by design:** orphan_wiring live thread; watch_queue disposition rail; Finding 4
> unification across `feed.prospects`, `feed.actions`, and `feed.research_actions`; the 107-name
> `watchlist_discount_screen`; and generalizing the Fed-day packet into a daily-regenerated
> discount/pullback packet.


Phase A of the decision-surface deep dive. Triggered by Codex's PR #69
self-correction ("show top 6 just echoes the same six generated directive
cards, not a real impact-ranked queue across holdings, watchlist, prospects,
and possible discounted buys"). This audit asks one question of the whole
system and answers it with live evidence:

> Of every place the system generates a *candidate* (a name to add, trim,
> watch, research, or buy-on-discount), how many actually reach the one surface
> whose job is to force a time-stamped yes/no — TODAY—DECIDE?

Original answer at audit time: **one.** Everything else was scoring-only, a
separate context panel, orphaned, or plumbed-but-never-called.

Current correction: `origin/main c6a059c` has already widened Today/Decide into
an action-first surface with material decisions, other rechecks, funding-only
paired sells, full remaining-card queue, and fed-packet `watch_queue`. This
document now preserves the miss taxonomy and named remaining work; it is no
longer a claim that the fed packet is orphaned.

This is measured against the canonical mission (`AGENTS.md` §Primary
Objective): the job is to "turn data into a few clear, evidence-backed,
time-stamped decisions and force a yes/no on each"; the enemy is "passivity —
under-sized ideas, setups rotting in queues, slow action." The drift test:
"does it make a real, high-conviction, well-timed opportunity more likely to
reach the operator's eyes and become a right-sized action."

## Method (reproducible)

Traced on 2026-06-17 from the canonical checkout against the live feed
(`src/latest_cockpit_feed.json`, stamp `2026-06-17T05:20:33Z`):

- Read the decide-surface build chain end to end:
  `full_build_runner.build_full_feed` → `today_decide.build_today_decide_payload`
  → `directive_recs.build_directive_cards` → renderer
  `cockpit_html_gen` / `today_decide.render_today_decide_html`.
- Enumerated candidate-bearing artifacts under `src/` (packets, screeners,
  prospect/best-idea/registry caches) and grepped for every non-test reader.
- Cross-checked orphan claims against `docs/integration_debt_report.md`.

## Finding 1 — the decide surface has exactly one candidate source

`directive_recs.build_directive_cards` builds cards from **only**
`feed.reallocation_brief.rows` (adds) + `.trims` (funding) + an optional
`extra_cards` argument (`src/directive_recs.py:308–455`). It sorts by a
priority blend and cuts at `goal["daily_card_max"]` (**3** today,
`src/goal_tunables.json:18`); the remainder renders as terse one-line
`backlog` rows, not real cards (`src/today_decide.py:814–819`).

Live candidate universe feeding the surface today — **6 rows total**:

| lane | ticker | notional | note |
|---|---|---:|---|
| add | GOOGL | $153,881 | seq now, AMBER |
| add | MSFT | $38,674 | seq now, AMBER |
| trim | GRNY | $123,084 | funding |
| trim | IVES | $68,104 | funding |
| trim | SMH | $968 | funding |
| trim | MAGS | **$400** | funding |

The `$400 MAGS funding leg` Codex flagged is real: a funding-mechanics row
that competes for "top" billing because it is one of only six things the
surface can see.

## Finding 2 — the orphan-wiring lane is plumbed to the door, never called

The V3 Task-5 work (`V3_PROGRESS.md`) added `orphan_wiring.py`
(MONITOR-RE-ENTRY cards, GRNY-DELTA evidence, a 13F+insider→`inst_state`
adapter, 16 tests) and threaded `extra_cards` / `extra_fs_items` /
`inst_states` *parameters* through `directive_recs` and `today_decide`. But the
production call site passes none of them:

```text
src/full_build_runner.py:989
    feed["today_decide"] = today_decide.build_today_decide_payload(
        feed=feed, weights=..., goal=..., accounts=execution_accounts, today=today,
    )   # no extra_cards, no inst_states, no orphan_honesty
```

Consequence: in the published feed, MONITOR-RE-ENTRY never emits and the
institutional lane is permanently `"not wired (orphan-wiring chunk)"`
(`src/directive_recs.py:471–474`). The capability *looks* shipped (parameter
plumbed, tests green, workboard MERGED) but nothing flows. This is the sharpest
single instance of the pattern: built, plumbed, marked done — and inert.

## Finding 3 — the richest candidate set in the repo was orphaned data

`src/fed_day_reallocation_packet.json` (built today, MERGED) carries the exact
"impact-ranked queue across holdings, watchlist, prospects, and discounted
buys" Codex said was missing:

- `act_if_green`: 2 (GOOGL/MSFT gated tranches)
- `deep_discount_research`: **9** (BMNR, LEU, AVAV, KTOS, ELF, SOFI, UUUU, MP, HOOD)
- `higher_quality_pullbacks`: **7** (MSFT, GOOGL, AVGO, FN, VRT, NVDA, AMZN)
- `watchlist_discount_screen`: **107** screened rows
- green/amber/red gates, source-status proof

Current correction: `full_build_runner.py` now loads this packet into the feed,
and `today_decide.py` consumes it for card context and a visible `watch_queue`.
The 107-name `watchlist_discount_screen` remains unconsumed and is named below
as deferred routine/product work.

## Finding 4 — multiple action surfaces, no shared candidate model

The dashboard renders Today/Decide cards (`reallocation_brief`), a separate
**Today's Actions** panel (`feed.actions`, `cockpit_html_gen._actions` :1369),
a **Top Prospects** panel (`feed.prospects.hot/movers_best/sell_fast` :1685),
and **From Research** (`feed.research_actions` :2194) — each from a different
source, none unified, and **only Today/Decide forces a disposition** (ACT /
PASS / RECHECK). A prospect or a research action is visible-as-context but never
pushed to an explicit yes/no. The funnel that forces action is both the
narrowest and the only one wired to a disposition log.

## Coverage matrix

Verified = traced in this audit. Reported = cited from
`docs/integration_debt_report.md`.

| candidate source | reaches TODAY—DECIDE (forces disposition)? | evidence |
|---|---|---|
| `reallocation_brief.rows` (adds) | **Yes** | `directive_recs.py:308` — verified |
| `reallocation_brief.trims` (funding) | **Yes, but demoted to Funding / paired sells** | `directive_recs.py:375` + Today/Decide lane split — corrected |
| `orphan_wiring` MONITOR-RE-ENTRY / 13F→inst | **No — plumbed, not called** | `full_build_runner.py:989` — verified |
| `fed_day_reallocation_packet.json` (9 discounts, 7 pullbacks, 107 screen) | **Partly yes** — 9 discounts + 7 pullbacks surface as rail-free `watch_queue`; 107-name screen deferred | `full_build_runner.DEFAULT_FILES.fed_day_reallocation_packet` -> `today_decide.watch_queue`; DSV2 staleness gate |
| battery / UW / Fundstrat / sector inputs | scoring-only (no new candidates) | `directive_recs._conviction` — verified |
| `decision_dossiers.json` | context attach only; coverage debt is Source-Proof-only | `AGENTS.md` §8.1 — verified |
| `feed.prospects` (Top Prospects) | separate panel, no disposition | `cockpit_html_gen.py:1685` — verified |
| `feed.actions` (Today's Actions) | separate panel, no disposition | `cockpit_html_gen.py:1369` — verified |
| `signal_log.json` / `social_watch.json` | watch-only panels | architecture §5 — verified |
| `held_decisions.json` | separate parked-decision strip | `cockpit_html_gen._held_decisions_strip` |
| `trigger_registry.json` / parabolic Phase 3 | push/alert spine; velocity not surfaced → `not_checked` | `docs/efficacy_gaps.md` — reported |
| `13f_best_ideas.py` | orphan (bare CLI, argparse/json/sys) | verified + report |
| `disconfirmation_registry.json` | sidecar, "no card surfacing"; now also flagged by `build_without_wire` as real remaining debt | workboard CC-C; report; DSV2 guardrail |
| `correlation_matrix.py`, `benchmark_overlay.py`, `deepdive_runner.py` | orphan | report (13 flagged; 34 candidate orphans) |

## The miss-types this exposes (use as a review checklist)

Codex's PR #69 response is a *good* catch; the lesson is the class of error that
produced the thing it caught. Five recurring miss-types, each failing the drift
test by construction:

1. **Relabel-as-fix** — change touches copy/UI/status, not source-shape ("show
   top 6" over the same 6). "Preserve the same failure under a cleaner label."
2. **Build-without-wire** — a rich artifact is committed with no reader on the
   decision path (the fed packet; the 34 orphan modules).
3. **Single-source funnel** — the decide surface draws from one lane, so
   watchlist / prospects / discounts structurally can't compete.
4. **Top-N truncation hiding the queue** — `cards[:max]` + terse backlog;
   "visible, never hidden" technically, but inert.
5. **"Top" as label, not impact rank** — a $400 funding leg billed alongside a
   $154k add.

Shared root cause: **"done" is defined as merged / tests-green / artifact-exists
rather than "surfaced and forced a disposition."** Two existing guardrails miss
this: the feed-block classifier (`dashboard_feed_block_classification.json`)
catches hidden *feed blocks* but not standalone packet JSONs that bypass the
feed; the integration-debt sweep flags orphan *modules*, not orphan *data
artifacts*. A build-without-wire packet passes every current check.

## Current fixes landed or in flight

Operator decision recorded 2026-06-17: redesign is **display-only first**. Show
real candidates, but do **not** change conviction scoring, gates, or sizing
without a separate doctrine gate.

- **PR #69 already merged:** Today/Decide now separates material decisions,
  other rechecks, and funding-only paired sells; renders remaining decisions as
  full cards; wires the fed-day packet into a visible rail-free `watch_queue`;
  and keeps funding helper legs from outranking real decisions.
- **DSV2 delta guardrail:** `integration_debt_sweep.py` now has a
  `build_without_wire` section. Candidate-bearing JSON must either be read by a
  decision-path module, have a real `state_ownership_map.json` feed path, or
  carry a justified `non_surfacing_reason` in `src/non_surfacing_allowlist.json`.
  The guard proves `fed_day_reallocation_packet.json` is wired and leaves
  `disconfirmation_registry.json` flagged as real debt.
- **DSV2 delta staleness rail:** fed-day packets are fresh only when
  `packet.as_of == build day`. Stale packets stay visible as research context
  with STALE/not_checked labels and stale price wording. Absent packets produce
  no fabricated rows and write an honesty note.

## Remaining work named for later

- Orphan_wiring live thread: blocked on absent caches and path cleanup; do not
  wire tonight for an operator-invisible honest-absence result.
- Watch_queue disposition rail: would require a new disposition verb and parity
  work; defer.
- Finding 4 unification: unify `feed.prospects`, `feed.actions`, and
  `feed.research_actions` into a shared candidate model; scoring/product work,
  not this guardrail slice.
- `watchlist_discount_screen`: 107-name screen remains unconsumed.
- Daily discount/pullback packet: generalize the event-specific Fed-day packet
  into a daily-regenerated routine artifact so watch_queue freshness does not
  depend on a one-off event packet.

## Historical recommended fixes (superseded in part)

Operator decision recorded 2026-06-17: redesign is **display-only first** — merge
the candidate sources and render real cards, but do **not** change conviction
scoring, gates, or sizing (matches the repo's shadow-first discipline).

- **B (spec → Codex, PR #69):** TODAY—DECIDE becomes two surfaces: top 3
  operator-focus cards, then a full impact-ranked queue of every meaningful
  candidate as real expandable cards. Source-shape change: a unified candidate
  model merging `reallocation_brief` + fed packet (`act_if_green`,
  `higher_quality_pullbacks`, `deep_discount_research`) + (when wired)
  orphan-wiring cards, deduped by ticker, ranked by portfolio-impact ×
  conviction × window. Low-impact funding legs pinned to the bottom and labeled
  *funding mechanics*, not "top." Honesty rails unchanged; ranking/sizing
  unchanged in v1 (display-only).
- **C (guardrail, mine — non-colliding):** a "build-without-wire" linter — the
  data-artifact analog of the module-orphan sweep. Any committed
  candidate-bearing JSON with no reader on the decision path and no
  `non_surfacing_reason` fails the integration-debt sweep. Wires "reaches the
  operator's eyes" into the drift test as a testable gate so the next
  fed-packet-shaped artifact can't merge as "done" while orphaned.
- **First wiring win:** thread `orphan_wiring` outputs into
  `full_build_runner.py:989` (Finding 2) — the cheapest real candidate the
  surface gains, and it closes the permanent `institutional: not wired` line.

## Current TLDR / next steps

- **TLDR:** The original miss has been corrected for the fed-day packet and
  funding helper legs. The permanent lesson is now enforced by
  `build_without_wire`: candidate artifacts cannot quietly exist without a
  decision-path reader, ownership-map feed path, or explicit non-surfacing
  reason.
- **Who does what:** Codex owns the DSV2 guardrail/staleness delta and the named
  deferrals. Any future scoring, ranking, or disposition-rail change remains a
  separate operator/doctrine gate.
- **Next step:** use the guardrail output and named deferrals to prioritize the
  next product slice without re-opening the already-merged action-first render.

## Historical TLDR / next steps (superseded in part)

- **TLDR:** The decide surface sees 6 funding-mechanics rows; the 16 named
  pullback/discount candidates and 107-name screen the system already produced
  never reach it. The build is rich at score, thin and single-sourced at
  decide — manufacturing the passivity the mission names as the enemy.
- **Who does what:** Codex owns the Finding-2 wiring and the Phase-B redesign on
  PR #69 (it owns `today_decide.py`/`directive_recs.py` there). Claude Code/
  architecture owns the Phase-C linter and this audit (no file collision).
- **Next step:** turn this audit into the Phase-B implementation spec and the
  Phase-C linter; re-run against the live feed and confirm the 9 deep-discount
  names appear as real cards.
