from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import snaptrade_positions_import as spi


def test_compute_request_signature_matches_hmac_contract():
    path = "/snapTrade/registerUser?clientId=PASSIVTEST&timestamp=1635790389"
    body = {"userId": "new_user_123"}
    payload = {
        "content": body,
        "path": "/api/v1/snapTrade/registerUser",
        "query": "clientId=PASSIVTEST&timestamp=1635790389",
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    expected = base64.b64encode(
        hmac.new(b"secret", canonical.encode("utf-8"), hashlib.sha256).digest()
    ).decode("ascii")

    assert spi.compute_request_signature(path, "secret", body) == expected


def test_credential_status_does_not_print_secret_values(monkeypatch):
    monkeypatch.setenv("SNAPTRADE_CLIENT_ID", "client-id")
    monkeypatch.setenv("SNAPTRADE_CONSUMER_KEY", "consumer-key")

    status = spi.credential_status()

    assert status == [
        {"name": "SNAPTRADE_CLIENT_ID", "present": True, "length": 9},
        {"name": "SNAPTRADE_CONSUMER_KEY", "present": True, "length": 12},
    ]


def _symbol(symbol="NVDA", description="NVIDIA CORP"):
    return {
        "symbol": {
            "symbol": {
                "symbol": symbol,
                "raw_symbol": symbol,
                "description": description,
                "type": {"description": "Common Stock"},
            }
        }
    }


def test_build_combined_from_snaptrade_preserves_owner_account_broker_and_cash():
    payload = {
        "profiles": [
            {
                "profile": "suraj",
                "owner": "SKB",
                "accounts": [
                    {
                        "account": {
                            "id": "acct-1",
                            "name": "Fidelity Taxable",
                            "number": "...1234",
                            "institution_name": "Fidelity",
                        },
                        "positions": [
                            {
                                **_symbol("NVDA", "NVIDIA CORP"),
                                "units": 12,
                                "price": 170,
                                "average_purchase_price": 100,
                            }
                        ],
                        "option_positions": [],
                        "balances": [
                            {"currency": {"code": "USD"}, "cash": 300.71},
                        ],
                    }
                ],
            }
        ]
    }

    combined = spi.build_combined_from_snaptrade(
        payload,
        as_of="2026-06-07T20:00:00Z",
        generated_at="2026-06-07T20:00:00Z",
    )

    assert combined["portfolio_summary"] == {
        "total_market_value": 2040.0,
        "total_cash": 300.71,
        "as_of": "2026-06-07T20:00:00Z",
    }
    row = combined["files"][0]
    assert row["owner"] == "SKB"
    assert row["broker"] == "Fidelity"
    assert row["account_name"] == "Fidelity Taxable ...1234"
    assert row["positions"][0]["symbol"] == "NVDA"
    assert row["positions"][0]["quantity"] == 12.0
    assert row["positions"][0]["market_value"] == 2040.0


def test_option_position_uses_underlying_and_contract_multiplier():
    payload = {
        "profiles": [
            {
                "profile": "parents",
                "owner": "Parents",
                "accounts": [
                    {
                        "account": {
                            "id": "acct-2",
                            "name": "Schwab IRA",
                            "institution_name": "Schwab",
                        },
                        "positions": [],
                        "option_positions": [
                            {
                                "symbol": {
                                    "option_symbol": {
                                        "ticker": "BMNR260821C00050000",
                                        "option_type": "CALL",
                                        "strike_price": 50,
                                        "expiration_date": "2026-08-21",
                                        "is_mini_option": False,
                                        "underlying_symbol": {
                                            "symbol": "BMNR",
                                            "raw_symbol": "BMNR",
                                        },
                                    }
                                },
                                "units": 5,
                                "price": 3.55,
                            }
                        ],
                        "balances": [],
                    }
                ],
            }
        ]
    }

    combined = spi.build_combined_from_snaptrade(payload)
    pos = combined["files"][0]["positions"][0]

    assert pos["symbol"] == "BMNR"
    assert pos["asset_type"] == "option"
    assert pos["market_value"] == 1775.0
    assert pos["option"]["multiplier"] == 100
    assert pos["option"]["call_put"] == "call"
    assert pos["option"]["price_convention"] == "underlying_share"


def test_robinhood_option_price_is_contract_value_not_share_price():
    payload = {
        "profiles": [
            {
                "profile": "suraj",
                "owner": "SKB",
                "accounts": [
                    {
                        "account": {
                            "id": "acct-rh",
                            "name": "Robinhood Individual",
                            "institution_name": "Robinhood",
                        },
                        "positions": [],
                        "option_positions": [
                            {
                                "symbol": {
                                    "option_symbol": {
                                        "ticker": "BMNR  280121C00030000",
                                        "option_type": "CALL",
                                        "strike_price": 30,
                                        "expiration_date": "2028-01-21",
                                        "is_mini_option": False,
                                        "underlying_symbol": {
                                            "symbol": "BMNR",
                                            "raw_symbol": "BMNR",
                                        },
                                    }
                                },
                                "units": 4,
                                "price": 448.0,
                            }
                        ],
                        "balances": [],
                    }
                ],
            }
        ]
    }

    combined = spi.build_combined_from_snaptrade(payload)
    pos = combined["files"][0]["positions"][0]

    assert pos["symbol"] == "BMNR"
    assert pos["description"] == "30 Call 2028-01-21"
    assert pos["quantity"] == 4.0
    assert pos["market_value"] == 1792.0
    assert pos["option"]["price_convention"] == "contract"


def test_zero_value_custody_placeholders_are_not_positions():
    payload = {
        "profiles": [
            {
                "profile": "parents",
                "owner": "Parents",
                "accounts": [
                    {
                        "account": {
                            "id": "acct-3",
                            "name": "Fidelity IRA",
                            "institution_name": "Fidelity",
                        },
                        "positions": [
                            {
                                **_symbol("NVDA", "NVIDIA CORP"),
                                "units": 2,
                                "price": 200,
                            },
                            {
                                **_symbol("L0C990030", "COLLATERAL DELV TO COMPUTERSHARE"),
                                "units": 10,
                                "price": 0,
                                "market_value": 0,
                            },
                            {
                                **_symbol("715ESC018", "PERSHING SQUAR ESCROW"),
                                "units": 10,
                                "price": 0,
                                "market_value": 0,
                            },
                        ],
                        "option_positions": [],
                        "balances": [],
                    }
                ],
            }
        ]
    }

    combined = spi.build_combined_from_snaptrade(payload)
    positions = combined["files"][0]["positions"]

    assert [pos["symbol"] for pos in positions] == ["NVDA"]


def test_resolve_profile_secret_reads_named_env(monkeypatch):
    monkeypatch.setenv("SNAPTRADE_TEST_USER_SECRET", "secret-value")

    assert spi.resolve_profile_secret({
        "profile": "test",
        "user_secret_env": "SNAPTRADE_TEST_USER_SECRET",
    }) == "secret-value"


def test_owner_for_account_supports_account_overrides():
    profile = {
        "profile": "household",
        "owner": "Unassigned",
        "account_owner_overrides": [
            {"account_id": "acct-parents", "owner": "Parents"},
            {"account_name_contains": "taxable", "owner": "SKB"},
        ],
    }

    assert spi.owner_for_account(profile, {"id": "acct-parents", "name": "IRA"}) == "Parents"
    assert spi.owner_for_account(profile, {"id": "acct-skb", "name": "Fidelity Taxable"}) == "SKB"
    assert spi.owner_for_account(profile, {"id": "acct-new", "name": "Unknown"}) == "Unassigned"
