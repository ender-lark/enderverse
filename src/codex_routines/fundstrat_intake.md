# Fundstrat Intake Routine

## Objective

Get Fundstrat publications into repo convention files so the daily cockpit can
surface named calls, time-sensitive technicals, and source-call candidates.

## Inputs

- Daily updates: Gmail connector search for recent Fundstrat messages.
- Daytime urgent watch: Gmail connector search for fresh Fundstrat messages
  during market hours, with strict Pushover alerting only for time-sensitive
  or action-changing items.
- Daily fallback: files in `G:\My Drive\Codex\Investing OS Context\03_Inbox\Fundstrat_Email_Drop`.
- Manual website fallback: user-supplied Fundstrat website screenshots or text
  converted into compact action-relevant rows by Codex.
- Monthly/Bible update: direct uploaded Fundstrat monthly PDF, text export, or
  structured JSON deck.

Accepted daily fallback file types:

- `.txt`
- `.eml`
- `.json` containing a list of Gmail-like messages or `{messages:[...]}`

Accepted monthly file types:

- `.pdf` with selectable text
- `.txt`
- `.json` in the existing `fundstrat_bible.json` deck shape

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

   If the connector exposes full bodies only in the tool stream and cannot pipe
   them safely to a local JSON file, extract only compact, source-backed daily
   call rows and run:

   ```bash
   python src/fundstrat_daily_compact_intake.py --stdin-json --out-dir src --merge-existing
   ```

   This path is intentionally narrower: it writes `fundstrat_daily_calls.json`,
   `inbox_call_dates.json`, redacted audit entries, summary, state,
   `source_call_candidates.json`, `source_calls.json`, `log_call_dates.json`,
   and `source_call_cache_summary.json`, but it rejects long raw-body-like
   quotes and suppresses low-value Fundstrat fluff such as webinars, replays,
   promotional notes, and general commentary that does not change action
   posture, timing, sizing, risk, or research priority. It does not update top
   prospects. Use it only for full-body-derived compact metadata, never for
   snippet-only discovery.

   When the user supplies Fundstrat website screenshots or pasted text, first
   extract only compact rows that preserve source date, author/lane, ticker,
   direction/posture, and a short source-backed summary. Then run the same
   compact command above. Do not store raw screenshots, long website text, or
   raw publication bodies in repo files.

3. If the drop folder has files, run:

   ```bash
   python src/fundstrat_email_intake.py <files> --out-dir src --state src/fundstrat_intake_state.json --merge-existing --top-prospects src/top_prospects.json --source-calls src/source_calls.json --log-call-dates src/log_call_dates.json --source-call-summary src/source_call_cache_summary.json
   ```

4. If only Gmail search snippets were available, write them only as discovery
   audit entries. Snippet-only entries do not populate `inbox_call_dates.json`
   and must be reported as not full-body checked. They also do not update
   `source_calls.json` or `log_call_dates.json`.
   State handling must preserve the upgrade path: snippet-only message IDs go
   into `snippet_discovery_message_ids`, while only full-body rows go into
   `processed_full_body_message_ids` / `processed_message_ids`. A later
   `batch_read_email` result for the same message ID must not be filtered out
   just because the snippet was already discovered.
5. The canonical intake commands above merge classified full-body source-call
   candidates into the repo cache during the same run. If a manual remerge of
   existing `source_call_candidates.json` is needed, run:

   ```bash
   python src/source_call_cache_merge.py --candidates src/source_call_candidates.json --source-calls src/source_calls.json --log-dates src/log_call_dates.json
   ```

   If compact daily-call observations are already visible in the latest feed
   but source-call calibration is still not checked, draft reviewable pending
   candidates from those observations and merge them into the cache:

   ```bash
   python src/source_call_candidate_draft.py --feed src/latest_cockpit_feed.json --out src/source_call_candidates.json --merge-existing --merge-cache
   ```

   This only pre-registers pending calls from existing compact observations. It
   does not score Win/Loss/Push outcomes.

