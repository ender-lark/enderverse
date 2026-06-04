#!/usr/bin/env python3
"""
uw_endpoint_catalog.py - official Unusual Whales endpoint constants.

This is intentionally small and boring: it centralizes the endpoint strings the
Investing OS is allowed to call so cache builders do not re-invent or hallucinate
UW paths. Source of truth checked 2026-06-04:
  - https://api.unusualwhales.com/docs
  - https://api.unusualwhales.com/api/openapi
  - https://unusualwhales.com/skill.md
"""
from __future__ import annotations

UW_API_BASE = "https://api.unusualwhales.com"
UW_CLIENT_API_ID = "100001"


class UWEndpoints:
    # Options flow / opportunity radar
    FLOW_ALERTS = "/api/option-trades/flow-alerts"
    TICKER_FLOW_ALERTS = "/api/stock/{ticker}/flow-alerts"
    TICKER_FLOW_RECENT = "/api/stock/{ticker}/flow-recent"
    TICKER_FLOW_PER_EXPIRY = "/api/stock/{ticker}/flow-per-expiry"
    TICKER_FLOW_PER_STRIKE = "/api/stock/{ticker}/flow-per-strike"

    # Open interest / chains
    TICKER_OI_CHANGE = "/api/stock/{ticker}/oi-change"
    MARKET_OI_CHANGE = "/api/market/oi-change"
    TICKER_OPTION_CONTRACTS = "/api/stock/{ticker}/option-contracts"
    TICKER_OPTION_CHAINS = "/api/stock/{ticker}/option-chains"
    TICKER_OPTIONS_VOLUME = "/api/stock/{ticker}/options-volume"

    # Dark pool / lit flow
    DARKPOOL_TICKER = "/api/darkpool/{ticker}"
    DARKPOOL_RECENT = "/api/darkpool/recent"
    LIT_FLOW_TICKER = "/api/lit-flow/{ticker}"
    LIT_FLOW_RECENT = "/api/lit-flow/recent"
    TICKER_STOCK_VOLUME_PRICE_LEVELS = "/api/stock/{ticker}/stock-volume-price-levels"

    # Greeks / GEX / IV
    TICKER_GREEK_EXPOSURE = "/api/stock/{ticker}/greek-exposure"
    TICKER_GREEK_EXPOSURE_STRIKE = "/api/stock/{ticker}/greek-exposure/strike"
    TICKER_GREEK_EXPOSURE_EXPIRY = "/api/stock/{ticker}/greek-exposure/expiry"
    TICKER_GREEK_EXPOSURE_STRIKE_EXPIRY = "/api/stock/{ticker}/greek-exposure/strike-expiry"
    TICKER_GREEKS = "/api/stock/{ticker}/greeks"
    TICKER_SPOT_EXPOSURES_STRIKE = "/api/stock/{ticker}/spot-exposures/strike"
    TICKER_SPOT_EXPOSURES_EXPIRY_STRIKE = "/api/stock/{ticker}/spot-exposures/expiry-strike"
    TICKER_GREEK_FLOW = "/api/stock/{ticker}/greek-flow"
    TICKER_IV_RANK = "/api/stock/{ticker}/iv-rank"
    TICKER_INTERPOLATED_IV = "/api/stock/{ticker}/interpolated-iv"
    TICKER_REALIZED_VOL = "/api/stock/{ticker}/volatility/realized"
    TICKER_VOL_STATS = "/api/stock/{ticker}/volatility/stats"
    TICKER_VOL_TERM_STRUCTURE = "/api/stock/{ticker}/volatility/term-structure"

    # Prices / state / technicals
    TICKER_OHLC = "/api/stock/{ticker}/ohlc/{candle_size}"
    TICKER_STOCK_STATE = "/api/stock/{ticker}/stock-state"
    TICKER_INFO = "/api/stock/{ticker}/info"
    COMPANY_PROFILE = "/api/companies/{ticker}/profile"
    TICKER_TECHNICAL_INDICATOR = "/api/stock/{ticker}/technical-indicator/{function}"
    MARKET_CORRELATIONS = "/api/market/correlations"

    # Earnings / fundamentals
    TICKER_EARNINGS = "/api/stock/{ticker}/earnings"
    EARNINGS_TICKER = "/api/earnings/{ticker}"
    TICKER_INCOME_STATEMENTS = "/api/stock/{ticker}/income-statements"
    TICKER_BALANCE_SHEETS = "/api/stock/{ticker}/balance-sheets"
    TICKER_CASH_FLOWS = "/api/stock/{ticker}/cash-flows"
    TICKER_FINANCIALS = "/api/stock/{ticker}/financials"
    TICKER_FUNDAMENTAL_BREAKDOWN = "/api/stock/{ticker}/fundamental-breakdown"
    COMPANY_EARNINGS_ESTIMATES = "/api/companies/{ticker}/earnings-estimates"
    COMPANY_TRANSCRIPT = "/api/companies/{ticker}/transcripts/{quarter}"

    # Analysts / insider / institutions / congress / news
    ANALYST_RATINGS = "/api/screener/analysts"
    INSIDER_TRANSACTIONS = "/api/insider/transactions"
    TICKER_INSIDERS = "/api/insider/{ticker}"
    TICKER_INSIDER_FLOW = "/api/insider/{ticker}/ticker-flow"
    INSTITUTION_HOLDINGS = "/api/institution/{name}/holdings"
    INSTITUTION_OWNERSHIP = "/api/institution/{ticker}/ownership"
    INSTITUTION_ACTIVITY = "/api/institution/{name}/activity/v2"
    INSTITUTIONS = "/api/institutions"
    INSTITUTIONS_LATEST_FILINGS = "/api/institutions/latest_filings"
    CONGRESS_RECENT_TRADES = "/api/congress/recent-trades"
    CONGRESS_TRADER = "/api/congress/congress-trader"
    CONGRESS_UNUSUAL_BY_TICKERS = "/api/congress/unusual-trades/by-tickers"
    NEWS_HEADLINES = "/api/news/headlines"

    # Screeners / market context
    STOCK_SCREENER = "/api/screener/stocks"
    OPTION_CONTRACT_SCREENER = "/api/screener/option-contracts"
    MARKET_TIDE = "/api/market/market-tide"
    SECTOR_TIDE = "/api/market/{sector}/sector-tide"
    ETF_TIDE = "/api/market/{ticker}/etf-tide"
    NET_FLOW_EXPIRY = "/api/net-flow/expiry"
    TOTAL_OPTIONS_VOLUME = "/api/market/total-options-volume"
    TOP_NET_IMPACT = "/api/market/top-net-impact"
    MARKET_MOVERS = "/api/market/movers"
    ECONOMIC_CALENDAR = "/api/market/economic-calendar"


