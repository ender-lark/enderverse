# Deep Synthesis Routine

## Objective

Run the Sunday Deep Synthesis pass from existing system records only. This
routine can write a synthesis page when connector access is available, but it
must not invent market evidence, trade recommendations, or outcome patterns.

## Monthly Outcome-Pattern Loop

On the monthly Deep Synthesis pass, or when explicitly requested, run:

```bash
python src/outcome_patterns.py --out src/outcome_patterns.json --format text
```

If live Notion exports for Trade Outcomes or Decisions Log are available, pass
them explicitly:

```bash
python src/outcome_patterns.py --trade-outcomes <trade-outcomes-export.json> --decisions <decisions-log-export.json> --out src/outcome_patterns.json --format text
```

Write the findings into the synthesis page only as system-learning observations.
Rows below the threshold must stay `insufficient sample`; do not force a pattern
from one or two anecdotes.

## Rules

- The detector groups only explicit driver/category tags.
- Prose reasons are not converted into driver tags.
- A pattern requires at least three rows sharing a driver inside a category.
- Findings can inform future review questions and queue priorities; they do not
  execute trades or override current evidence gates.
- Missing Trade Outcomes or Decisions Log exports are `not_checked`, not a clean
  outcome read.
