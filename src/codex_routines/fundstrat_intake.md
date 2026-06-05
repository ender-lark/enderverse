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
   intake with the Gmail connector `search_emails` tool. Validated search
   pattern:

   ```text
   (from:fundstrat OR from:fsinsight OR Fundstrat OR FSInsight OR "Tom Lee" OR "Mark Newton" OR "Sean Farrell") newer_than:14d -in:spam -in:trash
   ```

   Search results have the connector shape `{emails:[...]}` and are
   snippet-only discovery. They may be useful for deciding which message IDs to
   read, but they must not be treated as full-body checked.

   Read shortlisted message bodies with the Gmail connector `batch_read_email`
   tool in small batches, normally 5 messages or fewer. Feed the resulting
   Gmail connector JSON shape (`responses:[...]`) into:

   ```bash
   python src/fundstrat_email_intake.py --stdin-json --out-dir src --state src/fundstrat_intake_state.json --merge-existing --top-prospects src/top_prospects.json --source-calls src/source_calls.json --log-call-dates src/log_call_dates.json --source-call-summary src/source_call_cache_summary.json
   ```

   The parser accepts direct search rows and nested batch-read envelopes:
   `{emails:[...]}`, `{responses:[...]}`, `{results:[...]}`, `{items:[...]}`,
   and rows wrapped under `email`, `message`, `result`, or `data`. Search rows
   with only `snippet` remain snippet-only; only rows with full body/text/html
   fields can update daily calls, inbox dates, source-call candidates, or top
   prospects.

3. If the drop folder has files, run:

   ```bash
   python src/fundstrat_email_intake.py <files> --out-dir src --state src/fundstrat_intake_state.json --merge-existing --top-prospects src/top_prospects.json --source-calls src/source_calls.json --log-call-dates src/log_call_dates.json --source-call-summary src/source_call_cache_summary.json
   ```

4. If only Gmail search snippets were available, write them only as discovery
   audit entries. Snippet-only entries do not populate `inbox_call_dates.json`
   and must be reported as not full-body checked. They also do not update
   `source_calls.json` or `log_call_dates.json`.
5. The canonical intake commands above merge classified full-body source-call
   candidates into the repo cache during the same run. If a manual remerge of
   existing `source_call_candidates.json` is needed, run:

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
- Do not paste raw Fundstrat bodies into routine summaries.
- Do not turn non-action mentions into daily-call rows.
- Do not let snippet-only discovery update `top_prospects.json`.
- Do not let snippet-only discovery update `inbox_call_dates.json`.
- Do not let snippet-only discovery update `source_calls.json` or
  `log_call_dates.json`.
- Do not treat unfetched or unparsed emails as checked clear.
- Do not make trade recommendations from this routine; it only prepares source
  inputs for the cockpit build.
