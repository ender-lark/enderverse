# Conviction Engine — Stage 5 Runtime Wiring (Cloud Routine Setup)

**Pairs with** `Morning_Scan_Cloud_Routine_Setup.md` / `Off_Hours_Worker_Cloud_Routine_Setup.md`.
**Status:** Stages 1–4 built + tested (257 pytest · 25 JS seam · golden-master drift-free · full-chain capstone). This doc is the operator-side runtime wiring.

---

## What this is

The Conviction Engine turns live sources into a decision-grade cockpit view. Stage 5 wires the (already-built, already-tested) engine to **live data** and runs it as a Claude Code cloud routine.

**Boundary — this is a SUPPLEMENT, not a replacement.** It **reads + displays**. It does **not** trade, does **not** write canonical Notion state, does **not** size positions. Capital decisions stay with the operator and the live Investing 2026 system. SCOUT posture, same as the Synthesis routines.

---

## The one thing that's actually left

Every plug is **pure-logic + injectable**: the deterministic computation is done and unit-tested with fakes — rel-strength math + rotation labels (`uw_price`), position-card mapping (`portfolio`), the 10 reads, the seam, the cockpit. What is **not** wired is the **live data acquisition**: the thin adapter that pulls real data (UW API, 📊 Latest Portfolio, 📧 Fundstrat Inbox) and hands it to each plug.

> Stage 5 = write the data-acquisition layer, then run `collect → assemble_feed → render`.
> You are NOT rebuilding logic — you are feeding the plugs real numbers.

---

## Prerequisites

1. **Commit the engine** to `conviction_engine/` (manifest in the Build Plan).
2. **Python 3.12** + **node** (the cockpit is a React component; node renders/bundles it).
3. **Credentials — env only, NEVER committed, never in tool calls:**
   - **UW Bearer token** (rotation prices + macro) — already working in your cloud routines.
   - **Notion token** (📊 Latest Portfolio + 📧 Fundstrat Inbox reads).

---

## Skeleton-first (do THIS first — don't wire all six at once)

Wire only the **two critical plugs**, prove the loop end-to-end, ratify, then expand.

| Step | Plug | Live source | Plug entry point |
|---|---|---|---|
| 1 | `portfolio` | 📊 Latest Portfolio (`35ac5031-4bb6-81fc-b792-e50bf86d63f4`) | `portfolio_reader(positions, as_of)` |
| 2 | `uw_price` | UW close prices: 9 sleeve proxies + SPY/SMH, ≥63 trading days | the `uw_price` source maker (rel-strength + label) |

Then: `collect(registry)` → `assemble_feed(bundle)` → feed → render the cockpit. If the feed validates, the cockpit renders, and the sleeve rotation + positions **match the live system** → ratify. Only then add the rest.

`CRITICAL_SOURCES = ("portfolio", "uw_price")` — if either is missing, `collect()` flags `critical_missing` and you should **abort** rather than render a partial cockpit.

---

## The runtime sequence (the routine body)

```
1. ACQUIRE live data per plug (UW pulls, Latest Portfolio read, Inbox read).
2. BUILD the registry — one BaseSource per plug, fetcher = (live data -> plug logic):
      reg = SourceRegistry()
      reg.register(BaseSource(name="portfolio", fetcher=lambda: portfolio_reader(live_positions)))
      reg.register(<uw_price source built from live closes>)
      ...add the rest per phase...
3. snap = collect(reg, run_timestamp=now)          # Contract B
4. GATE: if snap.critical_missing: abort + surface (no partial cockpit)
5. feed = assemble_feed(
            {"as_of": <date>, "snapshot": dataclasses.asdict(snap), "theses": <theses>},
            parabolic=<set of parabolic names>)    # Contract C
6. GATE: assert validate_cockpit_feed(feed) == []
7. EMIT feed JSON  ->  render <ConvictionCockpit feed={feed} />  (or write feed where the cockpit reads it)
```

`theses` is the 15-row bundle (`theses.json` / 🧠 Live Theses) — passed to `assemble_feed`, it is **not** a plug. The cockpit's `feed` prop defaults to the embedded golden feed, so a missing live feed degrades to the demo rather than crashing.

---

