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
    return {
        "count": len(rows),
        "tickers": [row.get("ticker") for row in rows if row.get("ticker")],
        "rows": rows,
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


def build_status_summary(
    *,
    readiness: dict[str, Any],
    preview: dict[str, Any],
    open_store: dict[str, Any],
    queue: dict[str, Any],
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
) -> dict[str, Any]:
    src = Path(src_dir)
    preview_root = Path(preview_dir) if preview_dir else ROOT / "tmp"
    queue_file = Path(queue_path) if queue_path else src / "system_improvement_queue.json"
    open_file = Path(open_store_path) if open_store_path else src / "open_opportunities.json"
    return build_status_summary(
        readiness=live_readiness.readiness_report(src),
        preview=preview_server.preview_status(directory=preview_root),
        open_store=open_opportunities.load_open_opportunities(open_file),
        queue=queue_mod.load_queue(queue_file),
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Print compact live status without rebuilding")
    parser.add_argument("--src-dir", default=str(DEFAULT_SRC))
    parser.add_argument("--preview-dir")
    parser.add_argument("--queue")
    parser.add_argument("--open-store")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero unless go_live_ready is true")
    args = parser.parse_args(argv)

    status = live_status(
        src_dir=args.src_dir,
        preview_dir=args.preview_dir,
        queue_path=args.queue,
        open_store_path=args.open_store,
    )
    print(json.dumps(status, indent=2))
    return 0 if status["go_live_ready"] or not args.strict else 2


if __name__ == "__main__":
    raise SystemExit(main())
