"""Tests for the Stage-5 uw_macro adapter (runtime_adapters.py, S5.4).

Fixtures mirror the REAL UW shapes: get_yield_curve() returns a 1-element list of
percent-string tenors (latest-only, no 5d-ago); levels reuse the
get_ticker_close_prices daily {"data":[{"c","date"}]} shape.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from runtime_adapters import (
    rates_from_yield_curve,
    levels_from_close_responses,
    uw_macro_snapshot_from_uw,
)
from uw_macro import uw_macro_reader, build_uw_macro_source
from validators import validate_items

# real-shaped get_yield_curve() payload (the 1-element list UW returns)
YC = [{
    "id": 2026528, "year": 2026, "new_date": "2026-05-28",
    "bc_1month": "3.72", "bc_2month": "3.71", "bc_3month": "3.69",
    "bc_6month": "3.79", "bc_1year": "3.8", "bc_2year": "3.99",
    "bc_3year": "4.07", "bc_5year": "4.15", "bc_7year": "4.29",
    "bc_10year": "4.45", "bc_20year": "4.98", "bc_30year": "4.98",
}]


def _series(newest_first):
    """A get_ticker_close_prices-shaped response from a newest-first close list."""
    n = len(newest_first)
    return {"data": [{"c": c, "date": f"d{(n - i):04d}"} for i, c in enumerate(newest_first)]}


# --------------------------------------------------------------------------- #
# rates_from_yield_curve
# --------------------------------------------------------------------------- #
def test_rates_picks_2_10_30_as_percent_floats():
    rates = rates_from_yield_curve(YC)
    assert set(rates) == {"2Y", "10Y", "30Y"}
    assert rates["2Y"]["value"] == pytest.approx(3.99)
    assert rates["10Y"]["value"] == pytest.approx(4.45)
    assert rates["30Y"]["value"] == pytest.approx(4.98)
    # latest-only snapshot -> no 5d-ago rate
    assert all(v["value_5d_ago"] is None for v in rates.values())


def test_rates_accepts_bare_dict_and_drops_missing():
    rates = rates_from_yield_curve({"bc_2year": "3.99", "bc_10year": "", "bc_30year": None})
    assert set(rates) == {"2Y"}          # blank 10Y and null 30Y dropped


def test_rates_empty_on_empty_input():
    assert rates_from_yield_curve([]) == {}
    assert rates_from_yield_curve(None) == {}


# --------------------------------------------------------------------------- #
# levels_from_close_responses
# --------------------------------------------------------------------------- #
def test_levels_value_and_5d_back():
    # newest-first: latest=99.2; 5 trading days back (index -6 after sort) = 100.5
    lv = levels_from_close_responses({"DXY": _series([99.2, 99.5, 99.8, 100.0, 100.2, 100.5, 101.0])})
    assert lv["DXY"]["value"] == pytest.approx(99.2)
    assert lv["DXY"]["value_5d_ago"] == pytest.approx(100.5)


def test_levels_short_series_gives_none_5d():
    lv = levels_from_close_responses({"VIX": _series([17.2, 16.0, 15.5])})  # <6 pts
    assert lv["VIX"]["value"] == pytest.approx(17.2)
    assert lv["VIX"]["value_5d_ago"] is None


def test_levels_empty_series_dropped():
    assert levels_from_close_responses({"MOVE": {"data": []}}) == {}
    assert levels_from_close_responses(None) == {}


# --------------------------------------------------------------------------- #
# uw_macro_snapshot_from_uw  +  reader integration
# --------------------------------------------------------------------------- #
def test_snapshot_shape_and_rates_only_mode():
    snap = uw_macro_snapshot_from_uw(YC, None)
    assert set(snap) == {"rates", "levels"}
    assert snap["levels"] == {}                       # no level pulls -> absent
    assert set(snap["rates"]) == {"2Y", "10Y", "30Y"}


def test_snapshot_feeds_reader_and_validates():
    levels = {
        "DXY": _series([99.2, 99.6, 100.0, 100.3, 100.4, 100.5]),
        "VIX": _series([17.2, 16.5, 16.0, 15.5, 15.2, 15.0]),
    }
    snap = uw_macro_snapshot_from_uw(YC, levels)
    cards = uw_macro_reader(snap, as_of="2026-05-28")
    subjects = {c["subject"] for c in cards}
    # 3 rate cards + 2 spreads + 2 levels
    assert {"2Y", "10Y", "30Y", "2s10s", "10s30s", "DXY", "VIX"} <= subjects
    # rate card has no 5d tail (value_5d_ago is None)
    r10 = next(c for c in cards if c["subject"] == "10Y")
    assert r10["content"] == "10Y 4.45%"
    assert r10["data"]["chg_5d"] is None
    # level card DOES carry a 5d change
    dxy = next(c for c in cards if c["subject"] == "DXY")
    assert dxy["data"]["chg_5d"] == pytest.approx(99.2 - 100.5)
    # the whole batch is valid through the uniform plug
    src = build_uw_macro_source(snap)
    assert validate_items(src.fetch())["bad"] == []
