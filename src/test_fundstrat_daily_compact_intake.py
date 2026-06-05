import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from full_build_runner import build_full_feed_from_files
from fundstrat_daily_compact_intake import (
    MAX_QUOTE_CHARS,
    normalize_compact_calls,
    validate_compact_calls,
    write_compact_outputs,
)
from test_full_build_runner import _required_files


def test_normalize_compact_calls_accepts_short_full_body_derived_rows():
    calls = normalize_compact_calls({
        "calls": [{
            "author": "Newton",
            "ticker": "XOP",
            "direction": "avoid",
            "quote": "Bounce only; resistance near 175.72 should repel price toward 162.",
            "date": "2026-06-03",
            "source_message_id": "m1",
            "source": "Fundstrat full-body read",
        }]
    })

    assert calls[0]["ticker"] == "XOP"
    assert calls[0]["direction"] == "avoid"
    assert calls[0]["source_message_id"] == "m1"
    assert validate_compact_calls(calls) == []


def test_validate_compact_calls_rejects_long_raw_body_like_quote():
    calls = normalize_compact_calls([{
        "author": "Newton",
        "ticker": "XOP",
        "quote": "x" * (MAX_QUOTE_CHARS + 1),
        "date": "2026-06-03",
        "source": "Fundstrat full-body read",
    }])

    problems = validate_compact_calls(calls)
    assert any("quote" in problem for problem in problems)


def test_write_compact_outputs_marks_full_body_checked_without_bodies(tmp_path):
    calls = normalize_compact_calls([{
        "author": "Newton",
        "ticker": "RYF",
        "direction": "avoid",
        "quote": "Break below 74.40 keeps path of least resistance lower toward 71.",
        "date": "2026-06-03",
        "subject": "Daily Technical Strategy",
        "source_message_id": "read-1",
        "source": "Fundstrat full-body read",
    }])

    written = write_compact_outputs(calls, tmp_path, generated_at="2026-06-05T14:00:00+00:00")

    assert "fundstrat_daily_calls" in written
    summary = json.loads((tmp_path / "fundstrat_intake_summary.json").read_text(encoding="utf-8"))
    state = json.loads((tmp_path / "fundstrat_intake_state.json").read_text(encoding="utf-8"))
    entries = json.loads((tmp_path / "fundstrat_inbox_entries.json").read_text(encoding="utf-8"))
    assert summary["full_body_entries"] == 1
    assert summary["compact_full_body_derived"] is True
    assert state["processed_full_body_message_ids"] == ["read-1"]
    assert "body" not in entries[0]
    assert entries[0]["body_redacted"] is True


def test_write_compact_outputs_merge_preserves_existing_audit_entries(tmp_path):
    (tmp_path / "fundstrat_inbox_entries.json").write_text(json.dumps([{
        "subject": "Search hit",
        "date": "2026-06-02",
        "author": "Newton",
        "message_id": "snippet-1",
        "body_source": "snippet",
        "body_fetched": False,
    }]), encoding="utf-8")
    (tmp_path / "inbox_call_dates.json").write_text(json.dumps(["2026-06-02"]), encoding="utf-8")
    calls = normalize_compact_calls([{
        "author": "Newton",
        "ticker": "XOP",
        "direction": "avoid",
        "quote": "Bounce only; resistance near 175.72 should repel price toward 162.",
        "date": "2026-06-03",
        "source_message_id": "read-1",
        "source": "Fundstrat full-body read",
    }])

    write_compact_outputs(calls, tmp_path, merge_existing=True, generated_at="2026-06-05T14:00:00+00:00")

    entries = json.loads((tmp_path / "fundstrat_inbox_entries.json").read_text(encoding="utf-8"))
    dates = json.loads((tmp_path / "inbox_call_dates.json").read_text(encoding="utf-8"))
    assert {row["message_id"] for row in entries} == {"snippet-1", "read-1"}
    assert dates == ["2026-06-02", "2026-06-03"]


def test_compact_outputs_make_full_build_fundstrat_daily_has_data(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _required_files(src)
    calls = normalize_compact_calls([{
        "author": "Newton",
        "ticker": "XOP",
        "direction": "avoid",
        "quote": "Bounce only; resistance near 175.72 should repel price toward 162.",
        "date": "2026-06-03",
        "source_message_id": "read-1",
        "source": "Fundstrat full-body read",
    }])
    write_compact_outputs(calls, src, generated_at="2026-06-05T14:00:00+00:00")

    feed = build_full_feed_from_files(
        src_dir=src,
        as_of="2026-06-05",
        run_timestamp="2026-06-05T14:00:00+00:00",
    )
    rows = {row["key"]: row for row in feed["lane_status"]["rows"]}

    assert rows["fundstrat_daily"]["status"] == "has_data"


def test_compact_intake_cli_writes_outputs(tmp_path):
    src = tmp_path / "calls.json"
    src.write_text(json.dumps({"calls": [{
        "author": "Newton",
        "ticker": "XOP",
        "direction": "avoid",
        "quote": "Bounce only; resistance near 175.72 should repel price toward 162.",
        "date": "2026-06-03",
        "source_message_id": "read-1",
        "source": "Fundstrat full-body read",
    }]}), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            os.path.join(os.path.dirname(__file__), "fundstrat_daily_compact_intake.py"),
            str(src),
            "--out-dir",
            str(tmp_path),
            "--generated-at",
            "2026-06-05T14:00:00+00:00",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["written"] is True
    assert (tmp_path / "fundstrat_daily_calls.json").is_file()
