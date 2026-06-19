#!/usr/bin/env python3
"""Record and summarize Codex cloud routine run receipts.

Scheduled app automations should append a small receipt at the end of each run.
This gives the operator proof that a routine actually fired, separate from the
proof that the schedule is installed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "src" / "cloud_routine_receipts.json"
DEFAULT_BOUNDARY_CONFIG = ROOT / "src" / "cockpit_artifact_boundaries.json"
RECEIPT_SCHEMA_VERSION = 2
VALID_STATUSES = {"started", "success", "failed"}
VALID_RUN_SOURCES = {"manual", "scheduled"}
VALID_BOUNDARY_OUTCOMES = {
    "failed",
    "produced_fresh",
    "no_op",
    "stale_boundary",
    "missing",
    "fired_unknown",
}
JSON_READ_ENCODINGS = ("utf-8", "utf-8-sig", "cp1252", "utf-16")
CORE_PROOF_AUTOMATION_IDS = {
    "investing-os-pre-market-source-intake",
    "investing-os-fundstrat-pre-market-safety-sweep",
    "investing-os-morning-scan",
    "investing-os-broker-position-intake",
    "investing-os-early-cockpit-build",
    "investing-os-daily-synthesis",
    "investing-os-post-open-evidence-gate",
    "investing-os-fundstrat-daytime-watch",
    "investing-os-uw-opportunity-cache",
    "investing-os-parabolic-cache",
    "investing-os-full-cockpit-build",
    "investing-os-post-close-refresh",
    "investing-os-positions-sync",
    "investing-os-fundstrat-after-hours-catch-up",
}
PROOF_SCOPE_CORE = "core"
PROOF_SCOPE_SUPPORT = "support"
ET = ZoneInfo("America/New_York")
DAY_NAMES = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\s*([AP]M)\b", re.IGNORECASE)


def proof_scope(row: dict[str, Any]) -> str:
    explicit = str(row.get("proof_scope") or "").strip().lower()
    if explicit:
        return explicit
    routine_id = str(row.get("automation_id") or row.get("routine_id") or "")
    return PROOF_SCOPE_CORE if routine_id in CORE_PROOF_AUTOMATION_IDS else PROOF_SCOPE_SUPPORT


def with_proof_scope(row: dict[str, Any]) -> dict[str, Any]:
    scoped = dict(row)
    scoped["proof_scope"] = proof_scope(scoped)
    return scoped


def proof_required_automations(expected_automations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        with_proof_scope(row)
        for row in expected_automations
        if isinstance(row, dict) and proof_scope(row) == PROOF_SCOPE_CORE
    ]


def support_automations(expected_automations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        with_proof_scope(row)
        for row in expected_automations
        if isinstance(row, dict) and proof_scope(row) != PROOF_SCOPE_CORE
    ]


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_dt(value: Any) -> datetime | None:
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


def _normalize_artifact_path(path: str | Path) -> str:
    return str(path).replace("\\", "/").strip().lstrip("./")


def _repo_root_for_receipts(path: str | Path | None) -> Path:
    if path is None:
        return ROOT
    receipt_path = Path(path)
    parent = receipt_path.parent
    if parent.name == "src":
        return parent.parent
    return parent


def _config_path(repo_root: str | Path | None = None, boundary_config_path: str | Path | None = None) -> Path:
    if boundary_config_path is not None:
        return Path(boundary_config_path)
    root = Path(repo_root) if repo_root is not None else ROOT
    return root / "src" / "cockpit_artifact_boundaries.json"


def load_boundary_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path) if path is not None else DEFAULT_BOUNDARY_CONFIG
    if not config_path.is_file():
        return {"schema_version": 1, "artifacts": {}}
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": 1, "artifacts": {}}
    return payload if isinstance(payload, dict) else {"schema_version": 1, "artifacts": {}}


def _artifact_specs_for_routine(
    routine_id: str,
    *,
    config: dict[str, Any] | None = None,
    owned_artifacts: list[str] | None = None,
) -> list[dict[str, Any]]:
    payload = config if isinstance(config, dict) else load_boundary_config()
    raw_artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    explicit = {_normalize_artifact_path(path) for path in (owned_artifacts or []) if str(path or "").strip()}
    specs: list[dict[str, Any]] = []
    for key, raw in raw_artifacts.items():
        if not isinstance(raw, dict):
            continue
        rel_path = _normalize_artifact_path(str(raw.get("path") or key))
        owners = [str(owner) for owner in raw.get("owner_routine_ids") or []]
        if explicit:
            names = {rel_path, Path(rel_path).name}
            if not names.intersection(explicit):
                continue
        elif routine_id not in owners:
            continue
        spec = dict(raw)
        spec["path"] = rel_path
        specs.append(spec)
    if explicit:
        configured = {_normalize_artifact_path(spec.get("path") or "") for spec in specs}
        for rel_path in sorted(explicit - configured):
            specs.append({
                "path": rel_path,
                "owner_routine_ids": [routine_id],
                "as_of_field": "",
                "freshness": "same_et_session_day",
            })
    return specs


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_field_values(obj: Any, field_path: str) -> list[Any]:
    parts = [part for part in str(field_path or "").split(".") if part]
    if not parts:
        return []

    def walk(value: Any, remaining: list[str]) -> list[Any]:
        if not remaining:
            return [value]
        part = remaining[0]
        rest = remaining[1:]
        if isinstance(value, list):
            values: list[Any] = []
            if part in {"[]", "*"}:
                for item in value:
                    values.extend(walk(item, rest))
            else:
                for item in value:
                    values.extend(walk(item, remaining))
            return values
        if not isinstance(value, dict):
            return []
        if part.endswith("[]"):
            child = value.get(part[:-2])
            if not isinstance(child, list):
                return []
            values = []
            for item in child:
                values.extend(walk(item, rest))
            return values
        return walk(value.get(part), rest)

    return [value for value in walk(obj, parts) if value not in (None, "")]


def _best_as_of_value(obj: Any, field_path: str) -> str:
    values = _extract_field_values(obj, field_path)
    if not values:
        return ""
    parsed_values: list[tuple[datetime, Any]] = []
    for value in values:
        parsed = parse_dt(value)
        if parsed:
            parsed_values.append((parsed, value))
    if parsed_values:
        return str(max(parsed_values, key=lambda item: item[0])[1])
    for value in values:
        if isinstance(value, (str, int, float)):
            return str(value)
    return ""


def _freshness_window_minutes(freshness: str) -> int | None:
    text = str(freshness or "").strip().lower()
    match = re.fullmatch(r"(?:minutes?|mins?):\s*(\d+)", text)
    if match:
        return int(match.group(1))
    match = re.fullmatch(r"(?:hours?|hrs?):\s*(\d+)", text)
    if match:
        return int(match.group(1)) * 60
    return None


def _is_fresh_as_of(as_of: Any, freshness: str, reference_time: Any) -> bool:
    parsed_as_of = parse_dt(as_of)
    parsed_reference = parse_dt(reference_time) or datetime.now(timezone.utc)
    if not parsed_as_of:
        return False
    mode = str(freshness or "same_et_session_day").strip().lower()
    if mode in {"same_et_session_day", "same_session_day", "same_day"}:
        return parsed_as_of.astimezone(ET).date() == parsed_reference.astimezone(ET).date()
    minutes = _freshness_window_minutes(mode)
    if minutes is not None:
        delta = parsed_reference.astimezone(timezone.utc) - parsed_as_of.astimezone(timezone.utc)
        return timedelta(minutes=-5) <= delta <= timedelta(minutes=minutes)
    return False


def snapshot_owned_artifacts(
    routine_id: str,
    *,
    repo_root: str | Path = ROOT,
    owned_artifacts: list[str] | None = None,
    boundary_config_path: str | Path | None = None,
    reference_time: str | datetime | None = None,
) -> list[dict[str, Any]]:
    root = Path(repo_root)
    config = load_boundary_config(_config_path(root, boundary_config_path))
    rows: list[dict[str, Any]] = []
    for spec in _artifact_specs_for_routine(routine_id, config=config, owned_artifacts=owned_artifacts):
        rel_path = _normalize_artifact_path(spec.get("path") or "")
        abs_path = root / rel_path
        as_of_field = str(spec.get("as_of_field") or "").strip()
        freshness = str(spec.get("freshness") or "same_et_session_day").strip()
        row: dict[str, Any] = {
            "path": rel_path,
            "as_of_field": as_of_field,
            "freshness": freshness,
            "present": abs_path.is_file(),
            "missing": not abs_path.is_file(),
            "content_hash": "",
            "as_of": "",
            "fresh": False,
            "committed": False,
            "committed_sha": "",
        }
        if abs_path.is_file():
            row["content_hash"] = _hash_file(abs_path)
            try:
                payload = json.loads(abs_path.read_text(encoding="utf-8"))
            except Exception:
                payload = None
            if payload is not None and as_of_field:
                row["as_of"] = _best_as_of_value(payload, as_of_field)
            row["fresh"] = _is_fresh_as_of(
                row.get("as_of"),
                freshness,
                reference_time or datetime.now(timezone.utc),
            )
        rows.append(row)
    return rows


def annotate_artifact_changes(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    before_by_path = {
        _normalize_artifact_path(row.get("path") or ""): row
        for row in before
        if isinstance(row, dict)
    }
    rows: list[dict[str, Any]] = []
    for raw in after:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        previous = before_by_path.get(_normalize_artifact_path(row.get("path") or ""), {})
        previous_hash = str(previous.get("content_hash") or "")
        current_hash = str(row.get("content_hash") or "")
        row["previous_content_hash"] = previous_hash
        row["changed"] = bool(current_hash and current_hash != previous_hash)
        rows.append(row)
    return rows


def classify_boundary_outcome(status: str, artifact_rows: list[dict[str, Any]] | None = None) -> str:
    normalized_status = str(status or "").strip().lower()
    if normalized_status == "failed":
        return "failed"
    if normalized_status != "success":
        return "fired_unknown"
    rows = [row for row in artifact_rows or [] if isinstance(row, dict)]
    if not rows:
        return "fired_unknown"
    if any(bool(row.get("missing")) or not bool(row.get("present", True)) for row in rows):
        return "missing"
    if any(not bool(row.get("fresh")) for row in rows):
        return "stale_boundary"
    if any(bool(row.get("changed")) for row in rows):
        return "produced_fresh"
    return "no_op"


def _artifact_rows_from_receipt(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    details = receipt.get("details") if isinstance(receipt.get("details"), dict) else {}
    rows = details.get("artifact_boundaries") or details.get("artifacts") or []
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _boundary_details(
    receipt: dict[str, Any],
    routine_id: str,
    *,
    repo_root: str | Path,
    boundary_config_path: str | Path | None = None,
) -> dict[str, Any]:
    status = str(receipt.get("status") or "").strip().lower()
    explicit = str(receipt.get("boundary_outcome") or "").strip().lower()
    rows = _artifact_rows_from_receipt(receipt)
    if explicit in VALID_BOUNDARY_OUTCOMES:
        outcome = explicit
    elif rows:
        outcome = classify_boundary_outcome(status, rows)
    elif status == "failed":
        outcome = "failed"
    elif status == "success":
        current_rows = snapshot_owned_artifacts(
            routine_id,
            repo_root=repo_root,
            boundary_config_path=boundary_config_path,
            reference_time=receipt.get("recorded_at"),
        )
        if current_rows and any(bool(row.get("missing")) for row in current_rows):
            outcome = "missing"
            rows = current_rows
        elif current_rows and any(not bool(row.get("fresh")) for row in current_rows):
            outcome = "stale_boundary"
            rows = current_rows
        else:
            outcome = "fired_unknown"
            rows = current_rows
    else:
        outcome = ""
    missing_paths = [
        str(row.get("path") or "")
        for row in rows
        if bool(row.get("missing")) or not bool(row.get("present", True))
    ]
    stale_paths = [
        str(row.get("path") or "")
        for row in rows
        if row.get("present", True) and not bool(row.get("fresh"))
    ]
    changed_paths = [
        str(row.get("path") or "")
        for row in rows
        if bool(row.get("changed"))
    ]
    return {
        "outcome": outcome,
        "artifact_count": len(rows),
        "artifact_paths": [str(row.get("path") or "") for row in rows],
        "missing_artifacts": missing_paths,
        "stale_artifacts": stale_paths,
        "changed_artifacts": changed_paths,
    }


def _parse_schedule(schedule: Any) -> dict[str, Any]:
    """Best-effort parser for the repo's human-readable routine schedules."""
    text = str(schedule or "").strip()
    lower = text.lower()
    if not lower:
        return {}
    if "market weekdays" in lower or "weekday" in lower:
        days = [0, 1, 2, 3, 4]
    elif "daily" in lower:
        days = [0, 1, 2, 3, 4, 5, 6]
    else:
        days = [value for name, value in DAY_NAMES.items() if name in lower]
    match = TIME_RE.search(text)
    if not days or not match:
        return {}
    hour = int(match.group(1))
    minute = int(match.group(2))
    meridian = match.group(3).upper()
    if meridian == "PM" and hour != 12:
        hour += 12
    elif meridian == "AM" and hour == 12:
        hour = 0
    return {"days": days, "hour": hour, "minute": minute}


