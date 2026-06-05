#!/usr/bin/env python3
"""Validate and summarize the Investing OS system-improvement queue."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_QUEUE_PATH = Path(__file__).resolve().parent / "system_improvement_queue.json"
REQUIRED_ITEM_FIELDS = {
    "id",
    "title",
    "priority",
    "status",
    "area",
    "why",
    "done_when",
}
VALID_PRIORITIES = {"P0", "P1", "P2", "P3"}
VALID_STATUSES = {"queued", "active", "blocked", "done", "deferred"}


def load_queue(path: str | Path = DEFAULT_QUEUE_PATH) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as fh:
        return json.load(fh)


def validate_queue(queue: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    items = queue.get("items")
    if not isinstance(items, list):
        return ["items must be a list"]
    seen: set[str] = set()
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            problems.append(f"items[{idx}] must be an object")
            continue
        missing = REQUIRED_ITEM_FIELDS - set(item)
        for field in sorted(missing):
            problems.append(f"items[{idx}] missing {field}")
        item_id = str(item.get("id") or "").strip()
        if not item_id:
            problems.append(f"items[{idx}].id must be non-empty")
        elif item_id in seen:
            problems.append(f"duplicate item id: {item_id}")
        seen.add(item_id)
        if item.get("priority") not in VALID_PRIORITIES:
            problems.append(f"{item_id or idx} has invalid priority {item.get('priority')!r}")
        if item.get("status") not in VALID_STATUSES:
            problems.append(f"{item_id or idx} has invalid status {item.get('status')!r}")
    return problems


def active_or_queued(queue: dict[str, Any]) -> list[dict[str, Any]]:
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    rows = [
        item for item in queue.get("items", [])
        if isinstance(item, dict) and item.get("status") in {"active", "queued", "blocked"}
    ]
    rows.sort(key=lambda item: (order.get(item.get("priority"), 9), item.get("id", "")))
    return rows


def summary(queue: dict[str, Any]) -> dict[str, Any]:
    rows = active_or_queued(queue)
    by_status: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    for item in queue.get("items", []):
        if not isinstance(item, dict):
            continue
        by_status[item.get("status", "")] = by_status.get(item.get("status", ""), 0) + 1
        by_priority[item.get("priority", "")] = by_priority.get(item.get("priority", ""), 0) + 1
    return {
        "items": len(queue.get("items") or []),
        "active_or_queued": len(rows),
        "by_status": by_status,
        "by_priority": by_priority,
        "next": [
            {
                "id": item["id"],
                "priority": item["priority"],
                "status": item["status"],
                "title": item["title"],
            }
            for item in rows[:5]
        ],
    }


def _self_test() -> bool:
    queue = {
        "items": [
            {
                "id": "a",
                "title": "A",
                "priority": "P1",
                "status": "active",
                "area": "x",
                "why": "because",
                "done_when": "done",
            },
            {
                "id": "b",
                "title": "B",
                "priority": "P2",
                "status": "queued",
                "area": "x",
                "why": "because",
                "done_when": "done",
            },
        ]
    }
    assert validate_queue(queue) == []
    assert [r["id"] for r in active_or_queued(queue)] == ["a", "b"]
    assert summary(queue)["by_status"]["active"] == 1
    bad = {"items": [{"id": "a", "priority": "PX", "status": "queued"}]}
    assert validate_queue(bad)
    print("system_improvement_queue self-test: PASS")
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate system_improvement_queue.json")
    parser.add_argument("--path", default=str(DEFAULT_QUEUE_PATH))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    queue = load_queue(args.path)
    problems = validate_queue(queue)
    if problems:
        print(json.dumps({"valid": False, "problems": problems}, indent=2))
        return 2
    print(json.dumps({"valid": True, **summary(queue)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
