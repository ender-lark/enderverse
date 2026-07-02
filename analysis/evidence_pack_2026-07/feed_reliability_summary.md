# feed_reliability

Generated: 2026-07-02T05:32:33Z

- Live divergence rows: 5
- Seed cases checked: target_drift false missing, Fundstrat false staleness, HOOD option-risk render.

Files:
- feed_reliability.csv: live divergence table from seed-case rescan.
- generate_evidence_pack.py: generator script for this artifact.

Honesty notes:
- Broker/account_positions is treated as truth for held-name current exposure.
- Feed internal freshness surfaces are compared against each other; this does not prove the external FS Ingest Marker state unless the marker is separately fetched.
