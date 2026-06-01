import React, { useState } from "react";

// ───────────────────────────────────────────────────────────────
// CONVICTION COCKPIT — v5
// Consumes ONE Contract-C FEED (the engine's output) via the feed_to_cockpit
// seam, instead of hard-coded data consts. Swap the FEED const for a live fetch
// later; the render never changes.
// K1.2 wired from FEED: header stamp · Market read (rotation + macro) · Holdings.
// K1.2 wired from FEED: header stamp · Market read (rotation + macro) · Holdings.
// K1.3 wired: hero banner (⑧) · Today's actions / fresh signals (⑦) · Questions ·
//             Research · Catalysts (last three cockpit-curated until the feed emits them).
// ───────────────────────────────────────────────────────────────

const C = {
  bg:"#0c0e12", panel:"#13161c", panel2:"#171b22", panel3:"#1c212a", line:"#242a33",
  text:"#e6e9ef", dim:"#8a93a2", faint:"#5a6373",
  green:"#3fb27f", blue:"#4d9be6", amber:"#d6a44c", red:"#d96a6a", gray:"#6b7280", accent:"#c9a227",
};
const mono = "'SF Mono','SFMono-Regular',ui-monospace,'JetBrains Mono',Menlo,Consolas,monospace";
const sans = "'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif";

const CONV = {
  Strong:    { c:C.green, q:"high quality / high confidence — can support a larger position" },
  Promising: { c:C.blue,  q:"good and building, not fully proven — moderate size" },
  Mixed:     { c:C.amber, q:"real but uncertain / offsetting negatives — keep modest" },
  Weak:      { c:C.red,   q:"thin or fading — small, or an exit candidate" },
  "—":       { c:C.gray,  q:"not yet assessed — needs a thesis line" },
};
const POSTURE = { Strong:"a meaningful", Promising:"a moderate", Mixed:"a modest", Weak:"a small", "—":"an unassessed" };

// semantic color name (emitted by the seam) -> palette hex
const COLOR_HEX = { green:C.green, blue:C.blue, amber:C.amber, red:C.red, gray:C.gray };

