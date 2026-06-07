import os
import subprocess
import sys

from codex_uw.endpoints import UWEndpoints
from uw_endpoint_result_capture import capture_endpoint_results, plan_endpoint_checks


RUNBOOK = {
    "line": "UW action runbook: 1 check set.",
    "rows": [
        {
            "mode": "pre_market_crash_triage",
            "label": "Pre-market crash triage",
            "priority": 1,
            "ticker_scope": ["NVDA", "SMH"],
            "market_checks": ["MARKET_TIDE", "SECTOR_TIDE"],
            "ticker_checks": ["TICKER_FLOW_RECENT", "TICKER_OHLC"],
        }
    ],
}


class FakeClient:
    def __init__(self, empty=None, fail=None):
        self.empty = set(empty or [])
        self.fail = set(fail or [])
        self.calls = []

    def get_json(self, path_template, *, path_params=None, params=None):
        self.calls.append((path_template, path_params or {}, params or {}))
        if path_template in self.fail:
            raise RuntimeError("simulated endpoint failure")
        if path_template in self.empty:
            return {"data": []}
        return {"data": [{"ok": True}]}


def test_plan_endpoint_checks_uses_approved_catalog_and_marks_unsupported_params():
    checks, missing = plan_endpoint_checks(
        RUNBOOK,
        max_modes=1,
        max_tickers_per_mode=2,
        max_checks=5,
    )

    assert [check.endpoint for check in checks] == [
        "MARKET_TIDE",
        "TICKER_FLOW_RECENT",
        "TICKER_FLOW_RECENT",
        "TICKER_OHLC",
        "TICKER_OHLC",
    ]
    assert checks[1].ticker == "NVDA"
    assert checks[3].path_params["candle_size"] == "1d"
    assert checks[3].params["timeframe"] == "1M"
    assert missing[0]["endpoint"] == "SECTOR_TIDE"
    assert "unsupported path parameter" in missing[0]["summary"]


def test_plan_endpoint_checks_adds_market_correlation_tickers():
    runbook = {
        "rows": [
            {
                "mode": "pre_market_crash_triage",
                "priority": 1,
                "ticker_scope": ["XOP", "XLE", "TNX"],
                "market_checks": ["MARKET_CORRELATIONS"],
            }
        ]
    }

    checks, missing = plan_endpoint_checks(runbook)

    assert missing == []
    assert checks[0].endpoint == "MARKET_CORRELATIONS"
    assert checks[0].params == {"tickers": "XOP,XLE,TNX"}


def test_capture_endpoint_results_records_neutral_missing_and_failed_rows():
    client = FakeClient(
        empty={UWEndpoints.TICKER_OHLC},
        fail={UWEndpoints.TICKER_FLOW_RECENT},
    )

    payload = capture_endpoint_results(
        RUNBOOK,
        client,
        max_modes=1,
        max_tickers_per_mode=1,
        max_checks=3,
        checked_at="2026-06-07T18:30:00+00:00",
    )

    rows = payload["rows"]
    by_endpoint = {}
    for row in rows:
        by_endpoint.setdefault(row["endpoint"], []).append(row)
    assert payload["counts"]["neutral"] == 1
    assert payload["counts"]["missing"] == 2
    assert payload["counts"]["failed"] == 1
    assert by_endpoint["MARKET_TIDE"][0]["status"] == "neutral"
    assert by_endpoint["TICKER_FLOW_RECENT"][0]["status"] == "failed"
    assert "{" not in by_endpoint["TICKER_FLOW_RECENT"][0]["summary"]
    assert "}" not in by_endpoint["TICKER_FLOW_RECENT"][0]["summary"]
    assert by_endpoint["TICKER_OHLC"][0]["status"] == "missing"
    assert "Rows prove endpoint fetch status only" in payload["honesty_rule"]


def test_capture_cli_dry_run_does_not_require_uw_key(tmp_path):
    feed = tmp_path / "feed.json"
    feed.write_text(
        '{"uw_action_runbook":{"rows":[{"mode":"m","priority":1,"market_checks":["MARKET_TIDE"],"ticker_scope":[]}]}}',
        encoding="utf-8",
    )
    script = os.path.join(os.path.dirname(__file__), "uw_endpoint_result_capture.py")

    proc = subprocess.run(
        [sys.executable, script, "--feed", str(feed), "--dry-run", "--format", "text"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    assert "planned=1" in proc.stdout
