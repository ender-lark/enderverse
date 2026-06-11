"""Pattern engine wave-1 tests (Task 4 / C7).

Covers: threshold edges, thesis-break conflict veto, D-counts-no-points,
prediction_signals honest-empty stub, and validate_decision_card on every
emitted card.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import decision_card as dc
import pattern_engine as pe
from tunables import load_conviction_weights, load_goal_tunables

TODAY = "2026-06-10"
W = load_conviction_weights()
G = load_goal_tunables()


def _validate_card(card):
    """Every detector output must pass validate_decision_card."""
    inner = card["decision_card"]
    problems = dc.validate_decision_card(inner)
    assert not problems, f"invalid card: {problems}"


# ---------------------------------------------------------------------------
# ENDORSED-DIP
# ---------------------------------------------------------------------------
def _prospect(ticker, add_price, add_date):
    return {
        "add_date": add_date,
        "add_price": add_price,
        "add_price_date": add_date,
        "conviction": "BUILDING",
        "direction": "long",
        "ticker": ticker,
    }


def test_endorsed_dip_triggers_at_exact_threshold():
    prospects = {"NVDA": _prospect("NVDA", 100.0, "2026-06-01")}
    cards = pe.detect_endorsed_dip(
        prospects=prospects,
        source_calls=[],
        current_prices={"NVDA": 88.0},  # exactly 12% below add_price
        weights=W, goal=G, today=TODAY,
    )
    assert len(cards) == 1
    card = cards[0]
    assert card["pattern"] == "ENDORSED-DIP"
    assert card["ticker"] == "NVDA"
    assert abs(card["drop_pct"] - 12.0) < 1e-6
    _validate_card(card)


def test_endorsed_dip_does_not_trigger_just_above_threshold():
    prospects = {"NVDA": _prospect("NVDA", 100.0, "2026-06-01")}
    cards = pe.detect_endorsed_dip(
        prospects=prospects,
        source_calls=[],
        current_prices={"NVDA": 88.01},  # only 11.99% below
        weights=W, goal=G, today=TODAY,
    )
    assert cards == []


def test_endorsed_dip_date_at_lookback_boundary():
    # Default lookback is 30 days; today=2026-06-10, anchor=2026-05-11 → exactly 30d.
    prospects = {"NVDA": _prospect("NVDA", 100.0, "2026-05-11")}
    cards = pe.detect_endorsed_dip(
        prospects=prospects, source_calls=[],
        current_prices={"NVDA": 80.0}, weights=W, goal=G, today=TODAY,
    )
    assert len(cards) == 1, "30-day boundary should trigger"

    prospects = {"NVDA": _prospect("NVDA", 100.0, "2026-05-10")}  # 31 days
    cards = pe.detect_endorsed_dip(
        prospects=prospects, source_calls=[],
        current_prices={"NVDA": 80.0}, weights=W, goal=G, today=TODAY,
    )
    assert cards == [], "31-day-old anchor must NOT trigger"


def test_endorsed_dip_vetoes_on_bearish_source_call():
    prospects = {"NVDA": _prospect("NVDA", 100.0, "2026-06-01")}
    bearish = [{
        "ticker": "NVDA", "tier": "A", "source": "newton",
        "direction": "bearish", "date": "2026-06-08",
        "verbatim_quote": "thesis broken below 80",
    }]
    cards = pe.detect_endorsed_dip(
        prospects=prospects, source_calls=bearish,
        current_prices={"NVDA": 80.0}, weights=W, goal=G, today=TODAY,
    )
    assert cards == []


def test_endorsed_dip_vetoes_on_source_conflicts_set():
    prospects = {"MAGS": _prospect("MAGS", 100.0, "2026-06-01")}
    cards = pe.detect_endorsed_dip(
        prospects=prospects, source_calls=[],
        current_prices={"MAGS": 80.0},
        source_conflicts={"MAGS"},
        weights=W, goal=G, today=TODAY,
    )
    assert cards == []


def test_endorsed_dip_skips_when_no_current_price():
    prospects = {"NVDA": _prospect("NVDA", 100.0, "2026-06-01")}
    cards = pe.detect_endorsed_dip(
        prospects=prospects, source_calls=[],
        current_prices={}, weights=W, goal=G, today=TODAY,
    )
    assert cards == []


# ---------------------------------------------------------------------------
# EXPLICIT-ADD
# ---------------------------------------------------------------------------
def test_explicit_add_emits_for_fresh_tier_a():
    calls = [{
        "ticker": "PLTR", "tier": "A", "source": "newton",
        "direction": "bullish", "date": "2026-06-05",
        "verbatim_quote": "long PLTR above 30, target 40, stop 27",
        "id": "row-1",
    }]
    cards = pe.detect_explicit_add(
        source_calls=calls, weights=W, goal=G, today=TODAY,
    )
    assert len(cards) == 1
    card = cards[0]
    assert card["pattern"] == "EXPLICIT-ADD"
    assert card["ticker"] == "PLTR"
    assert card["tier"] == "A"
    _validate_card(card)


def test_explicit_add_ignores_expired_tier_a():
    # tier_window_days["A"] is 14 → 21 days old must be skipped.
    calls = [{
        "ticker": "OLD", "tier": "A", "source": "newton",
        "direction": "bullish", "date": "2026-05-20",  # 21d old vs 2026-06-10
    }]
    cards = pe.detect_explicit_add(
        source_calls=calls, weights=W, goal=G, today=TODAY,
    )
    assert cards == []


def test_explicit_add_ignores_non_tier_a():
    calls = [
        {"ticker": "BBB", "tier": "B", "source": "newton", "date": "2026-06-05"},
        {"ticker": "CCC", "tier": "C", "source": "lee", "date": "2026-06-05"},
        {"ticker": "DDD", "tier": "D", "source": "newton", "date": "2026-06-05"},
    ]
    cards = pe.detect_explicit_add(
        source_calls=calls, weights=W, goal=G, today=TODAY,
    )
    assert cards == []


def test_explicit_add_skips_bearish_tier_a():
    calls = [{
        "ticker": "SHORT", "tier": "A", "source": "newton",
        "direction": "bearish", "date": "2026-06-05",
    }]
    cards = pe.detect_explicit_add(
        source_calls=calls, weights=W, goal=G, today=TODAY,
    )
    assert cards == []


def test_explicit_add_respects_source_conflicts():
    calls = [{
        "ticker": "X", "tier": "A", "source": "newton",
        "direction": "bullish", "date": "2026-06-05",
    }]
    cards = pe.detect_explicit_add(
        source_calls=calls, source_conflicts={"X"},
        weights=W, goal=G, today=TODAY,
    )
    assert cards == []


# ---------------------------------------------------------------------------
# DRUMBEAT — D-counts-no-points
# ---------------------------------------------------------------------------
def _d_row(ticker, source, day):
    return {
        "ticker": ticker, "tier": "D", "source": source,
        "direction": "bullish",
        "date": f"2026-06-{day:02d}",
        "verbatim_quote": "favor/should narrative",
    }


def test_drumbeat_d_only_emits_card_with_zero_conviction_points():
    # 4 Tier-D mentions, same source, same ticker → drumbeat triggers,
    # but Tier D adds zero conviction points (P-SOURCE-CALIBRATION doctrine).
    calls = [_d_row("XYZ", "newton", d) for d in (1, 3, 5, 8)]
    cards = pe.detect_drumbeat(
        source_calls=calls, weights=W, goal=G, today=TODAY,
    )
    assert len(cards) == 1
    card = cards[0]
    assert card["pattern"] == "DRUMBEAT"
    assert card["mentions"] == 4
    assert card["tier_d_only"] is True
    # Doctrine: Tier-D never scores → conviction.points == 0.
    assert card["conviction"]["points"] == 0.0
    assert card["conviction"]["groups"]["fs"] == 0.0
    _validate_card(card)


def test_drumbeat_requires_min_mentions():
    calls = [_d_row("XYZ", "newton", d) for d in (1, 3, 5)]  # only 3
    cards = pe.detect_drumbeat(
        source_calls=calls, weights=W, goal=G, today=TODAY,
    )
    assert cards == []


def test_drumbeat_requires_single_source_concentration():
    # 2 from newton + 2 from lee on same ticker → no source hits 4.
    calls = [
        _d_row("XYZ", "newton", 1), _d_row("XYZ", "newton", 3),
        _d_row("XYZ", "lee", 5), _d_row("XYZ", "lee", 8),
    ]
    cards = pe.detect_drumbeat(
        source_calls=calls, weights=W, goal=G, today=TODAY,
    )
    assert cards == []


def test_drumbeat_window_filter_drops_stale_rows():
    # drumbeat_window_days = 30; row dated 2026-05-01 is 40d old → dropped.
    calls = [
        {"ticker": "OLD", "tier": "D", "source": "newton",
         "direction": "bullish", "date": "2026-05-01"},
        _d_row("OLD", "newton", 1), _d_row("OLD", "newton", 3),
        _d_row("OLD", "newton", 5),
    ]
    cards = pe.detect_drumbeat(
        source_calls=calls, weights=W, goal=G, today=TODAY,
    )
    # Only 3 rows are fresh → drumbeat does not fire.
    assert cards == []


def test_drumbeat_mixed_tiers_card_still_validates():
    # 2 Tier-A + 2 Tier-D from same source: drumbeat fires, conviction
    # picks up the A's (live, non-track-only) and D's stay 0.
    calls = [
        {"ticker": "ABC", "tier": "A", "source": "newton",
         "direction": "bullish", "date": "2026-06-05",
         "verbatim_quote": "entry/stop/target"},
        {"ticker": "ABC", "tier": "A", "source": "newton",
         "direction": "bullish", "date": "2026-06-07"},
        _d_row("ABC", "newton", 1), _d_row("ABC", "newton", 3),
    ]
    cards = pe.detect_drumbeat(
        source_calls=calls, weights=W, goal=G, today=TODAY,
    )
    assert len(cards) == 1
    card = cards[0]
    assert card["tier_d_only"] is False
    assert card["mentions"] == 4
    # Conviction reflects the live A items, never the D items.
    assert card["conviction"]["points"] > 0
    _validate_card(card)


# ---------------------------------------------------------------------------
# prediction_signals — pattern slot #11 honest-empty stub
# ---------------------------------------------------------------------------
def test_prediction_signals_absent_returns_not_checked(tmp_path):
    p = tmp_path / "prediction_signals.json"
    payload = pe.load_prediction_signals(p)
    assert payload["status"] == "not_checked"
    assert payload["rows"] == []
    assert "not wired" in payload["note"]


def test_prediction_signals_valid_payload(tmp_path):
    p = tmp_path / "prediction_signals.json"
    p.write_text(json.dumps({
        "as_of": "2026-06-10",
        "rows": [{
            "venue": "Polymarket",
            "topic": "Sept FOMC cuts ≥25bps",
            "probability": 0.62,
            "delta_24h": 0.04,
            "date": "2026-06-09",
            "related_tickers": ["qqq", "tlt"],
        }],
    }), encoding="utf-8")
    payload = pe.load_prediction_signals(p)
    assert payload["status"] == "ok"
    assert payload["rows"][0]["venue"] == "Polymarket"
    assert payload["rows"][0]["related_tickers"] == ["QQQ", "TLT"]


def test_prediction_signals_invalid_json_returns_invalid(tmp_path):
    p = tmp_path / "prediction_signals.json"
    p.write_text("{not json", encoding="utf-8")
    payload = pe.load_prediction_signals(p)
    assert payload["status"] == "invalid"
    assert "not valid JSON" in payload["note"]


def test_prediction_signals_invalid_probability_out_of_range(tmp_path):
    p = tmp_path / "prediction_signals.json"
    p.write_text(json.dumps({
        "rows": [{"venue": "v", "topic": "t", "probability": 1.5}],
    }), encoding="utf-8")
    payload = pe.load_prediction_signals(p)
    assert payload["status"] == "invalid"
    assert "[0, 1]" in payload["note"]


def test_prediction_signals_missing_required_field(tmp_path):
    p = tmp_path / "prediction_signals.json"
    p.write_text(json.dumps({"rows": [{"venue": "", "topic": "t", "probability": 0.5}]}),
                 encoding="utf-8")
    payload = pe.load_prediction_signals(p)
    assert payload["status"] == "invalid"


# ---------------------------------------------------------------------------
# Unified runner
# ---------------------------------------------------------------------------
def test_detect_patterns_runs_all_lanes_with_honesty_block(tmp_path):
    prospects = {"NVDA": _prospect("NVDA", 100.0, "2026-06-01")}
    calls = [
        _d_row("XYZ", "newton", d) for d in (1, 3, 5, 8)
    ] + [{
        "ticker": "PLTR", "tier": "A", "source": "newton",
        "direction": "bullish", "date": "2026-06-05",
        "verbatim_quote": "long PLTR",
    }]
    out = pe.detect_patterns(
        prospects=prospects,
        source_calls=calls,
        current_prices={"NVDA": 80.0},
        weights=W, goal=G, today=TODAY,
        prediction_signals_path=tmp_path / "missing.json",
    )
    assert set(out["cards"]) == {
        "endorsed_dip", "explicit_add", "drumbeat",
        "stale_leaps", "overexposure_rotation", "tier_b_side_play",
    }
    assert len(out["cards"]["endorsed_dip"]) == 1
    assert len(out["cards"]["explicit_add"]) == 1
    assert len(out["cards"]["drumbeat"]) == 1
    # Wave-2 lanes are honest-empty for the lanes whose inputs weren't supplied
    # (held_options, drift_rows). Tier-B side-play reads from prospects, which
    # IS supplied here — and the helper marks the prospect BUILDING — so we
    # expect one side-play card for NVDA.
    assert out["cards"]["stale_leaps"] == []
    assert out["cards"]["overexposure_rotation"] == []
    assert {c["ticker"] for c in out["cards"]["tier_b_side_play"]} == {"NVDA"}
    for card in out["cards"]["tier_b_side_play"]:
        _validate_card(card)
    assert out["prediction_signals"]["status"] == "not_checked"
    assert out["honesty"]["prediction_signals_status"] == "not_checked"
    assert out["honesty"]["lanes_not_checked"] == []
    for lane in ("endorsed_dip", "explicit_add", "drumbeat"):
        for card in out["cards"][lane]:
            _validate_card(card)


def test_detect_patterns_empty_inputs_returns_empty_cards():
    out = pe.detect_patterns(
        prospects={}, source_calls=[], current_prices={},
        weights=W, goal=G, today=TODAY,
        prediction_signals_path=Path("/nonexistent/prediction_signals.json"),
    )
    assert out["cards"]["endorsed_dip"] == []
    assert out["cards"]["explicit_add"] == []
    assert out["cards"]["drumbeat"] == []
    assert out["cards"]["stale_leaps"] == []
    assert out["cards"]["overexposure_rotation"] == []
    assert out["cards"]["tier_b_side_play"] == []
    assert out["prediction_signals"]["status"] == "not_checked"
    # Honest "not_checked" markers when wave-2 caches are absent.
    assert "stale_leaps_status" in out["honesty"]
    assert "overexposure_rotation_status" in out["honesty"]


# ---------------------------------------------------------------------------
# Wave-2: STALE-LEAPS
# ---------------------------------------------------------------------------
def test_stale_leaps_emits_when_dte_below_threshold():
    held = [{
        "ticker": "NVDA", "expiry_date": "2026-09-19",  # ~101d from today
        "option_type": "call", "strike": 180.0, "contracts": 5,
    }]
    cards = pe.detect_stale_leaps(
        held_options=held, weights=W, goal=G, today=TODAY,
    )
    assert len(cards) == 1
    card = cards[0]
    assert card["pattern"] == "STALE-LEAPS"
    assert card["dte"] < int(W["pattern_thresholds"]["stale_leaps_warn_dte"])
    assert card["contracts"] == 5
    _validate_card(card)


def test_stale_leaps_does_not_emit_above_threshold():
    held = [{
        "ticker": "NVDA", "expiry_date": "2028-01-21",
        "option_type": "call", "strike": 180.0, "contracts": 5,
    }]
    cards = pe.detect_stale_leaps(
        held_options=held, weights=W, goal=G, today=TODAY,
    )
    assert cards == []


def test_stale_leaps_thesis_window_after_expiry_flags_roll_candidate():
    held = [{
        "ticker": "NVDA", "expiry_date": "2026-09-19",
        "option_type": "call", "strike": 180.0, "contracts": 1,
        "thesis_window_end": "2027-12-31",
    }]
    cards = pe.detect_stale_leaps(
        held_options=held, weights=W, goal=G, today=TODAY,
    )
    assert len(cards) == 1
    band = cards[0]["decision_card"]["move"]["band"]
    assert "AFTER option expiry" in band
    assert "roll candidate" in band


# ---------------------------------------------------------------------------
# Wave-2: OVEREXPOSURE-ROTATION
# ---------------------------------------------------------------------------
def test_overexposure_rotation_fires_on_oversized_plus_turning_down():
    drift = [{"ticker": "MAGS", "direction": "OVERSIZED", "sleeve": "ai_semis"}]
    cards = pe.detect_overexposure_rotation(
        drift_rows=drift,
        sleeve_states={"ai_semis": "TURNING DOWN"},
        weights=W, goal=G, today=TODAY,
    )
    assert len(cards) == 1
    card = cards[0]
    assert card["pattern"] == "OVEREXPOSURE-ROTATION"
    assert card["direction"] == "TRIM"
    assert any("TURNING DOWN" in t for t in card["triggers"])
    _validate_card(card)


def test_overexposure_rotation_fires_on_oversized_plus_bearish_tier_a():
    drift = [{"ticker": "MAGS", "direction": "OVERSIZED", "sleeve": "ai_semis"}]
    calls = [{
        "ticker": "MAGS", "tier": "A", "source": "newton",
        "direction": "bearish", "date": "2026-06-05",
        "verbatim_quote": "MAGS technical break",
    }]
    cards = pe.detect_overexposure_rotation(
        drift_rows=drift, source_calls=calls,
        weights=W, goal=G, today=TODAY,
    )
    assert len(cards) == 1
    assert any("Tier-A" in t for t in cards[0]["triggers"])


def test_overexposure_rotation_no_trigger_means_no_card():
    drift = [{"ticker": "MAGS", "direction": "OVERSIZED", "sleeve": "ai_semis"}]
    cards = pe.detect_overexposure_rotation(
        drift_rows=drift, sleeve_states={"ai_semis": "STABLE"},
        weights=W, goal=G, today=TODAY,
    )
    assert cards == []


def test_overexposure_rotation_ignores_undersized_rows():
    drift = [{"ticker": "X", "direction": "UNDERSIZED", "sleeve": "ai_semis"}]
    cards = pe.detect_overexposure_rotation(
        drift_rows=drift, sleeve_states={"ai_semis": "TURNING DOWN"},
        weights=W, goal=G, today=TODAY,
    )
    assert cards == []


# ---------------------------------------------------------------------------
# Wave-2: TIER-B SIDE PLAYS
# ---------------------------------------------------------------------------
def test_tier_b_side_play_fires_for_building_conviction():
    prospects = {
        "CRS": {"provenance": "FS Top 5 SMID - 2026-05-28",
                "conviction": "BUILDING", "add_date": "2026-05-28"},
        "RIPE": {"provenance": "FS Top 5 - 2026-05-28",
                 "conviction": "BUILDING", "add_date": "2026-05-28"},
    }
    cards = pe.detect_tier_b_side_plays(
        prospects=prospects, weights=W, goal=G, today=TODAY,
    )
    assert {c["ticker"] for c in cards} == {"CRS", "RIPE"}
    for card in cards:
        assert card["pattern"] == "TIER-B-SIDE-PLAY"
        assert card["decision_card"]["impact"]["base"] == "sleeve"
        _validate_card(card)


def test_tier_b_side_play_fires_for_smid_top5_membership_even_without_building():
    prospects = {
        "STRONG": {"provenance": "FS Top 5 - 2026-05-28",
                   "conviction": "HIGH", "add_date": "2026-05-28"},
    }
    cards = pe.detect_tier_b_side_plays(
        prospects=prospects, smid_top5={"STRONG"},
        weights=W, goal=G, today=TODAY,
    )
    assert len(cards) == 1
    assert "SMID Top-5" in " ".join(cards[0]["triggers"])


def test_tier_b_side_play_skips_when_neither_trigger_present():
    prospects = {
        "QUIET": {"provenance": "FS Top 5 - 2026-05-28",
                  "conviction": "HIGH", "add_date": "2026-05-28"},
    }
    cards = pe.detect_tier_b_side_plays(
        prospects=prospects, weights=W, goal=G, today=TODAY,
    )
    assert cards == []


# ---------------------------------------------------------------------------
# FACTOR-OVERLAP guard (no new card; existing card mutated additively)
# ---------------------------------------------------------------------------
def _stub_buy_card(ticker, direction="BUY"):
    base = {
        "card_id": f"{ticker}-ADD-{TODAY}", "ticker": ticker, "direction": direction,
    }
    dc.attach(base, {
        "move": {"ticker": ticker, "direction": direction,
                 "lane": "test", "band": "$10,000 staged"},
        "conviction": {"read": "MODERATE", "points": 1.0,
                       "groups": {"fs": 1.0}, "raises": []},
        "window": {"class": "OPEN-NOW", "deadline": None,
                   "reasons": ["test"], "flips": []},
        "evidence": {"links": [{"label": "stub", "ref": "test"}]},
        "impact": {"band": "$10,000", "base": "book", "material": False, "basis": "stub"},
    })
    return base


def test_factor_overlap_attaches_caveat_above_threshold():
    cards = [_stub_buy_card("NVDA")]
    out = pe.apply_factor_overlap_caveat(cards, {"NVDA": 38.0}, weights=W)
    assert "factor_overlap_caveat" in out[0]
    assert out[0]["factor_overlap_caveat"]["exposure_pct"] == 38.0
    assert "FACTOR-OVERLAP" in out[0]["decision_card"]["move"]["band"]
    # Validates after mutation.
    assert dc.validate_decision_card(out[0]["decision_card"]) == []


def test_factor_overlap_no_op_below_threshold():
    cards = [_stub_buy_card("NVDA")]
    out = pe.apply_factor_overlap_caveat(cards, {"NVDA": 20.0}, weights=W)
    assert "factor_overlap_caveat" not in out[0]
    assert "FACTOR-OVERLAP" not in out[0]["decision_card"]["move"]["band"]


def test_factor_overlap_skips_non_buy_directions():
    cards = [_stub_buy_card("MAGS", direction="TRIM")]
    out = pe.apply_factor_overlap_caveat(cards, {"MAGS": 60.0}, weights=W)
    assert "factor_overlap_caveat" not in out[0]


def test_factor_overlap_handles_empty_inputs():
    assert pe.apply_factor_overlap_caveat(None, {"X": 50.0}, weights=W) == []
    cards = [_stub_buy_card("X")]
    # Empty exposure map: cards unchanged.
    pe.apply_factor_overlap_caveat(cards, {}, weights=W)
    assert "factor_overlap_caveat" not in cards[0]


# ---------------------------------------------------------------------------
# PARABOLIC-CHASE dampener (window class capped at STAGE-ONLY)
# ---------------------------------------------------------------------------
def test_parabolic_chase_caps_open_now_to_stage_only():
    cards = [_stub_buy_card("MU")]
    assert cards[0]["decision_card"]["window"]["class"] == "OPEN-NOW"
    out = pe.apply_parabolic_chase_dampener(cards, {"MU"})
    assert out[0]["parabolic_chase_dampener"]["applied"] is True
    assert out[0]["decision_card"]["window"]["class"] == "STAGE-ONLY"
    assert any("PARABOLIC-CHASE" in r
               for r in out[0]["decision_card"]["window"]["reasons"])
    assert dc.validate_decision_card(out[0]["decision_card"]) == []


def test_parabolic_chase_leaves_non_open_now_unchanged():
    cards = [_stub_buy_card("MU")]
    cards[0]["decision_card"]["window"]["class"] = "GATED"
    out = pe.apply_parabolic_chase_dampener(cards, {"MU"})
    assert out[0]["decision_card"]["window"]["class"] == "GATED"
    # Dampener flag is still attached because the ticker is flagged,
    # but the class stays at GATED (already below STAGE-ONLY in urgency).


def test_parabolic_chase_ignores_unflagged_tickers():
    cards = [_stub_buy_card("NVDA")]
    out = pe.apply_parabolic_chase_dampener(cards, {"MU"})
    assert "parabolic_chase_dampener" not in out[0]
    assert out[0]["decision_card"]["window"]["class"] == "OPEN-NOW"


def test_parabolic_chase_handles_empty_inputs():
    assert pe.apply_parabolic_chase_dampener(None, {"MU"}) == []
    cards = [_stub_buy_card("MU")]
    pe.apply_parabolic_chase_dampener(cards, None)
    assert "parabolic_chase_dampener" not in cards[0]


# ---------------------------------------------------------------------------
# Unified runner — wave-2 lanes round-trip
# ---------------------------------------------------------------------------
def test_detect_patterns_runs_wave_2_lanes_when_inputs_supplied():
    held = [{
        "ticker": "NVDA", "expiry_date": "2026-09-19",
        "option_type": "call", "strike": 180.0, "contracts": 5,
    }]
    drift = [{"ticker": "MAGS", "direction": "OVERSIZED", "sleeve": "ai_semis"}]
    prospects = {
        "CRS": {"provenance": "FS Top 5 SMID - 2026-05-28",
                "conviction": "BUILDING", "add_date": "2026-05-28"},
    }
    out = pe.detect_patterns(
        prospects=prospects, source_calls=[], current_prices={},
        weights=W, goal=G, today=TODAY,
        held_options=held, drift_rows=drift,
        sleeve_states={"ai_semis": "TURNING DOWN"},
        prediction_signals_path=Path("/nonexistent/prediction_signals.json"),
    )
    assert len(out["cards"]["stale_leaps"]) == 1
    assert len(out["cards"]["overexposure_rotation"]) == 1
    assert len(out["cards"]["tier_b_side_play"]) == 1
    assert "stale_leaps_status" not in out["honesty"]
    assert "overexposure_rotation_status" not in out["honesty"]
