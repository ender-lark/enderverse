# Small Biz Website Builder

**Working name:** Small Biz Website Builder (SBWB)
**Status:** Planning + research phase (handoff-ready build map)
**Owner:** suraj.balusu@gmail.com

> A web tool that, given a **zip code**, finds **well-reviewed local businesses that have no website**, scores them as sales prospects, estimates what they could pay, generates a **personalized phone-pitch**, and builds them **2+ polished, professional website options** on demand.

This is a **win-win lead-gen + fulfillment tool**: it arms a person with good people-skills to call a thriving-but-website-less business, show them they're leaving money on the table, and hand them a beautiful site that brings in more customers.

---

## What's in this folder

```
small-biz-website-builder/
├── README.md                ← you are here (project charter)
├── docs/
│   ├── 00-DECISIONS.md       ← locked-in decisions + open questions
│   ├── research/             ← deep-research notes (cited) feeding the plan
│   │   ├── 01-target-businesses.md
│   │   ├── 02-website-pricing.md
│   │   ├── 03-sales-pitch.md
│   │   ├── 04-web-design-2026.md
│   │   └── 05-tech-data-ai.md
│   └── plan/                 ← the build map (the deliverable)
│       ├── 00-OVERVIEW.md            ← exec summary + how the pieces fit
│       ├── 01-architecture.md        ← system architecture + stack
│       ├── 02-data-model.md          ← database schema
│       ├── 03-prospect-engine.md     ← find + score + price businesses
│       ├── 04-pitch-generator.md     ← pitch artifact generation
│       ├── 05-website-generator.md   ← website generation system
│       ├── 06-frontend-ux.md         ← screens, flows, components
│       ├── 07-api-spec.md            ← backend API contract
│       ├── 08-build-roadmap.md       ← phased, step-by-step build tasks
│       └── 09-handoff-prompt.md      ← copy-paste prompt for Codex/new chat
```

## The three core jobs

1. **Find & qualify** — Enter a zip → discover well-reviewed local businesses with no website → score each (0–100) and estimate monthly willingness-to-pay.
2. **Pitch** — For chosen prospects, generate a one-page personalized pitch: ~5–7 verbatim phone talking points up top, a key-facts cheat sheet (their stars/reviews, the competitor eating their lunch, the ROI math, the recommended price), and a short objection-handling section.
3. **Build** — Generate 2+ distinct, award-quality website options for the business, with regenerate + guided-tweak controls.

## Guiding principles

- **End-user is not sophisticated.** Type a zip, see prospects, click generate. No jargon, low text, high signal.
- **Quality is the product.** Generated sites must look genuinely top-tier (2026 award-level), not "AI template." Pitches must be persuasive and verbatim-speakable.
- **Win-win and honest.** Real businesses, real ROI math, no dark patterns.
- **Cheap to run in dev.** Mock mode everywhere so we don't burn API spend while building.

See `docs/00-DECISIONS.md` for the locked stack and scope, and `docs/plan/00-OVERVIEW.md` for the full build map.