6. When the monthly Fundstrat update is directly uploaded, parse only useful
   labeled sections into `fundstrat_bible.json`:

   ```bash
   python src/fundstrat_bible_intake.py <monthly-pdf-or-text-or-json> --out src/fundstrat_bible.json --summary src/fundstrat_bible_intake_summary.json --merge-existing --top-prospects src/top_prospects.json
   ```

   The monthly parser is intentionally compact: it captures explicit summary
   sections such as `What to Own`, separate `Consider List` rows, `Top 5`,
   `Bottom 5`, and short stance text when present. Core List tables are left
   out to avoid overclutter and fragile row extraction; do not reopen them
   unless the user makes a new explicit request after the working system is in
   place. Top-5/Bottom-5 and separate Consider List rows remain the
   prospect-signal path. It does not store raw PDF text,
   stock-price chart text, performance tables, or long numeric notes.

7. Validate output shape and the raw-body redaction rule:

   ```bash
   python src/fundstrat_email_intake.py --validate src
   python src/fundstrat_bible_intake.py --validate src/fundstrat_bible.json
   ```

8. If no Gmail results and no drop-folder files exist, do not overwrite
   `fundstrat_daily_calls.json`; report Fundstrat as not checked.
9. For daytime watch runs, after compact rows are merged and validation passes,
   run:

   ```bash
   python src/fundstrat_daytime_alert.py --send --write-state --format text
   ```

   This reads `fundstrat_daily_calls.json`, checks duplicate suppression in
   `fundstrat_daytime_alert_state.json`, and sends a Pushover notification only
   when a fresh Fundstrat item changes `act`, `wait`, `re-check`, `research`,
   `trim`, `hedge`, or `size` posture. Low-value or context-only Fundstrat
   content should update neither the action stack nor Pushover.

10. Run focused checks:

   ```bash
   python -m pytest src/test_fundstrat_email_intake.py src/test_fundstrat_daily_compact_intake.py src/test_fundstrat_daytime_alert.py src/test_pushover_notify.py src/test_fundstrat_bible_intake.py src/test_fundstrat_daily.py src/test_source_call_cache_merge.py -q
   ```

11. Summarize:
   - emails parsed
   - full-body emails parsed
   - snippet-only emails discovered
   - daily calls emitted
   - source-call candidates emitted
   - source calls merged
   - monthly Top-5/Bottom-5/consider rows emitted, if a direct monthly upload
     was supplied
   - inbox dates written
   - whether no-input meant not checked

## Output Files

- `src/fundstrat_bible.json` when a monthly upload is supplied
- `src/fundstrat_bible_intake_summary.json` when a monthly upload is supplied
- `src/fundstrat_daily_calls.json`
- `src/fundstrat_daytime_alert_state.json` for duplicate-suppressed Pushover
  alerts
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
- Do not commit raw Fundstrat PDF text.
- Do not store monthly stock-price chart/table text that does not affect
  stance, What-to-Own, consider-list, Top-5, or Bottom-5 surfacing.
- Do not turn non-action mentions into daily-call rows.
- Do not turn low-value Fundstrat content into dashboard rows or alerts. Fluff,
  replays, webinar invites, promotional notes, and broad context with no action
  implication remain quiet audit/discovery context.
- Do not let snippet-only discovery update `top_prospects.json`.
- Do not let snippet-only discovery update `inbox_call_dates.json`.
- Do not let snippet-only discovery update `source_calls.json` or
  `log_call_dates.json`.
- Do not treat unfetched or unparsed emails as checked clear.
- Do not use compact daily-call intake for raw publication bodies; quotes must
  be short source-backed summaries or ticker-level excerpts.
- Do not make trade recommendations from this routine; it only prepares source
  inputs for the cockpit build.
- Push alerts are review prompts only. They should interrupt only for
  time-sensitive or action-changing Fundstrat evidence, and they must tell the
  operator to open the cockpit before acting.
