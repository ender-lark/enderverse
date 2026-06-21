# Goal-Lens & Anti-Passivity — Low-Level Architecture & Features

**Reference doc — v1.0, 2026-06-20.** Canonical repo home; Notion mirror under the Command Center. Scope: the
**anti-passivity decision pipeline** — how the Investing OS turns the operator's goal + the live book into
sized, surfaced decisions, and the goal-lens discipline that governs it. This is the *subsystem* low-level
map; the whole-OS architecture lives in `docs/investing_os_system_architecture.md` and `src/ARCHITECTURE.md`.

> **What problem this subsystem exists to solve.** The enemy is **passivity** — and passivity gets built into
> the system as architecture: a target the operator set that nothing surfaces, a held name the detector calls
> "missing," a vetted buy that dies in a watch pile. This subsystem is the machinery that makes a real,
> right-sized opportunity *reach the operator as a decision* before the window closes — under the Honesty Rail.

---

## 1. Layer map (one screen)

```
DOCTRINE          Primary Goals  ──►  Goal-Lens Review Discipline  ──►  Sell-Gate & Sizing Doctrine
(why / the lens)  judge ALL analysis against the goal, never generic caution

GOVERNANCE        Boot Page (standing rule) · AGENTS.md · Command Center · CI Update Queue (fold)
(make it bind)    loaded first every session by Claude / Codex / Claude Code

PIPELINE          targets ─► held book ─► thesis-of-record ─► drift/under-size detect ─► conviction
(the machine)         │                                                                      │
                      └──► Sell Gate · Buy-Surfacing Gate · Rail-D sizing ◄──────────────────┘
                                              │
                                              ▼
                              decision surface (ACT / PASS / RECHECK)  ─►  operator  ─►  write-back

RAILS (cross-cutting)   Honesty Rail (non-tunable) · survival rails · MONITOR-sleeve discipline
```

## 2. Doctrine & governance layer

| Artifact | Repo | Notion | Role |
| --- | --- | --- | --- |
| Primary Goals doctrine | `docs/investing_os_primary_goals.md` | `382c5031-4bb6-8187-96d7-fa36b0445511` | The goal everything is judged against. Compact mirror also in `AGENTS.md` + the Boot Page block. |
| **Goal-Lens Review Discipline** | `docs/goal_lens_review_discipline.md` | `384c5031-4bb6-815e-8f5e-fa416fe89133` | Extends "judge system changes against the goal" to **ALL analysis**. Counters the inverse-of-cautious-AI failure. |
| Reusable goal-lens prompt | — | `384c5031-4bb6-8134-a14b-e7deb34b580a` | The runner that applies the discipline across the OS. |
| Sell-Gate & Sizing Doctrine | `docs/sell_gate_and_sizing_doctrine.md` | `382c5031-4bb6-8178-8db4-f4556a46d5b6` (v1.1) | Worked application: Sell Gate (B), funding hierarchy (C), Rail-D sizing, Rail-E Buy-Surfacing. |
| Custom Instructions (v12 draft) | — | `371c5031-4bb6-81a8-b28d-de209b7159b2` | In-session operating manual. Goal-lens fold **queued** (CI Update Queue `840a74bb-…`). |

**How it binds (forward-looking):** the Boot Page (`37bc5031-…`) carries a standing-rule block loaded first
every session; `AGENTS.md` carries the same for Codex/Claude Code; the Command Center links it. Today it is a
**standing doctrine every session loads**, not yet a hard code gate — the CI fold + the Rail-E code
enforcement (§3.8) are the steps that make it machine-enforced.

## 3. The anti-passivity pipeline (stage by stage)

