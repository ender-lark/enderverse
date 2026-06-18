# GRNY (FundStrat Granny Shots US Large Cap ETF) — Thesis of Record

**CURRENT VERDICT (2026-06-18):** HOLD - core quality-core wrapper, but **no add — this is our designated funding reservoir** (oversized #2 book position, ~1% off its 52-wk high) · conviction **medium**

> Sell-Gate note: this is the *inverse* of a protected anchor like LEU. GRNY is a diversified large-cap wrapper trading near its high and flagged OVERSIZED (9.4% actual vs a 3.0% model target). It is an **acceptable funding source** when a higher-conviction single-name at a real low needs cash — that is by design, not a thesis break. It is NOT a wrapper to top up here.

## Sector / strategy thesis (why we own it)
GRNY is the flagship Tom Lee / Fundstrat "Granny Shots" large-cap ETF — our way to own Fundstrat's house view as a single diversified quality-core sleeve instead of stock-picking it name by name. It is an actively managed fund that holds a basket of US large-caps selected for exposure to multiple converging Fundstrat themes (web: stockanalysis.com describes 20-50 securities across 5-10 themes). The thesis on file (`src/theses.json` → `thesis_grny`) is a T2 BuyAndHold, source "Lee," tagged `ai_complex` — a durable quality-core holding, not a tactical trade.

## Bull thesis
A multi-theme convergence screen targets names with several reinforcing tailwinds at once, packaged in a diversified active wrapper so we ride Lee's view without single-name selection risk. The franchise has scaled to multi-billion AUM (web: ~$4.5B mid-June 2026 per stockanalysis.com; a one-year-anniversary story cited ~$3.65B), which signals durable sponsor backing and tight spreads. The cockpit logged a single-session bullish UW options signal on 06-16 (sweep + OI build + dark-pool accumulation, flagged "strong") — supportive tape, but single-source and not a standalone thesis.

## Dated catalysts
- **Recurring quarterly rebalance** — the structural catalyst; theme additions/removals are the real "news" for this name (next reconstitution is the standing quarterly cycle; a specific completed-rebalance date is not grounded in our sources).
- No company earnings date (ETF — `get_company_info` returns `next_earnings_date: null`). Its catalysts are the underlying large-cap earnings season and the Fed/macro path, not a single print.

## Disconfirmers (what would break it)
- Fundstrat strategy/methodology change or sustained underperformance vs SPY/large-cap peers → the "own Lee's view in one ticker" rationale weakens; reassess vs a cheaper plain index. (Cockpit reads GRNY roughly IN LINE with the market on a 1M/3M relative basis — opportunity-cost, not a break.)
- A genuine thesis break is hard for a diversified active wrapper, so the live disconfirmer here is mostly **sizing**, not survival: it is already OVERSIZED. Treat drawdowns as a chance to fund higher-conviction names, not to add.
- AUM bleed / sponsor distress (no evidence today; AUM is growing) → only then question the wrapper itself.

## Range / sizing context
Price **~$27.47**, sitting **~1% below its 52-wk high of $27.76** (high made 2026-06-04) and **~+28% above the 52-wk low of $21.42** (low made 2025-06-20) — this is **near the high, NOT near a low** (source: data MCP `get_ticker_close_prices`, 2026-06-18). Up ~+12% over six months and ~+28% over one year. Our position is large: **~6,619 shares, ~$183,802, ~9.4% of the ~$1.9M book — the #2 holding behind only NVDA** (NVDA ~$212,710 direct) — spread across 8 accounts (Joint TOD, Rollover IRA, Roth IRAs, PCRA Trust, HSA, Robinhood Individual + IRAs, Individual ...254) **plus a LEAP call ladder** ($28-$35 strikes, Sep-2026 / Jan-2027 / Jan-2028 expiries). The cockpit flags it **OVERSIZED** (9.4% actual vs 3.0% model target) with `CONCENTRATION_CHECK` + `ALARM_DRIFT`. Bottom line: rich on size, near its high — the textbook profile of a holding to **fund from, not add to**.

## Structure (wrapper note)
Active, non-index US large-cap ETF; **expense ratio 0.75%** (web: AAII / Motley Fool / Seeking Alpha — above the large-cap-growth category average; the cost of owning the active Fundstrat overlay vs a plain index). AUM ~$4.5B (web, mid-June 2026). Because it is diversified large-cap, it carries far less single-name thesis risk than our concentrated holdings — which is exactly why it reads as a reservoir. (Note: the data-MCP `get_company_info` "marketcap" field reads ~$382M, which is the fund's reported net-asset figure but conflicts with the multi-billion AUM reported across several web sources; treated here as a stale/unreliable MCP field, with the AUM figure web-sourced.)

## Funding-tier note (Sell-Gate Rail C)
**Tier 1-2 / acceptable funding source.** This is the opposite end of the rail from LEU. GRNY is a diversified, redundant-with-the-index wrapper trading near its high and carrying an oversized weight; the fed-day reallocation packet already models it as the primary **funding reservoir** ("reservoir drawn to fund the names above," candidate trim sized in `src/fed_day_reallocation_packet.json`, including ~$74,007 of PCRA-Trust GRNY proceeds). When a higher-conviction single-name at a real low needs cash, trim GRNY toward its ~3% model weight *before* touching live single-name theses. Trimming here is the doctrine working as intended — not a sell signal on the thesis. (Note: per the packet, PCRA proceeds can fund ETF buys in-place but funding individual-stock adds requires an explicit operator transfer.)

---
## Superseded history (archive-never-delete)
**(2026-06-18) [origin]** Auto-drafted by the case-file thesis-of-record backfill (grounded screen + adversarial skeptic). PENDING OPERATOR CONFIRMATION - not operator-blessed; the verdict defaults to the status-quo posture and is not a new trade signal.
