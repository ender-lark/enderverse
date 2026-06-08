from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import snaptrade_book_refresh as sbr


def _symbol(symbol="NVDA"):
    return {
        "symbol": {
            "symbol": {
                "symbol": symbol,
                "raw_symbol": symbol,
                "description": f"{symbol} DESC",
                "type": {"description": "Common Stock"},
            }
        }
    }


def _payload():
    return {
        "profiles": [
            {
                "profile": "household",
                "owner": "SKB",
                "user_id": "user",
                "accounts": [
                    {
                        "account": {
                            "id": "acct-1",
                            "name": "Taxable",
                            "institution_name": "Fidelity",
                        },
                        "positions": [{**_symbol("NVDA"), "units": 2, "price": 200}],
                        "option_positions": [],
                        "balances": [{"currency": {"code": "USD"}, "cash": 50}],
                    }
                ],
            }
        ]
    }


def _patch_snaptrade(monkeypatch, payload=None):
    monkeypatch.setattr(sbr.snaptrade, "SnapTradeClient", lambda: object())
    monkeypatch.setattr(sbr.snaptrade, "read_profiles", lambda path: [{"profile": "household"}])
    monkeypatch.setattr(sbr.snaptrade, "pull_profiles", lambda client, profiles: payload or _payload())


def test_book_refresh_promotes_valid_snaptrade_pull(tmp_path, monkeypatch):
    _patch_snaptrade(monkeypatch)
    theses = tmp_path / "theses.json"
    theses.write_text(json.dumps([{"ticker": "NVDA"}]), encoding="utf-8")
    prior_account = tmp_path / "account_positions.json"
    prior_account.write_text(json.dumps({"snapshot_date": "2026-06-07", "account_positions": []}), encoding="utf-8")

    report = sbr.build_staged_book(
        profiles_path=tmp_path / "profiles.json",
        theses_path=theses,
        raw_out=tmp_path / "raw.json",
        combined_out=tmp_path / "combined.json",
        positions_out=tmp_path / "positions.json",
        account_out=prior_account,
        reconcile_out=tmp_path / "position_reconciliation.json",
    )

    assert report["valid"] is True
    assert report["promoted"] is True
    assert report["snapshot_date"]
    assert report["thesis_positions"] == 1
    assert report["account_rows"] == 1
    positions = json.loads((tmp_path / "positions.json").read_text(encoding="utf-8"))
    assert positions["positions"][0]["ticker"] == "NVDA"
    assert positions["sleeve_value"] == 450


def test_book_refresh_no_promote_leaves_live_files_untouched(tmp_path, monkeypatch):
    _patch_snaptrade(monkeypatch)
    theses = tmp_path / "theses.json"
    theses.write_text(json.dumps([{"ticker": "NVDA"}]), encoding="utf-8")
    positions = tmp_path / "positions.json"
    positions.write_text(json.dumps({"snapshot_date": "old", "positions": []}), encoding="utf-8")

    report = sbr.build_staged_book(
        profiles_path=tmp_path / "profiles.json",
        theses_path=theses,
        raw_out=tmp_path / "raw.json",
        combined_out=tmp_path / "combined.json",
        positions_out=positions,
        account_out=tmp_path / "account_positions.json",
        reconcile_out=tmp_path / "position_reconciliation.json",
        promote=False,
    )

    assert report["promoted"] is False
    assert json.loads(positions.read_text(encoding="utf-8"))["snapshot_date"] == "old"
    assert (tmp_path / "snaptrade_positions.staged.json").is_file()


def test_book_refresh_stops_before_promote_when_combined_invalid(tmp_path, monkeypatch):
    _patch_snaptrade(monkeypatch, payload={"profiles": []})
    theses = tmp_path / "theses.json"
    theses.write_text(json.dumps([{"ticker": "NVDA"}]), encoding="utf-8")
    positions = tmp_path / "positions.json"
    positions.write_text(json.dumps({"snapshot_date": "old", "positions": []}), encoding="utf-8")

    try:
        sbr.build_staged_book(
            profiles_path=tmp_path / "profiles.json",
            theses_path=theses,
            raw_out=tmp_path / "raw.json",
            combined_out=tmp_path / "combined.json",
            positions_out=positions,
            account_out=tmp_path / "account_positions.json",
            reconcile_out=tmp_path / "position_reconciliation.json",
        )
    except sbr.BookRefreshError as exc:
        assert "combined validation failed" in str(exc)
    else:
        raise AssertionError("expected invalid combined snapshot to fail")
    assert json.loads(positions.read_text(encoding="utf-8"))["snapshot_date"] == "old"
