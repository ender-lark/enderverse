import React, { useState } from "react";

// ───────────────────────────────────────────────────────────────
// CONVICTION COCKPIT — v4 (Holdings rebuilt: sourced reads + net-read + conviction-direction)
// Rotation + macro live 2026-05-29. Per-name reads sourced from FS 5/28 bible + theses (5/28 daily notes folded).
// cv=conviction(quality) · cd=conviction-direction(event-driven, not price) · nr=net-read(the plain "what to do").
// Per-name price arrow REMOVED (redundant with sleeve rotation). Positions still 5/27 book (labeled). Actions/Fresh Signals = next chunk.
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
  "—":       { c:C.gray,  q:"not yet assessed — seeds in the next pass" },
};
const POSTURE = { Strong:"a meaningful", Promising:"a moderate", Mixed:"a modest", Weak:"a small", "—":"an unassessed" };

// ── Live sleeve rotation (computed 2026-05-29, relative strength vs SPY) ──
const ROTATION = [
  { s:"AI / semis (SMH)",        w:"LEADING",      c:C.green, n:"+37 vs mkt (3M)", note:"your engine — leads everything, still accelerating (+47%/3M)" },
  { s:"Software (IGV)",          w:"LEADING",      c:C.green, n:"+14 vs mkt",      note:"caught up to semis last month (+20%/1M) — the second leg to watch" },
  { s:"Quality core (GRNY)",     w:"IN LINE",      c:C.blue,  n:"≈ market",        note:"tracking the index, at new highs" },
  { s:"Electrification (VOLT)",  w:"SOFTENING",    c:C.amber, n:"-6 vs mkt (1M)",  note:"kept pace over 3M, slipped behind in the last month" },
  { s:"Crypto (IBIT)",           w:"TURNING DOWN", c:C.red,   n:"-9 vs mkt (1M)",  note:"led the bounce, now rolling over (-2.6%/1M while mkt +6%)" },
  { s:"Financials (XLF)",        w:"LAGGING",      c:C.red,   n:"-10 vs mkt",      note:"the persistent laggard — flat/down, actually down YTD" },
  { s:"Critical minerals (REMX)",w:"LAGGING",      c:C.amber, n:"-10 vs mkt",      note:"flat/consolidating after a huge year — closest to a base; watch for the turn" },
  { s:"Nuclear (URA)",           w:"LAGGING",      c:C.red,   n:"-17 vs mkt",      note:"down on every window, no turn" },
  { s:"Gold hedge (GDX)",        w:"HEDGE",        c:C.gray,  n:"-33 vs mkt",      note:"gave back its run as risk-on resumed — normal hedge behavior; stabilizing" },
];

const MACRO = {
  line:"10Y 4.45%  ·  2s10s +46bp (normal slope)  ·  30Y 4.98%  ·  dollar firm (+2%/3M, flat 1M)",
  tape:"Risk-on — market at new highs, semis-led recovery off the early-April low.",
  impl:[
    ["Minerals (MP/LEU/UUUU)", "firm dollar = mild ongoing headwind, but flat lately — not worsening"],
    ["AI / long-duration growth", "10Y 4.45% is below the 4.75% alert — manageable; AI leads regardless"],
    ["Financials", "curve is positively sloped (mildly supportive) yet XLF lags — the weakness isn't the curve"],
    ["Crypto / nuclear", "elevated real yields = mild headwind; consistent with their lag"],
  ],
  note:"vol (VIX) not pulled this run — can add next pass",
};

