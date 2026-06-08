from account_trade_placement import (
    PARENT_SCHWAB_RULE,
    annotate_actions,
    annotate_reallocation_brief,
    recommend_account_placement,
)


ACCOUNT_POSITIONS = {
    "account_positions": [
        {
            "ticker": "GRNY",
            "market_value": 200000,
            "account": "PCRA Trust ...651",
            "owner": "Parents",
            "broker": "Schwab",
            "asset_type": "ETF",
        },
        {
            "ticker": "NVDA",
            "market_value": 100000,
            "account": "Individual ...254",
            "owner": "SKB",
            "broker": "Schwab",
            "asset_type": "Common Stock",
        },
        {
            "ticker": "NVDA",
            "market_value": 60000,
            "account": "Joint WROS",
            "owner": "Parents",
            "broker": "Fidelity",
            "asset_type": "Common Stock",
        },
        {
            "ticker": "BMNR",
            "market_value": 50000,
            "account": "Robinhood Individual",
            "owner": "SKB",
            "broker": "Robinhood",
            "asset_type": "Common Stock",
        },
        {
            "ticker": "BMNR",
            "market_value": 7000,
            "account": "Robinhood Individual",
            "owner": "SKB",
            "broker": "Robinhood",
            "asset_type": "option",
            "option": {"type": "call"},
        },
        {
            "ticker": "ETH",
            "market_value": 800,
            "account": "Robinhood Crypto 8794",
            "owner": "SKB",
            "broker": "Robinhood",
            "asset_type": "Cryptocurrency",
        },
    ]
}


def test_etf_add_routes_to_parent_schwab_pcra():
    placement = recommend_account_placement(
        {"ticker": "SMH", "capital_effect": "add", "what": "Add ETF exposure"},
        ACCOUNT_POSITIONS,
    )

    assert placement["status"] == "candidate"
    assert placement["owner"] == "Parents"
    assert placement["broker"] == "Schwab"
    assert "ETF candidate" in placement["why"]
    assert placement["rule"] == PARENT_SCHWAB_RULE


def test_individual_stock_add_avoids_parent_schwab_and_prefers_existing_holding():
    placement = recommend_account_placement(
        {"ticker": "NVDA", "capital_effect": "add", "what": "Add to NVDA"},
        ACCOUNT_POSITIONS,
    )

    assert placement["status"] == "candidate"
    assert placement["owner"] == "SKB"
    assert placement["broker"] == "Schwab"
    assert "Individual-stock candidate" in placement["why"]
    assert "PCRA" not in placement["account"]


def test_mixed_stock_and_option_rows_do_not_make_stock_add_an_option_trade():
    placement = recommend_account_placement(
        {"ticker": "BMNR", "capital_effect": "add", "what": "Add BMNR shares"},
        ACCOUNT_POSITIONS,
    )

    assert placement["instrument_class"] == "stock"
    assert placement["account"] == "Robinhood Individual"


def test_crypto_routes_to_robinhood_crypto():
    placement = recommend_account_placement(
        {"ticker": "ETH", "capital_effect": "add", "what": "Add crypto exposure"},
        ACCOUNT_POSITIONS,
    )

    assert placement["status"] == "candidate"
    assert placement["account"] == "Robinhood Crypto 8794"
    assert "Crypto candidates" in placement["why"]


def test_trim_uses_largest_existing_holding_account_even_for_etf():
    placement = recommend_account_placement(
        {"ticker": "GRNY", "action": "TRIM_FUNDING_CANDIDATE"},
        ACCOUNT_POSITIONS,
    )

    assert placement["side"] == "trim/sell"
    assert placement["account"] == "PCRA Trust ...651"
    assert "largest current account position" in placement["why"]


def test_annotators_add_account_placement_to_actions_and_reallocation_rows():
    actions = annotate_actions(
        [{"ticker": "NVDA", "capital_effect": "add", "what": "Add NVDA"}],
        ACCOUNT_POSITIONS,
    )
    brief = annotate_reallocation_brief(
        {"rows": [{"ticker": "SMH", "action": "ADD_CANDIDATE"}], "trims": []},
        ACCOUNT_POSITIONS,
    )

    assert actions[0]["account_placement"]["broker"] == "Schwab"
    assert brief["rows"][0]["account_placement"]["owner"] == "Parents"
    assert brief["account_placement_rule"]["parent_schwab"] == PARENT_SCHWAB_RULE
