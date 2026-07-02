# routine_health

Generated: 2026-07-02T05:32:33Z

- Routines/referenced receipt lanes: 38
- Receipt rows scanned: 500
- Feed cloud proof line: Core background cloud proof: 14/14 scheduled receipts proven; failed latest=0; support monitored=24, support overdue=0.
- Rows with silent-failure flags: 7

Files:
- routine_health.csv: run/skip/fail history by routine from receipt and automation status caches.
- generate_evidence_pack.py: generator script for this artifact.

Honesty notes:
- A started receipt without a later final receipt is flagged; the script does not assume success.
- `failed_count` includes historical failures even when latest status recovered.
