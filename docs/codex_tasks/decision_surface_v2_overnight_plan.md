# Codex Overnight Task — Decision Surface V2 remaining delta (guardrail + honesty gate + safe closeout)

**Authoritative plan. Re-read this whole file after any context compression before continuing.**
Workboard row to claim: `DECISION-SURFACE-V2-DELTA-2026-06-17`.

> **Read this first — the situation changed.** The big "action-first" Today/Decide rewrite the
> operator asked about HAS ALREADY MERGED to `origin/main` (commits `f097e05`, `f52f6c8`,
> `c6a059c`). It is verified good: the fed-day packet is wired into the feed, the 9 deep-discount +
> 5 pullback names render in a visible/legible (expanded) `watch_queue`, funding legs are demoted
> into a "Funding / paired sells" lane (never ACT), and rail-safety was adversarially confirmed
> (a `BMNR rank_score=9999` mutation still cannot produce a card or an ACT). **Do NOT rebuild any of
> that.** This task only adds the genuine remainder. If your `git log` shows you are NOT on top of
> `c6a059c` (or later) on `origin/main`, STOP and re-baseline — an earlier checkout is 4 commits
> behind and would make you rebuild merged work.

---

## 0. GROUND TRUTH (verified on origin/main `c6a059c`, 2026-06-17 — re-orient here after compression)

- **Baseline to protect:** `python -m pytest src -q` → **1628 passed / 0 failed / 6 skipped**;
  `python src/verify_standard.py` → "Verification passed."; `python src/build_golden.py --check`
  → drift-free. Do not finish below this.
- **Top operator-focus cards now:** GRNY/TRIM/65.0, GOOGL/BUY/63.3, IVES/SELL/58.2. The $400 MAGS
  funding leg is demoted (priority capped at 9, "Funding / paired sells" lane) — the old
  "$400-leg-is-#1" failure is already fixed.
- **`watch_queue`** carries 14 fed-packet candidates (9 deep-discount + 5 pullbacks), rendered as
  always-visible `td-queue-card` divs with each row's disconfirmation; **rail-free by design**
  (no ACT/PASS/RECHECK). MONITOR-sleeve names {BMNR,LEU,UUUU,MP} and source-disagreement names
  {KTOS,ELF,SOFI,UUUU,HOOD} appear ONLY here, never as cards.
- **Key call site:** `full_build_runner.py` builds `feed["today_decide"]` (~line 994) by calling
  `today_decide.build_today_decide_payload(feed, weights, goal, accounts, today)` — passes NO
  `extra_cards`/`inst_states`/`orphan_honesty`.
- **Fed packet consumption (today_decide.py):** `_fed_day_packet` (~687), `_fed_day_rows_by_ticker`
  (~692), `_attach_fed_day_context` (~709), `_build_fed_day_watch_queue` (~762). It reads packet
  sections `act_if_green` / `higher_quality_pullbacks` / `deep_discount_research` / `do_not_touch_yet`.
  **It never reads `as_of`/`generated_at` → there is NO staleness gate** (the bug Slice 2 fixes).
- **`integration_debt_sweep.py`** has only a Python-module orphan check (`module_wiring_section` ~169,
  `_local_import_graph` ~110); there is NO data-artifact "build-without-wire" check (the gap Slice 1 fixes).

> **Line numbers above are from the verified read of `origin/main` c6a059c. Confirm them against the
> code on your branch before editing; the action-first rewrite is large and may shift by a few lines.**

---

## SCOPE (what this task does — and explicitly does NOT do)

**DOES (core, required):**
1. **Slice 1 — Phase-C `build_without_wire` guardrail** in `integration_debt_sweep.py` (+ a
   `non_surfacing_allowlist.json`): fail any committed candidate-bearing `src/*.json` with no reader
   on the decision path and no declared non-surfacing reason. Prevents the whole class of "build an
   artifact, never wire it" miss from recurring (the fed packet was wired by hand; the next one won't be).
2. **Slice 2 — fed-packet staleness honesty gate**: the Fed-day-dated packet (`as_of` 2026-06-17) is
   currently consumed verbatim on any future build. Add a freshness check so stale/absent packets are
   honestly marked `not_checked`/STALE (research-context-only), never shown as if current. (Data-honesty rail.)
3. **Slice 3 — docs**: correct the now-superseded coverage audit, update architecture/AGENTS, and
   explicitly NAME the deferrals below.
