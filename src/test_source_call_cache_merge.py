import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from source_call_cache_merge import main, merge_source_calls


def test_merge_source_calls_adds_candidates_and_dedupes():
    existing = [{
        "source": "newton",
        "ticker": "NVDA",
        "tier": "A",
        "date": "2026-06-01",
        "window_end": "2026-06-15",
        "verbatim_quote": "Buy NVDA.",
    }]
    candidates = [
        {
            "source": "Newton",
            "ticker": "nvda",
            "tier": "A",
            "date": "2026-06-01",
            "window_end": "2026-06-15",
            "verbatim_quote": "Buy NVDA.",
        },
        {
            "source": "Lee",
            "ticker": "GOOGL",
            "tier": "B",
            "date": "2026-06-02",
            "window_end": "2026-07-02",
            "verbatim_quote": "Favor GOOGL.",
            "evidence_detail": {
                "source_surface": "video_transcript",
                "key_levels": "Hold support before action.",
            },
        },
    ]

    rows, summary = merge_source_calls(existing, candidates,
                                       generated_at="2026-06-05T14:00:00+00:00")

    assert summary["existing"] == 1
    assert summary["candidates"] == 2
    assert summary["added"] == 1
    assert summary["stored"] == 2
    assert summary["log_call_dates"] == ["2026-06-01", "2026-06-02"]
    assert rows[1]["source"] == "lee"
    assert rows[1]["ticker"] == "GOOGL"
    assert rows[1]["outcome"] == "Pending"
    assert rows[1]["repo_cache_only"] is True
    assert rows[1]["evidence_detail"]["key_levels"] == "Hold support before action."
    assert rows[1]["id"].startswith("repo_")


def test_cli_writes_source_calls_log_dates_and_summary(tmp_path):
    candidates = tmp_path / "source_call_candidates.json"
    source_calls = tmp_path / "source_calls.json"
    log_dates = tmp_path / "log_call_dates.json"
    summary = tmp_path / "source_call_cache_summary.json"
    candidates.write_text(json.dumps([{
        "source": "Newton",
        "ticker": "NVDA",
        "tier": "A",
        "date": "2026-06-05",
        "window_end": "2026-06-19",
        "verbatim_quote": "Buy NVDA.",
    }]), encoding="utf-8")

    assert main([
        "--candidates", str(candidates),
        "--source-calls", str(source_calls),
        "--log-dates", str(log_dates),
        "--summary", str(summary),
        "--generated-at", "2026-06-05T14:00:00+00:00",
    ]) == 0

    rows = json.loads(source_calls.read_text(encoding="utf-8"))
    dates = json.loads(log_dates.read_text(encoding="utf-8"))
    info = json.loads(summary.read_text(encoding="utf-8"))
    assert rows[0]["ticker"] == "NVDA"
    assert dates == ["2026-06-05"]
    assert info["added"] == 1
