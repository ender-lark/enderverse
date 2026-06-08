#!/usr/bin/env python3
"""Report whether the Investing OS daily cloud routine can operate unattended."""
from __future__ import annotations

import argparse
import json
import os
import tomllib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import codex_routine_manifest
import cloud_routine_receipts
import live_status as live_status_mod
import live_source_capability


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = ROOT / "src"
DEFAULT_AUTOMATION_NAME = "Investing OS Daily Cloud Refresh"
DEFAULT_AUTOMATION_ID = "investing-os-daily-cloud-refresh"
DEFAULT_AUTOMATION_PROOF = "cloud_automation_status.json"
DEFAULT_RECEIPT_PROOF = "cloud_routine_receipts.json"
DRILL_COMMAND = "python src/cloud_routine_drill.py --format text --strict"
MANUAL_RUN_COMMAND = "python src/cloud_routine_manual_run.py --format text --strict"
DEFAULT_EXPECTED_AUTOMATIONS = [
    {
        "automation_id": "investing-os-pre-market-source-intake",
        "automation_name": "Investing OS Pre-Market Source Intake",
        "role": "pre_market_source_intake",
        "schedule": "market weekdays 8:10 AM ET",
        "days": [0, 1, 2, 3, 4],
        "hour": 8,
        "minute": 10,
    },
    {
        "automation_id": "investing-os-fundstrat-pre-market-safety-sweep",
        "automation_name": "Investing OS Fundstrat Pre-Market Safety Sweep",
        "role": "fundstrat_pre_market_safety_sweep",
        "schedule": "market weekdays 7:45 AM ET",
        "days": [0, 1, 2, 3, 4],
        "hour": 7,
        "minute": 45,
        "expected_since": "2026-06-07T00:00:00-04:00",
    },
    {
        "automation_id": "investing-os-morning-scan",
        "automation_name": "Investing OS Morning Scan",
        "role": "morning_scan",
        "schedule": "market weekdays 8:35 AM ET",
        "days": [0, 1, 2, 3, 4],
        "hour": 8,
        "minute": 35,
    },
    {
        "automation_id": "investing-os-early-cockpit-build",
        "automation_name": "Investing OS Early Cockpit Build",
        "role": "early_cockpit_build",
        "schedule": "market weekdays 8:50 AM ET",
        "days": [0, 1, 2, 3, 4],
        "hour": 8,
        "minute": 50,
        "expected_since": "2026-06-08T00:00:00-04:00",
    },
    {
        "automation_id": "investing-os-daily-synthesis",
        "automation_name": "Investing OS Daily Synthesis",
        "role": "daily_synthesis",
        "schedule": "market weekdays 9:30 AM ET",
        "days": [0, 1, 2, 3, 4],
        "hour": 9,
        "minute": 30,
    },
    {
        "automation_id": "investing-os-uw-opportunity-cache",
        "automation_name": "Investing OS UW Opportunity Cache",
        "role": "uw_opportunity_cache",
        "schedule": "market weekdays 10:00 AM ET",
        "days": [0, 1, 2, 3, 4],
        "hour": 10,
        "minute": 0,
    },
    {
        "automation_id": "investing-os-parabolic-cache",
        "automation_name": "Investing OS Parabolic Cache",
        "role": "parabolic_cache",
        "schedule": "market weekdays 10:05 AM ET",
        "days": [0, 1, 2, 3, 4],
        "hour": 10,
        "minute": 5,
    },
    {
        "automation_id": "investing-os-full-cockpit-build",
        "automation_name": "Investing OS Full Cockpit Build",
        "role": "full_cockpit_build",
        "schedule": "market weekdays 10:30 AM ET",
        "days": [0, 1, 2, 3, 4],
        "hour": 10,
        "minute": 30,
    },
    {
        "automation_id": "investing-os-post-close-refresh",
        "automation_name": "Investing OS Post-Close Refresh",
        "role": "post_close_refresh",
        "schedule": "market weekdays 4:30 PM ET",
        "days": [0, 1, 2, 3, 4],
        "hour": 16,
        "minute": 30,
    },
    {
        "automation_id": "investing-os-fundstrat-after-hours-catch-up",
        "automation_name": "Investing OS Fundstrat After-Hours Catch-Up",
        "role": "fundstrat_after_hours_catchup",
        "schedule": "market weekdays 7:00 PM ET",
        "days": [0, 1, 2, 3, 4],
        "hour": 19,
        "minute": 0,
        "expected_since": "2026-06-07T00:00:00-04:00",
    },
    {
        "automation_id": "investing-os-off-hours-worker",
        "automation_name": "Investing OS Off-Hours Worker",
        "role": "off_hours_worker",
        "schedule": "daily 1:45 AM ET",
        "days": [0, 1, 2, 3, 4, 5, 6],
        "hour": 1,
        "minute": 45,
    },
    {
        "automation_id": "investing-os-deep-synthesis",
        "automation_name": "Investing OS Deep Synthesis",
        "role": "deep_synthesis",
        "schedule": "Sunday 1:00 PM ET",
        "days": [6],
        "hour": 13,
        "minute": 0,
    },
    {
        "automation_id": "investing-os-weekly-pilot-run",
        "automation_name": "Investing OS Weekly Pilot Run",
        "role": "weekly_pilot_run",
        "schedule": "Sunday 6:00 PM ET",
        "days": [6],
        "hour": 18,
        "minute": 0,
    },
]
ET = ZoneInfo("America/New_York")


