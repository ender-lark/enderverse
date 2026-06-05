# Research Action Promotion

## Objective

Prevent time-sensitive Research Queue work from staying visible only in the
From Research lane.

## Rule

Ordinary research remains `research_review` with `action_state=RESEARCH`.

Non-MONITOR research rows become `research_act_now` with
`action_state=ACT_NOW` when they have either:

- a structured near-term `days_out` within the research horizon
- an explicit urgent field such as `urgency`, `action_state`, `action`,
  `recommendation`, or `status` set to ACT_NOW / urgent / today / now

`feed_assembler` keeps the row in `research_actions` for context and also
copies it into `actions` unless that ticker is already represented by a sharper
action or catalyst.

## Guardrails

- MONITOR-stance rows stay review-only and never become an add nudge.
- Existing action/catalyst rows win by ticker.
- Promotion is a surfacing rule, not a trade recommendation.
- The promoted row still carries the gate hook and missing-evidence fields.
