"""Conviction Engine — the `fundstrat_bible` plug (Stage 1, S4).

The first plug whose raw material is Claude-read PROSE (the monthly Fundstrat
deck) rather than numbers. To keep it pure-logic and testable, the plug takes a
**pre-structured deck dict** — the READ-FIRST summary off the FS Bible pointer
page, parsed by the Claude-read step in Collection — and emits uniform fact-cards
carrying the deck's content VERBATIM:
  - macro stance        -> kind="stance"
  - What-to-Own sectors -> kind="what_to_own"  (one card per sector)
  - Top-5 / Bottom-5    -> kind="analyst_call"  (one card per ticker)

Boundary (Sources vs Analyst — RECORD): verbatim stance text + list membership
are MECHANICAL, so they belong to the plug. The plug does NOT decide whether a
pick fits the book, whether Bottom-5 means "trim", or how to weight Lee vs the
tape — that judgment is the Analyst. In particular `direction` here is just which
LIST a ticker came from (the deck's own framing); per the CI, Bottom-5 is a
funding-source flag, NOT a sell signal — the Analyst makes that call.

Pure-logic + injectable: pass a `deck` dict; in production Collection supplies it
from the live pointer-page read, in tests a fake dict. Trust 0.70, group
fundstrat (all FS plugs share ONE echo-chamber group via the dials).

Deck shape (every section optional; missing -> no cards, never faked):
    {
      "deck_date": "2026-05",
      "macro_stance": "..."  | ["bullet", "bullet"],     # verbatim
      "what_to_own": ["Technology", {"sector": "...", "note": "..."}],
      "top5":    ["NVDA", {"ticker": "GOOGL", "note": "..."}],
      "bottom5": ["XYZ", ...],
    }
"""
from __future__ import annotations

from datetime import datetime, timezone

from sources import BaseSource


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _name_note(item, key: str):
    """Accept a bare string or a {key, note} dict -> (name, note)."""
    if isinstance(item, dict):
        return item.get(key), item.get("note")
    return item, None


def fundstrat_bible_reader(deck: dict, as_of: str | None = None) -> list[dict]:
    """One verbatim fact-card per stance bullet, What-to-Own sector, and
    Top-5 / Bottom-5 ticker present in `deck`."""
    ts = as_of or deck.get("deck_date") or _utc_now_iso()
    rows: list[dict] = []

    # --- macro stance (str or list of str) ---
    stance = deck.get("macro_stance")
    stance_items = [stance] if isinstance(stance, str) else (stance or [])
    for s in stance_items:
        if not s:
            continue
        rows.append({
            "kind": "stance", "subject": "macro stance", "content": s,
            "timestamp": ts, "data": {"verbatim": s},
        })

    # --- What-to-Own sectors (one card each) ---
    for sec in (deck.get("what_to_own") or []):
        name, note = _name_note(sec, "sector")
        if not name:
            continue
        rows.append({
            "kind": "what_to_own", "subject": name,
            "content": f"FS What-to-Own: {name}", "timestamp": ts,
            "data": {"sector": name, "note": note, "verbatim": name},
        })

    # --- Top-5 / Bottom-5 (one analyst_call card per ticker) ---
    for list_name, label, direction in (
        ("top5", "FS Top-5", "favored"),
        ("bottom5", "FS Bottom-5", "unfavored"),
    ):
        for i, item in enumerate(deck.get(list_name) or [], start=1):
            ticker, note = _name_note(item, "ticker")
            if not ticker:
                continue
            content = f"{label}: {ticker}" + (f" — {note}" if note else "")
            rows.append({
                "kind": "analyst_call", "subject": ticker, "content": content,
                "timestamp": ts,
                "data": {
                    "ticker": ticker, "list": list_name, "direction": direction,
                    "rank": i, "note": note, "verbatim": note or ticker,
                },
            })

    return rows


def build_fundstrat_bible_source(
    deck: dict, name: str = "fundstrat_bible", **reader_kwargs
) -> BaseSource:
    """Wire the deck reader into the uniform `fundstrat_bible` plug
    (trust 0.70, group fundstrat via the dials)."""
    def fetcher() -> list[dict]:
        return fundstrat_bible_reader(deck, **reader_kwargs)

    return BaseSource(name=name, fetcher=fetcher)
