# AGENTS.md

Repo-local operating protocol for Codex agents working on the Investing OS.

## Source Of Truth

- `docs/monday_go_live_build_plan.md` is the active source of truth for the
  Monday go-live build.
- Repo/GitHub docs are canonical for implementation state. Notion is the
  readable mirror for recovery, rebuilds, upgrades, and troubleshooting.
- Treat older CI, Notion, Claude, or chat handoffs as context only until they
  are reconciled against the current repo state.
- If a task starts from
  `C:\Users\suraj\OneDrive\Old\Documents\Investing OS (2.0)`, first verify
  whether it is only a wrapper. When it is not a git repo, pivot to the
  canonical main checkout before editing. Do not schedule cloud routines
  against a feature checkout. As of the 2026-06-24 automation-watchdog repair,
  the clean main checkout used for local Codex app automation runtime is:
  `C:\Users\suraj\Documents\Codex\2026-06-24\automation-runtime-main`.
  Use `python src\automation_health_watchdog.py --canonical-cwd
  C:\Users\suraj\Documents\Codex\2026-06-24\automation-runtime-main` to audit
  key automation workspace health. The watchdog may auto-fix unhealthy key
  `cwds` only when the replacement checkout is itself clean/current `main`; it
  must never fabricate scheduled receipts or mark dark lanes green. Keep its
  proof check receipt-only; do not route the watchdog through live-status paths
  that can append generated option-shadow rows and dirty the runtime checkout.
  `C:\Users\suraj\Documents\Codex\2026-06-24\automation-main` is preserved as
  drift evidence because generated option-shadow output left it dirty and stale.
  The older
  `C:\Users\suraj\Documents\Codex\2026-06-17\auto-loose-thread-sweep\enderverse`
  checkout is preserved only as drift evidence because local failed-receipt
  commits made it diverge from `origin/main`.

## Primary Objective (Mission - canonical; never changes without operator)

Before any Investing OS system update or build, read
`docs/investing_os_primary_goals.md` and judge the change against it. The short
version:

- WHY: grow the book from about $1.9M to $3M inside the closing 1-3 year AI
  window, where returns cover life and work becomes optional.
- ENEMY: passivity, not recklessness. Right ideas under-sized, good setups
  rotting in queues, acting too slowly, or a signal the system knew about but
  never surfaced are all the same failure.
- JOB: decide and direct, not just display. Turn collected data into specific
  recommended moves, sized to conviction, with timing or trigger spelled out;
  force explicit yes/no/recheck on real decisions.
- SYNTHESIS: independent confirmation builds conviction; correlated echoes do
  not. Conflicts must show both sides and what would settle them.
- POSTURE: pull toward action. The strongest real move should be the loudest
  thing in front; weak signals stay quiet; routine plumbing never out-shouts a
  capital decision.
- HONESTY RAIL: strength loud, weakness quiet, risk always visible. Never
  inflate thin evidence, manufacture conviction, hide risk, or push a trade to
  hit the number.
- NO BUILD-AND-FORGET: detectors must surface in daily flow and outcomes must
  feed back into the system.

Single drift test: does the change make a real, high-conviction, well-timed,
right-sized opportunity more likely to reach the operator, clearly recommended,
shown like a decision, with the call or question one tap from action, and get
acted on before the window closes, without faking urgency or quietly loosening
discipline? If not, it is drift.

"remember our goals" / "consider our goals" / "why are we doing this" are
standing triggers: respond first with this doctrine, then continue the task.
The Notion Boot Page (37bc5031-4bb6-818d-97a9-cd98c32729a4) and its 2026-06-17
child doctrine page mirror the same source-of-truth intent.

## End-of-Session Loose-Thread Sweep (all agents)
At the end of any substantive task/session, before going idle, capture loose threads raised in that session that aren't already in Notion — any idea, research item, system/tooling task, or decision left parked / deferred / "do later".
(1) List candidates from THIS session's work only (Codex/Claude Code: your own commits, PRs, WORKBOARD entries, and punted TODOs since session start).
(2) Read the board — dedupe against the target queue before writing: Research Queue ds cab89576-0933-40b0-ad2e-6f9a6188e804 · System Update Queue ds 968cfff4-369c-40bb-b748-5633b9ff7685.
(3) Write only genuinely-new, still-timely rows, routed: research / decisions-to-make → Research Queue; system/tooling → System Update Queue; analyst calls → Source Call Log (e7def40e-1492-458a-9de8-bd77cd3f8471); firm decisions → Decisions Log (632c97f1-192a-4933-8682-60c730446caf).
(4) Capture-only — never execute / stage / present-as-done; content-based staleness; if nothing qualifies, write nothing. The claude.ai equivalent lives on the Boot Page.

## Build Protocol

- Read and update `docs/WORKBOARD.md` at the start and end of every
  implementation slice. Claim a row before editing so Claude, Codex,
  Claude Code, and cloud routines do not duplicate or collide.
