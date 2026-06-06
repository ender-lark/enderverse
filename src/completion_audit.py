#!/usr/bin/env python3
"""Non-mutating completion audit for the Investing OS build."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cloud_ops_status
import go_live_checklist
import live_status
import system_improvement_queue


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = ROOT / "src"


def _cloud_counts(cloud: dict[str, Any]) -> dict[str, Any]:
    summary = ((cloud.get("routine_receipts") or {}).get("summary") or {})
    due = cloud.get("routine_receipt_due") or {}
    next_due = due.get("next_due") or {}
    expected = int(summary.get("expected_count") or 0)
    scheduled = int(summary.get("scheduled_success_count") or 0)
    return {
        "scheduled_success": scheduled,
        "expected": expected,
        "missing_scheduled_success": int(summary.get("missing_scheduled_success_count") or 0),
        "failed_latest": int(summary.get("failed_latest_count") or 0),
        "live_run_proven": bool(cloud.get("live_run_proven")),
        "first_scheduled_run_proven": bool(cloud.get("first_scheduled_run_proven")),
        "next_due_name": next_due.get("routine_name") or next_due.get("routine_id") or "",
        "next_due_at": next_due.get("next_due_at") or "",
        "overdue_count": int(due.get("overdue_count") or 0),
        "due_waiting_count": int(due.get("due_waiting_count") or 0),
    }


def _next_recommended_action(
    *,
    checklist_summary: dict[str, Any],
    queue: dict[str, Any],
    cloud_counts: dict[str, Any],
    open_tickers: list[str],
) -> str:
    if checklist_summary.get("build_blocker_count"):
        blockers = ", ".join(checklist_summary.get("build_blockers") or [])
        return f"Fix build blocker(s): {blockers}."
    queue_next = queue.get("next") or []
    if queue_next:
        first = queue_next[0]
        return f"Promote queued slice: {first.get('id')} - {first.get('title')}."
    if cloud_counts.get("overdue_count"):
        return "Inspect overdue scheduled cloud receipt before changing code."
    if checklist_summary.get("waiting_on_source"):
        names = ", ".join(checklist_summary.get("waiting_on_source") or [])
        return f"No code blocker; wait for or supply source input: {names}."
    if cloud_counts.get("expected") and not cloud_counts.get("live_run_proven"):
        return "No code blocker; let remaining cloud routines prove naturally on schedule."
    if open_tickers:
        return "No build blocker; stock review backlog can wait until build work is explicitly resumed."
    return "No promoted build slice remains; wait for new evidence or user direction."


def _all_clear(
    *,
    build_clear: bool,
    checklist_summary: dict[str, Any],
    queue: dict[str, Any],
    cloud_summary: dict[str, Any],
    open_tickers: list[str],
    dark_lanes: list[str],
) -> bool:
    return (
        build_clear
        and not checklist_summary.get("waiting_on_source")
        and int(checklist_summary.get("monitoring_warning_count") or 0) == 0
        and int(queue.get("active_or_queued") or 0) == 0
        and bool(cloud_summary.get("live_run_proven"))
        and not open_tickers
        and not dark_lanes
    )


def build_completion_audit(*, src_dir: str | Path = DEFAULT_SRC) -> dict[str, Any]:
    src = Path(src_dir)
    live = live_status.live_status(src_dir=src)
    checklist = go_live_checklist.build_go_live_checklist(src_dir=src)
    cloud = cloud_ops_status.cloud_ops_status(src_dir=src)
    queue_payload = system_improvement_queue.load_queue(src / "system_improvement_queue.json")
    queue_problems = system_improvement_queue.validate_queue(queue_payload)
    queue = (
        {"valid": False, "problems": queue_problems, "items": 0, "active_or_queued": 0, "next": []}
        if queue_problems
        else {"valid": True, "problems": [], **system_improvement_queue.summary(queue_payload)}
    )
    checklist_summary = checklist.get("operator_summary") or {}
    cloud_summary = _cloud_counts(cloud)
    open_tickers = [
        str(ticker)
        for ticker in ((live.get("open_actions") or {}).get("tickers") or [])
        if ticker
    ]
    open_actions = live.get("open_actions") or {}
    open_review_due_count = int(open_actions.get("due_count") or 0)
    open_review_stale_count = int(open_actions.get("stale_count") or 0)
    open_review_oldest_age_days = int(open_actions.get("oldest_age_days") or 0)
    dark_lanes = [
        str(key)
        for key in ((live.get("dark_lanes") or {}).get("keys") or [])
        if key
    ]
    build_clear = (
        bool(live.get("go_live_ready"))
        and int(checklist_summary.get("build_blocker_count") or 0) == 0
        and int(checklist.get("fail_count") or 0) == 0
        and int(queue.get("active_or_queued") or 0) == 0
    )
    all_clear = _all_clear(
        build_clear=build_clear,
        checklist_summary=checklist_summary,
        queue=queue,
        cloud_summary=cloud_summary,
        open_tickers=open_tickers,
        dark_lanes=dark_lanes,
    )
    state = "blocked" if not build_clear and checklist_summary.get("build_blocker_count") else "build_clear"
    if build_clear and (
        checklist_summary.get("waiting_on_source")
        or not cloud_summary.get("live_run_proven")
        or open_tickers
    ):
        state = "build_clear_waiting_external"
    elif not build_clear and state != "blocked":
        state = "needs_build_work"
    return {
        "state": state,
        "build_clear": build_clear,
        "all_clear": all_clear,
        "go_live_ready": bool(live.get("go_live_ready")),
        "feed_generated_at": (live.get("data_flow") or {}).get("generated_at") or "",
        "actions": int(live.get("actions") or 0),
        "research_actions": int(live.get("research_actions") or 0),
        "build_blockers": checklist_summary.get("build_blockers") or [],
        "build_blocker_count": int(checklist_summary.get("build_blocker_count") or 0),
        "waiting_on_source": checklist_summary.get("waiting_on_source") or [],
        "waiting_on_source_count": int(checklist_summary.get("waiting_on_source_count") or 0),
        "waiting_on_schedule": checklist_summary.get("waiting_on_schedule") or [],
        "waiting_on_schedule_count": int(checklist_summary.get("waiting_on_schedule_count") or 0),
        "monitoring_warning_count": int(checklist_summary.get("monitoring_warning_count") or 0),
        "open_review_tickers": open_tickers,
        "open_review_count": len(open_tickers),
        "open_review_due_count": open_review_due_count,
        "open_review_stale_count": open_review_stale_count,
        "open_review_oldest_age_days": open_review_oldest_age_days,
        "dark_lanes": dark_lanes,
        "cloud": cloud_summary,
        "system_queue": queue,
        "next_recommended_action": _next_recommended_action(
            checklist_summary=checklist_summary,
            queue=queue,
            cloud_counts=cloud_summary,
            open_tickers=open_tickers,
        ),
    }


def format_text(report: dict[str, Any]) -> str:
    cloud = report.get("cloud") or {}
    queue = report.get("system_queue") or {}
    lines = [
        f"Completion audit: {str(report.get('state') or 'unknown').upper()}",
        (
            f"Build clear: {bool(report.get('build_clear'))} | "
            f"all clear: {bool(report.get('all_clear'))} | "
            f"go-live ready: {bool(report.get('go_live_ready'))} | "
            f"build blockers: {int(report.get('build_blocker_count') or 0)}"
        ),
        (
            f"Dashboard: actions={int(report.get('actions') or 0)} | "
            f"research_actions={int(report.get('research_actions') or 0)} | "
            f"feed={report.get('feed_generated_at') or 'missing'}"
        ),
        (
            f"Source waits: {int(report.get('waiting_on_source_count') or 0)}"
            + (f" ({', '.join(report.get('waiting_on_source') or [])})" if report.get("waiting_on_source") else "")
        ),
        (
            f"Cloud proof: {int(cloud.get('scheduled_success') or 0)}/"
            f"{int(cloud.get('expected') or 0)} scheduled | "
            f"live_run_proven={bool(cloud.get('live_run_proven'))} | "
            f"next={cloud.get('next_due_name') or 'none'} {cloud.get('next_due_at') or ''}".rstrip()
        ),
        (
            "Open reviews: "
            + (", ".join(report.get("open_review_tickers") or []) or "none")
            + (
                f" | due={int(report.get('open_review_due_count') or 0)}"
                f" | stale={int(report.get('open_review_stale_count') or 0)}"
                f" | oldest={int(report.get('open_review_oldest_age_days') or 0)}d"
                if report.get("open_review_tickers") else ""
            )
        ),
        (
            f"Queue: valid={bool(queue.get('valid'))} | items={int(queue.get('items') or 0)} | "
            f"active_or_queued={int(queue.get('active_or_queued') or 0)}"
        ),
        f"Next: {report.get('next_recommended_action') or 'none'}",
    ]
    blockers = report.get("build_blockers") or []
    if blockers:
        lines.append("Build blockers:")
        lines.extend(f"- {row}" for row in blockers)
    dark_lanes = report.get("dark_lanes") or []
    if dark_lanes:
        lines.append("Dark lanes:")
        lines.extend(f"- {row}" for row in dark_lanes)
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run a non-mutating Investing OS completion audit")
    parser.add_argument("--src-dir", default=str(DEFAULT_SRC))
    parser.add_argument("--format", choices=["json", "text"], default="json")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when build is not clear")
    parser.add_argument(
        "--require-all-clear",
        action="store_true",
        help="Exit non-zero until source waits, cloud proof waits, dark lanes, and open reviews are clear",
    )
    args = parser.parse_args(argv)
    report = build_completion_audit(src_dir=args.src_dir)
    if args.format == "text":
        print(format_text(report))
    else:
        print(json.dumps(report, indent=2))
    if args.require_all_clear and not report.get("all_clear"):
        return 3
    return 2 if args.strict and not report.get("build_clear") else 0


if __name__ == "__main__":
    raise SystemExit(main())
