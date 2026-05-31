/**
 * Conviction Engine · K1.1 seam — Contract-C FEED  ->  cockpit display shapes.
 *
 * Pure functions, NO JSX, NO React: this is the boundary the v5 cockpit consumes.
 * Kept as a standalone CommonJS module so it's node-testable in isolation
 * (test_feed_to_cockpit.js). The v5 cockpit inlines these same functions; this
 * file is the tested source of truth for the mapping — keep them in sync.
 *
 * Colors are emitted as SEMANTIC NAMES ("green"/"blue"/"amber"/"red"/"gray");
 * the cockpit maps name -> hex via its own palette (decouples mapping from theme).
 *
 * Three reconciliation decisions are encoded here (operator-approved defaults):
 *   1. rotation HEDGE/SOFTENING — engine emits the mechanical 5 labels; a thin
 *      DISPLAY overlay restores HEDGE (known hedge sleeves) + SOFTENING (kept
 *      pace over 3M, slipping over 1M) without the engine faking labels.
 *   2. catalysts/questions/research — passed through from the feed as-is (the
 *      cockpit layers in its own curated const; not this seam's job).
 *   3. fresh-signal long name — the feed carries the ticker, so n = ticker.
 */

const LABEL_COLOR = {
  "LEADING": "green",
  "IN LINE": "blue",
  "TURNING UP": "amber",
  "SOFTENING": "amber",
  "TURNING DOWN": "red",
  "LAGGING": "red",
  "HEDGE": "gray",
};

// known hedge sleeves -> displayed as HEDGE (reconciliation #1)
const HEDGE_SLEEVES = new Set(["GDX", "GLD", "SIL", "WPM"]);

// rotation-proxy subject -> human sleeve label for the leaderboard row
const SLEEVE_DISPLAY = {
  "SMH": "AI / semis (SMH)",
  "IGV": "Software (IGV)",
  "GRNY": "Quality core (GRNY)",
  "VOLT": "Electrification (VOLT)",
  "IBIT": "Crypto (IBIT)",
  "XLF": "Financials (XLF)",
  "REMX": "Critical minerals (REMX)",
  "URA": "Nuclear (URA)",
  "GDX": "Gold hedge (GDX)",
};

const FRESH_URG_LABEL = {
  "act": "early signal — act within days",
  "watch": "watch — wait for your trigger",
};
// event token -> readable phrase for the fresh-signal "What:" line (display layer).
// Covers the Analyst's FRESH_SIGNAL_EVENTS set; unknown tokens fall through verbatim.
const PRETTY_EVENT = {
  breakout: "Fresh breakout — cleared a downtrend",
  new_pick: "Newly named a source pick",
  new_top5: "Newly added to the Fundstrat Top-5",
  upgrade: "Source upgrade",
  bottom_in: "Source calling a bottom",
};

function colorFor(label) {
  return LABEL_COLOR[label] || "gray";
}

/** Engine sleeve label -> displayed label, applying the HEDGE/SOFTENING overlay. */
function overlayLabel(sleeve) {
  if (HEDGE_SLEEVES.has(sleeve.subject)) return "HEDGE";
  const r1 = sleeve.rel_1m, r3 = sleeve.rel_3m;
  // SOFTENING: held the line over 3M (>= ~flat) but slipping over the last month
  if (sleeve.label === "IN LINE" && typeof r1 === "number" && typeof r3 === "number"
      && r1 < -0.04 && r3 >= -0.02) {
    return "SOFTENING";
  }
  return sleeve.label;
}

/** "+37 vs mkt (3M)" / "≈ market" from rel_3m. */
function relString(rel3m) {
  if (typeof rel3m !== "number" || rel3m === 0) return "≈ market";
  const pts = Math.round(rel3m * 100);
  return `${pts > 0 ? "+" : ""}${pts} vs mkt (3M)`;
}

