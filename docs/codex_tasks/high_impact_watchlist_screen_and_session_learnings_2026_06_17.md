# System Update Queue — High-Impact Watchlist Screen + Session Learnings (2026-06-17)

Source: live reallocation session (Claude) on Fed day. Mission test for everything below: *does it make a
real, high-conviction, well-timed, right-sized opportunity more likely to reach the operator and get acted
on before the window closes?* (see PRIMARY GOALS). The window is closing — AI-driven repricings have been
fast and large over the last year, and the runway shortens into/after the **2026 midterms**.

---

## A. Durable learnings to encode (from today's session)

1. **Right-size is a first-class question, not an afterthought.** Every position must pass *"is this the
   right size for its conviction?"* A **tiny stub in a high-conviction name is itself the failure**
   (own-a-little-where-the-evidence-says-own-a-lot). Conversely, sub-~$1-2k positions with no live thesis
   are **noise** to clear/consolidate. The operator's book has many scattered micro-lots (same ticker held
   in 4-6 accounts at $0.5-3k each) — these need a consolidation + right-size pass, not just buy/sell.
   → **Build a "conviction-vs-size gap" detector**: flag (a) high-conviction names that are under-sized,
   (b) sub-threshold noise stubs, (c) the same ticker fragmented across accounts.

2. **Deep-discount "buy the low" only pays when the discount is sentiment/rates on a QUALITY business —
   not when it is dilution or a broken thesis.** A cheap chart on a company that must sell stock to survive
   (serial ATM, going-concern burn, lost anchor customer) is a value trap. Today's check killed POET
   (anchor customer cancelled all orders + litigation), LUNR (fresh $500M ATM lid), ASTS (≈139x fwd sales +
   standing ATM), and tempered FN (rich + CPO disintermediation). The clean ones were quality-on-sale
   (GOOGL, AVGO, FN).
   → **Add a dilution/cash-runway field to the deep-discount packet**: cash on hand, quarterly burn, months
   of runway, recent/imminent raises, YoY share-count growth. No discount buy should surface without it.

3. **Adversarial skeptics default to "wait" and quietly recreate passivity.** A verify-agent told to
   "refute if uncertain" will always find uncertainty — the net drifts to "here's why to hold," which is
   the documented failure mode wearing a lab coat. → When synthesizing, **weight the action case explicitly
   and size to conviction**; treat a skeptic "hold" as one input, not a veto.

4. **Tax-loss carryforward unlock.** Operator carries large prior-year capital losses → realizing gains is
   effectively tax-free this year. This removes the lot-routing gymnastics; **fund from the best investment
   source, not the lowest-tax one** (can trim oversized winners and the duplicative IVES wrapper in full,
   clear taxable stubs, etc.). → **Make the reallocation engine carryforward-aware** (a `tax_shield_usd`
   input that relaxes the gain-realization penalty). Confirm the exact carryforward figure from last year's
   Schedule D before relying on it.

5. **Post-FOMC macro/Fundstrat read (2026-06-17), for the record:** hawkish hold (cuts erased, 9/18 see a
   2026 hike, 2-yr spiking, bear-flattening). Newton 3:38pm: rate-proxies (REITs/Utilities) "hard hit,"
   metals down, but **tech leadership has not cracked, SOX +2.85%**; he expects the rate spike to be
   temporary on an Iran reopening. Financials/banks (1:21pm) and biotech/XBI (1:13pm) flagged as breakouts.
   → The intraday FlashInsights were **web-only at decision time** (Gmail digest lags ~to 5pm ET). The
   pre-market source-intake routine was **down** today. **Harden the Fundstrat intake to pull intraday
   member FlashInsights (not just the emailed digest), and alert when the intake routine is overdue.**

---

## B. THE BIG-LIST SCREEN (primary task — run OFF-HOURS tonight, parallel agents)

Operator has a large prospect list well beyond the names reviewed today. Critically, the repo's
**`watchlist_discount_screen` (107 names) is currently UNCONSUMED** (read nowhere — see
`docs/decision_surface_architecture.md` §4/§7). That is exactly the "great information that never reaches
the operator" failure the mission names. **Do not let good, fast-moving, high-impact names slip because we
never screened them.**

**Task:** screen the FULL list — the 107-name `watchlist_discount_screen` + all current holdings + any other
operator prospect lists — using **parallel agents** (Claude Code does this easily), each name through one
consistent lens:

- conviction (independent confirmations, not echoes) · regime fit (post-FOMC) · Fundstrat stance (Granny
  Shots / top / avoid) · **dilution & cash-runway** · **right-size verdict** (under/over/right vs conviction;
  is it a scattered micro-lot to consolidate or a noise stub to clear) · at-a-low vs active falling-knife ·
  asymmetry (realistic up vs down) · catalyst + date.
- Adversarial value-trap/dilution skeptic on every actionable BUY.

**Outputs:**
1. A ranked **"high-impact-at-lows"** report — the few names where the discount is sentiment/rates on a real
   business with a near catalyst (the ones that "can move a lot, fast").
