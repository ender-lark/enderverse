# Plan 08 — Build Roadmap

> Phased, ordered, concrete tasks. Each phase ends in a working, demoable state. **Build mock-first**: every external call has a mock so the whole product is demoable before any API key exists. Check off as you go.

## Phase 0 — Scaffold & foundations (½–1 day)
- [ ] `create-next-app` (TypeScript, App Router, Tailwind, ESLint) inside `small-biz-website-builder/app/` (or convert the provided scaffold).
- [ ] Add deps: `prisma @prisma/client zod @anthropic-ai/sdk`, shadcn/ui, `@supabase/supabase-js`.
- [ ] `.env.example` + env loader; `MOCK_MODE=true` default. Keys: `GOOGLE_MAPS_API_KEY`, `CENSUS_API_KEY`, `ANTHROPIC_API_KEY`, `PEXELS_API_KEY`, `DATABASE_URL`, `APP_PASSWORD`.
- [ ] Prisma schema from `docs/plan/02-data-model.md`; `prisma migrate dev`; `seed.ts` with mock prospects + one example pitch + one example site.
- [ ] Auth middleware (shared password or Supabase magic-link) gating operator routes.
- [ ] CI: typecheck + lint + `prisma validate` (a `SessionStart` hook can ensure these run in web sessions).

## Phase 1 — Prospect engine, mock-first (2–3 days)
- [ ] `lib/categories.ts` — raw Places types → vertical keys + per-vertical config (tier, industry multiplier, avg ticket, default theme, section order, monthly-searchers seed).
- [ ] `lib/adapters/places.ts` + `mock` — Text Search by category w/ field mask; fixtures for ~3 ZIPs.
- [ ] `lib/adapters/geocode.ts`, `lib/adapters/census.ts` (+ mocks).
- [ ] `lib/classifier.ts` — no-website URL classification + HTTP probe.
- [ ] `lib/prospectEngine.ts` — scan → classify → filter → enrich → **score (0–100)** → **price (WTP)** → competitor finder → ROI. Unit-test scoring + pricing against Research 02 worked examples.
- [ ] `POST /api/search`, `GET /api/search/:id`, `GET /api/prospects`, `GET /api/prospects/:id`.
- [ ] Screens `/` and `/prospects` and `/prospect/:id` with score badge, breakdown, competitor, ROI, pricing.
- ✅ **Milestone:** type a ZIP (mock) → ranked website-less prospects with scores + prices + competitor + ROI.

## Phase 2 — Pitch generator (1–2 days)
- [ ] `lib/adapters/llm.ts` (+ mock) — Anthropic structured outputs (schema-validated, retry).
- [ ] `lib/pitchGenerator.ts` — precompute ROI/price in code, one LLM call fills language → `Pitch`.
- [ ] `POST /api/prospects/:id/pitch`; screen `/prospect/:id/pitch` (Zone A/B/C, copy buttons, PDF export).
- [ ] Mock returns the Lumière template.
- ✅ **Milestone:** one-click pitch one-pager a non-marketer can read aloud.

## Phase 3 — Website generator (3–5 days, the quality core)
- [ ] `lib/themes/` — the 4 theme token bundles (Warm Boutique, Luxe Dark, Modern Clean, Bold Field) + `industryThemeMap.ts` + WCAG-AA contrast test.
- [ ] `lib/site-blocks/` — the section component library (Header, Hero ×variants, TrustStrip, Services, About, BeforeAfter, Testimonials, Gallery, Pricing, BookingCta, Faq, Map, Footer), all theme-aware, responsive, accessible.
- [ ] `lib/siteGenerator.ts` — content LLM call → `SiteContent` JSON (schema) → compose per industry section order → render; **one content JSON → two themes** = two options; image resolution via `lib/adapters/images.ts` (Pexels + Places photos, dedupe).
- [ ] QA pass: contrast + section completeness + copy-length sanity → `qaFlags`.
- [ ] `POST /api/prospects/:id/site`, `/regenerate`, `/tweak`, `PATCH /api/sites/:id`; public `GET /s/:slug`.
- [ ] Screens `/prospect/:id/sites` (two options, regenerate, theme switch, tweak chips + free-text, section controls) and the public render.
- ✅ **Milestone:** two visibly distinct, award-quality sites per business + regenerate + guided tweaks.

## Phase 4 — Pipeline, polish, publish/export (1–2 days)
- [ ] `/pipeline` light board; `PATCH /api/prospects/:id` status/notes.
- [ ] Publish (shareable `/s/:slug`) + static export to Supabase Storage.
- [ ] Cost guardrails: per-scan cost estimate, monthly cap, `PlacesCache`, retention cron.
- [ ] Empty/loading/error states; mobile pass; "capped results" notices.

## Phase 5 — Go live with real APIs (½–1 day)
- [ ] Provision Google Cloud (Places New + Geocoding), Census key, Anthropic, Pexels, Supabase prod.
- [ ] Flip `MOCK_MODE=false` in Vercel; smoke-test one real ZIP; confirm cost/scan.
- [ ] Verify ToS guardrails (placeId-only retention, attribution, 30-day refresh) and outreach guardrails are documented in-app.
- [ ] Deploy to Vercel; hand the URL + password to the 1–2 users.

## Testing strategy (throughout)
- Unit: scoring, pricing, classifier, category mapping, theme contrast.
- Schema: every LLM output validated; retry-on-mismatch covered.
- E2E (Playwright, Chromium preinstalled): zip→prospects→pitch→two sites→publish, in mock mode (free, deterministic).
- Visual: snapshot the 4 themes × a few industries to guard the quality bar.

## Rough estimate
~9–14 focused days to a polished, deployable v1 (mock-first lets most of it be built and demoed before any spend).
