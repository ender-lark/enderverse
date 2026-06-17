#!/usr/bin/env python3
"""Apply explicit operator interpretations to captured UW endpoint proof.

The capture file proves only that approved endpoints were fetched. A directional
read must be a separate operator interpretation tied to one captured neutral row
by mode, endpoint, ticker, and checked_at.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


INTERPRETATION_FILE_NAME = "uw_endpoint_interpretations.json"
VALID_OPERATOR_STATUSES = {"confirmed", "contradicted"}
ROW_KEYS = ("results", "rows", "endpoint_results")
HONESTY_RULE = (
    "Only an explicit operator interpretation tied to a captured neutral row can "
    "convert UW proof to confirmed or contradicted; neutral rows without that "
    "record stay inconclusive."
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _ticker(value: Any) -> str:
    return str(value or "").strip().upper()


def _target_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        _text(row, "mode", "profile", "scenario"),
        _text(row, "endpoint", "endpoint_name", "name"),
        _ticker(row.get("ticker") or row.get("symbol")),
        _text(row, "checked_at", "capture_checked_at", "timestamp", "as_of"),
    )


def _target_key_without_checked_at(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _text(row, "mode", "profile", "scenario"),
        _text(row, "endpoint", "endpoint_name", "name"),
        _ticker(row.get("ticker") or row.get("symbol")),
    )


def _row_list(payload: Any) -> tuple[list[Any], str | None, list[str]]:
    if payload is None:
        return [], None, []
    if isinstance(payload, list):
        return payload, None, []
    if isinstance(payload, dict):
        for key in ROW_KEYS:
            rows = payload.get(key)
            if rows is not None:
                if isinstance(rows, list):
                    return rows, key, []
                return [], key, [f"{key} must be a list"]
        return [], None, ["payload must include results, rows, or endpoint_results"]
    return [], None, [f"payload must be a JSON object or list, got {type(payload).__name__}"]


def _interpretation_rows(payload: Any) -> tuple[list[Any], list[str]]:
    if payload is None:
        return [], []
    if isinstance(payload, list):
        return payload, []
    if isinstance(payload, dict):
        for key in ("interpretations", "rows"):
            rows = payload.get(key)
            if rows is not None:
                if isinstance(rows, list):
                    return rows, []
                return [], [f"{key} must be a list"]
        return [], []
    return [], [f"interpretation payload must be a JSON object or list, got {type(payload).__name__}"]


def normalize_interpretation(row: Any, index: int = 0) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(row, dict):
        return None, [f"interpretations[{index}] must be a dict"]
    mode = _text(row, "mode", "profile", "scenario")
    endpoint = _text(row, "endpoint", "endpoint_name", "name")
    checked_at = _text(row, "checked_at", "capture_checked_at", "timestamp", "as_of")
    status = _text(row, "status", "result_status").lower()
    summary = _text(row, "summary", "evidence", "line")
    interpreted_at = _text(row, "interpreted_at", "created_at", "timestamped_at")
    problems: list[str] = []
    if not mode:
        problems.append(f"interpretations[{index}].mode is required")
    if not endpoint:
        problems.append(f"interpretations[{index}].endpoint is required")
    if not checked_at:
        problems.append(f"interpretations[{index}].checked_at is required")
    if status not in VALID_OPERATOR_STATUSES:
        problems.append(
            f"interpretations[{index}].status must be one of {sorted(VALID_OPERATOR_STATUSES)}, got {status!r}"
        )
    if not summary:
        problems.append(f"interpretations[{index}].summary is required")
    if not interpreted_at:
        problems.append(f"interpretations[{index}].interpreted_at is required")
    if problems:
        return None, problems
    normalized = {
        "mode": mode,
        "endpoint": endpoint,
        "ticker": _ticker(row.get("ticker") or row.get("symbol")),
        "checked_at": checked_at,
        "status": status,
        "summary": summary,
        "interpreted_at": interpreted_at,
        "operator": _text(row, "operator", "by"),
        "source": _text(row, "source") or "operator_uw_interpretation",
    }
    return normalized, []


def load_uw_endpoint_interpretations(
    src_dir: str | Path,
    *,
    override: str | Path | None = None,
) -> tuple[list[dict[str, Any]], Path | None, list[str]]:
    src = Path(src_dir)
    path = Path(override) if override else src / INTERPRETATION_FILE_NAME
    if not path.is_file():
        return [], path if override else None, []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return [], path, [f"UW endpoint interpretations failed to read {path.name}: {exc}"]
    rows, payload_problems = _interpretation_rows(payload)
    problems = list(payload_problems)
    normalized_rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for index, raw in enumerate(rows):
        normalized, row_problems = normalize_interpretation(raw, index)
        problems.extend(row_problems)
        if not normalized:
            continue
        key = _target_key(normalized)
        if key in seen:
            problems.append(
                "duplicate UW endpoint interpretation target: "
                + " ".join(part for part in key if part)
            )
            continue
        seen.add(key)
        normalized_rows.append(normalized)
    return normalized_rows, path, problems


def apply_operator_interpretations(
    capture_payload: Any,
    interpretations: list[dict[str, Any]],
) -> tuple[Any, dict[str, Any]]:
    summary: dict[str, Any] = {
        "available": len(interpretations),
        "applied": 0,
        "unmatched": 0,
        "counts": {},
        "problems": [],
        "honesty_rule": HONESTY_RULE,
    }
    if not interpretations:
        return capture_payload, summary

    payload = copy.deepcopy(capture_payload)
    rows, _, row_problems = _row_list(payload)
    if row_problems:
        summary["problems"].extend(row_problems)
        summary["unmatched"] = len(interpretations)
        return payload, summary
    if not rows:
        summary["problems"].append("operator interpretations present but captured UW endpoint results are missing")
        summary["unmatched"] = len(interpretations)
        return payload, summary

    by_key = {_target_key(row): row for row in interpretations}
    applied_keys: set[tuple[str, str, str, str]] = set()
    counts: Counter[str] = Counter()
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        status = _text(raw, "status", "result_status").lower()
        if status != "neutral":
            continue
        key = _target_key(raw)
        interpretation = by_key.get(key)
        if not interpretation:
            continue
        raw["capture_status"] = status
        raw["capture_summary"] = _text(raw, "summary", "line", "evidence")
        raw["status"] = interpretation["status"]
        raw["summary"] = interpretation["summary"]
        raw["source"] = interpretation["source"]
        raw["operator_interpretation"] = {
            "status": interpretation["status"],
            "summary": interpretation["summary"],
            "interpreted_at": interpretation["interpreted_at"],
            "operator": interpretation.get("operator") or "",
            "honesty_rule": HONESTY_RULE,
        }
        applied_keys.add(key)
        counts[interpretation["status"]] += 1

    unmatched = [row for row in interpretations if _target_key(row) not in applied_keys]
    summary["applied"] = len(applied_keys)
    summary["unmatched"] = len(unmatched)
    summary["counts"] = dict(counts)
    for row in unmatched:
        summary["problems"].append(
            "operator interpretation did not match a captured neutral UW endpoint row: "
            + " ".join(part for part in _target_key(row) if part)
        )
    if isinstance(payload, dict):
        payload["operator_interpretation_summary"] = summary
    return payload, summary


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8-sig") as fh:
        return json.load(fh)


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".uw_interpret.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _neutral_capture_matches(capture_payload: Any, row: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    rows, _, problems = _row_list(capture_payload)
    if problems:
        return [], problems
    target = _target_key_without_checked_at(row)
    checked_at = _text(row, "checked_at")
    matches = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        if _target_key_without_checked_at(raw) != target:
            continue
        if checked_at and _text(raw, "checked_at", "capture_checked_at", "timestamp", "as_of") != checked_at:
            continue
        if _text(raw, "status", "result_status").lower() == "neutral":
            matches.append(raw)
    return matches, []


def complete_interpretation_from_capture(
    row: dict[str, Any],
    capture_payload: Any,
) -> tuple[dict[str, Any] | None, list[str]]:
    matches, problems = _neutral_capture_matches(capture_payload, row)
    if problems:
        return None, problems
    if not matches:
        return None, ["no captured neutral UW endpoint row matches the requested interpretation"]
    if len(matches) > 1 and not row.get("checked_at"):
        return None, ["multiple captured neutral rows match; pass --checked-at to choose one"]
    out = dict(row)
    if not out.get("checked_at"):
        out["checked_at"] = _text(matches[0], "checked_at", "capture_checked_at", "timestamp", "as_of")
    return out, []


def _upsert_interpretation(rows: list[dict[str, Any]], row: dict[str, Any]) -> list[dict[str, Any]]:
    key = _target_key(row)
    kept = [existing for existing in rows if _target_key(existing) != key]
    kept.append(row)
    return kept


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Record an explicit UW endpoint interpretation.")
    parser.add_argument("--results", default=str(Path(__file__).resolve().parent / "uw_endpoint_results.json"))
    parser.add_argument(
        "--interpretations",
        default=str(Path(__file__).resolve().parent / INTERPRETATION_FILE_NAME),
    )
    parser.add_argument("--mode", required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--ticker", default="")
    parser.add_argument("--checked-at", default="")
    parser.add_argument("--status", required=True, choices=sorted(VALID_OPERATOR_STATUSES))
    parser.add_argument("--summary", required=True)
    parser.add_argument("--operator", default="")
    parser.add_argument("--interpreted-at", default="")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    args = parser.parse_args(argv)

    results_path = Path(args.results)
    interpretation_path = Path(args.interpretations)
    capture_payload = _load_json(results_path)
    requested = {
        "mode": args.mode,
        "endpoint": args.endpoint,
        "ticker": args.ticker,
        "checked_at": args.checked_at,
        "status": args.status,
        "summary": args.summary,
        "operator": args.operator,
        "interpreted_at": args.interpreted_at or _now_iso(),
        "source": "operator_uw_interpretation",
    }
    completed, complete_problems = complete_interpretation_from_capture(requested, capture_payload)
    if complete_problems or completed is None:
        report = {"written": False, "problems": complete_problems, "path": str(interpretation_path)}
        print(json.dumps(report, indent=2) if args.format == "json" else "\n".join(complete_problems))
        return 2
    normalized, normalize_problems = normalize_interpretation(completed, 0)
    if normalize_problems or normalized is None:
        report = {"written": False, "problems": normalize_problems, "path": str(interpretation_path)}
        print(json.dumps(report, indent=2) if args.format == "json" else "\n".join(normalize_problems))
        return 2

    existing_rows, _, load_problems = load_uw_endpoint_interpretations(
        interpretation_path.parent,
        override=interpretation_path,
    )
    if load_problems:
        report = {"written": False, "problems": load_problems, "path": str(interpretation_path)}
        print(json.dumps(report, indent=2) if args.format == "json" else "\n".join(load_problems))
        return 2
    rows = _upsert_interpretation(existing_rows, normalized)
    payload = {
        "generated_at": _now_iso(),
        "source": "operator_uw_interpretation",
        "honesty_rule": HONESTY_RULE,
        "interpretations": rows,
    }
    _write_json_atomic(interpretation_path, payload)
    report = {
        "written": True,
        "path": str(interpretation_path),
        "interpretations": len(rows),
        "target": {
            "mode": normalized["mode"],
            "endpoint": normalized["endpoint"],
            "ticker": normalized["ticker"],
            "checked_at": normalized["checked_at"],
            "status": normalized["status"],
        },
        "honesty_rule": HONESTY_RULE,
    }
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        ticker = f" {normalized['ticker']}" if normalized["ticker"] else ""
        print(
            "recorded UW endpoint interpretation: "
            f"{normalized['mode']} {normalized['endpoint']}{ticker} "
            f"{normalized['status']} at {normalized['checked_at']}"
        )
        print(f"honesty: {HONESTY_RULE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
