#!/usr/bin/env python3
"""Integration-debt sweep for repo wiring, routines, and queue reality.

This is an audit surface, not an executor. It names stale seams and dark
read-only lanes so the weekly pilot can review system debt without creating a
new schedule or pretending missing Notion data is checked clear.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = Path(__file__).resolve().parent
DOCS = ROOT / "docs"

DEFAULT_REPORT_PATH = DOCS / "integration_debt_report.md"
DEFAULT_JSON_PATH = SRC / "integration_debt_report.json"

WARN = "warn"
INFO = "info"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError:
        return ""


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def _atomic_write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".integration_debt.", suffix=".tmp", dir=str(path.parent))
    try:
        with open(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        Path(tmp).replace(path)
    finally:
        if Path(tmp).exists():
            Path(tmp).unlink()
    return path


def _atomic_write_json(path: Path, payload: Any) -> Path:
    return _atomic_write_text(path, json.dumps(payload, indent=2) + "\n")


def _rel(path: Path, root_dir: Path) -> str:
    try:
        return path.relative_to(root_dir).as_posix()
    except ValueError:
        return path.as_posix()


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def _finding(
    *,
    finding_id: str,
    area: str,
    title: str,
    line: str,
    severity: str = WARN,
    next_step: str = "",
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    row = {
        "id": finding_id,
        "area": area,
        "severity": severity,
        "title": title,
        "line": line,
    }
    if next_step:
        row["next_step"] = next_step
    if evidence:
        row["evidence"] = evidence
    return row


def _source_files(src_dir: Path) -> list[Path]:
    return sorted(
        p for p in src_dir.glob("*.py")
        if p.is_file() and not p.name.startswith("test_") and p.name != "__init__.py"
    )


def _local_import_graph(src_dir: Path) -> dict[str, set[str]]:
    modules = {p.stem for p in _source_files(src_dir)}
    imported_by: dict[str, set[str]] = {module: set() for module in modules}
    for path in _source_files(src_dir):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        except (OSError, SyntaxError):
            continue
        importer = path.stem
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            for name in names:
                if name in modules and name != importer:
                    imported_by.setdefault(name, set()).add(importer)
    return imported_by


def _routine_text(root_dir: Path, src_dir: Path) -> str:
    pieces = [
        json.dumps(_read_json(src_dir / "codex_routine_manifest.json", {}), sort_keys=True),
        json.dumps(_read_json(src_dir / "cloud_automation_status.json", {}), sort_keys=True),
    ]
    routines_dir = src_dir / "codex_routines"
    if routines_dir.is_dir():
        for path in sorted(routines_dir.glob("*.md")):
            pieces.append(_read_text(path))
    for path in (root_dir / ".github").glob("**/*"):
        if path.is_file() and path.suffix in {".yml", ".yaml", ".md"}:
            pieces.append(_read_text(path))
    return "\n".join(pieces)


def _command_references(src_dir: Path, root_dir: Path) -> dict[str, list[str]]:
    text = _routine_text(root_dir, src_dir)
    refs: dict[str, list[str]] = {}
    for path in _source_files(src_dir):
        module = path.stem
        patterns = [
            f"src/{module}.py",
            f"src\\{module}.py",
            f"{module}.py",
            f"-m {module}",
            f"python {module}.py",
        ]
        hits = [pattern for pattern in patterns if pattern in text]
        if hits:
            refs[module] = hits
    return refs


def _has_main(path: Path) -> bool:
    text = _read_text(path)
    return "__main__" in text and ("argparse" in text or "self-test" in text or "self_test" in text)


def module_wiring_section(src_dir: Path, root_dir: Path) -> dict[str, Any]:
    imported_by = _local_import_graph(src_dir)
    command_refs = _command_references(src_dir, root_dir)
    rows: list[dict[str, Any]] = []
    for path in _source_files(src_dir):
        module = path.stem
        importers = sorted(imported_by.get(module) or [])
        refs = command_refs.get(module) or []
        if importers or refs:
            continue
        rows.append({
            "module": module,
            "path": _rel(path, root_dir),
            "has_cli": _has_main(path),
            "line": f"{module}.py has no non-test import and no routine/prompt command reference.",
        })
    priority_terms = ("insider", "options", "rationale", "stale", "parabolic", "orchestrator")
    priority = [
        row for row in rows
        if any(term in row["module"] for term in priority_terms)
    ]
    sample = priority[:12] or rows[:12]
    finding_rows = [
        _finding(
            finding_id=f"module_unwired_{row['module']}",
            area="module_wiring",
            title=f"{row['module']}.py has no visible wiring",
            line=row["line"],
            severity=WARN if any(term in row["module"] for term in priority_terms) else INFO,
            next_step="Either wire it through a routine/surface, document it as standalone/manual, or retire it.",
            evidence=[row["path"]],
        )
        for row in sample
    ]
    warn_count = sum(1 for row in finding_rows if row["severity"] == WARN)
    return {
        "status": "warn" if warn_count else "info" if rows else "ok",
        "line": (
            f"Module wiring sweep: {len(rows)} candidate orphan module(s); "
            f"{warn_count} priority warning(s)."
            if rows else
            "Module wiring sweep: no candidate orphan modules found."
        ),
        "candidate_count": len(rows),
        "priority_warning_count": warn_count,
        "rows": sample,
        "findings": finding_rows,
    }


def _prompt_stems(src_dir: Path) -> set[str]:
    routines = src_dir / "codex_routines"
    if not routines.is_dir():
        return set()
    return {_norm(path.stem) for path in routines.glob("*.md") if path.name.lower() != "readme.md"}


def _manifest_doc_stems(src_dir: Path) -> set[str]:
    manifest = _read_json(src_dir / "codex_routine_manifest.json", {})
    out: set[str] = set()
    for routine in manifest.get("routines") or []:
        if not isinstance(routine, dict):
            continue
        doc = routine.get("doc")
        if doc:
            out.add(_norm(Path(str(doc)).stem))
        rid = routine.get("id")
        if rid:
            out.add(_norm(rid))
    return out


def _cloud_routine_rows(src_dir: Path) -> list[dict[str, Any]]:
    payload = _read_json(src_dir / "cloud_automation_status.json", {})
    return [
        row for row in payload.get("routines") or []
        if isinstance(row, dict) and str(row.get("status") or "").upper() == "ACTIVE"
    ]


ROLE_COVERAGE_ALIASES = {
    "pre_market_source_intake": {"fundstrat_intake", "broker_position_intake", "catalyst_intake"},
    "fundstrat_pre_market_safety_sweep": {"fundstrat_intake"},
    "fs_inbox_catchup_preopen": {"fs_inbox_catchup"},
    "fs_inbox_catchup_midday": {"fs_inbox_catchup"},
    "fs_inbox_catchup_postclose": {"fs_inbox_catchup"},
    "fs_inbox_catchup_evening": {"fs_inbox_catchup"},
    "early_cockpit_build": {"daily_full_build"},
    "full_cockpit_build": {"daily_full_build"},
    "post_close_refresh": {"daily_full_build"},
    "fundstrat_daytime_watch": {"fundstrat_intake"},
    "fundstrat_after_hours_catchup": {"fundstrat_intake", "fs_inbox_catchup"},
    "uw_opportunity_cache": {"uw_cache_refresh"},
    "parabolic_cache": {"uw_cache_refresh"},
    "positions_sync": {"positions_sync_routine"},
    "off_hours_worker": {"off_hours_research"},
    "off_hours_research_queue": {"off_hours_research"},
    "deep_synthesis": {"daily_synthesis"},
}


def _stem_variants(value: str) -> set[str]:
    base = _norm(value)
    variants = {base}
    for suffix in (
        "_routine_prompt_v1",
        "_prompt_v1",
        "_prompt",
        "_v1",
        "_preopen",
        "_midday",
        "_postclose",
        "_evening",
        "_run",
        "_routine",
    ):
        if base.endswith(suffix):
            variants.add(base[: -len(suffix)])
    return {variant for variant in variants if variant}


def _covered_by_prompt(role: str, prompt_stems: set[str], manifest_stems: set[str], module_stems: set[str]) -> bool:
    role_n = _norm(role)
    variants = _stem_variants(role_n)
    variants |= {
        role_n.replace("_intake", ""),
        role_n.replace("_cache", ""),
        role_n.replace("_run", ""),
        role_n.replace("_routine", ""),
    }
    variants |= ROLE_COVERAGE_ALIASES.get(role_n, set())
    prompt_variants = set()
    for stem in prompt_stems:
        prompt_variants |= _stem_variants(stem)
    for variant in variants:
        if variant in prompt_variants or variant in manifest_stems or variant in module_stems:
            return True
        if any(variant and (variant in stem or stem in variant) for stem in prompt_variants):
            return True
    return False


def routine_schedule_section(src_dir: Path, root_dir: Path) -> dict[str, Any]:
    prompts = _prompt_stems(src_dir)
    manifest_stems = _manifest_doc_stems(src_dir)
    module_stems = {path.stem for path in _source_files(src_dir)}
    cloud_rows = _cloud_routine_rows(src_dir)
    scheduled_roles = {_norm(row.get("role") or row.get("automation_id")) for row in cloud_rows}

    prompt_only = sorted(
        stem for stem in prompts
        if not (_stem_variants(stem) & manifest_stems)
        and not any((_stem_variants(stem) & _stem_variants(role)) or any(v in role or role in v for v in _stem_variants(stem)) for role in scheduled_roles)
    )
    scheduled_without_doc = []
    for row in cloud_rows:
        role = str(row.get("role") or row.get("automation_id") or "")
        if not _covered_by_prompt(role, prompts, manifest_stems, module_stems):
            scheduled_without_doc.append({
                "routine_id": row.get("automation_id") or "",
                "role": role,
                "schedule": row.get("schedule") or "",
                "line": f"{role} is scheduled but has no repo prompt/manifest doc match.",
            })

    findings = []
    for stem in prompt_only[:10]:
        findings.append(_finding(
            finding_id=f"prompt_without_schedule_{stem}",
            area="routine_schedule",
            title=f"{stem} prompt is not visibly scheduled",
            line=f"src/codex_routines/{stem}.md is not referenced by the manifest or active cloud schedules.",
            severity=INFO,
            next_step="Register it, mark it retired, or document why it is manual-only.",
        ))
    for row in scheduled_without_doc[:10]:
        findings.append(_finding(
            finding_id=f"scheduled_without_repo_prompt_{_norm(row['role'])}",
            area="routine_schedule",
            title=f"{row['role']} lacks repo prompt coverage",
            line=row["line"],
            severity=INFO,
            next_step="Add a repo prompt/doc or map the schedule to an existing manifest entry.",
            evidence=[row["routine_id"], row["schedule"]],
        ))

    warn_count = sum(1 for row in findings if row["severity"] == WARN)
    return {
        "status": "warn" if warn_count else "info" if findings else "ok",
        "line": (
            f"Routine schedule sweep: {len(prompt_only)} prompt-only file(s), "
            f"{len(scheduled_without_doc)} scheduled routine(s) without repo prompt/doc coverage."
        ),
        "prompt_only": prompt_only,
        "scheduled_without_doc": scheduled_without_doc,
        "rows": scheduled_without_doc[:12],
        "findings": findings,
    }


def options_exit_cadence_section(src_dir: Path, root_dir: Path) -> dict[str, Any]:
    pattern_text = _read_text(src_dir / "pattern_engine.py")
    morning_text = _read_text(src_dir / "morning_scan.py")
    routine_text = _routine_text(root_dir, src_dir)
    stale_surface = "detect_stale_leaps" in pattern_text and "held_options" in morning_text
    cadence_code = (src_dir / "rationale_decay_v3.py").is_file()
    cadence_routine = "rationale_decay_v3.py" in routine_text or "options_expiry_preflight.py" in routine_text
    stale_uses_full_cadence = (
        "rationale_decay_v3" in pattern_text
        or "options_expiry_preflight" in pattern_text
        or "7-rule" in pattern_text.lower()
    )
    if cadence_routine or stale_uses_full_cadence:
        status = "ok"
        findings: list[dict[str, Any]] = []
        line = "Options-exit cadence: v11.10 7-rule cadence has visible routine or STALE-LEAPS wiring."
    elif stale_surface:
        status = "warn"
        line = (
            "Options-exit cadence: STALE-LEAPS surface exists, but v11.10 7-rule "
            "cadence is not visibly wired into a routine or the STALE-LEAPS path."
        )
        findings = [_finding(
            finding_id="options_exit_7_rule_cadence",
            area="options_exit",
            title="v11.10 options-exit cadence is not fully wired",
            line=line,
            severity=WARN,
            next_step="Wire rationale_decay_v3/options_expiry_preflight into Weekly Pilot, a routine, or STALE-LEAPS; otherwise document it as manual-only.",
            evidence=[
                "src/rationale_decay_v3.py present" if cadence_code else "src/rationale_decay_v3.py missing",
                "src/pattern_engine.py STALE-LEAPS present",
                "src/morning_scan.py held_options defaults to caller-supplied/not_checked",
            ],
        )]
    else:
        status = "warn"
        line = "Options-exit cadence: neither STALE-LEAPS nor v11.10 7-rule routine wiring is visible."
        findings = [_finding(
            finding_id="options_exit_missing_surface",
            area="options_exit",
            title="Options-exit cadence surface is missing",
            line=line,
            severity=WARN,
            next_step="Restore STALE-LEAPS or wire the 7-rule cadence into an existing routine.",
        )]
    return {
        "status": status,
        "line": line,
        "stale_leaps_surface": stale_surface,
        "cadence_code_present": cadence_code,
        "cadence_routine_present": cadence_routine,
        "stale_uses_full_cadence": stale_uses_full_cadence,
        "findings": findings,
        "rows": findings,
    }


def _queue_rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("rows", "items", "results", "queue"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def notion_queue_section(root_dir: Path, src_dir: Path, queue_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if queue_rows is None:
        local_queue = _read_json(src_dir / "system_improvement_queue.json", {})
        local_items = [
            row for row in local_queue.get("items") or []
            if isinstance(row, dict) and row.get("status") in {"queued", "active", "blocked"}
        ]
        finding = _finding(
            finding_id="notion_queue_not_checked",
            area="notion_queue",
            title="Notion System Update Queue not checked",
            line=(
                "Notion queue rows were not supplied to this read-only sweep; "
                "repo-local queue state cannot prove live Notion status."
            ),
            severity=WARN,
            next_step="Run with a Notion queue export/connector snapshot when doing the weekly debt review.",
        )
        return {
            "status": "not_checked",
            "line": (
                f"Notion queue sweep: not_checked; repo-local system queue has {len(local_items)} active/queued item(s)."
            ),
            "local_queue_active_or_queued": len(local_items),
            "rows": local_items[:10],
            "findings": [finding],
        }

    open_rows = [
        row for row in queue_rows
        if str(row.get("status") or row.get("Status") or "").lower() not in {"done", "closed", "archived"}
    ]
    findings: list[dict[str, Any]] = []
    for row in open_rows:
        title = str(row.get("title") or row.get("name") or row.get("Name") or row.get("id") or "queue row")
        expected_files = row.get("files") or row.get("expected_files") or row.get("repo_files") or []
        expected_files = [str(v) for v in expected_files if v]
        if not expected_files:
            continue
        present = [path for path in expected_files if (root_dir / path).exists()]
        if len(present) == len(expected_files):
            findings.append(_finding(
                finding_id=f"queue_open_repo_done_{_norm(title)[:48]}",
                area="notion_queue",
                title=f"Queue row may be stale: {title}",
                line=f"{title}: all listed repo files exist while queue row remains open.",
                severity=INFO,
                next_step="Verify live Notion state and close/update the row if the repo work is complete.",
                evidence=present,
            ))
    return {
        "status": "info" if findings else "ok",
        "line": f"Notion queue sweep: checked {len(open_rows)} open row(s); {len(findings)} repo-reality mismatch(es).",
        "open_count": len(open_rows),
        "rows": open_rows[:20],
        "findings": findings,
    }


def build_report(
    *,
    root_dir: str | Path = ROOT,
    src_dir: str | Path | None = None,
    queue_rows: list[dict[str, Any]] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    root = Path(root_dir)
    src = Path(src_dir) if src_dir else root / "src"
    sections = {
        "options_exit_cadence": options_exit_cadence_section(src, root),
        "module_wiring": module_wiring_section(src, root),
        "routine_schedule": routine_schedule_section(src, root),
        "notion_queue": notion_queue_section(root, src, queue_rows),
    }
    findings: list[dict[str, Any]] = []
    for section in sections.values():
        findings.extend(section.get("findings") or [])
    warning_count = sum(1 for row in findings if row.get("severity") == WARN)
    return {
        "generated_at": generated_at or _now_iso(),
        "status": "warn" if warning_count else "ok",
        "warning_count": warning_count,
        "finding_count": len(findings),
        "line": f"Integration debt: {warning_count} warning(s), {len(findings)} total finding(s).",
        "sections": sections,
        "findings": findings,
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Integration Debt Report",
        "",
        f"Generated: {report.get('generated_at') or ''}",
        "",
        f"Status: {report.get('status')} | warnings: {report.get('warning_count')} | findings: {report.get('finding_count')}",
        "",
        "## Findings",
        "",
    ]
    findings = report.get("findings") or []
    if not findings:
        lines.append("No integration-debt findings.")
    for idx, row in enumerate(findings, start=1):
        evidence = "; ".join(str(v) for v in row.get("evidence") or [])
        lines.extend([
            f"{idx}. [{str(row.get('severity') or '').upper()}] {row.get('title')}",
            f"   - Area: {row.get('area')}",
            f"   - Line: {row.get('line')}",
            f"   - Next: {row.get('next_step') or 'n/a'}",
        ])
        if evidence:
            lines.append(f"   - Evidence: {evidence}")
    lines.extend(["", "## Section Summary", ""])
    for key, section in (report.get("sections") or {}).items():
        lines.extend([
            f"### {key}",
            "",
            str(section.get("line") or section.get("status") or ""),
            "",
        ])
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any], *, out: str | Path = DEFAULT_REPORT_PATH, json_out: str | Path | None = None) -> None:
    _atomic_write_text(Path(out), markdown_report(report))
    if json_out:
        _atomic_write_json(Path(json_out), report)


def _load_queue_arg(path: str | None) -> list[dict[str, Any]] | None:
    if not path:
        return None
    payload = _read_json(Path(path), [])
    return _queue_rows_from_payload(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Investing OS integration-debt sweep")
    parser.add_argument("--root-dir", default=str(ROOT))
    parser.add_argument("--src-dir")
    parser.add_argument("--queue-json", help="Optional read-only Notion queue export/snapshot")
    parser.add_argument("--out", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--json-out", default="")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    report = build_report(
        root_dir=args.root_dir,
        src_dir=args.src_dir,
        queue_rows=_load_queue_arg(args.queue_json),
    )
    if not args.no_write:
        write_report(report, out=args.out, json_out=args.json_out)

    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(report["line"])
        for row in report.get("findings") or []:
            print(f"- {row['severity'].upper()} {row['area']}: {row['line']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
