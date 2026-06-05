"""Tests for the source-calibration chain staleness banner wired into daily_preflight
(v12.5, Issue #10 §3). The gauge logic lives in source_call_tracker and is tested
separately; here we test the PRE-FLIGHT WIRING + the honest 'not checked' degrade."""

import json
import sys
from types import SimpleNamespace

import daily_preflight
from daily_preflight import _calibration_chain_banner


def test_live_side_absent_says_not_checked():
    """No live Inbox/Log supplied -> PROVISIONAL 'not checked', never silent-clean."""
    source_calls = [{"date": "2026-05-19", "source": "newton"}]
    banner = _calibration_chain_banner(source_calls, None, None)
    assert "NOT CHECKED" in banner
    assert "PROVISIONAL" in banner
    assert "2026-05-19" in banner  # surfaces the cache as-of date


def test_fresh_chain_is_quiet():
    """Inbox <= Log <= Cache -> chain fresh -> empty banner."""
    source_calls = [{"date": "2026-05-28"}]          # cache newest 5/28
    banner = _calibration_chain_banner(
        source_calls, inbox_call_dates=["2026-05-28"], log_call_dates=["2026-05-28"])
    assert banner == ""


def test_log_cache_lag_fires_stale_banner():
    """The 2026-05-28 failure: Log newest 5/28 but cache stuck at 5/19 -> STALE."""
    source_calls = [{"date": "2026-05-19"}]          # cache stuck at 5/19
    banner = _calibration_chain_banner(
        source_calls, inbox_call_dates=["2026-05-28"], log_call_dates=["2026-05-28"])
    assert "STALE" in banner
    assert "PROVISIONAL" in banner
    assert "9d behind" in banner                     # (5/28 - 5/19)


def test_inbox_log_lag_fires_stale_banner():
    """Inbox ahead of Log -> un-ingested calls -> STALE."""
    source_calls = [{"date": "2026-05-28"}]
    banner = _calibration_chain_banner(
        source_calls, inbox_call_dates=["2026-06-02"], log_call_dates=["2026-05-28"])
    assert "STALE" in banner


def test_non_list_source_calls_degrades_safely():
    """Malformed source_calls (dict/None) -> treated as empty cache, no crash."""
    for bad in (None, {}, {"calls": []}, "garbage"):
        banner = _calibration_chain_banner(bad, None, None)
        assert "NOT CHECKED" in banner   # still surfaces, with unknown cache date


def test_comment_rows_without_date_are_ignored():
    """The _comment row in source_calls.json (no 'date') must not break extraction."""
    source_calls = [{"_comment": "header"}, {"date": "2026-05-19"}]
    banner = _calibration_chain_banner(source_calls, None, None)
    assert "2026-05-19" in banner


def test_main_passes_live_call_dates_into_orchestrator(tmp_path, monkeypatch, capsys):
    """Banner inputs must also reach persistence; otherwise P-WAKE-UP stays provisional."""
    captured = {}

    def fake_orchestrate(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    fake_so = SimpleNamespace(
        orchestrate=fake_orchestrate,
        format_text=lambda dashboard: "dashboard",
        format_json=lambda dashboard: json.dumps(dashboard),
    )
    monkeypatch.setitem(sys.modules, "session_orchestrator", fake_so)
    monkeypatch.setattr(sys, "argv", [
        "daily_preflight.py",
        "--inputs-dir", str(tmp_path),
    ])

    (tmp_path / "positions.json").write_text(json.dumps({
        "snapshot_date": daily_preflight.date.today().isoformat(),
        "positions": [],
    }), encoding="utf-8")
    (tmp_path / "theses.json").write_text("[]", encoding="utf-8")
    (tmp_path / "source_calls.json").write_text(json.dumps([
        {"date": "2026-05-28", "ticker": "NVDA"}
    ]), encoding="utf-8")
    (tmp_path / "inbox_call_dates.json").write_text(json.dumps(["2026-05-28"]), encoding="utf-8")
    (tmp_path / "log_call_dates.json").write_text(json.dumps(["2026-05-28"]), encoding="utf-8")

    daily_preflight.main()

    assert captured["inbox_call_dates"] == ["2026-05-28"]
    assert captured["log_call_dates"] == ["2026-05-28"]
    assert "dashboard" in capsys.readouterr().out
