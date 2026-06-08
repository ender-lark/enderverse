#!/usr/bin/env python3
"""Operator go-live checklist assembled from repo-local evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import action_memory_resolve
import cloud_ops_status
import live_status
import manual_source_drop


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = ROOT / "src"


def _row(
    key: str,
    label: str,
    status: str,
    detail: str,
    command: str = "",
    category: str = "build",
) -> dict[str, str]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "detail": detail,
        "command": command,
        "category": category,
    }


def _status_from_bool(ok: bool, *, warn: bool = False) -> str:
    if ok:
        return "pass"
    return "warn" if warn else "fail"


def _open_review_detail(review: dict[str, Any]) -> str:
    if not review.get("open_count"):
        return "No open action-memory reviews."
    tickers = [
        str(row.get("ticker"))
        for row in review.get("rows") or []
        if isinstance(row, dict) and row.get("ticker")
    ]
    ticker_text = f" ({', '.join(tickers)})" if tickers else ""
    due = int(review.get("due_count") or 0)
    stale = int(review.get("stale_count") or 0)
    return (
        f"{review.get('open_count')} open review(s){ticker_text}; "
        f"{due} due; {stale} stale; oldest {review.get('oldest_age_days')} trading day(s)."
    )


def _open_review_row_status(review: dict[str, Any]) -> str:
    if not review.get("open_count"):
        return "pass"
    due = int(review.get("due_count") or 0)
    stale = int(review.get("stale_count") or 0)
    return "warn" if due or stale else "pass"


def _dark_lane_detail(status: dict[str, Any]) -> str:
    details = _dark_lane_details(status)
    if not details:
        dark = status.get("dark_lanes") or {}
        return "Dark lanes: " + ", ".join(dark.get("keys") or [])
    return _format_dark_lane_details(details)


def _dark_lane_details(status: dict[str, Any]) -> list[dict[str, Any]]:
    dark = status.get("dark_lanes") or {}
    return [
        row for row in dark.get("details") or []
        if isinstance(row, dict)
    ]


def _deferred_optional_keys(source_capability: dict[str, Any]) -> set[str]:
    return {
        str(key)
        for key in source_capability.get("missing_deferred_optional_keys") or []
        if key
    }


def _actionable_dark_lane_details(status: dict[str, Any], source_capability: dict[str, Any]) -> list[dict[str, Any]]:
    deferred = _deferred_optional_keys(source_capability)
    return [
        row for row in _dark_lane_details(status)
        if str(row.get("key") or "") not in deferred
    ]


def _deferred_dark_lane_details(status: dict[str, Any], source_capability: dict[str, Any]) -> list[dict[str, Any]]:
    deferred = _deferred_optional_keys(source_capability)
    return [
        row for row in _dark_lane_details(status)
        if str(row.get("key") or "") in deferred
    ]


def _format_dark_lane_details(details: list[dict[str, Any]]) -> str:
    if not details:
        return "None."
    parts = []
    for row in details:
        label = row.get("label") or row.get("key") or "Dark lane"
        next_step = row.get("next_step") or row.get("missing_impact") or "supply source input"
        parts.append(f"{label}: {next_step}")
    return "; ".join(parts)


def _source_call_row_status(source_calls: dict[str, Any]) -> str:
    state = str(source_calls.get("status") or "not_checked")
    observed = int(source_calls.get("observed_count") or 0)
    overdue = int(source_calls.get("overdue_count") or 0)
    calibration = source_calls.get("calibration") or {}
    if overdue:
        return "fail"
    if state == "not_checked" and observed:
        return "warn"
    if (calibration.get("status") or "") == "stale":
        return "warn"
    return "pass"


def _sudden_event_command() -> str:
    return (
        'python src/sudden_event_refresh.py --title "<event headline>" '
        '--channels "oil,rates,volatility" --tickers "XOP,TNX" '
        '--why "<why exposure, hedges, or new-buy timing changes>" '
        '--trigger "<what confirms or changes the risk>"'
    )


def _event_watch_detail(event_watch: dict[str, Any]) -> str:
    if not event_watch.get("active"):
        return "No supplied active event watch in the current feed."
    channels = ", ".join(str(v) for v in (event_watch.get("channels") or []) if v)
    tickers = ", ".join(str(v) for v in (event_watch.get("tickers") or []) if v)
    parts = [
        str(event_watch.get("severity") or "watch"),
        str(event_watch.get("title") or "event risk"),
    ]
    if channels:
        parts.append(f"channels={channels}")
    if tickers:
        parts.append(f"tickers={tickers}")
    trigger = event_watch.get("trigger") or event_watch.get("summary") or ""
    if trigger:
        parts.append(f"trigger={trigger}")
    return " | ".join(parts)


def _cloud_row_status(cloud: dict[str, Any]) -> str:
    if not cloud.get("schedule_ready_for_unattended_run"):
        return "fail"
    receipts = ((cloud.get("routine_receipts") or {}).get("summary") or {})
    due = cloud.get("routine_receipt_due") or {}
    if int(receipts.get("failed_latest_count") or 0) or int(due.get("overdue_count") or 0):
        return "warn"
    if cloud.get("first_scheduled_run_proven"):
        return "pass"
    return "pass"


def _cloud_row_detail(cloud: dict[str, Any]) -> str:
    receipts = ((cloud.get("routine_receipts") or {}).get("summary") or {})
    due = cloud.get("routine_receipt_due") or {}
    next_due = due.get("next_due") or {}
    next_label = next_due.get("routine_name") or next_due.get("routine_id") or "none"
    next_at = next_due.get("next_due_at") or ""
    return (
        f"state={cloud.get('cloud_operating_state') or 'unknown'}; "
        f"schedule_ready={bool(cloud.get('schedule_ready_for_unattended_run'))}; "
        f"first_scheduled_proof={bool(cloud.get('first_scheduled_run_proven'))}; "
        f"scheduled_success={int(receipts.get('scheduled_success_count') or 0)}/"
        f"{int(receipts.get('expected_count') or 0)}; "
        "mode=background_natural; "
        f"next={next_label} {next_at}".rstrip()
    )


def _cloud_row_category(cloud: dict[str, Any]) -> str:
    if not cloud.get("schedule_ready_for_unattended_run"):
        return "build"
    receipts = ((cloud.get("routine_receipts") or {}).get("summary") or {})
    due = cloud.get("routine_receipt_due") or {}
    if int(receipts.get("failed_latest_count") or 0) or int(due.get("overdue_count") or 0):
        return "monitoring"
    return "background_monitor"


def _source_capability_row_status(source_capability: dict[str, Any]) -> str:
    if not source_capability.get("valid", True):
        return "fail"
    if int(source_capability.get("missing_live_capable_count") or 0):
        return "warn"
    return "pass"


def _source_capability_row_detail(source_capability: dict[str, Any]) -> str:
    missing = [
        str(key)
        for key in source_capability.get("missing_live_capable_keys") or []
        if key
    ]
    detail = (
        f"inputs={int(source_capability.get('present_inputs') or 0)}/"
        f"{int(source_capability.get('total_inputs') or 0)}; "
        f"missing_live_capable={int(source_capability.get('missing_live_capable_count') or 0)}; "
        f"deferred_optional={int(source_capability.get('missing_deferred_optional_count') or 0)}"
    )
    if missing:
        detail += f" ({', '.join(missing)})"
    return detail


def _live_source_config(source_capability: dict[str, Any]) -> dict[str, Any]:
    return source_capability.get("live_source_config") or {}


def _live_source_config_row_status(source_capability: dict[str, Any]) -> str:
    config = _live_source_config(source_capability)
    if not config:
        return "warn"
    if int(config.get("missing_count") or 0):
        return "warn"
    return "pass"


def _live_source_config_row_detail(source_capability: dict[str, Any]) -> str:
    config = _live_source_config(source_capability)
    missing = [
        str(row.get("label") or row.get("key"))
        for row in config.get("missing") or []
        if isinstance(row, dict) and (row.get("label") or row.get("key"))
    ]
    detail = (
        f"configured={int(config.get('configured_count') or 0)}/"
        f"{int(config.get('total_count') or 0)}; "
        f"missing={int(config.get('missing_count') or 0)}"
    )
    if missing:
        detail += f" ({', '.join(missing)})"
    return detail


def _manual_drop_row_status(
    manual_report: dict[str, Any] | None,
    status: dict[str, Any],
    source_capability: dict[str, Any],
) -> str:
    if manual_report:
        return "pass" if manual_report.get("valid") else "warn"
    if int(source_capability.get("missing_live_capable_count") or 0):
        return "warn"
    if _actionable_dark_lane_details(status, source_capability):
        return "warn"
    return "pass"


def _manual_drop_row_detail(
    manual_report: dict[str, Any] | None,
    status: dict[str, Any],
    source_capability: dict[str, Any],
) -> str:
    if manual_report:
        return f"Validated supplied drop sections: {', '.join(manual_report.get('sections_seen') or [])}."
    missing_live = [
        str(key)
        for key in source_capability.get("missing_live_capable_keys") or []
        if key
    ]
    if missing_live:
        return (
            "No manual live-source drop supplied; use "
            f"docs/manual_live_source_drop.template.json for {', '.join(missing_live)}."
        )
    if _actionable_dark_lane_details(status, source_capability):
        return "No manual drop supplied; optional event/signal/catalyst lanes may remain dark."
    if _deferred_dark_lane_details(status, source_capability):
        return "No manual drop required for core go-live; queued optional lanes remain visible as not checked."
    return "No manual drop supplied; no dark lanes or missing live-capable inputs currently require one."


def _manual_drop_command(source_capability: dict[str, Any]) -> str:
    if int(source_capability.get("missing_live_capable_count") or 0):
        return (
            "validate: python src/manual_source_drop.py manual-live-source-drop.json "
            "--src-dir src --validate-only | "
            "apply: python src/manual_source_drop.py manual-live-source-drop.json "
            "--src-dir src"
        )
    return (
        "validate: python src/manual_source_drop.py <manual-drop.json> --src-dir src --validate-only | "
        "apply: python src/manual_source_drop.py <manual-drop.json> --src-dir src"
    )


def _operator_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Separate code blockers from expected waits and source gaps."""
    build_blockers = [
        row for row in rows
        if row.get("status") == "fail" and row.get("category") == "build"
    ]
    waiting_on_source = [
        row for row in rows
        if row.get("status") == "warn" and row.get("category") == "source_input"
    ]
    waiting_on_schedule = [
        row for row in rows
        if row.get("status") in {"pass", "warn"} and row.get("category") == "natural_schedule"
    ]
    review_backlog = [
        row for row in rows
        if row.get("status") == "warn" and row.get("category") == "review_backlog"
    ]
    monitoring = [
        row for row in rows
        if row.get("status") == "warn" and row.get("category") == "monitoring"
    ]
    background_monitors = [
        row for row in rows
        if row.get("category") == "background_monitor"
    ]
    source_wait_labels = _source_wait_labels(waiting_on_source)
    state = "blocked" if build_blockers else "build_ready"
    if not build_blockers and (waiting_on_source or waiting_on_schedule or review_backlog or monitoring):
        state = "build_ready_with_waits"
    return {
        "state": state,
        "build_blocker_count": len(build_blockers),
        "waiting_on_source_count": len(source_wait_labels),
        "waiting_on_schedule_count": len(waiting_on_schedule),
        "review_backlog_count": len(review_backlog),
        "monitoring_warning_count": len(monitoring),
        "background_monitor_count": len(background_monitors),
        "build_blockers": [row["label"] for row in build_blockers],
        "waiting_on_source": source_wait_labels,
        "waiting_on_schedule": [row["label"] for row in waiting_on_schedule],
        "review_backlog": [row["label"] for row in review_backlog],
        "monitoring": [row["label"] for row in monitoring],
        "background_monitors": [row["label"] for row in background_monitors],
    }


