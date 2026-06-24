"""Watch key Investing OS automations for failed proof and stale local worktrees.

The watchdog intentionally fixes only the failure mode that is safe to repair
without fabricating proof: unhealthy local automation cwd pointers can be
rewritten to a known clean checkout. Failed or overdue routine receipts remain
visible so the operator gets an alert instead of a false green.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cloud_ops_status
import pushover_notify

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
DEFAULT_AUTOMATIONS_DIR = DEFAULT_CODEX_HOME / "automations"
DEFAULT_CANONICAL_CWD = Path(
    os.environ.get("INVESTING_OS_AUTOMATION_CANONICAL_CWD", ROOT)
)

SAFE_FIX_REASONS = {
    "missing_cwd",
    "not_git_worktree",
    "not_main_branch",
    "diverged_from_origin_main",
    "behind_origin_main",
    "dirty_worktree",
}


@dataclass(frozen=True)
class AutomationRecord:
    """Installed Codex automation record parsed from automation.toml."""

    automation_id: str
    path: Path
    name: str
    active: bool
    kind: str
    prompt: str
    cwds: tuple[Path, ...]

    @property
    def is_investing_os(self) -> bool:
        text = " ".join(
            [
                self.automation_id.lower(),
                self.name.lower(),
                self.prompt.lower(),
                " ".join(str(cwd).lower() for cwd in self.cwds),
            ]
        )
        tokens = (
            "investing os",
            "investment os",
            "enderverse",
            "life-os",
            "work-os",
            "loose_thread_sweep",
            "cloud_routine",
        )
        return any(token in text for token in tokens)

    @property
    def uses_safe_helper(self) -> bool:
        return "cloud_routine_commit.py" in self.prompt


def _expected_key_ids() -> set[str]:
    expected = getattr(cloud_ops_status, "DEFAULT_EXPECTED_AUTOMATIONS", ())
    return {row["automation_id"] for row in expected if row.get("automation_id")}


def _load_automation_record(path: Path) -> AutomationRecord | None:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None

    cwd_values = data.get("cwds") or []
    cwds = tuple(Path(value).expanduser() for value in cwd_values if value)
    status = str(data.get("status") or "").upper()
    return AutomationRecord(
        automation_id=str(data.get("id") or path.parent.name),
        path=path,
        name=str(data.get("name") or path.parent.name),
        active=bool(data.get("active", False)) or status == "ACTIVE",
        kind=str(data.get("kind") or ""),
        prompt=str(data.get("prompt") or ""),
        cwds=cwds,
    )


def load_automation_records(automations_dir: Path) -> list[AutomationRecord]:
    if not automations_dir.exists():
        return []

    records: list[AutomationRecord] = []
    for toml_path in sorted(automations_dir.glob("*/automation.toml")):
        record = _load_automation_record(toml_path)
        if record is not None:
            records.append(record)
    return records


def _run_git(cwd: Path, args: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def inspect_git_health(cwd: Path, *, fetch: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "cwd": str(cwd),
        "ok": False,
        "reasons": [],
        "branch": None,
        "ahead_origin_main": None,
        "behind_origin_main": None,
        "dirty_files": None,
    }

    if not cwd.exists():
        result["reasons"].append("missing_cwd")
        return result

    inside = _run_git(cwd, ["rev-parse", "--is-inside-work-tree"])
    if inside.returncode != 0 or inside.stdout.strip().lower() != "true":
        result["reasons"].append("not_git_worktree")
        result["git_error"] = (inside.stderr or inside.stdout).strip()
        return result

    if fetch:
        fetch_result = _run_git(cwd, ["fetch", "origin", "main"])
        if fetch_result.returncode != 0:
            result["reasons"].append("fetch_failed")
            result["git_error"] = (fetch_result.stderr or fetch_result.stdout).strip()

    branch = _run_git(cwd, ["branch", "--show-current"])
    if branch.returncode == 0:
        result["branch"] = branch.stdout.strip()

    if result["branch"] != "main":
        result["reasons"].append("not_main_branch")

    rev_count = _run_git(cwd, ["rev-list", "--left-right", "--count", "HEAD...origin/main"])
    if rev_count.returncode == 0:
        parts = rev_count.stdout.strip().split()
        if len(parts) == 2:
            ahead, behind = int(parts[0]), int(parts[1])
            result["ahead_origin_main"] = ahead
            result["behind_origin_main"] = behind
            if ahead and behind:
                result["reasons"].append("diverged_from_origin_main")
            elif behind:
                result["reasons"].append("behind_origin_main")
    else:
        result["reasons"].append("origin_main_unavailable")

    dirty = _run_git(cwd, ["status", "--porcelain"])
    if dirty.returncode == 0:
        dirty_files = [line for line in dirty.stdout.splitlines() if line.strip()]
        result["dirty_files"] = len(dirty_files)
        if dirty_files:
            result["reasons"].append("dirty_worktree")

    result["ok"] = not result["reasons"]
    return result


def _toml_string(value: str) -> str:
    if "'" not in value:
        return "'" + value + "'"
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def replace_cwds_line(raw: str, cwds: list[Path]) -> str:
    rendered = "cwds = [" + ", ".join(_toml_string(str(cwd)) for cwd in cwds) + "]"
    if re.search(r"(?m)^cwds\s*=", raw):
        return re.sub(r"(?m)^cwds\s*=.*$", lambda _match: rendered, raw, count=1)
    suffix = "\n" if raw.endswith("\n") else "\n\n"
    return raw + suffix + rendered + "\n"


def _canonical_ready(canonical_cwd: Path, *, fetch: bool = False) -> dict[str, Any]:
    if not canonical_cwd.exists():
        return {
            "ok": False,
            "cwd": str(canonical_cwd),
            "reason": "canonical_cwd_missing",
        }
    marker = canonical_cwd / "src" / "cloud_routine_commit.py"
    if not marker.exists():
        return {
            "ok": False,
            "cwd": str(canonical_cwd),
            "reason": "canonical_safe_helper_missing",
        }

    health = inspect_git_health(canonical_cwd, fetch=fetch)
    if not health["ok"]:
        return {
            "ok": False,
            "cwd": str(canonical_cwd),
            "reason": "canonical_git_unhealthy",
            "git_health": health,
        }
    return {"ok": True, "cwd": str(canonical_cwd), "git_health": health}


def _record_needs_cwd_fix(
    record: AutomationRecord,
    health_rows: list[dict[str, Any]],
    canonical_cwd: Path,
    key_ids: set[str],
) -> bool:
    if record.automation_id not in key_ids:
        return False
    if record.cwds == (canonical_cwd,):
        return False
    for row in health_rows:
        reasons = set(row.get("reasons") or [])
        if reasons & SAFE_FIX_REASONS:
            return True
    return False


def _apply_cwd_fix(record: AutomationRecord, canonical_cwd: Path) -> dict[str, Any]:
    raw = record.path.read_text(encoding="utf-8")
    updated = replace_cwds_line(raw, [canonical_cwd])
    if updated != raw:
        record.path.write_text(updated, encoding="utf-8")
    return {
        "automation_id": record.automation_id,
        "name": record.name,
        "file": str(record.path),
        "old_cwds": [str(cwd) for cwd in record.cwds],
        "new_cwds": [str(canonical_cwd)],
        "changed": updated != raw,
    }


def _summarize_cloud_attention(cloud_report: dict[str, Any]) -> list[dict[str, Any]]:
    attention: list[dict[str, Any]] = []
    receipt_sections = [
        ("routine_receipts", "core"),
        ("support_routine_receipts", "support"),
    ]
    for section, label in receipt_sections:
        summary = ((cloud_report.get(section) or {}).get("summary") or {})
        for item in summary.get("failed_latest") or []:
            attention.append(
                {
                    "kind": "failed_latest_receipt",
                    "section": label,
                    "routine_id": item.get("routine_id"),
                    "status": item.get("last_scheduled_status")
                    or item.get("last_status")
                    or item.get("status"),
                    "recorded_at": item.get("last_scheduled_recorded_at")
                    or item.get("last_recorded_at")
                    or item.get("completed_at"),
                    "summary": item.get("last_scheduled_summary")
                    or item.get("last_summary"),
                }
            )

    due_sections = [
        ("routine_receipt_due", "core"),
        ("support_routine_receipt_due", "support"),
    ]
    for section, label in due_sections:
        due = cloud_report.get(section) or {}
        for item in due.get("overdue") or []:
            attention.append(
                {
                    "kind": "overdue_receipt",
                    "section": label,
                    "routine_id": item.get("routine_id"),
                    "overdue_line": item.get("overdue_line"),
                    "last_due_at": item.get("last_due_at"),
                    "last_scheduled_success_at": item.get(
                        "last_scheduled_success_at"
                    ),
                    "age_hours": item.get("age_hours"),
                    "max_age_hours": item.get("max_age_hours"),
                    "max_age_minutes": item.get("max_age_minutes"),
                }
            )
    return attention


def _build_alert_message(report: dict[str, Any]) -> str:
    lines = [
        f"status={report['status']}",
        f"automation_problems={len(report['automation_problems'])}",
        f"fixes={len(report['fixes_applied'])}",
        f"cloud_attention={len(report['cloud_attention'])}",
    ]

    for problem in report["automation_problems"][:6]:
        reasons = ",".join(problem.get("reasons") or [])
        lines.append(f"- {problem['automation_id']}: {reasons}")

    for item in report["cloud_attention"][:6]:
        lines.append(f"- {item['kind']}: {item.get('routine_id')}")

    return "\n".join(lines)[:950]


def _send_pushover_alert(
    report: dict[str, Any],
    *,
    send_alert: bool,
    dry_run_alert: bool,
) -> dict[str, Any]:
    if not (send_alert or dry_run_alert):
        return {"attempted": False}
    if report["status"] == "ok":
        return {"attempted": False, "reason": "no_attention_needed"}

    try:
        response = pushover_notify.send_message(
            title="Investing OS automation watchdog",
            message=_build_alert_message(report),
            priority=1,
            dry_run=not send_alert,
        )
    except Exception as exc:  # pragma: no cover - defensive around local config
        return {"attempted": True, "ok": False, "error": str(exc)}

    return {
        "attempted": True,
        "ok": True,
        "dry_run": not send_alert,
        "response": response,
    }


def audit_automation_health(
    *,
    automations_dir: Path = DEFAULT_AUTOMATIONS_DIR,
    canonical_cwd: Path = DEFAULT_CANONICAL_CWD,
    apply: bool = False,
    fetch: bool = False,
    include_all_active: bool = False,
    send_alert: bool = False,
    dry_run_alert: bool = False,
    cloud_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    canonical_cwd = canonical_cwd.resolve()
    key_ids = _expected_key_ids()
    records = load_automation_records(automations_dir)
    selected = [
        record
        for record in records
        if record.active
        and record.is_investing_os
        and (include_all_active or record.automation_id in key_ids)
    ]

    canonical = _canonical_ready(canonical_cwd, fetch=fetch)
    automation_problems: list[dict[str, Any]] = []
    fixes_applied: list[dict[str, Any]] = []

    for record in selected:
        cwd_health = [
            inspect_git_health(cwd, fetch=fetch)
            for cwd in (record.cwds or (Path("__missing_cwd__"),))
        ]
        problem_rows = [row for row in cwd_health if row.get("reasons")]
        if problem_rows:
            automation_problems.append(
                {
                    "automation_id": record.automation_id,
                    "name": record.name,
                    "file": str(record.path),
                    "cwds": [str(cwd) for cwd in record.cwds],
                    "reasons": sorted(
                        {
                            reason
                            for row in problem_rows
                            for reason in (row.get("reasons") or [])
                        }
                    ),
                    "cwd_health": problem_rows,
                }
            )

        if (
            apply
            and canonical["ok"]
            and _record_needs_cwd_fix(record, cwd_health, canonical_cwd, key_ids)
        ):
            fixes_applied.append(_apply_cwd_fix(record, canonical_cwd))

    if cloud_report is None:
        cloud_report = cloud_ops_status.cloud_ops_status(
            src_dir=ROOT / "src",
            automations_dir=automations_dir,
        )
    cloud_attention = _summarize_cloud_attention(cloud_report)

    unresolved_automation = [
        problem
        for problem in automation_problems
        if problem["automation_id"]
        not in {fix["automation_id"] for fix in fixes_applied if fix["changed"]}
    ]
    status = "ok"
    if unresolved_automation or cloud_attention:
        status = "needs_attention"
    elif fixes_applied:
        status = "fixed"

    report: dict[str, Any] = {
        "status": status,
        "checked_automations": len(selected),
        "automations_dir": str(automations_dir),
        "canonical_cwd": str(canonical_cwd),
        "canonical": canonical,
        "automation_problems": automation_problems,
        "unresolved_automation_problems": unresolved_automation,
        "fixes_applied": fixes_applied,
        "cloud_attention": cloud_attention,
    }
    report["pushover"] = _send_pushover_alert(
        report,
        send_alert=send_alert,
        dry_run_alert=dry_run_alert,
    )
    return report


def format_text(report: dict[str, Any]) -> str:
    lines = [
        (
            "Automation watchdog: "
            f"status={report['status']} | "
            f"checked={report['checked_automations']} | "
            f"problems={len(report['automation_problems'])} | "
            f"fixes={len(report['fixes_applied'])} | "
            f"cloud_attention={len(report['cloud_attention'])}"
        ),
        f"Automations dir: {report['automations_dir']}",
        f"Canonical cwd: {report['canonical_cwd']}",
    ]

    if not report["canonical"]["ok"]:
        lines.append(f"Canonical readiness: {report['canonical'].get('reason')}")

    if report["automation_problems"]:
        lines.append("Automation workspace problems:")
        for problem in report["automation_problems"]:
            reasons = ", ".join(problem["reasons"])
            lines.append(f"- {problem['automation_id']}: {reasons}")
            for cwd in problem["cwds"] or ["<none>"]:
                lines.append(f"  cwd={cwd}")

    if report["fixes_applied"]:
        lines.append("Auto-fixes applied:")
        for fix in report["fixes_applied"]:
            old_cwds = ", ".join(fix["old_cwds"] or ["<none>"])
            new_cwds = ", ".join(fix["new_cwds"])
            lines.append(f"- {fix['automation_id']}: {old_cwds} -> {new_cwds}")

    if report["cloud_attention"]:
        lines.append("Cloud proof attention:")
        for item in report["cloud_attention"]:
            if item["kind"] == "failed_latest_receipt":
                lines.append(
                    f"- failed latest {item['section']}: "
                    f"{item.get('routine_id')} "
                    f"status={item.get('status')} at {item.get('recorded_at')}"
                )
            else:
                overdue_line = item.get("overdue_line")
                if overdue_line:
                    lines.append(f"- overdue {item['section']}: {overdue_line}")
                else:
                    lines.append(
                        f"- overdue {item['section']}: "
                        f"{item.get('routine_id')} "
                        f"last_due={item.get('last_due_at')} "
                        f"last_success={item.get('last_scheduled_success_at')} "
                        f"max_age_minutes={item.get('max_age_minutes')}"
                    )

    pushover = report["pushover"]
    if pushover.get("attempted"):
        mode = "dry-run" if pushover.get("dry_run") else "sent"
        ok = "ok" if pushover.get("ok") else "failed"
        lines.append(f"Pushover alert: {mode} {ok}")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit and optionally repair key Investing OS automation health."
    )
    parser.add_argument(
        "--automations-dir",
        type=Path,
        default=DEFAULT_AUTOMATIONS_DIR,
        help="Codex automations directory to inspect.",
    )
    parser.add_argument(
        "--canonical-cwd",
        type=Path,
        default=DEFAULT_CANONICAL_CWD,
        help="Known clean main checkout to use for safe cwd auto-fixes.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Rewrite unhealthy key automation cwds to --canonical-cwd.",
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Fetch origin/main before checking git health.",
    )
    parser.add_argument(
        "--include-all-active",
        action="store_true",
        help="Check every active Investing OS automation, not only proof-critical keys.",
    )
    parser.add_argument(
        "--send-alert",
        action="store_true",
        help="Send a real Pushover alert when attention is needed.",
    )
    parser.add_argument(
        "--dry-run-alert",
        action="store_true",
        help="Build the Pushover alert payload without sending it.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit nonzero when unresolved attention remains.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = audit_automation_health(
        automations_dir=args.automations_dir,
        canonical_cwd=args.canonical_cwd,
        apply=args.apply,
        fetch=args.fetch,
        include_all_active=args.include_all_active,
        send_alert=args.send_alert,
        dry_run_alert=args.dry_run_alert,
    )
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_text(report))

    if args.strict and report["status"] != "ok":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
