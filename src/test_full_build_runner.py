import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from full_build_runner import (
    active_parabolic_tickers,
    build_full_feed_from_files,
    convention_input_status,
    normalize_closes_cache,
    normalize_positions_cache,
)
import macro_pulse_scan as mp
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
    _write(src / "signal_log.json", [
        {"ticker": "NVDA", "signal": "Morning scan flag", "priority": "watch", "date": "2026-06-05"}
    ])

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
    assert rows["signal_log"]["status"] == "has_data"
    assert rows["research"]["status"] == "not_checked"
    assert rows["target_drift"]["status"] == "has_data"
    assert feed["signal_log"][0]["signal"] == "Morning scan flag"
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
    assert rows["signal_log"]["status"] == "not_checked"
    assert rows["synthesis"]["status"] == "not_checked"


def test_full_build_runner_missing_price_file_is_dark_not_false_has_data(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _required_files(src)
    (src / "uw_closes.json").unlink()

    feed = build_full_feed_from_files(
        src_dir=src,
        as_of="2026-06-05",
        run_timestamp="2026-06-05T14:00:00+00:00",
    )

    rows = _lane_rows(feed)
    assert rows["uw_price"]["status"] == "not_checked"
    assert feed["lane_status"]["has_dark_lanes"] is True


def test_full_build_runner_accepts_macro_pulse_state(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _required_files(src)
    curve = mp.YieldCurveSnapshot(
        date="2026-06-05",
        yields={"2y": 4.00, "10y": 4.50, "30y": 5.00},
    )
    cross = mp.CrossAssetSnapshot(
        tlt_price=83.0,
        ief_price=93.0,
        lqd_price=107.0,
        hyg_price=79.0,
        uup_price=27.0,
        vix_level=18.0,
        gld_price=417.0,
        uso_price=148.0,
        move_index=95.0,
    )
    _write(src / "macro_state.json", mp.build_macro_state(
        curve,
        cross,
        mp.assemble_regime(curve, cross),
        mp.check_alerts(curve, cross),
    ))

    feed = build_full_feed_from_files(
        src_dir=src,
        as_of="2026-06-05",
        run_timestamp="2026-06-05T14:00:00+00:00",
    )

    rows = _lane_rows(feed)
    assert rows["uw_macro"]["status"] == "has_data"
    assert "10Y 4.50%" in feed["macro"]["line"]
    assert "USD (UUP) 27" in feed["macro"]["line"]


def test_convention_input_status_uses_manifest_contract(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _required_files(src)
    (src / "uw_closes.json").unlink()

    rows = {row["key"]: row for row in convention_input_status(src)}

    assert rows["positions"]["status"] == "present"
    assert rows["theses"]["required"] is True
    assert rows["uw_prices"]["status"] == "missing_optional"
    assert "quiet tape" in rows["uw_prices"]["missing_behavior"]


def test_full_build_cli_reports_dark_lanes_and_missing_inputs(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _required_files(src)
    (src / "uw_closes.json").unlink()
    feed_out = tmp_path / "feed.json"
    script = os.path.join(os.path.dirname(__file__), "full_build_runner.py")

    proc = subprocess.run(
        [
            sys.executable,
            script,
            "--src-dir",
            str(src),
            "--feed-out",
            str(feed_out),
            "--as-of",
            "2026-06-05",
            "--run-timestamp",
            "2026-06-05T14:00:00+00:00",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert "uw_price" in payload["dark_lane_keys"]
    missing = {row["key"]: row for row in payload["missing_optional_inputs"]}
    assert missing["uw_prices"]["source"] == "uw_cache_refresh_or_supplied_price_cache"
    assert payload["missing_required_inputs"] == []


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
    overlap = {
        r["ticker"]: r
        for r in feed["portfolio_views"]["views"]["combined"]["effective_exposure"]["overlap_rows"]
    }
    assert overlap["NVDA"]["lookthrough_market_value"] == 1600
