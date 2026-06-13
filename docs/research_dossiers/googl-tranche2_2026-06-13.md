# GOOGL — tranche-2 context + AI-infrastructure financing

**Question (one sentence):** Does the now-priced $84.75B AI-infrastructure
financing package (ATM + Berkshire) change the staged tranche-2 add case ahead of
the armed 2026-06-19 review?

## Current state + links
- **Position:** GOOGL is **not** in the curated sleeve `src/positions.json`
  (snapshot 2026-06-12); `AGENTS.md` keeps ANET and GOOGL explicitly open. Sleeve
  exposure is therefore tracked via the Live Thesis + trigger, not the positions
  file. (Account-level size not in this agent's read set — see MISSING EVIDENCE.)
- **Live Thesis:** `37dc50314bb681738ff3e12f39893b7e` (GOOGL tranche-2, staged
  6/12 entry).
- **Registered trigger:** `googl-tranche-2-review-2026-06-19` in
  `src/trigger_registry.json` — `date_event` 2026-06-19, status **armed**,
  expires 2026-06-23. Note: "Fires on +1 week price/flow confirmation unless the
  next FS stock-ideas deck re-confirms GOOGL earlier; if the next deck drops
  GOOGL, stop at 3.7% and reassess."
- **Notion row:** `37ac5031…479e` (Status=Queued, Priority=High).
- **New risk:** Power & Policy lane (`37ec5031…8151`, 2026-06-13) flags a **GOOGL
  NSPM-11** political/regulatory risk routed into the **Sunday 6/14** operator
  review.

## Catalyst + time window (reference only)
- 6/14 night operator review (held packets); 6/19 tranche-2 trigger (6 days out);
  financing absorption "this week" per the scout packet.

## Evidence pulled (as-of 2026-06-12 close; pulled 2026-06-13)
- **Price (UW OHLC):** close **$359.68** (open 362.62 / H 366.57 / L 354.94).
  5-session path: 6/8 $363.31 → 6/9 $364.26 → 6/10 $356.38 → 6/11 $357.77 →
  6/12 $359.68. Net ~flat on the week; financing news absorbed without a break of
  the $356–366 range.
- **Options flow (UW, 6/12):** net_premium **+$13.2M**; call premium $172.4M vs
  put $54.2M; bullish $112.4M vs bearish $99.7M; IV rank **30.9** (subdued). Mild
  positive tilt, not a conviction surge.
- **Financing (Notion scout, SEC 424B5, checked 6/9–6/12):** package priced &
  upsized to **$84.75B** (from proposed $80B) — Series B mandatory convertible
  preferred/depositary shares, an ATM of up to **$40B** Class A/Class C, and a
  **$10B** Berkshire-affiliate private placement; proceeds for AI infra / global
  compute.

## FS-COVERED vs NEW
- **FS-COVERED:** GOOGL is a Lee/FS open-review name; the tranche-2 staging is the
  FS-aligned path.
- **NEW:** the upsized financing terms and the NSPM-11 political risk are new and
  not yet reconciled into the FS thesis (the Power & Policy lane explicitly routes
  NSPM-11 to the 6/14 review).

## MISSING EVIDENCE — not checked
- GOOGL account-level position size / cost basis (outside this agent's read set;
  `positions.json` is read-only and does not list it).
- Share-count dilution math from the mandatory convertible + ATM; exact Berkshire
  terms; cost-of-capital vs capex ROI.
- Post-6/12 price/flow confirmation for the 6/19 trigger; whether the next FS
  stock-ideas deck re-confirms or drops GOOGL.
- T4 deepdive battery (multi-day OI build, 10-day dark-pool blocks, greek
  exposure) — not run; owned by T4.
- NSPM-11 specifics and transmission (owned by Power & Policy lane, held to 6/14).

## Proposed state: **WATCH** (trigger-gated; ACT_NOW not on source row)
1. **What it reveals:** financing is large but the tape treated it as neutral-to-
   mildly-positive, not defensive — consistent with the add thesis, not yet
   confirming it.
2. **Clear action?** No standalone action tonight; the action is gated by the
   armed 6/19 trigger and the 6/14 review. Evidence-only.
3. **Time-sensitive?** Yes — 6/19 trigger (6 days) and 6/14 review.
4. **Affects sizing/conviction/leverage/risk?** Potentially: dilution math and
   NSPM-11 are the two unresolved levers; "stop at 3.7% and reassess" if the next
   FS deck drops GOOGL caps sizing risk.
5. **Evidence still missing?** Yes — dilution math, post-6/12 confirmation, NSPM-11
   transmission (all listed above).
