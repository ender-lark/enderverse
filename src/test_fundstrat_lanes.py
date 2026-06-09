import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fundstrat_lanes import classify_fundstrat_lane, classify_fundstrat_publication


def test_tom_lee_maps_to_macro_baseline():
    lane = classify_fundstrat_lane(author="Tom Lee", text="Risk backdrop remains constructive.")

    assert lane["fundstrat_lane"] == "macro"
    assert lane["source_domain"] == "macro_strategy"
    assert lane["trust_weight"] == 0.70
    assert "macro baseline" in lane["source_weight_note"].lower()
    assert lane["publication_type"] == "macro_update"
    assert lane["capture_policy"] == "audit_only"


def test_newton_specific_technical_call_keeps_normal_weight():
    lane = classify_fundstrat_lane(
        author="Mark Newton",
        text="QQQ support near 520 must hold before leaning into growth.",
    )

    assert lane["fundstrat_lane"] == "technical"
    assert lane["source_domain"] == "technical_timing"
    assert lane["trust_weight"] == 0.70
    assert "entry timing" in lane["source_weight_note"].lower()
    assert lane["capture_policy"] == "daily_call"


def test_newton_soft_technical_context_is_lower_weight():
    lane = classify_fundstrat_lane(author="Newton", text="Technology should continue to act well.")

    assert lane["fundstrat_lane"] == "technical"
    assert lane["trust_weight"] < 0.70
    assert "lower weight" in lane["source_weight_note"].lower()
    assert lane["capture_policy"] == "audit_only"


def test_crypto_lane_stays_scoped_to_crypto_context():
    lane = classify_fundstrat_lane(author="Farrell", ticker="IBIT", text="Bitcoin setup improving.")

    assert lane["fundstrat_lane"] == "crypto"
    assert lane["source_domain"] == "crypto_strategy"
    assert lane["trust_weight"] == 0.65
    assert "crypto-specific" in lane["source_weight_note"].lower()


def test_monthly_lists_route_to_baseline_not_daily_call():
    publication = classify_fundstrat_publication(
        subject="June Monthly Bible - Top 5 large cap",
        ticker="NVDA",
        direction="buy",
        text="NVDA is included in the monthly Top 5 large cap list.",
    )

    assert publication["publication_type"] == "monthly_bible"
    assert publication["capture_policy"] == "monthly_baseline"
    assert publication["use_case"] == "allocation_baseline"


def test_weekly_recap_without_action_stays_audit_only():
    publication = classify_fundstrat_publication(
        subject="Weekly Review",
        ticker="QQQ",
        text="QQQ was discussed in a recap of last week's market action.",
    )

    assert publication["publication_type"] == "weekly_review"
    assert publication["capture_policy"] == "audit_only"
    assert publication["decision_usefulness"] == "low"


def test_weekly_review_with_risk_change_is_daily_call():
    publication = classify_fundstrat_publication(
        subject="Weekly Review",
        ticker="QQQ",
        direction="watch",
        text="Watch QQQ support near 520; break below would raise hedge/re-check risk.",
    )

    assert publication["publication_type"] == "weekly_review"
    assert publication["capture_policy"] == "daily_call"
    assert publication["use_case"] == "risk_posture"


def test_promotion_without_action_is_suppressed():
    publication = classify_fundstrat_publication(
        subject="Join us for a Fundstrat webinar replay",
        text="General long-term market thoughts and replay registration details.",
    )

    assert publication["publication_type"] == "promotion"
    assert publication["capture_policy"] == "suppress"
