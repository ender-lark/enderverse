# Architecture And Operating Docs Audit - 2026-06-16

## Scope

This audit refreshed the durable repo docs that a future Codex, Claude Code, or
GitHub session should read before changing Investing OS architecture or
operations.

Primary docs checked:

- `AGENTS.md`
- `docs/investing_os_system_architecture.md`
- `src/ARCHITECTURE.md`
- `docs/codex_new_chat_handoff.md`
- `docs/codex_build_queue.md`
- `docs/completion_audit.md`
- `docs/integration_debt_report.md`
- `src/codex_routine_manifest.json`
- `src/cloud_automation_status.json`
- `src/state_ownership_map.json`

## Current Repo Truth

Audit commands run on 2026-06-16 from the canonical checkout:

```powershell
python src/live_status.py --format text
python src/cloud_ops_status.py --format text
python src/completion_audit.py --format text
python src/system_improvement_queue.py
python src/state_ownership_map.py
python src/codex_routine_manifest.py
python src/integration_debt_sweep.py --out docs/integration_debt_report.md --json-out src/integration_debt_report.json --format text
```

Observed state:

- Local operator status is `live_clear`.
- Local readiness, publish readiness, and live-data readiness are true.
- Current feed stamp is `2026-06-16T05:19:05.446825+00:00`.
- Dashboard has 4 actions, 1 research action, and 0 open reviews.
- The only dark source lane is deferred optional `social_watch`.
- System improvement queue is valid with 22 items and no active/queued items
  after transcript closeout.
- Routine manifest is valid with 9 repo routines and 22 daily convention inputs.
- State ownership map is valid.
- Cloud ops is not ready: core scheduled proof is complete at 14/14, support
  scheduled proof is 7/12, and full live-run proof is false because receipt
  freshness/support proof still lags.

## Architecture Status

The core architecture remains:

1. Source access gathers connector, browser, source-vault, or supplied evidence.
2. Intake modules normalize evidence into compact repo convention files.
3. The deterministic feed engine reads repo convention files only.
4. Action and synthesis layers promote only evidence-backed review prompts.
5. Dashboard renderers publish local HTML and JSX validation surfaces.
6. Cloud receipts prove whether scheduled automations actually ran.

Important current additions:

- SnapTrade is the preferred read-only broker-position source when strict
  staged validation passes. Manual PDF/text extraction is fallback only.
- Fundstrat web intake can use the authenticated Chrome session, but only
  compact full-content-derived rows land in repo.
- Fundstrat video transcript review now uses the private source-vault flow on
  clean `main`: raw transcripts stay out of the public repo, and public state is
  limited to metadata, hashes, short synthesis, compact derived rows, and
  private-vault references.
- UW endpoint proof is separate from the UW runbook. Successful neutral endpoint
  fetches remain `inconclusive`, not supportive evidence.
- Notion write success is proven only after live page readback. Repo mirrors and
  local JSON files are not proof of live Notion row status.

## Collaboration And GitHub Learnings

The durable collaboration rules now live in `AGENTS.md` and `docs/WORKBOARD.md`:

- The OneDrive Investing OS folder can be a wrapper. Check the git root first
  and pivot to the canonical checkout before editing.
- Work in small verified slices and update `docs/WORKBOARD.md` at the start and
  end of each implementation slice.
- Default closeout preference is commit, push, PR/merge when safe, sync `main`,
  and update the workboard. Do not bypass GitHub conflicts, failing checks,
  stale reviews, or branch protection.
- Codex owns live local environment, scheduled routines, Notion execution, and
  repo closeout. Claude Code should own isolated logic branches/PRs with clear
  file boundaries. Claude.ai is best used for architecture, specs, critique,
  and prompts that Codex or Claude Code can implement.
- Missing, stale, failed, inconclusive, or optional lanes stay visible as dark,
  stale, or `not_checked`; they are never summarized as checked clear.

## Transcript Closeout Update

After the initial docs audit, clean `main` added the Fundstrat transcript
implementation:

- `fundstrat_transcript_vault.py` writes raw transcript/caption text only to
  the private source vault and keeps public repo state to metadata, hashes,
  short synthesis, compact derived rows, and `vault://...` references.
- `fundstrat_transcript_synthesis.py` emits compact Notion-ready review notes
  without raw transcript text.
- Two 2026-06-15 Fundstrat transcript review notes were written to Notion
  Synthesis Log and fetched back successfully.
- `src/codex_routines/fundstrat_late_evening_web_transcript_sweep.md` gives the
  scheduled transcript sweep repo prompt coverage.
- `fundstrat-video-transcript-intake` is now done in
  `src/system_improvement_queue.json`.

## Open Gaps

- Cloud proof is behind live local readiness. Do not call the unattended
  schedule healthy until `cloud_ops_status.py --format text --require-live-run`
  passes or the overdue receipt gaps are intentionally reclassified.
- Integration debt sweep is `warn` with 1 warning and 14 findings on clean
  `main`: 13 info-level module-wiring candidates,
  `research_action_promotion` is not scheduled, and the live Notion queue was
  not checked.
- The system-improvement queue has no active/queued items after transcript
  closeout.
- Social Watch remains watch-only and deferred optional. It must stay dark until
  a compliant Reddit/social API or supplied normalized cache is available.

## Next Audit Command

Use this command set before changing architecture or claiming the system is
current:

```powershell
python src/live_status.py --format text
python src/cloud_ops_status.py --format text
python src/completion_audit.py --format text
python src/integration_debt_sweep.py --no-write --format text
```
