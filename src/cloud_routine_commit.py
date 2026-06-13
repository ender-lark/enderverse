#!/usr/bin/env python3
"""Commit only routine-owned cloud output files.

Scheduled routines may run while unrelated generated files are dirty. This
helper stages only an explicit allowlist so a cloud job can persist receipts and
refreshed dashboard artifacts without accidentally committing unrelated state.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


DEFAULT_ALLOWED_PATHS = [
    "src/cloud_routine_receipts.json",
    "src/live_source_config.json",
    "src/latest_cockpit_feed.json",
    "src/rendered/conviction_cockpit_v5.jsx",
    "docs/index.html",
    "tmp/dashboard_preview.html",
    "tmp/dashboard_parity_feed.json",
    "src/heartbeat.json",
    "src/heartbeat_summary.json",
    "src/daily_synthesis.json",
    "src/daily_synthesis_intake_summary.json",
    "src/source_call_candidates.json",
    "src/source_call_cache_summary.json",
    "src/open_opportunities.json",
    "src/positions.json",
    "src/account_positions.json",
    "src/position_reconciliation.json",
    "src/orphan_triage.json",
    "src/orphan_triage.md",
    "src/macro_state.json",
    "src/uw_closes.json",
    "src/uw_price_responses.json",
    "src/fundstrat_daily_calls.json",
    "src/fundstrat_daytime_alert_state.json",
    "src/fundstrat_bible.json",
    "src/fs_ingest_inventory.json",
    "src/fundstrat_inbox_entries.json",
    "src/fundstrat_intake_state.json",
    "src/fundstrat_intake_summary.json",
    "src/source_calls.json",
    "src/inbox_call_dates.json",
    "src/log_call_dates.json",
    "src/source_shelf_life.json",
    "src/top_prospects.json",
    "src/signal_log.json",
    "src/signal_log_intake_summary.json",
    "src/catalysts.json",
    "src/catalyst_intake_summary.json",
    "src/event_risks.json",
    "src/event_risk_intake_summary.json",
    "src/uw_opportunity_signals.json",
    "src/parabolic_setups.json",
    "src/research_queue.json",
    # V3 decision-layer state files (Task 8):
    "src/dispositions.jsonl",        # append-only ACT/PASS/RECHECK/UNDO spine
    "src/timing_gates.json",         # post-open evidence-gate state transitions
    "src/prediction_signals.json",   # parallel prediction-markets lane (pattern slot #11)
]


def _run_git(args: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=check,
    )


def _git_failure(exc: subprocess.CalledProcessError, *, step: str) -> dict[str, Any]:
    return {
        "valid": False,
        "git_step": step,
        "returncode": exc.returncode,
        "stdout": (exc.stdout or "").strip(),
        "stderr": (exc.stderr or "").strip(),
        "error": f"git {step} failed with exit code {exc.returncode}",
    }


def _normalize(path: str | Path) -> str:
    return str(path).replace("\\", "/").strip().lstrip("./")


def _status_rows(cwd: Path) -> list[dict[str, str]]:
    proc = _run_git(["status", "--porcelain=v1", "-uall"], cwd=cwd)
    rows: list[dict[str, str]] = []
    for line in proc.stdout.splitlines():
        if not line:
            continue
        status = line[:2]
        path_text = line[3:]
        if " -> " in path_text:
            path_text = path_text.split(" -> ", 1)[1]
        rows.append({"status": status, "path": _normalize(path_text)})
    return rows


def _selected_paths(rows: list[dict[str, str]], allowed: set[str]) -> list[str]:
    return sorted({row["path"] for row in rows if row["path"] in allowed})


def _unrelated_paths(rows: list[dict[str, str]], selected: set[str]) -> list[str]:
    return sorted({row["path"] for row in rows if row["path"] not in selected})


def cloud_routine_commit(
    *,
    message: str,
    allowed_paths: list[str] | None = None,
    cwd: str | Path = ROOT,
    push: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Stage/commit/push only the allowed changed paths."""
    repo = Path(cwd)
    allowed = {_normalize(path) for path in (allowed_paths or DEFAULT_ALLOWED_PATHS)}
    try:
        rows = _status_rows(repo)
    except subprocess.CalledProcessError as exc:
        report = _git_failure(exc, step="status")
        report.update({
            "dry_run": dry_run,
            "message": message,
            "allowed_count": len(allowed),
            "selected_paths": [],
            "unrelated_dirty_paths": [],
            "committed": False,
            "pushed": False,
            "commit": "",
            "reason": "git status failed",
        })
        return report
    selected = _selected_paths(rows, allowed)
    unrelated = _unrelated_paths(rows, set(selected))
    report: dict[str, Any] = {
        "valid": True,
        "dry_run": dry_run,
        "message": message,
        "allowed_count": len(allowed),
        "selected_paths": selected,
        "unrelated_dirty_paths": unrelated,
        "committed": False,
        "pushed": False,
        "commit": "",
        "reason": "",
    }
    if not selected:
        report["reason"] = "no allowed changed paths"
        return report
    if dry_run:
        report["reason"] = "dry run"
        return report

    try:
        _run_git(["add", "--", *selected], cwd=repo)
        staged = _run_git(["diff", "--cached", "--name-only"], cwd=repo).stdout.splitlines()
    except subprocess.CalledProcessError as exc:
        report.update(_git_failure(exc, step="add/diff"))
        report["reason"] = "git add/diff failed"
        return report
    staged_selected = sorted(_normalize(path) for path in staged if _normalize(path) in set(selected))
    if not staged_selected:
        report["reason"] = "allowed paths had no staged diff"
        return report
    try:
        _run_git(["commit", "-m", message], cwd=repo)
    except subprocess.CalledProcessError as exc:
        report.update(_git_failure(exc, step="commit"))
        report["reason"] = "git commit failed"
        return report
    report["committed"] = True
    try:
        report["commit"] = _run_git(["rev-parse", "--short", "HEAD"], cwd=repo).stdout.strip()
    except subprocess.CalledProcessError:
        report["commit"] = ""
    if push:
        try:
            _run_git(["push"], cwd=repo)
        except subprocess.CalledProcessError as exc:
            report.update(_git_failure(exc, step="push"))
            report["committed"] = True
            report["reason"] = "git push failed after commit"
            return report
        report["pushed"] = True
    report["reason"] = "committed"
    return report