def _automation_dirs(base: Path) -> list[Path]:
    if not base.exists():
        return []
    return [p for p in base.rglob("automation.toml") if p.is_file()]


def _toml_text_has_active_status(text: str) -> bool:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("status") and "ACTIVE" in stripped.upper():
            return True
    return False


def _status_is_active(value: Any) -> bool:
    return str(value or "").strip().upper() == "ACTIVE"


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=ET)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=ET)


def _proof_metadata(proof_path: str | Path | None) -> dict[str, Any]:
    if proof_path is None:
        return {}
    path = Path(proof_path)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _proof_rows(proof_path: str | Path | None) -> list[dict[str, Any]]:
    if proof_path is None:
        return []
    path = Path(proof_path)
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [{
            "path": str(path),
            "active": False,
            "evidence_type": "repo_proof",
            "problem": str(exc),
        }]
    if not isinstance(payload, dict):
        return [{
            "path": str(path),
            "active": False,
            "evidence_type": "repo_proof",
            "problem": "proof file must be a JSON object",
        }]
    raw_rows = payload.get("routines") if isinstance(payload.get("routines"), list) else [payload]
    rows: list[dict[str, Any]] = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        row["path"] = str(path)
        row["active"] = _status_is_active(row.get("status"))
        row["evidence_type"] = "repo_proof"
        rows.append(row)
    return rows


def _proof_superseded_rows(proof_path: str | Path | None) -> list[dict[str, Any]]:
    payload = _proof_metadata(proof_path)
    raw_rows = payload.get("superseded") if isinstance(payload.get("superseded"), list) else []
    rows: list[dict[str, Any]] = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        row["active"] = _status_is_active(row.get("status"))
        row["evidence_type"] = "repo_proof"
        row["path"] = str(proof_path or "")
        rows.append(row)
    return rows


def _scheduled_at(row: dict[str, Any], day: datetime) -> datetime:
    return datetime(
        day.year,
        day.month,
        day.day,
        int(row.get("hour") or 0),
        int(row.get("minute") or 0),
        tzinfo=ET,
    )


def _next_run_after(row: dict[str, Any], after: datetime) -> datetime | None:
    days = set(int(day) for day in row.get("days") or [])
    if not days:
        return None
    cursor = after.astimezone(ET)
    for offset in range(0, 14):
        candidate_day = cursor + timedelta(days=offset)
        if candidate_day.weekday() not in days:
            continue
        candidate = _scheduled_at(row, candidate_day)
        if candidate > cursor:
            return candidate
    return None


def _last_run_between(row: dict[str, Any], start: datetime, end: datetime) -> datetime | None:
    days = set(int(day) for day in row.get("days") or [])
    if not days:
        return None
    start_et = start.astimezone(ET)
    end_et = end.astimezone(ET)
    latest: datetime | None = None
    for offset in range(0, 14):
        candidate_day = start_et + timedelta(days=offset)
        if candidate_day.date() > end_et.date():
            break
        if candidate_day.weekday() not in days:
            continue
        candidate = _scheduled_at(row, candidate_day)
        if start_et < candidate <= end_et:
            latest = candidate
    return latest


