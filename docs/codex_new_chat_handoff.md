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

1. Read `docs/codex_build_queue.md` and promote only evidence-backed slices.
2. Prioritize system/routine/dashboard buildout over stock-specific research.
3. Keep dashboard parity classification current before any feed/dashboard UI work.
4. Use `python src/verify_standard.py` as the standard verification command.
5. Commit and push after each clean verified slice.

Important recent state:

- Latest completed slice before this handoff refresh: Fundstrat monthly state ownership map.
- `docs/codex_build_queue.md` is the canonical queue.
- The user explicitly said to focus on building the working system first and not
  spend time on stock research such as AVGO.
- Dashboard parity review is complete; JSX injection is canonical, generated HTML is a summary/export path.
- Fundstrat daily email intake and direct monthly PDF/text/JSON upload intake are supported.
- Monthly Core List tables are intentionally not stored and should not be
  revisited tonight; only explicit future user direction should reopen that.
  Top-5/Bottom-5 and separate Consider List rows are the monthly
  prospect-signal path.
- AVGO remains unassessed until an actual thesis is written, but its timing
  catalyst has passed; it is now a low-priority queued Research Queue item, not
  an immediate From Research action.
- The stale retired `src/test_reallocate.py` workaround has been removed; plain full-suite pytest passes.

Current verification baseline:

- `python -m pytest src -q` -> `840 passed, 6 skipped`.
- `python src\test_reallocate_rebuild.py` -> passed.
- `python src\verify_standard.py` should run the same full pytest tree plus the standalone self-tests.

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

Then read `docs/codex_build_queue.md` and start only the next promoted slice.

Do not start with stock-specific research. If no concrete implementation slice
is queued, run a fresh completion audit and promote the next system/routine/UI
gap from current repo evidence.

## Dashboard Parity Status

The dashboard parity review and guardrail are complete:

- `src/conviction_cockpit_v5.jsx` via JSX injection is canonical.
- `docs/index.html` is a generated summary/export path.
- `docs/dashboard_feed_block_classification.json` classifies feed blocks.
- `src/test_dashboard_parity_guardrail.py` protects feed-block classification.

Before any future feed/dashboard meaning or UI work, refresh the parity review
and classification first.