## Plug data-acquisition map (what each fetcher pulls)

| Plug | Live source | Independence group | Critical |
|---|---|---|---|
| `portfolio` | 📊 Latest Portfolio page | `own` | **YES** |
| `uw_price` | UW close prices (9 proxies + SPY/SMH) | `market_data` | **YES** |
| `uw_macro` | UW yield curve / DXY / vol | `market_data` | no |
| `fundstrat_bible` | 📌 Latest Fundstrat Bible pointer (`36ec5031-4bb6-8169-ad5e-c8f56a950c0f`) | `fundstrat` | no |
| `fundstrat_daily` | 📧 Fundstrat Inbox 7-day (`354c5031-4bb6-81b5-b88c-f7cdb0e81731`) | `fundstrat` | no |
| `meridian` | frozen static baseline (the Meridian doc) | `thematic_research` | no (static) |

> **Source independence:** `fundstrat_bible` + `fundstrat_daily` collapse to **one** group (`fundstrat`) — the engine already treats them as one correlated bet. Don't re-separate them at the data layer.

---

## The cloud routine

- **Where:** a Claude Code cloud routine (same harness as Morning Scan / Off-Hours Worker).
- **Cadence:** suggest running **after Morning Scan** — the cockpit consumes the same morning data (rotation + macro + Inbox). On-demand is also fine.
- **Posture:** SCOUT — produce the cockpit view; never trade, never auto-write canonical Notion state.
- **Output:** the feed JSON + the rendered cockpit, surfaced to the operator.

---

## First-run ratification (what to check before trusting it)

1. `snap.sources_ok` includes `portfolio` + `uw_price`; `snap.critical_missing == []`.
2. `validate_cockpit_feed(feed) == []`.
3. The cockpit renders; the source-stamp dates look fresh (`as of … · sources: bible …, rotation …, book …`).
4. **Cross-check vs the live system:** sleeve rotation + positions agree with the canonical Investing 2026 read. The engine is a supplement — it must not contradict the canonical system on what you hold. If it disagrees, trust the canonical system and fix the plug's data acquisition.
5. Log the ratification (Build Plan / 📖 Decisions Log, Rule/Research Update).

---

## Phased plug rollout (after the skeleton ratifies)

| Phase | Adds | Cockpit section it lights up |
|---|---|---|
| 1 (skeleton) | `portfolio` + `uw_price` | Holdings + sleeve rotation |
| 2 | `uw_macro` | Market read — macro backdrop |
| 3 | `fundstrat_bible` + `fundstrat_daily` | per-name reads (conviction/why) + Today's actions (fresh signals) |
| 4 | `meridian` | thematic (HALEU / rare-earths) context |

Each phase: wire the one fetcher, re-run, eyeball the newly-populated section against reality, then proceed.

---

## Failure modes to watch

- **`critical_missing` fires** → abort + surface; do not render a partial cockpit.
- **Staleness:** `portfolio` is cadence `on_refresh` (broker-PDF driven, not daily) — the staleness read budgets it accordingly, and a book older than 7 days separately trips the re-upload flag (#PORTFOLIO-READ-LEAD).
- **Drift from the live system** → canonical system wins; fix the plug data, not the cockpit.
- **Token hygiene** → creds in the routine env only, never committed, never in a tool call.
- **Logic/plug change** → re-run `python build_golden.py --check`; if it flags drift, that's a real behavior change — re-freeze deliberately with `python build_golden.py` only after confirming the new output is correct.

---

## Backlog carried into runtime (non-blocking)

- Fresh-signal prose is terse (event token → readable phrase via the seam's `PRETTY_EVENT`; the source context is in "Why:"). Richer per-signal reasoning = a future Analyst (⑦) enrichment.
- `be` / "what could break it" is not yet engine-populated — the panel renders only when present.
- The seam is inlined in `conviction_cockpit_v5.jsx` **and** lives in `feed_to_cockpit.js` (node-tested source of truth); a drift check keeps them identical. Future option: have the build `import` the seam to drop the copy.

---

*Stages 1–4 are frozen and guarded by the golden master + the test suite. This runtime layer is the only remaining piece, and it is additive: pull live data, feed the plugs, render. Start with the two critical plugs.*
