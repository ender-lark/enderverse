"""Unit tests for the uw_macro plug (S3).

Run:  python -m pytest src/test_uw_macro.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from validators import validate_items
from uw_macro import (
    curve_spread,
    uw_macro_reader,
    build_uw_macro_source,
)


SNAP = {
    "rates": {
        "2Y":  {"value": 3.95, "value_5d_ago": 3.98},
        "10Y": {"value": 4.45, "value_5d_ago": 4.48},
        "30Y": {"value": 4.80, "value_5d_ago": 4.82},
    },
    "levels": {
        "DXY":  {"value": 99.2, "value_5d_ago": 100.5},
        "VIX":  {"value": 17.2, "value_5d_ago": 15.0},
        "MOVE": {"value": 95.0, "value_5d_ago": 92.0},
    },
}


def _by_subject(rows):
    return {r["subject"]: r for r in rows}


# --------------------------------------------------------------------------- #
# curve_spread
# --------------------------------------------------------------------------- #
def test_curve_spread_value_and_change():
    spread, chg = curve_spread(SNAP["rates"], "2Y", "10Y")
    assert spread == pytest.approx(50.0)     # (4.45 - 3.95) * 100
    assert chg == pytest.approx(0.0)         # same spread 5d ago


def test_curve_spread_missing_leg_returns_none():
    assert curve_spread({"10Y": {"value": 4.45}}, "2Y", "10Y") is None


def test_curve_spread_missing_5d_gives_none_change():
    rates = {"2Y": {"value": 3.95}, "10Y": {"value": 4.45}}
    spread, chg = curve_spread(rates, "2Y", "10Y")
    assert spread == pytest.approx(50.0)
    assert chg is None


# --------------------------------------------------------------------------- #
# uw_macro_reader — rate / spread / level cards
# --------------------------------------------------------------------------- #
def test_reader_card_count_and_kind():
    rows = uw_macro_reader(SNAP, as_of="2026-05-29")
    # 3 rates + 2 spreads + 3 levels
    assert len(rows) == 8
    assert all(r["kind"] == "macro" for r in rows)
    assert all(r["timestamp"] == "2026-05-29" for r in rows)


def test_reader_rate_card_content_and_data():
    r = _by_subject(uw_macro_reader(SNAP))["10Y"]
    assert r["content"] == "10Y 4.45% (-3bp 5d)"
    assert r["data"]["chg_5d"] == pytest.approx(-3.0)
    assert r["data"]["unit"] == "bp" and r["data"]["metric"] == "rate"


def test_reader_spread_cards():
    rows = _by_subject(uw_macro_reader(SNAP))
    assert rows["2s10s"]["content"] == "2s10s +50bp (+0bp 5d)"
    assert rows["2s10s"]["data"]["value"] == pytest.approx(50.0)
    assert rows["10s30s"]["content"] == "10s30s +35bp (+1bp 5d)"
    assert rows["10s30s"]["data"]["metric"] == "spread"


def test_reader_level_cards():
    rows = _by_subject(uw_macro_reader(SNAP))
    assert rows["DXY"]["content"] == "DXY 99.2 (-1.3 5d)"
    assert rows["DXY"]["data"]["chg_5d"] == pytest.approx(-1.3)
    assert rows["VIX"]["content"] == "VIX 17.2 (+2.2 5d)"
    assert rows["MOVE"]["content"] == "MOVE 95 (+3.0 5d)"
    assert rows["MOVE"]["data"]["unit"] == "pt"


def test_reader_missing_5d_omits_delta_tail():
    rows = uw_macro_reader({"rates": {"10Y": {"value": 4.45}}})
    assert len(rows) == 1
    assert rows[0]["content"] == "10Y 4.45%"
    assert rows[0]["data"]["chg_5d"] is None


def test_reader_skips_spread_when_leg_missing():
    rows = uw_macro_reader({"rates": {"10Y": {"value": 4.45, "value_5d_ago": 4.48}}})
    subjects = [r["subject"] for r in rows]
    assert subjects == ["10Y"]                # no 2s10s / 10s30s without 2Y / 30Y


def test_reader_skips_card_with_no_value():
    rows = uw_macro_reader({"levels": {"VIX": {"value": None, "value_5d_ago": 15.0}}})
    assert rows == []


# --------------------------------------------------------------------------- #
# build_uw_macro_source — wired plug emits VALID Contract-A cards
# --------------------------------------------------------------------------- #
def test_build_source_dials_and_valid_cards():
    src = build_uw_macro_source(SNAP, as_of="2026-05-29")
    assert src.name == "uw_macro"
    assert src.trust_weight == 0.95
    assert src.independence_group == "market_data"

    items = src.fetch()
    assert len(items) == 8
    assert validate_items(items)["bad"] == []          # every macro card well-formed
    assert all(i.kind == "macro" for i in items)
    ten = next(i for i in items if i.subject == "10Y")
    assert ten.content == "10Y 4.45% (-3bp 5d)"


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-q"]))