4. **Slice 4 — verify + safe closeout.**

**DOES NOT (deliberately deferred — name these in the docs + morning report, do not attempt tonight):**
- **orphan_wiring live thread.** `compute_orphan_wiring` is still uncalled in the build, but its
  caches (13F/insider/re-entry-zone) do not exist on disk and one source hardcodes a Linux path
  (`/mnt/project/fs_holdings.json`). Wiring it tonight yields ONLY honest-absence (institutional stays
  "not wired") — zero operator-visible change for real risk. Defer until those caches exist.
- **watch_queue disposition rail.** Giving watch rows a RESEARCH/PASS forcing affordance would add a
  new disposition verb (touches disposition_log + both renderers + parity). The names are already
  visible/legible/triageable; this is an enhancement, not a fix. Defer.
- **Finding 4 unification.** `feed.prospects` (Top Prospects), `feed.actions` (Today's Actions),
  `feed.research_actions` (From Research) are still context-only panels with no disposition rail. A
  unified-candidate-model is V2-scoring work. Defer.
- **`watchlist_discount_screen` (107-name screen)** in the packet is still unconsumed; and the fed-day
  packet is event-specific (it goes stale daily). Generalizing it into a daily-regenerated
  discount/pullback packet is a routine concern. Defer.

---

## STOP CONDITIONS (hard — halt, write the blocker to the STATUS file + workboard, push branch UNMERGED, do not merge)

1. `python src/verify_standard.py` does not exit 0, OR `python src/build_golden.py --check` reports drift.
2. **Golden is NOT a leak detector for the today_decide render surface** (golden_feed has no
   today_decide payload). Do not rely on it to catch a rail leak. Slice 1/2 do not touch the render
   rails, but if you ever do, the guard is the parity suite + a fresh non-lockstep invariant — never golden.
3. You are about to touch any **render rail / posture / card surface**, or `tunables.py`,
   `conviction_*`, `timing_engine.py`, `reallocate*.py`, `decision_card.py`, `orphan_wiring.py`
   internals, or any golden/snapshot JSON. This task does not need them. (Slice 2 touches only the
   fed-packet *consumption* helpers in today_decide.py, additively.)
4. Any change would let a MONITOR-sleeve {BMNR,LEU,UUUU,MP} or source-disagreement
   {KTOS,ELF,SOFI,UUUU,HOOD} name gain an ACT/BUY affordance. (Derive these from the packet's own
   `source_flags`/`research_status`, never hardcode the lists — UUUU is BOTH MONITOR and source-disagreement.)
5. Branch base is not `origin/main` (`c6a059c` or later), or a rebase conflict appears in
   `today_decide.py` / `TodayDecide.jsx` / `directive_recs.py`.
6. Closeout merge cannot be proven all-green (see §Slice 4) — leave pushed-but-unmerged.

---

## FILE OWNERSHIP

**Own (edit):** `src/integration_debt_sweep.py`, `src/test_integration_debt_sweep.py`,
`src/today_decide.py` (ONLY the fed-packet consumption helpers + their honesty output — Slice 2),
`src/TodayDecide.jsx` (ONLY the watch-queue caption/stale badge if needed — Slice 2),
`src/test_today_decide.py`, and NEW: `src/non_surfacing_allowlist.json`,
`src/test_decision_surface_v2_delta.py`, `docs/codex_tasks/decision_surface_v2_STATUS.md`.
Docs: `docs/decision_surface_coverage_audit_2026_06_17.md`,
`docs/investing_os_system_architecture.md`, `AGENTS.md`.

**Do NOT touch:** the render rails / card posture / `_review_posture` / `_render_card` / card sections;
`directive_recs.py`; `full_build_runner.py` (no orphan-wiring thread this task); `tunables.py`,
`conviction_*`, `timing_engine.py`, `reallocate*.py`, `decision_card.py`, `orphan_wiring.py`;
any `golden_*` / `*_snapshot*` JSON; the locked `main` worktree.

---

## WORK PROTOCOL (robust to multi-hour autonomous runs)

- Keep `docs/codex_tasks/decision_surface_v2_STATUS.md` as a running checklist with intra-slice
  sub-steps, each marked DONE `<hash>` / IN-PROGRESS / BLOCKED. Update at start and end of every slice.
- **On resume after compression:** run `git log --oneline` and `git status` FIRST — the last DSV2
  commit is ground truth; the working tree is mid-slice scratch. Re-read this plan and the STATUS
  sub-steps; do not assume a sub-step landed unless its artifact is present.
- One slice = one clean, verified, committed change. Run `python src/verify_standard.py` before every
  commit; commit only on green. Stage explicit paths only — **never `git add -A`** (cloud routines and
  other worktrees write here). Run `git diff --cached --stat` before each commit to confirm only
  intended files are staged.
- Any in-task run of `integration_debt_sweep.py` MUST use `--no-write` (it writes tracked
  `docs/integration_debt_report.md` + `src/integration_debt_report.json` by default; do not churn them
  as a side effect; the Sunday Weekly Pilot owns that regeneration).
- Commit message: `[codex] DSV2-delta sliceN: <what>` + standard co-author trailer.

---

## SLICE 0 — Setup

1. `git fetch origin`. Create the branch off **origin/main** via a fresh worktree (never the locked
   main worktree, never the stale local HEAD): `git worktree add <path> -b codex/decision-surface-v2-delta origin/main`.
   Pin the base SHA in STATUS.
2. Copy this plan into the new branch as the recovery anchor: it lives in the operator's working tree
   at `docs/codex_tasks/decision_surface_v2_overnight_plan.md` — copy it into the branch and commit, OR
   re-create it from the operator's prompt. Also create `docs/codex_tasks/decision_surface_v2_STATUS.md`.
3. Record the baseline (pytest summary, verify_standard, build_golden --check) in STATUS. Confirm
   1628/0/6 + "Verification passed." + drift-free. If different, that is your floor.
4. Claim workboard row `DECISION-SURFACE-V2-DELTA-2026-06-17` (IN-PROGRESS), single targeted edit to
   that one row. Re-read the live workboard first; do not collide with any IN-PROGRESS row.
5. Commit: `[codex] DSV2-delta slice0: branch + plan anchor + baseline + workboard claim`.

---

## SLICE 1 — Phase-C `build_without_wire` guardrail

Add a check to `src/integration_debt_sweep.py` flagging committed candidate-bearing DATA artifacts
with no reader on the decision path and no declared non-surfacing reason. Reuse the file's existing
helpers (`_finding`, `_read_json`, `_rel`, `_source_files`, the `build_report` `sections` dict).

**Detection (must actually catch real candidate JSON — verify against live files):** a `src/*.json`
"carries candidates" if ANY of: (a) ≥2 top-level keys are ticker-shaped (`^[A-Z]{1,6}(\.[A-Z]{1,3})?$`);
(b) ANY top-level value is a list of dicts each having `ticker`/`symbol`; (c) ANY top-level value is a
dict containing a `rows`/`results`/`items`/`signals` list of dicts having `ticker`/`symbol` (this is
what catches the fed packet's `deep_discount_research`/`higher_quality_pullbacks` and a
`watchlist_discount_screen.rows`); (d) the top level is a list of such dicts; (e) top-level
`tickers`/`candidates` present. **Skip** `integration_debt_report.json`, `golden_*`, `*_snapshot*`,
`*.example.*`, `*.local.*`.
> Before coding, run a quick probe: load each `src/*.json` and print which ones your predicate marks
> as candidate-bearing. It MUST include `fed_day_reallocation_packet.json`, `top_prospects.json`,
> `disconfirmation_registry.json`. If it misses the fed packet, the predicate is wrong — fix it before proceeding.

**Wired test:** an artifact is WIRED if its basename appears in the concatenated source of the
decision-path modules (`today_decide`, `directive_recs`, `feed_assembler`, `full_build_runner`,
`cockpit_html_gen`), OR `state_ownership_map.json` declares a real `feed_path` for it, OR it has a
`non_surfacing_reason` in `src/non_surfacing_allowlist.json` (basename match). Otherwise emit a
`WARN` finding `id=build_without_wire_<stem>`, `area="build_without_wire"`, with a `next_step` naming
the three remedies. Section shape mirrors `module_wiring_section`:
`{status, line, candidate_count, rows[:20], findings}`. Plug into `build_report`'s `sections` dict
between `module_wiring` and `routine_schedule` (single edit — it auto-flows everywhere).

**`src/non_surfacing_allowlist.json`:** `{schema_version, generated_at, policy, classifications:
["proof_cache","audit_artifact","intermediate_cache","example_fixture","sample_data","deprecated_retired"],
artifacts:[{artifact, classification, non_surfacing_reason, owner, added}]}`. Run the new check
(`--no-write`) and seed the allowlist with the legitimately-non-surfacing artifacts it flags (e.g.
`uw_endpoint_results.json`→proof_cache, `orphan_triage.json`→audit_artifact, any sample/fixture JSON).
**Do NOT allowlist** `disconfirmation_registry.json` or `13f_best_ideas`-style outputs — they are real
remaining orphans and should stay flagged (record them in STATUS as known debt for a future task).

**Closed-loop assertions (the proof this guardrail works):**
- **Positive:** `fed_day_reallocation_packet.json` is candidate-bearing AND detected as WIRED (because
  `today_decide.py` reads its basename) → NOT flagged. This proves wired-detection works on the real
  artifact the operator cared about.
- **Negative:** a fixture candidate JSON with no reader → flagged WARN; same file once added to the
  allowlist (or once a decision-path module references its basename) → clears. (Follow the
  `_minimal_repo` pattern in `test_integration_debt_sweep.py`.)

**Verify:** `verify_standard` green; `python src/integration_debt_sweep.py --no-write --format text`
runs and lists `build_without_wire` with the fed packet NOT in it. Paste the section output into STATUS.
Commit: `[codex] DSV2-delta slice1: build-without-wire integration-debt guardrail + allowlist`.

---

## SLICE 2 — Fed-packet staleness honesty gate

The fed packet is Fed-day-dated and consumed verbatim with no freshness check (verified: the
consumption helpers never read `as_of`/`generated_at`). Make staleness honest WITHOUT hiding the names.

In `today_decide.py` fed-packet consumption (additively; do not touch card rails/posture):
- Compute packet freshness once: read `packet.get("as_of")`; `fresh` if `as_of == today_iso`
  (same build day). Treat missing packet or missing/unparseable `as_of` as `absent`/`stale`.
- **Fresh:** behave exactly as today (attach `fed_day_context`, build `watch_queue`).
- **Stale (packet present, `as_of` < today):** still render the `watch_queue` rows (preserve
  visibility — the mission), but flag the section `stale`/`not_checked`: the caption and each row show
  the `as_of` date prominently and label prices "as of {as_of} — STALE, research context only", and
  add an honesty entry `honesty["fed_day_packet"] = "stale (as_of {as_of}) — research context only,
  prices not current"`. Also reflect it in the `trust_panel` if that path is clean to extend.
- **Absent:** `watch_queue` empty + a single honest "fed-day packet not_checked — no packet on disk"
  note in `honesty` and the caption. Never fabricate rows.
- Carry `packet_as_of` and a `freshness` status onto the `watch_queue` payload so both renderers can
  show it. Mirror the caption/stale badge in `TodayDecide.jsx` (caption + per-row stale label only — no
  rail changes). Keep JSX parity green (the watch rows remain rail-free; this is display text only).

**Tests (`src/test_decision_surface_v2_delta.py`):** fresh packet → watch_queue populated, no stale
note; stale packet (`as_of` = yesterday) → rows still present but flagged stale + honesty note; absent
packet → empty watch_queue + honest not_checked note, zero fabricated rows.

**Verify:** `verify_standard` green; `build_golden.py --check` drift-free; render the dashboard and
confirm the watch-queue caption shows the `as_of` freshness, and that a simulated stale `as_of` flips
it to the STALE/not_checked label. Commit: `[codex] DSV2-delta slice2: fed-packet staleness honesty gate`.

---

## SLICE 3 — Docs (correct the record + name the deferrals)

- **`docs/decision_surface_coverage_audit_2026_06_17.md`:** add a dated "SUPERSEDED IN PART (origin/main
  c6a059c)" note at the top: the fed packet is now wired into the feed and surfaced as a visible
  `watch_queue`; funding legs are demoted; rail-safety verified. Update the coverage matrix rows that
  changed. Keep the miss-type taxonomy (it is the durable lesson).
