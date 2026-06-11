"""Tests for data_health.py and its wiring into the TODAY-DECIDE surface."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import data_health as dh


NOW = dt.date(2026, 6, 11)


def _feed(**kw):
    base = {"staleness": {"entries": []}}
    base.update(kw)
    return base


def test_fresh_source_within_cadence():
    f = _feed(staleness={"entries": [{"source": "uw_price", "date": "2026-06-10"}]})
    out = dh.assess(f, now=NOW, rates_path="/nonexistent/x.json", shelf_path="/nonexistent/s.json")
    px = [i for i in out["items"] if i["source"] == "uw_price"][0]
    assert px["status"] == "fresh"


def test_stale_source_beyond_double_cadence():
    f = _feed(staleness={"entries": [{"source": "fundstrat_daily", "date": "2026-06-04"}]})
    out = dh.assess(f, now=NOW, rates_path="/nonexistent/x.json", shelf_path="/nonexistent/s.json")
    it = [i for i in out["items"] if i["source"] == "fundstrat_daily"][0]
    assert it["status"] == "stale"
    assert "analyst daily notes" in out["blockers"]


def test_relevant_until_judgment_overrides_cadence():
    # A monthly-style note filed long ago but whose content covers through next week
    f = _feed(staleness={"entries": [
        {"source": "fundstrat_daily", "date": "2026-06-01", "relevant_until": "2026-06-19"}]})
    out = dh.assess(f, now=NOW, rates_path="/nonexistent/x.json", shelf_path="/nonexistent/s.json")
    it = [i for i in out["items"] if i["source"] == "fundstrat_daily"][0]
    assert it["status"] == "fresh"
    assert "covers through 2026-06-19" in it["detail"]


def test_relevant_until_past_goes_stale_even_if_recent():
    f = _feed(staleness={"entries": [
        {"source": "fundstrat_daily", "date": "2026-06-10", "relevant_until": "2026-06-10"}]})
    out = dh.assess(f, now=NOW, rates_path="/nonexistent/x.json", shelf_path="/nonexistent/s.json")
    it = [i for i in out["items"] if i["source"] == "fundstrat_daily"][0]
    assert it["status"] == "stale"


def test_unknown_source_is_skipped_not_guessed():
    f = _feed(staleness={"entries": [{"source": "mystery_feed", "date": "2020-01-01"}]})
    out = dh.assess(f, now=NOW, rates_path="/nonexistent/x.json", shelf_path="/nonexistent/s.json")
    assert not [i for i in out["items"] if i["source"] == "mystery_feed"]


def test_fs_unread_behind_blocks():
    f = _feed(fs_unread={"count": 6, "checked_at": "2026-06-11T10:30"})
    out = dh.assess(f, now=NOW, rates_path="/nonexistent/x.json", shelf_path="/nonexistent/s.json")
    it = [i for i in out["items"] if i["source"] == "fs_inbox"][0]
    assert it["status"] == "behind"
    assert "6 newer notes unread" in it["detail"]
    assert "FS inbox" in out["blockers"]
    assert out["worst"] == "blocked"


def test_fs_inbox_absent_is_not_checked_never_all_clear():
    out = dh.assess(_feed(), now=NOW, rates_path="/nonexistent/x.json", shelf_path="/nonexistent/s.json")
    it = [i for i in out["items"] if i["source"] == "fs_inbox"][0]
    assert it["status"] == "not_checked"
    assert "FS inbox" not in out["blockers"]


def test_empty_track_record_announces_but_never_blocks(tmp_path):
    rp = tmp_path / "source_rates.json"
    rp.write_text(json.dumps({"newton": {"A": {"n": 0}}, "lee": {"A": {"n": 0}}}))
    out = dh.assess(_feed(fs_unread={"count": 0, "checked_at": "x"}), now=NOW, rates_path=rp, shelf_path="/nonexistent/s.json")
    tr = [i for i in out["items"] if i["source"] == "track_record"][0]
    assert tr["status"] == "empty"
    assert "no graded calls yet" in tr["detail"]
    assert out["blockers"] == []
    assert out["worst"] == "announce"


def test_scored_track_record_reads_fresh(tmp_path):
    rp = tmp_path / "source_rates.json"
    rp.write_text(json.dumps({"newton": {"A": {"n": 20}}}))
    out = dh.assess(_feed(fs_unread={"count": 0, "checked_at": "x"}), now=NOW, rates_path=rp, shelf_path="/nonexistent/s.json")
    tr = [i for i in out["items"] if i["source"] == "track_record"][0]
    assert tr["status"] == "fresh" and "20 graded calls" in tr["detail"]


def test_stale_gate_blocks():
    gates = [{"symbol": "QQQ", "stated": "2026-06-01"}]
    out = dh.assess(_feed(), gates=gates, now=NOW, rates_path="/nonexistent/x.json", shelf_path="/nonexistent/s.json")
    g = [i for i in out["items"] if i["source"] == "gates"][0]
    assert g["status"] == "stale"
    assert "QQQ gate" in out["blockers"]


def test_renderer_shows_strip_and_check_first_when_blocked():
    import today_decide as td
    payload = {
        "built": "2026-06-11",
        "goal_anchor": {"pace_line": "y"}, "plan_line": {},
        "gates": [],
        "data_health": {
            "items": [{"source": "fs_inbox", "label": "FS inbox", "status": "behind",
                       "detail": "6 newer notes unread (checked 10:30)"}],
            "worst": "blocked", "blockers": ["FS inbox"],
        },
        "cards": [{
            "card_id": "X-1", "ticker": "GOOGL",
            "decision_card": {"move": {"direction": "BUY", "band": "$1"}},
            "conviction": {"read": "LOW", "points": 0},
            "window": {"class": "STAGE-ONLY"},
            "execution": {}, "impact": {}, "recheck_date": "2026-06-16",
        }],
        "backlog": [], "honesty": {}, "congruence": {},
    }
    html = td.render_today_decide_html(payload)
    assert "data freshness:" in html
    assert "6 newer notes unread" in html
    assert "CHECK DATA FIRST" in html
    # direction renders muted, not green, when blocked
    assert 'color:#94a3b8;font-weight:700">BUY' in html


def test_renderer_no_check_first_when_all_fresh():
    import today_decide as td
    payload = {
        "built": "2026-06-11",
        "goal_anchor": {"pace_line": "y"}, "plan_line": {},
        "gates": [],
        "data_health": {"items": [{"source": "uw_price", "label": "prices",
                                   "status": "fresh", "detail": "2026-06-11"}],
                        "worst": "fresh", "blockers": []},
        "cards": [{
            "card_id": "X-1", "ticker": "GOOGL",
            "decision_card": {"move": {"direction": "BUY", "band": "$1"}},
            "conviction": {"read": "LOW", "points": 0},
            "window": {"class": "STAGE-ONLY"},
            "execution": {}, "impact": {}, "recheck_date": "2026-06-16",
        }],
        "backlog": [], "honesty": {}, "congruence": {},
    }
    html = td.render_today_decide_html(payload)
    assert "CHECK DATA FIRST" not in html
    assert 'color:#34d399;font-weight:700">BUY' in html


# ---- slice 2: shelf-life at filing time ----

def test_record_and_load_shelf_life_roundtrip(tmp_path):
    sp = tmp_path / "shelf.json"
    rec = dh.record_shelf_life("fundstrat_daily", "2026-06-17", "covers next week", path=sp)
    assert rec["relevant_until"] == "2026-06-17"
    loaded = dh.load_shelf_life(sp)
    assert loaded["fundstrat_daily"]["basis"] == "covers next week"


def test_record_shelf_life_rejects_bad_date(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        dh.record_shelf_life("fundstrat_daily", "next tuesday", path=tmp_path / "s.json")


def test_filed_judgment_overrides_cadence_in_assess(tmp_path):
    sp = tmp_path / "shelf.json"
    dh.record_shelf_life("fundstrat_daily", "2026-06-17", "Newton: into next week", path=sp)
    f = _feed(staleness={"entries": [{"source": "fundstrat_daily", "date": "2026-06-09"}]})
    out = dh.assess(f, now=NOW, rates_path="/nonexistent/x.json", shelf_path=sp)
    it = [i for i in out["items"] if i["source"] == "fundstrat_daily"][0]
    assert it["status"] == "fresh"
    assert "covers through 2026-06-17" in it["detail"]


def test_expired_filed_judgment_goes_stale(tmp_path):
    sp = tmp_path / "shelf.json"
    dh.record_shelf_life("fundstrat_daily", "2026-06-10", "covered last week only", path=sp)
    f = _feed(staleness={"entries": [{"source": "fundstrat_daily", "date": "2026-06-10"}]})
    out = dh.assess(f, now=NOW, rates_path="/nonexistent/x.json", shelf_path=sp)
    it = [i for i in out["items"] if i["source"] == "fundstrat_daily"][0]
    assert it["status"] == "stale"
    assert "covered only through 2026-06-10" in it["detail"]


def test_entry_level_field_wins_over_filed_judgment(tmp_path):
    sp = tmp_path / "shelf.json"
    dh.record_shelf_life("fundstrat_daily", "2026-06-10", "old judgment", path=sp)
    f = _feed(staleness={"entries": [
        {"source": "fundstrat_daily", "date": "2026-06-09", "relevant_until": "2026-06-19"}]})
    out = dh.assess(f, now=NOW, rates_path="/nonexistent/x.json", shelf_path=sp)
    it = [i for i in out["items"] if i["source"] == "fundstrat_daily"][0]
    assert it["status"] == "fresh" and "2026-06-19" in it["detail"]


def test_missing_shelf_file_is_silent_noop():
    f = _feed(staleness={"entries": [{"source": "uw_price", "date": "2026-06-10"}]})
    out = dh.assess(f, now=NOW, rates_path="/nonexistent/x.json", shelf_path="/nonexistent/s.json")
    assert [i for i in out["items"] if i["source"] == "uw_price"][0]["status"] == "fresh"
