// Lead scoring + willingness-to-pay + ROI. Pure functions (unit-tested in Phase 1).
// Encodes docs/plan/03-prospect-engine.md and docs/research/02-website-pricing.md.

import { VERTICAL_BY_KEY } from "./categories";

export type WebsiteStatus = "none" | "social_only" | "directory_only" | "placeholder_dead" | "real";

const NATIONAL_MEDIAN_INCOME = 82000; // ACS national median household income anchor (Research 05).

// --- Geographic price multiplier from zip median household income (0.85–1.40) ---
export function geoMultiplier(medianIncome?: number | null): number {
  if (!medianIncome) return 1.0;
  const r = medianIncome / NATIONAL_MEDIAN_INCOME;
  // 6 bands roughly per Research 02
  if (r < 0.7) return 0.85;
  if (r < 0.9) return 0.95;
  if (r < 1.1) return 1.0;
  if (r < 1.4) return 1.12;
  if (r < 1.8) return 1.25;
  return 1.40;
}

// --- Strength multiplier from reviews / rating / competitive pressure (0.9–1.15) ---
export function strengthMultiplier(p: { rating?: number | null; reviewCount?: number | null; hasStrongerCompetitor?: boolean }): number {
  let m = 1.0;
  if ((p.rating ?? 0) >= 4.7) m += 0.05;
  if ((p.reviewCount ?? 0) >= 150) m += 0.05;
  else if ((p.reviewCount ?? 0) >= 75) m += 0.025;
  if (p.hasStrongerCompetitor) m += 0.05; // they can SEE the demand they're losing
  return Math.min(1.15, Math.max(0.9, m));
}

const BASE_MONTHLY = 199; // Growth tier anchor (Research 02)

export function recommendedMonthly(input: {
  verticalKey: string; medianIncome?: number | null;
  rating?: number | null; reviewCount?: number | null; hasStrongerCompetitor?: boolean;
}): { monthly: number; tier: "starter" | "growth" | "pro"; geo: number; strength: number } {
  const v = VERTICAL_BY_KEY[input.verticalKey];
  const industry = v?.industryMult ?? 1.0;
  const geo = geoMultiplier(input.medianIncome);
  const strength = strengthMultiplier(input);
  const raw = BASE_MONTHLY * industry * geo * strength;
  const monthly = clampToNine(raw, 99, 899);
  const tier = monthly >= 320 ? "pro" : monthly >= 180 ? "growth" : "starter";
  return { monthly, tier, geo, strength };
}

function clampToNine(n: number, lo: number, hi: number): number {
  const clamped = Math.min(hi, Math.max(lo, n));
  return Math.round(clamped / 10) * 10 - 1; // ...9 price points (e.g. 499)
}

// --- ROI math (defensible estimate ranges) ---
export function roiEstimate(input: { verticalKey: string }): {
  monthlySearchers: number; lostPctLow: number; lostPctHigh: number; avgTicket: number;
  revenueAtRiskLow: number; revenueAtRiskHigh: number;
} {
  const v = VERTICAL_BY_KEY[input.verticalKey];
  const monthlySearchers = v?.monthlySearchersSeed ?? 80;
  const avgTicket = v?.avgNewCustomerValue ?? 300;
  const lostPctLow = 0.2, lostPctHigh = 0.35; // referred customers lost at the verification step
  return {
    monthlySearchers, lostPctLow, lostPctHigh, avgTicket,
    revenueAtRiskLow: Math.round(monthlySearchers * lostPctLow * avgTicket),
    revenueAtRiskHigh: Math.round(monthlySearchers * lostPctHigh * avgTicket),
  };
}

// --- Lead score (0–100) with transparent breakdown ---
export interface ScoreInput {
  verticalKey: string;
  rating?: number | null;
  reviewCount?: number | null;
  websiteStatus: WebsiteStatus;
  medianIncome?: number | null;
  hasCompetitorWithSite?: boolean;
  priceLevel?: number | null;
}

const WEIGHTS = { category: 30, reputation: 20, gap: 20, wealth: 15, competition: 10, priceLevel: 5 };

export function leadScore(input: ScoreInput): { score: number; breakdown: Record<string, number> } {
  const v = VERTICAL_BY_KEY[input.verticalKey];
  const category = v?.categoryScore ?? 0.3;

  const ratingPart = clamp01(((input.rating ?? 4.3) - 4.3) / (5.0 - 4.3));
  const reviewsPart = clamp01(Math.log10((input.reviewCount ?? 25) + 1) / Math.log10(500));
  const reputation = 0.5 * ratingPart + 0.5 * reviewsPart;

  const gapMap: Record<WebsiteStatus, number> = { none:1.0, social_only:0.9, placeholder_dead:0.85, directory_only:0.7, real:0.0 };
  const gap = gapMap[input.websiteStatus];

  const wealth = clamp(((input.medianIncome ?? NATIONAL_MEDIAN_INCOME) / NATIONAL_MEDIAN_INCOME), 0.4, 1.0);
  const competition = input.hasCompetitorWithSite ? 1.0 : 0.3;
  const priceLevel = clamp01(((input.priceLevel ?? 2) - 1) / 3);

  const subs = { category, reputation, gap, wealth, competition, priceLevel };
  const weighted =
    WEIGHTS.category * subs.category + WEIGHTS.reputation * subs.reputation +
    WEIGHTS.gap * subs.gap + WEIGHTS.wealth * subs.wealth +
    WEIGHTS.competition * subs.competition + WEIGHTS.priceLevel * subs.priceLevel;
  const total = Object.values(WEIGHTS).reduce((a, b) => a + b, 0);

  return { score: Math.round((100 * weighted) / total), breakdown: subs };
}

const clamp01 = (n: number) => Math.min(1, Math.max(0, n));
const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n));