def _source_wait_labels(rows: list[dict[str, str]]) -> list[str]:
    labels = []
    for row in rows:
        text = f"{row.get('label', '')} {row.get('detail', '')}".lower()
        if "account_positions" in text or "account positions" in text:
            label = "Account Positions"
        elif "unusual whales" in text or "uw_api_key" in text:
            label = "Unusual Whales live fetch"
        else:
            label = row.get("label") or row.get("key") or "Source input"
        if label not in labels:
            labels.append(label)
    return labels


def _optional_dark_lane_command(status: dict[str, Any], source_capability: dict[str, Any]) -> str:
    keys = {
        str(key)
        for key in ((status.get("dark_lanes") or {}).get("keys") or [])
        if key
    }
    if keys and keys.issubset({"account_positions", "meridian"}):
        return _manual_drop_command(source_capability)
    return "python src/manual_source_drop.py <manual-drop.json> --src-dir src --validate-only"


def build_go_live_checklist(
    *,
    src_dir: str | Path = DEFAULT_SRC,
    manual_drop: str | Path | None = None,
) -> dict[str, Any]:
    src = Path(src_dir)
    status = live_status.live_status(src_dir=src)
    cloud = cloud_ops_status.cloud_ops_status(src_dir=src)
    review = action_memory_resolve.review_report(store_path=src / "open_opportunities.json")
    manual_report = None
    if manual_drop:
        manual_report = manual_source_drop.ingest_manual_source_drop(
            [manual_source_drop._read_json(manual_drop)],
            src_dir=src,
            dry_run=True,
        )
    preview = status.get("preview") or {}
    queue = status.get("system_queue") or {}
    data_flow = status.get("data_flow") or {}
    event_watch = data_flow.get("event_watch") or {}
    source_calls = status.get("source_calls") or {}
    source_capability = status.get("source_capability") or {}
    rows = [
        _row(
            "refresh",
            "Refresh dashboard artifacts",
            "pass" if status.get("go_live_ready") else "fail",
            "Run the live refresh before relying on the dashboard; current readiness is green."
            if status.get("go_live_ready")
            else "Readiness is blocked; run refresh/status and fix blockers before relying on the dashboard.",
            "python src/live_dashboard_refresh.py",
        ),
        _row(
            "status",
            "Live readiness status",
            _status_from_bool(bool(status.get("go_live_ready"))),
            f"{status.get('live_summary')}; actions={status.get('actions')}; research_actions={status.get('research_actions')}",
            "python src/live_status.py --format text",
        ),
        _row(
            "cloud_ops",
            "Cloud proof background monitor",
            _cloud_row_status(cloud),
            _cloud_row_detail(cloud),
            "python src/cloud_ops_status.py --format text",
            _cloud_row_category(cloud),
        ),
        _row(
            "data_flow",
            "Live data flow",
            _status_from_bool(
                bool(status.get("live_data_ready")) and bool(data_flow.get("feed_present")),
                warn=True,
            ),
            (
                f"feed={data_flow.get('generated_at') or 'missing'}; "
                f"lanes_with_data={data_flow.get('lanes_with_data', 0)}; "
                f"dark_lanes={data_flow.get('dark_lanes', 0)}; "
                f"top_action={data_flow.get('top_action', {}).get('kind') or 'none'}"
            ),
            "python src/live_status.py --format text",
        ),
        _row(
            "source_capability",
            "Live source coverage",
            _source_capability_row_status(source_capability),
            _source_capability_row_detail(source_capability),
            "python src/live_source_capability.py --format text",
            "source_input",
        ),
        _row(
            "live_source_config",
            "Live source configuration",
            _live_source_config_row_status(source_capability),
            _live_source_config_row_detail(source_capability),
            "python src/live_source_capability.py --format text",
            "source_input",
        ),
        _row(
            "preview",
            "Canonical JSX cockpit",
            _status_from_bool(bool(preview.get("preview_exists") and preview.get("server_running")), warn=True),
            preview.get("canonical_url") or preview.get("url") or "Canonical JSX cockpit URL unavailable.",
            "python src/dashboard_preview_server.py --check",
        ),
        _row(
            "source_calls",
            "Source-call calibration",
            _source_call_row_status(source_calls),
            source_calls.get("line") or "Source-call calibration not checked.",
            "python src/live_status.py --format text",
            "build" if _source_call_row_status(source_calls) == "fail" else "monitoring",
        ),
        _row(
            "manual_drop",
            "Manual source drop",
            _manual_drop_row_status(manual_report, status, source_capability),
            _manual_drop_row_detail(manual_report, status, source_capability),
            _manual_drop_command(source_capability),
            "source_input",
        ),
        _row(
            "sudden_event",
            "Sudden event refresh",
            "pass",
            "One supplied market-moving headline can be appended to Event Risk and pushed through the live dashboard refresh.",
            _sudden_event_command(),
        ),
        _row(
            "event_watch",
            "Active event watch",
            "pass" if event_watch.get("active") else "warn",
            _event_watch_detail(event_watch),
            _sudden_event_command(),
            "monitoring",
        ),
        _row(
            "open_reviews",
            "Open action reviews",
            _open_review_row_status(review),
            _open_review_detail(review),
            "python src/action_memory_resolve.py --review-report",
            "review_backlog",
        ),
        _row(
            "queue",
            "Implementation queue",
            _status_from_bool(bool(queue.get("valid")) and not bool(queue.get("active_or_queued")), warn=True),
            f"{queue.get('items', 0)} item(s), {queue.get('active_or_queued', 0)} active/queued.",
            "python src/system_improvement_queue.py",
        ),
    ]
    actionable_dark = _actionable_dark_lane_details(status, source_capability)
    deferred_dark = _deferred_dark_lane_details(status, source_capability)
    if actionable_dark:
        rows.append(_row(
            "dark_lanes",
            "Optional dark lanes",
            "warn",
            _format_dark_lane_details(actionable_dark),
            _optional_dark_lane_command(status, source_capability),
            "source_input",
        ))
    if deferred_dark:
        rows.append(_row(
            "deferred_dark_lanes",
            "Deferred optional dark lanes",
            "pass",
            _format_dark_lane_details(deferred_dark),
            "Keep visible as not checked; do not treat absence as checked clear.",
            "background_monitor",
        ))
    fail_count = sum(1 for row in rows if row["status"] == "fail")
    warn_count = sum(1 for row in rows if row["status"] == "warn")
    operator_summary = _operator_summary(rows)
    return {
        "go_live_ready": bool(status.get("go_live_ready")) and fail_count == 0,
        "status": "fail" if fail_count else "warn" if warn_count else "pass",
        "fail_count": fail_count,
        "warn_count": warn_count,
        "operator_summary": operator_summary,
        "rows": rows,
        "preview_url": preview.get("url") or "",
        "manual_drop_checked": manual_report is not None,
    }


