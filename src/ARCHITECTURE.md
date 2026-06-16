# Conviction Engine — Low-Level Architecture & Design Decisions

*The deep reference for the cockpit/feed engine (`conviction_engine/`). Pairs with the high-level six-layer doc (`Investing_2026_System_Architecture` / the Notion "🏗️ System Architecture" page) — that one says **how the layers fit**; this one says **how the engine works inside L4–L6 and why each piece is shaped the way it is**.*

*Status: v1.0 — written 2026-06-02, immediately after the `research_actions` ("From Research") build. Living doc: when an engine module or the feed contract changes materially, update the relevant section **here**, then the code/CI.*

---

## 0 · How to use this doc

Read this when you're about to **touch the engine** (add a lane, change a read, alter the feed shape, edit the renderer) — not at session-open (the high-level doc is for orientation). The order that's worked: (1) find the **seam** you're crossing in the high-level doc, (2) come **here** for the exact function/contract on each side, (3) make the change contract-first, (4) re-freeze the golden + run the suite + `--selftest`.

The engine is **deterministic and pure**: it turns supplied state into a validated FEED and nothing else (no I/O, no judgment). That property is load-bearing — it's why the same code runs identically in the cloud routine (L5) and in a live preview, and why the golden-master test can pin exact output. Don't break it (no network calls, no clock reads except where a caller passes a stamp, no Notion access inside the engine).

---

## 1 · The feed pipeline (entry points)

The pure engine entry points live in `runtime_skeleton.py` and wrap `assemble_feed` (`feed_assembler.py`). The repo-owned routine entry point is `full_build_runner.py`: it loads convention files from `src/`, adapts cached positions into the same source rails, normalizes catalyst rows, calls `assemble_feed`, and can publish through the existing gate.

The **caller** (the L5 cloud routine, Codex runner, or a live preview) gathers state and passes it in; the engine assembles + the caller publishes.

| Entry point | Used by | Builds |
|---|---|---|
| `full_build_runner.py --src-dir src ...` | Codex/FULL routine control point | loads convention files, builds a validated FEED, optionally publishes |
| `build_full_feed(...)` | L5 Early build (~8:50 AM ET) and FULL build (~10:30 AM ET) | the complete FEED from available convention inputs; the early build must leave later synthesis/UW/parabolic inputs honest when they have not run yet |
| `build_skeleton_feed(...)` | the "Dashboard" fast-view | book + rotation only; Tier-1 panels in empty-state; dark lanes stamped |
| `assemble_feed(bundle, *, parabolic, generated_at, heartbeat, synthesis, research, radar, catalysts)` | both of the above (+ tests) | the actual assembly; returns the FEED dict |
| `publish_cockpit_feed.py --feed <feed.json> ...` | L5/operator publish boundary | validates the finished FEED, writes the publish artifact, then updates `open_opportunities.json` |

**`build_full_feed` is a pass-through**: it forwards `research`, `catalysts`, `synthesis`, `heartbeat`, `radar` into `assemble_feed` and **returns its output unchanged**. Consequence that matters: any new feed key `assemble_feed` emits appears in the FULL build automatically — no routine-prompt change needed (this is exactly why `research_actions` shipped without touching L5).

**Side effects live after the publish gate.** The daily routine should build the
FEED first, then call `publish_cockpit_feed.py`. That runner runs
`publish_gate.validate_publish_gate(feed)` and fails closed: if the feed is stale
or malformed it writes neither the latest feed artifact nor action memory. If the
gate passes, it writes the optional feed copy and calls
`runtime_skeleton.update_action_memory_after_publish(...)`, which keeps
unresolved opportunities durable across days.

**External vs derived inputs** (critical distinction):
- **Derived from the book** (the engine computes them): `holdings`, `rotation`, `hero`, `fresh_signals` (⑦), the needs-you list (⑧), `actions` (⑦b), `research_actions` (⑦c).
- **External reads, passed in by the caller** (the engine only threads/shapes them): `synthesis`, `research`, `heartbeat`, `radar`, `catalysts`, `signal_log`, `social_watch`, `macro` (via the snapshot), `generated_at`.

If an external input is `None`, the engine defaults it (`research or {}`, `catalysts or []`, …). So a quiet/empty external lane is **not** an engine bug — it's an empty input. (See §10, the canonical 6/1 lesson.)

