# Options Opportunity Surfacing — Scope & Build Plan (2026-06-18)

**Queue item:** `options-opportunity-surfacing` (P1, queued) in `src/system_improvement_queue.json`.
**Notion (living plan):** 🛠️ System Update Queue → "🎯 Options Opportunity Surfacing" (`383c5031-4bb6-8147-9b52-d1bbac62e960`).
**Status:** scoped & queued. Build not yet scheduled.

---

## The ask (operator, 2026-06-18)

A lot of names ripped today; with options the operator would have made a killing. The operator has lost
money on options and feels the need to make it back on options. Core complaint: **option opportunities
never surface** — they're buried in the dashboard, don't come up when talking to Claude directly, and
can't be acted on intraday ("you can't even do it after hours"). We do options tracking + watchlists, but
when there's a good options opportunity it has to be surfaced and acted on ASAP.

## Reframe (the problem we are actually solving)

The real problem is **the system is blind to the options *expression* of its own convictions** and lets
time-boxed moves die unsurfaced. It is **NOT** "make back what I lost on options." Leverage cuts both ways;
loss-chasing is the *recklessness* failure mode — the opposite of the anti-passivity north star. We build
disciplined **opportunity capture**: defined-risk, conviction-gated, right-sized, risk visible. This
guardrail was adversarially stress-checked during scoping and is load-bearing.

## North-star test this must pass

The screen — and a direct conversation — must **pull the operator to a right-sized, defined-risk options
action before the window closes**. Strength loud, weakness quiet — *but weakness in a high-conviction name
is itself a loud BUY window*. Risk always visible. A score must never masquerade as a recommendation.

## Operator decisions locked (2026-06-18)

- **Posture: disciplined capture.** Defined-risk only; conviction-gated; the down-day IV spike is a BRAKE
  (route to a spread or "wait"), not a green light.
- **Premium budget: ~2% per trade / ~10% aggregate** premium-at-risk (% of total portfolio); size by max-loss.
- **Output: plain language, explain everything simply.** Operator: "make sure you're very clear and explain
  things simply." Every term defined on the card; max-loss in $ AND %.

---

## Current-state map (verified from code, 2026-06-18)

**Headline: the options strand is wired and running — but it looks at the wrong things, too slowly, and
never as a trade.**

What IS wired (do not rebuild):
- `uw_cache_refresh` routine → `codex_uw.orchestrator --mode opportunity` → writes
  `src/uw_opportunity_signals.json` → `full_build_runner.py` loads it (≈line 927/978) → engine → feed as
  `lean_in` / `buy_now` / `reentry_zone` actions. `open_opportunities.py` persists un-acted ideas across
  builds with aging cues ("flagged 5/28, +12%, day 5").
- Context modules exist but are only modifiers/standalone: `uw_iv_context.py`, `iv_context_surface.py`,
  `gamma_positioning.py`, `stale_leaps_scan.py`, `options_expiry_preflight.py`, `parabolic_setup_screener.py`.

The gaps (each verified):
- **G1 — wrong signals.** The opportunity scan requires `flow, oi, dark_pool` — the FLOW family, the
  research's weakest/most-contested predictor. The STRONG signals (IV-rank cheapness, expected-move-vs-target,
  liquidity gate, down-day IV tax) appear only as optional ±1 modifiers, not as the screen.
- **G2 — no trade is ever constructed.** Routine doc: "UW is a conviction/timing augmenter, not a standalone
  trade signal." Output is a direction lean; nothing emits strike / expiry / structure / contract / premium /
  size.
- **G3 — universe & trigger mismatch.** Scan is gated to `theses.json` and triggers on FLOW. Operator wants
  watchlist + lean-in + Fundstrat names, triggered especially on DOWN-in-price (with the IV-tax guardrail).
- **G4 — batch cadence, not intraday.** `uw_cache_refresh` is a scheduled refresh; `open_opportunities` is
  "across daily builds," no intraday memory. THE killer for perishable options.
- **G5 — buried, not loud, unlabeled as options.** Surfaces as a lean-in/aging row (the VRT/XLRE
  thesis-less-Watch-row miss pattern); the "options-ness" isn't even labeled.
- **G6 — no conversational recall.** `case_file.py` treats options only as an identity note
  ("wrappers/options/underliers are not silently merged"); it does not surface a live options setup when a
  ticker is mentioned.

**Net:** not a greenfield build. (a) re-weight signals toward the strong predictors, (b) add a
trade-construction + sizing step, (c) widen the universe & add weakness as a trigger, (d) make it
intraday/on-demand, (e) surface loud + in conversation. Reuse the existing acquisition/cache/persistence spine.

