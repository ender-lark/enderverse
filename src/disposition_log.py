#!/usr/bin/env python3
"""Disposition log spine (Task 3).

Append-only JSONL tracking for TODAY decisions and utility readers for
open-cards, orphan escalation, action-memory mapping, and 30-day lookback joins.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from open_opportunities import age_business_days
from prospect_performance import compute_performance as _compute_performance
from tunables import load_goal_tunables
from top_prospects_feeder import CACHE_PATH as TOP_PROSPECTS_CACHE_PATH

SRC = Path(__file__).resolve().parent
DISPOSITIONS_PATH = SRC / "dispositions.jsonl"

VALID_VERBS = {"ACT", "PASS", "RECHECK", "UNDO"}
REASON_REQUIRED_VERBS = {"PASS"}


def _parse_iso_date(value: str | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if not str(value).strip():
        return None
    raw = str(value).strip()
    if "T" in raw:
        raw = raw.split("T", 1)[0]
    try:
        return date.fromisoformat(raw)
    except Exception:
        return None


def _today(value: str | date | None) -> str:
    if value is None:
        return date.today().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    parsed = _parse_iso_date(str(value))
    return parsed.isoformat() if parsed else str(value).strip()


def _clean_str(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def append_disposition(
    et_date: str,
    card_id: str,
    ticker: str,
    verb: str,
    reason: str | None = None,
    *,
    source: str = "chat",
    resurface_date: str | None = None,
    recheck_default_days: int = 5,
    path: Path | str = DISPOSITIONS_PATH,
) -> dict[str, Any]:
    """Append one immutable disposition row.

    APPEND ONLY: all rows are appended as newline JSON objects.
    `PASS` requires a non-empty reason.
    `UNDO` is a valid verb and carries no reason requirement.
    """
    verb_u = _clean_str(verb).upper()
    if verb_u not in VALID_VERBS:
        raise ValueError(f"unsupported disposition verb: {verb_u!r}")
    if verb_u in REASON_REQUIRED_VERBS and not _clean_str(reason):
        raise ValueError("reason is required for PASS")

    et_day = _parse_iso_date(et_date) or date.today()
    et = et_day.isoformat()
    row: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "et_date": et,
        "card_id": _clean_str(card_id),
        "ticker": _clean_str(ticker).upper(),
        "verb": verb_u,
        "source": _clean_str(source) or "chat",
    }
    if reason:
        row["reason"] = _clean_str(reason)
    if verb_u == "RECHECK":
        row["resurface_date"] = _today(
            resurface_date
            or (et_day + timedelta(days=int(recheck_default_days))).isoformat()
        )
    out = Path(path)
    parent = out.parent
    if parent and not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)
    with open(out, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")
    return row


def _parse_dispositions(path: Path | str = DISPOSITIONS_PATH) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    p = Path(path)
    if not p.exists():
        return out
    for raw in p.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except Exception:
            continue
        if not isinstance(row, dict):
            continue
        row["verb"] = _clean_str(row.get("verb")).upper()
        out.append(row)
    return out


def last_dispositions(path: Path | str = DISPOSITIONS_PATH) -> dict[str, dict[str, Any]]:
    """Latest disposition per card."""
    out: dict[str, dict[str, Any]] = {}
    for row in _parse_dispositions(path):
        card = _clean_str(row.get("card_id"))
        if card:
            out[card] = row
    return out


def load_open_cards(cards: list[dict[str, Any]], *, dispositions: list[dict[str, Any]] | None = None,
                   path: Path | str = DISPOSITIONS_PATH) -> list[dict[str, Any]]:
    """Return cards whose latest disposition is none or UNDO."""
    latest = {}
    rows = dispositions if dispositions is not None else _parse_dispositions(path)
    for row in rows:
        card = _clean_str(row.get("card_id"))
        if card:
            latest[card] = row
    out: list[dict[str, Any]] = []
    for card in cards:
        cid = _clean_str(card.get("card_id"))
        if not cid:
            continue
        last = latest.get(cid, {})
        v = _clean_str(last.get("verb")).upper()
        if v in ("", "UNDO"):
            out.append(card)
    return out


def orphan_escalation(
    cards: list[dict[str, Any]],
    *,
    as_of: str | None = None,
    tunables: dict[str, Any] | None = None,
    first_flagged_key: str = "first_flagged",
    path: Path | str = DISPOSITIONS_PATH,
) -> list[dict[str, Any]]:
    """Tag orphan cards with escalation/pin state from trading-day age."""
    del path  # path reserved for Task-3 compatibility; kept for future extensibility
    t = tunables if tunables is not None else load_goal_tunables()
    escalate_after = int(t.get("orphan_escalate_days", 0))
    pin_after = int(t.get("orphan_pin_days", 0))
    as_of_iso = _today(as_of)
    out = []
    for row in cards:
        next_row = dict(row)
        first = _clean_str(row.get(first_flagged_key))
        days = age_business_days(first, as_of_iso) if first else None
        next_row["orphan_age_days"] = days
        if days is None:
            next_row["orphan_state"] = "open"
        elif days >= pin_after and pin_after:
            next_row["orphan_state"] = "pin"
        elif days >= escalate_after and escalate_after:
            next_row["orphan_state"] = "escalate"
        else:
            next_row["orphan_state"] = "open"
        out.append(next_row)
    return out


def map_to_action_memory(verb: str) -> str | None:
    """Map disposition verbs to action-memory status labels."""
    return {
        "ACT": "acted",
        "PASS": "ignored",
        "RECHECK": "deferred",
    }.get(_clean_str(verb).upper())


def _load_top_prospects(path: Path | str = TOP_PROSPECTS_CACHE_PATH) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def lookback_30d(
    path: Path | str = DISPOSITIONS_PATH,
    *,
    as_of: str | None = None,
    price_fn: Callable[[str, str | None], float | None] | None = None,
    top_prospects_path: Path | str = TOP_PROSPECTS_CACHE_PATH,
    tunables_path: Path | str | None = None,
    window_days: int | None = None,
) -> list[dict[str, Any]]:
    """Collect ACT/PASS dispositions with add-date performance snapshots.

    Returns one row per matching disposition within the lookback window.
    """
    try:
        t = load_goal_tunables(path=tunables_path) if tunables_path else load_goal_tunables()
    except Exception:
        t = {}
    lookback = int(window_days if window_days is not None else t.get("disposition_review_days", 30))
    today = _today(as_of)
    as_of_day = _parse_iso_date(today) or date.today()
    cache = _load_top_prospects(top_prospects_path)
    rows = _parse_dispositions(path)
    out: list[dict[str, Any]] = []
    if price_fn is None:
        price_fn = lambda _ticker, _date=None: None

    spy_current = price_fn("SPY")
    spy_hist: dict[str, float | None] = {}

    def _spy_at(d: str | None) -> float | None:
        if not d:
            return None
        if d not in spy_hist:
            spy_hist[d] = price_fn("SPY", d)
        return spy_hist[d]

    for row in rows:
        verb = _clean_str(row.get("verb")).upper()
        if verb not in {"ACT", "PASS"}:
            continue
        et = _clean_str(row.get("et_date"))
        if not et:
            continue
        try:
            if (as_of_day - date.fromisoformat(et)).days > lookback:
                continue
        except Exception:
            continue
        tk = _clean_str(row.get("ticker")).upper()
        if not tk:
            continue
        rec = cache.get(tk, {})
        if not isinstance(rec, dict):
            continue
        add_price = rec.get("add_price")
        add_date = rec.get("add_date")
        try:
            add_price_f = float(add_price) if add_price is not None else None
        except (TypeError, ValueError):
            add_price_f = None
        if add_price_f is None or not add_date:
            continue
        try:
            current = price_fn(tk)
            perf = _compute_performance(
                add_price=add_price_f,
                current_price=current,
                spy_at_add=_spy_at(add_date),
                spy_current=spy_current,
                add_date=add_date,
                today=today,
            )
            out.append({
                "ticker": tk,
                "card_id": _clean_str(row.get("card_id")),
                "verb": verb,
                "status": map_to_action_memory(verb),
                "et_date": et,
                "reason": row.get("reason"),
                "add_price": add_price,
                "pct_since_add": perf.get("pct_since_add"),
                "pct_vs_spy": perf.get("pct_vs_spy"),
            })
        except Exception:
            out.append({
                "ticker": tk,
                "card_id": _clean_str(row.get("card_id")),
                "verb": verb,
                "status": map_to_action_memory(verb),
                "et_date": et,
                "reason": row.get("reason"),
                "add_price": add_price,
                "pct_since_add": None,
                "pct_vs_spy": None,
            })
    return out
