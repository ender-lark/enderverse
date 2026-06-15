import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reallocation_brief import build_reallocation_brief


def _feed():
    return {
        "generated_at": "2026-06-07T14:00:00+00:00",
        "uw_action_runbook": {
            "rows": [
                {
                    "mode": "portfolio_reallocation",
                    "market_checks": ["ETF_TIDE", "SECTOR_TIDE"],
                    "ticker_checks": ["TICKER_OHLC", "TICKER_FLOW_RECENT"],
                    "downgrade_when": "live flow/price argues for waiting",
                }
            ]
        },
    }


def _positions(snapshot_date="2026-05-31"):
    total = 1_000_000.0
    weights = {
        "SMH": 9.0,
        "MAGS": 8.0,
        "IGV": 5.5,
        "GRNY": 9.0,
        "GRNJ": 7.0,
        "NVDA": 6.0,
        "MU": 3.0,
        "LEU": 4.0,
        "BMNR": 2.0,
    }
    return {
        "snapshot_date": snapshot_date,
        "sleeve_value": total,
        "positions": [
            {"ticker": ticker, "market_value": pct / 100.0 * total}
            for ticker, pct in weights.items()
        ],
    }


def test_reallocation_brief_labels_stale_positions_as_test_data():
    block = build_reallocation_brief(_feed(), _positions(), as_of="2026-06-07")

    assert block["status"] == "test_data_only"
    assert block["candidate_only"] is True
    assert "test data only" in block["line"]
    assert block["counts"]["adds"] > 0
    assert block["counts"]["trims"] > 0
    assert block["funding"]["allocated_usd"] > 0
    assert all(row["ticker"] != "GRNJ" for row in block["trims"])
    assert all(
        funding["ticker"] != "GRNJ"
        for row in block["rows"]
        for funding in row.get("funded_by") or []
    )
    assert any("GRNJ" in note and "protected" in note for note in block["notes"])
    assert any("positions snapshot 2026-05-31" in blocker for blocker in block["blockers"])
    assert "same-session UW price/flow" in block["rows"][0]["blockers"]
    assert "TICKER_FLOW_RECENT" in block["rows"][0]["uw_ticker_checks"]
    assert block["rows"][0]["capital_efficiency"]["summary"]
    assert "perfect bottom" in block["rows"][0]["capital_efficiency"]["timing_balance"]
    assert block["rows"][0]["options_review_prompt"]["status"] == "review_only"
    assert "Maximum loss" in block["rows"][0]["options_review_prompt"]["max_loss_gate"]
    assert block["rows"][0]["disconfirmation"] == "live flow/price argues for waiting"
    past_sequence_rows = [row for row in block["rows"] if row["sequence_state"] == "past_gate"]
    assert past_sequence_rows
    assert any(
        "legacy catalyst sequencing date has passed" in blocker
        for blocker in past_sequence_rows[0]["blockers"]
    )
    assert "no trades are executed" in block["honesty_rule"]
    assert block["options_gate"]["status"] == "review_only"
    assert "defined-risk review prompts" in block["options_gate"]["line"]
    assert block["capital_efficiency"]["summary"]
    assert any(row["ticker"] == "BMNR" and row["status"] == "undecided_recheck" for row in block["special_reviews"])


def test_reallocation_brief_same_day_positions_are_candidate_only_not_final():
    block = build_reallocation_brief(_feed(), _positions("2026-06-07"), as_of="2026-06-07")

    assert block["status"] == "candidate_only"
    assert block["candidate_only"] is True
    assert "Same-day positions" in block["honesty_rule"]
    assert "test-data" not in block["honesty_rule"]
    assert all("latest current positions" not in row["blockers"] for row in block["rows"])
    assert any("tax/account constraints" in blocker for blocker in block["blockers"])
    assert not any("max-action capacity not supplied" in blocker for blocker in block["blockers"])
