# Plan 01 — System Architecture

> Source: `docs/research/05-tech-data-ai.md`, `00-DECISIONS.md`.

## Stack

- **Frontend + backend:** Next.js (App Router, TypeScript, React Server Components where useful). One app, deployed to **Vercel**.
- **Styling:** Tailwind CSS + a small design-token layer (CSS variables driven by the generated-site themes). shadcn/ui for the operator-facing app chrome.
- **Database:** Postgres via **Supabase**; **Prisma** ORM. Supabase Storage for exported site assets.
- **Secrets:** all external API keys live server-side (Next.js Route Handlers / server actions only). Never shipped to client.
- **External services:** Google Places API (New) + Geocoding; Census ACS; Anthropic (Claude) for generation; Pexels (images). Each behind an adapter with a **mock implementation** toggled by `MOCK_MODE`.

## High-level diagram

```
┌─────────────────────────────────────────── Next.js on Vercel ───────────────────────────────────────────┐
│  Operator UI (React)                          Server (Route Handlers / Server Actions)                     │
│   /            search by zip                    POST /api/search        → ProspectEngine.scan()            │
│   /prospects   ranked results + score           GET  /api/prospects     → list/filter                     │
│   /prospect/:id detail, competitor, ROI         POST /api/prospects/:id/pitch   → PitchGenerator           │
│   /prospect/:id/pitch   the one-pager           POST /api/prospects/:id/site    → SiteGenerator (×2)       │
│   /prospect/:id/sites   2 options + tweaks      POST /api/sites/:id/regenerate, /tweak                     │
│   /s/:slug     PUBLIC generated site render     GET  /s/:slug           → render Site from DB              │
│                                                                                                            │
│  Service layer (lib/)                          Adapters (lib/adapters/, each w/ mock)                      │
│   prospectEngine  scoring/pricing/ROI            places.ts   (Google Places New)                          │
│   pitchGenerator  Pitch artifact                 geocode.ts                                                │
│   siteGenerator   SiteContent + themes           census.ts   (ACS demographics)                           │
│   themes/         token bundles + section map    llm.ts      (Anthropic, structured outputs)              │
│   classifier      no-website detection           images.ts   (Pexels + Places photos)                     │
└───────────────────────────────┬──────────────────────────────────────────────┬───────────────────────────┘
                                 │                                              │
                          Postgres (Supabase) ◀── Prisma                 Supabase Storage (exports)
```

## Request flows

1. **Scan:** UI posts a ZIP → `ProspectEngine.scan()` geocodes, runs per-category Places Text Search (or mock fixtures), classifies website status, filters, enriches (ACS + competitor), scores + prices, persists `Search` + `Prospect[]`, returns ranked list. Long scans run as a background job (status polled) so the UI stays responsive.
2. **Pitch:** `PitchGenerator` precomputes ROI + price in code, then one structured LLM call fills language → `Pitch` persisted + rendered.
3. **Site:** `SiteGenerator` produces **one `SiteContent` JSON** then renders it through **two themes** = two visibly distinct options at zero extra LLM cost; images resolved via Pexels/Places; persisted as two `Site` rows. Regenerate/tweak operate on the structured model.
4. **Public render:** `/s/:slug` renders a published `Site` from the DB (the shareable preview link).

## Background jobs / async

- ZIP scans and site generation can exceed a single request budget → use a job pattern (Vercel background functions or a lightweight queue table polled by the client). `Search.status` / `Site.status` drive UI spinners.
- **Retention job** (cron): refresh/purge Places-derived fields >30 days old (ToS).

## Cost & safety controls

- `MOCK_MODE=true` short-circuits every external adapter with fixtures → full app runs free.
- Per-scan cost estimate written to `Search.costCents`; a configurable monthly spend cap aborts scans past budget.
- `PlacesCache` table dedupes identical lookups within TTL.
- Rate-limit guard around Places (respect QPS); exponential backoff.

## Environments

- **Local:** `.env.local`, `MOCK_MODE=true` by default; Supabase local or a dev project.
- **Preview/Prod:** Vercel env vars hold real keys; `MOCK_MODE=false`. Supabase prod project. One-click deploy from the repo.

## Security

- Light auth gate (Supabase magic-link or a single shared password middleware) on all operator routes; `/s/:slug` is public.
- All keys server-only; CSP headers; input validation (zod) on every route handler.
- No PII beyond public business data; cold-outreach guardrails documented (TCPA/CAN-SPAM) in research 05.
