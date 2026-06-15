# Disconfirmation Gaps

Theses that **cannot currently be proven wrong** — they lack an operator-confirmed kill-switch.

As of: 2026-06-15
Source: `src/disconfirmation_registry.json` (sidecar, owned by Claude Code / CC-C). Regenerate with `python src/disconfirmation_registry.py --gaps`.

A thesis is only treated as falsifiable once its disconfirmation entry is reviewed and marked `CONFIRMED`. `DRAFT — operator to confirm` entries are Claude-seeded starters: reasoned, specific, and checkable, but **not yet operator-confirmed fact**.

**Coverage: 0/14 theses have a confirmed kill-switch** — 8 missing, 6 draft, 0 confirmed.

## No kill-switch at all (MISSING)

No disconfirmation entry exists — there is currently no written way to prove these wrong.

**Active (urgent — being acted on with no kill-switch):**
- MAGS (T2 · BuyAndHold · ACTIVE)
- SMH (T2 · BuyAndHold · ACTIVE)
- IGV (T3 · BuyAndHold · ACTIVE)
- IVES (T3 · Speed · ACTIVE)
- VOLT (T3 · Speed · ACTIVE)
- XLF (T3 · BuyAndHold · ACTIVE)

**Monitor / other:**
- MP (T3 · Speed · MONITOR)
- UUUU (T3 · Speed · MONITOR)

## DRAFT — operator to confirm

Starter reasoning exists but is unconfirmed. Review, then edit and set `status: CONFIRMED` in the registry to make it a live kill-switch.

### BMNR (T1 · Generational · MONITOR)
- **Fastest way wrong:** Held as leveraged / treasury-style ETH exposure (crypto/eth factor tags); the thesis breaks if ETH enters a structural downtrend or the equity de-rates to / below the value of its ETH-per-share, so it stops being an accretive way to own ETH.
- **Invalidating evidence:** ETH closing below its key multi-month support on a sustained basis (operator to set the level); OR BMNR trading at or under its ETH net-asset value (market cap <= underlying ETH holdings, mNAV <= 1) for several weeks; OR equity / at-the-market raises that dilute rather than grow ETH-per-share.
- **Flip trigger:** Premium-to-NAV gone (price <= ETH-per-share) for a sustained stretch, OR a structural ETH support break - either flips BMNR from accretive leverage to leveraged downside and forces a re-rate of the Generational tag (already flagged CRITICALLY_BELOW the T1 floor).
- Last reviewed: 2026-06-13 · status: DRAFT — operator to confirm

### LEU (T1 · Generational · MONITOR)
- **Fastest way wrong:** The domestic-enrichment / HALEU thesis breaks if U.S. policy support for onshore enrichment stalls or a competing Western HALEU supplier erodes Centrus's near-monopoly, removing the enrichment-pricing power.
- **Invalidating evidence:** Non-renewal or cancellation of the DOE HALEU contract; a competing Western HALEU line reaching commercial output; or SWU / enrichment prices rolling over while commercial offtake stays absent.
- **Flip trigger:** DOE deprioritizes domestic-enrichment funding OR a key HALEU award is cancelled or granted to a competitor - removing the policy-backed monopoly that underpins the Generational tag.
- Last reviewed: 2026-06-13 · status: DRAFT — operator to confirm

### GRNJ (T2 · BuyAndHold · ACTIVE)
- **Fastest way wrong:** GRNJ stops being a diversified, research-backed SMID Granny Shots sleeve and becomes either concentrated factor beta, impaired liquidity, or a weaker use of capital than direct higher-conviction holdings/cash.
- **Invalidating evidence:** Official holdings or independent holdings data show the fund is no longer broadly diversified / theme-screened (operator to set exact concentration threshold); or AUM/liquidity/spread deterioration makes the ETF costly to use; or Fundstrat removes the key SMID AI/data/infrastructure/nuclear/cyclical holdings while price action materially lags SMID benchmarks through a full rebalance cycle.
- **Flip trigger:** A verified process/holdings break, liquidity impairment, or full-cycle relative failure flips GRNJ from protected diversified core to re-check/trim candidate. Same Fundstrat source alone is not enough.
- Last reviewed: 2026-06-15 · status: DRAFT — operator to confirm

