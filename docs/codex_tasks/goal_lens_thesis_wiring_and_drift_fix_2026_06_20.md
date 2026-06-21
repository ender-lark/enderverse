# Codex Task Pack — Wire the 9 AI-model singles into Thesis-of-Record + fix the drift detector

**Author:** Claude (decision/architecture lane) · **Date:** 2026-06-20 · **Owner to execute:** Codex (live data + modules + Notion).
**Provenance:** the 2026-06-19 Goal-Lens retroactive review (`docs/goal_lens_review_discipline.md`;
Notion 🔭 Goal-Lens Retroactive Review `384c5031-4bb6-8173-974a-fc155687e96b`). That review found the
operator's own AI working model **~$517k under-filled** while the surface stayed silent — root cause: **9 of
the 11 model single-names are `tracked:false` with no thesis-of-record, so the drift detector labels them
"missing vs target" instead of "under-target (held X%)."** This pack makes that gap structurally visible so it
can never go silent again.

## Rails (read first — non-negotiable)
- **No trades, ever.** This pack wires thesis/visibility plumbing only. It executes nothing and recommends
  nothing to buy/sell. (The operator holds the 9 sized moves from the review separately.)
- **Do NOT edit `src/account_positions.json` / `src/positions.json` / `src/position_reconciliation.json`** —
  those are owned by `CLOUD-BROKER-INTAKE` and regenerated from SnapTrade. The `tracked` flag must become true
  via theses.json membership at the next intake (Task 1), not by hand-editing the book.
- **Do NOT modify any live automation prompt/schedule.** This is code + data + docs only.
- **Repo is source of truth.** Claim on `docs/WORKBOARD.md` (Task 0) before editing. Work in small verified
  slices; `python src/verify_standard.py` is the gate. Merge only on **operator-explicit** authorization with
  green checks (AGENTS.md Merge Authority) — do not self-merge this pack without the operator's word.
- **Honesty rail / Rail D unchanged:** the drift line is **context, never a trigger**. This pack changes how a
  held-but-untracked name is *labeled and surfaced*, not the no-auto-trim/no-auto-add doctrine.

---

## Task 0 — Claim + ground truth
1. Add to `docs/WORKBOARD.md`:
   `| GOAL-LENS-THESIS-WIRING-2026-06-20 | Codex | Wire 9 AI-model singles into theses.json + per-ticker dossiers; fix target-drift detector to classify held-but-untracked names by real weight (not MISSING) | `src/theses.json`; `docs/research_dossiers/{GOOGL,AVGO,TSM,MSFT,AMZN,VRT}.md`; `src/position_drift_check.py`; `src/session_orchestrator.py`; `src/test_position_drift_check.py` (or focused new test); coverage tests | CLAIMED | <stamp> |`
   Must-not-touch: broker-core position files (CLOUD-BROKER-INTAKE), any automation prompt.
2. Fresh clean checkout; run `python src/verify_standard.py`; record the **actual** baseline pass/skip count
   (Boot Page cites ~1747/6 as of 2026-06-18, but establish the real number on this branch first — verify
   against `main`, not a report).
3. Grep-inventory before writing: confirm `theses.json` schema, confirm how `tracked` is derived at broker
   intake (Task 1 depends on this), and read `position_drift_check.py` + the `session_orchestrator.py` twin.

## Task 1 — Add the 9 model single-names to `src/theses.json`
These are in `reallocate_config.default_working_model()` with real targets but are absent from `theses.json`,
so they read as untracked. Append entries matching the existing schema (`ticker, id, tier, lane, stance,
source, factor_tags`). Proposed values (confirm `lane`/`source` against the existing taxonomy — keep
`stance:"ACTIVE"`, these are NOT the MONITOR sleeve):