2. A **right-size report** — under-sized conviction names to size up; oversized/parabolic names to trim;
   scattered micro-lots to consolidate; noise stubs to clear.
3. Both shown as **decisions** (lead with the move, sized, dated), not a data dump — and wired so they reach
   the operator (see C).

**Constraints:** advisory only — **no auto-execution**. Stay inside survival rails. Run when markets are
closed (more time, calmer tape). ~$50k of dry powder was parked from today's raise specifically to deploy
fast on whatever this surfaces.

## C. System wire-ups this implies (so it is not build-and-forget)

- **Wire the 107-name `watchlist_discount_screen` into the decision surface** (it is orphaned today).
- Add the **dilution/runway** and **right-size/conviction-gap** fields to the packet + surface.
- Make the reallocation engine **carryforward-aware**.
- **Harden Fundstrat intake** (intraday FlashInsights + overdue-routine alert).
- **Stand up a recurring off-hours parallel-agent screen** of the full list so the queue can't rot — and
  feed back what happened (did the flagged name move?) per the no-build-and-forget rail.

## E. Auto-persist session research to Notion (so we never re-research from scratch)

Today's per-ticker research (multi-agent verdicts: thesis-now, catalyst, key risk, dilution/cash-runway,
Fundstrat stance, price as-of, verdict+conviction) was written into the **📚 Research Queue**
(`collection://cab89576-0933-40b0-ad2e-6f9a6188e804`, under Life OS → Finance → Session State) — one dated
section per ticker, create-or-append. That was done manually this session. **Make it automatic:**

- After any reallocation/research session or the off-hours screen (Section B), **auto-write each researched
  ticker's findings to its Research Queue page**, dated, create-or-append (never overwrite history) — so the
  next session starts from the saved dossier, not a blank page. This complements the existing
  ticker→Research-Queue→Pipedream auto-research spine noted in the "Cross-Pollination Log."
- Capture the durable fields (thesis/catalyst/risk/dilution-runway/FS-stance/price-as-of) separately from the
  session-specific **verdict + date**, so a stale verdict is never mistaken for current — every note carries
  its as-of date, and the reader re-checks price/flow before acting.
- Mirror the same dossier into the repo (`docs/research_dossiers/<ticker>_<date>.md`) as the off-hours worker
  already does for some names, so repo and Notion stay in lockstep.

## D. Urgency note
AI and other high-beta names have made large, fast moves over the last year; the operator's $1.9M→$3M
window narrows into/after the 2026 midterms. Cash is staged. The cost of *missing* a real high-impact name
now outweighs the cost of an extra screen — so the screen runs tonight, not "soon."

---

## F. CORRECTION — operator feedback 2026-06-17 (supersedes the bright-line framing in A1)

Full doctrine: **`docs/sell_gate_and_sizing_doctrine.md`** (v1). Two structural fixes:

**F1. Thesis-of-Record gap (the LEU / Janus miss).** LEU was queued for a "right-size" trim *at its 52-week
low* — as a funding source — before its live thesis (Project Janus US-Army microreactors + EO 14299, the
$2.7B DOE enrichment program, Centrus's $900M HALEU task order) was surfaced. Root cause: a sell was proposed
without loading the holding's thesis. → **Every holding gets a maintained Thesis-of-Record** (Notion Research
Queue page + repo `docs/research_dossiers/<ticker>.md`: bull case, dated catalysts incl. policy/federal,
disconfirmers, conviction, last-updated). **No trim/sell may be emitted without loading it + a fresh
catalyst/policy check; if stale/missing, refresh first.** Enforce a **Sell Gate**: a sell survives only if the
thesis is impaired/dead, or it's a profit-trim of a winner near its high, or it's a redundant wrapper — and a
**"selling into weakness" warning fires whenever the name is near a 52-wk low** (a near-veto for funding sells).

**F2. Soften the right-size rule → judgment, not a bright-line trigger.** The operator dislikes hard rules that
fire without reasoning. **Right-size becomes an asymmetric judgment prompt:** LOUD pull toward sizing UP an
under-owned high-conviction setup (the documented failure mode); a GENTLE, Sell-Gate-gated prompt to *consider*
trimming an over-owned one — never an auto-trim, never selling a live thesis into weakness. Remove hard
thresholds ("beta>X + >$Y → trim"); apply reasoned judgment (thesis + conviction + concentration +
range-position + tax + alternatives).

**Build tasks:** (1) per-holding Thesis-of-Record maintained by the off-hours worker; (2) Sell Gate on every
emitted trim/sell card (show thesis state, range-position/near-low flag, next catalyst, funding tier);
(3) replace the right-size threshold with the asymmetric judgment-prompt; (4) track policy/federal-program
catalysts per holding (wire a gov-contract/policy source); (5) **Funding hierarchy** — cash → redundant
wrappers → dead theses → winners-at-highs → tax-loss lots → (last, with explicit thesis-break) a live thesis,
never at its low.
