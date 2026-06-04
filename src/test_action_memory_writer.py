"""Tests for routine-side action memory writer."""
import json
import os

import action_memory_writer as amw
import open_opportunities as oo


def _feed(actions=None, held=None):
    return {
        "generated_at": "2026-06-04T16:00:00",
        "actions": actions or [],
        "holdings": [{"cat": "Book", "pos": [
            {"t": t, "st": "Owned"} for t in (held or [])
        ]}],
    }


def _buy(ticker, kind="buy_now"):
    return {"ticker": ticker, "kind": kind, "source": "test"}


def test_writer_adds_trackable_actions_to_store(tmp_path):
    path = tmp_path / "open_opportunities.json"
    summary = amw.update_action_memory_from_feed(
        _feed(actions=[_buy("AVGO"), _buy("FN", "watch_entry")]),
        store_path=str(path),
        prices={"AVGO": 1400},
    )
    assert summary["open_count"] == 1
    saved = json.load(open(path))
    assert saved["opportunities"][0]["ticker"] == "AVGO"
    assert saved["opportunities"][0]["flag_price"] == 1400
    assert saved["history"] == []


def test_writer_marks_prior_open_as_acted_when_now_held(tmp_path):
    path = tmp_path / "open_opportunities.json"
    store = oo.seed_open_opportunities([
        {"ticker": "FN", "first_flagged": "2026-05-28", "flag_price": 600},
    ], as_of="2026-05-28")
    json.dump(store, open(path, "w"))
    summary = amw.update_action_memory_from_feed(
        _feed(actions=[], held=["FN"]),
        store_path=str(path),
    )
    assert summary["open_count"] == 0
    assert summary["dropped"][0]["status"] == "acted"
    saved = json.load(open(path))
    assert saved["history"][0]["ticker"] == "FN"
    assert saved["history"][0]["status"] == "acted"


def test_writer_applies_explicit_resolution(tmp_path):
    path = tmp_path / "open_opportunities.json"
    store = oo.seed_open_opportunities([
        {"ticker": "MU", "first_flagged": "2026-05-28"},
    ], as_of="2026-05-28")
    json.dump(store, open(path, "w"))
    summary = amw.update_action_memory_from_feed(
        _feed(),
        store_path=str(path),
        resolutions=[{"ticker": "MU", "status": "missed", "reason": "ran before action"}],
    )
    assert summary["history_count"] == 1
    saved = json.load(open(path))
    assert saved["history"][0]["status"] == "missed"
    assert saved["history"][0]["reason"] == "ran before action"


def test_writer_cli_updates_store(tmp_path):
    feed = tmp_path / "feed.json"
    store = tmp_path / "open_opportunities.json"
    feed.write_text(json.dumps(_feed(actions=[_buy("ITA")])))
    rc = amw.main(["--feed", str(feed), "--store", str(store)])
    assert rc == 0
    saved = json.load(open(store))
    assert saved["opportunities"][0]["ticker"] == "ITA"
    assert os.path.exists(store)
