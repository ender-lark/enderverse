# Plan 06 — Frontend / UX

> Design principle: the operator is NOT sophisticated. **Type a ZIP → see prospects → click Generate.** Low text, high signal, obvious next action on every screen. The operator app itself should also look polished (it's the product's first impression), but its job is speed and clarity, not flair.

## Screens & flows

### 1. `/` — Search
- Big single input: **"Enter a ZIP code"** + a Search button. Optional advanced drawer: category filter (defaults to A/B-tier target set), min rating, min reviews.
- On submit → progress state ("Scanning Oakhaven… checking 12 business types") → routes to results. Mock mode is instant.
- Recent searches list below.

### 2. `/prospects` — Ranked results
- Cards sorted by **lead score (0–100)**, score shown as a big colored badge. Each card: business name, category, ★rating · review count, **"No website" / "Facebook only" tag**, recommended **$X/mo**, and a one-line "why" (e.g. "4.8★, 180 reviews, no site, affluent area").
- Primary action per card: **Generate** (→ creates pitch + 2 sites) and **View**. Secondary: Save to pipeline.
- Filter/sort controls; a "capped results" notice if Places hit the 60-cap.

### 3. `/prospect/:id` — Prospect detail
- Header: name, category, stars/reviews, phone (click-to-call), map.
- **Score breakdown** panel ("why this score" — the weighted components).
- **Competitor** callout (name, rank, their stars/reviews, "they rank #1 with weaker reviews").
- **ROI math** ("~20 lost bookings/mo × $250 ≈ ~$5k/mo at risk", with the estimate band shown).
- **Pricing** (recommended monthly + tier + optional one-time).
- Two big buttons: **Generate Pitch** · **Generate Website**.

### 4. `/prospect/:id/pitch` — The one-pager
- Renders the `Pitch` artifact (Plan 04): Zone A read-aloud (large, bold, numbered), Zone B key-facts box, Zone C objections/offer.
- Buttons: Copy script · Copy follow-up email · Export PDF · Regenerate.

### 5. `/prospect/:id/sites` — Website options
- **Two option cards side by side** (Option A / Option B), each a live thumbnail/iframe preview + "Open full preview" (→ `/s/:slug`).
- Controls: **Regenerate** (new copy/images), **Switch theme**, and a **guided-tweak box** with quick chips ("More modern", "Warmer", "More premium", "Punchier headline") + optional free-text.
- Section controls on the full preview: swap hero variant, reorder/hide section, replace image, inline-edit text.
- **Publish** (gives a shareable `/s/:slug` link) · **Export**.

### 6. `/s/:slug` — Public generated site
- The actual award-quality generated website (Plan 05). Mobile-first. This is what the operator shows/sends the business owner.

### 7. `/pipeline` (light) — Saved prospects
- Simple board/list by status (new / saved / pitched / built / won / lost) with notes. No heavy CRM.

## UX rules
- Every screen has ONE obvious primary action.
- Numbers are pre-computed and shown plainly; estimates are labeled.
- Loading states are explicit and friendly; nothing silently truncates (show "capped" / "showing top N").
- Works great on a phone (operators may use it mid-call).
- Empty/mock states are seeded so a first-run demo looks alive.

## Component inventory (operator app)
shadcn/ui base: `ScoreBadge`, `ProspectCard`, `ScoreBreakdown`, `CompetitorCallout`, `RoiPanel`, `PricePanel`, `PitchSheet`, `SiteOptionCard`, `TweakBar`, `PipelineBoard`. Generated-site blocks live separately under `lib/site-blocks/` (Plan 05).