def _automation_matches_expected(row: dict[str, Any], expected: dict[str, Any]) -> bool:
    recorded_name = str(row.get("automation_name") or row.get("name") or "")
    recorded_id = str(row.get("automation_id") or row.get("id") or "")
    automation_name = str(expected.get("automation_name") or "")
    automation_id = str(expected.get("automation_id") or "")
    name_matches = bool(recorded_name) and recorded_name.lower() == automation_name.lower()
    id_matches = bool(recorded_id) and recorded_id.lower() == automation_id.lower()
    return name_matches or id_matches


def _toml_text_matches(row: dict[str, Any], text: str) -> bool:
    recorded_name = str(row.get("automation_name") or row.get("name") or "")
    recorded_id = str(row.get("automation_id") or row.get("id") or "")
    lowered = text.lower()
    return (
        bool(recorded_id) and recorded_id.lower() in lowered
    ) or (
        bool(recorded_name) and recorded_name.lower() in lowered
    )


def _toml_prompt_protocol(path: Path, text: str, routine_id: str) -> dict[str, Any]:
    try:
        payload = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return {
            "path": str(path),
            "routine_id": routine_id,
            "ok": False,
            "problem": f"automation TOML parse failed: {exc}",
        }
    prompt = str(payload.get("prompt") or "")
    has_runner = "cloud_routine_runner.py" in prompt and routine_id in prompt
    has_receipt = "cloud_routine_receipts.py" in prompt and routine_id in prompt
    has_final_status = "success" in prompt.lower() and "failed" in prompt.lower()
    has_scheduled_source = "--run-source scheduled" in prompt
    lowered = prompt.lower()
    has_writeback = "commit and push" in lowered and "push fails" in lowered
    has_safe_commit_helper = "cloud_routine_commit.py" in prompt
    has_source_honesty = any(
        token in lowered
        for token in (
            "dark/not_checked",
            "checked clear",
            "do not invent",
            "fabricate",
            "manufactur",
            "missing data",
            "source gap",
            "connector or data pulls fail",
            "do not scan the outside world",
        )
    )
    missing_parts = []
    if not ((has_runner or has_receipt) and has_final_status and has_scheduled_source):
        missing_parts.append("routine-specific scheduled started/final receipt protocol")
    if not has_writeback:
        missing_parts.append("commit/push write-back protocol")
    if not has_safe_commit_helper:
        missing_parts.append("safe routine-owned commit helper")
    if not has_source_honesty:
        missing_parts.append("missing-source honesty guard")
    ok = not missing_parts
    problem = "" if ok else "prompt missing: " + ", ".join(missing_parts)
    return {
        "path": str(path),
        "routine_id": routine_id,
        "ok": ok,
        "has_runner": has_runner,
        "has_receipt_command": has_receipt,
        "has_final_status": has_final_status,
        "has_scheduled_source": has_scheduled_source,
        "has_writeback": has_writeback,
        "has_safe_commit_helper": has_safe_commit_helper,
        "has_source_honesty": has_source_honesty,
        "problem": problem,
    }


def _prompt_protocol_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    checked: list[dict[str, Any]] = []
    for row in rows:
        for match in row.get("matches") or []:
            if not isinstance(match, dict):
                continue
            protocol = match.get("prompt_protocol")
            if isinstance(protocol, dict):
                checked.append({
                    "routine_id": row.get("automation_id") or "",
                    "routine_name": row.get("automation_name") or "",
                    **protocol,
                })
    missing = [row for row in checked if not row.get("ok")]
    return {
        "checked_count": len(checked),
        "ok_count": len(checked) - len(missing),
        "missing_count": len(missing),
        "rows": checked,
        "missing": missing,
        "ready": not missing,
    }


