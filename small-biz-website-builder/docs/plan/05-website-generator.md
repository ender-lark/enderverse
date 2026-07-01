# Plan 05 — Website Generator

> Turns a prospect's structured data into **2+ distinct, award-quality website options**, with regenerate + guided tweaks. Source research: `docs/research/04-web-design-2026.md`. **Quality bar:** must never look "templatey." We achieve this with a **design-token + section-component system** (fixed, well-designed building blocks) filled by **LLM-written content** — never free-form HTML.

## Architecture principle: structure is fixed, content is generated

```
Prospect data ──▶ [1] Content model (LLM)  ──▶ structured JSON (copy, services, faqs…)
                  [2] Theme selection       ──▶ token bundle (color/type/space/motion)
                  [3] Section composition    ──▶ ordered list of section blocks
                  [4] React render            ──▶ live site at /s/{slug}
```
The LLM produces **validated JSON content + a theme/section plan**, NOT markup. React components consume tokens + content. This guarantees polish, accessibility, and consistency while still feeling bespoke per business.

## 1. The content model (LLM output schema)

The generator calls Claude with the prospect's data (name, category, rating, reviews, services inferred from category, location, hours, phone) and a strict JSON schema. Example shape:

```ts
type SiteContent = {
  business: { name; tagline; category; phone; address; hours; mapUrl; bookingUrl? };
  brandVoice: 'luxury' | 'trustworthy' | 'rugged' | 'editorial' | 'warm';
  hero: { headline; subhead; primaryCta; secondaryCta?; imageQuery };
  valueProps: { icon; title; body }[];          // 3–4 trust/benefit blocks
  services: { name; blurb; priceFrom?; imageQuery }[];  // 4–8
  about: { heading; body; credentials?: string[] };
  testimonials: { quote; author; stars }[];     // seeded from real Google review themes
  gallery: { imageQuery; caption? }[];
  faqs: { q; a }[];                              // 4–6, local-SEO friendly
  cta: { heading; body; button };
  seo: { title; metaDescription; coreKeyword; localBusinessSchema };
};
```
- **Headlines** lead with the value prop / transformation, one line, per Research 04.
- **Testimonials** are synthesized from the *themes* of the business's real Google reviews (never fabricated as specific named people unless using real public review text + attribution). Mark AI-assembled testimonials clearly in the editor; the operator confirms before publish.
- **imageQuery** drives the stock-image fetch (Unsplash/Pexels), industry- and section-appropriate.
- **localBusinessSchema** = JSON-LD `LocalBusiness` with NAP, hours, geo, aggregateRating.

## 2. The theme token system

Four named, fully-specified themes. The generator picks a **default theme per industry** (below) and offers a **second, contrasting theme** as the alternate option. Each theme is a token bundle:

```ts
type Theme = {
  name; archetype: 'calm-luxury' | 'sturdy-conversion';
  color: { bg; surface; text; muted; primary; accent; onPrimary; border };
  font: { head; body; headWeight; bodyWeight; scale };  // Google Fonts
  radius; shadow; spacingUnit; motion: { ease; durMs; scrollReveal: bool };
};
```

### Theme A — "Warm Boutique" (calm-luxury)
For med spa, salon, wellness, cafe. `bg #F7F3EE · surface #FFFFFF · text #2E2A26 · primary #9CAF88 · accent #C9A86A`. Head **Cormorant Garamond** (600), body **Jost** (300, wide tracking). Radius 16px, soft shadows, generous whitespace (spacingUnit 8 → large), gentle scroll reveal.

### Theme B — "Luxe Dark" (calm-luxury, dramatic)
For cosmetic surgery, fine dining, premium law, barbershop. `bg #121212 · surface #1C1C1E · text #F2EDE4 · primary #C8A04B · accent #B89B5E`. Head **Playfair Display** (700), body **Inter** (400). Radius 8px, subtle gold borders, editorial photography, parallax hero.

### Theme C — "Modern Clean" (sturdy-conversion)
For dental, dermatology, PT, vet, accountants, gyms. `bg #F7FAFC · surface #FFFFFF · text #1A2433 · primary #1A5F7A · accent #4FB3D9`. Head **Poppins** (600), body **Inter** (400). Radius 12px, crisp shadows, bright/airy, click-to-book prominent.

### Theme D — "Bold Field" (sturdy-conversion, high-intent)
For HVAC, plumbing, roofing, electrical, garage door, remodeling, pool, landscaping. `bg #FFFFFF / hero #0F2A4A · text #1E2933 · primary #1565C0 · accent #F26522 (CTA)`. Head **Montserrat** (800) / **Oswald** for condensed, body **Roboto** (400). Sticky emergency call bar, trust-badge strip, proof-heavy. Radius 8px.

