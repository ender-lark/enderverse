# missed_moves

Generated: 2026-07-02T05:32:33Z

- Candidate rows: 217
- Rows with no matching Decisions Log ticker: 40
- Rows with computable foregone dollars: 9
- Rows with positive/rankable foregone gains: 0

Files:
- missed_moves.csv: surfaced-but-not-decision-matched queue, opportunity, prospect, and flow rows.
- generate_evidence_pack.py: generator script for this artifact.

Honesty notes:
- Matching is ticker-level only; it does not claim a semantic decision join.
- Foregone dollars are emitted only when a structured flag price, current price, and target gap exist.
- Negative returns are retained as loss-avoided/no-foregone-gain rows, not ranked as costly missed gains.
- Rows without those structured fields remain in the table with a gap_reason.
