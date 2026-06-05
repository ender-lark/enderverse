import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import signal_log_intake as intake
from full_build_runner import build_full_feed_from_files


def _required_full_build_files(src):
    (src / "positions.json").write_text(json.dumps({
        "snapshot_date": "2026-06-04",
        "sleeve_value": 100000,
        "positions": [{"ticker": "NVDA", "shares": 10, "market_value": 12000}],
    }), encoding="utf-8")
    (src / "theses.json").write_text(json.dumps([
        {"ticker": "NVDA", "tier": "T2", "stance": "ACTIVE", "factor_tags": ["ai_complex"]},
    ]), encoding="utf-8")


def test_normalize_signal_log_accepts_wrappers_and_aliases():
    rows = intake.normalize_signal_log([{
        "morning_scan": [
            {"symbol": "nvda", "note": "Watch AI leader bid", "urgency": "High", "timestamp": "2026-06-05T12:00:00Z"},
            "Market breadth improving",
        ]
    }])

    assert rows[0]["ticker"] == "NVDA"
    assert rows[0]["signal"] == "Watch AI leader bid"
    assert rows[0]["priority"] == "high"
    assert rows[0]["date"] == "2026-06-05"
    assert rows[1]["signal"] == "Market breadth improving"


def test_validate_signal_log_rejects_empty_or_missing_text():
    assert intake.validate_signal_log([]) == ["signal log must include at least one row"]
    problems = intake.validate_signal_log([{"ticker": "NVDA"}])
    assert problems == ["rows[0] must include non-empty signal/title/what/summary"]


def test_cli_writes_valid_signal_log_and_summary(tmp_path):
    input_path = tmp_path / "signals.json"
    out = tmp_path / "signal_log.json"
    summary = tmp_path / "summary.json"
    input_path.write_text(json.dumps({
        "signals": [{"ticker": "NVDA", "summary": "Morning scan watch", "priority": "watch"}]
    }), encoding="utf-8")
    script = os.path.join(os.path.dirname(__file__), "signal_log_intake.py")

    proc = subprocess.run(
        [sys.executable, script, str(input_path), "--out", str(out), "--summary", str(summary)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["valid"] is True
    assert payload["written"] is True
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written[0]["signal"] == "Morning scan watch"


def test_cli_rejects_empty_signal_log_without_writing_cache(tmp_path):
    input_path = tmp_path / "signals.json"
    out = tmp_path / "signal_log.json"
    summary = tmp_path / "summary.json"
    input_path.write_text(json.dumps({"signals": [{"ticker": "NVDA"}]}), encoding="utf-8")
    script = os.path.join(os.path.dirname(__file__), "signal_log_intake.py")

    proc = subprocess.run(
        [sys.executable, script, str(input_path), "--out", str(out), "--summary", str(summary)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 2
    assert not out.exists()
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["written"] is False


def test_validate_missing_cache_returns_json_failure(tmp_path):
    missing = tmp_path / "missing.json"
    script = os.path.join(os.path.dirname(__file__), "signal_log_intake.py")

    proc = subprocess.run(
        [sys.executable, script, "--validate", str(missing)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 2
    payload = json.loads(proc.stdout)
    assert payload["problems"] == ["cache file not found"]


def test_valid_signal_log_cache_feeds_full_build_lane(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _required_full_build_files(src)
    (src / "signal_log.json").write_text(json.dumps([
        {"ticker": "NVDA", "signal": "Morning scan watch", "priority": "watch"}
    ]), encoding="utf-8")

    feed = build_full_feed_from_files(
        src_dir=src,
        as_of="2026-06-05",
        run_timestamp="2026-06-05T14:00:00+00:00",
    )

    rows = {row["key"]: row for row in feed["lane_status"]["rows"]}
    assert rows["signal_log"]["status"] == "has_data"
    assert feed["signal_log"][0]["signal"] == "Morning scan watch"
