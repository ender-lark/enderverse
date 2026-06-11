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
    assert set(out["cards"]) == {"endorsed_dip", "explicit_add", "drumbeat"}
    assert len(out["cards"]["endorsed_dip"]) == 1
    assert len(out["cards"]["explicit_add"]) == 1
    assert len(out["cards"]["drumbeat"]) == 1
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
    assert out["prediction_signals"]["status"] == "not_checked"
