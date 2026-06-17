#!/usr/bin/env python3
"""Bounded safe-hygiene planner for Life OS / Work OS Notion data."""
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from life_work_os_config import (
    AFTER_HOURS_QUEUE_DATA_SOURCE_ID,
    INBOX_DATA_SOURCE_ID,
    LEGACY_INBOX_PARENT_PAGE_ID,
    SYSTEM_CHANGELOG_DATA_SOURCE_ENV,
    SYSTEM_CHANGELOG_PAGE_ENV,
    SYSTEM_CHANGELOG_PAGE_ID,
    TASKS_DATA_SOURCE_ID,
    TIMEZONE,
)
from life_work_os_notion import (
    NotionRestClient,
    and_filter,
    is_empty_filter,
    page_title,
    properties_schema,
    property_payload,
    property_text,
    prop_filter,
    title_property,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "src" / "life_work_os_hygiene_receipt.json"
ET = ZoneInfo(TIMEZONE)
PAST_EVENT_RE = re.compile(
    r"\b("
    r"may \d{1,2}|june \d{1,2}|july \d{1,2}|august \d{1,2}|"
    r"appointment|surgery|reservation|flight|hotel|pickup|dropoff"
    r")\b",
    re.IGNORECASE,
)
INVESTING_BACKFILL_RE = re.compile(
    r"\b("
    r"investing|position|positions|fundstrat|etf|sleeve|portfolio|"
    r"rebalance|allocation|risk|attribution|tax-location|fmp|trade journal"
    r")\b",
    re.IGNORECASE,
)
TEXT_TRANSLATION = str.maketrans({
    "\u2192": "->",
    "\u2190": "<-",
    "\u2014": "-",
    "\u2013": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\U0001f4d2": "[notebook]",
    "\U0001f5c4": "[file]",
    "\ufe0f": "",
    "\u00d7": "x",
    "\u00a0": " ",
})


@dataclass(frozen=True)
class HygieneOperation:
    op: str
    page_id: str
    title: str
    reason: str
    target_status: str = ""
    properties: dict[str, Any] | None = None


def _block_text(block: Mapping[str, Any]) -> str:
    block_type = str(block.get("type") or "")
    payload = block.get(block_type)
    if not isinstance(payload, dict):
        return ""
    rich = payload.get("rich_text") or payload.get("title")
    if not isinstance(rich, list):
        return ""
    return "".join(str(item.get("plain_text") or "") for item in rich if isinstance(item, dict)).strip()


def _now(value: str | None = None) -> datetime:
    if value:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(ET)
    return datetime.now(ET)


def _page_id(row: Mapping[str, Any]) -> str:
    return str(row.get("id") or "")


def _normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def _is_recurring(row: Mapping[str, Any]) -> bool:
    text = " ".join([
        property_text(row, "Recurring"),
        property_text(row, "Frequency"),
        property_text(row, "Repeat"),
    ]).lower()
    return any(token in text for token in ("true", "daily", "weekly", "monthly", "recurring", "repeat"))


def _is_work_case_content(row: Mapping[str, Any]) -> bool:
    text = " ".join([
        page_title(row),
        property_text(row, "Domain"),
        property_text(row, "Project"),
        property_text(row, "Source Project"),
    ]).lower()
    return any(
        token in text
        for token in (
            "eeoc",
            "claim",
            "case file",
            "strategic brief",
            "game plan",
            "evidence ledger",
            "settlement",
            "retaliation",
            "constructive discharge",
            "awc",
            "solventum",
            "sandra",
            "brent",
            "senior leaders",
            "ip lead",
        )
    )


def _is_closed_or_cancelled(row: Mapping[str, Any]) -> bool:
    status = property_text(row, "Status").lower()
    title = page_title(row).lower()
    closed_tokens = ("done", "cancelled", "canceled", "archived", "delivered", "superseded", "disconfirmed")
    return any(token in status for token in closed_tokens) or any(token in title for token in closed_tokens)


def _due_date(row: Mapping[str, Any]) -> datetime | None:
    value = property_text(row, "Due Date")
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:10]).replace(tzinfo=ET)
    except ValueError:
        return None


