# Research 04 — Award-Quality Web Design (2026)

> Basis for the **website generator's theme/token system** (`docs/plan/05-website-generator.md`). Sources: Awwwards, CSS Design Awards, FWA, Webflow/Made-in-Webflow, Godly, Land-book, Httpster + 2025–2026 trend roundups. The generated sites must read as genuinely top-tier — never "AI template."

## 1. What defines award-winning design in 2026

The period's story is a **bifurcation**: technical, motion-heavy WebGL "experience" sites at the agency top end, and a parallel rise of **expressive-typography minimalism** + a **neo-brutalist counter-movement**. For *local service businesses that must convert customers* (our use case), we borrow the polish and restraint, not the flashy WebGL.

**Recurring patterns in winners:**
- **Layout:** Bento grids (modular rounded tiles, à la Apple/Linear) are the defining mainstream layout; deliberate asymmetry / broken grids as the counter-trend.
- **Typography (the single strongest signal):** Oversized, expressive display type as the hero anchor. "Almost every Awwwards winner uses bold expressive typography as the hero element." Exaggerated hierarchy (huge display vs tiny captions). Recurring typefaces: **PP Neue Montreal**, **Söhne** (grotesques), often paired. Variable + kinetic type on hero headlines (used sparingly — it fights accessibility & Core Web Vitals).
- **Color:** Dark mode as full identity + one electric accent; OR muted earthy palettes (clay, sage) for wellness/luxury; vibrant gradients with blur/distortion. Accessibility floor: ≥4.5:1 body, ≥3:1 large headings.
- **Whitespace:** Two camps — refined minimalism (one idea per hero, low cognitive load) vs maximalist density. For local businesses → **refined minimalism wins** (clarity converts).
- **Motion:** **GSAP + ScrollTrigger is the de-facto standard** (free since Webflow's 2024 GreenSock acquisition). Scroll-as-storytelling, parallax revival, smooth scroll (Lenis/Locomotive), native CSS scroll-driven animations emerging.
- **Micro-interactions:** Custom cursors + magnetic/sticky buttons are the agency signature; subtle hover-reveal feedback.
- **Hero patterns:** Full-bleed oversized-type hero with one concise headline + single CTA; emotion-first (tone before copy); editorial photography over stock.

**Studios setting the standard** (cite when emulating): Locomotive, Resn, Active Theory, Unseen Studio, OFF+BRAND, Little Workshop, Noomo, Media.Monks.

**Net default for our generator (safe + on-trend):** clean broken-grid or bento layout · oversized expressive headline in a grotesque (Neue Montreal / Söhne class) · generous whitespace · dark mode w/ one electric accent OR muted earthy palette for wellness · editorial photography or tasteful gradient accent · GSAP/ScrollTrigger reveal + parallax · magnetic buttons + subtle custom cursor · kinetic type only on the hero headline.

## 2. Conversion + trust for LOCAL service sites (non-negotiables)

Award gloss is worthless if it doesn't convert a local customer. Every generated site MUST have:
- **Above-the-fold value prop** + a single primary CTA.
- **Persistent click-to-call** (sticky on mobile) — most local searches are mobile and high-intent.
- **Online booking / lead form** (the after-hours capture the pitch promises).
- **Reviews / social proof** (stars, count, testimonials) — pulled from their Google reputation, their #1 asset.
- **Trust signals:** licensed/insured/certified badges, years in business, awards.
- **Services**, **pricing transparency** where appropriate, **location/hours/map**, **photo gallery**.
- **Fast load, mobile-first, WCAG-AA accessibility.**
- **Local SEO basics:** LocalBusiness schema (JSON-LD), consistent NAP, GBP linkage, the core "[service] near [town]" keyword in H1/title.

## 3. Per-industry design language

Two macro-archetypes dominate: **"calm luxury / editorial elegance"** (med spa, salon, fine dining, law → serif + neutral/muted + whitespace) vs **"sturdy conversion"** (home services, barbershop, functional dental → bold sans + high-contrast accent + proof-heavy). Across all: a persistent Book/Call CTA above the fold, and **real photography beats stock**.

| Industry | Palette (hex) | Fonts (head / body) | Hero imagery | Tone |
|---|---|---|---|---|
| **Med Spa / Aesthetics** | Ivory `#F5F0E8`, Sage `#9CAF88`, Blush `#E8D5CF`, Champagne `#C9A86A`, Charcoal-teal `#2E3A3A` | Cormorant Garamond / Jost (or Montserrat) | Dewy skin, serene treatment rooms, warm-neutral grade, real before/after | Calm clinical luxury |
| **Dental** | Trust blue `#1A5F7A`, Teal `#4FB3D9`, Sage `#7FB7A4`, Sand `#E8DCCB`, Off-white `#F7FAFC`, Slate `#2D3748` | Poppins / Nunito Sans / Inter | Real dentist & team, bright airy office, smiling patients | Clean, trustworthy, calming |
| **Law Firm** | Navy `#1A2B4A`, Charcoal `#1C1C1E`, Brass `#B89B5E`, Slate `#6B7280`, Off-white `#F7F5F1` | Playfair Display / Lora + Inter / Source Sans 3 | Editorial attorney portraits, architecture/skyline, dark overlay | Trustworthy authority |
| **Home Services / Trades** | Navy `#0F2A4A`, Blue `#1565C0`, CTA orange `#F26522`, Yellow `#FFC107`, Light `#F5F7FA`, Slate `#1E2933` | Montserrat / Poppins / Oswald + Roboto / Inter | Uniformed tech at door, branded van, real before/after, daylight + dark scrim | Rugged reliability |
| **Hair Salon / Beauty** | Cream `#F7F3EE`, Blush `#E2BFAC`, Dusty rose `#D7B4B0`, Taupe `#A4978E`, Espresso `#3A332F`, Gold `#C9A66B` | Playfair Display / Cormorant + Montserrat / Jost | Bright soft-lit editorial, finished hair, serene interiors | Quiet luxury, pampering |
| **Barbershop** | Near-black `#121212`, Off-white `#F2EDE4`, Brass `#C8A04B`, Oxblood `#7B2D26`, Vintage brown `#5C4033` | Oswald / Bebas Neue / Anton + Roboto / Inter | Moody B&W / sepia, barber mid-cut, leather/brick/brass | Confident, timeless, masculine craft |
| **Restaurant / Cafe / Bar** | Fine: charcoal `#1A1714` + gold `#C8A35B`; Cafe: cream `#F5EDE1` + terracotta `#C46A4A`; Bar: black `#0E0E10` + neon `#16C0B0`/`#E94FA1` | Playfair / Fraunces / Anton + Inter / DM Sans / Space Grotesk | Full-bleed food or ambiance, compact ~50–60vh hero | Sensory, aspirational, warm |

Per-industry section order is specified in detail in `docs/plan/05-website-generator.md` (each vertical's section sequence, e.g. med spa = hero → treatments → provider creds → before/after → pricing → testimonials → membership → FAQ → booking/location).

## 4. Drives the generator (see plan/05)

The takeaway for implementation: a **design-token + section-component system**, NOT free-form HTML. The generator picks a **theme** (token bundle: color scale, type scale, spacing, radius, shadow, motion) matched to the industry, fills a **library of section blocks** (hero variants, services grid, testimonials, booking CTA, gallery, about, FAQ, footer) with LLM-written content, and renders polished React components. This guarantees award-level quality and lets us produce 2 visibly distinct options + regenerate. The concrete theme token values ("Modern Clean", "Bold Editorial", "Warm Boutique", "Luxe Dark") are defined in the build spec.

## Sources
Awwwards (Sites of the Year/Day, winner list, Locomotive/Resn/GSAP showcases), CSS Design Awards 2025, FWA, Webflow/Made-in-Webflow, Godly, Land-book, Httpster; Muzli, Figma, Framer, Wix, TheeDigital, StudioMeyer "reality check"; type: Pangram Pangram (Neue Montreal), Klim (Söhne), Typewolf, Creative Boom top-50-fonts; per-industry galleries: Marceline Studios, Tiffany Kenyon, delmain.co, meetdandy, Magier, Contra, PaperStreet, sitebuilderreport, colorlib, lovable.dev, menutiger, getbento. Full URLs preserved in session research log.