// ── the engine feed (one Contract-C object). Replace with a live fetch later. ──
const FEED = {
  "generated_at": "2026-05-29T16:00:00",
  "staleness": {
    "stamp": "sourced: uw_price 05-29 \u00b7 uw_macro 05-29 \u00b7 fundstrat_bible 05-28 \u00b7 fundstrat_daily 05-28 \u00b7 meridian 03-15 (baseline) \u00b7 portfolio 05-27",
    "entries": [
      {
        "source": "uw_price",
        "date": "2026-05-29",
        "age_days": 0,
        "cadence": "daily",
        "stale": false,
        "flag": ""
      },
      {
        "source": "uw_macro",
        "date": "2026-05-29",
        "age_days": 0,
        "cadence": "daily",
        "stale": false,
        "flag": ""
      },
      {
        "source": "fundstrat_bible",
        "date": "2026-05-28",
        "age_days": 1,
        "cadence": "monthly",
        "stale": false,
        "flag": ""
      },
      {
        "source": "fundstrat_daily",
        "date": "2026-05-28",
        "age_days": 1,
        "cadence": "daily",
        "stale": false,
        "flag": ""
      },
      {
        "source": "meridian",
        "date": "2026-03-15",
        "age_days": 75,
        "cadence": "static",
        "stale": false,
        "flag": "(baseline)"
      },
      {
        "source": "portfolio",
        "date": "2026-05-27",
        "age_days": 2,
        "cadence": "on_refresh",
        "stale": false,
        "flag": ""
      }
    ],
    "stale": []
  },
  "hero": {
    "hero": {
      "count": 12,
      "names": [
        "SMH",
        "MAGS",
        "NVDA",
        "MU",
        "GRNY",
        "XLF",
        "LEU",
        "MP",
        "UUUU",
        "BMNR",
        "IBIT",
        "VOLT"
      ],
      "leading_sleeves": [
        "SMH",
        "IGV"
      ]
    },
    "needs_you": {
      "count": 1,
      "items": [
        {
          "reason": "fresh_act",
          "detail": "ITA"
        }
      ]
    }
  },
  "fresh_signals": [
    {
      "ticker": "FN",
      "urgency": "watch",
      "what": "new_top5",
      "why": "FN \u2014 newly named FS Top-5 SMID (AI optical)",
      "when": "2026-05-28",
      "detail": "05-28 fundstrat_bible new_top5"
    },
    {
      "ticker": "ITA",
      "urgency": "act",
      "what": "breakout",
      "why": "ITA cleared a multi-month downtrend \u2014 Newton 5/28 (breakout)",
      "when": "2026-05-28",
      "detail": "05-28 fundstrat_daily breakout"
    }
  ],
  "holdings": [
    {
      "cat": "AI / Semiconductors",
      "rot": {
        "w": "LEADING"
      },
      "pos": [
        {
          "t": "SMH",
          "n": "SMH",
          "pct": 9.9,
          "st": "Owned",
          "cv": "Strong",
          "ty": "Core",
          "own": "p,s",
          "lock": "",
          "fresh": false,
          "cd": "flat",
          "cdNote": "No recent change.",
          "nr": "Core hold \u2014 Lee-endorsed, leading; ride it.",
          "dr": [
            [
              "Lee \u00b7 ai_complex, semiconductors, long_duration_growth"
            ]
          ],
          "be": "\u2014"
        },
        {
          "t": "MAGS",
          "n": "MAGS",
          "pct": 9.09,
          "st": "Owned",
          "cv": "Strong",
          "ty": "Core",
          "own": "p,s",
          "lock": "",
          "fresh": false,
          "cd": "flat",
          "cdNote": "No recent change.",
          "nr": "Core hold \u2014 Lee-endorsed, leading; ride it.",
          "dr": [
            [
              "Lee \u00b7 ai_complex, long_duration_growth, global_exporter"
            ]
          ],
          "be": "\u2014"
        },
        {
          "t": "NVDA",
          "n": "NVDA",
          "pct": 6.73,
          "st": "Owned",
          "cv": "Strong",
          "ty": "Core",
          "own": "p,s",
          "lock": "",
          "fresh": false,
          "cd": "flat",
          "cdNote": "No recent change.",
          "nr": "Core hold \u2014 Lee-endorsed, leading; ride it.",
          "dr": [
            [
              "Lee \u00b7 ai_complex, semiconductors, long_duration_growth, global_exporter"
            ]
          ],
          "be": "\u2014"
        },
        {
          "t": "MU",
          "n": "MU",
          "pct": 2.0,
          "st": "Owned",
          "cv": "Strong",
          "ty": "Tactical",
          "own": "s",
          "lock": "",
          "fresh": false,
          "cd": "flat",
          "cdNote": "No recent change.",
          "nr": "Hold \u2014 parabolic; do NOT trim on the move, only on a named break (your rule).",
          "dr": [
            [
              "Lee \u00b7 ai_complex, semiconductors"
            ]
          ],
          "be": "\u2014"
        },
        {
          "t": "AVGO",
          "n": "AVGO",
          "pct": 3.5,
          "st": "Owned",
          "cv": "\u2014",
          "ty": "Tactical",
          "own": "p,s",
          "lock": "",
          "fresh": false,
          "cd": "flat",
          "cdNote": "No recent change.",
          "nr": "Core hold but undocumented \u2014 give me a line.",
          "dr": [
            [
              "no documented thesis"
            ]
          ],
          "be": "\u2014"
        },
        {
          "t": "ANET",
          "n": "ANET",
          "pct": 0.29,
          "st": "Owned",
          "cv": "Promising",
          "ty": "Tactical",
          "own": "s",
          "lock": "",
          "fresh": false,
          "cd": "flat",
          "cdNote": "No recent change.",
          "nr": "Core hold \u2014 source-endorsed, leading; ride it.",
          "dr": [
            [
              "no documented thesis"
            ]
          ],
          "be": "\u2014"
        }
      ]
    },
    {
      "cat": "Quality core",
      "rot": {
        "w": "IN LINE"
      },
      "pos": [
        {
          "t": "GRNY",
          "n": "GRNY",
          "pct": 5.0,
          "st": "Owned",
          "cv": "Strong",
          "ty": "Core",
          "own": "p,s",
          "lock": "",
          "fresh": false,
          "cd": "flat",
          "cdNote": "No recent change.",
          "nr": "Core hold \u2014 Lee-endorsed, leading; ride it.",
          "dr": [
            [
              "Lee \u00b7 ai_complex"
            ]
          ],
          "be": "\u2014"
        }
      ]
    },
    {
      "cat": "Financials",
      "rot": {
        "w": "LAGGING"
      },
      "pos": [
        {
          "t": "XLF",
          "n": "XLF",
          "pct": 3.0,
          "st": "Owned",
          "cv": "Promising",
          "ty": "Tactical",
          "own": "p",
          "lock": "",
          "fresh": false,
          "cd": "up",
          "cdNote": "05-28 fundstrat_bible favorable_shift",
          "nr": "Catch-up \u2014 Lee-endorsed laggard; favorable entry, no rush.",
          "dr": [
            [
              "Lee \u00b7 financials, cyclicals"
            ]
          ],
          "be": "\u2014"
        }
      ]
    },
    {
      "cat": "Nuclear",
      "rot": {
        "w": "LAGGING"
      },
      "pos": [
        {
          "t": "LEU",
          "n": "LEU",
          "pct": 1.5,
          "st": "Owned",
          "cv": "Promising",
          "ty": "Core",
          "own": "s",
          "lock": "\ud83d\udd12",
          "fresh": false,
          "cd": "flat",
          "cdNote": "No recent change.",
          "nr": "Hold light \u2014 burned sleeve; watch for YOUR re-entry trigger, no add on a source call.",
          "dr": [
            [
              "Meridian \u00b7 critical_minerals, nuclear, uranium"
            ]
          ],
          "be": "\u2014"
        },
        {
          "t": "UUUU",
          "n": "UUUU",
          "pct": 0.8,
          "st": "Owned",
          "cv": "Mixed",
          "ty": "Tactical",
          "own": "s",
          "lock": "",
          "fresh": false,
          "cd": "down",
          "cdNote": "05-28 fundstrat_bible new_bottom5",
          "nr": "Hold light \u2014 burned sleeve + cross-source split (fundstrat_bible vs meridian); watch for YOUR re-entry trigger, no add on a source call.",
          "dr": [
            [
              "Meridian \u00b7 critical_minerals, uranium"
            ]
          ],
          "be": "\u2014"
        }
      ]
    },
    {
      "cat": "Critical minerals",
      "rot": {
        "w": "LAGGING"
      },
      "pos": [
        {
          "t": "MP",
          "n": "MP",
          "pct": 1.2,
          "st": "Owned",
          "cv": "Promising",
          "ty": "Tactical",
          "own": "s",
          "lock": "",
          "fresh": false,
          "cd": "flat",
          "cdNote": "No recent change.",
          "nr": "Hold light \u2014 burned sleeve; watch for YOUR re-entry trigger, no add on a source call.",
          "dr": [
            [
              "Meridian \u00b7 critical_minerals, rare_earth"
            ]
          ],
          "be": "\u2014"
        }
      ]
    },
    {
      "cat": "Crypto",
      "rot": {
        "w": "TURNING DOWN"
      },
      "pos": [
        {
          "t": "BMNR",
          "n": "BMNR",
          "pct": 2.5,
          "st": "Owned",
          "cv": "Mixed",
          "ty": "Core",
          "own": "s",
          "lock": "\ud83d\udd12",
          "fresh": false,
          "cd": "flat",
          "cdNote": "05-28 fundstrat_daily bottom_in vs 05-28 fundstrat_daily unfavorable_shift \u2014 net flat",
          "nr": "Hold light \u2014 burned sleeve + cross-source split (fundstrat_daily); watch for YOUR re-entry trigger, no add on a source call.",
          "dr": [
            [
              "operator \u00b7 crypto, eth"
            ]
          ],
          "be": "\u2014"
        },
        {
          "t": "IBIT",
          "n": "IBIT",
          "pct": 1.5,
          "st": "Owned",
          "cv": "Promising",
          "ty": "Core",
          "own": "p",
          "lock": "\ud83d\udd12",
          "fresh": false,
          "cd": "up",
          "cdNote": "05-28 fundstrat_daily bottom_in",
          "nr": "Hold light \u2014 burned sleeve; watch for YOUR re-entry trigger, no add on a source call.",
          "dr": [
            [
              "operator \u00b7 crypto"
            ]
          ],
          "be": "\u2014"
        }
      ]
    },
    {
      "cat": "Electrification",
      "rot": {
        "w": "IN LINE"
      },
      "pos": [
        {
          "t": "VOLT",
          "n": "VOLT",
          "pct": 1.0,
          "st": "Owned",
          "cv": "Promising",
          "ty": "Tactical",
          "own": "s",
          "lock": "",
          "fresh": false,
          "cd": "flat",
          "cdNote": "No recent change.",
          "nr": "Core hold \u2014 operator-endorsed, leading; ride it. You're underweight to conviction here \u2014 the gap is the flag.",
          "dr": [
            [
              "operator \u00b7 nuclear, ai_complex"
            ]
          ],
          "be": "\u2014"
        }
      ]
    },
    {
      "cat": "Other holdings",
      "rot": {
        "w": ""
      },
      "pos": [
        {
          "t": "ITA",
          "n": "ITA",
          "pct": 0.6,
          "st": "Owned",
          "cv": "Promising",
          "ty": "Tactical",
          "own": "s",
          "lock": "",
          "fresh": true,
          "cd": "up",
          "cdNote": "05-28 fundstrat_daily breakout",
          "nr": "Core hold \u2014 source-endorsed, leading; ride it.",
          "dr": [
            [
              "no documented thesis"
            ]
          ],
          "be": "\u2014"
        },
        {
          "t": "AMZN",
          "n": "AMZN",
          "pct": 2.0,
          "st": "Owned",
          "cv": "\u2014",
          "ty": "Tactical",
          "own": "p",
          "lock": "",
          "fresh": false,
          "cd": "flat",
          "cdNote": "No recent change.",
          "nr": "Core hold but undocumented \u2014 give me a line.",
          "dr": [
            [
              "no documented thesis"
            ]
          ],
          "be": "\u2014"
        },
        {
          "t": "COST",
          "n": "COST",
          "pct": 1.8,
          "st": "Owned",
          "cv": "\u2014",
          "ty": "Tactical",
          "own": "p",
          "lock": "",
          "fresh": false,
          "cd": "flat",
          "cdNote": "No recent change.",
          "nr": "Core hold but undocumented \u2014 give me a line.",
          "dr": [
            [
              "no documented thesis"
            ]
          ],
          "be": "\u2014"
        },
        {
          "t": "MSFT",
          "n": "MSFT",
          "pct": 2.2,
          "st": "Owned",
          "cv": "\u2014",
          "ty": "Tactical",
          "own": "p,s",
          "lock": "",
          "fresh": false,
          "cd": "flat",
          "cdNote": "No recent change.",
          "nr": "Core hold but undocumented \u2014 give me a line.",
          "dr": [
            [
              "no documented thesis"
            ]
          ],
          "be": "\u2014"
        }
      ]
    }
  ],
  "rotation": [
    {
      "subject": "SMH",
      "label": "LEADING",
      "rel_1m": 0.08,
      "rel_3m": 0.37,
      "abs_3m": 0.47,
      "rel_3m_vs_smh": 0.0,
      "note": "LEADING +37%/3M vs mkt"
    },
    {
      "subject": "IGV",
      "label": "LEADING",
      "rel_1m": 0.2,
      "rel_3m": 0.14,
      "abs_3m": 0.24,
      "rel_3m_vs_smh": -0.23,
      "note": "LEADING +14%/3M vs mkt"
    },
    {
      "subject": "GRNY",
      "label": "IN LINE",
      "rel_1m": 0.0,
      "rel_3m": 0.0,
      "abs_3m": 0.1,
      "rel_3m_vs_smh": -0.37,
      "note": "IN LINE +0%/3M vs mkt"
    },
    {
      "subject": "VOLT",
      "label": "IN LINE",
      "rel_1m": -0.06,
      "rel_3m": 0.01,
      "abs_3m": 0.05,
      "rel_3m_vs_smh": -0.36,
      "note": "IN LINE +1%/3M vs mkt"
    },
    {
      "subject": "IBIT",
      "label": "TURNING DOWN",
      "rel_1m": -0.09,
      "rel_3m": 0.1,
      "abs_3m": 0.18,
      "rel_3m_vs_smh": -0.27,
      "note": "TURNING DOWN +10%/3M vs mkt"
    },
    {
      "subject": "XLF",
      "label": "LAGGING",
      "rel_1m": -0.03,
      "rel_3m": -0.1,
      "abs_3m": -0.02,
      "rel_3m_vs_smh": -0.47,
      "note": "LAGGING -10%/3M vs mkt"
    },
    {
      "subject": "REMX",
      "label": "LAGGING",
      "rel_1m": -0.02,
      "rel_3m": -0.1,
      "abs_3m": 0.01,
      "rel_3m_vs_smh": -0.47,
      "note": "LAGGING -10%/3M vs mkt"
    },
    {
      "subject": "URA",
      "label": "LAGGING",
      "rel_1m": -0.08,
      "rel_3m": -0.17,
      "abs_3m": -0.12,
      "rel_3m_vs_smh": -0.54,
      "note": "LAGGING -17%/3M vs mkt"
    },
    {
      "subject": "GDX",
      "label": "LAGGING",
      "rel_1m": -0.1,
      "rel_3m": -0.33,
      "abs_3m": -0.2,
      "rel_3m_vs_smh": -0.7,
      "note": "LAGGING -33%/3M vs mkt"
    }
  ],
  "macro": {
    "line": "10Y 4.45% (-1bp 5d) \u00b7 2s10s +46bp (+1bp 5d) \u00b7 DXY 99.5 (flat 5d) \u00b7 30Y 4.98%",
    "regime": {
      "duration": "flat",
      "vol": "calm",
      "dollar": "neutral",
      "label": "duration_flat \u00b7 vol_calm \u00b7 dollar_neutral"
    },
    "alerts": [],
    "implications": []
  },
  "catalysts": [],
  "questions": [],
  "research": {}
};

