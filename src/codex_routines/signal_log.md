# Signal Log Intake Routine

## Objective

Normalize supplied Signal Log or Morning Scan JSON into `signal_log.json` so the
cockpit can display watch-only context.

This routine does not create buy/sell/trim actions. Signal Log rows can explain
attention, but action promotion requires a sharper source.

## Procedure

From a supplied JSON file:

```bash
python src/signal_log_intake.py <signal-log-json> --out src/signal_log.json --summary src/signal_log_intake_summary.json --merge-existing
```

From a connector/stdin JSON payload:

```bash
python src/signal_log_intake.py --stdin-json --out src/signal_log.json --summary src/signal_log_intake_summary.json --merge-existing
```

Validate the current cache:

```bash
python src/signal_log_intake.py --validate src/signal_log.json
```

## Accepted Shape

Input may be a list of rows or a wrapper such as `signal_log`, `signals`,
`rows`, `items`, `results`, or `morning_scan`.

Useful row fields:

- `ticker` or `symbol`
- `signal`, `title`, `what`, `summary`, `note`, or `description`
- `date`, `as_of`, `created_at`, or `timestamp`
- `priority`, `urgency`, or `rank`
- `source`

## Verification

```bash
python -m pytest src/test_signal_log_intake.py src/test_cockpit_blocks.py src/test_research_priority_label.py -q
```

## Rules

- Do not overwrite `signal_log.json` when no signal log is supplied.
- Rows are watch-only and must not directly promote into Today's Actions.
- Missing Signal Log input is not checked, not no signals.
- Empty or textless rows fail validation instead of publishing a false checked
  lane.