// ── HOLDINGS (5/27 book · reads sourced FS 5/28 bible + rotation 5/29) ──
// Per-name: cv=conviction(quality) · cd=conviction-direction (up/flat/down, EVENT-driven, not price) ·
// cdNote=what moved it (the trail) · nr=net-read (the plain "what to do") · dr=why (source-tagged) · be=what could break it.
const HOLD = [
  { cat:"AI / Semiconductors — the engine (~36%)", rot:{w:"LEADING",c:C.green}, pos:[
    { t:"SMH", n:"Semiconductor ETF", pct:9.90, st:"Owned", cv:"Strong", ty:"Core", cd:"up", own:"p,s",
      nr:"Core hold — your AI engine, leads everything. Trims are your de-concentration call, not a weakness signal.",
      cdNote:"FS reaffirmed Tech as double-OW in the 5/28 deck; leading the tape.",
      dr:[["Broad AI-chip complex (Lee)","owns the whole semi complex in one ticker; Fundstrat Tech is double-overweight"]],
      be:"AI capex slows, or China export curbs tighten." },
    { t:"MAGS", n:"Magnificent-7 ETF", pct:9.09, st:"Owned", cv:"Strong", ty:"Core", cd:"up", own:"p,s",
      nr:"Core hold — FS 'What to Own' core long. Trim only to cut AI overlap.",
      cdNote:"In the 5/28 'What to Own' list; Tech +52% Y/Y.",
      dr:[["Mega-cap quality (Lee)","the Mag-7 in one ticker; named in FS 'What to Own'"]],
      be:"Concentration — a few names drive it." },
    { t:"NVDA", n:"Nvidia", pct:6.73, st:"Owned", cv:"Strong", ty:"Core", cd:"up", own:"p,s",
      nr:"Core hold — FS core AI long, ~19x fwd (cheap for the growth).",
      cdNote:"Leading; the 5/28 deck pegs it ~19x forward — reasonable vs the growth.",
      dr:[["AI compute leader (Lee)","the dominant supplier of AI chips"]],
      be:"Hyperscaler capex gap or margin compression (your exit-watch signals)." },
    { t:"MU", n:"Micron", pct:3.20, st:"Owned", cv:"Strong", ty:"Tactical", cd:"up", own:"p,s",
      nr:"Hold — parabolic; do NOT trim on the move, only on a named break (your rule).",
      cdNote:"Parabolic; FS flags no sell (it's even held inside RPG).",
      dr:[["Memory/HBM upcycle (Lee)","high-bandwidth memory is sold out into the AI buildout"]],
      be:"Memory is cyclical; the cycle eventually turns." },
    { t:"IVES", n:"Dan Ives AI ETF", pct:3.73, st:"Owned", cv:"Promising", ty:"Tactical", cd:"flat", own:"p,s",
      nr:"Hold — your AI thematic basket; rides the complex.",
      cdNote:"No recent change.",
      dr:[["AI thematic basket (your pick)","a thematic AI ETF tied to a known analyst"]],
      be:"Thematic crowding; AI multiple compression." },
    { t:"AVGO", n:"Broadcom", pct:1.59, st:"Owned", cv:"Promising", ty:"Core", cd:"flat", own:"p,s",
      nr:"Core hold — AI networking + custom silicon; not currently an FS-named pick.",
      cdNote:"No recent change.",
      dr:[["AI networking + custom silicon","picks-and-shovels for hyperscaler AI"]],
      be:"Hyperscaler capex cyclicality." },
    { t:"ANET", n:"Arista Networks", pct:0.29, st:"Owned", cv:"Promising", ty:"Tactical", cd:"up", own:"p,s",
      nr:"Tiny — now a current FS Top-5 large-cap (AI networking). Among FS's most-wanted.",
      cdNote:"Named an FS Top-5 large-cap in the 5/28 deck → conviction up.",
      dr:[["AI networking (Lee Top-5)","named FS Top-5 large-cap, 5/28"]],
      be:"Hyperscaler capex cyclicality; tiny position." },
    { t:"NBIS", n:"Nebius (neocloud)", pct:1.01, st:"Owned", cv:"Mixed", ty:"Speculative", cd:"flat", own:"p",
      nr:"Hold small — rents out GPU capacity; higher-risk infra.",
      cdNote:"No recent change.",
      dr:[["AI compute rental","rents out GPU capacity"]],
      be:"Capital-intensive; execution risk." },
    { t:"+ more", n:"SOXX · ASML · FTXL · LITE · CLS · POET", pct:0, st:"Owned", cv:"Promising", ty:"Tactical", cd:"flat", own:"p,s",
      nr:"Hold — semis ETF (an FS high-composite shadow name) + EUV monopoly + optical; assess individually next pass.",
      cdNote:"No recent change.",
      dr:[["Additional AI / semi / optical names","SOXX broad semis; ASML EUV monopoly; the rest optical/components"]],
      be:"AI-complex cyclicality." },
  ]},
  { cat:"Quality / Fundstrat ETFs", rot:{w:"IN LINE",c:C.blue}, pos:[
    { t:"GRNY", n:"Fundstrat Granny Shots (large-cap)", pct:9.16, st:"Owned", cv:"Strong", ty:"Core", cd:"flat", own:"p,s",
      nr:"Core hold — Lee's flagship quality-momentum basket. Near highs.",
      cdNote:"No recent change; tracking the index at new highs.",
      dr:[["Lee quality-momentum basket","rules-based basket of his favored large-caps — this IS Lee's strategy, productized"]],
      be:"Broad market drawdown." },
    { t:"GRNJ", n:"Fundstrat Granny Shots (small/mid-cap)", pct:7.29, st:"Owned", cv:"Promising", ty:"Core", cd:"flat", own:"p,s",
      nr:"Core hold — same Granny Shots strategy, small/mid-cap; pairs with GRNY.",
      cdNote:"No recent change.",
      dr:[["Granny Shots, SMID (Lee)","Lee's framework on small/mid-caps — ~62 holdings, industrials-heavy"],["Pairs with GRNY","your Fundstrat quality core across the cap spectrum"]],
      be:"Small/mid-caps swing harder than large-caps in a drawdown." },
  ]},
  { cat:"Software", rot:{w:"LEADING",c:C.green}, pos:[
    { t:"IGV", n:"Software ETF", pct:4.77, st:"Owned", cv:"Strong", ty:"Core", cd:"up", own:"p,s",
      nr:"Own it — FS calls software a 'bottom in' (5/28) and it's already leading. The second AI leg.",
      cdNote:"5/28 deck: software 'bottom in' + in 'What to Own'; rotation has it leading → conviction up.",
      dr:[["Broad software (Lee)","one ticker for the software complex; FS 5/28 'bottom in', in 'What to Own'"]],
      be:"Rate sensitivity; SaaS multiple compression." },
    { t:"MSFT", n:"Microsoft", pct:1.32, st:"Owned", cv:"—", ty:"Core", cd:"flat", own:"p,s",
      nr:"Core hold + AI — but no documented thesis from you. Worth a line.",
      cdNote:"Unassessed — give me your thesis and I'll grade it.",
      dr:[["AI + cloud compounder","Azure + Copilot — but this isn't in your documented theses"]],
      be:"AI monetization slower than priced." },
    { t:"+ more", n:"ORCL · PLTR", pct:0, st:"Owned", cv:"Promising", ty:"Tactical", cd:"flat", own:"p,s",
      nr:"Hold small — OCI AI-capacity + federal-AI. Valuation/execution risk.",
      cdNote:"No recent change.",
      dr:[["AI-cloud + federal-AI","ORCL OCI ramp; PLTR government contracts"]],
      be:"Valuation; execution." },
  ]},
  { cat:"Crypto / Digital-asset treasuries", flag:"add only on a strong signal", rot:{w:"TURNING DOWN",c:C.red}, pos:[
    { t:"BMNR", n:"ETH treasury (+ call stack)", pct:3.49, st:"Owned", cv:"Mixed", ty:"Speculative", cd:"flat", lock:true, own:"p,s",
      nr:"Hold light by choice — watch for your trigger, don't chase. FS itself is split.",
      cdNote:"Lee 5/28 'crypto bottom in' (+) vs Farrell 5/28 'struggling, favor flexibility' (−) → net flat. Your hold-light stance lines up with Farrell.",
      dr:[["ETH treasury flywheel (your pick)","raises capital to buy ETH; a premium to holdings can fund more buying"],["FS is split","Lee structurally constructive; Farrell (crypto specialist, 5/28) cautious near-term"]],
      be:"ETH drop; the Tom-Lee operator-conflict + dilution; the premium can collapse." },
    { t:"+ more", n:"IBIT · ETHA · HYPE · MSTR · COIN", pct:0, st:"Owned", cv:"Mixed", ty:"Speculative", cd:"flat", lock:true, own:"p,s",
      nr:"Hold light — same split read; HYPE's supply overhang is fading (Farrell). Don't chase.",
      cdNote:"Same Lee-vs-Farrell split; HYPE overhang fading per Farrell 5/28.",
      dr:[["BTC/ETH + smaller crypto","spot ETFs + speculative tokens"]],
      be:"Crypto drawdown." },
  ]},
  { cat:"Nuclear / Uranium", flag:"add only on a strong signal", rot:{w:"LAGGING",c:C.red}, pos:[
    { t:"LEU", n:"Centrus (+ $300 call)", pct:4.89, st:"Owned", cv:"Promising", ty:"Core", cd:"flat", lock:true, own:"p,s",
      nr:"Hold light — Meridian's enrichment-monopoly thesis is intact but lagging. Add only on a strong catalyst.",
      cdNote:"No FS change; Meridian thesis intact; sleeve lagging with no turn yet.",
      dr:[["HALEU/DOE enrichment monopoly (Meridian)","the only US enricher of advanced-reactor fuel — the 'Valve' thesis"]],
      be:"Funding/timing; enrichment competition; strong-dollar headwind." },
    { t:"UUUU", n:"Energy Fuels", pct:2.18, st:"Owned", cv:"Mixed", ty:"Tactical", cd:"down", lock:true, own:"p,s",
      nr:"Hold light, no add — Meridian likes it, but FS just put it Bottom-5 (5/28). Real source split; the lag isn't catch-up here.",
      cdNote:"FS moved it to Bottom-5 in the 5/28 deck → conviction down; Meridian thesis still on. Catch-up logic does NOT apply — FS isn't endorsing it.",
      dr:[["Uranium + rare-earth dual (Meridian)","held on Meridian's critical-minerals thesis"],["FS Bottom-5 (5/28)","Fundstrat flags it as a tactical avoid this month"]],
      be:"Commodity cycle; the FS-vs-Meridian split unresolved." },
    { t:"+ more", n:"CCJ · BWXT", pct:0, st:"Owned", cv:"Promising", ty:"Tactical", cd:"flat", lock:true, own:"p,s",
      nr:"Hold light — uranium major + naval/SMR components. Add only on a strong signal.",
      cdNote:"No recent change.",
      dr:[["Uranium + nuclear components","CCJ miner; BWXT components/defense"]],
      be:"Commodity cycle; program timing." },
  ]},
  { cat:"Critical minerals / Rare earths", flag:"add only on a strong signal", rot:{w:"LAGGING",c:C.amber}, pos:[
    { t:"MP", n:"MP Materials", pct:1.00, st:"Owned", cv:"Promising", ty:"Tactical", cd:"flat", lock:true, own:"p,s",
      nr:"Hold light — US-gov-backed (stake + price floor); trimmed, lagging. Add only on a strong signal.",
      cdNote:"No recent change; trimmed 56% earlier; sleeve lagging (closest to a base, no turn yet).",
      dr:[["US-government-backed (Meridian)","gov holds an equity stake + a guaranteed price floor; Mountain Pass + magnets"]],
      be:"China floods the market; strong dollar; a US–China thaw deflates the 'domestic supply' premium." },
    { t:"LYSDY", n:"Lynas (Australia)", pct:0.11, st:"Owned", cv:"Promising", ty:"Core", cd:"flat", lock:true, own:"p,s",
      nr:"Hold — the sleeve's durability anchor; the name to watch hardest if minerals turns up.",
      cdNote:"No recent change.",
      dr:[["Largest non-China separator (Meridian)","the processing bottleneck the West needs; Australian — less politically fragile than a US-favoritism play"]],
      be:"Still commodity-price exposed; Chinese oversupply." },
    { t:"+ more", n:"LIT · ARRRF · UURAF · TLOFF", pct:0, st:"Owned", cv:"Weak", ty:"Speculative", cd:"flat", lock:true, own:"p",
      nr:"Hold tiny, no add — lithium ETF + lottery-ticket rare-earth probes.",
      cdNote:"No recent change.",
      dr:[["Lithium ETF + tiny probes","broad + lottery-ticket exposure"]],
      be:"Oversupply; tiny names can go to zero." },
  ]},
  { cat:"Clean energy / Power / Electrification", rot:{w:"SOFTENING",c:C.amber}, pos:[
    { t:"VOLT", n:"Tema Electrification ETF", pct:4.18, st:"Owned", cv:"Promising", ty:"Tactical", cd:"flat", own:"p,s",
      nr:"Hold — your grid-power thesis; FS Industrials-OW is a tailwind, but momentum softened lately.",
      cdNote:"Sleeve softened over the last month; no thesis change.",
      dr:[["Electrification / power / grid (your pick)","actively managed — GE Vernova, Eaton, NextEra up top; the AI-power-demand theme"]],
      be:"Rate-sensitive theme; project timing." },
    { t:"+ names", n:"PWR · STRL · IESC · FIX · BE · GEV", pct:0, st:"Owned", cv:"Promising", ty:"Tactical", cd:"up", own:"p,s",
      nr:"Hold — PWR/STRL/IESC/FIX are current FS Top-5 picks (electrical/infra/HVAC data-center build); BE/GEV ride the power theme.",
      cdNote:"PWR (Top-5 large-cap) + STRL/IESC/FIX (Top-5 SMID) all named in the 5/28 deck → group conviction up.",
      dr:[["Data-center power build (Lee Top-5)","PWR + STRL + IESC + FIX are named FS Top-5 picks, 5/28; BE/GEV adjacent"]],
      be:"Cyclical capex; profitability (BE)." },
    { t:"+ ETFs", n:"PBW · DRIV · SNSR · NXT", pct:0, st:"Owned", cv:"Mixed", ty:"Tactical", cd:"flat", own:"p,s",
      nr:"Hold — FS May tactical ETF picks (clean energy / EV / IoT). Assess individually next pass.",
      cdNote:"No recent change.",
      dr:[["FS tactical ETF picks (Lee/Newton)","clean-energy / EV / IoT baskets from the May tactical sleeve"]],
      be:"Rate-sensitive themes; weak tape." },
  ]},
  { cat:"Financials", rot:{w:"LAGGING",c:C.red}, pos:[
    { t:"XLF", n:"Financials ETF", pct:1.53, st:"Owned", cv:"Promising", ty:"Tactical", cd:"up", own:"p",
      nr:"Diversify-into-financials pick (FS 5/28) — it's lagged, which is catch-up room → add on the diversify thesis, no rush.",
      cdNote:"5/28 deck reaffirmed financials in 'What to Own' → conviction building. Price still lagging — that's the entry, not a red flag.",
      dr:[["Financials to cut AI concentration (Lee)","FS 5/28 'What to Own' lists XLF + KRE — the diversify-off-mega-cap-tech call"],["Lagged = catch-up","a source-endorsed laggard has room to run as it converges to value"]],
      be:"Credit deterioration; or financials simply keep lagging (thesis doesn't play out)." },
    { t:"+ names", n:"GS · JPM", pct:0, st:"Owned", cv:"Promising", ty:"Core", cd:"up", own:"p,s",
      nr:"Hold — GS is a current FS Top-5 large-cap (5/28); JPM the quality anchor. Both ride the diversify theme.",
      cdNote:"GS named an FS Top-5 large-cap in the 5/28 deck → conviction up.",
      dr:[["Quality banks (Lee; GS Top-5)","GS named FS Top-5 large-cap 5/28; JPM money-center anchor"]],
      be:"Credit cycle; markets cyclicality." },
  ]},
  { cat:"Gold / Silver — hedges", rot:{w:"HEDGE",c:C.gray}, pos:[
    { t:"GDX", n:"Gold miners", pct:1.78, st:"Owned", cv:"Promising", ty:"Hedge", cd:"flat", own:"p",
      nr:"Hedge — gave back its run as risk-on resumed (expected). Judged by its protective role, not return.",
      cdNote:"Normal hedge behavior; stabilizing.",
      dr:[["Portfolio protection","gold as a hedge against a risk-off turn"]],
      be:"Gold reverses; real yields spike." },
    { t:"+ more", n:"WPM · SIL", pct:0, st:"Owned", cv:"Promising", ty:"Hedge", cd:"flat", own:"p",
      nr:"Hedge hold — streaming royalty (lower-risk) + silver (higher-beta).",
      cdNote:"No recent change.",
      dr:[["Royalty + silver","protection with a demand kicker"]],
      be:"Metals price." },
  ]},
  { cat:"Space / Defense / Broad / Other", rot:{w:"MIXED",c:C.gray}, pos:[
    { t:"GOOGL", n:"Alphabet", pct:0.45, st:"Owned", cv:"Promising", ty:"Core", cd:"up", own:"p,s",
      nr:"Tiny — now a current FS Top-5 large-cap (5/28). Was thin, now FS-named.",
      cdNote:"Newly added to the FS Top-5 in the 5/28 deck → conviction up.",
      dr:[["FS Top-5 large-cap (Lee, NEW 5/28)","newly named among Fundstrat's most-wanted large-caps"]],
      be:"Ad cyclicality; the AI-search-disruption narrative." },
    { t:"ITA", n:"Aerospace & Defense ETF", pct:0, st:"Owned", cv:"Promising", ty:"Tactical", cd:"up", fresh:true, own:"p,s",
      nr:"Fresh breakout — Newton (5/28) says it just cleared a multi-month downtrend. A laggard turning up (see Fresh Signals up top).",
      cdNote:"Newton 5/28 PM flagged the breakout (cleared a multi-month downtrend) → conviction up; fresh.",
      dr:[["Aerospace/defense breakout (Newton 5/28)","cleared a multi-month downtrend — leadership broadening into A&D"]],
      be:"Defense-budget / geopolitics swings; the breakout fails to follow through." },
    { t:"AMZN", n:"Amazon", pct:1.28, st:"Owned", cv:"—", ty:"Core", cd:"flat", own:"p,s",
      nr:"Core hold — quality compounder, but no documented thesis from you. Worth a line.",
      cdNote:"Unassessed — give me your thesis and I'll grade it.",
      dr:[["AWS + retail compounder","cloud + commerce — but not in your documented theses"]],
      be:"AWS deceleration." },
    { t:"RDDT", n:"Reddit", pct:0.90, st:"Owned", cv:"Promising", ty:"Tactical", cd:"flat", own:"p",
      nr:"Hold — AI data-licensing angle (content licensed for AI training).",
      cdNote:"No recent change.",
      dr:[["AI data licensing","content licensed for AI training"]],
      be:"Ad cyclicality; valuation." },
    { t:"+ more", n:"COST · RPG · XLI · ASTS · LUNR · UMAC", pct:0, st:"Owned", cv:"—", ty:"Tactical", cd:"flat", own:"p,s",
      nr:"Mixed — RPG (FS Pure Growth, holds ~2.7% MU) + XLI (FS double-OW industrials) are FS-tied; COST is a core compounder (no documented thesis — a line?); the rest are moonshots.",
      cdNote:"No recent change; RPG/XLI are FS-tied, the small names are speculative.",
      dr:[["FS-tied + core + spec","RPG/XLI ride FS calls; COST core compounder; ASTS/LUNR/UMAC lottery-tickets"]],
      be:"Mixed — varies by name." },
  ]},
];

