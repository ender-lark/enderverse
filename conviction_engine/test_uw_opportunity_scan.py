#!/usr/bin/env python3
"""
test_uw_opportunity_scan.py — Strand 3, Chunk 3 tests for the SCOUT producer.

The load-bearing test is the ROUND-TRIP LOCK: every cache the scout emits must pass
cleanly through the LOCKED consumer ``uw_opportunity.uw_opportunity_cards`` to the
expected cards. That ties the producer to the Chunk-1 contract — if the scout ever
drifts from the schema, these fail. The scout adds NO engine files, so the engine
golden stays drift-free (asserted in test_golden_master.py, unchanged).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from analyst_config import UW_OPP_STRENGTH_TRUST
from uw_opportunity import (
    uw_opportunity_cards,
    SIGNAL_TYPES,
    DIRECTIONS,
    UW_OPP_KIND,
    UW_OPP_SOURCE,
    UW_OPP_INDEPENDENCE_GROUP,
)
import uw_opportunity_scan as S
from uw_opportunity_scan import (
    scan,
    BundleAdapters,
    normalize_flow,
    normalize_oi,
    normalize_dark_pool,
    normalize_gamma,
    normalize_iv,
    observation_from_uw,
    universe_from_theses,
    universe_from_bundle,
)

GEN = "2026-05-29T10:30:00Z"


def _bundle_adapters(obs):
    return BundleAdapters(obs)


# ════════════════════════════════════════════════════════════════════════════
# 1. THE ROUND-TRIP LOCK — emitted cache must round-trip through the consumer
# ════════════════════════════════════════════════════════════════════════════
def test_emitted_cache_roundtrips_through_consumer():
    obs = {
        "ANET": {"flow": {"ask_side_call_premium": 2_100_000, "put_premium": 700_000,
                          "call_put_ratio": 3.0, "is_sweep": True}},
        "NVDA": {"oi": {"oi_change_pct": 38.0, "side": "call", "strikes": [1300, 1350]}},
        "MU": {"dark_pool": {"notional_signed": 14_000_000, "sessions": 4}},
    }
    cache = scan(["ANET", "NVDA", "MU"], "2026-05-29", adapters=_bundle_adapters(obs), generated_at=GEN)

    # cache shape
    assert cache["source"] == "uw_opportunity_scan"
    assert cache["as_of"] == "2026-05-29"
    assert cache["generated_at"] == GEN
    assert len(cache["signals"]) == 3

    # round-trips cleanly through the LOCKED consumer
    cards = uw_opportunity_cards(cache)
    assert len(cards) == 3
    assert {c["subject"] for c in cards} == {"ANET", "NVDA", "MU"}
    assert all(c["kind"] == UW_OPP_KIND for c in cards)
    assert all(c["source"] == UW_OPP_SOURCE for c in cards)
    assert all(c["independence_group"] == UW_OPP_INDEPENDENCE_GROUP for c in cards)
    # the cards expose the opportunity semantics the direction read keys on
    by = {c["subject"]: c for c in cards}
    assert by["ANET"]["data"]["signal_type"] == "sweep"
    assert by["ANET"]["data"]["direction"] == "bullish"
    assert by["NVDA"]["data"]["signal_type"] == "oi_build"
    assert by["MU"]["data"]["signal_type"] == "dark_pool_accum"


def test_emitted_signals_satisfy_the_contract_enums():
    obs = {
        "ANET": {"flow": {"ask_side_call_premium": 2_100_000, "put_premium": 100_000, "is_sweep": True}},
        "NVDA": {"oi": {"oi_change_pct": 38.0, "side": "put"}},
        "MU": {"dark_pool": {"notional_signed": -14_000_000, "sessions": 4}},
    }
    cache = scan(["ANET", "NVDA", "MU"], "2026-05-29", adapters=_bundle_adapters(obs), generated_at=GEN)
    for s in cache["signals"]:
        assert s["ticker"]
        assert s["signal_type"] in SIGNAL_TYPES
        assert s["direction"] in DIRECTIONS
        assert s["strength"] in UW_OPP_STRENGTH_TRUST


def test_roundtrips_to_the_same_cards_as_a_handbuilt_cache():
    """'Round-trips through ... to the EXPECTED cards': the cards off the scout's
    cache equal the cards off a hand-built cache carrying the same signals."""
    obs = {"ANET": {"flow": {"ask_side_call_premium": 2_100_000, "put_premium": 700_000,
                             "call_put_ratio": 3.0, "is_sweep": True}}}
    cache = scan(["ANET"], "2026-05-29", adapters=_bundle_adapters(obs), generated_at=GEN)
    scout_cards = uw_opportunity_cards(cache)

    handbuilt = {
        "as_of": "2026-05-29", "generated_at": GEN, "source": "uw_opportunity_scan",
        "signals": [dict(cache["signals"][0])],
    }
    expected_cards = uw_opportunity_cards(handbuilt)
    assert scout_cards == expected_cards


def test_trust_weight_maps_from_strength():
    obs = {"AAA": {"flow": {"ask_side_call_premium": 3_000_000, "is_sweep": False}}}  # strong
    cache = scan(["AAA"], "d", adapters=_bundle_adapters(obs), generated_at=GEN)
    card = uw_opportunity_cards(cache)[0]
    assert card["trust_weight"] == UW_OPP_STRENGTH_TRUST["strong"]


# ════════════════════════════════════════════════════════════════════════════
# 2. DIRECTION logic (bullish / bearish per signal type)
# ════════════════════════════════════════════════════════════════════════════
def test_flow_direction_bearish_when_puts_dominate():
    obs = {"X": {"flow": {"ask_side_call_premium": 300_000, "ask_side_put_premium": 2_500_000}}}
    sig = scan(["X"], "d", adapters=_bundle_adapters(obs), generated_at=GEN)["signals"][0]
    assert sig["direction"] == "bearish"
    assert "put" in sig["evidence"]


def test_oi_direction_follows_building_side():
    bull = scan(["X"], "d", adapters=_bundle_adapters({"X": {"oi": {"oi_change_pct": 20, "side": "call"}}}),
                generated_at=GEN)["signals"][0]
    bear = scan(["Y"], "d", adapters=_bundle_adapters({"Y": {"oi": {"oi_change_pct": 20, "side": "put"}}}),
                generated_at=GEN)["signals"][0]
    assert bull["direction"] == "bullish"
    assert bear["direction"] == "bearish"


def test_dark_pool_direction_from_notional_sign():
    pos = scan(["X"], "d", adapters=_bundle_adapters({"X": {"dark_pool": {"notional_signed": 5_000_000}}}),
               generated_at=GEN)["signals"][0]
    neg = scan(["Y"], "d", adapters=_bundle_adapters({"Y": {"dark_pool": {"notional_signed": -5_000_000}}}),
               generated_at=GEN)["signals"][0]
    assert pos["direction"] == "bullish" and "net buy" in pos["evidence"]
    assert neg["direction"] == "bearish" and "net sell" in neg["evidence"]


# ════════════════════════════════════════════════════════════════════════════
# 3. STRENGTH bands per signal type
# ════════════════════════════════════════════════════════════════════════════
def test_flow_strength_bands():
    def strength(prem):
        obs = {"X": {"flow": {"ask_side_call_premium": prem}}}
        return scan(["X"], "d", adapters=_bundle_adapters(obs), generated_at=GEN)["signals"][0]["strength"]
    assert strength(2_500_000) == "strong"
    assert strength(1_000_000) == "moderate"
    assert strength(100_000) == "weak"


def test_oi_strength_bands():
    def strength(pct):
        obs = {"X": {"oi": {"oi_change_pct": pct, "side": "call"}}}
        return scan(["X"], "d", adapters=_bundle_adapters(obs), generated_at=GEN)["signals"][0]["strength"]
    assert strength(40) == "strong"
    assert strength(15) == "moderate"
    assert strength(5) == "weak"


def test_dark_pool_strength_bands():
    def strength(n):
        obs = {"X": {"dark_pool": {"notional_signed": n}}}
        return scan(["X"], "d", adapters=_bundle_adapters(obs), generated_at=GEN)["signals"][0]["strength"]
    assert strength(12_000_000) == "strong"
    assert strength(5_000_000) == "moderate"
    assert strength(1_000_000) == "weak"


def test_signal_type_sweep_vs_call_flow():
    sweep = scan(["X"], "d", adapters=_bundle_adapters({"X": {"flow": {"ask_side_call_premium": 1e6, "is_sweep": True}}}),
                 generated_at=GEN)["signals"][0]
    flow = scan(["Y"], "d", adapters=_bundle_adapters({"Y": {"flow": {"ask_side_call_premium": 1e6, "is_sweep": False}}}),
                generated_at=GEN)["signals"][0]
    assert sweep["signal_type"] == "sweep"
    assert flow["signal_type"] == "call_flow"


# ════════════════════════════════════════════════════════════════════════════
# 4. gamma / IV MODIFIER (±1 notch, clamped) + provenance
# ════════════════════════════════════════════════════════════════════════════
def test_gamma_short_lifts_strength_one_notch():
    obs = {"X": {"flow": {"ask_side_call_premium": 1_000_000},   # base = moderate
                 "gamma": {"regime": "short_gamma", "strength": "clear"}}}
    sig = scan(["X"], "d", adapters=_bundle_adapters(obs), generated_at=GEN)["signals"][0]
    assert sig["strength"] == "strong"
    assert sig["detail"]["gamma_regime"] == "short_gamma"


def test_gamma_long_tempers_strength():
    obs = {"X": {"flow": {"ask_side_call_premium": 1_000_000},   # base = moderate
                 "gamma": {"regime": "long_gamma"}}}
    sig = scan(["X"], "d", adapters=_bundle_adapters(obs), generated_at=GEN)["signals"][0]
    assert sig["strength"] == "weak"


def test_iv_expensive_tempers_strength():
    obs = {"X": {"flow": {"ask_side_call_premium": 3_000_000},   # base = strong
                 "iv": {"classification": "expensive", "iv_rank": 82}}}
    sig = scan(["X"], "d", adapters=_bundle_adapters(obs), generated_at=GEN)["signals"][0]
    assert sig["strength"] == "moderate"
    assert sig["detail"]["iv_classification"] == "expensive"


def test_modifier_is_clamped_to_one_notch():
    # long_gamma (-1) + expensive IV (-1) must clamp to -1, not -2:
    # base strong -> moderate (NOT weak).
    obs = {"X": {"flow": {"ask_side_call_premium": 3_000_000},
                 "gamma": {"regime": "long_gamma"},
                 "iv": {"classification": "expensive"}}}
    sig = scan(["X"], "d", adapters=_bundle_adapters(obs), generated_at=GEN)["signals"][0]
    assert sig["strength"] == "moderate"


# ════════════════════════════════════════════════════════════════════════════
# 5. TOLERANCE + empty-day honesty + min-strength
# ════════════════════════════════════════════════════════════════════════════
def test_empty_day_emits_empty_signals_not_omitted():
    cache = scan(["ANET", "NVDA"], "2026-05-29", adapters=_bundle_adapters({}), generated_at=GEN)
    assert cache["signals"] == []
    assert "signals" in cache  # never omit the key


def test_raising_adapter_skips_never_aborts():
    class _Boom:
        def flow(self, t):
            raise RuntimeError("network down")
        def oi(self, t):
            return {"oi_change_pct": 40, "side": "call"}  # this one still lands

    cache = scan(["X"], "d", adapters=_Boom(), generated_at=GEN)
    assert len(cache["signals"]) == 1
    assert cache["signals"][0]["signal_type"] == "oi_build"


def test_blank_and_missing_tickers_skipped():
    obs = {"X": {"flow": {"ask_side_call_premium": 1e6}}}
    cache = scan(["X", "", "   ", "MISSING"], "d", adapters=_bundle_adapters(obs), generated_at=GEN)
    assert [s["ticker"] for s in cache["signals"]] == ["X"]


def test_min_strength_filter_drops_weak():
    obs = {"W": {"flow": {"ask_side_call_premium": 100_000}},        # weak
           "M": {"flow": {"ask_side_call_premium": 1_000_000}}}      # moderate
    all_sigs = scan(["W", "M"], "d", adapters=_bundle_adapters(obs), generated_at=GEN, min_strength="weak")
    only_mod = scan(["W", "M"], "d", adapters=_bundle_adapters(obs), generated_at=GEN, min_strength="moderate")
    assert {s["ticker"] for s in all_sigs["signals"]} == {"W", "M"}
    assert {s["ticker"] for s in only_mod["signals"]} == {"M"}


def test_determinism_same_inputs_same_cache():
    obs = {
        "ANET": {"flow": {"ask_side_call_premium": 2_100_000, "call_put_ratio": 3.0, "is_sweep": True}},
        "NVDA": {"oi": {"oi_change_pct": 38.0, "side": "call", "strikes": [1300, 1350]}},
    }
    a = scan(["ANET", "NVDA"], "2026-05-29", adapters=_bundle_adapters(obs), generated_at=GEN)
    b = scan(["ANET", "NVDA"], "2026-05-29", adapters=_bundle_adapters(obs), generated_at=GEN)
    assert a == b


def test_signal_emission_order_is_stable():
    # universe order, then flow -> oi -> dark_pool within a ticker.
    obs = {"X": {"dark_pool": {"notional_signed": 12_000_000},
                 "flow": {"ask_side_call_premium": 2_000_000},
                 "oi": {"oi_change_pct": 40, "side": "call"}}}
    sigs = scan(["X"], "d", adapters=_bundle_adapters(obs), generated_at=GEN)["signals"]
    assert [s["signal_type"] for s in sigs] == ["call_flow", "oi_build", "dark_pool_accum"]


def test_per_signal_as_of_passes_through_when_present():
    obs = {"X": {"flow": {"ask_side_call_premium": 2e6, "data_time": "2026-05-29T15:30:00Z"}}}
    sig = scan(["X"], "d", adapters=_bundle_adapters(obs), generated_at=GEN)["signals"][0]
    assert sig["as_of"] == "2026-05-29T15:30:00Z"


# ════════════════════════════════════════════════════════════════════════════
# 6. NORMALIZERS — the raw-UW -> observation producer boundary
# ════════════════════════════════════════════════════════════════════════════
def test_normalize_flow_aggregates_ask_side():
    # real get_flow_alerts shape: bare list, STRING premiums, total_ask_side_prem per row,
    # has_sweep boolean / alert_rule (confirmed live NVDA 2026-06-02).
    raw = [
        {"type": "call", "total_premium": "1500000", "total_ask_side_prem": "1500000", "alert_rule": "RepeatedHits"},
        {"type": "call", "total_premium": "600000", "total_ask_side_prem": "600000", "has_sweep": True},
        {"type": "put", "total_premium": "400000", "total_ask_side_prem": "400000", "alert_rule": "RepeatedHits"},
    ]
    obs = normalize_flow(raw)
    assert obs["ask_side_call_premium"] == 2_100_000
    assert obs["put_premium"] == 400_000
    assert obs["is_sweep"] is True
    assert obs["call_put_ratio"] == 5.25


def test_normalize_flow_empty_returns_none():
    assert normalize_flow([]) is None
    assert normalize_flow({"data": []}) is None
    assert normalize_flow(None) is None


def test_normalize_oi_parses_occ_and_scales_fraction():
    # real get_open_interest_changes shape: no type/strike field (parse OCC option_symbol);
    # oi_change is a FRACTION (0.40 == 40%); oi_diff_plain is the absolute change.
    raw = [
        {"option_symbol": "NVDA260605C00230000", "oi_change": 0.40, "oi_diff_plain": 5000},
        {"option_symbol": "NVDA260612C00235000", "oi_change": 0.25, "oi_diff_plain": 3000},
        {"option_symbol": "NVDA260605P00200000", "oi_change": 0.10, "oi_diff_plain": 1000},
    ]
    obs = normalize_oi(raw)
    assert obs["side"] == "call"            # call abs-change 8000 > put 1000
    assert obs["oi_change_pct"] == 40.0     # max(0.40, 0.25) * 100
    assert obs["strikes"] == [230, 235]     # parsed from the OCC symbols


def test_normalize_oi_none_without_percentage():
    # absolute change present but no oi_change/oi_change_pct -> can't grade strength -> None
    raw = [{"option_symbol": "NVDA260605C00230000", "oi_diff_plain": 5000}]
    assert normalize_oi(raw) is None


def test_normalize_dark_pool_signs_by_nbbo_mid_and_counts_sessions():
    # real get_dark_pool_trades shape: STRING premium, nbbo_ask/nbbo_bid, executed_at; NO
    # VWAP field -> sign from price vs NBBO mid (confirmed live NVDA 2026-06-02).
    raw = [
        {"premium": "8000000", "price": "214.50", "nbbo_ask": "214.45", "nbbo_bid": "214.37",
         "executed_at": "2026-05-28T20:16:49Z"},    # price > mid -> +8M
        {"premium": "6000000", "price": "214.25", "nbbo_ask": "214.05", "nbbo_bid": "214.00",
         "executed_at": "2026-05-27T20:00:00Z"},    # price > mid -> +6M
        {"premium": "2000000", "price": "214.00", "nbbo_ask": "214.40", "nbbo_bid": "214.30",
         "executed_at": "2026-05-27T21:00:00Z"},    # price < mid -> -2M
    ]
    obs = normalize_dark_pool(raw)
    assert obs["notional_signed"] == 12_000_000     # +8 +6 -2
    assert obs["sessions"] == 2                       # 05-28 + 05-27


def test_normalize_dark_pool_derives_notional_and_defaults_sign_positive():
    # premium absent -> size*price; no NBBO -> default accumulation (+)
    raw = [{"size": 100_000, "price": "50.0", "executed_at": "2026-05-28T20:00:00Z"}]
    obs = normalize_dark_pool(raw)
    assert obs["notional_signed"] == 5_000_000


# ── gamma / IV normalizers use INJECTED pure fns (no src/ dependency in tests) ──
def _fake_gamma(payload):
    assert payload["ticker"] and payload["spot"] and payload["strikes"]
    return {"regime": "short_gamma", "strength": "clear", "implication": "trending tape"}


def _fake_iv(ticker, iv_rank=None, atm_iv_current=None, atm_iv_30d_mean=None, **kw):
    return SimpleNamespace(classification="expensive", iv_rank=iv_rank)


def test_normalize_gamma_with_injected_analyze():
    obs = normalize_gamma([{"strike": 100, "gamma": 1}], spot=101.0, ticker="X", analyze=_fake_gamma)
    assert obs["regime"] == "short_gamma"
    assert obs["strength"] == "clear"


def test_normalize_gamma_tolerant_without_inputs():
    assert normalize_gamma([], spot=None, ticker="X", analyze=_fake_gamma) is None
    assert normalize_gamma([{"strike": 1}], spot=None, ticker="X", analyze=_fake_gamma) is None
    assert normalize_gamma([{"strike": 1}], spot=10, ticker="X", analyze=None) is None


def test_normalize_iv_with_injected_classify():
    obs = normalize_iv({"iv_rank": 82, "atm_iv": 0.55}, ticker="X", classify=_fake_iv)
    assert obs["classification"] == "expensive"
    assert obs["iv_rank"] == 82


def test_normalize_iv_none_without_rank():
    assert normalize_iv({"atm_iv": 0.5}, ticker="X", classify=_fake_iv) is None
    assert normalize_iv(None, ticker="X", classify=_fake_iv) is None


def test_observation_from_uw_assembles_full_observation():
    obs = observation_from_uw(
        ticker="NVDA", spot=227.0,
        flow=[{"type": "call", "total_premium": "2000000", "total_ask_side_prem": "2000000", "has_sweep": True}],
        oi=[{"option_symbol": "NVDA260605C00230000", "oi_change": 0.35, "oi_diff_plain": 5000}],
        dark_pool=[{"premium": "12000000", "price": "214.5", "nbbo_ask": "214.45",
                    "nbbo_bid": "214.37", "executed_at": "2026-05-28T20:00:00Z"}],
        greek=[{"strike": 100, "gamma": 1}],
        iv={"iv_rank": 82},
        gamma_analyze=_fake_gamma, iv_classify=_fake_iv,
    )
    assert set(obs) == {"flow", "oi", "dark_pool", "gamma", "iv"}
    # and the assembled observation drives a coherent scan
    cache = scan(["NVDA"], "d", adapters=_bundle_adapters({"NVDA": obs}), generated_at=GEN)
    types = {s["signal_type"] for s in cache["signals"]}
    assert types == {"sweep", "oi_build", "dark_pool_accum"}


# ════════════════════════════════════════════════════════════════════════════
# 7. UNIVERSE loaders
# ════════════════════════════════════════════════════════════════════════════
def test_universe_from_theses_reads_tickers(tmp_path):
    import json
    p = tmp_path / "theses.json"
    p.write_text(json.dumps([{"ticker": "nvda"}, {"ticker": "SMH"}, {"ticker": "nvda"}, {"no_ticker": 1}]))
    assert universe_from_theses(str(p)) == ["NVDA", "SMH"]   # upper, dedup, order, skip-blank


def test_universe_from_bundle_prefers_explicit_then_observation_keys():
    assert universe_from_bundle({"universe": ["anet", "nvda"]}) == ["ANET", "NVDA"]
    assert universe_from_bundle({"observations": {"mu": {}, "anet": {}}}) == ["MU", "ANET"]
    assert universe_from_bundle([]) == []


def test_real_repo_theses_loads_as_universe():
    # the committed conviction universe loads and is non-empty
    uni = universe_from_theses(S.DEFAULT_THESES_PATH)
    assert isinstance(uni, list) and len(uni) >= 1
    assert all(t == t.upper() for t in uni)

# ════════════════════════════════════════════════════════════════════════════
# 8. LIVE-SHAPE REGRESSION — verbatim (trimmed) NVDA payloads pulled from the UW
#    connector on 2026-06-02. Locks the field maps against reality: if a future
#    UW response renames a field these break, instead of silently emitting [].
# ════════════════════════════════════════════════════════════════════════════
LIVE_FLOW_NVDA = [  # get_flow_alerts(NVDA) — 2 call rows + 1 put row, real fields
    {"has_sweep": False, "type": "put", "total_premium": "123680", "total_bid_side_prem": "0",
     "total_ask_side_prem": "123680", "alert_rule": "RepeatedHits", "option_chain": "NVDA280121P00170000"},
    {"has_sweep": False, "type": "call", "total_premium": "226250", "total_bid_side_prem": "27150",
     "total_ask_side_prem": "199100", "alert_rule": "RepeatedHits", "option_chain": "NVDA260918C00240000"},
    {"has_sweep": True, "type": "call", "total_premium": "123510", "total_bid_side_prem": "0",
     "total_ask_side_prem": "123510", "alert_rule": "RepeatedHits", "option_chain": "NVDA260717C00240000"},
]
LIVE_OI_NVDA = [  # get_open_interest_changes(NVDA) — volume_candles trimmed off (unused)
    {"option_symbol": "NVDA260605C00230000", "oi_change": "0.71013212746414187805", "oi_diff_plain": 20101},
    {"option_symbol": "NVDA260612C00235000", "oi_change": "2.6057858376511226", "oi_diff_plain": 18105},
    {"option_symbol": "NVDA260603C00225000", "oi_change": "1.11817603778726496503", "oi_diff_plain": 12310},
]
LIVE_DP_NVDA = [  # get_dark_pool_trades(NVDA, order=prem) — top prints, real fields
    {"size": 3360000, "price": "214.25", "premium": "719880000.00", "nbbo_ask": "214.45",
     "nbbo_bid": "214.37", "executed_at": "2026-05-28T20:16:49Z"},
    {"size": 3041179, "price": "214.25", "premium": "651572600.75", "nbbo_ask": "214.05",
     "nbbo_bid": "214", "executed_at": "2026-05-28T20:02:20Z"},
]


def test_live_flow_shape_extracts_bullish_calls():
    obs = normalize_flow(LIVE_FLOW_NVDA)
    assert obs is not None
    assert obs["ask_side_call_premium"] == 199100 + 123510   # the two ask-side call rows
    assert obs["ask_side_put_premium"] == 123680
    assert obs["is_sweep"] is True                            # the 3rd row's has_sweep
    sig = scan(["NVDA"], "d", adapters=_bundle_adapters({"NVDA": {"flow": obs}}), generated_at=GEN)["signals"][0]
    assert sig["signal_type"] == "sweep" and sig["direction"] == "bullish"


def test_live_oi_shape_parses_occ_and_scales():
    obs = normalize_oi(LIVE_OI_NVDA)
    assert obs is not None
    assert obs["side"] == "call"
    assert obs["oi_change_pct"] == pytest.approx(260.578, rel=1e-3)   # 2.6057.. fraction * 100
    assert obs["strikes"] == [230, 235, 225]


def test_live_dark_pool_shape_sums_signed_notional():
    obs = normalize_dark_pool(LIVE_DP_NVDA)
    assert obs is not None
    # row1 price 214.25 < mid 214.41 -> -; row2 price 214.25 >= mid 214.025 -> +
    assert obs["notional_signed"] == pytest.approx(651572600.75 - 719880000.00, rel=1e-6)
    assert obs["sessions"] == 1                               # both 2026-05-28


def test_live_payloads_round_trip_through_the_consumer():
    obs = observation_from_uw(
        ticker="NVDA", flow=LIVE_FLOW_NVDA, oi=LIVE_OI_NVDA, dark_pool=LIVE_DP_NVDA,
    )
    cache = scan(["NVDA"], "2026-06-02", adapters=_bundle_adapters({"NVDA": obs}), generated_at=GEN)
    cards = uw_opportunity_cards(cache)
    assert len(cards) == 3                                    # flow + oi + dark_pool all extracted
    assert all(c["kind"] == UW_OPP_KIND for c in cards)
    assert {c["data"]["signal_type"] for c in cards} == {"sweep", "oi_build", "dark_pool_accum"}
