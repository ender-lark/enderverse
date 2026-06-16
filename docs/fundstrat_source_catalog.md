# Fundstrat Source Catalog

Last Chrome review: 2026-06-15.

This catalog records how Fundstrat Direct web surfaces should feed the Investing
OS. It is a routing guide, not a scraping plan. Fundstrat member content should
be read through the authenticated Chrome session and reduced to compact,
source-backed rows; raw article bodies, screenshots, long excerpts,
credentials, cookies, local storage, and browser profile data stay out of repo
files.

## Capture Priority

| Source family | Observed surface | Current use | Capture rule |
| --- | --- | --- | --- |
| Macro FlashInsights | `members/flashinsights/` | Fast same-day tactical source | Checked when the complete feed card is visible. Use `source_surface=flashinsights_feed`. |
| Crypto FlashInsights | `members/crypto-flash-insights/` | Fast same-day crypto source | Same as Macro FlashInsights; capture only compact ticker/asset calls. |
| Intraday Word | `latest-research/?category=intraday-alert` | High-decay article source | Listing cards are discovery only. Open the article detail page before checked capture. |
| First Word | `latest-research/?category=first-word` | Pre-market and same-day macro posture | Detail page required for checked capture. Use for posture, timing, risk, sizing, and named-ticker implications. |
| Daily Technical Strategy | `latest-research/?category=daily-technical-strategy` | Technical levels and risk checks | Detail page required. Capture only levels, invalidation, timing, and named-ticker/sector implications. |
| Live Technical Stock Analysis | `latest-research/?category=live-technical-stock-analysis` | Named-stock technical context | Detail page required. Useful when it touches held names, queued research, or high-priority candidates. |
| US Policy / Fed Watch | `latest-research/?category=us-policy`, `?category=fed-watch` | Macro/event-risk context | Detail page required. Promote only if it changes exposure review, rates/oil/geopolitical risk, or catalyst timing. |
| Crypto Research | Digital Asset Strategy, Funding Fridays, Liquid Ventures, Special Reports | Crypto sleeve context | Detail page required. Promote only if it changes crypto sleeve posture, a held asset, or a priority crypto-equity proxy. |
| Tom Lee Macro Minute and other videos | Macro Minute, Latest Videos, media pages | Private transcript vault plus compact derived rows | Video-only cards remain discovery-only. Checked review requires visible transcript/captions, companion article, or supplied compact notes. Full transcript text goes only to the private source vault; public repo caches keep metadata, hashes, synthesis, and compact derived rows. |
| Webinars and appearances | Latest Webinars, market updates, in-the-news | Mostly noise | Discovery/audit only unless there is a concrete, transcript-backed call tied to current holdings or high-priority research. |
| Top Ideas stock lists | Large-Cap, SMID-Cap | Baseline/watchlist, not daily-call | Tables include ticker, sector/industry, price, performance, support, resistance, and date added. Use later for adds/removes/support-resistance changes, not routine daily-call alerts. |
| Upticks | Stock list, commentary, performance, historical | Baseline/watchlist | Same table-style baseline. Capture only meaningful list changes or technical levels that overlap portfolio/research priorities. |
| Sector Allocation | Current Outlook, prior outlooks, sector/tools/performance | Allocation baseline | Useful for sector over/under-weight comparison and ETF sleeve review. Do not promote unchanged tables to daily actions. |
| Crypto Core Strategy / Crypto Picks | Strategy, performance, historical changes, tools | Crypto allocation baseline | Tables include asset, weight, rebalance price/current price, and rebalance date. Use for crypto sleeve baseline/diffing, not daily-call rows. |
| Market Heatmap / Watchlist | Tools pages | Context, usually redundant | Existing market-data and portfolio lanes are canonical. Use only as manual context unless a future tool proves a specific edge. |
| Community / Academy / books / account pages | Community and account settings | Not an investing signal | Do not capture except for operator setup notes. |
| iOS/app push notifications | Fundstrat app notifications | Trigger only | Pushes can tell us a new item exists. They are not checked source content and must lead to website/Gmail detail review. |

## Tomorrow Run Order

1. Daytime Watch opens authenticated Chrome and checks Macro FlashInsights plus
   Crypto FlashInsights first. New full cards go through
   `python src/fundstrat_web_intake.py --stdin-json --out-dir src --merge-existing`.
2. If a notification, unread badge, or listing card points to a standard
   article, open the detail page before capture. Use
   `source_surface=article_detail` and a `full_content_basis` that explicitly
   says the article detail page text was visible.
3. Video cards are discovery-only unless transcript/caption/companion text is
   visible. One Mark Newton transcript proof has landed. Repeat work should use
   `fundstrat_transcript_vault.py` for full private-vault review packs and the
   existing compact fields only for cockpit/source-call derivation.
4. Stock-list and crypto-list tables are not part of tomorrow's fast lane. They
   should become a slower baseline/diff lane only if they produce adds/removes,
   weight changes, support/resistance changes, or direct portfolio overlap.

## Noise Filters

Capture only when the item changes one of:

- act/wait/trim/avoid/hedge posture
- intraday or same-session timing
- sizing or leverage posture
- risk, support, resistance, target, or invalidation level
- research priority for a named current holding or high-priority candidate
- sector/crypto allocation baseline when it changes versus prior state

Suppress by default:

- listing-card previews, search results, push notifications, and unread badges
- video-only titles, thumbnails, and embedded players without transcript/caption
- webinars, replay invites, promotions, and appearances with no concrete call
- unchanged list tables or broad market background with no action implication
- generic trending/watchlist/tool rows that duplicate existing market-data lanes

## Implementation State

- Implemented now: strict compact web wrapper
  `src/fundstrat_web_intake.py`, web fast-lane protocol, and routine/manifest
  routing for FlashInsights and article-detail compact rows.
- Active for tomorrow: scheduled Fundstrat routines should prefer the
  authenticated Chrome web lane when Chrome is available and fall back to Gmail
  full-body intake when it is not.
- Implemented now: private source-vault transcript review packs through
  `src/fundstrat_transcript_vault.py`, with public metadata in
  `src/fundstrat_transcript_index.json` and compact rows still routed through
  the existing web wrapper when useful.
- Deferred until evidence of usefulness: structured list-table baseline diffing
  for Top Ideas, Upticks, Sector Allocation, and Crypto Core Strategy.