def format_text(report: dict[str, Any]) -> str:
    lines = [
        f"Cloud routine commit valid: {bool(report.get('valid'))}",
        f"Committed: {bool(report.get('committed'))} | pushed: {bool(report.get('pushed'))}",
        f"Selected paths: {len(report.get('selected_paths') or [])}",
    ]
    if report.get("commit"):
        lines.append(f"Commit: {report.get('commit')}")
    if report.get("reason"):
        lines.append(f"Reason: {report.get('reason')}")
    if report.get("error"):
        lines.append(f"Error: {report.get('error')}")
    if report.get("stderr"):
        lines.append(f"Git stderr: {report.get('stderr')}")
    if report.get("selected_paths"):
        lines.append("Allowed changed paths:")
        lines.extend(f"- {path}" for path in report.get("selected_paths") or [])
    if report.get("unrelated_dirty_paths"):
        lines.append("Unrelated dirty paths left untouched:")
        lines.extend(f"- {path}" for path in report.get("unrelated_dirty_paths") or [])
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Commit only allowed cloud routine output files")
    parser.add_argument("--message", required=True)
    parser.add_argument("--allow", action="append", default=[], help="Allowed changed path; can be repeated")
    parser.add_argument("--cwd", default=str(ROOT))
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--format", choices=["json", "text"], default="json")
    args = parser.parse_args(argv)

    report = cloud_routine_commit(
        message=args.message,
        allowed_paths=args.allow or DEFAULT_ALLOWED_PATHS,
        cwd=args.cwd,
        push=args.push,
        dry_run=args.dry_run,
    )
    if args.format == "text":
        print(format_text(report))
    else:
        print(json.dumps(report, indent=2))
    return 0 if report.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
