import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import battery_evidence as be
import battery_feed_adapter as bfa
from tunables import load_conviction_weights


def _by_key(payload):
    return {row["key"]: row for row in payload["factors"]}


def _factor(key, direction, strength, decisive=False):
    return {
        "key": key,
        "label": key,
        "direction": direction,
        "strength": strength,
        "value_str": key,
        "source": "test",
        "decisive": decisive,
    }


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


def test_uw_opportunity_factors_map_real_signal_shape():
    payload = be.build_battery_evidence(
        "BMNR",
        uw_opportunity={
            "status": "checked",
            "ticker": "BMNR",
            "as_of": "2026-06-16",
            "signals": [
                {
                    "ticker": "BMNR",
                    "signal_type": "sweep",
                    "direction": "bullish",
                    "strength": "strong",
                    "evidence": "ask-side call sweeps $1.1M, 1:1 c/p",
                    "detail": {"premium": 1_121_517, "call_put_ratio": 1.47},
                },
                {
                    "ticker": "BMNR",
                    "signal_type": "dark_pool_accum",
                    "direction": "bearish",
                    "strength": "weak",
                    "evidence": "dark-pool blocks $1M net sell",
                    "detail": {"notional": -861_447, "sessions": 1},
                },
                {
                    "ticker": "BMNR",
                    "signal_type": "oi_build",
                    "direction": "bullish",
                    "strength": "surprise",
                    "evidence": "malformed strength should not carry direction",
                },
            ],
        },
    )

    rows = _by_key(payload)
    sweep = rows["uw_opportunity_sweep"]
    assert sweep["direction"] == "bull"
    assert sweep["strength"] == 0.9
    assert sweep["decisive"] is True
    assert "as_of 2026-06-16" in sweep["value_str"]
    assert "c/p 1.47" in sweep["value_str"]
    dark = rows["uw_opportunity_dark_pool_accum"]
    assert dark["direction"] == "bear"
    assert dark["strength"] == 0.5
    assert "notional -$861,447" in dark["value_str"]
    unknown = rows["uw_opportunity_oi_build"]
    assert unknown["direction"] == "neutral"
    assert unknown["strength"] == 0.0


def test_uw_opportunity_checked_no_signal_is_not_not_checked():
    checked = be.build_battery_evidence(
        "MSFT",
        uw_opportunity={
            "status": "checked",
            "ticker": "MSFT",
            "as_of": "2026-06-16",
            "signals": [],
        },
    )
    row = checked["factors"][0]
    assert row["key"] == "uw_opportunity_none"
    assert row["direction"] == "neutral"
    assert row["strength"] == 0.0
    assert "no signal for MSFT" in row["value_str"]
    assert "not_checked" not in row["value_str"]

    unavailable = be.build_battery_evidence(
        "MSFT",
        uw_opportunity={
            "status": "not_checked",
            "ticker": "MSFT",
            "signals": [],
        },
    )
    row = unavailable["factors"][0]
    assert row["key"] == "uw_opportunity_not_checked"
    assert "not_checked" in row["value_str"]


def test_group_rotation_factor_maps_group_context_without_claiming_stock_range():
    leading = be.group_rotation_factor(
        {"status": "checked", "category": "AI / Semiconductors", "rot_w": "LEADING", "cd": "up"}
    )
    assert leading["direction"] == "bull"
    assert leading["strength"] == 0.5
    assert "GROUP-level context" in leading["value_str"]
    assert "ticker momentum up" in leading["value_str"]

    turning_down = be.group_rotation_factor({"status": "checked", "rot_w": "TURNING DOWN", "cd": "up"})
    assert turning_down["direction"] == "bear"

    inline = be.group_rotation_factor({"status": "checked", "rot_w": "IN LINE", "cd": "flat"})
    assert inline["direction"] == "neutral"
    assert inline["strength"] == 0.0


def test_gather_battery_inputs_uses_opportunity_cache_and_holdings_shape():
    feed = {
        "holdings": [
            {
                "cat": "AI / Semiconductors",
                "rot": {"w": "LEADING"},
                "pos": [{"t": "BMNR", "cd": "up", "cdNote": "flow changed"}],
            }
        ]
    }
    inputs = bfa.gather_battery_inputs(
        "BMNR",
        feed,
        opportunity_signals={
            "as_of": "2026-06-16",
            "signals": [
                {
                    "ticker": "BMNR",
                    "signal_type": "sweep",
                    "direction": "bullish",
                    "strength": "moderate",
                    "evidence": "ask-side call sweeps",
                },
                {
                    "ticker": "MSFT",
                    "signal_type": "sweep",
                    "direction": "bullish",
                    "strength": "strong",
                    "evidence": "other ticker",
                },
            ],
        },
    )
    assert inputs["iv_ctx"] is None
    assert len(inputs["uw_opportunity"]["signals"]) == 1
    assert inputs["group_rotation"]["rot_w"] == "LEADING"
    payload = be.build_battery_evidence("BMNR", **inputs)
    assert {"uw_opportunity_sweep", "group_rotation_momentum"} <= set(_by_key(payload))

    empty = bfa.gather_battery_inputs(
        "GOOGL",
        {"holdings": []},
        opportunity_signals={"as_of": "2026-06-16", "signals": []},
    )
    empty_payload = be.build_battery_evidence("GOOGL", **empty)
    rows = _by_key(empty_payload)
    assert rows["uw_opportunity_none"]["direction"] == "neutral"
    assert rows["group_rotation_not_checked"]["direction"] == "neutral"


def test_gather_battery_inputs_marks_absent_opportunity_source_not_checked(tmp_path):
    missing = tmp_path / "missing.json"
    inputs = bfa.gather_battery_inputs("BMNR", {"holdings": []}, signals_path=missing)
    payload = be.build_battery_evidence("BMNR", **inputs)
    assert _by_key(payload)["uw_opportunity_not_checked"]["strength"] == 0.0


def test_battery_summary_selector_preserves_mixed_conflicts_within_cap():
    factors = [
        _factor("bull_strong", "bull", 0.9, decisive=True),
        _factor("bull_mid", "bull", 0.7),
        _factor("bull_low", "bull", 0.5),
        _factor("bear_low", "bear", 0.5),
        _factor("neutral", "neutral", 0.0),
    ]
    selected = be.select_decisive_factors(factors, cap=4)
    keys = [row["key"] for row in selected]
    assert "bull_strong" in keys
    assert "bear_low" in keys
    assert len(selected) <= 4

    pure_bull = be.select_decisive_factors(
        [
            _factor("bull_low", "bull", 0.5),
            _factor("bull_strong", "bull", 0.9, decisive=True),
            _factor("bull_mid", "bull", 0.7),
        ],
        cap=2,
    )
    assert [row["key"] for row in pure_bull] == ["bull_strong", "bull_mid"]


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
