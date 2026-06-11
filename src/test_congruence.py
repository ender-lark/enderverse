import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from congruence import (
    CongruenceMissingError,
    congruence_from_repo,
    congruence_report,
    exposure,
    load_book_from_account_positions,
    load_book_from_feed,
)

TODAY = "2026-06-10"

def _ins(iid="INSIGHT-901", polarity="bullish", mapped=None, adjacent=None, watch=None):
    return {
        "insight_id": iid,
        "statement": "test thesis",
        "polarity": polarity,
        "belief_strength": 90,
        "status": "ACTIVE",
        "stated": "2026-06-01",
        "last_reviewed": "2026-06-08",
        "sectors": [],
        "keywords": [],
        "tickers_mapped": mapped if mapped is not None else ["GEV", "BE"],
        "tickers_adjacent": adjacent if adjacent is not None else ["VRT"],
        "watch_tickers": watch if watch is not None else ["TLN"],
        "factor_tags": [],
        "evidence_for": [],
        "evidence_against": [],
        "history": [],
    }

_TV = {"GEV": 60000.0, "VRT": 30000.0, "TLN": 10000.0, "TSM": 4268.0, "NVDA": 200000.0}
_TOTAL = 1_890_000.0
_W = {"pattern_thresholds": {"congruence_flag_named_pct": 1.0}, "insight_stale_days": 60}

def test_exposure_buckets_and_missing_named():
    exp = exposure(_ins(), _TV, _TOTAL)
    assert exp["named_held"] == {"GEV": 60000.0} and exp["missing_named"] == ["BE"]
    assert exp["adjacent_held"] == {"VRT": 30000.0}
    assert exp["named_pct"] == pytest.approx(3.17, abs=0.01)
    assert exp["combined_pct"] == pytest.approx(4.76, abs=0.01)
    assert exp["watch_held"] == {"TLN": 10000.0}

def test_flag_fires_on_strongest_belief_smallest_exposure():
    payload = {"insights": [_ins(iid="INSIGHT-903", mapped=["TSM"], adjacent=[], watch=[])]}
    report = congruence_report(payload, _TV, _TOTAL, weights=_W, today=TODAY)
    row = report["rows"][0]
    assert row["named_pct"] == pytest.approx(0.23, abs=0.01)
    assert row["flagged"] is True and "SMALLEST EXPOSURE" in row["flag_note"]
    assert report["flagged_ids"] == ["INSIGHT-903"]

def test_no_flag_when_named_above_threshold():
    report = congruence_report({"insights": [_ins()]}, _TV, _TOTAL, weights=_W, today=TODAY)
    assert report["rows"][0]["flagged"] is False
    assert report["flagged_ids"] == []

def test_risk_polarity_never_flags():
    payload = {"insights": [_ins(iid="INSIGHT-904", polarity="risk", mapped=["TSM"], adjacent=[], watch=[])]}
    report = congruence_report(payload, _TV, _TOTAL, weights=_W, today=TODAY)
    assert report["rows"][0]["flagged"] is False

def test_report_line_is_human_readable():
    report = congruence_report({"insights": [_ins()]}, _TV, _TOTAL, weights=_W, today=TODAY)
    line = report["rows"][0]["line"]
    assert "GEV" in line and "named $" in line and "combined" in line

def test_feed_loader_aggregates_and_validates(tmp_path):
    feed = {"portfolio_views": {"views": {"combined": {
        "rows": [
            {"ticker": "TSM", "market_value": 4268},
            {"ticker": "tsm", "market_value": 1000},
            {"ticker": "GEV", "market_value": 60000},
        ],
        "total_value": 1890000,
    }}}}
    path = tmp_path / "latest_cockpit_feed.json"
    path.write_text(json.dumps(feed), encoding="utf-8")
    tv, total = load_book_from_feed(path)
    assert tv["TSM"] == 5268.0 and tv["GEV"] == 60000.0 and total == 1890000.0
    with pytest.raises(CongruenceMissingError):
        load_book_from_feed(tmp_path / "absent.json")

def test_account_positions_fallback_loader(tmp_path):
    path = tmp_path / "account_positions.json"
    path.write_text(json.dumps({"combined_positions": [
        {"ticker": "NVDA", "market_value": 1000.0},
        {"market_value": 50.0},
    ]}), encoding="utf-8")
    tv, total = load_book_from_account_positions(path)
    assert tv == {"NVDA": 1000.0} and total == 1050.0
    bad = tmp_path / "empty.json"
    bad.write_text(json.dumps({"combined_positions": []}), encoding="utf-8")
    with pytest.raises(CongruenceMissingError):
        load_book_from_account_positions(bad)

def test_congruence_from_repo_honest_empty_then_ok(tmp_path):
    payload = {"insights": [_ins(iid="INSIGHT-903", mapped=["TSM"], adjacent=[], watch=[])]}
    out = congruence_from_repo(
        payload, weights=_W,
        feed_path=tmp_path / "a.json", account_positions_path=tmp_path / "b.json",
        today=TODAY,
    )
    assert out["status"] == "not_checked" and out["rows"] == []
    assert "not checked is not all clear" in out["reason"]
    feed_path = tmp_path / "a.json"
    feed_path.write_text(json.dumps({"portfolio_views": {"views": {"combined": {
        "rows": [{"ticker": "TSM", "market_value": 4268}], "total_value": 1890000}}}}), encoding="utf-8")
    ok = congruence_from_repo(payload, weights=_W, feed_path=feed_path,
                              account_positions_path=tmp_path / "b.json", today=TODAY)
    assert ok["status"] == "ok" and ok["book_source"] == "latest_cockpit_feed.portfolio_views"
    assert ok["flagged_ids"] == ["INSIGHT-903"]