// ───────────────────────────────────────────────────────────────
// feed_to_cockpit seam — INLINED from feed_to_cockpit.js (node-tested there).
// Keep the two in sync; this is the runtime copy for the self-contained artifact.
// Pure functions: Contract-C FEED -> the display shapes this cockpit renders.
// ───────────────────────────────────────────────────────────────
const LABEL_COLOR = {
  "LEADING":"green", "IN LINE":"blue", "TURNING UP":"amber", "SOFTENING":"amber",
  "TURNING DOWN":"red", "LAGGING":"red", "HEDGE":"gray",
};
const HEDGE_SLEEVES = new Set(["GDX","GLD","SIL","WPM"]);
const SLEEVE_DISPLAY = {
  "SMH":"AI / semis (SMH)", "IGV":"Software (IGV)", "GRNY":"Quality core (GRNY)",
  "VOLT":"Electrification (VOLT)", "IBIT":"Crypto (IBIT)", "XLF":"Financials (XLF)",
  "REMX":"Critical minerals (REMX)", "URA":"Nuclear (URA)", "GDX":"Gold hedge (GDX)",
};
const FRESH_URG_LABEL = {
  "act":"early signal — act within days", "watch":"watch — wait for your trigger",
};
const PRETTY_EVENT = {
  breakout:"Fresh breakout — cleared a downtrend", new_pick:"Newly named a source pick",
  new_top5:"Newly added to the Fundstrat Top-5", upgrade:"Source upgrade", bottom_in:"Source calling a bottom",
};
function colorFor(label){ return LABEL_COLOR[label] || "gray"; }
function overlayLabel(s){
  if (HEDGE_SLEEVES.has(s.subject)) return "HEDGE";
  const r1=s.rel_1m, r3=s.rel_3m;
  if (s.label==="IN LINE" && typeof r1==="number" && typeof r3==="number" && r1<-0.04 && r3>=-0.02) return "SOFTENING";
  return s.label;
}
function relString(r3){ if (typeof r3!=="number"||r3===0) return "≈ market"; const p=Math.round(r3*100); return `${p>0?"+":""}${p} vs mkt (3M)`; }
function rotationRow(s){ const w=overlayLabel(s); return { s:SLEEVE_DISPLAY[s.subject]||s.subject, w, c:colorFor(w), n:relString(s.rel_3m), note:s.note||"" }; }
function macroView(m){ const r=m.regime||{}, a=m.alerts||[]; return { line:m.line||"", tape:r.label||"", impl:m.implications||[], note:a.length?`${a.length} macro alert(s) firing`:"No macro alerts firing." }; }
function groupPct(pos){ const s=pos.reduce((a,p)=>a+(typeof p.pct==="number"?p.pct:0),0); return Math.round(s); }
function holdingGroup(h){ const w=(h.rot&&h.rot.w)||""; return { cat:`${h.cat} (~${groupPct(h.pos)}%)`, rot:{w,c:colorFor(w)}, pos:h.pos }; }
function freshSignalRow(sig){ return { t:sig.ticker, n:sig.ticker, urg:sig.urgency, urgLabel:FRESH_URG_LABEL[sig.urgency]||sig.urgency, when:sig.when||"", what:PRETTY_EVENT[sig.what]||sig.what||"", why:sig.why||"", detail:sig.detail||"" }; }
function heroView(hero){ const h=(hero&&hero.hero)||{}, ny=(hero&&hero.needs_you)||{}; return { leadCount:h.count||0, leadNames:h.names||[], leadingSleeves:h.leading_sleeves||[], needsCount:ny.count||0, needsItems:ny.items||[] }; }
function stamp(feed){
  const entries=(feed.staleness&&feed.staleness.entries)||[];
  const bySrc=Object.fromEntries(entries.map(e=>[e.source,e.date]));
  const LABEL={fundstrat_bible:"bible", uw_price:"rotation", portfolio:"book"};
  const parts=[]; for (const src of ["fundstrat_bible","uw_price","portfolio"]) if (bySrc[src]) parts.push(`${LABEL[src]} ${bySrc[src]}`);
  return `as of ${(feed.generated_at||"").slice(0,10)}${parts.length?` · sources: ${parts.join(", ")}`:""}`;
}
// ── ⑦b Actions panel view-model (the prioritized "what to do today" rows) ──
const ACTION_KIND_META = {
  buy_now:         { icon:"⏳", label:"Buy trigger",    c:C.amber },
  reentry_zone:    { icon:"⏳", label:"Re-entry zone",  c:C.amber },
  monitor_reentry: { icon:"🔒", label:"Re-entry watch", c:C.blue  },
  red_gate:        { icon:"🔴", label:"RED gate",       c:C.red   },
  macro_alert:     { icon:"🌐", label:"Macro alert",    c:C.amber },
  watch_entry:     { icon:"👁", label:"Watch",          c:C.blue  },
  stale_critical:  { icon:"⚠️", label:"Stale source",   c:C.dim   },
  synthesis:       { icon:"🧠", label:"Synthesis",      c:C.blue  },
};
const CONF_META = {
  High:     { c:C.green, label:"High" },
  Moderate: { c:C.amber, label:"Moderate" },
  Low:      { c:C.faint, label:"Low" },
};
function actionRow(a){
  const m = ACTION_KIND_META[a.kind] || { icon:"•", label:a.kind, c:C.dim };
  const cf = CONF_META[a.confidence] || { c:C.dim, label:a.confidence };
  return { rank:a.rank, kind:a.kind, icon:m.icon, kindLabel:m.label, c:m.c,
           ticker:a.ticker||"", what:a.what||"", confLabel:cf.label, confColor:cf.c,
           yourMove:a.your_move||"", why:a.why||"", gatePreview:(a.gate&&a.gate.preview)||"" };
}
// ── Tier-1 view-model: heartbeat (layer run-status strip) ──
const HB_STATUS = { ok:{c:C.green,label:"ok"}, stale:{c:C.amber,label:"stale"}, down:{c:C.red,label:"down"} };
function heartbeatRow(h){ const s=HB_STATUS[h.status]||{c:C.gray,label:h.status}; return { layer:h.layer, c:s.c, statusLabel:s.label, lastRun:h.last_run||"", note:h.note||"" }; }
function toCockpit(feed){
  return {
    generatedAt: feed.generated_at||"", stamp: stamp(feed),
    macro: macroView(feed.macro||{}),
    rotation: (feed.rotation||[]).map(rotationRow),
    holdings: (feed.holdings||[]).map(holdingGroup),
    actions: (feed.actions||[]).map(actionRow),
    heartbeat: (feed.heartbeat||[]).map(heartbeatRow),
    synthesis: feed.synthesis||{},
    freshSignals: (feed.fresh_signals||[]).map(freshSignalRow),
    hero: heroView(feed.hero||{}),
    catalysts: feed.catalysts||[], questions: feed.questions||[], research: feed.research||{},
  };
}

