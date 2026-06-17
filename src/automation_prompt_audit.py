#!/usr/bin/env python3
"""Audit installed OS app automations for safe receipt handling."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CODEX_HOME = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
DEFAULT_AUTOMATIONS_DIR = DEFAULT_CODEX_HOME / "automations"


def _is_monitored_os(data: dict[str, Any], raw_text: str) -> bool:
    text = " ".join(
        str(data.get(key) or "")
        for key in ("id", "name", "prompt")
    )
    text += " " + raw_text
    lowered = text.lower()
    return any(
        token in lowered
        for token in (
            "investing-os",
            "investing os",
            "life-os",
            "life os",
            "work-os",
            "work os",
            "life/work os",
        )
    )


def _parse_automation(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"{path}: unreadable automation file: {exc}"
    try:
        return tomllib.loads(raw_text), None
    except tomllib.TOMLDecodeError as exc:
        return None, f"{path}: invalid TOML: {exc}"


def _worktree_hardened(cwd: Path) -> tuple[bool, list[str]]:
    problems: list[str] = []
    commit_helper = cwd / "src" / "cloud_routine_commit.py"
    receipts = cwd / "src" / "cloud_routine_receipts.py"
    if not commit_helper.exists():
        problems.append("missing src/cloud_routine_commit.py")
    elif "receipt_normalized" not in commit_helper.read_text(encoding="utf-8", errors="replace"):
        problems.append("safe helper does not report receipt normalization")
    if not receipts.exists():
        problems.append("missing src/cloud_routine_receipts.py")
    else:
        receipt_text = receipts.read_text(encoding="utf-8", errors="replace")
        if "JSON_READ_ENCODINGS" not in receipt_text:
            problems.append("receipt reader lacks legacy encoding fallback")
        if "validate_receipt_file_encoding" not in receipt_text:
            problems.append("receipt reader lacks strict UTF-8 validation")
    return not problems, problems


def audit_automations(automations_dir: Path = DEFAULT_AUTOMATIONS_DIR) -> dict[str, Any]:
    if not automations_dir.exists():
        return {
            "valid": True,
            "checked": False,
            "reason": f"automation directory not found: {automations_dir}",
            "rows": [],
            "problems": [],
        }

    rows: list[dict[str, Any]] = []
    problems: list[str] = []
    worktree_cache: dict[str, tuple[bool, list[str]]] = {}
    for toml_path in sorted(automations_dir.rglob("automation.toml")):
        raw_text = toml_path.read_text(encoding="utf-8", errors="replace")
        data, parse_error = _parse_automation(toml_path)
        if parse_error:
            problems.append(parse_error)
            continue
        assert data is not None
        if not _is_monitored_os(data, raw_text):
            continue
        if str(data.get("status") or "").upper() != "ACTIVE":
            continue
        prompt = str(data.get("prompt") or "")
        cwds = [str(cwd) for cwd in data.get("cwds") or []]
        row_problems: list[str] = []
        if "cloud_routine_commit.py" not in prompt:
            row_problems.append("active prompt does not use src/cloud_routine_commit.py safe helper")
        if not cwds:
            row_problems.append("active prompt has no cwd")
        for cwd_text in cwds:
            cwd = Path(cwd_text)
            if not cwd.exists():
                row_problems.append(f"cwd missing: {cwd}")
                continue
            cache_key = str(cwd.resolve())
            if cache_key not in worktree_cache:
                worktree_cache[cache_key] = _worktree_hardened(cwd)
            hardened, cwd_problems = worktree_cache[cache_key]
            if not hardened:
                for problem in cwd_problems:
                    row_problems.append(f"{cwd}: {problem}")
        row = {
            "id": data.get("id") or toml_path.parent.name,
            "name": data.get("name") or "",
            "path": str(toml_path),
            "cwds": cwds,
            "has_safe_helper": "cloud_routine_commit.py" in prompt,
            "has_prompt_receipt_normalize": "--normalize" in prompt and "--require-utf8" in prompt,
            "problems": row_problems,
        }
        rows.append(row)
        for problem in row_problems:
            problems.append(f"{row['id']}: {problem}")

    return {
        "valid": not problems,
        "checked": True,
        "automations_dir": str(automations_dir),
        "active_investing_os_automations": len(rows),
        "active_monitored_os_automations": len(rows),
        "rows": rows,
        "problems": problems,
    }


def format_text(report: dict[str, Any]) -> str:
    if not report.get("checked"):
        return f"Automation prompt audit not checked: {report.get('reason', '')}"
    lines = [
        "Automation prompt audit: "
        f"active_monitored_os={report.get('active_monitored_os_automations', report.get('active_investing_os_automations', 0))} "
        f"| valid={bool(report.get('valid'))}",
    ]
    normalize_count = sum(1 for row in report.get("rows", []) if row.get("has_prompt_receipt_normalize"))
    lines.append(f"Prompts explicitly normalizing receipts: {normalize_count}/{len(report.get('rows', []))}")
    if report.get("problems"):
        lines.append("Problems:")
        lines.extend(f"- {problem}" for problem in report["problems"])
    else:
        lines.append("All active monitored OS automations use the safe commit helper and hardened worktrees.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--automations-dir",
        default=str(DEFAULT_AUTOMATIONS_DIR),
        help="Directory containing Codex app automation.toml files",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    report = audit_automations(Path(args.automations_dir))
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_text(report))
    return 0 if report.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
