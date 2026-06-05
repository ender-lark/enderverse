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
    "account_positions",
    "catalysts",
    "daily_synthesis",
    "fundstrat_bible",
    "positions",
    "position_reconciliation",
    "theses",
    "fundstrat_daily_calls",
    "fundstrat_inbox_entries",
    "heartbeat",
    "inbox_call_dates",
    "log_call_dates",
    "macro_state",
    "meridian",
    "open_opportunities",
    "parabolic_setups",
    "research_queue",
    "signal_log",
    "source_calls",
    "system_improvement_queue",
    "top_prospects",
    "uw_opportunity_signals",
    "uw_closes",
}


def _read_json(path: str | Path) -> Any:
    with Path(path).open(encoding="utf-8") as fh:
        return json.load(fh)


def _default_file_keys() -> set[str]:
    try:
        from full_build_runner import DEFAULT_FILES
    except Exception:
        return set()
    if not isinstance(DEFAULT_FILES, dict):
        return set()
    return {str(key) for key in DEFAULT_FILES}


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

    feed_paths = "\n".join(
        str(obj.get("feed_path") or "")
        for obj in objects
        if isinstance(obj, dict)
    )
    missing_default_files = sorted(
        key
        for key in _default_file_keys()
        if f"DEFAULT_FILES.{key}" not in feed_paths
    )
    if missing_default_files:
        problems.append(
            "full_build_runner.DEFAULT_FILES keys missing ownership feed_path references: "
            + ", ".join(missing_default_files)
        )
    return problems


def _self_test() -> int:
    default_refs = " ".join(
        f"full_build_runner.DEFAULT_FILES.{key}"
        for key in sorted(_default_file_keys())
    )
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
    payload["objects"][0]["feed_path"] = default_refs or "x"
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