- Work in small, clean, verified slices.
- Commit after each clean verified slice.
- Prefer the existing repo patterns and helpers before adding new abstractions.
- Keep important operating decisions in repo docs; do not rely on chat memory.
- Use `python src/verify_standard.py` as the standard verification command
  unless a narrower focused check is explicitly appropriate before it.
- For larger architecture or system-maintenance tasks, plan first, then keep
  moving in autopilot unless the user explicitly pauses, redirects, or asks for
  a decision. Preserve deferred items in repo docs instead of chat.
- For longer user-facing closeouts, include a short TLDR, who does what next,
  and the recommended next step when that structure is useful.

## Merge Authority

- For verified Codex coding, docs, routine, and dashboard slices, the standing
  closeout preference is full closeout: commit, push, open/update the PR when
  needed, merge when GitHub reports the branch mergeable, sync `main`, and
  update `docs/WORKBOARD.md`.
- Codex may treat the user's requested slice as authorization for that standard
  closeout when the branch is not draft, GitHub reports it mergeable, and the
  required checks are green or the operator explicitly accepts the documented
  check risk.
- Codex must not bypass merge conflicts, failing checks, branch protection, or
  stale review state. If GitHub blocks the merge, report the blocker and leave
  the PR unmerged.
- After any Codex-performed merge, sync `main`, update `docs/WORKBOARD.md` from
  `PR#<n>` to `MERGED PR#<n>` when applicable, and verify the post-merge state
  before starting the next slice.

## Multi-Agent Coordination

- Route work by environment: Codex owns live data, local environment,
  scheduled routines, and Notion execution; Claude Code owns isolated,
  self-contained logic on a branch/PR when no live data is needed, measures its
  own baseline, and stays off other agents' files; Claude.ai owns architecture,
  specs, cross-agent verification, and decision analysis, using live tools for
  verification but shipping repo code only through prompts to Codex or Claude
  Code.
- Every task or prompt declares file ownership: the files it owns and the
  rows/files it must not touch, explicitly naming other agents' claimed rows.
- Shared files such as `src/trigger_registry.json` require isolated additions,
  rebasing, and preservation of other branches' blocks.
- Before speccing new work, inventory the repo first: grep existing modules and
  read the in-flight pack. The engine often already exists; the remaining gap is
  usually a thin data or wiring layer.

## Verification Discipline

- Trust evidence over reports: verify against `main` and live artifacts, never
  against workboard status or an agent's own summary.
- Establish ground truth before judging a claim: use a fresh clone or clean
  checkout, run the full suite, record the actual count, and read the workboard.
- Verify the boundary outcome, not the internal step. API success does not prove
  a push reached the phone; credentials fixed in one shell do not prove a
  scheduled job can see them.
- Distinguish cosmetic flags from real failures empirically by reading live
  timestamps and data, such as a connection's actual sync status.
- Run the cheap diagnostic before the expensive fix; a fresh-process test can
  separate a harmless stale-process issue from a broken environment.
- When manual auditing recurs, turn the audit into a tool and schedule it. Prove
  features against the real failures they target, and document honest gaps
  instead of faking green.

## Life/Work OS Scheduled Routines

- Life OS and Work OS routines live in this repo as support-monitored cloud
  routines on the same rail as Investing OS: `src/cloud_routine_runner.py`,
  `src/cloud_routine_receipts.py`, and `src/cloud_routine_commit.py`.
- The registered active support routine set is:
  `life-os-daily-briefing`, `work-os-daily-briefing`,
  `life-os-weekly-review`, `work-os-weekly-review`,
  `life-work-os-heartbeat-watch`, and `life-work-os-safe-hygiene`.
- Routine prompts live under `src/codex_routines/`. Repo status is mirrored in
  `src/cloud_automation_status.json`; app-active status means the Codex
  automation exists, while scheduled-proof status is proven only by
  `run_source=scheduled` receipts landing on main.
- Life/Work Notion reads must be deterministic REST reads using
  `Notion-Version: 2025-09-03` and `POST /v1/data_sources/{id}/query` with
  server-side filters and full pagination. Do not use agentic Notion search or
  MCP search to produce backlog counts.
- Secrets come from environment only: `NOTION_TOKEN`, `PUSHOVER_TOKEN`, and
  `PUSHOVER_USER`. Do not read the deprecated Notion Routine Secrets page.
- Every Notion write must be fetched back before success is claimed. Missing,
  blocked, stale, schema-mismatched, or credential-missing lanes remain
  `not_checked` / dark.
- The safe-hygiene routine can only perform mechanical Tasks/Inbox/After-Hours
  Queue writes. It must never delete, must cap mutations per run, must log every
  mutation, and must never auto-mutate Work case-file content, Strategic Brief,
  Game Plan, Insights, or Evidence Ledger.

## Dashboard Protocol