---

## What to look at — research-grounded criteria

**Framing fact:** long options are, on average, a *negative-carry* trade (the volatility risk premium; IV
usually > subsequently realized vol; zero-beta ATM straddles lose ~3%/week, Coval & Shumway 2001). So
**conviction is necessary but not sufficient** — you also need cheap-enough IV, an expected move that clears
premium + theta, and a structure/size that survives being wrong.

**The anti-revenge mechanism (the heart):** a dip usually *inflates* the option's premium (price down → IV up;
the leverage effect). "Down day + IV spike" is the revenge-buy trap. Surface BOTH the dip and the IV tax;
route rich-IV dips to a defined-risk debit spread or "wait" — never auto-convert a dip into an overpriced
naked long.

**Screening checklist (cheapest disqualifiers first):**
1. **Liquidity gate (HARD)** — OI ≥ ~100 (ideal thousands), tight spread, real size; else do not trade.
2. **IV cheapness** — IV rank/percentile ≤ ~25–30 → premium cheap; ≥ ~50 → rich, prefer spreads/skip.
3. **IV vs realized** — flag IV >> realized (overpaying for vol).
4. **Expected move vs your target** — EM ≈ 0.85 × front ATM straddle; act only if your move > break-even.
5. **Catalyst/earnings proximity** — block long premium into a known IV-crush event unless intended.
6. **Term structure/skew** — backwardation (front IV > back) flags an imminent event.
7. **DTE vs thesis horizon** — match expiry to thesis; avoid very short DTE for long premium.
8. **Delta** — ~0.70Δ+ = stock-replacement (low theta); ~0.30–0.40Δ = cheaper/lottery; delta ≈ P(ITM).
9. **Down-day IV tax (anti-revenge)** — if down AND IV spiked, flag "rich *because* it fell" → spread/wait.
10. **Flow (LOW weight, contested)** — soft tiebreaker only, never a primary trigger.

**Structure decision tree:** liquid? → no = don't trade. Earnings before expiry? → default avoid / use spread
/ expiry after event. IV cheap → long call/put slightly ITM (weeks–months) or deep-ITM LEAPS (multi-quarter).
IV rich (or gapped-down + IV spiked) → debit vertical spread, or wait for IV to settle. Always: max loss known
at entry; size by premium-at-risk.

**Sizing:** premium-at-risk IS the risk (max loss = premium). `Contracts = RiskBudget ÷ (Premium × 100)`.
Cap ~2%/trade, ~10% aggregate (operator-set). Fractional Kelly, never full. Do **not** encode "most options
expire worthless" (false — CBOE: ~10% exercised / 55–60% closed / 30–35% worthless); use "100% loss is a
realistic outcome, size for it."

**Evidence-quality flags to carry in the engine:** strong = vol-risk-premium, earnings IV-crush, leverage
effect, liquidity/slippage, max-loss sizing. Moderate/heuristic = IVR/IVP thresholds, OI floor, 30–45 DTE
sweet spot. Weak/contested = options flow / UOA (the one signal the current scan is built on — flag for
re-weighting). Sources in the Notion plan + the research agent transcript (Coval & Shumway 2001; Goyal &
Saretto 2009; Pan & Poteshman 2006; Cremers & Weinbaum 2010; Jiang & Strong; CBOE; OIC Rule of 16;
Option Alpha; Risk-Constrained Kelly arXiv 1603.06183).

---

## Scope — in / out

**IN**
- Trade-construction step: conviction name + live chain/IV/liquidity → ONE defined-risk idea
  (structure + strike + expiry + est. premium + max-loss) sized to budget.
- Re-weighted signal set (IV cheapness, expected-move-vs-target, liquidity, down-day IV tax primary; flow
  demoted to low-weight tiebreaker).
- Universe = watchlist + lean-in + Fundstrat + theses; down-in-price as a primary trigger (with IV-tax brake).
- Loud top-line surfacing + conversational recall (`case_file`) + intraday/on-demand freshness.
- Plain-language explanation of every term; max-loss in $ and %.

**OUT (hard boundaries)**
- Auto-execution / order placement — NEVER. The system only shows a sized idea; the operator trades.
- Naked / undefined-risk structures.
- Selling-premium / income strategies (v1).
- Non-conviction speculation.
- Real-time streaming greeks dashboards / a backtester (later).

## Doctrinal guardrails

