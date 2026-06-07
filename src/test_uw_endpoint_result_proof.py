import json
from pathlib import Path

from uw_endpoint_result_proof import (
    build_uw_endpoint_result_proof,
    load_uw_endpoint_results,
)


RUNBOOK = {
    "rows": [
        {
            "mode": "pre_market_crash_triage",
            "label": "Pre-market crash triage",
            "market_checks": ["MARKET_TIDE"],
            "ticker_checks": ["TICKER_FLOW_RECENT"],
        },
    ]
}


def test_uw_endpoint_proof_missing_results_stays_not_checked():
    block = build_uw_endpoint_result_proof(
        None,
        RUNBOOK,
        generated_at="2026-06-07T14:00:00+00:00",
    )

    assert block["status"] == "not_checked"
    assert "no captured endpoint result proof" in block["line"]
    assert "instructions only" in block["line"]
    assert block["count"] == 0
    assert "captured UW endpoint results are missing" in block["blockers"]


def test_uw_endpoint_proof_summarizes_captured_results_and_blockers():
    block = build_uw_endpoint_result_proof(
        {
            "results": [
                {
                    "mode": "pre_market_crash_triage",
                    "endpoint": "MARKET_TIDE",
                    "checked_at": "2026-06-07T13:30:00+00:00",
                    "status": "confirmed",
                    "summary": "Broad tape confirms risk-off pressure.",
                },
                {
                    "mode": "pre_market_crash_triage",
                    "endpoint": "TICKER_FLOW_RECENT",
                    "ticker": "NVDA",
                    "checked_at": "2026-06-06T20:00:00+00:00",
                    "status": "contradicted",
                    "summary": "Old flow contradicts a fresh sell-pressure read.",
                },
                {
                    "mode": "pre_market_crash_triage",
                    "endpoint": "DARKPOOL_TICKER",
                    "ticker": "SMH",
                    "checked_at": "2026-06-07T13:35:00+00:00",
                    "status": "missing",
                    "summary": "No captured darkpool response.",
                },
            ]
        },
        RUNBOOK,
        generated_at="2026-06-07T14:00:00+00:00",
    )

    assert block["status"] == "has_data"
    assert block["count"] == 3
    assert block["counts"]["confirmed"] == 1
    assert block["counts"]["contradicted"] == 1
    assert block["counts"]["missing"] == 1
    assert block["rows"][0]["decision_interpretation"] == "supports"
    assert block["rows"][1]["decision_interpretation"] == "contradicts"
    assert block["rows"][2]["decision_interpretation"] == "missing"
    assert block["interpretation_counts"]["supports"] == 1
    assert block["interpretation_counts"]["contradicts"] == 1
    assert block["stale_count"] == 1
    assert "supports=1" in block["line"]
    assert "missing=1" in block["line"]
    assert "contradicted endpoint evidence" in block["blockers"][0]
    assert any("not same-session" in blocker for blocker in block["blockers"])


def test_uw_endpoint_proof_neutral_fetch_is_inconclusive_and_blocks_promotion():
    block = build_uw_endpoint_result_proof(
        {
            "results": [
                {
                    "mode": "pre_market_crash_triage",
                    "endpoint": "MARKET_TIDE",
                    "checked_at": "2026-06-07T13:30:00+00:00",
                    "status": "neutral",
                    "summary": "Fetched rows, but result needs operator interpretation.",
                },
            ]
        },
        RUNBOOK,
        generated_at="2026-06-07T14:00:00+00:00",
    )

    assert block["status"] == "has_data"
    assert block["rows"][0]["decision_interpretation"] == "inconclusive"
    assert block["interpretation_counts"]["inconclusive"] == 1
    assert "inconclusive=1" in block["line"]
    assert any("inconclusive endpoint result" in blocker for blocker in block["blockers"])
    assert "neutral fetch success is inconclusive" in block["honesty_rule"]


def test_uw_endpoint_proof_invalid_rows_fail_closed():
    block = build_uw_endpoint_result_proof(
        {"results": [{"mode": "pre_market_crash_triage", "endpoint": "MARKET_TIDE", "status": "done"}]},
        RUNBOOK,
        generated_at="2026-06-07T14:00:00+00:00",
    )

    assert block["status"] == "failed"
    assert block["count"] == 0
    assert "no valid captured endpoint results" in block["line"]
    assert any("status must be one of" in problem for problem in block["problems"])


def test_load_uw_endpoint_results_uses_convention_names(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    payload = {"results": []}
    (src / "uw_endpoint_result_proof.json").write_text(json.dumps(payload), encoding="utf-8")

    loaded, path, problems = load_uw_endpoint_results(src)

    assert loaded == payload
    assert Path(path).name == "uw_endpoint_result_proof.json"
    assert problems == []


def test_load_uw_endpoint_results_missing_explicit_file_is_not_checked(tmp_path):
    loaded, path, problems = load_uw_endpoint_results(
        tmp_path,
        override=tmp_path / "uw_endpoint_results.json",
    )

    assert loaded is None
    assert Path(path).name == "uw_endpoint_results.json"
    assert problems == []
