#!/usr/bin/env python3
"""Run a cloud routine command with guaranteed run receipts."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import cloud_routine_receipts


ROOT = Path(__file__).resolve().parents[1]


def run_cloud_routine(
    *,
    routine_id: str,
    command: list[str],
    cwd: str | Path = ROOT,
    receipt_path: str | Path | None = None,
    owns_artifacts: list[str] | None = None,
    boundary_config_path: str | Path | None = None,
    success_summary: str = "",
    failure_summary: str = "",
    run_source: str = "manual",
    dry_run: bool = False,
) -> dict[str, object]:
    if not command:
        raise ValueError("command must not be empty")
    receipt_file = Path(receipt_path) if receipt_path else cloud_routine_receipts.DEFAULT_OUT
    if dry_run:
        return {
            "routine_id": routine_id,
            "dry_run": True,
            "command": command,
            "receipt_path": str(receipt_file),
            "run_source": run_source,
            "owns_artifacts": owns_artifacts or [],
        }
    started = cloud_routine_receipts.append_receipt(
        path=receipt_file,
        routine_id=routine_id,
        status="started",
        run_source=run_source,
        summary=f"{routine_id} started",
    )

    repo_root = Path(cwd)
    before_artifacts = cloud_routine_receipts.snapshot_owned_artifacts(
        routine_id,
        repo_root=repo_root,
        owned_artifacts=owns_artifacts,
        boundary_config_path=boundary_config_path,
    )
    proc = subprocess.run(command, cwd=Path(cwd))
    status = "success" if proc.returncode == 0 else "failed"
    summary = success_summary if proc.returncode == 0 else failure_summary
    if not summary:
        summary = f"{routine_id} exited {proc.returncode}"
    recorded_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    after_artifacts = cloud_routine_receipts.snapshot_owned_artifacts(
        routine_id,
        repo_root=repo_root,
        owned_artifacts=owns_artifacts,
        boundary_config_path=boundary_config_path,
        reference_time=recorded_at,
    )
    artifact_boundaries = cloud_routine_receipts.annotate_artifact_changes(
        before_artifacts,
        after_artifacts,
    )
    boundary_outcome = cloud_routine_receipts.classify_boundary_outcome(status, artifact_boundaries)
    final = cloud_routine_receipts.append_receipt(
        path=receipt_file,
        routine_id=routine_id,
        status=status,
        run_source=run_source,
        summary=summary,
        details={
            "returncode": proc.returncode,
            "command": command,
            "artifact_boundaries": artifact_boundaries,
        },
        boundary_outcome=boundary_outcome,
        recorded_at=recorded_at,
    )
    return {
        "routine_id": routine_id,
        "returncode": proc.returncode,
        "status": status,
        "boundary_outcome": boundary_outcome,
        "started_receipt": started,
        "final_receipt": final,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run a command and append cloud routine receipts")
    parser.add_argument("--routine-id", required=True)
    parser.add_argument("--receipt-path")
    parser.add_argument("--cwd", default=str(ROOT))
    parser.add_argument("--owns-artifacts", default="", help="Comma-separated repo paths owned by this run")
    parser.add_argument("--boundary-config", help="Optional cockpit artifact boundary config JSON")
    parser.add_argument("--success-summary", default="")
    parser.add_argument("--failure-summary", default="")
    parser.add_argument("--run-source", choices=sorted(cloud_routine_receipts.VALID_RUN_SOURCES), default="manual")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run after --")
    args = parser.parse_args(argv)

    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("supply a command after --")

    result = run_cloud_routine(
        routine_id=args.routine_id,
        command=command,
        cwd=args.cwd,
        receipt_path=args.receipt_path,
        owns_artifacts=[
            item.strip()
            for item in args.owns_artifacts.split(",")
            if item.strip()
        ] or None,
        boundary_config_path=args.boundary_config,
        success_summary=args.success_summary,
        failure_summary=args.failure_summary,
        run_source=args.run_source,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2))
    return int(result.get("returncode") or 0)


if __name__ == "__main__":
    raise SystemExit(main())
