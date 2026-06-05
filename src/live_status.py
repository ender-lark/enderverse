#!/usr/bin/env python3
"""Print a compact live status summary without rebuilding or publishing."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import action_memory_resolve as action_resolver
import dashboard_preview_server as preview_server
import live_readiness
import live_source_capability
import open_opportunities
import system_improvement_queue as queue_mod
from event_risk import active_event_watch


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = ROOT / "src"


def _keys(rows: list[dict[str, Any]], key: str = "key") -> list[str]:
    return [
        str(row.get(key))
        for row in rows
        if isinstance(row, dict) and row.get(key)
    ]


def _open_actions_summary(store: dict[str, Any]) -> dict[str, Any]:
    rows = action_resolver.open_action_rows(store)
    review_rows = action_resolver.review_rows(store)
    return {
        "count": len(rows),
        "tickers": [row.get("ticker") for row in rows if row.get("ticker")],
        "rows": rows,
        "review_rows": review_rows,
    }


def _queue_summary(queue: dict[str, Any]) -> dict[str, Any]:
    problems = queue_mod.validate_queue(queue)
    summary = queue_mod.summary(queue) if not problems else {}
    return {
        "valid": not problems,
        "problems": problems,
        "items": summary.get("items", 0),
        "active_or_queued": summary.get("active_or_queued", 0),
        "next": summary.get("next", []),
    }


def _load_feed(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _data_flow_summary(readiness: dict[str, Any], feed: dict[str, Any] | None) -> dict[str, Any]:
    feed = feed or {}
    lane_counts = ((feed.get("lane_status") or {}).get("counts") or {})
    entries = (feed.get("staleness") or {}).get("entries") or []
    source_dates = {
        str(entry.get("source")): str(entry.get("date"))
        for entry in entries
        if isinstance(entry, dict) and entry.get("source") and entry.get("date")
    }
    actions = feed.get("actions") or []
    top_action = actions[0] if actions and isinstance(actions[0], dict) else {}
    return {
        "feed_present": bool(feed),
        "generated_at": feed.get("generated_at") or "",
        "staleness_stamp": (feed.get("staleness") or {}).get("stamp") or "",
        "source_dates": source_dates,
        "lanes_with_data": int(lane_counts.get("has_data") or 0),
        "dark_lanes": len(readiness.get("dark_lane_keys") or []),
        "dark_lane_keys": readiness.get("dark_lane_keys") or [],
        "stale_or_failed_lanes": readiness.get("stale_or_failed_lane_keys") or [],
        "actions": int(readiness.get("actions") or 0),
        "research_actions": int(readiness.get("research_actions") or 0),
        "top_action": {
            "ticker": top_action.get("ticker") or "",
            "kind": top_action.get("kind") or "",
            "what": top_action.get("what") or "",
            "action_state": top_action.get("action_state") or "",
        },
        "event_watch": active_event_watch(feed.get("event_risk") or []),
    }


def _source_call_summary(feed: dict[str, Any] | None) -> dict[str, Any]:
    feed = feed or {}
    feedback = feed.get("feedback") if isinstance(feed, dict) else {}
    source_calls = (feedback or {}).get("source_calls") if isinstance(feedback, dict) else {}
    if not isinstance(source_calls, dict):
        source_calls = {}
    return {
        "status": source_calls.get("status") or "not_checked",
        "line": source_calls.get("line") or "Source-call calibration not checked.",
        "observed_count": int(source_calls.get("observed_count") or 0),
        "pending_count": int(source_calls.get("pending_count") or 0),
        "overdue_count": int(source_calls.get("overdue_count") or 0),
        "oldest_overdue_days": int(source_calls.get("oldest_overdue_days") or 0),
        "calibration": source_calls.get("calibration") or {},
    }


def build_status_summary(
    *,
    readiness: dict[str, Any],
    preview: dict[str, Any],
    open_store: dict[str, Any],
    queue: dict[str, Any],
    feed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge existing evidence into one operator-facing status object."""
    open_actions = _open_actions_summary(open_store)
    queue_status = _queue_summary(queue)
    status = {
        "go_live_ready": bool(readiness.get("go_live_ready")),
        "rehearsal_ready": bool(readiness.get("rehearsal_ready")),
        "publish_ready": bool(readiness.get("publish_ready")),
        "required_inputs_ready": bool(readiness.get("required_inputs_ready")),
        "live_data_ready": bool(readiness.get("live_data_ready")),
        "actions": int(readiness.get("actions") or 0),
        "research_actions": int(readiness.get("research_actions") or 0),
        "dark_lanes": {
            "count": len(readiness.get("dark_lane_keys") or []),
            "keys": readiness.get("dark_lane_keys") or [],
            "details": readiness.get("dark_lane_details") or [],
        },
        "blockers": {
            "missing_required_inputs": _keys(readiness.get("missing_required_inputs") or []),
            "stale_required_inputs": _keys(readiness.get("stale_required_inputs") or []),
            "missing_minimum_live_inputs": _keys(readiness.get("missing_minimum_live_inputs") or []),
            "invalid_minimum_live_inputs": _keys(readiness.get("invalid_minimum_live_inputs") or []),
            "publish_gate_problems": readiness.get("publish_gate_problems") or [],
            "build_problem": readiness.get("build_problem") or "",
        },
        "open_actions": open_actions,
        "data_flow": _data_flow_summary(readiness, feed),
        "source_calls": _source_call_summary(feed),
        "source_capability": readiness.get("source_capability") or {},
        "preview": preview,
        "system_queue": queue_status,
        "next_steps": readiness.get("next_steps") or [],
    }
    if not status["go_live_ready"]:
        status["live_summary"] = "blocked"
    elif queue_status["active_or_queued"]:
        status["live_summary"] = "live_with_build_queue"
    elif open_actions["count"]:
        status["live_summary"] = "live_with_open_reviews"
    else:
        status["live_summary"] = "live_clear"
    return status


