# Efficacy Gaps — miss-classes and how the trigger spine expresses them

Produced by the EFFICACY-HARNESS slice (`src/test_efficacy_harness.py`,
`src/efficacy_scenarios.json`). When a documented miss cannot be encoded as any
current trigger condition type, it is recorded here instead of being faked into
a trigger that does not really catch it. Each entry is a precise spec; once the
spine can express the class, the entry is marked **RESOLVED** with the slice/PR
that closed it.

Current spine condition types (`trigger_check.CONDITION_TYPES`):
`price_cross`, `level_touch`, `iv_threshold`, `date_event`, `acceleration`.

---

## GAP 1 — parabolic-acceleration — **RESOLVED 2026-06-14 (PARABOLIC-TRIGGER slice, PR#29)**

- **Miss it blocked:** MU parabolic, 2026-05-27 (`mu-parabolic-2026-05-27` in
  `efficacy_scenarios.json`). MU accelerated into a multi-day blow-off; the
  system "knew" (the screener could score it) but had no armable trigger, so
  nothing pinged.
- **Signal that existed:** rapid rate-of-change — a sharp N-day percent move /
  parabolic slope. `parabolic_setup_screener.py` already classifies this as
  `Phase 3 (parabola)` (`ret_2y > 300 and ret_60d > 25`), and there is a
  scheduled `investing-os-parabolic-cache` routine. That output was a **research
  surface**, never wired into the trigger registry as a firing condition.
- **Why the original four condition types could not fit:**
  - `price_cross` and `level_touch` fire on a **fixed price** (a level or a
    zone). A parabolic move has no single pre-known level — picking one after
    the fact is hindsight, and a slow grind to the same level would fire it
    falsely.
  - `iv_threshold` fires on an **IV level**, not on price velocity.
  - `date_event` fires on a **calendar date**, unrelated to price action.
  - None encode "price rose X% over N days", "consecutive up days >= K", or
    "entered Phase 3", which is what a parabolic-acceleration trigger needs.

### What was built (the resolution)

1. **New `acceleration` condition type** in `trigger_check.CONDITION_TYPES`,
   evaluated by `_evaluate_acceleration(row, quote)` from a quote that carries
   *velocity*, not just a last price. It supports any combination of three
   sub-checks, **all of which must pass to fire (AND)** so a confirmation never
   loosens the trigger:

   | param | meaning |
   | --- | --- |
   | `field` (default `pct_change_5d`) | velocity field read off the quote |
   | `threshold` / `level` | percent move that arms the fire, e.g. `40` |
   | `operator` / `direction` | `above` (default) / `below` |
   | `min_consecutive_up_days` (optional) | slope floor vs quote `consecutive_up_days` |
   | `min_phase` (optional) | parabolic-phase floor vs the screener's `phase` (`"Phase 3 (parabola)"` → 3) |

   A slow grind to the same price prints a small percent move and a lower phase,
   so it does **not** fire. When a configured sub-check's velocity field is
   absent the evaluator returns a `no quote` / `acceleration missing` reason and
   the spine routes the trigger to `not_checked` — never a false all-clear. The
   trigger is idempotent: it fires once, then sits in a terminal state.

2. **Auto-registration hook** in `parabolic_setup_screener.py`
   (`phase3_acceleration_trigger` / `register_phase3_acceleration_triggers`,
   plus a `--register-triggers` CLI flag). When the screener classifies a name
   as `Phase 3 (parabola)` it arms an `acceleration` trigger via the existing
   registry path (`load_registry` → `upsert_trigger` → `save_registry`). It is
   **additive** — the research-surface output (`render_text_report` /
   `build_emit_payload`) is unchanged — and **idempotent** (re-running upserts
   the same `parabolic-accel-<ticker>` id without duplicating or resetting a
   fired trigger).

3. **Live arming:** MU is parabolic and IV-pinned right now, so
   `parabolic-accel-mu` is armed in `trigger_registry.json` (matching the hook's
   output shape, so a screener re-run upserts in place).

4. **Efficacy proof:** `mu-parabolic-2026-05-27` is now an `expressible`,
   `real_registry` scenario. The harness replays the 5/27 acceleration through
   the live `acceleration` trigger and asserts it fires exactly once, emits a
   push payload, is idempotent, does **not** fire on a slow grind, and is
   `not_checked` (never a false all-clear) when velocity data is missing — the
   same standard the other three misses are held to. **All four documented
   misses are now proven-caught.**

### Remaining sub-aspect (named, not silently dropped)

The condition type and the registry arming are complete, but the **live quote
cache does not yet surface velocity**. `trigger_check.load_quote_cache` builds
quotes from `uw_closes.json` (price/last/close only); it does not yet attach
`pct_change_5d` / `consecutive_up_days` / `phase`. Until that enrichment lands,
an armed `acceleration` trigger evaluated by the scheduled trigger-check routine
is honestly reported as `not_checked` (correct per the Data Honesty rail), and
MU must also be present in the screened universe (it is not in
`CANDIDATE_PROFILES` today) for the screener to auto-arm it on its own. The
clean follow-up is to surface the parabolic cache's `phase` (and a computed
`pct_change_Nd`) onto the quote so the spine stays the single place that turns a
known signal into a push. This is a wiring task, not a spine gap: the
acceleration vocabulary now exists and is proven.
