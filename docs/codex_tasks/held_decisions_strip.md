# Codex Pack 3 Amendment: T9 Held-Decisions Strip

Operator GO'd 2026-06-13. Builds on merged PR#15 trigger spine. Suggested id T9 - renumber if taken.

## Task 0

Claim T9 on docs/WORKBOARD.md per the claim protocol before editing.

Files owned: src/held_decisions.json; src/held_decisions.py; src/test_held_decisions.py; strip render block in src/cockpit_html_gen.py (+ test); companion entries in src/trigger_registry.json.

## Purpose

Surface operator-PARKED decision packets with review-by dates on the dash, and ping the operator when the date arrives - the missing third alert category (system decision cards and market triggers exist; deliberately-parked operator decisions don't).

## 1) Data Contract

`src/held_decisions.json` single owner: `held_decisions.py` CLI.

Array of packets:

```json
{
  "id": "string",
  "title": "string",
  "notion_url": "string",
  "parked_date": "YYYY-MM-DD",
  "review_by": "YYYY-MM-DD, America/New_York",
  "status": "held|reviewed|released|reparked",
  "log": [
    {"at": "timestamp", "action": "string", "note": "string"}
  ]
}
```

CLI:

```text
python src/held_decisions.py --add / --resolve <id> --action go|kill|repark [--new-date] / --list
```

`--add` also registers a companion `date_event` trigger in `trigger_registry.json`:

```text
id: held-review-<id>
event: held_decision_review
date: review_by
```

`--resolve` cancels/fires that trigger. Atomic writes, same pattern as `trigger_check.py`.

## 2) Render Contract

Render a "Held for you" strip in `cockpit_html_gen.py`.

Placement: adjacent to TODAY-DECIDE, visually distinct from research/queue views.

Per item:

- title linked to `notion_url`
- `review_by`
- color green before date, amber on date by NY time, red past date
- count badge

Empty list renders nothing.

`held_decisions.json` missing/unreadable renders one warning line: `held decisions: not checked`.

Never silently blank on unreadable file; this is an honesty rail.

Date logic must be date-rot-safe in tests, with no hardcoded today.

## 3) Push

Use existing spine only.

`trigger_check.py` already evaluates `date_event`; confirm `held_decision_review` events produce a Pushover ping on `review_by` morning, plus one overdue escalation if still `held` the next day, max one per day.

No new notification code paths.

## 4) Seed Payload

Ship with these three, all with `review_by` 2026-06-14:

- `sunday-rebalance-packet` - "Full-book rebalance (Council synthesis)" - https://app.notion.com/p/37ec50314bb6810e861dcd6f631f61c4
- `sunday-geo-risk-register-v0` - "Geo Risk Register v0 (Power & Policy)" - https://app.notion.com/p/37ec50314bb681a3a6aedaa13e35664d
- `sunday-policy-money-map-v0` - "Policy Money Map v0 (Power & Policy)" - https://app.notion.com/p/37ec50314bb681a99a3ef660dcb00959

All three log entries note: convergence page = https://app.notion.com/p/37ec50314bb681f88292d11876b0bd66

## 5) Guardrails

- EXCLUSIVITY: only dated, operator-parked decision packets. Never auto-mirror Research Queue, System Update Queue, or any other list. If it has no review date and no operator parking action, it does not belong here.
- Items leave the strip ONLY via `--resolve` with an explicit operator disposition (`go`, `kill`, or `repark`), recorded in the log. Nothing silently disappears.
- A strip entry is information, not authorization: resolving a packet never stages or executes anything.

## 6) Acceptance

- Seeded file renders 3 green items today and amber on 2026-06-14 with frozen-clock tests for before/on/after.
- CLI add/resolve round-trip includes companion trigger lifecycle.
- Unreadable-file warning renders.
- Zero regressions in existing golden renders.
- Suite green.
- WORKBOARD updated.
- Completion report ends with the Wrap Block.

## Not In Scope

Generic alert framework, Notion auto-sync, new push channels, queue mirroring.
