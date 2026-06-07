import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from codex_uw.endpoints import INVALID_ENDPOINTS
from uw_endpoint_router import (
    UW_ROUTING_PROFILES,
    endpoint_names_for_mode,
    profile_for_mode,
    validate_profiles,
)


def test_all_uw_routing_profiles_validate_against_catalog():
    validate_profiles()


def test_no_routing_profile_uses_known_invalid_endpoint_paths():
    for profile in UW_ROUTING_PROFILES.values():
        for group in profile["groups"]:
            for endpoint in group["endpoints"]:
                assert endpoint["path"] not in INVALID_ENDPOINTS
                assert endpoint["path"].startswith("/api/")


def test_crash_triage_profile_has_required_market_and_risk_lanes():
    names = set(endpoint_names_for_mode("pre_market_crash_triage"))

    assert "MARKET_TIDE" in names
    assert "TOP_NET_IMPACT" in names
    assert "TICKER_FLOW_RECENT" in names
    assert "DARKPOOL_TICKER" in names
    assert "TICKER_GREEK_EXPOSURE_STRIKE" in names
    assert "TICKER_SPOT_EXPOSURES_STRIKE" in names
    assert "TICKER_IV_RANK" in names


def test_reallocation_profile_covers_exposure_factor_sponsorship_and_flow():
    names = set(endpoint_names_for_mode("portfolio_reallocation"))

    assert "TICKER_OHLC" in names
    assert "ETF_TIDE" in names
    assert "SECTOR_TIDE" in names
    assert "ANALYST_RATINGS" in names
    assert "INSTITUTION_OWNERSHIP" in names
    assert "TICKER_FLOW_RECENT" in names
    assert "DARKPOOL_TICKER" in names


def test_reddit_escalation_is_vetting_not_action_source():
    profile = profile_for_mode("reddit_escalation_vetting")

    assert "Vet a Reddit velocity signal" in profile["purpose"]
    assert "never continuous trade promotion" in profile["default_cadence"]
    assert "not direct execution" in profile["groups"][0]["decision_use"]
