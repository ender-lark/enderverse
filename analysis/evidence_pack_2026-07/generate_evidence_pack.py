#!/usr/bin/env python3
"""Generate the July 2026 Investing OS evidence pack.

The pack is deliberately conservative:
- raw Notion snapshots are saved when NOTION_TOKEN is available;
- repo caches are used as fallback/source evidence;
- unavailable joins stay blank with a gap_reason instead of being inferred.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PACK_DATE = "2026-07-02"
DEFAULT_OUT_DIR = Path("analysis") / "evidence_pack_2026-07"
SOURCE_CALL_LOG_DS = "e7def40e-1492-458a-9de8-bd77cd3f8471"
DECISIONS_LOG_DS = "632c97f1-192a-4933-8682-60c730446caf"
RESEARCH_QUEUE_DS = "cab89576-0933-40b0-ad2e-6f9a6188e804"
SYSTEM_UPDATE_QUEUE_DS = "968cfff4-369c-40bb-b748-5633b9ff7685"

FALSE_TICKERS = {
    "A", "AI", "ALL", "AM", "API", "AS", "AT", "ATH", "BE", "BUY", "BY",
    "CAN", "CEO", "CFO", "CI", "CPI", "DTE", "ETF", "ET", "FED", "FOMC",
    "FOR", "GDP", "GO", "HIGH", "IF", "IN", "IV", "LOW", "MAY", "MCP",
    "NO", "NOW", "OF", "OK", "ON", "OR", "PM", "PT", "Q", "RE", "SEC",
    "SELL", "T", "THE", "TO", "TV", "US", "USD", "WE", "YES",
}

QUALITY_BY_TIER = {
    "A": "Specific",
    "B": "Target",
    "C": "Directional",
    "D": "Vague",
}

OUTCOME_BUCKET = {
    "win": "hit",
    "validated": "hit",
    "right call": "hit",
    "loss": "miss",
    "wrong call": "miss",
    "miss": "miss",
    "push": "push",
    "pending": "open",
    "active": "open",
    "open": "open",
    "unscored": "open",
    "": "open",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: list[str] = []
        for row in rows:
            for key in row:
                if key not in keys:
                    keys.append(key)
        fieldnames = keys
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                clean = {}
                for key in fieldnames:
                    value = row.get(key, "")
                    if isinstance(value, (list, dict)):
                        clean[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
                    else:
                        clean[key] = value
                writer.writerow(clean)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def parse_date(value: Any) -> date | None:
    if value in (None, "", [], {}):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def safe_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if value in (None, "", [], {}):
        return None
    text = str(value).replace("$", "").replace(",", "").replace("%", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def pct_return(start: float | None, end: float | None) -> float | None:
    if start in (None, 0) or end is None:
        return None
    return (end - start) / start


def money(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.2f}"


def positive_float(value: Any) -> float | None:
    num = safe_float(value)
    if num is None or num <= 0:
        return None
    return num


def percent(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}"


def compact(text: Any, limit: int = 240) -> str:
    out = " ".join(str(text or "").split())
    if len(out) <= limit:
        return out
    return out[: limit - 3] + "..."


def notion_property_value(prop: Any) -> Any:
    if not isinstance(prop, dict):
        return prop
    typ = prop.get("type")
    if typ in {"title", "rich_text"}:
        items = prop.get(typ) or []
        if isinstance(items, list):
            return "".join(str(item.get("plain_text") or "") for item in items if isinstance(item, dict)).strip()
        return ""
    if typ in {"select", "status"}:
        value = prop.get(typ)
        return str((value or {}).get("name") or "") if isinstance(value, dict) else ""
    if typ == "multi_select":
        return [
            str(item.get("name") or "")
            for item in (prop.get("multi_select") or [])
            if isinstance(item, dict) and item.get("name")
        ]
    if typ == "date":
        value = prop.get("date") or {}
        return str(value.get("start") or "") if isinstance(value, dict) else ""
    if typ in {"created_time", "last_edited_time", "url", "email", "phone_number", "number", "checkbox"}:
        return prop.get(typ)
    if typ == "relation":
        return [row.get("id") for row in prop.get("relation") or [] if isinstance(row, dict)]
    if "plain_text" in prop:
        return prop.get("plain_text")
    return ""


def flatten_notion_page(page: dict[str, Any]) -> dict[str, Any]:
    props = page.get("properties") if isinstance(page.get("properties"), dict) else {}
    flat = {
        "id": page.get("id") or "",
        "url": page.get("url") or "",
        "created_time": page.get("created_time") or "",
        "last_edited_time": page.get("last_edited_time") or "",
    }
    for key, value in props.items():
        flat[str(key)] = notion_property_value(value)
    return flat


def query_notion_data_source(repo_root: Path, data_source_id: str, *, page_size: int = 100) -> dict[str, Any]:
    sys.path.insert(0, str(repo_root / "src"))
    from life_work_os_notion import NotionAPIError, NotionRestClient  # type: ignore

    client = NotionRestClient(timeout=30)
    try:
        result = client.query_data_source(data_source_id, page_size=page_size)
    except NotionAPIError as exc:
        return {
            "ok": False,
            "data_source_id": data_source_id,
            "error": str(exc),
            "rows": [],
            "pages_fetched": 0,
        }
    return {
        "ok": True,
        "data_source_id": data_source_id,
        "rows": result.rows,
        "pages_fetched": result.pages_fetched,
        "fetched_at": now_iso(),
    }


def fetch_notion_snapshots(repo_root: Path, out_dir: Path, *, skip: bool) -> dict[str, Any]:
    raw_dir = out_dir / "raw"
    snapshots: dict[str, Any] = {}
    if skip or not os.environ.get("NOTION_TOKEN"):
        gap = {
            "ok": False,
            "error": "NOTION_TOKEN missing or --no-notion supplied",
            "rows": [],
            "pages_fetched": 0,
        }
        for name in ("source_call_log", "decisions_log", "research_queue", "system_update_queue"):
            snapshots[name] = dict(gap, name=name)
            write_json(raw_dir / f"notion_{name}.error.json", snapshots[name])
        return snapshots

    targets = {
        "source_call_log": SOURCE_CALL_LOG_DS,
        "decisions_log": DECISIONS_LOG_DS,
        "research_queue": RESEARCH_QUEUE_DS,
        "system_update_queue": SYSTEM_UPDATE_QUEUE_DS,
    }
    for name, ds in targets.items():
        snap = query_notion_data_source(repo_root, ds, page_size=100)
        snapshots[name] = snap
        if snap.get("ok"):
            write_json(raw_dir / f"notion_{name}.json", snap)
        else:
            write_json(raw_dir / f"notion_{name}.error.json", snap)
    return snapshots


def business_days_ending(end: date, count: int) -> list[date]:
    days: list[date] = []
    cur = end
    while len(days) < count:
        if cur.weekday() < 5:
            days.append(cur)
        cur -= timedelta(days=1)
    return list(reversed(days))


def build_price_context(repo_root: Path, feed: dict[str, Any], account_positions: dict[str, Any]) -> dict[str, Any]:
    current: dict[str, float] = {}
    for key, value in (feed.get("current_closes") or {}).items():
        num = safe_float(value)
        if num is not None:
            current[str(key).upper()] = num

    for row in account_positions.get("combined_positions") or []:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").upper()
        shares = safe_float(row.get("shares"))
        mv = safe_float(row.get("market_value"))
        if ticker and shares and shares > 0 and mv is not None:
            current.setdefault(ticker, mv / shares)

    closes = read_json(repo_root / "src" / "uw_closes.json", {}) or {}
    as_of = parse_date((account_positions or {}).get("snapshot_date")) or parse_date((feed.get("open_opportunities") or {}).get("as_of"))
    as_of = as_of or date(2026, 7, 1)
    series: dict[str, list[tuple[date, float]]] = {}
    for ticker, values in closes.items():
        if not isinstance(values, list):
            continue
        nums = [safe_float(v) for v in values]
        nums = [v for v in nums if v is not None]
        if not nums:
            continue
        dates = business_days_ending(as_of, len(nums))
        tk = str(ticker).upper()
        series[tk] = list(zip(dates, nums))
        current.setdefault(tk, nums[-1])

    return {"current": current, "series": series, "as_of": as_of.isoformat()}


def price_on_or_after(series: list[tuple[date, float]], target: date) -> tuple[date, float] | None:
    for day, close in series:
        if day >= target:
            return day, close
    return None


def price_return_for_date(price_ctx: dict[str, Any], ticker: str, start_date: date | None, horizon_days: int | None = None) -> dict[str, Any]:
    tk = str(ticker or "").upper()
    if not tk or start_date is None:
        return {"gap": "missing ticker or start_date"}
    series = price_ctx.get("series", {}).get(tk)
    if not series:
        return {"gap": "no dated local price series for ticker"}
    start = price_on_or_after(series, start_date)
    if not start:
        return {"gap": "start date outside local price series"}
    target_date = start_date + timedelta(days=horizon_days) if horizon_days is not None else parse_date(price_ctx.get("as_of"))
    if target_date is None:
        return {"gap": "missing target date"}
    end = price_on_or_after(series, target_date)
    if not end:
        return {"gap": "horizon not mature in local price series"}
    ret = pct_return(start[1], end[1])
    return {
        "start_date_used": start[0].isoformat(),
        "start_price": start[1],
        "end_date_used": end[0].isoformat(),
        "end_price": end[1],
        "return": ret,
        "gap": "",
    }


def current_position_maps(account_positions: dict[str, Any]) -> tuple[dict[str, float], dict[str, float], dict[str, list[dict[str, Any]]]]:
    book = safe_float(account_positions.get("sleeve_value")) or 0.0
    pct_by_ticker: dict[str, float] = {}
    mv_by_ticker: dict[str, float] = {}
    option_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in account_positions.get("combined_positions") or []:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").upper()
        mv = safe_float(row.get("market_value")) or 0.0
        if ticker and mv:
            mv_by_ticker[ticker] = mv_by_ticker.get(ticker, 0.0) + mv
            if book:
                pct_by_ticker[ticker] = 100.0 * mv_by_ticker[ticker] / book
    for row in account_positions.get("account_positions") or []:
        if not isinstance(row, dict):
            continue
        opt = row.get("option")
        if opt:
            ticker = str((opt or {}).get("underlying") or row.get("ticker") or "").upper()
            if ticker:
                option_rows[ticker].append(row)
    return pct_by_ticker, mv_by_ticker, option_rows


def build_known_tickers(*payloads: Any) -> set[str]:
    tickers: set[str] = set()

    def add(value: Any) -> None:
        if not value:
            return
        text = str(value).upper().strip()
        if re.fullmatch(r"[A-Z][A-Z0-9]{1,5}", text) and text not in FALSE_TICKERS:
            tickers.add(text)

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).lower() in {"ticker", "symbol", "underlying", "proxy"}:
                    add(child)
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for payload in payloads:
        walk(payload)
    return tickers


def extract_tickers(text: Any, known: set[str]) -> list[str]:
    haystack = str(text or "")
    found: list[str] = []
    for match in re.finditer(r"\b[A-Z][A-Z0-9]{1,5}\b", haystack):
        ticker = match.group(0).upper()
        if ticker in FALSE_TICKERS:
            continue
        if known and ticker not in known:
            continue
        if ticker not in found:
            found.append(ticker)
    return found


def horizon_bucket(window_days: int | None) -> str:
    if window_days is None:
        return "unknown"
    if window_days <= 14:
        return "0-14d"
    if window_days <= 30:
        return "15-30d"
    if window_days <= 60:
        return "31-60d"
    if window_days <= 120:
        return "61-120d"
    return "121d+"


def normalize_source_calls(notion_snapshot: dict[str, Any], repo_root: Path) -> tuple[list[dict[str, Any]], str]:
    rows: list[dict[str, Any]] = []
    if notion_snapshot.get("ok") and notion_snapshot.get("rows"):
        for page in notion_snapshot.get("rows") or []:
            flat = flatten_notion_page(page)
            made = flat.get("Date Made")
            end = flat.get("Window End")
            made_d = parse_date(made)
            end_d = parse_date(end)
            window_days = (end_d - made_d).days if made_d and end_d else None
            tickers = flat.get("Tickers Touched") or flat.get("Position Tickers Affected") or ""
            if isinstance(tickers, list):
                tickers = ", ".join(str(t) for t in tickers)
            rows.append({
                "id": flat.get("id"),
                "url": flat.get("url"),
                "source": flat.get("Source") or "",
                "ticker": tickers,
                "tier": str(flat.get("Tier") or "").upper(),
                "confidence_in_tier": flat.get("Confidence in Tier") or "",
                "date": made or "",
                "window_end": end or "",
                "window_days": window_days,
                "outcome": flat.get("Outcome") or "",
                "backfill": str(flat.get("Backfill") or "").lower() == "true",
                "call_summary": flat.get("Call Summary") or "",
                "verbatim_quote": flat.get("Verbatim Quote") or "",
                "source_record": "notion_source_call_log",
            })
        return rows, "notion_source_call_log"

    local = read_json(repo_root / "src" / "source_calls.json", []) or []
    for row in local:
        if not isinstance(row, dict):
            continue
        rows.append({
            "id": row.get("id"),
            "url": "",
            "source": row.get("source") or "",
            "ticker": row.get("ticker") or "",
            "tier": str(row.get("tier") or "").upper(),
            "confidence_in_tier": row.get("confidence_in_tier") or "",
            "date": row.get("date") or "",
            "window_end": row.get("window_end") or "",
            "window_days": safe_float(row.get("window_days")),
            "outcome": row.get("outcome") or "",
            "backfill": bool(row.get("backfill")),
            "call_summary": row.get("call_summary") or "",
            "verbatim_quote": row.get("verbatim_quote") or "",
            "source_record": "repo_source_calls_json",
        })
    return rows, "repo_source_calls_json"


def generate_source_hit_rates(out_dir: Path, source_calls: list[dict[str, Any]], fetch_source: str) -> dict[str, Any]:
    detail_rows: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)
    for row in source_calls:
        tier = str(row.get("tier") or "").upper()
        quality = QUALITY_BY_TIER.get(tier, "Unknown")
        window_days = safe_float(row.get("window_days"))
        horizon = horizon_bucket(int(window_days) if window_days is not None else None)
        outcome_text = str(row.get("outcome") or "").strip().lower()
        bucket = OUTCOME_BUCKET.get(outcome_text, "open")
        key = (str(row.get("source") or "").strip() or "unknown", quality, horizon)
        grouped[key][bucket] += 1
        grouped[key]["n"] += 1
        detail_rows.append({
            "source": key[0],
            "ticker": row.get("ticker") or "",
            "quality_ladder": quality,
            "tier": tier,
            "horizon": horizon,
            "window_days": int(window_days) if window_days is not None else "",
            "outcome": row.get("outcome") or "",
            "outcome_bucket": bucket,
            "date": row.get("date") or "",
            "window_end": row.get("window_end") or "",
            "backfill": row.get("backfill"),
            "source_record": row.get("source_record"),
            "id": row.get("id") or "",
            "url": row.get("url") or "",
        })

    rate_rows: list[dict[str, Any]] = []
    for (source, quality, horizon), counts in sorted(grouped.items()):
        hit = counts.get("hit", 0)
        miss = counts.get("miss", 0)
        push = counts.get("push", 0)
        open_n = counts.get("open", 0)
        n = counts.get("n", 0)
        scored = hit + miss + push
        hit_rate = hit / (hit + miss) if (hit + miss) else None
        rate_rows.append({
            "source": source,
            "quality_ladder": quality,
            "horizon": horizon,
            "n": n,
            "hit": hit,
            "miss": miss,
            "push": push,
            "open": open_n,
            "scored_n": scored,
            "hit_rate_ex_push": percent(hit_rate),
            "low_n_cell": "true" if n < 15 else "false",
            "low_scored_n": "true" if scored < 15 else "false",
        })

    write_csv(out_dir / "source_hit_rates.csv", rate_rows)
    write_csv(out_dir / "source_hit_rates_detail.csv", detail_rows)
    total = len(detail_rows)
    low_cells = sum(1 for row in rate_rows if row["low_n_cell"] == "true")
    open_calls = sum(1 for row in detail_rows if row["outcome_bucket"] == "open")
    md = [
        "# source_hit_rates",
        "",
        f"Generated: {now_iso()}",
        "",
        f"- Input source: {fetch_source}",
        f"- Calls analyzed: {total}",
        f"- Group cells: {len(rate_rows)}",
        f"- Low-n cells flagged: {low_cells}",
        f"- Open/pending/unscored calls: {open_calls}",
        "",
        "Files:",
        "- source_hit_rates.csv: source x quality ladder x horizon hit/miss/open table with n per cell.",
        "- source_hit_rates_detail.csv: one row per source call used in the grouping.",
        "- generate_evidence_pack.py: generator script for this artifact.",
        "",
        "Honesty notes:",
        "- D/Vague calls are retained in the denominator table; they are not averaged away.",
        "- Hit rates are blank unless there is a hit+miss denominator; low-n and low-scored-n are explicit flags.",
    ]
    write_md(out_dir / "source_hit_rates_summary.md", md)
    return {"rows": len(rate_rows), "detail_rows": len(detail_rows), "low_n_cells": low_cells}


def write_md(path: Path, lines: list[str]) -> None:
    atomic_write_text(path, "\n".join(lines).rstrip() + "\n")


def normalize_decisions(notion_snapshot: dict[str, Any], repo_root: Path) -> tuple[list[dict[str, Any]], str]:
    rows: list[dict[str, Any]] = []
    if notion_snapshot.get("ok") and notion_snapshot.get("rows"):
        for page in notion_snapshot.get("rows") or []:
            flat = flatten_notion_page(page)
            sources = flat.get("Sources")
            if isinstance(sources, list):
                sources = ", ".join(str(s) for s in sources)
            rows.append({
                "id": flat.get("id") or "",
                "url": flat.get("url") or "",
                "date": flat.get("Date") or "",
                "decision": flat.get("Decision") or "",
                "type": flat.get("Type") or "",
                "status": flat.get("Status") or "",
                "sources": sources or "",
                "sleeves_affected": flat.get("Sleeves Affected") or "",
                "outcome": flat.get("Outcome") or "",
                "rationale": flat.get("Rationale") or "",
                "source_record": "notion_decisions_log",
            })
        return rows, "notion_decisions_log"

    dispositions = read_jsonl(repo_root / "src" / "dispositions.jsonl")
    for row in dispositions:
        rows.append({
            "id": row.get("card_id") or "",
            "url": "",
            "date": row.get("et_date") or row.get("ts") or "",
            "decision": f"{row.get('verb') or ''} {row.get('ticker') or ''}".strip(),
            "type": "Disposition",
            "status": row.get("verb") or "",
            "sources": row.get("source") or "",
            "sleeves_affected": row.get("ticker") or "",
            "outcome": "",
            "rationale": row.get("reason") or "",
            "source_record": "repo_dispositions_jsonl",
        })
    return rows, "repo_dispositions_jsonl"


def target_maps(feed: dict[str, Any], account_positions: dict[str, Any]) -> tuple[dict[str, float], dict[str, float], float]:
    target_pct: dict[str, float] = {}
    for row in (feed.get("target_drift") or {}).get("rows") or []:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").upper()
        pct = safe_float(row.get("target_pct"))
        if ticker and pct is not None:
            target_pct[ticker] = pct
    for row in (feed.get("reallocation_brief") or {}).get("rows") or []:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").upper()
        pct = safe_float(row.get("target_pct"))
        if ticker and pct is not None:
            target_pct.setdefault(ticker, pct)
    current_pct, _mv, _option = current_position_maps(account_positions)
    book = safe_float(account_positions.get("sleeve_value")) or safe_float((feed.get("today_decide") or {}).get("goal_anchor", {}).get("book_value")) or 0.0
    return target_pct, current_pct, book


def generate_decision_outcomes(
    out_dir: Path,
    decisions: list[dict[str, Any]],
    source_name: str,
    known_tickers: set[str],
    price_ctx: dict[str, Any],
    feed: dict[str, Any],
    account_positions: dict[str, Any],
    top_prospects: dict[str, Any],
) -> dict[str, Any]:
    target_pct, current_pct, book = target_maps(feed, account_positions)
    current_prices = price_ctx.get("current") or {}
    rows: list[dict[str, Any]] = []
    decision_tickers: set[str] = set()

    for decision in decisions:
        text = " ".join(str(decision.get(k) or "") for k in ("decision", "sleeves_affected", "rationale"))
        tickers = extract_tickers(text, known_tickers)
        if not tickers:
            tickers = [""]
        for ticker in tickers:
            if ticker:
                decision_tickers.add(ticker)
            d = parse_date(decision.get("date"))
            ret_now = price_return_for_date(price_ctx, ticker, d, None) if ticker else {"gap": "no ticker detected"}
            ret_30 = price_return_for_date(price_ctx, ticker, d, 30) if ticker else {"gap": "no ticker detected"}
            ret_90 = price_return_for_date(price_ctx, ticker, d, 90) if ticker else {"gap": "no ticker detected"}
            gap_parts = []
            for label, ret in (("to_date", ret_now), ("plus_30d", ret_30), ("plus_90d", ret_90)):
                if ret.get("gap"):
                    gap_parts.append(f"{label}: {ret['gap']}")
            tk_target = target_pct.get(ticker)
            tk_current = current_pct.get(ticker, 0.0)
            full_doctrine_size = (tk_target / 100.0) * book if tk_target is not None and book else None
            current_size = (tk_current / 100.0) * book if book else None
            return_to_date = ret_now.get("return")
            full_pnl = full_doctrine_size * return_to_date if full_doctrine_size is not None and return_to_date is not None else None
            current_pnl = current_size * return_to_date if current_size is not None and return_to_date is not None else None
            rows.append({
                "decision_date": decision.get("date") or "",
                "ticker": ticker,
                "decision": decision.get("decision") or "",
                "type": decision.get("type") or "",
                "status": decision.get("status") or "",
                "action_taken": decision.get("status") or decision.get("type") or "",
                "outcome_text": decision.get("outcome") or "",
                "size_vs_t_band": "unknown" if tk_target is None else f"current {tk_current:.4f}% vs target {tk_target:.4f}%",
                "current_pct": percent(tk_current),
                "target_pct": percent(tk_target),
                "decision_price_date_used": ret_now.get("start_date_used", ""),
                "decision_price": money(ret_now.get("start_price")),
                "current_price_date_used": ret_now.get("end_date_used", ""),
                "current_price": money(ret_now.get("end_price") or current_prices.get(ticker)),
                "return_to_date": percent(return_to_date),
                "return_plus_30d": percent(ret_30.get("return")),
                "return_plus_90d": percent(ret_90.get("return")),
                "full_doctrine_size_usd": money(full_doctrine_size),
                "current_size_usd": money(current_size),
                "pnl_at_full_doctrine_size_usd": money(full_pnl),
                "pnl_at_current_size_usd": money(current_pnl),
                "pnl_if_acted_on_signal_date_usd": "",
                "gap_reason": "; ".join(gap_parts + ["signal date separate from decision date not structured"] if gap_parts else ["signal date separate from decision date not structured"]),
                "source_record": decision.get("source_record") or source_name,
                "url": decision.get("url") or "",
            })

    cost_rows = build_costliest_gap_rows(
        feed=feed,
        account_positions=account_positions,
        top_prospects=top_prospects,
        decision_tickers=decision_tickers,
        price_ctx=price_ctx,
    )
    write_csv(out_dir / "decision_outcomes.csv", rows)
    write_csv(out_dir / "decision_outcomes_costliest_gaps.csv", cost_rows)
    priced = sum(1 for row in rows if row.get("return_to_date"))
    gap_count = len(rows) - priced
    md = [
        "# decision_outcomes",
        "",
        f"Generated: {now_iso()}",
        "",
        f"- Input source: {source_name}",
        f"- Decisions expanded to ticker rows: {len(rows)}",
        f"- Rows with local dated price join: {priced}",
        f"- Rows with named price/join gaps: {gap_count}",
        f"- Costliest gap candidates emitted: {len(cost_rows)}",
        "",
        "Files:",
        "- decision_outcomes.csv: Decisions Log rows expanded to detected tickers and joined to local price series when available.",
        "- decision_outcomes_costliest_gaps.csv: top under-sizing/missing-target gap candidates with computable foregone P/L.",
        "- generate_evidence_pack.py: generator script for this artifact.",
        "",
        "Honesty notes:",
        "- Full Decisions Log rows are fetched through Notion REST when available.",
        "- Most single-name decisions cannot be fully priced from repo-local dated closes; gap_reason names each missing join.",
        "- `pnl_if_acted_on_signal_date_usd` stays blank unless a structured signal date/price exists. It is not inferred from prose.",
    ]
    write_md(out_dir / "decision_outcomes_summary.md", md)
    return {"rows": len(rows), "priced_rows": priced, "costliest_gap_rows": len(cost_rows)}


def build_costliest_gap_rows(
    *,
    feed: dict[str, Any],
    account_positions: dict[str, Any],
    top_prospects: dict[str, Any],
    decision_tickers: set[str],
    price_ctx: dict[str, Any],
) -> list[dict[str, Any]]:
    target_pct, current_pct, book = target_maps(feed, account_positions)
    current_prices = price_ctx.get("current") or {}
    rows: list[dict[str, Any]] = []
    for ticker, target in sorted(target_pct.items()):
        current = current_pct.get(ticker, 0.0)
        if current >= target:
            continue
        prospect = top_prospects.get(ticker) if isinstance(top_prospects, dict) else None
        flag_price = safe_float((prospect or {}).get("add_price")) if isinstance(prospect, dict) else None
        flag_date = (prospect or {}).get("add_price_date") if isinstance(prospect, dict) else ""
        current_price = current_prices.get(ticker)
        ret = pct_return(flag_price, current_price)
        gap_notional = ((target - current) / 100.0) * book if book else None
        foregone = gap_notional * ret if gap_notional is not None and ret is not None else None
        if foregone is None:
            cost_flag = "unknown"
        elif foregone > 0:
            cost_flag = "foregone_gain"
        elif foregone < 0:
            cost_flag = "loss_avoided_not_foregone_gain"
        else:
            cost_flag = "flat"
        rows.append({
            "ticker": ticker,
            "gap_type": "under_target_or_missing",
            "matched_decision": "yes" if ticker in decision_tickers else "no",
            "flag_source": "top_prospects.add_price" if flag_price is not None else "target_drift_only",
            "flag_date": flag_date,
            "flag_price": money(flag_price),
            "current_price": money(current_price),
            "return_to_date": percent(ret),
            "current_pct": percent(current),
            "target_pct": percent(target),
            "under_size_notional_usd": money(gap_notional),
            "foregone_pnl_usd": money(foregone),
            "cost_flag": cost_flag,
            "gap_reason": "" if foregone is not None else "missing flag price or current price for foregone P/L",
        })
    rows.sort(
        key=lambda row: (
            positive_float(row.get("foregone_pnl_usd")) or float("-inf"),
            safe_float(row.get("under_size_notional_usd")) or 0.0,
        ),
        reverse=True,
    )
    return rows[:10]


def generate_missed_moves(
    out_dir: Path,
    *,
    repo_root: Path,
    notion_research_snapshot: dict[str, Any],
    decisions: list[dict[str, Any]],
    known_tickers: set[str],
    feed: dict[str, Any],
    account_positions: dict[str, Any],
    top_prospects: dict[str, Any],
    price_ctx: dict[str, Any],
) -> dict[str, Any]:
    decision_tickers = set()
    for drow in decisions:
        text = " ".join(str(drow.get(k) or "") for k in ("decision", "sleeves_affected", "rationale"))
        decision_tickers.update(extract_tickers(text, known_tickers))
    target_pct, current_pct, book = target_maps(feed, account_positions)
    current_prices = price_ctx.get("current") or {}
    candidates: list[dict[str, Any]] = []

    if notion_research_snapshot.get("ok") and notion_research_snapshot.get("rows"):
        research_rows = [flatten_notion_page(row) for row in notion_research_snapshot.get("rows") or []]
        research_source = "notion_research_queue"
    else:
        rq = read_json(repo_root / "src" / "research_queue.json", {}) or {}
        research_rows = []
        for row in rq.get("pending") or []:
            if isinstance(row, dict):
                research_rows.append({
                    "Ticker": row.get("ticker") or "",
                    "Priority": row.get("pr") or "",
                    "Status": row.get("status") or "",
                    "Topic": row.get("r") or "",
                    "Reason": row.get("notes") or row.get("source") or "",
                    "Added": rq.get("generated_at") or "",
                    "url": "",
                })
        research_source = "repo_research_queue_json"

    for row in research_rows:
        status = str(row.get("Status") or "").lower()
        if status in {"done", "completed", "archived"}:
            continue
        text = " ".join(str(row.get(k) or "") for k in ("Ticker", "Topic", "Reason", "Findings"))
        tickers = extract_tickers(text, known_tickers) or ([str(row.get("Ticker") or "").upper()] if row.get("Ticker") else [])
        for ticker in tickers:
            if ticker and ticker not in FALSE_TICKERS:
                candidates.append({
                    "source_surface": research_source,
                    "ticker": ticker,
                    "surfaced_date": row.get("Added") or row.get("created_time") or "",
                    "priority": row.get("Priority") or "",
                    "status": row.get("Status") or "",
                    "title": row.get("Topic") or row.get("Reason") or "",
                    "evidence": row.get("Reason") or row.get("Findings") or "",
                    "url": row.get("url") or "",
                })

    open_opps = read_json(repo_root / "src" / "open_opportunities.json", {}) or {}
    for section in ("opportunities", "history"):
        for row in open_opps.get(section) or []:
            if not isinstance(row, dict):
                continue
            status = str(row.get("status") or "").lower()
            if status == "acted":
                continue
            ticker = str(row.get("ticker") or "").upper()
            candidates.append({
                "source_surface": f"open_opportunities.{section}",
                "ticker": ticker,
                "surfaced_date": row.get("first_flagged") or "",
                "priority": "",
                "status": row.get("status") or "",
                "title": row.get("kind") or "",
                "evidence": row.get("reason") or "",
                "flag_price": row.get("flag_price"),
                "url": "",
            })

    for ticker, row in (top_prospects or {}).items():
        if not isinstance(row, dict):
            continue
        candidates.append({
            "source_surface": "top_prospects",
            "ticker": str(row.get("ticker") or ticker).upper(),
            "surfaced_date": row.get("add_date") or row.get("add_price_date") or "",
            "priority": row.get("urgency") or "",
            "status": row.get("direction") or "",
            "title": row.get("summary") or "",
            "evidence": row.get("provenance") or row.get("corroboration") or "",
            "flag_price": row.get("add_price"),
            "url": "",
        })

    bullish = feed.get("bullish_flow") or {}
    for row in bullish.get("rows") or []:
        if not isinstance(row, dict):
            continue
        candidates.append({
            "source_surface": "bullish_flow",
            "ticker": str(row.get("ticker") or "").upper(),
            "surfaced_date": bullish.get("as_of") or "",
            "priority": row.get("strength") or "",
            "status": row.get("direction") or "",
            "title": ", ".join(row.get("signal_types") or []),
            "evidence": "; ".join(row.get("evidence") or []),
            "flag_price": None,
            "url": "",
        })

    dedup: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in candidates:
        ticker = str(row.get("ticker") or "").upper()
        if not ticker or ticker in FALSE_TICKERS:
            continue
        key = (row.get("source_surface") or "", ticker, str(row.get("surfaced_date") or ""))
        dedup[key] = row

    out_rows: list[dict[str, Any]] = []
    for row in dedup.values():
        ticker = str(row.get("ticker") or "").upper()
        flag_price = safe_float(row.get("flag_price"))
        if flag_price is None and row.get("source_surface") != "bullish_flow":
            prospect = top_prospects.get(ticker) if isinstance(top_prospects, dict) else None
            if isinstance(prospect, dict):
                flag_price = safe_float(prospect.get("add_price"))
        current_price = current_prices.get(ticker)
        ret = pct_return(flag_price, current_price)
        target = target_pct.get(ticker)
        current = current_pct.get(ticker, 0.0)
        if target is not None and book:
            potential_notional = max(target - current, 0.0) / 100.0 * book
        else:
            potential_notional = None
        foregone = potential_notional * ret if potential_notional is not None and ret is not None else None
        gap_reason = ""
        if foregone is None:
            gap_reason = "missing structured flag price/current price/target gap for foregone-dollar math"
        elif foregone <= 0:
            gap_reason = "return_to_date is not positive; no foregone gain measured"
        out_rows.append({
            "source_surface": row.get("source_surface") or "",
            "ticker": ticker,
            "surfaced_date": row.get("surfaced_date") or "",
            "matching_decision": "yes" if ticker in decision_tickers else "no",
            "current_position_pct": percent(current),
            "target_pct": percent(target),
            "status": row.get("status") or "",
            "priority": row.get("priority") or "",
            "title": compact(row.get("title")),
            "flag_price": money(flag_price),
            "current_price": money(current_price),
            "return_to_date": percent(ret),
            "potential_gap_notional_usd": money(potential_notional),
            "foregone_dollars": money(foregone),
            "foregone_gain_rankable": "true" if foregone is not None and foregone > 0 else "false",
            "gap_reason": gap_reason,
            "evidence": compact(row.get("evidence"), 500),
            "url": row.get("url") or "",
        })
    out_rows.sort(
        key=lambda row: (
            positive_float(row.get("foregone_dollars")) or float("-inf"),
            safe_float(row.get("potential_gap_notional_usd")) or 0.0,
        ),
        reverse=True,
    )
    for i, row in enumerate(out_rows, 1):
        row["rank"] = i if row.get("foregone_gain_rankable") == "true" else ""

    write_csv(out_dir / "missed_moves.csv", out_rows)
    computable = sum(1 for row in out_rows if row.get("foregone_dollars"))
    positive_foregone = sum(1 for row in out_rows if row.get("foregone_gain_rankable") == "true")
    no_decision = sum(1 for row in out_rows if row.get("matching_decision") == "no")
    md = [
        "# missed_moves",
        "",
        f"Generated: {now_iso()}",
        "",
        f"- Candidate rows: {len(out_rows)}",
        f"- Rows with no matching Decisions Log ticker: {no_decision}",
        f"- Rows with computable foregone dollars: {computable}",
        f"- Rows with positive/rankable foregone gains: {positive_foregone}",
        "",
        "Files:",
        "- missed_moves.csv: surfaced-but-not-decision-matched queue, opportunity, prospect, and flow rows.",
        "- generate_evidence_pack.py: generator script for this artifact.",
        "",
        "Honesty notes:",
        "- Matching is ticker-level only; it does not claim a semantic decision join.",
        "- Foregone dollars are emitted only when a structured flag price, current price, and target gap exist.",
        "- Negative returns are retained as loss-avoided/no-foregone-gain rows, not ranked as costly missed gains.",
        "- Rows without those structured fields remain in the table with a gap_reason.",
    ]
    write_md(out_dir / "missed_moves_summary.md", md)
    return {"rows": len(out_rows), "no_decision_rows": no_decision, "computable_rows": computable}


def generate_feed_reliability(
    out_dir: Path,
    *,
    feed: dict[str, Any],
    account_positions: dict[str, Any],
) -> dict[str, Any]:
    current_pct, mv_by_ticker, option_rows = current_position_maps(account_positions)
    rows: list[dict[str, Any]] = []

    for row in (feed.get("target_drift") or {}).get("rows") or []:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").upper()
        feed_actual = safe_float(row.get("actual_pct")) or 0.0
        broker_actual = current_pct.get(ticker, 0.0)
        direction = row.get("direction") or ""
        if ticker and direction == "MISSING" and broker_actual > 0.01:
            rows.append({
                "case": "target_drift_false_missing_held_name",
                "ticker": ticker,
                "severity": "high",
                "feed_value": f"{direction} actual_pct={feed_actual}",
                "truth_value": f"broker/account_positions pct={broker_actual:.4f}, market_value={mv_by_ticker.get(ticker, 0.0):.2f}",
                "status": "live_divergence",
                "source": "target_drift vs account_positions",
            })
        elif ticker and abs(feed_actual - broker_actual) > 0.25 and broker_actual > 0:
            rows.append({
                "case": "target_drift_actual_pct_mismatch",
                "ticker": ticker,
                "severity": "medium",
                "feed_value": f"actual_pct={feed_actual}",
                "truth_value": f"broker/account_positions pct={broker_actual:.4f}",
                "status": "live_divergence",
                "source": "target_drift vs account_positions",
            })

    data_health_items = (((feed.get("today_decide") or {}).get("data_health") or {}).get("items") or [])
    fundstrat_health = [row for row in data_health_items if isinstance(row, dict) and row.get("source") == "fundstrat_daily"]
    staleness_entries = (feed.get("staleness") or {}).get("entries") or []
    fs_staleness = [row for row in staleness_entries if isinstance(row, dict) and row.get("source") == "fundstrat_daily"]
    source_audit = (feed.get("source_audits") or {}).get("fundstrat") or {}
    if fundstrat_health and fs_staleness:
        health_status = str(fundstrat_health[0].get("status") or "")
        stale_flag = bool(fs_staleness[0].get("stale"))
        if health_status.lower() == "stale" and not stale_flag:
            rows.append({
                "case": "fundstrat_daily_false_staleness_vs_feed_marker",
                "ticker": "",
                "severity": "high",
                "feed_value": f"today_decide.data_health={health_status}; detail={fundstrat_health[0].get('detail')}",
                "truth_value": f"staleness fundstrat_daily date={fs_staleness[0].get('date')} stale={stale_flag}; source_audit daily_calls={source_audit.get('daily_calls')}",
                "status": "live_divergence",
                "source": "today_decide.data_health vs staleness/source_audits",
            })

    hood_options = option_rows.get("HOOD") or []
    hood_actions = [row for row in feed.get("actions") or [] if isinstance(row, dict) and str(row.get("ticker") or "").upper() == "HOOD"]
    if hood_options and hood_actions:
        action = hood_actions[0]
        placement = action.get("account_placement") or {}
        instr = placement.get("instrument_class") or action.get("instrument_class") or ""
        risk_fields_present = any(k in action for k in ("max_loss_usd", "risk_amount_usd", "risk_pct_book"))
        if not risk_fields_present:
            rows.append({
                "case": "hood_option_exposure_without_option_risk_render",
                "ticker": "HOOD",
                "severity": "medium",
                "feed_value": f"action_label={action.get('action_label')} instrument_class={instr}",
                "truth_value": f"broker has {len(hood_options)} HOOD option row(s); action has no max_loss/risk_amount field",
                "status": "seed_case_rescan",
                "source": "latest_cockpit_feed.actions vs account_positions.option",
            })

    if not rows:
        rows.append({
            "case": "rescan",
            "ticker": "",
            "severity": "info",
            "feed_value": "",
            "truth_value": "",
            "status": "no_live_divergences_detected_by_seed_rescan",
            "source": "programmatic rescan",
        })

    write_csv(out_dir / "feed_reliability.csv", rows)
    md = [
        "# feed_reliability",
        "",
        f"Generated: {now_iso()}",
        "",
        f"- Live divergence rows: {sum(1 for row in rows if row.get('status') in {'live_divergence', 'seed_case_rescan'})}",
        f"- Seed cases checked: target_drift false missing, Fundstrat false staleness, HOOD option-risk render.",
        "",
        "Files:",
        "- feed_reliability.csv: live divergence table from seed-case rescan.",
        "- generate_evidence_pack.py: generator script for this artifact.",
        "",
        "Honesty notes:",
        "- Broker/account_positions is treated as truth for held-name current exposure.",
        "- Feed internal freshness surfaces are compared against each other; this does not prove the external FS Ingest Marker state unless the marker is separately fetched.",
    ]
    write_md(out_dir / "feed_reliability_summary.md", md)
    return {"rows": len(rows)}


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def generate_routine_health(out_dir: Path, *, receipts: dict[str, Any], automation_status: dict[str, Any], feed: dict[str, Any]) -> dict[str, Any]:
    receipt_rows = [row for row in receipts.get("receipts") or [] if isinstance(row, dict)]
    by_routine: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in receipt_rows:
        rid = str(row.get("routine_id") or "")
        if rid:
            by_routine[rid].append(row)
    routine_meta: dict[str, dict[str, Any]] = {}
    for row in automation_status.get("routines") or []:
        if not isinstance(row, dict):
            continue
        rid = str(row.get("automation_id") or row.get("id") or "")
        if rid:
            routine_meta[rid] = row

    all_ids = sorted(set(routine_meta) | set(by_routine))
    rows: list[dict[str, Any]] = []
    for rid in all_ids:
        recs = sorted(by_routine.get(rid, []), key=lambda r: str(r.get("recorded_at") or ""))
        latest = recs[-1] if recs else {}
        counts = Counter(str(r.get("status") or "").lower() for r in recs)
        scheduled_success = sum(1 for r in recs if str(r.get("run_source") or "").lower() == "scheduled" and str(r.get("status") or "").lower() == "success")
        latest_status = str(latest.get("status") or "")
        silent_flags: list[str] = []
        if not recs:
            silent_flags.append("no_receipts")
        if latest_status.lower() == "started":
            started_at = parse_dt(latest.get("recorded_at"))
            if started_at:
                age_hours = (datetime.now(timezone.utc) - started_at.astimezone(timezone.utc)).total_seconds() / 3600
                if age_hours > 2:
                    silent_flags.append("latest_started_without_final_over_2h")
        if counts.get("failed", 0) and latest_status.lower() != "failed":
            silent_flags.append("historical_failed_receipts")
        meta = routine_meta.get(rid) or {}
        rows.append({
            "routine_id": rid,
            "name": meta.get("automation_name") or "",
            "role": meta.get("role") or "",
            "configured_status": meta.get("status") or "",
            "schedule": meta.get("schedule") or "",
            "receipt_count": len(recs),
            "started_count": counts.get("started", 0),
            "success_count": counts.get("success", 0),
            "failed_count": counts.get("failed", 0),
            "skip_count": counts.get("skipped", 0) + counts.get("skip", 0),
            "scheduled_success_count": scheduled_success,
            "latest_status": latest_status,
            "latest_run_source": latest.get("run_source") or "",
            "latest_recorded_at": latest.get("recorded_at") or "",
            "latest_summary": compact(latest.get("summary"), 500),
            "silent_failure_flags": ", ".join(silent_flags),
        })

    cloud = (feed.get("source_audits") or {}).get("cloud_routines") or {}
    write_csv(out_dir / "routine_health.csv", rows)
    md = [
        "# routine_health",
        "",
        f"Generated: {now_iso()}",
        "",
        f"- Routines/referenced receipt lanes: {len(rows)}",
        f"- Receipt rows scanned: {len(receipt_rows)}",
        f"- Feed cloud proof line: {cloud.get('line') or 'not present'}",
        f"- Rows with silent-failure flags: {sum(1 for row in rows if row.get('silent_failure_flags'))}",
        "",
        "Files:",
        "- routine_health.csv: run/skip/fail history by routine from receipt and automation status caches.",
        "- generate_evidence_pack.py: generator script for this artifact.",
        "",
        "Honesty notes:",
        "- A started receipt without a later final receipt is flagged; the script does not assume success.",
        "- `failed_count` includes historical failures even when latest status recovered.",
    ]
    write_md(out_dir / "routine_health_summary.md", md)
    return {"rows": len(rows)}


def git_lines(repo_root: Path, args: list[str]) -> list[str]:
    try:
        proc = subprocess.run(["git", *args], cwd=repo_root, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.splitlines() if line.strip()]


def generate_system_inventory(out_dir: Path, repo_root: Path) -> dict[str, Any]:
    files = [
        line for line in git_lines(repo_root, ["ls-files", "src/*.py", "src/*.json"])
        if not Path(line).name.startswith("test_")
    ]
    key_paths = [
        repo_root / "src" / "full_build_runner.py",
        repo_root / "src" / "codex_routine_manifest.json",
        repo_root / "src" / "state_ownership_map.json",
        repo_root / "docs" / "WORKBOARD.md",
        repo_root / "AGENTS.md",
    ]
    key_text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in key_paths if path.is_file()).lower()
    outcome_keywords = (
        "outcome", "disposition", "source_call", "source_calls", "source_rates",
        "open_opportunities", "research_queue", "decision", "feedback", "calibration",
        "receipt", "notion",
    )
    rows: list[dict[str, Any]] = []
    for rel in files:
        path = repo_root / rel
        name = Path(rel).stem
        basename = Path(rel).name.lower()
        text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        lower = text.lower()
        wired = (name.lower() in key_text) or (basename in key_text)
        if rel.endswith(".json"):
            wired = wired or (rel.lower() in key_text)
        feedback = any(keyword in lower for keyword in outcome_keywords)
        touched = git_lines(repo_root, ["log", "-1", "--format=%cs", "--", rel])
        rows.append({
            "module": rel,
            "wired_into_daily_flow": "yes" if wired else "no",
            "daily_flow_reason": "referenced by full build/routine manifest/state/workboard/AGENTS" if wired else "no reference found in main flow index files",
            "feeds_outcomes_back": "yes" if feedback else "no",
            "outcome_feedback_reason": "contains outcome/disposition/calibration/receipt/notion feedback keywords" if feedback else "no outcome feedback keyword found",
            "last_touched": touched[0] if touched else "",
            "build_and_forget_risk": "high" if (not wired and not feedback) else ("medium" if not wired else "low"),
        })
    rows.sort(key=lambda row: (row["build_and_forget_risk"], row["wired_into_daily_flow"], row["module"]))
    write_csv(out_dir / "system_inventory.csv", rows)
    high = sum(1 for row in rows if row["build_and_forget_risk"] == "high")
    medium = sum(1 for row in rows if row["build_and_forget_risk"] == "medium")
    md = [
        "# system_inventory",
        "",
        f"Generated: {now_iso()}",
        "",
        f"- Modules/artifacts inventoried: {len(rows)}",
        f"- High build-and-forget risk: {high}",
        f"- Medium build-and-forget risk: {medium}",
        "",
        "Files:",
        "- system_inventory.csv: module x daily-flow wiring x outcome-feedback x last-touched map.",
        "- generate_evidence_pack.py: generator script for this artifact.",
        "",
        "Honesty notes:",
        "- Daily-flow wiring is a static reference scan over known flow index files, not a runtime trace.",
        "- Outcome feedback is keyword-based and should be treated as a triage map for Fable review, not final architecture truth.",
    ]
    write_md(out_dir / "system_inventory_summary.md", md)
    return {"rows": len(rows), "high_risk": high, "medium_risk": medium}


def build_manifest(out_dir: Path, stats: dict[str, Any], snapshots: dict[str, Any]) -> dict[str, Any]:
    artifacts = {
        "source_hit_rates": {
            "paths": ["source_hit_rates.csv", "source_hit_rates_detail.csv", "source_hit_rates_summary.md"],
            "description": "Source Call Log hit/miss/open table by source, quality ladder, and horizon.",
        },
        "decision_outcomes": {
            "paths": ["decision_outcomes.csv", "decision_outcomes_costliest_gaps.csv", "decision_outcomes_summary.md"],
            "description": "Decisions Log rows joined to local price data where available, with explicit join gaps.",
        },
        "missed_moves": {
            "paths": ["missed_moves.csv", "missed_moves_summary.md"],
            "description": "Research/opportunity/flow surfaces without ticker-level Decisions Log matches, ranked where foregone dollars are computable.",
        },
        "feed_reliability": {
            "paths": ["feed_reliability.csv", "feed_reliability_summary.md"],
            "description": "Seed divergence rescan against broker/feed truth.",
        },
        "routine_health": {
            "paths": ["routine_health.csv", "routine_health_summary.md"],
            "description": "Scheduled routine receipt run/skip/fail history and silent-failure flags.",
        },
        "system_inventory": {
            "paths": ["system_inventory.csv", "system_inventory_summary.md"],
            "description": "Build-and-forget map across src modules and JSON artifacts.",
        },
    }
    raw = {}
    for name, snap in snapshots.items():
        raw[name] = {
            "ok": bool(snap.get("ok")),
            "rows": len(snap.get("rows") or []),
            "pages_fetched": snap.get("pages_fetched") or 0,
            "error": snap.get("error") or "",
        }
    return {
        "generated_at": now_iso(),
        "pack_date": PACK_DATE,
        "generator": "analysis/evidence_pack_2026-07/generate_evidence_pack.py",
        "artifacts": artifacts,
        "stats": stats,
        "notion_snapshots": raw,
    }


def write_readme(out_dir: Path, manifest: dict[str, Any]) -> None:
    lines = [
        "# Evidence Pack 2026-07",
        "",
        f"Generated: {manifest['generated_at']}",
        "",
        "This pack is for Phase A Fable review. It ships the generator, raw Notion snapshots where available, CSV outputs, and one summary MD per artifact. Unknowns remain unknown.",
        "",
        "## Index",
        "",
    ]
    for name, meta in manifest["artifacts"].items():
        lines.append(f"- {name}: {meta['description']}")
        for path in meta["paths"]:
            lines.append(f"  - {path}")
    lines.extend([
        "",
        "## Raw Snapshots",
        "",
    ])
    for name, raw in manifest["notion_snapshots"].items():
        status = "ok" if raw["ok"] else "gap"
        detail = f"{raw['rows']} rows, {raw['pages_fetched']} pages" if raw["ok"] else raw["error"]
        lines.append(f"- {name}: {status} - {detail}")
    lines.extend([
        "",
        "## Reproduce",
        "",
        "From repo root:",
        "",
        "```powershell",
        "python analysis/evidence_pack_2026-07/generate_evidence_pack.py --repo-root . --out analysis/evidence_pack_2026-07",
        "```",
        "",
        "Set `NOTION_TOKEN` to refresh Notion snapshots. Without it, the script falls back to repo caches and writes named gaps.",
    ])
    write_md(out_dir / "README.md", lines)


def self_test() -> int:
    prop = {"type": "rich_text", "rich_text": [{"plain_text": "ABC"}, {"plain_text": " DEF"}]}
    assert notion_property_value(prop) == "ABC DEF"
    assert horizon_bucket(14) == "0-14d"
    assert horizon_bucket(30) == "15-30d"
    assert parse_date("2026-07-01T20:50:00.000-04:00") == date(2026, 7, 1)
    assert pct_return(100, 110) == 0.1
    known = {"NVDA", "SMH"}
    assert extract_tickers("Buy NVDA over SMH; AI is not ticker", known) == ["NVDA", "SMH"]
    return 0


def run(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    out_dir = (repo_root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    feed = read_json(repo_root / "src" / "latest_cockpit_feed.json", {}) or {}
    account_positions = read_json(repo_root / "src" / "account_positions.json", {}) or {}
    receipts = read_json(repo_root / "src" / "cloud_routine_receipts.json", {}) or {}
    automation_status = read_json(repo_root / "src" / "cloud_automation_status.json", {}) or {}
    top_prospects = read_json(repo_root / "src" / "top_prospects.json", {}) or {}
    research_queue = read_json(repo_root / "src" / "research_queue.json", {}) or {}
    source_calls_cache = read_json(repo_root / "src" / "source_calls.json", []) or []

    snapshots = fetch_notion_snapshots(repo_root, out_dir, skip=args.no_notion)
    source_calls, source_fetch_name = normalize_source_calls(snapshots.get("source_call_log") or {}, repo_root)
    decisions, decisions_fetch_name = normalize_decisions(snapshots.get("decisions_log") or {}, repo_root)
    known = build_known_tickers(feed, account_positions, top_prospects, research_queue, source_calls_cache, source_calls, decisions)
    price_ctx = build_price_context(repo_root, feed, account_positions)

    stats: dict[str, Any] = {}
    stats["source_hit_rates"] = generate_source_hit_rates(out_dir, source_calls, source_fetch_name)
    stats["decision_outcomes"] = generate_decision_outcomes(
        out_dir,
        decisions,
        decisions_fetch_name,
        known,
        price_ctx,
        feed,
        account_positions,
        top_prospects,
    )
    stats["missed_moves"] = generate_missed_moves(
        out_dir,
        repo_root=repo_root,
        notion_research_snapshot=snapshots.get("research_queue") or {},
        decisions=decisions,
        known_tickers=known,
        feed=feed,
        account_positions=account_positions,
        top_prospects=top_prospects,
        price_ctx=price_ctx,
    )
    stats["feed_reliability"] = generate_feed_reliability(out_dir, feed=feed, account_positions=account_positions)
    stats["routine_health"] = generate_routine_health(out_dir, receipts=receipts, automation_status=automation_status, feed=feed)
    stats["system_inventory"] = generate_system_inventory(out_dir, repo_root)

    manifest = build_manifest(out_dir, stats, snapshots)
    write_json(out_dir / "manifest.json", manifest)
    write_readme(out_dir, manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Investing OS Phase A evidence pack.")
    parser.add_argument("--repo-root", default=".", help="Repository root.")
    parser.add_argument("--out", default=str(DEFAULT_OUT_DIR), help="Output directory.")
    parser.add_argument("--no-notion", action="store_true", help="Do not fetch Notion REST snapshots.")
    parser.add_argument("--self-test", action="store_true", help="Run generator self-test only.")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    manifest = run(args)
    print(json.dumps({
        "generated_at": manifest["generated_at"],
        "out": str(Path(args.out)),
        "stats": manifest["stats"],
        "notion_snapshots": manifest["notion_snapshots"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
