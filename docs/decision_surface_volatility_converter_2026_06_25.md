# Volatility Opportunity Converter + Target-Drift Validation — 2026-06-25

**Author:** Claude Code · **Branch:** `codex/sell-gate-doctrine` · **Workboard:** `VOL-OPP-CONVERTER-2026-06-25`
**Trigger:** validate + improve Investing OS recommendations after the 2026-06-23/25 AI/semis volatility.

This is an architecture-decision record. Volatile truth (positions, %, decisions) lives in the
repo artifacts and Notion, never here — the numbers below are a point-in-time snapshot for context.

---

## 0. CORRECTION & root cause — why the numbers were stale (2026-06-25, `/goal` follow-up)

**The percentages/dollars in §1 and §4 below were computed off a STALE branch snapshot (2026-06-17). Corrected here; the corrected figures equal the operator's original spec.**

**Root cause — branch divergence, not a broken routine.** This feature branch's broker-intake-owned
position files (`account_positions.json`, `positions.json`) were frozen at **2026-06-17** (last
committed on the branch by `9a50e1f`), while the broker-intake routine keeps committing fresh daily
snapshots to **`main`** (now **2026-06-24**, sleeve **$1,856,472**). The long-running branch never
pulled them, so the decision surface sized off the 6/17 book ($1.923M) — which made NVDA look 11%
"under target." SnapTrade live confirms freshness (Schwab holdings `last_successful_sync`
2026-06-24T15:18Z; the two Schwab connections flag `is_degraded` but holdings still sync — the lag is
transactions only). Three-way agreement: operator spec == main 6/24 == live sync.

**Corrected weights (fresh 6/24 book):**

| ticker | held % | target | vs target |
|---|---|---|---|
| NVDA | 13.32% | 12% | **OVER $24.5k** (was misread as "in-band/under" off the stale book) |
| GOOGL | 4.99% | 8% | UNDER **$56.0k** |
| AVGO | 2.44% | 6% | UNDER **$66.1k** |
| MSFT | 1.87% | 5% | UNDER **$58.0k** |
| MU | 3.68% | 3% | OVER $12.7k |
| GRNY | 6.90% | 3% | OVER **$72.5k** |