// ── cockpit-curated content (NOT engine-derived) ──────────────────────────
// The FEED drives everything data-derived; these three are curated here until
// the feed produces them. Integration point: swap CURATED.X → VM.X once the
// feed emits catalysts/questions/research. Each section is labeled below.
const CURATED = {
  questions: [
    { q:"Want a number alongside the conviction word, or is the word enough?", d:"5/29", tag:"system design" },
    { q:"Account-level holdings view — add it, or is aggregate + Parents/SKB enough?", d:"5/29", tag:"system design" },
  ],
  research: {
    pending: [
      { r:"Deepen the 'why' on priority holdings with sourced rationale (Live Theses / Decisions Log / FS bible) — e.g. XLF's actual Fundstrat reasoning.", pr:"high" },
      { r:"Per-name live prices + day moves on the holdings rows (currently % is from the book snapshot).", pr:"med" },
      { r:"Critical-minerals watch universe — investable names around the federal money-flow.", pr:"med" },
    ],
    done: [
      { r:"Rotation engine is LIVE.", f:"AI engine leads everything (+47%/3M); software just caught up; the burned 🔒 sleeves all lag with none turning up → no re-entry signal, the light sizing is confirmed by the tape." },
      { r:"GRNJ + VOLT identified.", f:"GRNJ = Fundstrat Granny Shots small/mid-cap (pairs with GRNY). VOLT = Tema Electrification ETF (power/grid/nuclear). Both de-flagged and seeded." },
    ],
  },
  catalysts: [
    { d:"Aug 17", e:"Fabrinet (FN) earnings", note:"your AI/optical buy-on-pullback name — watch for the setup (~$580–620)" },
    { d:"~Aug", e:"OGE Form 278-T quarterly filing", note:"Trump-trade-pattern signal you track" },
  ],
};

