import React, { useEffect, useState, useMemo } from "react";

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
  "research": {},
  "heartbeat": [
    {"layer":"Morning Scan","status":"ok","last_run":"2026-05-29","note":"Signal Log current"},
    {"layer":"Off-Hours","status":"ok","last_run":"2026-05-29","note":"Research Queue updated"},
    {"layer":"Daily Synthesis","status":"ok","last_run":"2026-05-29","note":"scout/librarian — state, not actions"},
    {"layer":"Insider feed","status":"down","last_run":null,"note":"reads a stub — non-functional"},
    {"layer":"Macro cache","status":"stale","last_run":"2026-05-28","note":"no auto-refresh"}
  ],
  "synthesis": {"date":"2026-05-29","source":"Daily Synthesis","state_of_play":"AI/semis leads the tape (+47%/3M); software just caught up. Burned MONITOR sleeves still lag — no re-entry signal firing.","delta":"FN named a new FS Top-5 SMID (5/28). ITA cleared a multi-month downtrend (Newton 5/28).","hanging":["FN buy-on-pullback not yet acted (flagged 5/28).","XLF Fundstrat rationale still undocumented in Live Theses."]},
  "actions": [
    {"rank":1,"kind":"decision_aging","ticker":"FN","confidence":"High","what":"Named FS Top-5 (5/28) — still un-acted","age_days":5,"first_flagged":"5/28","move_since":"+12% since flag","sizing":"~$35K (5sh → ~2%), fund via GRNY above-ceiling trim","your_move":"Buy-on-pullback ~$620 OR post-AVGO print — don't let it keep running away.","why":"SAMPLE row. High-conviction AI/optical pick flagged 5/28; up 12% while un-acted — the persistence/aging cue exists so this stops happening. The age / move-since values come from the engine (E2 / E5); not live yet.","gate":{"preview":"≥$25K → gate (expect AMBER: AI concentration)"}},
    {"rank":2,"kind":"lean_in","ticker":"NVDA","confidence":"High","what":"Under-deployed vs conviction (AI core)","sizing":"Express via a researched add; fund by trimming SMH / MAGS — not more ETF beta","your_move":"Size toward conviction — under-sizing the AI core is the canonical failure.","why":"SAMPLE row illustrating lean_in (the engine's under-deployment surfacing): flags a high-conviction sleeve smaller than the thesis supports. Applies ONLY to high-conviction sleeves — never a MONITOR sleeve. Now styled to the engine's live lean_in kind (E1).","gate":{"preview":"≥$25K → gate"}},
    {"rank":3,"kind":"reentry_zone","ticker":"LEU","confidence":"Moderate","what":"MONITOR re-entry signal — setup fired","age_days":3,"first_flagged":"5/30","move_since":"+5% since flag","sizing":"Defined-risk only (small / options) — burned sleeve","your_move":"Re-entry condition met the bar — express defined-risk. NOT a floor-gap nudge.","why":"SAMPLE row showing the MONITOR re-entry path: a burned-sleeve name surfaces LOUD only when a genuine re-entry condition fires (convergence / catalyst / regime-turn) — never on a bare dip. LEU ran +5% un-acted; loud + sticky is the fix.","gate":{"preview":"defined-risk → no gate"}}
  ]
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
function money(v){ if(typeof v!=="number") return ""; if(Math.abs(v)>=1000000) return `$${(v/1000000).toFixed(2)}M`; if(Math.abs(v)>=1000) return `$${Math.round(v/1000)}K`; return `$${Math.round(v)}`; }
function freshSignalRow(sig){ return { t:sig.ticker, n:sig.ticker, urg:sig.urgency, urgLabel:FRESH_URG_LABEL[sig.urgency]||sig.urgency, when:sig.when||"", what:PRETTY_EVENT[sig.what]||sig.what||"", why:sig.why||"", detail:sig.detail||"" }; }
function signalLogRow(r){
  const text = r.signal || r.what || r.title || r.summary || "";
  return { ticker:r.ticker||"", signal:text, date:r.date||r.when||"", priority:r.priority||r.urgency||"",
           source:r.source||"Signal Log", note:r.note||r.detail||r.why||"" };
}
function heroView(hero){ const h=(hero&&hero.hero)||{}, ny=(hero&&hero.needs_you)||{}; return { leadCount:h.count||0, leadNames:h.names||[], leadingSleeves:h.leading_sleeves||[], needsCount:ny.count||0, needsItems:ny.items||[] }; }
function heroAttention(h, packet, op){
  const counts = (packet&&packet.counts)||{};
  const keyNow = counts.key_now||0;
  const recheck = counts.recheck||0;
  const backlog = counts.backlog||0;
  const blockers = counts.blockers||0;
  const actionCount = (op&&op.actions)||0;
  const legacyNeeds = (h&&h.needsCount)||0;
  const plural = (n, one, many)=> n===1 ? one : many;
  if(keyNow>0) return {
    active:true, count:keyNow, color:C.amber,
    title:`${keyNow} key ${plural(keyNow,"review prompt","review prompts")} ready`,
    detail:`Start with Today Decisions; run gates before capital moves.${blockers?` ${blockers} blocker${blockers===1?"":"s"} still listed.`:""}`
  };
  if(recheck>0) return {
    active:true, count:recheck, color:C.amber,
    title:`${recheck} setup${recheck===1?"":"s"} need fresh evidence`,
    detail:`Start with Today Decisions; available checks already ran for this build. Open unresolved lanes before capital moves.${backlog?` ${backlog} backlog item${backlog===1?"":"s"} remain visible.`:""}`
  };
  if(legacyNeeds>0) return {
    active:true, count:legacyNeeds, color:C.amber,
    title:`${legacyNeeds} item${legacyNeeds===1?"":"s"} need${legacyNeeds===1?"s":""} attention`,
    detail:"Time-sensitive items are in Today's actions below."
  };
  if(actionCount>0 || backlog>0) {
    const count = actionCount||backlog;
    return {
      active:true, count, color:C.blue,
      title:`${count} decision item${count===1?"":"s"} visible`,
      detail:"No immediate trade command; review backlog only if it affects current capital priority."
    };
  }
  return {
    active:false, count:"OK", color:C.green,
    title:"No decisions need attention",
    detail:"No fresh action prompts in this feed build."
  };
}
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
  top_prospect:    { icon:"🎯", label:"Top prospect",   c:C.amber },
  sell_fast:       { icon:"⚠️", label:"Sell-fast",      c:C.red   },
  monitor_reentry: { icon:"🔒", label:"Re-entry watch", c:C.blue  },
  red_gate:        { icon:"🔴", label:"RED gate",       c:C.red   },
  macro_alert:     { icon:"🌐", label:"Macro alert",    c:C.amber },
  watch_entry:     { icon:"👁", label:"Watch",          c:C.blue  },
  stale_critical:  { icon:"⚠️", label:"Stale source",   c:C.dim   },
  synthesis:       { icon:"🧠", label:"Synthesis",      c:C.blue  },
  lean_in:          { icon:"📈", label:"Under-deployed", c:C.green },  // surfaces via Today's actions (actions_read promotes the strongest); feed.lean_in is the FULL lane, intentionally not a separate panel — item-6 disposition
  conviction_gap:   { icon:"📈", label:"Size gap",       c:C.green },
  catalyst_imminent:{ icon:"📅", label:"Pre-catalyst",   c:C.blue  },
  decision_aging:   { icon:"🕒", label:"Aging — act",    c:C.amber },
  research_review:  { icon:"🔬", label:"Research",       c:C.blue  },
  research_act_now:  { icon:"R!", label:"Research ACT",   c:C.red   },
};
const CONF_META = {
  High:     { c:C.green, label:"High" },
  Moderate: { c:C.amber, label:"Moderate" },
  Low:      { c:C.faint, label:"Low" },
};
const ACTION_STATE_META = {
  ACT_NOW:  { c:C.red,   label:"ACT_NOW" },
  WATCH:    { c:C.blue,  label:"WATCH" },
  RESEARCH: { c:C.blue,  label:"RESEARCH" },
  MONITOR:  { c:C.amber, label:"MONITOR" },
};
const GOAL_IMPACT_META = {
  High:   { c:C.red,   label:"Goal: High" },
  Medium: { c:C.amber, label:"Goal: Med" },
  Low:    { c:C.faint, label:"Goal: Low" },
};
const DEFERRED_OPTIONAL_SOURCE_KEYS = new Set(["social_watch"]);
function actionRow(a, opts={}){
  const m = ACTION_KIND_META[a.kind] || { icon:"•", label:a.kind, c:C.dim };
  const cf = CONF_META[a.confidence] || { c:C.dim, label:a.confidence };
  const actionState = a.action_state || a.actionState || "";
  const decisionGroup = a.decision_group || a.decisionGroup || "";
  const decisionGroupLabel = a.decision_group_label || a.decisionGroupLabel || "";
  const st = ACTION_STATE_META[actionState] || null;
  const gi = GOAL_IMPACT_META[a.goal_impact] || null;
  return { rank:a.rank, kind:a.kind, icon:m.icon, kindLabel:m.label, c:m.c,
           ticker:a.ticker||"", what:a.what||"", confLabel:cf.label,
           confBadgeLabel:opts.confBadgeLabel||"conf", confColor:cf.c,
           actionState, stateLabel:st&&st.label||"", stateColor:st&&st.c||"",
           goalImpact:a.goal_impact||"", goalLabel:gi&&gi.label||"", goalColor:gi&&gi.c||"",
           goalScore:(typeof a.goal_score==="number"?a.goal_score:null),
           timeWindow:a.time_window||"", capitalEffect:a.capital_effect||"",
           actionLabel:a.action_label||"", goalWhy:a.why_it_moves_goal||"",
           goalChannels:a.goal_channels||[], missingEvidence:a.missing_evidence||[],
           yourMove:a.your_move||"", why:a.why||"", gatePreview:(a.gate&&a.gate.preview)||"",
           decisionGroup, decisionGroupLabel,
           synthesisChanges:a.synthesis_changes||"",
           capitalPriorityScore:(typeof a.capital_priority_score==="number"?a.capital_priority_score:null),
           freshness:a.freshness||"", freshnessJudgment:a.freshness_judgment||{},
           whyThisMatters:a.why_this_matters||"", disconfirmation:a.disconfirmation||{},
           capitalEfficiency:a.capital_efficiency||{},
           assumptionRefresh:a.assumption_refresh||{},
           accountPlacement:a.account_placement||{},
           ageDays:(typeof a.age_days==="number"?a.age_days:null), flagged:a.first_flagged||"",
           moveSince:a.move_since||"", sizing:a.sizing||"" };
}
// ── Tier-1 view-model: heartbeat (layer run-status strip) ──
const HB_STATUS = { ok:{c:C.green,label:"ok"}, stale:{c:C.amber,label:"stale"}, down:{c:C.red,label:"down"} };
function heartbeatRow(h){ const s=HB_STATUS[h.status]||{c:C.gray,label:h.status}; return { layer:h.layer, c:s.c, statusLabel:s.label, lastRun:h.last_run||"", note:h.note||"" }; }
const LANE_STATUS_META = {
  has_data:      { c:C.green, label:"data" },
  checked_clear: { c:C.blue,  label:"clear" },
  not_checked:   { c:C.amber, label:"not checked" },
  stale:         { c:C.amber, label:"stale" },
  failed:        { c:C.red,   label:"failed" },
};
function laneStatusRow(r){
  const m = LANE_STATUS_META[r.status] || { c:C.dim, label:r.status||"unknown" };
  return { key:r.key||"", label:r.label||r.key||"", c:m.c, statusLabel:m.label,
           detail:r.detail||"", count:(typeof r.count==="number"?r.count:0),
           checkedAt:r.checked_at||"", nextStep:r.next_step||"", missingImpact:r.missing_impact||"" };
}
function eventPortfolioRead(eventWatch){
  if(!eventWatch) return null;
  const channels = (eventWatch.channels||[]).map(x=>String(x).toLowerCase());
  const tickers = eventWatch.tickers||[];
  const macro = ["rates","oil","volatility"].some(c=>channels.includes(c));
  const title = eventWatch.title || "Active event risk";
  if(macro){
    return {
      headline:"Portfolio impact: re-check sizing and new-buy timing before adding beta.",
      implication:"Rates/oil/volatility matter only if they change your portfolio action: stage adds, reduce chase risk, preserve cash for better entries, or hedge/trim if confirmation turns against current exposure.",
      blocker:`Do not act from this headline alone. Unblock with same-session levels/headlines and affected sleeve tape${tickers.length?` (${tickers.join(", ")})`:""}.`,
    };
  }
  return {
    headline:`Portfolio impact: ${title} may change timing or risk posture.`,
    implication:"Use this as an action filter: does it change add/trim/hold, sizing, hedge, or research priority? If not, keep it collapsed.",
    blocker:"Do not act until the specific affected exposure and confirming evidence are clear.",
  };
}
function operatorStatus(feed){
  const counts = ((feed.lane_status||{}).counts)||{};
  const laneRows = ((feed.lane_status||{}).rows)||[];
  const darkRows = laneRows.filter(r=>r && r.status==="not_checked");
  const deferredDarkRows = darkRows.filter(r=>DEFERRED_OPTIONAL_SOURCE_KEYS.has(r.key));
  const actionableDarkRows = darkRows.filter(r=>!DEFERRED_OPTIONAL_SOURCE_KEYS.has(r.key));
  const feedback = feed.feedback||{};
  const openFeedback = (feedback.open_actions)||{};
  const openActions = openFeedback.count||0;
  const openDue = openFeedback.due_count||0;
  const openStale = openFeedback.stale_count||0;
  const openReviewPressure = openDue + openStale;
  const sourceCalls = feedback.source_calls||{};
  const sourceCallStatus = sourceCalls.status||"not_checked";
  const sourceCallObserved = sourceCalls.observed_count||0;
  const sourceCallPending = sourceCalls.pending_count||0;
  const sourceCallOverdue = sourceCalls.overdue_count||0;
  const liveConfig = feed.live_source_config||{};
  const alertPolicy = feed.alert_policy||{};
  const alertRows = alertPolicy.rows||[];
  const systemHealthRows = alertPolicy.system_health||[];
  const liveConfigMissing = liveConfig.missing_count||0;
  const liveConfigTotal = liveConfig.total_count||0;
  const liveConfigured = liveConfig.configured_count||0;
  const sourceCallWarn = sourceCallStatus==="not_checked" && sourceCallObserved>0;
  const sourceCallFail = sourceCallOverdue>0;
  const actions = (feed.actions||[]).length;
  const eventRows = (feed.event_risk||[]).filter(r=>r&&r.title);
  const severityRank = {critical:0, high:1, medium:2, low:3};
  eventRows.sort((a,b)=>(severityRank[a.severity]??9)-(severityRank[b.severity]??9));
  const eventWatch = eventRows[0] || null;
  const dark = actionableDarkRows.length;
  const deferredDark = deferredDarkRows.length;
  const stale = counts.stale||0;
  const failed = counts.failed||0;
  const status = (failed||sourceCallFail) ? "FAIL" : ((dark||stale||openReviewPressure||sourceCallWarn||liveConfigMissing) ? "WARN" : "PASS");
  const statusColor = (failed||sourceCallFail) ? C.red : (status==="WARN" ? C.amber : C.green);
  const sourceLane = failed ? `${failed} failed` : dark ? `${dark} dark` : stale ? `${stale} stale` : deferredDark ? `${deferredDark} deferred` : "clear";
  const sourceLaneWarning = Boolean(failed || dark || stale);
  const sourceCall = sourceCallFail ? `${sourceCallOverdue} overdue` : sourceCallWarn ? `${sourceCallObserved} unscored` : sourceCallPending ? `${sourceCallPending} pending` : "clear";
  const openReviewValue = openStale ? `${openStale} stale` : openDue ? `${openDue} due` : openActions ? `${openActions} new` : "0";
  const liveFetch = liveConfigTotal ? `${liveConfigured}/${liveConfigTotal}` : "unknown";
  return {
    status, statusColor, actions, openActions, openDue, openStale, openReviewPressure, openReviewValue,
    alertPolicy, alertRows, alertCount:alertRows.length, alertStatus:alertRows.length?"notify":"quiet", alertLine:alertPolicy.line||"", alertPolicyText:alertPolicy.policy||"",
    systemHealthRows, systemHealthCount:systemHealthRows.length,
    sourceLane, sourceLaneWarning, sourceCall, sourceCallWarn, sourceCallFail, deferredDark,
    liveFetch, liveConfigMissing, liveConfig,
    eventWatch,
    eventPortfolio: eventPortfolioRead(eventWatch),
    command:"python src/go_live_checklist.py --format text",
    suddenEventCommand:'python src/sudden_event_refresh.py --title "<event headline>" --channels "oil,rates,volatility" --tickers "XOP,TNX" --why "<why exposure, hedges, or new-buy timing changes>" --trigger "<what confirms or changes the risk>"',
  };
}
// ── ⑨ Radar view-model: endorsed (daily-call) names not owned yet ──
function radarRow(r){
  const levels=[];
  if(r.entry!=null) levels.push(`entry ${r.entry}`);
  if(r.stop!=null) levels.push(`stop ${r.stop}`);
  if(r.target!=null) levels.push(`tgt ${r.target}`);
  if(r.window) levels.push(String(r.window));
  return { ticker:r.ticker, author:r.author||"", direction:r.direction||"",
           levels:levels.join(" · "), date:r.date||"", quote:r.quote||"" };
}
// ── lazy view-model: split so each view's lanes are built ONLY when active ──
// sharedVM = chrome shown on BOTH views (header stamp + heartbeat strip).
function sharedVM(feed){
  return {
    generatedAt: feed.generated_at||"", stamp: stamp(feed),
    heartbeat: (feed.heartbeat||[]).map(heartbeatRow),
    laneStatus: ((feed.lane_status||{}).rows||[]).map(laneStatusRow),
    darkLaneCount: ((feed.lane_status||{}).rows||[]).filter(r=>r && r.status==="not_checked" && !DEFERRED_OPTIONAL_SOURCE_KEYS.has(r.key)).length,
    staleLaneCount: ((((feed.lane_status||{}).counts||{}).stale)||0) + ((((feed.lane_status||{}).counts||{}).failed)||0),
    operatorStatus: operatorStatus(feed),
    fundstratNews: feed.fundstrat_news||{},
    ifIWereYou: feed.if_i_were_you||{},
  };
}
// actionVM = the ⚡ Action surface (decide/do). Built only when mode==="action".
function actionVM(feed){
  const actions = (feed.actions||[]).map(actionRow);
  const researchActions = (feed.research_actions||[]).map(a=>actionRow(a, { confBadgeLabel:"priority" }));
  const isOpp = (a)=>["upside","sizing_gap","leverage","opportunity_cost"].some(c=>(a.goalChannels||[]).includes(c));
  const isRisk = (a)=>["downside_protection","data_quality"].some(c=>(a.goalChannels||[]).includes(c));
  return {
    macro: macroView(feed.macro||{}),
    rotation: (feed.rotation||[]).map(rotationRow),
    actions,
    actionGroups: feed.action_decision_groups||{},
    marketOpenPacket: feed.market_open_packet||{},
    alertPolicy: feed.alert_policy||{},
    sourceConflicts: feed.source_conflicts||{ status:"checked_clear", count:0, rows:[] },
    asymmetricOpportunities: feed.asymmetric_opportunities||{},
    socialWatch: feed.social_watch||{},
    uwActionRunbook: feed.uw_action_runbook||{},
    uwEndpointProof: feed.uw_endpoint_proof||{},
    reallocationBrief: feed.reallocation_brief||{},
    sourceAudits: feed.source_audits||{},
    actionSplit: {
      actNow: actions.filter(a=>a.actionState==="ACT_NOW"),
      opportunities: actions.filter(a=>a.actionState!=="ACT_NOW" && isOpp(a)),
      risks: actions.filter(a=>isRisk(a)),
    },
    todayPriority: todayPriorityRows(feed, actions, researchActions),
    researchActions,
    synthesis: feed.synthesis||{},
    radar: (feed.radar||[]).map(radarRow),
    freshSignals: (feed.fresh_signals||[]).map(freshSignalRow),
    signalLog: (feed.signal_log||[]).map(signalLogRow),
    bullishFlow: feed.bullish_flow||{},
    prospects: feed.prospects||{},
    feedback: feed.feedback||{},
    targetDrift: feed.target_drift||{},
    hero: heroView(feed.hero||{}),
    catalysts: feed.catalysts||[], questions: feed.questions||[], research: feed.research||{},
  };
}
// bookVM = the 📊 Book surface (dig into holdings). Built ONLY when mode==="book"
// — this is the per-position map; on Action it is never called.
function bookVM(feed){
  return { holdings: (feed.holdings||[]).map(holdingGroup), portfolioViews: feed.portfolio_views||null };
}
// thin wrapper — preserves the full public VM shape for feed_to_cockpit.js + node tests.
function toCockpit(feed){
  return { ...sharedVM(feed), ...actionVM(feed), ...bookVM(feed) };
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
function compactJoin(parts){
  return parts.filter(p=>p!==undefined && p!==null && p!==false && String(p).trim()).join(" | ");
}
function clipText(value, max=120){
  const s = String(value||"").replace(/\s+/g, " ").trim();
  return s.length > max ? `${s.slice(0, max-1).trim()}...` : s;
}
function tickerSummary(rows, max=3){
  const tickers = (rows||[]).map(r=>r&&(r.ticker||r.t||r.entity)).filter(Boolean);
  return tickers.length ? tickers.slice(0,max).join(", ") + (tickers.length>max ? ` +${tickers.length-max}` : "") : "";
}
function prospectRows(P){
  return [ ...((P||{}).hot||[]), ...((P||{}).movers_best||[]), ...((P||{}).sell_fast||[]) ];
}
function lowerText(value){ return String(value||"").toLowerCase(); }
function hasAnyText(value, terms){
  const text = lowerText(value);
  return terms.some(term=>text.includes(term));
}
function isNearTermWindow(value){
  return hasAnyText(value, ["today", "intraday", "1-3", "1 trading", "same-session", "market-open", "before acting"]);
}
function firstListText(values){
  return (values||[]).filter(Boolean).map(String).join(" / ");
}
function cleanPosture(value){
  return String(value||"review").toLowerCase().replaceAll("_"," ").replaceAll("-", " ");
}
function todayActionRow(a){
  const dis = a.disconfirmation||{}, refresh = a.assumptionRefresh||{}, cap = a.capitalEfficiency||{}, placement = a.accountPlacement||{};
  const invalidates = firstListText((dis.invalidates_if||[]).concat(refresh.invalidates_if||[])) || dis.summary || "";
  return {
    key:`action:${a.rank}:${a.ticker||a.kind}`,
    score:1000-(a.rank||0),
    ticker:a.ticker||"",
    title:a.what || "Decision prompt",
    home:"Action engine",
    source:a.kindLabel||a.kind||"action",
    posture:cleanPosture(actionLabelDisplay(a.actionLabel) || actionPostureChip(a) || a.actionState || "review"),
    color:a.stateColor || a.c || C.amber,
    timing:a.timeWindow || "current",
    whyHere:a.decisionGroup==="key_now" ? "Current key decision pressure." : a.decisionGroup==="recheck_before_acting" ? "You may act later, but fresh evidence is still missing or changed." : "Visible because it affects near-term capital priority.",
    changes:a.synthesisChanges || actionLabelDisplay(a.actionLabel) || actionPostureChip(a) || "review",
    nextStep:a.yourMove || refresh.next_step || "Run the gate before capital moves.",
    invalidates,
    details:a.whyThisMatters || a.why || cap.summary || "",
    backup:compactJoin([
      a.freshnessJudgment&&a.freshnessJudgment.judgment,
      cap.summary,
      placement.summary&&`account: ${placement.summary}`,
      placement.why&&`account why: ${placement.why}`,
      a.missingEvidence&&a.missingEvidence.length?`missing: ${a.missingEvidence.join(" / ")}`:"",
    ]),
    tooltip:"Promoted from the action engine because it changes today's posture or needs a re-check before capital moves.",
  };
}
function shouldPromoteActionToToday(a){
  return a.actionState==="ACT_NOW" || a.decisionGroup==="key_now" || a.decisionGroup==="recheck_before_acting" || isNearTermWindow(a.timeWindow);
}
function opportunityPriorityRows(feed, usedTickers){
  const rows = ((feed.asymmetric_opportunities||{}).rows||[]);
  return rows
    .filter(r=>{
      const ticker = String(r.ticker||"").toUpperCase();
      if(ticker && usedTickers.has(ticker)) return false;
      const score = Number(r.score||0);
      return score>=80 || isNearTermWindow(r.decay_window) || hasAnyText(r.reason, ["urgent", "time-sensitive", "before acting"]);
    })
    .map((r,i)=>({
      key:`asym:${r.ticker||i}`,
      score:800 + Number(r.score||0),
      ticker:r.ticker||"",
      title:r.reason || "Evidence-backed asymmetric setup",
      home:"Ideas / Asymmetric Opportunities",
      source:r.source||"asymmetric opportunity",
      posture:"review",
      color:C.green,
      timing:r.decay_window||"source dependent",
      whyHere:"Promoted because the setup may be a better use of capital than ordinary backlog ideas.",
      changes:"research / size",
      nextStep:r.action || "Refresh price, flow, and source evidence before deciding.",
      invalidates:"A changed price, broken thesis, contradicted source, or better capital use pushes this back to Ideas.",
      details:r.evidence||"",
      backup:compactJoin([`score ${r.score}`, r.evidence, r.decay_window&&`decays ${r.decay_window}`]),
      tooltip:"Promoted from Ideas only when the evidence-backed setup may affect near-term capital allocation.",
    }));
}
function prospectPriorityRows(feed, usedTickers){
  return prospectRows(feed.prospects||{})
    .filter(r=>{
      const ticker = String(r.ticker||"").toUpperCase();
      if(ticker && usedTickers.has(ticker)) return false;
      const urgency = String(r.urgency||"").toUpperCase();
      const vetted = String(r.corroboration||"") !== "Uncorroborated";
      return urgency==="ACT_NOW" || urgency==="HOT" || (r.direction==="avoid" && urgency!=="QUIET" && vetted);
    })
    .map((r,i)=>{
      const urgency = String(r.urgency||"review").toLowerCase();
      return {
        key:`prospect:${r.ticker||i}`,
        score:700 + Number(r.urgency_score||0) + Number(r.conviction_score||0),
        ticker:r.ticker||"",
        title:r.summary || `${r.ticker||"Prospect"} needs review`,
        home:"Ideas / Top Prospects",
        source:(r.sources||[]).join(" / ") || r.provenance || "top prospects",
        posture:r.direction==="avoid" ? "avoid / research" : "research",
        color:urgency==="act_now" ? C.red : C.amber,
        timing:r.urgency||"review",
        whyHere:"Promoted because the prospect signal is hot enough to affect today's research or capital priority.",
        changes:r.direction==="avoid" ? "trim / wait / research" : "research / no capital yet",
        nextStep:"Refresh thesis, price, and source corroboration before it can become an action.",
        invalidates:"If the signal is quiet, uncorroborated, or no longer price-sensitive, keep it in Ideas only.",
        details:r.provenance||"",
        backup:compactJoin([r.summary, r.corroboration, r.pct_vs_spy!=null?`vs SPY ${(r.pct_vs_spy*100).toFixed(1)}%`:""]),
        tooltip:"Promoted from Top Prospects only when research timing may unlock a near-term decision.",
      };
    });
}
function researchPriorityRows(researchActions, usedTickers){
  return (researchActions||[])
    .filter(a=>{
      const ticker = String(a.ticker||"").toUpperCase();
      if(ticker && usedTickers.has(ticker)) return false;
      return a.actionState==="ACT_NOW" || a.kind==="research_act_now" || isNearTermWindow(a.timeWindow);
    })
    .map((a)=>({
      ...todayActionRow(a),
      key:`research:${a.rank}:${a.ticker||a.kind}`,
      score:900-(a.rank||0),
      home:"Ideas / From Research",
      source:a.kindLabel||"research",
      posture:"research",
      changes:a.synthesisChanges || "research / no capital yet",
      whyHere:"Promoted because finishing this research could change a near-term buy/sell/size/wait decision.",
      tooltip:"Promoted from Research only when the research can change a near-term decision.",
    }));
}
function todayPriorityRows(feed, actions, researchActions){
  const usedTickers = new Set();
  const rows = [];
  (actions||[]).filter(shouldPromoteActionToToday).forEach(a=>{
    const row = todayActionRow(a);
    if(row.ticker) usedTickers.add(String(row.ticker).toUpperCase());
    rows.push(row);
  });
  researchPriorityRows(researchActions, usedTickers).forEach(r=>{
    if(r.ticker) usedTickers.add(String(r.ticker).toUpperCase());
    rows.push(r);
  });
  opportunityPriorityRows(feed, usedTickers).forEach(r=>{
    if(r.ticker) usedTickers.add(String(r.ticker).toUpperCase());
    rows.push(r);
  });
  prospectPriorityRows(feed, usedTickers).forEach(r=>{
    if(r.ticker) usedTickers.add(String(r.ticker).toUpperCase());
    rows.push(r);
  });
  return rows.sort((a,b)=>(b.score||0)-(a.score||0)).slice(0,12);
}
function FundstratMonthlyRows({ title, rows, empty }) {
  return (
    <div style={{ ...card, marginBottom:8 }}>
      <div style={{ display:"flex", alignItems:"baseline", justifyContent:"space-between", gap:8, marginBottom:6 }}>
        <div style={{ fontSize:12.5, fontWeight:700, color:C.text }}>{title}</div>
        <span style={{ fontFamily:mono, fontSize:10.5, color:rows&&rows.length?C.green:C.amber }}>{rows&&rows.length?`${rows.length} row${rows.length===1?"":"s"}`:"not captured"}</span>
      </div>
      {(!rows || rows.length===0) && <div style={{ fontSize:12, color:C.amber }}>{empty}</div>}
      {(rows||[]).map((r,i)=>(
        <div key={`${title}${r.ticker}${i}`} style={{ display:"grid", gridTemplateColumns:"36px minmax(60px,90px) minmax(0,1fr)", gap:8, alignItems:"baseline", padding:"6px 0", borderTop:i?`1px solid ${C.line}`:"none" }}>
          <span style={{ fontFamily:mono, fontSize:10.5, color:C.faint }}>#{r.rank||i+1}</span>
          <span style={{ fontFamily:mono, fontSize:13, fontWeight:800, color:C.text }}>{r.ticker}</span>
          <div>
            <div style={{ display:"flex", alignItems:"baseline", gap:8, flexWrap:"wrap" }}>
              <span style={{ fontFamily:mono, fontSize:10.5, color:r.add_price?C.green:C.amber }}>added {r.add_date||"date n/a"} | {r.add_price_label||"not captured"}</span>
              {r.report_move_pct!==undefined && r.report_move_pct!==null && <span style={{ fontFamily:mono, fontSize:10.5, color:Number(r.report_move_pct)>=0?C.green:C.red }}>report move {Number(r.report_move_pct)>0?"+":""}{r.report_move_pct}%</span>}
              {r.carry_over && <span style={{ fontFamily:mono, fontSize:10.5, color:C.faint }}>carry over</span>}
              {r.conviction && <span style={{ fontFamily:mono, fontSize:10.5, color:C.faint }}>{r.conviction}{r.urgency?` / ${r.urgency}`:""}</span>}
            </div>
            {r.add_price_source && <div style={{ marginTop:2, fontFamily:mono, fontSize:10.2, color:C.faint }}>price source: {r.add_price_source}</div>}
            {(r.name||r.note||r.summary||r.provenance) && <div style={{ marginTop:3, fontSize:11.5, color:C.dim }}>{r.name||r.note||r.summary||r.provenance}</div>}
          </div>
        </div>
      ))}
    </div>
  );
}
function IfIWereYouBlock({ block, sectionId="if-i-were-you", defaultOpen=false, openMap, setOpen }) {
  const rows = (block&&block.rows)||[];
  return (
    <Section id={sectionId} title="If I Were You" icon=">" badge={rows.length?`${rows.length}`:"0"} badgeColor={rows.length?C.amber:C.faint} summary={clipText((block&&block.line)||"Review-only priorities are not available in this feed build.", 110)} openMap={openMap} setOpen={setOpen} defaultOpen={defaultOpen}>
      {block&&block.honesty_rule && <div style={{ ...card, marginBottom:8, borderColor:C.amber+"33", background:C.amber+"0a", fontFamily:mono, fontSize:10.8, color:C.faint }}>{block.honesty_rule}</div>}
      {!rows.length && <div style={{ ...card, fontSize:12, color:C.faint }}>No review priorities in this feed build.</div>}
      {rows.map((r,i)=>(
        <div key={`${r.source||"you"}${i}`} style={{ ...card, marginBottom:7, borderColor:i===0?C.amber+"55":C.line }}>
          <div style={{ display:"flex", alignItems:"baseline", gap:8, flexWrap:"wrap" }}>
            <span style={{ fontFamily:mono, fontSize:10.5, color:C.faint }}>#{r.rank||i+1}</span>
            <span style={{ fontFamily:mono, fontSize:10.5, color:C.amber, border:`1px solid ${C.amber}55`, borderRadius:99, padding:"1px 8px" }}>{r.posture||"review"}</span>
            <span style={{ fontSize:12.8, fontWeight:750, color:C.text }}>{r.label}</span>
          </div>
          {r.why && <div style={{ marginTop:6, fontSize:11.8, color:C.dim }}>Why: {r.why}</div>}
          {r.what_i_would_do && <div style={{ marginTop:5, fontSize:12.2, color:C.text }}>What I would do: {r.what_i_would_do}</div>}
          {r.source && <div style={{ marginTop:5, fontFamily:mono, fontSize:10.5, color:C.faint }}>source: {r.source}</div>}
        </div>
      ))}
    </Section>
  );
}
const SECTION_DESCRIPTIONS = {
  "status-checks": "Health summary for data lanes and build checks; open only when a warning changes trust in the dashboard.",
  "today-priority-stack": "Legacy promoted-decision queue; retained as backup if a future view needs it.",
  "today-decisions": "Decision-first queue; only items that can change a near-term act, wait, refresh, research, trim, hedge, size, or no-capital-yet call belong here.",
  "if-i-were-you": "Plain-English review priorities; not execution and not a replacement for trade gates.",
  "market-open-packet": "Morning decision packet; use this to refresh gates and blockers before capital moves.",
  actions: "Underlying action engine detail; backup context for Today Focus rather than a second to-do list.",
  "source-conflicts": "Bull and bear source splits; useful only when they change posture or conviction.",
  "top-prospects": "Idea watchlist; prospects overlap into Today only if timing or research unlock matters now.",
  "asymmetric-opportunities": "Evidence-backed skew prompts; review candidates, not automatic buys.",
  "uw-action-runbook": "Live-check menu for UW-backed confirmation; use when a decision needs same-session evidence.",
  "reallocation-brief": "Capital-efficiency workspace; compare better uses of cash before parking money in merely good ideas.",
  "target-drift": "Sizing gaps versus working targets; use to decide whether to add, defer, or revise targets.",
  "research-actions": "Research items that can change a decision; non-urgent research stays in Ideas.",
  "fresh-signals": "Recently captured signals; useful only if they change action, timing, or research priority.",
  "signal-log": "Watch-only signal memory; context lane, not a trade instruction lane.",
  "bullish-flow": "UW flow candidates; confirm before promoting to Today or sizing capital.",
  synthesis: "Distilled market read; macro and news are shown only when they change portfolio action.",
  "source-audits": "Proof of source checks, routine receipts, and writebacks; use to judge data trust.",
  feedback: "Open loops and stale reviews; close or refresh items before they distort decisions.",
  radar: "Endorsed but unowned names; idea context until a concrete decision trigger appears.",
  holdings: "Portfolio book; inspect exposures, accounts, sizing, and allocation guidance.",
  "fundstrat-news": "Fundstrat source context; low-value updates stay collapsed unless they change decisions.",
  "fundstrat-monthly": "Fundstrat thesis and allocation archive; useful context, not live tactical proof by itself.",
  "fundstrat-daily": "Fast-decay Fundstrat calls; re-check live tape before acting.",
  "fundstrat-news-gaps": "Missing Fundstrat evidence; dark gaps are not checked-clear.",
  "if-i-were-you-news": "Plain-English priorities from source context; review-only.",
  "system-cloud-routines": "Cloud routine health; failures show what data may be missing or stale.",
  "system-cloud-routine-table": "Routine receipt details; diagnostic backup for cloud proof.",
  "system-source-proof": "Connector, Fundstrat, UW, and Notion audit status.",
  "system-upgrades": "Build queue and safe upgrade checks; system work stays separate from portfolio actions.",
  "current-commands": "Useful operator commands for the current build.",
  "operator-actions": "Day-to-day commands for refreshing, reviewing, and maintaining the cockpit.",
  "system-checks": "Verification and system-health commands; use when diagnosing the machine.",
  "source-links": "Durable source-of-truth links for repo, plans, and docs.",
  market: "Portfolio-relevant macro and rotation context; compact unless it changes action.",
  research: "Research queue; prioritize only what can change capital allocation.",
  rpending: "Pending research you may need to prioritize.",
  rdone: "Completed research with significant findings.",
  cats: "Upcoming catalysts; use only when timing or risk changes.",
  questions: "Open questions for you; not blockers unless a decision depends on them.",
  "social-watch": "Queued social/reddit lane; dark means not checked, not no signal."
};
function Section({ id, title, icon, badge, badgeColor, summary, description, children, openMap, setOpen, defaultOpen=false }) {
  const isOpen = openMap[id] === undefined ? defaultOpen : openMap[id];
  const summaryNode = typeof summary === "function" ? summary({ isOpen }) : summary;
  const desc = description || SECTION_DESCRIPTIONS[id] || "Category summary and expandable backup detail.";
  const accent = badgeColor || C.faint;
  const toggle = () => setOpen(s=>({...s,[id]: !(s[id]===undefined?defaultOpen:s[id])}));
  return (
    <div id={id} style={{ marginTop:14 }}>
      <div onClick={toggle}
        style={{ cursor:"pointer", padding:"9px 10px", border:`1px solid ${isOpen?accent+"55":C.line}`, borderLeft:`4px solid ${accent}`, borderRadius:8, background:isOpen?`${accent}0b`:C.panel, userSelect:"none" }}>
        <div style={{ display:"flex", alignItems:"center", gap:9, minWidth:0 }}>
          <span style={{ color:C.faint, fontFamily:mono, fontSize:11, width:12, transform:isOpen?"none":"rotate(-90deg)", transition:"transform .15s" }}>v</span>
          <span style={{ fontSize:14 }}>{icon}</span>
          <span style={{ fontSize:13.5, fontWeight:750, color:C.text, minWidth:0, flex:"1 1 auto" }}>{title}</span>
          {badge!==undefined && badge!==null && (
            <span style={{ fontFamily:mono, fontSize:11, color:accent, border:`1px solid ${accent}55`, borderRadius:99, padding:"1px 8px", whiteSpace:"nowrap", background:`${accent}10` }}>{badge}</span>
          )}
          <span style={{ fontFamily:mono, fontSize:10.5, color:isOpen?C.faint:accent, whiteSpace:"nowrap" }}>{isOpen?"hide":"expand"}</span>
        </div>
        <div style={{ marginTop:6, fontSize:11.6, color:C.dim, lineHeight:1.35 }}>{desc}</div>
        {summaryNode && (
          <div style={{ marginTop:4, color:isOpen?C.faint:C.text, fontSize:11.7, lineHeight:1.35, overflow:"hidden" }}>
            {summaryNode}
          </div>
        )}
      </div>
      {isOpen && <div style={{ marginTop:4 }}>{children}</div>}
    </div>
  );
}
const card = { background:C.panel, border:`1px solid ${C.line}`, borderRadius:11, padding:"12px 14px" };
const muted = { color:C.dim, fontSize:12.5 };
const OPEN_STORAGE_KEY = "convictionCockpit.openSections.v4";
function loadStoredOpen(){
  if(typeof window === "undefined" || !window.localStorage) return {};
  try {
    const raw = window.localStorage.getItem(OPEN_STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch (_) {
    return {};
  }
}
function cueColor(cue){
  return cue==="favored" ? C.green : cue==="avoid" ? C.red : cue==="mixed" ? C.amber : C.faint;
}
function targetGapLabel(row){
  if(row.working_model_target_pct==null) return "";
  const gap = row.working_model_gap_pct;
  const sign = gap>0 ? "+" : "";
  return `model target ${row.working_model_target_pct.toFixed(1)}% | gap ${sign}${gap.toFixed(1)}pp`;
}
const TONE_COLOR = { red:C.red, amber:C.amber, green:C.green, blue:C.blue, gray:C.faint };
function toneColor(tone){ return TONE_COLOR[tone] || C.faint; }
function toneCard(tone, extra={}){
  const c = toneColor(tone);
  return {
    ...card,
    borderColor:`${c}55`,
    borderLeft:`4px solid ${c}`,
    background:`${c}0d`,
    ...extra,
  };
}
function placementTone(p){
  const status = String((p||{}).status||"").toLowerCase();
  if(status==="blocked") return "red";
  if(["needs_review","not_checked"].includes(status)) return "amber";
  if(status==="candidate") return "green";
  return "gray";
}
function actionTone(a){
  const refresh = a.assumptionRefresh || {};
  const fresh = a.freshnessJudgment || {};
  const refreshStatus = String(refresh.status||"").toLowerCase();
  const freshLabel = String(fresh.label||"").toLowerCase();
  if(a.actionState==="ACT_NOW" || a.decisionGroup==="key_now") return "red";
  if(a.decisionGroup==="recheck_before_acting" || ["changed_recheck","stale","invalidated"].includes(refreshStatus) || ["stale","not checked","fast-moving"].includes(freshLabel)) return "amber";
  if(a.decisionGroup==="important_backlog") return "blue";
  if((a.accountPlacement||{}).status==="candidate") return "green";
  return "gray";
}
function packetTone(r){
  const kind = String((r||{}).kind||"");
  const refresh = String((r||{}).refresh_status||"");
  if(kind==="gate_key_now") return "red";
  if(["recheck_first","positions_blocker","dark_lane","uw_check"].includes(kind) || ["changed_recheck","stale","invalidated"].includes(refresh)) return "amber";
  if(kind==="reallocation_review") return "green";
  if(kind==="important_backlog" || kind==="open_reviews") return "blue";
  return "gray";
}
const REFRESH_STATUS_META = {
  upgraded: {
    label:"Checked: still urgent",
    tone:"green",
    title:"The assumption-refresh pass kept this item prominent. It is not a trade command; run the relevant source, position, and pre-trade gate before capital moves.",
  },
  changed_recheck: {
    label:"Evidence missing",
    tone:"amber",
    title:"The latest dashboard build checked available assumptions, but something important is missing, old, or changed. Confirm same-session price, flow, position, source, or event-risk evidence before acting.",
  },
  still_valid: {
    label:"Auto-checked valid",
    tone:"green",
    title:"Available feed evidence did not break this setup during the latest build. Keep it visible, but use the normal gate before acting.",
  },
  stale: {
    label:"Stale evidence",
    tone:"amber",
    title:"The evidence has aged past its useful window. The system should refresh the source before treating this as actionable.",
  },
  invalidated: {
    label:"Invalidated: do not act",
    tone:"red",
    title:"Available evidence broke the setup. Do not act from this row unless it is rebuilt from fresh evidence.",
  },
};
function refreshStatusMeta(status){
  const key = String(status||"").toLowerCase();
  return REFRESH_STATUS_META[key] || {
    label:`Checked: ${String(status||"review").replaceAll("_"," ")}`,
    tone:"gray",
    title:"Assumption-refresh status from the feed. It explains the row's current review posture; it does not execute or authorize a trade.",
  };
}
function decisionGroupMeta(key, label){
  const k = String(key||"").toLowerCase();
  if(k==="key_now") return { title:"Ready to Decide", chip:"ready", short:"Ready", tone:"red", description:"Today decisions that do not need another evidence gate before you decide act, defer, trim, hedge, size, or no capital." };
  if(k==="recheck_before_acting") return { title:"Evidence Missing", chip:"Evidence Missing", short:"Evidence", tone:"amber", description:"Blocked until the named price, source, position, flow, or event-risk check is refreshed. The dashboard should already have tried the cheap available checks." };
  if(k==="important_backlog") return { title:"Backlog", chip:"compare capital", short:"Backlog", tone:"blue", description:"Useful decisions that still matter, but first compare against better current uses of capital and the cost of waiting." };
  if(k==="quiet_watch") return { title:"Watch", chip:"watch only", short:"Watch", tone:"gray", description:"Tracked context that should stay quiet unless it changes action, sizing, risk, or research priority." };
  return { title:label||String(key||"Decision Lane").replaceAll("_"," "), chip:String(label||key||"review").replaceAll("_"," ").toLowerCase(), tone:"gray", description:"Decision lane from the action engine." };
}
function actionLabelDisplay(label){
  const text = String(label||"");
  const lower = text.toLowerCase();
  if(lower==="re-check" || lower==="recheck") return "Evidence Missing";
  if(lower==="add/rotate") return "add/rotate candidate";
  return text;
}
function actionPostureChip(a){
  const meta = decisionGroupMeta(a.decisionGroup, a.decisionGroupLabel);
  return meta.chip;
}
function advisorForAction(a, adviceRows){
  const ticker = String(a.ticker||"").toLowerCase();
  const source = String(a.kind||a.source||"").toLowerCase();
  return (adviceRows||[]).find(r=>{
    const label = String(r.label||"").toLowerCase();
    const rSource = String(r.source||"").toLowerCase();
    if(ticker && label.includes(ticker)) return true;
    if(a.decisionGroup==="recheck_before_acting" && rSource==="market_open_packet") return true;
    if(source && rSource && (source.includes(rSource) || rSource.includes(source))) return true;
    return false;
  }) || null;
}
function todayTone(r){
  const posture = lowerText((r||{}).posture);
  const title = lowerText((r||{}).title);
  const changes = lowerText((r||{}).changes);
  const rowColor = lowerText((r||{}).color);
  const text = `${posture} ${title} ${changes}`;
  if(rowColor===lowerText(C.red) || hasAnyText(text, ["act", "key now", "trim", "sell", "exit", "protect capital", "urgent", "avoid"])) return "red";
  if(hasAnyText(posture, ["re check", "re-check", "wait", "blocked"])) return "amber";
  if(rowColor===lowerText(C.amber)) return "amber";
  if(hasAnyText(posture, ["research", "review", "no capital yet"])) return "blue";
  return "green";
}
function freshnessColor(label){
  const value = String(label||"").toLowerCase();
  if(value==="stale" || value==="not checked") return C.red;
  if(value==="fast-moving" || value==="archive") return C.amber;
  if(value==="fresh") return C.green;
  return C.faint;
}
function routineImpact(row){
  const role = String((row||{}).role || (row||{}).routine_id || "").toLowerCase();
  if(role.includes("uw_opportunity")) return "UW/asymmetric-flow opportunity prompts may be incomplete or stale; the dashboard may miss flow-backed opportunities or rely on the prior cache.";
  if(role.includes("parabolic")) return "Parabolic/chase-risk checks may be stale; do not assume high-momentum names were freshly screened.";
  if(role.includes("fundstrat")) return "Fundstrat updates may not be fully captured; recent source changes could be missing until the next clean intake.";
  if(role.includes("daily_synthesis") || role.includes("deep_synthesis")) return "Synthesis may not include every latest source; treat recommendations as needing a refresh before major capital moves.";
  if(role.includes("cockpit") || role.includes("build") || role.includes("post_close")) return "Dashboard build/publish freshness may be affected; verify the local JSX timestamp before relying on the screen.";
  if(role.includes("broker") || role.includes("position")) return "Account positions may be stale; sizing/account-placement guidance may be incomplete.";
  return "Routine-owned data may be stale or missing; use the affected lane as not fully checked until the routine is clean.";
}
function freshnessTitle(label, row){
  const value = String(label||"").toLowerCase();
  const evidence = row&&row.evidence_date ? ` Evidence date: ${row.evidence_date}.` : "";
  const checked = row&&row.last_checked ? ` Last checked: ${row.last_checked}.` : "";
  const decay = row&&row.decay_window ? ` Decay window: ${row.decay_window}.` : "";
  if(value==="fresh") return `Fresh enough to keep this decision prompt visible; still run the gate before capital moves.${evidence}${checked}${decay}`;
  if(value==="fast-moving") return `Fast-moving evidence can go stale intraday. Re-check same-session levels/headlines before acting.${evidence}${checked}${decay}`;
  if(value==="stale") return `Stale evidence. Refresh this source before treating the row as actionable.${evidence}${checked}${decay}`;
  if(value==="not checked") return `This source was not checked. Do not infer all-clear from missing data.${evidence}${checked}${decay}`;
  return `Freshness context for this row.${evidence}${checked}${decay}`;
}
function evidenceNeededText(a){
  const disconfirmation = (a&&a.disconfirmation)||{};
  const assumptionRefresh = (a&&a.assumptionRefresh)||{};
  const freshness = (a&&a.freshnessJudgment)||{};
  const parts = [
    ...((a&&a.missingEvidence)||[]),
    ...((disconfirmation.confirm_before_acting)||[]),
    ...((assumptionRefresh.what_changed)||[]).map(x=>`changed: ${x}`),
    ...(assumptionRefresh.next_step ? [assumptionRefresh.next_step] : []),
    ...(String(freshness.label||"").toLowerCase()==="stale" ? ["refresh stale source evidence"] : []),
    ...(String(freshness.label||"").toLowerCase()==="not checked" ? ["source not checked"] : []),
  ].map(x=>friendlyEvidencePart(x)).filter(Boolean);
  const unique = [];
  parts.forEach(p=>{
    if(!unique.some(x=>x.toLowerCase()===p.toLowerCase())) unique.push(p);
  });
  return unique.length ? unique.slice(0,4).join(" / ") : "";
}
function friendlyEvidencePart(value){
  const raw = String(value||"").trim();
  const lower = raw.toLowerCase();
  if(!raw) return "";
  if(lower==="live opportunity") return "same-session price/tape still supports the setup";
  if(lower==="funding leg") return "where the money comes from, including any trim/rotate source";
  if(lower==="pre-trade gate") return "final pre-trade check: price, source, risk, account, and sizing";
  if(lower==="live price" || lower==="price") return "same-session price level";
  if(lower==="position" || lower==="current exposure") return "current position/exposure from the live book";
  if(lower==="source confirmation") return "source confirmation still supports the action";
  if(lower==="event risk") return "event-risk trigger has not changed the action";
  return raw;
}
function laneEvidenceSummary(rows){
  const parts = [];
  (rows||[]).forEach(a=>{
    const text = evidenceNeededText(a);
    if(text) text.split(" / ").forEach(p=>{
      const part = p.trim();
      if(part && !parts.some(x=>x.toLowerCase()===part.toLowerCase())) parts.push(part);
    });
  });
  return parts.length ? `Needed: ${parts.slice(0,4).join(" / ")}${parts.length>4?" / more in cards":""}` : "Needed evidence is listed inside each blocked card.";
}
function packetWorkSummary(packet, reallocationBrief, counts){
  const packetCounts = (packet&&packet.counts)||{};
  const reCounts = (reallocationBrief&&reallocationBrief.counts)||{};
  const funding = (reallocationBrief&&reallocationBrief.funding)||{};
  const blockers = [
    ...((reallocationBrief&&reallocationBrief.blockers)||[]),
    ...((packet&&packet.blockers)||[]),
  ].filter(Boolean);
  const ready = (counts&&counts.key_now) || packetCounts.key_now || 0;
  const evidence = (counts&&counts.recheck_before_acting) || packetCounts.recheck || 0;
  const backlog = (counts&&counts.important_backlog) || packetCounts.backlog || 0;
  const urgentVisible = packetCounts.urgent_visible || 0;
  const adds = reCounts.adds || 0;
  const trims = reCounts.trims || 0;
  const line = compactJoin([
    `${ready} ready`,
    `${evidence} evidence-gated`,
    `${backlog} backlog`,
    urgentVisible ? `${urgentVisible} urgent checks visible` : null,
    adds ? `${adds} candidate adds` : null,
    trims ? `${trims} funding trims` : null,
  ]);
  const hasWork = Boolean(evidence || backlog || urgentVisible || adds || trims || blockers.length);
  const primaryBlocker = blockers[0] || "";
  const capitalLine = adds
    ? compactJoin([
        reallocationBrief.line || null,
        typeof funding.shortfall_usd==="number" ? `shortfall ${money(funding.shortfall_usd)}` : null,
      ])
    : "";
  return { ready, evidence, backlog, urgentVisible, adds, trims, line, hasWork, primaryBlocker, capitalLine };
}
function TodayWorkNowStrip({ packet, reallocationBrief, counts, onOpenOps, onOpenReallocation }){
  const W = packetWorkSummary(packet, reallocationBrief, counts);
  const color = W.ready ? C.red : W.hasWork ? C.amber : C.green;
  const message = W.ready
    ? "There is at least one ready decision. Decide act, defer, trim, hedge, size, or no capital after the card's gate."
    : W.hasWork
      ? "Ready is zero because the system is blocking capital-sized moves until the named evidence clears. That means work now is gather evidence and compare capital, not assume nothing matters."
      : "No forced portfolio decision is visible in this build.";
  const action = W.adds
    ? `Highest-value work: validate the reallocation brief, then run same-session price/flow and pre-trade gates before any add or trim.`
    : W.evidence
      ? "Highest-value work: open Evidence Missing and clear the named blockers before treating any setup as actionable."
      : W.backlog
        ? "Highest-value work: compare backlog items against better uses of capital before spending attention or cash."
        : "Highest-value work: stay quiet unless a source changes action, sizing, risk, or research priority.";
  return (
    <div style={{ marginBottom:10, padding:"9px 10px", border:`1px solid ${color}55`, borderRadius:8, background:`${color}0d` }}>
      <div style={{ display:"flex", alignItems:"baseline", justifyContent:"space-between", gap:8, flexWrap:"wrap" }}>
        <div style={{ fontSize:13.2, fontWeight:850, color:C.text }}>Work now: {W.line || "quiet"}</div>
        <div style={{ display:"flex", gap:6, flexWrap:"wrap" }}>
          <button onClick={onOpenReallocation} style={{ cursor:"pointer", border:`1px solid ${C.blue}55`, background:`${C.blue}10`, color:C.blue, borderRadius:7, padding:"3px 8px", fontFamily:mono, fontSize:10.5 }}>Reallocation</button>
          <button onClick={onOpenOps} style={{ cursor:"pointer", border:`1px solid ${C.amber}55`, background:`${C.amber}10`, color:C.amber, borderRadius:7, padding:"3px 8px", fontFamily:mono, fontSize:10.5 }}>Evidence checks</button>
        </div>
      </div>
      <div style={{ marginTop:5, fontSize:12.2, color:C.dim }}>{message}</div>
      <div style={{ marginTop:4, fontSize:12.2, color:C.text }}>{action}</div>
      {W.primaryBlocker && <div style={{ marginTop:4, fontSize:11.5, color:C.amber }}>Main blocker: {friendlyEvidencePart(W.primaryBlocker)}</div>}
      {W.capitalLine && <div style={{ marginTop:4, fontFamily:mono, fontSize:10.5, color:C.faint }}>{W.capitalLine}</div>}
    </div>
  );
}
function confidenceBasis(a, advisorNote){
  const freshness = (a&&a.freshnessJudgment)||{};
  const base = compactJoin([
    a&&a.kindLabel ? a.kindLabel : null,
    a&&a.source ? `source ${a.source}` : null,
    freshness.evidence_date ? `evidence ${freshness.evidence_date}` : null,
    a&&a.goalScore!=null ? `goal ${a.goalScore}/100` : null,
    a&&a.capitalPriorityScore!=null ? `capital priority ${a.capitalPriorityScore}` : null,
  ]);
  const weak = compactJoin([
    evidenceNeededText(a) ? `missing ${clipText(evidenceNeededText(a), 80)}` : null,
    freshness.judgment && String(freshness.label||"").toLowerCase()!=="fresh" ? `freshness ${clipText(freshness.judgment, 70)}` : null,
  ]);
  if(base && weak) return clipText(`Based on ${base}. Weak because ${weak}.`, 190);
  if(base) return clipText(`Based on ${base}.`, 170);
  if(weak) return clipText(`Confidence is limited because ${weak}.`, 170);
  return "Confidence is based on the current action-engine evidence stack; open backup details for source rows.";
}
function evidenceGatherPrompt(a, evidence){
  const title = compactJoin([a&&a.ticker, a&&a.what]) || "this Today decision";
  return [
    `Codex, gather the missing evidence for this Today decision: ${title}.`,
    `Needed evidence: ${evidence || "identify the missing source, price, position, flow, event-risk, and pre-trade checks."}`,
    a&&a.yourMove ? `Current decision text: ${a.yourMove}` : "",
    a&&a.whyThisMatters ? `Why it matters: ${a.whyThisMatters}` : "",
    "Refresh only the relevant evidence lanes, keep missing/stale sources honest, update the local JSX cockpit if the decision changes, and do not place trades.",
  ].filter(Boolean).join("\n");
}
function copyTextToClipboard(text, setPosOpen, key, event){
  if(event && event.stopPropagation) event.stopPropagation();
  setPosOpen(st=>({...st,[key]:text}));
  if(typeof navigator!=="undefined" && navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(text).catch(()=>{});
  }
}

const COMMAND_ACTIONS = [
  { name:"Start here", desc:"Use the canonical JSX cockpit first. It has the deepest drilldowns and is the v1 validation surface.", command:"http://127.0.0.1:8765/cockpit_jsx_preview.html" },
  { name:"Refresh the cockpit", desc:"Rebuild the feed, rendered JSX, local preview, and HTML mirror before trusting a stale screen.", command:"python src/live_dashboard_refresh.py" },
  { name:"Refresh book from SnapTrade", desc:"Pull account API positions, validate, promote the book, and rebuild the cockpit. Use daily and after reported trades.", command:"python src/snaptrade_book_refresh.py --refresh-dashboard" },
  { name:"Review market-open packet", desc:"Walk the current Key Now, Re-check, backlog, blockers, and assumption-refresh sequence.", command:"python src/market_open_packet.py --feed src/latest_cockpit_feed.json --format text" },
  { name:"Review reallocation", desc:"Candidate-only funded add/trim plan. Use it to compare capital uses, not to execute trades.", command:"python src/reallocation_brief.py --feed src/latest_cockpit_feed.json --positions src/positions.json --format text" },
  { name:"Review open actions", desc:"Resolve only after act, invalidate, defer, ignore, or miss is explicit.", command:"python src/action_memory_resolve.py --review-report" },
];
const COMMAND_CHECKS = [
  { name:"Live status", desc:"Fast readiness, dark-lane, source-call, and preview status.", command:"python src/live_status.py --format text" },
  { name:"Go-live checklist", desc:"Operating checklist for source, dashboard, event, and review gates.", command:"python src/go_live_checklist.py --format text" },
  { name:"Push alert gate", desc:"Shows only action-relevant candidates that would be allowed to interrupt you. System-health warnings stay out of the top alert slot.", command:"python src/alert_policy.py --feed src/latest_cockpit_feed.json --format text" },
  { name:"Fundstrat alert check", desc:"Dry-run the Fundstrat/Pushover lane; low-value Fundstrat content should stay quiet.", command:"python src/fundstrat_daytime_alert.py --dry-run --format text" },
  { name:"UW action runbook", desc:"Same-session check sets for price, flow, tape, event risk, and Fundstrat confirmation.", command:"python src/uw_action_runbook.py --feed src/latest_cockpit_feed.json --format text" },
  { name:"SnapTrade stage only", desc:"Pull and validate account data without changing the live book.", command:"python src/snaptrade_book_refresh.py --no-promote" },
  { name:"Standard verification", desc:"Run before claiming a code or dashboard slice is clean.", command:"python src/verify_standard.py" },
  { name:"Cloud proof", desc:"Background scheduled-receipt status. Failed or overdue matters; natural proof gaps stay monitored.", command:"python src/cloud_ops_status.py --format text" },
];
const COMMAND_LINKS = [
  { name:"GitHub repo", desc:"Executable source of truth for implementation state.", href:"https://github.com/ender-lark/enderverse" },
  { name:"Notion architecture mirror", desc:"Readable rebuild and troubleshooting mirror.", href:"https://app.notion.com/p/376c50314bb681d4b04cda8e73d6c34b" },
  { name:"Monday build plan", desc:"Current go-live plan and acceptance criteria.", href:"https://app.notion.com/p/378c50314bb681afb39bcb82efce9d47" },
  { name:"Published HTML mirror", desc:"Shareable/export surface after JSX validation.", href:"https://ender-lark.github.io/enderverse/" },
];

function ActionCard({ a, keyPrefix, posOpen, setPosOpen, stamp, footerLabel, showAging=false, showSizing=false, advisorNote=null }) {
  const key = keyPrefix + a.rank + (a.ticker || a.kind), isO = posOpen[key];
  const disconfirmation = a.disconfirmation || {};
  const capitalEfficiency = a.capitalEfficiency || {};
  const assumptionRefresh = a.assumptionRefresh || {};
  const accountPlacement = a.accountPlacement || {};
  const hasDisconfirmation = !!(disconfirmation.summary || (disconfirmation.invalidates_if||[]).length || (disconfirmation.confirm_before_acting||[]).length);
  const hasCapitalEfficiency = !!(capitalEfficiency.summary || capitalEfficiency.timing_balance || (capitalEfficiency.compare_against||[]).length);
  const hasAssumptionRefresh = !!(assumptionRefresh.status || assumptionRefresh.next_step || (assumptionRefresh.what_changed||[]).length || (assumptionRefresh.invalidates_if||[]).length);
  const hasAccountPlacement = !!(accountPlacement.summary || accountPlacement.why || accountPlacement.label);
  const hasDetail = !!(a.why || a.whyThisMatters || (a.freshnessJudgment&&a.freshnessJudgment.judgment) || a.missingEvidence.length || hasDisconfirmation || hasCapitalEfficiency || hasAssumptionRefresh || hasAccountPlacement);
  const urgent = a.actionState === "ACT_NOW";
  const tone = actionTone(a);
  const edge = toneColor(tone);
  const placementColor = toneColor(placementTone(accountPlacement));
  return (
    <div key={key} style={{ ...toneCard(tone), marginBottom:8,
      borderColor: urgent ? edge+"aa" : edge+"44",
      background: urgent ? edge+"18" : `${edge}0d`,
      boxShadow: urgent ? `0 0 0 1px ${edge}55 inset` : "none" }}>
      <div onClick={()=>setPosOpen(st=>({...st,[key]:!st[key]}))} style={{ cursor:hasDetail?"pointer":"default" }}>
        <div style={{ display:"flex", alignItems:"baseline", gap:8, flexWrap:"wrap" }}>
          <span style={{ fontFamily:mono, fontSize:11, color:C.faint }}>#{a.rank}</span>
          {a.ticker && <span style={{ fontFamily:mono, fontWeight:700, fontSize:13.5, color:C.text }}>{a.ticker}</span>}
          <span style={{ fontSize:12.5, fontWeight:600, color:C.text }}>{a.what}</span>
        </div>
        <div style={{ marginTop:7, display:"flex", alignItems:"center", gap:7, flexWrap:"wrap" }}>
          {a.stateLabel && <span style={{ fontFamily:mono, fontSize:11, fontWeight:urgent?800:600, color:a.stateColor, border:`1px solid ${a.stateColor}${urgent?"bb":"66"}`, borderRadius:99, padding:"1px 8px", background:`${a.stateColor}${urgent?"22":"12"}` }}>{a.stateLabel}</span>}
          {a.goalLabel && <span title={a.goalScore!=null?`goal score ${a.goalScore}/100`:""} style={{ fontFamily:mono, fontSize:11, color:a.goalColor, border:`1px solid ${a.goalColor}66`, borderRadius:99, padding:"1px 8px", background:`${a.goalColor}10` }}>{a.goalLabel}</span>}
          {a.actionLabel && <span style={{ fontFamily:mono, fontSize:11, fontWeight:700, color:urgent?C.text:C.dim, border:`1px solid ${(urgent?a.stateColor:C.line)}${urgent?"aa":""}`, borderRadius:99, padding:"1px 8px", background:urgent?`${a.stateColor}20`:C.panel2 }}>{actionLabelDisplay(a.actionLabel)}</span>}
          {a.decisionGroupLabel && <span style={{ fontFamily:mono, fontSize:11, color:C.text, border:`1px solid ${C.line}`, borderRadius:99, padding:"1px 8px", background:C.panel2 }}>{actionPostureChip(a)}</span>}
          {a.timeWindow && <span style={{ fontFamily:mono, fontSize:11, color:C.faint }}>{a.timeWindow}</span>}
          {a.freshnessJudgment && a.freshnessJudgment.label && <span title={a.freshnessJudgment.judgment||""} style={{ fontFamily:mono, fontSize:11, color:freshnessColor(a.freshnessJudgment.label), border:`1px solid ${freshnessColor(a.freshnessJudgment.label)}44`, borderRadius:99, padding:"1px 8px", background:`${freshnessColor(a.freshnessJudgment.label)}0d` }}>{a.freshnessJudgment.label}</span>}
          {assumptionRefresh.status && <span title={assumptionRefresh.next_step||""} style={{ fontFamily:mono, fontSize:11, color:["changed_recheck","stale","invalidated"].includes(assumptionRefresh.status)?C.amber:C.green, border:`1px solid ${(["changed_recheck","stale","invalidated"].includes(assumptionRefresh.status)?C.amber:C.green)}55`, borderRadius:99, padding:"1px 8px", background:`${(["changed_recheck","stale","invalidated"].includes(assumptionRefresh.status)?C.amber:C.green)}10` }}>refresh: {String(assumptionRefresh.status).replace("_"," ")}</span>}
          {capitalEfficiency.label && <span title={capitalEfficiency.summary||""} style={{ fontFamily:mono, fontSize:11, color:C.amber, border:`1px solid ${C.amber}55`, borderRadius:99, padding:"1px 8px", background:`${C.amber}10` }}>capital: {capitalEfficiency.label}</span>}
          {hasAccountPlacement && <span title={accountPlacement.why||accountPlacement.rule||"candidate account placement"} style={{ fontFamily:mono, fontSize:11, color:placementColor, border:`1px solid ${placementColor}66`, borderRadius:99, padding:"1px 8px", background:`${placementColor}12` }}>acct: {accountPlacement.label||accountPlacement.account||"review"}</span>}
          {a.synthesisChanges && <span title="what this synthesis changes" style={{ fontFamily:mono, fontSize:11, color:C.blue, border:`1px solid ${C.blue}55`, borderRadius:99, padding:"1px 8px", background:`${C.blue}10` }}>changes: {a.synthesisChanges}</span>}
          {a.capitalPriorityScore!=null && <span title="capital priority inside this decision group" style={{ fontFamily:mono, fontSize:11, color:C.faint, border:`1px solid ${C.line}`, borderRadius:99, padding:"1px 8px", background:C.panel2 }}>priority: {a.capitalPriorityScore}</span>}
          <span style={{ fontFamily:mono, fontSize:11, color:a.c, border:`1px solid ${a.c}55`, borderRadius:99, padding:"1px 8px" }}>{a.icon} {a.kindLabel}</span>
          <span style={{ fontFamily:mono, fontSize:11, color:a.confColor, border:`1px solid ${a.confColor}55`, borderRadius:99, padding:"1px 8px" }}>{a.confBadgeLabel}: {a.confLabel}</span>
          {a.gatePreview && <span style={{ fontFamily:mono, fontSize:11, color:C.dim, border:`1px solid ${C.line}`, borderRadius:99, padding:"1px 8px", background:C.panel2 }}>{a.gatePreview}</span>}
          {showAging && a.ageDays!=null && <span title="how long this has been actionable — the cost of waiting" style={{ fontFamily:mono, fontSize:11, color:C.amber, border:`1px solid ${C.amber}55`, borderRadius:99, padding:"1px 8px" }}>🕒 open {a.ageDays}d{a.flagged?` · since ${a.flagged}`:""}{a.moveSince?` · ${a.moveSince}`:""}</span>}
        </div>
        <div style={{ marginTop:8, fontSize:12.5, color:C.text }}><span style={{ color:C.dim, fontWeight:600 }}>Your move:</span> {a.yourMove}</div>
        {advisorNote && (
          <div style={{ marginTop:6, fontSize:12.2, color:C.text }}>
            <span style={{ color:C.dim, fontWeight:650 }}>Plain-English read:</span> {advisorNote.what_i_would_do || advisorNote.why || advisorNote.label}
          </div>
        )}
        {a.goalWhy && <div style={{ marginTop:5, fontSize:12.2, color:a.goalColor }}><span style={{ color:C.dim, fontWeight:600 }}>Goal impact:</span> {a.goalWhy}</div>}
        {showSizing && a.sizing && <div style={{ marginTop:5, fontSize:12, color:C.dim }}><span style={{ fontFamily:mono, fontSize:10, color:C.faint, textTransform:"uppercase", letterSpacing:0.5 }}>Size </span>{a.sizing}</div>}
        {hasDetail && (
          <div style={{ marginTop:7, display:"flex", justifyContent:"flex-end" }}>
            <span style={{ fontSize:11, color:a.c }}>{isO?"hide why ▲":"why ▾"}</span>
          </div>
        )}
      </div>
      {isO && hasDetail && (
        <div style={{ marginTop:8, paddingTop:8, borderTop:`1px solid ${C.line}`, ...muted }}>
          {a.whyThisMatters && <div style={{ marginBottom:6, color:C.text }}><span style={{ color:C.dim, fontWeight:600 }}>Why this matters:</span> {a.whyThisMatters}</div>}
          {a.why && <div>{a.why}</div>}
          {a.freshnessJudgment && a.freshnessJudgment.judgment && <div style={{ marginTop:6, fontFamily:mono, fontSize:10, color:C.faint }}>freshness: {a.freshnessJudgment.judgment} | evidence {a.freshnessJudgment.evidence_date||"n/a"} | decays {a.freshnessJudgment.decay_window||"source dependent"}</div>}
          {hasCapitalEfficiency && (
            <div style={{ marginTop:8, paddingTop:7, borderTop:`1px solid ${C.line}`, color:C.text }}>
              <div style={{ fontWeight:700, color:C.amber }}>Capital efficiency</div>
              {capitalEfficiency.summary && <div style={{ marginTop:4 }}>{capitalEfficiency.summary}</div>}
              {capitalEfficiency.priority_reason && <div style={{ marginTop:4 }}>Priority: {capitalEfficiency.priority_reason}</div>}
              {capitalEfficiency.do_nothing_risk && <div style={{ marginTop:4 }}>Do nothing: {capitalEfficiency.do_nothing_risk}</div>}
              {capitalEfficiency.timing_balance && <div style={{ marginTop:5, fontFamily:mono, fontSize:10, color:C.faint }}>timing: {capitalEfficiency.timing_balance}</div>}
              {(capitalEfficiency.compare_against||[]).length>0 && <div style={{ marginTop:5, fontFamily:mono, fontSize:10, color:C.faint }}>compare: {(capitalEfficiency.compare_against||[]).join(" / ")}</div>}
            </div>
          )}
          {hasAccountPlacement && (
            <div style={{ marginTop:8, paddingTop:7, borderTop:`1px solid ${C.line}`, color:C.text }}>
              <div style={{ fontWeight:700, color:C.green }}>Account placement</div>
              {accountPlacement.summary && <div style={{ marginTop:4 }}>{accountPlacement.summary}</div>}
              {accountPlacement.why && <div style={{ marginTop:4 }}>Why: {accountPlacement.why}</div>}
              {accountPlacement.rule && <div style={{ marginTop:5, fontFamily:mono, fontSize:10, color:C.faint }}>rule: {accountPlacement.rule}</div>}
              {(accountPlacement.caveats||[]).length>0 && <div style={{ marginTop:5, fontFamily:mono, fontSize:10, color:C.faint }}>caveats: {(accountPlacement.caveats||[]).join(" / ")}</div>}
            </div>
          )}
          {hasAssumptionRefresh && (
            <div style={{ marginTop:8, paddingTop:7, borderTop:`1px solid ${C.line}`, color:C.text }}>
              <div style={{ fontWeight:700, color:C.amber }}>Assumption refresh</div>
              {assumptionRefresh.status && <div style={{ marginTop:4 }}>status: {String(assumptionRefresh.status).replace("_"," ")}</div>}
              {assumptionRefresh.next_step && <div style={{ marginTop:4 }}>{assumptionRefresh.next_step}</div>}
              {(assumptionRefresh.what_changed||[]).length>0 && <div style={{ marginTop:5, fontFamily:mono, fontSize:10, color:C.faint }}>changed: {(assumptionRefresh.what_changed||[]).join(" / ")}</div>}
              {(assumptionRefresh.invalidates_if||[]).length>0 && <div style={{ marginTop:5, fontFamily:mono, fontSize:10, color:C.faint }}>invalidates: {(assumptionRefresh.invalidates_if||[]).join(" / ")}</div>}
            </div>
          )}
          {hasDisconfirmation && (
            <div style={{ marginTop:8, paddingTop:7, borderTop:`1px solid ${C.line}`, color:C.text }}>
              <div style={{ fontWeight:700, color:C.amber }}>What could make this wrong?</div>
              {disconfirmation.summary && <div style={{ marginTop:4 }}>{disconfirmation.summary}</div>}
              {(disconfirmation.invalidates_if||[]).length>0 && <div style={{ marginTop:5, fontFamily:mono, fontSize:10, color:C.faint }}>invalidates: {(disconfirmation.invalidates_if||[]).join(" / ")}</div>}
              {(disconfirmation.confirm_before_acting||[]).length>0 && <div style={{ marginTop:5, fontFamily:mono, fontSize:10, color:C.faint }}>confirm: {(disconfirmation.confirm_before_acting||[]).join(" / ")}</div>}
              {disconfirmation.downgrade_to && <div style={{ marginTop:5, fontFamily:mono, fontSize:10, color:C.amber }}>downgrade: {disconfirmation.downgrade_to}</div>}
            </div>
          )}
          {(a.goalChannels.length>0 || a.capitalEffect || a.synthesisChanges || a.capitalPriorityScore!=null) && <div style={{ marginTop:8, fontFamily:mono, fontSize:10, color:C.faint }}>channels: {a.goalChannels.join(" / ") || "n/a"}{a.capitalEffect?` · capital: ${a.capitalEffect}`:""}{a.synthesisChanges?` · changes: ${a.synthesisChanges}`:""}{a.goalScore!=null?` · score: ${a.goalScore}/100`:""}{a.capitalPriorityScore!=null?` · priority: ${a.capitalPriorityScore}`:""}</div>}
          {a.missingEvidence.length>0 && <div style={{ marginTop:5, fontFamily:mono, fontSize:10, color:C.amber }}>missing: {a.missingEvidence.join(" / ")}</div>}
          <div style={{ marginTop:8, fontFamily:mono, fontSize:10, color:C.faint }}>{stamp} · {footerLabel} · drill in chat to run the gate</div>
        </div>
      )}
    </div>
  );
}

function TodayActionCard({ a, keyPrefix, posOpen, setPosOpen, stamp, footerLabel, showAging=false, showSizing=false, advisorNote=null }) {
  const key = keyPrefix + a.rank + (a.ticker || a.kind);
  const isO = posOpen[key];
  const disconfirmation = a.disconfirmation || {};
  const capitalEfficiency = a.capitalEfficiency || {};
  const assumptionRefresh = a.assumptionRefresh || {};
  const accountPlacement = a.accountPlacement || {};
  const freshness = a.freshnessJudgment || {};
  const tone = actionTone(a);
  const edge = toneColor(tone);
  const urgent = a.actionState === "ACT_NOW";
  const refreshMeta = refreshStatusMeta(assumptionRefresh.status);
  const refreshStatus = String(assumptionRefresh.status||"").toLowerCase();
  const freshLabel = String(freshness.label||"").toLowerCase();
  const evidenceChip = ["invalidated","changed_recheck","stale"].includes(refreshStatus)
    ? refreshMeta
    : ["stale","not checked","fast-moving"].includes(freshLabel)
      ? { label: freshLabel==="fast-moving" ? "Fast-moving evidence" : freshLabel==="not checked" ? "Evidence not checked" : "Stale evidence", tone: freshLabel==="not checked" ? "red" : "amber", title: freshnessTitle(freshLabel, freshness) }
      : null;
  const evidenceColor = evidenceChip ? toneColor(evidenceChip.tone) : C.faint;
  const posture = actionLabelDisplay(a.actionLabel) || actionPostureChip(a);
  const conviction = clipText(a.whyThisMatters || a.why || (advisorNote&&advisorNote.why) || a.goalWhy || "", 170);
  const neededEvidence = evidenceNeededText(a);
  const basis = confidenceBasis(a, advisorNote);
  const gatherKey = `${key}:gathered`;
  const gatherPrompt = evidenceGatherPrompt(a, neededEvidence);
  const gatherRequest = posOpen[gatherKey];
  const work = compactJoin([
    a.source && `source ${a.source}`,
    a.kindLabel && `lane ${a.kindLabel}`,
    freshness.evidence_date && `evidence ${freshness.evidence_date}`,
    freshness.last_checked && `checked ${freshness.last_checked}`,
    a.goalScore!=null && `goal ${a.goalScore}/100`,
    a.capitalPriorityScore!=null && `capital priority ${a.capitalPriorityScore}`,
  ]);
  const hasDisconfirmation = !!(disconfirmation.summary || (disconfirmation.invalidates_if||[]).length || (disconfirmation.confirm_before_acting||[]).length);
  const hasCapitalEfficiency = !!(capitalEfficiency.summary || capitalEfficiency.timing_balance || (capitalEfficiency.compare_against||[]).length);
  const hasEvidenceCheck = !!(assumptionRefresh.status || assumptionRefresh.next_step || (assumptionRefresh.what_changed||[]).length || (assumptionRefresh.invalidates_if||[]).length || freshness.judgment);
  const hasAccountPlacement = !!(accountPlacement.summary || accountPlacement.why || accountPlacement.label);
  const hasDetail = !!(a.why || a.whyThisMatters || work || a.missingEvidence.length || hasDisconfirmation || hasCapitalEfficiency || hasEvidenceCheck || hasAccountPlacement);
  const showEvidenceChip = evidenceChip && !(a.decisionGroup==="recheck_before_acting" && ["changed_recheck","stale"].includes(refreshStatus));
  return (
    <div key={key} style={{ ...toneCard(tone), marginBottom:8, borderColor: urgent ? edge+"aa" : edge+"44", background: urgent ? edge+"18" : `${edge}0d`, boxShadow: urgent ? `0 0 0 1px ${edge}55 inset` : "none" }}>
      <div onClick={()=>setPosOpen(st=>({...st,[key]:!st[key]}))} style={{ cursor:hasDetail?"pointer":"default" }}>
        <div style={{ display:"flex", alignItems:"baseline", justifyContent:"space-between", gap:10, flexWrap:"wrap" }}>
          <div style={{ display:"flex", alignItems:"baseline", gap:8, flexWrap:"wrap", minWidth:0 }}>
            <span style={{ fontFamily:mono, fontSize:11, color:C.faint }}>#{a.rank}</span>
            {a.ticker && <span style={{ fontFamily:mono, fontWeight:800, fontSize:13.5, color:C.text }}>{a.ticker}</span>}
            <span style={{ fontSize:12.7, fontWeight:750, color:C.text }}>{a.what}</span>
          </div>
          {hasDetail && <span style={{ fontSize:11, color:edge, whiteSpace:"nowrap" }}>{isO?"hide details ^":"details v"}</span>}
        </div>
        <div style={{ marginTop:7, display:"flex", alignItems:"center", gap:7, flexWrap:"wrap" }}>
          <span title="Action posture this card changes or requires." style={{ fontFamily:mono, fontSize:11, fontWeight:700, color:edge, border:`1px solid ${edge}66`, borderRadius:99, padding:"1px 8px", background:`${edge}12` }}>{posture}</span>
          {a.timeWindow && <span title="How quickly this decision can matter." style={{ fontFamily:mono, fontSize:11, color:C.faint }}>{a.timeWindow}</span>}
          <span title={basis} style={{ fontFamily:mono, fontSize:11, color:a.confColor, border:`1px solid ${a.confColor}55`, borderRadius:99, padding:"1px 8px" }}>{a.confBadgeLabel}: {a.confLabel}</span>
          {showEvidenceChip && <span title={evidenceChip.title||""} style={{ fontFamily:mono, fontSize:11, color:evidenceColor, border:`1px solid ${evidenceColor}55`, borderRadius:99, padding:"1px 8px", background:`${evidenceColor}10` }}>{evidenceChip.label}</span>}
          {showAging && a.ageDays!=null && <span title="How long this has been actionable; the cost of waiting." style={{ fontFamily:mono, fontSize:11, color:C.amber, border:`1px solid ${C.amber}55`, borderRadius:99, padding:"1px 8px" }}>open {a.ageDays}d{a.flagged?` since ${a.flagged}`:""}{a.moveSince?` ${a.moveSince}`:""}</span>}
        </div>
        <div style={{ marginTop:8, fontSize:12.5, color:C.text }}><span style={{ color:C.dim, fontWeight:700 }}>Decision:</span> {a.yourMove}</div>
        {neededEvidence && (
          <div style={{ marginTop:7, display:"grid", gridTemplateColumns:"1fr auto", gap:8, alignItems:"center" }}>
            <div style={{ fontSize:12.1, color:C.amber }}><span style={{ color:C.dim, fontWeight:700 }}>Needed evidence:</span> {clipText(neededEvidence, 220)}</div>
            <button
              onClick={(event)=>copyTextToClipboard(gatherPrompt, setPosOpen, gatherKey, event)}
              title="Copies an exact Codex request to gather the missing evidence for this card."
              style={{ cursor:"pointer", border:`1px solid ${C.amber}66`, background:gatherRequest?`${C.green}18`:`${C.amber}12`, color:gatherRequest?C.green:C.amber, borderRadius:7, padding:"4px 8px", fontFamily:mono, fontSize:10.5, whiteSpace:"nowrap" }}
            >{gatherRequest?"request ready":"Gather evidence"}</button>
          </div>
        )}
        {gatherRequest && <div style={{ marginTop:6, padding:7, border:`1px solid ${C.line}`, borderRadius:7, background:C.panel2, fontFamily:mono, fontSize:10.5, color:C.faint, whiteSpace:"pre-wrap", overflowWrap:"anywhere" }}>Codex evidence request:\n{gatherRequest}</div>}
        {conviction && <div style={{ marginTop:5, fontSize:12.2, color:C.text }}><span style={{ color:C.dim, fontWeight:700 }}>Why conviction:</span> {conviction}</div>}
        <div style={{ marginTop:5, fontSize:12.1, color:C.dim }}><span style={{ color:C.faint, fontWeight:700 }}>Confidence basis:</span> {basis}</div>
        {advisorNote && <div style={{ marginTop:6, fontSize:12.2, color:C.text }}><span style={{ color:C.dim, fontWeight:650 }}>Plain-English read:</span> {advisorNote.what_i_would_do || advisorNote.why || advisorNote.label}</div>}
        {a.goalWhy && <div style={{ marginTop:5, fontSize:12.2, color:a.goalColor }}><span style={{ color:C.dim, fontWeight:700 }}>Why it matters:</span> {a.goalWhy}</div>}
        {showSizing && a.sizing && <div style={{ marginTop:5, fontSize:12, color:C.dim }}><span style={{ fontFamily:mono, fontSize:10, color:C.faint, textTransform:"uppercase", letterSpacing:0.5 }}>Size </span>{a.sizing}</div>}
      </div>
      {isO && hasDetail && (
        <div style={{ marginTop:8, paddingTop:8, borderTop:`1px solid ${C.line}`, ...muted }}>
          {work && <div style={{ marginTop:2, fontFamily:mono, fontSize:10, color:C.faint }}>work: {work}</div>}
          <div style={{ marginTop:6, color:C.text }}><span style={{ color:C.dim, fontWeight:700 }}>Confidence is based on:</span> {basis}</div>
          {a.whyThisMatters && <div style={{ marginTop:6, color:C.text }}><span style={{ color:C.dim, fontWeight:700 }}>Why this matters:</span> {a.whyThisMatters}</div>}
          {a.why && <div style={{ marginTop:5 }}>{a.why}</div>}
          {hasEvidenceCheck && (
            <div style={{ marginTop:8, paddingTop:7, borderTop:`1px solid ${C.line}`, color:C.text }}>
              <div style={{ fontWeight:700, color:C.amber }}>Latest evidence check</div>
              {assumptionRefresh.status && <div style={{ marginTop:4 }}>status after latest build: {refreshMeta.label}</div>}
              {freshness.judgment && <div style={{ marginTop:4 }}>freshness: {freshness.judgment}</div>}
              {freshness.evidence_date && <div style={{ marginTop:4, fontFamily:mono, fontSize:10, color:C.faint }}>evidence {freshness.evidence_date} | checked {freshness.last_checked||"n/a"} | decays {freshness.decay_window||"source dependent"}</div>}
              {assumptionRefresh.next_step && <div style={{ marginTop:4 }}>{assumptionRefresh.next_step}</div>}
              {(assumptionRefresh.what_changed||[]).length>0 && <div style={{ marginTop:5, fontFamily:mono, fontSize:10, color:C.faint }}>changed: {(assumptionRefresh.what_changed||[]).join(" / ")}</div>}
            </div>
          )}
          {hasCapitalEfficiency && (
            <div style={{ marginTop:8, paddingTop:7, borderTop:`1px solid ${C.line}`, color:C.text }}>
              <div style={{ fontWeight:700, color:C.amber }}>Capital efficiency</div>
              {capitalEfficiency.summary && <div style={{ marginTop:4 }}>{capitalEfficiency.summary}</div>}
              {capitalEfficiency.priority_reason && <div style={{ marginTop:4 }}>Priority: {capitalEfficiency.priority_reason}</div>}
              {capitalEfficiency.do_nothing_risk && <div style={{ marginTop:4 }}>Do nothing: {capitalEfficiency.do_nothing_risk}</div>}
              {capitalEfficiency.timing_balance && <div style={{ marginTop:5, fontFamily:mono, fontSize:10, color:C.faint }}>timing: {capitalEfficiency.timing_balance}</div>}
              {(capitalEfficiency.compare_against||[]).length>0 && <div style={{ marginTop:5, fontFamily:mono, fontSize:10, color:C.faint }}>compare: {(capitalEfficiency.compare_against||[]).join(" / ")}</div>}
            </div>
          )}
          {hasAccountPlacement && (
            <div style={{ marginTop:8, paddingTop:7, borderTop:`1px solid ${C.line}`, color:C.text }}>
              <div style={{ fontWeight:700, color:C.green }}>Account placement</div>
              {accountPlacement.summary && <div style={{ marginTop:4 }}>{accountPlacement.summary}</div>}
              {accountPlacement.why && <div style={{ marginTop:4 }}>Why: {accountPlacement.why}</div>}
              {accountPlacement.rule && <div style={{ marginTop:5, fontFamily:mono, fontSize:10, color:C.faint }}>rule: {accountPlacement.rule}</div>}
            </div>
          )}
          {hasDisconfirmation && (
            <div style={{ marginTop:8, paddingTop:7, borderTop:`1px solid ${C.line}`, color:C.text }}>
              <div style={{ fontWeight:700, color:C.amber }}>What could make this wrong?</div>
              {disconfirmation.summary && <div style={{ marginTop:4 }}>{disconfirmation.summary}</div>}
              {(disconfirmation.invalidates_if||[]).length>0 && <div style={{ marginTop:5, fontFamily:mono, fontSize:10, color:C.faint }}>invalidates: {(disconfirmation.invalidates_if||[]).join(" / ")}</div>}
              {(disconfirmation.confirm_before_acting||[]).length>0 && <div style={{ marginTop:5, fontFamily:mono, fontSize:10, color:C.faint }}>confirm: {(disconfirmation.confirm_before_acting||[]).join(" / ")}</div>}
            </div>
          )}
          {(a.goalChannels.length>0 || a.capitalEffect || a.synthesisChanges || a.capitalPriorityScore!=null) && <div style={{ marginTop:8, fontFamily:mono, fontSize:10, color:C.faint }}>hidden decision metadata: channels {a.goalChannels.join(" / ") || "n/a"}{a.capitalEffect?` | capital: ${a.capitalEffect}`:""}{a.synthesisChanges?` | changes: ${a.synthesisChanges}`:""}{a.goalScore!=null?` | score: ${a.goalScore}/100`:""}{a.capitalPriorityScore!=null?` | priority: ${a.capitalPriorityScore}`:""}</div>}
          {a.missingEvidence.length>0 && <div style={{ marginTop:5, fontFamily:mono, fontSize:10, color:C.amber }}>missing: {a.missingEvidence.join(" / ")}</div>}
          <div style={{ marginTop:8, fontFamily:mono, fontSize:10, color:C.faint }}>{stamp} | {footerLabel} | no trade without gate</div>
        </div>
      )}
    </div>
  );
}
function TodayPriorityStack({ rows, openMap, setOpen, posOpen, setPosOpen }) {
  const summary = rows.length
    ? compactJoin([`${rows.length} promoted`, rows[0]&&`${rows[0].ticker?`${rows[0].ticker} `:""}${clipText(rows[0].title,72)}`])
    : "No time-sensitive ideas or research items promoted above the detail lanes.";
  return (
    <Section id="today-priority-stack" title="Today Priority Stack" icon="!" badge={rows.length?`${rows.length}`:"quiet"} badgeColor={rows.length?C.amber:C.green} summary={summary} openMap={openMap} setOpen={setOpen} defaultOpen={false}>
      {!rows.length && <div style={{ ...card, fontSize:12, color:C.faint }}>No promoted Today items. Use the lower sections as backup context, not as a forced action list.</div>}
      {(rows||[]).map((r,i)=>{
        const key=`todaypri${r.key||i}`, isO=posOpen[key];
        const tone = todayTone(r);
        const c = toneColor(tone);
        return (
          <div key={key} style={{ ...toneCard(tone), marginBottom:8 }}>
            <div onClick={()=>setPosOpen(st=>({...st,[key]:!st[key]}))} style={{ cursor:"pointer" }} title={r.tooltip||"Click for why, invalidation, and data backup."}>
              <div style={{ display:"flex", alignItems:"baseline", gap:8, flexWrap:"wrap" }}>
                <span style={{ fontFamily:mono, fontSize:11, color:C.faint }}>#{i+1}</span>
                {r.ticker && <span style={{ fontFamily:mono, fontWeight:800, fontSize:13.5, color:C.text }}>{r.ticker}</span>}
                <span style={{ fontSize:12.8, fontWeight:750, color:C.text }}>{r.title}</span>
              </div>
              <div style={{ marginTop:7, display:"flex", alignItems:"center", gap:7, flexWrap:"wrap" }}>
                <span title="Action posture this row changes or requires." style={{ fontFamily:mono, fontSize:11, color:c, border:`1px solid ${c}66`, borderRadius:99, padding:"1px 8px", background:`${c}12` }}>{r.posture}</span>
                <span title="Where the full source row lives." style={{ fontFamily:mono, fontSize:11, color:C.dim, border:`1px solid ${C.line}`, borderRadius:99, padding:"1px 8px", background:C.panel2 }}>{r.home}</span>
                {r.timing && <span title="How quickly the assumption can decay." style={{ fontFamily:mono, fontSize:11, color:C.faint }}>{r.timing}</span>}
                {r.source && <span title="Primary source or lane." style={{ fontFamily:mono, fontSize:11, color:C.faint }}>{r.source}</span>}
              </div>
              <div style={{ marginTop:8, fontSize:12.2, color:C.text }}><span style={{ color:C.dim, fontWeight:700 }}>What this changes:</span> {r.changes}</div>
              <div style={{ marginTop:4, fontSize:12.2, color:C.text }}><span style={{ color:C.dim, fontWeight:700 }}>Next:</span> {r.nextStep}</div>
              <div style={{ marginTop:5, fontSize:11.7, color:C.dim }}><span style={{ color:C.faint, fontWeight:700 }}>Why here:</span> {r.whyHere}</div>
              <div style={{ marginTop:7, display:"flex", justifyContent:"flex-end" }}>
                <span style={{ fontSize:11, color:c }}>{isO?"hide backup ^":"data backup v"}</span>
              </div>
            </div>
            {isO && (
              <div style={{ marginTop:8, paddingTop:8, borderTop:`1px solid ${C.line}`, fontSize:11.5, color:C.dim }}>
                {r.details && <div style={{ marginBottom:5 }}><span style={{ color:C.faint, fontWeight:700 }}>Detail:</span> {r.details}</div>}
                {r.invalidates && <div style={{ marginBottom:5, color:C.amber }}><span style={{ fontWeight:700 }}>Invalidates:</span> {r.invalidates}</div>}
                {r.backup && <div style={{ fontFamily:mono, fontSize:10.5, color:C.faint }}>backup: {r.backup}</div>}
              </div>
            )}
          </div>
        );
      })}
    </Section>
  );
}

function SystemCriticalBanner({ sourceAudits, onOpenSystem }) {
  const cloud = ((sourceAudits||{}).cloud_routines)||{};
  const routineRows = cloud.rows||[];
  const failedRows = routineRows.filter(r=>String(r.last_status||"").toLowerCase()==="failed");
  const missing = cloud.missing_scheduled_success||[];
  if(!failedRows.length && !missing.length) return null;
  const c = failedRows.length ? C.red : C.amber;
  if(!failedRows.length){
    return (
      <div style={{ marginTop:8, marginBottom:7, padding:"5px 8px", border:`1px solid ${C.amber}44`, borderRadius:7, background:`${C.amber}0b`, display:"flex", alignItems:"center", justifyContent:"space-between", gap:8, flexWrap:"wrap" }}>
        <div style={{ fontFamily:mono, fontSize:10.8, color:C.dim }}>System proof: {missing.length} scheduled receipt gap{missing.length===1?"":"s"}; manual fixes can be reviewed in System.</div>
        <button onClick={onOpenSystem} style={{ cursor:"pointer", border:`1px solid ${C.amber}55`, background:`${C.amber}10`, color:C.amber, borderRadius:6, padding:"2px 7px", fontFamily:mono, fontSize:10 }}>System</button>
      </div>
    );
  }
  const primary = failedRows[0] || {};
  const title = failedRows.length
    ? `System data gap: ${failedRows.map(r=>r.routine_name||r.routine_id).slice(0,2).join(", ")} failed${failedRows.length>2?` +${failedRows.length-2}`:""}`
    : `System proof gap: ${missing.length} scheduled routine${missing.length===1?"":"s"} not fully proven`;
  return (
    <div style={{ ...toneCard("red"), marginTop:12, marginBottom:8 }}>
      <div style={{ display:"flex", alignItems:"baseline", justifyContent:"space-between", gap:10, flexWrap:"wrap" }}>
        <div style={{ fontSize:13.2, fontWeight:800, color:C.text }}>{title}</div>
        <button onClick={onOpenSystem} style={{ cursor:"pointer", border:`1px solid ${c}66`, background:`${c}12`, color:c, borderRadius:7, padding:"3px 8px", fontFamily:mono, fontSize:10.5 }}>open System</button>
      </div>
      <div style={{ marginTop:5, fontSize:11.8, color:C.dim }}>{cloud.line || "Cloud routine proof is incomplete."}</div>
      <div style={{ marginTop:4, fontSize:11.8, color:C.amber }}>Dashboard impact: {routineImpact(primary)}</div>
    </div>
  );
}

function DecisionLaneBoard({ lanes, adviceRows, posOpen, setPosOpen, stamp }) {
  const order = ["key_now","recheck_before_acting","important_backlog","quiet_watch"];
  const byKey = Object.fromEntries((lanes||[]).map(l=>[String(l.section.key||l.section.label||""), l]));
  const complete = [
    ...order.map(key=>byKey[key] || { section:{ key, label:decisionGroupMeta(key).title, ranks:[] }, rows:[] }),
    ...(lanes||[]).filter(l=>!order.includes(String(l.section.key||""))),
  ];
  const sorted = complete.sort((a,b)=>{
    const ak = order.indexOf(String(a.section.key||""));
    const bk = order.indexOf(String(b.section.key||""));
    return (ak<0?99:ak) - (bk<0?99:bk);
  });
  const firstWithRows = sorted.find(l=>(l.rows||[]).length);
  const defaultKey = ((firstWithRows||sorted[0])&&((firstWithRows||sorted[0]).section.key)) || "";
  const selectedKey = posOpen["today:selectedLane"] || defaultKey;
  const selected = sorted.find(l=>String(l.section.key||"")===String(selectedKey)) || sorted[0];
  if(!sorted.length) return <div style={{ ...card, fontSize:12, color:C.faint }}>No action-engine decisions in this feed build.</div>;
  const selectedMeta = decisionGroupMeta(selected.section.key, selected.section.label);
  const selectedColor = toneColor(selectedMeta.tone);
  const selectedNames = selected.rows.map(a=>a.ticker||a.what).filter(Boolean).slice(0,5).join(", ");
  return (
    <div>
      <div style={{ marginBottom:8, fontFamily:mono, fontSize:10.5, color:C.faint, textTransform:"uppercase", letterSpacing:0 }}>Decision lane board</div>
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(160px,1fr))", gap:8, marginBottom:10 }}>
        {sorted.map(({section, rows})=>{
          const meta = decisionGroupMeta(section.key, section.label);
          const c = toneColor(meta.tone);
          const active = String(section.key||"")===String(selected.section.key||"");
          const names = rows.map(a=>a.ticker||a.what).filter(Boolean).slice(0,3).join(", ");
          const summary = section.key==="recheck_before_acting"
            ? laneEvidenceSummary(rows)
            : names ? `Includes: ${names}` : "Nothing in this lane.";
          return (
            <button
              key={section.key||section.label}
              onClick={()=>setPosOpen(st=>({...st,"today:selectedLane":section.key||section.label}))}
              title={meta.description}
              style={{ cursor:"pointer", textAlign:"left", minHeight:74, padding:"9px 10px", border:`1px solid ${active?c:C.line}`, borderRadius:8, background:active?`${c}16`:C.panel2, color:C.text, boxShadow:active?`0 0 0 1px ${c}55 inset`:"none" }}
            >
              <div style={{ display:"flex", justifyContent:"space-between", gap:8, alignItems:"baseline" }}>
                <span style={{ fontSize:13, fontWeight:850, color:C.text }}>{meta.title}</span>
                <span style={{ fontFamily:mono, fontSize:10.5, color:c, border:`1px solid ${c}66`, borderRadius:99, padding:"1px 7px", background:`${c}10` }}>{rows.length}</span>
              </div>
              <div style={{ marginTop:5, fontSize:11.2, color:C.dim, lineHeight:1.35 }}>{clipText(summary, 96)}</div>
            </button>
          );
        })}
      </div>
      <div style={{ ...toneCard(selectedMeta.tone), padding:"10px 11px", borderLeft:`2px solid ${selectedColor}` }}>
        <div style={{ display:"flex", alignItems:"baseline", justifyContent:"space-between", gap:8, flexWrap:"wrap" }}>
          <div style={{ display:"flex", alignItems:"baseline", gap:8, flexWrap:"wrap" }}>
            <span style={{ fontSize:13.4, fontWeight:850, color:C.text }}>{selectedMeta.title}</span>
            <span style={{ fontFamily:mono, fontSize:10.8, color:selectedColor, border:`1px solid ${selectedColor}66`, borderRadius:99, padding:"1px 8px", background:`${selectedColor}12` }}>{selected.rows.length}</span>
          </div>
        </div>
        <div style={{ marginTop:5, fontSize:11.8, color:C.dim }}>{selectedMeta.description}</div>
        <div style={{ marginTop:4, fontSize:12, color:C.text }}>{selected.section.key==="recheck_before_acting" ? laneEvidenceSummary(selected.rows) : (selectedNames ? `Includes: ${selectedNames}` : "Nothing in this lane right now.")}</div>
        <div style={{ marginTop:9 }}>
        {selected.rows.map(a=>(
          <TodayActionCard
            key={`${selected.section.key||"lane"}${a.rank}${a.ticker||a.kind}`}
            a={a}
            keyPrefix={`lane${selected.section.key||"x"}`}
            posOpen={posOpen}
            setPosOpen={setPosOpen}
            stamp={stamp}
            footerLabel="review prompt - no trade without gate"
            showAging={true}
            showSizing={true}
            advisorNote={advisorForAction(a, adviceRows)}
          />
        ))}
        </div>
      </div>
    </div>
  );
}
function TodayDecisionQueue({ actions, actionGroups, ifIWereYou, sourceAudits, marketOpenPacket, reallocationBrief, openMap, setOpen, posOpen, setPosOpen, stamp, onOpenSystem, onOpenOps, onOpenReallocation }) {
  const sections = ((actionGroups||{}).sections||[]).filter(s=>(s.ranks||[]).length);
  const byRank = Object.fromEntries((actions||[]).map(a=>[a.rank,a]));
  const lanes = sections.map(section=>({ section, rows:(section.ranks||[]).map(r=>byRank[r]).filter(Boolean) })).filter(x=>x.rows.length);
  const counts = (actionGroups||{}).counts||{};
  const urgent = counts.key_now||0;
  const refresh = counts.recheck_before_acting||0;
  const backlog = counts.important_backlog||0;
  const summary = urgent
    ? `${urgent} decision${urgent===1?"":"s"} need action or explicit deferral now.`
    : refresh
      ? `No immediate trade command; ${refresh} setup${refresh===1?"":"s"} are blocked by named evidence checks.`
      : backlog
        ? `${backlog} backlog decision${backlog===1?"":"s"} to compare against better uses of capital.`
        : "No forced portfolio action right now.";
  const badgeColor = urgent ? C.red : refresh ? C.amber : backlog ? C.blue : C.green;
  const adviceRows = (ifIWereYou&&ifIWereYou.rows)||[];
  return (
    <>
      <SystemCriticalBanner sourceAudits={sourceAudits} onOpenSystem={onOpenSystem} />
      <Section
        id="today-decisions"
        title="Today Decisions"
        icon="!"
        badge={(actions||[]).length?`${(actions||[]).length}`:"quiet"}
        badgeColor={badgeColor}
        description="Start here. This is the only Today surface for action, waiting, checking assumptions, sizing, trimming, hedging, or deciding no capital yet; the filter is early-retirement capital efficiency."
        summary={summary}
        openMap={openMap}
        setOpen={setOpen}
        defaultOpen={true}
      >
        <TodayWorkNowStrip
          packet={marketOpenPacket}
          reallocationBrief={reallocationBrief}
          counts={counts}
          onOpenOps={onOpenOps}
          onOpenReallocation={onOpenReallocation}
        />
        <DecisionLaneBoard
          lanes={lanes}
          adviceRows={adviceRows}
          posOpen={posOpen}
          setPosOpen={setPosOpen}
          stamp={stamp}
        />
      </Section>
    </>
  );
}

function CommandRow({ row }) {
  return (
    <div style={{ ...card, marginBottom:8 }}>
      <div style={{ fontSize:13, fontWeight:700, color:C.text }}>{row.name}</div>
      <div style={{ marginTop:4, fontSize:12.3, color:C.dim }}>{row.desc}</div>
      {row.command && <div style={{ marginTop:7, fontFamily:mono, fontSize:10.8, color:C.faint, overflowWrap:"anywhere" }}>{row.command}</div>}
    </div>
  );
}

function CommandLink({ row }) {
  return (
    <a href={row.href} target="_blank" rel="noreferrer" style={{ ...card, marginBottom:8, display:"block", textDecoration:"none" }}>
      <div style={{ fontSize:13, fontWeight:700, color:C.text }}>{row.name}</div>
      <div style={{ marginTop:4, fontSize:12.3, color:C.dim }}>{row.desc}</div>
      <div style={{ marginTop:7, fontFamily:mono, fontSize:10.8, color:C.faint, overflowWrap:"anywhere" }}>{row.href}</div>
    </a>
  );
}

export default function ConvictionCockpit({ feed = FEED } = {}) {
  const [mode, setMode] = useState("action");   // action = decide/do | book = holdings | news = Fundstrat | system = health/upgrades
  // Lazy + memoized view-model. shared is always built; each view's lanes are built ONLY when that
  // view is active, so on Action bookVM (the per-position map) is never called — holdings aren't
  // iterated at all. useMemo means toggling back and forth doesn't recompute either side.
  const shared = sharedVM(feed);
  const A = useMemo(() => ["action","ideas","news","ops","system","reallocation"].includes(mode) ? actionVM(feed) : null, [mode, feed]);
  const B = useMemo(() => mode === "book"   ? bookVM(feed)   : null, [mode, feed]);
  const VM = { ...shared, ...(A || {}), ...(B || {}) };   // only the active view's lanes + shared
  const R = (VM.research && ((VM.research.pending||[]).length || (VM.research.done||[]).length))
    ? VM.research : CURATED.research;   // live Research Queue when present, else curated fallback
  const CATS = (VM.catalysts||[]).map(c=>({
    d: c.date||"",
    e: `${c.ticker?`${c.ticker} · `:""}${c.label||"Catalyst"}`,
    note: `${c.days_out!=null?`in ~${c.days_out}d · `:""}${c.source||"Catalyst Calendar"}`
  }));
  const [open, setOpen] = useState(loadStoredOpen);
  const [posOpen, setPosOpen] = useState({});
  const [collapsed, setCollapsed] = useState({});
  const [view, setView] = useState("agg");
  const [legend, setLegend] = useState(false);
  useEffect(() => {
    if(typeof window === "undefined" || !window.localStorage) return;
    try {
      window.localStorage.setItem(OPEN_STORAGE_KEY, JSON.stringify(open));
    } catch (_) {}
  }, [open]);
  const dirColor = (d)=> d==="up"?C.green : d==="down"?C.red : C.dim;
  const ownerFilter = (own) => view==="agg" ? true : view==="parents" ? own.includes("p") : own.includes("s");
  const portfolioViewKey = view==="agg" ? "combined" : view;
  const portfolioView = VM.portfolioViews && VM.portfolioViews.views ? VM.portfolioViews.views[portfolioViewKey] : null;
  const effectiveExposure = portfolioView && portfolioView.effective_exposure ? portfolioView.effective_exposure : null;
  const layerIssues = VM.heartbeat.filter(h=>h.statusLabel!=="ok");
  const checkIssues = VM.laneStatus.filter(r=>!["data","clear"].includes(r.statusLabel) && !DEFERRED_OPTIONAL_SOURCE_KEYS.has(r.key));
  const deferredChecks = VM.laneStatus.filter(r=>!["data","clear"].includes(r.statusLabel) && DEFERRED_OPTIONAL_SOURCE_KEYS.has(r.key));
  const statusSummary = compactJoin([
    `${VM.heartbeat.length} layers${layerIssues.length?`, ${layerIssues.length} issue${layerIssues.length===1?"":"s"}`:", green"}`,
    `${VM.laneStatus.length} checks${checkIssues.length?`, ${checkIssues.map(r=>`${r.label} ${r.statusLabel}`).slice(0,3).join(", ")}${checkIssues.length>3?` +${checkIssues.length-3}`:""}`:", green"}${deferredChecks.length?` | deferred: ${deferredChecks.map(r=>r.label).slice(0,2).join(", ")}`:""}`
  ]);

  return (
    <div style={{ background:C.bg, color:C.text, fontFamily:sans, minHeight:"100%", padding:"18px 13px 52px", lineHeight:1.45 }}>
      <div style={{ maxWidth:840, margin:"0 auto" }}>

        {/* HEADER */}
        <div style={{ display:"flex", alignItems:"baseline", justifyContent:"space-between", flexWrap:"wrap", gap:8 }}>
          <div style={{ fontSize:20, fontWeight:700, letterSpacing:-0.3 }}>Conviction Cockpit</div>
          <div style={{ fontFamily:mono, fontSize:11.5, color:C.faint }}>{VM.stamp}</div>
        </div>

        {mode==="system" && (<Section id="status-checks" title="Status & Checks" icon="!" badge={checkIssues.length||layerIssues.length?`${checkIssues.length+layerIssues.length} issue${checkIssues.length+layerIssues.length===1?"":"s"}`:"green"} badgeColor={checkIssues.length||layerIssues.length?C.amber:C.green} summary={statusSummary} openMap={open} setOpen={setOpen} defaultOpen={false}>
          {VM.heartbeat.length>0 && (
            <div style={{ display:"flex", flexWrap:"wrap", gap:6, alignItems:"center" }}>
              <span style={{ fontFamily:mono, fontSize:10, color:C.faint, marginRight:2 }}>LAYERS</span>
              {VM.heartbeat.map((h,i)=>(
                <span key={i} title={`${h.note}${h.lastRun?` | last ${h.lastRun}`:""}`}
                  style={{ display:"inline-flex", alignItems:"center", gap:5, padding:"2px 8px", borderRadius:99,
                    fontSize:10.5, fontFamily:mono, color:h.c, border:`1px solid ${h.c}44`, background:`${h.c}12`, whiteSpace:"nowrap" }}>
                  <span style={{ width:6, height:6, borderRadius:99, background:h.c }} />{h.layer}{h.statusLabel!=="ok"?` | ${h.statusLabel}`:""}
                </span>
              ))}
            </div>
          )}
          {VM.laneStatus.length>0 && (
            <div style={{ marginTop:8, display:"flex", flexWrap:"wrap", gap:6, alignItems:"center" }}>
              <span style={{ fontFamily:mono, fontSize:10, color:C.faint, marginRight:2 }}>CHECKS</span>
              {VM.laneStatus.map((r,i)=>(
                <span key={i} title={`${r.detail}${r.missingImpact?` | ${r.missingImpact}`:""}${r.nextStep?` | next: ${r.nextStep}`:""}${r.checkedAt?` | checked ${r.checkedAt}`:""}`}
                  style={{ display:"inline-flex", alignItems:"center", gap:5, padding:"2px 8px", borderRadius:99,
                    fontSize:10.5, fontFamily:mono, color:r.c, border:`1px solid ${r.c}44`, background:`${r.c}10`, whiteSpace:"nowrap" }}>
                  {r.label} | {r.statusLabel}{r.count?` ${r.count}`:""}
                </span>
              ))}
            </div>
          )}
        </Section>)}

        {/* HEARTBEAT — layer run-status strip (Tier-1: see the machine ran) */}
        {false && VM.heartbeat.length>0 && (
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

        {/* VIEW TOGGLE — shared chrome (sticky): ⚡ Action ⇄ 📊 Book */}
        {false && VM.laneStatus.length>0 && (
          <div style={{ marginTop:8, display:"flex", flexWrap:"wrap", gap:6, alignItems:"center" }}>
            <span style={{ fontFamily:mono, fontSize:10, color:C.faint, marginRight:2 }}>CHECKS</span>
            {VM.laneStatus.map((r,i)=>(
              <span key={i} title={`${r.detail}${r.missingImpact?` · ${r.missingImpact}`:""}${r.nextStep?` · next: ${r.nextStep}`:""}${r.checkedAt?` Â· checked ${r.checkedAt}`:""}`}
                style={{ display:"inline-flex", alignItems:"center", gap:5, padding:"2px 8px", borderRadius:99,
                  fontSize:10.5, fontFamily:mono, color:r.c, border:`1px solid ${r.c}44`, background:`${r.c}10`, whiteSpace:"nowrap" }}>
                {r.label} Â· {r.statusLabel}{r.count?` ${r.count}`:""}
              </span>
            ))}
          </div>
        )}

        <div style={{ position:"sticky", top:0, zIndex:10, background:C.bg, marginTop:6, paddingTop:10, paddingBottom:8, borderBottom:`1px solid ${C.line}` }}>
          <div style={{ display:"flex", gap:4, background:C.panel, border:`1px solid ${C.line}`, borderRadius:9, padding:3, width:"fit-content" }}>
            {[["action","Today"],["reallocation","Reallocation"],["book","Book"],["ideas","Ideas"],["news","News"],["ops","Ops"],["system","System"],["commands","Commands"]].map(([k,l])=>(
              <button key={k} onClick={()=>setMode(k)} style={{ cursor:"pointer", border:"none", borderRadius:6, padding:"6px 14px", fontSize:12.5, fontWeight:600, fontFamily:sans, background: mode===k?C.panel3:"transparent", color: mode===k?C.text:C.faint }}>{l}</button>
            ))}
          </div>
        </div>

        {/* ⚡ ACTION VIEW ───────────────────────────────────────────── */}
        {["action","ideas","news","ops","reallocation"].includes(mode) && (<>

        {mode==="action" && (<>

        <div style={{ marginTop:12, display:"flex", alignItems:"center", gap:8, fontSize:11.5, color:C.faint, flexWrap:"wrap" }}>
          <span>Full book + per-name detail lives in Book.</span>
          <button onClick={()=>setMode("book")} style={{ cursor:"pointer", background:"transparent", border:`1px solid ${C.line}`, borderRadius:7, padding:"3px 9px", fontSize:11, fontFamily:mono, color:C.dim }}>open Book</button>
        </div>

        <TodayDecisionQueue
          actions={VM.actions||[]}
          actionGroups={VM.actionGroups||{}}
          ifIWereYou={VM.ifIWereYou}
          sourceAudits={VM.sourceAudits}
          marketOpenPacket={VM.marketOpenPacket}
          reallocationBrief={VM.reallocationBrief}
          openMap={open}
          setOpen={setOpen}
          posOpen={posOpen}
          setPosOpen={setPosOpen}
          stamp={VM.stamp}
          onOpenSystem={()=>setMode("system")}
          onOpenOps={()=>setMode("ops")}
          onOpenReallocation={()=>setMode("reallocation")}
        />

        <Section id="source-conflicts" title="Source conflicts" icon="!" badge={(VM.sourceConflicts.rows||[]).length?`${(VM.sourceConflicts.rows||[]).length}`:"0"} badgeColor={(VM.sourceConflicts.rows||[]).length?C.amber:C.faint} summary={(() => { const rows=(VM.sourceConflicts.rows||[]), first=rows[0]; return rows.length ? compactJoin([`${rows.length} split`, first&&`${first.ticker}: ${clipText(first.action_posture||first.decision_effect||"",72)}`]) : "No bull/bear source splits affecting current holdings."; })()} openMap={open} setOpen={setOpen} defaultOpen={false}>
          {(VM.sourceConflicts.rows||[]).length===0 && <div style={{ ...card, fontSize:12, color:C.faint }}>No current bull/bear source splits surfaced by the conviction engine.</div>}
          {(VM.sourceConflicts.rows||[]).map((r,i)=>(
            <div key={"src-conflict"+(r.ticker||i)} style={{ ...card, marginBottom:7, borderColor:C.amber+"44" }}>
              <div style={{ display:"flex", alignItems:"baseline", gap:8, flexWrap:"wrap" }}>
                <span style={{ fontFamily:mono, fontWeight:800, color:C.text }}>{r.ticker||"PORTFOLIO"}</span>
                <span style={{ fontFamily:mono, fontSize:10.5, color:C.amber, border:`1px solid ${C.amber}55`, borderRadius:99, padding:"1px 8px" }}>{r.label||"source split"}</span>
                {r.scope && <span style={{ fontFamily:mono, fontSize:10.5, color:C.faint }}>{r.scope.replace("_"," ")}</span>}
              </div>
              {r.bull_read && <div style={{ marginTop:7, fontSize:12, color:C.green }}>Bull: {r.bull_read}</div>}
              {r.bear_read && <div style={{ marginTop:4, fontSize:12, color:C.red }}>Bear: {r.bear_read}</div>}
              <div style={{ marginTop:7, fontSize:12.5, color:C.text }}>Posture: {r.action_posture||"Hold; no add until the split resolves."}</div>
              <div style={{ marginTop:4, fontSize:11.5, color:C.faint }}>{r.decision_effect||"Review only; no execution."}</div>
            </div>
          ))}
          <div style={{ marginTop:6, fontFamily:mono, fontSize:10.5, color:C.faint }}>{VM.sourceConflicts.honesty_rule||"Conflicts downgrade action posture; they do not execute trades."}</div>
        </Section>

        </>)}

        {mode==="ideas" && (<>

        <Section id="top-prospects" title="Top Prospects" icon="+" badge={(VM.prospects.counts&&VM.prospects.counts.total)?`${VM.prospects.counts.total}`:"0"} badgeColor={(VM.prospects.counts&&VM.prospects.counts.total)?C.accent:C.faint} summary={(() => { const P=VM.prospects||{}, ct=P.counts||{}, rows=prospectRows(P), top=rows[0]||{}; return ct.total ? compactJoin([`${ct.total} tracked`, `${ct.act_now||0} act-now`, `${ct.hot||0} hot`, `${ct.uncorroborated||0} uncorroborated`, top.ticker&&`top: ${top.ticker} ${top.urgency||top.direction||""}`]) : "No tracked prospects in this feed."; })()} openMap={open} setOpen={setOpen} defaultOpen={false}>
          {(() => {
            const P = VM.prospects||{}, ct = P.counts||{};
            if(!ct.total) return <div style={{ ...card, fontSize:12, color:C.faint }}>No prospects tracked in this feed build.</div>;
            const URG = { ACT_NOW:C.red, HOT:C.amber, BUILDING:C.blue, QUIET:C.faint };
            const CORR = (c)=> c==="Vetted-Buy"?C.green : c==="Uncorroborated"?C.faint : C.blue;
            const pctxt = (x)=> x==null?"" : `${x>=0?"+":""}${(x*100).toFixed(1)}% vs SPY`;
            const pcol = (x)=> x==null?C.faint : x>=0?C.green:C.red;
            const prow = (r)=>{
              const key="prosp"+(r.ticker||""), isO=posOpen[key], uc=URG[r.urgency]||C.faint;
              return (
                <div key={key} style={{ ...card, marginBottom:7, borderColor:uc+"33" }}>
                  <div onClick={()=>setPosOpen(st=>({...st,[key]:!st[key]}))} style={{ cursor:r.summary?"pointer":"default" }}>
                    <div style={{ display:"flex", alignItems:"baseline", gap:8, flexWrap:"wrap" }}>
                      <span style={{ fontFamily:mono, fontWeight:700, fontSize:13.5, color:C.text }}>{r.ticker}</span>
                      <span style={{ fontFamily:mono, fontSize:11, color:uc, border:`1px solid ${uc}55`, borderRadius:99, padding:"1px 8px" }}>{r.urgency}</span>
                      {r.pct_vs_spy!=null && <span style={{ fontFamily:mono, fontSize:11, color:pcol(r.pct_vs_spy) }}>{pctxt(r.pct_vs_spy)}</span>}
                      <span style={{ fontFamily:mono, fontSize:11, color:CORR(r.corroboration), border:`1px solid ${CORR(r.corroboration)}55`, borderRadius:99, padding:"1px 8px" }}>{r.corroboration}</span>
                    </div>
                    {(r.sources&&r.sources.length>0) && <div style={{ marginTop:6, display:"flex", gap:5, flexWrap:"wrap" }}>{r.sources.map((s,j)=>(<span key={j} style={{ fontFamily:mono, fontSize:10, color:C.dim, border:`1px solid ${C.line}`, borderRadius:99, padding:"1px 7px" }}>{s}</span>))}</div>}
                  </div>
                  {isO && r.summary && <div style={{ marginTop:8, paddingTop:8, borderTop:`1px solid ${C.line}`, ...muted }}>{r.summary}</div>}
                </div>
              );
            };
            return (
              <div>
                <div style={{ fontSize:11, color:C.faint, fontFamily:mono, marginBottom:8 }}>{ct.total} tracked | {ct.act_now||0} act-now | {ct.hot||0} hot | {ct.uncorroborated||0} uncorroborated | candidate surface, not the book</div>
                {(P.hot||[]).length>0 && <div style={{ fontFamily:mono, fontSize:10, color:C.faint, textTransform:"uppercase", letterSpacing:0.5, marginBottom:4 }}>Hot</div>}
                {(P.hot||[]).map(prow)}
                {((P.movers_best||[]).length>0 || (P.movers_worst||[]).length>0) && (
                  <div style={{ ...card, marginBottom:7, marginTop:2 }}>
                    <div style={{ fontFamily:mono, fontSize:10, color:C.faint, textTransform:"uppercase", letterSpacing:0.5, marginBottom:5 }}>Movers | vs SPY</div>
                    {(P.movers_best||[]).map((r,j)=>(<div key={"mb"+j} style={{ fontSize:12, color:C.text, marginBottom:2 }}><span style={{ fontFamily:mono, fontWeight:700 }}>{r.ticker}</span> <span style={{ color:pcol(r.pct_vs_spy), fontFamily:mono }}>{pctxt(r.pct_vs_spy)}</span></div>))}
                    {(P.movers_worst||[]).map((r,j)=>(<div key={"mw"+j} style={{ fontSize:12, color:C.dim, marginBottom:2 }}><span style={{ fontFamily:mono, fontWeight:700 }}>{r.ticker}</span> <span style={{ color:pcol(r.pct_vs_spy), fontFamily:mono }}>{pctxt(r.pct_vs_spy)}</span></div>))}
                  </div>
                )}
                {(P.sell_fast||[]).length>0 && (
                  <div style={{ ...card, marginBottom:7, borderColor:C.red+"44", background:C.red+"0a" }}>
                    <div style={{ fontFamily:mono, fontSize:10, color:C.red, textTransform:"uppercase", letterSpacing:0.5, marginBottom:5 }}>Sell-fast - FS dropped a name you may hold</div>
                    {(P.sell_fast||[]).map((r,j)=>(<div key={"sf"+j} style={{ fontSize:12.5, color:C.text, marginBottom:2 }}><span style={{ fontFamily:mono, fontWeight:700 }}>{r.ticker}</span> <span style={{ color:C.dim }}>{r.summary||"avoid"}</span></div>))}
                  </div>
                )}
              </div>
            );
          })()}
        </Section>

        <Section id="asymmetric-opportunities" title="Asymmetric Opportunities" icon="+" badge={(VM.asymmetricOpportunities&&VM.asymmetricOpportunities.count)?`${VM.asymmetricOpportunities.count}`:"0"} badgeColor={(VM.asymmetricOpportunities&&VM.asymmetricOpportunities.count)?C.green:C.faint} summary={(() => { const O=VM.asymmetricOpportunities||{}, rows=O.rows||[]; return O.count ? compactJoin([`${O.count} review prompts`, tickerSummary(rows), rows[0]&&clipText(rows[0].reason,72)]) : "No evidence-backed asymmetric prompt."; })()} openMap={open} setOpen={setOpen} defaultOpen={false}>
          <div style={{ fontSize:11, color:C.faint, fontFamily:mono, marginBottom:8 }}>DEDUPED ACROSS ACTIONS / TARGET DRIFT / PROSPECTS / RADAR / UW FLOW. Review prompts only; no auto-trade.</div>
          {!(VM.asymmetricOpportunities&&VM.asymmetricOpportunities.count) && <div style={{ ...card, fontSize:12, color:C.faint }}>No asymmetric opportunity row cleared the evidence filter in this feed build.</div>}
          {((VM.asymmetricOpportunities&&VM.asymmetricOpportunities.rows)||[]).map((r,i)=>(
            <div key={`${r.ticker}${i}`} style={{ ...card, marginBottom:7, borderColor:C.green+"33" }}>
              <div style={{ display:"flex", alignItems:"baseline", gap:8, flexWrap:"wrap" }}>
                <span style={{ fontFamily:mono, fontWeight:700, fontSize:13.5, color:C.text }}>{r.ticker}</span>
                <span style={{ fontFamily:mono, fontSize:11, color:C.green, border:`1px solid ${C.green}55`, borderRadius:99, padding:"1px 8px" }}>score {r.score}</span>
                <span style={{ fontFamily:mono, fontSize:11, color:C.faint }}>{r.source}</span>
              </div>
              <div style={{ marginTop:6, fontSize:12.5, color:C.text }}>{r.reason}</div>
              {r.evidence && <div style={{ marginTop:4, fontSize:11.5, color:C.dim }}>Evidence: {r.evidence}</div>}
              <div style={{ marginTop:4, fontFamily:mono, fontSize:10.5, color:C.faint }}>decays {r.decay_window||"source dependent"} | {r.action||"review"}</div>
            </div>
          ))}
        </Section>

        </>)}

        {mode==="ops" && (<>

        <Section id="uw-action-runbook" title="UW Action Runbook" icon="?" badge={((VM.uwActionRunbook||{}).rows||[]).length?`${((VM.uwActionRunbook||{}).rows||[]).length}`:"0"} badgeColor={((VM.uwActionRunbook||{}).rows||[]).length?C.blue:C.faint} summary={(() => { const U=VM.uwActionRunbook||{}, P=U.endpoint_proof||VM.uwEndpointProof||{}; return compactJoin([U.line||"No active UW check set.", P.line&&clipText(P.line,88)]); })()} openMap={open} setOpen={setOpen} defaultOpen={false}>
          <div style={{ fontSize:11, color:C.faint, fontFamily:mono, marginBottom:8 }}>SCENARIO CHECKLIST FROM THE CURRENT DASHBOARD. It recommends UW endpoint groups and ticker scopes; it is not proof any endpoint was fetched.</div>
          {(() => {
            const P=(VM.uwActionRunbook||{}).endpoint_proof || VM.uwEndpointProof || {};
            if(!P.line) return null;
            const ok=P.status==="has_data", fail=P.status==="failed";
            const hasBlockers=(P.blockers||[]).length>0;
            const col=ok&&!hasBlockers?C.green:(fail?C.red:C.amber);
            const interp=P.interpretation_counts||{};
            return (
              <div style={{ ...card, marginBottom:8, borderColor:col+"44", background:col+"0a" }}>
                <div style={{ display:"flex", alignItems:"baseline", gap:8, flexWrap:"wrap" }}>
                  <span style={{ fontFamily:mono, fontSize:11, color:col, border:`1px solid ${col}55`, borderRadius:99, padding:"1px 8px" }}>endpoint proof {(P.status||"unknown").replaceAll("_"," ")}</span>
                  <span style={{ fontSize:12.3, color:C.text }}>{P.line}</span>
                </div>
                {Object.keys(interp).length>0 && <div style={{ marginTop:4, fontFamily:mono, fontSize:10.5, color:C.faint }}>interpretation: supports {interp.supports||0} | contradicts {interp.contradicts||0} | inconclusive {interp.inconclusive||0} | missing {interp.missing||0}</div>}
                {(P.blockers||[]).slice(0,3).map((b,i)=>(<div key={i} style={{ marginTop:4, fontSize:11.5, color:C.dim }}>Proof blocker: {b}</div>))}
                {(P.rows||[]).slice(0,5).map((r,i)=>(<div key={`${r.mode||""}${r.endpoint||""}${r.ticker||""}${i}`} style={{ marginTop:4, fontFamily:mono, fontSize:10.5, color:C.faint }}>endpoint: {r.mode} / {r.endpoint}{r.ticker?` ${r.ticker}`:""} - {r.decision_interpretation||r.status} ({r.status})</div>))}
              </div>
            );
          })()}
          {!(((VM.uwActionRunbook||{}).rows||[]).length) && <div style={{ ...card, fontSize:12, color:C.faint }}>No active UW check set in this feed build.</div>}
          {((VM.uwActionRunbook||{}).rows||[]).map((r,i)=>(
            <div key={`${r.mode||r.label}${i}`} style={{ ...card, marginBottom:8, borderColor:C.blue+"33" }}>
              <div style={{ display:"flex", alignItems:"baseline", gap:8, flexWrap:"wrap" }}>
                <span style={{ fontFamily:mono, fontWeight:700, fontSize:13.5, color:C.text }}>{r.label||r.mode}</span>
                <span style={{ fontFamily:mono, fontSize:11, color:C.blue, border:`1px solid ${C.blue}55`, borderRadius:99, padding:"1px 8px" }}>priority {r.priority||i+1}</span>
              </div>
              {r.why && <div style={{ marginTop:6, fontSize:12.5, color:C.text }}>{r.why}</div>}
              {r.operator_question && <div style={{ marginTop:4, fontSize:11.5, color:C.dim }}>Question: {r.operator_question}</div>}
              {(r.ticker_scope||[]).length>0 && <div style={{ marginTop:6, fontFamily:mono, fontSize:10.5, color:C.faint }}>tickers: {(r.ticker_scope||[]).join(", ")}</div>}
              {(r.market_checks||[]).length>0 && <div style={{ marginTop:4, fontFamily:mono, fontSize:10.5, color:C.faint }}>market checks: {(r.market_checks||[]).join(", ")}</div>}
              {(r.ticker_checks||[]).length>0 && <div style={{ marginTop:4, fontFamily:mono, fontSize:10.5, color:C.faint }}>ticker checks: {(r.ticker_checks||[]).join(", ")}</div>}
              <div style={{ marginTop:7, paddingTop:7, borderTop:`1px solid ${C.line}`, fontSize:11.5, color:C.amber }}>Blocks action if: {r.blocks_action_if||"fresh confirming evidence is missing"}</div>
              <div style={{ marginTop:4, fontSize:11.5, color:C.dim }}>Promote when: {r.promote_when||"routed checks confirm the dashboard thesis"}</div>
              <div style={{ marginTop:4, fontSize:11.5, color:C.dim }}>Downgrade when: {r.downgrade_when||"fresh evidence fails or contradicts"}</div>
            </div>
          ))}
          {(VM.uwActionRunbook||{}).command && <div style={{ marginTop:6, fontFamily:mono, fontSize:10.5, color:C.faint }}>Command: {(VM.uwActionRunbook||{}).command}</div>}
        </Section>

        </>)}

        {mode==="reallocation" && (<>

        <Section id="reallocation-brief" title="Candidate Reallocation Brief" icon="#" badge={((VM.reallocationBrief||{}).counts||{}).adds?`${((VM.reallocationBrief||{}).counts||{}).adds} adds`:"0"} badgeColor={(VM.reallocationBrief||{}).status==="test_data_only"?C.amber:(((VM.reallocationBrief||{}).counts||{}).adds?C.green:C.faint)} summary={clipText((VM.reallocationBrief||{}).line || "No reallocation brief in this feed build.")} openMap={open} setOpen={setOpen} defaultOpen={false}>
          {(() => {
            const R=VM.reallocationBrief||{}, rows=R.rows||[], trims=R.trims||[], funding=R.funding||{}, special=R.special_reviews||[], capital=R.capital_efficiency||{}, optionsGate=R.options_gate||{};
            const warn=R.status==="test_data_only";
            if(!R.line) return <div style={{ ...card, fontSize:12, color:C.faint }}>No reallocation brief in this feed build.</div>;
            return (
              <div>
                <div style={{ ...card, marginBottom:8, borderColor:(warn?C.amber:C.green)+"44", background:(warn?C.amber:C.green)+"0a" }}>
                  <div style={{ display:"flex", alignItems:"baseline", justifyContent:"space-between", gap:8, flexWrap:"wrap" }}>
                    <div style={{ fontSize:12.5, color:warn?C.amber:C.text, fontWeight:650 }}>{R.line}</div>
                    <span style={{ fontFamily:mono, fontSize:11, color:warn?C.amber:C.green, border:`1px solid ${(warn?C.amber:C.green)}55`, borderRadius:99, padding:"1px 8px" }}>{(R.status||"candidate").replaceAll("_"," ")}</span>
                  </div>
                  <div style={{ marginTop:6, fontFamily:mono, fontSize:10.5, color:C.faint }}>pool {money(funding.pool_total_usd)} | allocated {money(funding.allocated_usd)} | shortfall {money(funding.shortfall_usd)}</div>
                  {capital.summary && <div style={{ marginTop:5, fontSize:11.5, color:C.dim }}>Capital efficiency: {capital.summary}</div>}
                  {capital.timing_balance && <div style={{ marginTop:4, fontSize:11.5, color:C.dim }}>Timing: {capital.timing_balance}</div>}
                  {capital.do_nothing_risk && <div style={{ marginTop:4, fontSize:11.5, color:C.dim }}>Do nothing: {capital.do_nothing_risk}</div>}
                  {optionsGate.line && <div style={{ marginTop:4, fontSize:11.5, color:C.amber }}>Options gate: {optionsGate.line}</div>}
                  {(R.blockers||[]).slice(0,4).map((b,i)=>(<div key={i} style={{ marginTop:5, fontSize:11.5, color:C.dim }}>Blocker: {b}</div>))}
                </div>
                {rows.slice(0,6).map((r,i)=>{
                  const funded=(r.funded_by||[]).map(f=>`${f.ticker} ${money(f.notional_usd)}`).join(", ");
                  const cap=r.capital_efficiency||{};
                  const opt=r.options_review_prompt||{};
                  const placement=r.account_placement||{};
                  const tone = placementTone(placement);
                  const placementColor = toneColor(tone);
                  return (
                    <div key={`${r.ticker}${i}`} style={{ ...toneCard(tone), marginBottom:7 }}>
                      <div style={{ display:"flex", alignItems:"baseline", gap:8, flexWrap:"wrap" }}>
                        <span style={{ fontFamily:mono, fontWeight:700, fontSize:13.5, color:C.text }}>{r.ticker}</span>
                        <span style={{ fontFamily:mono, fontSize:11, color:C.green, border:`1px solid ${C.green}55`, borderRadius:99, padding:"1px 8px" }}>add {money(r.notional_usd)}</span>
                        <span style={{ fontFamily:mono, fontSize:11, color:C.faint }}>{r.sequence}</span>
                        {r.gate && <span style={{ fontFamily:mono, fontSize:11, color:C.amber, border:`1px solid ${C.amber}55`, borderRadius:99, padding:"1px 8px" }}>gate {r.gate}</span>}
                      </div>
                      {r.entry_note && <div style={{ marginTop:5, fontSize:12, color:C.text }}>{r.entry_note}</div>}
                      {funded && <div style={{ marginTop:4, fontFamily:mono, fontSize:10.5, color:C.faint }}>funded by: {funded}</div>}
                      {placement.summary && <div style={{ marginTop:4, fontSize:11.5, color:placementColor }}>Account: {placement.summary}</div>}
                      {placement.why && <div style={{ marginTop:4, fontFamily:mono, fontSize:10.5, color:C.faint }}>account why: {placement.why}</div>}
                      {cap.summary && <div style={{ marginTop:4, fontSize:11.5, color:C.dim }}>Capital: {cap.summary}</div>}
                      {cap.consequence_of_doing_nothing && <div style={{ marginTop:4, fontSize:11.5, color:C.dim }}>Do nothing: {cap.consequence_of_doing_nothing}</div>}
                      {opt.label && <div style={{ marginTop:4, fontSize:11.5, color:C.amber }}>Options: {opt.label}; {opt.max_loss_gate}</div>}
                      {(r.blockers||[]).length>0 && <div style={{ marginTop:4, fontSize:11.5, color:C.dim }}>Blocks: {(r.blockers||[]).join(", ")}</div>}
                      {r.disconfirmation && <div style={{ marginTop:4, fontSize:11.5, color:C.dim }}>Disconfirm: {r.disconfirmation}</div>}
                    </div>
                  );
                })}
                {trims.length>0 && <div style={{ ...card, marginTop:8 }}>
                  <div style={{ fontFamily:mono, fontSize:10, color:C.faint, textTransform:"uppercase", marginBottom:5 }}>Funding trims</div>
                  {trims.slice(0,6).map((r,i)=>(<div key={`${r.ticker}${i}`} style={{ fontSize:12, color:C.dim, marginBottom:3 }}><span style={{ fontFamily:mono, fontWeight:700, color:C.text }}>{r.ticker}</span> trim {money(r.notional_usd)} <span style={{ color:C.faint }}>{(r.funds||[]).map(f=>`${f.ticker} ${money(f.notional_usd)}`).join(", ")}</span></div>))}
                </div>}
                {special.length>0 && <div style={{ ...card, marginTop:8 }}>
                  <div style={{ fontFamily:mono, fontSize:10, color:C.faint, textTransform:"uppercase", marginBottom:5 }}>Special re-checks</div>
                  {special.slice(0,5).map((r,i)=>(<div key={`${r.ticker}${i}`} style={{ fontSize:12, color:C.dim, marginBottom:4 }}><span style={{ fontFamily:mono, fontWeight:700, color:C.text }}>{r.ticker}</span> <span style={{ color:C.amber }}>{(r.status||"").replaceAll("_"," ")}</span> - {r.next_step}</div>))}
                </div>}
                {R.command && <div style={{ marginTop:6, fontFamily:mono, fontSize:10.5, color:C.faint }}>Command: {R.command}</div>}
              </div>
            );
          })()}
        </Section>

        <Section id="target-drift" title="Target drift" icon="🎯" badge={VM.targetDrift.actionable_count?`${VM.targetDrift.actionable_count}`:"0"} badgeColor={VM.targetDrift.actionable_count?C.amber:C.faint} summary={clipText(VM.targetDrift.line || "Target drift not checked in this feed build.")} openMap={open} setOpen={setOpen} defaultOpen={false}>
          <div style={{ fontSize:11, color:C.faint, fontFamily:mono, marginBottom:8 }}>CURRENT BOOK vs REALLOCATION WORKING MODEL — sizing gaps only; candidates, not orders.</div>
          {!VM.targetDrift.line && <div style={{ ...card, fontSize:12, color:C.faint }}>Target drift not checked in this feed build.</div>}
          {VM.targetDrift.line && (
            <div style={{ ...card, marginBottom:8, borderColor:(VM.targetDrift.actionable_count?C.amber:C.line)+"44" }}>
              <div style={{ fontSize:12.5, color:VM.targetDrift.actionable_count?C.amber:C.dim }}>{VM.targetDrift.line}</div>
              <div style={{ marginTop:8, display:"flex", gap:6, flexWrap:"wrap" }}>
                <span style={{ fontFamily:mono, fontSize:10.5, color:C.green, border:`1px solid ${C.green}44`, borderRadius:99, padding:"1px 7px" }}>under {VM.targetDrift.undersized_count||0}</span>
                <span style={{ fontFamily:mono, fontSize:10.5, color:C.red, border:`1px solid ${C.red}44`, borderRadius:99, padding:"1px 7px" }}>over {VM.targetDrift.oversized_count||0}</span>
                <span style={{ fontFamily:mono, fontSize:10.5, color:C.amber, border:`1px solid ${C.amber}44`, borderRadius:99, padding:"1px 7px" }}>missing {VM.targetDrift.missing_count||0}</span>
                {(VM.targetDrift.alarm_count||0)>0 && <span style={{ fontFamily:mono, fontSize:10.5, color:C.red, border:`1px solid ${C.red}66`, borderRadius:99, padding:"1px 7px" }}>alarm {VM.targetDrift.alarm_count}</span>}
              </div>
            </div>
          )}
          {(VM.targetDrift.rows||[]).map((r,i)=>{
            const dc = r.direction==="OVERSIZED" ? C.red : (r.direction==="UNDERSIZED"||r.direction==="MISSING") ? C.green : C.dim;
            return (
              <div key={`${r.ticker}${i}`} style={{ ...card, marginBottom:7, display:"grid", gridTemplateColumns:"72px 1fr auto", gap:8, alignItems:"center", borderColor:dc+"33" }}>
                <span style={{ fontFamily:mono, fontWeight:700, fontSize:13, color:C.text }}>{r.ticker}</span>
                <div style={{ minWidth:0 }}>
                  <div style={{ fontSize:12.5, color:dc, fontWeight:600 }}>{(r.direction||"").toLowerCase().replace("_"," ")}</div>
                  <div style={{ marginTop:2, fontFamily:mono, fontSize:11, color:C.faint }}>actual {typeof r.actual_pct==="number"?r.actual_pct.toFixed(1):"?"}% · target {typeof r.target_pct==="number"?r.target_pct.toFixed(1):"?"}%</div>
                </div>
                <span style={{ fontFamily:mono, fontSize:11.5, color:C.dim }}>{typeof r.drift_absolute_pct==="number"?`${r.drift_absolute_pct>0?"+":""}${r.drift_absolute_pct.toFixed(1)}pp`:""}</span>
              </div>
            );
          })}
        </Section>

        </>)}

        {mode==="ideas" && (<>

        {/* FROM RESEARCH — ticker-specific Research-Queue items as their OWN
            candidate-action category (engine ⑦c research_actions), SEPARATE from
            Today's actions; deduped against the action+catalyst lanes
            (catalyst-precedence). Default-open when populated. */}
        <Section id="research-actions" title="From Research" icon="🔎" badge={VM.researchActions.length?`${VM.researchActions.length}`:"0"} badgeColor={VM.researchActions.length?C.blue:C.faint} summary={VM.researchActions.length ? compactJoin([`${VM.researchActions.length} review items`, VM.researchActions[0]&&`${VM.researchActions[0].ticker?`${VM.researchActions[0].ticker} `:""}${clipText(VM.researchActions[0].what,70)}`]) : "No high-priority Research Queue action rows."} openMap={open} setOpen={setOpen} defaultOpen={false}>
          <div style={{ fontSize:11, color:C.faint, fontFamily:mono, marginBottom:8 }}>FROM YOUR RESEARCH QUEUE — high-priority / dated dossiers as candidate reviews. SEPARATE from Today's actions; a name on the catalyst lane shows there, not here. Drill in chat to act.</div>
          {VM.researchActions.length===0 && <div style={{ ...card, fontSize:12, color:C.faint }}>Nothing from research right now — no high-priority or dated Research-Queue items in this feed build.</div>}
          {VM.researchActions.map((a)=>(
            <ActionCard
              key={"rsch"+a.rank+(a.ticker||a.kind)}
              a={a}
              keyPrefix="rsch"
              posOpen={posOpen}
              setPosOpen={setPosOpen}
              stamp={VM.stamp}
              footerLabel="research candidate — you decide, you size"
            />
          ))}
        </Section>

        {/* FRESH SIGNALS — Morning-Scan ⑦ signals not yet promoted to an action.
            A scan/watch surface, not a gated action. */}
        <Section id="fresh-signals" title="Fresh signals" icon="📨" badge={VM.freshSignals.length?`${VM.freshSignals.length}`:"0"} badgeColor={VM.freshSignals.length?C.blue:C.faint} summary={VM.freshSignals.length ? compactJoin([`${VM.freshSignals.length} fresh`, tickerSummary(VM.freshSignals), VM.freshSignals[0]&&clipText(VM.freshSignals[0].what,64)]) : "No fresh signal rows in this feed build."} openMap={open} setOpen={setOpen} defaultOpen={false}>
          <div style={{ fontSize:11, color:C.faint, fontFamily:mono, marginBottom:8 }}>MORNING-SCAN SIGNALS (⑦) — fresh movement / new names, not yet a fired action. A watch surface; promote in chat.</div>
          {VM.freshSignals.length===0 && <div style={{ ...card, fontSize:12, color:C.faint }}>No fresh signals in this feed build.</div>}
          {VM.freshSignals.map((s,i)=>{
            const key="fsig"+i+(s.t||""), isO=posOpen[key];
            return (
              <div key={key} style={{ ...card, marginBottom:8 }}>
                <div onClick={()=>setPosOpen(st=>({...st,[key]:!st[key]}))} style={{ cursor:(s.why||s.detail)?"pointer":"default" }}>
                  <div style={{ display:"flex", alignItems:"baseline", gap:8, flexWrap:"wrap" }}>
                    {s.t && <span style={{ fontFamily:mono, fontWeight:700, fontSize:13.5, color:C.text }}>{s.t}</span>}
                    <span style={{ fontSize:12.5, fontWeight:600, color:C.text }}>{s.what}</span>
                  </div>
                  <div style={{ marginTop:7, display:"flex", alignItems:"center", gap:7, flexWrap:"wrap" }}>
                    {s.urgLabel && <span style={{ fontFamily:mono, fontSize:11, color:C.blue, border:`1px solid ${C.blue}55`, borderRadius:99, padding:"1px 8px" }}>{s.urgLabel}</span>}
                    {s.when && <span style={{ fontFamily:mono, fontSize:11, color:C.faint }}>{s.when}</span>}
                  </div>
                  {s.why && <div style={{ marginTop:8, fontSize:12.5, color:C.dim }}>{s.why}</div>}
                  {s.detail && (
                    <div style={{ marginTop:7, display:"flex", justifyContent:"flex-end" }}>
                      <span style={{ fontSize:11, color:C.blue }}>{isO?"hide ▲":"detail ▾"}</span>
                    </div>
                  )}
                </div>
                {isO && s.detail && (
                  <div style={{ marginTop:8, paddingTop:8, borderTop:`1px solid ${C.line}`, ...muted }}>{s.detail}</div>
                )}
              </div>
            );
          })}
        </Section>

        </>)}

        {/* SIGNAL LOG — external Morning Scan notes. Watch-only; never promoted into actions here. */}
        {mode==="ops" && (<Section id="signal-log" title="Signal Log" icon="📡" badge={VM.signalLog.length?`${VM.signalLog.length}`:"0"} badgeColor={VM.signalLog.length?C.blue:C.faint} summary={VM.signalLog.length ? compactJoin([`${VM.signalLog.length} watch rows`, tickerSummary(VM.signalLog), VM.signalLog[0]&&clipText(VM.signalLog[0].signal,72)]) : "Signal Log not supplied in this feed build."} openMap={open} setOpen={setOpen} defaultOpen={false}>
          <div style={{ fontSize:11, color:C.faint, fontFamily:mono, marginBottom:8 }}>MORNING SCAN LOG — watch-only items from the external signal log.</div>
          {VM.signalLog.length===0 && <div style={{ ...card, fontSize:12, color:C.faint }}>Signal Log not supplied in this feed build.</div>}
          {VM.signalLog.map((r,i)=>(
            <div key={`${r.ticker||"sig"}${i}`} style={{ ...card, marginBottom:8, borderColor:C.blue+"33" }}>
              <div style={{ display:"flex", alignItems:"baseline", gap:8, flexWrap:"wrap" }}>
                {r.ticker && <span style={{ fontFamily:mono, fontWeight:700, fontSize:13.5, color:C.text }}>{r.ticker}</span>}
                <span style={{ fontSize:12.5, fontWeight:600, color:C.text }}>{r.signal}</span>
              </div>
              <div style={{ marginTop:7, display:"flex", gap:7, flexWrap:"wrap", alignItems:"center" }}>
                {r.priority && <span style={{ fontFamily:mono, fontSize:11, color:C.blue, border:`1px solid ${C.blue}55`, borderRadius:99, padding:"1px 8px" }}>{r.priority}</span>}
                {r.date && <span style={{ fontFamily:mono, fontSize:11, color:C.faint }}>{r.date}</span>}
                <span style={{ fontFamily:mono, fontSize:11, color:C.dim }}>{r.source}</span>
              </div>
              {r.note && <div style={{ marginTop:8, fontSize:12.5, color:C.dim }}>{r.note}</div>}
            </div>
          ))}
        </Section>)}

        {/* BULLISH FLOW (UW) — read-only WATCH lane: the daily UW opportunity
            cache (Strand-3 surfacing / B1), grouped by ticker (uw_flow = one
            name, one bucket). NOT conviction — the gated Chunk-2 hook is separate. */}
        {mode==="ideas" && (<Section id="bullish-flow" title="Bullish flow (UW)" icon="🌊" badge={(VM.bullishFlow.rows||[]).length?`${VM.bullishFlow.tickers} · ${VM.bullishFlow.count}`:"0"} badgeColor={(VM.bullishFlow.rows||[]).length?C.green:C.faint} summary={((VM.bullishFlow.rows||[]).length) ? compactJoin([`${VM.bullishFlow.tickers||0} tickers`, `${VM.bullishFlow.count||0} signals`, VM.bullishFlow.as_of&&`as of ${VM.bullishFlow.as_of}`, tickerSummary(VM.bullishFlow.rows)]) : "No bullish-flow signals in this feed build."} openMap={open} setOpen={setOpen} defaultOpen={false}>
          <div style={{ fontSize:11, color:C.faint, fontFamily:mono, marginBottom:8 }}>DAILY UW OPTIONS RADAR — fresh bullish flow / sweeps / OI build / dark-pool, grouped by name (5 sweeps = one bucket). A WATCH surface, not conviction; not a fired action.{VM.bullishFlow.as_of?` · as-of ${VM.bullishFlow.as_of}`:""}</div>
          {(VM.bullishFlow.rows||[]).length===0 && <div style={{ ...card, fontSize:12, color:C.faint }}>No bullish-flow signals in this feed build.</div>}
          {(VM.bullishFlow.rows||[]).map((r,i)=>{
            const isBull=r.direction==="bullish", dc=isBull?C.green:C.red;
            const key="bflow"+i+(r.ticker||""), isO=posOpen[key];
            return (
              <div key={key} style={{ ...card, marginBottom:8, borderColor:dc+"33" }}>
                <div onClick={()=>setPosOpen(st=>({...st,[key]:!st[key]}))} style={{ cursor:(r.evidence&&r.evidence.length)?"pointer":"default" }}>
                  <div style={{ display:"flex", alignItems:"baseline", gap:8, flexWrap:"wrap" }}>
                    <span style={{ fontFamily:mono, fontWeight:700, fontSize:13.5, color:C.text }}>{r.ticker}</span>
                    <span style={{ fontFamily:mono, fontSize:11, color:dc, border:`1px solid ${dc}55`, borderRadius:99, padding:"1px 8px" }}>{isBull?"▲":"▼"} {r.direction}</span>
                    <span style={{ fontFamily:mono, fontSize:11, color:C.dim, border:`1px solid ${C.line}`, borderRadius:99, padding:"1px 8px" }}>{r.strength}</span>
                    {r.n>1 && <span style={{ fontFamily:mono, fontSize:11, color:C.faint }}>×{r.n}</span>}
                    {r.parked && <span title="Parked / MONITOR sleeve — deliberately benched; flow here is NOT a green light. Add only on a real re-entry trigger." style={{ fontFamily:mono, fontSize:11, color:C.amber, border:`1px solid ${C.amber}55`, borderRadius:99, padding:"1px 8px" }}>🔒 Parked</span>}
                  </div>
                  <div style={{ marginTop:7, fontFamily:mono, fontSize:11, color:C.faint }}>{(r.signal_types||[]).join(" · ")}</div>
                  {(r.evidence&&r.evidence.length>0) && (
                    <div style={{ marginTop:7, display:"flex", justifyContent:"flex-end" }}>
                      <span style={{ fontSize:11, color:dc }}>{isO?"hide ▲":"evidence ▾"}</span>
                    </div>
                  )}
                </div>
                {isO && r.evidence && r.evidence.length>0 && (
                  <div style={{ marginTop:8, paddingTop:8, borderTop:`1px solid ${C.line}`, ...muted }}>
                    {r.evidence.map((e,j)=>(<div key={j} style={{ marginBottom:3 }}>• {e}</div>))}
                    <div style={{ marginTop:6, fontFamily:mono, fontSize:10, color:C.faint }}>uw_flow — one independence bucket per name · watch, not a buy</div>
                  </div>
                )}
              </div>
            );
          })}
        </Section>)}

        {/* SYNTHESIS — today's read / state-of-play (Daily Synthesis; Tier-1) */}
        {mode==="news" && (<Section id="synthesis" title="Today's read — synthesis" icon="🧠" badge={VM.synthesis&&VM.synthesis.date?VM.synthesis.date:""} badgeColor={C.blue} summary={clipText((VM.synthesis||{}).state_of_play || (VM.synthesis||{}).delta || "No synthesis loaded in this feed build.")} openMap={open} setOpen={setOpen} defaultOpen={false}>
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
        </Section>)}

        {/* RADAR — endorsed names not owned yet (engine ⑨ radar block) */}
        {mode==="ops" && (<>

        <Section id="source-audits" title="Source Proof" icon="!" badge={(() => { const c=((VM.sourceAudits||{}).cloud_routines)||{}; return c.expected_count?`${c.scheduled_success_count||0}/${c.expected_count}`:"audit"; })()} badgeColor={(() => { const c=((VM.sourceAudits||{}).cloud_routines)||{}; return c.expected_count && (c.scheduled_success_count||0) >= c.expected_count ? C.green : C.amber; })()} summary={(() => { const A=VM.sourceAudits||{}, c=A.cloud_routines||{}, u=A.uw_endpoint_proof||VM.uwEndpointProof||{}; return compactJoin([c.line&&clipText(c.line,72), u.line&&clipText(u.line,72)]); })()} openMap={open} setOpen={setOpen} defaultOpen={false}>
          {(() => {
            const A=VM.sourceAudits||{};
            const rows=[
              ["Cloud routines", (A.cloud_routines||{}).line],
              ["Connector evidence", (A.connector_evidence||{}).line],
              ["UW routing", (A.uw_routing||{}).line],
              ["UW action runbook", (A.uw_action_runbook||{}).line],
              ["UW endpoint proof", (A.uw_endpoint_proof||{}).line],
              ["Fundstrat intake", (A.fundstrat||{}).line],
              ["Notion/writeback", (A.notion_writeback||{}).line],
            ].filter(r=>r[1]);
            if(!rows.length) return <div style={{ ...card, fontSize:12, color:C.faint }}>No source-audit block in this feed build.</div>;
            return (
              <div>
                {rows.map(([label,line])=>(
                  <div key={label} style={{ ...card, marginBottom:7 }}>
                    <div style={{ fontFamily:mono, fontSize:10.5, color:C.faint, textTransform:"uppercase", marginBottom:3 }}>{label}</div>
                    <div style={{ fontSize:12.5, color:C.text }}>{line}</div>
                  </div>
                ))}
                {(((A.cloud_routines||{}).missing_scheduled_success)||[]).length>0 && <div style={{ fontSize:11.5, color:C.dim }}>Background scheduled receipts pending: {((A.cloud_routines||{}).missing_scheduled_success||[]).slice(0,6).map(r=>r.routine_name||r.routine_id).join(", ")}</div>}
                {(((A.uw_routing||{}).rows)||[]).length>0 && <div style={{ fontSize:11.5, color:C.dim, marginTop:6 }}>UW next checks: {((A.uw_routing||{}).rows||[]).slice(0,3).map(r=>`${r.label||r.mode}: ${(r.top_endpoints||[]).slice(0,5).join(", ")}`).join(" | ")}</div>}
              </div>
            );
          })()}
        </Section>

        <Section id="feedback" title="Feedback loops" icon="🔁" badge={(() => { const f=VM.feedback||{}, sc=f.source_calls||{}, sp=sc.persistence||{}, oa=f.open_actions||{}; const n=(sc.overdue_count||0)+(sp.loud_count||0)+(sp.provisional_count||0)+(oa.count||0); return n?`${n}`:"0"; })()} badgeColor={(() => { const f=VM.feedback||{}, sc=f.source_calls||{}, sp=sc.persistence||{}, oa=f.open_actions||{}; return (sp.loud_count||0)?C.red:((sc.overdue_count||0)+(sp.provisional_count||0)+(oa.count||0))?C.amber:C.faint; })()} summary={(() => { const f=VM.feedback||{}, sc=f.source_calls||{}, oa=f.open_actions||{}; return compactJoin([oa.line&&clipText(oa.line,72), sc.line&&clipText(sc.line,72)]); })()} openMap={open} setOpen={setOpen} defaultOpen={false}>
          {(() => {
            const f=VM.feedback||{}, sc=f.source_calls||{}, cal=sc.calibration||{}, sp=sc.persistence||{}, oa=f.open_actions||{}, recs=f.recommendations||[];
            return (
              <div>
                <div style={{ ...card, marginBottom:8, borderColor:(sc.overdue_count?C.amber:C.line)+"44" }}>
                  <div style={{ fontFamily:mono, fontSize:10, color:C.faint, textTransform:"uppercase", letterSpacing:0.5, marginBottom:5 }}>Source scoring</div>
                  <div style={{ fontSize:12.5, color:sc.overdue_count?C.amber:C.dim }}>{sc.line||"Source calls not checked."}</div>
                  {(sc.rates||[]).length>0 && <div style={{ marginTop:7, display:"flex", gap:6, flexWrap:"wrap" }}>{(sc.rates||[]).slice(0,4).map((r,i)=>(<span key={i} style={{ fontFamily:mono, fontSize:10.5, color:C.dim, border:`1px solid ${C.line}`, borderRadius:99, padding:"1px 7px" }}>{r.source}: {r.hit_rate==null?"n/a":`${Math.round(r.hit_rate*100)}%`} n={r.n}</span>))}</div>}
                  {(sc.due||[]).length>0 && <div style={{ marginTop:7 }}>{(sc.due||[]).map((it,i)=>(<div key={i} style={{ fontSize:12, color:C.dim, marginBottom:3 }}><span style={{ fontFamily:mono, fontWeight:700, color:C.text }}>{it.ticker}</span> {it.source}{it.tier?` ${it.tier}`:""} scoring overdue {it.overdue_days}d <span style={{ color:C.faint }}>window {it.window_end||"n/a"}</span></div>))}</div>}
                  {cal.line && <div style={{ marginTop:8, paddingTop:7, borderTop:`1px solid ${C.line}`, fontSize:11.5, color:cal.status==="checked_fresh"?C.green:cal.status==="stale"?C.red:C.amber }}>{cal.line}</div>}
                  {sp.line && <div style={{ marginTop:8, paddingTop:7, borderTop:`1px solid ${C.line}` }}>
                    <div style={{ fontFamily:mono, fontSize:10, color:C.faint, textTransform:"uppercase", letterSpacing:0.5, marginBottom:4 }}>Source persistence</div>
                    <div style={{ fontSize:12.5, color:(sp.loud_count||0)?C.red:(sp.provisional_count||0)?C.amber:C.dim }}>{sp.line}</div>
                    {(sp.clusters||[]).length>0 && <div style={{ marginTop:7 }}>{(sp.clusters||[]).map((it,i)=>(<div key={i} style={{ fontSize:12, color:C.dim, marginBottom:3 }}><span style={{ fontFamily:mono, fontWeight:700, color:it.loud?C.red:it.provisional?C.amber:C.text }}>{it.ticker}</span> {it.source} {it.count}x/{it.within_days}d{it.has_ab?" A/B":""} <span style={{ color:C.faint }}>{it.loud?"LOUD":it.provisional?"PROVISIONAL":it.quiet_reason||"quiet"}</span></div>))}</div>}
                  </div>}
                </div>
                <div style={{ ...card, marginBottom:8, borderColor:(oa.count?C.amber:C.line)+"44" }}>
                  <div style={{ fontFamily:mono, fontSize:10, color:C.faint, textTransform:"uppercase", letterSpacing:0.5, marginBottom:5 }}>Open action backlog</div>
                  <div style={{ fontSize:12.5, color:oa.count?C.amber:C.dim }}>{oa.line||"Open action backlog not checked."}</div>
                  {(oa.items||[]).length>0 && <div style={{ marginTop:7 }}>{(oa.items||[]).map((it,i)=>(<div key={i} style={{ fontSize:12, color:C.dim, marginBottom:3 }}><span style={{ fontFamily:mono, fontWeight:700, color:C.text }}>{it.ticker}</span> {it.age_days}d open{it.move_since?` · ${it.move_since}`:""} <span style={{ color:C.faint }}>({it.source||it.kind})</span></div>))}</div>}
                  {(oa.recent_history||[]).length>0 && <div style={{ marginTop:8, paddingTop:7, borderTop:`1px solid ${C.line}` }}>
                    <div style={{ fontFamily:mono, fontSize:10, color:C.faint, textTransform:"uppercase", letterSpacing:0.5, marginBottom:4 }}>Recent resolutions</div>
                    {(oa.recent_history||[]).slice(0,3).map((it,i)=>(<div key={i} style={{ fontSize:12, color:C.dim, marginBottom:3 }}><span style={{ fontFamily:mono, fontWeight:700, color:C.text }}>{it.ticker}</span> {it.status}{it.reason?` · ${it.reason}`:""}</div>))}
                  </div>}
                </div>
                {recs.length>0 && <div style={{ fontSize:11.5, color:C.faint, fontFamily:mono }}>NEXT: {recs[0]}</div>}
              </div>
            );
          })()}
        </Section>

        </>)}

        {mode==="ideas" && (<Section id="radar" title="Radar — endorsed, not owned" icon="📡" badge={VM.radar.length?`${VM.radar.length}`:"0"} badgeColor={VM.radar.length?C.blue:C.faint} summary={VM.radar.length ? compactJoin([`${VM.radar.length} endorsed/unowned`, tickerSummary(VM.radar), VM.radar[0]&&clipText(VM.radar[0].direction||VM.radar[0].author,64)]) : "No endorsed unowned radar rows."} openMap={open} setOpen={setOpen} defaultOpen={false}>
          <div style={{ fontSize:11, color:C.faint, fontFamily:mono, marginBottom:8 }}>ENDORSED by a daily analyst call · NOT in the book · not a parked 🔒 MONITOR sleeve. A watch surface — not a position.</div>
          {VM.radar.length===0 && <div style={{ ...card, fontSize:12, color:C.faint }}>Nothing on the radar — no endorsed, un-owned names in the latest daily calls.</div>}
          {VM.radar.map((r,i)=>{
            const key="radar"+r.ticker+i, isO=posOpen[key];
            return (
              <div key={key} style={{ ...card, marginBottom:8 }}>
                <div onClick={()=>setPosOpen(st=>({...st,[key]:!st[key]}))} style={{ cursor:r.quote?"pointer":"default" }}>
                  <div style={{ display:"flex", alignItems:"baseline", gap:8, flexWrap:"wrap" }}>
                    <span style={{ fontFamily:mono, fontWeight:700, fontSize:13.5, color:C.text }}>{r.ticker}</span>
                    {r.author && <span style={{ fontFamily:mono, fontSize:11, color:C.dim }}>{r.author}</span>}
                    {r.direction && <span style={{ fontSize:11.5, color:C.blue, border:`1px solid ${C.blue}55`, borderRadius:99, padding:"0px 7px" }}>{r.direction}</span>}
                    {r.date && <span style={{ fontFamily:mono, fontSize:10.5, color:C.faint, marginLeft:"auto" }}>{r.date}</span>}
                  </div>
                  {r.levels && <div style={{ marginTop:7, fontFamily:mono, fontSize:11.5, color:C.dim }}>{r.levels}</div>}
                  {r.quote && (
                    <div style={{ marginTop:7, display:"flex", justifyContent:"flex-end" }}>
                      <span style={{ fontSize:11, color:C.blue }}>{isO?"hide call ▲":"call ▾"}</span>
                    </div>
                  )}
                </div>
                {isO && r.quote && (
                  <div style={{ marginTop:8, paddingTop:8, borderTop:`1px solid ${C.line}`, ...muted }}>{r.quote}</div>
                )}
              </div>
            );
          })}
        </Section>)}

        </>)}

        {/* 📊 BOOK VIEW ─────────────────────────────────────────────── */}
        {mode==="book" && (<>

        {/* HOLDINGS (from FEED) */}
        <Section id="holdings" title="Holdings" icon="📊" summary={portfolioView ? compactJoin([`${view==="agg"?"Combined":view==="parents"?"Parents":"SKB"} ${money(portfolioView.total_value)}`, `${(portfolioView.rows||[]).length} direct rows`, (VM.portfolioViews||{}).as_of&&`as of ${(VM.portfolioViews||{}).as_of}`]) : compactJoin([`${(VM.holdings||[]).length} sleeve groups`, "account view pending"])} openMap={open} setOpen={setOpen} defaultOpen={false}>
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
              Showing names held by <b style={{ color:C.dim }}>{view==="parents"?"Parents":"SKB"}</b>. When account positions are available, the account view below uses exact direct $/% rows; the detailed holding rows remain conviction-oriented.
            </div>
          )}

          {portfolioView && (
            <div style={{ ...card, marginBottom:10, borderColor:C.blue+"55", background:C.blue+"08" }}>
              <div style={{ display:"flex", alignItems:"baseline", justifyContent:"space-between", gap:10, flexWrap:"wrap" }}>
                <div>
                  <div style={{ fontSize:12, fontWeight:700, color:C.text }}>{view==="agg"?"Combined":view==="parents"?"Parents":"SKB"} account view</div>
                  <div style={{ ...muted, fontSize:11.5 }}>{VM.portfolioViews.caveat||"Direct holdings only."}</div>
                  {(VM.portfolioViews.allocation_guidance||{}).basis && <div style={{ marginTop:3, fontFamily:mono, fontSize:10.5, color:C.faint }}>Allocation guide: working model target + Fundstrat cue | {(VM.portfolioViews.allocation_guidance||{}).basis}{(VM.portfolioViews.allocation_guidance||{}).fundstrat_source_date?` | Fundstrat ${(VM.portfolioViews.allocation_guidance||{}).fundstrat_source_date}`:""}</div>}
                </div>
                <div style={{ fontFamily:mono, fontSize:16, fontWeight:700, color:C.text }}>{money(portfolioView.total_value)}</div>
              </div>
              <div style={{ marginTop:10, display:"grid", gridTemplateColumns:"repeat(auto-fit, minmax(150px, 1fr))", gap:8 }}>
                {(portfolioView.categories||[]).map((c,i)=>(
                  <div key={i} style={{ border:`1px solid ${C.line}`, borderRadius:8, padding:"7px 8px", background:C.panel }}>
                    <div style={{ display:"flex", justifyContent:"space-between", gap:8 }}>
                      <span style={{ fontSize:11.5, color:C.text, fontWeight:600 }}>{c.category}</span>
                      <span style={{ fontFamily:mono, fontSize:11, color:C.faint }}>{typeof c.pct==="number"?`${c.pct.toFixed(1)}%`:""}</span>
                    </div>
                    {targetGapLabel(c) && <div style={{ marginTop:3, fontFamily:mono, fontSize:10.5, color:c.working_model_gap_pct>1?C.green:c.working_model_gap_pct<-1?C.red:C.faint }}>{targetGapLabel(c)}</div>}
                    <div style={{ marginTop:4, display:"flex", gap:5, flexWrap:"wrap", alignItems:"center" }}>
                      <span style={{ fontFamily:mono, fontSize:10.5, color:cueColor(c.fundstrat_cue||"no_current_cue"), border:`1px solid ${cueColor(c.fundstrat_cue||"no_current_cue")}55`, borderRadius:99, padding:"0px 6px" }}>Fundstrat {String(c.fundstrat_cue||"no_current_cue").replaceAll("_"," ")}</span>
                      {c.fundstrat_source_date && <span style={{ fontFamily:mono, fontSize:10.5, color:C.faint }}>{c.fundstrat_source_date}</span>}
                    </div>
                    {c.fundstrat_reason && <div style={{ marginTop:3, fontSize:10.8, color:C.faint }}>{c.fundstrat_reason}{(c.fundstrat_tickers||[]).length?` (${(c.fundstrat_tickers||[]).slice(0,4).join(", ")})`:""}</div>}
                    <div style={{ marginTop:4, fontFamily:mono, fontSize:10.5, color:C.dim }}>{money(c.market_value)} · {(c.tickers||[]).slice(0,5).join(", ")}</div>
                  </div>
                ))}
              </div>
              {effectiveExposure && ((effectiveExposure.sleeves||[]).some(s=>s.lookthrough_market_value>0) || (effectiveExposure.overlap_rows||[]).length>0) && (
                <div style={{ marginTop:10, borderTop:`1px solid ${C.line}`, paddingTop:9 }}>
                  <div style={{ display:"flex", alignItems:"baseline", justifyContent:"space-between", gap:10, flexWrap:"wrap", marginBottom:7 }}>
                    <div style={{ fontSize:11.5, fontWeight:700, color:C.text }}>Effective exposure</div>
                    <div style={{ fontFamily:mono, fontSize:10.5, color:C.faint }}>{effectiveExposure.source||"ETF look-through estimate"}</div>
                  </div>
                  <div style={{ ...muted, fontSize:11, marginBottom:8 }}>{effectiveExposure.caveat||"Estimated ETF overlap; not additive to book weight."}</div>
                  <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit, minmax(170px, 1fr))", gap:8 }}>
                    {(effectiveExposure.sleeves||[]).filter(s=>s.lookthrough_market_value>0).map((s,i)=>(
                      <div key={`${s.category}${i}`} style={{ border:`1px solid ${C.line}`, borderRadius:8, padding:"7px 8px", background:C.panel2 }}>
                        <div style={{ display:"flex", justifyContent:"space-between", gap:8 }}>
                          <span style={{ fontSize:11.5, color:C.text, fontWeight:600 }}>{s.category}</span>
                          <span style={{ fontFamily:mono, fontSize:11, color:C.faint }}>{typeof s.effective_pct==="number"?`${s.effective_pct.toFixed(1)}%`:""}</span>
                        </div>
                        {targetGapLabel(s) && <div style={{ marginTop:3, fontFamily:mono, fontSize:10.5, color:s.working_model_gap_pct>1?C.green:s.working_model_gap_pct<-1?C.red:C.faint }}>{targetGapLabel(s)}</div>}
                        {(s.fundstrat_cue && s.fundstrat_cue!=="no_current_cue") && <div style={{ marginTop:3, fontFamily:mono, fontSize:10.5, color:cueColor(s.fundstrat_cue) }}>Fundstrat {String(s.fundstrat_cue).replaceAll("_"," ")}{s.fundstrat_source_date?` | ${s.fundstrat_source_date}`:""}</div>}
                        <div style={{ marginTop:4, fontFamily:mono, fontSize:10.5, color:C.dim }}>direct {typeof s.direct_pct==="number"?s.direct_pct.toFixed(1):"0.0"}% + ETF {typeof s.lookthrough_pct==="number"?s.lookthrough_pct.toFixed(1):"0.0"}%</div>
                      </div>
                    ))}
                  </div>
                  {(effectiveExposure.overlap_rows||[]).length>0 && (
                    <div style={{ marginTop:8 }}>
                      {(effectiveExposure.overlap_rows||[]).map((r,i)=>(
                        <div key={`${r.ticker}${i}`} style={{ display:"grid", gridTemplateColumns:"72px 1fr auto", gap:8, alignItems:"center", padding:"4px 0", borderTop:i?`1px solid ${C.line}`:"none" }}>
                          <span style={{ fontFamily:mono, fontSize:12, fontWeight:700, color:C.text }}>{r.ticker}</span>
                          <span style={{ fontSize:11.5, color:C.dim, whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>{(r.sources||[]).map(s=>s.etf).join(", ")} overlap</span>
                          <span style={{ fontFamily:mono, fontSize:11.5, color:C.faint }}>{money(r.effective_market_value)}{typeof r.effective_pct==="number"?` Â· ${r.effective_pct.toFixed(1)}%`:""}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
              <div style={{ marginTop:10, borderTop:`1px solid ${C.line}`, paddingTop:8 }}>
                <div style={{ fontFamily:mono, fontSize:10.5, color:C.faint, marginBottom:6 }}>{(portfolioView.rows||[]).length} direct account row{(portfolioView.rows||[]).length===1?"":"s"}</div>
                {(portfolioView.rows||[]).map((r,i)=>(
                  <div key={`${r.ticker}${r.account}${i}`} style={{ display:"grid", gridTemplateColumns:"72px 1fr auto", gap:8, alignItems:"center", padding:"4px 0", borderTop:i?`1px solid ${C.line}`:"none" }}>
                    <span style={{ fontFamily:mono, fontSize:12, fontWeight:700, color:C.text }}>{r.ticker}</span>
                    <span style={{ fontSize:11.5, color:C.dim, whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>{r.description?`${r.description} · `:""}{r.account}{r.owner&&r.owner!=="Multiple"?` · ${r.owner}`:""}{r.category?` · ${r.category}`:""}</span>
                    <span style={{ fontFamily:mono, fontSize:11.5, color:C.faint }}>{money(r.market_value)}{typeof r.pct==="number"?` · ${r.pct.toFixed(1)}%`:""}</span>
                  </div>
                ))}
              </div>
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
                                {p.cdNote && p.cdNote.indexOf("uw_opportunity")>=0 && <span title="direction turned on fresh UW options flow — timing / confirmation, not conviction" style={{ fontFamily:mono, fontSize:9.5, color:C.green, border:`1px solid ${C.green}55`, borderRadius:99, padding:"0px 5px" }}>UW</span>}
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

        </>)}

        {mode==="news" && (<>

        <Section id="fundstrat-news" title="Fundstrat News" icon="F" badge={(VM.fundstratNews&&VM.fundstratNews.status)==="has_data"?"loaded":"not checked"} badgeColor={(VM.fundstratNews&&VM.fundstratNews.status)==="has_data"?C.green:C.amber} summary={clipText((VM.fundstratNews||{}).line || "No Fundstrat news block in this feed build.", 120)} openMap={open} setOpen={setOpen} defaultOpen={false}>
          {(() => {
            const F=VM.fundstratNews||{}, M=F.monthly||{}, D=F.daily||{}, gaps=F.gaps||[];
            return (
              <div>
                <div style={{ ...card, marginBottom:8, borderColor:C.blue+"44", background:C.blue+"0a" }}>
                  <div style={{ fontSize:12.8, fontWeight:750, color:C.text }}>{F.line||"Fundstrat News is not checked."}</div>
                  {F.honesty_rule && <div style={{ marginTop:5, fontFamily:mono, fontSize:10.8, color:C.faint }}>{F.honesty_rule}</div>}
                </div>

                <Section id="fundstrat-monthly" title="Monthly Bible / Allocation" icon="M" badge={M.deck_date||"not checked"} badgeColor={M.deck_date?C.green:C.amber} summary={compactJoin([M.deck_date&&`deck ${M.deck_date}`, M.age_days!=null&&`${M.age_days}d old`, (M.allocation_plan||[]).length&&`${(M.allocation_plan||[]).length} allocation cues`]) || "Monthly bible not checked."} openMap={open} setOpen={setOpen} defaultOpen={false}>
                  <div style={{ ...card, marginBottom:8 }}>
                    <div style={{ fontFamily:mono, fontSize:10.5, color:C.faint, marginBottom:5 }}>Source: {M.source_file||"not captured"} | {M.freshness_label||"not checked"}</div>
                    <div style={{ fontSize:12, color:C.dim }}>{M.freshness_judgment||"No monthly judgment available."}</div>
                    {(M.allocation_plan||[]).length>0 && (
                      <div style={{ marginTop:8, display:"flex", flexWrap:"wrap", gap:6 }}>
                        {(M.allocation_plan||[]).map((x,i)=><span key={`${x}${i}`} style={{ fontFamily:mono, fontSize:10.8, color:C.text, border:`1px solid ${C.line}`, borderRadius:99, padding:"2px 8px", background:C.panel2 }}>{x}</span>)}
                      </div>
                    )}
                  </div>
                  <FundstratMonthlyRows title="Top 5 large cap" rows={M.top_large_cap||[]} empty="Top 5 large cap is not captured in this feed." />
                  <FundstratMonthlyRows title="Top 5 SMID" rows={M.top_smid||[]} empty="Top 5 SMID is not captured in the live monthly/prospect caches yet." />
                  <FundstratMonthlyRows title="Bottom 5 large cap" rows={M.bottom5||[]} empty="Bottom 5 large cap is not captured in this feed." />
                  <FundstratMonthlyRows title="Bottom 5 SMID" rows={M.bottom5_smid||[]} empty="Bottom 5 SMID is not captured in this feed." />
                </Section>

                <Section id="fundstrat-daily" title="Daily Additions / Deltas" icon="D" badge={D.count?`${D.count}`:"0"} badgeColor={D.count?C.blue:C.faint} summary={compactJoin([D.latest_date&&`latest ${D.latest_date}`, D.count!=null&&`${D.count} stored call${D.count===1?"":"s"}`, D.freshness_judgment&&clipText(D.freshness_judgment,70)]) || "No full-body daily calls stored."} openMap={open} setOpen={setOpen} defaultOpen={false}>
                  <div style={{ ...card, marginBottom:8, fontSize:12, color:C.dim }}>
                    {D.freshness_judgment||"No full-body Fundstrat daily rows are currently stored."}
                    <div style={{ marginTop:5, fontFamily:mono, fontSize:10.5, color:C.faint }}>full-body {D.full_body_entries||0} | snippet-only {D.snippet_only_entries||0} | stored daily {D.stored_daily_calls||0}</div>
                  </div>
                  {!(D.rows||[]).length && <div style={{ ...card, fontSize:12, color:C.faint }}>No daily Fundstrat additions/deltas in this feed build.</div>}
                  {(D.rows||[]).slice(0,12).map((r,i)=>(
                    <div key={`${r.ticker}${r.date}${i}`} style={{ ...card, marginBottom:7 }}>
                      <div style={{ display:"flex", alignItems:"baseline", gap:8, flexWrap:"wrap" }}>
                        <span style={{ fontFamily:mono, fontWeight:800, color:C.text }}>{r.ticker}</span>
                        <span style={{ fontFamily:mono, fontSize:10.5, color:C.blue, border:`1px solid ${C.blue}55`, borderRadius:99, padding:"1px 8px" }}>{r.author||"Fundstrat"}</span>
                        <span style={{ fontFamily:mono, fontSize:10.5, color:C.amber }}>{r.action_implication||"context"}</span>
                        <span style={{ fontFamily:mono, fontSize:10.5, color:C.faint }}>{r.date}</span>
                      </div>
                      {r.quote && <div style={{ marginTop:6, fontSize:12.2, color:C.text }}>{r.quote}</div>}
                      <div style={{ marginTop:5, fontSize:11.5, color:C.dim }}>{r.source_weight_note||r.confidence_policy||"Use as context until action implication is clear."}</div>
                    </div>
                  ))}
                </Section>

                <Section id="fundstrat-news-gaps" title="Fundstrat Data Gaps" icon="!" badge={gaps.length?`${gaps.length}`:"0"} badgeColor={gaps.length?C.amber:C.green} summary={gaps.length ? clipText(gaps[0].line,100) : "No captured Fundstrat News gaps."} openMap={open} setOpen={setOpen} defaultOpen={false}>
                  {!gaps.length && <div style={{ ...card, fontSize:12, color:C.green }}>No gaps surfaced by the Fundstrat News builder.</div>}
                  {gaps.map((g,i)=>(
                    <div key={`${g.key}${i}`} style={{ ...card, marginBottom:7, borderColor:(g.severity==="warn"?C.amber:C.blue)+"44" }}>
                      <div style={{ fontFamily:mono, fontSize:10.8, color:g.severity==="warn"?C.amber:C.blue, marginBottom:4 }}>{g.key||"gap"}</div>
                      <div style={{ fontSize:12.5, color:C.text }}>{g.line}</div>
                      {g.next_step && <div style={{ marginTop:5, fontSize:11.5, color:C.dim }}>Next: {g.next_step}</div>}
                    </div>
                  ))}
                </Section>
              </div>
            );
          })()}
        </Section>

        </>)}

        {mode==="system" && (<>

        <Section id="system-cloud-routines" title="Cloud Routine Health" icon="!" badge={(() => { const c=((VM.sourceAudits||{}).cloud_routines)||{}; return (c.failed_latest_count||0)?`${c.failed_latest_count} fail`:(c.expected_count?`${c.scheduled_success_count||0}/${c.expected_count}`:"audit"); })()} badgeColor={(() => { const c=((VM.sourceAudits||{}).cloud_routines)||{}; return (c.failed_latest_count||0)?C.red:(c.expected_count && (c.scheduled_success_count||0) >= c.expected_count ? C.green : C.amber); })()} summary={(() => { const c=((VM.sourceAudits||{}).cloud_routines)||{}; return c.line || "Cloud routine proof is not loaded."; })()} openMap={open} setOpen={setOpen} defaultOpen={false}>
          {(() => {
            const cloud=((VM.sourceAudits||{}).cloud_routines)||{};
            const routineRows=cloud.rows||[];
            const missing=cloud.missing_scheduled_success||[];
            const missingIds=new Set(missing.map(r=>r.routine_id).filter(Boolean));
            const failedRows=routineRows.filter(r=>String(r.last_status||"").toLowerCase()==="failed");
            const statusColor=(cloud.failed_latest_count||0)?C.red:(missing.length?C.amber:C.green);
            return (
              <div>
                <div style={{ ...card, marginBottom:8, borderColor:statusColor+"66", background:statusColor+"0d" }}>
                  <div style={{ fontSize:13, fontWeight:750, color:C.text }}>
                    {(cloud.failed_latest_count||0) ? `Cloud routine failed: ${failedRows.map(r=>r.routine_name||r.routine_id).join(", ") || `${cloud.failed_latest_count} routine(s)`}` : (cloud.line || "Cloud routines checked.")}
                  </div>
                  <div style={{ marginTop:5, fontSize:11.8, color:C.dim }}>{cloud.line || "No cloud routine audit line in this feed."}</div>
                  {failedRows.length>0 && <div style={{ marginTop:5, fontSize:11.8, color:C.amber }}>Dashboard impact: {routineImpact(failedRows[0])}</div>}
                  <div style={{ marginTop:6, fontFamily:mono, fontSize:10.5, color:C.faint }}>Check: python src/cloud_ops_status.py --format text</div>
                </div>
                {failedRows.map((r,i)=>(
                  <div key={`${r.routine_id||"failed"}${i}`} style={{ ...toneCard("red"), marginBottom:7 }}>
                    <div style={{ display:"flex", alignItems:"baseline", justifyContent:"space-between", gap:8, flexWrap:"wrap" }}>
                      <div style={{ fontSize:12.8, fontWeight:800, color:C.text }}>{r.routine_name||r.routine_id}</div>
                      <span style={{ fontFamily:mono, fontSize:10.5, color:C.red, border:`1px solid ${C.red}66`, borderRadius:99, padding:"1px 8px" }}>{r.last_status||"failed"}</span>
                    </div>
                    <div style={{ marginTop:4, fontSize:11.8, color:C.dim }}>Schedule: {r.schedule||"n/a"} | last source: {r.last_run_source||"n/a"} | last recorded: {r.last_recorded_at||"n/a"}</div>
                    {r.last_summary && <div style={{ marginTop:4, fontSize:11.8, color:C.text }}>Last summary: {r.last_summary}</div>}
                    <div style={{ marginTop:4, fontSize:11.8, color:C.amber }}>Impact: {routineImpact(r)}</div>
                    <div style={{ marginTop:4, fontSize:11.8, color:C.dim }}>How to treat the dashboard: keep that lane as not fully proven until the routine succeeds; do not promote UW/asymmetric-flow ideas from this proof alone.</div>
                  </div>
                ))}
                {missing.length>0 && (
                  <div style={{ ...toneCard(missing.some(r=>String(r.last_status||"").toLowerCase()==="failed")?"red":"amber"), marginBottom:8 }}>
                    <div style={{ fontSize:12.6, fontWeight:750, color:C.text }}>Scheduled proof still missing</div>
                    {missing.slice(0,8).map((r,i)=>(
                      <div key={`${r.routine_id||"missing"}${i}`} style={{ marginTop:5, fontSize:11.8, color:String(r.last_status||"").toLowerCase()==="failed"?C.red:C.dim }}>
                        {r.routine_name||r.routine_id} | {r.schedule||"schedule n/a"} | last status {r.last_status||"unknown"}
                      </div>
                    ))}
                  </div>
                )}
                {routineRows.length>0 && (
                  <Section id="system-cloud-routine-table" title="Routine Receipt Table" icon=">" badge={`${routineRows.length}`} badgeColor={C.faint} summary="All cloud routines with latest receipt status." openMap={open} setOpen={setOpen} defaultOpen={false}>
                    {routineRows.map((r,i)=>{
                      const status=String(r.last_status||"unknown").toLowerCase();
                      const tone=status==="failed"?"red":missingIds.has(r.routine_id)?"amber":status==="success"?"green":"gray";
                      const c=toneColor(tone);
                      return (
                        <div key={`${r.routine_id||i}`} style={{ ...toneCard(tone), marginBottom:6 }}>
                          <div style={{ display:"flex", alignItems:"baseline", gap:8, flexWrap:"wrap" }}>
                            <span style={{ fontSize:12.4, fontWeight:750, color:C.text }}>{r.routine_name||r.routine_id}</span>
                            <span style={{ fontFamily:mono, fontSize:10.5, color:c, border:`1px solid ${c}55`, borderRadius:99, padding:"1px 8px" }}>{r.last_status||"unknown"}</span>
                            <span style={{ fontFamily:mono, fontSize:10.5, color:C.faint }}>{r.schedule||""}</span>
                          </div>
                          <div style={{ marginTop:4, fontFamily:mono, fontSize:10.4, color:C.faint }}>last scheduled success: {r.last_scheduled_success_at||"not proven"} | last recorded: {r.last_recorded_at||"n/a"}</div>
                          {r.last_summary && <div style={{ marginTop:4, fontSize:11.5, color:C.dim }}>{r.last_summary}</div>}
                        </div>
                      );
                    })}
                  </Section>
                )}
              </div>
            );
          })()}
        </Section>

        <Section id="system-source-proof" title="Source Proof And Writebacks" icon="?" badge="audit" badgeColor={C.blue} summary="Connector evidence, UW routing/proof, Fundstrat intake, and Notion writeback status." openMap={open} setOpen={setOpen} defaultOpen={false}>
          {(() => {
            const A=VM.sourceAudits||{};
            const rows=[
              ["Connector evidence", (A.connector_evidence||{}).line],
              ["UW routing", (A.uw_routing||{}).line],
              ["UW action runbook", (A.uw_action_runbook||{}).line],
              ["UW endpoint proof", (A.uw_endpoint_proof||{}).line],
              ["Fundstrat intake", (A.fundstrat||{}).line],
              ["Notion/writeback", (A.notion_writeback||{}).line],
            ].filter(r=>r[1]);
            return rows.length ? rows.map(([label,line])=>(
              <div key={label} style={{ ...card, marginBottom:7 }}>
                <div style={{ fontFamily:mono, fontSize:10.5, color:C.faint, textTransform:"uppercase", marginBottom:3 }}>{label}</div>
                <div style={{ fontSize:12.4, color:C.text }}>{line}</div>
              </div>
            )) : <div style={{ ...card, fontSize:12, color:C.faint }}>No source-audit rows in this feed build.</div>;
          })()}
        </Section>

        <Section id="system-upgrades" title="System Upgrades And Checks" icon="+" badge={`${COMMAND_CHECKS.length+1}`} badgeColor={C.amber} summary="System-only checks, upgrade queue, verification, cloud proof, and alert-gate dry runs." openMap={open} setOpen={setOpen} defaultOpen={false}>
          {[...COMMAND_CHECKS, { name:"Build queue", desc:"Repo-local backlog for deferred system upgrades and implementation notes.", command:"docs/codex_build_queue.md" }].map((row,i)=><CommandRow key={`${row.name}${i}`} row={row} />)}
        </Section>

        </>)}

        {mode==="commands" && (<>

        <Section id="current-commands" title="Current commands" icon="!" badge={`${COMMAND_ACTIONS.length} actions`} badgeColor={C.blue} summary="Operator actions and checks for the current Investing OS build." openMap={open} setOpen={setOpen} defaultOpen={false}>
          <div style={{ marginBottom:10, ...card, borderColor:C.blue+"44", background:C.blue+"0a" }}>
            <div style={{ fontSize:12.5, fontWeight:700, color:C.text }}>Use this tab as the practical runbook.</div>
            <div style={{ marginTop:5, fontSize:12, color:C.dim }}>The cockpit is still review-only: commands refresh evidence, inspect gates, or update memory after you explicitly decide. They do not place trades.</div>
          </div>
          <Section id="operator-actions" title="Operating actions" icon=">" badge={`${COMMAND_ACTIONS.length}`} badgeColor={C.green} summary="Start, refresh, review packet, reallocation, and open actions." openMap={open} setOpen={setOpen} defaultOpen={false}>
            {COMMAND_ACTIONS.map((row,i)=><CommandRow key={`${row.name}${i}`} row={row} />)}
          </Section>
          <Section id="system-checks" title="System checks" icon="?" badge={`${COMMAND_CHECKS.length}`} badgeColor={C.amber} summary="Status, alerts, UW, SnapTrade staging, verification, and cloud proof." openMap={open} setOpen={setOpen} defaultOpen={false}>
            {COMMAND_CHECKS.map((row,i)=><CommandRow key={`${row.name}${i}`} row={row} />)}
          </Section>
          <Section id="source-links" title="Source links" icon="@" badge={`${COMMAND_LINKS.length}`} badgeColor={C.dim} summary="Repo, Notion architecture, Monday plan, and published mirror." openMap={open} setOpen={setOpen} defaultOpen={false}>
            {COMMAND_LINKS.map((row,i)=><CommandLink key={`${row.name}${i}`} row={row} />)}
          </Section>
          <div style={{ marginTop:8, fontFamily:mono, fontSize:10.5, color:C.faint }}>
            Social Watch remains queued/dark until the separate compliant Reddit/social work is merged; do not treat missing social data as no signal.
          </div>
        </Section>

        </>)}

        {/* ⚡ ACTION VIEW (cont.) ────────────────────────────────────── */}
        {["news","ideas","ops"].includes(mode) && (<>

        {/* MARKET READ — rotation + macro (from FEED) */}
        {mode==="news" && (<Section id="market" title="Market read — rotation + macro" icon="🌐" summary={compactJoin([VM.macro&&VM.macro.impl&&VM.macro.impl[0]&&clipText(VM.macro.impl[0],96), VM.rotation&&VM.rotation[0]&&`lead: ${VM.rotation[0].s} ${VM.rotation[0].w}`]) || "No market read loaded."} openMap={open} setOpen={setOpen} defaultOpen={false}>
          <div style={{ ...card, marginBottom:8 }}>
            <div style={{ fontSize:11, color:C.faint, fontFamily:mono, marginBottom:8 }}>SLEEVE LEADERSHIP (relative strength vs market)</div>
            {VM.rotation.map((r,i)=>(
              <div key={i} style={{ display:"grid", gridTemplateColumns:"minmax(110px, 168px) auto minmax(0, 1fr)", gap:10, alignItems:"center", padding:"5px 0", borderTop: i?`1px solid ${C.line}`:"none" }}>
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
        </Section>)}

        {/* RESEARCH — live Research Queue (R = VM.research when present, else curated) */}
        {mode==="ideas" && (<Section id="research" title="Research" icon="🔬" badge={(R.pending||[]).length+(R.done||[]).length} badgeColor={C.blue} summary={compactJoin([`${(R.pending||[]).length} pending`, `${(R.done||[]).length} completed`, (R.pending||[])[0]&&clipText((R.pending||[])[0].title||(R.pending||[])[0].r,72)])} openMap={open} setOpen={setOpen} defaultOpen={false}>
          <Section id="rpending" title="Pending — you prioritize" icon="⏳" badge={(R.pending||[]).length} badgeColor={C.blue} summary={(R.pending||[]).length ? clipText((R.pending||[])[0].title||(R.pending||[])[0].r,88) : "Nothing pending."} openMap={open} setOpen={setOpen} defaultOpen={false}>
            {(R.pending||[]).length===0 && <div style={{ ...card, fontSize:12, color:C.faint }}>Nothing pending.</div>}
            {(R.pending||[]).map((x,i)=>{ const pr=x.priority||x.pr||""; return (
              <div key={i} style={{ ...card, marginBottom:7, display:"flex", gap:10, alignItems:"flex-start" }}>
                <span style={{ fontFamily:mono, fontSize:10, color: pr==="high"?C.amber:C.faint, marginTop:2, minWidth:34 }}>{pr}</span>
                <span style={{ fontSize:12.5, color:C.dim }}>{x.title||x.r}{x.note?` — ${x.note}`:""}</span>
              </div>
            ); })}
          </Section>
          <Section id="rdone" title="Completed — significant findings" icon="✅" badge={(R.done||[]).length} badgeColor={C.green} summary={(R.done||[]).length ? clipText((R.done||[])[0].title||(R.done||[])[0].r,88) : "No completed findings."} openMap={open} setOpen={setOpen} defaultOpen={false}>
            {(R.done||[]).map((x,i)=>(
              <div key={i} style={{ ...card, marginBottom:7, borderColor:C.green+"33" }}>
                <div style={{ fontSize:13, color:C.text }}>{x.title||x.r}</div>
                <div style={{ marginTop:5, ...muted }}>{x.finding||x.f}</div>
              </div>
            ))}
          </Section>
        </Section>)}

        {/* CATALYSTS - live feed rows from Catalyst Calendar / catalyst intake */}
        {mode==="news" && (<Section id="cats" title="Upcoming catalysts — near-term" icon="📅" badge={CATS.length} badgeColor={CATS.length?C.blue:C.faint} summary={CATS.length ? compactJoin([`${CATS.length} catalysts`, `${CATS[0].d} ${clipText(CATS[0].e,62)}`]) : "No catalysts supplied in this feed build."} openMap={open} setOpen={setOpen} defaultOpen={false}>
          {CATS.length===0 && <div style={{ ...card, fontSize:12, color:C.faint }}>No catalysts supplied in this feed build.</div>}
          {CATS.map((x,i)=>(
            <div key={i} style={{ ...card, marginBottom:7, display:"flex", gap:12, alignItems:"baseline" }}>
              <span style={{ fontFamily:mono, fontSize:12, color:C.accent, minWidth:58 }}>{x.d}</span>
              <div><div style={{ fontSize:13, color:C.text }}>{x.e}</div><div style={muted}>{x.note}</div></div>
            </div>
          ))}
        </Section>)}

        {/* QUESTIONS (cockpit-curated; swap CURATED.questions → VM.questions when the feed emits them) */}
        {mode==="ops" && (<Section id="questions" title="Questions for you" icon="❓" badge={`${CURATED.questions.length}`} badgeColor={C.dim} summary={CURATED.questions.length ? clipText(CURATED.questions[0].q,88) : "No open questions."} openMap={open} setOpen={setOpen} defaultOpen={false}>
          {CURATED.questions.length===0 && <div style={{ ...card, fontSize:12, color:C.faint }}>No open questions.</div>}
          {CURATED.questions.map((x,i)=>(
            <div key={i} style={{ ...card, marginBottom:7 }}>
              <div style={{ fontSize:12.5, color:C.dim }}>{x.q}</div>
              <div style={{ marginTop:5, fontFamily:mono, fontSize:10.5, color:C.faint }}>{x.tag} · {x.d}</div>
            </div>
          ))}
        </Section>)}

        {mode==="ops" && (<Section id="social-watch" title="Social Watch" icon="*" badge={(VM.socialWatch&&VM.socialWatch.count)?`${VM.socialWatch.count}`:"0"} badgeColor={(VM.socialWatch&&VM.socialWatch.status)==="has_data"?C.amber:C.faint} summary={(() => { const S=VM.socialWatch||{}; return compactJoin([String(S.status||"not_checked").replaceAll("_"," "), S.line||"Reddit/social feed is not implemented yet.", "watch-only"]); })()} openMap={open} setOpen={setOpen} defaultOpen={false}>
          <div style={{ fontSize:11, color:C.faint, fontFamily:mono, marginBottom:8 }}>REDDIT / SOCIAL EARLY-SIGNAL WATCH. Watch-only until independently confirmed by UW, price/news, Fundstrat, catalyst, or source-call evidence.</div>
          {(() => {
            const S=VM.socialWatch||{}, rows=S.rows||[];
            if(!rows.length) return (
              <div style={{ ...card, fontSize:12, color:S.status==="not_checked"?C.amber:C.faint }}>
                {S.line||"No social anomalies in this feed build."}
                {S.honesty_rule && <div style={{ marginTop:6, fontFamily:mono, fontSize:10.5, color:C.faint }}>{S.honesty_rule}</div>}
                {S.command && <div style={{ marginTop:6, fontFamily:mono, fontSize:10.5, color:C.faint }}>Command: {S.command}</div>}
              </div>
            );
            return (
              <div>
                <div style={{ ...card, marginBottom:8, borderColor:C.amber+"44", background:C.amber+"0a" }}>
                  <div style={{ fontSize:12.5, color:C.text }}>{S.line}</div>
                  {S.honesty_rule && <div style={{ marginTop:5, fontFamily:mono, fontSize:10.5, color:C.faint }}>{S.honesty_rule}</div>}
                  {S.promotion_rule && <div style={{ marginTop:5, fontFamily:mono, fontSize:10.5, color:C.faint }}>{S.promotion_rule}</div>}
                </div>
                {rows.slice(0,6).map((r,i)=>(
                  <div key={`${r.ticker||r.entity||"social"}${i}`} style={{ ...card, marginBottom:7, borderColor:C.amber+"33" }}>
                    <div style={{ display:"flex", alignItems:"baseline", gap:8, flexWrap:"wrap" }}>
                      <span style={{ fontFamily:mono, fontWeight:700, fontSize:13.5, color:C.text }}>{r.ticker||r.entity||"SOCIAL"}</span>
                      <span style={{ fontFamily:mono, fontSize:11, color:C.amber, border:`1px solid ${C.amber}55`, borderRadius:99, padding:"1px 8px" }}>score {r.score}</span>
                      <span style={{ fontFamily:mono, fontSize:11, color:C.faint }}>{r.escalation||"Quiet Watch"}</span>
                    </div>
                    {r.summary && <div style={{ marginTop:6, fontSize:12.5, color:C.text }}>{r.summary}</div>}
                    {(r.subreddits||[]).length>0 && <div style={{ marginTop:4, fontFamily:mono, fontSize:10.5, color:C.faint }}>subreddits: {(r.subreddits||[]).join(", ")}</div>}
                    {(r.evidence||[]).length>0 && <div style={{ marginTop:4, fontFamily:mono, fontSize:10.5, color:C.faint }}>evidence: {(r.evidence||[]).join(" / ")}</div>}
                    {(r.independent_confirmation||[]).length>0 && <div style={{ marginTop:4, fontFamily:mono, fontSize:10.5, color:C.faint }}>independent confirmation: {(r.independent_confirmation||[]).join(" / ")}</div>}
                    <div style={{ marginTop:5, fontSize:11.5, color:C.dim }}>Risk: {r.risk}</div>
                  </div>
                ))}
                {S.command && <div style={{ marginTop:6, fontFamily:mono, fontSize:10.5, color:C.faint }}>Command: {S.command}</div>}
              </div>
            );
          })()}
        </Section>)}

        <div style={{ marginTop:18, fontSize:11, color:C.faint, textAlign:"center", fontFamily:mono }}>
          {VM.stamp} · tap anything to expand · every section collapses independently
        </div>

        </>)}

      </div>
    </div>
  );
}