def format_text(report: dict[str, Any]) -> str:
    lines = [
        f"Go-live checklist: {str(report.get('status') or '').upper()}",
        f"Ready: {bool(report.get('go_live_ready'))} | failures: {report.get('fail_count', 0)} | warnings: {report.get('warn_count', 0)}",
    ]
    summary = report.get("operator_summary") or {}
    if summary:
        build_label = "blocked" if summary.get("build_blocker_count") else "no build blockers"
        lines.append(
            "Build status: "
            f"{summary.get('state') or 'unknown'} | {build_label} | "
            f"source waits={summary.get('waiting_on_source_count', 0)} | "
            f"schedule waits={summary.get('waiting_on_schedule_count', 0)} | "
            f"background monitors={summary.get('background_monitor_count', 0)} | "
            f"review backlog={summary.get('review_backlog_count', 0)}"
        )
    preview_url = report.get("preview_url") or ""
    if preview_url:
        lines.append(f"Preview: {preview_url}")
    lines.append("")
    for row in report.get("rows") or []:
        status = str(row.get("status") or "").upper()
        label = row.get("label") or row.get("key") or "Checklist item"
        detail = row.get("detail") or ""
        command = row.get("command") or ""
        lines.append(f"[{status}] {label}: {detail}")
        if command:
            lines.append(f"  command: {command}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Print non-mutating go-live operator checklist")
    parser.add_argument("--src-dir", default=str(DEFAULT_SRC))
    parser.add_argument("--manual-drop", help="Optional manual source-drop JSON to validate without writing")
    parser.add_argument("--format", choices=["json", "text"], default="json")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on warnings as well as failures")
    args = parser.parse_args(argv)

    report = build_go_live_checklist(src_dir=args.src_dir, manual_drop=args.manual_drop)
    if args.format == "text":
        print(format_text(report))
    else:
        print(json.dumps(report, indent=2))
    if report["fail_count"]:
        return 2
    if args.strict and report["warn_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
