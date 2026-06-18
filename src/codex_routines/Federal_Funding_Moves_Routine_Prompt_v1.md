# Federal Funding Moves Routine

## Objective

Find federal awards, loans, contracts, grants, letters of intent, and program
funding announcements that can change Investing OS buy/hold/research/watch
posture. Rank direct public-company beneficiaries first, route private or
read-through items as watch context, and preserve risk and conditionality.

This routine is source intake only. It never executes trades, sizes positions,
or creates a direct buy/sell path. MONITOR names such as BMNR, LEU, UUUU, and MP
stay review-only unless the existing Investing OS monitor re-entry path later
confirms defined-risk fields.

## Start Of Run

1. Append a started receipt for the exact automation id:
   `python src/cloud_routine_receipts.py --routine-id <automation-id> --status started --run-source scheduled --summary "federal funding move scan started"`
2. Read `AGENTS.md`, `docs/investing_os_primary_goals.md`, this routine prompt,
   `src/theses.json`, current `src/signal_log.json`, current
   `src/research_queue.json`, and current `src/federal_funding_moves.json` when
   present.
3. Use `--run-source scheduled` on every started, success, and failed receipt
   written by this scheduled automation.

## Source Priority

Use primary official sources first:

- War/Defense: War.gov Today in DOW, Releases, Contracts, Air Force, Space
  Force, Navy, Army, DARPA, DIU, OSC, and other official military award pages.
- Commerce/CHIPS/NIST: CHIPS awards, definitive agreements, letters of intent,
  semiconductor supply-chain funding, and materials R&D awards.
- Energy/critical minerals: DOE, LPO, OCED, EERE, NNSA, NRC, EXIM, DFC, USGS,
  and official critical-minerals announcements.
- DHS/CBP, NASA, NSF TIP, Treasury/IRS/IRA, DOT, and other federal program
  pages when they can affect material public tickers or portfolio themes.
- USAspending, SAM.gov, FPDS, or agency procurement pages only when they add
  award evidence not available from press releases.

Secondary sources such as Reuters, GovCon Wire, Stock Titan, company IR, or
market-data pages can be used only to verify market reaction, map public
tickers, or fill read-through context. They do not replace the primary award
source when a primary source is available.

## Market Filter

For each candidate, ask:

- Is a public company the direct recipient, or is the recipient private with
  only read-through exposure?
- Is the award large enough or strategically important enough to change
  materiality, timing, conviction, risk, or research priority?
- Is the funding conditional, not yet closed, subject to due diligence, an IDIQ,
  a small modification, or an undisclosed option?
- Does the item map to active holdings, live theses, current watch queues, or
  high-impact strategic themes such as AI infrastructure, semis, defense
  autonomy, nuclear/uranium/HALEU, rare earths, power, space, or critical
  minerals?
- What evidence would invalidate or graduate the watch: final close, task-order
  dollars, offtake/customer detail, capex budget, dilution, permits, execution
  risk, price reaction, or same-session flow?

Suppress generic political noise, immaterial contract maintenance, duplicate
headlines, non-public private-company awards with no useful ticker read-through,
and awards where the source cannot be verified.

## Priority And Routing

- `high`: direct public-company recipient, material award size or strategic
  importance, and current Investing OS relevance.
- `medium`: private recipient with useful public read-through, public-company
  backlog support, or smaller direct award that may matter with follow-on
  evidence.
- `low`: real award, but too small or too indirect to affect posture.

Use directness:

- `direct_public`: named public company is the direct beneficiary.
- `public_read_through`: public tickers benefit indirectly, but recipient or
  contract path is not clean enough for direct beneficiary treatment.
- `private_read_through`: direct recipient is private; public tickers are only
  investors, suppliers, customers, peers, or theme beneficiaries.
- `contract_backlog`: public company gets real backlog/support but the item is
  too small, undisclosed, option-only, or long-cycle to create an urgent
  capital decision.
- `watch_only`: useful portfolio or theme context only.
- `ignore`: verified but not useful for Investing OS.

Use actionability:

- `review_now`: direct, material, public-company item that could change today's
  review priority. Do not use for MONITOR names unless it remains review-only.
- `research_review`: direct or semi-direct item that should enter Research
  Queue review.
- `watch`: Signal Log context only.
- `ignore`: do not write derived Signal Log or Research Queue rows.

## Compact JSON Contract

After the scan, prepare one compact JSON payload. Do not store raw article
bodies. Include links and short summaries only.

```json
{
  "as_of": "YYYY-MM-DD",
  "generated_at": "YYYY-MM-DDTHH:MM:SSZ",
  "rows": [
    {
      "date": "YYYY-MM-DD",
      "agency": "Department / office",
      "program": "Program or office",
      "recipient": "Company or entity",
      "award_details": "$725M conditional loan commitment for ...",
      "public_tickers": ["UUUU"],
      "priority": "high",
      "directness": "direct_public",
      "actionability": "research_review",
      "investing_angle": "One-sentence so-what for Investing OS.",
      "risks": ["conditional close", "execution risk"],
      "next_trigger": "What would graduate/invalidate the signal.",
      "source_urls": ["https://official-source.example/..."],
      "source_quality": "primary"
    }
  ]
}
```

If the scan completes and finds no verified useful rows, write:

```json
{"as_of":"YYYY-MM-DD","generated_at":"...","rows":[]}
```

Do not fabricate rows to avoid an empty scan.

## Write And Verify

Pipe the compact JSON into the normalizer:

```powershell
python src/federal_funding_intake.py --stdin-json --out src/federal_funding_moves.json --summary src/federal_funding_intake_summary.json --signal-log-out src/signal_log.json --research-out src/research_queue.json --theses src/theses.json --merge-existing
```

Validate changed caches:

```powershell
python src/federal_funding_intake.py --validate src/federal_funding_moves.json
python src/signal_log_intake.py --validate src/signal_log.json
python src/research_queue_intake.py --validate src/research_queue.json
python src/cloud_routine_receipts.py --validate --format text
```

If Notion write access is available and a row needs live workflow tracking,
write only the compact Research Queue or Signal Log equivalent, then fetch the
live page/row back and verify title, ticker, status, and key finding before
claiming the Notion write succeeded. If Notion is unavailable, the repo cache is
still the source input and the missing Notion mirror stays not checked.

## End Of Run

Append a success or failed receipt with `--run-source scheduled` and a compact
summary: sources checked, verified rows, direct public rows, research rows,
Signal Log rows, Notion write/readback status, dark or failed sources, and
blockers.

Use the safe helper when routine-owned files changed:

```powershell
python src/cloud_routine_commit.py --message "Federal funding moves scheduled run" --push --format text
```

The helper must stage only routine-owned files and leave unrelated dirty files
untouched. If the push fails, report it.
