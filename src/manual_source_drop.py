#!/usr/bin/env python3
"""Ingest one explicit manual source-drop file into safe source caches."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import catalyst_calendar_intake as catalyst_intake
import event_risk
import event_risk_intake
import signal_log_intake


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = ROOT / "src"
SECTION_ALIASES = {
    "event_risks": ("event_risks", "event_risk", "market_events", "sudden_events"),
    "signal_log": ("signal_log", "signals", "morning_scan"),
    "catalysts": ("catalysts", "catalyst_calendar"),
}


def _read_json(path: str | Path) -> Any:
    with Path(path).open(encoding="utf-8-sig") as fh:
        return json.load(fh)


def _payloads_from_inputs(paths: list[str | Path], *, stdin_json: bool = False) -> list[Any]:
    payloads = [_read_json(path) for path in paths]
    if stdin_json:
        payloads.append(json.load(sys.stdin))
    return payloads


def _section(payload: Any, canonical: str) -> Any:
    if not isinstance(payload, dict):
        return None
    for key in SECTION_ALIASES[canonical]:
        if key in payload:
            return payload[key]
    return None


def _merge_event_risks(
    payloads: list[Any],
    *,
    out: Path,
    summary: Path,
    merge_existing: bool,
    default_date: str,
    dry_run: bool,
) -> dict[str, Any] | None:
    incoming: list[dict] = []
    for payload in payloads:
        section = _section(payload, "event_risks")
        if section is not None:
            incoming.extend(event_risk.normalize_event_risks(section, default_date=default_date))
    if not incoming:
        return None
    existing = (
        event_risk.normalize_event_risks(event_risk_intake._read_json(out), default_date=default_date)
        if merge_existing and out.is_file()
        else []
    )
    rows = event_risk_intake._merge(existing, incoming) if existing else incoming
    problems = event_risk.validate_event_risks(rows)
    result = {
        "valid": not problems,
        "problems": problems,
        "out": str(out),
        "written": False,
        "input_rows": len(incoming),
        "stored": len(rows),
        "promoted": sum(1 for row in rows if row.get("severity") in {"critical", "high"}),
    }
    if not problems and not dry_run:
        event_risk_intake._atomic_write_json(out, rows)
        result["written"] = True
    if not dry_run:
        event_risk_intake._atomic_write_json(summary, result)
    return result


def _merge_signal_log(
    payloads: list[Any],
    *,
    out: Path,
    summary: Path,
    merge_existing: bool,
    dry_run: bool,
) -> dict[str, Any] | None:
    section_payloads = []
    for payload in payloads:
        section = _section(payload, "signal_log")
        if section is not None:
            section_payloads.append(section)
    incoming = signal_log_intake.normalize_signal_log(section_payloads)
    if not incoming:
        return None
    rows = incoming
    if merge_existing and out.is_file():
        rows = signal_log_intake.merge_rows(
            signal_log_intake.normalize_signal_log([signal_log_intake._read_json(out)]),
            incoming,
        )
    problems = signal_log_intake.validate_signal_log(rows)
    result = {
        "valid": not problems,
        "problems": problems,
        "out": str(out),
        "written": False,
        "rows": len(rows),
        "input_rows": len(incoming),
    }
    if not problems and not dry_run:
        signal_log_intake._atomic_write_json(out, rows)
        result["written"] = True
    if not dry_run:
        signal_log_intake._atomic_write_json(summary, result)
    return result


def _merge_catalysts(
    payloads: list[Any],
    *,
    out: Path,
    summary: Path,
    merge_existing: bool,
    default_source: str,
    dry_run: bool,
) -> dict[str, Any] | None:
    incoming: list[dict] = []
    for payload in payloads:
        section = _section(payload, "catalysts")
        if section is not None:
            incoming.extend(catalyst_intake._rows_from_payload(section))
    if not incoming:
        return None
    existing = catalyst_intake._read_json(out, default=[]) if merge_existing else []
    rows, result = catalyst_intake.merge_catalysts(
        existing,
        incoming,
        default_source=default_source,
    )
    result = {"parsed": True, **result, "out": str(out), "written": False}
    if not dry_run:
        catalyst_intake._atomic_write_json(out, rows)
        result["written"] = True
        catalyst_intake._atomic_write_json(summary, result)
    return result


def ingest_manual_source_drop(
    payloads: list[Any],
    *,
    src_dir: str | Path = DEFAULT_SRC,
    merge_existing: bool = True,
    default_date: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    src = Path(src_dir)
    as_of = default_date or date.today().isoformat()
    sections = {
        "event_risks": _merge_event_risks(
            payloads,
            out=src / "event_risks.json",
            summary=src / "event_risk_intake_summary.json",
            merge_existing=merge_existing,
            default_date=as_of,
            dry_run=dry_run,
        ),
        "signal_log": _merge_signal_log(
            payloads,
            out=src / "signal_log.json",
            summary=src / "signal_log_intake_summary.json",
            merge_existing=merge_existing,
            dry_run=dry_run,
        ),
        "catalysts": _merge_catalysts(
            payloads,
            out=src / "catalysts.json",
            summary=src / "catalyst_intake_summary.json",
            merge_existing=merge_existing,
            default_source="Manual Source Drop",
            dry_run=dry_run,
        ),
    }
    written = {key: value for key, value in sections.items() if value is not None}
    problems = [
        f"{key}: {problem}"
        for key, result in written.items()
        for problem in (result.get("problems") or [])
    ]
    return {
        "valid": not problems,
        "problems": problems,
        "dry_run": dry_run,
        "merge_existing": merge_existing,
        "sections_seen": sorted(written),
        "sections": written,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Ingest one explicit manual source-drop JSON")
    parser.add_argument("files", nargs="*")
    parser.add_argument("--stdin-json", action="store_true")
    parser.add_argument("--src-dir", default=str(DEFAULT_SRC))
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--no-merge-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not args.files and not args.stdin_json:
        print("no input files or --stdin-json supplied", file=sys.stderr)
        return 2
    report = ingest_manual_source_drop(
        _payloads_from_inputs(args.files, stdin_json=args.stdin_json),
        src_dir=args.src_dir,
        merge_existing=not args.no_merge_existing,
        default_date=args.date,
        dry_run=args.dry_run,
    )
    print(json.dumps(report, indent=2))
    return 0 if report["valid"] and report["sections_seen"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
