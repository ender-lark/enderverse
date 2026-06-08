#!/usr/bin/env python3
"""Run the Investing OS cloud routine stack immediately with manual receipts."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import catalyst_calendar_intake
import cloud_ops_status
import cloud_routine_receipts


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECEIPTS = ROOT / "src" / "cloud_routine_receipts.json"


@dataclass(frozen=True)
class Step:
    label: str
    command: list[str] | None = None
    check: Callable[[Path], dict[str, Any]] | None = None
    optional: bool = False


@dataclass(frozen=True)
class Routine:
    routine_id: str
    summary: str
    steps: list[Step]


def _python(*args: str) -> list[str]:
    return [sys.executable, *args]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_catalysts(repo: Path) -> dict[str, Any]:
    path = repo / "src" / "catalysts.json"
    if not path.is_file():
        return {"valid": False, "problem": "src/catalysts.json missing"}
    payload = _read_json(path)
    rows = payload if isinstance(payload, list) else []
    valid_rows = [
        catalyst_calendar_intake.normalize_catalyst_row(row)
        for row in rows
        if isinstance(row, dict)
    ]
    valid_rows = [row for row in valid_rows if row]
    return {
        "valid": len(valid_rows) == len(rows) and bool(valid_rows),
        "rows": len(rows),
        "valid_rows": len(valid_rows),
        "problem": "" if valid_rows else "no valid catalyst rows",
    }


def _validate_json_list_or_object(repo: Path, rel_path: str, key: str | None = None) -> dict[str, Any]:
    path = repo / rel_path
    if not path.is_file():
        return {"valid": False, "problem": f"{rel_path} missing"}
    payload = _read_json(path)
    rows = payload.get(key) if key and isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return {"valid": False, "problem": f"{rel_path} must contain a list"}
    return {"valid": True, "rows": len(rows)}


def _bundle_has_observations(path: Path, *, key: str = "observations") -> bool:
    if not path.is_file():
        return False
    try:
        payload = _read_json(path)
    except Exception:
        return False
    if key == "tickers":
        rows = payload.get("tickers") if isinstance(payload, dict) else {}
        return bool(rows)
    observations = payload.get("observations") if isinstance(payload, dict) else {}
    return bool(observations)


def default_routines(repo: Path = ROOT) -> list[Routine]:
    opportunity_bundle = repo / "tmp" / "uw" / "opportunity_bundle.json"
    parabolic_bundle = repo / "tmp" / "uw" / "parabolic_bundle.json"
    opportunity_steps = [
        Step("uw opportunity self-test", _python("src/uw_opportunity_scan.py", "--self-test")),
        Step("uw opportunity cache validate", check=lambda r: _validate_json_list_or_object(
            r, "src/uw_opportunity_signals.json", key="signals"
        )),
        Step("live source config validate", _python("src/live_source_config_update.py", "--validate", "src/live_source_config.json")),
    ]
    if _bundle_has_observations(opportunity_bundle):
        opportunity_steps.append(Step(
            "uw opportunity existing bundle score",
            _python(
                "src/uw_opportunity_scan.py",
                "--from-bundle",
                "tmp/uw/opportunity_bundle.json",
                "--emit",
                "src/uw_opportunity_signals.json",
            ),
        ))
    else:
        opportunity_steps.append(Step(
            "uw opportunity bundle skipped",
            check=lambda _r: {"valid": True, "skipped": True, "reason": "tmp/uw/opportunity_bundle.json missing or empty"},
            optional=True,
        ))

    parabolic_steps = [
        Step("parabolic self-test", _python("src/parabolic_setup_screener.py", "--self-test")),
        Step("parabolic cache validate", check=lambda r: _validate_json_list_or_object(
            r, "src/parabolic_setups.json", key="results"
        )),
    ]
    if _bundle_has_observations(parabolic_bundle, key="tickers"):
        parabolic_steps.append(Step(
            "parabolic existing bundle score",
            _python(
                "src/parabolic_setup_screener.py",
                "--from-bundle",
                "tmp/uw/parabolic_bundle.json",
                "--emit",
                "src/parabolic_setups.json",
            ),
        ))
    else:
        parabolic_steps.append(Step(
            "parabolic bundle skipped",
            check=lambda _r: {"valid": True, "skipped": True, "reason": "tmp/uw/parabolic_bundle.json missing or empty"},
            optional=True,
        ))

    return [
        Routine(
            "investing-os-pre-market-source-intake",
            "pre-market source intake manual run completed; missing account/meridian inputs remain dark",
            [
                Step("fundstrat cache validate", _python("src/fundstrat_email_intake.py", "--validate", "src")),
                Step("event risk validate", _python("src/event_risk_intake.py", "--validate", "src/event_risks.json")),
                Step("catalyst cache validate", check=_validate_catalysts),
            ],
        ),
        Routine(
            "investing-os-morning-scan",
            "morning scan manual run completed; Signal Log remains watch-only",
            [
                Step("signal log validate", _python("src/signal_log_intake.py", "--validate", "src/signal_log.json")),
                Step("macro cache validate", _python("src/macro_pulse_scan.py", "--validate", "src/macro_state.json")),
            ],
        ),
        Routine(
            "investing-os-early-cockpit-build",
            "early cockpit build manual run refreshed dashboard artifacts",
            [Step("early live dashboard refresh", _python("src/live_dashboard_refresh.py"))],
        ),
        Routine(
            "investing-os-daily-synthesis",
            "daily synthesis manual run completed from current cockpit feed evidence",
            [
                Step(
                    "daily synthesis from feed",
                    _python(
                        "src/daily_synthesis_from_feed.py",
                        "--feed",
                        "src/latest_cockpit_feed.json",
                        "--out",
                        "src/daily_synthesis.json",
                        "--summary",
                        "src/daily_synthesis_intake_summary.json",
                    ),
                ),
                Step("daily synthesis validate", _python("src/daily_synthesis_intake.py", "--validate", "src/daily_synthesis.json")),
            ],
        ),
        Routine("investing-os-uw-opportunity-cache", "UW opportunity cache manual run completed", opportunity_steps),
        Routine("investing-os-parabolic-cache", "parabolic cache manual run completed", parabolic_steps),
        Routine(
            "investing-os-full-cockpit-build",
            "full cockpit build manual run refreshed dashboard artifacts",
            [Step("live dashboard refresh", _python("src/live_dashboard_refresh.py"))],
        ),
        Routine(
            "investing-os-post-close-refresh",
            "post-close manual run refreshed dashboard artifacts",
            [Step("post-close dashboard refresh", _python("src/live_dashboard_refresh.py"))],
        ),
        Routine(
            "investing-os-off-hours-worker",
            "off-hours worker manual run checked research queue cache only",
            [Step("research queue validate", _python("src/research_queue_intake.py", "--validate", "src/research_queue.json"))],
        ),
        Routine(
            "investing-os-deep-synthesis",
            "deep synthesis manual support run completed from repo evidence",
            [
                Step("daily synthesis validate", _python("src/daily_synthesis_intake.py", "--validate", "src/daily_synthesis.json")),
                Step(
                    "source call candidates merge",
                    _python(
                        "src/source_call_candidate_draft.py",
                        "--feed",
                        "src/latest_cockpit_feed.json",
                        "--out",
                        "src/source_call_candidates.json",
                        "--merge-existing",
                        "--merge-cache",
                    ),
                ),
            ],
        ),
        Routine(
            "investing-os-weekly-pilot-run",
            "weekly pilot manual support run checked routine heartbeat/status evidence",
            [
                Step("heartbeat status write", _python("src/heartbeat_status.py", "--src-dir", "src", "--out", "src/heartbeat.json", "--summary", "src/heartbeat_summary.json")),
                Step("heartbeat validate", _python("src/heartbeat_status.py", "--validate", "src/heartbeat.json")),
            ],
        ),
    ]


def _run_step(step: Step, repo: Path) -> dict[str, Any]:
    if step.check:
        result = step.check(repo)
        return {
            "label": step.label,
            "returncode": 0 if result.get("valid") else 2,
            "optional": step.optional,
            "check": result,
        }
    if not step.command:
        return {"label": step.label, "returncode": 0, "optional": step.optional}
    proc = subprocess.run(step.command, cwd=repo, text=True, capture_output=True)
    return {
        "label": step.label,
        "command": step.command,
        "returncode": proc.returncode,
        "optional": step.optional,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def _routine_map(routines: list[Routine]) -> dict[str, Routine]:
    return {routine.routine_id: routine for routine in routines}


def run_manual_stack(
    *,
    routine_ids: list[str] | None = None,
    repo: str | Path = ROOT,
    receipt_path: str | Path = DEFAULT_RECEIPTS,
    routines: list[Routine] | None = None,
    write_receipts: bool = True,
) -> dict[str, Any]:
    repo_path = Path(repo)
    all_routines = routines if routines is not None else default_routines(repo_path)
    selected = all_routines
    if routine_ids:
        lookup = _routine_map(all_routines)
        missing = [routine_id for routine_id in routine_ids if routine_id not in lookup]
        if missing:
            return {"valid": False, "problems": [f"unknown routine id: {routine_id}" for routine_id in missing], "routines": []}
        selected = [lookup[routine_id] for routine_id in routine_ids]

    reports: list[dict[str, Any]] = []
    for routine in selected:
        if write_receipts:
            cloud_routine_receipts.append_receipt(
                path=receipt_path,
                routine_id=routine.routine_id,
                status="started",
                run_source="manual",
                summary=f"{routine.routine_id} manual run started",
            )
        step_reports = [_run_step(step, repo_path) for step in routine.steps]
        failures = [
            step for step in step_reports
            if int(step.get("returncode") or 0) != 0 and not step.get("optional")
        ]
        status = "failed" if failures else "success"
        summary = routine.summary if status == "success" else f"{routine.routine_id} manual run failed"
        details = {"steps": step_reports}
        if write_receipts:
            cloud_routine_receipts.append_receipt(
                path=receipt_path,
                routine_id=routine.routine_id,
                status=status,
                run_source="manual",
                summary=summary,
                details=details,
            )
        reports.append({
            "routine_id": routine.routine_id,
            "status": status,
            "summary": summary,
            "steps": step_reports,
        })

    failed = [row for row in reports if row.get("status") == "failed"]
    return {
        "valid": not failed,
        "run_source": "manual",
        "receipt_path": str(receipt_path),
        "routine_count": len(reports),
        "success_count": len(reports) - len(failed),
        "failed_count": len(failed),
        "routines": reports,
        "scheduled_proof_note": (
            "Manual receipts prove the routine paths can run now; they do not "
            "satisfy scheduled cloud proof."
        ),
    }


def format_text(report: dict[str, Any]) -> str:
    lines = [
        f"Manual cloud routine run valid: {bool(report.get('valid'))}",
        (
            "Routines: "
            f"success={int(report.get('success_count') or 0)}/"
            f"{int(report.get('routine_count') or 0)} | "
            f"failed={int(report.get('failed_count') or 0)}"
        ),
        f"Receipt source: {report.get('run_source') or 'manual'}",
        str(report.get("scheduled_proof_note") or ""),
    ]
    for routine in report.get("routines") or []:
        lines.append(f"- {routine.get('routine_id')}: {routine.get('status')}")
        failed_steps = [
            step for step in routine.get("steps") or []
            if int(step.get("returncode") or 0) != 0 and not step.get("optional")
        ]
        for step in failed_steps:
            lines.append(f"  failed step: {step.get('label')} rc={step.get('returncode')}")
    if report.get("problems"):
        lines.append("Problems:")
        lines.extend(f"- {problem}" for problem in report.get("problems") or [])
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run cloud routines immediately with manual receipts")
    parser.add_argument("--routine-id", action="append", help="Limit to one routine id; repeatable")
    parser.add_argument("--receipt-path", default=str(DEFAULT_RECEIPTS))
    parser.add_argument("--repo", default=str(ROOT))
    parser.add_argument("--no-receipts", action="store_true")
    parser.add_argument("--format", choices=["json", "text"], default="json")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--list", action="store_true", help="List routine ids and exit")
    args = parser.parse_args(argv)

    if args.list:
        rows = [{
            "routine_id": row["automation_id"],
            "routine_name": row["automation_name"],
            "schedule": row["schedule"],
        } for row in cloud_ops_status.DEFAULT_EXPECTED_AUTOMATIONS]
        print(json.dumps(rows, indent=2))
        return 0

    report = run_manual_stack(
        routine_ids=args.routine_id,
        repo=args.repo,
        receipt_path=args.receipt_path,
        write_receipts=not args.no_receipts,
    )
    if args.format == "text":
        print(format_text(report))
    else:
        print(json.dumps(report, indent=2))
    if args.strict and not report.get("valid"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
