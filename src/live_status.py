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
import open_opportunities
import system_improvement_queue as queue_mod


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


def format_text(status: dict[str, Any]) -> str:
    """Return a human-readable operator status without changing JSON output."""
    data_flow = status.get("data_flow") or {}
    preview = status.get("preview") or {}
    open_actions = status.get("open_actions") or {}
    dark_lanes = status.get("dark_lanes") or {}
    queue = status.get("system_queue") or {}
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
        f"Preview: {preview_url} ({preview_state})",
        f"Open review tickers: {_join_values(open_actions.get('tickers') or [])}",
        (
            f"Queue: valid={bool(queue.get('valid'))} | "
            f"items={int(queue.get('items') or 0)} | "
            f"active_or_queued={int(queue.get('active_or_queued') or 0)}"
        ),
    ]

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
