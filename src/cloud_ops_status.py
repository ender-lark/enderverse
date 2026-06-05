#!/usr/bin/env python3
"""Report whether the Investing OS daily cloud routine can operate unattended."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import codex_routine_manifest
import cloud_routine_receipts
import live_status as live_status_mod


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = ROOT / "src"
DEFAULT_AUTOMATION_NAME = "Investing OS Daily Cloud Refresh"
DEFAULT_AUTOMATION_ID = "investing-os-daily-cloud-refresh"
DEFAULT_AUTOMATION_PROOF = "cloud_automation_status.json"
DEFAULT_RECEIPT_PROOF = "cloud_routine_receipts.json"
DEFAULT_EXPECTED_AUTOMATIONS = [
    {
        "automation_id": "investing-os-pre-market-source-intake",
        "automation_name": "Investing OS Pre-Market Source Intake",
        "role": "pre_market_source_intake",
        "schedule": "market weekdays 8:10 AM ET",
    },
    {
        "automation_id": "investing-os-morning-scan",
        "automation_name": "Investing OS Morning Scan",
        "role": "morning_scan",
        "schedule": "market weekdays 8:35 AM ET",
    },
    {
        "automation_id": "investing-os-daily-synthesis",
        "automation_name": "Investing OS Daily Synthesis",
        "role": "daily_synthesis",
        "schedule": "market weekdays 9:30 AM ET",
    },
    {
        "automation_id": "investing-os-uw-opportunity-cache",
        "automation_name": "Investing OS UW Opportunity Cache",
        "role": "uw_opportunity_cache",
        "schedule": "market weekdays 10:00 AM ET",
    },
    {
        "automation_id": "investing-os-parabolic-cache",
        "automation_name": "Investing OS Parabolic Cache",
        "role": "parabolic_cache",
        "schedule": "market weekdays 10:05 AM ET",
    },
    {
        "automation_id": "investing-os-full-cockpit-build",
        "automation_name": "Investing OS Full Cockpit Build",
        "role": "full_cockpit_build",
        "schedule": "market weekdays 10:30 AM ET",
    },
    {
        "automation_id": "investing-os-post-close-refresh",
        "automation_name": "Investing OS Post-Close Refresh",
        "role": "post_close_refresh",
        "schedule": "market weekdays 4:30 PM ET",
    },
    {
        "automation_id": "investing-os-off-hours-worker",
        "automation_name": "Investing OS Off-Hours Worker",
        "role": "off_hours_worker",
        "schedule": "daily 1:45 AM ET",
    },
    {
        "automation_id": "investing-os-deep-synthesis",
        "automation_name": "Investing OS Deep Synthesis",
        "role": "deep_synthesis",
        "schedule": "Sunday 1:00 PM ET",
    },
    {
        "automation_id": "investing-os-weekly-pilot-run",
        "automation_name": "Investing OS Weekly Pilot Run",
        "role": "weekly_pilot_run",
        "schedule": "Sunday 6:00 PM ET",
    },
]


def _automation_dirs(base: Path) -> list[Path]:
    if not base.exists():
        return []
    return [p for p in base.rglob("automation.toml") if p.is_file()]


def _toml_text_has_active_status(text: str) -> bool:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("status") and "ACTIVE" in stripped.upper():
            return True
    return False


def _status_is_active(value: Any) -> bool:
    return str(value or "").strip().upper() == "ACTIVE"


def _proof_rows(proof_path: str | Path | None) -> list[dict[str, Any]]:
    if proof_path is None:
        return []
    path = Path(proof_path)
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [{
            "path": str(path),
            "active": False,
            "evidence_type": "repo_proof",
            "problem": str(exc),
        }]
    if not isinstance(payload, dict):
        return [{
            "path": str(path),
            "active": False,
            "evidence_type": "repo_proof",
            "problem": "proof file must be a JSON object",
        }]
    raw_rows = payload.get("routines") if isinstance(payload.get("routines"), list) else [payload]
    rows: list[dict[str, Any]] = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        row["path"] = str(path)
        row["active"] = _status_is_active(row.get("status"))
        row["evidence_type"] = "repo_proof"
        rows.append(row)
    return rows


def _automation_matches_expected(row: dict[str, Any], expected: dict[str, Any]) -> bool:
    recorded_name = str(row.get("automation_name") or row.get("name") or "")
    recorded_id = str(row.get("automation_id") or row.get("id") or "")
    automation_name = str(expected.get("automation_name") or "")
    automation_id = str(expected.get("automation_id") or "")
    name_matches = bool(recorded_name) and recorded_name.lower() == automation_name.lower()
    id_matches = bool(recorded_id) and recorded_id.lower() == automation_id.lower()
    return name_matches or id_matches


def _automation_summary(
    *,
    automations_dir: str | Path | None = None,
    automation_name: str = DEFAULT_AUTOMATION_NAME,
    automation_id: str = DEFAULT_AUTOMATION_ID,
    automation_proof: str | Path | None = None,
    expected_automations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if automations_dir is None:
        home = os.environ.get("CODEX_HOME")
        base = Path(home) / "automations" if home else Path()
    else:
        base = Path(automations_dir)

    expected = expected_automations or [{
        "automation_id": automation_id,
        "automation_name": automation_name,
        "role": "daily_cloud_refresh",
        "schedule": "",
    }]
    all_matches: list[dict[str, Any]] = []
    proof_rows = _proof_rows(automation_proof)
    routine_rows: list[dict[str, Any]] = []
    local_texts: list[tuple[Path, str]] = []
    for path in _automation_dirs(base):
        text = path.read_text(encoding="utf-8", errors="replace")
        local_texts.append((path, text))

    for expected_row in expected:
        matches: list[dict[str, Any]] = []
        expected_name = str(expected_row.get("automation_name") or "")
        for path, text in local_texts:
            if expected_name and expected_name.lower() in text.lower():
                matches.append({
                    "path": str(path),
                    "active": _toml_text_has_active_status(text),
                    "evidence_type": "local_toml",
                })
        matches.extend(row for row in proof_rows if _automation_matches_expected(row, expected_row))
        all_matches.extend(matches)
        routine_rows.append({
            "automation_id": expected_row.get("automation_id") or "",
            "automation_name": expected_row.get("automation_name") or "",
            "role": expected_row.get("role") or "",
            "schedule": expected_row.get("schedule") or "",
            "installed": bool(matches),
            "active": any(row.get("active") for row in matches),
            "matches": matches,
        })

    missing = [row for row in routine_rows if not row["installed"]]
    inactive = [row for row in routine_rows if row["installed"] and not row["active"]]

    return {
        "automation_id": automation_id,
        "automation_name": automation_name,
        "automations_dir": str(base) if str(base) else "",
        "automation_proof": str(automation_proof or ""),
        "expected_count": len(routine_rows),
        "installed_count": len(routine_rows) - len(missing),
        "active_count": len([row for row in routine_rows if row["active"]]),
        "installed": not missing,
        "active": not missing and not inactive,
        "missing": missing,
        "inactive": inactive,
        "routines": routine_rows,
        "matches": all_matches,
    }


def _manifest_summary(src_dir: Path) -> dict[str, Any]:
    manifest_path = src_dir / "codex_routine_manifest.json"
    try:
        manifest = codex_routine_manifest.load_manifest(manifest_path)
        problems = codex_routine_manifest.validate_manifest(manifest, root=ROOT)
        summary = codex_routine_manifest.summary(manifest)
    except Exception as exc:
        return {"valid": False, "problems": [str(exc)], "summary": {}}
    return {"valid": not problems, "problems": problems, "summary": summary}


def _receipt_summary(path: str | Path, expected_automations: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        payload = cloud_routine_receipts.load_receipts(path)
        problems = cloud_routine_receipts.validate_receipts(payload)
        summary = cloud_routine_receipts.summarize_receipts(
            payload,
            expected_automations=expected_automations,
        )
    except Exception as exc:
        return {
            "valid": False,
            "problems": [str(exc)],
            "summary": {
                "receipt_file_present": False,
                "expected_count": len(expected_automations),
                "success_count": 0,
                "failed_latest_count": 0,
                "missing_success_count": len(expected_automations),
                "rows": [],
                "missing_success": expected_automations,
                "failed_latest": [],
            },
        }
    return {"valid": not problems, "problems": problems, "summary": summary}


def _operating_gaps(
    status: dict[str, Any],
    automation: dict[str, Any],
    manifest: dict[str, Any],
    receipts: dict[str, Any],
) -> list[str]:
    gaps: list[str] = []
    if not automation.get("installed"):
        missing = [
            str(row.get("automation_name") or row.get("automation_id") or "unknown")
            for row in automation.get("missing") or []
            if isinstance(row, dict)
        ]
        suffix = f": {', '.join(missing)}" if missing else "."
        gaps.append(f"Codex cloud routine stack is incomplete{suffix}")
    elif not automation.get("active"):
        inactive = [
            str(row.get("automation_name") or row.get("automation_id") or "unknown")
            for row in automation.get("inactive") or []
            if isinstance(row, dict)
        ]
        suffix = f": {', '.join(inactive)}" if inactive else "."
        gaps.append(f"Codex cloud routine stack has inactive routines{suffix}")
    if not manifest.get("valid"):
        gaps.append("Routine manifest is invalid.")
    if not receipts.get("valid"):
        gaps.append("Cloud routine receipt file is invalid.")
    failed_receipts = ((receipts.get("summary") or {}).get("failed_latest") or [])
    for row in failed_receipts:
        if not isinstance(row, dict):
            continue
        label = row.get("routine_name") or row.get("routine_id") or "Cloud routine"
        summary = row.get("last_summary") or row.get("last_recorded_at") or "latest run failed"
        gaps.append(f"{label} latest run receipt failed: {summary}")
    if not status.get("go_live_ready"):
        gaps.append("Dashboard is not go-live ready.")
    dark = (status.get("dark_lanes") or {}).get("details") or []
    for row in dark:
        if not isinstance(row, dict):
            continue
        label = row.get("label") or row.get("key") or "Optional lane"
        next_step = row.get("next_step") or row.get("missing_impact") or "supply source input"
        gaps.append(f"{label} remains dark: {next_step}")
    if (status.get("open_actions") or {}).get("count"):
        tickers = [
            str(ticker)
            for ticker in (status.get("open_actions") or {}).get("tickers") or []
            if ticker
        ]
        suffix = f" ({', '.join(tickers)})" if tickers else ""
        gaps.append(f"Open action reviews remain unresolved{suffix}.")
    return gaps


def cloud_ops_status(
    *,
    src_dir: str | Path = DEFAULT_SRC,
    automations_dir: str | Path | None = None,
    automation_name: str = DEFAULT_AUTOMATION_NAME,
    automation_id: str = DEFAULT_AUTOMATION_ID,
    automation_proof: str | Path | None = None,
    receipt_proof: str | Path | None = None,
) -> dict[str, Any]:
    src = Path(src_dir)
    if automation_proof is None:
        automation_proof = src / DEFAULT_AUTOMATION_PROOF
    if receipt_proof is None:
        receipt_proof = src / DEFAULT_RECEIPT_PROOF
    status = live_status_mod.live_status(src_dir=src)
    manifest = _manifest_summary(src)
    automation = _automation_summary(
        automations_dir=automations_dir,
        automation_name=automation_name,
        automation_id=automation_id,
        automation_proof=automation_proof,
        expected_automations=DEFAULT_EXPECTED_AUTOMATIONS,
    )
    receipts = _receipt_summary(receipt_proof, DEFAULT_EXPECTED_AUTOMATIONS)
    gaps = _operating_gaps(status, automation, manifest, receipts)
    return {
        "ready_for_unattended_daily_run": (
            bool(status.get("go_live_ready"))
            and bool(manifest.get("valid"))
            and bool(automation.get("active"))
            and bool(receipts.get("valid"))
        ),
        "local_go_live_ready": bool(status.get("go_live_ready")),
        "routine_manifest": manifest,
        "cloud_automation": automation,
        "routine_receipts": receipts,
        "dark_lanes": status.get("dark_lanes") or {},
        "open_actions": status.get("open_actions") or {},
        "gaps": gaps,
        "source_pull_note": (
            "The scheduled routines can run the repo refresh and connector/supplied "
            "intake attempts, but missing connector exports must remain visible as "
            "dark lanes instead of being treated as checked clear."
        ),
    }


def format_text(report: dict[str, Any]) -> str:
    manifest_summary = (report.get("routine_manifest") or {}).get("summary") or {}
    automation = report.get("cloud_automation") or {}
    receipts = ((report.get("routine_receipts") or {}).get("summary") or {})
    dark = report.get("dark_lanes") or {}
    lines = [
        f"Cloud ops ready: {bool(report.get('ready_for_unattended_daily_run'))}",
        f"Local go-live ready: {bool(report.get('local_go_live_ready'))}",
        (
            "Routine manifest: "
            f"valid={bool((report.get('routine_manifest') or {}).get('valid'))} | "
            f"routines={manifest_summary.get('routines', 0)} | "
            f"active={manifest_summary.get('active', 0)}"
        ),
        (
            "Cloud routine stack: "
            f"installed={bool(automation.get('installed'))} | "
            f"active={bool(automation.get('active'))} | "
            f"expected={int(automation.get('expected_count') or 0)} | "
            f"active_count={int(automation.get('active_count') or 0)}"
        ),
        (
            "Dark source lanes: "
            f"{int(dark.get('count') or 0)}"
        ),
        (
            "Cloud run receipts: "
            f"success={int(receipts.get('success_count') or 0)}/"
            f"{int(receipts.get('expected_count') or 0)} | "
            f"failed_latest={int(receipts.get('failed_latest_count') or 0)} | "
            f"missing_success={int(receipts.get('missing_success_count') or 0)}"
        ),
    ]
    gaps = report.get("gaps") or []
    if gaps:
        lines.append("Gaps:")
        lines.extend(f"- {gap}" for gap in gaps)
    else:
        lines.append("Gaps: none")
    lines.append(str(report.get("source_pull_note") or ""))
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Report daily cloud operating readiness")
    parser.add_argument("--src-dir", default=str(DEFAULT_SRC))
    parser.add_argument("--automations-dir")
    parser.add_argument("--automation-name", default=DEFAULT_AUTOMATION_NAME)
    parser.add_argument("--automation-id", default=DEFAULT_AUTOMATION_ID)
    parser.add_argument("--automation-proof")
    parser.add_argument("--receipt-proof")
    parser.add_argument("--format", choices=["json", "text"], default="json")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero unless unattended daily ops are ready")
    args = parser.parse_args(argv)

    report = cloud_ops_status(
        src_dir=args.src_dir,
        automations_dir=args.automations_dir,
        automation_name=args.automation_name,
        automation_id=args.automation_id,
        automation_proof=args.automation_proof,
        receipt_proof=args.receipt_proof,
    )
    if args.format == "text":
        print(format_text(report))
    else:
        print(json.dumps(report, indent=2))
    if args.strict and not report.get("ready_for_unattended_daily_run"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
