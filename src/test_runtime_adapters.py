"""Tests for the Stage-5 portfolio adapter (runtime_adapters.py, S5.1).

Fixture mirrors the REAL notion-fetch render of 📊 Latest Portfolio: escaped
"\\$" money, <table><tr><td> rows on their own lines, an Account Totals table
BEFORE the Per-Ticker table (to prove the parser targets the right one), a
header + separator row, an option row, and mixed owner values.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from runtime_adapters import (
    _to_number,
    parse_per_ticker_table,
    positions_from_rows,
    portfolio_positions_from_page,
    closes_by_ticker_from_uw,
    catalysts_from_calendar_rows,
    UW_ROTATION_TICKERS,
    UW_ROTATION_TIMEFRAME,
)
from portfolio import build_portfolio_source
from uw_price import build_uw_price_source
from sources import SourceRegistry

# Real-shaped mini page: wrapper text + two tables + trailing section.
PAGE = r"""Here is the result of "view" for the Page ...
<content>
# 📊 Latest Portfolio
**As of:** 2026-05-27 16:03 ET (broker PDF refresh)
**Grand Total:** \$1,882,441.28
## Account Totals (descending)
<table>
<tr>
<td>Owner</td>
<td>Broker</td>
<td>Account</td>
<td>MV</td>
<td>Cash</td>
<td>Flags</td>
</tr>
<tr>
<td>---</td>
<td>---</td>
<td>---</td>
<td>---:</td>
<td>---:</td>
<td>---</td>
</tr>
<tr>
<td>p</td>
<td>fidelity</td>
<td>Joint WROS - TOD</td>
<td>\$591,200</td>
<td>\$17,144.11</td>
<td>-</td>
</tr>
</table>
## Per-Ticker Aggregation (≥\$500)
<table>
<tr>
<td>Ticker</td>
<td>Shares</td>
<td>MV</td>
<td>% Sleeve</td>
<td>Owners</td>
</tr>
<tr>
<td>---</td>
<td>---:</td>
<td>---:</td>
<td>---:</td>
<td>---</td>
</tr>
<tr>
<td>SMH</td>
<td>313.05</td>
<td>\$186,444</td>
<td>9.90%</td>
<td>p,s</td>
</tr>
<tr>
<td>XLF</td>
<td>560.00</td>
<td>\$28,788</td>
<td>1.53%</td>
<td>p</td>
</tr>
<tr>
<td>LEU 300 CALL</td>
<td>1</td>
<td>\$5,000</td>
<td>0.27%</td>
<td>p</td>
</tr>
</table>
## Zombie/Dust (\<\$500, framework skip)
- TEM \$236 · ORBS \$132
</content>
"""


def test_to_number_strips_money_commas_percent():
    assert _to_number(r"\$186,444") == 186444.0
    assert _to_number("$28,788") == 28788.0
    assert _to_number("313.05") == 313.05
    assert _to_number("6,336.00") == 6336.0
    assert _to_number("9.90%") == 9.90
    assert _to_number("1") == 1.0
    assert _to_number("-") is None
    assert _to_number("") is None
    assert _to_number(None) is None


def test_parse_per_ticker_table_returns_data_rows_only():
    rows = parse_per_ticker_table(PAGE)
    assert len(rows) == 3                      # header + separator dropped
    assert [r["ticker"] for r in rows] == ["SMH", "XLF", "LEU 300 CALL"]


def test_parse_targets_per_ticker_not_account_totals():
    # Account Totals (which has 'fidelity'/'p' cells) sits BEFORE the section;
    # the parser must not pick it up.
    rows = parse_per_ticker_table(PAGE)
    flat = {r["ticker"] for r in rows}
    assert "fidelity" not in flat and "p" not in flat
    assert rows[0]["ticker"] == "SMH"


def test_positions_from_rows_maps_fields():
    rows = parse_per_ticker_table(PAGE)
    pos = positions_from_rows(rows)
    smh = next(p for p in pos if p["ticker"] == "SMH")
    assert smh["pct"] == 9.90
    assert smh["shares"] == 313.05
    assert smh["value"] == 186444.0
    assert smh["owner"] == "p,s"
    assert smh["account"] is None and smh["sleeve"] is None


def test_option_row_parsed():
    pos = portfolio_positions_from_page(PAGE)
    opt = next(p for p in pos if p["ticker"] == "LEU 300 CALL")
    assert opt["value"] == 5000.0
    assert opt["owner"] == "p"
    assert opt["pct"] == 0.27


def test_owner_variants_preserved():
    pos = portfolio_positions_from_page(PAGE)
    by_t = {p["ticker"]: p for p in pos}
    assert by_t["SMH"]["owner"] == "p,s"
    assert by_t["XLF"]["owner"] == "p"


def test_end_to_end_count_and_tickers():
    pos = portfolio_positions_from_page(PAGE)
    assert len(pos) == 3
    assert {p["ticker"] for p in pos} == {"SMH", "XLF", "LEU 300 CALL"}


def test_missing_section_raises():
    try:
        parse_per_ticker_table("# Some other page\nno table here")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_feeds_the_real_portfolio_plug():
    """The adapter output flows into the actual `portfolio` plug -> position cards."""
    pos = portfolio_positions_from_page(PAGE)
    reg = SourceRegistry()
    reg.register(build_portfolio_source(pos))
    items = reg.fetch_all()
    positions = [it for it in items if getattr(it, "kind", None) == "position"]
    assert len(positions) == 3
    smh = next(it for it in positions if it.subject == "SMH")
    assert smh.data["ticker"] == "SMH"
    assert smh.data["pct"] == 9.90
    assert smh.data["owner"] == "p,s"
    assert smh.data["value"] == 186444.0


# ── uw_price adapter (S5.2) ──────────────────────────────────────────────

def _fake_uw(closes_ascending):
    """A get_ticker_close_prices-shaped response (NEWEST-FIRST daily {c,date})
    built from an ascending close list, mirroring the real UW shape."""
    data = [{"c": c, "date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}"}
            for i, c in enumerate(closes_ascending)]
    return {"data": list(reversed(data)), "returns": {}, "market_time": "postmarket"}


def test_uw_rotation_tickers_and_timeframe():
    assert UW_ROTATION_TIMEFRAME == "1Y"          # 3M (~63) is one short of the 63-bar lookback
    assert "SPY" in UW_ROTATION_TICKERS and "SMH" in UW_ROTATION_TICKERS
    assert len(UW_ROTATION_TICKERS) == 10         # 9 proxies + SPY


def test_closes_sorted_oldest_to_newest():
    asc = [100.0, 101.0, 102.0, 103.0]
    cbt = closes_by_ticker_from_uw({"SMH": _fake_uw(asc)})
    assert cbt["SMH"] == asc                       # newest-first input -> ascending output
    assert cbt["SMH"][-1] == 103.0                 # newest last (what pct_return reads as latest)


def test_closes_robust_to_input_order():
    already_asc = {"data": [{"c": 10.0, "date": "2026-01-01"},
                            {"c": 11.0, "date": "2026-01-02"},
                            {"c": 12.0, "date": "2026-01-03"}]}
    assert closes_by_ticker_from_uw({"X": already_asc})["X"] == [10.0, 11.0, 12.0]


def test_empty_or_denied_series_dropped():
    cbt = closes_by_ticker_from_uw({
        "SMH": _fake_uw([1.0, 2.0]),
        "IDX": {"data": []},          # index access denied -> empty
        "BAD": {},                    # malformed
    })
    assert "SMH" in cbt and "IDX" not in cbt and "BAD" not in cbt


def test_feeds_the_real_uw_price_plug():
    """Adapter output flows into the actual uw_price plug -> rotation cards, and
    ordering is correct (a steady riser must lead a flat benchmark)."""
    smh = [100 + i * 0.3 for i in range(70)]       # rises ~19% over the window
    flat = [100.0] * 70
    responses = {"SMH": _fake_uw(smh), "SPY": _fake_uw(flat), "IGV": _fake_uw([50.0] * 70)}
    cbt = closes_by_ticker_from_uw(responses)
    assert cbt["SMH"][-1] > cbt["SMH"][0]          # ascending restored
    reg = SourceRegistry()
    reg.register(build_uw_price_source(cbt, proxies=["SMH", "IGV"]))
    rot = [it for it in reg.fetch_all() if getattr(it, "kind", None) == "rotation"]
    assert len(rot) == 2
    smh_card = next(it for it in rot if it.subject == "SMH")
    assert smh_card.data["rel_3m"] > 0             # SMH led flat SPY — sign proves ordering
    assert smh_card.data["label"] in ("LEADING", "TURNING DOWN")
    igv_card = next(it for it in rot if it.subject == "IGV")
    assert igv_card.data["label"] == "IN LINE"     # flat vs flat


# â”€â”€ Catalyst Calendar adapter â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_catalysts_from_calendar_rows_normalizes_live_helper_shape():
    rows = [
        {"ticker": "AVGO", "date": "2026-06-06T00:00:00+00:00",
         "name": "Q2 earnings", "type": "Earnings"},
    ]
    cats = catalysts_from_calendar_rows(rows, as_of="2026-06-04")
    assert cats == [{
        "ticker": "AVGO",
        "label": "Q2 earnings",
        "date": "2026-06-06",
        "days_out": 2,
        "source": "Catalyst Calendar",
    }]


def test_catalysts_from_calendar_rows_splits_tickers_and_sorts():
    rows = [
        {"tickers": "UUUU, MP; LEU", "date": "2026-06-10", "label": "Nuclear hearing"},
        {"ticker": "AVGO", "date": "2026-06-06", "label": "Earnings"},
    ]
    cats = catalysts_from_calendar_rows(rows, as_of="2026-06-04")
    assert [(c["days_out"], c["ticker"]) for c in cats] == [
        (2, "AVGO"), (6, "LEU"), (6, "MP"), (6, "UUUU")
    ]


def test_catalysts_from_calendar_rows_skips_past_far_and_malformed():
    rows = [
        {"ticker": "OLD", "date": "2026-06-01", "label": "Past"},
        {"ticker": "FAR", "date": "2026-07-01", "label": "Too far"},
        {"ticker": "BAD", "date": "not a date", "label": "Bad"},
        {"ticker": "AVGO", "date": "2026-06-06", "label": "Earnings"},
    ]
    cats = catalysts_from_calendar_rows(rows, as_of="2026-06-04", horizon_days=7)
    assert [c["ticker"] for c in cats] == ["AVGO"]


def test_catalysts_from_calendar_rows_dedupes_same_event():
    rows = [
        {"ticker": "AVGO", "date": "2026-06-06", "label": "Earnings"},
        {"ticker": "AVGO", "date": "2026-06-06T00:00:00+00:00", "label": "Earnings"},
    ]
    cats = catalysts_from_calendar_rows(rows, as_of="2026-06-04")
    assert len(cats) == 1
