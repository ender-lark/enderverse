# Top Prospects Auto-Research Routine

## Objective

Move uncorroborated Top Prospects into the Research Queue quickly enough that
off-hours workers can validate, disconfirm, or discard them before they become
stale. This routine is a queue bridge only. It does not write buy/sell/sizing
recommendations and does not bypass Research Queue review.

## Source

- Canonical cache: `src/top_prospects.json`
- Bridge script: `python src/prospect_autoresearch.py`
- Destination: Notion Research Queue and `src/top_prospects.json` cache metadata

## Normal Mode

After the usage reset, run in throughput mode:

```bash
python src/prospect_autoresearch.py --min-conviction BUILDING --max-items 8
```

This queues the best uncorroborated prospects first by urgency, urgency score,
conviction, conviction score, and direction. It marks queued prospects as
`Auto-research queued` so later runs do not duplicate them.

## Usage-Constrained Mode

When the user declares a temporary usage-constrained period, run only a dry-run
or HOT/ACT_NOW pass:

```bash
python src/prospect_autoresearch.py --dry-run --min-urgency HOT --max-items 5
python src/prospect_autoresearch.py --min-urgency HOT --max-items 2
```

If the dry-run selects zero rows, do not queue lower-conviction prospects during
the constrained period.

## Rules

- Use `--dry-run` before live writes when changing thresholds.
- Do not queue all uncorroborated prospects blindly.
- Do not queue snippet-only, unsupported, or stale promotional context.
- Avoid duplicate work by skipping rows with `research_queue_page_id`.
- If a Notion write fails, do not flip `corroboration`; report the blocker.
- Missing source pulls stay dark/not_checked; never checked clear.

## Verification

Run:

```bash
python src/prospect_autoresearch.py --self-test
python src/prospect_autoresearch.py --dry-run --min-conviction BUILDING --max-items 5
```
