// Validates scoring + pricing against the Research 02 worked examples. Run: npm test
import { describe, it, expect } from "vitest";
import { recommendedMonthly, leadScore, geoMultiplier } from "./scoring";

describe("geoMultiplier", () => {
  it("scales with income vs national median", () => {
    expect(geoMultiplier(50000)).toBeLessThan(1);
    expect(geoMultiplier(82000)).toBe(1.0);
    expect(geoMultiplier(200000)).toBeGreaterThan(1.2);
  });
});

describe("recommendedMonthly", () => {
  it("affluent med spa lands in the ~$450-560 band (research ~$499)", () => {
    const r = recommendedMonthly({ verticalKey: "med_spa", medianIncome: 140000, rating: 4.8, reviewCount: 180, hasStrongerCompetitor: true });
    expect(r.monthly).toBeGreaterThanOrEqual(450);
    expect(r.monthly).toBeLessThanOrEqual(580);
    expect(r.tier).toBe("pro");
  });

  it("mid-income plumber lands in the ~$250-320 band (research ~$279)", () => {
    const r = recommendedMonthly({ verticalKey: "plumbing", medianIncome: 75000, rating: 4.6, reviewCount: 60 });
    expect(r.monthly).toBeGreaterThanOrEqual(240);
    expect(r.monthly).toBeLessThanOrEqual(330);
  });

  it("rural barbershop floors near ~$149", () => {
    const r = recommendedMonthly({ verticalKey: "salon", medianIncome: 48000, rating: 4.7, reviewCount: 40 });
    expect(r.monthly).toBeGreaterThanOrEqual(120);
    expect(r.monthly).toBeLessThanOrEqual(190);
  });
});

describe("leadScore", () => {
  it("A-tier, no website, affluent, strong reviews scores high", () => {
    const { score } = leadScore({ verticalKey: "med_spa", rating: 4.8, reviewCount: 180, websiteStatus: "none", medianIncome: 140000, hasCompetitorWithSite: true, priceLevel: 3 });
    expect(score).toBeGreaterThanOrEqual(80);
  });

  it("a business with a real website is filtered/low (gap sub-score 0)", () => {
    const { score, breakdown } = leadScore({ verticalKey: "med_spa", rating: 4.8, reviewCount: 180, websiteStatus: "real", medianIncome: 140000 });
    expect(breakdown.gap).toBe(0);
    expect(score).toBeLessThan(80);
  });
});