// ── presentational (preserved from v4) ──
function Pill({ label, color, title }) {
  return (
    <span title={title} style={{ display:"inline-flex", alignItems:"center", gap:6, padding:"2px 9px", borderRadius:99,
      fontSize:11, fontFamily:mono, color, border:`1px solid ${color}44`, background:`${color}14`, whiteSpace:"nowrap" }}>
      <span style={{ width:6, height:6, borderRadius:99, background:color }} />{label}
    </span>
  );
}
function Section({ id, title, icon, badge, badgeColor, children, openMap, setOpen, defaultOpen=true }) {
  const isOpen = openMap[id] === undefined ? defaultOpen : openMap[id];
  return (
    <div style={{ marginTop:14 }}>
      <div onClick={()=>setOpen(s=>({...s,[id]: !(s[id]===undefined?defaultOpen:s[id])}))}
        style={{ display:"flex", alignItems:"center", gap:9, cursor:"pointer", padding:"7px 2px", userSelect:"none" }}>
        <span style={{ color:C.faint, fontFamily:mono, fontSize:11, transform:isOpen?"none":"rotate(-90deg)", transition:"transform .15s" }}>▾</span>
        <span style={{ fontSize:14 }}>{icon}</span>
        <span style={{ fontSize:13.5, fontWeight:700, color:C.text }}>{title}</span>
        {badge!==undefined && badge!==null && (
          <span style={{ fontFamily:mono, fontSize:11, color:badgeColor||C.faint, border:`1px solid ${(badgeColor||C.faint)}55`, borderRadius:99, padding:"1px 8px" }}>{badge}</span>
        )}
      </div>
      {isOpen && <div style={{ marginTop:4 }}>{children}</div>}
    </div>
  );
}
const card = { background:C.panel, border:`1px solid ${C.line}`, borderRadius:11, padding:"12px 14px" };
const muted = { color:C.dim, fontSize:12.5 };

