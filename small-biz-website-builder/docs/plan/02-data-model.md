# Plan 02 — Data Model

> Postgres (Supabase) via Prisma. Stores the operator's pipeline, prospects, generated pitches and sites, plus cached lookups. **ToS:** only `placeId` is retained indefinitely; other Places-derived fields are cache with `placesRefreshedAt` and refreshed/purged on a ~30-day cycle.

## Entities (Prisma-style)

```prisma
model User {                 // the 1–2 operators
  id        String   @id @default(cuid())
  email     String   @unique
  name      String?
  createdAt DateTime @default(now())
  searches  Search[]
  prospects Prospect[]
}

model Search {               // one ZIP scan
  id          String   @id @default(cuid())
  userId      String
  user        User     @relation(fields: [userId], references: [id])
  zip         String
  centerLat   Float
  centerLng   Float
  categories  String[]       // categories scanned
  status      String         // queued | running | done | error
  resultCount Int      @default(0)
  capped      Boolean  @default(false)   // true if 60-result cap hit anywhere (no silent truncation)
  costCents   Int      @default(0)       // estimated API spend for this scan
  createdAt   DateTime @default(now())
  prospects   Prospect[]
}

model Prospect {
  id              String   @id @default(cuid())
  userId          String
  searchId        String
  user            User     @relation(fields: [userId], references: [id])
  search          Search   @relation(fields: [searchId], references: [id])

  // identity (placeId is the only durable Places field)
  placeId         String
  name            String
  category        String          // normalized vertical key (e.g. "med_spa")
  rawTypes        String[]
  phone           String?
  address         String?
  town            String?
  lat             Float?
  lng             Float?

  // cached Places signal (refreshable)
  rating          Float?
  reviewCount     Int?
  priceLevel      Int?
  websiteUri      String?
  websiteStatus   String          // none | social_only | directory_only | placeholder_dead | real
  placesRefreshedAt DateTime?

  // enrichment
  zipMedianIncome Int?
  competitor      Json?           // { name, rank, stars, reviews, hasSite }
  coreKeyword     String?

  // scoring + pricing
  leadScore       Int?            // 0–100
  scoreBreakdown  Json?           // component sub-scores for "why this score"
  recommendedMonthly Int?
  suggestedTier   String?         // starter | growth | pro
  oneTimePrice    Int?
  roi             Json?           // { monthlySearchers, lostPct, avgTicket, revenueAtRisk }

  // pipeline state
  status          String   @default("new")  // new | saved | pitched | built | won | lost
  notes           String?

  createdAt       DateTime @default(now())
  pitch           Pitch?
  sites           Site[]

  @@index([userId, status])
  @@index([placeId])
}

model Pitch {
  id          String   @id @default(cuid())
  prospectId  String   @unique
  prospect    Prospect @relation(fields: [prospectId], references: [id])
  content     Json     // the Pitch artifact (see Plan 04)
  model       String?  // LLM used
  createdAt   DateTime @default(now())
}

model Site {
  id          String   @id @default(cuid())
  prospectId  String
  prospect    Prospect @relation(fields: [prospectId], references: [id])
  slug        String   @unique           // /s/{slug}
  optionLabel String                     // "Option A" / "Option B"
  themeId     String                     // warm-boutique | luxe-dark | modern-clean | bold-field
  content     Json                       // SiteContent (see Plan 05)
  imageRefs   Json                       // resolved stock/Places image URLs + attribution
  status      String   @default("draft") // draft | published | exported
  qaFlags     Json?                      // contrast/completeness checks
  createdAt   DateTime @default(now())
  updatedAt   DateTime @updatedAt

  @@index([prospectId])
}

model ZipDemographics {          // cached ACS pulls (public-domain, safe to keep)
  zip            String   @id
  medianIncome   Int?
  perCapita      Int?
  geoMultiplier  Float?
  fetchedAt      DateTime @default(now())
}

model PlacesCache {             // optional response cache to cut cost / respect rate limits
  cacheKey   String   @id      // hash of (endpoint + params)
  payload    Json
  fetchedAt  DateTime @default(now())
  expiresAt  DateTime
}
```

## Notes
- **Category normalization:** a `lib/categories.ts` map collapses raw Places `types` into our vertical keys (`med_spa`, `dentist`, `hvac`, …) which key the scoring tier, pricing multiplier, theme default, and section order.
- **`scoreBreakdown` / `roi` as JSON** so the UI can show transparent "why" without schema churn.
- **Retention job:** a scheduled task nulls/refreshes Places-derived fields older than ~30 days, keeping `placeId` (ToS compliance).
- **Seed data:** `prisma/seed.ts` loads a handful of mock prospects + a fully-generated example pitch and site so the app is demoable with zero API spend.