def _is_investing_backfill_candidate(row: Mapping[str, Any]) -> bool:
    domain = property_text(row, "Domain").strip().lower()
    if domain and domain not in {"finance", "investing", "investing 2026"}:
        return False
    if _is_work_case_content(row):
        return False
    text = " ".join([
        page_title(row),
        domain,
        property_text(row, "Area"),
        property_text(row, "Project"),
        property_text(row, "Notes"),
    ])
    return bool(INVESTING_BACKFILL_RE.search(text))


def plan_past_event_closures(
    rows: list[Mapping[str, Any]],
    *,
    now: datetime,
    cap: int,
) -> list[HygieneOperation]:
    ops: list[HygieneOperation] = []
    cutoff = now - timedelta(days=14)
    for row in rows:
        if len(ops) >= cap:
            break
        title = page_title(row)
        due = _due_date(row)
        if not title or not due or due >= cutoff:
            continue
        domain = property_text(row, "Domain").strip().lower()
        if domain in {"work", "nicole"} or _is_recurring(row) or _is_work_case_content(row):
            continue
        if not PAST_EVENT_RE.search(title):
            continue
        ops.append(
            HygieneOperation(
                op="cancel_past_event_task",
                page_id=_page_id(row),
                title=title,
                reason="Due date is more than 14 days past and title matches one-time past-event heuristic.",
                target_status="Cancelled",
            )
        )
    return ops


def _richness(row: Mapping[str, Any]) -> int:
    props = row.get("properties")
    if not isinstance(props, dict):
        return len(json.dumps(row, sort_keys=True))
    return sum(len(str(value)) for value in props.values())


def plan_duplicate_cancellations(
    rows: list[Mapping[str, Any]],
    *,
    cap: int,
) -> list[HygieneOperation]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        if _is_work_case_content(row):
            continue
        title = page_title(row)
        key = _normalize_title(title)
        if not key:
            continue
        groups.setdefault(key, []).append(row)
    ops: list[HygieneOperation] = []
    for key in sorted(groups):
        duplicates = groups[key]
        if len(duplicates) < 2:
            continue
        keep = max(duplicates, key=_richness)
        for row in duplicates:
            if len(ops) >= cap:
                return ops
            if row is keep:
                continue
            ops.append(
                HygieneOperation(
                    op="cancel_duplicate_task",
                    page_id=_page_id(row),
                    title=page_title(row),
                    reason=f"Conservative exact-title duplicate; kept richer row {keep.get('id') or 'unknown'}.",
                    target_status="Cancelled",
                )
            )
    return ops


def plan_finance_source_project_backfill(
    rows: list[Mapping[str, Any]],
    *,
    cap: int,
) -> list[HygieneOperation]:
    ops: list[HygieneOperation] = []
    for row in rows:
        if len(ops) >= cap:
            break
        title = page_title(row)
        source_project = property_text(row, "Source Project")
        if _is_closed_or_cancelled(row):
            continue
        if source_project or not _is_investing_backfill_candidate(row):
            continue
        ops.append(
            HygieneOperation(
                op="backfill_investing_source_project",
                page_id=_page_id(row),
                title=title,
                reason='Finance/Investing task has null Source Project; backfill to "Investing 2026".',
                properties={"Source Project": "Investing 2026"},
            )
        )
    return ops


def plan_orphan_inbox_recovery(
    blocks: list[Mapping[str, Any]],
    *,
    existing_source_ids: set[str],
    cap: int,
) -> list[HygieneOperation]:
    ops: list[HygieneOperation] = []
    for block in blocks:
        if len(ops) >= cap:
            break
        block_id = _page_id(block)
        text = _block_text(block)
        if not block_id or not text or block_id in existing_source_ids:
            continue
        ops.append(
            HygieneOperation(
                op="recover_orphan_inbox_capture",
                page_id=block_id,
                title=text[:80],
                reason="Legacy Inbox child-page capture recovered verbatim into Inbox DB.",
                properties={
                    "Raw Content": text,
                    "Source": "recovered",
                    "Recovered Source Block": block_id,
                },
            )
        )
    return ops


