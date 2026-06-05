import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from full_build_runner import (
    active_parabolic_tickers,
    build_full_feed_from_files,
    normalize_closes_cache,
    normalize_positions_cache,
)
from validators import validate_cockpit_feed


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _series(base, n=70):
    return [base + i for i in range(n)]


def _required_files(src):
    _write(src / "positions.json", {
        "snapshot_date": "2026-06-04",
        "sleeve_value": 100000,
        "positions": [
            {"ticker": "NVDA", "shares": 10, "market_value": 12000, "account": "SKB"},
            {"ticker": "SMH", "shares": 5, "market_value": 8000, "account": "SKB"},
        ],
    })
    _write(src / "theses.json", [
        {"ticker": "NVDA", "tier": "T2", "stance": "ACTIVE", "factor_tags": ["ai_complex"]},
        {"ticker": "SMH", "tier": "T2", "stance": "ACTIVE", "factor_tags": ["semiconductors"]},
    ])
    _write(src / "uw_closes.json", {"SMH": _series(400), "SPY": _series(600)})


def _account_positions_file(src):
    _write(src / "account_positions.json", {
        "snapshot_date": "2026-06-04",
        "sleeve_value": 100000,
        "account_positions": [
            {"ticker": "NVDA", "description": "NVIDIA", "shares": 10, "market_value": 12000, "account": "Taxable", "owner": "SKB", "broker": "Fidelity", "tracked": True},
            {"ticker": "SMH", "description": "Semis ETF", "shares": 5, "market_value": 8000, "account": "IRA", "owner": "Parents", "broker": "Schwab", "tracked": True},
        ],
    })


def _lane_rows(feed):
    return {r["key"]: r for r in feed["lane_status"]["rows"]}


def test_normalize_positions_cache_derives_pct_from_sleeve_value():
    rows, stamp = normalize_positions_cache({
        "snapshot_date": "2026-06-04",
        "sleeve_value": 200000,
        "positions": [{"ticker": "nvda", "market_value": "$20,000", "shares": "10"}],
    })
    assert stamp == "2026-06-04"
    assert rows[0]["ticker"] == "NVDA"
    assert rows[0]["pct"] == 10.0
    assert rows[0]["value"] == 20000.0


def test_normalize_closes_cache_accepts_arrays_and_uw_rows():
    closes = normalize_closes_cache({
        "SMH": [1, "2", "$3"],
        "SPY": {"data": [{"date": "2026-06-02", "c": 5},
                          {"date": "2026-06-01", "c": 4}]},
        "IGV": [{"date": "2026-06-02", "close": 7},
                {"date": "2026-06-01", "close": 6}],
    })
    assert closes["SMH"] == [1.0, 2.0, 3.0]
    assert closes["SPY"] == [4.0, 5.0]
    assert closes["IGV"] == [6.0, 7.0]


def test_active_parabolic_tickers_uses_non_skip_surface_tiers():
    active = active_parabolic_tickers({"results": [
        {"ticker": "VIAV", "surface_tier": "AUTOFIRE"},
        {"ticker": "MU", "surface_tier": "WATCHLIST"},
        {"ticker": "AEHR", "surface_tier": "SKIP"},
    ]})
    assert active == {"VIAV", "MU"}


def test_full_build_runner_loads_convention_files_and_marks_lanes(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _required_files(src)
    _write(src / "uw_opportunity_signals.json", {
        "generated_at": "2026-06-05T10:00:00Z",
        "source": "uw_opportunity_scan",
        "signals": [{
            "ticker": "NVDA",
            "signal_type": "sweep",
            "direction": "bullish",
            "strength": "moderate",
            "evidence": "call sweeps",
        }],
    })
    _write(src / "top_prospects.json", {
        "FN": {
            "ticker": "FN",
            "direction": "long",
            "conviction": "ACT_NOW",
            "urgency": "ACT_NOW",
            "conviction_score": 30,
            "urgency_score": 30,
            "sources": ["FS-Monthly"],
            "corroboration": "Uncorroborated",
        }
    })
    _write(src / "catalysts.json", [
        {"ticker": "NVDA", "date": "2026-06-06", "label": "Earnings"}
    ])
    _write(src / "daily_synthesis.json", {
        "source": "Daily Synthesis",
        "hanging": ["NVDA add only if the gate clears."]
    })

    feed = build_full_feed_from_files(
        src_dir=src,
        as_of="2026-06-05",
        run_timestamp="2026-06-05T14:00:00+00:00",
    )

    assert validate_cockpit_feed(feed) == []
    rows = _lane_rows(feed)
    assert rows["uw_opportunity"]["status"] == "has_data"
    assert rows["top_prospects"]["status"] == "has_data"
    assert rows["catalysts"]["status"] == "has_data"
    assert rows["research"]["status"] == "not_checked"
    assert rows["target_drift"]["status"] == "has_data"
    assert feed["bullish_flow"]["rows"]
    assert feed["prospects"]["counts"]["act_now"] == 1
    assert feed["target_drift"]["actionable_count"] > 0
    assert feed["target_drift"]["rows"]
    assert any(a.get("source") == "daily_synthesis" for a in feed["actions"])


def test_full_build_runner_threads_source_call_freshness_files(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _required_files(src)
    _write(src / "source_calls.json", [
        {"source": "newton", "ticker": "FN", "tier": "A", "outcome": "Pending",
         "date": "2026-06-01", "window_end": "2026-06-15"},
        {"source": "newton", "ticker": "FN", "tier": "B", "outcome": "Pending",
         "date": "2026-06-04", "window_end": "2026-06-18"},
    ])
    _write(src / "inbox_call_dates.json", ["2026-06-04"])
    _write(src / "log_call_dates.json", ["2026-06-04"])

    feed = build_full_feed_from_files(
        src_dir=src,
        as_of="2026-06-05",
        run_timestamp="2026-06-05T14:00:00+00:00",
    )

    assert validate_cockpit_feed(feed) == []
    sc = feed["feedback"]["source_calls"]
    assert sc["calibration"]["status"] == "checked_fresh"
    assert sc["persistence"]["loud_count"] == 1
    assert sc["persistence"]["clusters"][0]["ticker"] == "FN"


def test_full_build_runner_missing_optional_files_are_dark_not_clear(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _required_files(src)

    feed = build_full_feed_from_files(
        src_dir=src,
        as_of="2026-06-05",
        run_timestamp="2026-06-05T14:00:00+00:00",
    )

    rows = _lane_rows(feed)
    assert rows["uw_opportunity"]["status"] == "not_checked"
    assert rows["top_prospects"]["status"] == "not_checked"
    assert rows["catalysts"]["status"] == "not_checked"
    assert rows["synthesis"]["status"] == "not_checked"


def test_full_build_runner_adds_portfolio_views_when_account_positions_exist(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _required_files(src)
    _account_positions_file(src)

    feed = build_full_feed_from_files(
        src_dir=src,
        as_of="2026-06-05",
        run_timestamp="2026-06-05T14:00:00+00:00",
    )

    assert validate_cockpit_feed(feed) == []
    assert feed["portfolio_views"]["views"]["combined"]["total_value"] == 100000
    assert {r["ticker"] for r in feed["portfolio_views"]["views"]["skb"]["rows"]} == {"NVDA"}
    assert {r["ticker"] for r in feed["portfolio_views"]["views"]["parents"]["rows"]} == {"SMH"}
