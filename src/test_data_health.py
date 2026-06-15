from __future__ import annotations

import datetime as dt
import json

import data_health as dh


NOW = dt.date(2026, 6, 11)


def _feed(**kwargs):
    base = {"staleness": {"entries": []}}
    base.update(kwargs)
    return base


def test_fresh_source_within_cadence():
    feed = _feed(staleness={"entries": [{"source": "uw_price", "date": "2026-06-10"}]})
    out = dh.assess(feed, now=NOW, rates_path="/nonexistent/x.json", shelf_path="/nonexistent/s.json")
    assert [item for item in out["items"] if item["source"] == "uw_price"][0]["status"] == "fresh"


def test_stale_source_beyond_double_cadence():
    feed = _feed(staleness={"entries": [{"source": "fundstrat_daily", "date": "2026-06-04"}]})
    out = dh.assess(feed, now=NOW, rates_path="/nonexistent/x.json", shelf_path="/nonexistent/s.json")
    item = [row for row in out["items"] if row["source"] == "fundstrat_daily"][0]
    assert item["status"] == "stale"
    assert "analyst daily notes" in out["blockers"]


def test_relevant_until_judgment_overrides_cadence():
    feed = _feed(staleness={"entries": [
        {"source": "fundstrat_daily", "date": "2026-06-01", "relevant_until": "2026-06-19"},
    ]})
    out = dh.assess(feed, now=NOW, rates_path="/nonexistent/x.json", shelf_path="/nonexistent/s.json")
    item = [row for row in out["items"] if row["source"] == "fundstrat_daily"][0]
    assert item["status"] == "fresh"
    assert "covers through 2026-06-19" in item["detail"]


def test_relevant_until_past_goes_stale_even_if_recent():
    feed = _feed(staleness={"entries": [
        {"source": "fundstrat_daily", "date": "2026-06-10", "relevant_until": "2026-06-10"},
    ]})
    out = dh.assess(feed, now=NOW, rates_path="/nonexistent/x.json", shelf_path="/nonexistent/s.json")
    assert [row for row in out["items"] if row["source"] == "fundstrat_daily"][0]["status"] == "stale"


def test_unknown_source_is_skipped_not_guessed():
    feed = _feed(staleness={"entries": [{"source": "mystery_feed", "date": "2020-01-01"}]})
    out = dh.assess(feed, now=NOW, rates_path="/nonexistent/x.json", shelf_path="/nonexistent/s.json")
    assert not [row for row in out["items"] if row["source"] == "mystery_feed"]


def test_fs_unread_behind_blocks():
    feed = _feed(fs_unread={"count": 6, "checked_at": "2026-06-11T10:30"})
    out = dh.assess(feed, now=NOW, rates_path="/nonexistent/x.json", shelf_path="/nonexistent/s.json")
    item = [row for row in out["items"] if row["source"] == "fs_inbox"][0]
    assert item["status"] == "behind"
    assert "6 newer notes unread" in item["detail"]
    assert "FS inbox" in out["blockers"]
    assert out["worst"] == "blocked"


def test_fs_inbox_absent_is_not_checked_never_all_clear():
    out = dh.assess(_feed(), now=NOW, rates_path="/nonexistent/x.json", shelf_path="/nonexistent/s.json")
    item = [row for row in out["items"] if row["source"] == "fs_inbox"][0]
    assert item["status"] == "not_checked"
    assert "FS inbox" not in out["blockers"]


def test_empty_track_record_announces_but_never_blocks(tmp_path):
    rates = tmp_path / "source_rates.json"
    rates.write_text(json.dumps({"newton": {"A": {"n": 0}}, "lee": {"A": {"n": 0}}}))
    out = dh.assess(_feed(fs_unread={"count": 0, "checked_at": "x"}), now=NOW, rates_path=rates, shelf_path="/nonexistent/s.json")
    item = [row for row in out["items"] if row["source"] == "track_record"][0]
    assert item["status"] == "empty"
    assert out["blockers"] == []
    assert out["worst"] == "announce"


def test_scored_track_record_reads_fresh(tmp_path):
    rates = tmp_path / "source_rates.json"
    rates.write_text(json.dumps({"newton": {"A": {"n": 20}}}))
    out = dh.assess(_feed(fs_unread={"count": 0, "checked_at": "x"}), now=NOW, rates_path=rates, shelf_path="/nonexistent/s.json")
    item = [row for row in out["items"] if row["source"] == "track_record"][0]
    assert item["status"] == "fresh" and "20 graded calls" in item["detail"]


def test_stale_gate_blocks():
    out = dh.assess(_feed(), gates=[{"symbol": "QQQ", "stated": "2026-06-01"}], now=NOW, rates_path="/nonexistent/x.json", shelf_path="/nonexistent/s.json")
    assert [row for row in out["items"] if row["source"] == "gates"][0]["status"] == "stale"
    assert "QQQ gate" in out["blockers"]


