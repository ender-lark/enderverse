"""Data health: is each input fresh, behind, or empty?

Produces plain-English, self-labeling chips for the decision surface and a
``blockers`` list that downgrades card verdicts to "CHECK DATA FIRST" when the
inputs a verdict relies on are stale, behind, or missing.

Design (operator-approved 2026-06-11):
- Staleness is NOT a rigid timer. Two questions, worst answer wins:
  1. "Are we behind?"  -> unread newer info from the source (``fs_unread``)
     or age beyond the source's own publishing rhythm (``CADENCE_DAYS``,
     defaults only).
  2. "Is this item past its own shelf life?" -> a per-item ``relevant_until``
     written at filing time by whoever ingested it (judgment from content).
     When present it OVERRIDES the cadence default.
- Empty sources never block; they ANNOUNCE ("no graded calls yet").
- Honest absence: an input that was never checked says "not checked", never
  "all clear".
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

SRC = Path(__file__).resolve().parent

# Default publishing rhythm per source, in days. These are FALLBACKS only;
# a per-item ``relevant_until`` (judgment at filing time) always wins.
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

# Severity ranks: 0 announce-fresh, 1 announce-soft, 2 blocker.
_RANK = {"fresh": 0, "not_checked": 1, "aging": 1, "empty": 1, "behind": 2, "stale": 2, "missing": 2}
_BLOCK_RANK = 2


def _parse_date(s: str) -> dt.date | None:
    s = str(s or "")[:10]
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def _age_days(date_str: str, now: dt.date) -> float | None:
    d = _parse_date(date_str)
    if d is None:
        return None
    return float((now - d).days)


def _item(source: str, label: str, status: str, detail: str) -> dict[str, Any]:
    return {"source": source, "label": label, "status": status, "detail": detail}



# ---------------------------------------------------------------------------
# Shelf-life store: judgments written AT FILING TIME (slice 2).
# Whoever reads a note (Claude in-session, a cloud routine via receipt+commit)
# records what window the note's CONTENT actually covers. The dashboard then
# trusts that judgment instead of the cadence fallback.
# ---------------------------------------------------------------------------
SHELF_PATH = SRC / "source_shelf_life.json"


def load_shelf_life(path: Path | str = SHELF_PATH) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return d if isinstance(d, dict) else {}


def record_shelf_life(source: str, relevant_until: str, basis: str = "", *,
                      path: Path | str = SHELF_PATH,
                      filed_at: str | None = None) -> dict[str, Any]:
    """Record a content-judged relevance window for a source.

    ``relevant_until`` must be YYYY-MM-DD. ``basis`` is the one-line plain-
    English reason (e.g. "Newton 6/10: 'lower into next week'"). Returns the
    stored record."""
    d = _parse_date(relevant_until)
    if d is None:
        raise ValueError(f"relevant_until must be YYYY-MM-DD, got {relevant_until!r}")
    data = load_shelf_life(path)
    data[str(source)] = {
        "relevant_until": d.isoformat(),
        "basis": str(basis),
        "filed_at": filed_at or dt.date.today().isoformat(),
    }
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data[str(source)]

def assess(
    feed: dict[str, Any],
    *,
    gates: list[dict[str, Any]] | None = None,
    now: dt.date | None = None,
    rates_path: Path | str | None = None,
    shelf_path: Path | str | None = None,
) -> dict[str, Any]:
    """Assess every known input the decision surface relies on.

    Returns ``{"items": [...], "worst": str, "blockers": [labels]}``.
    Unknown sources are skipped (never guessed at).
    """
    today = now or dt.date.today()
    items: list[dict[str, Any]] = []

    # --- staleness entries from the feed -----------------------------------
    shelf = load_shelf_life(shelf_path if shelf_path is not None else SHELF_PATH)
    entries = (feed.get("staleness") or {}).get("entries") or []
    for e in entries:
        src = str(e.get("source") or "")
        cad = CADENCE_DAYS.get(src)
        if cad is None:
            continue  # unknown source: do not guess a rhythm for it
        label = LABELS.get(src, src)
        ru = e.get("relevant_until") or (shelf.get(src) or {}).get("relevant_until")
        if ru:
            ru_d = _parse_date(str(ru))
            if ru_d is None:
                items.append(_item(src, label, "aging", f"shelf-life unreadable ({ru})"))
            elif today <= ru_d:
                items.append(_item(src, label, "fresh", f"covers through {ru_d.isoformat()}"))
            else:
                items.append(_item(src, label, "stale", f"covered only through {ru_d.isoformat()}"))
            continue
        age = _age_days(str(e.get("date") or ""), today)
        if age is None:
            items.append(_item(src, label, "missing", "no date on record"))
        elif age <= cad:
            items.append(_item(src, label, "fresh", f"{str(e.get('date'))[:10]}"))
        elif age <= 2 * cad:
            items.append(_item(src, label, "aging", f"{age:.0f}d old"))
        else:
            items.append(_item(src, label, "stale", f"{age:.0f}d old"))

    # --- timing gates --------------------------------------------------------
    for g in gates or []:
        sym = str(g.get("symbol") or g.get("gate_id") or "gate")
        age = _age_days(str(g.get("stated") or ""), today)
        if age is None:
            items.append(_item("gates", f"{sym} gate", "missing", "no as-of date"))
        elif age <= GATE_CADENCE_DAYS:
            items.append(_item("gates", f"{sym} gate", "fresh", f"as of {str(g.get('stated'))[:10]}"))
        else:
            items.append(_item("gates", f"{sym} gate", "stale", f"stated {age:.0f}d ago - reconfirm"))

    # --- unread analyst notes (the 6/11 failure) -----------------------------
    fu = feed.get("fs_unread")
    if fu is None:
        items.append(_item("fs_inbox", "FS inbox", "not_checked", "not checked this render"))
    else:
        count = int(fu.get("count") or 0)
        checked = str(fu.get("checked_at") or "")[:16]
        if count > 0:
            items.append(_item("fs_inbox", "FS inbox", "behind",
                               f"{count} newer notes unread (checked {checked})"))
        else:
            items.append(_item("fs_inbox", "FS inbox", "fresh", f"all notes read (checked {checked})"))

    # --- analyst track record: empty announces, never blocks -----------------
    rp = Path(rates_path) if rates_path is not None else SRC / "source_rates.json"
    if not rp.exists():
        items.append(_item("track_record", "analyst track record", "missing",
                           "hit-rate file absent"))
    else:
        try:
            rates = json.loads(rp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            rates = None
        if not isinstance(rates, dict):
            items.append(_item("track_record", "analyst track record", "missing", "unreadable"))
        else:
            scored = 0
            for src_name, tiers in rates.items():
                if not isinstance(tiers, dict):
                    continue
                for t in tiers.values():
                    if isinstance(t, dict):
                        scored += int(t.get("n") or 0)
            if scored == 0:
                items.append(_item("track_record", "analyst track record", "empty",
                                   "no graded calls yet - cannot score any source"))
            else:
                items.append(_item("track_record", "analyst track record", "fresh",
                                   f"{scored} graded calls"))

    # ``missing`` on track record is announce-only, same as empty.
    blockers = [it["label"] for it in items
                if _RANK.get(it["status"], 1) >= _BLOCK_RANK and it["source"] != "track_record"]
    ranks = [_RANK.get(it["status"], 1) if it["source"] != "track_record"
             else min(_RANK.get(it["status"], 1), 1)
             for it in items] or [0]
    worst_rank = max(ranks)
    worst = {0: "fresh", 1: "announce", 2: "blocked"}[worst_rank]
    return {"items": items, "worst": worst, "blockers": blockers}
