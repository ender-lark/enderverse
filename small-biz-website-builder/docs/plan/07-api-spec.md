# Plan 07 — API Spec

> Next.js Route Handlers (all server-side; keys never exposed). All inputs validated with zod. JSON in/out. Auth middleware gates everything except `GET /s/:slug`.

## Endpoints

### `POST /api/search`
Start a ZIP scan.
```
req:  { zip: string, categories?: string[], minRating?: number, minReviews?: number }
res:  { searchId: string, status: "queued" }
```
Kicks off `ProspectEngine.scan()` as a background job. Poll with the next endpoint.

### `GET /api/search/:id`
```
res: { id, status: "queued|running|done|error", resultCount, capped, costCents }
```

### `GET /api/prospects?searchId=&status=&sort=score`
```
res: { prospects: ProspectSummary[] }   // id, name, category, rating, reviewCount,
                                        // websiteStatus, leadScore, recommendedMonthly, oneLineWhy
```

### `GET /api/prospects/:id`
```
res: { prospect: ProspectDetail }       // full record incl. scoreBreakdown, competitor, roi, pricing
```

### `PATCH /api/prospects/:id`
Update pipeline state / notes.
```
req: { status?: "new|saved|pitched|built|won|lost", notes?: string }
```

### `POST /api/prospects/:id/pitch`
Generate (or regenerate) the pitch.
```
res: { pitch: Pitch }                   // Plan 04 artifact; ROI/price precomputed in code
```

### `POST /api/prospects/:id/site`
Generate the two website options (one content JSON → two themes).
```
req:  { }                               // defaults from prospect category
res:  { sites: [Site, Site] }           // Option A + Option B, each with slug
```

### `POST /api/sites/:id/regenerate`
```
req: { mode?: "content" | "theme", themeId?: string }
res: { site: Site }
```

### `POST /api/sites/:id/tweak`
Guided tweak (chips or free-text → token overrides + constrained re-prompt).
```
req: { instruction: string }            // e.g. "more premium", "warmer colors", "punchier headline"
res: { site: Site }
```

### `PATCH /api/sites/:id`
Section-level edits (safe operations on the structured model).
```
req: { content?: Partial<SiteContent>, sectionOrder?: string[], hidden?: string[], heroVariant?: string }
res: { site: Site }
```

### `POST /api/sites/:id/publish`  ·  `POST /api/sites/:id/export`
```
publish res: { url: "/s/{slug}" }
export  res: { downloadUrl }            // static bundle in Supabase Storage
```

### `GET /s/:slug`  (public, no auth)
Server-renders the published `Site` from the DB.

## Conventions
- Errors: `{ error: { code, message } }`, proper HTTP status.
- All external spend gated by `MOCK_MODE` and the monthly cost cap (returns `402`-style app error when capped).
- Idempotency: regenerate creates a new version of `content` on the existing `Site` row (or a sibling, configurable); `place_id`-keyed lookups dedupe via `PlacesCache`.
- Rate limiting on `/api/search` and generation endpoints (per user).
