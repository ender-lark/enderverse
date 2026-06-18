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

## Population backlog (not done — staged)
Seed a file for each current holding from the live book (`src/positions.json` /
`src/account_positions.json`) and its Notion Research Queue / Live Theses row. Prioritize names that are
(a) candidate funding sources, or (b) near 52-week lows with live theses — exactly where Rail B's
"selling into weakness" near-veto must be able to fire (LEU, and per the 6/17 reconciliation BE / IVES /
UUUU).
