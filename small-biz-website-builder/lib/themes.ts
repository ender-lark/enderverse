// The 4 design-theme token bundles (docs/research/04 + docs/plan/05).
// Structure is fixed; the generator fills content. Every theme must pass WCAG-AA
// (enforced by a contrast unit test in Phase 3).

export type ThemeId = "warm-boutique" | "luxe-dark" | "modern-clean" | "bold-field";
export type Archetype = "calm-luxury" | "sturdy-conversion";

export interface Theme {
  id: ThemeId;
  name: string;
  archetype: Archetype;
  color: {
    bg: string; surface: string; text: string; muted: string;
    primary: string; accent: string; onPrimary: string; border: string;
  };
  font: { head: string; body: string; headWeight: number; bodyWeight: number; scale: number };
  radiusPx: number;
  shadow: "soft" | "crisp" | "subtle-gold" | "none";
  spacingUnitPx: number;
  motion: { ease: string; durMs: number; scrollReveal: boolean; parallaxHero: boolean };
}

export const THEMES: Record<ThemeId, Theme> = {
  "warm-boutique": {
    id: "warm-boutique", name: "Warm Boutique", archetype: "calm-luxury",
    color: { bg:"#F7F3EE", surface:"#FFFFFF", text:"#2E2A26", muted:"#6F665C", primary:"#9CAF88", accent:"#C9A86A", onPrimary:"#1F2A22", border:"#E5DDD2" },
    font: { head:"Cormorant Garamond", body:"Jost", headWeight:600, bodyWeight:300, scale:1.28 },
    radiusPx: 16, shadow: "soft", spacingUnitPx: 8,
    motion: { ease:"cubic-bezier(0.22,1,0.36,1)", durMs:600, scrollReveal:true, parallaxHero:false },
  },
  "luxe-dark": {
    id: "luxe-dark", name: "Luxe Dark", archetype: "calm-luxury",
    color: { bg:"#121212", surface:"#1C1C1E", text:"#F2EDE4", muted:"#B6AEA0", primary:"#C8A04B", accent:"#B89B5E", onPrimary:"#121212", border:"#2C2A26" },
    font: { head:"Playfair Display", body:"Inter", headWeight:700, bodyWeight:400, scale:1.3 },
    radiusPx: 8, shadow: "subtle-gold", spacingUnitPx: 8,
    motion: { ease:"cubic-bezier(0.16,1,0.3,1)", durMs:700, scrollReveal:true, parallaxHero:true },
  },
  "modern-clean": {
    id: "modern-clean", name: "Modern Clean", archetype: "sturdy-conversion",
    color: { bg:"#F7FAFC", surface:"#FFFFFF", text:"#1A2433", muted:"#5B6B7C", primary:"#1A5F7A", accent:"#4FB3D9", onPrimary:"#FFFFFF", border:"#E2E8F0" },
    font: { head:"Poppins", body:"Inter", headWeight:600, bodyWeight:400, scale:1.25 },
    radiusPx: 12, shadow: "crisp", spacingUnitPx: 8,
    motion: { ease:"cubic-bezier(0.4,0,0.2,1)", durMs:450, scrollReveal:true, parallaxHero:false },
  },
  "bold-field": {
    id: "bold-field", name: "Bold Field", archetype: "sturdy-conversion",
    color: { bg:"#FFFFFF", surface:"#0F2A4A", text:"#1E2933", muted:"#5A6573", primary:"#1565C0", accent:"#F26522", onPrimary:"#FFFFFF", border:"#D4DBE3" },
    font: { head:"Montserrat", body:"Roboto", headWeight:800, bodyWeight:400, scale:1.27 },
    radiusPx: 8, shadow: "crisp", spacingUnitPx: 8,
    motion: { ease:"cubic-bezier(0.4,0,0.2,1)", durMs:400, scrollReveal:true, parallaxHero:false },
  },
};

// Google Fonts used across themes (load in the generated-site <head>):
export const GOOGLE_FONTS = ["Cormorant Garamond","Jost","Playfair Display","Inter","Poppins","Montserrat","Roboto","Oswald"];
