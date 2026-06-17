# Two-Layer Conviction Model Council Proposal

Date: 2026-06-16
Owner: Codex
Status: operator approved the safe shadow slice after Claude architecture review.
Do not flip the live card score/ranking from legacy conviction to combined
overall conviction until the shadow split has been reviewed on real cards for a
couple of weeks and the activation gate is explicitly approved.

## Why This Exists

The current conviction engine answers "how strong is the evidence for this
ticker?" as one signed score. That is clean, but it misses a common investing
case: a sector or sleeve can be decisively supported while the individual name
has little fresh single-name evidence, or the sector can be strong while the
name-specific tape is bearish.

The goal is not a prettier model. The goal is faster, clearer action triage:

- Is the sector/sleeve wind at our back or in our face?
- Is this specific name confirmed, weak, or not checked?
- What is the one overall act/pass conviction read after those two layers are
  reconciled?

## Current Contracts Verified On Main

- `src/conviction_engine.py` has one signed score today: `points`, `read`,
  `strength_5`, and `direction`.
- The direct scoring groups are explicit: `fs`, `uw`, `operator_insight`, and
  `institutional`.
- `src/directive_recs.py` already uses `conviction["points"]` in action
  priority for buy/add and sell/trim cards.
- `src/today_decide.py`, `src/TodayDecide.jsx`, and `src/cockpit_html_gen.py`
  consume the single render-ready `conviction_display` payload.
- `src/feed_assembler.py` already has a ticker-to-sleeve map (`NAME_SLEEVE`)
  and sleeve display labels (`SLEEVE_CAT`). That is useful precedent, but it is
  UI/feed glue today, not a scoring contract.

Because `points` feeds ranking and action promotion, any change to the score is
a doctrine/scoring change. This proposal is the gate before implementation.

## Approved Shadow V1 Dials

These values are judgment defaults, not calibrated truths. They are named
tunables in `src/conviction_weights.json` and queued for revisit after graded
outcomes exist.

- `mode`: `shadow`. Compute and render the split in the drawer, but leave live
  ranking, sizing, and the card-face conviction line on the legacy score.
- `sector_weight`: `0.33`.
- `sector_lift_cap`: `0.5`. This matches the existing ceiling for weak or
  suggestive evidence such as single-day options flow.
- `sector_only_capital_action_allowed`: `false`. A hot sector with no fresh
  name evidence can only produce a recheck posture, never a buy/add action.
- `sector_only_alert_enabled`: `false` for the shadow PR. The alert-policy hook
  is present and tested, but suppressed until explicitly enabled.
- Sector lift affects shadow rank/urgency interpretation only. It does not
  affect dollar sizing.
- Sleeve proxy tickers such as `SMH`, `SOXX`, `IGV`, `URA`, `URNM`, `REMX`,
  `XLE`, `XOP`, `XLF`, `GDX`, and `IBIT` get `not_applicable` sector status so
  the same view is not counted as both name and sector evidence.
- Broad market gauges such as `SPX`, `SPY`, `QQQ`, `IWM`, `RSP`, `VIX`, `DXY`,
  `TNX`, and `TLT` feed market context only. They do not auto-lift individual
  names.
- Sector shelf lives: daily tactical calls `7` days, monthly stances `35` days,
  catalyst backstop `35` days unless a future resolver is wired.

Claude review also added three hard guardrails:

- If name-specific evidence is negative, positive sector lift is clamped to
  zero for the combined number. A hot sector cannot rescue a name whose own tape
  is bad.
- A given source-call row scores in one layer only, and same-source same-week
  sleeve views are deduped to avoid correlated Fundstrat inflation.
- Sector lift may raise the read band by at most one notch and can never print
  `HIGH` when name evidence alone is below the moderate threshold.

## Proposed Contract

Add a shadow payload first, without changing existing top-level conviction
fields:

```json
{
  "conviction_layers": {
    "legacy": {
      "points": 0.0,
      "read": "LOW",
      "strength_5": 1,
      "direction": "neutral"
    },
    "sector": {
      "points": 0.0,
      "read": "LOW",
      "strength_5": 1,
      "direction": "neutral",
      "status": "checked_no_signal",
      "sleeve": "SMH",
      "category": "AI / Semiconductors",
      "mapped_from": [],
      "why": [],
      "not_checked": []
    },
    "name": {
      "points": 0.0,
      "read": "LOW",
      "strength_5": 1,
      "direction": "neutral",
      "status": "checked_no_signal",
      "groups": {},
      "why": [],
      "not_checked": []
    },
    "overall": {
      "points_decimal": 0.0,
      "read": "LOW",
      "strength_5": 1,
      "direction": "neutral",
      "sector_lift": 0.0,
      "sector_lift_cap": 0.0,
      "conflict": null,
      "formula_version": "proposal"
    }
  }
}
```

The existing `conviction.points`, `conviction.read`, `conviction.strength_5`,
`conviction.direction`, and `conviction_display` must stay byte-identical in
the first build slice unless an explicit activation flag is approved later.

## Layer Definitions

### Name-Specific Layer

Name-specific conviction is the current direct-ticker score after excluding
sector-only evidence. It should include:

- Fundstrat rows whose `ticker` equals the card ticker.
- Same-session UW state for the ticker.
- Operator insight rows that explicitly map to the ticker.
- Institutional state when that lane becomes real.

