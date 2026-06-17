#!/usr/bin/env python3
"""Independent Life/Work OS briefing staleness watcher."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import pushover_notify
from life_work_os_config import (
    BRIEFING_REVIEW_LOG_DATA_SOURCE_ID,
    DAILY_LIFE,
    DAILY_WORK,
    TIMEZONE,
    RoutineSpec,
)
from life_work_os_notion import (
    NotionRestClient,
    and_filter,
    date_filter,
    properties_schema,
    property_text,
    prop_filter,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "src" / "life_work_os_heartbeat.json"
ET = ZoneInfo(TIMEZONE)
DAILY_MONITORS = (DAILY_LIFE, DAILY_WORK)


@dataclass(frozen=True)
class HeartbeatRow:
    automation_id: str
    name: str
    expected_slot: str
    stale_after: str
    last_log_date: str
    last_log_url: str
    state: str
    alarm: str = ""


def _now(value: str | None = None) -> datetime:
    if value:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(ET)
    return datetime.now(ET)


def expected_slot_before(routine: RoutineSpec, now: datetime) -> datetime:
    cursor = now.astimezone(ET)
    for offset in range(0, 10):
        day = cursor.date() - timedelta(days=offset)
        candidate = datetime(day.year, day.month, day.day, routine.slot.hour, routine.slot.minute, tzinfo=ET)
        if candidate.weekday() in routine.days and candidate <= cursor:
            return candidate
    return datetime(cursor.year, cursor.month, cursor.day, routine.slot.hour, routine.slot.minute, tzinfo=ET)


def _briefing_log_filter(schema: Mapping[str, dict[str, Any]], routine: RoutineSpec, now: datetime) -> dict[str, Any] | None:
    os_filter, _ = prop_filter(schema, "OS", "equals", routine.os_name)
    type_filter, _ = prop_filter(schema, "Type", "equals", routine.report_type)
    date_since, _ = date_filter(schema, "Date", "on_or_after", (now - timedelta(days=10)).date())
    return and_filter(os_filter, type_filter, date_since)


def latest_log_rows(client: NotionRestClient, now: datetime) -> dict[str, dict[str, Any]]:
    schema = properties_schema(client.retrieve_data_source(BRIEFING_REVIEW_LOG_DATA_SOURCE_ID))
    latest: dict[str, dict[str, Any]] = {}
    for routine in DAILY_MONITORS:
        filter_ = _briefing_log_filter(schema, routine, now)
        query = client.query_data_source(
            BRIEFING_REVIEW_LOG_DATA_SOURCE_ID,
            filter_=filter_,
            sorts=[{"property": "Date", "direction": "descending"}] if "Date" in schema else [],
        )
        latest[routine.automation_id] = query.rows[0] if query.rows else {}
    return latest


def evaluate_staleness(
    *,
    latest_rows: Mapping[str, Mapping[str, Any]],
    now: datetime,
    threshold_hours: int = 36,
) -> list[HeartbeatRow]:
    rows: list[HeartbeatRow] = []
    for routine in DAILY_MONITORS:
        slot = expected_slot_before(routine, now - timedelta(hours=threshold_hours))
        stale_after = slot + timedelta(hours=threshold_hours)
        latest = latest_rows.get(routine.automation_id) or {}
        last_date = property_text(latest, "Date")
        last_url = str(latest.get("url") or "")
        state = "current"
        alarm = ""
        if now > stale_after:
            if not last_date or last_date < slot.date().isoformat():
                state = "stale"
                alarm = f"{routine.name} has not run since {last_date or 'never'}"
        rows.append(
            HeartbeatRow(
                automation_id=routine.automation_id,
                name=routine.name,
                expected_slot=slot.isoformat(),
                stale_after=stale_after.isoformat(),
                last_log_date=last_date,
                last_log_url=last_url,
                state=state,
                alarm=alarm,
            )
        )
    return rows


def run_heartbeat(
    *,
    dry_run: bool,
    push: bool,
    now_text: str | None,
    threshold_hours: int = 36,
) -> dict[str, Any]:
    now = _now(now_text)
    client = NotionRestClient(dry_run=dry_run)
    latest = latest_log_rows(client, now)
    rows = evaluate_staleness(latest_rows=latest, now=now, threshold_hours=threshold_hours)
    alarms = [row for row in rows if row.state == "stale"]
    push_reports: list[dict[str, Any]] = []
    if push:
        for row in alarms:
            push_reports.append(
                pushover_notify.send_message(
                    title="Life/Work OS routine alarm",
                    message=f"{row.alarm}. Expected slot: {row.expected_slot}",
                    priority=1,
                    dry_run=dry_run,
                )
            )
    return {
        "valid": True,
        "generated_at": now.isoformat(),
        "threshold_hours": threshold_hours,
        "alarm_count": len(alarms),
        "rows": [asdict(row) for row in rows],
        "push_reports": push_reports,
    }


def _format_text(report: Mapping[str, Any]) -> str:
    lines = [
        f"Life/Work heartbeat valid: {bool(report.get('valid'))}",
        f"Alarms: {int(report.get('alarm_count') or 0)}",
    ]
    for row in report.get("rows") or []:
        if not isinstance(row, dict):
            continue
        line = f"- {row.get('name')}: {row.get('state')} | last={row.get('last_log_date') or 'never'}"
        if row.get("alarm"):
            line += f" | {row.get('alarm')}"
        lines.append(line)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--now")
    parser.add_argument("--threshold-hours", type=int, default=36)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--format", choices=("json", "text"), default="text")
    args = parser.parse_args(argv)

    try:
        report = run_heartbeat(
            dry_run=args.dry_run,
            push=args.push,
            now_text=args.now,
            threshold_hours=args.threshold_hours,
        )
    except Exception as exc:
        report = {"valid": False, "error": str(exc), "alarm_count": 0, "rows": []}
    Path(args.out).write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    if args.format == "json":
        print(json.dumps(report, indent=2, default=str))
    else:
        print(_format_text(report))
    return 0 if report.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
