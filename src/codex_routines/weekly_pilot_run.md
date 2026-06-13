# Weekly Pilot Run Routine

## Objective

Run the Sunday operator-facing system pilot without creating a new schedule.
This prompt belongs to the existing `investing-os-weekly-pilot-run` automation
at Sunday 6:00 PM ET.

## Required Integration-Debt Check

Before summarizing weekly readiness, run:

```bash
python src/integration_debt_sweep.py --out docs/integration_debt_report.md --json-out src/integration_debt_report.json
```

Review the resulting warning count in the dashboard source-audit panel. A
warning is not a trading alert; it is system debt that can make a lane dark,
stale, duplicated, or only manually checked.

## Weekly Pilot Procedure

1. Check cloud routine receipt health and overdue rows.
2. Check source freshness and dashboard build state.
3. Run the integration-debt sweep and preserve `not_checked` for missing
   Notion queue rows unless a live queue export/connector snapshot is supplied.
4. Review whether the v11.10 options-exit cadence is actually live in a routine
   or STALE-LEAPS surface before treating option exits as fully covered.
5. Summarize blockers, warnings, and next actions. Do not execute trades.

## Rules

- Do not create a second weekly schedule.
- Do not close or mutate Notion queue rows from this routine; T6 owns Notion
  queue execution.
- Missing live Notion queue state is `not_checked`, not clear.
- System-health warnings stay in Ops unless they change action validity,
  sizing, timing, or risk.
