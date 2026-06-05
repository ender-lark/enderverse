# Verification

The repo-owned standard verification command is:

```powershell
python src/verify_standard.py
```

Run it from the repository root after each clean implementation slice. GitHub
Actions runs the same command on push and pull request.

## What It Runs

- `python -m pytest src --ignore=src/test_reallocate.py -q`
- `python src/test_reallocate_rebuild.py`
- `python src/render_cockpit.py --selftest`
- `python src/broker_pdf_extractor.py --self-test`

For dashboard JSX edits, also run:

```powershell
python src/verify_standard.py --include-js
```

That adds an `esbuild` bundle check for `src/conviction_cockpit_v5.jsx`. On
Windows, the verifier uses `npx.cmd` when available to avoid PowerShell script
execution-policy failures.

## Known Expected Failure

Do not use `python -m pytest src -q` as the standard command yet. It still
collects the retired `src/test_reallocate.py` Chunk 1 tests, which import
symbols such as `CLS_CORE` from the old reallocation API. The current
target-weight rotation planner is covered by `src/test_reallocate_rebuild.py`,
which is included in the standard verifier.
