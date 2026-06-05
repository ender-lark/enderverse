#!/usr/bin/env python3
"""Build the cockpit heartbeat strip from repo-local readiness evidence."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from live_readiness import readiness_report


DEFAULT_OUT = Path(__file__).resolve().parent / "heartbeat.json"
DEFAULT_SUMMARY = Path(__file__).resolve().parent / "heartbeat_summary.json"
VALID_STATUS = {"ok", "stale", "down"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: str | Path, payload: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".heartbeat.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def _read_json(path: str | Path) -> Any:
    with Path(path).open(encoding="utf-8") as fh:
        return json.load(fh)


def _row(layer: str, status: str, note: str, *, last_run: str) -> dict[str, str]:
    return {
        "layer": layer,
        "status": status,
        "last_run": last_run,
        "note": note,
    }


def heartbeat_rows(report: dict[str, Any], *, generated_at: str | None = None) -> list[dict[str, str]]:
    """Readiness report -> dashboard heartbeat rows.

    Heartbeat answers "what ran and what is blocking publish"; lane_status still
    answers which individual data lanes were checked, stale, or dark.
    """
    ts = generated_at or _utc_now_iso()
    missing_required = report.get("missing_required_inputs") or []
    stale_required = report.get("stale_required_inputs") or []
    missing_minimum = report.get("missing_minimum_live_inputs") or []
    publish_problems = report.get("publish_gate_problems") or []
    dark_lanes = report.get("dark_lane_keys") or []
    dark_lane_details = report.get("dark_lane_details") or []
    required_status = "down" if missing_required else "stale" if stale_required else "ok"
    if missing_required:
        required_note = "missing: " + ", ".join(row.get("key", "") for row in missing_required)
    elif stale_required:
        required_note = "stale/unverified: " + ", ".join(row.get("key", "") for row in stale_required)
    else:
        required_note = "positions/theses convention inputs present and fresh"

    optional_note = (
        "dark lanes: " + ", ".join(str(key) for key in dark_lanes)
        if dark_lanes else "all optional lanes supplied or checked clear"
    )
    if dark_lane_details:
        fixes = [
            str(row.get("next_step") or "").rstrip(".")
            for row in dark_lane_details[:2]
            if isinstance(row, dict) and row.get("next_step")
        ]
        if fixes:
            optional_note += " | next: " + "; ".join(fixes)

    rows = [
        _row(
            "Required Inputs",
            required_status,
            required_note,
            last_run=ts,
        ),
        _row(
            "Minimum Market Data",
            "down" if missing_minimum else "ok",
            "missing: " + ", ".join(row.get("key", "") for row in missing_minimum)
            if missing_minimum else "UW price and macro caches present",
            last_run=ts,
        ),
        _row(
            "Publish Gate",
            "down" if publish_problems else "ok",
            "; ".join(str(problem) for problem in publish_problems[:2])
            if publish_problems else "publish-gate checks passed",
            last_run=ts,
        ),
        _row(
            "Optional Source Lanes",
            "stale" if dark_lanes else "ok",
            optional_note,
            last_run=ts,
        ),
        _row(
            "Daily Full Build",
            "ok" if report.get("build_ready") else "down",
            "rehearsal build can run" if report.get("build_ready") else report.get("build_problem", "build not ready"),
            last_run=ts,
        ),
    ]
    return rows


def validate_heartbeat(rows: Any) -> list[str]:
    problems: list[str] = []
    if not isinstance(rows, list):
        return ["heartbeat must be a list"]
    if not rows:
        problems.append("heartbeat must include at least one row")
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            problems.append(f"rows[{idx}] must be an object")
            continue
        layer = row.get("layer")
        if not isinstance(layer, str) or not layer.strip():
            problems.append(f"rows[{idx}].layer must be a non-empty string")
        status = row.get("status")
        if status not in VALID_STATUS:
            problems.append(f"rows[{idx}].status must be one of {sorted(VALID_STATUS)}")
        note = row.get("note")
        if note is not None and not isinstance(note, str):
            problems.append(f"rows[{idx}].note must be a string when present")
    return problems


def heartbeat_summary(rows: list[dict[str, str]], *, out: str | None = None, written: bool = False) -> dict[str, Any]:
    problems = validate_heartbeat(rows)
    counts = {status: 0 for status in sorted(VALID_STATUS)}
    for row in rows:
        status = row.get("status")
        if status in counts:
            counts[status] += 1
    return {
        "valid": not problems,
        "problems": problems,
        "out": out or "",
        "written": written,
        "rows": len(rows),
        "counts": counts,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build heartbeat.json from readiness evidence")
    parser.add_argument("--src-dir", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--validate", metavar="HEARTBEAT_JSON")
    parser.add_argument("--no-write", action="store_true", help="Print summary without writing heartbeat.json")
    args = parser.parse_args(argv)

    if args.validate:
        if not Path(args.validate).is_file():
            print(json.dumps({"valid": False, "path": args.validate, "problems": ["cache file not found"]}, indent=2))
            return 2
        rows = _read_json(args.validate)
        summary = heartbeat_summary(rows)
        print(json.dumps(summary, indent=2))
        return 0 if summary["valid"] else 2

    report = readiness_report(args.src_dir)
    rows = heartbeat_rows(report)
    summary = heartbeat_summary(rows, out=args.out, written=False)
    if summary["problems"]:
        if not args.no_write:
            _atomic_write_json(args.summary, summary)
        print(json.dumps(summary, indent=2))
        return 2
    if not args.no_write:
        _atomic_write_json(args.out, rows)
        summary["written"] = True
        _atomic_write_json(args.summary, summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