def _with_schedule_fields(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    has_explicit_schedule = (
        isinstance(normalized.get("days"), list)
        and "hour" in normalized
        and "minute" in normalized
    )
    if has_explicit_schedule:
        return normalized
    parsed = _parse_schedule(normalized.get("schedule"))
    for key, value in parsed.items():
        normalized.setdefault(key, value)
    return normalized


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


def _row_grace_minutes(row: dict[str, Any], default: int) -> int:
    for key in ("max_age_minutes", "grace_minutes"):
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed >= 0:
            return parsed
    return default


def _label(row: dict[str, Any]) -> str:
    return str(row.get("routine_name") or row.get("automation_name") or row.get("routine_id") or row.get("automation_id") or "Cloud routine")


def summarize_due_receipts(
    receipt_summary: dict[str, Any],
    expected_automations: list[dict[str, Any]],
    *,
    activated_at: datetime | str | None,
    now: datetime | str | None = None,
    grace_minutes: int = 30,
) -> dict[str, Any]:
    """Compute cadence-aware due state from the canonical receipt summary."""
    parsed_now = parse_dt(now) if now is not None else None
    now_et = (parsed_now or datetime.now(ET)).astimezone(ET)
    activation = (parse_dt(activated_at) or now_et).astimezone(ET)
    summary = receipt_summary.get("summary") if isinstance(receipt_summary.get("summary"), dict) else receipt_summary
    receipt_rows = {
        str(row.get("routine_id") or ""): row
        for row in (summary.get("rows") or [])
        if isinstance(row, dict)
    }
    rows: list[dict[str, Any]] = []
    for raw_expected in expected_automations:
        if not isinstance(raw_expected, dict):
            continue
        expected = _with_schedule_fields(raw_expected)
        routine_id = str(expected.get("automation_id") or expected.get("routine_id") or "")
        if not routine_id:
            continue
        receipt = receipt_rows.get(routine_id, {})
        last_success = parse_dt(receipt.get("last_scheduled_success_at"))
        routine_activation = parse_dt(expected.get("expected_since")) or activation
        routine_activation = max(activation, routine_activation.astimezone(ET))
        row_grace = _row_grace_minutes(expected, grace_minutes)
        last_due = _last_run_between(expected, routine_activation, now_et)
        next_cursor = max(now_et, routine_activation)
        next_due = _next_run_after(expected, next_cursor)
        overdue_after = last_due + timedelta(minutes=row_grace) if last_due else None
        if last_due is None:
            state = "not_due_yet"
        elif last_success and last_success.astimezone(ET) >= last_due:
            state = "current"
        elif overdue_after and now_et > overdue_after:
            state = "overdue"
        else:
            state = "due_waiting"
        last_scheduled_success_at = receipt.get("last_scheduled_success_at") or ""
        last_scheduled_receipt_at = receipt.get("last_scheduled_recorded_at") or ""
        last_manual_success_at = receipt.get("last_manual_success_at") or ""
        last_manual_receipt_at = receipt.get("last_manual_recorded_at") or ""
        last_ran_at = last_scheduled_success_at
        last_ran_label = last_ran_at or "never"
        latest_manual_support_label = last_manual_success_at or last_manual_receipt_at or ""
        label = _label({"routine_name": receipt.get("routine_name"), **expected, "routine_id": routine_id})
        manual_suffix = (
            f"; latest manual support {latest_manual_support_label}"
            if latest_manual_support_label
            else ""
        )
        rows.append({
            "routine_id": routine_id,
            "routine_name": expected.get("automation_name") or receipt.get("routine_name") or "",
            "role": expected.get("role") or receipt.get("role") or "",
            "schedule": expected.get("schedule") or receipt.get("schedule") or "",
            "due_state": state,
            "expected_since": routine_activation.isoformat(),
            "last_due_at": last_due.isoformat() if last_due else "",
            "next_due_at": next_due.isoformat() if next_due else "",
            "overdue_after": overdue_after.isoformat() if overdue_after else "",
            "max_age_minutes": row_grace,
            "last_status": receipt.get("last_status") or "",
            "last_run_source": receipt.get("last_run_source") or "",
            "last_recorded_at": receipt.get("last_recorded_at") or "",
            "last_success_at": receipt.get("last_success_at") or "",
            "last_scheduled_status": receipt.get("last_scheduled_status") or "",
            "last_scheduled_recorded_at": last_scheduled_receipt_at,
            "last_scheduled_success_at": last_scheduled_success_at,
            "last_scheduled_summary": receipt.get("last_scheduled_summary") or "",
            "last_manual_recorded_at": last_manual_receipt_at,
            "last_manual_success_at": last_manual_success_at,
            "last_manual_summary": receipt.get("last_manual_summary") or "",
            "manual_support_only": bool(receipt.get("manual_support_only")),
            "last_summary": receipt.get("last_summary") or "",
            "last_boundary_outcome": receipt.get("last_boundary_outcome") or "",
            "last_boundary_artifact_count": int(receipt.get("last_boundary_artifact_count") or 0),
            "last_boundary_artifacts": receipt.get("last_boundary_artifacts") or [],
            "missing_boundary_artifacts": receipt.get("missing_boundary_artifacts") or [],
            "stale_boundary_artifacts": receipt.get("stale_boundary_artifacts") or [],
            "changed_boundary_artifacts": receipt.get("changed_boundary_artifacts") or [],
            "last_ran_at": last_ran_at,
            "last_ran_label": last_ran_label,
            "last_scheduled_success_label": last_ran_label,
            "latest_manual_support_label": latest_manual_support_label,
            "overdue_line": f"overdue: {label}, last scheduled success {last_ran_label}{manual_suffix}",
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


def _atomic_write_json(path: str | Path, payload: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".cloud_routine_receipts.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def load_receipts_bytes(raw: bytes, *, label: str = "<bytes>") -> dict[str, Any]:
    problems: list[str] = []
    for encoding in JSON_READ_ENCODINGS:
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError as exc:
            problems.append(f"{encoding}: {exc}")
            continue
        try:
            payload = json.loads(text)
            break
        except json.JSONDecodeError as exc:
            problems.append(f"{encoding}: {exc}")
    else:
        raise ValueError(f"{label} could not be decoded as JSON: {'; '.join(problems)}")
    if isinstance(payload, list):
        return {"schema_version": 1, "receipts": payload}
    if isinstance(payload, dict):
        receipts = payload.get("receipts")
        if not isinstance(receipts, list):
            payload = dict(payload)
            payload["receipts"] = []
        return payload
    return {"schema_version": 1, "receipts": []}


def _load_json_file(path: Path) -> Any:
    return load_receipts_bytes(path.read_bytes(), label=str(path))


def load_receipts(path: str | Path = DEFAULT_OUT) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        return {"schema_version": 1, "receipts": []}
    return _load_json_file(path)


def _receipt_sort_key(row: dict[str, Any]) -> tuple[float, str]:
    parsed = parse_dt(row.get("recorded_at"))
    timestamp = parsed.timestamp() if parsed else 0.0
    return timestamp, json.dumps(row, sort_keys=True, ensure_ascii=True)


def merge_receipt_payloads(*payloads: dict[str, Any], keep: int = 500) -> dict[str, Any]:
    """Return a canonical receipt payload containing the union of input rows."""
    merged: dict[str, dict[str, Any]] = {}
    schema_version = 1
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        try:
            schema_version = max(schema_version, int(payload.get("schema_version") or 1))
        except (TypeError, ValueError):
            schema_version = max(schema_version, 1)
        for row in payload.get("receipts") or []:
            if not isinstance(row, dict):
                continue
            key = json.dumps(row, sort_keys=True, ensure_ascii=True)
            merged[key] = row
    receipts = sorted(merged.values(), key=_receipt_sort_key)
    if keep > 0:
        receipts = receipts[-keep:]
    updated_at = receipts[-1].get("recorded_at") if receipts else ""
    result: dict[str, Any] = {"schema_version": schema_version, "receipts": receipts}
    if updated_at:
        result["updated_at"] = updated_at
    problems = validate_receipts(result)
    if problems:
        raise ValueError("; ".join(problems))
    return result


def merge_receipts_file(
    path: str | Path,
    *payloads: dict[str, Any],
    keep: int = 500,
) -> dict[str, Any]:
    current = load_receipts(path)
    merged = merge_receipt_payloads(current, *payloads, keep=keep)
    _atomic_write_json(path, merged)
    return merged


def validate_receipt_file_encoding(path: str | Path = DEFAULT_OUT) -> list[str]:
    path = Path(path)
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return [f"{path} must be UTF-8 JSON; decode failed: {exc}"]
    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        return [f"{path} must be valid JSON: {exc}"]
    return []


def normalize_receipts_file(path: str | Path = DEFAULT_OUT) -> dict[str, Any]:
    payload = load_receipts(path)
    problems = validate_receipts(payload)
    if problems:
        raise ValueError("; ".join(problems))
    _atomic_write_json(path, payload)
    return payload


def validate_receipts(payload: Any) -> list[str]:
    problems: list[str] = []
    if not isinstance(payload, dict):
        return ["receipt file must be a JSON object"]
    receipts = payload.get("receipts")
    if not isinstance(receipts, list):
        return ["receipts must be a list"]
    for idx, row in enumerate(receipts):
        if not isinstance(row, dict):
            problems.append(f"receipts[{idx}] must be an object")
            continue
        if not str(row.get("routine_id") or "").strip():
            problems.append(f"receipts[{idx}].routine_id is required")
        status = str(row.get("status") or "").strip().lower()
        if status not in VALID_STATUSES:
            problems.append(f"receipts[{idx}].status must be one of {sorted(VALID_STATUSES)}")
        run_source = str(row.get("run_source") or "manual").strip().lower()
        if run_source not in VALID_RUN_SOURCES:
            problems.append(f"receipts[{idx}].run_source must be one of {sorted(VALID_RUN_SOURCES)}")
        if not str(row.get("recorded_at") or "").strip():
            problems.append(f"receipts[{idx}].recorded_at is required")
    return problems


def append_receipt(
    *,
    path: str | Path = DEFAULT_OUT,
    routine_id: str,
    status: str,
    summary: str = "",
    run_source: str = "manual",
    details: dict[str, Any] | None = None,
    boundary_outcome: str | None = None,
    recorded_at: str | None = None,
    keep: int = 500,
) -> dict[str, Any]:
    normalized_status = status.strip().lower()
    if normalized_status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}")
    normalized_source = run_source.strip().lower()
    if normalized_source not in VALID_RUN_SOURCES:
        raise ValueError(f"run_source must be one of {sorted(VALID_RUN_SOURCES)}")
    payload = load_receipts(path)
    receipts = [row for row in payload.get("receipts") or [] if isinstance(row, dict)]
    receipt: dict[str, Any] = {
        "routine_id": routine_id.strip(),
        "status": normalized_status,
        "run_source": normalized_source,
        "recorded_at": recorded_at or _now_utc(),
    }
    if summary:
        receipt["summary"] = summary.strip()
    if details:
        receipt["details"] = details
    normalized_boundary = str(boundary_outcome or "").strip().lower()
    if normalized_boundary:
        if normalized_boundary not in VALID_BOUNDARY_OUTCOMES:
            raise ValueError(f"boundary_outcome must be one of {sorted(VALID_BOUNDARY_OUTCOMES)}")
        receipt["boundary_outcome"] = normalized_boundary
    elif normalized_status == "failed":
        receipt["boundary_outcome"] = "failed"
    elif normalized_status == "success" and details:
        receipt["boundary_outcome"] = classify_boundary_outcome(
            normalized_status,
            _artifact_rows_from_receipt({"details": details}),
        )
    receipts.append(receipt)
    payload = merge_receipt_payloads(
        {
            "schema_version": max(RECEIPT_SCHEMA_VERSION, int(payload.get("schema_version") or 1)),
            "receipts": receipts,
        },
        keep=keep,
    )
    problems = validate_receipts(payload)
    if problems:
        raise ValueError("; ".join(problems))
    _atomic_write_json(path, payload)
    return receipt


def summarize_receipts(
    payload: dict[str, Any],
    *,
    expected_automations: list[dict[str, Any]] | None = None,
    repo_root: str | Path | None = None,
    boundary_config_path: str | Path | None = None,
) -> dict[str, Any]:
    receipts = [row for row in payload.get("receipts") or [] if isinstance(row, dict)]
    expected = expected_automations or []
    boundary_repo_root = Path(repo_root) if repo_root is not None else ROOT
    routine_ids = [str(row.get("automation_id") or "") for row in expected if row.get("automation_id")]
    if not routine_ids:
        routine_ids = sorted({str(row.get("routine_id") or "") for row in receipts if row.get("routine_id")})

    rows: list[dict[str, Any]] = []
    for routine_id in routine_ids:
        matching = [row for row in receipts if str(row.get("routine_id") or "") == routine_id]
        matching.sort(key=lambda row: str(row.get("recorded_at") or ""), reverse=True)
        last = matching[0] if matching else {}
        successes = [row for row in matching if str(row.get("status") or "").lower() == "success"]
        scheduled_receipts = [
            row
            for row in matching
            if str(row.get("run_source") or "manual").lower() == "scheduled"
        ]
        manual_receipts = [
            row
            for row in matching
            if str(row.get("run_source") or "manual").lower() == "manual"
        ]
        scheduled_successes = [
            row
            for row in successes
            if str(row.get("run_source") or "manual").lower() == "scheduled"
        ]
        manual_successes = [
            row
            for row in successes
            if str(row.get("run_source") or "manual").lower() == "manual"
        ]
        success = successes[0] if successes else {}
        latest_scheduled = scheduled_receipts[0] if scheduled_receipts else {}
        latest_manual = manual_receipts[0] if manual_receipts else {}
        scheduled_success = scheduled_successes[0] if scheduled_successes else {}
        manual_success = manual_successes[0] if manual_successes else {}
        expected_row = next((row for row in expected if row.get("automation_id") == routine_id), {})
        boundary_receipt = (
            latest_scheduled
            if str(latest_scheduled.get("status") or "").lower() in {"success", "failed"}
            else scheduled_success
        )
        boundary = (
            _boundary_details(
                boundary_receipt,
                routine_id,
                repo_root=boundary_repo_root,
                boundary_config_path=boundary_config_path,
            )
            if boundary_receipt
            else {"outcome": "", "artifact_count": 0, "artifact_paths": [], "missing_artifacts": [], "stale_artifacts": [], "changed_artifacts": []}
        )
        rows.append({
            "routine_id": routine_id,
            "routine_name": expected_row.get("automation_name") or "",
            "role": expected_row.get("role") or "",
            "schedule": expected_row.get("schedule") or "",
            "proof_scope": expected_row.get("proof_scope") or "",
            "receipt_count": len(matching),
            "last_status": last.get("status") or "no_receipt",
            "last_run_source": last.get("run_source") or "manual",
            "last_recorded_at": last.get("recorded_at") or "",
            "last_success_at": success.get("recorded_at") or "",
            "last_scheduled_success_at": scheduled_success.get("recorded_at") or "",
            "last_scheduled_status": latest_scheduled.get("status") or "",
            "last_scheduled_recorded_at": latest_scheduled.get("recorded_at") or "",
            "last_scheduled_summary": latest_scheduled.get("summary") or "",
            "last_manual_recorded_at": latest_manual.get("recorded_at") or "",
            "last_manual_success_at": manual_success.get("recorded_at") or "",
            "last_manual_summary": manual_success.get("summary") or "",
            "manual_support_only": bool(manual_success and not scheduled_success),
            "last_summary": last.get("summary") or "",
            "last_boundary_outcome": boundary.get("outcome") or "",
            "last_boundary_artifact_count": int(boundary.get("artifact_count") or 0),
            "last_boundary_artifacts": boundary.get("artifact_paths") or [],
            "missing_boundary_artifacts": boundary.get("missing_artifacts") or [],
            "stale_boundary_artifacts": boundary.get("stale_artifacts") or [],
            "changed_boundary_artifacts": boundary.get("changed_artifacts") or [],
        })

    missing_success = [row for row in rows if not row.get("last_success_at")]
    missing_scheduled_success = [row for row in rows if not row.get("last_scheduled_success_at")]
    manual_support_only = [row for row in rows if row.get("manual_support_only")]
    failed_latest = [row for row in rows if row.get("last_status") == "failed"]
    produced_fresh = [row for row in rows if row.get("last_boundary_outcome") == "produced_fresh"]
    stale_boundary = [row for row in rows if row.get("last_boundary_outcome") == "stale_boundary"]
    no_op = [row for row in rows if row.get("last_boundary_outcome") == "no_op"]
    missing_boundary = [row for row in rows if row.get("last_boundary_outcome") == "missing"]
    fired_unknown = [row for row in rows if row.get("last_boundary_outcome") == "fired_unknown"]
    return {
        "receipt_file_present": bool(receipts),
        "expected_count": len(rows),
        "success_count": len(rows) - len(missing_success),
        "scheduled_success_count": len(rows) - len(missing_scheduled_success),
        "produced_fresh_count": len(produced_fresh),
        "stale_boundary_count": len(stale_boundary),
        "no_op_count": len(no_op),
        "missing_count": len(missing_boundary),
        "fired_unknown_count": len(fired_unknown),
        "manual_support_only_count": len(manual_support_only),
        "failed_latest_count": len(failed_latest),
        "missing_success_count": len(missing_success),
        "missing_scheduled_success_count": len(missing_scheduled_success),
        "rows": rows,
        "produced_fresh": produced_fresh,
        "stale_boundary": stale_boundary,
        "no_op": no_op,
        "missing": missing_boundary,
        "fired_unknown": fired_unknown,
        "missing_success": missing_success,
        "missing_scheduled_success": missing_scheduled_success,
        "manual_support_only": manual_support_only,
        "failed_latest": failed_latest,
    }


def format_text(summary: dict[str, Any]) -> str:
    lines = [
        (
            "Cloud routine receipts: "
            f"success={int(summary.get('success_count') or 0)}/"
            f"{int(summary.get('expected_count') or 0)} | "
            f"scheduled_success={int(summary.get('scheduled_success_count') or 0)}/"
            f"{int(summary.get('expected_count') or 0)} | "
            f"manual_support_only={int(summary.get('manual_support_only_count') or 0)} | "
            f"failed_latest={int(summary.get('failed_latest_count') or 0)} | "
            f"missing_scheduled_success={int(summary.get('missing_scheduled_success_count') or 0)}"
        ),
        (
            "Boundary outcomes: "
            f"produced_fresh={int(summary.get('produced_fresh_count') or 0)}/"
            f"{int(summary.get('expected_count') or 0)} | "
            f"stale_boundary={int(summary.get('stale_boundary_count') or 0)} | "
            f"no_op={int(summary.get('no_op_count') or 0)} | "
            f"missing={int(summary.get('missing_count') or 0)} | "
            f"fired_unknown={int(summary.get('fired_unknown_count') or 0)}"
        )
    ]
    failed = summary.get("failed_latest") or []
    if failed:
        lines.append("Failed latest receipts:")
        for row in failed:
            label = row.get("routine_name") or row.get("routine_id") or "unknown"
            lines.append(f"- {label}: {row.get('last_summary') or row.get('last_recorded_at') or 'failed'}")
    missing = summary.get("missing_success") or []
    if missing:
        lines.append("No success receipt yet:")
        for row in missing[:10]:
            label = row.get("routine_name") or row.get("routine_id") or "unknown"
            lines.append(f"- {label}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Record or inspect Codex cloud routine run receipts")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--routine-id")
    parser.add_argument("--status", choices=sorted(VALID_STATUSES))
    parser.add_argument("--summary", default="")
    parser.add_argument("--run-source", choices=sorted(VALID_RUN_SOURCES), default="manual")
    parser.add_argument("--details-json", help="Optional JSON object with run details")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument(
        "--require-utf8",
        action="store_true",
        help="fail validation unless the receipt file is strict UTF-8 JSON",
    )
    parser.add_argument(
        "--normalize",
        action="store_true",
        help="rewrite the receipt file as canonical UTF-8 JSON without adding a receipt",
    )
    parser.add_argument("--format", choices=["json", "text"], default="json")
    args = parser.parse_args(argv)

    path = Path(args.out)
    if args.routine_id or args.status:
        if not args.routine_id or not args.status:
            parser.error("--routine-id and --status must be supplied together")
        details = json.loads(args.details_json) if args.details_json else None
        append_receipt(
            path=path,
            routine_id=args.routine_id,
            status=args.status,
            summary=args.summary,
            run_source=args.run_source,
            details=details,
        )
    if args.normalize:
        normalize_receipts_file(path)

    payload = load_receipts(path)
    problems = validate_receipts(payload)
    if args.require_utf8:
        problems.extend(validate_receipt_file_encoding(path))
    try:
        import cloud_ops_status

        expected_automations = cloud_ops_status.DEFAULT_EXPECTED_AUTOMATIONS
    except Exception:
        expected_automations = []
    summary = summarize_receipts(payload, expected_automations=expected_automations)
    result = {"valid": not problems, "problems": problems, "summary": summary}
    if args.format == "text":
        print(format_text(summary))
        if problems:
            print("Problems:")
            for problem in problems:
                print(f"- {problem}")
    else:
        print(json.dumps(result, indent=2))
    if args.validate and problems:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
