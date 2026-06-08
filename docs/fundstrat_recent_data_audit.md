# Fundstrat Recent Data Audit

Updated: 2026-06-07 23:01 ET; SMID backfill updated 2026-06-08

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
  - Add-price backfill: UW OHLC supplied May 28 add-price proxies for 19 unique monthly names. The selector prefers the May 28 premarket row because the Fundstrat report timestamp was pre-regular-session, then falls back to the May 28 regular-session row when no premarket row exists.

- Fundstrat daily cache: `src/fundstrat_daily_calls.json`
  - Stored call rows: 6
  - Dates: 2026-06-03 and 2026-06-05
  - Tickers: QQQ, RSP, RYF, SOX, TNX, XOP
  - Current interpretation: mostly Mark Newton technical/timing evidence, useful for timing filters and re-checks, not standalone thesis changes.

- Fundstrat inbox cache: `src/fundstrat_inbox_entries.json`
  - Stored inbox entries: 16
  - Date range: 2026-06-03 through 2026-06-05
  - Full-body/fetched entries: 5
  - Snippet-only entries: 11
  - Snippet-only rows remain discovery only and cannot count as checked-clear or synthesized evidence.

- Source-call cache: `src/source_calls.json`
  - Stored pending calls: 6
  - Tickers: QQQ, RSP, RYF, SOX, TNX, XOP
  - Current scoring lag: clean; no calls past window-end awaiting a score.

## Audit Findings

1. Top 5 SMID was initially missing from the compact cache and has now been backfilled from the May 28 Fundstrat FIRST WORD email.
   - Confirmed Top 5 SMID: STRL, IESC, FIX, CRS, FN.
   - Confirmed Bottom 5 SMID: ELF, SATS, UUUU, SOFI, KTOS.
   - The source email provides report percent moves and carry-over labels, not absolute add prices.

2. Price when added was initially missing and has now been backfilled from UW OHLC.
   - `top_prospects.json` has `add_date`, `add_price`, `add_price_source`, `add_price_date`, and `add_price_market_time` for the 19 unique monthly names.
   - SATS appears in both large-cap and SMID Bottom 5 lists but is one unique prospect-cache row.
   - Caveat: these are UW OHLC add-price proxies, not a raw Fundstrat-provided absolute price field.

3. Several June 3-5 inbox rows are still snippet-only.
   - This is not a bug if they were only discovered by search/snippet, but it means they should not be treated as synthesized.
   - If a snippet-only row sounds decision-relevant, the correct move is full-body read, compact extraction, and merge into the daily/source-call caches.

4. The live daily synthesis is using stored daily calls, target drift, and event risk, but it does not yet summarize the Fundstrat storage gaps.
   - The dashboard News tab and `If I Were You` section now surface those gaps directly.
   - Future synthesis can include this as a data-quality note when monthly performance or missed opportunities are discussed.

## Implementation Changes From This Audit

- Added `src/fundstrat_news.py`.
- Added `fundstrat_news` to `src/latest_cockpit_feed.json`.
- Added a JSX `News` tab beside `Commands`.
- Added a review-only `If I Were You` section.
- Updated the Fundstrat source-audit line to include cumulative stored cache counts, not just latest-run counts.
- Backfilled compact May 28 SMID Top 5 / Bottom 5 rows from the verified Fundstrat FIRST WORD Gmail source.
- Added `src/fundstrat_add_price_backfill.py` and backfilled monthly add prices from approved UW OHLC rows.

## Operating Rule

Fundstrat remains the baseline source of truth, but it is not an execution trigger by itself. Monthly list membership is thesis/allocation context; daily calls are faster-decay timing input. Anything stale, missing, snippet-only, or uncaptured stays visible as a gap instead of being treated as checked clear.