---

## 2 · The FEED contract (the L4→L5→L6 payload)

The single artifact every layer agrees on. Validated by `validators.validate_cockpit_feed` (Contract-C). Keys:

| Key | Source | Shape | Lane / panel |
|---|---|---|---|
| `generated_at` | caller (clock) | ISO string | build stamp |
| `staleness` | engine | `{stamp, entries[], stale[]}` | heartbeat freshness |
| `hero` | engine (book) | `{hero:{count,names,leading_sleeves}, needs_you:{count,items}}` | hero strip |
| `holdings` | engine (book) | `[{cat, rot:{w}, pos:[…]}]` | the book |
| `rotation` | engine (prices) | `[{subject,label,rel_1m,rel_3m,…,note}]` | rotation |
| `macro` | caller (UW) | `{line, regime:{…}, alerts[], implications[]}` | macro |
| `fresh_signals` | engine ⑦ (book) | `[…]` | (feeds actions) |
| `signal_log` | caller (Morning Scan) | `[{ticker?, signal/title/what/summary, ...}]` | Signal Log watch-only lane |
| `social_watch` | caller (`social_watch.py` normalized cache) | `{status,line,count,rows[]}` | Social Watch, watch-only Reddit/social anomaly lane |
| `actions` | engine ⑦b | `[action-row]` | **Today's actions** |
| `market_open_packet` | full build (`market_open_packet.py`) | `{status,line,counts,rows[]}` | **Market-Open Packet** sequencing/re-check aid |
| `research_actions` | engine ⑦c | `[action-row]` | **From Research** (new) |
| `catalysts` | caller (Catalyst Calendar) | `[{ticker,label,date,days_out,source}]` | Upcoming catalysts |
| `questions` | caller / curated | `[…]` | open questions |
| `research` | caller (Research Queue) | `{pending:[{r,pr,…}], done:[…]}` | Research panel |
| `heartbeat` | caller | `[{layer,status,last_run,note}]` | heartbeat strip |
| `synthesis` | caller (Daily Synthesis) | `{state_of_play,delta,hanging[],source,date}` | today's read |
| `radar` | caller (daily calls) | `[{ticker,author,direction,entry,stop,target,window,date,quote}]` | Radar |
| `target_drift` | full build (positions vs reallocate_config) | `{status,line,actionable_count,rows[]}` | Target Drift |

**The action-row shape** (`_ACTION_REQUIRED` in `validators.py`) — shared by `actions` **and** `research_actions`:
```
rank:int · kind:str · ticker:str|None · what:str · confidence:"High"|"Moderate"|"Low"
· your_move:str · gate:dict|None · source:str · why:str   (+ optional days_to_catalyst:int)
```
Reusing one row shape is deliberate — it lets the renderer's single `actionRow` mapper render both lanes (see §5).
The full dashboard enrichment layer may add optional decision metadata such as
`freshness_judgment`, `disconfirmation`, `capital_efficiency`, and
`account_placement`, and `market_open_packet`; these fields are operator
guidance, not order instructions. `account_placement` is derived from current
account-position rows by `account_trade_placement.py`; Parents Schwab/PCRA Trust
is treated as ETF-only, so ETF add candidates are steered there when possible
and individual-stock add candidates avoid it.

**Optional-block pattern (forward-compat).** `actions`, `catalysts`, `questions`, and `research_actions` are **validated-if-present**: absent → still valid. *Why:* a feed built by an older routine (before a key existed) must still pass the publish gate and render. This is what let `research_actions` land without breaking any stored/old feed. When you add a lane, follow this pattern — never make a new key required.

---

## 3 · The reads (`analyst_judgment.py` — the "brain")

Pure functions over the book + the external plugs. The numbering (⑦, ⑧, …) is the assembly order in `assemble_feed`.

