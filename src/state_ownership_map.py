#!/usr/bin/env python3
"""Validate the Investing OS state ownership map."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_MAP_PATH = Path(__file__).resolve().parent / "state_ownership_map.json"

REQUIRED_OBJECT_FIELDS = {
    "id",
    "source_of_truth",
    "repo_artifact",
    "producer",
    "feed_path",
    "dashboard_surface",
    "mirror_policy",
    "freshness_contract",
    "not_checked_behavior",
    "action_surface",
}

EXPECTED_ARTIFACT_IDS = {
    "positions",
    "theses",
    "fundstrat_daily_calls",
    "research_queue",
    "catalysts",
    "uw_opportunity_signals",
    "parabolic_setups",
    "top_prospects",
    "source_calls",
    "macro_state",
    "uw_closes",
    "daily_synthesis",
    "open_opportunities",
    "heartbeat",
}


def _read_json(path: str | Path) -> Any:
    with Path(path).open(encoding="utf-8") as fh:
        return json.load(fh)


def validate_ownership_map(payload: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if not isinstance(payload, dict):
        return ["top-level must be an object"]
    objects = payload.get("objects")
    if not isinstance(objects, list) or not objects:
        return ["objects must be a non-empty list"]

    seen: set[str] = set()
    ids: set[str] = set()
    for idx, obj in enumerate(objects):
        if not isinstance(obj, dict):
            problems.append(f"objects[{idx}] must be an object")
            continue
        obj_id = str(obj.get("id") or "").strip()
        if not obj_id:
            problems.append(f"objects[{idx}].id must be non-empty")
        elif obj_id in seen:
            problems.append(f"duplicate object id: {obj_id}")
        else:
            seen.add(obj_id)
            ids.add(obj_id)
        for field in REQUIRED_OBJECT_FIELDS:
            value = obj.get(field)
            if not isinstance(value, str) or not value.strip():
                problems.append(f"{obj_id or f'objects[{idx}]'}.{field} must be non-empty")

    missing = sorted(EXPECTED_ARTIFACT_IDS - ids)
    if missing:
        problems.append(f"missing expected artifact ownership ids: {', '.join(missing)}")
    return problems


def _self_test() -> int:
    payload = {
        "objects": [
            {
                field: "x"
                for field in REQUIRED_OBJECT_FIELDS
            }
            | {"id": obj_id}
            for obj_id in EXPECTED_ARTIFACT_IDS
        ]
    }
    assert validate_ownership_map(payload) == []
    bad = {"objects": [{"id": "positions"}]}
    assert validate_ownership_map(bad)
    print("state_ownership_map self-test: PASS")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate state_ownership_map.json")
    parser.add_argument("--path", default=str(DEFAULT_MAP_PATH))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()
    problems = validate_ownership_map(_read_json(args.path))
    print(json.dumps({
        "valid": not problems,
        "problems": problems,
    }, indent=2))
    return 0 if not problems else 2


if __name__ == "__main__":
    raise SystemExit(main())
