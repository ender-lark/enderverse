# Scaffold status

This is a **starter scaffold**, not a finished app. It gives the next session (Codex or a
fresh Claude Code session) concrete, research-encoded code to build on. Follow
`docs/plan/08-build-roadmap.md` and the `docs/plan/09-handoff-prompt.md` kickoff.

## What's here (ready to build on)
```
package.json            deps + scripts (dev/build/test/db)
.env.example            all env vars; MOCK_MODE=true default (runs free)
tsconfig.json           TS config (Next.js + @/* paths)
prisma/schema.prisma    full DB schema (Plan 02)
lib/
  config.ts             MOCK_MODE toggle, filters, cost guardrail
  categories.ts         ★ the research as data: ~26 verticals w/ tier, pricing mult,
                        customer value, default theme, Places types, section order
  themes.ts             ★ the 4 design-token bundles (Plan 05 / Research 04)
  scoring.ts            ★ leadScore(0–100) + recommendedMonthly(WTP) + roiEstimate (pure, tested)
  scoring.test.ts       validates pricing/scoring vs Research 02 examples (npm test)
  classifier.ts         no-website URL classification (pure, Pass 1)
  adapters/places.ts    Google Places (New) adapter w/ mock fixtures (the mock-first pattern)
docs/                   full research (5 briefs) + plan (10 docs)
```
★ = the load-bearing, research-derived logic. Reuse it; don't re-derive.

## What's NOT here yet (build per the roadmap)
- The Next.js `app/` routes + UI screens (Plan 06) and API route handlers (Plan 07).
- Remaining adapters: `geocode.ts`, `census.ts`, `llm.ts`, `images.ts` (+ mocks) — follow the
  `adapters/places.ts` mock-first pattern.
- `prospectEngine.ts`, `pitchGenerator.ts`, `siteGenerator.ts` orchestration.
- `lib/site-blocks/` section components + `lib/themes` CSS-var wiring (the generated-site renderer).
- `prisma/seed.ts` mock prospects + example pitch + example site.
- Auth middleware, cost guardrails wiring, retention cron, tests/E2E.

## First steps for the executor
1. `npm install` (pin to latest stable; versions in package.json are indicative).
2. Run `create-next-app` conventions over this folder OR add the `app/` dir manually; keep `lib/`.
3. `npx prisma migrate dev` against a Supabase/local Postgres; write `prisma/seed.ts`.
4. `npm test` — the scoring/pricing tests should pass (they already encode the research).
5. Proceed through `docs/plan/08-build-roadmap.md` Phase 1 → 5, mock-first.
