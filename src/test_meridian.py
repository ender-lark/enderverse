"""Unit tests for the meridian plug (S6).

Run:  python -m pytest src/test_meridian.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from validators import validate_items
from meridian import meridian_reader, build_meridian_source, MERIDIAN_MODEL_TAG


ITEMS = [
    {"subject": "LEU", "item_type": "thesis",
     "quote": "LEU — HALEU enrichment monopoly; generational lane",
     "theme": "HALEU", "date": "2026-03-05"},
    {"subject": "MP", "item_type": "call", "direction": "buy",
     "entry": 60, "target": 90, "quote": "MP — buy, rare-earth magnet reshoring",
     "date": "2026-03-05"},
    {"subject": "Project Janus", "item_type": "thesis",
     "quote": "Project Janus — DOE HALEU offtake catalyst H2",
     "theme": "nuclear fuel", "date": "2026-03-05"},
    {"subject": "UUUU", "item_type": "model", "direction": "buy",
     "entry": 7, "target": 12,
     "quote": "UUUU modeled long, rare-earth + uranium dual", "date": "2026-03-05"},
]


def _by_subject(rows):
    return {r["subject"]: r for r in rows}


# --------------------------------------------------------------------------- #
# counts + kinds
# --------------------------------------------------------------------------- #
def test_count_and_kinds():
    rows = meridian_reader(ITEMS)
    assert len(rows) == 4
    kinds = sorted(r["kind"] for r in rows)
    assert kinds == ["analyst_call", "analyst_call", "analyst_call", "model_trade"]


# --------------------------------------------------------------------------- #
# thesis / call
# --------------------------------------------------------------------------- #
def test_thesis_card():
    leu = _by_subject(meridian_reader(ITEMS))["LEU"]
    assert leu["kind"] == "analyst_call"
    assert leu["content"] == "LEU — HALEU enrichment monopoly; generational lane"
    assert leu["data"]["item_type"] == "thesis"
    assert leu["data"]["theme"] == "HALEU"
    assert leu["data"]["is_model"] is False


def test_call_card_levels():
    mp = _by_subject(meridian_reader(ITEMS))["MP"]
    assert mp["data"]["direction"] == "buy"
    assert mp["data"]["entry"] == 60 and mp["data"]["target"] == 90
    assert mp["content"] == "MP — buy, rare-earth magnet reshoring"   # verbatim wins


# --------------------------------------------------------------------------- #
# model trade — the non-actionable distinction
# --------------------------------------------------------------------------- #
def test_model_trade_flagged_and_prefixed():
    uuuu = _by_subject(meridian_reader(ITEMS))["UUUU"]
    assert uuuu["kind"] == "model_trade"
    assert uuuu["data"]["is_model"] is True
    assert uuuu["data"]["model_tag"] == MERIDIAN_MODEL_TAG
    assert uuuu["content"] == "[Meridian model] UUUU modeled long, rare-earth + uranium dual"


def test_model_trade_templated_when_no_quote():
    rows = meridian_reader([
        {"subject": "ABC", "item_type": "model", "direction": "buy", "entry": 5}])
    assert rows[0]["kind"] == "model_trade"
    assert rows[0]["content"] == "[Meridian model] Meridian: buy ABC (entry 5)"


# --------------------------------------------------------------------------- #
# templated (non-model) content
# --------------------------------------------------------------------------- #
def test_thesis_templated_with_theme():
    rows = meridian_reader([
        {"subject": "REMX", "item_type": "thesis", "theme": "rare earths"}])
    assert rows[0]["content"] == "Meridian: REMX — rare earths"


def test_call_templated_with_levels():
    rows = meridian_reader([
        {"subject": "MP2", "item_type": "call", "direction": "buy",
         "entry": 60, "target": 90}])
    assert rows[0]["content"] == "Meridian: buy MP2 (entry 60, tgt 90)"


# --------------------------------------------------------------------------- #
# resilience + timestamps
# --------------------------------------------------------------------------- #
def test_subjectless_item_skipped():
    rows = meridian_reader([{"item_type": "thesis", "quote": "no subject"},
                            {"subject": "LEU", "item_type": "thesis", "quote": "x"}])
    assert [r["subject"] for r in rows] == ["LEU"]


def test_timestamp_uses_date_then_as_of():
    rows = _by_subject(meridian_reader(ITEMS))
    assert rows["LEU"]["timestamp"] == "2026-03-05"
    rows2 = meridian_reader([{"subject": "MP", "item_type": "thesis", "quote": "x"}],
                            as_of="2026-05-29")
    assert rows2[0]["timestamp"] == "2026-05-29"


# --------------------------------------------------------------------------- #
# wired plug -> dials + valid Contract-A cards (incl. the model_trade card)
# --------------------------------------------------------------------------- #
def test_build_source_dials_and_valid_cards():
    src = build_meridian_source(ITEMS)
    assert src.name == "meridian"
    assert src.trust_weight == 0.75
    assert src.independence_group == "thematic_research"

    items = src.fetch()
    assert len(items) == 4
    assert validate_items(items)["bad"] == []        # model_trade card validates too
    uuuu = next(i for i in items if i.subject == "UUUU")
    assert uuuu.kind == "model_trade"
    assert uuuu.trust_weight == 0.75                 # reliability unchanged by is_model


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-q"]))