const Q_WHEN = [
  { q:"Want a number alongside the conviction word, or is the word enough?", d:"5/29", tag:"system design" },
  { q:"Account-level holdings view — add it, or is aggregate + Parents/SKB enough?", d:"5/29", tag:"system design" },
];
const R_PENDING = [
  { r:"Deepen the 'why' on priority holdings with your real sourced rationale (Live Theses / Decisions Log / FS bible) — e.g. XLF's actual Fundstrat reasoning. [chunk 2]", pr:"high" },
  { r:"Per-name live prices + day moves on the holdings rows (currently % is from the 5/27 book).", pr:"med" },
  { r:"Critical-minerals watch universe — investable names around the federal money-flow (e.g. ReElement/AREC).", pr:"med" },
];
const R_DONE = [
  { r:"Rotation engine is LIVE (data 5/29).", f:"Your AI engine leads everything (+47%/3M); software just caught up; the 🔒 burned sleeves all lag with none turning up → no re-entry signal, the light sizing is confirmed by the tape." },
  { r:"GRNJ + VOLT identified.", f:"GRNJ = Fundstrat Granny Shots small/mid-cap (pairs with GRNY). VOLT = Tema Electrification ETF (power/grid/nuclear). Both de-flagged and seeded." },
  { r:"Vulcan (the ProPublica name tied to Don Jr.) is PRIVATE / uninvestable.", f:"Play the durable public names around the federal money-flow (MP, Lynas) — not the favor itself." },
];
const CATALYSTS = [
  { d:"Aug 17", e:"Fabrinet (FN) earnings", note:"your AI/optical buy-on-pullback name — watch for the setup (~$580–620)" },
  { d:"~Aug", e:"OGE Form 278-T quarterly filing", note:"Trump-trade-pattern signal you track" },
];

