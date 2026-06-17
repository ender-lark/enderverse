#!/usr/bin/env python3
"""Deterministic Notion REST helpers for Life OS and Work OS routines."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

from life_work_os_config import NOTION_VERSION


NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_TOKEN_ENV = "NOTION_TOKEN"
RETRY_BACKOFF_SECONDS = (1, 2, 5)


class NotionAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class QueryResult:
    data_source_id: str
    rows: list[dict[str, Any]]
    pages_fetched: int
    filter_used: dict[str, Any] | None
    sorts_used: list[dict[str, Any]]


class NotionRestClient:
    """Small stdlib Notion client pinned to the data-source API."""

    def __init__(
        self,
        *,
        token: str | None = None,
        version: str = NOTION_VERSION,
        timeout: float = 30.0,
        dry_run: bool = False,
    ) -> None:
        self.token = token if token is not None else os.environ.get(NOTION_TOKEN_ENV, "")
        self.version = version
        self.timeout = timeout
        self.dry_run = dry_run
        self.requests: list[dict[str, Any]] = []
        if not self.token and not self.dry_run:
            raise NotionAPIError(f"{NOTION_TOKEN_ENV} env var is required")

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        self.requests.append({"method": method, "path": path, "body": body})
        if self.dry_run:
            return {"object": "dry_run", "id": "dry-run"}
        raw = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            NOTION_API_BASE + path,
            data=raw,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": self.version,
                "Content-Type": "application/json",
            },
        )
        for attempt in range(len(RETRY_BACKOFF_SECONDS) + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = response.read().decode("utf-8", errors="replace")
                    return json.loads(payload) if payload else {}
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
                if exc.code == 429 or exc.code >= 500:
                    if attempt < len(RETRY_BACKOFF_SECONDS):
                        time.sleep(RETRY_BACKOFF_SECONDS[attempt])
                        continue
                raise NotionAPIError(f"Notion HTTP {exc.code} {method} {path}: {error_body[:500]}") from exc
            except urllib.error.URLError as exc:
                if attempt < len(RETRY_BACKOFF_SECONDS):
                    time.sleep(RETRY_BACKOFF_SECONDS[attempt])
                    continue
                raise NotionAPIError(f"Notion request failed {method} {path}: {exc}") from exc
        raise NotionAPIError(f"Notion request exhausted retries {method} {path}")

    def retrieve_page(self, page_id: str) -> dict[str, Any]:
        return self._request("GET", f"/pages/{page_id}")

    def retrieve_data_source(self, data_source_id: str) -> dict[str, Any]:
        return self._request("GET", f"/data_sources/{data_source_id}")

    def query_data_source(
        self,
        data_source_id: str,
        *,
        filter_: dict[str, Any] | None = None,
        sorts: list[dict[str, Any]] | None = None,
        page_size: int = 100,
    ) -> QueryResult:
        rows: list[dict[str, Any]] = []
        start_cursor: str | None = None
        pages_fetched = 0
        while True:
            body: dict[str, Any] = {"page_size": page_size}
            if filter_:
                body["filter"] = filter_
            if sorts:
                body["sorts"] = sorts
            if start_cursor:
                body["start_cursor"] = start_cursor
            payload = self._request("POST", f"/data_sources/{data_source_id}/query", body)
            pages_fetched += 1
            results = payload.get("results") if isinstance(payload.get("results"), list) else []
            rows.extend(row for row in results if isinstance(row, dict))
            if not payload.get("has_more"):
                break
            next_cursor = payload.get("next_cursor")
            if not next_cursor:
                break
            start_cursor = str(next_cursor)
        return QueryResult(
            data_source_id=data_source_id,
            rows=rows,
            pages_fetched=pages_fetched,
            filter_used=filter_,
            sorts_used=sorts or [],
        )

    def list_block_children(self, block_id: str, *, page_size: int = 100) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        cursor = None
        while True:
            params = {"page_size": str(page_size)}
            if cursor:
                params["start_cursor"] = cursor
            path = f"/blocks/{block_id}/children?{urllib.parse.urlencode(params)}"
            payload = self._request("GET", path)
            rows.extend(row for row in payload.get("results") or [] if isinstance(row, dict))
            if not payload.get("has_more"):
                break
            cursor = payload.get("next_cursor")
            if not cursor:
                break
        return rows

    def append_block_children(self, block_id: str, children: list[dict[str, Any]]) -> dict[str, Any]:
        return self._request("PATCH", f"/blocks/{block_id}/children", {"children": children})

    def create_page(
        self,
        *,
        data_source_id: str,
        properties: dict[str, Any],
        children: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "parent": {"data_source_id": data_source_id},
            "properties": properties,
        }
        if children:
            body["children"] = children
        return self._request("POST", "/pages", body)

    def update_page_properties(self, page_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/pages/{page_id}", {"properties": properties})


def env_status(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    env = env or os.environ
    return {
        "notion_token": bool(str(env.get(NOTION_TOKEN_ENV) or "").strip()),
        "pushover_token": bool(str(env.get("PUSHOVER_TOKEN") or env.get("PUSHOVER_APP_TOKEN") or "").strip()),
        "pushover_user": bool(str(env.get("PUSHOVER_USER") or env.get("PUSHOVER_USER_KEY") or "").strip()),
        "notion_version": NOTION_VERSION,
        "secrets_source": "environment_only",
    }


def properties_schema(data_source: dict[str, Any]) -> dict[str, dict[str, Any]]:
    props = data_source.get("properties")
    return props if isinstance(props, dict) else {}


def property_type(schema: Mapping[str, dict[str, Any]], name: str) -> str | None:
    row = schema.get(name)
    if not isinstance(row, dict):
        return None
    prop_type = row.get("type")
    return str(prop_type) if prop_type else None


def title_property(schema: Mapping[str, dict[str, Any]]) -> str | None:
    for name, row in schema.items():
        if isinstance(row, dict) and row.get("type") == "title":
            return name
    return None


def _condition(prop_type: str, operator: str, value: Any) -> dict[str, Any] | None:
    if prop_type == "status":
        return {"status": {operator: value}}
    if prop_type == "select":
        return {"select": {operator: value}}
    if prop_type == "multi_select":
        mapped = {
            "equals": "contains",
            "does_not_equal": "does_not_contain",
        }.get(operator)
        return {"multi_select": {mapped: value}} if mapped else None
    if prop_type in {"rich_text", "title"}:
        mapped = {
            "equals": "equals",
            "does_not_equal": "does_not_equal",
            "contains": "contains",
            "does_not_contain": "does_not_contain",
        }.get(operator)
        return {prop_type: {mapped: value}} if mapped else None
    return None


def prop_filter(
    schema: Mapping[str, dict[str, Any]],
    name: str,
    operator: str,
    value: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    prop_type = property_type(schema, name)
    if not prop_type:
        return None, f"missing property {name}"
    condition = _condition(prop_type, operator, value)
    if not condition:
        return None, f"unsupported property type for {name}: {prop_type}"
    return {"property": name, **condition}, None


def checkbox_filter(
    schema: Mapping[str, dict[str, Any]],
    name: str,
    value: bool,
) -> tuple[dict[str, Any] | None, str | None]:
    prop_type = property_type(schema, name)
    if not prop_type:
        return None, f"missing property {name}"
    if prop_type != "checkbox":
        return None, f"unsupported property type for {name}: {prop_type}"
    return {"property": name, "checkbox": {"equals": value}}, None


def date_filter(
    schema: Mapping[str, dict[str, Any]],
    name: str,
    operator: str,
    value: date | str,
) -> tuple[dict[str, Any] | None, str | None]:
    prop_type = property_type(schema, name)
    if not prop_type:
        return None, f"missing property {name}"
    if prop_type != "date":
        return None, f"unsupported property type for {name}: {prop_type}"
    text = value.isoformat() if isinstance(value, date) else str(value)
    return {"property": name, "date": {operator: text}}, None


def is_empty_filter(
    schema: Mapping[str, dict[str, Any]],
    name: str,
) -> tuple[dict[str, Any] | None, str | None]:
    prop_type = property_type(schema, name)
    if not prop_type:
        return None, f"missing property {name}"
    if prop_type in {"rich_text", "title", "date", "select", "multi_select", "relation"}:
        return {"property": name, prop_type: {"is_empty": True}}, None
    return None, f"unsupported property type for {name}: {prop_type}"


def and_filter(*filters: dict[str, Any] | None) -> dict[str, Any] | None:
    present = [row for row in filters if row]
    if not present:
        return None
    if len(present) == 1:
        return present[0]
    return {"and": present}


def or_filter(*filters: dict[str, Any] | None) -> dict[str, Any] | None:
    present = [row for row in filters if row]
    if not present:
        return None
    if len(present) == 1:
        return present[0]
    return {"or": present}


def rich_text(content: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": {"content": str(content)[:1900]}}]


def property_payload(schema: Mapping[str, dict[str, Any]], name: str, value: Any) -> dict[str, Any] | None:
    prop_type = property_type(schema, name)
    if not prop_type:
        return None
    if prop_type == "title":
        return {"title": rich_text(str(value))}
    if prop_type == "rich_text":
        return {"rich_text": rich_text(str(value))}
    if prop_type == "select":
        return {"select": {"name": str(value)}}
    if prop_type == "status":
        return {"status": {"name": str(value)}}
    if prop_type == "checkbox":
        return {"checkbox": bool(value)}
    if prop_type == "date":
        return {"date": {"start": value.isoformat() if hasattr(value, "isoformat") else str(value)}}
    return None


def plain_text_from_rich_text(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    return "".join(str(item.get("plain_text") or "") for item in items if isinstance(item, dict)).strip()


def page_title(page: Mapping[str, Any]) -> str:
    props = page.get("properties")
    if not isinstance(props, dict):
        return ""
    for row in props.values():
        if isinstance(row, dict) and row.get("type") == "title":
            return plain_text_from_rich_text(row.get("title"))
    return ""


def property_text(page: Mapping[str, Any], name: str) -> str:
    props = page.get("properties")
    if not isinstance(props, dict):
        return ""
    row = props.get(name)
    if not isinstance(row, dict):
        return ""
    prop_type = row.get("type")
    if prop_type in {"title", "rich_text"}:
        return plain_text_from_rich_text(row.get(prop_type))
    if prop_type in {"select", "status"}:
        value = row.get(prop_type)
        return str((value or {}).get("name") or "") if isinstance(value, dict) else ""
    if prop_type == "multi_select":
        return ", ".join(str(v.get("name") or "") for v in row.get("multi_select") or [] if isinstance(v, dict))
    if prop_type == "date":
        value = row.get("date") or {}
        return str(value.get("start") or "") if isinstance(value, dict) else ""
    if prop_type == "checkbox":
        return "true" if row.get("checkbox") else "false"
    return ""

