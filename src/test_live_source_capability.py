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

    report = live_source_capability.capability_report(src)

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


def test_capability_report_tracks_present_inputs_without_marking_missing_clear(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "positions.json").write_text("{}", encoding="utf-8")
    (src / "theses.json").write_text("[]", encoding="utf-8")

    report = live_source_capability.capability_report(src)
    by_key = {row["key"]: row for row in report["rows"]}

    assert by_key["positions"]["present"] is True
    assert by_key["theses"]["present"] is True
    assert "catalysts" in report["missing_live_capable_keys"]
    assert report["missing_live_capable_count"] > 0


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
