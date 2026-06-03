/**
 * Node test for the K1.1 seam (feed_to_cockpit.js) against the frozen golden FEED.
 * Run:  node test_feed_to_cockpit.js   (exit 0 = pass, 1 = fail)
 *
 * Asserts the field maps + the three reconciliations land correctly, so the
 * cockpit's input shapes are pinned before any UI is written.
 */
const fs = require("fs");
const path = require("path");
const M = require("./feed_to_cockpit.js");

const FEED = JSON.parse(fs.readFileSync(path.join(__dirname, "golden_feed.json"), "utf8"));
const vm = M.toCockpit(FEED);

let fails = 0;
function ok(name, cond, got) {
  if (cond) { console.log("  \u2713 " + name); }
  else { console.log("  \u2717 " + name + (got !== undefined ? "  got: " + JSON.stringify(got) : "")); fails++; }
}
const rotBy = Object.fromEntries(vm.rotation.map(r => [r.s.match(/\(([^)]+)\)/)?.[1] || r.s, r]));
const posByT = {};
vm.holdings.forEach(h => h.pos.forEach(p => { posByT[p.t] = p; }));
const freshByT = Object.fromEntries(vm.freshSignals.map(s => [s.t, s]));

console.log("ROTATION (reconciliation #1 — HEDGE/SOFTENING overlay + semantic colors):");
ok("GDX -> HEDGE / gray", rotBy.GDX && rotBy.GDX.w === "HEDGE" && rotBy.GDX.c === "gray", rotBy.GDX);
ok("VOLT -> SOFTENING / amber", rotBy.VOLT && rotBy.VOLT.w === "SOFTENING" && rotBy.VOLT.c === "amber", rotBy.VOLT);
ok("SMH -> LEADING / green / '+37 vs mkt (3M)'",
   rotBy.SMH && rotBy.SMH.w === "LEADING" && rotBy.SMH.c === "green" && rotBy.SMH.n === "+37 vs mkt (3M)", rotBy.SMH);
ok("SMH sleeve display label", rotBy.SMH && rotBy.SMH.s === "AI / semis (SMH)", rotBy.SMH && rotBy.SMH.s);
ok("GRNY rel==0 -> '≈ market'", rotBy.GRNY && rotBy.GRNY.n === "\u2248 market", rotBy.GRNY && rotBy.GRNY.n);
ok("XLF LAGGING -> red", rotBy.XLF && rotBy.XLF.w === "LAGGING" && rotBy.XLF.c === "red", rotBy.XLF);

console.log("HOLDINGS (rot color + cat % + pos pass-through):");
ok("every group has rot.c set", vm.holdings.every(h => !!h.rot.c));
ok("every group cat ends with '%)'", vm.holdings.every(h => /~\d+%\)$/.test(h.cat)), vm.holdings.map(h => h.cat));
ok("AI group cat present", vm.holdings.some(h => h.cat.startsWith("AI / Semiconductors")), vm.holdings.map(h => h.cat));
const POS_FIELDS = ["t", "n", "pct", "st", "cv", "ty", "own", "lock", "fresh", "cd", "cdNote", "nr", "dr", "be"];
ok("every pos carries all 14 fields", vm.holdings.every(h => h.pos.every(p => POS_FIELDS.every(f => f in p))));
ok("SMH pos cv=Strong cd=flat preserved", posByT.SMH && posByT.SMH.cv === "Strong" && posByT.SMH.cd === "flat", posByT.SMH && [posByT.SMH.cv, posByT.SMH.cd]);
ok("UUUU pos cv=Mixed cd=down preserved", posByT.UUUU && posByT.UUUU.cv === "Mixed" && posByT.UUUU.cd === "down", posByT.UUUU && [posByT.UUUU.cv, posByT.UUUU.cd]);
ok("BMNR lock 🔒 preserved", posByT.BMNR && posByT.BMNR.lock === "\ud83d\udd12", posByT.BMNR && posByT.BMNR.lock);

console.log("FRESH SIGNALS (reconciliation #3 — field map + ticker-as-name):");
ok("ITA -> t=ITA, urg=act, n=ITA, urgLabel set",
   freshByT.ITA && freshByT.ITA.t === "ITA" && freshByT.ITA.urg === "act" && freshByT.ITA.n === "ITA" && !!freshByT.ITA.urgLabel, freshByT.ITA);
ok("FN -> urg=watch", freshByT.FN && freshByT.FN.urg === "watch", freshByT.FN);
ok("exactly 2 fresh signals", vm.freshSignals.length === 2, vm.freshSignals.length);
ok("ITA what -> readable phrase (breakout mapped)", freshByT.ITA && freshByT.ITA.what === "Fresh breakout — cleared a downtrend", freshByT.ITA && freshByT.ITA.what);
ok("FN what -> readable phrase (new_top5 mapped)", freshByT.FN && freshByT.FN.what === "Newly added to the Fundstrat Top-5", freshByT.FN && freshByT.FN.what);

console.log("MACRO / HERO / STAMP / curated pass-through (reconciliation #2):");
ok("macro line + tape set", !!vm.macro.line && !!vm.macro.tape, vm.macro);
ok("macro impl is an array (empty on calm regime)", Array.isArray(vm.macro.impl), vm.macro.impl);
ok("hero leadCount=12, leading SMH/IGV", vm.hero.leadCount === 12 && vm.hero.leadingSleeves.join(",") === "SMH,IGV", vm.hero);
ok("hero needs you = ITA", vm.hero.needsCount === 1 && vm.hero.needsItems[0] && vm.hero.needsItems[0].detail === "ITA", vm.hero.needsItems);
ok("stamp mentions bible + book dates", /bible 2026-05-28/.test(vm.stamp) && /book 2026-05-27/.test(vm.stamp), vm.stamp);
ok("catalysts/questions/research passed through", Array.isArray(vm.catalysts) && Array.isArray(vm.questions) && typeof vm.research === "object");

console.log("");
if (fails) { console.log(`\u274c ${fails} assertion(s) failed`); process.exit(1); }
console.log("\u2705 feed_to_cockpit seam: all assertions pass"); process.exit(0);
