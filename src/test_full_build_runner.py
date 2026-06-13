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
    _write(src / "social_watch.json", {
        "generated_at": "2026-06-05T13:30:00Z",
        "items": [
            {
                "ticker": "NVDA",
                "subreddit": "stocks",
                "title_snippet": "NVDA channel-check rumor",
                "mentions": 20,
                "velocity_z": 2.5,
                "independent_confirmation": ["UW flow pending"],
            }
        ],
    })
    _write(src / "event_risks.json", [
        {
            "date": "2026-06-05",
            "title": "Oil shock risk from geopolitical escalation",
            "severity": "high",
            "horizon": "daily",
            "channels": ["oil", "rates"],
            "source": "Daily event scan",
            "summary": "Crude spike can change new-buy timing and hedge posture.",
        }
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
    assert rows["social_watch"]["status"] == "has_data"
    assert rows["event_risk"]["status"] == "has_data"
    assert rows["research"]["status"] == "not_checked"
    assert rows["target_drift"]["status"] == "has_data"
    assert feed["signal_log"][0]["signal"] == "Morning scan flag"
    assert feed["social_watch"]["rows"][0]["ticker"] == "NVDA"
    assert feed["social_watch"]["honesty_rule"].startswith("Watch-only")
    assert feed["event_risk"][0]["title"] == "Oil shock risk from geopolitical escalation"
    assert feed["bullish_flow"]["rows"]
    assert feed["prospects"]["counts"]["act_now"] == 1
    assert feed["target_drift"]["actionable_count"] > 0
    assert feed["target_drift"]["rows"]
    assert any(a.get("source") == "daily_synthesis" for a in feed["actions"])
    assert any(a.get("kind") == "event_risk" for a in feed["actions"])
    assert all(a["disconfirmation"]["question"] == "What would make this wrong?" for a in feed["actions"])
    assert all(a.get("capital_efficiency", {}).get("summary") for a in feed["actions"])


def test_full_build_runner_uses_eastern_as_of_for_utc_midnight_run(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _required_files(src)
    _write(src / "macro_state.json", {
        "rates": {"10Y": {"value": 4.2, "value_5d_ago": 4.1}},
        "levels": {"DXY": {"value": 99.0, "value_5d_ago": 98.5}},
    })

    feed = build_full_feed_from_files(
        src_dir=src,
        run_timestamp="2026-06-06T00:03:00+00:00",
        generated_at="2026-06-06T00:03:00+00:00",
    )

    entries = {
        row["source"]: row
        for row in feed["staleness"]["entries"]
        if isinstance(row, dict)
    }
    assert entries["uw_price"]["date"].startswith("2026-06-05T20:03:00")
    assert entries["uw_price"]["age_days"] == 0
    assert entries["uw_macro"]["date"].startswith("2026-06-05T20:03:00")
    assert entries["uw_macro"]["age_days"] == 0


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
    assert rows["social_watch"]["status"] == "not_checked"
    assert rows["event_risk"]["status"] == "not_checked"
    assert rows["synthesis"]["status"] == "not_checked"
    assert rows["account_positions"]["status"] == "not_checked"
    assert rows["account_positions"]["detail"] == "missing live source input"
    assert "meridian" not in rows
    assert feed["lane_status"]["counts"]["not_checked"] >= 8


def test_missing_source_gap_rows_do_not_duplicate_existing_lanes(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _required_files(src)

    feed = build_full_feed_from_files(
        src_dir=src,
        as_of="2026-06-05",
        run_timestamp="2026-06-05T14:00:00+00:00",
    )

    keys = [row.get("key") for row in feed["lane_status"]["rows"]]
    assert keys.count("signal_log") == 1
    assert keys.count("catalysts") == 1
    assert keys.count("account_positions") == 1
    assert keys.count("meridian") == 0


def test_full_build_runner_snippet_only_fundstrat_daily_stays_not_checked(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _required_files(src)
    _write(src / "fundstrat_daily_calls.json", [])
    _write(src / "fundstrat_intake_summary.json", {
        "entries": 10,
        "full_body_entries": 0,
        "snippet_only_entries": 10,
        "daily_calls": 0,
    })

    feed = build_full_feed_from_files(
        src_dir=src,
        as_of="2026-06-05",
        run_timestamp="2026-06-05T14:00:00+00:00",
    )

    rows = _lane_rows(feed)
    assert rows["fundstrat_daily"]["status"] == "not_checked"


def test_full_build_runner_full_body_fundstrat_daily_can_be_checked_clear(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _required_files(src)
    _write(src / "fundstrat_daily_calls.json", [])
    _write(src / "fundstrat_intake_summary.json", {
        "entries": 2,
        "full_body_entries": 2,
        "snippet_only_entries": 0,
        "daily_calls": 0,
    })

    feed = build_full_feed_from_files(
        src_dir=src,
        as_of="2026-06-05",
        run_timestamp="2026-06-05T14:00:00+00:00",
    )

    rows = _lane_rows(feed)
    assert rows["fundstrat_daily"]["status"] == "checked_clear"


def test_full_build_runner_threads_fundstrat_news_and_if_i_were_you(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _required_files(src)
    _write(src / "fundstrat_bible.json", {
        "deck_date": "2026-05-28",
        "what_to_own": ["MAG7", "Financials"],
        "top5": ["AMD", "ANET"],
        "bottom5": ["DE"],
    })
    _write(src / "fundstrat_daily_calls.json", [
        {
            "author": "Newton",
            "ticker": "QQQ",
            "direction": "watch",
            "quote": "Support near 695-705 matters before adding beta.",
            "date": "2026-06-05",
            "subject": "Daily Technical Strategy",
        }
    ])
    _write(src / "fundstrat_intake_summary.json", {
        "entries": 1,
        "full_body_entries": 1,
        "snippet_only_entries": 0,
        "daily_calls": 1,
        "stored_daily_calls": 1,
    })
    _write(src / "fs_ingest_inventory.json", {
        "entries": [
            {
                "source_id": "fundstrat_core_stock_ideas:2026-05-28",
                "title": "May Core",
                "ingested_at": "2026-06-08T14:00:00Z",
                "sections": [
                    {"name": "top5", "status": "distilled"},
                    {"name": "smid top5", "status": "skipped"},
                ],
            }
        ]
    })
    _write(src / "top_prospects.json", {
        "AMD": {
            "ticker": "AMD",
            "add_date": "2026-05-28",
            "add_price": 120.5,
            "provenance": "FS Top 5 - 2026-05-28",
        },
        "ANET": {
            "ticker": "ANET",
            "add_date": "2026-05-28",
            "add_price": None,
            "provenance": "FS Top 5 - 2026-05-28",
        },
    })

    feed = build_full_feed_from_files(
        src_dir=src,
        as_of="2026-06-08",
        run_timestamp="2026-06-08T14:00:00+00:00",
    )

    assert validate_cockpit_feed(feed) == []
    assert feed["fundstrat_news"]["monthly"]["top_large_cap"][0]["ticker"] == "AMD"
    assert feed["fundstrat_news"]["monthly"]["top_large_cap"][1]["add_price_label"] == "not captured"
    assert any(gap["key"] == "missing_smid_top5" for gap in feed["fundstrat_news"]["gaps"])
    assert feed["fs_ingest_guard"]["status"] == "warn"
    assert any(gap["key"] == "fs_ingest_partial" for gap in feed["fundstrat_news"]["gaps"])
    assert feed["if_i_were_you"]["status"] == "review_only"
    assert feed["if_i_were_you"]["rows"]


def test_full_build_runner_fundstrat_audit_reports_stored_cache_counts(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _required_files(src)
    _write(src / "fundstrat_intake_summary.json", {
        "entries": 1,
        "full_body_entries": 1,
        "snippet_only_entries": 0,
        "daily_calls": 1,
        "stored_daily_calls": 2,
    })
    _write(src / "fundstrat_inbox_entries.json", [
        {"subject": "Daily", "body_fetched": True},
        {"subject": "Snippet", "body_fetched": False},
    ])
    _write(src / "fundstrat_daily_calls.json", [
        {"author": "Newton", "ticker": "QQQ", "direction": "watch", "quote": "Support near 700.", "date": "2026-06-05"},
        {"author": "Newton", "ticker": "RSP", "direction": "watch", "quote": "Rotation context.", "date": "2026-06-05"},
    ])

    feed = build_full_feed_from_files(
        src_dir=src,
        as_of="2026-06-08",
        run_timestamp="2026-06-08T14:00:00+00:00",
    )

    audit = feed["source_audits"]["fundstrat"]
    assert audit["stored_cache_entries"] == 2
    assert audit["stored_full_body_entries"] == 1
    assert audit["stored_snippet_only_entries"] == 1
    assert audit["stored_daily_call_rows"] == 2
    assert "stored cache: 2 inbox entries" in audit["line"]


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


def test_full_build_runner_adds_decision_support_and_audit_blocks(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _required_files(src)

    feed = build_full_feed_from_files(
        src_dir=src,
        as_of="2026-06-05",
        run_timestamp="2026-06-05T14:00:00+00:00",
    )

    assert "action_decision_groups" in feed
    assert "key_now" in feed["action_decision_groups"]["counts"]
    assert "asymmetric_opportunities" in feed
    assert feed["asymmetric_opportunities"]["dedupe_rule"]
    assert "source_audits" in feed
    assert "fundstrat" in feed["source_audits"]
    assert "cloud_routines" in feed["source_audits"]
    assert "uw_routing" in feed["source_audits"]
    assert "UW routing:" in feed["source_audits"]["uw_routing"]["line"]
    assert "uw_action_runbook" in feed
    assert "uw_action_runbook" in feed["source_audits"]
    assert "UW action runbook:" in feed["source_audits"]["uw_action_runbook"]["line"]
    assert "uw_endpoint_proof" in feed
    assert feed["uw_endpoint_proof"]["status"] == "not_checked"
    assert "uw_endpoint_proof" in feed["source_audits"]
    assert "runbook remains instructions only" in feed["source_audits"]["uw_endpoint_proof"]["line"]
    assert "endpoint_proof" in feed["uw_action_runbook"]
    assert "reallocation_brief" in feed
    assert "Reallocation brief:" in feed["reallocation_brief"]["line"]
    assert feed["reallocation_brief"]["candidate_only"] is True
    assert "market_open_packet" in feed
    assert feed["market_open_packet"]["line"].startswith("Market-open packet:")
    assert feed["market_open_packet"]["rows"]
    assert "key_now" in feed["market_open_packet"]["counts"]
    assert "alert_policy" in feed
    assert feed["alert_policy"]["delivery"] == "review_only_no_send"
    assert "fundstrat_signal_confirmation" in {
        row["mode"] for row in feed["uw_routing"]["rows"]
    }


def test_full_build_runner_wires_captured_uw_endpoint_proof(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _required_files(src)
    _write(src / "uw_endpoint_results.json", {
        "results": [
            {
                "mode": "fundstrat_signal_confirmation",
                "endpoint": "TICKER_FLOW_RECENT",
                "ticker": "NVDA",
                "checked_at": "2026-06-05T13:45:00+00:00",
                "status": "confirmed",
                "summary": "Flow supports the Fundstrat confirmation check.",
            }
        ]
    })

    feed = build_full_feed_from_files(
        src_dir=src,
        as_of="2026-06-05",
        run_timestamp="2026-06-05T14:00:00+00:00",
    )

    assert feed["uw_endpoint_proof"]["status"] == "has_data"
    assert feed["uw_endpoint_proof"]["counts"]["confirmed"] == 1
    assert feed["uw_endpoint_proof"]["interpretation_counts"]["supports"] == 1
    assert "supports=1" in feed["source_audits"]["uw_endpoint_proof"]["line"]
    assert feed["uw_action_runbook"]["endpoint_proof"]["status"] == "has_data"
