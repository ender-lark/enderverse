# Conviction Engine

A 4-layer signal system that turns raw sources into a decision-grade cockpit view.
It is a **supplement** to the live Investing 2026 scripts in `src/` — not a replacement.

> **Boundary:** this folder (`conviction_engine/`) is self-contained. It does **not**
> import from `src/` (the live ~19-script system), and `src/` does not depend on it.
> Build and test the engine in isolation.

The whole thing is built dependency-order and **tested at every seam**: each layer talks to
the next only through a small, validated contract, so a change in one layer can't silently
corrupt another.

---

## The four layers

```
 ① SOURCES            ② COLLECTION           ③ ANALYST              ④ COCKPIT
 plugs that fetch  →  error-tolerant     →  10 reads turn the   →  one React view that
 rows from UW /       runner that bundles    snapshot into a        renders the feed
 Fundstrat / Notion   sources into one       Contract-C feed        (web / mobile)
 / the portfolio      snapshot
        │                    │                      │                      │
   Contract A           Contract B            Contract C            feed_to_cockpit
   (SourceItem)      (CollectedSnapshot)     (CockpitFeed)         seam (toCockpit)
```

**Data flow, end to end:**

```
sources (plugs) ─► collect() ─► CollectedSnapshot ─► assemble_feed() ─► CockpitFeed (JSON)
                                                                              │
                                                          toCockpit() (seam)  ▼
                                                          view-model ─► <ConvictionCockpit feed=…>
```

---

## The three contracts (the seams)

Everything crosses a layer boundary only as one of these shapes. Validators enforce them.

| Contract | Shape | Defined in |
|---|---|---|
| **A — `SourceItem`** | `{source, kind, subject, content, timestamp, trust_weight, independence_group, data}` | `sources.py`, `validators.py` |
| **B — `CollectedSnapshot`** | `{run_id, run_timestamp, items, sources_ok, sources_failed, staleness, critical_missing}` | `collection.py` |
| **C — `CockpitFeed`** | `{generated_at, staleness, hero, fresh_signals, holdings[], rotation[], macro, catalysts, questions, research}` — each holding group is `{cat, rot, pos[]}`; each position carries `{t, n, pct, st, cv, ty, own, lock, fresh, cd, cdNote, nr, dr, be}` | `feed_assembler.py`, validated by `validators.validate_cockpit_feed` |

The **JS seam** (`feed_to_cockpit.js` → `toCockpit(feed)`) is the boundary between Contract C
and the cockpit's display shapes. It is pure CommonJS and node-tested independently.

---

## Sources (① — the v1 plugs)

Six plugs ship today. Each returns dict rows (the plug stamps `source`; rows may override
`trust_weight` / `independence_group` / `timestamp` per item).

| Plug | Independence group | Notes |
|---|---|---|
| `uw_price` | `market_data` | **critical** — sleeve rotation / prices |
| `uw_macro` | `market_data` | curve, DXY, vol |
| `fundstrat_bible` | `fundstrat` | monthly deck: stance, What-to-Own, Top/Bottom-5 |
| `fundstrat_daily` | `fundstrat` | daily notes (the two Fundstrat plugs **collapse to one** independence group) |
| `meridian` | `thematic_research` | **frozen static baseline** (HALEU / rare earths) |
| `portfolio` | `own` | **critical** — held positions |

`CRITICAL_SOURCES = ("portfolio", "uw_price")`. If a critical plug fails, `collect()` records it
in `critical_missing`; a non-critical plug failing is tolerated (one `kind="error"` item, the
pull survives). Before Layer 3 assembly, `collection_gate.validate_collection_gate(...)` layers
Contract-B shape, run/source stamp parsing, critical-source fail-closed behavior, and staleness /
failure-record consistency checks.

---

## Analyst (③ — the ten reads)

`feed_assembler.assemble_feed(bundle, parabolic=…, generated_at=…)` runs ten reads over the
snapshot and emits a Contract-C feed.

