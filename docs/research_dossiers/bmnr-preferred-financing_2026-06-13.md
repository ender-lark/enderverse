# BMNR — June preferred financing impact on mNAV / ETH-per-share flywheel

**Question (one sentence):** Is the 9.50% Series A preferred raise accretive to
ETH-per-share (mNAV > 1.0, dividend covered by staking yield) or dilutive enough
to weaken the MONITOR-sleeve thesis?

## Current state + links
- **Position:** held — **BMNR 3,486 sh = $57,142** (`src/positions.json`,
  2026-06-12).
- **Thesis:** `thesis_bmnr` (`src/theses.json`) — tier **T1**, lane Generational,
  stance **MONITOR**, factor tags crypto/eth. Comment: reclassified 5/3/26;
  currently T2 5% baseline, upgrade to T1 (10%) only on a high-confidence trigger;
  "currently CRITICALLY_BELOW T1 floor."
- **MONITOR sleeve rule (`AGENTS.md` V3):** BMNR has exactly one action path —
  MONITOR-RE-ENTRY from `orphan_wiring`, requiring defined-risk fields. No
  alternate buy path. No re-entry condition is currently met.
- **Notion row:** `37ac5031…491d` (Status=Queued, Priority=High).

## Catalyst + time window (reference only)
- "Next session to ~1 week" per the scout packet; preferred-settlement market
  reaction and any follow-on ATM are the watch items.

## Evidence pulled (as-of 2026-06-12 close; pulled 2026-06-13)
- **Price (UW OHLC):** close **$16.11** (O 16.31 / H 16.81 / L 15.95). 5-session:
  6/8 $16.85 → 6/9 $16.20 → 6/10 $15.64 → 6/11 $16.52 → 6/12 $16.11 (≈ -4.4% wk,
  choppy, no breakout).
- **Options flow (UW, 6/12):** net_premium **+$1.84M** (mild positive); IV rank
  **7.1** (very low — market not pricing a near-term catalyst). Call OI 1.26M vs
  put OI 0.46M.
- **Filings (Notion scout, SEC, checked 6/9):** 2026-06-05 424B5 + 8-K — **9.50%
  Series A Perpetual Preferred**, 3.5M shares @ $80, est. net proceeds **~$273.8M**;
  use: ETH/digital-asset acquisition, staking/validator infra, ecosystem
  investments, working capital, common repurchases. SEC Ex-99.1 (6/8): **5,543,872
  ETH held as of 6/7 (4.59% of ETH supply)**, ~$9.6B crypto+cash.

## FS-COVERED vs NEW
- **NEW / operator lane:** BMNR is an operator-sourced crypto-treasury proxy, not
  a Fundstrat name — no FS coverage to reconcile. Evidence here is all NEW.

## MISSING EVIDENCE — not checked
- Current **mNAV** (market cap vs crypto+cash NAV) — the single most important
  number, not computed tonight (needs live share count + market cap).
- **ETH-per-share before/after** the preferred; preferred **dividend-coverage**
  math vs staking/option yield.
- Whether the common **repurchases** are real or only optional; post-settlement
  market reaction.
- T4 deepdive battery (multi-day OI, dark-pool blocks) — not run (T4-owned).

## Proposed state: **MONITOR** (gated; no re-entry condition met)
1. **What it reveals:** scale is real (4.59% of ETH supply) but the accretion
   question — the whole thesis — is unresolved; price/IV show no near-term
   catalyst priced.
2. **Clear action?** No. MONITOR sleeve has only a defined-risk MONITOR-RE-ENTRY
   path and no condition is met. Evidence-only.
3. **Time-sensitive?** Mildly — settlement reaction over the next week, but no
   dated catalyst.
4. **Affects sizing/conviction/leverage/risk?** Yes if mNAV/accretion resolve:
   accretive issuance supports a T1 upgrade case; dilutive would confirm the
   "critically below floor" read. Stays gated until quantified.
5. **Evidence still missing?** Yes — mNAV, ETH-per-share delta, dividend coverage
   (all above). **Do not** treat the raise as accretive without these.
