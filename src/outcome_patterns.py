#!/usr/bin/env python3
"""Outcome-pattern loop for Trade Outcomes and Decisions Log exports.

The detector is intentionally conservative: it groups only explicit
driver/category tags from exported rows. It does not infer drivers from prose,
does not assign blame, and does not create trade recommendations.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SRC = Path(__file__).resolve().parent
DEFAULT_TRADE_OUTCOMES_PATHS = (
    SRC / "trade_outcomes.json",
    SRC / "trade_outcomes_export.json",
    SRC / "outcomes.json",
)
DEFAULT_DECISION_PATHS = (
    SRC / "decisions_log.json",
    SRC / "decisions_export.json",
)
DEFAULT_DISPOSITIONS_PATH = SRC / "dispositions.jsonl"
DEFAULT_REPORT_PATH = SRC / "outcome_patterns.json"

THRESHOLD_DEFAULT = 3


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _norm_label(value: Any) -> str:
    text = _text(value)
    return " ".join(text.replace("_", " ").replace("-", " ").split()).lower()


def _display_label(value: Any) -> str:
    text = _text(value)
    return " ".join(text.replace("_", " ").split()) if text else ""


def _notion_value(value: Any) -> Any:
    """Flatten common Notion export property shapes."""
    if isinstance(value, dict):
        if "name" in value:
            return value.get("name")
        if "select" in value:
            return _notion_value(value.get("select"))
        if "multi_select" in value:
            return [_notion_value(row) for row in value.get("multi_select") or []]
        if "title" in value:
            return " ".join(_text(part.get("plain_text") or part.get("text", {}).get("content")) for part in value.get("title") or [])
        if "rich_text" in value:
            return " ".join(_text(part.get("plain_text") or part.get("text", {}).get("content")) for part in value.get("rich_text") or [])
        if "number" in value:
            return value.get("number")
        if "checkbox" in value:
            return value.get("checkbox")
        if "date" in value:
            date_value = value.get("date") or {}
            return date_value.get("start") if isinstance(date_value, dict) else date_value
    return value


def _props(row: dict[str, Any]) -> dict[str, Any]:
    props = row.get("properties")
    if isinstance(props, dict):
        out = dict(row)
        for key, value in props.items():
            out.setdefault(key, _notion_value(value))
            out.setdefault(key.lower().replace(" ", "_"), _notion_value(value))
        return out
    return row


def _flatten_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in (
            "outcomes",
            "trade_outcomes",
            "decisions",
            "rows",
            "items",
            "results",
            "payload",
        ):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
            if isinstance(value, dict):
                nested = _flatten_rows(value)
                if nested:
                    return nested
    return []


def load_rows(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.is_file():
        return []
    text = p.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    if p.suffix.lower() == ".jsonl":
        rows = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows
    try:
        return _flatten_rows(json.loads(text))
    except json.JSONDecodeError:
        return []


def _first(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in row and row.get(key) not in (None, "", [], {}):
            return row.get(key)
    lowered = {str(k).lower().replace(" ", "_"): v for k, v in row.items()}
    for key in keys:
        lk = key.lower().replace(" ", "_")
        if lowered.get(lk) not in (None, "", [], {}):
            return lowered[lk]
    return None


def _listify(value: Any) -> list[Any]:
    value = _notion_value(value)
    if value in (None, "", [], {}):
        return []
    if isinstance(value, list):
        return [item for item in value if _text(item)]
    if isinstance(value, str):
        if "," in value:
            return [part.strip() for part in value.split(",") if part.strip()]
        return [value]
    return [value]


def _record_from_row(row: dict[str, Any], *, source: str) -> dict[str, Any] | None:
    row = _props(row)
    category = _first(row, (
        "category",
        "Category",
        "outcome_category",
        "decision_category",
        "event_category",
        "Event Type",
        "event_type",
        "change_type",
        "verb",
    ))
    drivers_raw = []
    for key in (
        "driver_tags",
        "Driver Tags",
        "drivers",
        "Drivers",
        "driver",
        "Driver",
        "reason_tags",
        "Reason Tags",
        "category_tags",
        "Category Tags",
    ):
        drivers_raw.extend(_listify(row.get(key)))
    drivers = []
    seen = set()
    for driver in drivers_raw:
        norm = _norm_label(driver)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        drivers.append({"key": norm, "label": _display_label(driver)})
    category_label = _display_label(category) or ("decision" if source == "decisions" else "outcome")
    category_key = _norm_label(category_label) or source
    if not drivers:
        return None
    return {
        "source": source,
        "id": _text(_first(row, ("id", "card_id", "outcome_id", "page_id"))) or "",
        "ticker": _text(_first(row, ("ticker", "Ticker", "symbol", "Symbol"))).upper(),
        "category_key": category_key,
        "category": category_label,
        "drivers": drivers,
    }


def normalize_records(
    *,
    trade_outcomes: list[dict[str, Any]] | None = None,
    decisions: list[dict[str, Any]] | None = None,
    dispositions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for source, rows in (
        ("trade_outcomes", trade_outcomes or []),
        ("decisions", decisions or []),
        ("decisions", dispositions or []),
    ):
        for row in rows:
            if not isinstance(row, dict):
                continue
            rec = _record_from_row(row, source=source)
            if rec:
                records.append(rec)
    return records


def detect_patterns(records: list[dict[str, Any]], *, threshold: int = THRESHOLD_DEFAULT) -> dict[str, Any]:
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    category_labels: dict[str, str] = {}
    for record in records:
        key = _text(record.get("category_key")) or "uncategorized"
        by_category[key].append(record)
        category_labels.setdefault(key, _text(record.get("category")) or key)

    findings: list[dict[str, Any]] = []
    insufficient: list[dict[str, Any]] = []
    for category_key in sorted(by_category):
        rows = by_category[category_key]
        total = len(rows)
        counts: Counter[str] = Counter()
        labels: dict[str, str] = {}
        tickers: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            for driver in row.get("drivers") or []:
                dkey = driver.get("key")
                if not dkey:
                    continue
                counts[dkey] += 1
                labels.setdefault(dkey, driver.get("label") or dkey)
                if row.get("ticker"):
                    tickers[dkey].add(str(row["ticker"]))
        category = category_labels.get(category_key) or category_key
        category_findings = []
        for driver_key, count in counts.most_common():
            if count < threshold:
                continue
            line = f"{count} of {total} {category} shared {labels.get(driver_key) or driver_key}"
            category_findings.append({
                "category": category,
                "category_key": category_key,
                "driver": labels.get(driver_key) or driver_key,
                "driver_key": driver_key,
                "count": count,
                "sample_size": total,
                "line": line,
                "tickers": sorted(tickers.get(driver_key) or []),
            })
        if category_findings:
            findings.extend(category_findings)
        else:
            top = counts.most_common(1)
            insufficient.append({
                "category": category,
                "category_key": category_key,
                "sample_size": total,
                "top_driver": labels.get(top[0][0]) if top else "",
                "top_count": top[0][1] if top else 0,
                "line": f"insufficient sample: {total} {category} row(s), no driver reached {threshold}",
            })
    status = "has_patterns" if findings else "insufficient_sample" if records else "not_checked"
    return {
        "status": status,
        "threshold": threshold,
        "record_count": len(records),
        "finding_count": len(findings),
        "findings": findings,
        "insufficient": insufficient,
        "line": (
            f"Outcome patterns: {len(findings)} driver pattern(s) from {len(records)} tagged row(s)."
            if findings else
            f"Outcome patterns: insufficient sample from {len(records)} tagged row(s)."
            if records else
            "Outcome patterns: not_checked - no tagged Trade Outcomes or Decisions rows supplied."
        ),
        "honesty_rule": "Only explicit driver/category tags are grouped; prose reasons are not inferred into patterns.",
    }


def build_report(
    *,
    trade_outcomes: list[dict[str, Any]] | None = None,
    decisions: list[dict[str, Any]] | None = None,
    dispositions: list[dict[str, Any]] | None = None,
    threshold: int = THRESHOLD_DEFAULT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    records = normalize_records(
        trade_outcomes=trade_outcomes,
        decisions=decisions,
        dispositions=dispositions,
    )
    report = detect_patterns(records, threshold=threshold)
    report["generated_at"] = generated_at or _now_iso()
    return report


def default_rows(paths: tuple[Path, ...]) -> list[dict[str, Any]]:
    for path in paths:
        rows = load_rows(path)
        if rows:
            return rows
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect repeated outcome/decision drivers")
    parser.add_argument("--trade-outcomes", action="append", default=[])
    parser.add_argument("--decisions", action="append", default=[])
    parser.add_argument("--dispositions", default=str(DEFAULT_DISPOSITIONS_PATH))
    parser.add_argument("--threshold", type=int, default=THRESHOLD_DEFAULT)
    parser.add_argument("--out", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    trade_rows: list[dict[str, Any]] = []
    decision_rows: list[dict[str, Any]] = []
    for path in args.trade_outcomes:
        trade_rows.extend(load_rows(path))
    for path in args.decisions:
        decision_rows.extend(load_rows(path))
    if not args.trade_outcomes:
        trade_rows = default_rows(DEFAULT_TRADE_OUTCOMES_PATHS)
    if not args.decisions:
        decision_rows = default_rows(DEFAULT_DECISION_PATHS)
    disposition_rows = load_rows(args.dispositions) if args.dispositions else []

    report = build_report(
        trade_outcomes=trade_rows,
        decisions=decision_rows,
        dispositions=disposition_rows,
        threshold=args.threshold,
    )
    if not args.no_write:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(report["line"])
        for row in report.get("findings") or []:
            print(f"- {row['line']}")
        for row in report.get("insufficient") or []:
            print(f"- {row['line']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
