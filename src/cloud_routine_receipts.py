#!/usr/bin/env python3
"""Record and summarize Codex cloud routine run receipts.

Scheduled app automations should append a small receipt at the end of each run.
This gives the operator proof that a routine actually fired, separate from the
proof that the schedule is installed.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "src" / "cloud_routine_receipts.json"
VALID_STATUSES = {"started", "success", "failed"}
VALID_RUN_SOURCES = {"manual", "scheduled"}


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


def load_receipts(path: str | Path = DEFAULT_OUT) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        return {"schema_version": 1, "receipts": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return {"schema_version": 1, "receipts": payload}
    if isinstance(payload, dict):
        receipts = payload.get("receipts")
        if not isinstance(receipts, list):
            payload = dict(payload)
            payload["receipts"] = []
        return payload
    return {"schema_version": 1, "receipts": []}


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
    recorded_at: str | None = None,
    keep: int = 250,
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
    receipts.append(receipt)
    payload = {
        "schema_version": int(payload.get("schema_version") or 1),
        "updated_at": receipt["recorded_at"],
        "receipts": receipts[-keep:],
    }
    problems = validate_receipts(payload)
    if problems:
        raise ValueError("; ".join(problems))
    _atomic_write_json(path, payload)
    return receipt


def summarize_receipts(
    payload: dict[str, Any],
    *,
    expected_automations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    receipts = [row for row in payload.get("receipts") or [] if isinstance(row, dict)]
    expected = expected_automations or []
    routine_ids = [str(row.get("automation_id") or "") for row in expected if row.get("automation_id")]
    if not routine_ids:
        routine_ids = sorted({str(row.get("routine_id") or "") for row in receipts if row.get("routine_id")})

    rows: list[dict[str, Any]] = []
    for routine_id in routine_ids:
        matching = [row for row in receipts if str(row.get("routine_id") or "") == routine_id]
        matching.sort(key=lambda row: str(row.get("recorded_at") or ""), reverse=True)
        last = matching[0] if matching else {}
        successes = [row for row in matching if str(row.get("status") or "").lower() == "success"]
        scheduled_successes = [
            row
            for row in successes
            if str(row.get("run_source") or "manual").lower() == "scheduled"
        ]
        success = successes[0] if successes else {}
        scheduled_success = scheduled_successes[0] if scheduled_successes else {}
        expected_row = next((row for row in expected if row.get("automation_id") == routine_id), {})
        rows.append({
            "routine_id": routine_id,
            "routine_name": expected_row.get("automation_name") or "",
            "role": expected_row.get("role") or "",
            "schedule": expected_row.get("schedule") or "",
            "receipt_count": len(matching),
            "last_status": last.get("status") or "no_receipt",
            "last_run_source": last.get("run_source") or "manual",
            "last_recorded_at": last.get("recorded_at") or "",
            "last_success_at": success.get("recorded_at") or "",
            "last_scheduled_success_at": scheduled_success.get("recorded_at") or "",
            "last_summary": last.get("summary") or "",
        })

    missing_success = [row for row in rows if not row.get("last_success_at")]
    missing_scheduled_success = [row for row in rows if not row.get("last_scheduled_success_at")]
    failed_latest = [row for row in rows if row.get("last_status") == "failed"]
    return {
        "receipt_file_present": bool(receipts),
        "expected_count": len(rows),
        "success_count": len(rows) - len(missing_success),
        "scheduled_success_count": len(rows) - len(missing_scheduled_success),
        "failed_latest_count": len(failed_latest),
        "missing_success_count": len(missing_success),
        "missing_scheduled_success_count": len(missing_scheduled_success),
        "rows": rows,
        "missing_success": missing_success,
        "missing_scheduled_success": missing_scheduled_success,
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
            f"failed_latest={int(summary.get('failed_latest_count') or 0)} | "
            f"missing_scheduled_success={int(summary.get('missing_scheduled_success_count') or 0)}"
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

    payload = load_receipts(path)
    problems = validate_receipts(payload)
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