**Six mechanical** (`analyst.py`): rotation · macro · staleness · type · hero/needs-you · weight.
**Four judgment** (`analyst_judgment.py`): conviction (`cv`) · conviction-direction (`cd`) ·
net-read (`nr`) · fresh-signal.

- **`cv`** ∈ Strong / Promising / Mixed / Weak / "—" (unassessed). **Single-source cap:** a bare
  external pick with no operator thesis and `<2` independent streams caps at **Promising**, not
  Strong. Strong requires an operator thesis **or** ≥2 independent streams.
- **`cd`** ∈ up / flat / down — event-driven (a source call, a catalyst), **not** daily price.
- **Fresh signals** surface only on `FRESH_SIGNAL_EVENTS = {breakout, new_pick, new_top5, upgrade,
  bottom_in}`. `favorable_shift` drives `cd=up` + a catch-up net-read on the row, but is **not** a
  fresh signal.

---

## Cockpit (④)

`conviction_cockpit_v5.jsx` — a single React component, industrial/utilitarian dark-terminal
aesthetic. It reads **one** Contract-C feed via the inlined seam and renders: header stamp ·
hero banner · Today's actions (fresh signals) · Questions · Market read (rotation + macro) ·
Research · Holdings · Catalysts.

```jsx
// standalone / demo: renders the embedded golden feed
<ConvictionCockpit />
// runtime: render the live feed
<ConvictionCockpit feed={liveFeed} />
```

The `feed` prop defaults to the embedded golden `FEED`, so the file renders on its own; at
runtime the cockpit receives the live feed as a prop. **Questions / Research / Catalysts** are a
small cockpit-curated const (`CURATED`) until the feed emits them — the swap point is documented
inline (`CURATED.X → VM.X`).

---

## The golden master (frozen oracle + regression wall)

The engine is deterministic, so its output is frozen and guarded:

- **`golden_snapshot.json`** — `{as_of, snapshot: <CollectedSnapshot>, theses: [15]}`. 48 SourceItems.
- **`golden_feed.json`** — the corrected oracle in Contract-C shape, the regression anchor.
- **`build_golden.py`** — regenerates both from the snapshot; `--check` is a drift-check.
- **`test_golden_master.py`** (the wall) — asserts the full feed reproduces the oracle exactly,
  plus granular per-name `cv`/`cd`/net-read checks. Proven deterministic across PYTHONHASHSEED.
- **`test_end_to_end.py`** — fixture-replay plugs → real `collect()` → real `assemble_feed()`
  reproduces the oracle exactly (Sources→Collection→Analyst contracts actually run).
- **`full_chain_smoke.py` + `full_chain_render.js`** — the cross-language capstone: real chain →
  live feed (== oracle, regenerated not read) → real seam → complete view-model. The React render
  over that view-model is proven by the SSR smoke-test.

---

## How to run

```bash
# all Python tests: sources → collection → analyst → golden master → end-to-end
python -m pytest -q                       # 257 pass

# JS seam contract test
node test_feed_to_cockpit.js              # 25 assertions

# full-chain capstone (real collect → assemble_feed → seam → view-model)
python full_chain_smoke.py                # needs node on PATH

# golden-master drift check (does the live chain still reproduce the frozen oracle?)
python build_golden.py --check

# regenerate the oracle after an INTENTIONAL change (then re-run the wall)
python build_golden.py

# transform/lint the cockpit (needs esbuild)
npx esbuild conviction_cockpit_v5.jsx --bundle --external:react \
    --format=esm --outfile=/tmp/check.js --loader:.jsx=jsx
```

---

## Runtime wiring (Stage 5 — the handoff)

Dashboard canonicalization:

- Canonical operator dashboard path: render the Contract-C FEED through
  `conviction_cockpit_v5.jsx`, using `render_cockpit.py` to inject a live feed
  into the pinned renderer when needed.
- `docs/index.html` is a generated summary/export path only. Do not add new
  operator meaning there unless the canonical JSX surface is already present or
  the block is intentionally classified.
- Feed-block classification lives in
  `../docs/dashboard_feed_block_classification.json`.

