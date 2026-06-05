#!/usr/bin/env python3
"""Report whether the Investing OS daily cloud routine can operate unattended."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import codex_routine_manifest
import live_status as live_status_mod


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = ROOT / "src"
DEFAULT_AUTOMATION_NAME = "Investing OS Daily Cloud Refresh"
DEFAULT_AUTOMATION_ID = "investing-os-daily-cloud-refresh"
DEFAULT_AUTOMATION_PROOF = "cloud_automation_status.json"


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


def _automation_proof_summary(
    proof_path: str | Path | None,
    *,
    automation_name: str,
    automation_id: str,
) -> dict[str, Any] | None:
    if proof_path is None:
        return None
    path = Path(proof_path)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "path": str(path),
            "active": False,
            "evidence_type": "repo_proof",
            "problem": str(exc),
        }
    if not isinstance(payload, dict):
        return {
            "path": str(path),
            "active": False,
            "evidence_type": "repo_proof",
            "problem": "proof file must be a JSON object",
        }
    recorded_name = str(payload.get("automation_name") or payload.get("name") or "")
    recorded_id = str(payload.get("automation_id") or payload.get("id") or "")
    name_matches = bool(recorded_name) and recorded_name.lower() == automation_name.lower()
    id_matches = bool(recorded_id) and recorded_id.lower() == automation_id.lower()
    if not (name_matches or id_matches):
        return None
    return {
        "path": str(path),
        "active": _status_is_active(payload.get("status")),
        "evidence_type": "repo_proof",
        "automation_id": recorded_id,
        "automation_name": recorded_name,
        "verified_at": payload.get("verified_at") or "",
        "verification_source": payload.get("verification_source") or "",
    }


def _automation_summary(
    *,
    automations_dir: str | Path | None = None,
    automation_name: str = DEFAULT_AUTOMATION_NAME,
    automation_id: str = DEFAULT_AUTOMATION_ID,
    automation_proof: str | Path | None = None,
) -> dict[str, Any]:
    if automations_dir is None:
        home = os.environ.get("CODEX_HOME")
        base = Path(home) / "automations" if home else Path()
    else:
        base = Path(automations_dir)

    matches: list[dict[str, Any]] = []
    for path in _automation_dirs(base):
        text = path.read_text(encoding="utf-8", errors="replace")
        if automation_name.lower() not in text.lower():
            continue
        matches.append({
            "path": str(path),
            "active": _toml_text_has_active_status(text),
            "evidence_type": "local_toml",
        })

    proof = _automation_proof_summary(
        automation_proof,
        automation_name=automation_name,
        automation_id=automation_id,
    )
    if proof is not None:
        matches.append(proof)

    return {
        "automation_id": automation_id,
        "automation_name": automation_name,
        "automations_dir": str(base) if str(base) else "",
        "automation_proof": str(automation_proof or ""),
        "installed": bool(matches),
        "active": any(row["active"] for row in matches),
        "matches": matches,
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


def _operating_gaps(status: dict[str, Any], automation: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    if not automation.get("installed"):
        gaps.append("Daily Codex cloud automation is not installed.")
    elif not automation.get("active"):
        gaps.append("Daily Codex cloud automation is installed but not active.")
    if not manifest.get("valid"):
        gaps.append("Routine manifest is invalid.")
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
) -> dict[str, Any]:
    src = Path(src_dir)
    if automation_proof is None:
        automation_proof = src / DEFAULT_AUTOMATION_PROOF
    status = live_status_mod.live_status(src_dir=src)
    manifest = _manifest_summary(src)
    automation = _automation_summary(
        automations_dir=automations_dir,
        automation_name=automation_name,
        automation_id=automation_id,
        automation_proof=automation_proof,
    )
    gaps = _operating_gaps(status, automation, manifest)
    return {
        "ready_for_unattended_daily_run": (
            bool(status.get("go_live_ready"))
            and bool(manifest.get("valid"))
            and bool(automation.get("active"))
        ),
        "local_go_live_ready": bool(status.get("go_live_ready")),
        "routine_manifest": manifest,
        "cloud_automation": automation,
        "dark_lanes": status.get("dark_lanes") or {},
        "open_actions": status.get("open_actions") or {},
        "gaps": gaps,
        "source_pull_note": (
            "The scheduled routine can run the repo refresh and connector/supplied "
            "intake attempts, but missing connector exports must remain visible as "
            "dark lanes instead of being treated as checked clear."
        ),
    }


def format_text(report: dict[str, Any]) -> str:
    manifest_summary = (report.get("routine_manifest") or {}).get("summary") or {}
    automation = report.get("cloud_automation") or {}
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
            "Daily cloud automation: "
            f"installed={bool(automation.get('installed'))} | "
            f"active={bool(automation.get('active'))} | "
            f"id={automation.get('automation_id') or ''}"
        ),
        (
            "Dark source lanes: "
            f"{int(dark.get('count') or 0)}"
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
    parser.add_argument("--format", choices=["json", "text"], default="json")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero unless unattended daily ops are ready")
    args = parser.parse_args(argv)

    report = cloud_ops_status(
        src_dir=args.src_dir,
        automations_dir=args.automations_dir,
        automation_name=args.automation_name,
        automation_id=args.automation_id,
        automation_proof=args.automation_proof,
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
