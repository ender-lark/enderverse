#!/usr/bin/env python3
"""Report whether the current repo convention files are ready for a live build.

This command does not fetch sources and does not publish. It turns the existing
full-build evidence into an operator-facing go/no-go report.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from full_build_runner import FullBuildError, build_full_feed_from_files, convention_input_status
from publish_gate import validate_publish_gate


MINIMUM_LIVE_INPUTS = {"uw_prices", "macro"}


def _lane_rows(feed: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("key")): row
        for row in (feed.get("lane_status", {}).get("rows") or [])
        if isinstance(row, dict) and row.get("key")
    }


def _missing_input_rows(status_rows: list[dict[str, Any]], *, required: bool | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in status_rows:
        if row.get("present"):
            continue
        if required is not None and bool(row.get("required")) is not required:
            continue
        out.append(row)
    return out


def readiness_report(
    src_dir: str | Path = Path(__file__).resolve().parent,
    *,
    as_of: str | None = None,
    run_timestamp: str | None = None,
    generated_at: str | None = None,
    minimum_live_inputs: set[str] | None = None,
) -> dict[str, Any]:
    src = Path(src_dir)
    minimum_live_inputs = minimum_live_inputs or set(MINIMUM_LIVE_INPUTS)
    input_rows = convention_input_status(src)
    missing_required = _missing_input_rows(input_rows, required=True)
    missing_optional = _missing_input_rows(input_rows, required=False)
    input_by_key = {row["key"]: row for row in input_rows}
    missing_minimum_live = [
        input_by_key[key]
        for key in sorted(minimum_live_inputs)
        if key in input_by_key and not input_by_key[key].get("present")
    ]

    feed: dict[str, Any] | None = None
    build_problem = ""
    try:
        feed = build_full_feed_from_files(
            src_dir=src,
            as_of=as_of,
            run_timestamp=run_timestamp,
            generated_at=generated_at,
        )
    except (FileNotFoundError, FullBuildError, json.JSONDecodeError, ValueError) as exc:
        build_problem = str(exc)

    publish_gate_problems = validate_publish_gate(feed) if feed is not None else []
    lane_rows = _lane_rows(feed or {})
    dark_lane_keys = [
        key
        for key, row in lane_rows.items()
        if row.get("status") == "not_checked"
    ]
    stale_or_failed_lane_keys = [
        key
        for key, row in lane_rows.items()
        if row.get("status") in {"stale", "failed"}
    ]

    build_ready = feed is not None and not missing_required and not build_problem
    publish_ready = build_ready and not publish_gate_problems
    live_data_ready = not missing_minimum_live
    go_live_ready = publish_ready and live_data_ready

    next_steps: list[str] = []
    if missing_required:
        next_steps.append("Populate required convention files before any build.")
    if build_problem:
        next_steps.append("Fix the full-build error before publishing.")
    if publish_gate_problems:
        next_steps.append("Fix publish-gate problems before publishing.")
    if missing_minimum_live:
        missing = ", ".join(row["key"] for row in missing_minimum_live)
        next_steps.append(f"Populate minimum live market inputs: {missing}.")
    if dark_lane_keys:
        next_steps.append("Review dark lanes; missing optional lanes must stay visible, not checked clear.")
    if not next_steps:
        next_steps.append("Run the daily full build with --publish.")

    return {
        "go_live_ready": go_live_ready,
        "rehearsal_ready": build_ready,
        "build_ready": build_ready,
        "publish_ready": publish_ready,
        "live_data_ready": live_data_ready,
        "build_problem": build_problem,
        "publish_gate_problems": publish_gate_problems,
        "missing_required_inputs": missing_required,
        "missing_optional_inputs": missing_optional,
        "missing_minimum_live_inputs": missing_minimum_live,
        "dark_lane_keys": dark_lane_keys,
        "stale_or_failed_lane_keys": stale_or_failed_lane_keys,
        "actions": len((feed or {}).get("actions") or []),
        "research_actions": len((feed or {}).get("research_actions") or []),
        "next_steps": next_steps,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Report live readiness without publishing")
    parser.add_argument("--src-dir", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--as-of")
    parser.add_argument("--run-timestamp")
    parser.add_argument("--generated-at")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero unless go_live_ready is true")
    args = parser.parse_args(argv)

    report = readiness_report(
        args.src_dir,
        as_of=args.as_of,
        run_timestamp=args.run_timestamp,
        generated_at=args.generated_at,
    )
    print(json.dumps(report, indent=2))
    return 0 if report["go_live_ready"] or not args.strict else 2


if __name__ == "__main__":
    raise SystemExit(main())
