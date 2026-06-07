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


def test_category_summary_adds_working_model_and_fundstrat_guidance():
    payload = {
        "snapshot_date": "2026-06-07",
        "sleeve_value": 10000,
        "account_positions": [
            {
                "ticker": "NVDA",
                "description": "NVIDIA",
                "shares": 10,
                "market_value": 1000,
                "account": "Fidelity",
                "owner": "SKB",
                "broker": "Fidelity",
                "tracked": True,
                "asset_type": "Common Stock",
            },
            {
                "ticker": "GOOGL",
                "description": "Alphabet",
                "shares": 10,
                "market_value": 500,
                "account": "Fidelity",
                "owner": "SKB",
                "broker": "Fidelity",
                "tracked": True,
                "asset_type": "Common Stock",
            },
        ],
    }
    fundstrat = {
        "deck_date": "2026-05-28",
        "what_to_own": ["MAG7", "Financials"],
        "top5": ["GOOGL", "GS"],
        "bottom5": [],
    }

    views = pv.build_portfolio_views(payload, fundstrat_bible=fundstrat)
    category = next(row for row in views["views"]["combined"]["categories"] if row["category"] == "AI / Semiconductors")

    assert category["working_model_target_pct"] > 0
    assert category["working_model_gap_pct"] is not None
    assert category["fundstrat_cue"] == "favored"
    assert category["fundstrat_source_date"] == "2026-05-28"
    assert "GOOGL" in category["fundstrat_tickers"]
    assert views["allocation_guidance"]["basis"] == "visual guidance only; not an instruction to trade"
