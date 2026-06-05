from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import live_source_config_update as update


def test_build_live_source_config_stores_only_proof_metadata():
    config = update.build_live_source_config(
        [
            {
                "date": "2026-06-05",
                "call_volume": 52273851,
                "put_volume": 44439181,
            },
            {
                "data": [
                    {"timestamp": "2026-06-05T15:25:00-04:00", "net_call_premium": "-1"},
                    {"timestamp": "2026-06-05T15:30:00-04:00", "net_put_premium": "1"},
                ],
                "date": "2026-06-05",
            },
        ],
        verified_at="2026-06-05T15:31:00-04:00",
    )

    uw = config["connectors"]["unusual_whales"]
    assert config["verified_at"] == "2026-06-05T15:31:00-04:00"
    assert uw["available"] is True
    assert uw["market_state_date"] == "2026-06-05"
    assert uw["market_tide_latest_timestamp"] == "2026-06-05T15:30:00-04:00"
    assert "call_volume" not in uw
    assert "put_volume" not in uw
    assert "data" not in uw
    assert update.validate_config(config) == []


def test_build_live_source_config_accepts_wrapped_payloads():
    config = update.build_live_source_config(
        [{
            "market_state": {"date": "2026-06-05", "put_call_ratio": "0.85"},
            "market_tide": {"data": [{"timestamp": "2026-06-05T15:30:00-04:00"}]},
        }],
        verified_at="2026-06-05T15:31:00-04:00",
    )

    uw = config["connectors"]["unusual_whales"]
    assert uw["market_state_date"] == "2026-06-05"
    assert uw["market_tide_latest_timestamp"] == "2026-06-05T15:30:00-04:00"


def test_validate_config_rejects_raw_payload_fields():
    config = update.build_live_source_config(
        [{"date": "2026-06-05", "call_volume": 1}],
        verified_at="2026-06-05T15:31:00-04:00",
    )
    config["connectors"]["unusual_whales"]["call_volume"] = 1

    problems = update.validate_config(config)

    assert any("raw market payload fields" in problem for problem in problems)


def test_cli_writes_and_validates_config(tmp_path):
    input_path = tmp_path / "uw.json"
    out_path = tmp_path / "live_source_config.json"
    input_path.write_text(
        json.dumps({
            "market_state": {"date": "2026-06-05", "call_volume": 1},
            "market_tide": {"data": [{"timestamp": "2026-06-05T15:30:00-04:00"}]},
        }),
        encoding="utf-8",
    )
    script = os.path.join(os.path.dirname(__file__), "live_source_config_update.py")

    proc = subprocess.run(
        [
            sys.executable,
            script,
            str(input_path),
            "--out",
            str(out_path),
            "--verified-at",
            "2026-06-05T15:31:00-04:00",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    validate_proc = subprocess.run(
        [sys.executable, script, "--validate", str(out_path)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    assert validate_proc.returncode == 0
    assert json.loads(proc.stdout)["written"] is True
    assert json.loads(validate_proc.stdout)["valid"] is True
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["connectors"]["unusual_whales"]["market_tide_latest_timestamp"] == "2026-06-05T15:30:00-04:00"
