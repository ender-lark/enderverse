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
    print(json.dumps({"refreshed": True, "steps": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
