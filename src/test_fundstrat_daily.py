"""Unit tests for the fundstrat_daily plug (S5).

Run:  python -m pytest src/test_fundstrat_daily.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from validators import validate_items
from fundstrat_daily import (
    fundstrat_daily_reader,
    build_fundstrat_daily_source,
    _fmt_levels,
)


CALLS = [
    {"author": "Newton", "ticker": "NVDA", "direction": "buy",
     "entry": 170, "stop": 160, "target": 200, "window": "2-3 weeks",
     "date": "2026-05-28"},
    {"author": "Lee", "ticker": "GS", "direction": "buy",
     "quote": "GS breakout, add here", "date": "2026-05-27"},
    {"author": "Farrell", "ticker": "HYPE", "direction": "accumulate",
     "quote": "HYPE — conviction HOLD, accumulate dips", "date": "2026-05-28"},
]


def _by_subject(items):
    return {i.subject: i for i in items}


# --------------------------------------------------------------------------- #
# _fmt_levels
# --------------------------------------------------------------------------- #
def test_fmt_levels_full():
    assert _fmt_levels(170, 160, 200, "2-3 weeks") == "entry 170, stop 160, tgt 200, 2-3 weeks"


def test_fmt_levels_partial():
    assert _fmt_levels(100, None, 130, None) == "entry 100, tgt 130"


def test_fmt_levels_empty():
    assert _fmt_levels(None, None, None, None) == ""


# --------------------------------------------------------------------------- #
# reader content
# --------------------------------------------------------------------------- #
def test_count_and_kind():
    rows = fundstrat_daily_reader(CALLS)
    assert len(rows) == 3
    assert all(r["kind"] == "analyst_call" for r in rows)


def test_templated_content_when_no_quote():
    rows = {r["subject"]: r for r in fundstrat_daily_reader(CALLS)}
    assert rows["NVDA"]["content"] == "Newton: buy NVDA (entry 170, stop 160, tgt 200, 2-3 weeks)"
    assert rows["NVDA"]["data"]["entry"] == 170
    assert rows["NVDA"]["data"]["target"] == 200


def test_verbatim_quote_wins():
    rows = {r["subject"]: r for r in fundstrat_daily_reader(CALLS)}
    assert rows["GS"]["content"] == "GS breakout, add here"
    assert rows["GS"]["data"]["verbatim"] == "GS breakout, add here"


def test_partial_levels_template():
    rows = fundstrat_daily_reader([
        {"author": "Newton", "ticker": "MU", "direction": "buy",
         "entry": 100, "target": 130, "date": "2026-05-28"}])
    assert rows[0]["content"] == "Newton: buy MU (entry 100, tgt 130)"


def test_timestamp_uses_call_date():
    rows = {r["subject"]: r for r in fundstrat_daily_reader(CALLS)}
    assert rows["NVDA"]["timestamp"] == "2026-05-28"
    assert rows["GS"]["timestamp"] == "2026-05-27"


def test_as_of_fallback_when_no_call_date():
    rows = fundstrat_daily_reader(
        [{"author": "Newton", "ticker": "AVGO", "direction": "buy"}],
        as_of="2026-05-29")
    assert rows[0]["timestamp"] == "2026-05-29"


def test_call_without_ticker_skipped():
    rows = fundstrat_daily_reader([
        {"author": "Lee", "quote": "broad market constructive"},   # no ticker
        {"author": "Newton", "ticker": "NVDA", "direction": "buy"},
    ])
    assert [r["subject"] for r in rows] == ["NVDA"]


# --------------------------------------------------------------------------- #
# per-author trust + wired plug
# --------------------------------------------------------------------------- #
def test_per_author_trust_via_built_plug():
    items = _by_subject(build_fundstrat_daily_source(CALLS).fetch())
    assert items["NVDA"].trust_weight == 0.70     # Newton -> plug default
    assert items["GS"].trust_weight == 0.70       # Lee    -> plug default
    assert items["HYPE"].trust_weight == 0.65     # Farrell -> override
    # all stay in the one fundstrat echo-chamber group
    assert {i.independence_group for i in items.values()} == {"fundstrat"}


def test_lane_metadata_preserved_on_daily_rows():
    rows = {r["subject"]: r for r in fundstrat_daily_reader(CALLS)}

    assert rows["NVDA"]["data"]["fundstrat_lane"] == "technical"
    assert rows["NVDA"]["data"]["source_domain"] == "technical_timing"
    assert "entry timing" in rows["NVDA"]["data"]["source_weight_note"].lower()
    assert rows["GS"]["data"]["fundstrat_lane"] == "macro"
    assert rows["GS"]["data"]["author_role"] == "Tom Lee macro/strategy view"
    assert rows["HYPE"]["data"]["fundstrat_lane"] == "crypto"
    assert rows["HYPE"]["trust_weight"] == 0.65


def test_soft_newton_call_gets_lower_technical_weight():
    rows = fundstrat_daily_reader([
        {"author": "Newton", "ticker": "XLK", "direction": "favor",
         "quote": "Technology should continue to act well.", "date": "2026-06-05"},
    ])

    assert rows[0]["data"]["fundstrat_lane"] == "technical"
    assert rows[0]["trust_weight"] < 0.70
    assert "lower weight" in rows[0]["data"]["source_weight_note"].lower()


def test_build_source_dials_and_valid_cards():
    src = build_fundstrat_daily_source(CALLS)
    assert src.name == "fundstrat_daily"
    assert src.trust_weight == 0.70               # plug default
    items = src.fetch()
    assert len(items) == 3
    assert validate_items(items)["bad"] == []     # every card well-formed
    assert items[0].kind == "analyst_call"


def test_direction_preserved():
    rows = {r["subject"]: r for r in fundstrat_daily_reader(CALLS)}
    assert rows["HYPE"]["data"]["direction"] == "accumulate"


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-q"]))
