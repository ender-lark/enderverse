# Evidence Pack 2026-07

Generated: 2026-07-02T05:10:18Z

This pack is for Phase A Fable review. It ships the generator, raw Notion snapshots where available, CSV outputs, and one summary MD per artifact. Unknowns remain unknown.

Notion index: https://app.notion.com/p/Evidence-Pack-2026-07-Phase-A-Index-391c50314bb6814db8e3c2031a7f91ce

## Index

- source_hit_rates: Source Call Log hit/miss/open table by source, quality ladder, and horizon.
  - source_hit_rates.csv
  - source_hit_rates_detail.csv
  - source_hit_rates_summary.md
- decision_outcomes: Decisions Log rows joined to local price data where available, with explicit join gaps.
  - decision_outcomes.csv
  - decision_outcomes_costliest_gaps.csv
  - decision_outcomes_summary.md
- missed_moves: Research/opportunity/flow surfaces without ticker-level Decisions Log matches, ranked where foregone dollars are computable.
  - missed_moves.csv
  - missed_moves_summary.md
- feed_reliability: Seed divergence rescan against broker/feed truth.
  - feed_reliability.csv
  - feed_reliability_summary.md
- routine_health: Scheduled routine receipt run/skip/fail history and silent-failure flags.
  - routine_health.csv
  - routine_health_summary.md
- system_inventory: Build-and-forget map across src modules and JSON artifacts.
  - system_inventory.csv
  - system_inventory_summary.md

## Raw Snapshots

- source_call_log: ok - 208 rows, 3 pages
- decisions_log: ok - 257 rows, 3 pages
- research_queue: ok - 111 rows, 2 pages
- system_update_queue: gap - Notion HTTP 404 POST /data_sources/968cfff4-369c-40bb-b748-5633b9ff7685/query: {"object":"error","status":404,"code":"object_not_found","message":"Could not find database with ID: 968cfff4-369c-40bb-b748-5633b9ff7685. Make sure the relevant pages and databases are shared with your integration \"LifeOS cc\".","additional_data":{"integration_id":"36ec5031-4bb6-8109-bd09-00277bf571c6"},"request_id":"09c943b4-b49a-4a08-95db-1d630460d9b7"}

## Reproduce

From repo root:

```powershell
python analysis/evidence_pack_2026-07/generate_evidence_pack.py --repo-root . --out analysis/evidence_pack_2026-07
```

Set `NOTION_TOKEN` to refresh Notion snapshots. Without it, the script falls back to repo caches and writes named gaps.
