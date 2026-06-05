import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import daily_synthesis_intake as intake
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


def test_normalize_synthesis_accepts_wrapped_payload_and_aliases():
    payload = {
        "daily_synthesis": {
            "state_of_play": "AI remains the leadership sleeve.",
            "followups": ["NVDA review add timing."],
            "recommendations": [{"symbol": "NVDA", "next_step": "Review add timing", "urgency": "high"}],
        }
    }

    out = intake.normalize_synthesis(payload, default_date="2026-06-05")

    assert out["source"] == "Daily Synthesis"
    assert out["date"] == "2026-06-05"
    assert out["hanging"] == ["NVDA review add timing."]
    assert out["actions"][0]["symbol"] == "NVDA"


def test_validate_synthesis_rejects_empty_or_bad_actions():
    assert intake.validate_synthesis({}) == [
        "daily synthesis must include state_of_play, delta, hanging, or actions"
    ]
    problems = intake.validate_synthesis({"actions": [{"urgency": "high"}]})
    assert any("actions[0]" in problem for problem in problems)


def test_cli_writes_valid_synthesis_and_summary(tmp_path):
    input_path = tmp_path / "synthesis.json"
    out = tmp_path / "daily_synthesis.json"
    summary = tmp_path / "summary.json"
    input_path.write_text(json.dumps({
        "source": "Daily Synthesis",
        "date": "2026-06-05",
        "state_of_play": "Quiet tape, but NVDA needs sizing review.",
        "actions": [{"ticker": "NVDA", "what": "Review sizing", "urgency": "high"}],
    }), encoding="utf-8")
    script = os.path.join(os.path.dirname(__file__), "daily_synthesis_intake.py")

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
    assert written["actions"][0]["ticker"] == "NVDA"


def test_cli_rejects_empty_synthesis_without_writing_cache(tmp_path):
    input_path = tmp_path / "empty.json"
    out = tmp_path / "daily_synthesis.json"
    summary = tmp_path / "summary.json"
    input_path.write_text(json.dumps({"source": "Daily Synthesis"}), encoding="utf-8")
    script = os.path.join(os.path.dirname(__file__), "daily_synthesis_intake.py")

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


def test_merge_existing_preserves_prior_hanging_items(tmp_path):
    existing = {"state_of_play": "Prior", "hanging": ["NVDA review sizing."]}
    incoming = {"delta": "New day", "hanging": ["NVDA review sizing.", "MSFT watch catalyst."]}

    merged = intake.merge_synthesis(existing, intake.normalize_synthesis(incoming))

    assert merged["state_of_play"] == "Prior"
    assert merged["delta"] == "New day"
    assert merged["hanging"] == ["NVDA review sizing.", "MSFT watch catalyst."]


def test_valid_synthesis_cache_feeds_full_build_actions(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _required_full_build_files(src)
    (src / "daily_synthesis.json").write_text(json.dumps({
        "source": "Daily Synthesis",
        "date": "2026-06-05",
        "actions": [{"ticker": "NVDA", "what": "Review add timing", "urgency": "high"}],
    }), encoding="utf-8")

    feed = build_full_feed_from_files(
        src_dir=src,
        as_of="2026-06-05",
        run_timestamp="2026-06-05T14:00:00+00:00",
    )

    rows = {row["key"]: row for row in feed["lane_status"]["rows"]}
    assert rows["synthesis"]["status"] == "has_data"
    assert any(row.get("source") == "daily_synthesis" for row in feed["actions"])
