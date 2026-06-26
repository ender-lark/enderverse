from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
import sys
import urllib.error

import pytest

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
                            "balance": {"total": {"amount": 2340.71}},
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
    assert row["reported_total"] == 2340.71
    assert row["validation"]["reported_total"] == 2340.71
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


# ─────────────────────────────────────────────────────────────────────────────
# 2026-06-26 hardening: retry-alone + backoff, no-retry-on-auth, re-sign each
# attempt, sequential pacing, and the echo-corroboration guard. All mocked — no
# live SnapTrade API. Spec: docs/codex_tasks/snaptrade_serial_access_hardening_2026_06_26.md
# ─────────────────────────────────────────────────────────────────────────────

def _client(**kw):
    # explicit creds so __init__ never touches the env; backoff_base 0 = instant retries
    return spi.SnapTradeClient(client_id="cid", consumer_key="ckey", backoff_base=0.0, **kw)


class _Resp:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_error(code, detail=b"boom"):
    return urllib.error.HTTPError("https://api.snaptrade.com/api/v1/x", code, "err", {}, io.BytesIO(detail))


def _patch_urlopen(monkeypatch, side_effects, capture=None):
    it = iter(side_effects)
    calls = {"n": 0}

    def fake(req, timeout=None):
        calls["n"] += 1
        if capture is not None:
            capture.append(req.full_url)
        item = next(it)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr("urllib.request.urlopen", fake)
    return calls


def test_request_retries_transient_timeout_then_succeeds(monkeypatch):
    calls = _patch_urlopen(monkeypatch, [TimeoutError("timed out"), _Resp({"ok": True})])
    assert _client(max_attempts=3).request("GET", "/accounts") == {"ok": True}
    assert calls["n"] == 2  # one timeout + one success


def test_request_retries_503_then_succeeds(monkeypatch):
    calls = _patch_urlopen(monkeypatch, [_http_error(503), _Resp({"ok": 1})])
    assert _client(max_attempts=3).request("GET", "/x") == {"ok": 1}
    assert calls["n"] == 2


def test_request_does_not_retry_auth_4xx(monkeypatch):
    calls = _patch_urlopen(monkeypatch, [_http_error(401, b"bad signature"), _Resp({"ok": 1})])
    with pytest.raises(spi.SnapTradeError) as ei:
        _client(max_attempts=3).request("GET", "/x")
    assert "401" in str(ei.value)
    assert calls["n"] == 1  # auth failure fails fast — no retry


def test_request_exhausts_retries_and_raises(monkeypatch):
    calls = _patch_urlopen(monkeypatch, [TimeoutError("t")] * 5)
    with pytest.raises(spi.SnapTradeError) as ei:
        _client(max_attempts=3).request("GET", "/x")
    assert "after 3 attempts" in str(ei.value)
    assert calls["n"] == 3


def test_request_resigns_with_fresh_timestamp_each_attempt(monkeypatch):
    seen = []
    _patch_urlopen(monkeypatch, [TimeoutError("t"), _Resp({"ok": 1})], capture=seen)
    times = iter([1000, 1001, 1002, 1003])
    monkeypatch.setattr(spi.time, "time", lambda: next(times))
    _client(max_attempts=3).request("GET", "/accounts")
    assert len(seen) == 2
    assert "timestamp=1000" in seen[0] and "timestamp=1001" in seen[1]  # re-signed, not reused


class _FakeClient:
    """A SnapTradeClient stand-in for pull_profiles. `snapshot(account_id, round)` returns one
    account's holdings for that pull round, so the echo re-pull can change on the 2nd round."""

    def __init__(self, accounts, snapshot, *, degraded=False):
        self.accounts = accounts
        self.snapshot = snapshot
        self.degraded = degraded
        self._round = {}
        self._next = {}

    def list_connections(self, uid, sec):
        return [{"id": "conn", "is_degraded": self.degraded}]

    def list_accounts(self, uid, sec):
        return self.accounts

    def account_positions(self, aid, uid, sec):
        r = self._next.get(aid, 0)
        self._round[aid] = r
        self._next[aid] = r + 1
        return self.snapshot(aid, r)["positions"]

    def option_positions(self, aid, uid, sec):
        return self.snapshot(aid, self._round.get(aid, 0))["option_positions"]

    def account_balances(self, aid, uid, sec):
        return self.snapshot(aid, self._round.get(aid, 0))["balances"]


