from datetime import date

import options_decay_audit as audit


def _option_row(
    *,
    ticker="HOOD",
    expiry="2026-09-18",
    call_put="call",
    strike=100,
    contracts=2,
    market_value=2886,
    account="Rollover IRA",
):
    return {
        "ticker": ticker,
        "description": f"{strike} {call_put.title()} {expiry}",
        "shares": contracts,
        "market_value": market_value,
        "account": account,
        "owner": "Parents",
        "broker": "Fidelity",
        "tracked": True,
        "asset_type": "option",
        "option": {
            "underlying": ticker,
            "expiry": expiry,
            "call_put": call_put,
            "strike": strike,
            "multiplier": 100,
            "occ_symbol": f"{ticker}  260918C00100000",
        },
    }


def test_no_options_is_quiet_clean_noop():
    report = audit.build_audit({"account_positions": []}, as_of=date(2026, 6, 30))

    assert report["valid"] is True
    assert report["status"] == "quiet"
    assert report["counts"]["option_positions"] == 0
    assert report["alerts"] == []


def test_material_unpriced_premium_inside_decay_window_alerts():
    report = audit.build_audit(
        {"account_positions": [_option_row()]},
        chain_cache={},
        as_of=date(2026, 6, 30),
    )

    row = report["alerts"][0]
    assert report["status"] == "notify"
    assert row["ticker"] == "HOOD"
    assert row["severity"] == "high"
    assert row["dte"] == 80
    assert "material_option_premium_unpriced_inside_decay_window" in row["reasons"]
    assert "underlying_or_fresh_chain_not_checked" in row["data_gaps"]


def test_mostly_extrinsic_premium_alerts_when_underlying_price_available():
    payload = {
        "account_positions": [
            _option_row(),
            {
                "ticker": "HOOD",
                "shares": 10,
                "market_value": 1008.2,
                "asset_type": "Common Stock",
            },
        ]
    }
    report = audit.build_audit(payload, chain_cache={}, as_of=date(2026, 6, 30))

    row = report["alerts"][0]
    assert abs(row["underlying_price"] - 100.82) < 0.001
    assert row["extrinsic_pct_value"] > 0.90
    assert "mostly_extrinsic_premium" in row["reasons"]


def test_near_expiry_material_option_is_critical():
    report = audit.build_audit(
        {
            "account_positions": [
                _option_row(expiry="2026-07-02", market_value=1250),
            ]
        },
        as_of=date(2026, 6, 30),
    )

    row = report["alerts"][0]
    assert row["severity"] == "critical"
    assert "expires_in_2_days" in row["reasons"]


def test_fresh_chain_theta_can_alert_without_book_underlying_position():
    payload = {
        "account_positions": [
            _option_row(ticker="MSFT", expiry="2026-08-21", strike=400, contracts=1, market_value=3200),
        ]
    }
    chain = {
        "_meta": {"as_of": "2026-06-30"},
        "MSFT": {
            "chain": {
                "price_data": {"price": "371.00"},
                "states": [
                    {
                        "expires": "2026-08-21",
                        "option_type": "call",
                        "strike": "400",
                        "theta": "-0.50",
                        "iv": "0.42",
                        "delta": "0.35",
                        "open_interest": 1000,
                        "volume": 25,
                    }
                ],
            }
        },
    }
    report = audit.build_audit(payload, chain_cache=chain, as_of=date(2026, 6, 30))

    row = report["alerts"][0]
    assert row["ticker"] == "MSFT"
    assert row["theta_week_pct_value"] > 0.10
    assert "theta_decay_exceeds_10pct_of_value_per_week" in row["reasons"]
    assert "matching_fresh_chain_contract_not_checked" not in row["data_gaps"]
