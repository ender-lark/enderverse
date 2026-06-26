# Fundstrat Deep Crawl Routine

## Objective

Run a slower authenticated Fundstrat website crawl that covers the sections the
fast FlashInsights lane intentionally skips: Stock Lists, Sector Allocation,
Fundstrat Large-Cap Top Ideas, Fundstrat SMID-Cap Top Ideas, Upticks, crypto
strategy tables, and the usual research/video surfaces.

This routine is a baseline/diff and discovery lane. It can create compact
action-relevant rows through existing Fundstrat intake helpers, but it must not
turn unchanged tables into action prompts.

## Inputs

- Authenticated Fundstrat member pages through the user's logged-in Chrome
  session.
- Target manifest: `src/fundstrat_deep_crawl_targets.json`.
- Existing Fundstrat compact intake helpers and caches.
- Existing dashboard/feed artifacts for portfolio overlap checks.

## Procedure

1. Write a `started` receipt with `run_source=scheduled` for
   `investing-os-fundstrat-deep-crawl`.
2. Verify the target manifest:

   ```powershell
   python src/fundstrat_deep_crawl.py --validate
   ```

3. Read `docs/fundstrat_source_catalog.md`,
   `docs/fundstrat_web_fast_lane.md`, and
   `src/fundstrat_deep_crawl_targets.json`.
4. Use logged-in Chrome to check every target in the manifest. The screenshot
   reference sections are included explicitly:
   - Stock Lists / Latest Stock Lists
   - Upticks / Stock List / Performance / Commentary / Historical
   - Sector Allocation / Current Outlook / Prior Outlooks / Performance /
     Sector / Tools
   - Fundstrat Large-Cap Top Ideas / Stock List / Commentary
   - Fundstrat SMID-Cap Top Ideas / Stock List / Commentary
5. For FlashInsights, standard research, and transcript-backed videos, use the
   existing compact web intake rules. Detail pages are required for standard
   articles; video-only cards remain discovery-only.
6. For stock-list, sector-allocation, Top Ideas, Upticks, and crypto strategy
   tables:
   - Capture only compact baseline/diff metadata: section, visible date,
     table title, tickers/assets, weights, stances, support/resistance, dates
     added, adds/removes, and short action implication.
   - Do not store raw page text, screenshots, raw tables, credentials, cookies,
     local storage, browser profile data, or long excerpts.
   - Do not emit a daily-call row for an unchanged table.
   - Emit a compact row only when a change affects portfolio exposure,
     research priority, sector stance, support/resistance levels, adds/removes,
     or a high-priority watch/interest name.
7. Write or update only deep-crawl-owned summary/baseline artifacts for table
   checks, such as `src/fundstrat_deep_crawl_summary.json` and
   `src/fundstrat_list_baselines.json`. Existing Fundstrat daily-call or
   source-call cache writes should go through their owning helpers, not
   ad-hoc JSON edits.
8. If compact Fundstrat rows land, validate the normal Fundstrat cache:

   ```powershell
   python src/fundstrat_email_intake.py --validate src
   ```

9. Refresh the dashboard only if the crawl lands compact rows, updates a
   baseline/diff artifact, or changes watch/interest context.
10. Validate:

   ```powershell
   python src/fundstrat_deep_crawl.py --validate
   python -m pytest src/test_fundstrat_deep_crawl.py src/test_fundstrat_web_intake.py -q
   ```

11. Append a `success` or `failed` receipt with this same routine id. The final
    summary must name sections checked, sections not checked, rows/diffs landed,
    any portfolio/watchlist overlaps, validation results, and blockers.
12. Use the safe helper to commit/push routine-owned outputs if changed:

    ```powershell
    python src/cloud_routine_commit.py --message "Fundstrat deep crawl scheduled run" --push --format text
    ```

## No-Input Behavior

If Chrome is unavailable, logged out, blocked by CAPTCHA/permission prompts, or
the relevant pages do not expose tables/detail text, write a failed or
not-checked receipt naming the exact blocker. Do not mark the deep crawl checked
clear and do not overwrite baseline artifacts.

If a section is visible but unchanged, record it as checked/no-change in the
deep-crawl summary only. Do not create daily-call rows, action prompts, or
Pushover alerts from unchanged stock-list tables.

## Public/Private Boundary

- Public repo allowed: compact metadata, hashes, target ids, checked/no-change
  statuses, adds/removes, short summaries, and validation results.
- Private or not stored: raw Fundstrat member-page text, screenshots, raw
  tables, credentials, cookies, local storage, browser profile data, full
  article bodies, and raw transcripts.
