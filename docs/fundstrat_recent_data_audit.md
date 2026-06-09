# Fundstrat Recent Data And Process Audit

Updated: 2026-06-09 14:35 ET

## Current Live Cache State

- Monthly Bible cache: `src/fundstrat_bible.json`
  - Source file: `20260528-Market-UpdatevFSD-1.pdf`
  - Deck date: 2026-05-28
  - Stored sections: What-to-Own, Top 5 large cap, Bottom 5 large cap, Top 5 SMID, Bottom 5 SMID
  - Stored What-to-Own: MAG7, Ethereum, Software, Industrials, Financials, Small-caps, Energy/Basic Materials
  - Stored Top 5 large cap: AMD, ANET, GOOGL, PWR, GS
  - Stored Top 5 SMID: STRL, IESC, FIX, CRS, FN
  - Stored Bottom 5 large cap: DE, TPL, HOOD, PKG, SATS
  - Stored Bottom 5 SMID: ELF, SATS, UUUU, SOFI, KTOS
  - Source backfill: Gmail Fundstrat FIRST WORD 2026-05-28 (`19e6d040f643eb49`) supplied compact SMID list names and report-move percentages.
  - Add-price backfill: UW OHLC supplied May 28 add-price proxies for 19 unique monthly names. These are approved OHLC proxies, not raw Fundstrat absolute add-price fields.

- Fundstrat daily cache: `src/fundstrat_daily_calls.json`
  - Stored call rows: 12
  - Dates: 2026-06-03, 2026-06-05, 2026-06-08, 2026-06-09
  - Main current rows: QQQ watch/defensive, RSP watch/rotation context, SOX watch, GOLD add-watch, MSTR patience/watch, GOOGL support/buy framing.
  - Current interpretation: daily rows are fast-decay timing, risk, and re-check filters. They are not standalone execution triggers.

- Source-call cache: `src/source_calls.json`
  - Stored pending calls: 12
  - Log dates: 2026-06-03, 2026-06-05, 2026-06-08, 2026-06-09
  - The prior stale warning was cleared by classifying compact full-body-derived daily rows into the same source-call cache used by full Gmail intake.

- Fundstrat inbox cache: `src/fundstrat_inbox_entries.json`
  - Stores redacted audit metadata only. Raw publication bodies must not be committed.
  - Snippet-only rows remain discovery only and cannot count as checked-clear or synthesized evidence.

## Process Verdict

The intended source hierarchy is correct after the 2026-06-09 fix:

1. `fundstrat_bible` is the monthly baseline.
   - It carries list membership, What-to-Own sectors, and stance context.
   - It is monthly cadence context, not a fresh tape read.
   - It can support thesis/allocation work, candidate lists, and top-prospect tracking.

2. `fundstrat_daily` is the fast-decay overlay.
   - It can update timing, support/resistance, risk posture, add/trim/avoid/watch framing, and research priority.
   - It can override or gate the monthly baseline when the story changes after the monthly deck.
   - It should route capital actions to `Re-check Before Acting` unless same-session price/flow/event evidence confirms the call still applies.

3. Fundstrat is one independence group.
   - Monthly Bible and daily notes share `independence_group = fundstrat`.
   - Multiple FS notes can increase persistence and urgency, but they do not count as independent confirmation by themselves.
   - Same-source conflicts must downgrade toward hold, no-add, re-check, watch, or research until resolved.

4. Current events and tape can supersede older FS context.
   - Example: the 2026-05-28 Bible is constructive on MAG7/Software and Top 5 names such as GOOGL/ANET, but the 2026-06-08 Newton daily note makes Growth/QQQ/AI-beta a tactical re-check, not an automatic dip-buy.
   - Example: MSTR reserve rebuild eased immediate tailspin risk, but the June 9 Farrell update still says patience until demand/reserve concerns improve.
   - Example: GOOGL remains monthly/daily-supported, but the AI-infrastructure financing/capital-raise context creates a separate review gate before simple add framing.

5. Calibration dates must mean source-call dates, not generic inbox dates.
   - Full-body notes that produce action-like daily calls update `inbox_call_dates.json`.
   - Compact full-body-derived daily rows now also classify into `source_call_candidates.json`, `source_calls.json`, `log_call_dates.json`, and `source_call_cache_summary.json`.
   - Full-body context notes that produce no action-like call stay in the redacted audit file but do not create `inbox_call_dates` gaps.
   - Snippets never update daily calls, top prospects, inbox call dates, or source-call calibration.

## June 9 Fixes

- `src/fundstrat_daily_compact_intake.py`
  - Now classifies compact full-body-derived daily rows into source-call candidates.
  - Now merges those candidates into `source_calls.json`, `log_call_dates.json`, and `source_call_cache_summary.json`.
  - Preserves existing source-call candidates while adding newly classified compact rows.

- `src/fundstrat_email_intake.py`
  - Now populates `inbox_call_dates.json` from extracted action-like daily calls, not from every full-body email date.
  - Keeps no-action full-body context in the redacted audit file without creating a false source-call stale warning.

## Operating Rule

Fundstrat remains important, but it is not an execution trigger by itself. Monthly list membership is thesis/allocation context; daily calls are faster-decay timing and risk input. A monthly Top 5 name can still be a no-add or re-check today if a newer daily note, market event, financing change, earnings change, rates/oil move, or same-session tape invalidates the older setup. Anything stale, missing, snippet-only, or uncaptured stays visible as a gap instead of being treated as checked clear.