Defined-risk only · conviction-gated · ≤2%/trade & ≤10% aggregate premium budget (size by max-loss) ·
down-day IV-tax brake · earnings/IV-crush block · liquidity hard gate · plain-language output (risk loud, no
score-as-recommendation) · honesty ("100% loss realistic," not "most expire worthless") · loss-chasing
tripwire (to design).

## Phased approach (thin first slice first)

- **Phase 1 — Options expression on names we already surface, on-demand + loud (thin slice).** On an existing
  surfaced conviction name OR when asked about a ticker in conversation, compute the defined-risk expression on
  demand (pull live chain + IV + liquidity, run the checklist), emit ONE sized idea + IV-tax brake + plain
  explanation. Surface loud top-line + via `case_file` recall. Reuses the existing acquisition spine; no new
  continuous infra. *Smallest thing that would have caught "what ripped today."*
- **Phase 2 — Weakness trigger + intraday surfacing.** Across watchlist + lean-in + Fundstrat, when a
  conviction name is down ≥ threshold intraday, proactively surface the expression (IV-tax brake front and
  center) via a lightweight intraday re-check (not the daily build).
- **Phase 3 — Re-weight the existing flow scan + close the loop.** Demote flow to a low-weight tiebreaker in
  `uw_opportunity_scan`; promote IV/EM/liquidity to the primary screen; log outcomes and calibrate from the
  Source Call Log.

## Open questions for the operator

- Loss-chasing tripwire: explicit cool-off after a realized options loss? (Recommended: yes, light-touch.)
- Down-trigger threshold: −3% / −5% intraday / near support / 52-wk low? (Phase 2.)
- Surface location: loud block inside Today/Decide vs a dedicated "Options" lane?
- Keep 2%/10% percentages or pin exact dollar caps (needs account size)?
- Universe precedence: surface even when a name is on the watchlist/Fundstrat but not yet in `theses.json`?
  (Assumed yes.)

---

## Build status (2026-06-18)

**Phase 1 ENGINE shipped + tested (this session, in-lane).**
- `src/options_expression.py` — pure core: a normalized `subject` (ticker + conviction + live
  chain/IV/liquidity) → ONE defined-risk options idea (structure + strike + expiry + est. premium +
  max-loss + size at ≤2%/≤10%), with the IV-tax brake, a first-class timing verdict (named
  flip-condition), a light loss-chasing tripwire, and a plain-language card (move/when/why/the-catch +
  per-term glossary). Wide-net-then-filter: every candidate gets a graded disposition (ACT/WAIT/WATCH/
  SKIP) + a plain `filter_reason` — nothing is silently dropped. Every threshold is a named, override-able
  dial (`DEFAULTS`, `cfg=`); no inline magic numbers.
