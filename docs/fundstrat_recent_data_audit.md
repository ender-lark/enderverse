# Fundstrat Recent Data Audit

Updated: 2026-06-07 23:01 ET

## Current Live Cache State

- Monthly Bible cache: `src/fundstrat_bible.json`
  - Source file: `20260528-Market-UpdatevFSD-1.pdf`
  - Deck date: 2026-05-28
  - Stored sections: What-to-Own, Top 5 large cap, Bottom 5
  - Stored What-to-Own: MAG7, Ethereum, Software, Industrials, Financials, Small-caps, Energy/Basic Materials
  - Stored Top 5 large cap: AMD, ANET, GOOGL, PWR, GS
  - Stored Bottom 5: DE, TPL, HOOD, PKG, SATS

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

1. Top 5 SMID is not stored in the live monthly/prospect caches.
   - Older fixtures mention FN as a Top-5 SMID watch, but the live `fundstrat_bible.json` and `top_prospects.json` do not currently store a SMID Top 5 list.
   - Treat this as a storage gap, not as current live evidence.
   - Next step: re-read the May 28 monthly material or supplied PDF text and explicitly store SMID rows if confirmed.

2. Price when added is not captured for monthly Top 5 / Bottom 5 rows.
   - `top_prospects.json` has `add_date` for the 10 monthly rows but `add_price` is null for all 10.
   - The News tab now labels these as `not captured`.
   - Next step: backfill from an approved historical price cache before using since-added performance.

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

## Operating Rule

Fundstrat remains the baseline source of truth, but it is not an execution trigger by itself. Monthly list membership is thesis/allocation context; daily calls are faster-decay timing input. Anything stale, missing, snippet-only, or uncaptured stays visible as a gap instead of being treated as checked clear.
