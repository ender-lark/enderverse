# Fundstrat Intake Routine

## Objective

Get Fundstrat publications into repo convention files so the daily cockpit can
surface named calls, time-sensitive technicals, and source-call candidates.

## Inputs

- Preferred: Gmail connector search for recent Fundstrat messages.
- Fallback: files in `G:\My Drive\Codex\Investing OS Context\03_Inbox\Fundstrat_Email_Drop`.

Accepted fallback file types:

- `.txt`
- `.eml`
- `.json` containing a list of Gmail-like messages or `{messages:[...]}`

## Procedure

1. Check the repo is on `main` and up to date.
2. If Gmail is available, search for Fundstrat emails since the last successful
   intake. Validated search pattern:

   ```text
   (from:fundstrat OR from:fsinsight OR Fundstrat OR FSInsight OR "Tom Lee" OR "Mark Newton" OR "Sean Farrell") newer_than:14d -in:spam -in:trash
   ```

   Read shortlisted message bodies with the Gmail batch-read tool. Feed the
   resulting Gmail connector JSON shape (`responses:[...]`) into:

   ```bash
   python src/fundstrat_email_intake.py --stdin-json --out-dir src --state src/fundstrat_intake_state.json --merge-existing --top-prospects src/top_prospects.json
   ```

3. If the drop folder has files, run:

   ```bash
   python src/fundstrat_email_intake.py <files> --out-dir src --state src/fundstrat_intake_state.json --merge-existing --top-prospects src/top_prospects.json
   ```

4. If only Gmail search snippets were available, write them only as discovery
   audit entries. Snippet-only entries do not populate `inbox_call_dates.json`
   and must be reported as not full-body checked.
5. After a full-body parse, merge classified source-call candidates into the
   repo cache:

   ```bash
   python src/source_call_cache_merge.py --candidates src/source_call_candidates.json --source-calls src/source_calls.json --log-dates src/log_call_dates.json
   ```

6. Validate output shape and the raw-body redaction rule:

   ```bash
   python src/fundstrat_email_intake.py --validate src
   ```

7. If no Gmail results and no drop-folder files exist, do not overwrite
   `fundstrat_daily_calls.json`; report Fundstrat as not checked.
8. Run focused checks:

   ```bash
   python -m pytest src/test_fundstrat_email_intake.py src/test_fundstrat_daily.py src/test_source_call_cache_merge.py -q
   ```

9. Summarize:
   - emails parsed
   - full-body emails parsed
   - snippet-only emails discovered
   - daily calls emitted
   - source-call candidates emitted
   - source calls merged
   - inbox dates written
   - whether no-input meant not checked

## Output Files

- `src/fundstrat_daily_calls.json`
- `src/fundstrat_inbox_entries.json`
- `src/inbox_call_dates.json`
- `src/log_call_dates.json`
- `src/source_calls.json`
- `src/source_call_candidates.json`
- `src/source_call_cache_summary.json`
- `src/fundstrat_intake_summary.json`
- `src/fundstrat_intake_state.json`
- `src/top_prospects.json` when full-body daily calls produced prospect events

`fundstrat_inbox_entries.json` redacts raw email bodies by default and stores
only body length/hash metadata. Use `--keep-bodies` only for temporary local
debugging, and do not commit raw publication bodies.

## Rules

- Preserve source date and author.
- Do not commit raw Fundstrat email bodies.
- Do not turn non-action mentions into daily-call rows.
- Do not let snippet-only discovery update `top_prospects.json`.
- Do not treat unfetched or unparsed emails as checked clear.
- Do not make trade recommendations from this routine; it only prepares source
  inputs for the cockpit build.
