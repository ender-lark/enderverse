# How To Change A Conviction Input

This page covers the narrow paths for changing conviction inputs without
turning a small source change into scoring surgery.

## Add A Battery Input

Battery inputs are entry-quality evidence only. They do not change conviction
scores directly.

1. Add a pure mapper in `src/battery_evidence.py` that returns either one
   factor or a list of factors using the existing factor contract.
2. Add one source-level entry to `BATTERY_SOURCES` with a stable `key`, mapper,
   input name, call shape, return shape, and the correct `None` behavior.
3. Add a matching line under `battery_sources` in
   `src/conviction_weights.json` with `{"enabled": true, "weight": 1.0}`.
4. Add a focused test proving the default config leaves existing battery output
   unchanged unless the new source is explicitly populated.

## Disable Or Reweight A Battery Input

Edit `src/conviction_weights.json`:

- Set `enabled` to `false` to skip the source entirely.
- Set `weight` between `0.0` and `1.0` to scale only that source's factor
  strengths.

This does not recompute mapper-specific `decisive` booleans and does not feed
the conviction score. Reweighting affects the evidence payload and render
priority only.

## Add Or Replace A Conviction Group Input

Conviction groups live in `src/conviction_engine.py` and are deliberately not a
plugin registry. Changing a group input is a scoring change and should be rare,
explicit, and tested against the locked score oracle.

Use this path only when the input should directly affect `points`, `read`,
`groups`, sizing, and action ranking. Add or update focused tests in
`src/test_conviction_engine.py` before changing group behavior.
