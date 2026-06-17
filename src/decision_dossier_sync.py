#!/usr/bin/env python3
"""Sync Live Theses rows into the compact Decision Dossier repo mirror.

Runtime cards read ``decision_dossiers.json`` only. This module converts the
human-editable Live Theses Notion fields into that compact shape without
creating trade posture, sizing, gate, alert, or ranking effects.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import decision_dossiers as dd


LIVE_THESES_DS = "0f083d6f-be67-4815-a64a-a21959812f0d"
LIVE_THESES_SOURCE = f"Live Theses Notion data source {LIVE_THESES_DS}"


class DossierSyncError(RuntimeError):
    """Raised when a requested sync cannot produce a validated payload."""


def _today(value: str | date | None = None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _iso_day(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        value = value.get("start") or value.get("date") or value.get("value")
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def _money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "UNKNOWN"


def _clip(text: Any, limit: int = 220) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def _text_from_rich(chunks: Any) -> str | None:
    if not isinstance(chunks, list):
        return None
    text = "".join(str(c.get("plain_text") or c.get("text", {}).get("content") or "") for c in chunks)
    return text.strip() or None


def property_value(prop: Any) -> Any:
    """Return a plain value from either raw Notion API or connector-flattened properties."""
    if not isinstance(prop, dict) or "type" not in prop:
        return prop
    typ = prop.get("type")
    if typ == "title":
        return _text_from_rich(prop.get("title"))
    if typ in {"rich_text", "text"}:
        return _text_from_rich(prop.get("rich_text")) if "rich_text" in prop else prop.get("text")
    if typ == "select":
        item = prop.get("select")
        return item.get("name") if isinstance(item, dict) else None
    if typ == "multi_select":
        return [item.get("name") for item in prop.get("multi_select", []) if isinstance(item, dict) and item.get("name")]
    if typ == "number":
        return prop.get("number")
    if typ == "date":
        item = prop.get("date")
        return item.get("start") if isinstance(item, dict) else None
    if typ == "url":
        return prop.get("url")
    if typ == "checkbox":
        return bool(prop.get("checkbox"))
    return prop.get(typ)


def flatten_properties(page_or_row: dict[str, Any]) -> dict[str, Any]:
    """Normalize Notion page/query properties into a flat dict."""
    props = page_or_row.get("properties") if isinstance(page_or_row.get("properties"), dict) else page_or_row
    flat = {str(key): property_value(value) for key, value in props.items()}
    if page_or_row.get("url") and not flat.get("url"):
        flat["url"] = page_or_row["url"]
    if page_or_row.get("id") and not flat.get("id"):
        flat["id"] = page_or_row["id"]
    return flat


def _extract_properties_from_page_text(text: str) -> dict[str, Any] | None:
    match = re.search(r"<properties>\s*(\{.*?\})\s*</properties>", text, flags=re.S)
    if not match:
        return None
    return json.loads(match.group(1))


def _extract_page_url(text: str) -> str | None:
    match = re.search(r"<page\s+url=\"([^\"]+)\"", text)
    return match.group(1) if match else None


def pages_from_connector_fetch(payload: Any) -> list[dict[str, Any]]:
    """Extract page-shaped rows from a Notion connector fetch/search payload.

    This supports the MCP fetch result shape used when the row-query tool is not
    available. It also accepts direct page dictionaries and lists for tests or
    supplied snapshots.
    """
    if isinstance(payload, list):
        pages: list[dict[str, Any]] = []
        for item in payload:
            pages.extend(pages_from_connector_fetch(item))
        return pages
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("properties"), dict):
        return [payload]
    if isinstance(payload.get("results"), list):
        return [row for row in payload["results"] if isinstance(row, dict)]

    pages: list[dict[str, Any]] = []
    for item in payload.get("content") or []:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            continue
        raw_text = item["text"]
        try:
            outer = json.loads(raw_text)
        except json.JSONDecodeError:
            outer = {"text": raw_text}
        page_text = str(outer.get("text") or "")
        props = _extract_properties_from_page_text(page_text)
        if not props:
            continue
        url = props.get("url") or outer.get("url") or _extract_page_url(page_text)
        pages.append({
            "title": outer.get("title") or props.get("Ticker"),
            "url": url,
            "properties": props,
        })
    return pages


def _get(props: dict[str, Any], key: str) -> Any:
    value = props.get(key)
    if value not in (None, ""):
        return value
    expanded = props.get(f"date:{key}:start")
    return expanded if expanded not in (None, "") else None


def _read(label: str, text: str, as_of: str | None, max_age_days: int | None, source: str) -> dict[str, Any]:
    return {
        "label": label,
        "text": text,
        "as_of": as_of,
        "max_age_days": max_age_days,
        "source": source,
    }


def pending_sync_row(ticker: str, *, reason: str, synced_at: str, notion_url: str | None = None) -> dict[str, Any]:
    tick = ticker.upper().strip()
    return {
        "ticker": tick,
        "status": "pending_sync",
        "one_liner": f"{tick} dossier mirror pending verified Live Theses sync: {reason}",
        "notion_url": notion_url,
        "last_reviewed": None,
        "next_review_due": None,
        "synced_at": synced_at,
        "reads": {
            "edge": _read("Edge/moat", "UNKNOWN - Live Theses edge read was not available.", None, 90, "decision_dossier_sync"),
            "price": _read("Good buy price?", "UNKNOWN - no fresh price or valuation read was synced.", None, 1, "decision_dossier_sync"),
            "timing": _read("Good timing?", "UNKNOWN - no fresh timing/catalyst read was synced.", None, 1, "decision_dossier_sync"),
            "avoid": _read("What-not / avoid", "UNKNOWN - Live Theses avoid/falsifier read was not available.", None, 90, "decision_dossier_sync"),
        },
    }


def dossier_from_live_thesis(page_or_row: dict[str, Any], *, today: str | date | None = None) -> dict[str, Any]:
    """Convert one Live Theses row/page into one decision_dossiers row."""
    day = _today(today)
    synced_at = day.isoformat()
    props = flatten_properties(page_or_row)
    ticker = str(_get(props, "Ticker") or page_or_row.get("title") or "").upper().strip()
    if not ticker:
        raise DossierSyncError("Live Theses row missing Ticker")

    notion_url = str(_get(props, "url") or page_or_row.get("url") or "").strip() or None
    named_anchor = _clip(_get(props, "Named Anchor"), 260)
    active_risks = _clip(_get(props, "Active Risks Named"), 260)
    exit_conditions = _clip(_get(props, "Exit Conditions"), 260)
    forward_catalyst = _clip(_get(props, "Forward Catalyst"), 220)
    reentry_source = _clip(_get(props, "Re-Entry Zone Source"), 160)
    anchor_status = str(_get(props, "Anchor Status") or "not_checked")
    anchor_source = str(_get(props, "Anchor Source") or "not_checked")
    thesis_status = str(_get(props, "Thesis Status") or "not_checked")
    tier = str(_get(props, "Tier") or "not_checked")
    factor_bucket = str(_get(props, "Factor Bucket") or "not_checked")
    anchor_date = _iso_day(_get(props, "Anchor Date"))
    last_reviewed = _iso_day(_get(props, "Last Two-Lens Run")) or anchor_date
    next_review_due = _iso_day(_get(props, "Next Review Due"))

    if not named_anchor and not active_risks and not exit_conditions:
        return pending_sync_row(
            ticker,
            reason="row did not include Named Anchor, Active Risks Named, or Exit Conditions",
            synced_at=synced_at,
            notion_url=notion_url,
        )

    review_overdue = bool(next_review_due and date.fromisoformat(next_review_due) < day)
    broken = anchor_status.upper() in {"BROKEN", "SUPERSEDED"} or thesis_status in {"Expired", "Thesis-Break Watch"}
    status = "stale" if review_overdue or broken else "fresh"

    edge_bits = [
        f"{tier} / {thesis_status} thesis",
        f"anchor {anchor_status} from {anchor_source}",
    ]
    if named_anchor:
        edge_bits.append(named_anchor)
    edge_text = "; ".join(edge_bits) + "."

    zone_lo = _get(props, "Re-Entry Zone Lo")
    zone_hi = _get(props, "Re-Entry Zone Hi")
    if zone_lo is not None and zone_hi is not None:
        price_text = f"Re-entry zone {_money(zone_lo)}-{_money(zone_hi)}"
        if reentry_source:
            price_text += f"; source: {reentry_source}"
        price_text += ". Re-check live price/tape before action."
        price_as_of = last_reviewed
        price_source = "Live Theses Re-Entry Zone"
    else:
        price_text = "UNKNOWN - Live Theses row has no re-entry zone or current valuation read."
        price_as_of = None
        price_source = "Live Theses"

    if forward_catalyst:
        timing_text = f"Forward catalyst: {forward_catalyst}. Re-check timing before action."
        timing_as_of = last_reviewed
    elif review_overdue:
        timing_text = f"UNKNOWN - no forward catalyst is mirrored and thesis review was due {next_review_due}."
        timing_as_of = next_review_due
    else:
        timing_text = "UNKNOWN - no current timing/catalyst read is mirrored."
        timing_as_of = None

    avoid_bits = []
    if active_risks:
        avoid_bits.append(f"Risks: {active_risks}")
    if exit_conditions:
        avoid_bits.append(f"Exit/falsifier: {exit_conditions}")
    avoid_text = " ".join(avoid_bits) if avoid_bits else "UNKNOWN - no avoid/falsifier read is mirrored."

    review_note = f"review due {next_review_due}, tactical reads not current" if review_overdue else "review current"
    one_liner = (
        f"{ticker}: {tier} / {thesis_status}; anchor {anchor_status}. "
        f"{_clip(named_anchor, 130) if named_anchor else 'No named anchor text mirrored.'} "
        f"{review_note}."
    )

    return {
        "ticker": ticker,
        "status": status,
        "one_liner": one_liner,
        "notion_url": notion_url,
        "last_reviewed": last_reviewed,
        "next_review_due": next_review_due,
        "synced_at": synced_at,
        "source_data": {
            "source": LIVE_THESES_SOURCE,
            "factor_bucket": factor_bucket,
            "anchor_source": anchor_source,
            "thesis_status": thesis_status,
            "anchor_status": anchor_status,
        },
        "reads": {
            "edge": _read("Edge/moat", edge_text, last_reviewed, 90, "Live Theses: Named Anchor"),
            "price": _read("Good buy price?", price_text, price_as_of, 1, price_source),
            "timing": _read("Good timing?", timing_text, timing_as_of, 1, "Live Theses: Forward Catalyst / Next Review Due"),
            "avoid": _read("What-not / avoid", avoid_text, last_reviewed, 90, "Live Theses: Active Risks Named / Exit Conditions"),
        },
    }


def fetch_live_rows(tickers: list[str]) -> list[dict[str, Any]]:
    try:
        from notion_helpers import NotionClient
    except ImportError as exc:
        raise DossierSyncError("notion_helpers is not importable") from exc

    client = NotionClient()
    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        res = client.query_database(
            data_source_id=LIVE_THESES_DS,
            filter_={"property": "Ticker", "title": {"equals": ticker.upper()}},
            page_size=5,
        )
        if not res.ok or not res.data:
            raise DossierSyncError(f"Live Theses query failed for {ticker}: {res.error or res.status}")
        rows.extend(res.data.get("results") or [])
    return rows


def build_payload(
    rows: list[dict[str, Any]],
    *,
    existing: dict[str, Any] | None = None,
    tickers: list[str] | None = None,
    today: str | date | None = None,
    sync_status: str = "synced_from_live_theses",
) -> dict[str, Any]:
    day = _today(today).isoformat()
    existing_rows = dict((existing or {}).get("dossiers") or {})
    by_ticker: dict[str, dict[str, Any]] = {}
    for row in rows:
        dossier = dossier_from_live_thesis(row, today=day)
        by_ticker[dossier["ticker"]] = dossier

    for ticker in tickers or []:
        tick = ticker.upper().strip()
        if tick and tick not in by_ticker:
            by_ticker[tick] = pending_sync_row(
                tick,
                reason="no matching Live Theses row was fetched",
                synced_at=day,
            )

    existing_rows.update(by_ticker)
    payload = {
        "generated_at": day,
        "source": {
            "human_edit_source": LIVE_THESES_SOURCE,
            "runtime_source": "repo mirror",
            "sync_status": sync_status,
            "alert_sequence_note": "Dossier alert/watch wiring is deferred to a follow-up that consumes merged staleness guard PR#57.",
        },
        "dossiers": dict(sorted(existing_rows.items())),
    }
    return dd.assert_valid_payload(payload)


def load_input_pages(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    payload = json.loads(p.read_text(encoding="utf-8-sig"))
    pages = pages_from_connector_fetch(payload)
    if not pages:
        raise DossierSyncError(f"{p}: no Notion page rows found")
    return pages


def write_payload(payload: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _parse_tickers(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip().upper() for item in re.split(r"[,\s]+", raw) if item.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="JSON file from Notion API/query or connector fetch")
    parser.add_argument("--live", action="store_true", help="Query Live Theses through notion_helpers/NOTION_API_TOKEN")
    parser.add_argument("--tickers", help="Comma/space-separated tickers to sync or preserve as pending")
    parser.add_argument("--existing", default=str(dd.DEFAULT_DOSSIERS_PATH), help="Existing dossier JSON to merge")
    parser.add_argument("--out", default=str(dd.DEFAULT_DOSSIERS_PATH), help="Output decision_dossiers.json path")
    parser.add_argument("--today", help="Override sync date")
    parser.add_argument("--dry-run", action="store_true", help="Print payload instead of writing")
    args = parser.parse_args(argv)

    tickers = _parse_tickers(args.tickers)
    if not args.input and not args.live:
        parser.error("one of --input or --live is required")
    if args.input and args.live:
        parser.error("use only one of --input or --live")

    rows = fetch_live_rows(tickers) if args.live else load_input_pages(args.input)
    existing = dd.load_payload(args.existing)
    status = "synced_from_live_theses_api" if args.live else "synced_from_verified_connector_fetch"
    payload = build_payload(rows, existing=existing, tickers=tickers, today=args.today, sync_status=status)

    if args.dry_run:
        print(json.dumps(payload, indent=2))
    else:
        write_payload(payload, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
