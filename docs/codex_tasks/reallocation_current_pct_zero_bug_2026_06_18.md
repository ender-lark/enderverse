# BUG (engine lane): reallocation_brief reads `current_pct = 0` for already-held names → mis-sized build-to-target adds

**Filed:** 2026-06-18 (~10am ET) by the render/decision-surface chat after running the live
"final check" on the GOOGL add the operator surfaced. **Lane: ENGINE** (reallocation packet /
`directive_recs.py` / conviction sizing). The render only DISPLAYS what the brief provides — it
must not "fix" this by netting in the renderer.

## What's wrong
On the live `src/latest_cockpit_feed.json` (generated 2026-06-18T13:53Z, `positions_as_of` 2026-06-18),
the GOOGL reallocation row reports the position as **empty** while the portfolio actually holds a
meaningful GOOGL position:

| field (reallocation_brief.rows GOOGL) | value |
|---|---|
| `current_pct` | **0.0** |
| `effective_current_pct` | **0.0** |
| `target_pct` | 8.0 |
| `notional_usd` | **153,472.96**  (= 8.0% of the $1,918,412 book) |

But `portfolio_views.views.combined` holds **GOOGL = $90,912** (~**4.7%** of book), split across
accounts (SKB ~$55,619 + Parents ~$35,293; even the brief's *target* account, Parents Fidelity
Joint WROS-TOD ...2063, already holds ~$29,109 GOOGL). So `current_pct` should be ~4.7%, not 0.

The funding side is fine — the trims (GRNY/IVES/SMH/MAGS) are read from real positions and sum
correctly. It is specifically the **add row's current-holding read** that comes back as zero.

## Impact (why it matters)
The add is sized as if you hold **zero** of the name, so it adds the **full target weight** instead
of the gap to target:
- Placing the GOOGL add as written ($153,473) on top of the existing $90,912 lands GOOGL at
  **~12.7% of book** — well over the 8% target.
- The correct add to reach 8% is **~$62,500** (`target_usd − current_usd` = 153,473 − 90,912).
- This is systemic: **every** "X% target" build-to-target add will be oversized by whatever is
  already held until the current-position read is fixed. This is a right-sizing / over-concentration
  hazard, the opposite of the primary goal.

## Likely cause (for you to confirm)
The reallocation/`directive_recs` current-position read isn't netting existing holdings into
`current_pct`/`effective_current_pct` for the ADD rows (works for TRIM rows). Possible angles:
ticker/account mapping (e.g., GOOGL vs GOOG, or a per-account view that excludes the lots), a
snapshot source that differs from `portfolio_views.combined`, or the add-sizer assuming a 0 base.

## Fix (engine)
- Compute `current_pct`/`effective_current_pct` from the **same combined, all-account** positions
  the portfolio view uses, so held names read their true weight.
- Size the add as `max(0, target_usd − current_usd)` (gap to target), not the full target.
- Add a regression test: a held name (e.g., GOOGL at ~4.7%) with an 8% target produces an add of
  ~3.3% of book, not 8%.

## Paste-ready prompt for the engine/Codex chat
```
You own the conviction engine + reallocation packet (directive_recs.py / the reallocation brief /
conviction sizing). BUG to fix (evidence in docs/codex_tasks/reallocation_current_pct_zero_bug_2026_06_18.md,
verified on the 2026-06-18 feed): the brief reports GOOGL current_pct=0 / effective_current_pct=0 and
sizes the add to the FULL 8% target ($153,473), but portfolio_views.combined already holds ~$90,912
GOOGL (~4.7% of book) across SKB+Parents. So build-to-target ADD rows ignore existing holdings and are
oversized by whatever is already held (GOOGL would land ~12.7% vs the 8% target; correct add ~$62.5k).
TRIM rows read real positions fine — it's the ADD current-holding read that returns ~0.

SETUP: git fetch; work off origin/main in a fresh worktree. Verify against origin/main + the live feed.
FIX: make current_pct/effective_current_pct read the SAME combined all-account positions the portfolio
view uses, and size each add as max(0, target_usd - current_usd) (gap to target), not the full target.
Add a regression test (held name at ~4.7% + 8% target -> ~3.3% add). Keep the suite + verify_standard
green; rebase before push. ENGINE LANE ONLY — the render (today_decide.py) correctly displays whatever
the brief provides; do not net in the renderer. Coordinate with the F2 sizing work; this is upstream of it.
```
