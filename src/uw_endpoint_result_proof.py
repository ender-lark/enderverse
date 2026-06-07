#!/usr/bin/env python3
"""Summarize captured Unusual Whales endpoint result proof.

This module does not fetch UW data. It reads a normalized result-proof cache,
checks whether the rows are interpretable, and produces an operator-facing
audit block that can sit beside the no-fetch UW action runbook.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


RESULT_FILE_NAMES = ("uw_endpoint_results.json", "uw_endpoint_result_proof.json")
VALID_RESULT_STATUSES = {"confirmed", "contradicted", "neutral", "missing", "failed"}
DECISION_INTERPRETATION = {
    "confirmed": "supports",
    "contradicted": "contradicts",
    "neutral": "inconclusive",
    "missing": "missing",
    "failed": "missing",
}
ET = ZoneInfo("America/New_York")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _et_day(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return datetime.now(ET).date().isoformat()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ET)
        return parsed.astimezone(ET).date().isoformat()
    except ValueError:
        return text[:10]


def _parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ET)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _result_rows(payload: Any) -> tuple[list[Any], list[str]]:
    if payload is None:
        return [], []
    if isinstance(payload, list):
        return payload, []
    if isinstance(payload, dict):
        for key in ("results", "rows", "endpoint_results"):
            rows = payload.get(key)
            if rows is not None:
                if isinstance(rows, list):
                    return rows, []
                return [], [f"{key} must be a list"]
        return [], ["result proof payload must include results, rows, or endpoint_results"]
    return [], [f"result proof payload must be a JSON object or list, got {type(payload).__name__}"]


def _text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _normalize_row(row: Any, index: int) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(row, dict):
        return None, [f"results[{index}] must be a dict"]
    mode = _text(row, "mode", "profile", "scenario")
    endpoint = _text(row, "endpoint", "endpoint_name", "name")
    status = _text(row, "status", "result_status").lower()
    checked_at = _text(row, "checked_at", "timestamp", "as_of", "date")
    summary = _text(row, "summary", "line", "evidence")
    problems: list[str] = []
    if not mode:
        problems.append(f"results[{index}].mode is required")
    if not endpoint:
        problems.append(f"results[{index}].endpoint is required")
    if status not in VALID_RESULT_STATUSES:
        problems.append(
            f"results[{index}].status must be one of {sorted(VALID_RESULT_STATUSES)}, got {status!r}"
        )
    if not checked_at:
        problems.append(f"results[{index}].checked_at is required")
    if not summary:
        problems.append(f"results[{index}].summary is required")
    if problems:
        return None, problems
    normalized = {
        "mode": mode,
        "endpoint": endpoint,
        "ticker": _text(row, "ticker", "symbol"),
        "status": status,
        "decision_interpretation": DECISION_INTERPRETATION.get(status, "inconclusive"),
        "checked_at": checked_at,
        "summary": summary,
        "source": _text(row, "source", "evidence_url", "url"),
    }
    return normalized, []


def _runbook_modes(runbook: dict[str, Any]) -> set[str]:
    return {
        str(row.get("mode") or "").strip()
        for row in runbook.get("rows") or []
        if isinstance(row, dict) and row.get("mode")
    }


def load_uw_endpoint_results(
    src_dir: str | Path,
    *,
    override: str | Path | None = None,
) -> tuple[Any, Path | None, list[str]]:
    src = Path(src_dir)
    path = Path(override) if override else None
    if path is None:
        for name in RESULT_FILE_NAMES:
            candidate = src / name
            if candidate.is_file():
                path = candidate
                break
    if path is None:
        return None, None, []
    if not path.is_file():
        return None, path, []
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")), path, []
    except Exception as exc:
        return None, path, [f"UW endpoint result proof failed to read {path.name}: {exc}"]


def build_uw_endpoint_result_proof(
    payload: Any,
    runbook: dict[str, Any] | None = None,
    *,
    generated_at: str | None = None,
    result_path: str | Path | None = None,
    load_problems: list[str] | None = None,
) -> dict[str, Any]:
    runbook = runbook or {}
    runbook_rows = [row for row in runbook.get("rows") or [] if isinstance(row, dict)]
    runbook_modes = _runbook_modes(runbook)
    payload_rows, payload_problems = _result_rows(payload)
    problems = list(load_problems or []) + payload_problems
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(payload_rows):
        normalized, row_problems = _normalize_row(raw, index)
        problems.extend(row_problems)
        if normalized:
            rows.append(normalized)

    if not runbook_rows and not rows and not problems:
        return {
            "status": "checked_clear",
            "line": "UW endpoint proof: no active UW check sets to verify.",
            "count": 0,
            "counts": {},
            "rows": [],
            "blockers": [],
            "honesty_rule": "Endpoint proof is captured result evidence only; no rows means no endpoint evidence was used.",
        }

    if not rows:
        status = "failed" if problems else "not_checked"
        line = (
            f"UW endpoint proof: {len(problems)} problem(s); no valid captured endpoint results."
            if problems else
            "UW endpoint proof: no captured endpoint result proof; runbook remains instructions only."
        )
        return {
            "status": status,
            "line": line,
            "count": 0,
            "counts": {},
            "rows": [],
            "blockers": problems[:] if problems else ["captured UW endpoint results are missing"],
            "problems": problems,
            "result_path": str(result_path or ""),
            "honesty_rule": "Runbook instructions do not count as UW endpoint proof.",
        }

    build_day = _et_day(generated_at or _now_iso())
    counts = dict(Counter(row["status"] for row in rows))
    interpretation_counts = dict(Counter(row["decision_interpretation"] for row in rows))
    stale_rows = [row for row in rows if _et_day(row.get("checked_at")) != build_day]
    off_runbook = [
        row for row in rows
        if runbook_modes and row.get("mode") not in runbook_modes
    ]
    newest = max(
        (parsed for parsed in (_parse_dt(row.get("checked_at")) for row in rows) if parsed),
        default=None,
    )
    missing_or_failed = int(counts.get("missing") or 0) + int(counts.get("failed") or 0)
    inconclusive_count = int(interpretation_counts.get("inconclusive") or 0)
    blockers: list[str] = []
    if interpretation_counts.get("contradicts"):
        blockers.append("contradicted endpoint evidence requires re-check before acting")
    if inconclusive_count:
        blockers.append("inconclusive endpoint result(s) cannot promote related actions")
    if missing_or_failed:
        blockers.append("missing/failed endpoint result(s) keep related actions blocked")
    if stale_rows:
        blockers.append("one or more endpoint result rows are not same-session fresh")
    if off_runbook:
        blockers.append("one or more endpoint result rows do not match the current runbook modes")
    if problems:
        blockers.append("one or more endpoint proof rows are malformed and were ignored")

    line = (
        "UW endpoint proof: "
        f"{len(rows)} captured result(s); "
        f"supports={int(interpretation_counts.get('supports') or 0)}, "
        f"contradicts={int(interpretation_counts.get('contradicts') or 0)}, "
        f"inconclusive={inconclusive_count}, "
        f"missing={int(interpretation_counts.get('missing') or 0)}; "
        f"stale={len(stale_rows)}."
    )
    if newest:
        line += f" newest={newest.astimezone(ET).strftime('%Y-%m-%d %H:%M ET')}."
    return {
        "status": "failed" if problems else "has_data",
        "line": line,
        "count": len(rows),
        "counts": counts,
        "interpretation_counts": interpretation_counts,
        "newest_checked_at": newest.isoformat() if newest else "",
        "same_session_date": build_day,
        "stale_count": len(stale_rows),
        "off_runbook_count": len(off_runbook),
        "rows": rows,
        "blockers": blockers,
        "problems": problems,
        "result_path": str(result_path or ""),
        "honesty_rule": "Only interpreted endpoint result rows count as UW proof; neutral fetch success is inconclusive and cannot promote actions.",
    }


def _format_text(block: dict[str, Any]) -> str:
    lines = [block.get("line") or "UW endpoint proof"]
    if block.get("honesty_rule"):
        lines.append(f"honesty: {block['honesty_rule']}")
    for blocker in block.get("blockers") or []:
        lines.append(f"blocker: {blocker}")
    for row in block.get("rows") or []:
        ticker = f" {row.get('ticker')}" if row.get("ticker") else ""
        lines.append(
            f"- {row.get('mode')} {row.get('endpoint')}{ticker}: "
            f"{row.get('decision_interpretation') or row.get('status')} "
            f"({row.get('status')}) at {row.get('checked_at')} - {row.get('summary')}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize captured UW endpoint proof.")
    parser.add_argument("--results", default=str(Path(__file__).resolve().parent / "uw_endpoint_results.json"))
    parser.add_argument("--runbook", default=str(Path(__file__).resolve().parent / "latest_cockpit_feed.json"))
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    payload, path, problems = load_uw_endpoint_results(Path(args.results).parent, override=args.results)
    runbook_payload: dict[str, Any] = {}
    generated_at = ""
    runbook_path = Path(args.runbook)
    if runbook_path.is_file():
        raw = json.loads(runbook_path.read_text(encoding="utf-8-sig"))
        if isinstance(raw, dict) and isinstance(raw.get("uw_action_runbook"), dict):
            generated_at = str(raw.get("generated_at") or "")
            runbook_payload = raw.get("uw_action_runbook") or {}
        elif isinstance(raw, dict):
            runbook_payload = raw
    block = build_uw_endpoint_result_proof(
        payload,
        runbook_payload,
        generated_at=generated_at,
        result_path=path,
        load_problems=problems,
    )
    if args.format == "json":
        print(json.dumps(block, indent=2, sort_keys=True))
    else:
        print(_format_text(block))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
