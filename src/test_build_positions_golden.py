#!/usr/bin/env python3
"""Golden-master + schema-validator tests for build_positions_cache.py (ISSUE-05, Chunk 2).

The golden-master is a realistic synthetic --combined extract (Fidelity per-account,
Schwab aggregate, Robinhood per-account, with cash, a non-thesis'd name, and an
unpriced right). The transform must reproduce EXACTLY the expected positions.json.
If the real 5/31 combined.json is supplied later, swap GOLDEN_COMBINED for it and
update GOLDEN_EXPECTED to the hand-verified result for a stronger oracle.

Runnable directly: `python3 test_build_positions_golden.py`.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_positions_cache as bpc


# ----------------------------------------------------------------- the oracle
GOLDEN_COMBINED = {
    "schema_version": "2.0",
    "files": [
        {
            "source_file": "Parents_fidelity.pdf",
            "validation": {"passed": True},
            "positions_scope": "per_account",
            "positions": [
                {"symbol": "NVDA", "description": "NVIDIA CORP", "market_value": 100000.0,
                 "quantity": 470.0, "account_name": "Joint WROS"},
                {"symbol": "NVDA", "description": "NVIDIA CORP", "market_value": 26076.0,
                 "quantity": 126.0, "account_name": "Roth IRA"},
                {"symbol": "MAGS", "description": "ROUNDHILL MAG 7 ETF", "market_value": 172152.0,
                 "quantity": 2435.01, "account_name": "Joint WROS"},
                {"symbol": "GS", "description": "GOLDMAN SACHS", "market_value": 12253.0,
                 "quantity": 12.0, "account_name": "Joint WROS"},          # NOT thesis'd -> excluded
                {"symbol": "RGHT", "description": "SOME RIGHT", "market_value": None,
                 "quantity": None, "account_name": "Joint WROS", "flags": ["unpriced"]},  # skipped
            ],
        },
        {
            "source_file": "Parents_schwab.pdf",
            "validation": {"passed": True},
            "positions_scope": "aggregate",                                 # no account_name on rows
            "positions": [
                {"symbol": "LEU", "description": "CENTRUS ENERGY", "market_value": 93143.0,
                 "quantity": 511.0},
                {"symbol": "SMH", "description": "VANECK SEMI ETF", "market_value": 170734.0,
                 "quantity": 285.05},
            ],
        },
        {
            "source_file": "SKB_rh.pdf",
            "validation": {"all_visible_captured": True},                   # Robinhood-style
            "positions_scope": "per_account",
            "positions": [
                {"symbol": "BMNR", "description": "BITMINE", "market_value": 50000.0,
                 "quantity": 1000.0, "account_name": "Individual"},
                {"symbol": "DOGE", "description": "Dogecoin", "asset_type": "crypto",
                 "market_value": 5000.0, "quantity": 12345.0, "account_name": "Individual"},  # not thesis'd
            ],
        },
    ],
    "portfolio_summary": {
        # sum of all priced positions: 100000+26076+172152+12253+93143+170734+50000+5000 = 629358
        "total_market_value": 629358.0,
        "total_cash": 12545.0,
        "as_of": "2026-05-31T14:49:00",
    },
}

GOLDEN_THESES = [{"ticker": "NVDA"}, {"ticker": "MAGS"}, {"ticker": "LEU"},
                 {"ticker": "SMH"}, {"ticker": "BMNR"}]

GOLDEN_EXPECTED = {
    "snapshot_date": "2026-05-31",
    "sleeve_value": 641903,                                                 # 629358 + 12545
    "positions": [
        {"ticker": "MAGS", "shares": 2435.01, "market_value": 172152, "account": "Joint WROS"},
        {"ticker": "SMH",  "shares": 285.05,  "market_value": 170734, "account": "Multiple"},
        {"ticker": "NVDA", "shares": 596.0,   "market_value": 126076, "account": "Multiple"},
        {"ticker": "LEU",  "shares": 511.0,   "market_value": 93143,  "account": "Multiple"},
        {"ticker": "BMNR", "shares": 1000.0,  "market_value": 50000,  "account": "Individual"},
    ],
}


def test_golden_master_exact():
    out = bpc.build_positions(GOLDEN_COMBINED, GOLDEN_THESES)
    assert out == GOLDEN_EXPECTED, (
        "transform diverged from the golden master:\n"
        f"  got:      {out}\n  expected: {GOLDEN_EXPECTED}")


def test_golden_output_passes_validator():
    out = bpc.build_positions(GOLDEN_COMBINED, GOLDEN_THESES)
    errs = bpc.validate_positions(out)
    assert errs == [], errs


# ----------------------------------------------------------------- validator negatives
def test_validator_flags_missing_and_bad_fields():
    bad = {"positions": [{"ticker": "", "market_value": -5, "shares": "x", "account": ""}]}
    errs = bpc.validate_positions(bad)
    joined = " | ".join(errs)
    assert "snapshot_date" in joined, joined
    assert "sleeve_value" in joined, joined
    assert "ticker must be" in joined, joined
    assert "market_value must be" in joined, joined
    assert "shares must be" in joined, joined
    assert "account must be" in joined, joined


def test_validator_flags_duplicate_ticker():
    dup = {"snapshot_date": "2026-05-31", "sleeve_value": 100,
           "positions": [
               {"ticker": "NVDA", "shares": 1, "market_value": 10, "account": "A"},
               {"ticker": "NVDA", "shares": 1, "market_value": 10, "account": "B"},
           ]}
    errs = bpc.validate_positions(dup)
    assert any("duplicate" in e for e in errs), errs


def test_validator_flags_subset_exceeding_book():
    impossible = {"snapshot_date": "2026-05-31", "sleeve_value": 100,
                  "positions": [{"ticker": "NVDA", "shares": 1, "market_value": 500, "account": "A"}]}
    errs = bpc.validate_positions(impossible)
    assert any("exceeds sleeve_value" in e for e in errs), errs


def test_validator_accepts_clean():
    good = {"snapshot_date": "2026-05-31", "sleeve_value": 1000,
            "positions": [{"ticker": "NVDA", "shares": 1.0, "market_value": 500, "account": "Joint"}]}
    assert bpc.validate_positions(good) == []


def run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"test_build_positions_golden: PASS ({len(tests)} tests "
          "— golden-master exact match + validator positive/negative)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
