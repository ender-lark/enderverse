# AVGO — missing standalone thesis (~$40K held, untracked)

**Question (one sentence):** AVGO is held (~$40K) but absent from the curated
positions and thesis files — what is the standalone AI-networking / custom-ASIC
thesis and is the position tracked correctly?

## Current state + links
- **Position / tracking gap:** AVGO is **not** in the curated sleeve
  `src/positions.json` (snapshot 2026-06-12, 13 names) and has **no thesis** in
  `src/theses.json` — yet the seed list flags it as **"~$40K held, untracked."**
  This is a real reconciliation gap: an untracked holding with no thesis row.
- **Notion row:** `37ac5031…8479e`-adjacent "AVGO — write the AI-networking and
  custom-ASIC thesis line when evidence is available; timing catalyst passed"
  (`src/research_queue.json`, pr=low, Status=Queued); source note "important AVGO
  date passed."
- Named in Power & Policy lane portfolio context (AI/semis concentration).

## Catalyst + time window (reference only)
- The row says the **timing catalyst already passed** (AVGO fiscal-Q2 print was
  early June). So this is **not** time-sensitive on a catalyst basis — it is a
  standing thesis-and-tracking gap, "this week" only in the sense of closing the
  untracked-holding loop.

## Evidence pulled (as-of 2026-06-12 close; pulled 2026-06-13)
- **Price (UW OHLC):** close **$382.07** (O 383.72 / H 384.98 / L 377.00).
  5-session: 6/8 $396.60 → 6/9 $392.16 (intraday H **$407.87**) → 6/10 $372.10 →
  6/11 $385.57 → 6/12 $382.07. **Post-print fade ≈ -3.7% on the week** off a
  6/9 spike-and-reverse — classic "sell-the-news" digestion.
- **Options flow (UW, 6/12):** net_premium **-$0.95M** (neutral); bullish $79.5M
  vs bearish $80.5M; IV rank **38.6** (cooling from ~49 on 6/10). No directional
  conviction post-print.

## FS-COVERED vs NEW
- **FS-COVERED:** AVGO is inside the FS/Lee AI-complex baseline.
- **NEW:** a written **standalone** AVGO thesis line (AI-networking + custom-ASIC,
  i.e. the hyperscaler XPU/networking franchise) and — more urgently — the
  **tracking reconciliation** (why a ~$40K holding is missing from
  `positions.json`) are both NEW and unaddressed.

## MISSING EVIDENCE — not checked
- The actual AVGO account position (size, account, cost basis) — `positions.json`
  is read-only and does not list it; the untracked-holding gap should be routed to
  the positions-sync / reconciliation owner.
- AVGO fiscal-Q2 results detail (AI revenue run-rate, VMware mix, guide) — not
  pulled; the "catalyst passed" so this is backfill, not live.
- T4 deepdive battery (multi-day OI, dark-pool blocks) — not run.

## Proposed state: **RESEARCH** (thesis + tracking backfill; not time-critical)
1. **What it reveals:** a digestion tape post-print (neutral flow) plus a genuine
   bookkeeping gap — a held name with neither a thesis nor a positions entry.
2. **Clear action?** No trade action (catalyst passed). The actionable item is
   operational: **reconcile the untracked ~$40K holding** and write the standalone
   thesis line. Evidence-only on the trade side.
3. **Time-sensitive?** No (catalyst passed); the tracking gap should still be
   closed promptly for portfolio honesty.
4. **Affects sizing/conviction/leverage/risk?** Yes indirectly — an untracked $40K
   position distorts concentration/sizing math until reconciled.
5. **Evidence still missing?** Yes — the position record itself, Q2 fundamentals,
   and the thesis text.
