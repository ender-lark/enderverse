#!/usr/bin/env python3
"""Append one supplied sudden event and refresh the live dashboard."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
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


def sudden_event_plan(
    *,
    title: str,
    why: str,
    trigger: str,
    channels: str = "",
    tickers: str = "",
    affected: str = "",
    severity: str = "high",
    horizon: str = "daily",
    direction: str = "risk_watch",
    source: str = "Supplied sudden-event note",
    event_date: str | None = None,
    src_dir: str | Path = DEFAULT_SRC,
) -> list[Step]:
    """Build the command sequence for headline-to-dashboard refresh."""
    src = Path(src_dir)
    as_of = event_date or date.today().isoformat()
    py = sys.executable or "python"
    intake = [
        py,
        "src/event_risk_intake.py",
        "--title",
        title,
        "--why",
        why,
        "--trigger",
        trigger,
        "--severity",
        severity,
        "--horizon",
        horizon,
        "--direction",
        direction,
        "--source",
        source,
        "--date",
        as_of,
        "--out",
        _rel(src / "event_risks.json"),
        "--summary",
        _rel(src / "event_risk_intake_summary.json"),
        "--merge-existing",
    ]
    if channels:
        intake.extend(["--channels", channels])
    if tickers:
        intake.extend(["--tickers", tickers])
    if affected:
        intake.extend(["--affected", affected])
    return [
        Step("event_risk_intake", intake),
        Step("live_dashboard_refresh", [py, "src/live_dashboard_refresh.py", "--src-dir", _rel(src)]),
        Step("live_status", [py, "src/live_status.py", "--src-dir", _rel(src), "--format", "text"]),
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
    parser = argparse.ArgumentParser(description="Append a supplied sudden event and refresh the dashboard")
    parser.add_argument("--title", required=True, help="Short supplied event headline")
    parser.add_argument("--why", required=True, help="Why it matters for exposure, hedges, or new-buy timing")
    parser.add_argument("--trigger", required=True, help="What would confirm or change the risk")
    parser.add_argument("--channels", default="", help="Comma/semicolon separated affected channels")
    parser.add_argument("--tickers", default="", help="Comma/semicolon separated symbols or ETFs")
    parser.add_argument("--affected", default="", help="Comma/semicolon separated affected sleeves")
    parser.add_argument("--severity", default="high", choices=["critical", "high", "medium", "low"])
    parser.add_argument("--horizon", default="daily")
    parser.add_argument("--direction", default="risk_watch")
    parser.add_argument("--source", default="Supplied sudden-event note")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--src-dir", default=str(DEFAULT_SRC))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    steps = sudden_event_plan(
        title=args.title,
        why=args.why,
        trigger=args.trigger,
        channels=args.channels,
        tickers=args.tickers,
        affected=args.affected,
        severity=args.severity,
        horizon=args.horizon,
        direction=args.direction,
        source=args.source,
        event_date=args.date,
        src_dir=args.src_dir,
    )
    if args.dry_run:
        print(json.dumps({"steps": [_step_dict(step) for step in steps]}, indent=2))
        return 0
    results = run_steps(steps)
    print(json.dumps({"refreshed": True, "steps": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
