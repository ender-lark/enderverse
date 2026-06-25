# Plan 09 — Handoff Prompt

> Copy-paste this into Codex or a fresh Claude Code session to execute the build. It points at the docs in this repo so the executor has full context. Run phase by phase.

---

## Master kickoff prompt

```
You are building "Small Biz Website Builder" (SBWB), a private web tool. The complete,
researched plan lives in this repo under `small-biz-website-builder/docs/`. Read these first:

  docs/plan/00-OVERVIEW.md        ← what we're building + how pieces fit
  docs/00-DECISIONS.md            ← locked stack/scope decisions
  docs/plan/01-architecture.md    ← stack + system design
  docs/plan/02-data-model.md      ← Prisma schema
  docs/plan/03-prospect-engine.md ← find/score/price businesses
  docs/plan/04-pitch-generator.md ← pitch artifact
  docs/plan/05-website-generator.md ← theme tokens + section library + generation
  docs/plan/06-frontend-ux.md     ← screens/flows
  docs/plan/07-api-spec.md        ← endpoint contract
  docs/plan/08-build-roadmap.md   ← the ordered task list — FOLLOW THIS
  docs/research/*                 ← cited research backing every number/decision

Build mock-first: every external call (Google Places, Census, Anthropic, Pexels) has a
mock implementation toggled by MOCK_MODE so the whole app is demoable before any API key.

Work through docs/plan/08-build-roadmap.md PHASE BY PHASE. After each phase, run typecheck +
tests and confirm the milestone works in MOCK_MODE before moving on. Do not skip the
unit tests on scoring/pricing/classifier or the WCAG-AA theme contrast test. Keep the
quality bar from docs/plan/05: generated sites must look like a real agency built them —
fill the fixed token/component system, never emit free-form HTML.

Stack: Next.js (App Router, TS) + Tailwind + shadcn/ui + Prisma + Supabase Postgres,
deploy target Vercel. Anthropic SDK with structured outputs for generation.

Start with Phase 0 (scaffold). If the provided scaffold in small-biz-website-builder/app
exists, build on it; otherwise create it. Ask me only if a decision isn't covered by
00-DECISIONS.md (open questions are listed there).
```

## Per-phase prompts (use after the master prompt as you go)

- **Phase 1:** "Implement Phase 1 (Prospect Engine, mock-first) per docs/plan/08 and docs/plan/03. Deliver `lib/categories.ts`, the places/geocode/census adapters + mocks, the no-website classifier, `prospectEngine.ts` with scoring+pricing+competitor+ROI, the four prospect endpoints, and the `/`, `/prospects`, `/prospect/:id` screens. Unit-test scoring & pricing against the Research 02 worked examples. Demo: a ZIP returns ranked scored prospects in MOCK_MODE."

- **Phase 2:** "Implement Phase 2 (Pitch Generator) per docs/plan/04. LLM adapter with structured outputs + mock, `pitchGenerator.ts` (ROI/price precomputed in code, one LLM call for language), the pitch endpoint, and the `/prospect/:id/pitch` screen with copy buttons + PDF export."

- **Phase 3:** "Implement Phase 3 (Website Generator) per docs/plan/05 — the quality core. Build the 4 theme token bundles + industry map + contrast test, the section-block component library, `siteGenerator.ts` (one content JSON → two themes), image adapter, QA pass, the site endpoints, and the `/prospect/:id/sites` + public `/s/:slug` screens. Two options must be visibly distinct and pass WCAG-AA."

- **Phase 4:** "Implement Phase 4: light pipeline board, publish + static export, cost guardrails (cost estimate, monthly cap, PlacesCache, retention cron), and a mobile/empty/error polish pass."

- **Phase 5:** "Go live: provision real API keys, flip MOCK_MODE=false in Vercel, smoke-test one real ZIP, verify ToS + outreach guardrails are surfaced in-app, deploy, and report the URL + cost-per-scan."

## Reminders for the executor
- Honesty: ROI is shown as labeled estimate ranges; never fabricate testimonials, awards, or precision.
- ToS: retain only `place_id` long-term; refresh/purge other Places fields ~30 days; attribution where required; do NOT build a resale/telemarketing list (this is the operator's own pipeline).
- Cost: keep everything runnable in MOCK_MODE; respect the monthly spend cap.
- Quality: snapshot the themes; a "templatey" site is a failed acceptance criterion.
```