> Industry→default/alternate theme mapping lives in `lib/themes/industryThemeMap.ts`. Each theme passes WCAG-AA contrast; the build includes a contrast unit test.

## 3. The section block library

Fixed, polished React components, each theme-aware. The composition step selects and orders them per industry. Library:

| Block | Variants | Notes |
|---|---|---|
| `Header` | transparent-over-hero, solid, sticky+call-bar | Always has primary CTA; mobile sticky click-to-call. |
| `Hero` | image-full, split, dark-overlay, gradient | Oversized headline, 1 primary CTA. |
| `TrustStrip` | logos, badges, stars+count, years | Directly under hero for conversion. |
| `Services` | grid, cards, list+price | 4–8 items from content model. |
| `About` | text+image, credentials | Provider creds for medical/legal. |
| `BeforeAfter` | slider, gallery | Med spa / trades / dental. |
| `Testimonials` | carousel, grid, single-quote | From review themes. |
| `Gallery` | masonry, bento, carousel | Real-photo first. |
| `Pricing` | tiers, from-pricing, hidden | Transparent where appropriate. |
| `BookingCta` | form, embed, call | The lead-capture promise. |
| `Faq` | accordion | Local-SEO Q&A. |
| `Map` | embed + NAP + hours | LocalBusiness signals. |
| `Footer` | full, minimal | NAP, license #, social, repeat CTA. |

### Per-industry section order (examples; full map in code)
- **Med spa:** Header → Hero → TrustStrip → Services(treatments) → About(provider creds) → BeforeAfter → Pricing → Testimonials → BookingCta → Faq → Map → Footer.
- **Home services/trades:** Header(+call bar) → Hero → TrustStrip(licensed/insured/certs) → Services → ServiceAreaMap → About(why-us/guarantees) → BeforeAfter → Testimonials → Pricing/Financing → BookingCta → Footer(phone/hours/license#).
- **Law firm:** Header → Hero → Services(practice areas) → About(credibility/results) → Attorneys → Testimonials → Insights → BookingCta(consultation) → Map → Footer.
- **Restaurant:** Header → Hero(~55vh) → Menu → About/story → Gallery → Reservations → Hours+Map → Footer.

## 4. Generation pipeline (two distinct options)

1. **Resolve inputs** — pull prospect record; infer service list from category (seed library per vertical); fetch zip demographics for tone.
2. **Option 1 = default theme** for the industry; **Option 2 = the alternate theme** (different archetype where sensible, e.g. Modern Clean vs Warm Boutique) so the two look genuinely different, not recolored.
3. For each option: **one LLM call** → `SiteContent` JSON (schema-validated, retry on mismatch). Vary the prompt's voice/angle per option so copy differs too.
4. **Image fetch** — resolve each `imageQuery` to a stock URL (industry-filtered), de-duplicate across sections.
5. **Compose + render** — map content to ordered section blocks; render to a live route; store the `Site` record (content JSON + theme id + image refs).
6. **Score the result** (lightweight): contrast check, section completeness, copy length sanity — flag for regenerate if it fails.

## 5. Regenerate & guided tweaks

- **Regenerate** — re-run the pipeline (new seed → different copy/images) keeping the theme, or switch theme.
- **Guided tweak input** (simple, since users aren't sophisticated): a free-text box "Make it more [contemporary / luxurious / bold / minimal] / change colors to [x] / emphasize [service]". This maps to **token overrides + a constrained LLM re-prompt**, NOT arbitrary restructuring. Provide quick-chip presets ("More modern", "Warmer", "More premium", "Punchier headline") so typing is optional.
- **Section-level controls** — swap hero variant, reorder/hide a section, replace an image, edit any text inline. All safe operations on the structured model.

## 6. Hosting / delivery of generated sites

- v1: DB-backed render at `/s/{slug}` (shareable preview link the operator can text/email the prospect on the call).
- Export: static HTML/Next export bundle for handoff when a deal closes, or publish to a subdomain `{slug}.{ourdomain}`.
- Connect-custom-domain is a post-v1 delivery feature (see scope in `00-DECISIONS.md`).

## 7. Cost notes (per generated option)

- LLM: one structured content call ≈ a few cents to ~$0.30 depending on model/length (Research 02 estimated <$5–$30 per full build across iterations).
- Images: Unsplash/Pexels free tier (attribution where required).
- Mock mode returns a canned `SiteContent` + placeholder images so the whole flow runs free in dev.

## Acceptance criteria
- Two generated options for the same business are **visibly distinct** (different archetype/theme + different copy), both pass WCAG-AA and look like a real agency built them.
- Every site has: above-fold value prop, click-to-call, booking/lead capture, reviews/social proof, services, location/hours/map, LocalBusiness schema, mobile-first responsive layout.
- Regenerate and at least the chip-preset tweaks work end-to-end.
