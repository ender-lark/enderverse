"""Conviction Engine — the `portfolio` plug (Stage 1, S7).

The canonical book (📊 Latest Portfolio) -> uniform `kind="position"` fact-cards,
one per holding. Trust 0.95, group own, cadence "on_refresh" (it updates when
broker PDFs are uploaded — NOT a daily feed, so the staleness read budgets it
accordingly; the #PORTFOLIO-READ-LEAD rule separately flags a >7-day-old refresh).

The Analyst reconstructs the book by filtering `kind="position"` (the P3 decision:
portfolio rides the uniform rails as a plug, not a separate snapshot field).

Boundary (Sources vs Analyst — RECORD): the plug emits the holdings as-is
(ticker, %, shares, value, account, owner, sleeve). It does NOT judge
concentration, sizing, or what to trim — that is the Analyst.

Pure-logic + injectable: pass parsed positions (the portfolio-pdf-extractor /
Latest Portfolio read output); tests use fakes.

Position shape (ticker required; `pct` in PERCENT units, e.g. 9.9 == 9.90%):
    {ticker, pct, shares, value, account, owner, sleeve}
One card per position item at whatever granularity the input provides (already
aggregated per-ticker, or per-account holdings — the plug maps 1:1; the Analyst
aggregates).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sources import BaseSource


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def portfolio_reader(positions, as_of: str | None = None) -> list[dict]:
    """One position card per holding. Ticker-less items are skipped (no fake
    rows). `pct` is rendered as e.g. "SMH 9.90% Owned"; absent pct -> "SMH Owned".
    """
    ts = as_of or _utc_now_iso()
    rows: list[dict] = []
    for p in positions or []:
        ticker = p.get("ticker")
        if not ticker:
            continue
        pct = p.get("pct")
        content = f"{ticker} {pct:.2f}% Owned" if pct is not None else f"{ticker} Owned"
        rows.append({
            "kind": "position", "subject": ticker, "content": content,
            "timestamp": ts,
            "data": {
                "ticker": ticker, "pct": pct, "shares": p.get("shares"),
                "value": p.get("value"), "account": p.get("account"),
                "owner": p.get("owner"), "sleeve": p.get("sleeve"),
            },
        })
    return rows


def build_portfolio_source(
    positions, name: str = "portfolio", **reader_kwargs
) -> BaseSource:
    """Wire the book reader into the uniform `portfolio` plug
    (trust 0.95, group own, cadence on_refresh via the dials)."""
    def fetcher() -> list[dict]:
        return portfolio_reader(positions, **reader_kwargs)

    return BaseSource(name=name, fetcher=fetcher)