def live_status(
    *,
    src_dir: str | Path = DEFAULT_SRC,
    preview_dir: str | Path | None = None,
    queue_path: str | Path | None = None,
    open_store_path: str | Path | None = None,
    feed_path: str | Path | None = None,
) -> dict[str, Any]:
    src = Path(src_dir)
    preview_root = Path(preview_dir) if preview_dir else ROOT / "tmp"
    queue_file = Path(queue_path) if queue_path else src / "system_improvement_queue.json"
    open_file = Path(open_store_path) if open_store_path else src / "open_opportunities.json"
    feed_file = Path(feed_path) if feed_path else src / "latest_cockpit_feed.json"
    return build_status_summary(
        readiness=live_readiness.readiness_report(src),
        preview=preview_server.preview_status(directory=preview_root),
        open_store=open_opportunities.load_open_opportunities(open_file),
        queue=queue_mod.load_queue(queue_file),
        feed=_load_feed(feed_file),
    )


def _join_values(values: list[Any], *, empty: str = "none") -> str:
    cleaned = [str(value) for value in values if value]
    return ", ".join(cleaned) if cleaned else empty


def _dark_lane_commands(key: str) -> list[str]:
    live_source_command = (
        "python src/manual_source_drop.py docs/manual_live_source_drop.template.json "
        "--src-dir src --validate-only"
    )
    commands = {
        "account_positions": [live_source_command],
        "meridian": [live_source_command],
        "catalysts": [
            "python src/catalyst_calendar_intake.py <catalyst-calendar.json> --out src/catalysts.json --summary src/catalyst_intake_summary.json --merge-existing",
            "python src/manual_source_drop.py <manual-drop.json> --src-dir src --validate-only",
        ],
        "signal_log": [
            "python src/signal_log_intake.py <signal-log.json> --out src/signal_log.json --summary src/signal_log_intake_summary.json --merge-existing",
            "python src/manual_source_drop.py <manual-drop.json> --src-dir src --validate-only",
        ],
    }
    return commands.get(key, ["python src/manual_source_drop.py <manual-drop.json> --src-dir src --validate-only"])


def _dark_lane_templates(keys: list[str]) -> list[str]:
    templates = []
    if any(key in {"account_positions", "meridian"} for key in keys):
        templates.append("docs/manual_live_source_drop.template.json")
    if any(key not in {"account_positions", "meridian"} for key in keys):
        templates.append("docs/manual_drop.template.json")
    return templates or ["docs/manual_drop.template.json"]


def _sudden_event_command() -> str:
    return (
        'python src/sudden_event_refresh.py --title "<event headline>" '
        '--channels "oil,rates,volatility" --tickers "XOP,TNX" '
        '--why "<why exposure, hedges, or new-buy timing changes>" '
        '--trigger "<what confirms or changes the risk>"'
    )