Staged adds: trio ≈ **$180k**; full AI-model set ≈ **$438k**. Funding: GRNY $72.5k → MU $12.7k
(≈ **$85k** unconditional); **NVDA is over $24.5k but funding-of-LAST-RESORT** ("only if a concentration
rail is breached" — operator policy), not a routine trim. Unconditional funding only partially covers
the trio — staging is funding-rate-limited.

**Fixes shipped (this follow-up):**
1. **Positions-staleness guard** (`positions_staleness()` + `from_feed`) — stamps `⚠ STALE POSITIONS
   (Nd old) — refresh before sizing` onto the headline + honesty when the snapshot is >3 days old. The
   build previously sized off a stale book *silently*; verified the guard fires on the 6/17 data.
2. **Conditional-funding precedence** — a `funding_policy.conditional` name (NVDA) is funding-of-last-
   resort even when over target (ranked last, flagged, excluded from the funding total).
3. **Broker-core files left untouched** — I deliberately did NOT permanently swap the broker-intake-
   owned position files on this shared branch (that clobbers `CLOUD-BROKER-INTAKE` ownership and breaks
   the date-coupled `test_fed_day_reallocation_packet`). Proper refresh = an ops action: merge
   `origin/main`'s position files into the branch (or run the positions-sync), then commit.

**Systemic flags (Codex/operator):** long-running feature branches drift from main's daily position
commits; and `test_fed_day_reallocation_packet` hardcodes `snapshot_date == "2026-06-17"` (a smell that
breaks on every legitimate refresh — it should read the actual snapshot date).

---

## 1. The validated bug — and what was actually wrong

**Report:** `src/latest_cockpit_feed.json` `target_drift` showed **GOOGL / AVGO / MSFT as MISSING @ 0%**
while `portfolio_views.combined.rows` showed them held.

**Finding (verified empirically, not from a status light):** the **code was already fixed** — commit
`cd64af9` (workboard `GOAL-LENS-THESIS-WIRING`, PR#95) made `full_build_runner` feed the full-book
`account_positions` dict into `position_drift_check.target_weight_drift_summary`, and
`load_actuals_from_positions_cache` reads `combined_positions` (the FULL book, incl. untracked names)
first. Running it on the current `account_positions.json` returns the **correct** read:

| ticker | held % | target % | direction |
|---|---|---|---|
| GOOGL | 3.76% | 8% | UNDERSIZED (~$81.5k gap) |
| AVGO | 2.12% | 6% | UNDERSIZED (~$74.7k gap) |
| MSFT | 1.55% | 5% | UNDERSIZED (~$66.3k gap) |
| GRNY | 9.56% | 3% | OVERSIZED (~$126k excess) |
| MU | 3.67% | 3% | OVERSIZED (~$12.8k excess) |
| NVDA | 11.06% | 12% | IN-BAND (slightly under — **not** a funding source) |

The **`latest_cockpit_feed.json` artifact was simply STALE** — generated before the fix, so it still
showed `missing_count: 9`. A fresh in-process build now returns `missing_count: 1` and classifies
GOOGL/AVGO/MSFT as UNDERSIZED. **The bug was a stale surface, not live logic.**

> **Stale-spec note:** the originating spec assumed NVDA *overweight* by ~$24.5k and a $1.856M book.
> Live data moved (book $1.923M; the selloff pulled NVDA to **11.06% vs 12%**, i.e. slightly UNDER).
> So NVDA is **not** a funding source now — GRNY and post-beat MU are. Sizing was computed from live
> data, not the spec's figures.

**Remaining real work (this change):** the fix had **no regression guard**. The real
`account_positions.json` carries both `combined_positions` (full) *and* `tracked_combined_positions`
(which OMITS untracked GOOGL/AVGO/MSFT) — a live foot-gun: a future refactor reading the wrong key
silently reintroduces MISSING@0%. We lock it (§3).

---

## 2. The volatility opportunity converter

`src/volatility_opportunity_converter.py` — a pure, self-contained fusion layer (mirrors
`options_surface.py`'s producer/render/honesty pattern). It turns a volatility event into **one staged,
sized, time-stamped command** instead of six tiles the operator must fuse in their head (where
under-sizing and "maybe later" creep in).

**Fuses:** Fundstrat compact calls · live tape (reclaim? IV capitulation?) · current holdings ·
the FIXED target-weight gaps · flow/UW proof (independent confirmation only) · event-risk state
(oil/rates/Hormuz) → a command with dispositions:

| disposition | meaning |
|---|---|
| **STAGE-LEAD** | under-target quality name that HELD UP (structural gap, not tape-driven). Loudest; fires on the same reclaim gate, but surfaces an *optional* operator-choice early tranche. |
| **STAGE** | gated add (semis/wrapper dip) — armed, fires on the named reclaim trigger. |
| **CONFIRM-HOLD** | thesis confirmed by the event but already at/over target → **do NOT chase**. |
| **FUND** | over-target sleeve that finances the staged adds (trim into strength). |
| **HOLD** | in-band; no action (explicit, not silence). |
| **AVOID-NEW / WATCH** | no-position avoid-new context / honest not-checked. |

**Doctrine rails enforced by construction** (each has a test): lead with the move; strength loud /
weakness quiet / risk visible; **don't chase** (over-target ≠ ADD on a beat — the MU-beat trap);
**neutral ≠ support** (inconclusive/not-checked flow never lifts conviction); **honest absence**
(Social Watch stays not_checked); **GRNJ protected** (never auto-funded); never silent; never raises
on malformed input; **no trade execution** (every move is a sized prompt with a trigger + funding leg,
never an order — the operator owns the call).

**Demotion (`demote_no_position_sells`):** quiets loud "sell fast" rows on names we don't own —
UNLESS held, or an avoid-new-exposure note that gates a real new-buy choice (kept as quiet context).
Demotes by setting `action_state="WATCH"` (Contract-C-valid) and carries semantics on its own fields.

**Wiring (no build-and-forget):** opt-in `volatility` payload in `today_decide`, rendered LOUD
(mirrors the `options` seam — kept inside the payload, *not* a new top-level feed block, to satisfy
the dashboard-parity guardrail). `full_build_runner.from_feed(feed)` produces it from the
already-assembled feed (no new live pulls) and applies the demotion.

### Known limitation → Codex handoff

`from_feed` is thin: the **cached** feed lacks structured per-ticker tape % moves, a structured
Fundstrat "buy_dip" stance, and a *scored* event-risk state. So the scheduled build currently
surfaces the **target-gap staged adds** (the core win — ~$460k of under-target AI-model names as sized
actions instead of MISSING rows) but reports `regime: NEUTRAL / gate: PENDING` and treats MU as FUND
rather than CONFIRM-HOLD. The **full** regime/gate/MU-confirm fusion (as in the fixture + this
session's live recommendation) needs the feed to carry those inputs. **Next step (Codex):** wire
structured Fundstrat directional stances + per-ticker tape + a scored event-risk state into the feed
so the scheduled converter emits the full command. Until then, the live in-session recommendation
(below) is the rich view.

---

## 3. Regression lock (the account_positions drift shape)

`src/test_target_weight_drift_preflight.py` gains two tests pinning the exact `account_positions.json`
shape: a dict whose `combined_positions` (full book, incl. untracked GOOGL/AVGO/MSFT) co-exists with
`tracked_combined_positions` (omits them). They assert the drift read measures the **full** book —
untracked names show real weight as UNDERSIZED, **never MISSING@0%** — and that `combined_positions`
is preferred over the tracked-only key.

---

## 4. The staged command (live, 2026-06-24/25 close — recommendation only, NOT executed)

**Regime:** SEMIS_SELLOFF_REBOUND_PENDING. 6/23 semis −7% (SMH 622, DRAM −14%); 6/24 MU beat
(rev $41.46B, EPS $25.11, Q4 guide $50B). **Gate:** QQQ held ~704 / SMH held support but **neither
reclaimed** → stage, don't chase. **Event-risk: SUPPORTIVE** — USO −5.7% (oil soft), TLT +1.5%
(long-end yields easing); only the semis complex is at max IV (capitulation, not macro risk-off).

- **STAGE-LEAD (loudest, structural under-target, held up):** GOOGL +$81.5k · AVGO +$74.7k · MSFT +$66.3k.
  Fire on the reclaim; *optional* early tranche is the operator's call (thesis isn't tape-dependent).
  (Full AI-model underfill is ~$460k incl. TSM/AMZN/ANET/FN/ASML.)
- **STAGE (tape-dependent):** SMH/QQQ wrapper exposure — armed, fires strictly on the reclaim.
- **CONFIRM-HOLD (do NOT chase):** MU — beat **confirms** the AI-memory thesis but it's already
  ~$12.8k OVER target; the excess is a funding candidate (trim into post-beat strength).
- **HOLD:** NVDA 11.06% vs 12% — in-band; the selloff brought it to target; not a funding source.
- **Funding (in order):** GRNY ~$126k over (primary) → MU ~$12.8k (post-beat strength) → NVDA only if
  a concentration rail breaks (not now). **GRNJ protected — never auto-funded.**
- **What blocks it:** QQQ/SMH have not reclaimed (gate not OPEN). Flow neutral on the names (NOT
  counted as confirmation). Social Watch not_checked.

---

## 5. Verification

- `python -m pytest src` → **1743 passed, 6 skipped**. The only 2 failures (`test_go_live_checklist`)
  are **pre-existing** — they fail on committed HEAD `a843360` with all changes stashed (proven
  reversibly); this change touches neither `go_live_checklist` nor `system_improvement_queue`.
- Focused: `test_volatility_opportunity_converter.py` (~57, incl. ~41 adversarial-regression tests) +
  `test_target_weight_drift_preflight.py` (9) + `test_today_decide.py` (incl. 3 new) +
  `test_full_build_runner.py` all green.
- `render_cockpit.py --selftest` PASS (JSX feed injector still round-trips after the today_decide edit);
  `dashboard_parity_guardrail` PASS.
- Boundary-outcome proof: an in-process `build_full_feed_from_files` on live cached data returns
  `missing_count: 1` (was 9), surfaces the staged command, and demotes RYF/XOP — writing no artifact.
- Adversarial verification workflow (`verify-vol-converter`): see `## 6`.

## 6. Adversarial verification (3 workflow passes)

The converter is a real-money doctrine module, so it was hardened by **three adversarial
verification passes** (skeptic agents that try to *refute* each rail / recompute each number),
each round's findings fixed and locked with regression tests before the next — loop-until-clean.

- **Pass 1 (`verify-vol-converter`):** the **recommendation numbers all CONFIRMED** to the cent
  (GOOGL/AVGO/MSFT gaps, GRNY/MU funding, NVDA in-band) by independent recomputation from
  `account_positions.json` + `reallocate_config`. **Critical caveat surfaced:** the positions
  snapshot is dated **2026-06-17**, so the *weights* are ~8 days stale vs the 6/24-25 as-of — stamped
  here and in the recommendation (honesty rail). Found 5 code-rail breaks.
- **Pass 2 (hardened module):** confirmed the pass-1 fixes; found 5 deeper breaks (string-shaped
  `protected`, NaN/inf book crash, `_truthy` denylist opening the gate on "not reclaimed",
  phantom-trim on an empty positions lane, missing-actual double-booking).
- **Pass 3 (twice-hardened):** the **core doctrine rails HELD** (don't-chase-by-numbers, gate
  discipline — *0 OPEN leaks across 40+ vectors*, phantom-trim, neutral-flow-never-support). Found 3
  exotic residuals (dict/nested/scalar `protected` shapes, non-iterable lane args, confirmation
  manufactured from `event_confirmation="false"` / a bearish "couldn't beat" headline).

**All findings across the three passes are fixed and regression-tested** (≈41 adversarial tests):
strict affirmative reclaim gate (fail-closed allowlist), `_num` rejects NaN/inf, universal
`_as_list`/`_flat_tokens` safe-iteration + `protected` normaliser, proven-excess-only funding,
phantom-trim skip + honest withhold, `_affirmative` + word-boundary/negation-guarded confirmation,
positive-book guard, conflicted-row + MISSING + ELEVATED honesty notes. Direct re-probes of every
reported vector pass; the production `from_feed` path is verified clean.

**Net:** the in-memory doctrine engine is sound and fail-closed under crafted inputs. The only
deliberately-accepted residual is documented in §2 — `from_feed` reports `regime: NEUTRAL` because
the cached feed lacks structured tape/stances/scored event-risk (the Codex enrichment handoff).