PARABOLIC_ENDPOINTS = {
    "earnings": UWEndpoints.TICKER_EARNINGS,
    "prices": UWEndpoints.TICKER_OHLC,
    "income": UWEndpoints.TICKER_INCOME_STATEMENTS,
    "info": UWEndpoints.TICKER_INFO,
}

UW_OPPORTUNITY_ENDPOINTS = {
    "flow": UWEndpoints.TICKER_FLOW_ALERTS,
    "oi": UWEndpoints.TICKER_OI_CHANGE,
    "dark_pool": UWEndpoints.DARKPOOL_TICKER,
    "greek": UWEndpoints.TICKER_GREEK_EXPOSURE_STRIKE,
    "iv": UWEndpoints.TICKER_IV_RANK,
}

INVALID_ENDPOINTS = {
    "/api/options/flow",
    "/api/flow",
    "/api/flow/live",
    "/api/stock/{ticker}/flow",
    "/api/stock/{ticker}/options",
    "/api/unusual-activity",
}


def validate_endpoint_path(path: str) -> None:
    """Fail fast on common hallucinated UW endpoint shapes."""
    if "/api/v1/" in path or "/api/v2/" in path:
        raise ValueError(f"Invalid/hallucinated UW endpoint path: {path}")
    if path in INVALID_ENDPOINTS:
        raise ValueError(f"Invalid/hallucinated UW endpoint path: {path}")
    if not path.startswith("/api/"):
        raise ValueError(f"UW endpoint must start with /api/: {path}")
