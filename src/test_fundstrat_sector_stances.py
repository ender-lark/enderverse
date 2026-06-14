import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fundstrat_sector_stances as stances


DECK = {
    "sector_allocation": {
        "as_of": "2026-06-11",
        "tactical_top3": [{"sector": "Health Care", "ticker": "XLV"}],
        "tactical_bottom3": [{"sector": "Energy", "ticker": "XLE"}],
        "named_levels": [{"ticker": "EWRE", "level": 38.0}],
        "monthly_checklist": [{"item": "EWRE breakout gate"}],
    }
}


def test_tactical_snapshot_is_queryable():
    snap = stances.tactical_snapshot(DECK)

    assert snap["as_of"] == "2026-06-11"
    assert snap["top3"][0]["ticker"] == "XLV"
    assert snap["bottom3"][0]["sector"] == "Energy"
    assert snap["named_levels"][0]["ticker"] == "EWRE"
    assert snap["monthly_checklist"][0]["item"] == "EWRE breakout gate"


def test_missing_bible_returns_empty_lists():
    snap = stances.tactical_snapshot({})

    assert snap["top3"] == []
    assert snap["bottom3"] == []
    assert snap["named_levels"] == []
    assert snap["monthly_checklist"] == []
