# Plan 00 — Overview

> Executive summary + map of how the pieces fit. Read this first, then the numbered plan docs. Research backing each piece is in `docs/research/`.

## What we're building

A private web tool for 1–2 trusted operators. Flow:

1. **Find & qualify** — operator types a **ZIP** → tool finds **well-reviewed local businesses with no real website**, scores each **0–100**, estimates a **monthly price** they'd pay, names a **competitor** eating their lunch, and computes **ROI** ("~$5k/mo at risk").
2. **Pitch** — one click generates a **one-page, partly verbatim-speakable pitch** (read-aloud script + key-facts box + objections/offer).
3. **Build** — one click generates **two distinct, award-quality websites** for the business, with regenerate + guided tweaks; publish a shareable link to show on the call.

The whole thing is a **win-win**: the operator earns by selling premium websites; the business captures the customers its reputation already earns it.

## How the pieces fit

```
                 ┌──────────────── Prospect Engine (Plan 03) ────────────────┐
   ZIP  ───────▶ │ Places search → no-website classifier → quality filter →   │
                 │ ACS income → competitor → SCORE (0–100) → PRICE → ROI       │
                 └───────────────┬───────────────────────────┬────────────────┘
                                 │ prospect record            │
                   ┌─────────────▼──────────┐    ┌────────────▼─────────────┐
                   │ Pitch Generator (P04)  │    │ Website Generator (P05)  │
                   │ precomputed ROI/price  │    │ 1 content JSON → 2 themes │
                   │ → LLM fills language   │    │ → award-quality sites     │
                   └─────────────┬──────────┘    └────────────┬─────────────┘
                                 │                            │
                          one-page pitch              2 live site options + tweaks
```

Supporting layers: **Data Model (P02)**, **Architecture (P01)**, **API Spec (P07)**, **Frontend/UX (P06)**. Execution order in **Build Roadmap (P08)**. Copy-paste kickoff in **Handoff Prompt (P09)**.

## Key design decisions (full list in `00-DECISIONS.md`)
- **Next.js + Vercel + Supabase Postgres + Prisma.**
- **Google Places API (New)** for discovery (only source with reviews + the `websiteUri` field); **Census ACS** for pricing geography; **Claude** for content; **Pexels** + the business's own Places photos for imagery.
- **Mock-first:** every external call has a mock → the entire product is buildable and demoable before any API key or spend.
- **Quality via tokens, not free-form HTML:** the website generator fills a fixed component/token system, guaranteeing award-level polish.
- **Honesty + ToS guardrails:** ROI shown as labeled estimates; only `place_id` retained long-term; cold-outreach norms (TCPA/CAN-SPAM) documented.

## The research that grounds it (`docs/research/`)
- **01 Target businesses** — ranked ~25 verticals by LTV × local-search dependence × affordability × winnability; A-tier = med spa, dental/ortho, derm, cosmetic surgery, fertility, PI law; the scoring + WTP model.
- **02 Website pricing** — Website-as-a-Service model; $149/$199/$349 tiers × industry (0.8–2.0) × geography (0.85–1.40) multipliers; 80–94% margins.
- **03 Sales pitch** — loss-aversion framing; the read-aloud script + key-facts + objections artifact spec; worked example.
- **04 Web design 2026** — award patterns + per-industry design language → the 4-theme token system.
- **05 Tech / data / AI** — Places API (New) field masks/SKUs/cost (~$1/ZIP), no-website detection, ACS demographics, Claude structured-output generation, ToS guardrails.

## What "done" looks like (v1)
Type a ZIP → ranked website-less prospects with scores, prices, competitor, ROI → one-click pitch one-pager → one-click two award-quality sites with regenerate/tweak → publish a shareable link. Deployed to Vercel, gated by a password, handed to 1–2 users. ~9–14 focused build days.
