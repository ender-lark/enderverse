#!/usr/bin/env python3
"""Validate and summarize the Fundstrat deep-crawl target manifest."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_TARGETS = Path(__file__).resolve().parent / "fundstrat_deep_crawl_targets.json"
REQUIRED_FIELDS = {
    "id",
    "family",
    "priority",
    "cadence",
    "navigation_path",
    "capture_rule",
    "checked_behavior",
    "daily_call_eligible",
}


def read_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.is_file():
        return default
    with p.open(encoding="utf-8") as fh:
        return json.load(fh)


def validate_targets(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["target manifest must be a dict"]
    problems: list[str] = []
    if payload.get("schema_version") != 1:
        problems.append("schema_version must be 1")
    targets = payload.get("targets")
    if not isinstance(targets, list) or not targets:
        return problems + ["targets must be a non-empty list"]

    seen: set[str] = set()
    has_stock_lists = False
    has_fast_lane = False
    for idx, target in enumerate(targets):
        label = f"targets[{idx}]"
        if not isinstance(target, dict):
            problems.append(f"{label} must be a dict")
            continue
        missing = sorted(REQUIRED_FIELDS - set(target))
        for field in missing:
            problems.append(f"{label}.{field} is required")
        target_id = str(target.get("id") or "").strip()
        if not target_id:
            problems.append(f"{label}.id must be non-empty")
        elif target_id in seen:
            problems.append(f"duplicate target id: {target_id}")
        else:
            seen.add(target_id)
        if not isinstance(target.get("priority"), int) or int(target.get("priority") or 0) < 1:
            problems.append(f"{label}.priority must be a positive integer")
        if not isinstance(target.get("navigation_path"), list) or not target.get("navigation_path"):
            problems.append(f"{label}.navigation_path must be a non-empty list")
        if target.get("daily_call_eligible") not in {True, False}:
            problems.append(f"{label}.daily_call_eligible must be boolean")
        family = str(target.get("family") or "")
        if family == "Stock Lists":
            has_stock_lists = True
            if target.get("daily_call_eligible") is True:
                problems.append(f"{label} Stock Lists targets must not be daily-call eligible")
        if target.get("daily_call_eligible") is True:
            has_fast_lane = True
    if not has_stock_lists:
        problems.append("manifest must include Stock Lists targets")
    if not has_fast_lane:
        problems.append("manifest must include at least one daily-call eligible fast-lane target")
    return problems


def summarize_targets(payload: Any) -> dict[str, Any]:
    targets = payload.get("targets") if isinstance(payload, dict) else []
    targets = [target for target in targets or [] if isinstance(target, dict)]
    by_family = Counter(str(target.get("family") or "unknown") for target in targets)
    by_cadence = Counter(str(target.get("cadence") or "unknown") for target in targets)
    return {
        "targets": len(targets),
        "by_family": dict(sorted(by_family.items())),
        "by_cadence": dict(sorted(by_cadence.items())),
        "daily_call_eligible": sum(1 for target in targets if target.get("daily_call_eligible") is True),
        "baseline_diff_only": sum(1 for target in targets if target.get("daily_call_eligible") is False),
        "stock_list_targets": [
            target.get("id")
            for target in targets
            if target.get("family") == "Stock Lists"
        ],
    }


def _self_test() -> bool:
    payload = {
        "schema_version": 1,
        "targets": [
            {
                "id": "flash",
                "family": "FlashInsights",
                "priority": 1,
                "cadence": "every_run",
                "navigation_path": ["FlashInsights"],
                "capture_rule": "complete cards",
                "checked_behavior": "visible",
                "daily_call_eligible": True,
            },
            {
                "id": "sector",
                "family": "Stock Lists",
                "priority": 4,
                "cadence": "deep_crawl",
                "navigation_path": ["Stock Lists", "Sector Allocation"],
                "capture_rule": "baseline diff",
                "checked_behavior": "table visible",
                "daily_call_eligible": False,
            },
        ],
    }
    assert validate_targets(payload) == []
    assert summarize_targets(payload)["stock_list_targets"] == ["sector"]
    bad = {**payload, "targets": [{**payload["targets"][1], "daily_call_eligible": True}]}
    assert validate_targets(bad)
    print("fundstrat_deep_crawl self-test: PASS")
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate Fundstrat deep-crawl target manifest")
    parser.add_argument("--targets", default=str(DEFAULT_TARGETS))
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return 0 if _self_test() else 1

    payload = read_json(args.targets, default={})
    problems = validate_targets(payload)
    if args.validate:
        print(json.dumps({"valid": not problems, "problems": problems}, indent=2))
        return 0 if not problems else 1
    if args.summary:
        print(json.dumps({"valid": not problems, "problems": problems, "summary": summarize_targets(payload)}, indent=2))
        return 0 if not problems else 1
    parser.error("choose --validate, --summary, or --self-test")


if __name__ == "__main__":
    raise SystemExit(main())
