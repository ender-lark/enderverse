import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fundstrat_lanes import classify_fundstrat_lane


def test_tom_lee_maps_to_macro_baseline():
    lane = classify_fundstrat_lane(author="Tom Lee", text="Risk backdrop remains constructive.")

    assert lane["fundstrat_lane"] == "macro"
    assert lane["source_domain"] == "macro_strategy"
    assert lane["trust_weight"] == 0.70
    assert "macro baseline" in lane["source_weight_note"].lower()


def test_newton_specific_technical_call_keeps_normal_weight():
    lane = classify_fundstrat_lane(
        author="Mark Newton",
        text="QQQ support near 520 must hold before leaning into growth.",
    )

    assert lane["fundstrat_lane"] == "technical"
    assert lane["source_domain"] == "technical_timing"
    assert lane["trust_weight"] == 0.70
    assert "entry timing" in lane["source_weight_note"].lower()


def test_newton_soft_technical_context_is_lower_weight():
    lane = classify_fundstrat_lane(author="Newton", text="Technology should continue to act well.")

    assert lane["fundstrat_lane"] == "technical"
    assert lane["trust_weight"] < 0.70
    assert "lower weight" in lane["source_weight_note"].lower()


def test_crypto_lane_stays_scoped_to_crypto_context():
    lane = classify_fundstrat_lane(author="Farrell", ticker="IBIT", text="Bitcoin setup improving.")

    assert lane["fundstrat_lane"] == "crypto"
    assert lane["source_domain"] == "crypto_strategy"
    assert lane["trust_weight"] == 0.65
    assert "crypto-specific" in lane["source_weight_note"].lower()
