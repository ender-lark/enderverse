import json

from system_improvement_queue import (
    active_or_queued,
    load_queue,
    summary,
    validate_queue,
)


def test_committed_queue_validates():
    queue = load_queue()
    assert validate_queue(queue) == []
    ids = {item["id"] for item in queue["items"]}
    assert "holdings-account-tabs" in ids
    assert "broker-pdf-position-reconciliation" in ids
    assert "fundstrat-gmail-hardening" in ids


def test_active_or_queued_prioritizes_p1_before_p2():
    queue = {
        "items": [
            {
                "id": "p2",
                "title": "P2",
                "priority": "P2",
                "status": "queued",
                "area": "x",
                "why": "w",
                "done_when": "d",
            },
            {
                "id": "p1",
                "title": "P1",
                "priority": "P1",
                "status": "active",
                "area": "x",
                "why": "w",
                "done_when": "d",
            },
        ]
    }
    assert [item["id"] for item in active_or_queued(queue)] == ["p1", "p2"]


def test_validate_queue_catches_duplicate_and_bad_values():
    queue = {
        "items": [
            {
                "id": "dup",
                "title": "A",
                "priority": "P9",
                "status": "queued",
                "area": "x",
                "why": "w",
                "done_when": "d",
            },
            {
                "id": "dup",
                "title": "B",
                "priority": "P1",
                "status": "unknown",
                "area": "x",
                "why": "w",
                "done_when": "d",
            },
        ]
    }
    problems = validate_queue(queue)
    assert any("duplicate" in p for p in problems)
    assert any("invalid priority" in p for p in problems)
    assert any("invalid status" in p for p in problems)


def test_summary_is_json_serializable():
    data = summary(load_queue())
    json.dumps(data)
    assert data["items"] >= 1
    assert data["next"]
