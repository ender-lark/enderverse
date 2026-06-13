from __future__ import annotations

import json

import held_decisions
import trigger_check


def _held_packet() -> dict:
    return {
        "id": "test-packet",
        "title": "Test held packet",
        "notion_url": "https://app.notion.com/p/test",
        "parked_date": "2026-06-13",
        "review_by": "2026-06-14",
        "status": "held",
        "log": [{"at": "2026-06-13T00:00:00-04:00", "action": "parked", "note": "operator parked"}],
    }


def test_cli_add_and_resolve_updates_companion_trigger(tmp_path):
    held_path = tmp_path / "held_decisions.json"
    registry_path = tmp_path / "trigger_registry.json"
    registry_path.write_text("[]", encoding="utf-8")

    rc = held_decisions.main([
        "--add",
        "--held-path",
        str(held_path),
        "--registry",
        str(registry_path),
        "--id",
        "test-packet",
        "--title",
        "Test held packet",
        "--notion-url",
        "https://app.notion.com/p/test",
        "--parked-date",
        "2026-06-13",
        "--review-by",
        "2026-06-14",
        "--note",
        "operator parked",
        "--now",
        "2026-06-13T08:00:00-04:00",
    ])

    rows = json.loads(held_path.read_text(encoding="utf-8"))
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert rc == 0
    assert rows[0]["status"] == "held"
    assert registry[0]["id"] == "held-review-test-packet"
    assert registry[0]["condition"]["params"]["event"] == "held_decision_review"
    assert registry[0]["condition"]["params"]["date"] == "2026-06-14"

    rc = held_decisions.main([
        "--resolve",
        "test-packet",
        "--action",
        "repark",
        "--new-date",
        "2026-06-21",
        "--held-path",
        str(held_path),
        "--registry",
        str(registry_path),
        "--now",
        "2026-06-14T09:00:00-04:00",
    ])

    rows = json.loads(held_path.read_text(encoding="utf-8"))
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert rc == 0
    assert rows[0]["status"] == "reparked"
    assert rows[0]["review_by"] == "2026-06-21"
    assert registry[0]["status"] == "armed"
    assert registry[0]["condition"]["params"]["date"] == "2026-06-21"

    rc = held_decisions.main([
        "--resolve",
        "test-packet",
        "--action",
        "kill",
        "--held-path",
        str(held_path),
        "--registry",
        str(registry_path),
        "--now",
        "2026-06-15T09:00:00-04:00",
    ])

    rows = json.loads(held_path.read_text(encoding="utf-8"))
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert rc == 0
    assert rows[0]["status"] == "reviewed"
    assert registry[0]["status"] == "cancelled"
    assert registry[0]["cancel_reason"] == "operator resolved held decision: kill"


def test_trigger_check_fires_held_review_and_one_overdue_escalation():
    packet = _held_packet()
    registry = [held_decisions.make_review_trigger(packet, now="2026-06-13T08:00:00-04:00")]

    due = trigger_check.evaluate_registry(
        registry,
        trigger_check.quote_fn_from_map({}),
        as_of="2026-06-14T12:00:00Z",
        held_decision_statuses={"test-packet": "held"},
    )

    assert due["fired_count"] == 1
    assert registry[0]["status"] == "fired"
    assert "held decision review due" in registry[0]["fire_reason"]

    overdue = trigger_check.evaluate_registry(
        registry,
        trigger_check.quote_fn_from_map({}),
        as_of="2026-06-15T12:00:00Z",
        held_decision_statuses={"test-packet": "held"},
    )
    repeat = trigger_check.evaluate_registry(
        registry,
        trigger_check.quote_fn_from_map({}),
        as_of="2026-06-15T13:00:00Z",
        held_decision_statuses={"test-packet": "held"},
    )

    assert overdue["fired_count"] == 1
    assert "still held one day after review_by" in overdue["fired"][0]["fire_reason"]
    assert registry[0]["overdue_escalated_on"] == "2026-06-15"
    assert repeat["fired_count"] == 0


def test_seeded_held_decisions_and_triggers_are_aligned():
    rows = held_decisions.load_decisions()
    registry = trigger_check.load_registry()
    active_ids = {row["id"] for row in held_decisions.active_decisions(rows)}
    trigger_ids = {row["id"] for row in registry}

    assert {
        "sunday-rebalance-packet",
        "sunday-geo-risk-register-v0",
        "sunday-policy-money-map-v0",
    }.issubset(active_ids)
    for decision_id in active_ids:
        assert f"held-review-{decision_id}" in trigger_ids
