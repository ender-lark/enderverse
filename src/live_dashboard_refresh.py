#!/usr/bin/env python3
"""Run the repo-local live dashboard refresh sequence.

Source intake remains separate. This command takes whatever convention files
are present in `src/`, rebuilds the feed, refreshes repo-evidence synthesis from
that feed, rebuilds again, and renders the dashboard artifacts.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from live_readiness import readiness_report


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = ROOT / "src"


@dataclass(frozen=True)
class Step:
    name: str
    command: list[str]


def _rel(path: str | Path) -> str:
    p = Path(path)
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def refresh_plan(
    *,
    src_dir: str | Path = DEFAULT_SRC,
    feed_out: str | Path | None = None,
    jsx_out: str | Path | None = None,
    html_out: str | Path | None = None,
    preview_out: str | Path | None = None,
    parity_out: str | Path | None = None,
    publish: bool = True,
) -> list[Step]:
    src = Path(src_dir)
    feed = Path(feed_out) if feed_out else src / "latest_cockpit_feed.json"
    jsx = Path(jsx_out) if jsx_out else src / "rendered" / "conviction_cockpit_v5.jsx"
    html = Path(html_out) if html_out else ROOT / "docs" / "index.html"
    preview = Path(preview_out) if preview_out else ROOT / "tmp" / "dashboard_preview.html"
    parity = Path(parity_out) if parity_out else ROOT / "tmp" / "dashboard_parity_feed.json"
    py = sys.executable or "python"

    build_cmd = [py, "src/full_build_runner.py", "--src-dir", _rel(src), "--feed-out", _rel(feed)]
    if publish:
        build_cmd.append("--publish")

    return [
        Step("heartbeat_pre_synthesis", [
            py, "src/heartbeat_status.py", "--src-dir", _rel(src),
            "--out", _rel(src / "heartbeat.json"),
            "--summary", _rel(src / "heartbeat_summary.json"),
        ]),
        Step("build_publish_pre_synthesis", build_cmd),
        Step("repo_evidence_synthesis", [
            py, "src/daily_synthesis_from_feed.py",
            "--feed", _rel(feed),
            "--out", _rel(src / "daily_synthesis.json"),
            "--summary", _rel(src / "daily_synthesis_intake_summary.json"),
        ]),
        Step("heartbeat_post_synthesis", [
            py, "src/heartbeat_status.py", "--src-dir", _rel(src),
            "--out", _rel(src / "heartbeat.json"),
            "--summary", _rel(src / "heartbeat_summary.json"),
        ]),
        Step("build_publish_final", build_cmd),
        Step("render_canonical_jsx", [
            py, "src/render_cockpit.py", _rel(feed), "--out", _rel(jsx),
        ]),
        Step("render_summary_html", [
            py, "src/cockpit_html_gen.py", _rel(feed), "--out", _rel(html),
        ]),
        Step("render_preview_html", [
            py, "src/cockpit_html_gen.py", _rel(feed), "--out", _rel(preview),
        ]),
        Step("write_parity_feed", [
            py, "src/full_build_runner.py", "--src-dir", _rel(src), "--feed-out", _rel(parity),
        ]),
    ]


def _step_dict(step: Step) -> dict[str, object]:
    return {"name": step.name, "command": step.command}


def run_steps(steps: list[Step]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for step in steps:
        print(f"\n== {step.name} ==", flush=True)
        print("+ " + " ".join(step.command), flush=True)
        proc = subprocess.run(step.command, cwd=ROOT)
        row = {"name": step.name, "returncode": proc.returncode}
        results.append(row)
        if proc.returncode != 0:
            raise SystemExit(proc.returncode)
    return results


def _readiness_brief(report: dict | None) -> dict:
    if not report:
        return {}
    return {
        "go_live_ready": bool(report.get("go_live_ready")),
        "publish_ready": bool(report.get("publish_ready")),
        "required_inputs_ready": bool(report.get("required_inputs_ready")),
        "live_data_ready": bool(report.get("live_data_ready")),
        "missing_required_inputs": [
            row.get("key") for row in report.get("missing_required_inputs") or [] if isinstance(row, dict)
        ],
        "stale_required_inputs": [
            row.get("key") for row in report.get("stale_required_inputs") or [] if isinstance(row, dict)
        ],
        "invalid_minimum_live_inputs": [
            row.get("key") for row in report.get("invalid_minimum_live_inputs") or [] if isinstance(row, dict)
        ],
        "next_steps": (report.get("next_steps") or [])[:5],
    }


def build_refresh_summary(
    feed_path: str | Path,
    *,
    preview_out: str | Path | None = None,
    readiness: dict | None = None,
) -> dict:
    feed_file = Path(feed_path)
    feed = json.loads(feed_file.read_text(encoding="utf-8"))
    lane_status = feed.get("lane_status") if isinstance(feed, dict) else {}
    counts = lane_status.get("counts") if isinstance(lane_status, dict) else {}
    rows = lane_status.get("rows") if isinstance(lane_status, dict) else []
    dark_rows = [
        {
            "key": r.get("key") or "",
            "label": r.get("label") or "",
            "next_step": r.get("next_step") or "",
            "missing_impact": r.get("missing_impact") or "",
        }
        for r in rows or []
        if isinstance(r, dict) and r.get("status") == "not_checked"
    ]
    actions = [
        {
            "ticker": a.get("ticker"),
            "kind": a.get("kind") or "",
            "action_state": a.get("action_state") or a.get("urgency") or "",
            "what": a.get("what") or a.get("headline") or "",
        }
        for a in (feed.get("actions") or [])
        if isinstance(a, dict)
    ]
    feedback = feed.get("feedback") if isinstance(feed, dict) else {}
    source_calls = (feedback or {}).get("source_calls") if isinstance(feedback, dict) else {}
    staleness = feed.get("staleness") if isinstance(feed, dict) else {}
    return {
        "feed": _rel(feed_file),
        "preview": _rel(preview_out) if preview_out else "",
        "generated_at": feed.get("generated_at") or "",
        "data_flow": {
            "staleness_stamp": (staleness or {}).get("stamp") or "",
            "lanes_with_data": int((counts or {}).get("has_data") or 0),
            "dark_lanes": int((counts or {}).get("not_checked") or 0),
            "dark_lane_keys": [r["key"] for r in dark_rows if r.get("key")],
        },
        "actions": {
            "count": len(actions),
            "top": actions[:5],
        },
        "source_calls": {
            "status": (source_calls or {}).get("status") or "not_checked",
            "line": (source_calls or {}).get("line") or "Source calls not checked.",
            "observed_count": int((source_calls or {}).get("observed_count") or 0),
        },
        "readiness": _readiness_brief(readiness),
        "dark_lane_details": dark_rows[:5],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Refresh repo-local live dashboard artifacts")
    parser.add_argument("--src-dir", default=str(DEFAULT_SRC))
    parser.add_argument("--feed-out")
    parser.add_argument("--jsx-out")
    parser.add_argument("--html-out")
    parser.add_argument("--preview-out")
    parser.add_argument("--parity-out")
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    steps = refresh_plan(
        src_dir=args.src_dir,
        feed_out=args.feed_out,
        jsx_out=args.jsx_out,
        html_out=args.html_out,
        preview_out=args.preview_out,
        parity_out=args.parity_out,
        publish=not args.no_publish,
    )
    if args.dry_run:
        print(json.dumps({"steps": [_step_dict(step) for step in steps]}, indent=2))
        return 0
    results = run_steps(steps)
    feed = Path(args.feed_out) if args.feed_out else Path(args.src_dir) / "latest_cockpit_feed.json"
    preview = Path(args.preview_out) if args.preview_out else ROOT / "tmp" / "dashboard_preview.html"
    readiness = readiness_report(args.src_dir)
    summary = build_refresh_summary(feed, preview_out=preview, readiness=readiness)
    print(json.dumps({"refreshed": True, "steps": results, "summary": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
