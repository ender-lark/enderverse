"""ETF wrapper look-through disclosures for decision cards.

This is display-only decision context. It never changes card ranking, sizing,
or account routing.
"""
from __future__ import annotations

from typing import Any


WRAPPER_LOOKTHROUGH: dict[str, dict[str, Any]] = {
    "SMH": {
        "source": "VanEck daily holdings as of 2026-06-11",
        "holdings": {
            "NVDA": 0.1451,
            "TSM": 0.0927,
            "MU": 0.0783,
            "INTC": 0.0722,
            "AMD": 0.0707,
            "AVGO": 0.0610,
        },
    },
    "SOXX": {
        "source": "iShares/Schwab holdings snapshot June 2026",
        "holdings": {
            "MU": 0.1134,
            "AMD": 0.0885,
            "MRVL": 0.0816,
            "AVGO": 0.0613,
            "INTC": 0.0591,
            "NVDA": 0.0587,
        },
    },
    "IVES": {
        "source": "Wedbush/Morningstar holdings snapshot June 2026",
        "holdings": {
            "MU": 0.0617,
            "NVDA": 0.0477,
            "MSFT": 0.0476,
            "GOOGL": 0.0460,
            "AMD": 0.0459,
            "AVGO": 0.0447,
        },
    },
    "GRNY": {
        "source": "Schwab/Fundstrat GRNY holdings snapshot June 2026",
        "holdings": {
            "KLAC": 0.0270,
            "LLY": 0.0261,
            "CDNS": 0.0257,
            "ORCL": 0.0256,
            "GE": 0.0254,
            "HOOD": 0.0253,
            "GS": 0.0247,
            "PKG": 0.0247,
            "ANET": 0.0247,
            "UNH": 0.0246,
            "AMD": 0.0245,
        },
    },
    "GRNJ": {
        "source": "Schwab/Fundstrat GRNJ holdings snapshot June 2026",
        "holdings": {
            "CRS": 0.0194,
            "RDDT": 0.0194,
            "MDB": 0.0193,
            "GLXY": 0.0188,
            "NTRA": 0.0183,
            "ZETA": 0.0183,
            "SN": 0.0182,
            "CRDO": 0.0180,
            "NBIX": 0.0178,
            "STRL": 0.0178,
            "NBIS": 0.0177,
        },
    },
    "MAGS": {
        "source": "Roundhill/MAGS holdings snapshot June 2026",
        "holdings": {
            "GOOGL": 0.1582,
            "NVDA": 0.1496,
            "AAPL": 0.1480,
            "AMZN": 0.1450,
            "META": 0.1420,
            "MSFT": 0.1410,
            "TSLA": 0.1162,
        },
    },
}

DISPLAY_DIRECTIONS = {"BUY", "ADD", "TRIM", "SELL"}


def _ticker(value: Any) -> str:
    return str(value or "").strip().upper()


def _num(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _held_from_accounts(accounts: list[dict[str, Any]] | None) -> dict[str, float]:
    held: dict[str, float] = {}
    for account in accounts or []:
        if not isinstance(account, dict):
            continue
        for ticker, value in (account.get("holdings") or {}).items():
            tick = _ticker(ticker)
            amount = _num(value)
            if tick and amount > 0:
                held[tick] = held.get(tick, 0.0) + amount
    return held


def _held_from_feed(feed: dict[str, Any] | None) -> dict[str, float]:
    view = (((feed or {}).get("portfolio_views") or {}).get("views") or {}).get("combined") or {}
    held: dict[str, float] = {}
    for row in view.get("rows") or []:
        if not isinstance(row, dict):
            continue
        tick = _ticker(row.get("ticker"))
        value = _num(row.get("market_value"))
        asset_type = str(row.get("asset_type") or "").lower()
        if tick and value > 0 and "etf" not in asset_type:
            held[tick] = held.get(tick, 0.0) + value
    return held


def _fmt_pct(fraction: float) -> str:
    return f"{fraction * 100:.1f}%"


def card_lookthrough_disclosure(
    card: dict[str, Any],
    *,
    accounts: list[dict[str, Any]] | None = None,
    feed: dict[str, Any] | None = None,
    max_holdings: int = 6,
) -> dict[str, Any] | None:
    ticker = _ticker(card.get("ticker"))
    direction = _ticker(card.get("direction"))
    config = WRAPPER_LOOKTHROUGH.get(ticker)
    if not config or direction not in DISPLAY_DIRECTIONS:
        return None

    held = _held_from_accounts(accounts) or _held_from_feed(feed)
    holdings = sorted(
        (
            {
                "ticker": underlying,
                "weight": float(weight),
                "weight_pct": round(float(weight) * 100.0, 2),
                "held_value": round(held.get(underlying, 0.0), 2),
                "overlaps_held_single": held.get(underlying, 0.0) > 0,
            }
            for underlying, weight in (config.get("holdings") or {}).items()
        ),
        key=lambda row: (-row["weight"], row["ticker"]),
    )
    if not holdings:
        return None

    top = holdings[:max_holdings]
    overlaps = [row for row in top if row["overlaps_held_single"]]
    return {
        "ticker": ticker,
        "source": config.get("source") or "look-through config",
        "holdings": top,
        "contains_line": "contains " + ", ".join(
            f"{row['ticker']} {_fmt_pct(row['weight'])}" for row in top
        ),
        "overlap": overlaps,
        "overlap_line": (
            "overlap with held singles: "
            + ", ".join(f"{row['ticker']} {_fmt_pct(row['weight'])}" for row in overlaps)
            if overlaps else "no overlap with held singles in checked accounts"
        ),
    }
