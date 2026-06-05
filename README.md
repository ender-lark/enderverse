# Investing OS

Operational repo for the Investing OS cockpit build. The current local path is:

```powershell
C:\Users\suraj\Documents\Codex\2026-06-04\confirm-you-can-access-my-github\work\enderverse
```

## Daily Live Command

Run this from the repo root:

```powershell
python src\live_dashboard_refresh.py
```

That one command:

- refreshes heartbeat status;
- builds and publish-gates the cockpit feed;
- writes repo-evidence Daily Synthesis from the feed;
- republishes the final feed;
- renders the canonical JSX artifact;
- renders the local dashboard preview and docs summary;
- prints a final summary with action count, data-lane count, dark lanes, source-call status, and `go_live_ready`.

Local preview:

```text
http://127.0.0.1:8765/dashboard_preview.html
```

To check or start the local preview server:

```powershell
python src\dashboard_preview_server.py --check
python src\dashboard_preview_server.py
```

If `go_live_ready` is false, treat the final summary as the status report and fix the named blocker before using the dashboard for live decisions.

For a fast non-rebuilding status check:

```powershell
python src\live_status.py
python src\live_status.py --format text
python src\go_live_checklist.py
python src\go_live_checklist.py --format text
```

These report live readiness, data-flow proof, preview-server state, unresolved
action-memory items, the implementation queue, and the go-live operating
checklist.

To add a supplied sudden market event before the refresh:

```powershell
python src\event_risk_intake.py --title "Iran/oil headline risk can change new-buy timing" --channels "oil,rates,volatility" --tickers "XOP,TNX" --why "Review exposure before adding risk." --trigger "WTI spike or Strait headlines accelerate." --out src\event_risks.json --summary src\event_risk_intake_summary.json --merge-existing
```

To add that event and immediately refresh the dashboard:

```powershell
python src\sudden_event_refresh.py --title "Iran/oil headline risk can change new-buy timing" --channels "oil,rates,volatility" --tickers "XOP,TNX" --why "Review exposure before adding risk." --trigger "WTI spike or Strait headlines accelerate."
```

High and critical event-risk rows surface as exposure-review actions, not
automatic buy/sell orders.

For one supplied file containing multiple manual sections:

```powershell
python src\manual_source_drop.py path\to\manual_drop.json --src-dir src
```

Use explicit top-level keys: `event_risks`, `signal_log`, and/or `catalysts`.
Start from `docs\manual_drop.template.json`, and check before writing with:

```powershell
python src\manual_source_drop.py docs\manual_drop.template.json --src-dir src --validate-only
```

## Resolving Open Review Items

List unresolved action-memory items:

```powershell
python src\action_memory_resolve.py --list
python src\action_memory_resolve.py --review-report
```

Resolve one after you decide:

```powershell
python src\action_memory_resolve.py --ticker ANET --status deferred --reason "wait for setup"
```

Allowed statuses are `acted`, `invalidated`, `ignored`, `deferred`, `missed`, `expired`, and `dropped`.

## Current Source Boundary

Repo convention files in `src\*.json` are the local operational state for this workspace. Missing optional sources must stay visible as not checked; do not overwrite them with empty files just to make the dashboard look clean.

Current expected optional dark lanes may include:

- `catalysts`: no Catalyst Calendar rows supplied.
- `signal_log`: no Morning Scan or Signal Log supplied.
- `source_calls` / `log_call_dates`: daily calls may be flowing, but calibration is not checked until scored source-call caches exist.

Monthly Fundstrat PDF intake stores only useful summary state. Do not parse or store Core List tables unless the user explicitly reopens that requirement. Stock-price chart clutter is out of scope.

## Verification

Standard check after implementation slices:

```powershell
python src\verify_standard.py
```

For dashboard JSX edits, also run:

```powershell
python src\verify_standard.py --include-js
```

## Important Entry Points

- `src\live_dashboard_refresh.py`: one-command local live refresh.
- `src\live_status.py`: non-rebuilding live status, data-flow proof, preview, open-action, and queue readout.
- `src\go_live_checklist.py`: non-mutating go-live checklist across refresh/status/source/review steps.
- `src\event_risk_intake.py`: supplied daily/weekly or one-line sudden-event risk intake.
- `src\sudden_event_refresh.py`: one-command supplied sudden-event intake plus dashboard refresh.
- `src\manual_source_drop.py`: one-file manual drop router for event risk, signal log, and catalysts.
- `src\dashboard_preview_server.py`: check/start the local dashboard preview server.
- `src\action_memory_resolve.py`: list or resolve open action-memory items.
- `src\live_readiness.py`: non-publishing go/no-go report.
- `src\full_build_runner.py`: builds the Contract-C cockpit feed from convention files.
- `src\render_cockpit.py`: injects the feed into the canonical JSX cockpit.
- `src\cockpit_html_gen.py`: renders the summary/export HTML preview.
- `src\codex_routine_manifest.json`: routine control plane and convention-input contract.
- `docs\codex_build_queue.md`: canonical implementation queue and completed slice history.
- `docs\dashboard_parity_review.md`: dashboard parity status; review before dashboard/feed meaning changes.

## Operating Rules

- Prioritize actionable buy/sell/hold/research items, time sensitivity, conviction, sizing, leverage, risk, and early-retirement impact.
- Use small build slices and commit after clean verification.
- Keep dark-lane honesty: missing source input is not checked, not all clear.
- The dashboard may surface review prompts and gates; it must not imply auto-buy or auto-sell.
- Keep Core List ingestion out of scope unless explicitly requested later.