def test_renderer_shows_strip_and_check_first_when_blocked():
    import today_decide as td

    payload = {
        "built": "2026-06-11",
        "goal_anchor": {"pace_line": "display-only"},
        "plan_line": {},
        "gates": [],
        "data_health": {
            "items": [{"source": "fs_inbox", "label": "FS inbox", "status": "behind", "detail": "6 newer notes unread"}],
            "worst": "blocked",
            "blockers": ["FS inbox"],
        },
        "cards": [{
            "card_id": "X-1",
            "ticker": "GOOGL",
            "decision_card": {"move": {"direction": "BUY", "band": "$1"}},
            "conviction": {"read": "LOW", "points": 0},
            "window": {"class": "STAGE-ONLY"},
            "execution": {},
            "impact": {},
            "recheck_date": "2026-06-16",
        }],
        "backlog": [],
        "honesty": {},
        "congruence": {},
    }
    html = td.render_today_decide_html(payload)
    assert "data freshness:" in html
    assert "6 newer notes unread" in html
    assert "CHECK DATA FIRST" in html
    assert 'color:#94a3b8;font-weight:700">RECHECK' in html
    assert "candidate BUY; blockers or conflicts must clear first" in html


def test_renderer_no_check_first_when_all_fresh():
    import today_decide as td

    payload = {
        "built": "2026-06-11",
        "goal_anchor": {"pace_line": "display-only"},
        "plan_line": {},
        "gates": [],
        "data_health": {
            "items": [{"source": "uw_price", "label": "prices", "status": "fresh", "detail": "2026-06-11"}],
            "worst": "fresh",
            "blockers": [],
        },
        "cards": [{
            "card_id": "X-1",
            "ticker": "GOOGL",
            "decision_card": {"move": {"direction": "BUY", "band": "$1"}},
            "conviction": {"read": "LOW", "points": 0},
            "window": {"class": "STAGE-ONLY"},
            "execution": {},
            "impact": {},
            "recheck_date": "2026-06-16",
        }],
        "backlog": [],
        "honesty": {},
        "congruence": {},
    }
    html = td.render_today_decide_html(payload)
    assert "CHECK DATA FIRST" not in html
    assert 'color:#94a3b8;font-weight:700">CANDIDATE' in html
    assert "candidate BUY; stage-only until gates confirm" in html


def test_record_and_load_shelf_life_roundtrip(tmp_path):
    shelf = tmp_path / "shelf.json"
    rec = dh.record_shelf_life("fundstrat_daily", "2026-06-17", "covers next week", path=shelf)
    assert rec["relevant_until"] == "2026-06-17"
    assert dh.load_shelf_life(shelf)["fundstrat_daily"]["basis"] == "covers next week"


def test_record_shelf_life_rejects_bad_date(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        dh.record_shelf_life("fundstrat_daily", "next tuesday", path=tmp_path / "s.json")


def test_filed_judgment_overrides_cadence_in_assess(tmp_path):
    shelf = tmp_path / "shelf.json"
    dh.record_shelf_life("fundstrat_daily", "2026-06-17", "Newton: into next week", path=shelf)
    feed = _feed(staleness={"entries": [{"source": "fundstrat_daily", "date": "2026-06-09"}]})
    out = dh.assess(feed, now=NOW, rates_path="/nonexistent/x.json", shelf_path=shelf)
    item = [row for row in out["items"] if row["source"] == "fundstrat_daily"][0]
    assert item["status"] == "fresh"


def test_expired_filed_judgment_goes_stale(tmp_path):
    shelf = tmp_path / "shelf.json"
    dh.record_shelf_life("fundstrat_daily", "2026-06-10", "covered last week only", path=shelf)
    feed = _feed(staleness={"entries": [{"source": "fundstrat_daily", "date": "2026-06-10"}]})
    out = dh.assess(feed, now=NOW, rates_path="/nonexistent/x.json", shelf_path=shelf)
    assert [row for row in out["items"] if row["source"] == "fundstrat_daily"][0]["status"] == "stale"


def test_entry_level_field_wins_over_filed_judgment(tmp_path):
    shelf = tmp_path / "shelf.json"
    dh.record_shelf_life("fundstrat_daily", "2026-06-10", "old judgment", path=shelf)
    feed = _feed(staleness={"entries": [
        {"source": "fundstrat_daily", "date": "2026-06-09", "relevant_until": "2026-06-19"},
    ]})
    out = dh.assess(feed, now=NOW, rates_path="/nonexistent/x.json", shelf_path=shelf)
    assert [row for row in out["items"] if row["source"] == "fundstrat_daily"][0]["status"] == "fresh"


def test_missing_shelf_file_is_silent_noop():
    feed = _feed(staleness={"entries": [{"source": "uw_price", "date": "2026-06-10"}]})
    out = dh.assess(feed, now=NOW, rates_path="/nonexistent/x.json", shelf_path="/nonexistent/s.json")
    assert [row for row in out["items"] if row["source"] == "uw_price"][0]["status"] == "fresh"
