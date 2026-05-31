// ───────────────────────────────────────────────────────────────
// Full-chain capstone — JS half.
// Reads a LIVE feed JSON (produced by full_chain_smoke.py from the REAL
// collect() -> assemble_feed() chain, no frozen intermediate), runs the REAL
// seam (feed_to_cockpit.js), and proves the cockpit view-model is complete and
// identical to the one the frozen golden feed produces.
//
// Pure CommonJS — needs only feed_to_cockpit.js (no React, no bundler). The
// React render over this exact view-model is proven by the K2 SSR smoke-test.
//
// Usage:  node full_chain_render.js <live_feed.json>
// ───────────────────────────────────────────────────────────────
const fs = require("fs");
const path = require("path");
const { toCockpit } = require("./feed_to_cockpit.js");

const HERE = __dirname;
const livePath = process.argv[2];
if (!livePath) { console.error("usage: node full_chain_render.js <live_feed.json>"); process.exit(2); }

const live = JSON.parse(fs.readFileSync(livePath, "utf8"));
const golden = JSON.parse(fs.readFileSync(path.join(HERE, "golden_feed.json"), "utf8"));

const vmLive = toCockpit(live);
const vmGold = toCockpit(golden);

const errs = [];
if (JSON.stringify(vmLive) !== JSON.stringify(vmGold)) errs.push("view-model from live feed != view-model from golden feed");
if (vmLive.holdings.length !== 8)      errs.push("expected 8 holding groups, got " + vmLive.holdings.length);
if (vmLive.rotation.length !== 9)      errs.push("expected 9 rotation sleeves, got " + vmLive.rotation.length);
if (vmLive.freshSignals.length !== 2)  errs.push("expected 2 fresh signals, got " + vmLive.freshSignals.length);
if (typeof vmLive.hero.needsCount !== "number") errs.push("hero.needsCount missing");
if (!vmLive.stamp || !vmLive.stamp.includes("as of")) errs.push("stamp missing/malformed");

if (errs.length) {
  console.error("FULL-CHAIN JS HALF FAILED:\n  - " + errs.join("\n  - "));
  process.exit(1);
}
console.log("\u2713 JS half: live feed -> seam -> complete view-model "
  + "(8 holdings, 9 sleeves, 2 fresh, hero, stamp), identical to the golden path");