export default function ConvictionCockpit({ feed = FEED } = {}) {
  const VM = toCockpit(feed);   // default = embedded golden feed; pass a live feed at runtime
  const R = (VM.research && ((VM.research.pending||[]).length || (VM.research.done||[]).length))
    ? VM.research : CURATED.research;   // live Research Queue when present, else curated fallback
  const [open, setOpen] = useState({});
  const [posOpen, setPosOpen] = useState({});
  const [collapsed, setCollapsed] = useState({});
  const [view, setView] = useState("agg");
  const [legend, setLegend] = useState(false);
  const dirColor = (d)=> d==="up"?C.green : d==="down"?C.red : C.dim;
  const ownerFilter = (own) => view==="agg" ? true : view==="parents" ? own.includes("p") : own.includes("s");

  return (
    <div style={{ background:C.bg, color:C.text, fontFamily:sans, minHeight:"100%", padding:"18px 13px 52px", lineHeight:1.45 }}>
      <div style={{ maxWidth:840, margin:"0 auto" }}>

        {/* HEADER */}
        <div style={{ display:"flex", alignItems:"baseline", justifyContent:"space-between", flexWrap:"wrap", gap:8 }}>
          <div style={{ fontSize:20, fontWeight:700, letterSpacing:-0.3 }}>Conviction Cockpit</div>
          <div style={{ fontFamily:mono, fontSize:11.5, color:C.faint }}>{VM.stamp}</div>
        </div>

        {/* HEARTBEAT — layer run-status strip (Tier-1: see the machine ran) */}
        {VM.heartbeat.length>0 && (
          <div style={{ marginTop:10, display:"flex", flexWrap:"wrap", gap:6, alignItems:"center" }}>
            <span style={{ fontFamily:mono, fontSize:10, color:C.faint, marginRight:2 }}>LAYERS</span>
            {VM.heartbeat.map((h,i)=>(
              <span key={i} title={`${h.note}${h.lastRun?` · last ${h.lastRun}`:""}`}
                style={{ display:"inline-flex", alignItems:"center", gap:5, padding:"2px 8px", borderRadius:99,
                  fontSize:10.5, fontFamily:mono, color:h.c, border:`1px solid ${h.c}44`, background:`${h.c}12`, whiteSpace:"nowrap" }}>
                <span style={{ width:6, height:6, borderRadius:99, background:h.c }} />{h.layer}{h.statusLabel!=="ok"?` · ${h.statusLabel}`:""}
              </span>
            ))}
          </div>
        )}

        {/* HERO — needs-you banner (engine ⑧) */}
        {(() => {
          const h = VM.hero;
          const need = h.needsCount > 0;
          const sleeves = h.leadingSleeves.map(s => SLEEVE_DISPLAY[s] || s).join(", ");
          return (
            <div style={{ marginTop:12, ...card, borderColor: need? C.amber+"66":C.green+"44", background: need? C.amber+"10":C.green+"0c", display:"flex", alignItems:"center", gap:12 }}>
              <div style={{ fontFamily:mono, fontSize:26, fontWeight:700, color: need?C.amber:C.green, lineHeight:1 }}>{need? h.needsCount : "✓"}</div>
              <div>
                <div style={{ fontSize:13.5, fontWeight:600 }}>{need ? `${h.needsCount} thing${h.needsCount>1?"s":""} need${h.needsCount>1?"":"s"} you${h.needsItems.length?`: ${h.needsItems.map(it=>it.detail).join(", ")}`:""}` : "Nothing needs you — all quiet"}</div>
                <div style={muted}>{need ? "Time-sensitive items are in Today's actions below." : "No fresh actions."} <span style={{ color:C.faint }}>{h.leadCount} name{h.leadCount===1?"":"s"} on strong footing{sleeves?` · leading: ${sleeves}`:""}.</span></div>
              </div>
            </div>
          );
        })()}

        {/* ACTIONS — prioritized "what to do today" (engine ⑦b actions block) */}
        <Section id="actions" title="Today's actions" icon="🟢" badge={VM.actions.length?`${Math.min(VM.actions.length,5)}${VM.actions.length>5?` of ${VM.actions.length}`:""}`:"0 live"} badgeColor={VM.actions.length?C.amber:C.faint} openMap={open} setOpen={setOpen}>
          <div style={{ fontSize:11, color:C.faint, fontFamily:mono, marginBottom:8 }}>PRIORITIZED — confidence-led. Gate badges are provisional; the real 🟢/🟡/🔴 runs when you act on it in chat.</div>
          {VM.actions.length===0 && <div style={{ ...card, fontSize:12, color:C.faint }}>Nothing to act on right now — no live buy-trigger, alert, or flag.</div>}
          {VM.actions.slice(0,5).map((a)=>{
            const key="act"+a.rank+(a.ticker||a.kind), isO=posOpen[key];
            return (
              <div key={key} style={{ ...card, marginBottom:8, borderColor:a.c+"44", background:a.c+"0a" }}>
                <div onClick={()=>setPosOpen(st=>({...st,[key]:!st[key]}))} style={{ cursor:a.why?"pointer":"default" }}>
                  <div style={{ display:"flex", alignItems:"baseline", gap:8, flexWrap:"wrap" }}>
                    <span style={{ fontFamily:mono, fontSize:11, color:C.faint }}>#{a.rank}</span>
                    {a.ticker && <span style={{ fontFamily:mono, fontWeight:700, fontSize:13.5, color:C.text }}>{a.ticker}</span>}
                    <span style={{ fontSize:12.5, fontWeight:600, color:C.text }}>{a.what}</span>
                  </div>
                  <div style={{ marginTop:7, display:"flex", alignItems:"center", gap:7, flexWrap:"wrap" }}>
                    <span style={{ fontFamily:mono, fontSize:11, color:a.c, border:`1px solid ${a.c}55`, borderRadius:99, padding:"1px 8px" }}>{a.icon} {a.kindLabel}</span>
                    <span style={{ fontFamily:mono, fontSize:11, color:a.confColor, border:`1px solid ${a.confColor}55`, borderRadius:99, padding:"1px 8px" }}>conf: {a.confLabel}</span>
                    {a.gatePreview && <span style={{ fontFamily:mono, fontSize:11, color:C.dim, border:`1px solid ${C.line}`, borderRadius:99, padding:"1px 8px", background:C.panel2 }}>{a.gatePreview}</span>}
                  </div>
                  <div style={{ marginTop:8, fontSize:12.5, color:C.text }}><span style={{ color:C.dim, fontWeight:600 }}>Your move:</span> {a.yourMove}</div>
                  {a.why && (
                    <div style={{ marginTop:7, display:"flex", justifyContent:"flex-end" }}>
                      <span style={{ fontSize:11, color:a.c }}>{isO?"hide why ▲":"why ▾"}</span>
                    </div>
                  )}
                </div>
                {isO && a.why && (
                  <div style={{ marginTop:8, paddingTop:8, borderTop:`1px solid ${C.line}`, ...muted }}>
                    {a.why}
                    <div style={{ marginTop:8, fontFamily:mono, fontSize:10, color:C.faint }}>{VM.stamp} · not a trade — you decide, you size · drill in chat to run the gate</div>
                  </div>
                )}
              </div>
            );
          })}
          {VM.actions.length>5 && <div style={{ fontSize:11.5, color:C.faint, fontFamily:mono, marginTop:2 }}>+{VM.actions.length-5} more lower-priority action{VM.actions.length-5>1?"s":""} (not shown)</div>}
        </Section>

        {/* SYNTHESIS — today's read / state-of-play (Daily Synthesis; Tier-1) */}
        <Section id="synthesis" title="Today's read — synthesis" icon="🧠" badge={VM.synthesis&&VM.synthesis.date?VM.synthesis.date:""} badgeColor={C.blue} openMap={open} setOpen={setOpen} defaultOpen={true}>
          {(() => {
            const s = VM.synthesis || {};
            const empty = !s.state_of_play && !s.delta && !(s.hanging&&s.hanging.length);
            if (empty) return <div style={{ ...card, fontSize:12, color:C.faint }}>No synthesis loaded — run a Fresh Run; the Daily Synthesis feeds this panel.</div>;
            return (
              <div style={card}>
                {s.state_of_play && <div style={{ fontSize:12.5, color:C.text }}><span style={{ color:C.dim, fontWeight:600 }}>State of play:</span> {s.state_of_play}</div>}
                {s.delta && <div style={{ marginTop:7, fontSize:12.5, color:C.dim }}><span style={{ color:C.dim, fontWeight:600 }}>Last 24–48h:</span> {s.delta}</div>}
                {s.hanging && s.hanging.length>0 && (
                  <div style={{ marginTop:8 }}>
                    <div style={{ fontFamily:mono, fontSize:10, color:C.faint, textTransform:"uppercase", letterSpacing:0.5, marginBottom:4 }}>Hanging</div>
                    {s.hanging.map((h,i)=>(<div key={i} style={{ ...muted, marginBottom:3 }}>• {h}</div>))}
                  </div>
                )}
                <div style={{ marginTop:9, fontFamily:mono, fontSize:10, color:C.faint }}>{s.source||"Daily Synthesis"}{s.date?` · ${s.date}`:""} · scout/librarian — state, not actions</div>
              </div>
            );
          })()}
        </Section>

        {/* HOLDINGS (from FEED) */}
        <Section id="holdings" title="Holdings" icon="📊" openMap={open} setOpen={setOpen} defaultOpen={true}>
          <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", flexWrap:"wrap", gap:8, marginBottom:8 }}>
            <div style={{ display:"flex", gap:4, background:C.panel, border:`1px solid ${C.line}`, borderRadius:8, padding:3 }}>
              {[["agg","Aggregate"],["parents","Parents"],["skb","SKB"]].map(([k,l])=>(
                <button key={k} onClick={()=>setView(k)} style={{ cursor:"pointer", border:"none", borderRadius:6, padding:"5px 11px", fontSize:11.5, fontFamily:mono, background: view===k?C.panel3:"transparent", color: view===k?C.text:C.faint }}>{l}</button>
              ))}
            </div>
            <button onClick={()=>setLegend(v=>!v)} style={{ cursor:"pointer", background:"transparent", border:`1px solid ${C.line}`, borderRadius:8, padding:"5px 10px", fontSize:11, fontFamily:mono, color:C.dim }}>{legend?"hide key":"key ▾"}</button>
          </div>

          {legend && (
            <div style={{ ...card, marginBottom:8, fontSize:11.5 }}>
              <div style={{ color:C.faint, fontFamily:mono, marginBottom:6 }}>CONVICTION = quality / confidence → guides how big a position CAN be (a ceiling, not a target)</div>
              {Object.entries(CONV).filter(([k])=>k!=="—").map(([k,v])=>(
                <div key={k} style={{ display:"flex", gap:9, alignItems:"center", marginBottom:4 }}>
                  <span style={{ minWidth:78 }}><Pill label={k} color={v.c} /></span><span style={muted}>{v.q}</span>
                </div>
              ))}
              <div style={{ marginTop:7, color:C.faint }}>TYPE: Core (durable, can be large) · Tactical (catalyst/cycle, has an exit) · Speculative (small, capped) · Hedge (protection). 🔒 = add only on a strong signal. <b style={{color:C.dim}}>▲/▼ on a row</b> = conviction-direction just changed — event-driven (a source call, a catalyst), NOT daily price; tap for why. No arrow = steady. The colored badge on a <b style={{color:C.dim}}>sleeve header</b> = live price rotation vs market. 🔔 = a fresh buy-signal.</div>
            </div>
          )}

          {view!=="agg" && (
            <div style={{ ...card, marginBottom:8, fontSize:11.5, color:C.faint }}>
              Showing names held by <b style={{ color:C.dim }}>{view==="parents"?"Parents":"SKB"}</b>. Exact per-owner $/% split isn't in the book snapshot yet. (% shown are book-aggregate.)
            </div>
          )}

          {VM.holdings.map(group=>{
            const rows = group.pos.filter(p=>ownerFilter(p.own||""));
            if (!rows.length) return null;
            const isC = collapsed[group.cat];
            return (
              <div key={group.cat} style={{ marginBottom:10 }}>
                <div onClick={()=>setCollapsed(s=>({...s,[group.cat]:!s[group.cat]}))}
                  style={{ display:"flex", alignItems:"center", gap:8, cursor:"pointer", padding:"5px 2px", userSelect:"none", flexWrap:"wrap" }}>
                  <span style={{ color:C.faint, fontFamily:mono, fontSize:10.5, transform:isC?"rotate(-90deg)":"none", transition:"transform .15s" }}>▾</span>
                  <span style={{ fontSize:12, fontWeight:600, color:C.dim }}>{group.cat}</span>
                  {group.rot && group.rot.w && <Pill label={group.rot.w} color={COLOR_HEX[group.rot.c]||C.gray} title="live sleeve rotation vs market" />}
                </div>
                {!isC && (
                  <div style={{ marginTop:5, border:`1px solid ${C.line}`, borderRadius:10, overflow:"hidden", background:C.panel }}>
                    {rows.map((p,i)=>{
                      const key=group.cat+p.t, isO=posOpen[key], cv=CONV[p.cv]||CONV["—"];
                      return (
                        <div key={key} style={{ borderTop: i?`1px solid ${C.line}`:"none" }}>
                          <div onClick={()=>setPosOpen(s=>({...s,[key]:!s[key]}))}
                            style={{ display:"grid", gridTemplateColumns:"80px 1fr auto", alignItems:"center", gap:10, padding:"10px 13px", cursor:"pointer", background:isO?C.panel2:"transparent" }}>
                            <div>
                              <div style={{ fontFamily:mono, fontWeight:700, fontSize:13, color:C.text }}>{p.t}</div>
                              <div style={{ fontFamily:mono, fontSize:10, color:C.faint }}>{p.pct>0?p.pct.toFixed(2)+"%":""}</div>
                            </div>
                            <div style={{ minWidth:0 }}>
                              <div style={{ fontSize:11.5, color:C.faint, whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>{p.n}</div>
                              {p.nr && <div style={{ fontSize:12.5, color:C.text, marginTop:2, whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>{p.nr}</div>}
                              <div style={{ display:"flex", gap:6, marginTop:5, flexWrap:"wrap", alignItems:"center" }}>
                                <Pill label={p.cv} color={cv.c} title={cv.q} />
                                <span style={{ fontFamily:mono, fontSize:10.5, color:C.faint }}>{p.ty}</span>
                                {(p.cd==="up"||p.cd==="down") && <span title="conviction-direction — the case for owning it recently changed (tap for why)" style={{ fontFamily:mono, fontSize:12.5, color:dirColor(p.cd) }}>{p.cd==="up"?"▲":"▼"}</span>}
                                {p.lock && <span style={{ fontSize:10.5 }} title="add only on a strong signal">🔒</span>}
                                {p.fresh && <span style={{ fontSize:10.5 }} title="fresh buy-signal — see Today's actions">🔔</span>}
                              </div>
                            </div>
                            <span style={{ color:C.faint, fontSize:11, transform:isO?"rotate(180deg)":"none", transition:"transform .15s" }}>▾</span>
                          </div>
                          {isO && (
                            <div style={{ padding:"2px 15px 14px", background:C.panel2, fontSize:12.5 }}>
                              {p.nr && <div style={{ color:C.text, fontSize:13, fontWeight:600, margin:"9px 0 8px", lineHeight:1.4 }}>→ {p.nr}</div>}
                              <div style={{ color:cv.c, fontSize:11, margin:"4px 0 5px" }}>Conviction: <b>{p.cv}</b> — {cv.q}</div>
                              <div style={{ fontSize:11.5, margin:"2px 0 6px" }}>
                                <span style={{ color:dirColor(p.cd), fontFamily:mono }}>{p.cd==="up"?"▲ rising":p.cd==="down"?"▼ falling":"▬ flat"}</span>
                                <span style={{ color:C.dim }}> — {p.cdNote||"no recent change"}</span>
                              </div>
                              <div style={{ color:C.faint, fontFamily:mono, fontSize:10, textTransform:"uppercase", letterSpacing:0.5, margin:"9px 0 4px" }}>Why</div>
                              {(p.dr||[]).map((d,j)=>{ const has2=d.length>1; const w=has2?d[0]:null; const why=has2?d[1]:d[0];
                                return (<div key={j} style={{ marginBottom:5, ...muted }}>{w&&<span style={{ color:C.text, fontWeight:600 }}>{w}</span>}{w?" — ":""}{why}</div>); })}
                              {p.be && p.be!=="—" && (<>
                                <div style={{ color:C.faint, fontFamily:mono, fontSize:10, textTransform:"uppercase", letterSpacing:0.5, margin:"9px 0 4px" }}>What could break it</div>
                                <div style={muted}>{p.be}</div>
                              </>)}
                              <div style={{ color:C.faint, fontFamily:mono, fontSize:10, textTransform:"uppercase", letterSpacing:0.5, margin:"9px 0 4px" }}>Size posture</div>
                              <div style={muted}>Conviction supports <span style={{ color:C.text }}>{POSTURE[p.cv]} position</span> (you hold {p.pct>0?p.pct.toFixed(2)+"%":"a small amount"}). Guidance — a ceiling, not a target; you size at the moment.</div>
                              <div style={{ marginTop:10, fontFamily:mono, fontSize:10, color:C.faint }}>{VM.stamp}</div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </Section>

        {/* QUESTIONS (cockpit-curated; swap CURATED.questions → VM.questions when the feed emits them) */}
        <Section id="questions" title="Questions for you" icon="❓" badge={`${CURATED.questions.length}`} badgeColor={C.dim} openMap={open} setOpen={setOpen} defaultOpen={false}>
          {CURATED.questions.length===0 && <div style={{ ...card, fontSize:12, color:C.faint }}>No open questions.</div>}
          {CURATED.questions.map((x,i)=>(
            <div key={i} style={{ ...card, marginBottom:7 }}>
              <div style={{ fontSize:12.5, color:C.dim }}>{x.q}</div>
              <div style={{ marginTop:5, fontFamily:mono, fontSize:10.5, color:C.faint }}>{x.tag} · {x.d}</div>
            </div>
          ))}
        </Section>

        {/* MARKET READ — rotation + macro (from FEED) */}
        <Section id="market" title="Market read — rotation + macro" icon="🌐" openMap={open} setOpen={setOpen} defaultOpen={true}>
          <div style={{ ...card, marginBottom:8 }}>
            <div style={{ fontSize:11, color:C.faint, fontFamily:mono, marginBottom:8 }}>SLEEVE LEADERSHIP (relative strength vs market)</div>
            {VM.rotation.map((r,i)=>(
              <div key={i} style={{ display:"grid", gridTemplateColumns:"168px 116px 1fr", gap:10, alignItems:"center", padding:"5px 0", borderTop: i?`1px solid ${C.line}`:"none" }}>
                <span style={{ fontSize:12.5, color:C.text }}>{r.s}</span>
                <Pill label={r.w} color={COLOR_HEX[r.c]||C.gray} />
                <span style={{ fontSize:11.5, color:C.dim }}><span style={{ fontFamily:mono, color:C.faint }}>{r.n}</span> · {r.note}</span>
              </div>
            ))}
          </div>
          <div style={card}>
            <div style={{ fontSize:11, color:C.faint, fontFamily:mono, marginBottom:6 }}>MACRO BACKDROP</div>
            <div style={{ fontFamily:mono, fontSize:12, color:C.text }}>{VM.macro.line}</div>
            <div style={{ marginTop:6, ...muted }}>{VM.macro.tape}</div>
            <div style={{ marginTop:8 }}>
              {VM.macro.impl.length>0 ? VM.macro.impl.map((it,i)=>{
                const isArr=Array.isArray(it); const k=isArr?it[0]:null; const v=isArr?it[1]:it;
                return (<div key={i} style={{ ...muted, marginBottom:4 }}>→ {k&&<b style={{ color:C.dim }}>{k}</b>}{k?" — ":""}{v}</div>);
              }) : <div style={{ ...muted, color:C.faint }}>No notable macro implications on a calm regime.</div>}
            </div>
            <div style={{ marginTop:8, fontSize:11, color:C.faint, fontFamily:mono }}>{VM.macro.note}</div>
          </div>
        </Section>

        {/* RESEARCH — live Research Queue (R = VM.research when present, else curated) */}
        <Section id="research" title="Research" icon="🔬" openMap={open} setOpen={setOpen} defaultOpen={false}>
          <Section id="rpending" title="Pending — you prioritize" icon="⏳" badge={(R.pending||[]).length} badgeColor={C.blue} openMap={open} setOpen={setOpen}>
            {(R.pending||[]).length===0 && <div style={{ ...card, fontSize:12, color:C.faint }}>Nothing pending.</div>}
            {(R.pending||[]).map((x,i)=>{ const pr=x.priority||x.pr||""; return (
              <div key={i} style={{ ...card, marginBottom:7, display:"flex", gap:10, alignItems:"flex-start" }}>
                <span style={{ fontFamily:mono, fontSize:10, color: pr==="high"?C.amber:C.faint, marginTop:2, minWidth:34 }}>{pr}</span>
                <span style={{ fontSize:12.5, color:C.dim }}>{x.title||x.r}{x.note?` — ${x.note}`:""}</span>
              </div>
            ); })}
          </Section>
          <Section id="rdone" title="Completed — significant findings" icon="✅" badge={(R.done||[]).length} badgeColor={C.green} openMap={open} setOpen={setOpen} defaultOpen={false}>
            {(R.done||[]).map((x,i)=>(
              <div key={i} style={{ ...card, marginBottom:7, borderColor:C.green+"33" }}>
                <div style={{ fontSize:13, color:C.text }}>{x.title||x.r}</div>
                <div style={{ marginTop:5, ...muted }}>{x.finding||x.f}</div>
              </div>
            ))}
          </Section>
        </Section>

        {/* CATALYSTS (cockpit-curated; swap CURATED.catalysts → VM.catalysts when the feed emits them) */}
        <Section id="cats" title="Upcoming catalysts — near-term" icon="📅" badge={CURATED.catalysts.length} openMap={open} setOpen={setOpen} defaultOpen={false}>
          {CURATED.catalysts.map((x,i)=>(
            <div key={i} style={{ ...card, marginBottom:7, display:"flex", gap:12, alignItems:"baseline" }}>
              <span style={{ fontFamily:mono, fontSize:12, color:C.accent, minWidth:58 }}>{x.d}</span>
              <div><div style={{ fontSize:13, color:C.text }}>{x.e}</div><div style={muted}>{x.note}</div></div>
            </div>
          ))}
          <div style={{ fontSize:11, color:C.faint, marginTop:4 }}>Cockpit-curated — auto-population from the calendar sync follows.</div>
        </Section>

        <div style={{ marginTop:18, ...card, background:C.panel2, fontSize:12, color:C.dim }}>
          <span style={{ color:C.green, fontFamily:mono }}>● v5:</span> every section reads from one Contract-C FEED via the feed_to_cockpit seam. Engine-derived: hero · fresh signals · rotation · macro · holdings. Cockpit-curated (until the feed emits them): questions · research · catalysts.
        </div>
        <div style={{ marginTop:12, fontSize:11, color:C.faint, textAlign:"center", fontFamily:mono }}>
          {VM.stamp} · tap anything to expand · every section collapses independently
        </div>
      </div>
    </div>
  );
}