- **`docs/investing_os_system_architecture.md` §5:** document the action-first Today/Decide (Material /
  Other rechecks / Funding-paired-sells lanes + impact-ranked backlog + watch_queue from the fed packet
  + do-not-touch block), the new `build_without_wire` integration-debt check, and the fed-packet
  staleness gate.
- **`AGENTS.md` §V3:** add the `build_without_wire` guardrail and the fed-packet freshness rail.
- **Name the deferrals** (in the audit doc's "remaining work" section AND the morning report):
  orphan_wiring live thread (blocked on absent caches + Linux-path source); watch_queue disposition
  rail; Finding 4 unification (prospects/actions/research_actions); `watchlist_discount_screen` 107-name
  consumption; generalize the Fed-day packet into a daily-regenerated discount/pullback packet so the
  watch_queue stays fresh. Capture each as a Research/System-Update-Queue loose-thread row per AGENTS.md.

Commit: `[codex] DSV2-delta slice3: docs — guardrail, staleness gate, named deferrals`.

---

## SLICE 4 — Verify + safe closeout (per AGENTS.md Merge Authority; ALL-GREEN-OR-ABORT)

**Verification:** `verify_standard` green; `build_golden.py --check` drift-free; `pytest src -q` ≥
1628 passed / 0 failed / 6 skipped plus the new DSV2 tests; `integration_debt_sweep.py --no-write
--format text` shows `build_without_wire` present with the fed packet WIRED (not flagged). Paste all
into STATUS.

**Closeout (autonomous-safe — the operator authorized merging tonight, but ONLY all-green):**
1. **Rebase** the branch onto current `origin/main` (`git fetch` first). On ANY conflict in
   `today_decide.py`/`TodayDecide.jsx`/`directive_recs.py`/`integration_debt_sweep.py` → STOP, push,
   leave unmerged. Require `merge-base(branch, origin/main) == origin/main HEAD` before proceeding.
2. **Push** the branch. PR via the gh-absent path (token from `git credential fill` used ONLY in the
   `Authorization` header — never in argv, logs, STATUS, or any committed file; set
   `GIT_TERMINAL_PROMPT=0`).
3. **Merge gate (all must hold, else STOP-and-leave-unmerged — no "accept risk" escape, no human is
   present):** POST the PR; POLL `GET /pulls/<n>` until `mergeable` is non-null, then re-poll once with
   a short delay; require `mergeable == true` and `mergeable_state` NOT in {dirty,behind,blocked,unknown};
   independently `GET /commits/<headsha>/check-runs` and require every run `completed` + `success`;
   `PUT /pulls/<n>/merge` with the expected head SHA (so GitHub rejects if the branch advanced).
   Any ambiguity after bounded retry → push, write blocker, leave unmerged.
4. **Post-merge:** sync via a fresh detached worktree off `origin/main` (NEVER the locked main
   worktree, NEVER `git add -A`). Run the dashboard refresh there for verification but keep
   routine-owned caches OUT of any commit (`latest_cockpit_feed.json`, `decision_dossiers.json`,
   `heartbeat.json`, `daily_synthesis.json`, `uw_*`, `source_call_candidates.json` are cloud-routine
   owned — do not stage them). Update the workboard row to `MERGED PR#<n>`.
5. **Loose-thread sweep** per AGENTS.md (capture-only, dedupe-first): file the named deferrals.
6. **Morning report** at the top of STATUS: **TLDR** (guardrail + honesty gate landed; the action-first
   surface was already live and verified); **what the operator sees** (top cards GRNY/GOOGL/IVES; the
   9+7 names in the visible watch_queue now carrying honest freshness); **verification evidence** (test
   counts, verify pass, golden drift-free, linter shows fed packet wired); **named deferrals**; **any
   blocker** and the exact failing gate. If anything blocked: branch pushed-but-unmerged, report says
   precisely what and why. Pushed-clean-unmerged-with-report is the safe terminal state.

---

## DEFINITION OF DONE

- `build_without_wire` guardrail exists, proves the fed packet WIRED and a fixture orphan flagged;
  allowlist documents legitimately-non-surfacing artifacts; remaining real orphans
  (`disconfirmation_registry.json`, 13F output) recorded as known debt.
- Fed-packet consumption is freshness-gated: stale → visible-but-flagged-STALE/not_checked; absent →
  honest not_checked; fresh → unchanged. No fabricated rows.
- Docs corrected; all deferrals named + captured as loose-thread rows.
- `verify_standard` green, golden drift-free, pytest ≥ baseline + new tests. Merged to `main` all-green,
  or pushed-but-unmerged with a precise blocker report. No render rail / scoring / doctrine file touched.
