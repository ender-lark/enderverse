import React, { useState, useMemo } from "react";

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
const FEED = {"generated_at": "2026-06-05T19:06:05.568860+00:00", "staleness": {"stamp": "sourced: portfolio 05-31 · uw_price 06-05 · uw_macro 06-05 · fundstrat_bible 05-28 · fundstrat_daily 06-03", "entries": [{"source": "portfolio", "date": "2026-05-31", "age_days": 5, "cadence": "on_refresh", "stale": false, "flag": ""}, {"source": "uw_price", "date": "2026-06-05T19:06:05.568860+00:00", "age_days": 0, "cadence": "daily", "stale": false, "flag": ""}, {"source": "uw_macro", "date": "2026-06-05T19:06:05.568860+00:00", "age_days": 0, "cadence": "daily", "stale": false, "flag": ""}, {"source": "fundstrat_bible", "date": "2026-05-28", "age_days": 8, "cadence": "monthly", "stale": false, "flag": ""}, {"source": "fundstrat_daily", "date": "2026-06-03", "age_days": 2, "cadence": "daily", "stale": false, "flag": ""}], "stale": []}, "lane_status": {"rows": [{"key": "portfolio", "label": "Portfolio", "status": "has_data", "detail": "checked", "count": 0, "checked_at": ""}, {"key": "uw_price", "label": "Prices", "status": "has_data", "detail": "checked", "count": 0, "checked_at": ""}, {"key": "uw_macro", "label": "Macro", "status": "has_data", "detail": "checked", "count": 0, "checked_at": ""}, {"key": "fundstrat_bible", "label": "FS Bible", "status": "has_data", "detail": "checked", "count": 0, "checked_at": ""}, {"key": "fundstrat_daily", "label": "FS Daily", "status": "has_data", "detail": "checked", "count": 0, "checked_at": ""}, {"key": "catalysts", "label": "Catalysts", "status": "has_data", "detail": "checked", "count": 8, "checked_at": ""}, {"key": "research", "label": "Research Queue", "status": "has_data", "detail": "checked", "count": 1, "checked_at": ""}, {"key": "synthesis", "label": "Daily Synthesis", "status": "has_data", "detail": "checked", "count": 6, "checked_at": ""}, {"key": "uw_opportunity", "label": "UW Flow", "status": "has_data", "detail": "checked", "count": 40, "checked_at": ""}, {"key": "signal_log", "label": "Signal Log", "status": "has_data", "detail": "checked", "count": 6, "checked_at": ""}, {"key": "event_risk", "label": "Event Risk", "status": "has_data", "detail": "checked", "count": 3, "checked_at": ""}, {"key": "top_prospects", "label": "Top Prospects", "status": "has_data", "detail": "checked", "count": 10, "checked_at": ""}, {"key": "target_drift", "label": "Target Drift", "status": "has_data", "detail": "checked", "count": 6, "checked_at": ""}, {"key": "account_positions", "label": "Account Positions", "status": "not_checked", "detail": "missing live source input", "count": 0, "checked_at": "", "next_step": "Supply src\\account_positions.json through the owning source routine or manual live-source drop.", "missing_impact": "Account views are not checked; do not imply no account-level breakdown."}, {"key": "meridian", "label": "Meridian", "status": "not_checked", "detail": "missing live source input", "count": 0, "checked_at": "", "next_step": "Supply src\\meridian_items.json through the owning source routine or manual live-source drop.", "missing_impact": "Meridian source is not checked; missing data is not a no-signal read."}], "counts": {"failed": 0, "not_checked": 2, "has_data": 13, "stale": 0, "checked_clear": 0}, "has_dark_lanes": true, "has_stale_or_failed": false}, "hero": {"hero": {"count": 14, "names": ["MAGS", "SMH", "GRNY", "GRNJ", "NVDA", "IGV", "LEU", "VOLT", "XLF", "IVES", "BMNR", "MU", "UUUU", "MP"], "leading_sleeves": ["SMH"]}, "needs_you": {"count": 0, "items": []}}, "actions": [{"rank": 1, "kind": "event_risk", "ticker": null, "action_state": "ACT_NOW", "what": "Event risk: Middle East oil/rates shock can affect new-buy timing", "confidence": "Moderate", "your_move": "Review exposure, hedges, and new buys before acting today: Middle East oil/rates shock can affect new-buy timing (oil, rates, volatility, energy, growth). If the event changes oil/rates/vol or a held sleeve, decide whether to hold, hedge, trim, or wait.", "gate": null, "source": "event_risk", "why": "Fundstrat technical work flagged a near-term WTI and 10-year yield bounce tied to Gulf/Iran-war headlines before a possible reversal; review exposure before new risk adds.", "time_window": "today", "capital_effect": "review", "goal_channels": ["downside_protection", "opportunity_cost", "data_quality"], "goal_impact": "Medium", "goal_score": 75, "action_label": "EVENT RISK", "why_it_moves_goal": "Fast exogenous shocks can change sizing, hedging, and opportunity cost before normal source lanes update.", "missing_evidence": ["WTI approaches 99-101, 10Y yield approaches roughly 4.55-4.59, or Strait/ceasefire headlines change abruptly."]}, {"rank": 2, "kind": "conviction_gap", "ticker": "NVDA", "action_state": "ACT_NOW", "what": "Conviction gap: NVDA is under target", "confidence": "High", "your_move": "NVDA is 6.6% vs 12.0% target. Decide: add with funding, hold below target with a written reason, cut the target, or remove it from the model. If adding, run the pre-trade gate; no auto-buy.", "gate": {"needs_gate": true, "preview": "🟡 size → gate", "ticker": "NVDA", "default_action": "ADD"}, "source": "target_drift", "why": "Target drift shows a 5.4pp sizing gap vs the AI working model.", "sizing": "Gap to target: 5.4pp; target is directional, not an order.", "goal_channels": ["sizing_gap", "conviction", "opportunity_cost"], "goal_impact": "High", "goal_score": 85, "time_window": "1-3 trading days", "capital_effect": "review", "action_label": "SIZE GAP", "why_it_moves_goal": "A high-conviction target gap can make the right thesis too small to matter unless disposition is explicit.", "missing_evidence": ["live opportunity", "funding leg", "pre-trade gate"]}, {"rank": 3, "kind": "lean_in", "ticker": "ANET", "action_state": "WATCH", "what": "Lean-in — looks good", "confidence": "Moderate", "your_move": "ANET looks good (Promising, LEADING) — size it yourself and run the pre-trade gate. No auto-buy.", "gate": {"needs_gate": true, "preview": "🟡 size → gate", "ticker": "ANET", "default_action": "ADD"}, "source": "lean_in", "why": "ANET: Promising and the tape's with it (LEADING) — a place to start.", "goal_channels": ["sizing_gap", "upside", "opportunity_cost"], "goal_impact": "High", "goal_score": 76, "time_window": "1-2 weeks", "capital_effect": "add", "action_label": "ADD/ROTATE", "why_it_moves_goal": "A conviction-backed sizing gap can make a right call too small.", "missing_evidence": []}, {"rank": 4, "kind": "lean_in", "ticker": "GOOGL", "action_state": "WATCH", "what": "Lean-in — looks good", "confidence": "Moderate", "your_move": "GOOGL looks good (Promising, LEADING) — size it yourself and run the pre-trade gate. No auto-buy.", "gate": {"needs_gate": true, "preview": "🟡 size → gate", "ticker": "GOOGL", "default_action": "ADD"}, "source": "lean_in", "why": "GOOGL: Promising and the tape's with it (LEADING) — a place to start.", "goal_channels": ["sizing_gap", "upside", "opportunity_cost"], "goal_impact": "High", "goal_score": 76, "time_window": "1-2 weeks", "capital_effect": "add", "action_label": "ADD/ROTATE", "why_it_moves_goal": "A conviction-backed sizing gap can make a right call too small.", "missing_evidence": []}], "fresh_signals": [], "signal_log": [{"signal": "Macro: complacent vol plus steep curve cyclical tailwind", "ticker": "XLF, GS, ITA", "date": "2026-06-04", "priority": "medium", "source": "https://app.notion.com/p/375c50314bb681df8743efc9c7563019", "note": "VIX near 16 and 2s10s near +41 bps create risk-on/financials tailwind context; hedge cost may be favorable. Watch-only."}, {"signal": "Iran escalation: US strikes plus prediction-market divergence", "ticker": "ITA, BWXT, LEU, UUUU, GLD", "date": "2026-06-04", "priority": "high", "source": "https://app.notion.com/p/375c50314bb681a29715f5ce022ede80", "note": "Fresh strikes and whale prediction-market divergence create fast geopolitical risk context for defense, nuclear fuel, and safe-haven sleeves. Watch-only."}, {"signal": "Oil rallying on Iran/Hormuz, inflation and macro watch", "ticker": "USO", "date": "2026-06-02", "priority": "medium", "source": "https://app.notion.com/p/373c50314bb6819c98d2e9d9c57c3bf0", "note": "USO rose roughly 5% week-over-week as Hormuz disruption stayed relevant; matters as inflation/rates input ahead of FOMC. Watch-only."}, {"signal": "Oil spike on renewed Iran-US strikes", "ticker": "USO, ITA, LEU, UUUU, CCJ, BWXT, BE", "date": "2026-06-01", "priority": "high", "source": "https://app.notion.com/p/372c50314bb6814c9314e3a0de7afd70", "note": "Oil shock can pressure AI-heavy multiples through inflation/rates while supporting defense and nuclear/critical-minerals watch sleeves. Watch-only."}, {"signal": "Oil down on US-Iran de-escalation and nuclear-deal expectations", "ticker": "LEU, UUUU, CCJ, BWXT, BE, ITA", "date": "2026-06-01", "priority": "medium", "source": "https://app.notion.com/p/372c50314bb681a7b9feda6914bbb3b4", "note": "Lower oil and yields create a risk-on book tailwind but mixed read for nuclear, energy-transition, and defense sleeves; oil direction is the hard tell. Watch-only."}, {"signal": "Metals tariffs raised, effective June 8", "ticker": "NUE, MP, XLI, LEU, UUUU", "date": "2026-06-02", "priority": "medium", "source": "https://app.notion.com/p/373c50314bb6818e9857f52cb4eda89b", "note": "Higher metals tariffs and ended exemptions are a policy tailwind for domestic materials and critical-minerals exposure. Watch-only."}], "event_risk": [{"date": "2026-06-03", "title": "Middle East oil/rates shock can affect new-buy timing", "severity": "high", "horizon": "daily", "channels": ["oil", "rates", "volatility", "energy", "growth"], "tickers": ["XOP", "XLE", "TNX"], "affected": ["Energy", "Semiconductors", "High-duration growth", "Portfolio hedges"], "source": "Fundstrat Gmail full-body read: Jun 3 FlashInsights / Daily Technical Strategy", "summary": "Fundstrat technical work flagged a near-term WTI and 10-year yield bounce tied to Gulf/Iran-war headlines before a possible reversal; review exposure before new risk adds.", "trigger": "WTI approaches 99-101, 10Y yield approaches roughly 4.55-4.59, or Strait/ceasefire headlines change abruptly.", "direction": "risk_watch"}, {"date": "2026-06-03", "title": "Financials breakdown and crypto-linked weakness weigh on tape breadth", "severity": "medium", "horizon": "1-2 weeks", "channels": ["financials", "breadth", "crypto", "risk appetite"], "tickers": ["RYF", "XLF", "COIN", "HOOD", "BX", "KKR"], "affected": ["Financials", "Crypto beta", "Broad equity tape"], "source": "Fundstrat Gmail full-body read: Daily Technical Strategy", "summary": "Fundstrat technical work flagged equal-weight financial weakness and crypto-linked financial pressure as a tape negative that may persist over coming weeks.", "trigger": "RYF remains below support near 74.40, crypto-linked financials fail to stabilize, or XLF/RYF relative weakness accelerates.", "direction": "risk_watch"}, {"date": "2026-06-03", "title": "Narrow AI leadership versus improving equal-weight participation", "severity": "medium", "horizon": "daily", "channels": ["breadth", "AI", "semiconductors", "rotation"], "tickers": ["MAGS", "SMH", "SPY", "RSP"], "affected": ["AI leaders", "Equal-weight market", "Rotation sleeves"], "source": "Fundstrat Gmail full-body read: Mark Newton webinar notice", "summary": "Fundstrat noted narrow semiconductor/AI leadership, oil swings, and a potential breadth shift as a rotation risk to monitor rather than an all-clear tape read.", "trigger": "Mag 7/AI leadership weakens while equal-weight participation improves, or oil swings disrupt growth leadership.", "direction": "risk_watch"}], "holdings": [{"cat": "AI / Semiconductors", "rot": {"w": "LEADING"}, "pos": [{"t": "MAGS", "n": "MAGS", "pct": 8.957227459423684, "st": "Owned", "cv": "Promising", "ty": "Core", "own": null, "lock": "", "fresh": false, "cd": "up", "cdNote": "06-04 uw_opportunity sweep · 06-04 uw_opportunity dark_pool_accum", "nr": "Core hold — Lee-endorsed, leading; ride it.", "dr": [["Lee · ai_complex, long_duration_growth, global_exporter"]], "be": "—"}, {"t": "SMH", "n": "SMH", "pct": 8.883447610583922, "st": "Owned", "cv": "Promising", "ty": "Core", "own": null, "lock": "", "fresh": false, "cd": "down", "cdNote": "06-04 uw_opportunity sweep · 06-04 uw_opportunity oi_build", "nr": "Core hold — Lee-endorsed, leading; ride it.", "dr": [["Lee · ai_complex, semiconductors, long_duration_growth"]], "be": "—"}, {"t": "NVDA", "n": "NVDA", "pct": 6.559850650438569, "st": "Owned", "cv": "Promising", "ty": "Core", "own": null, "lock": "", "fresh": false, "cd": "up", "cdNote": "06-04 uw_opportunity sweep · 06-04 uw_opportunity oi_build · 06-04 uw_opportunity dark_pool_accum", "nr": "Core hold — Lee-endorsed, leading; ride it.", "dr": [["Lee · ai_complex, semiconductors, long_duration_growth, global_exporter"]], "be": "—"}, {"t": "IVES", "n": "IVES", "pct": 3.875627362854291, "st": "Owned", "cv": "Promising", "ty": "Tactical", "own": null, "lock": "", "fresh": false, "cd": "up", "cdNote": "06-04 uw_opportunity sweep · 06-04 uw_opportunity oi_build", "nr": "Core hold — operator-endorsed, leading; ride it.", "dr": [["operator · ai_complex"]], "be": "—"}, {"t": "MU", "n": "MU", "pct": 3.2829431187543383, "st": "Owned", "cv": "Promising", "ty": "Tactical", "own": null, "lock": "", "fresh": false, "cd": "down", "cdNote": "06-04 uw_opportunity oi_build · 06-04 uw_opportunity dark_pool_accum", "nr": "Core hold — Lee-endorsed, leading; ride it.", "dr": [["Lee · ai_complex, semiconductors"]], "be": "—"}]}, {"cat": "Quality core", "rot": {"w": "IN LINE"}, "pos": [{"t": "GRNY", "n": "GRNY", "pct": 8.723140336764947, "st": "Owned", "cv": "Promising", "ty": "Core", "own": null, "lock": "", "fresh": false, "cd": "up", "cdNote": "06-04 uw_opportunity sweep · 06-04 uw_opportunity oi_build · 06-04 uw_opportunity dark_pool_accum", "nr": "Core hold — Lee-endorsed, leading; ride it.", "dr": [["Lee · ai_complex"]], "be": "—"}, {"t": "GRNJ", "n": "GRNJ", "pct": 7.27844972824249, "st": "Owned", "cv": "Promising", "ty": "Core", "own": null, "lock": "", "fresh": false, "cd": "down", "cdNote": "06-04 uw_opportunity dark_pool_accum", "nr": "Core hold — Lee-endorsed, leading; ride it.", "dr": [["Lee · ai_complex"]], "be": "—"}]}, {"cat": "Software", "rot": {"w": "IN LINE"}, "pos": [{"t": "IGV", "n": "IGV", "pct": 5.104545733620405, "st": "Owned", "cv": "Promising", "ty": "Tactical", "own": null, "lock": "", "fresh": false, "cd": "up", "cdNote": "06-04 uw_opportunity sweep · 06-04 uw_opportunity dark_pool_accum", "nr": "Core hold — Lee-endorsed, leading; ride it.", "dr": [["Lee · software, ai_complex"]], "be": "—"}]}, {"cat": "Nuclear", "rot": {"w": "LAGGING"}, "pos": [{"t": "LEU", "n": "LEU", "pct": 4.846316262681237, "st": "Owned", "cv": "Promising", "ty": "Core", "own": null, "lock": "🔒", "fresh": false, "cd": "down", "cdNote": "06-04 uw_opportunity oi_build · 06-04 uw_opportunity dark_pool_accum", "nr": "Hold light — burned sleeve; watch for YOUR re-entry trigger, no add on a source call.", "dr": [["Meridian · critical_minerals, nuclear, uranium"]], "be": "—"}, {"t": "UUUU", "n": "UUUU", "pct": 2.1223413499110793, "st": "Owned", "cv": "Promising", "ty": "Tactical", "own": null, "lock": "", "fresh": false, "cd": "up", "cdNote": "06-04 uw_opportunity sweep · 06-04 uw_opportunity oi_build", "nr": "Hold light — burned sleeve; watch for YOUR re-entry trigger, no add on a source call.", "dr": [["Meridian · critical_minerals, uranium"]], "be": "—"}]}, {"cat": "Electrification", "rot": {"w": "TURNING DOWN"}, "pos": [{"t": "VOLT", "n": "VOLT", "pct": 4.009711051472111, "st": "Owned", "cv": "Promising", "ty": "Tactical", "own": null, "lock": "", "fresh": false, "cd": "up", "cdNote": "06-04 uw_opportunity call_flow · 06-04 uw_opportunity oi_build · 06-04 uw_opportunity dark_pool_accum", "nr": "Core hold — operator-endorsed, leading; ride it.", "dr": [["operator · nuclear, ai_complex"]], "be": "—"}]}, {"cat": "Financials", "rot": {"w": "LAGGING"}, "pos": [{"t": "XLF", "n": "XLF", "pct": 3.9177203795759894, "st": "Owned", "cv": "Promising", "ty": "Tactical", "own": null, "lock": "", "fresh": false, "cd": "up", "cdNote": "06-04 uw_opportunity sweep · 06-04 uw_opportunity oi_build · 06-04 uw_opportunity dark_pool_accum", "nr": "Catch-up — Lee-endorsed laggard; favorable entry, no rush.", "dr": [["Lee · financials, cyclicals"]], "be": "—"}]}, {"cat": "Crypto", "rot": {"w": "LAGGING"}, "pos": [{"t": "BMNR", "n": "BMNR", "pct": 3.4988714492797364, "st": "Owned", "cv": "Promising", "ty": "Core", "own": null, "lock": "🔒", "fresh": false, "cd": "up", "cdNote": "06-04 uw_opportunity sweep · 06-04 uw_opportunity oi_build · 06-04 uw_opportunity dark_pool_accum", "nr": "Hold light — burned sleeve; watch for YOUR re-entry trigger, no add on a source call.", "dr": [["operator · crypto, eth"]], "be": "—"}]}, {"cat": "Critical minerals", "rot": {"w": "LAGGING"}, "pos": [{"t": "MP", "n": "MP", "pct": 0.9761521467438528, "st": "Owned", "cv": "Promising", "ty": "Tactical", "own": null, "lock": "", "fresh": false, "cd": "up", "cdNote": "06-04 uw_opportunity sweep · 06-04 uw_opportunity dark_pool_accum", "nr": "Hold light — burned sleeve; watch for YOUR re-entry trigger, no add on a source call.", "dr": [["Meridian · critical_minerals, rare_earth"]], "be": "—"}]}], "rotation": [{"subject": "SMH", "label": "LEADING", "rel_1m": 0.1545410559549189, "rel_3m": 0.4760501951268684, "abs_3m": 0.5872770962438344, "rel_3m_vs_smh": 0.0, "note": "LEADING +48%/3M vs mkt"}, {"subject": "IGV", "label": "IN LINE", "rel_1m": 0.08753073909060555, "rel_3m": 0.03074981652740741, "abs_3m": 0.1419767176443734, "rel_3m_vs_smh": -0.44530037859946103, "note": "IN LINE +3%/3M vs mkt"}, {"subject": "GRNY", "label": "IN LINE", "rel_1m": -0.008279715027970765, "rel_3m": 0.007676766758890646, "abs_3m": 0.11890366787585663, "rel_3m_vs_smh": -0.4683734283679778, "note": "IN LINE +1%/3M vs mkt"}, {"subject": "IBIT", "label": "LAGGING", "rel_1m": -0.26773076067454304, "rel_3m": -0.2194219989134502, "abs_3m": -0.10819509779648422, "rel_3m_vs_smh": -0.6954721940403186, "note": "LAGGING -22%/3M vs mkt"}, {"subject": "URA", "label": "LAGGING", "rel_1m": -0.11836144762099772, "rel_3m": -0.1068321747885601, "abs_3m": 0.00439472632840589, "rel_3m_vs_smh": -0.5828823699154285, "note": "LAGGING -11%/3M vs mkt"}, {"subject": "REMX", "label": "LAGGING", "rel_1m": -0.11181732728236579, "rel_3m": -0.07268300390069196, "abs_3m": 0.03854389721627403, "rel_3m_vs_smh": -0.5487331990275603, "note": "LAGGING -7%/3M vs mkt"}, {"subject": "XLF", "label": "LAGGING", "rel_1m": -0.0344065634898731, "rel_3m": -0.09248788101155897, "abs_3m": 0.018739020105407005, "rel_3m_vs_smh": -0.5685380761384274, "note": "LAGGING -9%/3M vs mkt"}, {"subject": "GDX", "label": "LAGGING", "rel_1m": -0.03916106885576028, "rel_3m": -0.26267062533617624, "abs_3m": -0.15144372421921026, "rel_3m_vs_smh": -0.7387208204630447, "note": "LAGGING -26%/3M vs mkt"}, {"subject": "VOLT", "label": "TURNING DOWN", "rel_1m": -0.07909457561343462, "rel_3m": 0.05568421651283739, "abs_3m": 0.16691111762980337, "rel_3m_vs_smh": -0.420365978614031, "note": "TURNING DOWN +6%/3M vs mkt"}], "macro": {"line": "10Y 4.47% · 2s10s +42bp · 10s30s +50bp · USD (UUP) 27.84 · VIX 16.06 · 30Y 4.97% · 2Y 4.05%", "regime": {"duration": "flat", "vol": "calm", "dollar": "neutral", "label": "duration_flat · vol_calm · dollar_neutral"}, "alerts": [], "implications": []}, "catalysts": [{"ticker": "GS", "label": "Q2 FY26 earnings", "date": "2026-07-15", "days_out": 40, "source": "Notion Catalyst Calendar page 35fc5031-4bb6-81c5-ae90-d8a84919999b"}, {"ticker": "GEV", "label": "Q2 2026 earnings", "date": "2026-07-22", "days_out": 47, "source": "Notion Catalyst Calendar page 35fc5031-4bb6-81c5-ae90-d8a84919999b"}, {"ticker": "INTC", "label": "Q2 2026 earnings", "date": "2026-07-23", "days_out": 48, "source": "Notion Catalyst Calendar page 35fc5031-4bb6-81c5-ae90-d8a84919999b"}, {"ticker": "LEU", "label": "Q2 FY26 earnings", "date": "2026-08-04", "days_out": 60, "source": "Notion Catalyst Calendar page 35fc5031-4bb6-81c5-ae90-d8a84919999b"}, {"ticker": "IONQ", "label": "Q2 FY26 earnings", "date": "2026-08-05", "days_out": 61, "source": "Notion Catalyst Calendar page 35fc5031-4bb6-81c5-ae90-d8a84919999b"}, {"ticker": "UUUU", "label": "Q2 FY26 earnings", "date": "2026-08-05", "days_out": 61, "source": "Notion Catalyst Calendar page 35fc5031-4bb6-81c5-ae90-d8a84919999b"}, {"ticker": "MP", "label": "Q2 FY26 earnings", "date": "2026-08-06", "days_out": 62, "source": "Notion Catalyst Calendar page 35fc5031-4bb6-81c5-ae90-d8a84919999b"}, {"ticker": "BMNR", "label": "Q1 FY27 earnings premarket", "date": "2026-11-21", "days_out": 169, "source": "Notion Catalyst Calendar page 35fc5031-4bb6-81c5-ae90-d8a84919999b"}], "questions": [], "research": {"generated_at": "2026-06-05T18:00:00Z", "source": "research_queue_intake", "pending": [{"r": "AVGO - write the AI-networking and custom-ASIC thesis line when evidence is available; timing catalyst passed", "pr": "low", "status": "Queued", "ticker": "AVGO", "source": "user update 2026-06-05: important AVGO date passed"}], "done": [], "summary": {"input_rows": 1, "pending": 1, "done": 0, "skipped": 0}}, "research_actions": [], "heartbeat": [{"layer": "Required Inputs", "status": "ok", "last_run": "2026-06-05T19:06:05.469821+00:00", "note": "positions/theses convention inputs present and fresh"}, {"layer": "Minimum Market Data", "status": "ok", "last_run": "2026-06-05T19:06:05.469821+00:00", "note": "UW price and macro caches present"}, {"layer": "Publish Gate", "status": "ok", "last_run": "2026-06-05T19:06:05.469821+00:00", "note": "publish-gate checks passed"}, {"layer": "Optional Source Lanes", "status": "stale", "last_run": "2026-06-05T19:06:05.469821+00:00", "note": "dark lanes: account_positions, meridian | next: Supply src\\account_positions.json through the owning source routine or manual live-source drop; Supply src\\meridian_items.json through the owning source routine or manual live-source drop"}, {"layer": "Daily Full Build", "status": "ok", "last_run": "2026-06-05T19:06:05.469821+00:00", "note": "rehearsal build can run"}], "synthesis": {"source": "Repo Evidence Synthesis", "date": "2026-06-05", "state_of_play": "Repo evidence read: 13 lane(s) have data and 2 optional lane(s) are not checked. Top action is Event risk: Middle East oil/rates shock can affect new-buy timing (act_now, moderate confidence, source event_risk). Primary event-risk watch is Middle East oil/rates shock can affect new-buy timing; trigger evidence: WTI approaches 99-101, 10Y yield approaches roughly 4.55-4.59, or Strait/ceasefire headlines change abruptly.", "delta": "Fundstrat Daily compact calls in radar: RYF avoid, TNX watch, XOP avoid. Target drift: 12 sizing gap(s) vs AI working model (1 under, 2 over, 9 missing); GRNY oversized 8.7% vs 3.0%; SMH oversized 8.9% vs 5.0%; NVDA undersized 6.6% vs 12.0%; GOOGL missing vs 8.0% target; AVGO missing vs 6.0% target; MSFT missing vs 5.0% target; +6 more", "hanging": ["Operator review still required: Review exposure, hedges, and new buys before acting today: Middle East oil/rates shock can affect new-buy timing (oil, rates, volatility, energy, growth). If the event changes oil/rates/vol or a held sleeve, decide whether to hold, hedge, trim, or wait.", "Account Positions is not checked: Account views are not checked; do not imply no account-level breakdown.", "Meridian is not checked: Meridian source is not checked; missing data is not a no-signal read."], "notes": ["Derived only from the existing cockpit feed.", "No standalone market fetch or autonomous trade recommendation was generated."]}, "radar": [{"ticker": "RYF", "author": "Newton", "direction": "avoid", "entry": null, "stop": null, "target": null, "window": null, "date": "2026-06-03", "quote": "Break below 74.40 keeps the path of least resistance lower toward 71."}, {"ticker": "TNX", "author": "Newton", "direction": "watch", "entry": null, "stop": null, "target": null, "window": null, "date": "2026-06-03", "quote": "Corrective bounce toward 4.554-4.586% should precede a turn lower if the ceasefire path holds."}, {"ticker": "XOP", "author": "Newton", "direction": "avoid", "entry": null, "stop": null, "target": null, "window": null, "date": "2026-06-03", "quote": "Bounce only; resistance near 175.72 should repel price toward 162."}], "lean_in": [{"ticker": "ANET", "owned": false, "stance_gate": "open", "conviction": "Promising", "cd": "flat", "rotation": "LEADING", "lean": "lean_in", "headline": "ANET: Promising and the tape's with it (LEADING) — a place to start.", "evidence": ["Conviction: external pick, no thesis on file — moderate, give me a line", "Rotation: LEADING"], "next_evidence": "Size toward the ceiling on conviction; if via options, a defined-risk structure. Raises it further: a 2nd independent source or a held rotation turn.", "opportunity_cost": "This IS the SMH opportunity-cost benchmark.", "ceiling": "Tactical — catalyst/cycle — medium, with a defined exit.", "caveats": ["clustered: 1 independent source — not independent confirmation", "already moved: entry less asymmetric (sleeve leading)"], "freshness": "as-of 2026-06-05", "action": "NONE"}, {"ticker": "GOOGL", "owned": false, "stance_gate": "open", "conviction": "Promising", "cd": "flat", "rotation": "LEADING", "lean": "lean_in", "headline": "GOOGL: Promising and the tape's with it (LEADING) — a place to start.", "evidence": ["Conviction: external pick, no thesis on file — moderate, give me a line", "Rotation: LEADING"], "next_evidence": "Size toward the ceiling on conviction; if via options, a defined-risk structure. Raises it further: a 2nd independent source or a held rotation turn.", "opportunity_cost": "This IS the SMH opportunity-cost benchmark.", "ceiling": "Tactical — catalyst/cycle — medium, with a defined exit.", "caveats": ["clustered: 1 independent source — not independent confirmation", "already moved: entry less asymmetric (sleeve leading)"], "freshness": "as-of 2026-06-05", "action": "NONE"}, {"ticker": "GRNY", "owned": true, "stance_gate": "open", "conviction": "Promising", "cd": "up", "rotation": "IN LINE", "lean": "build", "headline": "GRNY: Promising, conviction building, tape not yet confirmed — hold, watch for the turn.", "evidence": ["Conviction: real named backing (Lee), not fully proven / single-source — moderate", "Direction: 06-04 uw_opportunity sweep · 06-04 uw_opportunity oi_build · 06-04 uw_opportunity dark_pool_accum", "Rotation: IN LINE", "UW ▲ ask-side call sweeps $1.6M, 16:1 c/p (1d)", "UW ▲ call OI +50% at 29/29/26 strikes (1d)", "UW ▲ dark-pool blocks $4M net buy, 1 sessions (1d)"], "next_evidence": "Graduates it: the sleeve rotation turning up and holding, or a fresh independent catalyst.", "opportunity_cost": "Still lagging SMH (-47%/3M) — leaning in trades the benchmark for this name; size only as the relative trend turns.", "ceiling": "Core — durable — can be a large position; conviction sizes toward the upper end.", "caveats": [], "freshness": "as-of 2026-06-05", "action": "NONE"}, {"ticker": "IGV", "owned": true, "stance_gate": "open", "conviction": "Promising", "cd": "up", "rotation": "IN LINE", "lean": "build", "headline": "IGV: Promising, conviction building, tape not yet confirmed — hold, watch for the turn.", "evidence": ["Conviction: real named backing (Lee), not fully proven / single-source — moderate", "Direction: 06-04 uw_opportunity sweep · 06-04 uw_opportunity dark_pool_accum", "Rotation: IN LINE", "UW ▲ ask-side call sweeps $1.4M, 2:1 c/p (1d)", "UW ▼ put OI +92975% at 93/98/99 strikes (1d)", "UW ▲ dark-pool blocks $34M net buy, 1 sessions (1d)"], "next_evidence": "Graduates it: the sleeve rotation turning up and holding, or a fresh independent catalyst.", "opportunity_cost": "Still lagging SMH (-45%/3M) — leaning in trades the benchmark for this name; size only as the relative trend turns.", "ceiling": "Tactical — catalyst/cycle — medium, with a defined exit.", "caveats": [], "freshness": "as-of 2026-06-05", "action": "NONE"}, {"ticker": "IVES", "owned": true, "stance_gate": "open", "conviction": "Promising", "cd": "up", "rotation": "LEADING", "lean": "build", "headline": "IVES: Promising, conviction building, tape not yet confirmed — hold, watch for the turn.", "evidence": ["Conviction: real named backing (operator), not fully proven / single-source — moderate", "Direction: 06-04 uw_opportunity sweep · 06-04 uw_opportunity oi_build", "Rotation: LEADING", "UW ▲ ask-side call sweeps $0.3M (1d)", "UW ▲ call OI +36% at 40/41 strikes (1d)", "UW ▼ dark-pool blocks $0M net sell, 1 sessions (1d)"], "next_evidence": "Graduates it: the sleeve rotation turning up and holding, or a fresh independent catalyst.", "opportunity_cost": "This IS the SMH opportunity-cost benchmark.", "ceiling": "Tactical — catalyst/cycle — medium, with a defined exit.", "caveats": ["already moved: entry less asymmetric (sleeve leading) — flow is confirming a move already underway, not front-running it"], "freshness": "as-of 2026-06-05", "action": "NONE"}, {"ticker": "MAGS", "owned": true, "stance_gate": "open", "conviction": "Promising", "cd": "up", "rotation": "LEADING", "lean": "build", "headline": "MAGS: Promising, conviction building, tape not yet confirmed — hold, watch for the turn.", "evidence": ["Conviction: real named backing (Lee), not fully proven / single-source — moderate", "Direction: 06-04 uw_opportunity sweep · 06-04 uw_opportunity dark_pool_accum", "Rotation: LEADING", "UW ▲ ask-side call sweeps $3.8M, 12:1 c/p (1d)", "UW ▼ put OI +1175% at 67.5/66/60 strikes (1d)", "UW ▲ dark-pool blocks $16M net buy, 1 sessions (1d)"], "next_evidence": "Graduates it: the sleeve rotation turning up and holding, or a fresh independent catalyst.", "opportunity_cost": "This IS the SMH opportunity-cost benchmark.", "ceiling": "Core — durable — can be a large position; conviction sizes toward the upper end.", "caveats": ["already moved: entry less asymmetric (sleeve leading) — flow is confirming a move already underway, not front-running it"], "freshness": "as-of 2026-06-05", "action": "NONE"}, {"ticker": "NVDA", "owned": true, "stance_gate": "open", "conviction": "Promising", "cd": "up", "rotation": "LEADING", "lean": "build", "headline": "NVDA: Promising, conviction building, tape not yet confirmed — hold, watch for the turn.", "evidence": ["Conviction: real named backing (Lee), not fully proven / single-source — moderate", "Direction: 06-04 uw_opportunity sweep · 06-04 uw_opportunity oi_build · 06-04 uw_opportunity dark_pool_accum", "Rotation: LEADING", "UW ▲ ask-side call sweeps $14.6M, 3:1 c/p (1d)", "UW ▲ call OI +23940% at 220/225/230 strikes (1d)", "UW ▲ dark-pool blocks $7M net buy, 1 sessions (1d)"], "next_evidence": "Graduates it: the sleeve rotation turning up and holding, or a fresh independent catalyst.", "opportunity_cost": "This IS the SMH opportunity-cost benchmark.", "ceiling": "Core — durable — can be a large position; conviction sizes toward the upper end.", "caveats": ["already moved: entry less asymmetric (sleeve leading) — flow is confirming a move already underway, not front-running it"], "freshness": "as-of 2026-06-05", "action": "NONE"}, {"ticker": "XLF", "owned": true, "stance_gate": "open", "conviction": "Promising", "cd": "up", "rotation": "LAGGING", "lean": "build", "headline": "XLF: Promising, conviction up but the sleeve's still lagging — research deeper / hold, watch for the rotation to turn.", "evidence": ["Conviction: real named backing (Lee), not fully proven / single-source — moderate", "Direction: 06-04 uw_opportunity sweep · 06-04 uw_opportunity oi_build · 06-04 uw_opportunity dark_pool_accum", "Rotation: LAGGING", "UW ▲ ask-side call sweeps $0.9M, 1:1 c/p (1d)", "UW ▲ call OI +3967% at 51.5/52/52 strikes (1d)", "UW ▲ dark-pool blocks $54M net buy, 1 sessions (1d)"], "next_evidence": "Graduates it: the sleeve rotation turning up and holding, or a fresh independent catalyst.", "opportunity_cost": "Still lagging SMH (-57%/3M) — leaning in trades the benchmark for this name; size only as the relative trend turns.", "ceiling": "Tactical — catalyst/cycle — medium, with a defined exit.", "caveats": [], "freshness": "as-of 2026-06-05", "action": "NONE"}, {"ticker": "GS", "owned": false, "stance_gate": "open", "conviction": "Promising", "cd": "flat", "rotation": "LAGGING", "lean": "still_lagging", "headline": "GS: Promising and endorsed, but still lagging — favorable entry only once the rotation turns (not owned).", "evidence": ["Conviction: external pick, no thesis on file — moderate, give me a line", "Rotation: LAGGING"], "next_evidence": "Clears it: the rotation turning up (lagging -> turning up), confirming the catch-up.", "opportunity_cost": "Still lagging SMH (-57%/3M) — leaning in trades the benchmark for this name; size only as the relative trend turns.", "ceiling": "Tactical — catalyst/cycle — medium, with a defined exit.", "caveats": [], "freshness": "as-of 2026-06-05", "action": "NONE"}, {"ticker": "GRNJ", "owned": true, "stance_gate": "open", "conviction": "Promising", "cd": "down", "rotation": "IN LINE", "lean": "cooling", "headline": "GRNJ: the case is cooling (IN LINE) — watch / reassess, don't add (you own it).", "evidence": ["Conviction: real named backing (Lee), not fully proven / single-source — moderate", "Direction: 06-04 uw_opportunity dark_pool_accum", "Rotation: IN LINE", "UW ▼ dark-pool blocks $0M net sell, 1 sessions (1d)"], "next_evidence": "Re-opens it: the direction turning back up on a fresh event, or the rotation re-leading.", "opportunity_cost": "Still lagging SMH (-47%/3M) — leaning in trades the benchmark for this name; size only as the relative trend turns.", "ceiling": "Core — durable — can be a large position; conviction sizes toward the upper end.", "caveats": [], "freshness": "as-of 2026-06-05", "action": "NONE"}, {"ticker": "MU", "owned": true, "stance_gate": "open", "conviction": "Promising", "cd": "down", "rotation": "LEADING", "lean": "cooling", "headline": "MU: the case is cooling (LEADING) — watch / reassess, don't add (you own it).", "evidence": ["Conviction: real named backing (Lee), not fully proven / single-source — moderate", "Direction: 06-04 uw_opportunity oi_build · 06-04 uw_opportunity dark_pool_accum", "Rotation: LEADING", "UW ▲ ask-side call sweeps $11.2M, 1:1 c/p (1d)", "UW ▼ put OI +1250% at 690/780/1070 strikes (1d)", "UW ▼ dark-pool blocks $31M net sell, 1 sessions (1d)"], "next_evidence": "Re-opens it: the direction turning back up on a fresh event, or the rotation re-leading.", "opportunity_cost": "This IS the SMH opportunity-cost benchmark.", "ceiling": "Tactical — catalyst/cycle — medium, with a defined exit.", "caveats": [], "freshness": "as-of 2026-06-05", "action": "NONE"}, {"ticker": "PWR", "owned": false, "stance_gate": "open", "conviction": "Promising", "cd": "flat", "rotation": "TURNING DOWN", "lean": "cooling", "headline": "PWR: the case is cooling (TURNING DOWN) — watch / reassess, don't add (not owned).", "evidence": ["Conviction: external pick, no thesis on file — moderate, give me a line", "Rotation: TURNING DOWN"], "next_evidence": "Re-opens it: the direction turning back up on a fresh event, or the rotation re-leading.", "opportunity_cost": "Still lagging SMH (-42%/3M) — leaning in trades the benchmark for this name; size only as the relative trend turns.", "ceiling": "Tactical — catalyst/cycle — medium, with a defined exit.", "caveats": [], "freshness": "as-of 2026-06-05", "action": "NONE"}, {"ticker": "SMH", "owned": true, "stance_gate": "open", "conviction": "Promising", "cd": "down", "rotation": "LEADING", "lean": "cooling", "headline": "SMH: the case is cooling (LEADING) — watch / reassess, don't add (you own it).", "evidence": ["Conviction: real named backing (Lee), not fully proven / single-source — moderate", "Direction: 06-04 uw_opportunity sweep · 06-04 uw_opportunity oi_build", "Rotation: LEADING", "UW ▼ ask-side put sweeps $8.2M, c/p 0.50 (1d)", "UW ▼ put OI +178100% at 440/270/435 strikes (1d)", "UW ▲ dark-pool blocks $48M net buy, 1 sessions (1d)"], "next_evidence": "Re-opens it: the direction turning back up on a fresh event, or the rotation re-leading.", "opportunity_cost": "This IS the SMH opportunity-cost benchmark.", "ceiling": "Core — durable — can be a large position; conviction sizes toward the upper end.", "caveats": [], "freshness": "as-of 2026-06-05", "action": "NONE"}, {"ticker": "VOLT", "owned": true, "stance_gate": "open", "conviction": "Promising", "cd": "up", "rotation": "TURNING DOWN", "lean": "cooling", "headline": "VOLT: the case is cooling (TURNING DOWN) — watch / reassess, don't add (you own it).", "evidence": ["Conviction: real named backing (operator), not fully proven / single-source — moderate", "Direction: 06-04 uw_opportunity call_flow · 06-04 uw_opportunity oi_build · 06-04 uw_opportunity dark_pool_accum", "Rotation: TURNING DOWN", "UW ▲ ask-side call flow $0.0M (1d)", "UW ▲ call OI +100% at 50/38/41 strikes (1d)", "UW ▲ dark-pool blocks $2M net buy, 1 sessions (1d)"], "next_evidence": "Re-opens it: the direction turning back up on a fresh event, or the rotation re-leading.", "opportunity_cost": "Still lagging SMH (-42%/3M) — leaning in trades the benchmark for this name; size only as the relative trend turns.", "ceiling": "Tactical — catalyst/cycle — medium, with a defined exit.", "caveats": [], "freshness": "as-of 2026-06-05", "action": "NONE"}], "bullish_flow": {"as_of": "2026-06-04", "count": 40, "tickers": 14, "rows": [{"ticker": "BMNR", "direction": "bullish", "strength": "strong", "signal_types": ["sweep", "oi_build", "dark_pool_accum"], "n": 3, "evidence": ["ask-side call sweeps $1.3M, 4:1 c/p", "call OI +2207% at 18/17.5/17 strikes", "dark-pool blocks $3M net buy, 1 sessions"], "parked": true}, {"ticker": "GRNY", "direction": "bullish", "strength": "strong", "signal_types": ["sweep", "oi_build", "dark_pool_accum"], "n": 3, "evidence": ["ask-side call sweeps $1.6M, 16:1 c/p", "call OI +50% at 29/29/26 strikes", "dark-pool blocks $4M net buy, 1 sessions"], "parked": false}, {"ticker": "IGV", "direction": "bullish", "strength": "strong", "signal_types": ["sweep", "oi_build", "dark_pool_accum"], "n": 3, "evidence": ["ask-side call sweeps $1.4M, 2:1 c/p", "put OI +92975% at 93/98/99 strikes", "dark-pool blocks $34M net buy, 1 sessions"], "parked": false}, {"ticker": "IVES", "direction": "bullish", "strength": "strong", "signal_types": ["sweep", "oi_build", "dark_pool_accum"], "n": 3, "evidence": ["ask-side call sweeps $0.3M", "call OI +36% at 40/41 strikes", "dark-pool blocks $0M net sell, 1 sessions"], "parked": false}, {"ticker": "LEU", "direction": "bullish", "strength": "strong", "signal_types": ["sweep", "oi_build", "dark_pool_accum"], "n": 3, "evidence": ["ask-side call sweeps $2.7M, 2:1 c/p", "put OI +145% at 120/140/170 strikes", "dark-pool blocks $4M net sell, 1 sessions"], "parked": true}, {"ticker": "MAGS", "direction": "bullish", "strength": "strong", "signal_types": ["sweep", "oi_build", "dark_pool_accum"], "n": 3, "evidence": ["ask-side call sweeps $3.8M, 12:1 c/p", "put OI +1175% at 67.5/66/60 strikes", "dark-pool blocks $16M net buy, 1 sessions"], "parked": false}, {"ticker": "MP", "direction": "bullish", "strength": "strong", "signal_types": ["sweep", "oi_build", "dark_pool_accum"], "n": 3, "evidence": ["ask-side call sweeps $2.2M, 3:1 c/p", "put OI +1500% at 55/58/60 strikes", "dark-pool blocks $0M net buy, 1 sessions"], "parked": true}, {"ticker": "MU", "direction": "bullish", "strength": "strong", "signal_types": ["sweep", "oi_build", "dark_pool_accum"], "n": 3, "evidence": ["ask-side call sweeps $11.2M, 1:1 c/p", "put OI +1250% at 690/780/1070 strikes", "dark-pool blocks $31M net sell, 1 sessions"], "parked": false}, {"ticker": "NVDA", "direction": "bullish", "strength": "strong", "signal_types": ["sweep", "oi_build", "dark_pool_accum"], "n": 3, "evidence": ["ask-side call sweeps $14.6M, 3:1 c/p", "call OI +23940% at 220/225/230 strikes", "dark-pool blocks $7M net buy, 1 sessions"], "parked": false}, {"ticker": "UUUU", "direction": "bullish", "strength": "strong", "signal_types": ["sweep", "oi_build", "dark_pool_accum"], "n": 3, "evidence": ["ask-side call sweeps $2.6M, 4:1 c/p", "call OI +2000% at 21/19/20 strikes", "dark-pool blocks $0M net sell, 1 sessions"], "parked": true}, {"ticker": "VOLT", "direction": "bullish", "strength": "strong", "signal_types": ["call_flow", "oi_build", "dark_pool_accum"], "n": 3, "evidence": ["ask-side call flow $0.0M", "call OI +100% at 50/38/41 strikes", "dark-pool blocks $2M net buy, 1 sessions"], "parked": false}, {"ticker": "XLF", "direction": "bullish", "strength": "strong", "signal_types": ["sweep", "oi_build", "dark_pool_accum"], "n": 3, "evidence": ["ask-side call sweeps $0.9M, 1:1 c/p", "call OI +3967% at 51.5/52/52 strikes", "dark-pool blocks $54M net buy, 1 sessions"], "parked": false}, {"ticker": "SMH", "direction": "bearish", "strength": "strong", "signal_types": ["sweep", "oi_build", "dark_pool_accum"], "n": 3, "evidence": ["ask-side put sweeps $8.2M, c/p 0.50", "put OI +178100% at 440/270/435 strikes", "dark-pool blocks $48M net buy, 1 sessions"], "parked": false}, {"ticker": "GRNJ", "direction": "bearish", "strength": "weak", "signal_types": ["dark_pool_accum"], "n": 1, "evidence": ["dark-pool blocks $0M net sell, 1 sessions"], "parked": false}]}, "prospects": {"hot": [], "movers_best": [], "movers_worst": [], "sell_fast": [{"ticker": "DE", "direction": "avoid", "conviction": "BUILDING", "urgency": "QUIET", "conviction_score": 10.0, "urgency_score": 6.0, "pct_since_add": null, "pct_vs_spy": null, "sources": ["FS-Monthly"], "corroboration": "Uncorroborated", "provenance": "FS Bottom 5 - 2026-05-28", "summary": "DE: SELL-PRESSURE BUILDING / urgency QUIET (1 independent avoid signal)."}, {"ticker": "HOOD", "direction": "avoid", "conviction": "BUILDING", "urgency": "QUIET", "conviction_score": 10.0, "urgency_score": 6.0, "pct_since_add": null, "pct_vs_spy": null, "sources": ["FS-Monthly"], "corroboration": "Uncorroborated", "provenance": "FS Bottom 5 - 2026-05-28", "summary": "HOOD: SELL-PRESSURE BUILDING / urgency QUIET (1 independent avoid signal)."}, {"ticker": "PKG", "direction": "avoid", "conviction": "BUILDING", "urgency": "QUIET", "conviction_score": 10.0, "urgency_score": 6.0, "pct_since_add": null, "pct_vs_spy": null, "sources": ["FS-Monthly"], "corroboration": "Uncorroborated", "provenance": "FS Bottom 5 - 2026-05-28", "summary": "PKG: SELL-PRESSURE BUILDING / urgency QUIET (1 independent avoid signal)."}, {"ticker": "SATS", "direction": "avoid", "conviction": "BUILDING", "urgency": "QUIET", "conviction_score": 10.0, "urgency_score": 6.0, "pct_since_add": null, "pct_vs_spy": null, "sources": ["FS-Monthly"], "corroboration": "Uncorroborated", "provenance": "FS Bottom 5 - 2026-05-28", "summary": "SATS: SELL-PRESSURE BUILDING / urgency QUIET (1 independent avoid signal)."}, {"ticker": "TPL", "direction": "avoid", "conviction": "BUILDING", "urgency": "QUIET", "conviction_score": 10.0, "urgency_score": 6.0, "pct_since_add": null, "pct_vs_spy": null, "sources": ["FS-Monthly"], "corroboration": "Uncorroborated", "provenance": "FS Bottom 5 - 2026-05-28", "summary": "TPL: SELL-PRESSURE BUILDING / urgency QUIET (1 independent avoid signal)."}], "counts": {"total": 10, "long": 5, "avoid": 5, "act_now": 0, "hot": 0, "uncorroborated": 10}}, "feedback": {"source_calls": {"status": "has_data", "line": "SCORING LAG: clean — no calls past window-end awaiting a score.", "pending_count": 3, "overdue_count": 0, "oldest_overdue_days": 0, "rates": [{"source": "newton", "n": 0, "wins": 0, "losses": 0, "pushes": 0, "hit_rate": null, "tier_band": "NO_DATA", "discount_factor": 1.0}], "due": [], "calibration": {"status": "checked_fresh", "line": "Calibration chain checked fresh.", "worst_days_behind": 0, "cache_as_of": "2026-06-03"}, "persistence": {"status": "checked_clear", "line": "Source persistence checked: no repeated-call clusters.", "cluster_count": 0, "loud_count": 0, "provisional_count": 0, "guarded": false, "clusters": []}}, "open_actions": {"status": "has_data", "line": "Open action backlog: 2 open; oldest 0 trading day(s).", "count": 2, "oldest_age_days": 0, "items": [{"ticker": "ANET", "kind": "lean_in", "source": "lean_in", "first_flagged": "2026-06-05", "age_days": 0, "move_since": ""}, {"ticker": "GOOGL", "kind": "lean_in", "source": "lean_in", "first_flagged": "2026-06-05", "age_days": 0, "move_since": ""}], "recent_history": []}, "recommendations": ["Resolve oldest open action: act, invalidate, or keep watching explicitly."]}, "target_drift": {"status": "has_data", "line": "Target drift: 12 sizing gap(s) vs AI working model (1 under, 2 over, 9 missing); GRNY oversized 8.7% vs 3.0%; SMH oversized 8.9% vs 5.0%; NVDA undersized 6.6% vs 12.0%; GOOGL missing vs 8.0% target; AVGO missing vs 6.0% target; MSFT missing vs 5.0% target; +6 more", "actionable_count": 12, "undersized_count": 1, "oversized_count": 2, "missing_count": 9, "alarm_count": 3, "rows": [{"ticker": "GRNY", "direction": "OVERSIZED", "actual_pct": 8.7231, "target_pct": 3.0, "drift_relative": 1.907713, "drift_absolute_pct": 5.7231, "flags": ["CONCENTRATION_CHECK", "ALARM_DRIFT"], "source": "reallocate_config"}, {"ticker": "SMH", "direction": "OVERSIZED", "actual_pct": 8.8834, "target_pct": 5.0, "drift_relative": 0.77669, "drift_absolute_pct": 3.8834, "flags": ["CONCENTRATION_CHECK", "ALARM_DRIFT"], "source": "reallocate_config"}, {"ticker": "NVDA", "direction": "UNDERSIZED", "actual_pct": 6.5599, "target_pct": 12.0, "drift_relative": -0.453346, "drift_absolute_pct": -5.4401, "flags": ["P_UNDERSIZE_CANDIDATE", "ALARM_DRIFT"], "source": "reallocate_config"}, {"ticker": "GOOGL", "direction": "MISSING", "actual_pct": 0.0, "target_pct": 8.0, "drift_relative": -1.0, "drift_absolute_pct": -8.0, "flags": ["P_UNDERSIZE_CANDIDATE", "MISSING_TARGET"], "source": "reallocate_config"}, {"ticker": "AVGO", "direction": "MISSING", "actual_pct": 0.0, "target_pct": 6.0, "drift_relative": -1.0, "drift_absolute_pct": -6.0, "flags": ["P_UNDERSIZE_CANDIDATE", "MISSING_TARGET"], "source": "reallocate_config"}, {"ticker": "MSFT", "direction": "MISSING", "actual_pct": 0.0, "target_pct": 5.0, "drift_relative": -1.0, "drift_absolute_pct": -5.0, "flags": ["P_UNDERSIZE_CANDIDATE", "MISSING_TARGET"], "source": "reallocate_config"}]}};

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
function actionRow(a, opts={}){
  const m = ACTION_KIND_META[a.kind] || { icon:"•", label:a.kind, c:C.dim };
  const cf = CONF_META[a.confidence] || { c:C.dim, label:a.confidence };
  const st = ACTION_STATE_META[a.action_state] || null;
  const gi = GOAL_IMPACT_META[a.goal_impact] || null;
  return { rank:a.rank, kind:a.kind, icon:m.icon, kindLabel:m.label, c:m.c,
           ticker:a.ticker||"", what:a.what||"", confLabel:cf.label,
           confBadgeLabel:opts.confBadgeLabel||"conf", confColor:cf.c,
           actionState:a.action_state||"", stateLabel:st&&st.label||"", stateColor:st&&st.c||"",
           goalImpact:a.goal_impact||"", goalLabel:gi&&gi.label||"", goalColor:gi&&gi.c||"",
           goalScore:(typeof a.goal_score==="number"?a.goal_score:null),
           timeWindow:a.time_window||"", capitalEffect:a.capital_effect||"",
           actionLabel:a.action_label||"", goalWhy:a.why_it_moves_goal||"",
           goalChannels:a.goal_channels||[], missingEvidence:a.missing_evidence||[],
           yourMove:a.your_move||"", why:a.why||"", gatePreview:(a.gate&&a.gate.preview)||"",
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
function operatorStatus(feed){
  const counts = ((feed.lane_status||{}).counts)||{};
  const feedback = feed.feedback||{};
  const openActions = ((feedback.open_actions)||{}).count||0;
  const sourceCalls = feedback.source_calls||{};
  const sourceCallStatus = sourceCalls.status||"not_checked";
  const sourceCallObserved = sourceCalls.observed_count||0;
  const sourceCallPending = sourceCalls.pending_count||0;
  const sourceCallOverdue = sourceCalls.overdue_count||0;
  const sourceCallWarn = sourceCallStatus==="not_checked" && sourceCallObserved>0;
  const sourceCallFail = sourceCallOverdue>0;
  const actions = (feed.actions||[]).length;
  const eventRows = (feed.event_risk||[]).filter(r=>r&&r.title);
  const severityRank = {critical:0, high:1, medium:2, low:3};
  eventRows.sort((a,b)=>(severityRank[a.severity]??9)-(severityRank[b.severity]??9));
  const eventWatch = eventRows[0] || null;
  const dark = counts.not_checked||0;
  const stale = counts.stale||0;
  const failed = counts.failed||0;
  const status = (failed||sourceCallFail) ? "FAIL" : ((dark||stale||openActions||sourceCallWarn) ? "WARN" : "PASS");
  const statusColor = (failed||sourceCallFail) ? C.red : (status==="WARN" ? C.amber : C.green);
  const sourceLane = failed ? `${failed} failed` : dark ? `${dark} dark` : stale ? `${stale} stale` : "clear";
  const sourceCall = sourceCallFail ? `${sourceCallOverdue} overdue` : sourceCallWarn ? `${sourceCallObserved} unscored` : sourceCallPending ? `${sourceCallPending} pending` : "clear";
  return {
    status, statusColor, actions, openActions, sourceLane, sourceCall, sourceCallWarn, sourceCallFail,
    eventWatch,
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
    darkLaneCount: (((feed.lane_status||{}).counts||{}).not_checked)||0,
    staleLaneCount: ((((feed.lane_status||{}).counts||{}).stale)||0) + ((((feed.lane_status||{}).counts||{}).failed)||0),
    operatorStatus: operatorStatus(feed),
  };
}
// actionVM = the ⚡ Action surface (decide/do). Built only when mode==="action".
function actionVM(feed){
  const actions = (feed.actions||[]).map(actionRow);
  const isOpp = (a)=>["upside","sizing_gap","leverage","opportunity_cost"].some(c=>(a.goalChannels||[]).includes(c));
  const isRisk = (a)=>["downside_protection","data_quality"].some(c=>(a.goalChannels||[]).includes(c));
  return {
    macro: macroView(feed.macro||{}),
    rotation: (feed.rotation||[]).map(rotationRow),
    actions,
    actionSplit: {
      actNow: actions.filter(a=>a.actionState==="ACT_NOW"),
      opportunities: actions.filter(a=>a.actionState!=="ACT_NOW" && isOpp(a)),
      risks: actions.filter(a=>isRisk(a)),
    },
    researchActions: (feed.research_actions||[]).map(a=>actionRow(a, { confBadgeLabel:"priority" })),
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

function ActionCard({ a, keyPrefix, posOpen, setPosOpen, stamp, footerLabel, showAging=false, showSizing=false }) {
  const key = keyPrefix + a.rank + (a.ticker || a.kind), isO = posOpen[key];
  const urgent = a.actionState === "ACT_NOW";
  const highGoal = a.goalImpact === "High";
  const edge = urgent ? C.red : (highGoal ? (a.goalColor || a.c) : a.c);
  return (
    <div key={key} style={{ ...card, marginBottom:8,
      borderColor: urgent ? edge+"aa" : edge+"44",
      background: urgent ? edge+"18" : (highGoal ? edge+"10" : a.c+"0a"),
      boxShadow: urgent ? `0 0 0 1px ${edge}55 inset` : "none" }}>
      <div onClick={()=>setPosOpen(st=>({...st,[key]:!st[key]}))} style={{ cursor:a.why?"pointer":"default" }}>
        <div style={{ display:"flex", alignItems:"baseline", gap:8, flexWrap:"wrap" }}>
          <span style={{ fontFamily:mono, fontSize:11, color:C.faint }}>#{a.rank}</span>
          {a.ticker && <span style={{ fontFamily:mono, fontWeight:700, fontSize:13.5, color:C.text }}>{a.ticker}</span>}
          <span style={{ fontSize:12.5, fontWeight:600, color:C.text }}>{a.what}</span>
        </div>
        <div style={{ marginTop:7, display:"flex", alignItems:"center", gap:7, flexWrap:"wrap" }}>
          {a.stateLabel && <span style={{ fontFamily:mono, fontSize:11, fontWeight:urgent?800:600, color:a.stateColor, border:`1px solid ${a.stateColor}${urgent?"bb":"66"}`, borderRadius:99, padding:"1px 8px", background:`${a.stateColor}${urgent?"22":"12"}` }}>{a.stateLabel}</span>}
          {a.goalLabel && <span title={a.goalScore!=null?`goal score ${a.goalScore}/100`:""} style={{ fontFamily:mono, fontSize:11, color:a.goalColor, border:`1px solid ${a.goalColor}66`, borderRadius:99, padding:"1px 8px", background:`${a.goalColor}10` }}>{a.goalLabel}</span>}
          {a.actionLabel && <span style={{ fontFamily:mono, fontSize:11, fontWeight:700, color:urgent?C.text:C.dim, border:`1px solid ${(urgent?a.stateColor:C.line)}${urgent?"aa":""}`, borderRadius:99, padding:"1px 8px", background:urgent?`${a.stateColor}20`:C.panel2 }}>{a.actionLabel}</span>}
          {a.timeWindow && <span style={{ fontFamily:mono, fontSize:11, color:C.faint }}>{a.timeWindow}</span>}
          <span style={{ fontFamily:mono, fontSize:11, color:a.c, border:`1px solid ${a.c}55`, borderRadius:99, padding:"1px 8px" }}>{a.icon} {a.kindLabel}</span>
          <span style={{ fontFamily:mono, fontSize:11, color:a.confColor, border:`1px solid ${a.confColor}55`, borderRadius:99, padding:"1px 8px" }}>{a.confBadgeLabel}: {a.confLabel}</span>
          {a.gatePreview && <span style={{ fontFamily:mono, fontSize:11, color:C.dim, border:`1px solid ${C.line}`, borderRadius:99, padding:"1px 8px", background:C.panel2 }}>{a.gatePreview}</span>}
          {showAging && a.ageDays!=null && <span title="how long this has been actionable — the cost of waiting" style={{ fontFamily:mono, fontSize:11, color:C.amber, border:`1px solid ${C.amber}55`, borderRadius:99, padding:"1px 8px" }}>🕒 open {a.ageDays}d{a.flagged?` · since ${a.flagged}`:""}{a.moveSince?` · ${a.moveSince}`:""}</span>}
        </div>
        <div style={{ marginTop:8, fontSize:12.5, color:C.text }}><span style={{ color:C.dim, fontWeight:600 }}>Your move:</span> {a.yourMove}</div>
        {a.goalWhy && <div style={{ marginTop:5, fontSize:12.2, color:a.goalColor }}><span style={{ color:C.dim, fontWeight:600 }}>Goal impact:</span> {a.goalWhy}</div>}
        {showSizing && a.sizing && <div style={{ marginTop:5, fontSize:12, color:C.dim }}><span style={{ fontFamily:mono, fontSize:10, color:C.faint, textTransform:"uppercase", letterSpacing:0.5 }}>Size </span>{a.sizing}</div>}
        {a.why && (
          <div style={{ marginTop:7, display:"flex", justifyContent:"flex-end" }}>
            <span style={{ fontSize:11, color:a.c }}>{isO?"hide why ▲":"why ▾"}</span>
          </div>
        )}
      </div>
      {isO && a.why && (
        <div style={{ marginTop:8, paddingTop:8, borderTop:`1px solid ${C.line}`, ...muted }}>
          {a.why}
          {(a.goalChannels.length>0 || a.capitalEffect) && <div style={{ marginTop:8, fontFamily:mono, fontSize:10, color:C.faint }}>channels: {a.goalChannels.join(" / ") || "n/a"}{a.capitalEffect?` · capital: ${a.capitalEffect}`:""}{a.goalScore!=null?` · score: ${a.goalScore}/100`:""}</div>}
          {a.missingEvidence.length>0 && <div style={{ marginTop:5, fontFamily:mono, fontSize:10, color:C.amber }}>missing: {a.missingEvidence.join(" / ")}</div>}
          <div style={{ marginTop:8, fontFamily:mono, fontSize:10, color:C.faint }}>{stamp} · {footerLabel} · drill in chat to run the gate</div>
        </div>
      )}
    </div>
  );
}

export default function ConvictionCockpit({ feed = FEED } = {}) {
  const [mode, setMode] = useState("action");   // "action" = decide/do · "book" = dig into holdings
  // Lazy + memoized view-model. shared is always built; each view's lanes are built ONLY when that
  // view is active, so on Action bookVM (the per-position map) is never called — holdings aren't
  // iterated at all. useMemo means toggling back and forth doesn't recompute either side.
  const shared = sharedVM(feed);
  const A = useMemo(() => mode === "action" ? actionVM(feed) : null, [mode, feed]);
  const B = useMemo(() => mode === "book"   ? bookVM(feed)   : null, [mode, feed]);
  const VM = { ...shared, ...(A || {}), ...(B || {}) };   // only the active view's lanes + shared
  const R = (VM.research && ((VM.research.pending||[]).length || (VM.research.done||[]).length))
    ? VM.research : CURATED.research;   // live Research Queue when present, else curated fallback
  const CATS = (VM.catalysts||[]).map(c=>({
    d: c.date||"",
    e: `${c.ticker?`${c.ticker} · `:""}${c.label||"Catalyst"}`,
    note: `${c.days_out!=null?`in ~${c.days_out}d · `:""}${c.source||"Catalyst Calendar"}`
  }));
  const [open, setOpen] = useState({});
  const [posOpen, setPosOpen] = useState({});
  const [collapsed, setCollapsed] = useState({});
  const [view, setView] = useState("agg");
  const [legend, setLegend] = useState(false);
  const dirColor = (d)=> d==="up"?C.green : d==="down"?C.red : C.dim;
  const ownerFilter = (own) => view==="agg" ? true : view==="parents" ? own.includes("p") : own.includes("s");
  const portfolioViewKey = view==="agg" ? "combined" : view;
  const portfolioView = VM.portfolioViews && VM.portfolioViews.views ? VM.portfolioViews.views[portfolioViewKey] : null;
  const effectiveExposure = portfolioView && portfolioView.effective_exposure ? portfolioView.effective_exposure : null;

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

        {/* VIEW TOGGLE — shared chrome (sticky): ⚡ Action ⇄ 📊 Book */}
        {VM.laneStatus.length>0 && (
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
            {[["action","⚡ Action"],["book","📊 Book"]].map(([k,l])=>(
              <button key={k} onClick={()=>setMode(k)} style={{ cursor:"pointer", border:"none", borderRadius:6, padding:"6px 14px", fontSize:12.5, fontWeight:600, fontFamily:sans, background: mode===k?C.panel3:"transparent", color: mode===k?C.text:C.faint }}>{l}</button>
            ))}
          </div>
        </div>

        {/* ⚡ ACTION VIEW ───────────────────────────────────────────── */}
        {mode==="action" && (<>

        {/* affordance — the full book lives in the Book tab (nothing actionable is Book-only) */}
        <div style={{ marginTop:12, display:"flex", alignItems:"center", gap:8, fontSize:11.5, color:C.faint, flexWrap:"wrap" }}>
          <span>📊 Full book + per-name detail →</span>
          <button onClick={()=>setMode("book")} style={{ cursor:"pointer", background:"transparent", border:`1px solid ${C.line}`, borderRadius:7, padding:"3px 9px", fontSize:11, fontFamily:mono, color:C.dim }}>open Book ▸</button>
        </div>

        {/* HERO — needs-you banner (engine ⑧) */}
        {(() => {
          const h = VM.hero;
          const need = h.needsCount > 0;
          const sleeves = h.leadingSleeves.map(s => SLEEVE_DISPLAY[s] || s).join(", ");
          return (
            <div style={{ marginTop:12, ...card, borderColor: need? C.amber+"66":C.green+"44", background: need? C.amber+"10":C.green+"0c", display:"flex", alignItems:"center", gap:12 }}>
              <div style={{ fontFamily:mono, fontSize:26, fontWeight:700, color: need?C.amber:C.green, lineHeight:1 }}>{need? h.needsCount : "✓"}</div>
              <div>
                <div style={{ fontSize:13.5, fontWeight:600 }}>{need ? `${h.needsCount} thing${h.needsCount>1?"s":""} need${h.needsCount>1?"":"s"} you` : "Nothing needs you — all quiet"}</div>
                <div style={muted}>{need ? "Time-sensitive items are in Today's actions below." : "No fresh actions."} <span style={{ color:C.faint }}>{h.leadCount} name{h.leadCount===1?"":"s"} on strong footing{sleeves?` · leading: ${sleeves}`:""}.</span></div>
              </div>
            </div>
          );
        })()}

        {/* ACTIONS — prioritized "what to do today" (engine ⑦b actions block) */}
        {(() => {
          const op = VM.operatorStatus;
          const items = [
            ["Today actions", String(op.actions), op.actions?C.amber:C.dim],
            ["Open reviews", String(op.openActions), op.openActions?C.amber:C.green],
            ["Source lanes", op.sourceLane, op.sourceLane==="clear"?C.green:C.amber],
            ["Source calls", op.sourceCall, op.sourceCallFail?C.red:op.sourceCallWarn?C.amber:C.green],
          ];
          return (
            <div style={{ marginTop:10, ...card, borderColor:op.statusColor+"55", background:op.statusColor+"0d" }}>
              <div style={{ display:"flex", alignItems:"baseline", justifyContent:"space-between", gap:10, flexWrap:"wrap", marginBottom:8 }}>
                <div style={{ fontSize:13.5, fontWeight:700, color:C.text }}>Operator status</div>
                <span style={{ fontFamily:mono, fontSize:11, fontWeight:800, color:op.statusColor, border:`1px solid ${op.statusColor}77`, borderRadius:99, padding:"1px 8px", background:`${op.statusColor}14` }}>{op.status}</span>
              </div>
              <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit, minmax(120px, 1fr))", gap:8 }}>
                {items.map(([label,value,color])=>(
                  <div key={label} style={{ border:`1px solid ${C.line}`, borderRadius:8, padding:"7px 8px", background:C.panel }}>
                    <div style={{ fontFamily:mono, fontSize:10, color:C.faint, textTransform:"uppercase", marginBottom:3 }}>{label}</div>
                    <div style={{ fontFamily:mono, fontSize:14, fontWeight:800, color }}>{value}</div>
                  </div>
                ))}
              </div>
              <div style={{ marginTop:8, fontFamily:mono, fontSize:10.5, color:C.faint }}>Verify: {op.command}</div>
              {op.eventWatch && (
                <div style={{ marginTop:6, border:`1px solid ${C.amber}44`, borderRadius:8, padding:"7px 8px", background:C.amber+"0a" }}>
                  <div style={{ fontFamily:mono, fontSize:10, color:C.amber, textTransform:"uppercase", marginBottom:3 }}>Active event watch</div>
                  <div style={{ fontSize:12.5, color:C.text, fontWeight:650 }}>{op.eventWatch.title}</div>
                  <div style={{ marginTop:4, fontFamily:mono, fontSize:10.5, color:C.faint }}>
                    {(op.eventWatch.severity||"watch").toUpperCase()} {op.eventWatch.channels&&op.eventWatch.channels.length?`| ${op.eventWatch.channels.join(", ")}`:""} {op.eventWatch.tickers&&op.eventWatch.tickers.length?`| ${op.eventWatch.tickers.join(", ")}`:""}
                  </div>
                  {(op.eventWatch.trigger||op.eventWatch.summary) && <div style={{ marginTop:4, fontSize:11.5, color:C.dim }}>Trigger: {op.eventWatch.trigger||op.eventWatch.summary}</div>}
                </div>
              )}
              <div style={{ marginTop:4, fontFamily:mono, fontSize:10.5, color:C.faint }}>Sudden event: {op.suddenEventCommand}</div>
            </div>
          );
        })()}

        <Section id="actions" title="Today's actions" icon="🟢" badge={VM.actions.length?`${Math.min(VM.actions.length,5)}${VM.actions.length>5?` of ${VM.actions.length}`:""}`:"0 live"} badgeColor={VM.actions.length?C.amber:C.faint} openMap={open} setOpen={setOpen}>
          <div style={{ fontSize:11, color:C.faint, fontFamily:mono, marginBottom:8 }}>PRIORITIZED — confidence-led. Gate badges are provisional; the real 🟢/🟡/🔴 runs when you act on it in chat.</div>
          <div style={{ fontSize:11, color:C.faint, fontFamily:mono, marginBottom:8 }}>
            ACT_NOW {VM.actionSplit.actNow.length} · OPPORTUNITIES {VM.actionSplit.opportunities.length} · RISKS {VM.actionSplit.risks.length}
          </div>
          {VM.actions.length===0 && <div style={{ ...card, fontSize:12, color:C.faint }}>Nothing to act on right now — no live buy-trigger, alert, or flag.</div>}
          {VM.actions.slice(0,5).map((a)=>(
            <ActionCard
              key={"act"+a.rank+(a.ticker||a.kind)}
              a={a}
              keyPrefix="act"
              posOpen={posOpen}
              setPosOpen={setPosOpen}
              stamp={VM.stamp}
              footerLabel="not a trade — you decide, you size"
              showAging={true}
              showSizing={true}
            />
          ))}
          {VM.actions.length>5 && <div style={{ fontSize:11.5, color:C.faint, fontFamily:mono, marginTop:2 }}>+{VM.actions.length-5} more lower-priority action{VM.actions.length-5>1?"s":""} (not shown)</div>}
        </Section>

        {/* TOP PROSPECTS — the conviction-stack watchlist (item 5): FS-sourced
            names ranked by conviction/urgency, with alpha-vs-SPY movers + a
            sell-fast strip. Candidate surface; not the held book. */}
        <Section id="target-drift" title="Target drift" icon="🎯" badge={VM.targetDrift.actionable_count?`${VM.targetDrift.actionable_count}`:"0"} badgeColor={VM.targetDrift.actionable_count?C.amber:C.faint} openMap={open} setOpen={setOpen} defaultOpen={!!VM.targetDrift.actionable_count}>
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

        <Section id="top-prospects" title="Top Prospects" icon="🎯" badge={(VM.prospects.counts&&VM.prospects.counts.total)?`${VM.prospects.counts.total}`:"0"} badgeColor={(VM.prospects.counts&&VM.prospects.counts.total)?C.accent:C.faint} openMap={open} setOpen={setOpen} defaultOpen={!!(VM.prospects.counts&&VM.prospects.counts.total)}>
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
                <div style={{ fontSize:11, color:C.faint, fontFamily:mono, marginBottom:8 }}>{ct.total} tracked · {ct.act_now||0} act-now · {ct.hot||0} hot · {ct.uncorroborated||0} uncorroborated · candidate surface, not the book</div>
                {(P.hot||[]).length>0 && <div style={{ fontFamily:mono, fontSize:10, color:C.faint, textTransform:"uppercase", letterSpacing:0.5, marginBottom:4 }}>Hot</div>}
                {(P.hot||[]).map(prow)}
                {((P.movers_best||[]).length>0 || (P.movers_worst||[]).length>0) && (
                  <div style={{ ...card, marginBottom:7, marginTop:2 }}>
                    <div style={{ fontFamily:mono, fontSize:10, color:C.faint, textTransform:"uppercase", letterSpacing:0.5, marginBottom:5 }}>Movers · vs SPY</div>
                    {(P.movers_best||[]).map((r,j)=>(<div key={"mb"+j} style={{ fontSize:12, color:C.text, marginBottom:2 }}><span style={{ fontFamily:mono, fontWeight:700 }}>{r.ticker}</span> <span style={{ color:pcol(r.pct_vs_spy), fontFamily:mono }}>{pctxt(r.pct_vs_spy)}</span></div>))}
                    {(P.movers_worst||[]).map((r,j)=>(<div key={"mw"+j} style={{ fontSize:12, color:C.dim, marginBottom:2 }}><span style={{ fontFamily:mono, fontWeight:700 }}>{r.ticker}</span> <span style={{ color:pcol(r.pct_vs_spy), fontFamily:mono }}>{pctxt(r.pct_vs_spy)}</span></div>))}
                  </div>
                )}
                {(P.sell_fast||[]).length>0 && (
                  <div style={{ ...card, marginBottom:7, borderColor:C.red+"44", background:C.red+"0a" }}>
                    <div style={{ fontFamily:mono, fontSize:10, color:C.red, textTransform:"uppercase", letterSpacing:0.5, marginBottom:5 }}>⚠️ Sell-fast — FS dropped a name you may hold</div>
                    {(P.sell_fast||[]).map((r,j)=>(<div key={"sf"+j} style={{ fontSize:12.5, color:C.text, marginBottom:2 }}><span style={{ fontFamily:mono, fontWeight:700 }}>{r.ticker}</span> <span style={{ color:C.dim }}>{r.summary||"avoid"}</span></div>))}
                  </div>
                )}
              </div>
            );
          })()}
        </Section>

        {/* FROM RESEARCH — ticker-specific Research-Queue items as their OWN
            candidate-action category (engine ⑦c research_actions), SEPARATE from
            Today's actions; deduped against the action+catalyst lanes
            (catalyst-precedence). Default-open when populated. */}
        <Section id="research-actions" title="From Research" icon="🔎" badge={VM.researchActions.length?`${VM.researchActions.length}`:"0"} badgeColor={VM.researchActions.length?C.blue:C.faint} openMap={open} setOpen={setOpen} defaultOpen={VM.researchActions.length>0}>
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
        <Section id="fresh-signals" title="Fresh signals" icon="📨" badge={VM.freshSignals.length?`${VM.freshSignals.length}`:"0"} badgeColor={VM.freshSignals.length?C.blue:C.faint} openMap={open} setOpen={setOpen} defaultOpen={VM.freshSignals.length>0}>
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

        {/* SIGNAL LOG — external Morning Scan notes. Watch-only; never promoted into actions here. */}
        <Section id="signal-log" title="Signal Log" icon="📡" badge={VM.signalLog.length?`${VM.signalLog.length}`:"0"} badgeColor={VM.signalLog.length?C.blue:C.faint} openMap={open} setOpen={setOpen} defaultOpen={VM.signalLog.length>0}>
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
        </Section>

        {/* BULLISH FLOW (UW) — read-only WATCH lane: the daily UW opportunity
            cache (Strand-3 surfacing / B1), grouped by ticker (uw_flow = one
            name, one bucket). NOT conviction — the gated Chunk-2 hook is separate. */}
        <Section id="bullish-flow" title="Bullish flow (UW)" icon="🌊" badge={(VM.bullishFlow.rows||[]).length?`${VM.bullishFlow.tickers} · ${VM.bullishFlow.count}`:"0"} badgeColor={(VM.bullishFlow.rows||[]).length?C.green:C.faint} openMap={open} setOpen={setOpen} defaultOpen={(VM.bullishFlow.rows||[]).length>0}>
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

        {/* RADAR — endorsed names not owned yet (engine ⑨ radar block) */}
        <Section id="feedback" title="Feedback loops" icon="🔁" badge={(() => { const f=VM.feedback||{}, sc=f.source_calls||{}, sp=sc.persistence||{}, oa=f.open_actions||{}; const n=(sc.overdue_count||0)+(sp.loud_count||0)+(sp.provisional_count||0)+(oa.count||0); return n?`${n}`:"0"; })()} badgeColor={(() => { const f=VM.feedback||{}, sc=f.source_calls||{}, sp=sc.persistence||{}, oa=f.open_actions||{}; return (sp.loud_count||0)?C.red:((sc.overdue_count||0)+(sp.provisional_count||0)+(oa.count||0))?C.amber:C.faint; })()} openMap={open} setOpen={setOpen} defaultOpen={false}>
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

        <Section id="radar" title="Radar — endorsed, not owned" icon="📡" badge={VM.radar.length?`${VM.radar.length}`:"0"} badgeColor={VM.radar.length?C.blue:C.faint} openMap={open} setOpen={setOpen} defaultOpen={true}>
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
        </Section>

        </>)}

        {/* 📊 BOOK VIEW ─────────────────────────────────────────────── */}
        {mode==="book" && (<>

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
              Showing names held by <b style={{ color:C.dim }}>{view==="parents"?"Parents":"SKB"}</b>. When account positions are available, the account view below uses exact direct $/% rows; the detailed holding rows remain conviction-oriented.
            </div>
          )}

          {portfolioView && (
            <div style={{ ...card, marginBottom:10, borderColor:C.blue+"55", background:C.blue+"08" }}>
              <div style={{ display:"flex", alignItems:"baseline", justifyContent:"space-between", gap:10, flexWrap:"wrap" }}>
                <div>
                  <div style={{ fontSize:12, fontWeight:700, color:C.text }}>{view==="agg"?"Combined":view==="parents"?"Parents":"SKB"} account view</div>
                  <div style={{ ...muted, fontSize:11.5 }}>{VM.portfolioViews.caveat||"Direct holdings only."}</div>
                </div>
                <div style={{ fontFamily:mono, fontSize:16, fontWeight:700, color:C.text }}>{money(portfolioView.total_value)}</div>
              </div>
              <div style={{ marginTop:10, display:"grid", gridTemplateColumns:"repeat(auto-fit, minmax(150px, 1fr))", gap:8 }}>
                {(portfolioView.categories||[]).slice(0,6).map((c,i)=>(
                  <div key={i} style={{ border:`1px solid ${C.line}`, borderRadius:8, padding:"7px 8px", background:C.panel }}>
                    <div style={{ display:"flex", justifyContent:"space-between", gap:8 }}>
                      <span style={{ fontSize:11.5, color:C.text, fontWeight:600 }}>{c.category}</span>
                      <span style={{ fontFamily:mono, fontSize:11, color:C.faint }}>{typeof c.pct==="number"?`${c.pct.toFixed(1)}%`:""}</span>
                    </div>
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
                    {(effectiveExposure.sleeves||[]).filter(s=>s.lookthrough_market_value>0).slice(0,4).map((s,i)=>(
                      <div key={`${s.category}${i}`} style={{ border:`1px solid ${C.line}`, borderRadius:8, padding:"7px 8px", background:C.panel2 }}>
                        <div style={{ display:"flex", justifyContent:"space-between", gap:8 }}>
                          <span style={{ fontSize:11.5, color:C.text, fontWeight:600 }}>{s.category}</span>
                          <span style={{ fontFamily:mono, fontSize:11, color:C.faint }}>{typeof s.effective_pct==="number"?`${s.effective_pct.toFixed(1)}%`:""}</span>
                        </div>
                        <div style={{ marginTop:4, fontFamily:mono, fontSize:10.5, color:C.dim }}>direct {typeof s.direct_pct==="number"?s.direct_pct.toFixed(1):"0.0"}% + ETF {typeof s.lookthrough_pct==="number"?s.lookthrough_pct.toFixed(1):"0.0"}%</div>
                      </div>
                    ))}
                  </div>
                  {(effectiveExposure.overlap_rows||[]).length>0 && (
                    <div style={{ marginTop:8 }}>
                      {(effectiveExposure.overlap_rows||[]).slice(0,5).map((r,i)=>(
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
                {(portfolioView.rows||[]).slice(0,8).map((r,i)=>(
                  <div key={`${r.ticker}${r.account}${i}`} style={{ display:"grid", gridTemplateColumns:"72px 1fr auto", gap:8, alignItems:"center", padding:"4px 0", borderTop:i?`1px solid ${C.line}`:"none" }}>
                    <span style={{ fontFamily:mono, fontSize:12, fontWeight:700, color:C.text }}>{r.ticker}</span>
                    <span style={{ fontSize:11.5, color:C.dim, whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>{r.account}{r.owner&&r.owner!=="Multiple"?` · ${r.owner}`:""}{r.category?` · ${r.category}`:""}</span>
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

        {/* ⚡ ACTION VIEW (cont.) ────────────────────────────────────── */}
        {mode==="action" && (<>

        {/* MARKET READ — rotation + macro (from FEED) */}
        <Section id="market" title="Market read — rotation + macro" icon="🌐" openMap={open} setOpen={setOpen} defaultOpen={true}>
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
        </Section>

        {/* RESEARCH — live Research Queue (R = VM.research when present, else curated) */}
        <Section id="research" title="Research" icon="🔬" badge={(R.pending||[]).length+(R.done||[]).length} badgeColor={C.blue} openMap={open} setOpen={setOpen} defaultOpen={((R.pending||[]).length+(R.done||[]).length)>0}>
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

        {/* CATALYSTS - live feed rows from Catalyst Calendar / catalyst intake */}
        <Section id="cats" title="Upcoming catalysts — near-term" icon="📅" badge={CATS.length} badgeColor={CATS.length?C.blue:C.faint} openMap={open} setOpen={setOpen} defaultOpen={CATS.length>0}>
          {CATS.length===0 && <div style={{ ...card, fontSize:12, color:C.faint }}>No catalysts supplied in this feed build.</div>}
          {CATS.map((x,i)=>(
            <div key={i} style={{ ...card, marginBottom:7, display:"flex", gap:12, alignItems:"baseline" }}>
              <span style={{ fontFamily:mono, fontSize:12, color:C.accent, minWidth:58 }}>{x.d}</span>
              <div><div style={{ fontSize:13, color:C.text }}>{x.e}</div><div style={muted}>{x.note}</div></div>
            </div>
          ))}
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

        <div style={{ marginTop:18, fontSize:11, color:C.faint, textAlign:"center", fontFamily:mono }}>
          {VM.stamp} · tap anything to expand · every section collapses independently
        </div>

        </>)}

      </div>
    </div>
  );
}

