"""Collection gate - the L2 -> L3 handoff contract.

Contract-B validation proves a CollectedSnapshot has the right shape. This gate
adds the policy checks needed before Layer 3 consumes it: parseable run/source
stamps, critical-source fail-closed behavior, and cross-field consistency for
staleness and source failure metadata.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

try:  # flat import inside conviction_engine/ (house convention)
    from validators import validate_collected_snapshot
except ImportError:  # pragma: no cover - package-style import fallback
    from conviction_engine.validators import validate_collected_snapshot


def _field(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _parse_iso_date_or_datetime(value: Any, *, require_datetime: bool = False) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    text = value.strip()
    if require_datetime and "T" not in text:
        return False
    if not require_datetime and len(text) == 7:
        try:
            year, month = text.split("-")
            return 1 <= int(month) <= 12 and len(year) == 4
        except (ValueError, TypeError):
            return False
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        if "T" in normalized:
            datetime.fromisoformat(normalized)
        else:
            date.fromisoformat(normalized[:10])
    except ValueError:
        return False
    return True


def _source_name(item: Any) -> str:
    raw = _field(item, "source", "")
    return str(raw) if raw is not None else ""


def _item_kind(item: Any) -> str:
    raw = _field(item, "kind", "")
    return str(raw) if raw is not None else ""


def validate_collection_gate(snapshot: Any) -> list[str]:
    """Return L2 -> L3 handoff problems. Empty list == safe for L3 assembly."""
    problems = [f"Contract-B: {p}" for p in validate_collected_snapshot(snapshot)]
    if problems:
        return problems

    run_ts = _field(snapshot, "run_timestamp")
    if not _parse_iso_date_or_datetime(run_ts, require_datetime=True):
        problems.append(f"run_timestamp must be an ISO datetime stamp, got {run_ts!r}")

    critical_missing = list(_field(snapshot, "critical_missing") or [])
    if critical_missing:
        problems.append(
            "critical source(s) missing at L2->L3 handoff: "
            + ", ".join(str(s) for s in critical_missing)
        )

    items = list(_field(snapshot, "items") or [])
    staleness = dict(_field(snapshot, "staleness") or {})
    newest_by_source: dict[str, str] = {}
    error_sources: set[str] = set()
    for idx, item in enumerate(items):
        source = _source_name(item)
        kind = _item_kind(item)
        timestamp = _field(item, "timestamp")
        if not _parse_iso_date_or_datetime(timestamp):
            problems.append(f"items[{idx}] timestamp must be ISO date/datetime, got {timestamp!r}")
            continue
        if kind == "error":
            error_sources.add(source)
            continue
        if source:
            ts = str(timestamp)
            if source not in newest_by_source or ts > newest_by_source[source]:
                newest_by_source[source] = ts

    for source, expected in sorted(newest_by_source.items()):
        actual = staleness.get(source)
        if actual != expected:
            problems.append(
                f"staleness[{source!r}] must equal newest non-error item timestamp "
                f"{expected!r}, got {actual!r}"
            )
    for source in sorted(set(staleness) - set(newest_by_source)):
        problems.append(f"staleness[{source!r}] has no matching non-error SourceItem")
    for source, stamp in sorted(staleness.items()):
        if not _parse_iso_date_or_datetime(stamp):
            problems.append(f"staleness[{source!r}] must be ISO date/datetime, got {stamp!r}")

    failed = _field(snapshot, "sources_failed") or []
    failed_names = {
        str(row.get("name"))
        for row in failed
        if isinstance(row, dict) and row.get("name") not in (None, "")
    }
    ok_names = {str(s) for s in (_field(snapshot, "sources_ok") or [])}
    overlap = sorted(ok_names & failed_names)
    if overlap:
        problems.append("source(s) cannot be both ok and failed: " + ", ".join(overlap))
    missing_failed_rows = sorted(error_sources - failed_names)
    if missing_failed_rows:
        problems.append(
            "error SourceItem(s) missing from sources_failed: "
            + ", ".join(missing_failed_rows)
        )
    missing_error_items = sorted(failed_names - error_sources)
    if missing_error_items:
        problems.append(
            "sources_failed row(s) without matching error SourceItem: "
            + ", ".join(missing_error_items)
        )

    return problems


def is_valid_collection_gate(snapshot: Any) -> bool:
    return not validate_collection_gate(snapshot)


def assert_valid_collection_gate(snapshot: Any) -> None:
    problems = validate_collection_gate(snapshot)
    if problems:
        raise ValueError(
            "snapshot failed L2->L3 collection gate: " + "; ".join(problems)
        )
