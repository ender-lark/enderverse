# Daily Synthesis Intake Routine

## Objective

Normalize supplied Daily Synthesis JSON into `daily_synthesis.json` so the
cockpit can show the Synthesis panel and promote only explicit/conservative
synthesis actions.

This routine is a safe intake lane. It does not generate the synthesis read,
invent actions, or research stocks.

## Procedure

From a supplied JSON file:

```bash
python src/daily_synthesis_intake.py <daily-synthesis-json> --out src/daily_synthesis.json --summary src/daily_synthesis_intake_summary.json --merge-existing
```

From a connector/stdin JSON payload:

```bash
python src/daily_synthesis_intake.py --stdin-json --out src/daily_synthesis.json --summary src/daily_synthesis_intake_summary.json --merge-existing
```

Validate the current cache:

```bash
python src/daily_synthesis_intake.py --validate src/daily_synthesis.json
```

## Accepted Shape

The input may be a direct synthesis object or a wrapper such as
`daily_synthesis`, `synthesis`, `result`, or `payload`.

Useful fields:

- `source`
- `date`
- `state_of_play`
- `delta`
- `hanging`
- `actions`
- `action_items`
- `recommendations`
- `notes`

Structured action rows can use aliases already supported by the cockpit, such
as `ticker`, `symbol`, `what`, `action`, `recommendation`, `next_step`,
`urgency`, `time_window`, `sizing`, `capital_effect`, `goal_channels`, and
`missing_evidence`.

## Verification

```bash
python -m pytest src/test_daily_synthesis_intake.py src/test_actions_read.py src/test_cockpit_blocks.py -q
```

## Rules

- Do not overwrite `daily_synthesis.json` when no synthesis JSON is supplied.
- Do not convert vague prose into actions here; action promotion remains inside
  the cockpit's conservative synthesis action reader.
- Empty input is not checked, not a clean synthesis read.
- This routine may preserve supplied structured action metadata, but it must not
  create market recommendations.
