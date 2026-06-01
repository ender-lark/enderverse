#!/usr/bin/env python3
"""End-to-end (with fakes) for ISSUE-05.

Chains the golden combined.json through the real consumer:
    extractor combined.json  ->  build_positions_cache  ->  conviction_sizing_calibrator

Proves (a) the cache drives the real calibrator without massaging, and (b) MONITOR-stance
suppression (the ISSUE-06 fix) fires through the cache path — no live credentials needed.
Runnable directly: `python3 test_issue05_e2e.py`.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_positions_cache as bpc
import conviction_sizing_calibrator as csc
import test_build_positions_golden as golden   # reuse the GOLDEN_COMBINED fixture

# Theses with stance: BMNR + LEU are MONITOR (must be suppressed); the AI/semis
# names are non-MONITOR and large, so they read as above-ceiling, not gaps.
E2E_THESES = [
    {"ticker": "NVDA", "tier": "T1", "lane": "Generational"},
    {"ticker": "MAGS", "tier": "T2", "lane": "AI"},
    {"ticker": "SMH",  "tier": "T2", "lane": "AI"},
    {"ticker": "LEU",  "tier": "T1", "lane": "Generational", "stance": "MONITOR"},
    {"ticker": "BMNR", "tier": "T1", "lane": "Generational", "stance": "MONITOR"},
]


def test_calibrator_imported_locally_not_shadowed():
    # Guard against ISSUE-10: confirm we're exercising the local (patched) calibrator,
    # not a /mnt/project shadow copy.
    here = os.path.dirname(os.path.abspath(__file__))
    assert os.path.abspath(csc.__file__).startswith(here), csc.__file__


def test_extract_transform_calibrate_chain():
    out = bpc.build_positions(golden.GOLDEN_COMBINED, E2E_THESES)
    # Gate at the seam before feeding the consumer.
    assert bpc.validate_positions(out) == []

    report = csc.calibrate(out["positions"], E2E_THESES, sleeve_total=out["sleeve_value"])

    # No false gaps — the exact failure mode ISSUE-05/06 produced.
    assert len(report.critically_below) == 0, [g.ticker for g in report.critically_below]
    assert len(report.below_floor) == 0, [g.ticker for g in report.below_floor]
    assert report.gap_to_close_total == 0, report.gap_to_close_total

    # MONITOR names suppressed (ISSUE-06), exercised through the cache.
    assert {g.ticker for g in report.monitor_suppressed} == {"BMNR", "LEU"}, \
        [g.ticker for g in report.monitor_suppressed]

    # The big AI/semis names show as above-ceiling concentration, not under-deployment.
    assert {g.ticker for g in report.above_ceiling} == {"NVDA", "MAGS", "SMH"}, \
        [g.ticker for g in report.above_ceiling]


def run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"test_issue05_e2e: PASS ({len(tests)} tests — extract->transform->calibrate chain, "
          "MONITOR suppression via the cache, no false gaps)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