def plan_after_hours_queue_drain(
    rows: list[Mapping[str, Any]],
    *,
    cap: int,
) -> list[HygieneOperation]:
    ops: list[HygieneOperation] = []
    for row in rows:
        if len(ops) >= cap:
            break
        status = property_text(row, "Status").lower()
        safety = " ".join([property_text(row, "Safety"), property_text(row, "Mode"), property_text(row, "Scope")]).lower()
        if status in {"done", "cancelled"}:
            continue
        if "autonomous" not in safety and "safe" not in safety:
            continue
        ops.append(
            HygieneOperation(
                op="drain_after_hours_queue_item",
                page_id=_page_id(row),
                title=page_title(row),
                reason="After-Hours Queue item is marked autonomous-safe; closing with receipt-linked note.",
                target_status="Done",
            )
        )
    return ops


def _tasks_filter(schema: Mapping[str, dict[str, Any]]) -> dict[str, Any] | None:
    not_done, _ = prop_filter(schema, "Status", "does_not_equal", "Done")
    not_cancelled, _ = prop_filter(schema, "Status", "does_not_equal", "Cancelled")
    return and_filter(not_done, not_cancelled)


def _finance_backfill_filter(schema: Mapping[str, dict[str, Any]]) -> dict[str, Any] | None:
    source_empty, _ = is_empty_filter(schema, "Source Project")
    not_done, _ = prop_filter(schema, "Status", "does_not_equal", "Done")
    return and_filter(source_empty, not_done)


def _after_hours_filter(schema: Mapping[str, dict[str, Any]]) -> dict[str, Any] | None:
    not_done, _ = prop_filter(schema, "Status", "does_not_equal", "Done")
    return not_done


def _existing_recovered_ids(client: NotionRestClient, inbox_schema: Mapping[str, dict[str, Any]]) -> set[str]:
    if "Recovered Source Block" not in inbox_schema:
        return set()
    source, _ = prop_filter(inbox_schema, "Source", "equals", "recovered")
    rows = client.query_data_source(INBOX_DATA_SOURCE_ID, filter_=source).rows
    return {
        property_text(row, "Recovered Source Block")
        for row in rows
        if property_text(row, "Recovered Source Block")
    }


def fetch_candidate_rows(client: NotionRestClient) -> dict[str, list[dict[str, Any]]]:
    task_schema = properties_schema(client.retrieve_data_source(TASKS_DATA_SOURCE_ID))
    inbox_schema = properties_schema(client.retrieve_data_source(INBOX_DATA_SOURCE_ID))
    tasks = client.query_data_source(
        TASKS_DATA_SOURCE_ID,
        filter_=_tasks_filter(task_schema),
        sorts=[{"property": "Due Date", "direction": "ascending"}] if "Due Date" in task_schema else [],
    ).rows
    finance = client.query_data_source(
        TASKS_DATA_SOURCE_ID,
        filter_=_finance_backfill_filter(task_schema),
    ).rows
    queue_schema = properties_schema(client.retrieve_data_source(AFTER_HOURS_QUEUE_DATA_SOURCE_ID))
    queue = client.query_data_source(
        AFTER_HOURS_QUEUE_DATA_SOURCE_ID,
        filter_=_after_hours_filter(queue_schema),
    ).rows
    can_track_recovered_blocks = "Recovered Source Block" in inbox_schema and "Raw Content" in inbox_schema
    orphan_blocks = client.list_block_children(LEGACY_INBOX_PARENT_PAGE_ID) if can_track_recovered_blocks else []
    existing_rows = [
        {"id": source_id, "properties": {"Recovered Source Block": {"type": "rich_text", "rich_text": [{"plain_text": source_id}]}}}
        for source_id in _existing_recovered_ids(client, inbox_schema)
    ]
    return {
        "tasks": tasks,
        "finance": finance,
        "after_hours_queue": queue,
        "orphan_blocks": orphan_blocks,
        "existing_recovered": existing_rows,
    }


