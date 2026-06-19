# Dossier Keeper Routine

## Objective

Keep the per-ticker **thesis-of-record** store (`docs/research_dossiers/<T>.md`,
read by `case_file.py`) a **living** system, not a one-time backfill. Every run:
(1) draft a thesis-of-record for any *new* ticker of interest that lacks one, and
(2) **refresh** any dossier that is stale or about to go stale — before
`case_file`'s verdict-freshness rail (`VERDICT_MAX_AGE_DAYS`, 45 days) self-degrades
it to UNKNOWN. This routine drafts and opens a PR for operator review. It does
**not** auto-merge, write buy/sell/sizing recommendations, or bypass review.

## Source (what to work on)

- Worklist engine: `python -m dossier_universe --feed src/latest_cockpit_feed.json --format text`
  - `interest_universe(...)` = the union of *everything of interest*: action/material
    holdings + lean-in / open opportunities + recent source/analyst calls + top
    prospects + parabolic setups + source-call candidates (macro/index/crypto and
    cash sweeps excluded).
  - `keeper_report(...)` returns `to_draft` (missing) and `to_refresh` (stale or
    `refresh_soon`) plus per-ticker `klass`.
- Drafting reference: the existing dossiers (`docs/research_dossiers/LEU.md`,
  `MP.md`, `XLRE.md`) and the template in `docs/research_dossiers/README.md`.

## Normal Mode

1. Run the worklist: `python -m dossier_universe --feed src/latest_cockpit_feed.json --format json`.
2. For each ticker in `to_draft` and `to_refresh`, produce a grounded
   thesis-of-record via the **research -> adversarial-skeptic** pass:
   - Ground in repo data (`account_positions.json` weight/accounts,
     `source_calls.json` + `fundstrat_bible.json` stance/avoid-list,
     `top_prospects.json`) + live fundamentals (data MCP) + web for recent catalysts.
   - Follow the README template and the exact verdict header
     `**CURRENT VERDICT (YYYY-MM-DD):** ...· conviction **<x>**`.
3. Write the files to `docs/research_dossiers/`, then verify with
   `python -m case_file_coverage --feed src/latest_cockpit_feed.json` and a
   `case_file` parse (each new/updated file must read `fresh`).
4. Open a PR for operator review (branch `cc/dossier-keeper-refresh-<date>`).
   Do **not** auto-merge.

## Usage-Constrained Mode

When the user declares a usage-constrained period, cap the batch:

```bash
python -m dossier_universe --feed src/latest_cockpit_feed.json --format text   # inspect only
```

Then draft at most the top few `to_draft` (newest holdings / highest-conviction
lean-ins) and the `to_refresh` items closest to expiry; defer the rest to the next run.

## Rules (honesty + safety — non-negotiable)

- **Do not fabricate.** Ground every claim or omit it; if a real thesis can't be
  grounded, the verdict is `MONITOR - needs operator research`, stating what's missing.
- **Conservative verdicts.** Default to status-quo HOLD for a held name; the most
  aggressive sell-side verdict permitted is `MONITOR / reconsider - operator call`
  — never a bare SELL/EXIT/TRIM.
- **Mark provenance.** Every auto-drafted/auto-refreshed file carries the
  `PENDING OPERATOR CONFIRMATION` origin line — it is not operator-blessed and is
  not a trade signal.
- **Refresh = re-ground, not re-stamp.** Refreshing a stale dossier means re-running
  the research, not just bumping the date; preserve prior verdicts under
  "Superseded history (archive-never-delete)".
- **PR, never auto-merge.** The operator merges. This routine is source-proof
  (`blocks=False`); a missing/stale dossier is coverage debt, never a card blocker.
- Macro/index/crypto proxies and cash sweeps are excluded by the engine — do not
  hand-add equity theses for them.

## Conversational companion (the agent, in chat)

When a new ticker comes up in conversation and `case_file`/`keeper_report` shows it
has no fresh thesis-of-record, the agent drafts one then and there under the same
rules — so "tickers we talk about" are covered immediately, between scheduled runs.