1. **Swap fixture plugs for live ones.** Replace the canned fetchers with real
   UW / Notion / Fundstrat / portfolio fetchers (same `BaseSource(name, fetcher=…)` shape).
2. **Run the chain.** `collect(registry)` → `assemble_feed(bundle)` → a Contract-C feed (JSON).
3. **Render.** Pass that feed to the cockpit as the `feed` prop. The seam runs inside the component.
4. **Skeleton-first.** Stand up only the two `CRITICAL_SOURCES` first — `portfolio` + `uw_price` —
   prove the loop end-to-end, ratify the first run, then add `uw_macro`, the Fundstrat plugs, and
   `meridian`.
5. **Credentials.** UW Bearer token + Notion token live in the cloud-routine environment only —
   **never** in tool calls, never committed.

---

## Design decisions on record

- **ANET → Promising** (single-source cap): one correlated source, no operator thesis → adopt
  before sizing up, don't grade Strong.
- **AVGO → "—"** (unassessed): no thesis line yet; honest **and** required for golden-master
  reproducibility (hand-grading would break determinism). An AVGO-thesis research task is queued.
- **UUUU → burned-lead net-read**: "Hold light — burned + split (Meridian vs FS Bottom-5); watch
  YOUR trigger, no add." The binding re-entry gate is the operator's trigger, not the split resolving.
- **MONITOR stance** (burned sleeves — crypto/ETH, nuclear/uranium, critical minerals): below-T1-floor
  sizing is **intentional**, not a gap. Re-entry only on a high-confidence catalyst / macro regime-turn
  or a defined-risk options structure. These names are excluded from conviction-gap nudges.

---

## Known backlog / nuances (non-blocking)

- **Fresh-signal prose is terse.** The engine emits event tokens; the seam's `PRETTY_EVENT` maps
  the "What:" line to a readable phrase, and "Why:" carries the source context. Richer per-signal
  reasoning is a future Analyst (⑦) enrichment.
- **`be` / "what could break it" not yet engine-populated** (0/18 positions). The panel renders only
  when a break value is present — correct conditional, just no data yet.
- **The seam is inlined in `v5.jsx`** (so the artifact is self-contained) **and** lives in
  `feed_to_cockpit.js` (the node-tested source of truth). A drift check (extract v5's seam →
  deep-compare) keeps them identical. Future option: have the repo build `import` the seam to drop
  the copy entirely.
- **Conflict wording** -- refined 2026-06-05. The net-read now distinguishes a
  true cross-source split from same-source analyst disagreement (for example,
  BMNR Lee vs Farrell inside Fundstrat), while preserving the same Mixed / flat
  enums.
- **Macro implications are empty on a calm regime** (honest). Richer per-sector implications are a
  future enhancement.
- **v4 hand-curated content** (rich rotation notes, macro sector-implications, catalyst taglines) is
  replaced by data-derived versions; the curated catalysts/questions/research consts are placeholders
  until the feed emits them.

---

## Test inventory

| Suite | File | Count |
|---|---|---|
| Sources integration | `test_sources_integration.py` | 8 |
| uw_price / uw_macro | `test_uw_price.py` / `test_uw_macro.py` | 23 / 11 |
| Fundstrat bible / daily | `test_fundstrat_bible.py` / `test_fundstrat_daily.py` | 13 / 13 |
| Meridian / portfolio | `test_meridian.py` / `test_portfolio.py` | 10 / 7 |
| Collection | `test_collection.py` | 29 |
| Validators (contracts) | `test_validators.py` | 39 |
| Analyst mechanical | `test_analyst.py` | 32 |
| Analyst config | `test_analyst_config.py` | 12 |
| Analyst judgment | `test_analyst_judgment.py` | 35 |
| Golden-master wall | `test_golden_master.py` | 7 |
| End-to-end chain | `test_end_to_end.py` | 6 |
| **Python total** | `pytest -q` | **257** |
| Seam contract (JS) | `test_feed_to_cockpit.js` | 25 assertions |
| Full-chain capstone | `full_chain_smoke.py` (+ `full_chain_render.js`) | runner |