### GRNY (T2 · BuyAndHold · ACTIVE)
- **Fastest way wrong:** GRNY duplicates large-cap AI/hyperscaler exposure already owned directly, so the flagship wrapper becomes lower-conviction overlap rather than useful diversified exposure.
- **Invalidating evidence:** Current look-through plus direct holdings show large duplicated exposure to the same mega-cap AI names without adding differentiated upside; or Fundstrat removes the core large-cap AI/quality leaders from the list; or GRNY materially lags SPY/QQQ while preserving the same crowded exposures through a full rebalance cycle.
- **Flip trigger:** If overlap is high and the direct-name model has fresher/stronger conviction, trim GRNY only as a reviewable funding source after price/flow, tax/account, and same-session gates. Do not treat the wrapper as a thesis break without this evidence.
- Last reviewed: 2026-06-15 · status: DRAFT — operator to confirm

### NVDA (T2 · Speed · ACTIVE)
- **Fastest way wrong:** AI data-center demand decelerates faster than NVDA can broaden into new markets - hyperscaler capex digestion or a credible compute-efficiency shock breaks the GPU upgrade cycle.
- **Invalidating evidence:** Two consecutive quarters of sequential Data Center revenue decline; or 2+ of the top hyperscalers (MSFT/GOOGL/AMZN/META) guiding forward capex down year-over-year on the same earnings cycle; or next-gen (Blackwell/Rubin) gross margin guided materially below the recent ~70%+ on demand - not supply - grounds.
- **Flip trigger:** Sequential Data Center revenue turns negative for two straight quarters, OR an aggregate hyperscaler capex guide-down for the forward year - downgrade the secular-compute call to neutral pending re-confirmation.
- Last reviewed: 2026-06-13 · status: DRAFT — operator to confirm

### MU (T3 · Speed · ACTIVE)
- **Fastest way wrong:** The memory up-cycle rolls over - DRAM/HBM oversupply or HBM share loss reverses pricing power faster than AI-memory demand can absorb it.
- **Invalidating evidence:** Two consecutive quarters of declining DRAM average selling prices / bit pricing; rising days-of-inventory; or a confirmed HBM3E/HBM4 qualification loss at a major accelerator customer to SK Hynix or Samsung.
- **Flip trigger:** DRAM ASPs decline for two straight quarters OR a public HBM qualification loss at a top customer - flip the cyclical-upturn call to late-cycle pending re-confirmation.
- Last reviewed: 2026-06-13 · status: DRAFT — operator to confirm

## Confirmed kill-switches

(none yet — operator has not confirmed any disconfirmation)

## Full coverage table

| Ticker | Tier | Lane | Stance | Disconfirmation |
|---|---|---|---|---|
| BMNR | T1 | Generational | MONITOR | DRAFT |
| LEU | T1 | Generational | MONITOR | DRAFT |
| GRNJ | T2 | BuyAndHold | ACTIVE | DRAFT |
| GRNY | T2 | BuyAndHold | ACTIVE | DRAFT |
| MAGS | T2 | BuyAndHold | ACTIVE | MISSING |
| NVDA | T2 | Speed | ACTIVE | DRAFT |
| SMH | T2 | BuyAndHold | ACTIVE | MISSING |
| IGV | T3 | BuyAndHold | ACTIVE | MISSING |
| IVES | T3 | Speed | ACTIVE | MISSING |
| MP | T3 | Speed | MONITOR | MISSING |
| MU | T3 | Speed | ACTIVE | DRAFT |
| UUUU | T3 | Speed | MONITOR | MISSING |
| VOLT | T3 | Speed | ACTIVE | MISSING |
| XLF | T3 | BuyAndHold | ACTIVE | MISSING |

_Generated by `src/disconfirmation_registry.py` (`--gaps`). Sidecar only; does not surface cards._
