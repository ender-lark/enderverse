"""Unit tests for the fundstrat_bible plug (S4).

Run:  python -m pytest src/test_fundstrat_bible.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from validators import validate_items
from fundstrat_bible import (
    fundstrat_bible_reader,
    build_fundstrat_bible_source,
)


DECK = {
    "deck_date": "2026-05",
    "macro_stance": "Tactically constructive into mid-year; buy dips, S&P target intact.",
    "what_to_own": ["Technology", "Industrials", "Financials"],
    "top5": [
        {"ticker": "NVDA", "note": "secular AI leader"},
        "GOOGL",
        "AVGO",
        "GS",
        "PANW",
    ],
    "bottom5": ["XYZ", "ABC", "DEF"],
}


def _by_subject(rows):
    # subjects are unique here except possibly "macro stance"
    out = {}
    for r in rows:
        out.setdefault(r["subject"], []).append(r)
    return out


# --------------------------------------------------------------------------- #
# counts + timestamp
# --------------------------------------------------------------------------- #
def test_card_count_and_timestamp_uses_deck_date():
    rows = fundstrat_bible_reader(DECK)
    # stance 1 + what_to_own 3 + top5 5 + bottom5 3
    assert len(rows) == 12
    assert all(r["timestamp"] == "2026-05" for r in rows)


def test_as_of_overrides_deck_date():
    rows = fundstrat_bible_reader(DECK, as_of="2026-05-29")
    assert all(r["timestamp"] == "2026-05-29" for r in rows)


# --------------------------------------------------------------------------- #
# stance
# --------------------------------------------------------------------------- #
def test_stance_card_verbatim():
    rows = fundstrat_bible_reader(DECK)
    stance = [r for r in rows if r["kind"] == "stance"]
    assert len(stance) == 1
    assert stance[0]["subject"] == "macro stance"
    assert stance[0]["content"] == DECK["macro_stance"]
    assert stance[0]["data"]["verbatim"] == DECK["macro_stance"]


def test_stance_list_form_emits_multiple():
    deck = {"deck_date": "2026-05",
            "macro_stance": ["Risk-on tilt", "Add cyclicals on weakness"]}
    rows = fundstrat_bible_reader(deck)
    assert len(rows) == 2
    assert {r["content"] for r in rows} == {"Risk-on tilt", "Add cyclicals on weakness"}


def test_verbatim_preserved_with_special_chars():
    odd = 'Lee: "buy the dip"; S&P target 6,500 (≈ +8%)'
    rows = fundstrat_bible_reader({"deck_date": "2026-05", "macro_stance": odd})
    assert rows[0]["content"] == odd        # passed through unchanged


# --------------------------------------------------------------------------- #
# What-to-Own
# --------------------------------------------------------------------------- #
def test_what_to_own_cards():
    rows = [r for r in fundstrat_bible_reader(DECK) if r["kind"] == "what_to_own"]
    assert [r["subject"] for r in rows] == ["Technology", "Industrials", "Financials"]
    assert rows[0]["content"] == "FS What-to-Own: Technology"
    assert rows[0]["data"]["sector"] == "Technology"


# --------------------------------------------------------------------------- #
# Top-5 / Bottom-5
# --------------------------------------------------------------------------- #
def test_top5_cards_and_ranks():
    rows = [r for r in fundstrat_bible_reader(DECK)
            if r["kind"] == "analyst_call" and r["data"]["list"] == "top5"]
    assert len(rows) == 5
    assert [r["subject"] for r in rows] == ["NVDA", "GOOGL", "AVGO", "GS", "PANW"]
    assert [r["data"]["rank"] for r in rows] == [1, 2, 3, 4, 5]
    assert all(r["data"]["direction"] == "favored" for r in rows)


def test_top5_note_appended_dict_and_bare_str():
    by = _by_subject(fundstrat_bible_reader(DECK))
    assert by["NVDA"][0]["content"] == "FS Top-5: NVDA — secular AI leader"
    assert by["GOOGL"][0]["content"] == "FS Top-5: GOOGL"     # bare string, no note


def test_bottom5_cards():
    rows = [r for r in fundstrat_bible_reader(DECK)
            if r["data"].get("list") == "bottom5"]
    assert [r["subject"] for r in rows] == ["XYZ", "ABC", "DEF"]
    assert all(r["data"]["direction"] == "unfavored" for r in rows)
    assert rows[0]["content"] == "FS Bottom-5: XYZ"


def test_smid_top_bottom_cards_are_distinct_lists():
    deck = {
        "deck_date": "2026-05-28",
        "top5_smid": [{"ticker": "STRL", "note": "carry over"}, "FN"],
        "bottom5_smid": ["ELF", "KTOS"],
    }

    rows = [r for r in fundstrat_bible_reader(deck) if r["kind"] == "analyst_call"]

    assert [(r["subject"], r["data"]["list"], r["data"]["rank"]) for r in rows] == [
        ("STRL", "top5_smid", 1),
        ("FN", "top5_smid", 2),
        ("ELF", "bottom5_smid", 1),
        ("KTOS", "bottom5_smid", 2),
    ]
    assert rows[0]["content"].startswith("FS Top-5 SMID: STRL")
    assert rows[0]["content"].endswith("carry over")
    assert rows[-1]["content"] == "FS Bottom-5 SMID: KTOS"


# --------------------------------------------------------------------------- #
# resilience
# --------------------------------------------------------------------------- #
def test_missing_section_emits_no_cards_for_it():
    deck = {k: v for k, v in DECK.items() if k != "bottom5"}
    rows = fundstrat_bible_reader(deck)
    assert len(rows) == 9                      # 1 + 3 + 5
    assert not any(r["data"].get("list") == "bottom5" for r in rows)


def test_empty_item_skipped():
    deck = {"deck_date": "2026-05", "top5": ["NVDA", "", None, "GOOGL"]}
    rows = fundstrat_bible_reader(deck)
    assert [r["subject"] for r in rows] == ["NVDA", "GOOGL"]


def test_empty_deck_emits_nothing():
    assert fundstrat_bible_reader({"deck_date": "2026-05"}) == []


# --------------------------------------------------------------------------- #
# wired plug -> dials + valid Contract-A cards
# --------------------------------------------------------------------------- #
def test_build_source_dials_and_valid_cards():
    src = build_fundstrat_bible_source(DECK)
    assert src.name == "fundstrat_bible"
    assert src.trust_weight == 0.70
    assert src.independence_group == "fundstrat"      # echo-chamber group

    items = src.fetch()
    assert len(items) == 12
    assert validate_items(items)["bad"] == []
    nvda = next(i for i in items if i.subject == "NVDA")
    assert nvda.kind == "analyst_call"
    assert nvda.content == "FS Top-5: NVDA — secular AI leader"


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-q"]))
