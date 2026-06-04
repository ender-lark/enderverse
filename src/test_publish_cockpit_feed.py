"""Tests for the routine/operator publish runner."""
import json

import publish_cockpit_feed as pcf
from goal_impact import annotate_action


def _feed():
    action = annotate_action({
        "rank": 1,
        "kind": "buy_now",
        "ticker": "AVGO",
        "what": "Add AVGO through the sizing gate",
        "confidence": "High",
        "your_move": "Review sizing and execute if gate is clear",
        "gate": None,
        "source": "test",
        "why": "Fresh high-conviction opportunity",
    })
    return {
        "generated_at": "2026-06-04T16:00:00+00:00",
        "staleness": {
            "stamp": "sourced",
            "entries": [
                {"source": "portfolio", "date": "2026-06-04T16:00:00+00:00",
                 "age_days": 0, "stale": False, "flag": ""},
                {"source": "uw_price", "date": "2026-06-04T16:00:00+00:00",
                 "age_days": 0, "stale": False, "flag": ""},
            ],
            "stale": [],
        },
        "hero": {"hero": {"count": 0, "names": [], "leading_sleeves": []},
                 "needs_you": {"count": 0, "items": []}},
        "fresh_signals": [],
        "holdings": [],
        "rotation": [],
        "macro": {"line": "", "regime": {}, "alerts": [], "implications": []},
        "actions": [action],
        "catalysts": [],
        "questions": [],
        "research": {},
    }


def test_publish_runner_writes_feed_and_memory_after_gate_pass(tmp_path):
    feed_out = tmp_path / "latest_feed.json"
    store = tmp_path / "open_opportunities.json"
    summary = pcf.publish_cockpit_feed(
        _feed(),
        feed_out=str(feed_out),
        store_path=str(store),
        prices={"AVGO": 1400},
    )
    assert summary["published"] is True
    assert summary["memory"]["updated"] is True
    assert json.load(open(feed_out))["actions"][0]["ticker"] == "AVGO"
    assert json.load(open(store))["opportunities"][0]["ticker"] == "AVGO"


def test_publish_runner_writes_nothing_after_gate_fail(tmp_path):
    feed = _feed()
    feed["generated_at"] = "2026-06-04T10:00:00+00:00"
    feed_out = tmp_path / "latest_feed.json"
    store = tmp_path / "open_opportunities.json"
    summary = pcf.publish_cockpit_feed(
        feed,
        feed_out=str(feed_out),
        store_path=str(store),
    )
    assert summary["published"] is False
    assert summary["reason"] == "publish_gate_failed"
    assert not feed_out.exists()
    assert not store.exists()


def test_publish_runner_cli_updates_both_artifacts(tmp_path):
    feed_path = tmp_path / "feed.json"
    feed_out = tmp_path / "latest_feed.json"
    store = tmp_path / "open_opportunities.json"
    feed_path.write_text(json.dumps(_feed()))
    rc = pcf.main([
        "--feed", str(feed_path),
        "--feed-out", str(feed_out),
        "--store", str(store),
    ])
    assert rc == 0
    assert feed_out.exists()
    assert json.load(open(store))["opportunities"][0]["ticker"] == "AVGO"
