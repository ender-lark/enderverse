#!/usr/bin/env python3
"""Summarize which cockpit inputs are live-source capable versus local-only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import codex_routine_manifest
from full_build_runner import convention_input_status


DEFAULT_SRC = Path(__file__).resolve().parent
DEFAULT_MANIFEST = DEFAULT_SRC / "codex_routine_manifest.json"

CONNECTOR_TOKENS = (
    "connector",
    "gmail",
    "notion",
    "unusual whales",
    "api",
)
SUPPLIED_TOKENS = (
    "supplied",
    "upload",
    "export",
    "drop-folder",
    "drop folder",
    "json",
    "csv",
    "pdf",
    "text",
    "stdin",
)
REPO_EVIDENCE_TOKENS = (
    "repo-evidence",
    "existing cockpit feed",
    "repo convention",
    "publish",
    "action memory",
    "routine status",
    "github_manual",
)

ROUTINE_BY_INPUT_KEY = {
    "positions": "broker_position_intake",
    "account_positions": "broker_position_intake",
    "uw_prices": "uw_cache_refresh",
    "macro": "uw_cache_refresh",
    "fs_bible": "fundstrat_intake",
    "fs_daily": "fundstrat_intake",
    "signal_log": "signal_log_intake",
    "event_risk": "event_risk_intake",
    "synthesis": "daily_synthesis_intake",
    "research": "off_hours_research_queue",
    "catalysts": "catalyst_intake",
    "uw_opportunity": "uw_cache_refresh",
    "top_prospects": "fundstrat_intake",
    "source_calls": "fundstrat_intake",
    "inbox_call_dates": "fundstrat_intake",
    "log_call_dates": "fundstrat_intake",
    "parabolic": "uw_cache_refresh",
}

MODE_PRIORITY = ("connector_or_api", "supplied_or_export", "repo_cache_or_evidence", "repo_manual")


def _as_text(parts: list[Any]) -> str:
    return " ".join(str(part or "") for part in parts).lower()


def _routine_for_input(row: dict[str, Any], routines_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    key = str(row.get("key") or "")
    source = str(row.get("source") or "")
    for routine_id, routine in routines_by_id.items():
        if routine_id.lower() in source.lower():
            return routine
    mapped = ROUTINE_BY_INPUT_KEY.get(key)
    if mapped:
        return routines_by_id.get(mapped, {})
    return {}


def _modes_for_input(row: dict[str, Any], routine: dict[str, Any]) -> list[str]:
    commands = [
        command.get("command") or ""
        for command in routine.get("commands") or []
        if isinstance(command, dict)
    ]
    text = _as_text([
        row.get("source"),
        *(routine.get("input_boundaries") or []),
        *commands,
        routine.get("no_input_behavior"),
    ])
    modes: list[str] = []
    if any(token in text for token in CONNECTOR_TOKENS):
        modes.append("connector_or_api")
    if any(token in text for token in SUPPLIED_TOKENS):
        modes.append("supplied_or_export")
    if any(token in text for token in REPO_EVIDENCE_TOKENS):
        modes.append("repo_cache_or_evidence")
    if not modes:
        modes.append("repo_manual")
    return [mode for mode in MODE_PRIORITY if mode in modes]


def _primary_mode(modes: list[str]) -> str:
    for mode in MODE_PRIORITY:
        if mode in modes:
            return mode
    return "repo_manual"


def capability_report(
    src_dir: str | Path = DEFAULT_SRC,
    *,
    manifest_path: str | Path = DEFAULT_MANIFEST,
    input_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a non-fetching source capability report for daily build inputs."""
    src = Path(src_dir)
    manifest = codex_routine_manifest.load_manifest(manifest_path)
    problems = codex_routine_manifest.validate_manifest(manifest)
    routines = [row for row in manifest.get("routines") or [] if isinstance(row, dict)]
    routines_by_id = {str(row.get("id") or ""): row for row in routines if row.get("id")}
    if input_rows is None:
        input_rows = convention_input_status(src)

    rows: list[dict[str, Any]] = []
    for input_row in input_rows:
        if not isinstance(input_row, dict):
            continue
        routine = _routine_for_input(input_row, routines_by_id)
        modes = _modes_for_input(input_row, routine)
        rows.append({
            "key": input_row.get("key") or "",
            "required": bool(input_row.get("required")),
            "present": bool(input_row.get("present")),
            "source": input_row.get("source") or "",
            "routine_id": routine.get("id") or "",
            "routine_title": routine.get("title") or "",
            "primary_mode": _primary_mode(modes),
            "modes": modes,
        })

    by_primary = {mode: 0 for mode in MODE_PRIORITY}
    for row in rows:
        by_primary[row["primary_mode"]] = by_primary.get(row["primary_mode"], 0) + 1

    connector_keys = [row["key"] for row in rows if "connector_or_api" in row["modes"]]
    supplied_keys = [row["key"] for row in rows if "supplied_or_export" in row["modes"]]
    missing_keys = [row["key"] for row in rows if not row["present"]]
    live_capable_keys = sorted(set(connector_keys + supplied_keys))
    missing_live_capable = [
        row["key"]
        for row in rows
        if not row["present"] and ("connector_or_api" in row["modes"] or "supplied_or_export" in row["modes"])
    ]

    return {
        "valid": not problems,
        "problems": problems,
        "total_inputs": len(rows),
        "present_inputs": len(rows) - len(missing_keys),
        "missing_inputs": len(missing_keys),
        "connector_or_api_count": len(connector_keys),
        "supplied_or_export_count": len(supplied_keys),
        "live_capable_count": len(live_capable_keys),
        "missing_live_capable_count": len(missing_live_capable),
        "by_primary_mode": by_primary,
        "connector_or_api_keys": connector_keys,
        "supplied_or_export_keys": supplied_keys,
        "missing_input_keys": missing_keys,
        "missing_live_capable_keys": missing_live_capable,
        "rows": rows,
    }


def format_text(report: dict[str, Any]) -> str:
    lines = [
        f"Live source capability valid: {bool(report.get('valid'))}",
        (
            "Inputs: "
            f"present={int(report.get('present_inputs') or 0)}/"
            f"{int(report.get('total_inputs') or 0)} | "
            f"missing={int(report.get('missing_inputs') or 0)}"
        ),
        (
            "Capability: "
            f"connector_or_api={int(report.get('connector_or_api_count') or 0)} | "
            f"supplied_or_export={int(report.get('supplied_or_export_count') or 0)} | "
            f"live_capable={int(report.get('live_capable_count') or 0)} | "
            f"missing_live_capable={int(report.get('missing_live_capable_count') or 0)}"
        ),
    ]
    missing = report.get("missing_live_capable_keys") or []
    if missing:
        lines.append("Missing live-capable inputs:")
        lines.extend(f"- {key}" for key in missing)
    if report.get("problems"):
        lines.append("Problems:")
        lines.extend(f"- {problem}" for problem in report.get("problems") or [])
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Report live-source capability without fetching")
    parser.add_argument("--src-dir", default=str(DEFAULT_SRC))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--format", choices=["json", "text"], default="json")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when manifest/source capability is invalid")
    args = parser.parse_args(argv)

    report = capability_report(args.src_dir, manifest_path=args.manifest)
    if args.format == "text":
        print(format_text(report))
    else:
        print(json.dumps(report, indent=2))
    return 0 if report["valid"] or not args.strict else 2


if __name__ == "__main__":
    raise SystemExit(main())
