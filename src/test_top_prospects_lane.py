"""Top Prospects lane (item 5) — feed-wiring integration tests."""
import os
import json

import feed_assembler as FA
import validators as V
from prospect_surface import _sample_cache

_HERE = os.path.dirname(os.path.abspath(__file__))


def _snap():
    return json.load(open(os.path.join(_HERE, "golden_snapshot.json")))


def test_assemble_feed_emits_prospects_and_validates():
    feed = FA.assemble_feed(_snap(), top_prospects=_sample_cache())
    p = feed["prospects"]
    assert p["counts"]["total"] == 4 and p["counts"]["avoid"] == 1
    assert [r["ticker"] for r in p["hot"]] == ["NVDA", "ANET"]   # ACT_NOW before HOT
    assert [r["ticker"] for r in p["sell_fast"]] == ["LULU"]      # direction=avoid -> sell_fast
    assert p["movers_best"][0]["ticker"] == "NVDA"               # top alpha vs SPY
    assert V.validate_cockpit_feed(feed) == []


def test_assemble_feed_no_prospects_is_empty_and_valid():
    feed = FA.assemble_feed(_snap())
    assert feed["prospects"] == {}
    assert V.validate_cockpit_feed(feed) == []


def test_non_dict_prospects_cache_degrades_to_empty():
    # the guard: a non-dict cache (e.g. a list) degrades to {}, never raises
    feed = FA.assemble_feed(_snap(), top_prospects=[1, 2, 3])
    assert feed["prospects"] == {}
    assert V.validate_cockpit_feed(feed) == []
