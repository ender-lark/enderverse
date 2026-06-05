import json

import position_reconciliation as pr


CURRENT_COMBINED = {
    "files": [
        {
            "source_file": "SKB_fidelity.pdf",
            "broker": "Fidelity",
            "positions_scope": "per_account",
            "positions": [
                {"symbol": "NVDA", "description": "NVIDIA", "market_value": 1200, "quantity": 12, "account_name": "Taxable"},
                {"symbol": "GOOGL", "description": "Alphabet", "market_value": 800, "quantity": 4, "account_name": "Taxable"},
                {"symbol": "GS", "description": "Goldman", "market_value": 0, "quantity": 0, "account_name": "Taxable"},
            ],
        },
        {
            "source_file": "Parents_schwab.pdf",
            "positions_scope": "aggregate",
            "positions": [
                {"symbol": "SMH", "description": "Semis ETF", "market_value": 2000, "quantity": 20},
                {"symbol": "XLF", "description": "Financials", "market_value": 300, "quantity": 5},
            ],
        },
    ],
    "portfolio_summary": {
        "total_market_value": 4300,
        "total_cash": 100,
        "as_of": "2026-06-05T14:00:00",
    },
}


THESES = [{"ticker": "NVDA"}, {"ticker": "GOOGL"}, {"ticker": "SMH"}]


def test_account_position_rows_preserve_owner_broker_account_and_tracking():
    rows = pr.account_position_rows(CURRENT_COMBINED, THESES)
    by = {(r["account"], r["ticker"]): r for r in rows}

    assert by[("Taxable", "NVDA")]["owner"] == "SKB"
    assert by[("Taxable", "NVDA")]["broker"] == "Fidelity"
    assert by[("Taxable", "NVDA")]["tracked"] is True
    assert by[("Aggregate", "SMH")]["owner"] == "Parents"
    assert by[("Aggregate", "XLF")]["tracked"] is False


def test_build_account_positions_outputs_combined_and_tracked_combined():
    cache = pr.build_account_positions(CURRENT_COMBINED, THESES)

    assert cache["snapshot_date"] == "2026-06-05"
    assert cache["sleeve_value"] == 4400
    assert {p["ticker"] for p in cache["combined_positions"]} == {"NVDA", "GOOGL", "SMH", "XLF"}
    assert {p["ticker"] for p in cache["tracked_combined_positions"]} == {"NVDA", "GOOGL", "SMH"}
    assert pr.validate_account_positions(cache) == []


def test_reconcile_positions_classifies_new_add_trim_and_exit():
    prior = {
        "snapshot_date": "2026-06-04",
        "account_positions": [
            {"ticker": "NVDA", "shares": 10, "market_value": 1000, "account": "Taxable", "owner": "SKB", "broker": "Fidelity", "tracked": True},
            {"ticker": "SMH", "shares": 25, "market_value": 2500, "account": "Aggregate", "owner": "Parents", "broker": "Schwab", "tracked": True},
            {"ticker": "GS", "shares": 1, "market_value": 500, "account": "Taxable", "owner": "SKB", "broker": "Fidelity", "tracked": False},
        ],
    }
    current = pr.build_account_positions(CURRENT_COMBINED, THESES)
    report = pr.reconcile_positions(prior, current)
    changes = {(c["account"], c["ticker"]): c for c in report["changes"]}

    assert changes[("Taxable", "GOOGL")]["action"] == "NEW"
    assert changes[("Taxable", "NVDA")]["action"] == "ADD"
    assert changes[("Aggregate", "SMH")]["action"] == "TRIM"
    assert changes[("Taxable", "GS")]["action"] == "EXIT"
    assert report["counts"] == {"NEW": 2, "EXIT": 1, "ADD": 1, "TRIM": 1}


def test_value_change_without_share_change_is_not_a_trade_but_is_reported():
    prev = {"ticker": "NVDA", "shares": 10, "market_value": 1000, "account": "A"}
    curr = {"ticker": "NVDA", "shares": 10, "market_value": 1100, "account": "A"}
    change = pr.classify_change(prev, curr)

    assert change["action"] == "VALUE_CHANGE"
    assert change["market_value_delta"] == 100


def test_cli_writes_account_and_reconcile_outputs(tmp_path):
    combined = tmp_path / "combined.json"
    prior = tmp_path / "prior_account_positions.json"
    theses = tmp_path / "theses.json"
    account_out = tmp_path / "account_positions.json"
    reconcile_out = tmp_path / "position_reconciliation.json"
    combined.write_text(json.dumps(CURRENT_COMBINED), encoding="utf-8")
    theses.write_text(json.dumps(THESES), encoding="utf-8")
    prior.write_text(json.dumps({
        "snapshot_date": "2026-06-04",
        "account_positions": [
            {"ticker": "NVDA", "shares": 10, "market_value": 1000, "account": "Taxable", "owner": "SKB", "broker": "Fidelity", "tracked": True},
        ],
    }), encoding="utf-8")

    rc = pr.main([
        "--combined", str(combined),
        "--theses", str(theses),
        "--prior-account-positions", str(prior),
        "--account-out", str(account_out),
        "--reconcile-out", str(reconcile_out),
    ])

    assert rc == 0
    assert account_out.exists()
    assert reconcile_out.exists()
    assert json.loads(reconcile_out.read_text(encoding="utf-8"))["changes"]


def test_cli_missing_prior_writes_not_checked_reconciliation(tmp_path):
    combined = tmp_path / "combined.json"
    theses = tmp_path / "theses.json"
    account_out = tmp_path / "account_positions.json"
    reconcile_out = tmp_path / "position_reconciliation.json"
    combined.write_text(json.dumps(CURRENT_COMBINED), encoding="utf-8")
    theses.write_text(json.dumps(THESES), encoding="utf-8")

    rc = pr.main([
        "--combined", str(combined),
        "--theses", str(theses),
        "--prior-account-positions", str(tmp_path / "missing_prior.json"),
        "--account-out", str(account_out),
        "--reconcile-out", str(reconcile_out),
    ])
    report = json.loads(reconcile_out.read_text(encoding="utf-8"))

    assert rc == 0
    assert report["status"] == "not_checked"
    assert report["changes"] == []