### 3.1 Targets — the working model
- **`src/reallocate_config.py`** → `default_working_model()` returns the operator's **2026-06-02 AI working
  model**: per-name `target_pct` (NVDA 12 · GOOGL 8 · AVGO 6 · MSFT 5 · AMZN 4 · TSM 4 · MU 3 · ANET 3 ·
  ASML 2 · FN 2 · VRT 2 · SMH 5 · GRNY 3), tier, factor, sub-sector. Also the `Dials` (NVDA target, SMH
  approach, AI-sleeve flat ~60%, ETF keep-levels, **`chase_block_1m_runup_pct=35`**, catalyst gates) and
  `ETF_LOOKTHROUGH` (nets a wrapper's holding of a name out of single-name sizing). Concentration rail = **OFF**
  by default (the "no random cap" decision).
- Contract: targets are **directional context, never an order** (consumed by §3.4 and `reallocate.py`).

### 3.2 Held book
- **`src/account_positions.json`** `{snapshot_date, sleeve_value, account_positions:[…]}` — canonical book,
  written by the **8:20 ET broker intake** (SnapTrade) — `CLOUD-BROKER-INTAKE` owns it; never hand-edited.
  Each row has `tracked: true|false`. **`tracked` is the gate on what the surface "sees."**
- `src/positions.json` / `position_reconciliation.json` — same owner.

### 3.3 Thesis-of-Record (Sell-Gate Rail A)
- **`src/theses.json`** — per-position `{ticker, id, tier, lane, stance, source, factor_tags}`. `stance` =
  `ACTIVE` (gets the loud under-sizing pull) or `MONITOR` (volatile thematic; add only on a re-entry
  condition). **A name absent here is effectively invisible to the surface** (and tends to be `tracked:false`).
- **`docs/research_dossiers/<TICKER>.md`** — the repo half of Rail A (template + rules in the dir README): one
  dated CURRENT VERDICT on top, why-own, bull thesis, dated catalysts (incl. policy/federal), disconfirmers,
  range/sizing, funding-tier note, archive-never-delete history.
- **`src/decision_dossiers.py` / `.json`** (+ `decision_dossier_sync.py`, `_refresh.py`,
  `decision_dossier_coverage.py`) — freshness-safe per-name decision dossier surfaced on cards; coverage debt
  flagged when an action/material name lacks one.
- **`src/case_file.py` / `case_file_coverage.py`** — recall-at-mention assembler (verdict + FS calls + news +
  decisions, verdict-staleness loud).
- Notion mirror: 📚 Research Queue `collection://cab89576-…` + 🧠 Live Theses `0f083d6f-…`.

### 3.4 Drift / under-sizing detection  ← **the bug this week's pack fixes**
- **`src/position_drift_check.py`**: `target_baselines_from_reallocate_model()` (targets from §3.1) ×
  `load_actuals_from_positions_cache()` (held book) → `cross_reference()` →
  `target_weight_drift_summary()` emits `UNDERSIZED / OVERSIZED / MISSING` rows + the line
  *"N sizing gap(s) vs AI working model (X under, Y over, Z missing)"*.
- **`src/session_orchestrator.py` (~line 586)** — the preflight TARGET-DRIFT twin (same string).
- **`src/portfolio_views.py` (`working_model_gap_pct`, lines ~206/299)** — the data twin that *does* compute
  the real held-gap from the full book.
- **THE BUG:** the detector was fed a **tracked-only** positions view, so a held-but-`tracked:false` model
  name (GOOGL/AVGO/MSFT/AMZN/TSM/ANET/ASML/FN/VRT) never lands in `actuals` and falls to the **`MISSING`**
  bucket (`position_drift_check.py:399–414`) — it reads *"GOOGL missing vs 8% target"* when GOOGL is held at
  3.76%. That is how **~$517k of under-fill stayed invisible** (found 2026-06-19).
- **FIXED CONTRACT (pack `goal_lens_thesis_wiring_and_drift_fix_2026_06_20.md`):** read the **full book**;
  classify any held name by its **real weight** (never `MISSING`); reserve `MISSING` for true-$0 names with
  honest "0% held vs target" wording; DRY the orchestrator twin; **gap stays context, never a trigger**.
- Downstream surfacing of the gap as a card: `analyst_judgment.py` (`conviction_gap` action, "target is
  directional, not an order"), `decision_support.py`, `goal_impact.py`, `lane_status.py`,
  `reallocation_brief.py`.

### 3.5 Conviction engine
- **`src/conviction_engine.py` + `conviction_weights.json` + `tunables.py`**: **F1** — a real bull/bear split
  reads **CONFLICTED** (loud, RE-CHECK, never ACT, never up-sized) instead of averaging to a calm NEUTRAL.
  Two-layer shadow conviction (name/sector/overall) in the tap drawer. Independent-confirmation logic
  (correlated echoes ≠ breadth — the FN/VRT echo trap).
- **F2 sizing:** **`src/sizing_tunables.json` + `src/sell_gate.py`** — conviction drives the live suggested
  size; lift fires only on honest conviction (HIGH/MODERATE + ≥2 converging independent groups + BUY + not
  conflicted). `sell_gate.py` **flags, does not block** (`sell_gate_blocks=false`). Funding-aware
  (`treat_funding_pool_as_available`); dollar rounding tunable.

### 3.6 Sizing — Rail D (judgment prompt, not a trigger)
- Surfaces sizing context (under vs conviction · fragmented · oversized · parabolic) but **never auto-trims /
  auto-adds**. **Asymmetric:** LOUD pull to size UP an under-owned converging setup; GENTLE + Sell-Gate-gated
  prompt to consider trimming an over-owned one. No hard thresholds. Right-size never overrides a live thesis.

### 3.7 Sell Gate + funding hierarchy — Rail B / C
- **`src/reallocate.py` + `reallocate_config.py`**: planner ranks by thesis impact / funding source / gates —
  **"gaps as CONTEXT, never the trigger."** Funding order: idle cash → redundant wrappers → dead theses →
  winners at highs → tax-loss → (last, explicit thesis-break only) a live thesis, **never at its low**.
  `funding_protected_wrappers = {GRNJ}`. Sell Gate: a near-52wk-low live thesis never clears for mechanics; a
  "sell-into-weakness" skeptic flag is a **near-veto**.

### 3.8 Buy-Surfacing Gate — Rail E  ← **doctrine-only today; enforcement is the next forward-looking step**
- Doctrine (Sell-Gate doc §4.6): a vetted, sized BUY must be **wired** into the structured source layer the
  same session and reach the operator as **ACT/PASS/RECHECK**, never a rail-free WATCH row; window-aware
  loudness; funding-can't-fund → ask, don't bury. Skeptic "wait/don't chase" is **one input, not a veto**.
  Calibration rail: **NOT "buy every pullback."**
- **STATE: not code-enforced yet.** This is exactly how VRT (the #3 buy) and ANET died in watch. Enforcing it
  in code (ingest screen BUY verdicts → forced disposition; stop the parabolic-`SKIP` from dampening a
  thesis-backed discount; carry first-flagged price/date) is the open follow-up. Spec:
  `docs/codex_tasks/vrt_miss_rootcause_2026_06_18.md` §5b.

### 3.9 Triggers
- **`src/trigger_registry.json` + `trigger_check.py`**: dated / level-touch / parabolic-acceleration triggers
  (e.g. GOOGL tranche-2 `date_event`, ASTS/RKLB re-entry zones, MU parabolic accel auto-armed from the
  parabolic screener). Fires push (Pushover) + dashboard strip. Held-decision review triggers for parked
  packets.

### 3.10 Decision surface
- **`src/today_decide.py` + `TodayDecide.jsx` + `conviction_cockpit_v6.jsx`** (parity enforced by
  `test_jsx_parity.py`): ACT/PASS/RECHECK cards with caps-sourced sizing block, UNDO spine. Built by
  **`full_build_runner.py`** → `latest_cockpit_feed.json`; `daily_synthesis.json` is the orientation brief.
  `data_health.py` + `alert_policy.py` carry staleness/honesty flags.

### 3.11 Options surfacing (defined-risk expression)
- **`src/options_surface.py` / `options_expression.py` / `options_uw_adapter.py`**: surfaces sized,
  defined-risk options expressions of convictions; the **down-day IV-tax brake** routes a dip with inflated
  premium to a spread/wait instead of auto-buying a rich-IV call (anti-revenge). Phase-1 live; surfacing
  tile + conversational recall remain.

### 3.12 Honesty rails (cross-cutting, non-tunable)
- `tunables.py` **hard-fails** if a config tries to define an honesty rail. Tier D never scores; UW
  `inconclusive` = 0; OPEN-NOW requires a named positive trigger; pace is display-only (`AGENTS.md` §V3).

### 3.13 Write-back (close the loop)
- Decisions → Decisions Log `632c97f1-…`; theses → Live Theses `0f083d6f-…`; trades/sizing → Active Trade
  Rationales `a76caa96-…`; source calls → Source Call Log `e7def40e-…`; loose ends → Research Queue;
  system/tooling → System Update Queue `968cfff4-…`.

## 4. Data flow (end to end)

```
cloud routines (Morning Scan · Off-Hours Worker · Daily Synthesis · Deep Synthesis · 8:20 broker intake)
      │  write caches
      ▼
account_positions.json ─┐         reallocate_config working model ─┐
theses.json / dossiers ─┼─► drift detect (§3.4) ─► under/over ─────┤
signal_log / research ──┘         conviction engine (§3.5) ────────┴─► Rail-D sizing + Sell/Buy gates
                                                                              │
                                              triggers (§3.9) ───────────────►│
                                                                              ▼
                                              today_decide (§3.10) ── ACT/PASS/RECHECK ──► OPERATOR
                                                                                              │ decides
                                                                              write-back ◄────┘
```

## 5. File & ID map (quick index)
- Doctrine: `docs/investing_os_primary_goals.md` · `docs/goal_lens_review_discipline.md` ·
  `docs/sell_gate_and_sizing_doctrine.md`
- Targets/sizing: `src/reallocate_config.py` · `src/reallocate.py` · `src/sizing_tunables.json` ·
  `src/sell_gate.py`
- Thesis: `src/theses.json` · `docs/research_dossiers/` · `src/decision_dossiers.py` · `src/case_file.py`
- Detection: `src/position_drift_check.py` · `src/session_orchestrator.py` · `src/portfolio_views.py`
- Conviction/surface: `src/conviction_engine.py` · `src/today_decide.py` · `src/TodayDecide.jsx` ·
  `src/full_build_runner.py`
- Triggers/options: `src/trigger_registry.json` · `src/trigger_check.py` · `src/options_surface.py`
- Governance: Boot Page `37bc5031-…` · CI Update Queue `840a74bb-…` · `AGENTS.md` · `docs/WORKBOARD.md`

## 6. Forward-looking enforcement roadmap
1. **Thesis wiring + drift fix** (IN PROGRESS — pack `goal_lens_thesis_wiring_and_drift_fix_2026_06_20.md`,
   WORKBOARD `GOAL-LENS-THESIS-WIRING-2026-06-20`): the 9 model singles get a thesis-of-record + become
   `tracked`; the detector reads the full book → the gap can't read "missing" again.
2. **Buy-Surfacing Gate enforcement** (DEFERRED): code-enforce Rail E so a vetted sized buy can't die in
   watch (the VRT/ANET class). This is the strongest forward-looking guarantee.
3. **CI fold** (QUEUED, CI Update Queue): bake the goal-lens lens into the formal Custom Instructions.
4. **Re-gate the Fed packet post-FOMC** (DEFERRED): the AMBER_PRE_FOMC packet needs a post-event re-run.

## 7. Learnings (2026-06-19 → 06-20)
- **Passivity is built as architecture, not just habit.** ~$517k of under-fill was invisible because (a) 9
  model names had no thesis-of-record / `tracked:false`, and (b) the drift detector read a tracked-only view
  and labeled held-but-under names "missing." The goal-lens lens caught what a generic "looks fine" pass
  wouldn't.
- **The Honesty Rail cuts BOTH ways.** The adversarial verify both surfaced a real risk I had softened
  (GOOGL's $84.75B equity raise / ATM overhang) **and** caught me **under-sizing** a clean setup (AVGO) — the
  inverse-of-cautious-AI failure is as real as over-caution.
- **Chase-gate ≠ passivity.** "Don't buy TSM/ASML at the 52-wk-high into IVR 100" must still **ship a
  structure** (limit ladder / cash-secured puts), or the gate decays into the very inaction it guards against.
- **Mirrors rot.** The Notion Sell-Gate page had silently fallen a version behind the repo (v1 vs v1.1, missing
  Rail E). Repo is canonical; mirrors must be checked, not trusted.
- **Build-and-forget is the same disease as operator inaction.** VRT died in a watch pile; persisting this
  review to Notion (not leaving it in chat) is that lesson applied to ourselves.

## 8. Known gaps / open items
- Rail E (Buy-Surfacing Gate) is doctrine-only — not code-enforced (§3.8).
- `daily_synthesis` / drift twin still emit "missing" for held-but-under names until the pack lands (§3.4).
- 6 of the model singles have no dossier yet (pack Task 2); `tracked` derivation from theses membership to be
  confirmed at intake.
- Fed-day reallocation packet is unexecuted with a stale (`AMBER_PRE_FOMC`) gate.

*v1.0 — 2026-06-20. Canonical repo doc; keep the Notion mirror in sync. Update on any structural change to the
pipeline.*
