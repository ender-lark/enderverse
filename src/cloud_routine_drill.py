#!/usr/bin/env python3
"""Run a non-mutating drill of cloud routine receipt mechanics."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import cloud_ops_status
import cloud_routine_receipts
import cloud_routine_runner


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REAL_RECEIPTS = ROOT / "src" / "cloud_routine_receipts.json"
DEFAULT_ROUTINE_ID = "investing-os-post-close-refresh"


def _read_bytes(path: Path) -> bytes | None:
    if not path.exists():
        return None
    return path.read_bytes()


def run_drill(
    *,
    routine_id: str | None = None,
    real_receipt_path: str | Path = DEFAULT_REAL_RECEIPTS,
    cwd: str | Path = ROOT,
) -> dict[str, Any]:
    """Verify runner receipts against a temp store without touching live proof."""
    expected_rows = list(cloud_ops_status.DEFAULT_EXPECTED_AUTOMATIONS)
    if routine_id:
        expected_rows = [
            row
            for row in expected_rows
            if row.get("automation_id") == routine_id
        ]
        if not expected_rows:
            expected_rows = [{
                "automation_id": routine_id,
                "automation_name": routine_id,
                "role": "custom",
                "schedule": "",
            }]
    real_path = Path(real_receipt_path)
    before = _read_bytes(real_path)
    runner_results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="cloud-routine-drill-") as tmp:
        temp_receipts = Path(tmp) / "cloud_routine_receipts.drill.json"
        for row in expected_rows:
            current_id = str(row.get("automation_id") or "")
            result = cloud_routine_runner.run_cloud_routine(
                routine_id=current_id,
                command=[sys.executable, "-c", "raise SystemExit(0)"],
                cwd=cwd,
                receipt_path=temp_receipts,
                success_summary=f"{current_id} drill succeeded",
                failure_summary=f"{current_id} drill failed",
                run_source="scheduled",
            )
            runner_results.append(result)
        payload = cloud_routine_receipts.load_receipts(temp_receipts)
        problems = cloud_routine_receipts.validate_receipts(payload)
        summary = cloud_routine_receipts.summarize_receipts(
            payload,
            expected_automations=expected_rows,
        )
        temp_receipt_count = len(payload.get("receipts") or [])
    after = _read_bytes(real_path)
    real_untouched = before == after
    failed_results = [row for row in runner_results if int(row.get("returncode") or 0) != 0]
    return {
        "valid": not problems and not failed_results and real_untouched,
        "routine_id": routine_id or "all_expected",
        "routine_ids": [str(row.get("automation_id") or "") for row in expected_rows],
        "routine_count": len(expected_rows),
        "real_receipt_path": str(real_path),
        "real_receipt_untouched": real_untouched,
        "temp_receipt_count": temp_receipt_count,
        "scheduled_success_count": int(summary.get("scheduled_success_count") or 0),
        "failed_latest_count": int(summary.get("failed_latest_count") or 0),
        "runner_returncode": 0 if not failed_results else int(failed_results[0].get("returncode") or 0),
        "runner_status": "success" if not failed_results else "failed",
        "runner_results": runner_results,
        "problems": problems,
    }


def format_text(report: dict[str, Any]) -> str:
    lines = [
        f"Cloud routine drill valid: {bool(report.get('valid'))}",
        f"Routine: {report.get('routine_id') or ''}",
        f"Routines checked: {int(report.get('routine_count') or 0)}",
        f"Real receipt store untouched: {bool(report.get('real_receipt_untouched'))}",
        (
            "Temp receipts: "
            f"count={int(report.get('temp_receipt_count') or 0)} | "
            f"scheduled_success={int(report.get('scheduled_success_count') or 0)} | "
            f"failed_latest={int(report.get('failed_latest_count') or 0)}"
        ),
        (
            "Runner: "
            f"status={report.get('runner_status') or 'unknown'} | "
            f"returncode={int(report.get('runner_returncode') or 0)}"
        ),
    ]
    if report.get("problems"):
        lines.append("Problems:")
        lines.extend(f"- {problem}" for problem in report.get("problems") or [])
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run a safe cloud routine receipt drill")
    parser.add_argument(
        "--routine-id",
        help=(
            "Limit the drill to one routine id. By default the drill checks every "
            "expected cloud routine against a temp receipt store."
        ),
    )
    parser.add_argument("--real-receipts", default=str(DEFAULT_REAL_RECEIPTS))
    parser.add_argument("--cwd", default=str(ROOT))
    parser.add_argument("--format", choices=["json", "text"], default="json")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    report = run_drill(
        routine_id=args.routine_id,
        real_receipt_path=args.real_receipts,
        cwd=args.cwd,
    )
    if args.format == "text":
        print(format_text(report))
    else:
        print(json.dumps(report, indent=2))
    return 0 if report["valid"] or not args.strict else 2


if __name__ == "__main__":
    raise SystemExit(main())