- When the user asks for the dash, dashboard, cockpit, or conviction cockpit,
  open the local HTML dashboard first:
  `http://127.0.0.1:8765/dashboard_preview.html`.
- Treat `http://127.0.0.1:8765/cockpit_jsx_preview.html` as an internal
  JSX parity/validation surface, not the default operator dashboard.
- Major cockpit sections should be minimizable when they can clutter the first
  screen.
- Show portfolio impact, action validity, capital efficiency, freshness,
  rationale, and blockers ahead of raw data.

## Data Honesty

- Missing, stale, or failed lanes remain dark, stale, or `not_checked`; they are
  never treated as checked clear.
- Macro and news inputs should be distilled into portfolio and action
  implications before surfacing. Raw signals are useful only when they change
  decision timing, sizing, risk, or research priority.
- Treat Fundstrat as the primary baseline, but question it with evidence and
  invalidation checks rather than blindly following it or dismissing
  counterintuitive calls because they conflict with normal market logic.
- Treat Fundstrat as separate lanes: Tom Lee for macro, Mark Newton for
  technical/timing with variable confidence, and the crypto analyst lane for
  crypto-specific analysis. Weight each lane by its domain, freshness, and
  stated confidence instead of treating Fundstrat as one undifferentiated
  source.
- Meridian is stale thesis archive context after March 2026, not live tactical
  evidence.
- SnapTrade is the preferred read-only Account Positions source after staged
  validation. Manual PDF/text extraction remains a fallback.
- If SnapTrade fails and no fallback validates, Account Positions should become
  stale or `not_checked`, not silently fresh.

## Decision Safety

- The system surfaces review prompts and decision support only. It does not
  execute trades.
- Promoted actions need rationale, evidence freshness, decay speed, assumption
  refresh status, and invalidation triggers.
- A good opportunity is not enough; compare it against better current uses of
  capital while avoiding over-precise timing that misses major up days.
- Keep `ANET` and `GOOGL` open unless the user explicitly asks to resolve them.

## Out Of Scope For Main Build

- Do not work on Reddit/social in the main build except through
  `docs/reddit_social_new_chat_handoff.md`.
- Do not accelerate cloud routine proof unless the user explicitly asks. Let
  normal scheduled receipts accumulate in the background.

## V3 Decision Layer (TODAY—DECIDE)

- The V3 decision layer is **additive** to V2. Never remove a V2 section, lane,
  validator, or feed key when extending V3. New cards enter the cockpit ONLY
  through the action-implication contract — no parallel panels, no gate
  bypass.
- §3.4 honesty rails are **not** tunable. `tunables.py` hard-fails if a config
  file tries to define one. Tier D never scores; UW `inconclusive` = 0;
  OPEN-NOW requires a named positive trigger. Pace lives in the goal-anchor
  block only and is display-only.
- Every emitted card must pass `decision_card.validate_decision_card`.
  Missing fields are stamped UNKNOWN — never omitted.
- The MONITOR sleeve (`BMNR / LEU / UUUU / MP`) has exactly one Action path:
  MONITOR-RE-ENTRY cards from `orphan_wiring`. Those cards REQUIRE
  defined-risk fields (`stop_loss`, `risk_band`, `max_loss_usd`); without
  them no card emits. Do not add an alternate buy path.
- ACT / PASS / RECHECK rails ship as clipboard copies, second-tap UNDO is
  binding. `disposition_log.append_disposition` accepts the UNDO verb; PASS
  still requires a reason, UNDO does not.
- The 9:40 ET Post-Open Evidence Gate is mechanized by
  `post_open_evidence_gate.evaluate_all_gates`. The 8:35 ET Morning Scan is
  mechanized by `morning_scan.run_morning_scan`. Both modules are pure; the
  L5 wrapper supplies the price-lookup and writer callbacks.
- The cloud commit allowlist for routines now covers `dispositions.jsonl`,
  `timing_gates.json`, and `prediction_signals.json`. Routines may write
  these; ad-hoc edits should still go through the operator.
- The JSX parity contract between the Python HTML renderer and the React
  cockpit (`TodayDecide.jsx` / `conviction_cockpit_v6.jsx`) is enforced by
  `src/test_jsx_parity.py`. If a payload field changes shape, update BOTH
  renderers before committing.
- Candidate-bearing JSON artifacts must not be "built but invisible." The
  integration-debt sweep's `build_without_wire` section must flag any committed
  candidate artifact with no decision-path reader, no real
  `state_ownership_map.json` feed path, and no explicit
  `src/non_surfacing_allowlist.json` reason.
- Daily pullback/reallocation packets are current only when `packet.as_of`
  equals the build date. Stale packets may remain visible as research context,
  but they must render as STALE/not_checked with stale price wording and must
  not move conviction, ranking, sizing, gates, or action posture. Missing
  packets produce no fabricated watch rows and must write an honesty note.
