# Plan 03 — Prospect Engine (find · score · price)

> The core: ZIP → well-reviewed, website-less local businesses → 0–100 lead score → estimated monthly willingness-to-pay → competitor + ROI math. Source research: `docs/research/01-target-businesses.md`, `02-website-pricing.md`, `05-tech-data-ai.md`.

## Pipeline

```
ZIP ─▶ geocode (lat/lng) ─▶ for each target category: Places Text Search (circle bias)
    ─▶ collect candidates (place_id, name, types, rating, reviewCount, priceLevel, websiteUri, phone, location)
    ─▶ no-website classifier (URL classify + HTTP probe)
    ─▶ quality filter (min rating/reviews)
    ─▶ enrich: zip demographics (ACS), competitor finder
    ─▶ score (0–100) + estimate WTP + ROI
    ─▶ persist Prospect rows ─▶ rank ─▶ return top N to UI
```

## 1. Finding candidates (Places API New)

- **Geocode** the ZIP → center lat/lng (Geocoding API, Essentials tier).
- **Per category** in the active target list (Research 01 A/B-tier first), run **Text Search (New)** `"{category} in {zip}"` with `locationBias` circle, `includedType` where available.
- **Field mask** (single Search call returns everything needed — usually skip Place Details to stay at ~$1/zip): `places.id,places.displayName,places.types,places.rating,places.userRatingCount,places.priceLevel,places.websiteUri,places.nationalPhoneNumber,places.formattedAddress,places.location,nextPageToken`.
- Requesting `rating`/`userRatingCount`/`websiteUri` bills at **Enterprise SKU** — unavoidable; optimize call count, not fields.
- **Coverage:** 60-result hard cap per query (20/page × 3). For dense categories, grid-tile the ZIP (overlapping sub-circles) and use finer category terms. Dedupe by `place_id`. **Log when results are capped** (no silent truncation).
- **Cost:** ~$1/ZIP relying on Search responses; ~$4/ZIP if per-candidate Place Details added. Free dev tier: 1,000 Enterprise events/mo. Mock mode returns fixture candidates.

## 2. "No website" classifier

`websiteUri` absence is a strong flag, not a verdict. Two-pass:
- **Pass 1 — URL classification** (when a `websiteUri` IS present): strip UTM, take eTLD+1. Treat as **NOT a real site** if it's a social domain (facebook/instagram/tiktok), link-in-bio (linktr.ee), directory/booking portal (yelp/opentable/vagaro/healthgrades), or a builder placeholder (`*.business.site` [retired ~2024, often dead], `sites.google.com`, default builder URLs).
- **Pass 2 — HTTP probe** survivors: HEAD→GET, follow redirects, check redirect target + parked-page markers; TLS error = weak negative.
- Output: `websiteStatus ∈ { none, social_only, directory_only, placeholder_dead, real }`. Prospects = everything except `real`. `social_only` is a *great* prospect (the "you have a Facebook page" objection is pre-answered).

## 3. Quality filter (winnability)

Defaults (tunable in `config/scoring.ts`):
- `rating >= 4.3` AND `userRatingCount >= 25` (proven demand). Looser floor for low-volume premium categories (e.g. fertility).
- Category in the active target list.
- Has a phone number (callable).

## 4. Lead score (0–100)

Weighted, transparent, all inputs from Places + ACS + category table. Each sub-score normalized 0–1 then weighted:

| Component | Weight | Definition |
|---|---|---|
| **Category value** | 30 | A-tier=1.0, B=0.7, C=0.45, D=0.2 (from Research 01 tiering — LTV × local-search dependence × affordability). |
| **Reputation strength** | 20 | blend of rating (relative to 4.3–5.0) and log(reviewCount) capped — proven demand they're failing to capture. |
| **Website gap severity** | 20 | `none`=1.0, `social_only`=0.9, `directory_only`=0.7, `placeholder_dead`=0.85 (clear opening). |
| **Market wealth** | 15 | ACS zip median household income vs national median, clamped 0.4–1.0 (ability to pay). |
| **Competitive pressure** | 10 | a strong ranked competitor WITH a site exists, ideally with weaker reviews than the prospect (sharper pitch). |
| **Price level fit** | 5 | Places `priceLevel` aligns with a premium offer. |

`leadScore = round(100 × Σ weightᵢ × subScoreᵢ / Σ weightᵢ)`. Store the component breakdown for display ("why this score"). Score ≈ probability this is a high-value, winnable, high-WTP prospect.

## 5. Willingness-to-pay (recommended monthly price)

Per Research 02 price book:
```
monthly = round_to_9( BASE × industry_mult × geo_mult × strength_mult ), clamped [99, 899]
BASE = 199
industry_mult: A medical/legal 1.8–2.0 · high-ticket trades 1.3–1.5 · standard svc 1.0–1.2 · low-ticket personal care 0.8–1.0
geo_mult: from ACS income band, 0.85–1.40
strength_mult: 0.9–1.15 from reviews/rating/competitor pressure
```
Also surface a **tier suggestion** (Starter $149 / Growth $199 / Pro $349 pre-multiplier) and an **optional one-time build price** for operators who prefer project pricing. Worked examples (Research 02): affluent med spa ≈ $499/mo; wealthy-suburb dentist ≈ $529/mo; mid-income plumber ≈ $279/mo; rural barbershop ≈ $149/mo.

## 6. Competitor finder

For the chosen prospect's `coreKeyword = "{service} near {town}"`:
- Run a Places Text Search for the same category in the area; pick the **top-ranked result that HAS a real website** and is not the prospect.
- Capture `{name, rank, stars, reviews, hasSite:true}`. Flag the **asymmetry win** when the prospect's rating/review count is BETTER than this competitor's (the strongest pitch line).
- Store on the prospect for the pitch generator.

## 7. ROI math (for pitch + UI)

Defensible ranges, labeled estimates:
```
revenueAtRisk/mo ≈ monthlySearchers × lostPct × avgTicket
  monthlySearchers: rough per-category/per-zip estimate (seed table; refine later)
  lostPct: 0.20–0.35 (referred customers lost at the "verification" step with no site)
  avgTicket / new-customer value: from Research 01 category table
```
Show the assumption band, never false precision. This feeds Pitch `keyFacts.roi`.

## 8. Persistence & ToS

- **Store only `place_id` long-term**; treat other Places fields as ~30-day cache then refresh/delete (Google ToS).
- **Material ToS clause:** do NOT build/sell a "business listings / telemarketing list" from Maps content. Mitigation: this is the operator's own pipeline for direct outreach, not resale; keep retention minimal; document this in `00-DECISIONS.md` guardrails. (Flag for owner.)
- Optional cost-reduction backbone: pre-filter with free **Foursquare OS Places** (storable, has `website` field, no ratings), then confirm with Google.

## Acceptance criteria
- Given a ZIP, returns a ranked list of website-less, well-reviewed prospects with a 0–100 score, score breakdown, recommended monthly price, a named competitor (when one exists), and ROI math — all in mock mode without spending, and against live Places when keys are set.
- No-website classifier correctly treats Facebook-only / Linktree / dead-`business.site` as prospects.
- Pricing matches the Research 02 worked examples within rounding.