```json
{ "ticker": "GOOGL", "id": "thesis_googl", "tier": "T1", "lane": "Speed", "stance": "ACTIVE", "source": "operator", "factor_tags": ["ai_complex","hyperscaler","long_duration_growth"] }
{ "ticker": "AVGO",  "id": "thesis_avgo",  "tier": "T2", "lane": "Speed", "stance": "ACTIVE", "source": "operator", "factor_tags": ["ai_complex","semiconductors","networking"] }
{ "ticker": "MSFT",  "id": "thesis_msft",  "tier": "T2", "lane": "Speed", "stance": "ACTIVE", "source": "operator", "factor_tags": ["ai_complex","hyperscaler","software"] }
{ "ticker": "AMZN",  "id": "thesis_amzn",  "tier": "T2", "lane": "Speed", "stance": "ACTIVE", "source": "operator", "factor_tags": ["ai_complex","hyperscaler"] }
{ "ticker": "TSM",   "id": "thesis_tsm",   "tier": "T2", "lane": "Speed", "stance": "ACTIVE", "source": "operator", "factor_tags": ["ai_complex","semiconductors","foundry","global_exporter"] }
{ "ticker": "ANET",  "id": "thesis_anet",  "tier": "T3", "lane": "Speed", "stance": "ACTIVE", "source": "operator", "factor_tags": ["ai_complex","networking"] }
{ "ticker": "ASML",  "id": "thesis_asml",  "tier": "T3", "lane": "Speed", "stance": "ACTIVE", "source": "operator", "factor_tags": ["ai_complex","semiconductors","equipment","global_exporter"] }
{ "ticker": "FN",    "id": "thesis_fn",    "tier": "T3", "lane": "Speed", "stance": "ACTIVE", "source": "operator", "factor_tags": ["ai_complex","optics"] }
{ "ticker": "VRT",   "id": "thesis_vrt",   "tier": "T3", "lane": "Speed", "stance": "ACTIVE", "source": "operator", "factor_tags": ["ai_complex","power_thermal"] }
```
Then **confirm the `tracked` flag derivation**: a name present in `theses.json` should be marked `tracked:true`
on the next broker intake. If the derivation is membership-based, no further action — verify on the next intake
the 9 flip to `tracked:true`. If `tracked` is set some other way, wire it so theses.json membership ⇒ tracked.
**Do not hand-edit the book.**

## Task 2 — Create the 6 missing per-ticker dossiers (Rail A)
`docs/research_dossiers/{FN,ANET}.md` already exist (keep/reconcile if stale). Create the **6 missing**:
`GOOGL, AVGO, TSM, MSFT, AMZN, VRT`, using the template in `docs/research_dossiers/README.md`. Mark each
**"PENDING OPERATOR CONFIRMATION"** in the superseded-history origin line (same convention as `FN.md`); do not
fabricate beyond the grounded evidence below (all from the 2026-06-19 adversarially-verified review — re-pull
live price before any sell per Rail A). Seeds:

- **GOOGL — CURRENT VERDICT: ADD (staged) · conviction high.** Why own: full-stack AI (TPUs + Gemini +
  hyperscale), held 3.76% vs 8% target. Catalysts: tranche-2 review trigger (2026-06-19, expires 06-23);
  Q2 earnings 2026-07-22. **Disconfirmer/risk (loud): on 2026-06-02 Alphabet priced an $84.75B equity raise
  (upsized from $80B) — $40B ATM program + $10B Berkshire placement + mandatory convertible preferred — a real
  dilution/ATM supply overhang.** Street: PTs $420–515 (HSBC/Piper/Truist/Wells/Needham/Mizuho/Citizens Buy;
  UBS Neutral $410). Range: ~$368, −10% below its $408.61 high, IVR ~30 (not extended).
- **AVGO — CURRENT VERDICT: ADD (stage) · conviction high.** Custom ASIC + AI networking; held 2.12% vs 6%.
  Catalysts: 6/3 record print PASSED (rev +48%, AI chips +143% YoY); JPM reiterated OW $580 "aggressive buy"
  (2026-06-17); Apollo/Blackstone $35B AI-infra partnership (06-17); next earnings 2026-09-03. Range: ~$411,
  −17% below its $495 high, IVR ~41 — chase gate does NOT fire. Disconfirmer: AI-capex multiple compression on
  a risk-off tape.
- **TSM — CURRENT VERDICT: ACCUMULATE-ON-PULLBACK (chase-gate hold) · conviction high.** Foundry near-monopoly;
  held 0.23% vs 4% (biggest single gap). **Range: at its 52-wk high ~$462, IVR ~100 → do NOT buy at market;**
  stage limit ladder (~$430/$410) or sell cash-secured puts. Catalysts: earnings ~2026-07-16; Q1'26 rev
  +40.6% YoY. Disconfirmer: Taiwan/geopolitics; AI-capex digestion.
- **MSFT — CURRENT VERDICT: ADD (stage — knife) · conviction high.** Hyperscaler laggard; held 1.55% vs 5%.
  Range: ~$379, −32% below its $555 high (deepest mega-cap discount) BUT an active −22%/6mo downtrend making
  lower lows → stage, don't slug; consider cash-secured puts (IVR ~56). Catalysts: TD Cowen $540 (2026-06-04);
  Q3 FY26 beat (rev +18%, NI +23%); earnings 2026-07-29. Disconfirmer: continued lower-lows / Azure decel.
