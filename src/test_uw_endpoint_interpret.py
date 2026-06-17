import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from uw_endpoint_interpret import (
    HONESTY_RULE,
    apply_operator_interpretations,
    complete_interpretation_from_capture,
    load_uw_endpoint_interpretations,
)


CAPTURE = {
    "results": [
        {
            "mode": "portfolio_reallocation",
            "endpoint": "TICKER_FLOW_RECENT",
            "ticker": "NVDA",
            "checked_at": "2026-06-17T14:31:29+00:00",
            "status": "neutral",
            "summary": "Fetched TICKER_FLOW_RECENT for NVDA; row_count=50.",
        }
    ]
}


def test_operator_interpretation_can_confirm_matching_neutral_capture():
    interpreted, summary = apply_operator_interpretations(
        CAPTURE,
        [
            {
                "mode": "portfolio_reallocation",
                "endpoint": "TICKER_FLOW_RECENT",
                "ticker": "NVDA",
                "checked_at": "2026-06-17T14:31:29+00:00",
                "status": "confirmed",
                "summary": "NVDA call flow supports the reallocation check.",
                "interpreted_at": "2026-06-17T14:35:00+00:00",
                "operator": "operator",
                "source": "operator_uw_interpretation",
            }
        ],
    )

    row = interpreted["results"][0]
    assert row["status"] == "confirmed"
    assert row["capture_status"] == "neutral"
    assert row["capture_summary"].startswith("Fetched TICKER_FLOW_RECENT")
    assert row["operator_interpretation"]["honesty_rule"] == HONESTY_RULE
    assert summary["applied"] == 1
    assert summary["counts"]["confirmed"] == 1
    assert summary["problems"] == []


def test_neutral_capture_without_matching_interpretation_stays_neutral():
    interpreted, summary = apply_operator_interpretations(CAPTURE, [])

    assert interpreted["results"][0]["status"] == "neutral"
    assert summary["applied"] == 0


def test_unmatched_operator_interpretation_reports_problem_and_does_not_promote():
    interpreted, summary = apply_operator_interpretations(
        CAPTURE,
        [
            {
                "mode": "portfolio_reallocation",
                "endpoint": "TICKER_FLOW_RECENT",
                "ticker": "NVDA",
                "checked_at": "2026-06-17T13:00:00+00:00",
                "status": "confirmed",
                "summary": "Wrong capture timestamp must not apply.",
                "interpreted_at": "2026-06-17T14:35:00+00:00",
                "source": "operator_uw_interpretation",
            }
        ],
    )

    assert interpreted["results"][0]["status"] == "neutral"
    assert summary["applied"] == 0
    assert summary["unmatched"] == 1
    assert "did not match a captured neutral" in summary["problems"][0]


def test_load_interpretations_rejects_supports_alias_and_requires_confirmed_or_contradicted(tmp_path):
    path = tmp_path / "uw_endpoint_interpretations.json"
    path.write_text(
        json.dumps(
            {
                "interpretations": [
                    {
                        "mode": "portfolio_reallocation",
                        "endpoint": "TICKER_FLOW_RECENT",
                        "ticker": "NVDA",
                        "checked_at": "2026-06-17T14:31:29+00:00",
                        "status": "supports",
                        "summary": "Alias should not pass.",
                        "interpreted_at": "2026-06-17T14:35:00+00:00",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    rows, loaded_path, problems = load_uw_endpoint_interpretations(tmp_path)

    assert rows == []
    assert loaded_path == path
    assert any("confirmed" in problem and "contradicted" in problem for problem in problems)


def test_cli_records_interpretation_tied_to_current_capture(tmp_path):
    results = tmp_path / "uw_endpoint_results.json"
    interpretations = tmp_path / "uw_endpoint_interpretations.json"
    results.write_text(json.dumps(CAPTURE), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            os.path.join(os.path.dirname(__file__), "uw_endpoint_interpret.py"),
            "--results",
            str(results),
            "--interpretations",
            str(interpretations),
            "--mode",
            "portfolio_reallocation",
            "--endpoint",
            "TICKER_FLOW_RECENT",
            "--ticker",
            "NVDA",
            "--status",
            "confirmed",
            "--summary",
            "NVDA flow supports the reallocation check.",
            "--interpreted-at",
            "2026-06-17T14:35:00+00:00",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(interpretations.read_text(encoding="utf-8"))
    row = payload["interpretations"][0]
    assert row["checked_at"] == "2026-06-17T14:31:29+00:00"
    assert row["status"] == "confirmed"


def test_complete_interpretation_rejects_missing_capture_match():
    completed, problems = complete_interpretation_from_capture(
        {
            "mode": "portfolio_reallocation",
            "endpoint": "MARKET_TIDE",
            "status": "confirmed",
            "summary": "No matching capture.",
            "interpreted_at": "2026-06-17T14:35:00+00:00",
        },
        CAPTURE,
    )

    assert completed is None
    assert "no captured neutral" in problems[0]