- `src/options_shadow_log.py` — the "learn from the misses" ledger: appends every near-miss/hold
  (WATCH/WAIT/SKIP) with the dial that held it back, so thresholds get tuned from REAL missed
  opportunities (operator's explicit ask; the antidote to bright lines).
- `src/test_options_expression.py` — 9 tests, all green. Full suite: **1660 passed, 6 skipped**.

Operator decisions are encoded: disciplined capture; ~2% / ~10% budget; plain-language output. No live
data, no surfacing, no execution yet — that's the wiring below.

## Card contract (lead with the move — enforced by the engine output)

A surfaced card MUST read, top line first:
1. **MOVE** (imperative, sized): `BUY 3× NVDA Sep $145 calls (~$6.20) — most you can lose $1,860 (1.9% of book). Now.`  ← `result["move"]`
2. **WHEN** (timing verdict + flip-condition if waiting): `result["timing"]` / `result["when"]`.
3. **WHY** (one plain sentence): `result["why"]`.
4. **THE CATCH** (risk / IV-tax brake in plain words): `result["the_catch"]` / `result["brake_reason"]`.
- Collapsed one tap deep: the checklist, IV rank, expected move, break-even, `result["glossary"]`, the
  honesty line. A score never leads; it never masquerades as a recommendation.
- `result["tripwire_note"]` (if a recent options loss is flagged) shows on the card, light-touch.

## Adversarial re-examination — refinements applied (verdict: REFINE)

A critic re-examined the scope against the primary goal. Applied into the engine: (#2) timing as a
first-class verdict with a NAMED flip-condition; (#3) weakness gated on thesis-intact (`thesis_break` →
SKIP "thesis check, not a buy" — the XLRE doctrine inverted); (#6) a minimal loss-chasing tripwire in
Phase 1; (#4) the rejected-but-watched shadow log in Phase 1; (#7) an honest-empty / near-miss
`summarize_run` so an empty day says "checked N, clean/starved — nothing hidden," never goes silent;
(#5) soft dials are reads/ranks not cutoffs (only liquidity + defined-risk-only stay hard). (#1
lead-with-the-move) and (#8 keep Phase-1 on-demand) were already in the design.

## Execution ownership recommendation

- **Claude — this session (in-lane), leads the engine + data:** ✅ engine + shadow log (DONE). NEXT
  (in-lane): the **live UW-MCP `subject` adapter** (a NEW options module that assembles the chain/IV/
  liquidity bundle from the Unusual Whales MCP — needs MCP access, which this session has) and the
  **Phase-3 re-weight of `uw_opportunity*`** (demote flow to a low-weight tiebreaker; in-lane).
- **Ticker-dossier session (owns `case_file.py`):** the **G6 conversational-recall hook** — see TODO below.
- **Surfacing/render owner (or Codex):** the **loud top-line "OPTIONS EXPRESSION" block** in the action
  card / `today_decide` + the **intraday on-demand trigger**. Touches shared feed/render files — NOT this
  session's lane. Paste-ready prompt below.

Rationale: MCP access + north-star judgment + live verification → Claude for engine/adapter; render +
routine plumbing is mechanical/repo-bound → Codex or the surfacing owner; `case_file.py` is owned elsewhere.

## Cross-session coordination TODOs (do NOT edit other lanes from this session)

- `TODO(coordinate: case_file.py owner / Ticker-dossier session)` — **G6 options recall hook.** When a
  ticker is mentioned/assembled, call `options_expression.build_expression(subject)` (subject from the
  options live adapter) and attach the resulting idea (move/when/why/the-catch/glossary/tripwire) to the
  case-file recall so a live options setup surfaces in direct conversation. Respect MONITOR no-add; don't
  surface ACT louder than the conviction warrants.
- `TODO(coordinate: surfacing/render owner)` — wire a loud top-line "OPTIONS EXPRESSION" block into the
  action card / `today_decide` from `build_expression()` output (consume the contract; do not re-implement
  it), and add the intraday on-demand trigger. See the Codex prompt below.

## Paste-ready Codex prompt — surfacing + intraday wiring (for the surfacing owner / Codex)

```
TASK: Wire the already-built, tested options-expression engine into the cockpit surface + an
intraday on-demand trigger. Do NOT modify src/options_expression.py or src/options_shadow_log.py —
they are owned + locked; CONSUME their output contract.

CONTEXT: src/options_expression.py exposes build_expression(subject, *, cfg=None) -> dict and
summarize_run(results) -> dict. Output keys: disposition (ACT/WAIT/WATCH/SKIP), move, when,
timing{verdict,label,flip_condition}, structure, legs, max_loss_dollars, max_loss_pct_book,
iv_tax_brake, brake_reason, why, the_catch, glossary, tripwire_note, filter_reason. Scope +
card contract: docs/codex_tasks/options_opportunity_surfacing_scope_2026_06_18.md.

DO:
1. Add a loud, top-line "OPTIONS EXPRESSION" block to the action card / Today-Decide for any
   surfaced conviction name that has an ACT (or WAIT-with-flip) options result. LEAD WITH result["move"];
   put timing/why/the-catch on the face; collapse checklist/glossary one tap deep. Plain language only.
   Show max-loss in $ AND %. Show tripwire_note when present. A score must never masquerade as a rec.
2. Use summarize_run() for the honest-empty state: if nothing is ACT-able, say "checked N, clean/starved —
   nothing hidden" and name the closest call. Never render silence.
3. Add an on-demand / intraday trigger that builds subjects for the surfaced/asked names (NOT a
   universe-wide scan — that's Phase 2) and calls build_expression. Append near-misses via
   options_shadow_log.append_rejections().
4. Honesty rails apply (dark-lane discipline, stale stamps). Do NOT auto-execute. Add tests; keep the
   full suite green. Do NOT regenerate shared feed/index/heartbeat outputs unless coordinated.
```

> **Coordination note (2026-06-18):** built under a shared-worktree, multi-session regime. This session's
> lane = `uw_opportunity*.py`, `uw_iv_context.py`/`iv_context_surface.py`, `gamma_positioning.py`,
> `open_opportunities.py`, the options scope doc, and NEW options modules. The queue item in
> `src/system_improvement_queue.json` was appended before the lane rules landed; no further edits from here.
