# Sell-Gate & Sizing Doctrine

**Living reference (v1, 2026-06-17).** Rails that govern how the system proposes **trims/sells** and how it
reasons about **position size**. Born from a real miss (below). Read this before changing any reallocation,
right-size, or funding logic. Mission test (PRIMARY GOALS): does the change make a real, well-timed,
right-sized action more likely *without* faking urgency or capitulating on a live thesis?

---

## 0. The miss this exists to prevent (case study, 2026-06-17)

**LEU (Centrus) was queued for a "right-size" trim — as a funding source — while it sat near its 52-week
low**, *before* anyone surfaced its live thesis: **Project Janus** (US Army nuclear microreactors, EO 14299,
first criticality targeted before 2026-07-04), the **$2.7B DOE domestic-enrichment program**, and Centrus's
**$900M HALEU task order** — i.e. LEU is the prime US-owned enrichment beneficiary of a federal buildout,
recovering off its low, with consensus targets ~45-65% above spot. Two root failures:

1. **A sell was proposed without loading the holding's thesis of record.** The federal/Janus catalyst was
   simply not on file in the decision path.
2. **A bright-line "oversized → trim" rule fired without judgment**, and pointed straight at *selling a
   strong, catalyst-backed thesis into weakness* for funding convenience.

Both are structural, not "be more careful" problems. The four rails below close them.

---

## 0.5 Prime directive — NO mechanical sells (reinforced 2026-06-17, 2nd operator correction)

A sell/trim is justified **only** by (a) a thesis that is genuinely **impaired or complete**, or (b) a
**deliberate, reasoned risk decision** (concentration, regime, hedge) made with judgment. It is **never**
justified by a *mechanical attribute*. The four attributes that keep masquerading as triggers — and why each
is only a **flag that prompts judgment, never a trigger that acts**:

