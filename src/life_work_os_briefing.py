#!/usr/bin/env python3
"""Generate Life OS / Work OS briefings from deterministic Notion reads."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import pushover_notify
from life_work_os_config import (
    BRIEFING_REVIEW_LOG_DATA_SOURCE_ID,
    BRIEFING_ROUTINES,
    DRIFT_FLAGS_DATA_SOURCE_ID,
    EEOC_FILING_DEADLINE_PAGE_ID,
    EVIDENCE_FACT_LEDGER_DATA_SOURCE_ID,
    INBOX_DATA_SOURCE_ID,
    INSIGHTS_GROWTH_DATA_SOURCE_ID,
    TASKS_DATA_SOURCE_ID,
    TIMEZONE,
    WORK_OPERATIONS_DATA_SOURCE_ID,
    RoutineSpec,
)
from life_work_os_notion import (
    NotionAPIError,
    NotionRestClient,
    and_filter,
    checkbox_filter,
    date_filter,
    env_status,
    page_title,
    properties_schema,
    property_payload,
    property_text,
    prop_filter,
    title_property,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "src" / "life_work_os_last_run.json"
ET = ZoneInfo(TIMEZONE)
LEGEND = (
    "Legend: RED/BOLD = urgent, time-sensitive, important, no action logged; "
    "YELLOW = important-not-urgent or urgent in progress; GRAY = informational; "
    "PLAIN = routine."
)


@dataclass(frozen=True)
class SourceRequest:
    key: str
    label: str
    data_source_id: str
    limit: int = 20


@dataclass(frozen=True)
class BriefingItem:
    title: str
    source: str
    url: str = ""
    due: str = ""
    status: str = ""
    domain: str = ""
    hat: str = ""
    urgency: str = "plain"


def _now(value: str | None = None) -> datetime:
    if value:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(ET)
    return datetime.now(ET)


def _sorts_for(schema: Mapping[str, dict[str, Any]], names: list[str]) -> list[dict[str, Any]]:
    sorts: list[dict[str, Any]] = []
    for name in names:
        if name in schema:
            sorts.append({"property": name, "direction": "ascending"})
    return sorts


def effective_routine(routine_key: str, now: datetime) -> RoutineSpec:
    routine = BRIEFING_ROUTINES[routine_key]
    if routine_key == "life_weekly" and now.weekday() == 5 and now.day <= 7:
        return replace(routine, name="Life OS Monthly Deep", report_type="Monthly Deep")
    return routine


def _scope_filters(schema: Mapping[str, dict[str, Any]], *, work: bool) -> tuple[list[dict[str, Any]], list[str]]:
    filters: list[dict[str, Any]] = []
    issues: list[str] = []
    if work:
        row, issue = prop_filter(schema, "Domain", "equals", "Work")
        if issue:
            issues.append(issue)
        elif row:
            filters.append(row)
        return filters, issues

    domain, issue = prop_filter(schema, "Domain", "does_not_equal", "Work")
    if issue:
        issues.append(issue)
    elif domain:
        filters.append(domain)
    source_project, issue = prop_filter(schema, "Source Project", "does_not_equal", "Investing 2026")
    if issue:
        issues.append(issue)
    elif source_project:
        filters.append(source_project)
    return filters, issues


def _task_open_filter(schema: Mapping[str, dict[str, Any]], *, work: bool) -> tuple[dict[str, Any] | None, list[str]]:
    issues: list[str] = []
    filters: list[dict[str, Any]] = []
    for value in ("Done", "Cancelled"):
        row, issue = prop_filter(schema, "Status", "does_not_equal", value)
        if issue:
            issues.append(issue)
        elif row:
            filters.append(row)
    scope, scope_issues = _scope_filters(schema, work=work)
    filters.extend(scope)
    issues.extend(scope_issues)
    return and_filter(*filters), issues


def _inbox_unprocessed_filter(schema: Mapping[str, dict[str, Any]], *, work: bool) -> tuple[dict[str, Any] | None, list[str]]:
    filters: list[dict[str, Any]] = []
    issues: list[str] = []
    processed, processed_issue = checkbox_filter(schema, "Processed", False)
    if processed:
        filters.append(processed)
    else:
        status, status_issue = prop_filter(schema, "Status", "does_not_equal", "Processed")
        if status:
            filters.append(status)
        else:
            issues.append(processed_issue or status_issue or "missing unprocessed filter")
    scope, scope_issues = _scope_filters(schema, work=work)
    filters.extend(scope)
    issues.extend(scope_issues)
    return and_filter(*filters), issues


def _active_drift_filter(schema: Mapping[str, dict[str, Any]]) -> tuple[dict[str, Any] | None, list[str]]:
    active, issue = checkbox_filter(schema, "Active", True)
    if active:
        return active, []
    filters: list[dict[str, Any]] = []
    issues = [issue] if issue else []
    for value in ("Done", "Cancelled", "Resolved"):
        row, row_issue = prop_filter(schema, "Status", "does_not_equal", value)
        if row:
            filters.append(row)
        elif row_issue:
            issues.append(row_issue)
    return and_filter(*filters), issues if not filters else []


def _recent_insights_filter(schema: Mapping[str, dict[str, Any]], now: datetime) -> tuple[dict[str, Any] | None, list[str]]:
    scope, issues = _scope_filters(schema, work=False)
    for prop in ("Date", "Created", "Created time"):
        if prop in schema:
            row, issue = date_filter(schema, prop, "on_or_after", (now - timedelta(days=7)).date())
            if issue:
                issues.append(issue)
            return and_filter(*(scope + ([row] if row else []))), issues
    issues.append("missing recent-date property")
    return and_filter(*scope), issues


def _recent_work_insights_filter(schema: Mapping[str, dict[str, Any]], now: datetime) -> tuple[dict[str, Any] | None, list[str]]:
    scope, issues = _scope_filters(schema, work=True)
    for prop in ("Date", "Created", "Created time"):
        if prop in schema:
            row, issue = date_filter(schema, prop, "on_or_after", (now - timedelta(days=7)).date())
            if issue:
                issues.append(issue)
            return and_filter(*(scope + ([row] if row else []))), issues
    issues.append("missing recent-date property")
    return and_filter(*scope), issues


def _work_ops_filter(schema: Mapping[str, dict[str, Any]]) -> tuple[dict[str, Any] | None, list[str]]:
    filters: list[dict[str, Any]] = []
    issues: list[str] = []
    for value in ("Done", "Cancelled", "Archived"):
        row, issue = prop_filter(schema, "Status", "does_not_equal", value)
        if row:
            filters.append(row)
        elif issue:
            issues.append(issue)
    return and_filter(*filters), [] if filters else issues


def _ledger_filter(schema: Mapping[str, dict[str, Any]]) -> tuple[dict[str, Any] | None, list[str]]:
    pending, issue_pending = prop_filter(schema, "Preservation", "equals", "Pending")
    blocked, issue_blocked = prop_filter(schema, "Preservation", "equals", "Blocked")
    combined = {"or": [row for row in (pending, blocked) if row]}
    if combined["or"]:
        return combined, []
    return None, [issue for issue in (issue_pending, issue_blocked) if issue]


def filter_for_source(
    source: SourceRequest,
    schema: Mapping[str, dict[str, Any]],
    *,
    routine: RoutineSpec,
    now: datetime,
) -> tuple[dict[str, Any] | None, list[str], list[dict[str, Any]]]:
    work = routine.os_name == "Work"
    if source.key == "tasks":
        filter_, issues = _task_open_filter(schema, work=work)
        return filter_, issues, _sorts_for(schema, ["Push On", "Due Date"])
    if source.key == "inbox":
        filter_, issues = _inbox_unprocessed_filter(schema, work=work)
        return filter_, issues, []
    if source.key == "drift":
        # This DB intentionally has no Domain filter. Work relevance is tagged
        # inline from page content instead of filtered at query time.
        filter_, issues = _active_drift_filter(schema)
        return filter_, issues, []
    if source.key == "insights":
        filter_, issues = _recent_work_insights_filter(schema, now) if work else _recent_insights_filter(schema, now)
        return filter_, issues, _sorts_for(schema, ["Date", "Created"])
    if source.key == "work_ops":
        filter_, issues = _work_ops_filter(schema)
        return filter_, issues, _sorts_for(schema, ["Due Date", "Date"])
    if source.key == "ledger":
        filter_, issues = _ledger_filter(schema)
        return filter_, issues, []
    return None, [f"unknown source key {source.key}"], []


def _source_plan(routine_key: str) -> list[SourceRequest]:
    if routine_key == "life_daily":
        return [
            SourceRequest("tasks", "Life Tasks", TASKS_DATA_SOURCE_ID),
            SourceRequest("inbox", "Life Inbox", INBOX_DATA_SOURCE_ID),
            SourceRequest("drift", "Active Drift Flags", DRIFT_FLAGS_DATA_SOURCE_ID),
            SourceRequest("insights", "Insights & Growth", INSIGHTS_GROWTH_DATA_SOURCE_ID),
        ]
    if routine_key == "work_daily":
        return [
            SourceRequest("tasks", "Work Tasks", TASKS_DATA_SOURCE_ID),
            SourceRequest("work_ops", "Work Operations", WORK_OPERATIONS_DATA_SOURCE_ID),
            SourceRequest("ledger", "Evidence & Fact Ledger", EVIDENCE_FACT_LEDGER_DATA_SOURCE_ID),
            SourceRequest("insights", "Work Insights", INSIGHTS_GROWTH_DATA_SOURCE_ID),
            SourceRequest("drift", "Active Drift Flags", DRIFT_FLAGS_DATA_SOURCE_ID),
        ]
    if routine_key == "life_weekly":
        return [
            SourceRequest("tasks", "Slipped Life Tasks", TASKS_DATA_SOURCE_ID, limit=50),
            SourceRequest("inbox", "Life Hygiene Backlog", INBOX_DATA_SOURCE_ID, limit=50),
            SourceRequest("insights", "Life Pattern Candidates", INSIGHTS_GROWTH_DATA_SOURCE_ID, limit=50),
        ]
    if routine_key == "work_weekly":
        return [
            SourceRequest("tasks", "Slipped Work Tasks", TASKS_DATA_SOURCE_ID, limit=50),
            SourceRequest("work_ops", "Work Operations", WORK_OPERATIONS_DATA_SOURCE_ID, limit=50),
            SourceRequest("ledger", "Evidence Gaps", EVIDENCE_FACT_LEDGER_DATA_SOURCE_ID, limit=50),
            SourceRequest("insights", "Work Pattern Candidates", INSIGHTS_GROWTH_DATA_SOURCE_ID, limit=50),
        ]
    raise ValueError(f"unknown routine key {routine_key}")


def _item_from_page(page: Mapping[str, Any], source: SourceRequest, *, work: bool) -> BriefingItem:
    title = page_title(page) or "(untitled)"
    due = property_text(page, "Due Date") or property_text(page, "Push On") or property_text(page, "Date")
    status = property_text(page, "Status") or property_text(page, "Preservation")
    domain = property_text(page, "Domain")
    hat = ""
    if work:
        text = " ".join([title.lower(), domain.lower(), property_text(page, "Hat").lower()])
        hat = "claimant" if any(token in text for token in ("claim", "eeoc", "case", "evidence")) else "employee"
    urgency = "plain"
    if due and status.lower() not in {"in progress", "done", "cancelled"}:
        urgency = "red_bold"
    elif "blocked" in status.lower() or "pending" in status.lower():
        urgency = "yellow"
    elif source.key in {"insights", "drift"}:
        urgency = "gray"
    return BriefingItem(
        title=title,
        source=source.label,
        url=str(page.get("url") or ""),
        due=due,
        status=status,
        domain=domain,
        hat=hat,
        urgency=urgency,
    )


def _format_item(item: BriefingItem) -> str:
    prefix = {
        "red_bold": "RED/BOLD",
        "yellow": "YELLOW",
        "gray": "GRAY",
        "plain": "PLAIN",
    }.get(item.urgency, "PLAIN")
    hat = f" [{item.hat}]" if item.hat else ""
    due = f" | due/push: {item.due}" if item.due else ""
    status = f" | status: {item.status}" if item.status else ""
    return f"- {prefix}{hat}: {item.title} ({item.source}){due}{status}"


def _parse_date_text(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:10]).replace(tzinfo=ET)
    except ValueError:
        return None


def deadline_warning_ladder(deadline: datetime, now: datetime, *, action_logged: bool) -> str:
    days = (deadline.date() - now.date()).days
    if days > 62:
        return "hidden"
    if days > 31:
        return "neutral"
    if days > 7:
        return "yellow_weekly"
    if action_logged:
        return "gray_in_progress"
    return "red_daily"


def _eeoc_deadline_item(page: Mapping[str, Any], now: datetime) -> BriefingItem:
    title = page_title(page) or "EEOC Filing Deadline"
    due = (
        property_text(page, "Due Date")
        or property_text(page, "Deadline")
        or property_text(page, "Date")
    )
    status = property_text(page, "Status")
    deadline = _parse_date_text(due)
    action_logged = status.lower() in {"in progress", "done", "cancelled"}
    ladder = deadline_warning_ladder(deadline, now, action_logged=action_logged) if deadline else "not_checked"
    urgency = "gray"
    if ladder.startswith("red"):
        urgency = "red_bold"
    elif ladder.startswith("yellow"):
        urgency = "yellow"
    elif ladder == "hidden":
        urgency = "gray"
    return BriefingItem(
        title=title,
        source="EEOC Filing Deadline",
        url=str(page.get("url") or ""),
        due=due,
        status=status or ladder,
        domain="Work",
        hat="claimant",
        urgency=urgency,
    )


def collect_briefing(
    *,
    routine_key: str,
    client: NotionRestClient,
    now: datetime,
) -> dict[str, Any]:
    routine = effective_routine(routine_key, now)
    source_summaries: list[dict[str, Any]] = []
    items: list[BriefingItem] = []
    issues: list[str] = []
    for source in _source_plan(routine_key):
        try:
            schema = properties_schema(client.retrieve_data_source(source.data_source_id))
            filter_, filter_issues, sorts = filter_for_source(source, schema, routine=routine, now=now)
            if filter_issues and not filter_:
                issues.extend(f"{source.label}: {issue}" for issue in filter_issues)
                source_summaries.append({
                    "source": source.label,
                    "status": "not_checked",
                    "count": 0,
                    "issues": filter_issues,
                })
                continue
            query = client.query_data_source(source.data_source_id, filter_=filter_, sorts=sorts)
        except NotionAPIError as exc:
            issues.append(f"{source.label}: {exc}")
            source_summaries.append({"source": source.label, "status": "not_checked", "count": 0, "issues": [str(exc)]})
            continue
        source_items = [
            _item_from_page(page, source, work=routine.os_name == "Work")
            for page in query.rows[: source.limit]
        ]
        items.extend(source_items)
        source_summaries.append({
            "source": source.label,
            "status": "checked",
            "count": len(query.rows),
            "shown": len(source_items),
            "pages_fetched": query.pages_fetched,
            "filter": query.filter_used,
            "sorts": query.sorts_used,
        })
    if routine_key == "work_daily":
        try:
            deadline_page = client.retrieve_page(EEOC_FILING_DEADLINE_PAGE_ID)
        except NotionAPIError as exc:
            issues.append(f"EEOC Filing Deadline: {exc}")
            source_summaries.append({
                "source": "EEOC Filing Deadline",
                "status": "not_checked",
                "count": 0,
                "issues": [str(exc)],
            })
        else:
            items.append(_eeoc_deadline_item(deadline_page, now))
            source_summaries.append({
                "source": "EEOC Filing Deadline",
                "status": "checked",
                "count": 1,
                "shown": 1,
                "page_id": EEOC_FILING_DEADLINE_PAGE_ID,
            })
    if routine_key == "life_daily":
        person_first = ("mom", "belle", "nicole")
        items.sort(key=lambda item: (0 if any(name in item.title.lower() for name in person_first) else 1, item.title.lower()))
    summary = render_summary(routine=routine, now=now, items=items, source_summaries=source_summaries, issues=issues)
    return {
        "routine_key": routine_key,
        "routine": asdict(routine),
        "generated_at": now.isoformat(),
        "items": [asdict(item) for item in items],
        "source_summaries": source_summaries,
        "issues": issues,
        "summary": summary,
    }


def render_summary(
    *,
    routine: RoutineSpec,
    now: datetime,
    items: list[BriefingItem],
    source_summaries: list[dict[str, Any]],
    issues: list[str],
) -> str:
    lines = [
        f"{routine.name} - {now.date().isoformat()}",
        LEGEND,
        "",
    ]
    if routine.os_name == "Work":
        lines.append("Boundary: user's own Notion only; no Solventum tenant data. Every surfaced item is hat-labeled.")
        lines.append("Deadline ladder: >2mo hidden; 2mo neutral; 1mo yellow; final week daily/red unless action logged.")
        lines.append("")
    if not items:
        lines.append("No surfaced items from checked sources.")
    else:
        lines.extend(_format_item(item) for item in items[:50])
    lines.append("")
    lines.append("Source counts:")
    for source in source_summaries:
        status = source.get("status")
        count = int(source.get("count") or 0)
        shown = int(source.get("shown") or 0)
        lines.append(f"- {source.get('source')}: {status} | count={count} | shown={shown}")
    if issues:
        lines.append("")
        lines.append("Not checked / blockers:")
        lines.extend(f"- {issue}" for issue in issues)
    return "\n".join(lines).strip()


def build_briefing_log_properties(
    schema: Mapping[str, dict[str, Any]],
    *,
    routine: RoutineSpec,
    now: datetime,
    summary: str,
    push_sent: bool,
) -> dict[str, Any]:
    props: dict[str, Any] = {}
    title_name = title_property(schema)
    if title_name:
        props[title_name] = property_payload(
            schema,
            title_name,
            f"{now.date().isoformat()} {routine.name}",
        )
    for name, value in {
        "OS": routine.os_name,
        "Type": routine.report_type,
        "Date": now.date(),
        "Summary": summary[:1900],
        "Push Sent": push_sent,
    }.items():
        payload = property_payload(schema, name, value)
        if payload is not None:
            props[name] = payload
    return props


def write_briefing_log(
    *,
    client: NotionRestClient,
    routine: RoutineSpec,
    now: datetime,
    summary: str,
    push_sent: bool,
) -> dict[str, Any]:
    schema = properties_schema(client.retrieve_data_source(BRIEFING_REVIEW_LOG_DATA_SOURCE_ID))
    props = build_briefing_log_properties(schema, routine=routine, now=now, summary=summary, push_sent=push_sent)
    page = client.create_page(
        data_source_id=BRIEFING_REVIEW_LOG_DATA_SOURCE_ID,
        properties=props,
        children=[{"type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": summary[:1900]}}]}}],
    )
    page_id = str(page.get("id") or "")
    verified = False
    if page_id:
        fetched = client.retrieve_page(page_id)
        verified = bool(fetched.get("id") == page_id)
    return {
        "created": bool(page_id),
        "verified": verified,
        "page_id": page_id,
        "url": page.get("url") or "",
    }


def run_briefing(
    *,
    routine_key: str,
    write_log: bool,
    push: bool,
    dry_run: bool,
    now_text: str | None,
) -> dict[str, Any]:
    now = _now(now_text)
    routine = effective_routine(routine_key, now)
    client = NotionRestClient(dry_run=dry_run)
    result = collect_briefing(routine_key=routine_key, client=client, now=now)
    write_result = {"created": False, "verified": False, "page_id": "", "url": "", "skipped": not write_log}
    push_result: dict[str, Any] = {"sent": False, "skipped": not push}
    if write_log:
        write_result = write_briefing_log(
            client=client,
            routine=routine,
            now=now,
            summary=result["summary"],
            push_sent=False,
        )
    if push:
        url = str(write_result.get("url") or "")
        push_result = pushover_notify.send_message(
            title=routine.name,
            message=f"{routine.name} ready: {url or 'Briefing & Review Log row written.'}",
            url=url,
            url_title="Open briefing" if url else "",
            priority=0,
            dry_run=dry_run,
        )
    result["write_result"] = write_result
    result["push_result"] = push_result
    result["env_status"] = env_status()
    result["valid"] = not result["issues"] and (not write_log or bool(write_result.get("verified") or dry_run))
    return result


def _format_text(report: Mapping[str, Any]) -> str:
    lines = [
        f"Routine: {(report.get('routine') or {}).get('name') or report.get('routine_key')}",
        f"Valid: {bool(report.get('valid'))}",
        str(report.get("summary") or ""),
    ]
    write = report.get("write_result") or {}
    lines.append(f"Briefing log: created={bool(write.get('created'))} verified={bool(write.get('verified'))} skipped={bool(write.get('skipped'))}")
    push = report.get("push_result") or {}
    lines.append(f"Pushover: sent={bool(push.get('sent'))} dry_run={bool(push.get('dry_run'))} skipped={bool(push.get('skipped'))}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--routine", choices=sorted(BRIEFING_ROUTINES), required=False)
    parser.add_argument("--write-log", action="store_true")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--now")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--env-check", action="store_true")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    args = parser.parse_args(argv)

    if args.env_check:
        report = env_status()
        if args.format == "json":
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(
                "Env check: "
                f"NOTION_TOKEN={report['notion_token']} | "
                f"PUSHOVER_TOKEN={report['pushover_token']} | "
                f"PUSHOVER_USER={report['pushover_user']} | "
                f"Notion-Version={report['notion_version']}"
            )
        return 0 if all([report["notion_token"], report["pushover_token"], report["pushover_user"]]) else 2

    if not args.routine:
        parser.error("--routine is required unless --env-check is used")
    try:
        report = run_briefing(
            routine_key=args.routine,
            write_log=args.write_log,
            push=args.push,
            dry_run=args.dry_run,
            now_text=args.now,
        )
    except Exception as exc:
        report = {"valid": False, "error": str(exc), "routine_key": args.routine}
    Path(args.out).write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    if args.format == "json":
        print(json.dumps(report, indent=2, default=str))
    else:
        print(_format_text(report))
    return 0 if report.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
