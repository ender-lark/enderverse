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

from datetime import date, datetime
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


# ─────────────────────────────────────────────────────────────────────────
# uw_macro: UW yield-curve + level close-series  ->  uw_macro snapshot (S5.4)
# ─────────────────────────────────────────────────────────────────────────
# get_yield_curve() returns a LATEST-ONLY snapshot: a 1-element list of
#   {"new_date": "...", "bc_2year": "3.99", "bc_10year": "4.45", "bc_30year": "4.98", ...}
# (rates as percent strings). Because it's latest-only there is no 5d-ago rate,
# so rate cards emit without the "(±Xbp 5d)" tail — honest, not faked. (A daily
# rates-history pull for 5d rate-change is a documented enrichment backlog item.)
#
# Levels (DXY/VIX/MOVE) reuse the get_ticker_close_prices daily shape
# ({"data":[{"c","date"}]}); value = latest close, value_5d_ago = the close 5
# trading days back (index -6 of the date-sorted series). The routine maps each
# display label to a UW symbol it pulls (e.g. DXY<-UUP/DXY, VIX<-VIX, MOVE<-MOVE);
# this adapter just keys levels by whatever labels the caller passes.
# NOTE: the dollar slot stays KEYED "DXY" (regime + line-order find it by that),
# but because it's the UUP proxy (~$28, not the ~99 index) it RENDERS as
# "USD (UUP)" — see uw_macro._LEVEL_DISPLAY + publish_gate.MACRO_BANDS.
#
#   routine:  yc   = <get_yield_curve()>                                  # Claude fetches
#             lv   = {"DXY": <get_ticker_close_prices("UUP","3M")>, ...}  # Claude fetches
#             snap = uw_macro_snapshot_from_uw(yc, lv)
#             src  = build_uw_macro_source(snap)                          # from uw_macro.py

_YIELD_CURVE_TENORS = [("2Y", "bc_2year"), ("10Y", "bc_10year"), ("30Y", "bc_30year")]


def rates_from_yield_curve(yc_resp) -> dict:
    """get_yield_curve() response -> {tenor: {value(%), value_5d_ago=None}}.

    Accepts the 1-element list UW returns (or a bare snapshot dict). A tenor whose
    value is missing/blank is dropped (the reader then skips that card). value_5d_ago
    is None because the curve snapshot is latest-only."""
    snap = yc_resp[0] if isinstance(yc_resp, list) and yc_resp else yc_resp
    snap = snap or {}
    rates: dict = {}
    for tenor, key in _YIELD_CURVE_TENORS:
        raw = snap.get(key)
        if raw in (None, ""):
            continue
        try:
            rates[tenor] = {"value": float(raw), "value_5d_ago": None}
        except (TypeError, ValueError):
            continue
    return rates


def levels_from_close_responses(responses_by_symbol: dict) -> dict:
    """{label: <get_ticker_close_prices response>} -> {label: {value, value_5d_ago}}.

    value = latest close; value_5d_ago = close 5 trading days back (None if the
    series has < 6 points). Symbols with no usable closes are dropped (the reader
    then skips that level card rather than faking a number)."""
    out: dict = {}
    for label, resp in (responses_by_symbol or {}).items():
        data = (resp or {}).get("data") or []
        pts = [
            (pt.get("date") or "", pt.get("c"))
            for pt in data
            if isinstance(pt, dict) and pt.get("c") is not None
        ]
        if not pts:
            continue
        pts.sort(key=lambda dc: dc[0])              # oldest -> newest
        value = float(pts[-1][1])
        v5 = float(pts[-6][1]) if len(pts) >= 6 else None
        out[label] = {"value": value, "value_5d_ago": v5}
    return out


def uw_macro_snapshot_from_uw(yield_curve_resp, level_responses: dict | None = None) -> dict:
    """Live UW fetch output -> the macro_snapshot the uw_macro plug consumes:
    {"rates": {...}, "levels": {...}}. Pass level_responses=None for a
    rates-only snapshot (levels simply absent -> no level cards)."""
    return {
        "rates": rates_from_yield_curve(yield_curve_resp),
        "levels": levels_from_close_responses(level_responses or {}),
    }


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Catalyst Calendar: raw Notion/calendar rows -> feed["catalysts"] rows
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _parse_iso_date(value) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _split_tickers(value) -> list[str]:
    raw = str(value or "").upper()
    out: list[str] = []
    for tk in re.split(r"[\s,;/]+", raw):
        tk = tk.strip()
        if not tk or tk == "TICKER":
            continue
        if len(tk) > 8 or not tk.replace(".", "").isalnum():
            continue
        if tk not in out:
            out.append(tk)
    return out


def catalysts_from_calendar_rows(
    rows,
    *,
    as_of: str | date | None = None,
    horizon_days: int | None = None,
    default_source: str = "Catalyst Calendar",
) -> list[dict]:
    """Normalize raw Catalyst Calendar rows into Contract-C catalyst rows.

    Accepted raw keys are intentionally broad because the caller may pass rows
    from `live_theses_helpers.fetch_catalyst_calendar` (`name`/`type`) or a hand
    curated cache (`label`/`source`). Past rows are skipped. When `horizon_days`
    is supplied, rows beyond that window are skipped by the adapter rather than
    left for the analyst read to ignore.
    """
    base = as_of if isinstance(as_of, date) else _parse_iso_date(as_of) if as_of else date.today()
    if base is None:
        base = date.today()

    out: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        event_date = _parse_iso_date(row.get("date") or row.get("event_date") or row.get("when"))
        if event_date is None:
            continue
        days_out = (event_date - base).days
        if days_out < 0:
            continue
        if horizon_days is not None and days_out > horizon_days:
            continue

        label = (
            row.get("label")
            or row.get("name")
            or row.get("catalyst")
            or row.get("event")
            or row.get("type")
            or "Catalyst"
        )
        source = row.get("source") or default_source
        for ticker in _split_tickers(row.get("ticker") or row.get("tickers") or row.get("symbol")):
            key = (ticker, event_date.isoformat(), str(label).strip())
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "ticker": ticker,
                "label": str(label).strip() or "Catalyst",
                "date": event_date.isoformat(),
                "days_out": days_out,
                "source": str(source).strip() or default_source,
            })

    out.sort(key=lambda r: (r["days_out"], r["ticker"], r["label"]))
    return out
