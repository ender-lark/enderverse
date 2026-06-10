import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from execution_plan import (
    AccountsMissingError,
    classify_account,
    funding_reality_check,
    load_accounts,
    load_rules,
    plan_buy,
    plan_sell,
)

def _acct(owner, broker, account, total, holdings, etf_only=False, crypto_only=False,
          tax_type="taxable", tax_flag="TAXABLE â€” gains realize"):
    return {
        "owner": owner, "broker": broker, "account": account,
        "etf_only": etf_only, "crypto_only": crypto_only,
        "tax_type": tax_type, "tax_flag": tax_flag,
        "total_value": total, "holdings": dict(holdings), "option_value": 0.0,
    }

def _accounts():
    return [
        _acct("Parents", "Fidelity", "Joint WROS", 612000.0,
              {"NVDA": 50000.0, "MAGS": 20000.0}),
        _acct("Parents", "Schwab", "PCRA Trust", 368000.0,
              {"MAGS": 19710.0, "SMH": 30000.0}, etf_only=True,
              tax_type="traditional_ira", tax_flag="tax-advantaged (no cap-gains)"),
        _acct("SKB", "Robinhood", "Trad IRA", 180000.0, {"GOOGL": 10000.0},
              tax_type="traditional_ira", tax_flag="tax-advantaged (no cap-gains)"),
        _acct("SKB", "Robinhood", "Crypto", 1000.0, {}, crypto_only=True),
    ]

def test_classify_account_rules_cover_the_book():
    rules = load_rules()
    pcra = classify_account("Schwab PCRA Trust", "Parents", "Schwab", rules)
    assert pcra["etf_only"] is True
    rollover = classify_account("Rollover IRA", "Parents", "Fidelity", rules)
    assert rollover["tax_type"] == "traditional_ira" and "tax-advantaged" in rollover["tax_flag"]
    roth = classify_account("Roth IRA", "SKB", "Robinhood", rules)
    assert roth["tax_type"] == "roth"
    hsa = classify_account("Health Savings Account", "SKB", "Fidelity", rules)
    assert hsa["tax_type"] == "hsa"
    ind = classify_account("Individual", "SKB", "Schwab", rules)
    assert ind["tax_type"] == "taxable" and "TAXABLE" in ind["tax_flag"]
    crypto = classify_account("Robinhood Crypto", "SKB", "Robinhood", rules)
    assert crypto["crypto_only"] is True

def test_plan_buy_stock_excludes_pcra_with_hard_rule():
    plan = plan_buy("NVDA", 50000, accounts=_accounts(), is_etf=False)
    why = {e["account"]: e["why_not"] for e in plan["excluded"]}
    assert any("PCRA" in a for a in why)
    assert any("ETF-ONLY" in w for w in why.values())
    assert any("crypto-only" in w for w in why.values())
    assert all("PCRA" not in l["account"] for l in plan["eligible"])

def test_plan_buy_prefers_existing_position_then_capacity():
    googl = plan_buy("GOOGL", 25000, accounts=_accounts(), is_etf=False)
    assert "Trad IRA" in googl["suggested"]["account"]
    assert "add-to-position" in googl["suggested"]["why"]
    msft = plan_buy("MSFT", 25000, accounts=_accounts(), is_etf=False)
    assert "Joint" in msft["suggested"]["account"]
    assert "largest eligible" in msft["suggested"]["why"]
    assert msft["suggested"]["suggested_usd"] == 25000

def test_plan_buy_etf_can_route_into_pcra():
    plan = plan_buy("SMH", 10000, accounts=_accounts(), is_etf=True)
    assert "PCRA" in plan["suggested"]["account"]  # largest existing SMH position

def test_plan_sell_drains_largest_first_and_reports_unfilled():
    plan = plan_sell("MAGS", 50000, accounts=_accounts(), funded_buys_are_etf=True)
    assert [l["sell_usd"] for l in plan["legs"]] == [20000.0, 19710.0]
    assert "Joint" in plan["legs"][0]["account"]
    assert plan["unfilled_usd"] == pytest.approx(10290.0)
    assert "unfilled_note" in plan

def test_pcra_proceeds_constraint_and_transfer_flag():
    stock_funded = plan_sell("MAGS", 30000, accounts=_accounts(), funded_buys_are_etf=False)
    pcra_leg = [l for l in stock_funded["legs"] if "PCRA" in l["account"]][0]
    assert "proceeds_constraint" in pcra_leg
    assert stock_funded["transfer_dependency"] is True
    assert "operator" in stock_funded["transfer_note"]
    etf_funded = plan_sell("MAGS", 30000, accounts=_accounts(), funded_buys_are_etf=True)
    assert etf_funded["transfer_dependency"] is False

def test_funding_reality_check_computes_trapped_proceeds():
    trims = [{"ticker": "MAGS", "notional_usd": 39710}]
    stock = funding_reality_check(trims, [{"ticker": "NVDA"}],
                                  accounts=_accounts(), etf_tickers={"MAGS", "SMH"})
    assert stock["stock_adds_present"] is True
    assert stock["pcra_trapped_usd"] == pytest.approx(19710.0)
    assert stock["transfer_required_for_full_plan"] is True
    etf = funding_reality_check(trims, [{"ticker": "SMH"}],
                                accounts=_accounts(), etf_tickers={"MAGS", "SMH"})
    assert etf["transfer_required_for_full_plan"] is False

def test_cash_honesty_and_missing_cache(tmp_path):
    plan = plan_buy("NVDA", 1000, accounts=_accounts(), is_etf=False)
    assert plan["cash"].startswith("not_checked")
    with pytest.raises(AccountsMissingError):
        load_accounts(positions_path=tmp_path / "absent.json")