def _profile():
    return {"profile": "p1", "user_id": "u1", "user_secret": "s1", "owner": "Suraj"}


def _accts(*ids):
    return [{"id": i, "name": f"Acct {i}", "brokerage_authorization": "conn"} for i in ids]


def _distinct(aid, _round):
    return {"positions": [{"symbol": f"SYM_{aid}", "mv": 1}], "option_positions": [],
            "balances": [{"cash": 100 + len(aid)}]}


def _echo_then_distinct(aid, rnd):
    if rnd == 0:  # first pull: every account returns the IDENTICAL holdings (the echo bug)
        return {"positions": [{"symbol": "NVDA", "mv": 100}], "option_positions": [],
                "balances": [{"cash": -2187.71}]}
    return _distinct(aid, rnd)  # re-pull resolves to distinct


def test_pull_profiles_paces_each_account_and_stays_sequential(monkeypatch):
    sleeps = []
    monkeypatch.setattr(spi.time, "sleep", lambda s: sleeps.append(s))
    out = spi.pull_profiles(_FakeClient(_accts("A", "B"), _distinct), [_profile()], pace_seconds=0.2)
    assert sleeps == [0.2, 0.2]  # one pace per account, no echo re-pull
    assert [a["account"]["id"] for a in out["profiles"][0]["accounts"]] == ["A", "B"]
    assert out["echo_corroboration"]["suspects"] == []


def test_pull_profiles_degraded_connection_is_not_fatal():
    out = spi.pull_profiles(_FakeClient(_accts("A"), _distinct, degraded=True), [_profile()], pace_seconds=0)
    rows = out["profiles"][0]["accounts"]
    assert len(rows) == 1  # a degraded connection still yields a row
    assert rows[0]["connection"]["is_degraded"] is True


def test_pull_profiles_repulls_echoed_accounts_and_resolves():
    client = _FakeClient(_accts("A", "B"), _echo_then_distinct)
    out = spi.pull_profiles(client, [_profile()], pace_seconds=0)
    ec = out["echo_corroboration"]
    assert ec["suspects"] == [["A", "B"]]      # caught the identical-across-accounts echo
    assert ec["repulled"] == ["A", "B"]        # re-pulled each one alone
    assert ec["unresolved"] == []              # re-pull resolved them to distinct holdings
    rows = {a["account"]["id"]: a for a in out["profiles"][0]["accounts"]}
    assert rows["A"]["positions"] != rows["B"]["positions"]


def test_pull_profiles_flags_unresolved_echo_loudly():
    # an account that STILL echoes after re-pull must stay flagged, never silently trusted
    out = spi.pull_profiles(_FakeClient(_accts("A", "B"), lambda aid, r: _echo_then_distinct("X", 0)),
                            [_profile()], pace_seconds=0)
    assert out["echo_corroboration"]["unresolved"] == [["A", "B"]]


def test_find_echoed_accounts_flags_identical_distinct_accounts():
    out = {"profiles": [{"accounts": [
        {"account": {"id": "A"}, "positions": [{"s": "NVDA"}], "balances": [{"cash": -2187.71}], "option_positions": []},
        {"account": {"id": "B"}, "positions": [{"s": "NVDA"}], "balances": [{"cash": -2187.71}], "option_positions": []},
    ]}]}
    assert spi.find_echoed_accounts(out) == [["A", "B"]]


def test_find_echoed_accounts_ignores_empty_and_distinct():
    out = {"profiles": [{"accounts": [
        {"account": {"id": "A"}, "positions": [], "balances": [], "option_positions": []},  # empty — ok to match
        {"account": {"id": "B"}, "positions": [], "balances": [], "option_positions": []},
        {"account": {"id": "C"}, "positions": [{"s": "X"}], "balances": [{"cash": 1}], "option_positions": []},
        {"account": {"id": "D"}, "positions": [{"s": "Y"}], "balances": [{"cash": 2}], "option_positions": []},
    ]}]}
    assert spi.find_echoed_accounts(out) == []
