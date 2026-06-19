# Dossier Keeper Routine

## Objective

Keep the per-ticker **thesis-of-record** store (`docs/research_dossiers/<T>.md`,
read by `case_file.py`) a **living** system, not a one-time backfill. Every run:
(1) draft a thesis-of-record for any *new* ticker of interest that lacks one, and
(2) **refresh** any dossier that is stale or about to go stale — before
`case_file`'s verdict-freshness rail (`VERDICT_MAX_AGE_DAYS`, 45 days) self-degrades
it to UNKNOWN. This routine drafts, validates, and direct-commits the dossier
store through `cloud_routine_commit.py --push`; every drafted verdict remains
`PENDING OPERATOR CONFIRMATION` and is not a trade signal.

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
2. Select a capped batch: prioritize `to_refresh` items closest to expiry, then
   only the top few `to_draft` names by signal strength. Do not bulk-draft the
   full backlog in one run; defer the rest to the next schedule.
3. For each selected ticker, produce a grounded
   thesis-of-record via the **research -> adversarial-skeptic** pass:
   - Ground in repo data (`account_positions.json` weight/accounts,
     `source_calls.json` + `fundstrat_bible.json` stance/avoid-list,
     `top_prospects.json`) + live fundamentals (data MCP) + web for recent catalysts.
   - Follow the README template and the exact verdict header
     `**CURRENT VERDICT (YYYY-MM-DD):** ...· conviction **<x>**`.
4. Write the files to `docs/research_dossiers/`, then verify with
   `python -m case_file_coverage --feed src/latest_cockpit_feed.json` and a
   `case_file` parse (each new/updated file must read `fresh`).
5. Run `cd src && python -m case_file_coverage --discipline`. If it flags
   anything, block the commit and skip or fix the flagged file before rerunning.
   Never commit a flagged dossier.
6. Confirm every drafted/refreshed file contains `PENDING OPERATOR CONFIRMATION`,
   then direct-commit only allowed routine-owned changes with:
   `python src/cloud_routine_commit.py --message "Dossier keeper scheduled run" --push --format text`.

## Scheduled Batch Cap

Every scheduled run is capped, even outside usage-constrained periods:

```bash
python -m dossier_universe --feed src/latest_cockpit_feed.json --format text   # inspect only
```

Then draft at most the closest-expiry `to_refresh` items plus the top few
`to_draft` names (newest holdings / highest-conviction lean-ins). Defer the rest
to the next run instead of bulk-writing the backlog.

## Rules (honesty + safety — non-negotiable)

- **Do not fabricate.** Ground every claim or omit it; if a real thesis can't be
  grounded, the verdict is `MONITOR - needs operator research`, stating what's missing.
- **Held-name vocabulary.** HELD names use the held rail (`hold`, `add`, `trim`,
  `exit`). Default to status-quo HOLD; any sell-side `trim`/`exit` read is one
  grounded evidence echo pending operator confirmation, never an executable trade
  signal.
- **Mark provenance.** Every auto-drafted/auto-refreshed file carries the
  `PENDING OPERATOR CONFIRMATION` origin line — it is not operator-blessed and is
  not a trade signal.
- **Refresh = re-ground, not re-stamp.** Refreshing a stale dossier means re-running
  the research, not just bumping the date; preserve prior verdicts under
  "Superseded history (archive-never-delete)".
- **Direct commit only after hard gates.** `docs/research_dossiers/` is allowed
  in `cloud_routine_commit.py`, but only after every changed dossier carries
  `PENDING OPERATOR CONFIRMATION` and `case_file_coverage --discipline` is clean.
  If the lint flags anything, skip or fix the file first. This routine is
  source-proof (`blocks=False`); a missing/stale dossier is coverage debt, never
  a card blocker.
- Macro/index/crypto proxies and cash sweeps are excluded by the engine — do not
  hand-add equity theses for them.

## Conversational companion (the agent, in chat)

When a new ticker comes up in conversation and `case_file`/`keeper_report` shows it
has no fresh thesis-of-record, the agent drafts one then and there under the same
rules — so "tickers we talk about" are covered immediately, between scheduled runs.