// ── FRESH SIGNALS (Actions strip): did something just happen that's a buy? Seeded from the 5/28 daily notes. ──
const FRESH_SIGNALS = [
  { t:"ITA", n:"Aerospace & Defense ETF", urg:"act", urgLabel:"early signal — act within days", when:"Newton · 5/28 PM (1 day ago)",
    what:"Cleared a multi-month downtrend — a fresh breakout; leadership broadening into aerospace & defense.",
    why:"A laggard you already hold, turning up — Newton says lean bullish and add on weakness. Your catch-up setup: room to run as it re-rates.",
    detail:"Newton's 5/28 evening note ('Broadening Accelerates') flags ITA clearing a multi-month downtrend alongside health-care services, and he's explicitly bullish — use any weakness to add. You hold a small ITA slice already, so this is an add-candidate, not a new name. Time-sensitive because breakouts tend to run; a defined add on a dip toward the breakout level beats chasing green. Size it as a Tactical add." },
  { t:"FN", n:"Fabrinet — AI optical", urg:"watch", urgLabel:"watch — wait for your trigger (~$580–620)", when:"Lee · 5/28 monthly (1 day ago)",
    what:"Newly named a Fundstrat Top-5 SMID pick (AI-optical, 800G hyperscale ramps).",
    why:"The buy-on-pullback name you flagged is now FS-endorsed — but it's near its high (~$673, ~50x fwd). The edge is the entry, not today's price.",
    detail:"FN is a new FS Top-5 SMID long in the 5/28 deck — strong thesis (capacity-constrained, 800G ramps into FY27) but it stacks the AI beta you've been trimming and sits ~50x forward near an all-time high. Your documented buy-triggers: a pullback to ~$580–620, OR funding from an extra SMH/MAGS trim (an AI-rotation swap, not financials cash). Earnings 8/17 is the next catalyst. No rush — a standing watch with a price trigger, not an act-now signal." },
];

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
const STAMP = "sourced: FS 5/28 bible · rotation 5/29";

