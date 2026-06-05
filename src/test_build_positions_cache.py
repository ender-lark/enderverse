#!/usr/bin/env python3
"""Unit tests for build_positions_cache.py (ISSUE-05, Chunk 1).

Runnable directly: `python3 test_build_positions_cache.py` -> prints PASS, exit 0.
Covers the transform contract edges; golden-master + e2e come in Chunks 2-3.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_positions_cache as bpc


def _file(positions, source="x.pdf", validation=None):
    f = {"source_file": source, "positions": positions}
    if validation is not None:
        f["validation"] = validation
    return f


def test_date_only():
    assert bpc._date_only("2026-05-31T14:49:00") == "2026-05-31"
    assert bpc._date_only("2026-05-31") == "2026-05-31"
    assert bpc._date_only(None) is None
    assert bpc._date_only("") is None


def test_thesis_universe_uppercases_and_skips_blanks():
    u = bpc._thesis_universe([{"ticker": "nvda"}, {"ticker": " leu "}, {"ticker": ""}, {}])
    assert u == {"NVDA", "LEU"}, u


def test_aggregates_market_value_and_shares_across_accounts():
    combined = {"files": [
        _file([{"symbol": "NVDA", "market_value": 100000.0, "quantity": 470.0, "account_name": "Joint"}]),
        _file([{"symbol": "NVDA", "market_value": 26076.0, "quantity": 126.0, "account_name": "Roth"}]),
    ], "portfolio_summary": {"total_market_value": 126076.0, "total_cash": 0.0, "as_of": "2026-05-31T00:00:00"}}
    out = bpc.build_positions(combined, [{"ticker": "NVDA"}])
    p = out["positions"][0]
    assert p["market_value"] == 126076, p
    assert p["shares"] == 596.0, p
    assert p["account"] == "Multiple", p   # 2 distinct accounts


def test_filters_to_thesis_universe():
    combined = {"files": [_file([
        {"symbol": "NVDA", "market_value": 1000.0, "quantity": 1, "account_name": "A"},
        {"symbol": "GS", "market_value": 9999.0, "quantity": 1, "account_name": "A"},  # not thesis'd
    ])], "portfolio_summary": {"total_market_value": 10999.0, "total_cash": 0.0, "as_of": "2026-05-31"}}
    out = bpc.build_positions(combined, [{"ticker": "NVDA"}])
    assert {p["ticker"] for p in out["positions"]} == {"NVDA"}


def test_uses_outcome_logger_flatten_bridge(monkeypatch):
    called = {"value": False}

    def fake_flatten(doc):
        called["value"] = True
        assert doc == {"source": "extractor"}
        return {
            "snapshot_date": "2026-05-31",
            "sleeve_value": 1000,
            "positions": [
                {"ticker": "NVDA", "market_value": 500.0, "shares": 2, "account": "Joint"},
            ],
        }

    monkeypatch.setattr(bpc.outcome_logger, "flatten_extractor_snapshot", fake_flatten)

    out = bpc.build_positions({"source": "extractor"}, [{"ticker": "NVDA"}])

    assert called["value"] is True
    assert out["snapshot_date"] == "2026-05-31"
    assert out["positions"] == [
        {"ticker": "NVDA", "shares": 2.0, "market_value": 500, "account": "Joint"},
    ]


def test_sleeve_value_includes_cash():
    combined = {"files": [_file([{"symbol": "NVDA", "market_value": 5.0, "quantity": 1, "account_name": "A"}])],
                "portfolio_summary": {"total_market_value": 1909389.0, "total_cash": 12545.0, "as_of": "2026-05-31"}}
    out = bpc.build_positions(combined, [{"ticker": "NVDA"}])
    assert out["sleeve_value"] == 1921934, out["sleeve_value"]


def test_symbol_lowercase_maps_to_uppercase_ticker():
    combined = {"files": [_file([{"symbol": "nvda", "market_value": 5.0, "quantity": 1, "account_name": "A"}])],
                "portfolio_summary": {"total_market_value": 5.0, "total_cash": 0.0, "as_of": "2026-05-31"}}
    out = bpc.build_positions(combined, [{"ticker": "NVDA"}])
    assert out["positions"][0]["ticker"] == "NVDA"


def test_account_rule_single_vs_multiple_vs_aggregate():
    # single account -> that name
    c1 = {"files": [_file([{"symbol": "LEU", "market_value": 5.0, "quantity": 1, "account_name": "Rollover IRA"}])],
          "portfolio_summary": {"total_market_value": 5.0, "total_cash": 0.0, "as_of": "2026-05-31"}}
    assert bpc.build_positions(c1, [{"ticker": "LEU"}])["positions"][0]["account"] == "Rollover IRA"
    # aggregate scope: no account_name -> "Multiple"
    c2 = {"files": [_file([{"symbol": "LEU", "market_value": 5.0, "quantity": 1}])],
          "portfolio_summary": {"total_market_value": 5.0, "total_cash": 0.0, "as_of": "2026-05-31"}}
    assert bpc.build_positions(c2, [{"ticker": "LEU"}])["positions"][0]["account"] == "Multiple"


def test_skips_unpriced_positions():
    combined = {"files": [_file([
        {"symbol": "NVDA", "market_value": 5.0, "quantity": 1, "account_name": "A"},
        {"symbol": "RGHT", "market_value": None, "quantity": None, "account_name": "A"},
    ])], "portfolio_summary": {"total_market_value": 5.0, "total_cash": 0.0, "as_of": "2026-05-31"}}
    out = bpc.build_positions(combined, [{"ticker": "NVDA"}, {"ticker": "RGHT"}])
    assert {p["ticker"] for p in out["positions"]} == {"NVDA"}   # RGHT dropped (no MV)


def test_sorted_by_market_value_desc():
    combined = {"files": [_file([
        {"symbol": "SMALL", "market_value": 10.0, "quantity": 1, "account_name": "A"},
        {"symbol": "BIG", "market_value": 1000.0, "quantity": 1, "account_name": "A"},
    ])], "portfolio_summary": {"total_market_value": 1010.0, "total_cash": 0.0, "as_of": "2026-05-31"}}
    out = bpc.build_positions(combined, [{"ticker": "SMALL"}, {"ticker": "BIG"}])
    assert [p["ticker"] for p in out["positions"]] == ["BIG", "SMALL"]


def test_validation_warnings_collected():
    combined = {"files": [
        {"source_file": "fid.pdf", "validation": {"passed": False, "delta": 42.0}, "positions": []},
        {"source_file": "rh.pdf", "validation": {"all_visible_captured": False}, "positions": []},
        {"source_file": "ok.pdf", "validation": {"passed": True}, "positions": []},
    ], "warnings": ["inputs span more than 24 hours"]}
    w = bpc._validation_warnings(combined)
    joined = " ".join(w)
    assert "fid.pdf" in joined and "rh.pdf" in joined, w
    assert "ok.pdf" not in joined, w          # passing file not warned
    assert "24 hours" in joined, w            # extractor-level warning carried through
    assert len(w) == 3, w


def test_build_from_paths_handles_dict_theses_and_injects_warnings():
    combined = {"files": [
        _file([{"symbol": "NVDA", "market_value": 5.0, "quantity": 1, "account_name": "A"}],
              validation={"passed": False, "delta": 1.0}),
    ], "portfolio_summary": {"total_market_value": 5.0, "total_cash": 0.0, "as_of": "2026-05-31"}}
    theses_dict = {"theses": [{"ticker": "NVDA"}]}   # dict-shaped, not a bare list
    with tempfile.TemporaryDirectory() as d:
        cp, tp = os.path.join(d, "c.json"), os.path.join(d, "t.json")
        json.dump(combined, open(cp, "w"))
        json.dump(theses_dict, open(tp, "w"))
        out, warnings = bpc.build_from_paths(cp, tp)
    assert {p["ticker"] for p in out["positions"]} == {"NVDA"}   # dict theses unwrapped
    assert out["_warnings"] and warnings                          # warning surfaced into output


def run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"test_build_positions_cache: PASS ({len(tests)} tests "
          "— date, universe, aggregate, filter, sleeve+cash, symbol->ticker, "
          "account rule, unpriced skip, sort, warnings, dict-theses+loader)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
