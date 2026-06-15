import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from full_build_runner import build_full_feed_from_files
from fundstrat_daily_compact_intake import (
    MAX_QUOTE_CHARS,
    is_low_value_compact_call,
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


def test_compact_calls_suppress_low_value_fundstrat_fluff():
    rows = [{
        "author": "Fundstrat",
        "ticker": "SPY",
        "direction": "watch",
        "quote": "Join us for a webinar replay with general long-term market thoughts.",
        "date": "2026-06-08",
        "source_message_id": "m-fluff",
        "source": "Fundstrat full-body read",
    }]

    assert is_low_value_compact_call(rows[0]) is True
    assert normalize_compact_calls(rows) == []


def test_compact_calls_keep_watch_rows_when_they_change_timing_or_risk():
    calls = normalize_compact_calls([{
        "author": "Newton",
        "ticker": "QQQ",
        "direction": "watch",
        "quote": "Watch support near 741 today; break below would raise hedge/re-check risk.",
        "date": "2026-06-08",
        "source_message_id": "m-watch",
        "source": "Fundstrat full-body read",
    }])

    assert calls[0]["ticker"] == "QQQ"
    assert calls[0]["direction"] == "watch"
    assert calls[0]["capture_policy"] == "daily_call"
    assert calls[0]["use_case"] == "technical_timing"


def test_compact_calls_suppress_monthly_top5_rows_from_daily_call_path():
    rows = [{
        "author": "Fundstrat",
        "ticker": "NVDA",
        "direction": "buy",
        "subject": "June Monthly Bible - Top 5 large cap",
        "quote": "NVDA is included in the monthly Top 5 large cap list.",
        "date": "2026-06-09",
        "source_message_id": "m-monthly",
        "source": "Fundstrat full-body read",
    }]

    assert is_low_value_compact_call(rows[0]) is True
    assert normalize_compact_calls(rows) == []


def test_compact_calls_suppress_weekly_recaps_without_portfolio_change():
    rows = [{
        "author": "Fundstrat",
        "ticker": "QQQ",
        "direction": "watch",
        "subject": "Weekly Review",
        "quote": "QQQ was discussed in a recap of last week's market action.",
        "date": "2026-06-09",
        "source_message_id": "m-weekly",
        "source": "Fundstrat full-body read",
    }]

    assert is_low_value_compact_call(rows[0]) is True
    assert normalize_compact_calls(rows) == []


def test_compact_calls_keep_weekly_review_when_it_changes_risk_posture():
    calls = normalize_compact_calls([{
        "author": "Fundstrat",
        "ticker": "QQQ",
        "direction": "watch",
        "subject": "Weekly Review",
        "quote": "Watch QQQ support near 520; break below would raise hedge/re-check risk.",
        "date": "2026-06-09",
        "source_message_id": "m-weekly-risk",
        "source": "Fundstrat full-body read",
    }])

    assert calls[0]["ticker"] == "QQQ"
    assert calls[0]["publication_type"] == "weekly_review"
    assert calls[0]["capture_policy"] == "daily_call"
    assert calls[0]["use_case"] == "risk_posture"


def test_validate_compact_calls_rejects_long_raw_body_like_quote():
    calls = normalize_compact_calls([{
        "author": "Newton",
        "ticker": "XOP",
        "quote": "Break below support today " + ("x" * (MAX_QUOTE_CHARS + 1)),
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
    inventory = json.loads((tmp_path / "fs_ingest_inventory.json").read_text(encoding="utf-8"))
    assert inventory["entries"][0]["source_id"] == "read-1"
    assert inventory["entries"][0]["skipped_count"] == 0


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


def test_write_compact_outputs_merge_preserves_source_call_candidates(tmp_path):
    existing_candidates = [{
        "source": "newton",
        "ticker": "TNX",
        "tier": "B",
        "date": "2026-06-03",
        "outcome": "Pending",
    }]
    (tmp_path / "source_call_candidates.json").write_text(json.dumps(existing_candidates), encoding="utf-8")
    calls = normalize_compact_calls([{
        "author": "Newton",
        "ticker": "QQQ",
        "direction": "watch",
        "quote": "Support-zone check from a compact full-body-derived daily note.",
        "date": "2026-06-05",
        "source_message_id": "read-2",
        "source": "Fundstrat full-body read",
        "evidence_detail": {
            "source_surface": "video_transcript",
            "key_levels": "QQQ support zone must hold.",
            "confirmation_needed": "Breadth confirmation.",
        },
    }])

    write_compact_outputs(calls, tmp_path, merge_existing=True, generated_at="2026-06-07T16:00:00+00:00")

    candidates = json.loads((tmp_path / "source_call_candidates.json").read_text(encoding="utf-8"))
    source_calls = json.loads((tmp_path / "source_calls.json").read_text(encoding="utf-8"))
    log_dates = json.loads((tmp_path / "log_call_dates.json").read_text(encoding="utf-8"))
    assert {row["ticker"] for row in candidates} == {"TNX", "QQQ"}
    assert {row["ticker"] for row in source_calls} == {"TNX", "QQQ"}
    qqq_candidate = next(row for row in candidates if row["ticker"] == "QQQ")
    qqq_source_call = next(row for row in source_calls if row["ticker"] == "QQQ")
    assert qqq_candidate["evidence_detail"]["key_levels"] == "QQQ support zone must hold."
    assert qqq_source_call["evidence_detail"]["confirmation_needed"] == "Breadth confirmation."
    assert log_dates == ["2026-06-03", "2026-06-05"]


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
