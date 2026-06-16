import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import battery_evidence as be
from tunables import load_conviction_weights


def _by_key(payload):
    return {row["key"]: row for row in payload["factors"]}


def test_deepdive_lanes_normalize_to_factor_contract():
    payload = be.build_battery_evidence(
        "nvda",
        deepdive_battery={
            "lanes": [
                {
                    "name": "multi_day_oi_build",
                    "status": "fetched",
                    "days_of_oi_increases": 4,
                    "dominant_side": "call",
                    "flagged": True,
                    "summary": "multi-day OI build: 4 dated increase day(s), side call",
                },
                {
                    "name": "dark_pool_blocks",
                    "status": "fetched",
                    "flagged": True,
                    "qualifying_blocks": 2,
                    "net_signed_notional": -12_000_000,
                    "total_notional": 20_000_000,
                    "summary": "dark-pool blocks: 2 block(s), net -$12.0M",
                },
            ]
        },
    )

    assert be.validate_battery_evidence(payload) == []
    rows = _by_key(payload)
    assert rows["multi_day_oi_build"]["direction"] == "bull"
    assert rows["multi_day_oi_build"]["strength"] == 0.8
    assert rows["multi_day_oi_build"]["decisive"] is True
    assert rows["dark_pool_blocks"]["direction"] == "bear"
    assert rows["dark_pool_blocks"]["strength"] == 0.48
    assert rows["dark_pool_blocks"]["decisive"] is True
    assert payload["verdict_line"].startswith("Battery evidence mixed")


def test_not_checked_lanes_stay_visible_without_signal():
    payload = be.build_battery_evidence(
        "NVDA",
        deepdive_battery={
            "lanes": [
                {
                    "name": "multi_day_oi_build",
                    "endpoint": "get_open_interest_changes",
                    "status": "not_checked",
                    "summary": "not checked - no UW OI response supplied",
                }
            ]
        },
    )

    row = payload["factors"][0]
    assert row["direction"] == "neutral"
    assert row["strength"] == 0.0
    assert row["decisive"] is False
    assert "not_checked" in row["value_str"]
    assert "clear" in payload["verdict_line"]


def test_price_rotation_maps_ticker_row_only():
    payload = be.build_battery_evidence(
        "NVDA",
        uw_price=[
            {"proxy": "SMH", "label": "LEADING", "rel_3m": 0.12, "rel_1m": 0.04},
            {
                "proxy": "NVDA",
                "label": "TURNING DOWN",
                "rel_3m": 0.07,
                "rel_1m": -0.04,
            },
        ],
    )

    assert len(payload["factors"]) == 1
    factor = payload["factors"][0]
    assert factor["key"] == "price_rotation"
    assert factor["direction"] == "bear"
    assert factor["decisive"] is True
    assert "TURNING DOWN" in factor["value_str"]


def test_iv_hint_contract_from_context_dict():
    cheap = be.build_battery_evidence(
        "LEU",
        iv_ctx={
            "classification": "cheap",
            "recommended_structure": "LEAP_CALL",
            "iv_rank": 15,
        },
    )
    assert cheap["iv_hint"]["instrument"] == "options"
    assert cheap["iv_hint"]["iv_rank"] == 15
    assert "LEAP_CALL" in cheap["iv_hint"]["why"]

    expensive = be.build_battery_evidence(
        "IONQ",
        iv_ctx={
            "composite_class": "expensive",
            "recommended_structure": "DIAGONAL",
            "iv_rank": 85,
        },
    )
    assert expensive["iv_hint"]["instrument"] == "shares"
    assert expensive["iv_hint"]["iv_rank"] == 85


def test_validator_rejects_invalid_contract_values():
    problems = be.validate_battery_evidence(
        {
            "factors": [
                {
                    "key": "x",
                    "label": "Bad",
                    "direction": "bullish",
                    "strength": 1.2,
                    "value_str": "x",
                    "source": "test",
                    "decisive": "yes",
                }
            ],
            "iv_hint": {"instrument": "futures", "why": 1, "iv_rank": "high"},
            "verdict_line": 5,
        }
    )

    assert any("direction" in problem for problem in problems)
    assert any("strength" in problem for problem in problems)
    assert any("instrument" in problem for problem in problems)
    assert any("verdict_line" in problem for problem in problems)


def test_read_to_5_contract_is_tunable_and_validated():
    mapping = load_conviction_weights()["read_to_5"]
    assert mapping["high_score"] == 5
    assert mapping["moderate_score"] == 4
    assert mapping["moderate_0_66_score"] == 3
    assert mapping["moderate_0_33_score"] == 2
    assert mapping["floor_score"] == 1
    assert mapping["mid_fraction"] == 0.66
    assert mapping["low_fraction"] == 0.33