def plan_hygiene(
    *,
    rows: Mapping[str, list[Mapping[str, Any]]],
    now: datetime,
    max_mutations: int,
) -> list[HygieneOperation]:
    remaining = max_mutations
    ops: list[HygieneOperation] = []
    existing_source_ids = {
        property_text(row, "Recovered Source Block") or str(row.get("id") or "")
        for row in rows.get("existing_recovered") or []
    }
    orphan_ops = plan_orphan_inbox_recovery(
        list(rows.get("orphan_blocks") or []),
        existing_source_ids=existing_source_ids,
        cap=remaining,
    )
    ops.extend(orphan_ops)
    remaining = max_mutations - len(ops)
    for planner, key in (
        (plan_finance_source_project_backfill, "finance"),
        (plan_past_event_closures, "tasks"),
        (plan_duplicate_cancellations, "tasks"),
        (plan_after_hours_queue_drain, "after_hours_queue"),
    ):
        if remaining <= 0:
            break
        if planner is plan_past_event_closures:
            planned = planner(list(rows.get(key) or []), now=now, cap=remaining)
        else:
            planned = planner(list(rows.get(key) or []), cap=remaining)
        ops.extend(planned)
        remaining = max_mutations - len(ops)
    return ops[:max_mutations]


def _status_properties(schema: Mapping[str, dict[str, Any]], status: str) -> dict[str, Any]:
    props: dict[str, Any] = {}
    payload = property_payload(schema, "Status", status)
    if payload:
        props["Status"] = payload
    note = property_payload(schema, "Closeout Note", "Closed by Life/Work OS safe-hygiene routine; see receipt/changelog.")
    if note:
        props["Closeout Note"] = note
    return props


def _custom_properties(schema: Mapping[str, dict[str, Any]], values: Mapping[str, Any]) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for name, value in values.items():
        payload = property_payload(schema, name, value)
        if payload:
            props[name] = payload
    return props


def _rich_text(text: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": {"content": text[:1900]}}]


def _heading_block(level: int, text: str) -> dict[str, Any]:
    block_type = f"heading_{level}"
    return {"object": "block", "type": block_type, block_type: {"rich_text": _rich_text(text)}}


def _paragraph_block(text: str) -> dict[str, Any]:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rich_text(text)}}


def _bulleted_block(text: str) -> dict[str, Any]:
    return {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _rich_text(text)}}


def write_changelog(client: NotionRestClient, operations: list[HygieneOperation], *, now: datetime) -> dict[str, Any]:
    changelog_ds = str(os.environ.get(SYSTEM_CHANGELOG_DATA_SOURCE_ENV) or "").strip()
    title = f"Life/Work OS safe hygiene - {now.isoformat(timespec='minutes')}"
    summary = "\n".join(f"- {op.op}: {op.title} ({op.reason})" for op in operations)[:1900]
    if not changelog_ds:
        page_id = str(os.environ.get(SYSTEM_CHANGELOG_PAGE_ENV) or SYSTEM_CHANGELOG_PAGE_ID).strip()
        if not page_id:
            raise RuntimeError(
                f"{SYSTEM_CHANGELOG_DATA_SOURCE_ENV} or {SYSTEM_CHANGELOG_PAGE_ENV} is required before applying hygiene mutations"
            )
        children = [
            _heading_block(2, title),
            _paragraph_block("Change type: bounded safe-hygiene mutations. No deletions."),
            _paragraph_block("What:"),
            *[_bulleted_block(f"{op.op}: {op.title} - {op.reason}") for op in operations],
            _paragraph_block("Reversible: Yes. Roll back by restoring the affected Notion row properties from this receipt."),
        ]
        payload = client.append_block_children(page_id, children)
        verified = client.retrieve_page(page_id)
        return {
            "mode": "page_append",
            "page_id": page_id,
            "url": verified.get("url") or payload.get("url") or "",
            "verified": bool(verified.get("id")),
        }
    schema = properties_schema(client.retrieve_data_source(changelog_ds))
    props: dict[str, Any] = {}
    for name, value in {"Name": title, "Title": title, "Date": now.date(), "Summary": summary}.items():
        payload = property_payload(schema, name, value)
        if payload:
            props[name] = payload
    page = client.create_page(data_source_id=changelog_ds, properties=props)
    return {"mode": "data_source", "page_id": page.get("id") or "", "url": page.get("url") or "", "verified": bool(page.get("id"))}


