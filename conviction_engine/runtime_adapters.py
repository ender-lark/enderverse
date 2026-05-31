"""Stage-5 runtime adapters: live fetch output -> Conviction Engine plug inputs.

Claude-orchestrated model: in the cloud routine, Claude fetches the live data
with its own tools (Notion MCP for the book, UW MCP for prices), then calls
these PURE-PYTHON transforms to shape that data for the plugs. No network here —
fully testable with fakes.

S5.1 (this file): the `portfolio` adapter — the 📊 Latest Portfolio page's
"Per-Ticker Aggregation" table -> a positions list for `portfolio.portfolio_reader`
/ `portfolio.build_portfolio_source`.

  routine:  page_text = <notion-fetch 35ac5031-…>     # Claude fetches
            positions = portfolio_positions_from_page(page_text)
            src       = build_portfolio_source(positions)   # from portfolio.py

Later steps add the `uw_price` adapter (S5.2) and the skeleton wiring (S5.3).
"""
from __future__ import annotations

import re

# ─────────────────────────────────────────────────────────────────────────
# portfolio: 📊 Latest Portfolio page  ->  portfolio_reader positions
# ─────────────────────────────────────────────────────────────────────────
# The canonical book stores positions in the "Per-Ticker Aggregation" table:
#     Ticker | Shares | MV | % Sleeve | Owners        (e.g. SMH | 313.05 | $186,444 | 9.90% | p,s)
# Notion's fetch renders tables as <table><tr><td>…</td></tr></table> with the
# money column escaped ("\$186,444"). We locate THAT section (not Account
# Totals), pull its rows, and map to the plug's position shape.

_PER_TICKER_HEADER = "Per-Ticker Aggregation"


def _cells(tr_html: str) -> list[str]:
    return [c.strip() for c in re.findall(r"<td>(.*?)</td>", tr_html, re.S)]


def _is_separator_row(cells: list[str]) -> bool:
    """A markdown table separator row like ['---', '---:', ...]."""
    return all(c and set(c) <= {"-", ":"} for c in cells)


def _to_number(s: str | None) -> float | None:
    """'$186,444' / '\\$186,444' / '313.05' / '6,336.00' / '9.90%' -> float.

    Strips backslash, $, commas, %, and whitespace. Returns None for blank/
    non-numeric (e.g. a stray '-')."""
    if not s:
        return None
    cleaned = re.sub(r"[\\$,%\s]", "", s)
    if not cleaned or not re.search(r"\d", cleaned):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_per_ticker_table(page_text: str) -> list[dict]:
    """Extract the Per-Ticker Aggregation rows from a fetched 📊 Latest
    Portfolio page -> [{ticker, shares, mv, pct, owners}], header/separator
    rows dropped. Raises ValueError if the section/table isn't found (fail
    loud rather than silently returning an empty book)."""
    idx = page_text.find(_PER_TICKER_HEADER)
    if idx == -1:
        raise ValueError(f"'{_PER_TICKER_HEADER}' section not found in page")
    table_match = re.search(r"<table>(.*?)</table>", page_text[idx:], re.S)
    if not table_match:
        raise ValueError(f"no <table> under '{_PER_TICKER_HEADER}'")
    rows: list[dict] = []
    for tr in re.findall(r"<tr>(.*?)</tr>", table_match.group(1), re.S):
        cells = _cells(tr)
        if len(cells) < 5:
            continue
        if cells[0] == "Ticker":          # header row
            continue
        if _is_separator_row(cells):      # '---' separator row
            continue
        rows.append({
            "ticker": cells[0], "shares": cells[1], "mv": cells[2],
            "pct": cells[3], "owners": cells[4],
        })
    return rows


def positions_from_rows(rows: list[dict]) -> list[dict]:
    """Per-ticker rows -> portfolio_reader position shape.

    {ticker, pct(%), shares, value, owner('p,s'/'p'/'s'), account=None, sleeve=None}.
    account isn't in the per-ticker table; sleeve is mapped downstream by the
    Analyst (NAME_SLEEVE) — both left None here."""
    out: list[dict] = []
    for r in rows:
        ticker = (r.get("ticker") or "").strip()
        if not ticker:
            continue
        out.append({
            "ticker": ticker,
            "pct": _to_number(r.get("pct")),
            "shares": _to_number(r.get("shares")),
            "value": _to_number(r.get("mv")),
            "owner": (r.get("owners") or "").strip() or None,
            "account": None,
            "sleeve": None,
        })
    return out


def portfolio_positions_from_page(page_text: str) -> list[dict]:
    """Fetched 📊 Latest Portfolio page text -> positions ready for
    `portfolio.build_portfolio_source` / `portfolio.portfolio_reader`."""
    return positions_from_rows(parse_per_ticker_table(page_text))


# ─────────────────────────────────────────────────────────────────────────
# uw_price: UW close-price responses  ->  closes_by_ticker for the uw_price plug
# ─────────────────────────────────────────────────────────────────────────
# get_ticker_close_prices(ticker, "1Y") returns daily {c, date} NEWEST-FIRST.
# The rotation reader wants {ticker -> [oldest .. newest]} and pct_return needs
# MORE than the lookback (> 63), so the routine pulls "1Y" (~252 closes).
# "3M" returns ~63 daily closes — one short of the 63-bar lookback (would yield
# NO DATA rows), so do NOT use 3M here.

# The 9 sleeve proxies + the SPY benchmark. SMH doubles as the AI benchmark and
# is already a proxy, so no extra pull. The routine calls
# get_ticker_close_prices(t, UW_ROTATION_TIMEFRAME) for each of these and passes
# {ticker: response} to closes_by_ticker_from_uw().
UW_ROTATION_TICKERS = ["SMH", "IGV", "GRNY", "IBIT", "URA", "REMX", "XLF", "GDX", "VOLT", "SPY"]
UW_ROTATION_TIMEFRAME = "1Y"


def closes_by_ticker_from_uw(responses_by_ticker: dict) -> dict:
    """{ticker: <get_ticker_close_prices response>} -> {ticker: [oldest..newest closes]}.

    Sorts each series oldest-first BY DATE (robust to UW's newest-first default,
    and to any future ordering change). Tickers whose response has no usable
    closes (empty data / index access denied) are dropped — the rotation reader
    then emits an honest NO DATA row for any proxy missing its series rather than
    faking a number."""
    out: dict = {}
    for ticker, resp in (responses_by_ticker or {}).items():
        data = (resp or {}).get("data") or []
        pts = [
            (pt.get("date") or "", pt.get("c"))
            for pt in data
            if isinstance(pt, dict) and pt.get("c") is not None
        ]
        if not pts:
            continue
        pts.sort(key=lambda dc: dc[0])          # oldest -> newest (ascending date)
        out[ticker] = [float(c) for _, c in pts]
    return out