/** Engine rotation sleeve -> v4 ROTATION row {s,w,c,n,note}. */
function rotationRow(sleeve) {
  const w = overlayLabel(sleeve);
  return {
    s: SLEEVE_DISPLAY[sleeve.subject] || sleeve.subject,
    w,
    c: colorFor(w),
    n: relString(sleeve.rel_3m),
    note: sleeve.note || "",
  };
}

/** Engine macro_read output -> v4 MACRO {line,tape,impl,note}. */
function macroView(macro) {
  const regime = macro.regime || {};
  const alerts = macro.alerts || [];
  return {
    line: macro.line || "",
    tape: regime.label || "",
    impl: macro.implications || [],            // data-derived; empty on a calm regime
    note: alerts.length ? `${alerts.length} macro alert(s) firing` : "No macro alerts firing.",
  };
}

/** Sum of position weights in a group, rounded, for the cat "(~X%)" suffix. */
function groupPct(pos) {
  const s = pos.reduce((a, p) => a + (typeof p.pct === "number" ? p.pct : 0), 0);
  return Math.round(s);
}

/** Engine holding group -> v4 HOLD group {cat, rot:{w,c}, pos}. pos passes
 *  through (it already carries every v4 field plus lock/fresh for v5's UI). */
function holdingGroup(h) {
  const w = (h.rot && h.rot.w) || "";
  return {
    cat: `${h.cat} (~${groupPct(h.pos)}%)`,
    rot: { w, c: colorFor(w) },
    pos: h.pos,
  };
}

/** Engine fresh_signal -> v4 FRESH_SIGNALS row {t,n,urg,urgLabel,when,what,why,detail}. */
function freshSignalRow(sig) {
  return {
    t: sig.ticker,
    n: sig.ticker,                              // reconciliation #3: ticker, no long name
    urg: sig.urgency,
    urgLabel: FRESH_URG_LABEL[sig.urgency] || sig.urgency,
    when: sig.when || "",
    what: PRETTY_EVENT[sig.what] || sig.what || "",   // event token -> readable phrase
    why: sig.why || "",
    detail: sig.detail || "",
  };
}

/** Engine ⑧ hero block -> a flat banner view-model. */
function heroView(hero) {
  const h = (hero && hero.hero) || {};
  const ny = (hero && hero.needs_you) || {};
  return {
    leadCount: h.count || 0,
    leadNames: h.names || [],
    leadingSleeves: h.leading_sleeves || [],
    needsCount: ny.count || 0,
    needsItems: ny.items || [],
  };
}

/** Source-currency stamp from the feed's generated_at + staleness entries. */
function stamp(feed) {
  const entries = (feed.staleness && feed.staleness.entries) || [];
  const bySrc = Object.fromEntries(entries.map(e => [e.source, e.date]));
  const LABEL = { fundstrat_bible: "bible", uw_price: "rotation", portfolio: "book" };
  const parts = [];
  for (const src of ["fundstrat_bible", "uw_price", "portfolio"]) {
    if (bySrc[src]) parts.push(`${LABEL[src]} ${bySrc[src]}`);
  }
  const src = parts.length ? ` · sources: ${parts.join(", ")}` : "";
  return `as of ${(feed.generated_at || "").slice(0, 10)}${src}`;
}

/** Full view-model the cockpit renders from one Contract-C feed. */
function toCockpit(feed) {
  return {
    generatedAt: feed.generated_at || "",
    stamp: stamp(feed),
    macro: macroView(feed.macro || {}),
    rotation: (feed.rotation || []).map(rotationRow),
    holdings: (feed.holdings || []).map(holdingGroup),
    freshSignals: (feed.fresh_signals || []).map(freshSignalRow),
    hero: heroView(feed.hero || {}),
    catalysts: feed.catalysts || [],            // reconciliation #2: pass-through
    questions: feed.questions || [],
    research: feed.research || {},
  };
}

module.exports = {
  LABEL_COLOR, HEDGE_SLEEVES, SLEEVE_DISPLAY, FRESH_URG_LABEL,
  colorFor, overlayLabel, relString, rotationRow, macroView, groupPct,
  holdingGroup, freshSignalRow, heroView, stamp, toCockpit,
};
