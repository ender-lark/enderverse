"""Data health: is each decision input fresh, behind, or empty?

The decision surface uses this to downgrade cards to "CHECK DATA FIRST" when
an input it relies on is stale, behind, or missing. Staleness is judged from
source cadence plus any content-specific shelf-life recorded at filing time.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

SRC = Path(__file__).resolve().parent
SHELF_PATH = SRC / "source_shelf_life.json"

CADENCE_DAYS: dict[str, float] = {
    "portfolio": 1.6,
    "uw_price": 1.6,
    "uw_macro": 1.6,
    "live_tape": 1.0,
    "fundstrat_daily": 1.6,
    "fundstrat_bible": 35.0,
}
GATE_CADENCE_DAYS = 4.0

LABELS: dict[str, str] = {
    "portfolio": "positions",
    "uw_price": "prices",
    "uw_macro": "macro",
    "live_tape": "live tape",
    "fundstrat_daily": "analyst daily notes",
    "fundstrat_bible": "analyst monthly",
}

_RANK = {
    "fresh": 0,
    "not_checked": 1,
    "aging": 1,
    "empty": 1,
    "context": 1,
    "behind": 2,
    "stale": 2,
    "missing": 2,
}
_BLOCK_RANK = 2


def _parse_date(value: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _age_days(value: str, now: dt.date) -> float | None:
    parsed = _parse_date(value)
    if parsed is None:
        return None
    return float((now - parsed).days)


def _item(
    source: str,
    label: str,
    status: str,
    detail: str,
    *,
    blocks: bool | None = None,
    **extra: Any,
) -> dict[str, Any]:
    row = {"source": source, "label": label, "status": status, "detail": detail}
    if blocks is not None:
        row["blocks"] = blocks
    row.update(extra)
    return row


def _gate_blocks_action(gate: dict[str, Any]) -> bool:
    if "blocks" in gate:
        return bool(gate.get("blocks"))
    if "blocks_full_size" in gate:
        return bool(gate.get("blocks_full_size"))
    kind = str(gate.get("kind") or "").lower()
    gate_type = str(gate.get("gate_type") or gate.get("confirm_type") or "").lower()
    state = str(gate.get("state") or "").lower()
    if "context" in {kind, gate_type, state}:
        return False
    text = " ".join(
        str(gate.get(key) or "").lower()
        for key in ("note", "confirm_rule", "status")
    )
    if "never blocks" in text or "context only" in text:
        return False
    if "stage-only" in text or "stage only" in text:
        return False
    return True


def _blocks_item(item: dict[str, Any]) -> bool:
    if "blocks" in item:
        return bool(item.get("blocks"))
    if item.get("source") == "track_record":
        return False
    return _RANK.get(item.get("status"), 1) >= _BLOCK_RANK


def _rank_item(item: dict[str, Any]) -> int:
    rank = _RANK.get(item.get("status"), 1)
    if not _blocks_item(item):
        return min(rank, 1)
    return rank


def load_shelf_life(path: Path | str = SHELF_PATH) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def record_shelf_life(
    source: str,
    relevant_until: str,
    basis: str = "",
    *,
    path: Path | str = SHELF_PATH,
    filed_at: str | None = None,
) -> dict[str, Any]:
    parsed = _parse_date(relevant_until)
    if parsed is None:
        raise ValueError(f"relevant_until must be YYYY-MM-DD, got {relevant_until!r}")
    payload = load_shelf_life(path)
    payload[str(source)] = {
        "relevant_until": parsed.isoformat(),
        "basis": str(basis),
        "filed_at": filed_at or dt.date.today().isoformat(),
    }
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload[str(source)]


def assess(
    feed: dict[str, Any],
    *,
    gates: list[dict[str, Any]] | None = None,
    now: dt.date | None = None,
    rates_path: Path | str | None = None,
    shelf_path: Path | str | None = None,
) -> dict[str, Any]:
    today = now or dt.date.today()
    items: list[dict[str, Any]] = []

    shelf = load_shelf_life(shelf_path if shelf_path is not None else SHELF_PATH)
    entries = (feed.get("staleness") or {}).get("entries") or []
    for entry in entries:
        source = str(entry.get("source") or "")
        cadence = CADENCE_DAYS.get(source)
        if cadence is None:
            continue
        label = LABELS.get(source, source)
        relevant_until = entry.get("relevant_until") or (shelf.get(source) or {}).get("relevant_until")
        if relevant_until:
            relevant_date = _parse_date(str(relevant_until))
            if relevant_date is None:
                items.append(_item(source, label, "aging", f"shelf-life unreadable ({relevant_until})"))
            elif today <= relevant_date:
                items.append(_item(source, label, "fresh", f"covers through {relevant_date.isoformat()}"))
            else:
                items.append(_item(source, label, "stale", f"covered only through {relevant_date.isoformat()}"))
            continue

        age = _age_days(str(entry.get("date") or ""), today)
        if age is None:
            items.append(_item(source, label, "missing", "no date on record"))
        elif age <= cadence:
            items.append(_item(source, label, "fresh", str(entry.get("date"))[:10]))
        elif age <= 2 * cadence:
            items.append(_item(source, label, "aging", f"{age:.0f}d old"))
        else:
            items.append(_item(source, label, "stale", f"{age:.0f}d old"))

    for gate in gates or []:
        symbol = str(gate.get("symbol") or gate.get("gate_id") or "gate")
        gate_id = str(gate.get("gate_id") or "")
        blocks = _gate_blocks_action(gate)
        age = _age_days(str(gate.get("stated") or ""), today)
        if age is None:
            status = "missing" if blocks else "context"
            detail = "no as-of date" if blocks else "context gate has no as-of date"
            items.append(_item("gates", f"{symbol} gate", status, detail, blocks=blocks, symbol=symbol, gate_id=gate_id))
        elif age <= GATE_CADENCE_DAYS:
            items.append(_item("gates", f"{symbol} gate", "fresh", f"as of {str(gate.get('stated'))[:10]}", blocks=False, symbol=symbol, gate_id=gate_id))
        else:
            if blocks:
                items.append(_item("gates", f"{symbol} gate", "stale", f"stated {age:.0f}d ago - reconfirm", blocks=True, symbol=symbol, gate_id=gate_id))
            else:
                items.append(_item("gates", f"{symbol} gate", "context", f"stated {age:.0f}d ago - context only; reconfirm for awareness", blocks=False, symbol=symbol, gate_id=gate_id))

    fs_unread = feed.get("fs_unread")
    if fs_unread is None:
        items.append(_item("fs_inbox", "FS inbox", "not_checked", "not checked this render"))
    else:
        count = int(fs_unread.get("count") or 0)
        checked = str(fs_unread.get("checked_at") or "")[:16]
        if count > 0:
            items.append(_item("fs_inbox", "FS inbox", "behind", f"{count} newer notes unread (checked {checked})"))
        else:
            items.append(_item("fs_inbox", "FS inbox", "fresh", f"all notes read (checked {checked})"))

    rates = Path(rates_path) if rates_path is not None else SRC / "source_rates.json"
    if not rates.exists():
        items.append(_item("track_record", "analyst track record", "missing", "hit-rate file absent"))
    else:
        try:
            rates_payload = json.loads(rates.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            rates_payload = None
        if not isinstance(rates_payload, dict):
            items.append(_item("track_record", "analyst track record", "missing", "unreadable"))
        else:
            scored = 0
            for tiers in rates_payload.values():
                if not isinstance(tiers, dict):
                    continue
                for tier in tiers.values():
                    if isinstance(tier, dict):
                        scored += int(tier.get("n") or 0)
            if scored == 0:
                items.append(_item("track_record", "analyst track record", "empty", "no graded calls yet - cannot score any source"))
            else:
                items.append(_item("track_record", "analyst track record", "fresh", f"{scored} graded calls"))

    for item in items:
        item.setdefault("blocks", _blocks_item(item))

    blockers = [item["label"] for item in items if _blocks_item(item)]
    ranks = [_rank_item(item) for item in items] or [0]
    return {"items": items, "worst": {0: "fresh", 1: "announce", 2: "blocked"}[max(ranks)], "blockers": blockers}