def apply_operations(client: NotionRestClient, operations: list[HygieneOperation], *, dry_run: bool) -> dict[str, Any]:
    if dry_run or not operations:
        return {"applied": False, "dry_run": dry_run, "count": 0, "results": []}
    task_schema = properties_schema(client.retrieve_data_source(TASKS_DATA_SOURCE_ID))
    inbox_schema = properties_schema(client.retrieve_data_source(INBOX_DATA_SOURCE_ID))
    queue_schema = properties_schema(client.retrieve_data_source(AFTER_HOURS_QUEUE_DATA_SOURCE_ID))
    results: list[dict[str, Any]] = []
    for op in operations:
        if op.op == "recover_orphan_inbox_capture":
            props = _custom_properties(inbox_schema, op.properties or {})
            title_name = title_property(inbox_schema)
            if title_name and title_name not in props:
                payload = property_payload(inbox_schema, title_name, "Recovered inbox capture")
                if payload:
                    props[title_name] = payload
            updated = client.create_page(data_source_id=INBOX_DATA_SOURCE_ID, properties=props)
            results.append({"op": op.op, "page_id": op.page_id, "created": bool(updated.get("id") or updated.get("object"))})
            continue
        if op.op == "drain_after_hours_queue_item":
            props = _status_properties(queue_schema, op.target_status)
        elif op.properties:
            props = _custom_properties(task_schema, op.properties)
        else:
            props = _status_properties(task_schema, op.target_status)
        updated = client.update_page_properties(op.page_id, props)
        results.append({"op": op.op, "page_id": op.page_id, "updated": bool(updated.get("id") or updated.get("object"))})
    return {"applied": True, "dry_run": False, "count": len(results), "results": results}


def run_hygiene(
    *,
    apply: bool,
    dry_run: bool,
    max_mutations: int,
    now_text: str | None,
) -> dict[str, Any]:
    now = _now(now_text)
    client = NotionRestClient(dry_run=dry_run)
    rows = fetch_candidate_rows(client)
    operations = plan_hygiene(rows=rows, now=now, max_mutations=max_mutations)
    changelog = {"skipped": True}
    apply_result = {"applied": False, "dry_run": dry_run or not apply, "count": 0, "results": []}
    if apply and operations:
        changelog = write_changelog(client, operations, now=now)
        apply_result = apply_operations(client, operations, dry_run=dry_run)
    return {
        "valid": True,
        "generated_at": now.isoformat(),
        "apply_requested": apply,
        "max_mutations": max_mutations,
        "planned_count": len(operations),
        "operations": [asdict(op) for op in operations],
        "changelog": changelog,
        "apply_result": apply_result,
        "guardrails": [
            "idempotent",
            "never_delete",
            "cap_mutations_per_run",
            "log_every_mutation",
            "never_auto_mutate_work_case_content",
        ],
    }


def _format_text(report: Mapping[str, Any]) -> str:
    lines = [
        f"Life/Work safe hygiene valid: {bool(report.get('valid'))}",
        f"Planned mutations: {int(report.get('planned_count') or 0)}",
        f"Applied: {bool((report.get('apply_result') or {}).get('applied'))}",
    ]
    for op in report.get("operations") or []:
        if isinstance(op, dict):
            lines.append(f"- {op.get('op')}: {op.get('title')} | {op.get('reason')}")
    if report.get("error"):
        lines.append(f"Error: {report.get('error')}")
    text = "\n".join(lines).translate(TEXT_TRANSLATION)
    return text.encode("ascii", errors="replace").decode("ascii")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-mutations", type=int, default=10)
    parser.add_argument("--now")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--format", choices=("json", "text"), default="text")
    args = parser.parse_args(argv)

    try:
        report = run_hygiene(
            apply=args.apply,
            dry_run=args.dry_run,
            max_mutations=args.max_mutations,
            now_text=args.now,
        )
    except Exception as exc:
        report = {"valid": False, "error": str(exc), "planned_count": 0, "operations": []}
    Path(args.out).write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    if args.format == "json":
        print(json.dumps(report, indent=2, default=str))
    else:
        print(_format_text(report))
    return 0 if report.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
