import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import validators
from decision_card import (
    CARD_FIELDS,
    UNKNOWN,
    attach,
    is_unknown,
    stamp_unknown,
    unknown_field,
    validate_decision_card,
)

SRC = os.path.dirname(os.path.abspath(__file__))

def _complete_card():
    return {
        "move": {
            "ticker": "GOOGL",
            "direction": "BUY",
            "lane": "core_reallocation",
            "band": "$151,266 (0% -> 8% of book)",
        },
        "conviction": {
            "read": "HIGH",
            "points": 2.5,
            "groups": {"fs": 1.5, "uw": 0.5, "operator_insight": 0.0, "institutional": 0.0},
            "raises": ["next-morning OI confirm on Dec-27 405C", "13F overlap check"],
        },
        "window": {
            "class": "STAGE-ONLY",
            "deadline": "2026-06-12",
            "reasons": ["above 341-350 FS zone (ok-not-gift)", "index gate red-but-tested 6/9"],
            "flips": ["QQQ confirms above ~705 same-session"],
        },
        "evidence": {
            "links": [
                {"label": "FS Top-5 large cap 5/28", "ref": "fundstrat_bible.json"},
                {"label": "FS daily buy-zone call 6/3", "ref": "fundstrat_daily_calls.json"},
            ]
        },
        "impact": {
            "band": "~$151k redeploy toward AI model",
            "base": "book",
            "material": True,
            "basis": "0.5% book materiality = $9,454",
        },
    }

def test_complete_card_validates():
    assert validate_decision_card(_complete_card()) == []

def test_stamp_unknown_fills_all_five_fields():
    card = stamp_unknown({})
    assert set(CARD_FIELDS) <= set(card)
    for name in CARD_FIELDS:
        assert is_unknown(card[name])
        assert card[name]["note"]
    assert validate_decision_card(card) == []

def test_partial_card_gets_stamped_not_dropped():
    card = stamp_unknown({"move": _complete_card()["move"]})
    assert not is_unknown(card["move"])
    assert is_unknown(card["impact"])
    assert validate_decision_card(card) == []

def test_silent_omission_is_invalid():
    card = _complete_card()
    del card["impact"]
    problems = validate_decision_card(card)
    assert any("impact" in p for p in problems)

def test_bad_direction_and_empty_reasons_flagged():
    card = _complete_card()
    card["move"]["direction"] = "YOLO"
    card["window"]["reasons"] = []
    problems = validate_decision_card(card)
    assert any("direction" in p for p in problems)
    assert any("named reason" in p for p in problems)

def test_unknown_sentinel_values_allowed_in_enums():
    card = _complete_card()
    card["conviction"]["read"] = UNKNOWN
    card["window"]["class"] = UNKNOWN
    card["impact"]["base"] = UNKNOWN
    assert validate_decision_card(card) == []

def test_attach_stamps_validates_and_is_additive():
    row = {"rank": 1, "kind": "lean_in", "ticker": "GOOGL"}
    out = attach(row, {"move": _complete_card()["move"]})
    assert out is row
    assert "decision_card" in row
    assert is_unknown(row["decision_card"]["window"])

def test_attach_rejects_invalid_card():
    with pytest.raises(ValueError):
        attach({}, {"move": {"direction": "NOPE", "band": "x"}})

def test_golden_feed_tolerates_decision_card_additively():
    """V2's feed validator must accept rows that carry the new card (additive)."""
    with open(os.path.join(SRC, "golden_feed.json"), encoding="utf-8") as fh:
        feed = json.load(fh)
    baseline = validators.validate_cockpit_feed(feed)
    assert baseline == []
    attach(feed["actions"][0], _complete_card())
    feed["actions"][1]["decision_card"] = stamp_unknown({})
    assert validators.validate_cockpit_feed(feed) == []

def test_unknown_field_notes_are_specific():
    assert "timing" in unknown_field("window")["note"]
    assert unknown_field("nonexistent")["note"]
