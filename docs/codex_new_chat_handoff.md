# Codex New Chat Handoff

Use this prompt to restart the Investing OS rebuild in a fresh Codex chat.

## Copy/Paste Prompt

You are continuing the Investing OS rebuild in repo `ender-lark/enderverse`.

Workspace path on this machine:
`C:\Users\suraj\Documents\Codex\2026-06-04\confirm-you-can-access-my-github\work\enderverse`

Start by reading these files:

- `AGENTS.md` if present in the workspace root.
- `docs/codex_build_queue.md`
- `src/state_ownership_map.json`
- `src/full_build_runner.py`
- `src/feed_assembler.py`
- `src/conviction_cockpit_v5.jsx`
- `src/feedback_summary.py`

Current priority:

1. Do the dashboard parity review before more UI work.
2. Decide whether generated HTML or JSX is the canonical dashboard path.
3. Map every feed block to the dashboard surface.
4. Create a durable repo artifact for the parity review.
5. Only after parity review, resume the queued slices: reallocation/target drift, PDF holdings ingest, verification command, Codex-owned routines, Fundstrat intake expansion, ETF look-through sleeves.

Important recent state:

- Latest pushed slice: `e038a68 Surface source-call feedback loops`.
- `docs/codex_build_queue.md` is the canonical queue.
- Feedback/source-call surfacing is complete and pushed.
- The feedback block now includes source-call calibration freshness and persistence clusters.
- Missing calibration evidence keeps persistence clusters visible but provisional.
- Fresh calibration allows LOUD repeated source-call clusters to surface.
- Dashboard Feedback panel now shows source scoring, overdue rows, calibration status, source persistence rows, and open action backlog.

Verification already run for the latest slice:

- `python -m pytest src\test_feedback_summary.py src\test_full_build_runner.py src\test_validators.py -q` -> passed.
- `python src\render_cockpit.py --selftest` -> passed.
- `python -m py_compile src\feedback_summary.py src\feed_assembler.py src\full_build_runner.py` -> passed.
- `python -m pytest src --ignore=src\test_reallocate.py -q` -> passed.
- Full `python -m pytest src -q` still stops on the known `src/test_reallocate.py` import failure: `cannot import name 'CLS_CORE' from 'reallocate'`.

Working rules:

- One implementation slice per turn.
- Commit and push after every clean slice.
- Do not do more UI work until dashboard parity review is complete.
- GitHub JSON/docs are canonical for now; Notion sync can come later.
- Treat any short non-conflicting user reply as continue; explicit stop/pause/change-direction overrides.
- Focus on the user's core goal: early retirement through asymmetric opportunities, high conviction, and clear durable actions.

Recommended next command sequence:

```powershell
cd C:\Users\suraj\Documents\Codex\2026-06-04\confirm-you-can-access-my-github\work\enderverse
git fetch origin
git status --short
git log origin/main -5 --oneline
```

Then start the dashboard parity slice.

## Dashboard Parity Slice Definition

Deliverable should be a repo-owned artifact, likely `docs/dashboard_parity_review.md`, plus any small validator/script if useful.

The review should answer:

- Which dashboard file/path is canonical now?
- Which feed blocks are rendered fully, partially, or not at all?
- Which dashboard surfaces are sample/static/stale instead of live feed-backed?
- Which surfaces duplicate each other?
- Which missing surfaces can block action clarity?
- What is the minimal next implementation slice after parity?

Do not redesign the UI in the parity slice unless a tiny edit is required to make the review accurate.
