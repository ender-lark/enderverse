# Catalyst Intake Routine

## Objective

Keep dated catalyst events from disappearing into memory or prose. A held-name
catalyst inside the action horizon must become a durable cockpit action through
`catalysts.json`.

## Inputs

- Preferred: exported Catalyst Calendar rows from Notion or another calendar
  source.
- Fallback: files in
  `G:\My Drive\Codex\Investing OS Context\03_Inbox\Catalyst_Calendar_Drop`.

Accepted file types:

- `.json` containing a list or `{events:[...]}` / `{rows:[...]}`
- `.csv` with ticker/date/label-like headers

## Procedure

1. Check the repo is on `main` and up to date.
2. If no Catalyst Calendar rows were fetched or supplied, do not overwrite
   `src/catalysts.json`; report catalysts as not checked.
3. If rows were supplied, run:

   ```bash
   python src/catalyst_calendar_intake.py <files> --out src/catalysts.json --summary src/catalyst_intake_summary.json --merge-existing
   ```

4. Run focused checks:

   ```bash
   python -m pytest src/test_catalyst_calendar_intake.py src/test_catalyst_lane.py src/test_act_now_surfacing.py -q
   ```

5. Summarize:
   - input rows
   - catalysts added
   - stored catalyst count
   - dates covered
   - whether no-input meant not checked

## Output Files

- `src/catalysts.json`
- `src/catalyst_intake_summary.json`

## Rules

- Missing catalyst input is not checked, not quiet tape.
- Do not generate catalyst actions directly from this routine.
- The full build owns action surfacing through the existing catalyst lane.
- MONITOR names remain review/risk-check only when surfaced downstream.
