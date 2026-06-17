#!/usr/bin/env python3
"""Find capture-only loose-thread candidates from recent Codex repo activity."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import cloud_routine_receipts


ROOT = Path(__file__).resolve().parents[1]
ROUTINE_ID = "investing-os-loose-thread-sweep"
DEFAULT_RECEIPTS = ROOT / "src" / "cloud_routine_receipts.json"
DEFAULT_LOOKBACK_HOURS = 24
ET = ZoneInfo("America/New_York")

ROUTE_RESEARCH = "research_queue"
ROUTE_SYSTEM = "system_update_queue"
ROUTE_SOURCE_CALL = "source_call_log"
ROUTE_DECISION = "decisions_log"

ROUTE_TARGETS = {
    ROUTE_RESEARCH: {
        "label": "Research Queue",
        "data_source_id": "cab89576-0933-40b0-ad2e-6f9a6188e804",
    },
    ROUTE_SYSTEM: {
        "label": "System Update Queue",
        "data_source_id": "968cfff4-369c-40bb-b748-5633b9ff7685",
    },
    ROUTE_SOURCE_CALL: {
        "label": "Source Call Log",
        "data_source_id": "e7def40e-1492-458a-9de8-bd77cd3f8471",
    },
    ROUTE_DECISION: {
        "label": "Decisions Log",
        "data_source_id": "632c97f1-192a-4933-8682-60c730446caf",
    },
}

MARKER_RE = re.compile(
    r"\b(TODO|FOLLOW[-_ ]?UP|DEFER(?:RED)?|PUNT(?:ED)?|DO LATER|LATER)\b",
    re.IGNORECASE,
)
TABLE_SPLIT_RE = re.compile(r"(?<!\\)\|")


@dataclass(frozen=True)
class Candidate:
    route: str
    target_label: str
    target_data_source_id: str
    title: str
    why: str
    source_type: str
    source_ref: str
    source_date: str
    evidence: str
    staleness_check: str = "content-based review required before writing"


def _parse_dt(value: Any) -> datetime | None:
    parsed = cloud_routine_receipts.parse_dt(value)
    if not parsed:
        return None
    return parsed.astimezone(timezone.utc)


def cutoff_from_receipts(
    receipts_path: str | Path = DEFAULT_RECEIPTS,
    *,
    routine_id: str = ROUTINE_ID,
    default_lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    now: datetime | None = None,
) -> datetime:
    """Return the newest prior sweep receipt time, or a bounded fallback window."""
    payload = cloud_routine_receipts.load_receipts(receipts_path)
    matching = [
        _parse_dt(row.get("recorded_at"))
        for row in payload.get("receipts", [])
        if isinstance(row, dict) and row.get("routine_id") == routine_id
    ]
    matching = [dt for dt in matching if dt is not None]
    if matching:
        return max(matching)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc) - timedelta(hours=default_lookback_hours)


def _run_git(repo: Path, args: list[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    )
    return proc.stdout


def _route_for_text(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("source call", "fundstrat", "analyst call", "analyst note")):
        return ROUTE_SOURCE_CALL
    if any(token in lowered for token in ("firm decision", "decision log", "operator decided", "final decision")):
        return ROUTE_DECISION
    if any(
        token in lowered
        for token in (
            "system",
            "tooling",
            "automation",
            "routine",
            "test",
            "validator",
            "dashboard",
            "workboard",
            "github",
            "ci",
            "bug",
            "prompt",
            "script",
            "module",
            "wire",
            "rewire",
        )
    ):
        return ROUTE_SYSTEM
    return ROUTE_RESEARCH


def _candidate(
    *,
    title: str,
    why: str,
    source_type: str,
    source_ref: str,
    source_date: str,
    evidence: str,
) -> Candidate:
    route = _route_for_text(" ".join([title, why, evidence]))
    target = ROUTE_TARGETS[route]
    return Candidate(
        route=route,
        target_label=target["label"],
        target_data_source_id=target["data_source_id"],
        title=_compact(title, limit=140),
        why=_compact(why, limit=280),
        source_type=source_type,
        source_ref=source_ref,
        source_date=source_date,
        evidence=_compact(evidence, limit=500),
    )


def _compact(text: str, *, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _is_loose_thread_text(text: str) -> bool:
    lowered = text.lower()
    if MARKER_RE.search(text):
        return True
    return any(
        phrase in lowered
        for phrase in (
            "follow-up",
            "follow up",
            "deferred to",
            "left for",
            "next slice",
            "not yet wired",
            "pending follow",
            "parked",
            "backlog",
        )
    )


def collect_commit_candidates(repo: Path, cutoff: datetime) -> list[Candidate]:
    since = cutoff.astimezone(timezone.utc).isoformat()
    try:
        stdout = _run_git(
            repo,
            [
                "log",
                f"--since={since}",
                "--pretty=format:%H%x1f%aI%x1f%an%x1f%s",
                "--no-merges",
            ],
        )
    except subprocess.CalledProcessError:
        return []
    candidates: list[Candidate] = []
    for line in stdout.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 4:
            continue
        sha, authored_at, author, subject = parts
        if not _is_loose_thread_text(subject):
            continue
        candidates.append(
            _candidate(
                title=f"Follow up from commit: {subject}",
                why="Recent Codex commit message appears to park or defer follow-up work.",
                source_type="commit",
                source_ref=sha[:12],
                source_date=authored_at,
                evidence=f"{author}: {subject}",
            )
        )
    return candidates


def _parse_workboard_stamp(text: str) -> datetime | None:
    cleaned = text.strip().replace(" ET", "")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
        return parsed.replace(tzinfo=ET).astimezone(timezone.utc)
    return None


def collect_workboard_candidates(path: str | Path, cutoff: datetime) -> list[Candidate]:
    path = Path(path)
    if not path.is_file():
        return []
    candidates: list[Candidate] = []
    for idx, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        if not line.startswith("|") or "---" in line:
            continue
        cells = [cell.strip() for cell in TABLE_SPLIT_RE.split(line.strip("|"))]
        if len(cells) < 6 or cells[0].lower() == "id":
            continue
        row_id, agent, scope, files, status, stamp = cells[:6]
        if "codex" not in agent.lower():
            continue
        parsed_stamp = _parse_workboard_stamp(stamp)
        if parsed_stamp and parsed_stamp < cutoff:
            continue
        if not _is_loose_thread_text(" ".join([scope, files, status])):
            continue
        candidates.append(
            _candidate(
                title=f"Review Workboard loose thread: {row_id}",
                why=scope,
                source_type="workboard",
                source_ref=f"{path.as_posix()}:{idx}",
                source_date=stamp,
                evidence=f"{row_id} | {status} | {files}",
            )
        )
    return candidates


def collect_marker_candidates(paths: list[Path], cutoff: datetime) -> list[Candidate]:
    candidates: list[Candidate] = []
    for base in paths:
        if not base.exists():
            continue
        files = [base] if base.is_file() else sorted(base.rglob("*"))
        for path in files:
            if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
                continue
            try:
                modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            if modified < cutoff:
                continue
            for idx, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
                if not MARKER_RE.search(line):
                    continue
                title = re.sub(MARKER_RE, "", line).strip(" -:\t") or path.stem
                candidates.append(
                    _candidate(
                        title=f"Capture marker: {title}",
                        why="Recent task note contains a loose-thread marker.",
                        source_type="marker",
                        source_ref=f"{path.as_posix()}:{idx}",
                        source_date=modified.isoformat(),
                        evidence=line.strip(),
                    )
                )
    return candidates


def dedupe_candidates(candidates: list[Candidate]) -> list[Candidate]:
    seen: set[str] = set()
    unique: list[Candidate] = []
    for candidate in candidates:
        key = re.sub(r"[^a-z0-9]+", " ", f"{candidate.route} {candidate.title} {candidate.source_ref}".lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def collect_candidates(
    *,
    repo: str | Path = ROOT,
    receipts_path: str | Path = DEFAULT_RECEIPTS,
    default_lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    marker_paths: list[str | Path] | None = None,
) -> dict[str, Any]:
    repo = Path(repo)
    cutoff = cutoff_from_receipts(
        receipts_path,
        default_lookback_hours=default_lookback_hours,
    )
    marker_bases = [repo / "docs" / "codex_tasks"]
    if marker_paths is not None:
        marker_bases = [Path(p) if Path(p).is_absolute() else repo / p for p in marker_paths]
    candidates = dedupe_candidates(
        [
            *collect_commit_candidates(repo, cutoff),
            *collect_workboard_candidates(repo / "docs" / "WORKBOARD.md", cutoff),
            *collect_marker_candidates(marker_bases, cutoff),
        ]
    )
    return {
        "routine_id": ROUTINE_ID,
        "cutoff": cutoff.isoformat().replace("+00:00", "Z"),
        "candidate_count": len(candidates),
        "candidates": [asdict(candidate) for candidate in candidates],
        "rules": {
            "capture_only": True,
            "dedupe_before_write": True,
            "content_staleness_required": True,
            "notion_write_performed_by_this_script": False,
        },
        "targets": ROUTE_TARGETS,
    }


def format_text(report: dict[str, Any]) -> str:
    lines = [
        f"Loose-thread sweep candidates since {report.get('cutoff')}: {report.get('candidate_count')}",
    ]
    candidates = report.get("candidates") or []
    if not candidates:
        lines.append("nothing new")
        return "\n".join(lines)
    for idx, row in enumerate(candidates, start=1):
        lines.append(
            f"{idx}. [{row.get('target_label')}] {row.get('title')} "
            f"({row.get('source_ref')})"
        )
    return "\n".join(lines)


def _self_test() -> bool:
    now = datetime(2026, 6, 17, 2, 0, tzinfo=timezone.utc)
    assert _route_for_text("fix automation prompt parser") == ROUTE_SYSTEM
    assert _route_for_text("Fundstrat analyst call on RYF") == ROUTE_SOURCE_CALL
    assert _route_for_text("firm decision to keep GOOGL open") == ROUTE_DECISION
    assert _route_for_text("research whether INTC is still timely") == ROUTE_RESEARCH
    assert _is_loose_thread_text("TODO: wire queue capture")
    assert _is_loose_thread_text("deferred to next slice")
    assert cutoff_from_receipts(
        Path("__missing_receipts__.json"),
        now=now,
        default_lookback_hours=2,
    ) == now - timedelta(hours=2)
    print("loose_thread_sweep self-test: PASS")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(ROOT))
    parser.add_argument("--receipts", default=str(DEFAULT_RECEIPTS))
    parser.add_argument("--default-lookback-hours", type=int, default=DEFAULT_LOOKBACK_HOURS)
    parser.add_argument("--marker-path", action="append", dest="marker_paths")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return 0 if _self_test() else 1

    report = collect_candidates(
        repo=args.repo,
        receipts_path=args.receipts,
        default_lookback_hours=args.default_lookback_hours,
        marker_paths=args.marker_paths,
    )
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
