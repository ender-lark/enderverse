# Verification

The repo-owned standard verification command is:

```powershell
python src/verify_standard.py
```

Run it from the repository root after each clean implementation slice. GitHub
Actions runs the same command on push and pull request.

## What It Runs

- `python -m pytest src -q`
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