def format_text(status: dict[str, Any]) -> str:
    """Return a human-readable operator status without changing JSON output."""
    data_flow = status.get("data_flow") or {}
    preview = status.get("preview") or {}
    open_actions = status.get("open_actions") or {}
    dark_lanes = status.get("dark_lanes") or {}
    queue = status.get("system_queue") or {}
    source_calls = status.get("source_calls") or {}
    source_capability = status.get("source_capability") or {}
    top_action = data_flow.get("top_action") or {}

    preview_url = preview.get("url") or "preview URL unavailable"
    preview_state = "running" if preview.get("server_running") else "not running"
    top_kind = top_action.get("kind") or "none"
    top_what = top_action.get("what") or ""
    top_text = top_kind if not top_what else f"{top_kind}: {top_what}"

    lines = [
        f"Live status: {status.get('live_summary', 'unknown')}",
        (
            f"Ready: {bool(status.get('go_live_ready'))} | "
            f"publish: {bool(status.get('publish_ready'))} | "
            f"live data: {bool(status.get('live_data_ready'))}"
        ),
        (
            f"Actions: {int(status.get('actions') or 0)} | "
            f"research actions: {int(status.get('research_actions') or 0)} | "
            f"open reviews: {int(open_actions.get('count') or 0)}"
        ),
        (
            f"Data flow: feed={data_flow.get('generated_at') or 'missing'} | "
            f"lanes_with_data={int(data_flow.get('lanes_with_data') or 0)} | "
            f"dark_lanes={int(data_flow.get('dark_lanes') or 0)} | "
            f"top_action={top_text}"
        ),
        (
            f"Source calls: {source_calls.get('status') or 'not_checked'} | "
            f"observed={int(source_calls.get('observed_count') or 0)} | "
            f"pending={int(source_calls.get('pending_count') or 0)} | "
            f"overdue={int(source_calls.get('overdue_count') or 0)}"
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
            f"missing={int((source_capability.get('live_source_config') or {}).get('missing_count') or 0)}"
        ),
    ]
    lines.extend(live_source_capability.format_missing_live_capable(source_capability))
    lines.extend(live_source_capability.format_missing_live_config(source_capability))
    event_watch = data_flow.get("event_watch") or {}
    if event_watch.get("active"):
        channels = _join_values(event_watch.get("channels") or [])
        tickers = _join_values(event_watch.get("tickers") or [])
        trigger = event_watch.get("trigger") or event_watch.get("summary") or "fresh confirmation needed"
        lines.append(
            f"Active event watch: {event_watch.get('severity') or 'watch'} | "
            f"{event_watch.get('title') or 'event risk'} | channels={channels} | "
            f"tickers={tickers} | trigger={trigger}"
        )
    else:
        lines.append("Active event watch: none supplied")
    lines.extend([
        f"Preview: {preview_url} ({preview_state})",
        f"Open review tickers: {_join_values(open_actions.get('tickers') or [])}",
        (
            f"Queue: valid={bool(queue.get('valid'))} | "
            f"items={int(queue.get('items') or 0)} | "
            f"active_or_queued={int(queue.get('active_or_queued') or 0)}"
        ),
    ])

    blockers = status.get("blockers") or {}
    blocker_parts = []
    for key in (
        "missing_required_inputs",
        "stale_required_inputs",
        "missing_minimum_live_inputs",
        "invalid_minimum_live_inputs",
    ):
        values = blockers.get(key) or []
        if values:
            blocker_parts.append(f"{key}={_join_values(values)}")
    if blockers.get("publish_gate_problems"):
        blocker_parts.append(f"publish_gate={len(blockers.get('publish_gate_problems') or [])}")
    if blockers.get("build_problem"):
        blocker_parts.append("build_problem=present")
    lines.append(f"Blockers: {'; '.join(blocker_parts) if blocker_parts else 'none'}")
    lines.append("Sudden event command:")
    lines.append(f"- {_sudden_event_command()}")

    review_rows = open_actions.get("review_rows") or []
    if review_rows:
        lines.append("Open review commands:")
        lines.append("- python src/action_memory_resolve.py --review-report")
        for row in review_rows[:5]:
            if not isinstance(row, dict):
                continue
            ticker = row.get("ticker") or "UNKNOWN"
            commands = row.get("commands") or {}
            defer = commands.get("defer") or ""
            ignore = commands.get("ignore") or ""
            acted = commands.get("acted") or ""
            if defer:
                lines.append(f"- {ticker} defer: {defer}")
            if ignore:
                lines.append(f"- {ticker} ignore: {ignore}")
            if acted:
                lines.append(f"- {ticker} acted: {acted}")

    details = dark_lanes.get("details") or []
    if details:
        lines.append("Dark lanes:")
        for row in details:
            if not isinstance(row, dict):
                continue
            key = row.get("label") or row.get("key") or "unknown"
            next_step = row.get("next_step") or row.get("missing_impact") or "Supply source input."
            lines.append(f"- {key}: {next_step}")
        lines.append("Dark lane intake commands:")
        dark_keys = [
            str(row.get("key") or "").strip()
            for row in details
            if isinstance(row, dict)
        ]
        for template in _dark_lane_templates(dark_keys):
            lines.append(f"- Start template: {template}")
        for row in details:
            if not isinstance(row, dict):
                continue
            label = row.get("label") or row.get("key") or "Dark lane"
            key = str(row.get("key") or "").strip()
            for command in _dark_lane_commands(key):
                lines.append(f"- {label}: {command}")
    else:
        lines.append("Dark lanes: none")

    next_steps = status.get("next_steps") or []
    if next_steps:
        lines.append("Next steps:")
        for step in next_steps[:5]:
            lines.append(f"- {step}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Print compact live status without rebuilding")
    parser.add_argument("--src-dir", default=str(DEFAULT_SRC))
    parser.add_argument("--preview-dir")
    parser.add_argument("--queue")
    parser.add_argument("--open-store")
    parser.add_argument("--feed")
    parser.add_argument("--format", choices=["json", "text"], default="json")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero unless go_live_ready is true")
    args = parser.parse_args(argv)

    status = live_status(
        src_dir=args.src_dir,
        preview_dir=args.preview_dir,
        queue_path=args.queue,
        open_store_path=args.open_store,
        feed_path=args.feed,
    )
    if args.format == "text":
        print(format_text(status))
    else:
        print(json.dumps(status, indent=2))
    return 0 if status["go_live_ready"] or not args.strict else 2


if __name__ == "__main__":
    raise SystemExit(main())
