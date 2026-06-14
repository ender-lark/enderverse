"""Conviction Engine — the `fundstrat_bible` plug (Stage 1, S4).

The monthly Fundstrat update arrives as a direct PDF/text/JSON upload and is
first reduced by `fundstrat_bible_intake.py` into a compact deck dict. To keep
this plug pure-logic and testable, it accepts that **pre-structured deck dict**
and emits uniform fact-cards carrying the deck's useful content VERBATIM:
  - macro stance        -> kind="stance"
  - What-to-Own sectors -> kind="what_to_own"  (one card per sector)
  - Top-5 / Bottom-5    -> kind="analyst_call"  (one card per ticker)
    Large-cap keys use top5/bottom5; SMID keys use top5_smid/bottom5_smid.
  - sector tactical 3x3 -> kind="sector_stance" (one card per sector)
  - named levels        -> kind="named_level" (one card per level)

Boundary (Sources vs Analyst — RECORD): verbatim stance text + list membership
are MECHANICAL, so they belong to the plug. The plug does NOT decide whether a
pick fits the book, whether Bottom-5 means "trim", or how to weight Lee vs the
tape — that judgment is the Analyst. In particular `direction` here is just which
LIST a ticker came from (the deck's own framing); per the CI, Bottom-5 is a
funding-source flag, NOT a sell signal — the Analyst makes that call.

Pure-logic + injectable: pass a `deck` dict; in production the full build loads
`fundstrat_bible.json`, in tests a fake dict. Trust 0.70, group
fundstrat (all FS plugs share ONE echo-chamber group via the dials).

Deck shape (every section optional; missing -> no cards, never faked):
    {
      "deck_date": "2026-05",
      "macro_stance": "..."  | ["bullet", "bullet"],     # verbatim
      "what_to_own": ["Technology", {"sector": "...", "note": "..."}],
      "top5":    ["NVDA", {"ticker": "GOOGL", "note": "..."}],
      "bottom5": ["XYZ", ...],
      "top5_smid": ["STRL", ...],
      "bottom5_smid": ["ELF", ...],
      "sector_allocation": {
          "tactical_top3": [{"sector": "Health Care", "ticker": "XLV"}],
          "tactical_bottom3": [{"sector": "Energy", "ticker": "XLE"}],
          "named_levels": [{"ticker": "EWRE", "condition": "weekly close above", "level": 38}],
      },
    }
"""
from __future__ import annotations

from datetime import datetime, timezone

import fundstrat_sector_stances as sector_stances
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
        ("top5_smid", "FS Top-5 SMID", "favored"),
        ("bottom5_smid", "FS Bottom-5 SMID", "unfavored"),
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

    # --- Sector tactical top/bottom and named levels (June allocation layer) ---
    for list_name, label, direction, items in (
        ("tactical_top3", "FS Tactical Top-3", "favored", sector_stances.tactical_top3(deck)),
        ("tactical_bottom3", "FS Tactical Bottom-3", "unfavored", sector_stances.tactical_bottom3(deck)),
    ):
        for i, item in enumerate(items, start=1):
            sector = str(item.get("sector") or "").strip()
            ticker = str(item.get("ticker") or "").strip().upper()
            if not sector:
                continue
            adjustment = item.get("weight_adjustment_pct")
            adjustment_text = f" ({adjustment:+g}%)" if isinstance(adjustment, (int, float)) else ""
            content = f"{label}: {sector}{f' / {ticker}' if ticker else ''}{adjustment_text}"
            rows.append({
                "kind": "sector_stance",
                "subject": ticker or sector,
                "content": content,
                "timestamp": ts,
                "data": {
                    "sector": sector,
                    "ticker": ticker,
                    "list": list_name,
                    "direction": direction,
                    "rank": item.get("rank") or i,
                    "weight_adjustment_pct": adjustment,
                    "current_weight_pct": item.get("current_weight_pct"),
                    "vs_index_pct": item.get("vs_index_pct"),
                    "note": item.get("why") or "",
                    "verbatim": item.get("why") or sector,
                },
            })

    for item in sector_stances.named_levels(deck):
        ticker = str(item.get("ticker") or "").strip().upper()
        condition = str(item.get("condition") or "").strip()
        level = item.get("level")
        unit = str(item.get("unit") or "").strip()
        target = str(item.get("target") or "").strip()
        if not ticker or not condition or level in (None, ""):
            continue
        if unit.upper() == "USD":
            level_text = f"${float(level):g}"
        else:
            level_text = f"{level:g}" if isinstance(level, (int, float)) else str(level)
        content = f"FS named level: {ticker} {condition} {level_text}"
        if target:
            content += f" -> {target}"
        rows.append({
            "kind": "named_level",
            "subject": ticker,
            "content": content,
            "timestamp": ts,
            "data": {
                "ticker": ticker,
                "asset": item.get("asset") or "",
                "condition": condition,
                "level": level,
                "unit": unit,
                "target": target,
                "note": item.get("why") or "",
                "verbatim": item.get("why") or content,
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
