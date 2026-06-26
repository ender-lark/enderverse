// First seed market: San Antonio, TX (owner decision).
// Prioritize affluent north-side ZIPs for A-tier targets (med spa, dental/ortho, cosmetic,
// dermatology) where willingness-to-pay is highest. `incomeBand` is a rough hint for demos /
// the geo price multiplier; the real value comes from Census ACS at scan time.

export interface SeedZip {
  zip: string;
  area: string;
  incomeBand: "affluent" | "above_avg" | "mid";
  note?: string;
}

export const SAN_ANTONIO_ZIPS: SeedZip[] = [
  // --- Affluent (best first hunting grounds) ---
  { zip: "78209", area: "Alamo Heights / Terrell Hills", incomeBand: "affluent", note: "med spa, cosmetic, dental — high WTP" },
  { zip: "78257", area: "The Dominion / Far NW", incomeBand: "affluent" },
  { zip: "78258", area: "Stone Oak", incomeBand: "affluent", note: "dense med spa / aesthetics cluster" },
  { zip: "78256", area: "NW (La Cantera/Rim)", incomeBand: "affluent" },
  { zip: "78260", area: "Far North (Bulverde edge)", incomeBand: "affluent" },
  { zip: "78248", area: "North Central", incomeBand: "affluent" },
  { zip: "78230", area: "Churchill / Medical-adjacent", incomeBand: "above_avg" },
  { zip: "78231", area: "Shavano Park area", incomeBand: "affluent" },

  // --- Above-average ---
  { zip: "78216", area: "North Central (airport)", incomeBand: "above_avg" },
  { zip: "78232", area: "North Central", incomeBand: "above_avg" },
  { zip: "78250", area: "Northwest", incomeBand: "above_avg" },
  { zip: "78240", area: "Northwest (UTSA)", incomeBand: "above_avg" },
  { zip: "78212", area: "Monte Vista / Pearl", incomeBand: "above_avg", note: "gentrified central; restaurants/salons" },

  // --- Mid (broader trades/services coverage) ---
  { zip: "78201", area: "Near NW / Deco District", incomeBand: "mid" },
  { zip: "78228", area: "West Side", incomeBand: "mid" },
  { zip: "78223", area: "Southeast", incomeBand: "mid" },
  { zip: "78205", area: "Downtown / Alamo", incomeBand: "mid", note: "hospitality-heavy" },
];

export const DEFAULT_SEED_MARKET = "San Antonio, TX";
export const DEFAULT_SEED_ZIPS = SAN_ANTONIO_ZIPS.map((z) => z.zip);
// Suggested first demo scan: the three densest affluent A-tier areas.
export const FIRST_DEMO_ZIPS = ["78209", "78258", "78257"];