- **"It's oversized"** → flag, not a trim (Rail D).
- **"It's up a lot"** → NOT a reason. A winner whose **analyst targets are still being raised** is *thesis
  intact / let it run*, not a trim — e.g. MU's HBM/AI-memory super-cycle, undervalued at entry and re-rated
  as the thesis played out. **"Sell high" is as wrong as "sell low."** Trim a winner only for a real reason
  (the thesis is complete/over-priced vs a re-underwrite, or concentration risk you've reasoned through).
- **"It looks duplicative"** → reassess the actual product first. An **actively-managed, differentiated
  basket is not redundant** even if some holdings overlap. **IVES** (Dan Ives Wedbush AI Revolution — active,
  ~30 names, software + broad AI *beyond* chips) is a legitimate long-term **set-and-forget core** and is
  *complementary* to pure-semi **SMH**, not a duplicate of it. The operator's tilt can be **more IVES / less
  SMH**, never "drop IVES because it's a wrapper."
- **"It's at its low"** → never sell a live thesis here (Rail B; the LEU/Janus miss).

**Every** funding-source candidate (Rail C) — including the "redundant wrapper" and "winner at highs" tiers —
gets this same thesis check before it is sold. Reasoning over rules, even when it costs more time/tokens.

---

## 1. Rail A — Thesis of Record (per holding)

Every holding has a **living thesis-of-record**, maintained, dated, in two mirrored places:
- **Notion** "📚 Research Queue" page for the ticker (`collection://cab89576-0933-40b0-ad2e-6f9a6188e804`).
- **Repo** `docs/research_dossiers/<ticker>.md`.

It contains: **why we own it · the bull thesis · dated catalysts (including policy / federal programs /
government contracts) · the disconfirmers (what would break it) · conviction · last-updated date.**

**One CURRENT VERDICT, dated, at the top; older verdicts kept below as dated history (archive-never-delete).**
When a new read supersedes an old one, **mark the old as superseded** — never leave two contradictory verdicts
unranked on a page. That ambiguity is itself a mis-action risk: it happened 2026-06-17 on BE / IVES / UUUU when
a mechanical sweep verdict (trim/exit) collided with the judgment reassessment (hold/add), and had to be
reconciled by hand.

**Rule:** no trim/sell may be *recommended* without first loading the thesis-of-record **and** doing a fresh
catalyst/policy check. If the thesis is **stale** (older than the freshness window) or **missing**, refresh it
*before* proposing the sell — never sell against a blank or stale file.

## 2. Rail B — The Sell Gate (every proposed trim/sell must pass)

A sell recommendation must answer, in order:
1. **Thesis state** — impaired/dead, or alive? (from Rail A + fresh check)
2. **Range position** — is it near its 52-week low? If yes, **"selling into weakness" is flagged** and the
   sell needs an *explicit thesis-break* justification. Funding/right-size convenience is **not** sufficient.
3. **Live/un-priced catalyst** — earnings, federal program, contract, policy? If yes → default **HOLD**.

**A sell survives the gate only if:** the thesis is genuinely **impaired/dead**, OR it is a **profit-trim of a
winner at/near its high**, OR it is a **redundant/duplicative wrapper** (names held directly elsewhere).
A live-thesis name **at its low** never clears the gate for mechanics.

**Skeptic weighting:** a verifier flag of *"selling into weakness / live thesis"* is a **near-veto** on a
funding sell — not a footnote. (Asymmetric with the buy side, where a skeptic "wait" is just one input;
see the separate skeptic-bias note.)

## 3. Rail C — Funding hierarchy (where reallocation cash comes from, in order)

1. **Idle cash / money-market.**
2. **Redundant / duplicative wrappers** (an ETF whose constituents you already hold directly).
3. **Genuinely dead/impaired theses** (thesis broken, confirmed).
4. **Winners at/near their highs** (disciplined profit-trim).
5. **Tax-loss-harvest lots** (when a carryforward/loss benefit applies).
6. **LAST, and only with an explicit thesis-break:** a live-thesis name — **and never one at its low.**

The reallocation engine should exhaust the higher tiers before ever touching a live thesis, and surface which
tier each funding leg came from.

## 4. Rail D — Sizing is a JUDGMENT PROMPT, not a bright-line trigger

This replaces the old hard "right-size rule." The operator dislikes rules that fire without reasoning.

- The system **surfaces sizing context** — "under-sized vs conviction," "fragmented across N accounts,"
  "large/concentrated," "parabolic winner" — but **does not auto-recommend a trim or an add**.
- **Asymmetric by design** (the mission says under-sizing a strong setup is the documented way we lose):
  - **Under-owning** a high-conviction, *converging* setup → pull **LOUDLY** toward sizing up.
  - **Over-owning** → a **gentle** prompt to *consider* trimming, **gated by the Sell Gate** (so it can never
    trigger selling a live thesis into weakness).
- **No hard thresholds** ("beta > X + > $Y → trim"). The call is made with reasoned judgment over: thesis
  state · conviction · concentration/correlation · range position (don't sell into weakness) · tax ·
  alternatives. **Right-size never overrides a live thesis.**

---

## 5. Implementation / wiring (build tasks)

1. **Maintain the per-holding Thesis-of-Record** (Notion + repo), auto-refreshed by the off-hours worker;
   every holding without a current file is itself a flagged gap.
2. **Enforce the Sell Gate on every emitted trim/sell card**: the card must display thesis state, range
   position (with a near-52-wk-low warning), and the next dated catalyst, and must cite which funding tier
   (Rail C) it belongs to. A near-low live-thesis sell is blocked absent an explicit thesis-break field.
3. **Replace the right-size threshold** with the asymmetric judgment-prompt (loud under, gentle+gated over).
4. **Track policy/federal-program catalysts** per holding (a catalysts field; wire a government-contract /
   policy source — the Janus/DOE class of catalyst was invisible to the pipeline).
5. **Weight "sell-into-weakness" skeptic flags as near-vetoes** on funding sells.

Baseline doctrine version: v1 (2026-06-17). Update the version + date on any change, and keep the case study.
