#!/usr/bin/env python3
"""Validate and summarize Codex-owned Investing OS routine definitions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_MANIFEST_PATH = Path(__file__).resolve().parent / "codex_routine_manifest.json"
ROOT = Path(__file__).resolve().parents[1]

REQUIRED_ROUTINE_FIELDS = {
    "id",
    "title",
    "status",
    "cadence",
    "doc",
    "separation_group",
    "input_boundaries",
    "owns",
    "commands",
    "verification",
    "no_input_behavior",
}
REQUIRED_COMMAND_FIELDS = {"id", "command"}
REQUIRED_CONVENTION_INPUT_FIELDS = {"key", "paths", "required", "source", "missing_behavior"}
EXPECTED_ROUTINES = {
    "fundstrat_intake",
    "catalyst_intake",
    "broker_position_intake",
    "uw_cache_refresh",
    "daily_synthesis_intake",
    "signal_log_intake",
    "event_risk_intake",
    "daily_full_build",
    "off_hours_research_queue",
}
VALID_STATUSES = {"active", "active_safe_intake", "queued", "paused", "retired"}
VALID_SEPARATION_GROUPS = {"source_intake", "market_data_refresh", "feed_build_publish"}


def load_manifest(path: str | Path = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as fh:
        return json.load(fh)


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _non_empty_string_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(_non_empty_string(v) for v in value)


def _full_build_default_keys() -> set[str]:
    try:
        from full_build_runner import DEFAULT_FILES
    except Exception:
        return set()
    if not isinstance(DEFAULT_FILES, dict):
        return set()
    return {str(key) for key in DEFAULT_FILES}


def _validate_daily_convention_inputs(daily: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    inputs = daily.get("convention_inputs")
    if not isinstance(inputs, list) or not inputs:
        return ["daily_full_build.convention_inputs must be a non-empty list"]

    seen: set[str] = set()
    keys: set[str] = set()
    for idx, row in enumerate(inputs):
        label = f"daily_full_build.convention_inputs[{idx}]"
        if not isinstance(row, dict):
            problems.append(f"{label} must be an object")
            continue
        for field in sorted(REQUIRED_CONVENTION_INPUT_FIELDS):
            if field not in row:
                problems.append(f"{label}.{field} is required")
        key = str(row.get("key") or "").strip()
        if not key:
            problems.append(f"{label}.key must be non-empty")
        elif key in seen:
            problems.append(f"duplicate daily_full_build convention input key: {key}")
        else:
            seen.add(key)
            keys.add(key)
        if "paths" in row and not _non_empty_string_list(row.get("paths")):
            problems.append(f"{label}.paths must be a non-empty string list")
        if "required" in row and not isinstance(row.get("required"), bool):
            problems.append(f"{label}.required must be a boolean")
        if "source" in row and not _non_empty_string(row.get("source")):
            problems.append(f"{label}.source must be a non-empty string")
        missing_behavior = str(row.get("missing_behavior") or "").lower()
        if missing_behavior and not any(
            token in missing_behavior
            for token in ("not checked", "dark lane", "dark lanes", "build fail", "build failure", "required")
        ):
            problems.append(f"{label}.missing_behavior must preserve required/not-checked/dark-lane behavior")

    expected = _full_build_default_keys()
    missing = sorted(expected - keys)
    if missing:
        problems.append(
            "daily_full_build.convention_inputs missing full_build_runner.DEFAULT_FILES keys: "
            + ", ".join(missing)
        )
    extra = sorted(keys - expected)
    if expected and extra:
        problems.append(
            "daily_full_build.convention_inputs unknown keys: "
            + ", ".join(extra)
        )
    return problems


def validate_manifest(manifest: dict[str, Any], *, root: Path = ROOT) -> list[str]:
    problems: list[str] = []
    if not isinstance(manifest, dict):
        return ["top-level must be an object"]
    if manifest.get("schema_version") != 1:
        problems.append("schema_version must be 1")
    routines = manifest.get("routines")
    if not isinstance(routines, list) or not routines:
        return problems + ["routines must be a non-empty list"]

    seen_ids: set[str] = set()
    owned_outputs: dict[str, str] = {}
    routine_ids: set[str] = set()

    for idx, routine in enumerate(routines):
        label = f"routines[{idx}]"
        if not isinstance(routine, dict):
            problems.append(f"{label} must be an object")
            continue
        routine_id = str(routine.get("id") or "").strip()
        if routine_id:
            label = routine_id
            routine_ids.add(routine_id)
            if routine_id in seen_ids:
                problems.append(f"duplicate routine id: {routine_id}")
            seen_ids.add(routine_id)
        else:
            problems.append(f"{label}.id must be non-empty")

        for field in sorted(REQUIRED_ROUTINE_FIELDS):
            if field not in routine:
                problems.append(f"{label}.{field} is required")

        for field in ["title", "status", "cadence", "doc", "separation_group", "verification", "no_input_behavior"]:
            if field in routine and not _non_empty_string(routine[field]):
                problems.append(f"{label}.{field} must be a non-empty string")

        if routine.get("status") in {"", None}:
            pass
        elif routine.get("status") not in VALID_STATUSES:
            problems.append(f"{label}.status has unknown value {routine.get('status')!r}")
        if routine.get("separation_group") in {"", None}:
            pass
        elif routine.get("separation_group") not in VALID_SEPARATION_GROUPS:
            problems.append(f"{label}.separation_group has unknown value {routine.get('separation_group')!r}")

        doc = routine.get("doc")
        if _non_empty_string(doc) and not (root / doc).exists():
            problems.append(f"{label}.doc does not exist: {doc}")

        for list_field in ["input_boundaries", "owns"]:
            if list_field in routine and not _non_empty_string_list(routine[list_field]):
                problems.append(f"{label}.{list_field} must be a non-empty string list")

        for output in routine.get("owns") or []:
            if not _non_empty_string(output):
                continue
            prior = owned_outputs.get(output)
            if prior:
                problems.append(f"{output} is owned by both {prior} and {routine_id}")
            else:
                owned_outputs[output] = routine_id

        commands = routine.get("commands")
        if not isinstance(commands, list) or not commands:
            problems.append(f"{label}.commands must be a non-empty list")
        else:
            command_ids: set[str] = set()
            for cmd_idx, command in enumerate(commands):
                cmd_label = f"{label}.commands[{cmd_idx}]"
                if not isinstance(command, dict):
                    problems.append(f"{cmd_label} must be an object")
                    continue
                for field in sorted(REQUIRED_COMMAND_FIELDS):
                    if not _non_empty_string(command.get(field)):
                        problems.append(f"{cmd_label}.{field} must be a non-empty string")
                cmd_id = str(command.get("id") or "")
                if cmd_id in command_ids:
                    problems.append(f"duplicate command id in {label}: {cmd_id}")
                command_ids.add(cmd_id)

        no_input = str(routine.get("no_input_behavior") or "").lower()
        if no_input and ("not checked" not in no_input and "dark lane" not in no_input and "dark lanes" not in no_input):
            problems.append(f"{label}.no_input_behavior must preserve not-checked/dark-lane honesty")

    missing = sorted(EXPECTED_ROUTINES - routine_ids)
    if missing:
        problems.append(f"missing expected routines: {', '.join(missing)}")

    source_routines = {
        rid
        for rid, routine in ((r.get("id"), r) for r in routines if isinstance(r, dict))
        if routine.get("separation_group") in {"source_intake", "market_data_refresh"}
    }
    daily = next((r for r in routines if isinstance(r, dict) and r.get("id") == "daily_full_build"), None)
    if daily:
        daily_text = " ".join([daily.get("verification", ""), *(cmd.get("command", "") for cmd in daily.get("commands", []) if isinstance(cmd, dict))])
        for source_id in sorted(source_routines):
            if source_id in daily_text:
                problems.append(f"daily_full_build command text must not run source routine {source_id}")
        problems.extend(_validate_daily_convention_inputs(daily))

    return problems


def summary(manifest: dict[str, Any]) -> dict[str, Any]:
    routines = [r for r in manifest.get("routines", []) if isinstance(r, dict)]
    daily = next((r for r in routines if r.get("id") == "daily_full_build"), {})
    return {
        "routines": len(routines),
        "active": sum(1 for r in routines if str(r.get("status", "")).startswith("active")),
        "by_group": {
            group: sum(1 for r in routines if r.get("separation_group") == group)
            for group in sorted(VALID_SEPARATION_GROUPS)
        },
        "daily_convention_inputs": len(daily.get("convention_inputs") or []),
        "routine_ids": [r.get("id") for r in routines],
    }


def _self_test() -> bool:
    convention_inputs = [
        {
            "key": key,
            "paths": [f"src/{key}.json"],
            "required": key in {"positions", "theses"},
            "source": "test",
            "missing_behavior": "Build failure if required; otherwise report source as not checked.",
        }
        for key in sorted(_full_build_default_keys())
    ]
    routine = {
        "id": "fundstrat_intake",
        "title": "Fundstrat",
        "status": "active",
        "cadence": "daily",
        "doc": "src/codex_routines/fundstrat_intake.md",
        "separation_group": "source_intake",
        "input_boundaries": ["full-body email"],
        "owns": ["src/fundstrat_daily_calls.json"],
        "commands": [{"id": "run", "command": "python src/fundstrat_email_intake.py --validate src"}],
        "verification": "python -m pytest src/test_fundstrat_email_intake.py -q",
        "no_input_behavior": "Report Fundstrat as not checked.",
    }
    manifest = {
        "schema_version": 1,
        "routines": [
            routine,
            {**routine, "id": "catalyst_intake", "doc": "src/codex_routines/catalyst_intake.md", "owns": ["src/catalysts.json"]},
            {**routine, "id": "broker_position_intake", "doc": "src/codex_routines/broker_position_intake.md", "owns": ["src/positions.json"]},
            {**routine, "id": "uw_cache_refresh", "doc": "src/codex_routines/uw_cache_refresh.md", "separation_group": "market_data_refresh", "owns": ["src/uw_opportunity_signals.json"]},
            {**routine, "id": "daily_synthesis_intake", "doc": "src/codex_routines/daily_synthesis.md", "owns": ["src/daily_synthesis.json"]},
            {**routine, "id": "signal_log_intake", "doc": "src/codex_routines/signal_log.md", "owns": ["src/signal_log.json"]},
            {**routine, "id": "event_risk_intake", "doc": "src/codex_routines/event_risk.md", "owns": ["src/event_risks.json"]},
            {**routine, "id": "daily_full_build", "doc": "src/codex_routines/daily_full_build.md", "separation_group": "feed_build_publish", "owns": ["src/latest_cockpit_feed.json"], "convention_inputs": convention_inputs},
            {**routine, "id": "off_hours_research_queue", "doc": "src/codex_routines/off_hours_research.md", "owns": ["src/research_queue.json"]},
        ],
    }
    assert validate_manifest(manifest) == []
    bad = {"schema_version": 1, "routines": [{**routine, "no_input_behavior": "All clear."}]}
    assert validate_manifest(bad)
    print("codex_routine_manifest self-test: PASS")
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate Codex routine manifest")
    parser.add_argument("--path", default=str(DEFAULT_MANIFEST_PATH))
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--list", action="store_true", help="print routine ids and commands")
    args = parser.parse_args(argv)

    if args.self_test:
        return 0 if _self_test() else 1

    manifest = load_manifest(args.path)
    problems = validate_manifest(manifest)
    if problems:
        print(json.dumps({"valid": False, "problems": problems}, indent=2))
        return 2

    if args.list:
        for routine in manifest["routines"]:
            print(f"{routine['id']} [{routine['separation_group']}]")
            for command in routine["commands"]:
                print(f"  {command['id']}: {command['command']}")
        return 0

    print(json.dumps({"valid": True, **summary(manifest)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
