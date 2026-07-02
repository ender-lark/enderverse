# decision_outcomes

Generated: 2026-07-02T05:08:45Z

- Input source: notion_decisions_log
- Decisions expanded to ticker rows: 930
- Rows with local dated price join: 104
- Rows with named price/join gaps: 826
- Costliest gap candidates emitted: 4

Files:
- decision_outcomes.csv: Decisions Log rows expanded to detected tickers and joined to local price series when available.
- decision_outcomes_costliest_gaps.csv: top under-sizing/missing-target gap candidates with computable foregone P/L.
- generate_evidence_pack.py: generator script for this artifact.

Honesty notes:
- Full Decisions Log rows are fetched through Notion REST when available.
- Most single-name decisions cannot be fully priced from repo-local dated closes; gap_reason names each missing join.
- `pnl_if_acted_on_signal_date_usd` stays blank unless a structured signal date/price exists. It is not inferred from prose.