- **⑦ `fresh_signal_read(...)`** — scans the book for *fresh movement* signals. Empty when prices are flat/stale (a symptom, not a bug).
- **⑧ `hero_needs_you_read(..., fresh_signals=, catalyst_imminent=)`** — builds the "what needs you" list: macro alerts, MONITOR re-entry conditions, gate items, **and** folds in catalyst-imminent items (below).
- **`catalyst_needs_you(catalysts, held_tickers, theses, *, horizon_days=7)`** — turns *dated catalysts on HELD names* into needs-you items with reason `catalyst_imminent` (0..horizon days out). Burned/MONITOR sleeves → the catalyst is a WATCH/RISK flag, **never** an add nudge. L5 should normalize fetched calendar rows through `runtime_adapters.catalysts_from_calendar_rows(...)` before passing them into `build_full_feed`.
- **⑦b `actions_read(fresh_signals, needs_you_items, theses, *, synthesis_actions=None)`** — the **Today's actions** list. **Additive**: it ranks what ⑦ + ⑧ hand it (including `catalyst_imminent` items) plus conservative Daily Synthesis action candidates from `synthesis_actions_read(...)`. It does **not** invent from vague prose: structured `synthesis.actions` are preferred; ticker-led actionable `hanging` items can promote. Ranks via `_ACTION_PRIORITY` (e.g. `red_gate` > `buy_now` > `synthesis` > `catalyst_imminent` > …), confidence via `_CONFIDENCE_RANK`.
- **⑦c `research_actions_read(research, theses, taken_tickers=None, *, horizon_days=7, include_priorities={"high","med","medium"})`** — the **From Research** list (the 2026-06-02 build). Detailed below.

### 3.1 · `research_actions_read` — the From-Research surface

**Purpose:** surface ticker-specific Research-Queue dossiers as their **own** candidate-action category — *not* blended into Today's actions, *not* in the catalyst list.

