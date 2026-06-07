import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import portfolio_views as pv


def test_combined_view_keeps_option_series_separate_from_common_ticker():
    payload = {
        "snapshot_date": "2026-06-07",
        "account_positions": [
            {
                "ticker": "BMNR",
                "description": "Bitmine Immersion Technologies, Inc.",
                "shares": 100,
                "market_value": 1590,
                "account": "Robinhood Individual",
                "owner": "SKB",
                "broker": "Robinhood",
                "tracked": True,
                "asset_type": "Common Stock",
            },
            {
                "ticker": "BMNR",
                "description": "30 Call 2028-01-21",
                "shares": 4,
                "market_value": 1792,
                "account": "Robinhood Individual",
                "owner": "SKB",
                "broker": "Robinhood",
                "tracked": True,
                "asset_type": "option",
                "option": {
                    "underlying": "BMNR",
                    "expiry": "2028-01-21",
                    "call_put": "call",
                    "strike": 30,
                    "multiplier": 100,
                    "price_convention": "contract",
                },
            },
        ],
    }

    views = pv.build_portfolio_views(payload)
    rows = views["views"]["combined"]["rows"]

    assert len([row for row in rows if row["ticker"] == "BMNR"]) == 2
    option = next(row for row in rows if row.get("description") == "30 Call 2028-01-21")
    common = next(row for row in rows if row.get("description") == "Bitmine Immersion Technologies, Inc.")
    assert option["shares"] == 4
    assert option["market_value"] == 1792
    assert option["option"]["price_convention"] == "contract"
    assert common["shares"] == 100
    assert common["market_value"] == 1590
