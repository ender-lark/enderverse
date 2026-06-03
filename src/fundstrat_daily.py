"""Conviction Engine — the `fundstrat_daily` plug (Stage 1, S5).

Daily Fundstrat Inbox calls (Newton / Lee technicals + Farrell crypto) -> uniform
`kind="analyst_call"` fact-cards carrying each call VERBATIM plus its structured
price levels (entry / stop / target / window).

Per-author trust: Newton/Lee ride the plug default (0.70); Farrell is 0.65 — set
per-card via the BaseSource trust override, so ONE fundstrat_daily plug carries
both. All share group "fundstrat" (the echo-chamber bucket).

Boundary (Sources vs Analyst — RECORD): the verbatim call + its named levels are
mechanical -> plug. The plug does NOT tier the call (A/B/C/D), pre-register it for
scoring, or decide if it fits the book — that is P-SOURCE-CALIBRATION / the
Analyst. `direction` is the author's own word, not the plug's view.

Pure-logic + injectable: pass a list of structured `calls`; Collection's
Claude-read step parses the FS Inbox 7-day audit into that shape, tests use fakes.

Call shape (ticker required; everything else optional):
    {author, ticker, direction, entry, stop, target, window, quote, date}
"""
from __future__ import annotations

from datetime import datetime, timezone

from sources import BaseSource


# Authors whose calls deviate from the plug default trust (0.70).
AUTHOR_TRUST = {"farrell": 0.65}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fmt_levels(entry, stop, target, window) -> str:
    parts = []
    if entry is not None:
        parts.append(f"entry {entry}")
    if stop is not None:
        parts.append(f"stop {stop}")
    if target is not None:
        parts.append(f"tgt {target}")
    if window:
        parts.append(str(window))
    return ", ".join(parts)


def fundstrat_daily_reader(calls, as_of: str | None = None) -> list[dict]:
    """One analyst_call card per named daily call.

    content = the verbatim quote when present (the fact); otherwise a templated
    line from the structured fields. Calls without a ticker are skipped (these
    are named, ticker-level calls). Farrell calls carry a per-card 0.65 trust.
    """
    rows: list[dict] = []
    for c in calls or []:
        ticker = c.get("ticker")
        if not ticker:
            continue
        author = c.get("author") or "FS"
        direction = c.get("direction")
        quote = c.get("quote")
        entry, stop, target, window = (
            c.get("entry"), c.get("stop"), c.get("target"), c.get("window"))
        levels = _fmt_levels(entry, stop, target, window)

        if quote:
            content = quote
        else:
            head = f"{author}: " + (f"{direction} " if direction else "") + ticker
            content = head + (f" ({levels})" if levels else "")

        ts = c.get("date") or as_of or _utc_now_iso()
        row = {
            "kind": "analyst_call", "subject": ticker, "content": content,
            "timestamp": ts,
            "data": {
                "author": author, "ticker": ticker, "direction": direction,
                "entry": entry, "stop": stop, "target": target, "window": window,
                "verbatim": quote or content,
            },
        }
        # per-author trust override (Farrell 0.65); others fall to plug default
        tw = AUTHOR_TRUST.get((author or "").lower())
        if tw is not None:
            row["trust_weight"] = tw
        rows.append(row)

    return rows


def build_fundstrat_daily_source(
    calls, name: str = "fundstrat_daily", **reader_kwargs
) -> BaseSource:
    """Wire the daily-calls reader into the uniform `fundstrat_daily` plug
    (default trust 0.70, group fundstrat; Farrell cards self-override to 0.65)."""
    def fetcher() -> list[dict]:
        return fundstrat_daily_reader(calls, **reader_kwargs)

    return BaseSource(name=name, fetcher=fetcher)