**Logic, in order, per `research.pending` item `{r, pr, …}`:**
1. **Parse ticker** from the leading `"TICKER — …"` token (`_parse_research_ticker`, regex `^\s*([A-Z]{1,6}(?:\.[A-Z]{1,4})?)\s*[—–:\-]`). No leading ticker → **skip** (process/governance items stay in the Research panel; they're not trade actions).
2. **Filter:** keep if `pr ∈ {high, med}` **OR** a structured near-term date (`days_out` within `horizon_days`). The **date clause is dormant** today — live research items carry only `{r, pr}`, no `days_out`; it activates automatically if the routine starts emitting dates.
3. **Dedup (catalyst-precedence):** if the ticker is in `taken_tickers` (the caller passes the **union of `actions` + `catalysts` tickers**) → **drop**. So a name surfaces exactly once and From-Research *yields* to the sharper dated driver.
4. **MONITOR stance** (from `theses`) → `gate=None`, confidence forced `Low`, copy = "review/risk-check only; no add absent YOUR re-entry trigger." Non-MONITOR → a provisional `REVIEW` gate hook + priority-mapped confidence (high→High, med→Moderate).
5. **Rank:** sort by (priority, confidence, first-seen); assign contiguous `rank` from 1.

**Wiring** (`feed_assembler.assemble_feed`): after `actions`, `taken = {action tickers} ∪ {catalyst tickers}`; `research_actions = research_actions_read(research or {}, theses, taken)["research_actions"]`; added to the returned dict.

---

## 4 · Validators / Contract-C (`validators.py`)

`validate_cockpit_feed(feed) -> [problems]` — structural truth for the feed. Required top-level keys + per-block shape checks. Action rows checked by `_validate_action` (the row shape above + `kind ∈ _VALID_ACTION_KINDS`). `_VALID_ACTION_KINDS` now includes `research_review` (the From-Research kind) alongside `buy_now`, `catalyst_imminent`, `macro_alert`, etc.

`publish_gate.assert_valid_publish_gate(feed)` (`publish_gate.py`) is the **L5→L3 publish contract** = Contract-C structure **+** a real-clock `generated_at` (within ±2h of the run) **+** macro plausibility (catches the 6/1 "DXY 27.76" mislabel). It reuses `validate_cockpit_feed` and adds the stamp/plausibility checks. It does **not** reject unknown keys, so additive feed keys pass — verified for `research_actions`.

---

## 5 · The renderer (`conviction_cockpit_v5.jsx` — L6)

Pure render of the injected `feed`. Default export `ConvictionCockpit({ feed = FEED })` — `FEED` is a baked golden literal (the default/example); a live feed is injected at render time (see §6).

- **`toCockpit(feed)`** — the view-model. Maps each feed key to a render-ready shape: `actions:(feed.actions||[]).map(actionRow)`, `researchActions:(feed.research_actions||[]).map(actionRow)`, `holdings`, `rotation`, `radar`, `heartbeat`, `synthesis`, `hero`, `macro`, plus raw `catalysts`/`questions`/`research`.
- **`actionRow(a)`** — maps an action-row → render props via `ACTION_KIND_META` (icon/label/color per kind; `research_review` → 🔬 blue), `CONF_META`, and optional decision metadata such as freshness, disconfirmation, and capital-efficiency guidance. Shared by both action lanes.
- **`<Section>`** — the collapsible primitive: `id`, `title`, `icon`, `badge`, `badgeColor`, `openMap/setOpen`, `defaultOpen`. Reused for every panel; nest-able.
- **`CURATED`** (≈ the back of the file) — the **fallback** content for `questions`/`research`/`catalysts` "until the feed emits them." Today `research` and `catalysts` ARE feed-emitted, so the render prefers the feed and falls back to curated only when empty (`R = VM.research when populated else CURATED.research`). Reconcile-as-you-go: as a lane goes live, prefer the feed.

**The panel order** (top→bottom): heartbeat → hero strip → **Today's actions** (🟢) → **From Research** (🔎, new) → Radar (📡) → book → macro → **Research** panel (🔬) → catalysts → questions → synthesis.

### 5.1 · The From-Research section (the 2026-06-02 render change)
A **separate, collapsible `<Section id="research-actions" title="From Research" icon="🔎">`**, placed right after Today's actions. Renders `VM.researchActions` with the same row block as Today's actions; `defaultOpen` when populated; count badge. Icon is **🔎** (not 🔬) to disambiguate the *action lane* from the **🔬 Research** *queue panel* — they'd otherwise collide. The research-badge fix (folded in same build) gave the 🔬 Research panel a count badge + open-when-populated, so a populated queue no longer reads as empty at a glance.

---

## 6 · The read-path & injector (`render_cockpit.py`)

How the **live session** renders without cloning the repo (CI §6 Render Cockpit):
1. Fetch the 🛰️ Cockpit Feed — Latest Notion page → pull the FEED JSON + build stamp.
2. `render_cockpit.py <feed.json> --template <jsx>` — a **string-aware, brace-matched** replace of the `const FEED = {…}` literal in the jsx. Validates **fail-loud**: feed parses + has `holdings`; post-injection braces balanced + `export default function ConvictionCockpit` present + `generated_at` present. Writes the artifact and **prints the freshness/dark-lane caveat**.
3. The renderer `.jsx` is **pinned in project files** so the read-path never clones; fallback = raw-fetch that one file from `conviction_engine/`. **Never clone the repo for a render.**

`--selftest` round-trips the jsx's own baked golden FEED through the injector and validates the output (proves the template is injectable + structurally sound). `test_render_cockpit.py` = 8 seam tests on the same path.

---

## 7 · Build & test mechanics

- **`golden_feed.json`** — the frozen expected output of `assemble_feed(golden_snapshot.json, parabolic=…)`. `test_golden_master.py` asserts byte-exact equality, so **any change to the feed shape moves the golden** → re-freeze with `python build_golden.py` (writes `golden_snapshot.json` + `golden_feed.json`; self-validates; `--check` reports drift without writing). The golden snapshot passes no `research`/`catalysts`, so `research_actions`/`catalysts` freeze as `[]`.
- **Suite:** `python -m pytest -q` in `conviction_engine/` — currently **389 passing** (was 372 before the From-Research build; +17 in `test_research_actions.py`). The CI's "731 tests" figure is wrong; the `/src` suite (119) is separate from this engine suite.
- **Order when adding a feed key:** add the read → register the kind in `validators` → wire into `assemble_feed` → **re-freeze the golden** (keeps the suite green) → add the renderer section → `--selftest` + full suite. (This was the Chunk 2/3 sequence on 2026-06-02.)

---

## 8 · Design decisions & rationale (the "why")

*Settled calls — don't re-litigate without new evidence (Integrity principle). Each is here so future-us understands the shape.*

1. **Engine is pure / deterministic.** No I/O or judgment in L4. → same code runs in the cloud routine and a live preview; the golden can pin exact output; bugs are reproducible. Cost: callers must gather + pass all state. Worth it.
2. **`actions_read` is additive, not generative.** It ranks ⑦+⑧ output plus explicit/conservative synthesis action candidates; it doesn't manufacture actions from vague prose. → on a genuinely quiet day, an empty actions lane is *honest*, not broken. Synthesis promotion is intentionally narrow: structured `actions` rows or ticker-led actionable `hanging` lines only.
3. **`research_actions` is a SEPARATE feed key, not a `category` flag on `actions`** (operator decision, 2026-06-02). → keeps Today's-actions ranking + its "+N more" logic untouched; the two surfaces never blend; "From Research" is visibly its own lane. Alternative (a `category` field on one merged list) was rejected for exactly that blend risk.
4. **Catalyst-precedence dedup against the LIVE action+catalyst lanes** (not a static item-type rule). → a name surfaces **exactly once**, *regardless of whether the catalyst wire is deployed*: with catalysts live, AVGO is the catalyst action and drops from From-Research; without, it shows in From-Research. From-Research gracefully yields as the catalyst lane comes online. A static "dated items never appear in From-Research" rule would have hidden AVGO entirely until step-④ shipped — worse.
5. **From-Research v1 is ticker-specific only; the date clause is dormant.** → process/governance RQ items stay in the Research panel (the action lane stays trade-focused); the date filter is wired but inert until the routine emits structured `days_out` (parsing a date out of free text is too fragile to gate on). Honest v1 over a fragile fuller one. *(Risk: a high-priority dossier not written "TICKER — …" is silently skipped — see backlog.)*
6. **Forward-compat optional feed blocks.** New lanes are validated-if-present. → old/stored feeds stay valid; new code ships without a flag-day. Never make a new feed key required.
7. **Six layers, display split from its feed-routine** (high-level doc). → they're edited separately; validated by 6/1 (an L5 stamp bug + an L6 render bug were independent faults).
8. **Pinned-jsx read-path (no clone to render).** → the 6/1 slowdown was the render reaching into L4's repo to clone the renderer. Pinning the jsx + a no-clone injector (`render_cockpit.py`) fixed it. The injector validates fail-loud so a bad inject aborts instead of rendering garbage.
9. **ABORT-safe publish (L5).** On a critical-source failure the routine does **not** overwrite the feed page — a stale-but-good feed beats a half-written one. The live session then sees the old stamp and re-pulls/flags (Dark-Lane-Honesty).
10. **Re-use the action-row shape for research rows.** → one renderer mapper, one validator path. Cost: a duplicated row-render JSX block in two sections (backlog: extract a shared `ActionCard`).

---

## 9 · Known constraints & dead-spots

- **Catalyst fetch still external to the engine** — `runtime_adapters.catalysts_from_calendar_rows(...)` now normalizes calendar rows into the feed contract and `build_full_feed(..., catalysts=...)` surfaces held-name catalysts as actions. The live routine still must fetch/provide the Catalyst Calendar rows; absence remains a `not_checked`/dark-lane condition, not "no catalysts."
- **Parabolic cache remains separate from the insider feed** — insider/Form 4 now refreshes through `insider_cache_refresh.py` into status-stamped `insider_data.json`; missing UW credentials or failed pulls surface as `not_checked`, while stamped zero-row pulls can read as checked-clear no insider signal.
- **Macro cache stale** (no auto-refresh) — the cockpit routine pulls macro *live*, so the macro line is fine despite the stale `macro_state.json`.
- **UW route-arounds** (also in the high-level doc / CI §10): `get_option_trades` ignores filters → `get_flow_alerts`/`get_interval_flow --date`; screener ticker filter is comma-delimited; `MOVE` is a stock not the bond-vol index → DXY/VIX; dark-pool prints lag ~3 sessions; `get_interval_flow` depth ~12 days.
- **Notion connector:** bare page-IDs can mis-resolve → use data-source handles; can't cleanly filter rows by status → enumerate + per-row fetch; large pages time out on update.

---

## 10 · The canonical lesson (why empty ≠ broken)

The recurring trap: an empty lane looks like a failure. Three independent reasons a lane can be empty, none of which is an engine bug:
1. **Derived-but-no-signal** — `actions`/`fresh_signals` are computed from the book; flat/stale prices → nothing to surface.
2. **External-but-not-passed** — `catalysts` is empty because the routine did not pass calendar rows for that run, not because there are no catalysts.
3. **Curated-fallback / unsourced** — a dark lane means "not checked," never "all clear" (Dark-Lane-Honesty).

Before "fixing" an empty lane: identify which of the three it is (and *which seam/layer owns it*) before opening any box. On 2026-06-02 the "empty actions" report was #1 + #2 together — the engine was correct; the catalyst wire and a render-default were hiding/limiting output.

---

## 11 · Refinement backlog (v1 → v1.1)

- **Structured ticker field** on Off-Hours dossiers -- done 2026-06-05. ⑦c now prefers explicit `ticker`/`symbol` fields before legacy free-text parsing, and the structured date clause activates for plain-title ticker dossiers.
- **Extract a shared `ActionCard`** component -- done 2026-06-05. Today's Actions and From Research now share the canonical action-card renderer while preserving lane-specific footer copy, aging/sizing chips, and research priority labeling.
- **Conflict wording** -- done 2026-06-05. The conviction read now records whether a conflict is cross-source or same-source, so net-read prose can distinguish true independent-source disagreement from intra-source analyst disagreement without changing the Mixed/flat enums.
- **Relabel the From-Research confidence badge** `"priority:"` (it maps from research priority, not signal conviction — avoid conflation).
- **Live Catalyst Calendar fetch/intake** -- connector-shaped intake done 2026-06-05. `catalyst_calendar_intake.py` accepts exported files or live connector/stdin envelopes, including Notion-style `properties` rows, then writes `catalysts.json`; L5 still owns fetching/supplying rows before the pure engine normalizes them with `catalysts_from_calendar_rows(...)`.
- **Signal-Log -> cockpit lane** -- done 2026-06-05. External `signal_log` rows are watch-only feed context, rendered as a separate Signal Log lane; they do not promote into `actions`.
- **Synthesis structured action metadata** -- done 2026-06-05. Daily Synthesis explicit action rows now accept ticker/symbol aliases, recommendation/action text, urgency-derived confidence, timing, capital effect, sizing, goal channels, and missing-evidence fields. Free-form prose remains conservative: only ticker-led actionable hanging items promote.
- **Codex-owned routine orchestration** — replace Claude-only cloud routine prompts with repo-defined runners/automations that Codex can inspect and operate: build caches, gather inputs, build the feed, publish through the gate, and write action memory.
- **Fundstrat intake v1.1** — `fundstrat_email_intake.py` parses forwarded/exported daily emails into `fundstrat_daily_calls.json`, `fundstrat_inbox_entries.json`, `inbox_call_dates.json`, and `source_call_candidates.json`. It can also merge classified full-body candidates into `source_calls.json`, `log_call_dates.json`, and `source_call_cache_summary.json` during the same intake run, while snippet-only discovery leaves those caches untouched. `fundstrat_daily_compact_intake.py` handles compact full-body-derived rows and user-supplied website screenshot/text rows, rejects raw-body-sized quotes, suppresses low-value Fundstrat fluff before it can become a daily-call row, and now keeps source-call candidates/log dates synchronized for accepted compact rows. `fundstrat_daytime_alert.py` plus `pushover_notify.py` adds duplicate-suppressed Pushover review prompts for urgent/action-changing Fundstrat evidence only. `fundstrat_bible_intake.py` handles direct monthly PDF/text/JSON uploads and writes compact `fundstrat_bible.json` state for useful summary sections without storing raw PDF text, stock-price chart clutter, or Core List tables; Core List table ingestion is not a future requirement unless the user makes a new explicit request after the working system is in place. Top-5/Bottom-5 and separate Consider List rows can route into `top_prospects.json`.
- **Fundstrat sector stances** — `fundstrat_sector_stances.py` is the query surface for monthly sector-allocation tactical state embedded in `fundstrat_bible.json`: Newton tactical top-3/bottom-3, named levels such as EWRE weekly close above $38, and the monthly checklist. `fundstrat_bible.py` emits these as `sector_stance` / `named_level` source cards, and `fs_ingest_guard.py` must mark tactical top/bottom plus named-level sections distilled before the Fundstrat News block treats that layer as complete.
- **L2→L3 stamp/shape validator** -- done 2026-06-05. `collection_gate.py` now layers Contract-B shape, parseable run/source stamps, critical-source fail-closed behavior, and staleness/source-failure consistency before L3 assembly; `publish_gate.py` remains the L5→L3 publish gate.

---

## 12 · V3 decision layer (Tasks 1–8, 2026-06-10/11)

The V3 decision layer is **additive** to the V2 engine described above. Every V2 section continues to render unchanged; the V3 TODAY—DECIDE surface is the FIRST section of the cockpit, with V2 sections preserved below.

### 12.1 · Module map

| Module | Role |
|---|---|
| `tunables.py` + `goal_tunables.json` + `conviction_weights.json` | Operator-tunable thresholds and weights; §3.4 honesty rails are NOT tunable (loader hard-fails). |
| `decision_card.py` | 5-field card contract; UNKNOWN-stamped fields are valid, silent omission is not. |
| `insight_register.py` + `congruence.py` | Active insights and the bullets-vs-evidence congruence strip. |
| `conviction_engine.py` | Tier × calibration × freshness → groups (fs, uw, operator_insight, institutional) → read. Tier D never scores (doctrine). |
| `timing_engine.py` | Six T-lanes → OPEN-NOW / STAGE-ONLY / GATED / WAIT. OPEN-NOW requires a named positive trigger. |
| `execution_plan.py` | Per-account leg generation; PCRA ETF-only hard flags and per-leg tax-status flags live here. |
| `directive_recs.py` | Ranks ADD + TRIM cards; threads `extra_cards`, `extra_fs_items`, `inst_states` from orphan wiring (Task 5). |
| `today_decide.py` | TODAY—DECIDE payload + scoped HTML renderer; pace line is **display-only** (tested). |
| `disposition_log.py` | Append-only ACT/PASS/RECHECK/UNDO spine; orphan escalation; 30-day lookback. |
| `pattern_engine.py` | Wave-1 detectors (ENDORSED-DIP, EXPLICIT-ADD, DRUMBEAT, prediction_signals stub) and wave-2 (STALE-LEAPS, OVEREXPOSURE-ROTATION, TIER-B-SIDE-PLAY) + guards (`apply_factor_overlap_caveat`, `apply_parabolic_chase_dampener`). |
| `orphan_wiring.py` | MONITOR-RE-ENTRY (defined-risk required), GRNY-DELTA evidence items, 13F+insider → `inst_state` adapter. |
| `TodayDecide.jsx` + `conviction_cockpit_v6.jsx` | JSX parity port for the artifact cockpit. Same payload JSON in → same fields out (parity test). |
| `post_open_evidence_gate.py` | 9:40 ET routine: `timing_engine.evaluate_gate(gate, live_price)` per gate; propose + stamp. |
| `morning_scan.py` | 8:35 ET routine: runs `pattern_engine.detect_patterns` + the two guards. |

### 12.2 · TODAY—DECIDE payload contract

Both the Python HTML renderer (`today_decide.render_today_decide_html`) and the React component (`TodayDecide.jsx` embedded by `conviction_cockpit_v6.jsx`) consume the same payload:

* `payload.{built, goal_anchor, plan_line, gates[], cards[], backlog[], congruence, honesty}`
* per card: `card.{card_id, ticker, direction, recheck_date, last_disposition, conflicts[], conviction.{read, points, groups, raises}, window.{class, deadline, reasons, flips, named_trigger}, decision_card.{move, conviction, window, evidence, impact}, execution, sizing, impact}`
* BUY/ADD cards carry `sizing.{suggested_usd, source, heat, cap_basis}` from `conviction_sizing_calibrator`; this makes caps math visible before the operator accepts the card notional.
* Wrapper ETF BUY/ADD/TRIM/SELL cards may carry display-only `lookthrough.{contains_line, overlap_line, holdings[], source}` from `lookthrough_disclosure.py`; this surfaces ETF-vs-single-name overlap without changing ranking, sizing, or account routing.
* per-card rail copy: `ACT <card_id>` · `PASS <card_id> — reason: ` · `RECHECK <card_id> resurface <recheck_date>` · second tap copies `UNDO <card_id>`.

The parity is enforced by `src/test_jsx_parity.py`.

### 12.3 · Honesty rails carried into V3

* Pace line is computed once, labeled display-only, never feeds ranking or urgency (tested).
* Tier D is track-only; UW `inconclusive` = 0 ("a successful fetch is not a direction").
* OPEN-NOW requires a named positive trigger; quiet days read WAIT.
* Absent caches render `"not_checked"`; the loaders refuse silent defaults.
* MONITOR no-add-nudge stands: MONITOR-RE-ENTRY is the ONLY action path for `BMNR/LEU/UUUU/MP`, and the card REQUIRES defined-risk fields (`stop_loss`, `risk_band`, `max_loss_usd`) — without them no card emits.

### 12.4 · Routine + registration

* `cloud_routine_commit.DEFAULT_ALLOWED_PATHS` now allows `dispositions.jsonl`, `timing_gates.json`, and `prediction_signals.json` to be committed by scheduled routines.
* `state_ownership_map.json` registers `dispositions` and `prediction_signals` alongside the existing `timing_gates` entry.
* The 9:40 ET Post-Open Evidence Gate routine flows: load gates → `evaluate_all_gates(price_fn=…, writer=file_writer(…))` → on any change, the writer rewrites `timing_gates.json` and the L5 wrapper appends a receipt. The QQQ confirm / re-red flow is now mechanized end-to-end.
* The 8:35 ET Morning Scan routine flows: `run_morning_scan(...)` returns a JSON-serialisable payload containing pattern lanes + guard application + an honesty footer. The L5 wrapper persists the result as a routine receipt and the cockpit folds the cards into TODAY—DECIDE.

---

## 13 - Post-V3 implementation contracts (2026-06-16)

These contracts sit around the pure engine. They matter because future source,
routine, and proof work can otherwise make a lane look more proven than it is.

### 13.1 - Fundstrat transcript vault boundary

The transcript-vault helper is queued/deferred on clean `main`. When that slice
is implemented or cleanly cherry-picked, it is not an engine input and must not
place raw Fundstrat transcript text in the public repo.

* Full transcript/caption text is written only to the private vault directory
  named by `INVESTING_OS_SOURCE_VAULT`.
* Public repo state is limited to metadata, hashes, source dates, short
  synthesis, extract counts, compact-row counts, and private `vault://...`
  references.
* Compact derived rows still enter the cockpit through existing compact
  Fundstrat intake (`fundstrat_web_intake.py` /
  `fundstrat_daily_compact_intake.py`). The vault index alone does not make a
  dashboard call checked.
* Video-only cards, thumbnails, and titles stay discovery-only unless a visible
  transcript, captions, companion article, or supplied compact notes are
  available.

### 13.2 - UW proof remains separate from UW routing

`uw_action_runbook.py` and `uw_routing_recommendations.py` describe what to
check. `uw_endpoint_result_capture.py` and `uw_endpoint_result_proof.py` prove
what was actually captured.

* Captured endpoint rows prove fetch status only.
* `neutral` or otherwise non-directional fetch success maps to
  `inconclusive`, not `supports`.
* Missing or malformed proof fails closed into Source Proof and should keep the
  affected action/reallocation candidate gated.

### 13.3 - Scheduled receipts are runtime proof, not architecture

The active app automation stack is recorded in
`src/cloud_automation_status.json`, but live-run proof is the receipt store:
`src/cloud_routine_receipts.json`.

* Manual receipts do not satisfy scheduled proof.
* A routine should write a `started` receipt and then `success` or `failed` with
  `run_source=scheduled`.
* `cloud_ops_status.py` can report local go-live ready while the unattended
  routine stack remains `not_ready`; these are different states.

### 13.4 - Known low-level debt

The clean-main 2026-06-16 integration-debt sweep still reports:

* 12 info-level module-wiring candidates for standalone/manual modules that
  are not visibly imported by non-test code or routine/prompt command text.
* `research_action_promotion.md` is prompt-only.
* The live Notion System Update Queue was not checked by the repo-only sweep.

Until that debt is resolved, do not describe those paths as fully scheduled
decision architecture. Treat them as manual, prompt-only, or explicitly queued.

---

*End - Conviction Engine Low-Level Architecture v1.0 + V3 decision layer + post-V3 contracts (2026-06-16). Update here first when the engine or feed contract changes.*