def _automation_summary(
    *,
    automations_dir: str | Path | None = None,
    automation_name: str = DEFAULT_AUTOMATION_NAME,
    automation_id: str = DEFAULT_AUTOMATION_ID,
    automation_proof: str | Path | None = None,
    expected_automations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if automations_dir is None:
        home = os.environ.get("CODEX_HOME")
        base = Path(home) / "automations" if home else Path.home() / ".codex" / "automations"
    else:
        base = Path(automations_dir)

    expected = expected_automations or [{
        "automation_id": automation_id,
        "automation_name": automation_name,
        "role": "daily_cloud_refresh",
        "schedule": "",
    }]
    all_matches: list[dict[str, Any]] = []
    proof_rows = _proof_rows(automation_proof)
    superseded_rows = _proof_superseded_rows(automation_proof)
    routine_rows: list[dict[str, Any]] = []
    local_texts: list[tuple[Path, str]] = []
    for path in _automation_dirs(base):
        text = path.read_text(encoding="utf-8", errors="replace")
        local_texts.append((path, text))

    for expected_row in expected:
        matches: list[dict[str, Any]] = []
        expected_name = str(expected_row.get("automation_name") or "")
        for path, text in local_texts:
            if expected_name and expected_name.lower() in text.lower():
                matches.append({
                    "path": str(path),
                    "active": _toml_text_has_active_status(text),
                    "evidence_type": "local_toml",
                    "prompt_protocol": _toml_prompt_protocol(
                        path,
                        text,
                        str(expected_row.get("automation_id") or ""),
                    ),
                })
        matches.extend(row for row in proof_rows if _automation_matches_expected(row, expected_row))
        all_matches.extend(matches)
        routine_rows.append({
            "automation_id": expected_row.get("automation_id") or "",
            "automation_name": expected_row.get("automation_name") or "",
            "role": expected_row.get("role") or "",
            "schedule": expected_row.get("schedule") or "",
            "installed": bool(matches),
            "active": any(row.get("active") for row in matches),
            "matches": matches,
        })

    superseded_matches: list[dict[str, Any]] = []
    for superseded in superseded_rows:
        matches: list[dict[str, Any]] = []
        for path, text in local_texts:
            if not _toml_text_matches(superseded, text):
                continue
            matches.append({
                "automation_id": superseded.get("automation_id") or "",
                "automation_name": superseded.get("automation_name") or "",
                "role": superseded.get("role") or "",
                "path": str(path),
                "active": _toml_text_has_active_status(text),
                "evidence_type": "local_toml",
            })
        if not matches:
            matches.append(superseded)
        superseded_matches.extend(matches)

    missing = [row for row in routine_rows if not row["installed"]]
    inactive = [row for row in routine_rows if row["installed"] and not row["active"]]
    active_superseded = [row for row in superseded_matches if row.get("active")]
    prompt_protocol = _prompt_protocol_summary(routine_rows)

    return {
        "automation_id": automation_id,
        "automation_name": automation_name,
        "automations_dir": str(base) if str(base) else "",
        "automation_proof": str(automation_proof or ""),
        "expected_count": len(routine_rows),
        "installed_count": len(routine_rows) - len(missing),
        "active_count": len([row for row in routine_rows if row["active"]]),
        "installed": not missing,
        "active": not missing and not inactive and not active_superseded,
        "missing": missing,
        "inactive": inactive,
        "superseded": superseded_matches,
        "active_superseded": active_superseded,
        "active_superseded_count": len(active_superseded),
        "prompt_protocol": prompt_protocol,
        "routines": routine_rows,
        "matches": all_matches,
    }


def _manifest_summary(src_dir: Path) -> dict[str, Any]:
    manifest_path = src_dir / "codex_routine_manifest.json"
    try:
        manifest = codex_routine_manifest.load_manifest(manifest_path)
        problems = codex_routine_manifest.validate_manifest(manifest, root=ROOT)
        summary = codex_routine_manifest.summary(manifest)
    except Exception as exc:
        return {"valid": False, "problems": [str(exc)], "summary": {}}
    return {"valid": not problems, "problems": problems, "summary": summary}


def _receipt_summary(path: str | Path, expected_automations: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        payload = cloud_routine_receipts.load_receipts(path)
        problems = cloud_routine_receipts.validate_receipts(payload)
        summary = cloud_routine_receipts.summarize_receipts(
            payload,
            expected_automations=expected_automations,
        )
    except Exception as exc:
        return {
            "valid": False,
            "problems": [str(exc)],
            "summary": {
                "receipt_file_present": False,
                "expected_count": len(expected_automations),
                "success_count": 0,
                "scheduled_success_count": 0,
                "failed_latest_count": 0,
                "missing_success_count": len(expected_automations),
                "missing_scheduled_success_count": len(expected_automations),
                "rows": [],
                "missing_success": expected_automations,
                "missing_scheduled_success": expected_automations,
                "failed_latest": [],
            },
        }
    return {"valid": not problems, "problems": problems, "summary": summary}


def _receipt_due_summary(
    receipts: dict[str, Any],
    expected_automations: list[dict[str, Any]],
    *,
    activated_at: datetime | None,
    now: datetime | None = None,
    grace_minutes: int = 30,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(ET)
    if now.tzinfo is None:
        now = now.replace(tzinfo=ET)
    now_et = now.astimezone(ET)
    activation = (activated_at or now_et).astimezone(ET)
    receipt_rows = {
        str(row.get("routine_id") or ""): row
        for row in ((receipts.get("summary") or {}).get("rows") or [])
        if isinstance(row, dict)
    }
    rows: list[dict[str, Any]] = []
    for expected in expected_automations:
        routine_id = str(expected.get("automation_id") or "")
        receipt = receipt_rows.get(routine_id, {})
        last_success = _parse_dt(receipt.get("last_scheduled_success_at"))
        routine_activation = _parse_dt(expected.get("expected_since")) or activation
        if routine_activation.tzinfo is None:
            routine_activation = routine_activation.replace(tzinfo=ET)
        routine_activation = max(activation, routine_activation.astimezone(ET))
        last_due = _last_run_between(expected, routine_activation, now_et)
        next_due = _next_run_after(expected, now_et)
        overdue_after = last_due + timedelta(minutes=grace_minutes) if last_due else None
        if last_due is None:
            state = "not_due_yet"
        elif last_success and last_success.astimezone(ET) >= last_due:
            state = "current"
        elif overdue_after and now_et > overdue_after:
            state = "overdue"
        else:
            state = "due_waiting"
        rows.append({
            "routine_id": routine_id,
            "routine_name": expected.get("automation_name") or "",
            "role": expected.get("role") or "",
            "schedule": expected.get("schedule") or "",
            "due_state": state,
            "expected_since": routine_activation.isoformat(),
            "last_due_at": last_due.isoformat() if last_due else "",
            "next_due_at": next_due.isoformat() if next_due else "",
            "overdue_after": overdue_after.isoformat() if overdue_after else "",
            "last_success_at": receipt.get("last_success_at") or "",
            "last_scheduled_success_at": receipt.get("last_scheduled_success_at") or "",
        })
    overdue = [row for row in rows if row["due_state"] == "overdue"]
    due_waiting = [row for row in rows if row["due_state"] == "due_waiting"]
    current = [row for row in rows if row["due_state"] == "current"]
    not_due_yet = [row for row in rows if row["due_state"] == "not_due_yet"]
    next_candidates = [row for row in rows if row.get("next_due_at")]
    next_target = sorted(next_candidates, key=lambda row: row["next_due_at"])[0] if next_candidates else {}
    return {
        "activated_at": activation.isoformat(),
        "now": now_et.isoformat(),
        "grace_minutes": grace_minutes,
        "overdue_count": len(overdue),
        "due_waiting_count": len(due_waiting),
        "current_count": len(current),
        "not_due_yet_count": len(not_due_yet),
        "next_due": next_target,
        "rows": rows,
        "overdue": overdue,
        "due_waiting": due_waiting,
        "not_due_yet": not_due_yet,
    }


def _operating_gaps(
    status: dict[str, Any],
    automation: dict[str, Any],
    manifest: dict[str, Any],
    receipts: dict[str, Any],
    receipt_due: dict[str, Any],
) -> list[str]:
    gaps: list[str] = []
    if not automation.get("installed"):
        missing = [
            str(row.get("automation_name") or row.get("automation_id") or "unknown")
            for row in automation.get("missing") or []
            if isinstance(row, dict)
        ]
        suffix = f": {', '.join(missing)}" if missing else "."
        gaps.append(f"Codex cloud routine stack is incomplete{suffix}")
    elif not automation.get("active"):
        inactive = [
            str(row.get("automation_name") or row.get("automation_id") or "unknown")
            for row in automation.get("inactive") or []
            if isinstance(row, dict)
        ]
        active_superseded = [
            str(row.get("automation_name") or row.get("automation_id") or "unknown")
            for row in automation.get("active_superseded") or []
            if isinstance(row, dict)
        ]
        problems = inactive + active_superseded
        suffix = f": {', '.join(problems)}" if problems else "."
        gaps.append(f"Codex cloud routine stack has schedule conflicts{suffix}")
    prompt_protocol = automation.get("prompt_protocol") or {}
    for row in prompt_protocol.get("missing") or []:
        if not isinstance(row, dict):
            continue
        label = row.get("routine_name") or row.get("routine_id") or "Cloud routine"
        gaps.append(f"{label} is missing cloud receipt protocol: {row.get('problem') or 'prompt incomplete'}.")
    if not manifest.get("valid"):
        gaps.append("Routine manifest is invalid.")
    if not receipts.get("valid"):
        gaps.append("Cloud routine receipt file is invalid.")
    failed_receipts = ((receipts.get("summary") or {}).get("failed_latest") or [])
    for row in failed_receipts:
        if not isinstance(row, dict):
            continue
        label = row.get("routine_name") or row.get("routine_id") or "Cloud routine"
        summary = row.get("last_summary") or row.get("last_recorded_at") or "latest run failed"
        gaps.append(f"{label} latest run receipt failed: {summary}")
    for row in receipt_due.get("overdue") or []:
        if not isinstance(row, dict):
            continue
        label = row.get("routine_name") or row.get("routine_id") or "Cloud routine"
        gaps.append(f"{label} run receipt is overdue after {row.get('overdue_after')}.")
    source_capability = status.get("source_capability") or {}
    live_config = source_capability.get("live_source_config") or {}
    for row in live_config.get("missing") or []:
        if not isinstance(row, dict):
            continue
        label = row.get("label") or row.get("key") or "Live source"
        impact = row.get("impact") or "live source fetch is not configured"
        gaps.append(f"{label} configuration missing: {impact}")
    if not status.get("go_live_ready"):
        gaps.append("Dashboard is not go-live ready.")
    dark = (status.get("dark_lanes") or {}).get("details") or []
    for row in dark:
        if not isinstance(row, dict):
            continue
        label = row.get("label") or row.get("key") or "Optional lane"
        next_step = row.get("next_step") or row.get("missing_impact") or "supply source input"
        gaps.append(f"{label} remains dark: {next_step}")
    if (status.get("open_actions") or {}).get("count"):
        tickers = [
            str(ticker)
            for ticker in (status.get("open_actions") or {}).get("tickers") or []
            if ticker
        ]
        suffix = f" ({', '.join(tickers)})" if tickers else ""
        gaps.append(f"Open action reviews remain unresolved{suffix}.")
    return gaps


def cloud_ops_status(
    *,
    src_dir: str | Path = DEFAULT_SRC,
    automations_dir: str | Path | None = None,
    automation_name: str = DEFAULT_AUTOMATION_NAME,
    automation_id: str = DEFAULT_AUTOMATION_ID,
    automation_proof: str | Path | None = None,
    receipt_proof: str | Path | None = None,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    src = Path(src_dir)
    if automation_proof is None:
        automation_proof = src / DEFAULT_AUTOMATION_PROOF
    if receipt_proof is None:
        receipt_proof = src / DEFAULT_RECEIPT_PROOF
    status = live_status_mod.live_status(src_dir=src)
    manifest = _manifest_summary(src)
    automation = _automation_summary(
        automations_dir=automations_dir,
        automation_name=automation_name,
        automation_id=automation_id,
        automation_proof=automation_proof,
        expected_automations=DEFAULT_EXPECTED_AUTOMATIONS,
    )
    receipts = _receipt_summary(receipt_proof, DEFAULT_EXPECTED_AUTOMATIONS)
    proof_meta = _proof_metadata(automation_proof)
    receipt_due = _receipt_due_summary(
        receipts,
        DEFAULT_EXPECTED_AUTOMATIONS,
        activated_at=_parse_dt(proof_meta.get("verified_at")),
        now=_parse_dt(now) if now is not None else None,
    )
    gaps = _operating_gaps(status, automation, manifest, receipts, receipt_due)
    live_config = (status.get("source_capability") or {}).get("live_source_config") or {}
    live_config_ready = (
        int(live_config.get("total_count") or 0) == 0
        or (
            int(live_config.get("missing_count") or 0) == 0
            and int(live_config.get("stale_count") or 0) == 0
        )
    )
    schedule_ready = (
        bool(status.get("go_live_ready"))
        and live_config_ready
        and bool(manifest.get("valid"))
        and bool(automation.get("active"))
        and bool((automation.get("prompt_protocol") or {}).get("ready", True))
        and bool(receipts.get("valid"))
        and int(receipt_due.get("overdue_count") or 0) == 0
    )
    receipt_summary = receipts.get("summary") or {}
    scheduled_success_count = int(receipt_summary.get("scheduled_success_count") or 0)
    expected_receipt_count = int(receipt_summary.get("expected_count") or 0)
    failed_latest_count = int(receipt_summary.get("failed_latest_count") or 0)
    first_scheduled_run_proven = (
        schedule_ready
        and scheduled_success_count > 0
        and failed_latest_count == 0
    )
    live_run_proven = (
        schedule_ready
        and scheduled_success_count >= expected_receipt_count
        and expected_receipt_count > 0
        and failed_latest_count == 0
    )
    if not schedule_ready:
        operating_state = "not_ready"
    elif failed_latest_count:
        operating_state = "run_failed"
    elif live_run_proven:
        operating_state = "live_run_proven"
    elif first_scheduled_run_proven:
        operating_state = "partial_live_run_proven"
    else:
        operating_state = "ready_pending_first_success"
    return {
        "ready_for_unattended_daily_run": schedule_ready,
        "schedule_ready_for_unattended_run": schedule_ready,
        "first_scheduled_run_proven": first_scheduled_run_proven,
        "live_run_proven": live_run_proven,
        "cloud_operating_state": operating_state,
        "local_go_live_ready": bool(status.get("go_live_ready")),
        "routine_manifest": manifest,
        "cloud_automation": automation,
        "routine_receipts": receipts,
        "routine_receipt_due": receipt_due,
        "dark_lanes": status.get("dark_lanes") or {},
        "source_capability": status.get("source_capability") or {},
        "open_actions": status.get("open_actions") or {},
        "gaps": gaps,
        "source_pull_note": (
            "The scheduled routines can run the repo refresh and connector/supplied "
            "intake attempts, but missing connector exports must remain visible as "
            "dark lanes instead of being treated as checked clear."
        ),
        "drill_command": DRILL_COMMAND,
        "manual_run_command": MANUAL_RUN_COMMAND,
    }


def format_text(report: dict[str, Any]) -> str:
    manifest_summary = (report.get("routine_manifest") or {}).get("summary") or {}
    automation = report.get("cloud_automation") or {}
    receipts = ((report.get("routine_receipts") or {}).get("summary") or {})
    receipt_due = report.get("routine_receipt_due") or {}
    next_due = receipt_due.get("next_due") or {}
    dark = report.get("dark_lanes") or {}
    prompt_protocol = automation.get("prompt_protocol") or {}
    source_capability = (
        (report.get("live_status") or {}).get("source_capability")
        or report.get("source_capability")
        or {}
    )
    lines = [
        f"Cloud schedule ready: {bool(report.get('schedule_ready_for_unattended_run'))}",
        f"Cloud first scheduled run proven: {bool(report.get('first_scheduled_run_proven'))}",
        f"Cloud live-run proven: {bool(report.get('live_run_proven'))}",
        f"Cloud operating state: {report.get('cloud_operating_state') or 'unknown'}",
        f"Local go-live ready: {bool(report.get('local_go_live_ready'))}",
        (
            "Routine manifest: "
            f"valid={bool((report.get('routine_manifest') or {}).get('valid'))} | "
            f"routines={manifest_summary.get('routines', 0)} | "
            f"active={manifest_summary.get('active', 0)}"
        ),
        (
            "Cloud routine stack: "
            f"installed={bool(automation.get('installed'))} | "
            f"active={bool(automation.get('active'))} | "
            f"expected={int(automation.get('expected_count') or 0)} | "
            f"active_count={int(automation.get('active_count') or 0)} | "
            f"active_superseded={int(automation.get('active_superseded_count') or 0)}"
        ),
        (
            "Cloud receipt protocol: "
            f"checked={int(prompt_protocol.get('checked_count') or 0)} | "
            f"ok={int(prompt_protocol.get('ok_count') or 0)} | "
            f"missing={int(prompt_protocol.get('missing_count') or 0)}"
        ),
        (
            "Dark source lanes: "
            f"{int(dark.get('count') or 0)}"
        ),
        (
            "Live source capability: "
            f"inputs={int(source_capability.get('present_inputs') or 0)}/"
            f"{int(source_capability.get('total_inputs') or 0)} | "
            f"connector_or_api={int(source_capability.get('connector_or_api_count') or 0)} | "
            f"supplied_or_export={int(source_capability.get('supplied_or_export_count') or 0)} | "
            f"missing_live_capable={int(source_capability.get('missing_live_capable_count') or 0)}"
        ),
        (
            "Live source config: "
            f"configured={int((source_capability.get('live_source_config') or {}).get('configured_count') or 0)}/"
            f"{int((source_capability.get('live_source_config') or {}).get('total_count') or 0)} | "
            f"missing={int((source_capability.get('live_source_config') or {}).get('missing_count') or 0)} | "
            f"stale={int((source_capability.get('live_source_config') or {}).get('stale_count') or 0)}"
        ),
        (
            "Cloud run receipts: "
            f"scheduled_success={int(receipts.get('scheduled_success_count') or 0)}/"
            f"{int(receipts.get('expected_count') or 0)} | "
            f"failed_latest={int(receipts.get('failed_latest_count') or 0)} | "
            f"missing_scheduled_success={int(receipts.get('missing_scheduled_success_count') or 0)}"
        ),
        (
            "Cloud receipt due state: "
            f"overdue={int(receipt_due.get('overdue_count') or 0)} | "
            f"waiting={int(receipt_due.get('due_waiting_count') or 0)} | "
            f"not_due_yet={int(receipt_due.get('not_due_yet_count') or 0)} | "
            f"current={int(receipt_due.get('current_count') or 0)}"
        ),
    ]
    lines.extend(live_source_capability.format_missing_live_capable(source_capability))
    lines.extend(live_source_capability.format_missing_live_config(source_capability))
    due_waiting = [
        row for row in receipt_due.get("due_waiting") or []
        if isinstance(row, dict)
    ]
    overdue = [
        row for row in receipt_due.get("overdue") or []
        if isinstance(row, dict)
    ]
    if due_waiting:
        row = due_waiting[0]
        label = row.get("routine_name") or row.get("routine_id") or "unknown"
        lines.append(
            f"Due receipt waiting: {label} due at {row.get('last_due_at') or ''} "
            f"| grace until {row.get('overdue_after') or ''}"
        )
        if not report.get("first_scheduled_run_proven"):
            lines.append(f"First scheduled proof pending: waiting for {label} scheduled receipt.")
    elif overdue:
        row = overdue[0]
        label = row.get("routine_name") or row.get("routine_id") or "unknown"
        lines.append(
            f"Overdue receipt: {label} due at {row.get('last_due_at') or ''} "
            f"| overdue after {row.get('overdue_after') or ''}"
        )
        if not report.get("first_scheduled_run_proven"):
            lines.append(f"First scheduled proof pending: {label} scheduled receipt is overdue.")
    elif next_due:
        label = next_due.get("routine_name") or next_due.get("routine_id") or "unknown"
        lines.append(f"Next expected receipt: {label} at {next_due.get('next_due_at') or ''}")
        if not report.get("first_scheduled_run_proven"):
            lines.append(
                "First scheduled proof pending: "
                f"{label} has not reached its next scheduled receipt window yet."
            )
    lines.append(f"Cloud runner drill: {report.get('drill_command') or DRILL_COMMAND}")
    lines.append(f"Manual routine run: {report.get('manual_run_command') or MANUAL_RUN_COMMAND}")
    gaps = report.get("gaps") or []
    if gaps:
        lines.append("Gaps:")
        lines.extend(f"- {gap}" for gap in gaps)
    else:
        lines.append("Gaps: none")
    lines.append(str(report.get("source_pull_note") or ""))
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Report daily cloud operating readiness")
    parser.add_argument("--src-dir", default=str(DEFAULT_SRC))
    parser.add_argument("--automations-dir")
    parser.add_argument("--automation-name", default=DEFAULT_AUTOMATION_NAME)
    parser.add_argument("--automation-id", default=DEFAULT_AUTOMATION_ID)
    parser.add_argument("--automation-proof")
    parser.add_argument("--receipt-proof")
    parser.add_argument("--now", help="Override current time for testing, ISO format")
    parser.add_argument("--format", choices=["json", "text"], default="json")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero unless unattended daily ops are ready")
    parser.add_argument(
        "--require-first-proof",
        action="store_true",
        help="Exit non-zero unless at least one scheduled routine success receipt is present",
    )
    parser.add_argument(
        "--require-live-run",
        action="store_true",
        help="Exit non-zero unless every expected routine has a scheduled success receipt",
    )
    args = parser.parse_args(argv)

    report = cloud_ops_status(
        src_dir=args.src_dir,
        automations_dir=args.automations_dir,
        automation_name=args.automation_name,
        automation_id=args.automation_id,
        automation_proof=args.automation_proof,
        receipt_proof=args.receipt_proof,
        now=args.now,
    )
    if args.format == "text":
        print(format_text(report))
    else:
        print(json.dumps(report, indent=2))
    if args.require_live_run and not report.get("live_run_proven"):
        return 3
    if args.require_first_proof and not report.get("first_scheduled_run_proven"):
        return 2
    if args.strict and not report.get("ready_for_unattended_daily_run"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
