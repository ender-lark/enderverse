# Options Surfacing — wiring guide & paste-ready snippets (2026-06-18)

**Status:** the SURFACING layer is built, tested, and green (full suite **1681 passed / 6 skipped**).
This doc is the coordination handoff for the three touch-points that live in OTHER sessions' lanes
(in-flight / owned files) and therefore were **not** edited from the surfacing session — they are
paste-ready instead.

## What shipped (this session, in-lane)

- `src/options_surface.py` — the producer (`surface_options` / `persist_shadow_log`, built by the
  options-engine session) **plus** the SURFACE + RECALL layer (this session):
  - `render_surface_text(surface)` — plain-language block, **leads with the move**, when / why /
    the-catch on the face, max-loss in **$ AND %**, tripwire when present, checklist + glossary one
    tap deep, freshness stamp. For conversation + any text channel.
  - `render_options_block_html(surface)` — the same, as a self-contained HTML fragment for
    Today-Decide (inline styles; needs none of today_decide's CSS). Honest-empty = always labeled,
    never silent.
  - `cockpit_feed_block(surface)` — a feed-ready `options_expression` dict mirroring
    `asymmetric_opportunities`' row shape (extended for derivatives). `action` carries the sized
    MOVE; `score` is **promotion-ordering metadata only**, never a recommendation.
  - `recall_for_ticker(...)` / `build_options_lane(...)` — single-ticker, in-conversation recall;
    the lane is shaped for `case_file.py` with `blocks=False, alert_eligible=False` always.
  - `apply_no_add_rails(surface, conviction_lookup)` — never yell ACT on a MONITOR/trim/exit sleeve.
- `src/today_decide.py` — **additive, opt-in**: a new `options=` kwarg on
  `build_today_decide_payload`; rendered LOUD below the congruence strip when present (byte-identical
  when absent). Tested in `src/test_today_decide.py`.

Engine (locked, consumed not modified): `options_expression.py`, `options_uw_adapter.py`,
`options_shadow_log.py`. Card contract + doctrine:
`docs/codex_tasks/options_opportunity_surfacing_scope_2026_06_18.md`.

---

## Bundle the producer consumes

`surface_options(bundle, *, conviction_lookup=, account=, as_of=, generated_at=, cfg=)` where:

```python
bundle = {
  "NVDA": {
    "screener": <raw get_stock_screener(ticker="NVDA", limit=1) response>,
    "chain":    <raw get_options_chain(ticker="NVDA", expiry=<≈thesis-horizon expiry>) response>,
  },
  # ... one entry per surfaced/asked conviction name
}
conviction_lookup = { "NVDA": {"direction": "bullish", "conviction_intact": True,
                              "thesis_break": False, "thesis_horizon_days": 90,
                              "recent_options_loss": False, "stance": "ACTIVE"} }
account = {"portfolio_value": <book $>, "open_premium_at_risk": <open long-premium $>}
```

**Live MCP pulls happen UPSTREAM** (a routine or a chat session with the UW MCP), exactly like
`uw_opportunity_scan`'s `--from-bundle` path. The producer stays pure/token-safe.

### Routine / chat fetch sketch (the only place that touches the network)

```python
# For each ACTIVE conviction name (theses minus MONITOR), pull the two cheap reads and bundle them.
bundle = {}
for tk in active_conviction_names:                      # see filter in full_build_runner snippet below
    screener = get_stock_screener(ticker=tk, limit=1)   # iv_rank, iv30d, implied_move_perc, close, ...
    chain    = get_options_chain(ticker=tk, expiry=expiry_for(tk))  # nearest expiry past the horizon
    bundle[tk] = {"screener": screener, "chain": chain}
# write src/options_chain_bundle.json (the cache the file-driven build reads), or pass bundle inline.
```

---

## 1) `full_build_runner.py` (IN-FLIGHT — do not edit; paste when free)

Wire AFTER `assemble_feed()` returns and `feed['asymmetric_opportunities']` is built (≈ line 990), so
the options block can sit alongside the other opportunity surfaces and flow to Today-Decide.

```python
# --- options expression surface (Phase-1 surfacing) ---------------------------------
import options_surface as _opt_surface

options_bundle = _load_optional(src, "options_chain_bundle")  # {ticker: {screener, chain}}, or None
options_surface = None
if options_bundle:
    # ACTIVE conviction universe (mirror feed_assembler endorsement_subjects: exclude MONITOR).
    conviction_lookup = {
        t["ticker"]: {
            "direction": "bearish" if str(t.get("stance", "")).upper().startswith("BEAR") else "bullish",
            "conviction_intact": str(t.get("stance", "")).upper() != "MONITOR",
            "thesis_horizon_days": t.get("horizon_days", 90),
            "stance": t.get("stance", "ACTIVE"),
        }
        for t in (theses or []) if t.get("ticker")
    }
    account = {"portfolio_value": (positions_cache or {}).get("sleeve_value")}
    options_surface = _opt_surface.surface_options(
        options_bundle, conviction_lookup=conviction_lookup, account=account,
        as_of=positions_as_of)
    options_surface = _opt_surface.apply_no_add_rails(options_surface, conviction_lookup)
    _opt_surface.persist_shadow_log(options_surface)          # log near-misses for dial-tuning
    feed["options_expression"] = _opt_surface.cockpit_feed_block(options_surface)  # for the cockpit
# pass `options=options_surface` into the Today-Decide render call:
#   today_decide.build_and_render(..., options=options_surface)
```

Notes:
- `options_chain_bundle` is OPTIONAL — when absent, `options_surface` stays `None`, the cockpit block
  is omitted, and Today-Decide shows nothing new (honest, additive).
- Do **not** regenerate `latest_cockpit_feed.json` / `docs/index.html` / `heartbeat*.json` here unless
  coordinated — `cockpit_feed_block()` only **returns** the dict; the build owner persists it.

## 2) `conviction_cockpit_v5.jsx` (IN-FLIGHT — do not edit; paste when free)

Add a transform mirroring `opportunityPriorityRows`, reading `feed.options_expression`. The
`action` field already carries the sized move, so the row leads with the decision.

```jsx
// near opportunityPriorityRows (≈ line 445)
function optionsExpressionRows(feed, usedTickers) {
  const blk = feed.options_expression;
  if (!blk || !Array.isArray(blk.rows)) return [];
  return blk.rows
    .filter(r => !usedTickers.has(r.ticker))
    .map(r => ({
      key: `opt-${r.ticker}`, score: r.score, ticker: r.ticker,
      title: r.action,                         // LEAD WITH THE MOVE (the sized trade), not the score
      home: "Options expression", source: r.source,
      posture: r.disposition === "ACT" ? "act" : "wait",
      timing: r.decay_window, whyHere: r.reason,
      invalidates: r.the_catch,
      details: r.action, backup: [r.the_catch, r.tripwire_note].filter(Boolean).join(" · "),
    }));
}
// inside todayPriorityRows(...) (≈ line 535), after the opportunity rows:
//   rows = rows.concat(optionsExpressionRows(feed, usedTickers));
// honest-empty: if blk.status !== "has_data", render blk.line (e.g. "checked N … nothing hidden").
```

## 3) `case_file.py` (OWNED by the Ticker-dossier session — do not edit; one-line hook)

In `build_case_file()` (≈ src/case_file.py:482-488, after the verdict / earliest_record / decisions
lanes, before `return base`):

```python
base["options"] = options_surface.build_options_lane(
    ticker, is_equity=base["is_equity"],
    screener=<live get_stock_screener row or None>,
    chain=<live get_options_chain or None>,
    conviction=<{"direction","thesis_horizon_days","stance"} from the verdict/thesis>,
    account=<{"portfolio_value": book}>, as_of=today)
```

The lane honors case_file's honesty contract: `blocks=False, alert_eligible=False` always (an options
idea expresses an existing conviction — it never originates or blocks a decision). Macro/index tickers
(`is_equity=False`) skip with an honest n/a rule; no chain pulled → an honest `data_gap`. Options stay
a separate labeled query — no silent merge of underlier / wrapper / options.

---

## Doctrine the surface enforces (do not regress)

- **Lead with the decision.** Line 1 is `idea["move"]` (the sized trade), never a score or an analysis
  dump. `score` exists only to order cockpit promotion — it is never shown as the recommendation.
- **Plain language, risk loud.** Every term is defined inline via `idea["glossary"]`; max-loss shows
  in **$ AND %**; the loss-chasing tripwire shows when flagged; "a 100% loss is realistic" carries through.
- **Never silent.** Honest-empty uses `summarize_run`: "checked N … nothing hidden" + the closest call.
- **No-add rail.** A MONITOR/trim/exit sleeve is shown for awareness, never yelled as an ACT add.
- **Honesty rails.** Freshness stamp on every render; a sized idea is **never an order** — the operator
  places the trade. No auto-execution anywhere.
```
