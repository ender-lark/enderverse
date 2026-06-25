# Technical Brief: Data + AI Layer for a "Zip → No-Website Local Business → Generated Website" Tool

*Prepared 2026-06-25. All pricing/figures verified against official docs (2024–2026) and reputable secondary sources where official pages were bot-blocked. Verify the load-bearing numbers against the live pages cited before committing budget — Google changed Maps pricing on 2025-03-01 and continues to revise it.*

---

## 0. System overview (how the layers fit)

```
ZIP ──► Geocode ZIP → lat/lng (+ radius)
     ──► For each business category:
            Places Text/Nearby Search (New)  → candidate places (+ place_id)
            Places Place Details (New)        → websiteUri, rating, phone, etc.
     ──► "No website" classifier (websiteUri absent OR social/directory/placeholder + HTTP probe)
     ──► Quality filter (rating ≥ X, userRatingCount ≥ Y)
     ──► Pricing multiplier (Census ACS median income by ZCTA)
     ──► AI generation: Claude → structured JSON → fixed React/Next template system → 2 variants
     ──► Host on wildcard subdomain (business.tool.com), DB-backed render
```

Durable storage rule (ToS): **store only `place_id` long-term**; treat all other Places fields as cache-and-refresh (see §7).

---

# 1. Google Places API (New)

## 1.1 Which endpoint returns what

