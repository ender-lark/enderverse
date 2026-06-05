from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import live_source_capability


def test_capability_report_classifies_connector_and_supplied_lanes(tmp_path):
    src = tmp_path / "src"
    src.mkdir()

    report = live_source_capability.capability_report(src, environ={})

    assert report["valid"] is True
    assert report["total_inputs"] >= 20
    assert "fs_daily" in report["connector_or_api_keys"]
    assert "uw_opportunity" in report["connector_or_api_keys"]
    assert "catalysts" in report["connector_or_api_keys"]
    assert "signal_log" in report["connector_or_api_keys"]
    assert "positions" in report["supplied_or_export_keys"]
    assert "event_risk" in report["supplied_or_export_keys"]
    assert "theses" not in report["connector_or_api_keys"]
    assert "theses" not in report["supplied_or_export_keys"]
    assert "theses" in report["missing_input_keys"]
    assert report["live_source_config"]["configured"] is False
    assert report["live_source_config"]["missing_keys"] == ["uw_api_key"]


def test_capability_report_tracks_present_inputs_without_marking_missing_clear(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "positions.json").write_text("{}", encoding="utf-8")
    (src / "theses.json").write_text("[]", encoding="utf-8")

    report = live_source_capability.capability_report(src, environ={})
    by_key = {row["key"]: row for row in report["rows"]}

    assert by_key["positions"]["present"] is True
    assert by_key["theses"]["present"] is True
    assert by_key["account_positions"]["candidate_paths"]
    assert by_key["account_positions"]["missing_behavior"]
    assert "catalysts" in report["missing_live_capable_keys"]
    assert report["missing_live_capable_count"] > 0


def test_live_source_config_passes_when_uw_key_is_present(tmp_path):
    src = tmp_path / "src"
    src.mkdir()

    report = live_source_capability.capability_report(src, environ={"UW_API_KEY": "secret"})

    assert report["live_source_config"]["configured"] is True
    assert report["live_source_config"]["configured_count"] == 1
    assert report["live_source_config"]["missing_count"] == 0
    assert live_source_capability.format_missing_live_config(report) == []


def test_live_source_config_accepts_fresh_connector_proof(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "live_source_config.json").write_text(
        json.dumps({
            "verified_at": "2026-06-05T15:00:00-04:00",
            "connectors": {
                "unusual_whales": {
                    "available": True,
                    "verified_by": "Codex app Unusual Whales connector",
                }
            },
        }),
        encoding="utf-8",
    )

    report = live_source_capability.live_config_report(
        environ={},
        config_path=src / "live_source_config.json",
        now="2026-06-05T16:00:00-04:00",
    )

    assert report["configured"] is True
    assert report["configured_count"] == 1
    assert report["missing_count"] == 0
    assert report["stale_count"] == 0
    assert report["rows"][0]["connector_configured"] is True
    assert report["rows"][0]["connector_proof_fresh"] is True


def test_live_source_config_rejects_stale_connector_proof_without_api_key(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "live_source_config.json").write_text(
        json.dumps({
            "verified_at": "2026-06-03T09:00:00-04:00",
            "connectors": {
                "unusual_whales": {
                    "available": True,
                    "verified_by": "Codex app Unusual Whales connector",
                }
            },
        }),
        encoding="utf-8",
    )

    report = live_source_capability.live_config_report(
        environ={},
        config_path=src / "live_source_config.json",
        now="2026-06-05T16:00:00-04:00",
    )
    lines = live_source_capability.format_missing_live_config({"live_source_config": report})

    assert report["configured"] is False
    assert report["missing_count"] == 1
    assert report["stale_count"] == 1
    assert report["rows"][0]["connector_available"] is True
    assert report["rows"][0]["connector_proof_fresh"] is False
    assert "connector proof is stale" in "\n".join(lines)


def test_live_source_config_api_key_overrides_stale_connector_proof(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "live_source_config.json").write_text(
        json.dumps({
            "verified_at": "2026-06-03T09:00:00-04:00",
            "connectors": {
                "unusual_whales": {
                    "available": True,
                    "verified_by": "Codex app Unusual Whales connector",
                }
            },
        }),
        encoding="utf-8",
    )

    report = live_source_capability.live_config_report(
        environ={"UW_API_KEY": "secret"},
        config_path=src / "live_source_config.json",
        now="2026-06-05T16:00:00-04:00",
    )

    assert report["configured"] is True
    assert report["configured_count"] == 1
    assert report["missing_count"] == 0
    assert report["stale_count"] == 0
    assert report["rows"][0]["env_configured"] is True


def test_live_source_capability_cli_text(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    script = os.path.join(os.path.dirname(__file__), "live_source_capability.py")

    proc = subprocess.run(
        [sys.executable, script, "--src-dir", str(src), "--format", "text"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    assert "Live source capability valid: True" in proc.stdout
    assert "connector_or_api=" in proc.stdout
    assert "Live source config:" in proc.stdout
    assert "missing behavior:" in proc.stdout
    assert "expected path:" in proc.stdout


def test_live_source_capability_cli_json(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    script = os.path.join(os.path.dirname(__file__), "live_source_capability.py")

    proc = subprocess.run(
        [sys.executable, script, "--src-dir", str(src)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    assert json.loads(proc.stdout)["valid"] is True
