import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from portfolio_views import build_portfolio_views, validate_portfolio_views


ACCOUNT_CACHE = {
    "snapshot_date": "2026-06-05",
    "sleeve_value": 10000,
    "account_positions": [
        {"ticker": "NVDA", "description": "NVIDIA", "shares": 10, "market_value": 3000, "account": "Taxable", "owner": "SKB", "broker": "Fidelity", "tracked": True},
        {"ticker": "SMH", "description": "Semis ETF", "shares": 5, "market_value": 2000, "account": "IRA", "owner": "Parents", "broker": "Schwab", "tracked": True},
        {"ticker": "XLF", "description": "Financials ETF", "shares": 8, "market_value": 1000, "account": "Taxable", "owner": "SKB", "broker": "Fidelity", "tracked": False},
    ],
}


def test_build_portfolio_views_outputs_combined_skb_and_parents():
    views = build_portfolio_views(ACCOUNT_CACHE)

    assert validate_portfolio_views(views) == []
    assert views["basis"] == "direct_holdings_only"
    assert views["views"]["combined"]["total_value"] == 10000
    assert {r["ticker"] for r in views["views"]["combined"]["rows"]} == {"NVDA", "SMH", "XLF"}
    assert {r["ticker"] for r in views["views"]["skb"]["rows"]} == {"NVDA", "XLF"}
    assert {r["ticker"] for r in views["views"]["parents"]["rows"]} == {"SMH"}


def test_portfolio_views_category_summary_is_direct_only():
    views = build_portfolio_views(ACCOUNT_CACHE)
    combined_categories = {c["category"]: c for c in views["views"]["combined"]["categories"]}

    assert combined_categories["AI / Semiconductors"]["market_value"] == 5000
    assert combined_categories["AI / Semiconductors"]["pct"] == 50.0
    assert "direct holdings only" in views["caveat"]


def test_portfolio_views_effective_exposure_adds_etf_overlap_separately():
    views = build_portfolio_views(ACCOUNT_CACHE)
    effective = views["views"]["combined"]["effective_exposure"]
    overlaps = {row["ticker"]: row for row in effective["overlap_rows"]}
    sleeves = {row["category"]: row for row in effective["sleeves"]}

    assert effective["basis"] == "direct_plus_estimated_etf_lookthrough"
    assert overlaps["NVDA"]["direct_market_value"] == 3000
    assert overlaps["NVDA"]["lookthrough_market_value"] == 400
    assert overlaps["NVDA"]["effective_market_value"] == 3400
    assert overlaps["NVDA"]["sources"] == [{"etf": "SMH", "fraction": 0.2, "market_value": 400.0}]
    assert sleeves["AI / Semiconductors"]["direct_market_value"] == 5000
    assert sleeves["AI / Semiconductors"]["lookthrough_market_value"] == 720
    assert sleeves["AI / Semiconductors"]["effective_pct"] == 57.2


def test_portfolio_views_effective_exposure_is_account_specific():
    views = build_portfolio_views(ACCOUNT_CACHE)

    assert views["views"]["skb"]["effective_exposure"]["overlap_rows"] == []
    parent_overlap = {row["ticker"]: row for row in views["views"]["parents"]["effective_exposure"]["overlap_rows"]}
    assert parent_overlap["NVDA"]["direct_market_value"] == 0
    assert parent_overlap["NVDA"]["lookthrough_market_value"] == 400


def test_empty_or_missing_account_cache_returns_none():
    assert build_portfolio_views(None) is None
    assert build_portfolio_views({"account_positions": []}) is None