This layer is the only layer that can prove "this name specifically is ready."

### Sector/Sleeve Layer

Sector conviction is evidence about the sleeve, industry, ETF proxy, or broad
factor that should inform the name but should not masquerade as name evidence.
It can include:

- Fundstrat source-call rows whose subject is a mapped sleeve proxy such as
  `SMH`, `SOXX`, `IGV`, `XLF`, `URA`, `URNM`, `REMX`, `XLE`, `XOP`, `IBIT`,
  or `GDX`.
- Fundstrat Bible category cues when they are fresh enough for their cadence.
- Existing holdings rotation labels where the feed has a checked group read.

It should not include unsupported or inferred feeds. For example, the current
UW sector endpoint is not a usable source if the live proof says sector is an
unsupported path parameter. That stays `not_checked`.

### Overall Layer

Overall conviction is the single act/pass number after reconciling name and
sector. After activation, this should be the only number shown as the primary
conviction score. Sector/name subreads are explanatory drawer details, not
competing card-face scores.

## Recommended Formula Shape

The exact weights need Council approval, but the safe shape is:

```text
overall_decimal = name_points + bounded_sector_lift
bounded_sector_lift = sign(sector_points) * min(abs(sector_points) * sector_weight, sector_lift_cap)
```

Recommended rails:

- Sector lift is bounded. A strong sector can raise attention and urgency, but
  should not by itself create a high-conviction single-name action.
- Sector-only support can promote research/recheck priority, not capital action,
  until Council explicitly approves otherwise.
- Negative name-specific evidence overrides or caps positive sector evidence
  and sets a prominent conflict.
- Positive name-specific evidence with negative sector evidence can still act,
  but the sector drag must be visible and may lower urgency/size.
- Broad market calls such as `SPX` or `QQQ` should be separate market context
  unless explicitly mapped. They should not automatically lift every ticker.

## Mapping Contract

Do not make scoring depend directly on `feed_assembler.NAME_SLEEVE`. Instead,
create an explicit scoring-owned map, seeded from the existing sleeve map and
reviewed by the operator:

```json
{
  "ticker_to_sleeve": {
    "NVDA": "SMH",
    "AVGO": "SMH",
    "MU": "SMH"
  },
  "sleeve_subjects": {
    "SMH": ["SMH", "SOXX"],
    "IGV": ["IGV"],
    "XLF": ["XLF"]
  },
  "broad_market_subjects": ["SPX", "QQQ", "IWM"]
}
```

Missing map behavior:

- If a ticker has no map, sector layer is `not_checked: ["sector_map"]`.
- If a ticker is itself a sleeve proxy, sector layer is `not_applicable`.
- If a mapped sleeve has no checked evidence, sector layer is
  `checked_no_signal`, not `not_checked`.
- If sector evidence exists but is stale or blocked by the staleness guard, it
  is not actionable and must carry the source-health reason.

## UI Principle

After activation, the card face should still show one dominant conviction line:

```text
Conviction to Buy NVDA: 4/5 (HIGH)
```

The one-tap breakdown should show:

- Overall: the one action read.
- Name-specific: direct evidence for or against this ticker.
- Sector/sleeve: lift or drag applied, capped amount, and source rows.
- Conflict: prominent when sector and name disagree.
- What would raise it: exact missing evidence.
- Not checked: compact and last.

No second competing score should appear on the card face.

## Tests And Invariants For Any Build

Required before any implementation PR can merge:

- Default-off shadow payload leaves legacy `conviction()` output and action
  ranking byte-identical.
- Existing conviction score oracle remains unchanged when activation is off.
- Sector-only support cannot produce a capital-action promotion unless an
  activation flag and Council-approved formula allow it.
- Bearish name-specific evidence plus bullish sector evidence produces a
  conflict and does not hide the bearish name evidence.
- Bullish name-specific evidence plus bearish sector evidence shows sector drag
  and preserves the conflict in render payloads.
- Missing ticker map produces `not_checked`, while mapped-but-quiet sleeves
  produce `checked_no_signal`.
- Stale Fundstrat/source-call state blocks sector evidence from being treated
  as current.
- HTML and React renderers consume the same payload and do not re-derive layer
  logic.

## Proposed Build Slices After Approval

1. Shadow contract only: add a pure mapper and `conviction_layers` payload with
   activation off. Legacy output and rankings must be unchanged.
2. Renderer explanation: expose layer details in the breakdown only. Keep the
   existing top-line score unless activation is approved.
3. Formula activation: behind a config flag, switch the primary score to
   `overall`. Add golden tests for ranking/action-card changes.
4. Calibration loop: compare outcomes where sector was strong but name evidence
   was missing, conflicted, or confirming. Tune only with evidence.

## Model Council Questions

- Which sector/ETF subjects are valid sleeve proxies for scoring, and which are
  market context only?
- What is the maximum allowed sector lift?
- Can sector-only support ever create a buy/add card, or only a research/recheck
  card?
- Should sector lift affect suggested size, urgency, both, or neither?
- How should ETF cards such as `SMH` differ from constituent cards such as
  `NVDA`, `AVGO`, and `MU`?
- What is the required shelf life for sector calls by source type?

## Recommendation

Approve the two-layer direction, but build it in shadow mode first. The first PR
should prove no behavior change at default config and make sector/name
decomposition inspectable. Only after review should the system use `overall` for
ranking, sizing, or action promotion.
