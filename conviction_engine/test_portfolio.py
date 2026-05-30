"""Unit tests for the portfolio plug (S7).

Run:  python -m pytest src/test_portfolio.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from validators import validate_items
from portfolio import portfolio_reader, build_portfolio_source


POSITIONS = [
    {"ticker": "SMH", "pct": 9.9, "shares": 120, "value": 185000,
     "account": "Parents Fidelity", "owner": "Parents", "sleeve": "AI"},
    {"ticker": "LEU", "pct": 4.89, "shares": 300, "value": 91000,
     "account": "SKB Schwab", "owner": "SKB", "sleeve": "nuclear"},
    {"ticker": "GLD", "shares": 50, "account": "Parents Fidelity"},   # no pct
]


def _by_subject(rows):
    out = {}
    for r in rows:
        out.setdefault(r["subject"], []).append(r)
    return out


# --------------------------------------------------------------------------- #
# reader
# --------------------------------------------------------------------------- #
def test_count_and_kind():
    rows = portfolio_reader(POSITIONS)
    assert len(rows) == 3
    assert all(r["kind"] == "position" for r in rows)


def test_position_card_content_and_data():
    smh = _by_subject(portfolio_reader(POSITIONS))["SMH"][0]
    assert smh["content"] == "SMH 9.90% Owned"
    d = smh["data"]
    assert d["pct"] == 9.9 and d["shares"] == 120 and d["value"] == 185000
    assert d["account"] == "Parents Fidelity" and d["owner"] == "Parents"
    assert d["sleeve"] == "AI"


def test_missing_pct_content():
    gld = _by_subject(portfolio_reader(POSITIONS))["GLD"][0]
    assert gld["content"] == "GLD Owned"
    assert gld["data"]["pct"] is None


def test_ticker_less_skipped():
    rows = portfolio_reader([{"pct": 1.0, "account": "X"},          # no ticker
                             {"ticker": "SMH", "pct": 9.9}])
    assert [r["subject"] for r in rows] == ["SMH"]


def test_same_ticker_multiple_accounts_kept_separate():
    rows = portfolio_reader([
        {"ticker": "NVDA", "pct": 3.0, "account": "Parents Fidelity"},
        {"ticker": "NVDA", "pct": 2.0, "account": "SKB Schwab"},
    ])
    assert len(rows) == 2
    accounts = sorted(r["data"]["account"] for r in rows)
    assert accounts == ["Parents Fidelity", "SKB Schwab"]


def test_as_of_timestamp():
    rows = portfolio_reader([{"ticker": "SMH", "pct": 9.9}], as_of="2026-05-27")
    assert rows[0]["timestamp"] == "2026-05-27"


# --------------------------------------------------------------------------- #
# wired plug -> dials (incl. cadence) + valid Contract-A cards
# --------------------------------------------------------------------------- #
def test_build_source_dials_and_valid_cards():
    src = build_portfolio_source(POSITIONS)
    assert src.name == "portfolio"
    assert src.trust_weight == 0.95
    assert src.independence_group == "own"
    assert src.cadence == "on_refresh"          # not a daily feed -> no stale false-alarm

    items = src.fetch()
    assert len(items) == 3
    assert validate_items(items)["bad"] == []
    assert all(i.kind == "position" for i in items)
    smh = next(i for i in items if i.subject == "SMH")
    assert smh.content == "SMH 9.90% Owned"


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-q"]))
