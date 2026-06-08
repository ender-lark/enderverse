import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fundstrat_add_price_backfill import (
    apply_add_price_backfill,
    monthly_tickers,
    select_add_price_row,
)


def test_monthly_tickers_includes_large_and_smid_lists_deduped():
    deck = {
        "top5": ["AMD", {"ticker": "ANET"}],
        "bottom5": ["SATS"],
        "top5_smid": ["FN"],
        "bottom5_smid": ["SATS", "UUUU"],
    }

    assert monthly_tickers(deck) == ["AMD", "ANET", "SATS", "FN", "UUUU"]


def test_select_add_price_row_prefers_report_date_premarket():
    payload = {
        "data": [
            {"date": "2026-05-28", "market_time": "r", "close": "101"},
            {"date": "2026-05-28", "market_time": "pr", "close": "99.5"},
            {"date": "2026-05-27", "market_time": "r", "close": "98"},
        ]
    }

    row = select_add_price_row(payload, report_date="2026-05-28")

    assert row["market_time"] == "pr"
    assert row["close"] == "99.5"


def test_apply_add_price_backfill_preserves_existing_without_overwrite():
    prospects = {
        "AMD": {"ticker": "AMD", "add_price": None},
        "ANET": {"ticker": "ANET", "add_price": 10.0},
    }
    responses = {
        "AMD": {"data": [{"date": "2026-05-28", "market_time": "pr", "close": "99.5"}]},
        "ANET": {"data": [{"date": "2026-05-28", "market_time": "pr", "close": "88.0"}]},
    }

    summary = apply_add_price_backfill(
        prospects,
        responses,
        report_date="2026-05-28",
        source_note="Fundstrat report timestamp pre-regular-session",
    )

    assert summary["updated"] == ["AMD"]
    assert prospects["AMD"]["add_price"] == 99.5
    assert prospects["AMD"]["add_price_source"] == "UW OHLC pr 2026-05-28; Fundstrat report timestamp pre-regular-session"
    assert prospects["ANET"]["add_price"] == 10.0
