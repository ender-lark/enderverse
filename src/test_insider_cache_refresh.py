import json

import insider_cache_refresh as icr
from codex_uw.endpoints import UWEndpoints
from codex_uw.rest_client import UWConfigError


class FakeClient:
    def __init__(self, payload=None):
        self.payload = payload or {"data": []}
        self.calls = []

    def get_json(self, path_template, *, path_params=None, params=None):
        self.calls.append((path_template, path_params or {}, params or {}))
        return self.payload


def test_fetch_insider_cache_uses_uw_transactions_and_normalizes_form4_rows():
    client = FakeClient({
        "data": [{
            "ticker": "NVDA",
            "transaction_code": "P",
            "officer_title": "COB and CEO",
            "owner_name": "Jane Doe",
            "amount": "1000",
            "price": "120",
            "transaction_date": "2026-06-01",
            "filing_date": "2026-06-03",
            "formtype": "4",
            "is_10b5_1": False,
        }]
    })

    payload = icr.fetch_insider_cache(
        ["nvda", "mu"],
        client=client,
        start_date="2026-05-01",
        checked_at="2026-06-14",
    )

    assert client.calls[0][0] == UWEndpoints.INSIDER_TRANSACTIONS
    assert client.calls[0][2]["ticker_symbol"] == "NVDA,MU"
    assert payload["_meta"]["status"] == "has_data"
    assert payload["_meta"]["transaction_count"] == 1
    assert payload["NVDA"][0]["value"] == 120000.0
    assert payload["NVDA"][0]["formtype"] == "4"
    assert payload["NVDA"][0]["filing_date"] == "2026-06-03"
    assert payload["MU"] == []


def test_successful_zero_row_pull_is_checked_clear_not_stub():
    payload = icr.fetch_insider_cache(
        ["NVDA"],
        client=FakeClient({"data": []}),
        checked_at="2026-06-14",
    )

    assert payload["_meta"]["status"] == "checked_clear"
    assert payload["_meta"]["transaction_count"] == 0
    assert payload["NVDA"] == []


def test_missing_token_becomes_not_checked_payload():
    def factory(**kwargs):
        raise UWConfigError("UW_API_KEY is not set")

    payload = icr.fetch_insider_cache(
        ["NVDA"],
        client_factory=factory,
        checked_at="2026-06-14",
    )

    assert payload["_meta"]["status"] == "not_checked"
    assert "UW_API_KEY" in payload["_meta"]["reason"]
    assert payload["NVDA"] == []


def test_validate_cache_requires_metadata_and_transaction_fields(tmp_path):
    path = tmp_path / "insider_data.json"
    payload = icr.fetch_insider_cache(
        ["NVDA"],
        client=FakeClient({"data": []}),
        checked_at="2026-06-14",
    )
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert icr.validate_cache(json.loads(path.read_text(encoding="utf-8"))) == []
    assert "missing _meta" in icr.validate_cache({"NVDA": []})
