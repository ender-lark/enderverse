import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import action_memory_resolve as resolver
import open_opportunities as oo


def test_list_open_action_rows_normalizes_and_sorts():
    store = {"opportunities": [
        {"ticker": "GOOGL", "first_flagged": "2026-06-05", "status": "open"},
        {"ticker": "BAD"},
        {"ticker": "ANET", "first_flagged": "2026-06-04", "status": "open"},
    ]}

    rows = resolver.open_action_rows(store)

    assert [r["ticker"] for r in rows] == ["ANET", "GOOGL"]


def test_resolve_open_actions_writes_history(tmp_path):
    store_path = tmp_path / "open_opportunities.json"
    store = oo.seed_open_opportunities([
        {"ticker": "ANET", "first_flagged": "2026-06-05", "source": "lean_in"},
    ], as_of="2026-06-05")
    store_path.write_text(json.dumps(store), encoding="utf-8")

    summary = resolver.resolve_open_actions(
        store_path=store_path,
        resolutions=[{"ticker": "ANET", "status": "deferred", "reason": "wait for setup"}],
        as_of="2026-06-06",
    )

    assert summary["open_count"] == 0
    assert summary["resolved"][0]["ticker"] == "ANET"
    saved = json.loads(store_path.read_text(encoding="utf-8"))
    assert saved["history"][0]["status"] == "deferred"
    assert saved["history"][0]["reason"] == "wait for setup"


def test_resolve_open_actions_dry_run_does_not_write(tmp_path):
    store_path = tmp_path / "open_opportunities.json"
    store = oo.seed_open_opportunities([
        {"ticker": "GOOGL", "first_flagged": "2026-06-05"},
    ], as_of="2026-06-05")
    store_path.write_text(json.dumps(store), encoding="utf-8")

    summary = resolver.resolve_open_actions(
        store_path=store_path,
        resolutions=[{"ticker": "GOOGL", "status": "ignored", "reason": "no edge"}],
        as_of="2026-06-06",
        dry_run=True,
    )

    assert summary["open_count"] == 0
    saved = json.loads(store_path.read_text(encoding="utf-8"))
    assert saved["opportunities"][0]["ticker"] == "GOOGL"
    assert saved.get("history", []) == []


def test_cli_lists_open_items(tmp_path, capsys):
    store_path = tmp_path / "open_opportunities.json"
    store = oo.seed_open_opportunities([
        {"ticker": "ANET", "first_flagged": "2026-06-05"},
    ], as_of="2026-06-05")
    store_path.write_text(json.dumps(store), encoding="utf-8")

    assert resolver.main(["--store", str(store_path), "--list"]) == 0
    out = capsys.readouterr().out
    assert '"ticker": "ANET"' in out


def test_review_report_includes_age_and_resolution_commands(tmp_path):
    store_path = tmp_path / "open_opportunities.json"
    store = oo.seed_open_opportunities([
        {"ticker": "GOOGL", "first_flagged": "2026-06-05", "source": "lean_in"},
        {"ticker": "ANET", "first_flagged": "2026-06-04", "source": "lean_in"},
    ], as_of="2026-06-05")
    store_path.write_text(json.dumps(store), encoding="utf-8")

    report = resolver.review_report(store_path=store_path, as_of="2026-06-09")

    assert report["open_count"] == 2
    assert report["oldest_age_days"] == 3
    assert report["rows"][0]["ticker"] == "ANET"
    assert "--status deferred" in report["rows"][0]["commands"]["defer"]
    assert "--status acted" in report["rows"][0]["commands"]["acted"]


def test_cli_review_report_outputs_next_step(tmp_path, capsys):
    store_path = tmp_path / "open_opportunities.json"
    store = oo.seed_open_opportunities([
        {"ticker": "ANET", "first_flagged": "2026-06-05"},
    ], as_of="2026-06-05")
    store_path.write_text(json.dumps(store), encoding="utf-8")

    assert resolver.main(["--store", str(store_path), "--as-of", "2026-06-06", "--review-report"]) == 0
    out = capsys.readouterr().out
    assert "Resolve each row after operator review" in out
    assert "python src/action_memory_resolve.py --ticker ANET" in out