There are three relevant endpoints in the **Places API (New)** (`places.googleapis.com/v1/...`). All three use a **required `X-Goog-FieldMask` header** and an `X-Goog-Api-Key` header. ([Text Search New](https://developers.google.com/maps/documentation/places/web-service/text-search), [Nearby Search New](https://developers.google.com/maps/documentation/places/web-service/nearby-search), [Place Details New](https://developers.google.com/maps/documentation/places/web-service/place-details), [Choose fields / field masks](https://developers.google.com/maps/documentation/places/web-service/choose-fields))

| Field you need | Available in Search (Text/Nearby)? | Available in Place Details? | SKU tier that field triggers |
|---|---|---|---|
| `displayName` (business name) | Yes | Yes | Pro |
| `types` / `primaryType` (category) | Yes | Yes | Pro |
| `formattedAddress` | Yes | Yes | Pro |
| `location` (lat/lng) | Yes | Yes | Pro |
| `photos` | Yes | Yes | Pro |
| `rating` | Yes | Yes | **Enterprise** |
| `userRatingCount` | Yes | Yes | **Enterprise** |
| `priceLevel` | Yes | Yes | **Enterprise** |
| `nationalPhoneNumber` / `internationalPhoneNumber` | Yes | Yes | **Enterprise** |
| `regularOpeningHours` / `currentOpeningHours` | Yes | Yes | **Enterprise** |
| **`websiteUri`** | Yes | Yes | **Enterprise** |
| `id` / `name` / `nextPageToken` | Yes | Yes | Essentials (ID-only) |

Field-to-SKU mapping confirmed: `places.rating`, `places.userRatingCount`, `places.priceLevel`, `places.websiteUri`, `places.nationalPhoneNumber`, and `places.*OpeningHours` all fall in the **Enterprise** SKU; name/address/types/photos/location are **Pro**; id-only is **Essentials**. You are billed at the **highest** SKU any requested field belongs to. ([Place Data Fields New](https://developers.google.com/maps/documentation/places/web-service/data-fields), [Usage and billing](https://developers.google.com/maps/documentation/places/web-service/usage-and-billing))

**Key takeaway:** because you need `rating`, `userRatingCount`, and `websiteUri`, every "rich" call you make lands in the **Enterprise** SKU. So you cannot avoid Enterprise pricing on the data fields that define this product. The optimization lever is *call shape* (see §1.6), not field selection.

## 1.2 Does absence of `websiteUri` reliably mean "no website"?

**Mostly yes, but not perfectly — treat it as a strong candidate flag, not a verdict.** `websiteUri` is returned only when Google has a website on file for that Place.

- **Good news for this use case:** Google Business Profile stores **social links separately** from the website field, and social links can't be added via API/bulk tools. So a business with only a Facebook/Instagram page generally surfaces *correctly* as "no `websiteUri`." ([GBP social media links](https://support.google.com/business/answer/13580646?hl=en))
- **False negatives** (no `websiteUri` but they do have a site): Google simply doesn't have the URL on file. Mitigate with an optional confirmation search.
- **False positives** (has `websiteUri` but it's not a real site): owners/Google sometimes paste a Facebook URL, a Linktree, a Yelp listing, or a now-dead `*.business.site` Google-generated page into the website field. **You must classify the URL** (see §3).

## 1.3 Field masks (exact syntax)

The field mask is an HTTP header, with `places.` prefix for Search responses (which return a `places[]` array) and no prefix for Place Details (single object).

```
# Text/Nearby Search
X-Goog-FieldMask: places.id,places.displayName,places.types,places.primaryType,
  places.formattedAddress,places.location,places.rating,places.userRatingCount,
  places.priceLevel,places.websiteUri,places.nationalPhoneNumber,places.photos,
  nextPageToken

# Place Details
X-Goog-FieldMask: id,displayName,types,formattedAddress,rating,userRatingCount,
  priceLevel,websiteUri,nationalPhoneNumber,regularOpeningHours,photos
```
Requesting `*` (all fields) is allowed but always bills at the highest SKU and is discouraged in production. ([Choose fields](https://developers.google.com/maps/documentation/places/web-service/choose-fields))

## 1.4 Example request / response (Text Search New)

```http
POST https://places.googleapis.com/v1/places:searchText
Content-Type: application/json
X-Goog-Api-Key: YOUR_KEY
X-Goog-FieldMask: places.id,places.displayName,places.types,places.rating,
  places.userRatingCount,places.priceLevel,places.websiteUri,
  places.nationalPhoneNumber,places.formattedAddress,places.location,nextPageToken

{
  "textQuery": "med spa",
  "includedType": "spa",
  "locationBias": {
    "circle": { "center": { "latitude": 34.0901, "longitude": -118.4065 },
                "radius": 5000.0 }
  },
  "pageSize": 20
}
```

```json
{
  "places": [
    {
      "id": "ChIJ...",
      "displayName": { "text": "Sunset Glow Med Spa", "languageCode": "en" },
      "types": ["spa", "beauty_salon", "point_of_interest"],
      "rating": 4.8,
      "userRatingCount": 214,
      "priceLevel": "PRICE_LEVEL_MODERATE",
      "nationalPhoneNumber": "(310) 555-0199",
      "formattedAddress": "123 Sunset Blvd, Los Angeles, CA 90210, USA",
      "location": { "latitude": 34.0905, "longitude": -118.405 }
      // NOTE: no "websiteUri" key present → candidate "no website"
    }
  ],
  "nextPageToken": "AeJ..."
}
```
(`websiteUri` simply **omitted** when Google has no website on file — that absence is your signal.)

## 1.5 Pagination & result caps

- **`pageSize`**: 1–20; default and max **20 results per page**.
- **`nextPageToken`**: returned when more results exist; pass it back in the next request body to get the next page.
- **Hard cap: 60 results total** (3 pages × 20) for Text Search and Nearby Search (New). There is no way to page past 60 for a single query. ([Text Search New](https://developers.google.com/maps/documentation/places/web-service/text-search))

This 60-cap is the single biggest coverage constraint and drives the multi-query strategy in §2.

## 1.6 Pricing, SKU tiers, free credit (current, post-2025-03-01)

Google reorganized into **Essentials / Pro / Enterprise** SKUs on 2025-03-01, replacing the old pooled **$200/month credit** with **per-SKU free monthly caps**: **10,000 Essentials, 5,000 Pro, 1,000 Enterprise** events/month. ([March 2025 changes](https://developers.google.com/maps/billing-and-pricing/march-2025), [Usage and billing](https://developers.google.com/maps/documentation/places/web-service/usage-and-billing))

| Endpoint / SKU | Price per 1,000 requests | Free monthly cap |
|---|---|---|
| **Place Details** – Essentials (ID only) | ~$5 | 10,000 |
| **Place Details** – Pro | **$17** | 5,000 |
| **Place Details** – Enterprise | **$20** | 1,000 |
| **Text Search** – Pro (≈ legacy "Basic") | **~$32** | 5,000 |
| **Text Search** – Enterprise (≈ legacy "Advanced/Preferred") | **~$35–$40** | 1,000 |
| **Nearby Search** – Pro / Enterprise | **~$32 / ~$35–40** | 5,000 / 1,000 |
| **Geocoding** (Essentials) | **$5** | 10,000 |
| **Place Photo** (media) | Pro/Enterprise tier ($17–$20-equivalent) | per tier |

Place Details numbers ($5 / $17 / $20) are confirmed. ([woosmap 2026 breakdown](https://www.woosmap.com/blog/google-maps-api-pricing-breakdown)) Text/Nearby Search at the rich tier historically priced **Basic $32 / Advanced $35 / Preferred $40 per 1,000** (the New API maps these onto Pro/Enterprise). ([safegraph guide](https://www.safegraph.com/guides/google-places-api-pricing/), [nicolalazzari SKU breakdown](https://nicolalazzari.ai/articles/understanding-google-maps-apis-a-comprehensive-guide-to-uses-and-costs)) Google's overall range is **$2–$40 per 1,000** depending on SKU/tier/volume. Volume discounts apply automatically above set thresholds. ([pricing overview](https://developers.google.com/maps/billing-and-pricing/overview))

Subscription alternatives exist (e.g. Starter ~$100/mo for 50K events, etc.) but pay-as-you-go is right until volume is high. ([Maps Platform pricing](https://mapsplatform.google.com/pricing/))

### Rate limits
Default quotas are high — historically **on the order of hundreds of QPS per API** (e.g., ~600 requests/min default for Places, raisable on request). Plan for per-minute QPS limits and backoff on `429`; request quota increases in Cloud Console for batch scans.

## 1.7 Cost estimate: scanning one ZIP code

Assume **one ZIP, 10 business categories**, each category run as one Text Search with full pagination (worst case 3 pages = 60 results), then Place Details on net unique candidates.

| Step | Calls | SKU | Unit | Subtotal |
|---|---|---|---|---|
| Geocode ZIP → lat/lng | 1 | Essentials | $5/1K | $0.005 |
| Text Search (10 categories × up to 3 pages) | 30 | Enterprise (rating+website in mask) | ~$35/1K | ~$1.05 |
| Place Details refresh on unique candidates (~150) | 150 | Enterprise | $20/1K | $3.00 |
| **Total per ZIP (worst case)** | | | | **≈ $4.05** |

In practice you can often skip per-candidate Place Details because **Text/Nearby Search already returns `rating`, `userRatingCount`, `websiteUri`, and phone** in the same Enterprise-tier response — collapsing the cost to roughly the search calls only (**~$1.05/ZIP**, plus geocode). Use Place Details only to refresh stale records or pull fields not in the search response (e.g., full hours).

**Free tier covers it for development:** at 1,000 free Enterprise events/month you can scan a handful of ZIPs/month for $0. At production scale (thousands of ZIPs) budget ~$1–4 per ZIP and request volume discounts.

---

# 2. Searching by ZIP / area

## 2.1 Recommended approach: geocode → circle bias, with text queries per category

**Best practice = hybrid.** Geocode the ZIP to a lat/lng centroid, then run **Text Search (New)** with:
- `textQuery` = the category term (e.g. `"med spa"`, `"barber shop"`, `"dentist"`)
- `includedType` = the matching Places type to tighten results
- `locationBias` (soft) or `locationRestriction` (hard) = a **circle** around the centroid

Pure text search like `"med spas in 90210"` works but is less controllable than `textQuery` + explicit circle. ZIP centroids vary in real-world radius, so derive radius from the ZIP's geographic extent (or use a fixed 2–8 km and tile, see §2.3).

- Geocode via the **Geocoding API** (`$5/1K`, Essentials) or a free ZIP-centroid table (Census ZCTA gazetteer) to avoid even that cost.

## 2.2 Enumerating multiple categories

There is no "all businesses in this area" call — you must **iterate categories**. Maintain a curated list of target Places **types** / query terms, e.g.:
`restaurant, cafe, bar, hair_salon, beauty_salon, spa, barber_shop, dentist, plumber, electrician, lawyer, accounting, gym, pet_store, florist, bakery, car_repair, real_estate_agency, roofing_contractor, painter`.

For each type, run a Text Search (or Nearby Search with `includedTypes`). Deduplicate across categories by `place_id`. Nearby Search (New) accepts **`includedTypes` / `excludedTypes`** arrays and a `maxResultCount`, useful for type-driven sweeps; Text Search is better when you want a natural-language term. ([Nearby Search New](https://developers.google.com/maps/documentation/places/web-service/nearby-search))

## 2.3 Beating the 60-result cap (comprehensive coverage)

Because each query caps at 60 results, dense categories in dense ZIPs will be truncated. Strategies:

1. **Grid tiling:** Cover the ZIP with overlapping smaller circles (e.g. 500m–1km radius cells), run each category per cell, dedupe by `place_id`. This multiplies calls but captures everything.
2. **Category granularity:** Split broad terms into narrower ones (`"italian restaurant"`, `"sushi"`, `"taco"` instead of `"restaurant"`) to surface different result sets under the cap.
3. **`rankPreference`:** `DISTANCE` vs `RELEVANCE` returns different orderings — combining both passes increases unique coverage.
4. **Dedup key:** always `place_id` (stable, ToS-storable).

Trade-off: tiling improves recall but increases Enterprise-tier call volume linearly — budget accordingly.

---

# 3. Detecting "no website" reliably & enriching

A two-pass classifier on top of `websiteUri`:

## 3.1 Pass 1 — field presence + URL classification
- **No `websiteUri`** → strong candidate.
- **`websiteUri` present** → classify the registrable domain (eTLD+1), stripping UTM params (Google often appends `?utm_source=gmb`):
  - **Social → not a real site:** facebook.com, m.facebook.com, fb.me, instagram.com, tiktok.com, x.com/twitter.com, linkedin.com, youtube.com, pinterest.com, nextdoor.com
  - **Link-in-bio → not a real site:** linktr.ee, beacons.ai, bio.link, lnk.bio, campsite.bio (carrd.co is a judgment call — can be a real one-pager)
  - **Directory/booking portals → not their site:** yelp.com, tripadvisor.com, opentable.com, doordash.com, ubereats.com, grubhub.com, vagaro.com, booksy.com, square.site booking pages, toasttab.com, chownow.com, yellowpages-style domains
  - **Google/builder placeholders → flag (often dead):** `*.business.site` (**Google retired these ~March 2024 — frequently dead** ([SEJ](https://www.searchenginejournal.com/website-google-business-profile/444816/))), `sites.google.com`; builder defaults `*.wixsite.com`, `*.godaddysites.com`, `*.weebly.com`, `*.wordpress.com` → "probe and decide"

## 3.2 Pass 2 — lightweight HTTP verification
For URLs that survive Pass 1:
- **HEAD, fall back to GET** (small hosts mishandle HEAD); 3–5s timeout; follow redirects (cap ~5); browser User-Agent.
- **Check where redirects land** — a domain that 301s to Facebook = not a real site.
- **Status/content:** 200 + real HTML = real; 4xx/5xx, NXDOMAIN, parked-page markers, or `business.site` 404 = not real.
- **TLS errors / no HTTPS:** weak negative, not a hard reject (many tiny legit sites mis-handle TLS).

**False positives** (you flag "no site" but they have one): Google lacks the URL; site temporarily down; bot-blocked. Mitigate with an optional confirmation search using a **licensed Programmable/Custom Search API** (never scrape Google SERPs). **False negatives** (you flag "has site" but it's fake): caught by Pass 1 + redirect/parked-page checks.

## 3.3 GBP "claimed vs unclaimed" as a ripeness signal
Unclaimed listing = owner not engaged = better prospect — **but this is NOT exposed by the public Places API (New)**. There is no claimed/verified boolean. The Business Profile (ex-GMB) verification APIs *do* model ownership state, but they are **owner/partner-scoped** (for locations you manage), not for auditing arbitrary businesses. ([GBP verification](https://developers.google.com/my-business/content/manage-verification)) Use **completeness proxies** instead: missing website + missing hours + few/no photos + no owner replies to reviews → likely unclaimed/disengaged.

---

# 4. Alternative / supplementary data sources

The source with the best reviews (Yelp) is the *worst* for the website signal; the sources with the best website field (Foursquare OS Places, OSM) have weak/no reviews. → **multi-source join.**

## 4.1 Cost

| Source | Free tier | Paid cost | Storable? |
|---|---|---|---|
| **Google Places (New)** | Per-SKU caps (1K Enterprise/mo) | ~$20–40/1K (Enterprise) | **Only `place_id`** (rest: 30-day cache) |
| Yelp Fusion | 30-day trial, ~5K calls | ~$7.99–$14.99/1K; ~$229+/mo | **No** (24h; IDs only) |
| Foursquare Places API (hosted) | ~$200/mo credit (→ 500 Pro calls from Jun 2026) | PAYG; Premium ~$18.75/1K | Per ToS |
| **Foursquare OS Places** | **Fully free** | $0 | **Yes (Apache 2.0)** |
| OpenStreetMap / Overpass | Free | $0 (self-host infra) | Yes (ODbL share-alike) |
| data.gov business licenses | Free | $0 | Yes (varies) |
| Census ACS API | Free (500/day no key) | $0 | Yes (public domain) |

## 4.2 Coverage & key fields

| Source | Rating/reviews | Business website field | Coords/phone | US small-biz coverage |
|---|---|---|---|---|
| Google Places (New) | **Excellent** | **Yes** (`websiteUri`) | Yes | **Best** |
| Yelp Fusion | **Excellent** | **NO** (only Yelp page `url`) | Yes | Strong |
| Foursquare hosted | Yes (rating) | **Yes** | Yes | Strong (100M+) |
| Foursquare OS Places | No | **Yes** | Yes | Strong (100M+) |
| OpenStreetMap | No | `website`/`contact:website` (sparse) | Yes | Uneven (urban good) |
| data.gov licenses | No | Rarely | Address (often no coords) | City-by-city, patchy |
| Census ACS | N/A (demographics) | N/A | ZCTA-level | Full US |

## 4.3 ToS / licensing

| Source | License/ToS | Commercial redistribution |
|---|---|---|
| Google Places | Restrictive; only `place_id` durable; 30-day cache; attribution; **no telemarketing/listings DB** | No |
| Yelp | Restrictive; **24h cache**, attribution required | No |
| Foursquare hosted | Commercial API ToS | Per contract |
| **Foursquare OS Places** | **Apache 2.0** | **Yes, w/ attribution** |
| OpenStreetMap | **ODbL** | Yes, but **share-alike** on derived DBs |
| data.gov | Mostly open/public domain (varies) | Usually yes |
| Census ACS | Public domain | Yes |

### Source notes
- **Yelp Fusion** — `GET /v3/businesses/search` returns rating, review_count, categories, price, coordinates, phone, but **only a Yelp profile `url`, never the business's own website** — so it cannot detect "no website." Up to 240 results/query (`limit≤50` + `offset`); excludes zero-review businesses. **24-hour cache limit** (IDs storable indefinitely), mandatory attribution. Pricing: ~$7.99–$14.99/1K, ~$229+/mo entry, 30-day/~5K-call trial. ([Business Search](https://docs.developer.yelp.com/reference/v3_business_search), [pricing](https://business.yelp.com/data/resources/pricing/), [API terms](https://terms.yelp.com/developers/api_terms/20250113_en_us/))
- **Foursquare OS Places** (Apache 2.0, released Nov 2024) — **free, permanently storable, 100M+ POIs, includes a real `website` field** + tel/email/socials/coords/categories. **No ratings.** Ideal POI+website backbone. ([FSQ OS Places](https://foursquare.com/resources/blog/products/foursquare-open-source-places-a-new-foundational-dataset-for-the-geospatial-community/), [schema](https://docs.foursquare.com/data-products/docs/places-os-data-schema))
- **OpenStreetMap/Overpass** — free; query by area in Overpass QL; website in `website=*`/`contact:website=*`; **ODbL share-alike** if you redistribute a derived DB; coverage uneven; `website` tag inconsistently populated (missing tag may = "no site" OR "not mapped"). Self-host for production (public endpoint ~10K req/day fair-use). ([Overpass QL](https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL))
- **data.gov municipal licenses** — per-city, patchy, rarely has website/reviews; useful only as an "is it legally operating" cross-check (e.g., Chicago, NYC, San Diego portals).

## 4.4 Recommended stack

- **Primary discovery + website signal + reviews:** **Google Places API (New)** — it uniquely gives rating, userRatingCount, AND `websiteUri` in one call, with the best US coverage. This is the core engine.
- **Cost-reduction backbone (optional):** **Foursquare OS Places** (free, storable, has `website`) to pre-filter candidates and reduce paid Google Enterprise calls; confirm/enrich website-absence with **OSM**.
- **Supplementary review cross-check:** **Yelp Fusion** live (store IDs only, never >24h; show attribution).
- **Pricing multiplier:** **Census ACS** (see §5).
- **Net flow:** FSQ OS Places (`website` null) → confirm with OSM → verify + enrich live via **Google Places** → score quality → apply Census price multiplier.

---

# 5. Demographics for pricing (Census ACS by ZIP/ZCTA)

Use the **ACS 5-year** dataset (full ZCTA coverage) to drive geographic price multipliers.

**Endpoint:**
```
https://api.census.gov/data/2022/acs/acs5?get=NAME,B19013_001E,B19301_001E&for=zip%20code%20tabulation%20area:90210&key=YOUR_KEY
```
- **`B19013_001E`** = **median household income** ($) — primary multiplier.
- **`B19301_001E`** = **per capita income** ($) — secondary signal.
- Geography: `for=zip code tabulation area:90210` (or `:*` for all, comma-list for several).

**Response shape** (JSON 2-D array; first row = headers):
```json
[["NAME","B19013_001E","B19301_001E","zip code tabulation area"],
 ["ZCTA5 90210","130769","112345","90210"]]
```

**Key & cost:** **Free.** Up to **500 queries/day without a key**; beyond that a free instant API key is required. Up to 50 variables per call. Public domain — store freely. **Best practice: bulk-pull all ~33K ZCTAs once and cache locally** (updates annually). ([ACS 5-year](https://www.census.gov/data/developers/data-sets/acs-5year.html), [B19013 variable](https://api.census.gov/data/2020/acs/acs5/variables/B19013_001E.html), [key signup](https://api.census.gov/data/key_signup.html))

> Caveat: ZCTAs approximate, but don't exactly equal, USPS ZIP codes — fine for pricing tiers, not for exact mail routing.

**Multiplier example:** map median household income to a price band, e.g. `<$50K → 0.8×`, `$50–90K → 1.0×`, `$90–130K → 1.3×`, `>$130K → 1.6×` on a base website package price.

---

# 6. AI website generation approach

## 6.1 Architecture: structured content → fixed template system (NOT free-form HTML)

**Have Claude emit schema-validated JSON; render it through a hand-designed React/Next.js component system governed by design tokens. Never ask the LLM for raw HTML/CSS.**

| Concern | Free-form HTML | Structured JSON → fixed templates |
|---|---|---|
| Visual quality | Varies each run | Designer-built, always intentional |
| Consistency | Drifts run-to-run | Deterministic |
| A11y / SEO / responsive | LLM re-derives each time | Baked into components once |
| Validation | Hard | JSON Schema catches errors pre-render |
| Regeneration | Re-rolls whole design | Re-prompt one field |
| Token cost | High (verbose markup) | Low (copy only) |
| Security | Model HTML = XSS surface | Content is escaped data |

LLM = **content engine**; template system = **presentation engine**.

## 6.2 Constraining Claude to valid JSON

The Claude API supports **structured outputs** constraining the response to a JSON Schema (`output_config.format`), with `client.messages.parse()` returning a typed object validated against a Pydantic/Zod model. ([structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs), [tool use overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview))

```python
class Service(BaseModel):
    title: str
    description: str
class SiteContent(BaseModel):
    hero_headline: str
    hero_subtext: str
    about_copy: str
    services: list[Service]
    why_choose_us: list[str]
    review_summary: str
    meta_title: str
    meta_description: str
    primary_cta: str

resp = client.messages.parse(
    model="claude-sonnet-4-6",
    max_tokens=4000,
    output_config={"format": SiteContent},
    messages=[{"role": "user", "content": prompt_with_places_data}],
)
content = resp.parsed_output
```
Schema supports `enum`/`anyOf`/`$ref`/`additionalProperties:false`; **not** `minLength`/`maxLength`/numeric bounds — enforce lengths in the prompt + validate client-side. Incompatible with citations/prefilling.

The render layer is a normal Next.js app: `<Hero>`, `<Services>`, `<About>`, `<Reviews>`, `<Contact>` components taking the JSON as props, plus a **design-token layer** (CSS vars / Tailwind theme) chosen per category.

## 6.3 Content generation from Places data + reviews
- Give Claude **category + locale explicitly** ("family-owned Italian restaurant in Austin, TX") and the literal facts (hours, services, address).
- **Ground every claim in the input** — never invent awards, years in business, guarantees. Most important instruction for trust.
- **Review summarization:** pass 5–15 snippets → a 1–2 sentence "what customers love" blurb + 3–5 `why_choose_us` bullets from recurring themes. Paraphrase; never fabricate or attribute named quotes.
- **SEO:** `meta_title`/`meta_description` with category + city; `primary_cta` matched to vertical ("View the menu" / "Get a free quote").
- Single-shot `messages.parse` — no agent loop needed.

## 6.4 Claude model choice + token cost (per Anthropic docs, June 2026)

| Model | API ID | Input $/MTok | Output $/MTok |
|---|---|---:|---:|
| Claude Opus 4.8 | `claude-opus-4-8` | $5.00 | $25.00 |
| **Claude Sonnet 4.6** | `claude-sonnet-4-6` | $3.00 | $15.00 |
| Claude Haiku 4.5 | `claude-haiku-4-5` | $1.00 | $5.00 |

([Models overview](https://platform.claude.com/docs/en/about-claude/models/overview), [Pricing](https://platform.claude.com/docs/en/about-claude/pricing))

**Per-site cost** (≈3,500 input / 1,800 output tokens for full `SiteContent`):

| Model | Total per site |
|---|---:|
| Haiku 4.5 | ≈ **$0.013** |
| **Sonnet 4.6** | ≈ **$0.038** |
| Opus 4.8 | ≈ **$0.063** |

Two variants + a couple of section regenerations stays under **~$0.15/site** on Sonnet. Cut further with **prompt caching** (stable system prompt + schema) and the **Batch API** (50% off). **Recommendation: Sonnet 4.6 default, Opus 4.8 premium tier, Haiku 4.5 for cheap single-section regenerations.**

## 6.5 Image strategy

| | Unsplash API | Pexels API |
|---|---|---|
| Free limit | 50 req/hr demo; 5,000 req/hr prod | 200 req/hr + 20K/mo; liftable to unlimited |
| Commercial use | Yes | Yes |
| **API attribution** | **Required** (credit + hotlink + download event) | **Not required** |

([Unsplash docs](https://unsplash.com/documentation), [Unsplash attribution](https://help.unsplash.com/en/articles/2511315-guideline-attribution), [Pexels docs](https://www.pexels.com/api/documentation/))

**Pexels-first (no attribution, cleaner for white-label), Unsplash fallback.** Map **category → curated stock search queries** for consistency; **prefer the business's own Places photos** for hero/gallery. AI generation (Flux 2 Pro ~$0.03/image, DALL·E 3 $0.04–$0.12) only for abstract backgrounds or thin-coverage niches — stock is better for photorealistic storefront/food/people. ([AI image pricing](https://tokenmix.ai/blog/flux-kontext-image-api))

## 6.6 Rendering & hosting

| Option | Pros | Cons | Cost |
|---|---|---|---|
| Next.js static export per site | Cheapest to serve, fast, secure, SEO | Rebuild on edit | ~free → low |
| **DB-backed dynamic render** | Instant edits, one codebase, easy A/B | Needs server + DB | scales w/ traffic |
| **Subdomain-per-business** (`biz.tool.com`) | One deploy = unlimited tenants, instant provisioning | Wildcard DNS + SSL | marginal/tenant |
| Custom domain per business | Best brand/SEO | Per-domain certs | per-domain |

**Recommended production shape: single multi-tenant Next.js app, DB-backed (ISR), wildcard subdomain, optional custom-domain upgrade.** Vercel "for Platforms" supports wildcard multi-tenancy with on-the-fly per-subdomain SSL (**Pro $20/seat/mo — Hobby is non-commercial only**); **Netlify free tier permits commercial use, Pro $20/team**. Dominant cost at scale is bandwidth/build, not per-site — a few $/mo covers many low-traffic local sites. ([Vercel multi-tenant](https://vercel.com/docs/multi-tenant/domain-management), [Netlify pricing](https://www.netlify.com/pricing/))

## 6.7 Two variants + regeneration from feedback
- **Generate content once** → render the **same JSON through two token themes** (e.g. warm/editorial vs clean/modern: `{colors, fonts, radius, spacing, heroLayout, sectionOrder}`). Two genuinely different looks, **zero extra LLM cost** for the design axis. Optional cheap Haiku pass for an alternate headline register.
- **Feedback maps narrowly:** "punchier hero" → re-prompt that single field (~$0.001–0.01); "different colors/font" → swap token bundle (no LLM); "reorder/remove reviews" → change `sectionOrder` (no LLM). DB-backed render makes edits live with no rebuild.

---

# 7. Legal / ToS & rate-limit guardrails

## 7.1 Google Maps Platform Terms
- **Store only `place_id` long-term.** `place_id` is **explicitly exempt** from caching restrictions and may be stored **indefinitely** — make it your durable DB key. ([Places policies](https://developers.google.com/maps/documentation/places/web-service/policies), [Place IDs](https://developers.google.com/maps/documentation/places/web-service/place-id))
- **All other Places content:** general no-caching rule with a **limited ~30-day temporary cache**, after which it must be deleted. Don't warehouse `displayName`, address, `websiteUri`, phone, ratings permanently — refresh.
- **No scraping**: persisting Content for use outside the user session is prohibited.
- **No competing/substitute DB**: you **may not** use Maps content to build a "business listings database, mailing list, or **telemarketing list**." **This is the single most material clause for this product** — do not materialize a permanent Google-derived prospect/call list. Use Places for live discovery, store only `place_id`, and source any contact list you act on through compliant channels. ([Maps ToS §3.2.4](https://developers.google.com/maps/terms-20180207))
- **Attribution**: display all Google-provided attributions/notices (e.g., "Powered by Google", third-party review attributions) wherever you show Places data; don't obscure them.

## 7.2 Cold outreach (TCPA / DNC / CAN-SPAM) — high level, not legal advice
- **Lowest risk:** live, manually-dialed calls to a **business landline** — generally no TCPA prior consent needed.
- **High risk:** **autodialed/prerecorded/AI-voice calls or texts to mobile numbers require prior express consent** — including B2B. Many Places "phone numbers" are owner cell phones → mobile/TCPA territory. The FCC's **Feb 8, 2024 ruling** confirms **AI-generated voices are "artificial"** under the TCPA, so an AI voice dialer almost certainly needs consent. ([FCC AI-voice ruling](https://www.fcc.gov/document/fcc-confirms-tcpa-applies-ai-technologies-generate-human-voices))
- **SMS:** treated like calls; automated marketing texts to mobiles need consent. Cold B2B SMS = high risk.
- **DNC Registry (FTC TSR):** aimed at consumers; genuine B2B calls to business lines generally exempt, but **sole proprietors / home-based / owner-cell numbers can be treated as residential** — scrub lists against a DNC version ≤31 days old and honor internal do-not-call requests. Watch stricter **state mini-TCPA** laws (FL, OK, WA).
- **CAN-SPAM (cold email):** **no B2B exemption.** Requirements: truthful headers/subject, identify as ad, valid **physical postal address**, working **opt-out** honored within **10 business days** (mechanism live ≥30 days), and you're liable for vendors acting on your behalf. ([FTC CAN-SPAM guide](https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business))

**Practical guardrails:** prefer live calls to verified business landlines; treat mobile/AI-voice/prerecorded/SMS as consent-required; for email, be CAN-SPAM-compliant with a suppression list; and never persist Google data into a permanent telemarketing/mailing list.

---

# 8. Recommended implementation summary

1. **Discovery:** Google Places API (New) — geocode ZIP → circle-biased Text/Nearby Search per category, dedupe by `place_id`, beat the 60-cap with grid tiling + category granularity. Pull `rating`, `userRatingCount`, `websiteUri`, phone in the same Enterprise-tier search response to avoid extra Place Details calls. ~$1–4/ZIP.
2. **No-website classifier:** `websiteUri` absence → candidate; classify present URLs (social/link-in-bio/directory/`business.site`); HTTP-probe survivors (HEAD→GET, redirect-target + parked-page checks).
3. **Quality + pricing:** filter by rating/review count; multiply price by Census ACS median-income band per ZCTA (free, cached).
4. **Generation:** Claude (Sonnet 4.6, ~$0.04/site) → schema-validated JSON → fixed React/Next token-driven components; two variants via two token themes; Pexels-first imagery + business's own photos.
5. **Hosting:** DB-backed multi-tenant Next.js on wildcard subdomain (`biz.tool.com`), instant provisioning, cents per site.
6. **Guardrails:** store only `place_id` durably; respect 30-day cache + attribution + no-telemarketing-DB; B2B outreach via compliant channels (landline live calls / CAN-SPAM email).

---

## Sources

**Google Places API (New) & Maps Platform**
- Text Search (New) — https://developers.google.com/maps/documentation/places/web-service/text-search
- Nearby Search (New) — https://developers.google.com/maps/documentation/places/web-service/nearby-search
- Place Details (New) — https://developers.google.com/maps/documentation/places/web-service/place-details
- Place Data Fields (New) — https://developers.google.com/maps/documentation/places/web-service/data-fields
- Choose fields / field masks — https://developers.google.com/maps/documentation/places/web-service/choose-fields
- Usage and billing — https://developers.google.com/maps/documentation/places/web-service/usage-and-billing
- March 2025 pricing changes — https://developers.google.com/maps/billing-and-pricing/march-2025
- Pricing overview — https://developers.google.com/maps/billing-and-pricing/overview
- Maps Platform pricing — https://mapsplatform.google.com/pricing/
- Places policies (caching, attribution) — https://developers.google.com/maps/documentation/places/web-service/policies
- Place IDs — https://developers.google.com/maps/documentation/places/web-service/place-id
- Maps ToS (no telemarketing DB) — https://developers.google.com/maps/terms-20180207
- GBP social links — https://support.google.com/business/answer/13580646?hl=en
- GBP verification API — https://developers.google.com/my-business/content/manage-verification
- woosmap pricing breakdown — https://www.woosmap.com/blog/google-maps-api-pricing-breakdown
- safegraph Places pricing — https://www.safegraph.com/guides/google-places-api-pricing/
- nicolalazzari SKU/$ breakdown — https://nicolalazzari.ai/articles/understanding-google-maps-apis-a-comprehensive-guide-to-uses-and-costs
- business.site retirement — https://www.searchenginejournal.com/website-google-business-profile/444816/

**Alternative data sources**
- Yelp Business Search — https://docs.developer.yelp.com/reference/v3_business_search
- Yelp pricing — https://business.yelp.com/data/resources/pricing/
- Yelp API terms — https://terms.yelp.com/developers/api_terms/20250113_en_us/
- Foursquare OS Places — https://foursquare.com/resources/blog/products/foursquare-open-source-places-a-new-foundational-dataset-for-the-geospatial-community/
- FSQ OS data schema — https://docs.foursquare.com/data-products/docs/places-os-data-schema
- Foursquare pricing — https://foursquare.com/pricing/
- Overpass QL — https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL
- data.gov catalog — https://catalog.data.gov/

**Census ACS**
- ACS 5-year datasets — https://www.census.gov/data/developers/data-sets/acs-5year.html
- B19013_001E variable — https://api.census.gov/data/2020/acs/acs5/variables/B19013_001E.html
- Census API key signup — https://api.census.gov/data/key_signup.html

**AI generation**
- Claude structured outputs — https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- Claude tool use overview — https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview
- Claude models overview — https://platform.claude.com/docs/en/about-claude/models/overview
- Claude pricing — https://platform.claude.com/docs/en/about-claude/pricing
- Unsplash API docs — https://unsplash.com/documentation
- Unsplash attribution — https://help.unsplash.com/en/articles/2511315-guideline-attribution
- Pexels API docs — https://www.pexels.com/api/documentation/
- AI image pricing — https://tokenmix.ai/blog/flux-kontext-image-api
- Vercel multi-tenant — https://vercel.com/docs/multi-tenant/domain-management
- Netlify pricing — https://www.netlify.com/pricing/

**Legal / outreach**
- FCC AI-voice TCPA ruling — https://www.fcc.gov/document/fcc-confirms-tcpa-applies-ai-technologies-generate-human-voices
- FTC CAN-SPAM guide — https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business
