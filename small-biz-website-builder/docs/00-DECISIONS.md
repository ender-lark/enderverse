# 00 — Decisions & Scope

This file records the decisions that shape the build, the defaults I chose (a clarifying prompt was interrupted by a transient error, so I proceeded on the recommended options — all are overridable), and the open questions for the owner.

## Locked decisions (defaults — change any of these and the plan still holds)

| # | Decision | Choice | Rationale |
|---|---|---|---|
| D1 | Project home | New self-contained project in `small-biz-website-builder/` with its own DB | The host repo is an unrelated Python trading system; user asked for "a whole new project, a whole new database." |
| D2 | This session's deliverable | Deep research + a fully-mapped build plan (handoff-ready) **+ starter scaffold** | User emphasized careful planning they can hand to Codex/a new chat, then "start building." |
| D3 | Stack | **Next.js (App Router, TypeScript) + Vercel + Postgres** | Modern full-stack, one-click deploy, serverless API routes can hold secret keys, best fit for a polished publishable web tool in 2026. |
| D4 | Database | **Postgres via Supabase** (DB + storage + optional auth in one) + Prisma ORM | Fewest services to wire; storage for generated-site assets; can swap to Neon if preferred. |
| D5 | Prospect data source | **Google Places API (New)** primary; Yelp Fusion / OSM as fallbacks | Only source that reliably returns rating + review count + the `websiteUri` field to detect "no website." (Confirm exact capabilities in Research 05.) |
| D6 | Demographics for pricing | **US Census ACS API** (free) for zip median household income | Drives the geographic price multiplier. |
| D7 | AI generation | **Claude (latest model)** for copy + structured content; fixed React component/token system for layout | Guarantees award-level quality vs free-form HTML; LLM fills content, not structure. |
| D8 | Images | Stock via **Unsplash/Pexels API** (industry-matched) for v1; AI images as later upgrade | Cheap, fast, good enough; avoids per-image generation cost early. |
| D9 | Cost control | **Mock mode** for every external API, toggled by env var | Build & demo without burning Places/LLM spend. |
| D10 | Auth | Light gate (single shared password or Supabase magic-link) | Tool is for 1–2 trusted people; no need for full multi-tenant auth in v1. |
| D11 | Generated-site hosting | DB-backed render at `/{slug}` + static export option | Lets the salesperson share a live preview link instantly; export for handoff/delivery. |
| D12 | Pricing model sold to businesses | **Website-as-a-Service**: low/no upfront + monthly (Starter $149 / Growth $199 / Pro $349 before multipliers) | Removes the upfront-check objection (owners' #1 barrier); high MRR + retention. (Research 02.) |

## Open questions for the owner (none block the plan; sensible defaults are in place)

1. **Real API budget** — Confirm OK to provision a Google Cloud billing account for Places API. **Free-tier note (owner-confirmed direction):** the fields we need (rating, review count, `websiteUri`) bill at the **Enterprise** SKU = **1,000 free requests/month** (the 5,000 figure is the *Pro* tier, which lacks reviews). That's still ample to start — one request returns up to 20 businesses, so ~1,000 Enterprise requests ≈ **30–80 full ZIP scans/month free**, then ~$1/ZIP. Start on the free tier; add billing only when scans exceed it. (Re-verify against Google's live pricing page; revised Mar 2025.) Mock mode covers all dev regardless.
2. **Geographic focus — DECIDED: San Antonio, TX first.** Seed San Antonio ZIPs (see `lib/seedMarkets.ts`), prioritizing affluent north-side areas (Alamo Heights 78209, Stone Oak 78258, Dominion/78257) for A-tier targets (med spa, dental/ortho, cosmetic, dermatology) where willingness-to-pay is highest. Expand to other metros after validation.
3. **Branding** — Keep the name "Small Biz Website Builder" or rename? (Pick a public-facing brand before deploy.)
4. **Delivery** — When a business says yes, who registers the domain / handles billing? (Affects the "deliver" phase beyond v1 scope.)
5. **Auth level** — Single shared password fine, or per-user logins for the 1–2 operators?

## Explicitly out of scope for v1 (noted so the plan stays focused)

- Payment collection from the end businesses (Stripe integration) — design for it, build later.
- Full CRM / pipeline management — a simple saved-prospects list suffices for v1.
- Automated outbound calling/emailing — the tool produces the pitch; the human makes the call.
- Multi-tenant SaaS for strangers — this is a private tool for 1–2 people.

## Guardrails (carry into every build step)

- **ToS/legal:** Respect Google Places caching limits & display requirements; ACS data is public-domain. Cold-calling must respect basic TCPA/DNC norms (calling businesses, not consumers, is lower-risk but note it). Detailed in Research 05.
- **Honesty:** ROI math shown to owners must use defensible ranges, labeled as estimates — no fabricated precision.
- **Quality bar:** A generated site that looks "templatey" is a failure. The component/token system + real photography + per-industry design language exist to prevent that.
