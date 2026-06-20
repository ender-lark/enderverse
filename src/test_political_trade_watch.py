import json
import os
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from political_trade_watch import (
    build_political_trade_watch,
    build_political_trade_watch_block,
    fetch_live_trades,
    format_text,
    normalize_trade_row,
)
from codex_uw.endpoints import UWEndpoints
from validators import validate_cockpit_feed


SAMPLE_TRUMP_ROW = {
    "name": "Donald J Trump",
    "reporter": "Donald J Trump",
    "name_slug": "donald-trump",
    "ticker": "KFY",
    "symbol": "KFY",
    "notes": "KORN FERRY",
    "asset": "stock",
    "txn_type": "Buy",
    "transaction_date": "2026-01-26",
    "filed_at_date": "2026-05-14",
    "created_at": "2026-05-14T09:12:25.000000Z",
    "amounts": "$15,001 - $50,000",
    "low_value": "15001",
    "high_value": "50000",
    "mid_value": "32500.5",
    "member_type": "executive",
    "current_agency": "White House Office",
    "current_party": "republican",
    "file_record_id": "09b1c95e-a0df-4d6a-864b-a0f037506509",
    "link_url": "https://extapps2.oge.gov/example/trump.pdf",
}


def test_normalize_trump_trade_row_keeps_disclosure_watch_only():
    row = normalize_trade_row(
        SAMPLE_TRUMP_ROW,
        generated_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
    )

    assert row["ticker"] == "KFY"
    assert row["transaction_type"] == "Buy"
    assert row["lag_days"] == 108
    assert row["escalation"] == "Research Queue candidate"
    assert row["independent_confirmation"]
    assert "not a trade trigger" in row["blocker_before_action"]
    assert "OGE/source filing" in "; ".join(row["evidence"])


def test_build_political_trade_watch_filters_target_and_builds_candidates():
    payload = {
        "result": [
            SAMPLE_TRUMP_ROW,
            {**SAMPLE_TRUMP_ROW, "name": "Nancy Pelosi", "reporter": "Nancy Pelosi", "ticker": "NVDA"},
        ]
    }

    block = build_political_trade_watch(
        [payload],
        generated_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
    )

    assert block["status"] == "has_data"
    assert block["counts"]["rows"] == 1
    assert block["counts"]["research_queue_candidates"] == 1
    assert block["tickers"] == ["KFY"]
    assert block["rows"][0]["summary"].startswith("Donald J Trump Buy KFY")
    assert block["research_queue_candidates"][0]["source"] == "political_trade_watch"
    assert "watch-only" in block["honesty_rule"].lower()


def test_political_trade_watch_not_checked_preserves_fetch_failure():
    block = build_political_trade_watch(
        [],
        failures=[{"source": "uw", "error": "UW_API_KEY is not set"}],
        generated_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
    )

    assert block["status"] == "not_checked"
    assert block["rows"] == []
    assert "not checked" in block["line"].lower()
    assert "failures: 1" in format_text(block)


def test_existing_cache_block_round_trips_for_full_build():
    original = build_political_trade_watch(
        [{"result": [SAMPLE_TRUMP_ROW]}],
        generated_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
    )

    block = build_political_trade_watch_block(original)

    assert block["status"] == "has_data"
    assert block["rows"][0]["ticker"] == "KFY"
    assert block["command"].endswith("--format text")


def test_political_trade_watch_validator_blocks_direct_trade_escalation():
    problems = validate_cockpit_feed({
        "political_trade_watch": {
            "rows": [
                {
                    "ticker": "KFY",
                    "summary": "bad direct action",
                    "evidence": [],
                    "independent_confirmation": [],
                    "escalation": "BUY",
                }
            ]
        }
    })

    assert any("political_trade_watch" in problem and "direct trade" in problem for problem in problems)


def test_cli_accepts_input_and_writes_cache(tmp_path):
    input_path = tmp_path / "uw_trump.json"
    out_path = tmp_path / "political_trade_watch.json"
    input_path.write_text(json.dumps({"result": [SAMPLE_TRUMP_ROW]}), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            os.path.join(os.path.dirname(__file__), "political_trade_watch.py"),
            "--input",
            str(input_path),
            "--out",
            str(out_path),
            "--format",
            "text",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["status"] == "has_data"
    assert payload["rows"][0]["ticker"] == "KFY"
    assert "Trump trade watch:" in proc.stdout


def test_fetch_live_trades_uses_trader_endpoint_name_param():
    class FakeClient:
        def __init__(self):
            self.calls = []

        def get_json(self, path_template, *, path_params=None, params=None):
            self.calls.append((path_template, path_params or {}, params or {}))
            return {"data": [SAMPLE_TRUMP_ROW]}

    client = FakeClient()

    payload = fetch_live_trades(politician="Donald J Trump", limit=999, client=client)

    assert payload["data"][0]["name"] == "Donald J Trump"
    assert client.calls == [
        (
            UWEndpoints.CONGRESS_TRADER,
            {},
            {"name": "Donald J Trump", "limit": 200, "page": 0},
        )
    ]
