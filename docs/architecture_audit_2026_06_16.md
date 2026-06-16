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

- Local operator status is `live_with_build_queue`.
- Local readiness, publish readiness, and live-data readiness are true.
- Current feed stamp is `2026-06-15T12:57:07.557970+00:00`.
- Dashboard has 4 actions, 1 research action, and 0 open reviews.
- The only dark source lane is deferred optional `social_watch`.
- System improvement queue is valid with 22 items, 21 done, and 1 queued P3
  item: `fundstrat-video-transcript-intake`.
- Routine manifest is valid with 9 repo routines and 22 daily convention inputs.
- State ownership map is valid.
- Cloud ops is not ready: 20 of 26 expected scheduled routines have scheduled
  success receipts, 15 receipt windows are overdue, and full live-run proof is
  false.

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
- Fundstrat video transcript review now has a private source-vault path through
  `src/fundstrat_transcript_vault.py`. Raw transcripts go only to the private
  vault named by `INVESTING_OS_SOURCE_VAULT`; the public repo stores metadata,
  hashes, short synthesis, and compact derived rows only.
- The public `src/fundstrat_transcript_index.json` exists but currently has no
  registered transcript pack entries.
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

## Open Gaps

- Cloud proof is behind live local readiness. Do not call the unattended
  schedule healthy until `cloud_ops_status.py --format text --require-live-run`
  passes or the overdue receipt gaps are intentionally reclassified.
- Integration debt sweep is `warn` with 4 warnings and 6 findings:
  options-exit cadence is not fully wired, `options_expiry_preflight.py` and
  `stale_leaps_scan.py` have no visible non-test wiring, the
  `research_action_promotion` prompt is not scheduled, the late-evening
  Fundstrat web/transcript sweep is scheduled without a repo prompt/manifest
  doc match, and the live Notion queue was not checked.
- The only queued system-improvement item remains P3
  `fundstrat-video-transcript-intake`; because the transcript-vault helper now
  exists, the next useful slice is likely turning that queue item into a routine
  prompt/manifest/acceptance path or closing it if the current helper fully
  satisfies the need.
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