export default function ConvictionCockpit() {
  const [open, setOpen] = useState({});
  const [posOpen, setPosOpen] = useState({});
  const [collapsed, setCollapsed] = useState({});
  const [view, setView] = useState("agg");
  const [legend, setLegend] = useState(false);
  const dirColor = (d)=> d==="up"?C.green : d==="down"?C.red : C.dim;
  const ownerFilter = (own) => view==="agg" ? true : view==="parents" ? own.includes("p") : own.includes("s");
  const needsYou = 0; // blocking actions/questions
  const freshCount = FRESH_SIGNALS.length;
  const actNow = FRESH_SIGNALS.filter(s=>s.urg==="act").length;

  return (
    <div style={{ background:C.bg, color:C.text, fontFamily:sans, minHeight:"100%", padding:"18px 13px 52px", lineHeight:1.45 }}>
      <div style={{ maxWidth:840, margin:"0 auto" }}>

        <div style={{ display:"flex", alignItems:"baseline", justifyContent:"space-between", flexWrap:"wrap", gap:8 }}>
          <div style={{ fontSize:20, fontWeight:700, letterSpacing:-0.3 }}>Conviction Cockpit</div>
          <div style={{ fontFamily:mono, fontSize:11.5, color:C.dim }}>$1.88M · cash 1.48% · <span style={{ color:C.faint }}>book 5/27 · reads FS 5/28 · rotation 5/29</span></div>
        </div>

        <div style={{ marginTop:12, ...card, borderColor: freshCount? C.amber+"66":C.green+"44", background: freshCount? C.amber+"10":C.green+"0c", display:"flex", alignItems:"center", gap:12 }}>
          <div style={{ fontFamily:mono, fontSize:26, fontWeight:700, color: freshCount?C.amber:C.green, lineHeight:1 }}>{freshCount||"✓"}</div>
          <div>
            <div style={{ fontSize:13.5, fontWeight:600 }}>{freshCount? `${freshCount} fresh signal${freshCount>1?"s":""} to look at${actNow?` · ${actNow} time-sensitive`:""}`:"Nothing needs you — all quiet"}</div>
            <div style={muted}>{freshCount? "Buy-signals from the last day — in Today's actions below. 0 blocking questions; nothing forced." : "0 live actions · 0 blocking questions · no sleeve graduating. The rotation read confirms your current posture."}</div>
          </div>
        </div>

        {/* ACTIONS — Fresh Signals */}
        <Section id="actions" title="Today's actions" icon="🟢" badge={freshCount?`${freshCount} fresh`:"0 live"} badgeColor={freshCount?C.amber:C.faint} openMap={open} setOpen={setOpen}>
          <div style={{ fontSize:11, color:C.faint, fontFamily:mono, marginBottom:8 }}>FRESH SIGNALS — did something just happen that's a buy? (last ~48h)</div>
          {FRESH_SIGNALS.map((s)=>{
            const u = s.urg==="act" ? { c:C.amber, icon:"⏳" } : { c:C.blue, icon:"👁" };
            const key="fs"+s.t, isO=posOpen[key];
            return (
              <div key={key} style={{ ...card, marginBottom:8, borderColor:u.c+"44", background:u.c+"0a" }}>
                <div onClick={()=>setPosOpen(st=>({...st,[key]:!st[key]}))} style={{ cursor:"pointer" }}>
                  <div style={{ display:"flex", alignItems:"baseline", gap:8, flexWrap:"wrap" }}>
                    <span style={{ fontFamily:mono, fontWeight:700, fontSize:13.5, color:C.text }}>{s.t}</span>
                    <span style={{ fontSize:11.5, color:C.faint }}>{s.n}</span>
                  </div>
                  <div style={{ marginTop:5, fontSize:11.5, color:u.c, fontFamily:mono }}>{u.icon} {s.urgLabel}</div>
                  <div style={{ marginTop:7, fontSize:12.5, color:C.text }}><span style={{ color:C.dim, fontWeight:600 }}>What:</span> {s.what}</div>
                  <div style={{ marginTop:4, fontSize:12.5, color:C.dim }}><span style={{ color:C.dim, fontWeight:600 }}>Why it's a buy:</span> {s.why}</div>
                  <div style={{ marginTop:7, display:"flex", justifyContent:"space-between", alignItems:"center", gap:8 }}>
                    <span style={{ fontFamily:mono, fontSize:10.5, color:C.faint }}>{s.when}</span>
                    <span style={{ fontSize:11, color:u.c }}>{isO?"hide reasoning ▲":"full reasoning ▾"}</span>
                  </div>
                </div>
                {isO && (
                  <div style={{ marginTop:8, paddingTop:8, borderTop:`1px solid ${C.line}`, ...muted }}>
                    {s.detail}
                    <div style={{ marginTop:8, fontFamily:mono, fontSize:10, color:C.faint }}>{STAMP} · not a trade — you decide, you size</div>
                  </div>
                )}
              </div>
            );
          })}
          <div style={{ marginTop:6, paddingTop:10, borderTop:`1px solid ${C.line}`, fontSize:12, color:C.dim }}>
            👀 <b style={{ color:C.text }}>Also worth a look (not a signal):</b> software (IGV) caught up to your AI engine over the last month — the one sleeve keeping pace; the most natural place to lean further into AI if it keeps leading. Your 🔒 sleeves (crypto/nuclear/minerals) still show no turn — no re-entry yet.
          </div>
        </Section>

        {/* QUESTIONS */}
        <Section id="questions" title="Questions for you" icon="❓" badge={`${Q_WHEN.length}`} badgeColor={C.dim} openMap={open} setOpen={setOpen} defaultOpen={false}>
          <div style={{ ...card, marginBottom:8, fontSize:12, color:C.faint }}>Blocking: none right now (pilot scope + GRNJ/VOLT resolved).</div>
          {Q_WHEN.map((x,i)=>(
            <div key={i} style={{ ...card, marginBottom:7 }}>
              <div style={{ fontSize:12.5, color:C.dim }}>{x.q}</div>
              <div style={{ marginTop:5, fontFamily:mono, fontSize:10.5, color:C.faint }}>{x.tag} · {x.d}</div>
            </div>
          ))}
        </Section>

        {/* WHAT CHANGED */}
        <Section id="changed" title="What changed since you last looked" icon="🆕" openMap={open} setOpen={setOpen} defaultOpen={false}>
          <div style={card}>
            <div style={muted}><span style={{ color:C.text }}>Rotation reads went live</span> (data 5/29) — first time the cockpit is reading the tape. GRNJ &amp; VOLT confirmed and seeded. From here, this section shows only what's new since your last visit and won't hide items just because you've seen them once.</div>
          </div>
        </Section>

        {/* MARKET READ — rotation + macro */}
        <Section id="market" title="Market read — rotation + macro" icon="🌐" openMap={open} setOpen={setOpen} defaultOpen={true}>
          <div style={{ ...card, marginBottom:8 }}>
            <div style={{ fontSize:11, color:C.faint, fontFamily:mono, marginBottom:8 }}>SLEEVE LEADERSHIP (relative strength vs market · live 5/29)</div>
            {ROTATION.map((r,i)=>(
              <div key={i} style={{ display:"grid", gridTemplateColumns:"168px 116px 1fr", gap:10, alignItems:"center", padding:"5px 0", borderTop: i?`1px solid ${C.line}`:"none" }}>
                <span style={{ fontSize:12.5, color:C.text }}>{r.s}</span>
                <Pill label={r.w} color={r.c} />
                <span style={{ fontSize:11.5, color:C.dim }}><span style={{ fontFamily:mono, color:C.faint }}>{r.n}</span> · {r.note}</span>
              </div>
            ))}
          </div>
          <div style={card}>
            <div style={{ fontSize:11, color:C.faint, fontFamily:mono, marginBottom:6 }}>MACRO BACKDROP (live 5/29)</div>
            <div style={{ fontFamily:mono, fontSize:12, color:C.text }}>{MACRO.line}</div>
            <div style={{ marginTop:6, ...muted }}>{MACRO.tape}</div>
            <div style={{ marginTop:8 }}>
              {MACRO.impl.map(([k,v],i)=>(<div key={i} style={{ ...muted, marginBottom:4 }}>→ <b style={{ color:C.dim }}>{k}</b> — {v}</div>))}
            </div>
            <div style={{ marginTop:8, fontSize:11, color:C.faint, fontFamily:mono }}>{MACRO.note}</div>
          </div>
        </Section>

        {/* RESEARCH */}
        <Section id="research" title="Research" icon="🔬" openMap={open} setOpen={setOpen} defaultOpen={false}>
          <Section id="rpending" title="Pending — you prioritize" icon="⏳" badge={R_PENDING.length} badgeColor={C.blue} openMap={open} setOpen={setOpen}>
            {R_PENDING.map((x,i)=>(
              <div key={i} style={{ ...card, marginBottom:7, display:"flex", gap:10, alignItems:"flex-start" }}>
                <span style={{ fontFamily:mono, fontSize:10, color: x.pr==="high"?C.amber:C.faint, marginTop:2, minWidth:34 }}>{x.pr}</span>
                <span style={{ fontSize:12.5, color:C.dim }}>{x.r}</span>
              </div>
            ))}
          </Section>
          <Section id="rdone" title="Completed — significant findings" icon="✅" badge={R_DONE.length} badgeColor={C.green} openMap={open} setOpen={setOpen} defaultOpen={false}>
            {R_DONE.map((x,i)=>(
              <div key={i} style={{ ...card, marginBottom:7, borderColor:C.green+"33" }}>
                <div style={{ fontSize:13, color:C.text }}>{x.r}</div>
                <div style={{ marginTop:5, ...muted }}>{x.f}</div>
              </div>
            ))}
          </Section>
        </Section>

        {/* HOLDINGS */}
        <Section id="holdings" title="Holdings" icon="📊" openMap={open} setOpen={setOpen} defaultOpen={true}>
          <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", flexWrap:"wrap", gap:8, marginBottom:8 }}>
            <div style={{ display:"flex", gap:4, background:C.panel, border:`1px solid ${C.line}`, borderRadius:8, padding:3 }}>
              {[["agg","Aggregate"],["parents","Parents 67.9%"],["skb","SKB 32.1%"]].map(([k,l])=>(
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
              <div style={{ marginTop:7, color:C.faint }}>TYPE: Core (durable, can be large) · Tactical (catalyst/cycle, has an exit) · Speculative (small high-risk, capped) · Hedge (protection). 🔒 = add only on a strong signal. <b style={{color:C.dim}}>▲/▼ on a row</b> = your conviction-direction just changed — event-driven (a source call, a catalyst), NOT daily price; tap for why. No arrow = steady. The colored badge on each <b style={{color:C.dim}}>sleeve header</b> = live price rotation vs market (the momentum layer). 🔔 = a fresh buy-signal (see top). ACTIONS live up top.</div>
            </div>
          )}

          {view!=="agg" && (
            <div style={{ ...card, marginBottom:8, fontSize:11.5, color:C.faint }}>
              Showing names held by <b style={{ color:C.dim }}>{view==="parents"?"Parents":"SKB"}</b>. Exact per-owner $/% split isn't in the 5/27 snapshot — populates with the per-owner parse. (% shown are book-aggregate.)
            </div>
          )}

          {HOLD.map(group=>{
            const rows = group.pos.filter(p=>ownerFilter(p.own));
            if (!rows.length) return null;
            const isC = collapsed[group.cat];
            return (
              <div key={group.cat} style={{ marginBottom:10 }}>
                <div onClick={()=>setCollapsed(s=>({...s,[group.cat]:!s[group.cat]}))}
                  style={{ display:"flex", alignItems:"center", gap:8, cursor:"pointer", padding:"5px 2px", userSelect:"none", flexWrap:"wrap" }}>
                  <span style={{ color:C.faint, fontFamily:mono, fontSize:10.5, transform:isC?"rotate(-90deg)":"none", transition:"transform .15s" }}>▾</span>
                  <span style={{ fontSize:12, fontWeight:600, color:C.dim }}>{group.cat}</span>
                  {group.rot && <Pill label={group.rot.w} color={group.rot.c} title="live sleeve rotation vs market (5/29)" />}
                  {group.flag && <span style={{ fontSize:10.5, color:C.amber, fontFamily:mono }}>🔒 {group.flag}</span>}
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
                                {p.fresh && <span style={{ fontSize:10.5 }} title="fresh buy-signal — see Fresh Signals up top">🔔</span>}
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
                              {p.dr.map(([w,why],j)=>(<div key={j} style={{ marginBottom:5, ...muted }}><span style={{ color:C.text, fontWeight:600 }}>{w}</span> — {why}</div>))}
                              {p.be && p.be!=="—" && (<>
                                <div style={{ color:C.faint, fontFamily:mono, fontSize:10, textTransform:"uppercase", letterSpacing:0.5, margin:"9px 0 4px" }}>What could break it</div>
                                <div style={muted}>{p.be}</div>
                              </>)}
                              <div style={{ color:C.faint, fontFamily:mono, fontSize:10, textTransform:"uppercase", letterSpacing:0.5, margin:"9px 0 4px" }}>Size posture</div>
                              <div style={muted}>Conviction supports <span style={{ color:C.text }}>{POSTURE[p.cv]} position</span> (you hold {p.pct>0?p.pct.toFixed(2)+"%":"a small amount"}). Guidance — a ceiling, not a target; you size at the moment.</div>
                              <div style={{ marginTop:10, fontFamily:mono, fontSize:10, color:C.faint }}>{STAMP}</div>
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
          <div style={{ marginTop:8, fontSize:11, color:C.faint }}>
            Options sleeve (LEU $300 call · BMNR call stack · HOOD $100 call) + dust (&lt;$500) shown in a later pass. "+ more" rows group smaller names to seed individually.
          </div>
        </Section>

        {/* CATALYSTS */}
        <Section id="cats" title="Upcoming catalysts — yours, near-term" icon="📅" badge={CATALYSTS.length} openMap={open} setOpen={setOpen} defaultOpen={false}>
          {CATALYSTS.map((x,i)=>(
            <div key={i} style={{ ...card, marginBottom:7, display:"flex", gap:12, alignItems:"baseline" }}>
              <span style={{ fontFamily:mono, fontSize:12, color:C.accent, minWidth:58 }}>{x.d}</span>
              <div><div style={{ fontSize:13, color:C.text }}>{x.e}</div><div style={muted}>{x.note}</div></div>
            </div>
          ))}
          <div style={{ fontSize:11, color:C.faint, marginTop:4 }}>More populate when the calendar sync runs (held-name earnings + policy dates, next ~30 days).</div>
        </Section>

        <div style={{ marginTop:18, ...card, background:C.panel2, fontSize:12, color:C.dim }}>
          <span style={{ color:C.green, fontFamily:mono }}>● LIVE:</span> sleeve rotation + macro (5/29) · per-name reads now sourced from the FS 5/28 bible + your theses, with a staleness stamp on each. <span style={{ color:C.accent, fontFamily:mono }}>NEXT:</span> Fresh Signals in the Actions strip (ITA, FN). Per-name % is still from the 5/27 book; live prices + the daily pipeline follow.
        </div>
        <div style={{ marginTop:12, fontSize:11, color:C.faint, textAlign:"center", fontFamily:mono }}>
          decisions on top · sleeve reads are live · tap anything to expand · every section collapses independently
        </div>
      </div>
    </div>
  );
}
