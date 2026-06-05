#!/usr/bin/env python3
"""Summarize which cockpit inputs are live-source capable versus local-only."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

import codex_routine_manifest
from full_build_runner import convention_input_status


DEFAULT_SRC = Path(__file__).resolve().parent
DEFAULT_MANIFEST = DEFAULT_SRC / "codex_routine_manifest.json"
DEFAULT_CONFIG = DEFAULT_SRC / "live_source_config.json"
DEFAULT_CONNECTOR_PROOF_MAX_AGE_HOURS = 36

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
LIVE_CONFIG_REQUIREMENTS = [
    {
        "key": "uw_api_key",
        "label": "Unusual Whales live access",
        "kind": "env_or_connector",
        "env_var": "UW_API_KEY",
        "connector_key": "unusual_whales",
        "connector_proof_max_age_hours": DEFAULT_CONNECTOR_PROOF_MAX_AGE_HOURS,
        "affected_inputs": ["uw_opportunity", "parabolic"],
        "impact": (
            "Live UW opportunity/parabolic fetches cannot run; existing UW caches "
            "may still render but must be treated as cached evidence."
        ),
        "next_step": "Set UW_API_KEY in the automation environment or refresh the Codex app connector proof before live UW cache runs.",
    },
]


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


def _read_json(path: str | Path) -> Any:
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _connector_row(config: dict[str, Any], connector_key: str) -> dict[str, Any]:
    connectors = config.get("connectors") if isinstance(config, dict) else {}
    connector = connectors.get(connector_key) if isinstance(connectors, dict) else {}
    if not isinstance(connector, dict):
        return {}
    return connector


def _connector_configured(config: dict[str, Any], connector_key: str) -> bool:
    connector = _connector_row(config, connector_key)
    return bool(connector.get("available") or connector.get("configured"))


def _connector_verified_at(config: dict[str, Any], connector: dict[str, Any]) -> datetime | None:
    return _parse_dt(connector.get("verified_at") or config.get("verified_at"))


def _connector_proof_fresh(
    config: dict[str, Any],
    connector: dict[str, Any],
    *,
    max_age_hours: int,
    now: datetime | None,
) -> tuple[bool, str, float | None]:
    verified_at = _connector_verified_at(config, connector)
    if verified_at is None:
        return False, "", None
    current = now or datetime.now(timezone.utc)
    current = current if current.tzinfo else current.replace(tzinfo=timezone.utc)
    age_hours = (current.astimezone(timezone.utc) - verified_at.astimezone(timezone.utc)).total_seconds() / 3600
    return age_hours <= max_age_hours, verified_at.isoformat(), round(age_hours, 2)


def live_config_report(
    environ: dict[str, str] | None = None,
    *,
    config_path: str | Path | None = DEFAULT_CONFIG,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    """Return non-secret live-fetch configuration status."""
    env = os.environ if environ is None else environ
    config = _read_json(config_path) if config_path else {}
    parsed_now = _parse_dt(now) if isinstance(now, str) else now
    rows: list[dict[str, Any]] = []
    for requirement in LIVE_CONFIG_REQUIREMENTS:
        env_var = str(requirement.get("env_var") or "")
        connector_key = str(requirement.get("connector_key") or "")
        max_age_hours = int(requirement.get("connector_proof_max_age_hours") or DEFAULT_CONNECTOR_PROOF_MAX_AGE_HOURS)
        env_configured = bool(str(env.get(env_var) or "").strip()) if env_var else False
        connector = _connector_row(config, connector_key) if connector_key else {}
        connector_available = _connector_configured(config, connector_key) if connector_key else False
        proof_fresh, verified_at, proof_age_hours = _connector_proof_fresh(
            config,
            connector,
            max_age_hours=max_age_hours,
            now=parsed_now,
        ) if connector_available else (False, "", None)
        connector_configured = connector_available and proof_fresh
        configured = env_configured or connector_configured
        rows.append({
            **requirement,
            "configured": configured,
            "present": configured,
            "env_configured": env_configured,
            "connector_configured": connector_configured,
            "connector_available": connector_available,
            "connector_proof_fresh": proof_fresh,
            "connector_verified_at": verified_at,
            "connector_proof_age_hours": proof_age_hours,
            "connector_proof_max_age_hours": max_age_hours,
        })
    missing = [row for row in rows if not row.get("configured")]
    stale = [
        row for row in rows
        if row.get("connector_available") and not row.get("connector_proof_fresh") and not row.get("env_configured")
    ]
    return {
        "valid": True,
        "configured": not missing,
        "total_count": len(rows),
        "configured_count": len(rows) - len(missing),
        "missing_count": len(missing),
        "missing_keys": [row.get("key") for row in missing if row.get("key")],
        "stale_count": len(stale),
        "stale_keys": [row.get("key") for row in stale if row.get("key")],
        "rows": rows,
        "missing": missing,
        "stale": stale,
        "config_path": str(config_path or ""),
    }


def capability_report(
    src_dir: str | Path = DEFAULT_SRC,
    *,
    manifest_path: str | Path = DEFAULT_MANIFEST,
    config_path: str | Path | None = None,
    input_rows: list[dict[str, Any]] | None = None,
    environ: dict[str, str] | None = None,
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
            "status": input_row.get("status") or "",
            "candidate_paths": input_row.get("candidate_paths") or [],
            "missing_behavior": input_row.get("missing_behavior") or "",
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
        "live_source_config": live_config_report(
            environ,
            config_path=config_path if config_path is not None else src / "live_source_config.json",
        ),
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
        (
            "Live source config: "
            f"configured={int((report.get('live_source_config') or {}).get('configured_count') or 0)}/"
            f"{int((report.get('live_source_config') or {}).get('total_count') or 0)} | "
            f"missing={int((report.get('live_source_config') or {}).get('missing_count') or 0)} | "
            f"stale={int((report.get('live_source_config') or {}).get('stale_count') or 0)}"
        ),
    ]
    lines.extend(format_missing_live_capable(report))
    lines.extend(format_missing_live_config(report))
    if report.get("problems"):
        lines.append("Problems:")
        lines.extend(f"- {problem}" for problem in report.get("problems") or [])
    return "\n".join(lines)


def format_missing_live_capable(report: dict[str, Any]) -> list[str]:
    """Return human-readable detail lines for missing live-capable inputs."""
    missing = report.get("missing_live_capable_keys") or []
    if not missing:
        return []
    lines = ["Missing live-capable inputs:"]
    rows_by_key = {
        str(row.get("key") or ""): row
        for row in report.get("rows") or []
        if isinstance(row, dict)
    }
    for key in missing:
        row = rows_by_key.get(str(key), {})
        source = str(row.get("source") or "")
        owner = str(row.get("routine_title") or row.get("routine_id") or source or "unowned")
        bits = [
            owner,
            str(row.get("primary_mode") or ""),
        ]
        if source and source != owner:
            bits.append(source)
        lines.append(f"- {key}: " + " | ".join(bit for bit in bits if bit))
        missing_behavior = str(row.get("missing_behavior") or "")
        if missing_behavior:
            lines.append(f"  missing behavior: {missing_behavior}")
        candidate_paths = [
            str(path)
            for path in (row.get("candidate_paths") or [])[:3]
            if path
        ]
        if candidate_paths:
            lines.append("  expected path: " + ", ".join(candidate_paths))
    return lines


def format_missing_live_config(report: dict[str, Any]) -> list[str]:
    """Return human-readable lines for missing live-fetch configuration."""
    config = report.get("live_source_config") or {}
    missing = [
        row for row in config.get("missing") or []
        if isinstance(row, dict)
    ]
    if not missing:
        return []
    lines = ["Missing live-source configuration:"]
    for row in missing:
        label = str(row.get("label") or row.get("key") or "Live source")
        env_var = str(row.get("env_var") or "")
        affected = [
            str(key)
            for key in row.get("affected_inputs") or []
            if key
        ]
        suffix = f" ({', '.join(affected)})" if affected else ""
        if env_var:
            connector_key = str(row.get("connector_key") or "")
            if row.get("connector_available") and not row.get("connector_proof_fresh"):
                age = row.get("connector_proof_age_hours")
                max_age = row.get("connector_proof_max_age_hours")
                connector_note = f" and {connector_key} connector proof is stale ({age}h old; max {max_age}h)"
            else:
                connector_note = f" and {connector_key} connector proof is absent" if connector_key else ""
            lines.append(f"- {label}: {env_var} is not set{connector_note}{suffix}")
        else:
            lines.append(f"- {label}: not configured{suffix}")
        impact = str(row.get("impact") or "")
        if impact:
            lines.append(f"  impact: {impact}")
        next_step = str(row.get("next_step") or "")
        if next_step:
            lines.append(f"  next step: {next_step}")
    return lines


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
