#!/usr/bin/env python3
"""Unit tests for the positions-cache staleness guard (ISSUE-05 Part 2).

Uses an injected `today` so results are deterministic regardless of the host clock.
Runnable directly: `python3 test_positions_freshness.py`.
"""
from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daily_preflight as dp

T = date(2026, 6, 1)


def test_fresh_today():
    s, age, _ = dp._positions_freshness({"snapshot_date": "2026-06-01"}, today=T)
    assert s == "fresh" and age == 0, (s, age)


def test_fresh_within_window():
    s, age, _ = dp._positions_freshness({"snapshot_date": "2026-05-27"}, today=T)  # 5 days
    assert s == "fresh" and age == 5, (s, age)


def test_fresh_exactly_at_limit():
    s, age, _ = dp._positions_freshness({"snapshot_date": "2026-05-25"}, today=T)  # 7 days == limit
    assert s == "fresh" and age == 7, (s, age)


def test_stale_beyond_window():
    s, age, msg = dp._positions_freshness({"snapshot_date": "2026-05-15"}, today=T)  # 17 days
    assert s == "stale" and age == 17, (s, age)
    assert "re-upload" in msg.lower(), msg


def test_unknown_missing_date():
    s, age, msg = dp._positions_freshness({"sleeve_value": 1}, today=T)
    assert s == "unknown" and age is None, (s, age)
    assert "snapshot_date" in msg, msg


def test_unknown_unparseable_date():
    s, _, _ = dp._positions_freshness({"snapshot_date": "yesterday"}, today=T)
    assert s == "unknown", s


def test_unknown_future_date():
    s, age, _ = dp._positions_freshness({"snapshot_date": "2026-06-05"}, today=T)
    assert s == "unknown" and age == -4, (s, age)


def test_bare_list_is_unknown():
    s, _, _ = dp._positions_freshness([{"ticker": "NVDA"}], today=T)
    assert s == "unknown", s


def test_datetime_snapshot_parsed_by_date_part():
    s, age, _ = dp._positions_freshness({"snapshot_date": "2026-05-31T14:49:00"}, today=T)
    assert s == "fresh" and age == 1, (s, age)   # the 5/31 book under a 6/1 clock


def run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"test_positions_freshness: PASS ({len(tests)} tests "
          "— fresh / at-limit / stale / unknown / future / datetime-snapshot / bare-list)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
