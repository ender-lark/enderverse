from __future__ import annotations

from post_open_uw_evidence_run import (
    _summary_from_details,
    validate_redacted_endpoint_results,
)


def _safe_payload() -> dict:
    return {
        "generated_at": "2026-06-17T14:31:29+00:00",
        "source": "uw_endpoint_result_capture",
        "runbook_line": "Check post-open UW flow.",
        "planned_checks": 1,
        "rows": [
            {
                "mode": "post_open_flow_confirmation",
                "endpoint": "TICKER_FLOW_RECENT",
                "ticker": "NVDA",
                "status": "neutral",
                "checked_at": "2026-06-17T14:31:29+00:00",
                "summary": "Fetched TICKER_FLOW_RECENT for NVDA; row_count=25. Result requires operator interpretation before any promotion.",
                "source": "uw_endpoint_result_capture",
                "row_count": 25,
            },
        ],
        "counts": {"neutral": 1},
        "honesty_rule": "Rows prove endpoint fetch status only; neutral rows do not confirm a trade thesis.",
    }


def test_validate_redacted_endpoint_results_accepts_summary_only_payload():
    assert validate_redacted_endpoint_results(_safe_payload()) == []


def test_validate_redacted_endpoint_results_rejects_raw_or_sensitive_fields():
    payload = _safe_payload()
    payload["raw_response"] = {"data": [{"symbol": "NVDA"}]}
    payload["rows"][0]["body"] = "not allowed"

    problems = validate_redacted_endpoint_results(payload)

    assert any("unexpected top-level proof keys" in problem for problem in problems)
    assert any("unexpected keys" in problem for problem in problems)
    assert any("sensitive/raw-response marker" in problem for problem in problems)


def test_validate_redacted_endpoint_results_rejects_secret_markers_in_summary():
    payload = _safe_payload()
    payload["rows"][0]["summary"] = "authorization bearer value was returned"

    problems = validate_redacted_endpoint_results(payload)

    assert problems == ["proof payload contains sensitive/raw-response marker text"]


def test_summary_records_boundary_commit_without_claiming_support():
    summary = _summary_from_details({
        "boundary_artifact_committed": True,
        "proof_interpretation_counts": {
            "supports": 0,
            "contradicts": 0,
            "inconclusive": 10,
            "missing": 3,
        },
        "dashboard_refresh_status": "success",
    })

    assert "0 supports" in summary
    assert "10 inconclusive" in summary
    assert "boundary_artifact_committed=true" in summary
    assert "dashboard_refresh=success" in summary


def test_summary_can_record_no_fresh_boundary_data():
    summary = _summary_from_details({
        "boundary_artifact_committed": False,
        "no_fresh_boundary_data": True,
        "proof_interpretation_counts": {},
        "dashboard_refresh_status": "not_run",
    })

    assert "no_fresh_boundary_data=true" in summary