- **AMZN — CURRENT VERDICT: ADD · conviction high.** AWS re-accel (Q1 AWS +28% YoY to $37.6B, ~30% cloud
  share, OpenAI multi-year deal, ~$200B AI/Kuiper capex); held 1.14% vs 4%. Range: ~$244, −12% below its $278
  high, IVR ~28 (pullback, not extension). Catalysts: Q2 earnings 2026-07-30; June Prime Day. Disconfirmer:
  capex margin drag without AWS acceleration.
- **VRT — CURRENT VERDICT: ADD (disciplined) · conviction high.** Datacenter power/thermal, $15B+ backlog,
  least chip-correlated; held 0.00% vs 2% — **the named buy-surfacing miss (Rail E); ran +11% to ~$333 again.**
  Catalysts: Bernstein INITIATED Outperform $416 (2026-06-10); ThermoKey acquisition completed 2026-06-12;
  earnings 2026-07-29. Range: ~$333, −12% below its $380 high, IVR ~60 → disciplined entry (starter + limit
  $300–310 + defined-risk spread), NOT a market chase. Disconfirmer: AI-capex/power-demand slowdown.

Optionally regenerate via the existing case-file/dossier buy-side backfill tool (the one that produced
`FN.md`) and reconcile against these seeds — do not silently diverge.

## Task 3 — Fix the target-drift detector (the honesty bug)
**Symptom:** `daily_synthesis` reads "… (0 under, 2 over, **9 missing**)" and lists held names
(GOOGL/AVGO/MSFT/AMZN) as "missing vs target" — but they are HELD, just under-target and `tracked:false`.
**Root cause:** `position_drift_check.load_actuals_from_positions_cache` (and the
`session_orchestrator.py:~586` twin) are fed a tracked-only positions view, so untracked held names never
appear in `actuals` and fall to the `missing` bucket (`position_drift_check.py:399–414`).

**Behavioral contract to implement:**
1. The drift detector's actuals must aggregate the **full book** (all `account_positions` rows summed by
   ticker across accounts, options handled as today), **independent of the `tracked` flag**. Confirm the
   caller passes the full book (e.g. `account_positions.json` → `account_positions`), not a tracked subset;
   if `load_actuals_from_positions_cache` only reads a `"positions"` key, make the caller pass the full book
   or teach the loader the `account_positions` shape.
2. A model-target name that is **held at all** is classified by its **real weight** (UNDERSIZED / OVERSIZED /
   AT-BAND) — **never `MISSING`**. After this, GOOGL reads `GOOGL undersized 3.8% vs 8.0%`, not
   `GOOGL missing vs 8.0% target`.
3. Reserve `MISSING` strictly for names with **$0 across the entire book**, and phrase it honestly
   (e.g. `VRT 0% held vs 2.0% target`) so a real zero never reads like a data hole.
4. Apply the identical fix to the `session_orchestrator.py` twin; prefer extracting one shared helper (DRY) so
   the cockpit-feed and preflight lines can't drift apart again.
5. **Doctrine unchanged:** keep the gap as **context, never a trigger** (`reallocate.py` "gaps as context"),
   honesty rail intact, no auto-trim/auto-add.

**Test (add):** feed a book where GOOGL is held ~3.76% (and `tracked:false`) with an 8% target →
assert `direction == "UNDERSIZED"` and `actual_pct ≈ 3.76`, and assert GOOGL is **not** in the `missing`
bucket. Add a true-zero case (VRT at $0) → asserts `MISSING` with the honest "0% held" wording.

## Task 4 — Verify + close
1. `python src/verify_standard.py` green; report the pass/skip delta vs the Task 0 baseline (new tests only).
2. Re-run the dossier coverage linter (`case_file_coverage.py` / `decision_dossier_coverage.py`) — the 6 new
   dossiers should flip from missing→covered; FN/ANET already covered.
3. Re-generate `daily_synthesis` (or its drift twin) and confirm the line now reads the 9 as
   `undersized X% vs target`, with `MISSING` only for true-zero names — paste the before/after line in the PR.
4. Update `docs/WORKBOARD.md` CLAIMED→PR#<n>→MERGED on the operator's go. Do not self-merge without it.

## Out of scope (separate follow-ups, do not bundle)
- Re-running the Fed-day reallocation packet post-FOMC (re-gate AMBER→GREEN/RED) — separate task.
- Buy-Surfacing-Gate (Rail E) enforcement so a vetted buy can't expire in watch — separate task.
- The operator's 9 sized trades — operator action, not this pack.
