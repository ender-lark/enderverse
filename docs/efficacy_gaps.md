# Efficacy Gaps — miss-classes the trigger spine cannot yet express

Produced by the EFFICACY-HARNESS slice (`src/test_efficacy_harness.py`,
`src/efficacy_scenarios.json`). When a documented miss cannot be encoded as any
current trigger condition type, it is recorded here instead of being faked into
a trigger that does not really catch it. Each entry is a precise spec for a
**future** trigger-type addition — this doc does **not** build the new type.

Current spine condition types (`trigger_check.CONDITION_TYPES`):
`price_cross`, `level_touch`, `iv_threshold`, `date_event`.

---

## GAP 1 — trigger spine cannot yet express **parabolic-acceleration**

- **Miss it blocks:** MU parabolic, 2026-05-27 (`mu-parabolic-2026-05-27` in
  `efficacy_scenarios.json`). MU accelerated into a multi-day blow-off; the
  system "knew" (the screener could score it) but had no armable trigger, so
  nothing pinged.
- **Signal that existed:** rapid rate-of-change — a sharp N-day percent move /
  parabolic slope. `parabolic_setup_screener.py` already classifies this as
  `Phase 3 (parabola)` (`ret_2y > 300 and ret_60d > 25`), and there is a
  scheduled `investing-os-parabolic-cache` routine. That output is a **research
  surface**, never wired into the trigger registry as a firing condition.
- **Why no existing condition type fits:**
  - `price_cross` and `level_touch` fire on a **fixed price** (a level or a
    zone). A parabolic move has no single pre-known level — picking one after
    the fact is hindsight, and a slow grind to the same level would fire it
    falsely.
  - `iv_threshold` fires on an **IV level**, not on price velocity.
  - `date_event` fires on a **calendar date**, unrelated to price action.
  - None encode "price rose X% over N days", "consecutive up days >= K", or
    "entered Phase 3", which is what a parabolic-acceleration trigger needs.

### Spec for the future condition type (do NOT build here)

A new `CONDITION_TYPES` member, e.g. `acceleration` (or `parabolic`), evaluated
from a quote that carries velocity, not just a last price. Proposed params:

| param | meaning |
| --- | --- |
| `field` | velocity field on the quote, e.g. `pct_change_5d` / `pct_change_20d` |
| `threshold` | percent move that arms the fire, e.g. `40` |
| `operator` | `above` (default) / `below` |
| `min_consecutive_up_days` (optional) | additional slope confirmation |

It would slot beside the existing `_evaluate_*` helpers as
`_evaluate_acceleration(row, quote)` returning the same `(fired, reason)` tuple,
and `evaluate_registry` would route `condition_type == "acceleration"` to it.
The cleanest data source is the existing parabolic cache / `phase` classifier,
surfaced onto the quote (e.g. `phase`, `pct_change_5d`) so the spine stays the
single place that turns a known signal into a push.

### Honest fallback until it exists

Today a parabolic miss is **not** silently cleared. An armed trigger whose
condition type is not in `CONDITION_TYPES` is routed to `not_checked` with
reason `unsupported condition ...` (proven by
`test_mu_parabolic_is_a_coverage_gap_not_a_false_all_clear`). That is the
correct honest behaviour — a real gap shows up as "not checked", never as
"all clear" — but it means the parabolic class is **armed-but-dead** until the
condition type above is added. That is the cost this doc is tracking.
