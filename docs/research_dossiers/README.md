# Research Dossiers — per-holding Thesis of Record (repo mirror)

**This directory is the repo half of Sell-Gate & Sizing Doctrine Rail A** (`docs/sell_gate_and_sizing_doctrine.md` §1). It was created 2026-06-17 by the storage/synthesis audit
(`docs/investing_os_storage_and_synthesis_audit_2026_06_17.md`, finding **S12**), which found the repo
half of Rail A missing while the Notion half (📚 Research Queue, `collection://cab89576-0933-40b0-ad2e-6f9a6188e804`)
existed. Scaffold only — **the per-ticker files still need to be populated** (owner: the off-hours worker /
operator; do not fabricate verdicts).

## Why this exists (the miss it prevents)
LEU was queued for a "right-size" funding trim *near its 52-week low* before anyone loaded its
thesis-of-record (Project Janus / DOE enrichment / HALEU). Rail A's rule: **no trim/sell may be
*recommended* without first loading the holding's thesis-of-record and doing a fresh catalyst/policy
check.** That check needs a store on both sides; this is the repo side.

## Convention
- One file per holding: `docs/research_dossiers/<TICKER>.md` (e.g. `LEU.md`).
- **Mirrors** the Notion Research Queue page for that ticker — keep both in sync; neither is secretly
  canonical. When they diverge, reconcile, don't pick silently.
- **One CURRENT VERDICT, dated, at the top.** Older verdicts kept below as dated history
  (**archive-never-delete**). When a new read supersedes an old one, **mark the old superseded** — never
  leave two contradictory unranked verdicts on a page (that ambiguity is itself a mis-action risk; it bit
  BE / IVES / UUUU on 2026-06-17).
- If a holding has **no** dossier, that is itself a flagged gap (a sell can't clear the Sell Gate against a
  blank file). If the dossier is **stale** (older than the freshness window), refresh *before* proposing
  any sell.

## Template (copy for each `<TICKER>.md`)

```markdown
# <TICKER> — Thesis of Record

**CURRENT VERDICT (YYYY-MM-DD):** <hold / add / trim / exit> — <one-line why> · conviction <low/med/high>

(HELD names only. For a name we do NOT own, use the buy-side template below — a "HOLD"
on something you don't own is a category error and reads as a posture that doesn't exist.)

## Why we own it
<the core reason this is in the book>

## Bull thesis
<what has to be true for this to work>

## Dated catalysts
- <date> — <catalyst> (include policy / federal programs / government contracts — the Janus/DOE class
  that was invisible to the pipeline)

## Disconfirmers (what would break it)
- <falsifier> → <what we'd do>

## Range / sizing context
<52-wk position (near-low warning if applicable) · current weight · concentration/correlation notes>

## Funding-tier note (Sell-Gate Rail C)
<if ever a funding source: which tier — idle cash > redundant wrapper > dead thesis > winner-at-high >
 TLH lot > (last, only with explicit thesis-break) live thesis, never one at its low>

---
## Superseded history (archive-never-delete)
**(YYYY-MM-DD) [SUPERSEDED]** <prior verdict + why it changed>
```

## Buy-side template — NON-HELD names of interest (watchlist / lean-in / source-call)

The store's job is **decide and direct, not display** (the primary goal). For a name we do **not**
own, the verdict is a grounded **buy-side disposition** — never a "HOLD" (you can't hold what you
don't own). The first token of the verdict must be one of **{BUY-CANDIDATE, WATCH, PASS}**.

```markdown
# <TICKER> — Thesis of Record (watchlist — not held)

**CURRENT VERDICT (YYYY-MM-DD):** <BUY-CANDIDATE | WATCH | PASS> — <one-line why>[ · starter ~$<size> on <dated trigger>  (BUY-CANDIDATE only)] · conviction <x or "none — thin">

**Evidence basis:** <the dated, independent source(s) — or "one technical mention only; thin">
**Independent confirmation ledger:** <each independent GROUP named; "disconfirmers present? …">

## Why it's of interest
## Bull case (stated fairly)   <!-- or "Structural role" for a factor/sector/duration ETF -->
## Dated catalysts
## Disconfirmers / what would make it a PASS
## Range / sizing context (52-wk position; not held) + Buy-side size hint
## Structure (wrapper note)   <!-- ETFs only -->

---
## Superseded history (archive-never-delete)
**(YYYY-MM-DD) [origin]** <who drafted it; PENDING OPERATOR CONFIRMATION; not a trade signal>
```

### Discipline rail (the hard gates — keep `case_file_coverage --discipline` clean)
- **Default is WATCH or PASS.** A draft must *earn* its way up to **BUY-CANDIDATE**: it needs (a) a
  **dated, named, independent** piece of evidence AND **≥2 non-correlated independent signal groups**,
  and (b) a real range/sizing context from live data. If either fails → WATCH (or PASS if negative).
- **Never invent** a size, a trigger, a catalyst date, or a conviction. A **size** appears only with a
  book-fit basis and is always a **starter/stage** (like MP's "~$5–6k start"), never a max; a **trigger**
  is only a real dated catalyst already listed under *Dated catalysts*; **conviction is omitted**
  (say "none — thin"), never set to "low" just to fill the slot.
- **Echoes are not breadth.** Count independent *groups*: "sell-side consensus" is **one** group no
  matter how many desks/PTs; Fundstrat/source-call is one; our own screen is one. Conviction "high"
  requires **≥2 groups** OR **1 group that survived a named disconfirmer**.
- **Staleness parity.** Every buy-side verdict self-degrades to UNKNOWN at the freshness window like a
  held verdict; any price/level in a trigger must be **dated** so a stale buy can't read as live.
- **Factor/sector/duration ETFs** get a structural-role note, not a single-name conviction verdict.

> Note (cross-session): this vocabulary should be reconciled with the Notion Research Queue mirror, and
> the independence-group taxonomy is the upstream input the F2 conviction→size engine wants — coordinate,
> don't fork. Wiring a BUY-CANDIDATE onto the live decision surface is owned by the decision-surface
> session (the VRT Buy-Surfacing Gate); a tidy `.md` verdict does not by itself close the VRT class.

## Population backlog (not done — staged)
Seed a file for each current holding from the live book (`src/positions.json` /
`src/account_positions.json`) and its Notion Research Queue / Live Theses row. Prioritize names that are
(a) candidate funding sources, or (b) near 52-week lows with live theses — exactly where Rail B's
"selling into weakness" near-veto must be able to fire (LEU, and per the 6/17 reconciliation BE / IVES /
UUUU).
