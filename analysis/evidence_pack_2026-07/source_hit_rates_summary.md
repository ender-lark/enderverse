# source_hit_rates

Generated: 2026-07-02T05:32:33Z

- Input source: notion_source_call_log
- Calls analyzed: 208
- Group cells: 40
- Low-n cells flagged: 38
- Open/pending/unscored calls: 205

Files:
- source_hit_rates.csv: source x quality ladder x horizon hit/miss/open table with n per cell.
- source_hit_rates_detail.csv: one row per source call used in the grouping.
- generate_evidence_pack.py: generator script for this artifact.

Honesty notes:
- D/Vague calls are retained in the denominator table; they are not averaged away.
- Hit rates are blank unless there is a hit+miss denominator; low-n and low-scored-n are explicit flags.
