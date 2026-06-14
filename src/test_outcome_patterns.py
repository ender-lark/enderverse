import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import outcome_patterns as op


def test_detects_three_shared_drivers_in_category():
    report = op.build_report(
        trade_outcomes=[
            {"ticker": "A", "category": "loss", "driver_tags": ["chased parabolic"]},
            {"ticker": "B", "category": "loss", "driver_tags": ["chased parabolic"]},
            {"ticker": "C", "category": "loss", "driver_tags": ["chased parabolic", "oversized"]},
            {"ticker": "D", "category": "loss", "driver_tags": ["late source"]},
        ],
        threshold=3,
        generated_at="2026-06-13T00:00:00Z",
    )

    assert report["status"] == "has_patterns"
    assert report["findings"][0]["line"] == "3 of 4 loss shared chased parabolic"
    assert report["findings"][0]["tickers"] == ["A", "B", "C"]


def test_below_threshold_is_insufficient_sample_not_forced_pattern():
    report = op.build_report(
        decisions=[
            {"ticker": "A", "category": "pass", "driver": "stale evidence"},
            {"ticker": "B", "category": "pass", "driver": "stale evidence"},
        ],
        threshold=3,
    )

    assert report["status"] == "insufficient_sample"
    assert report["findings"] == []
    assert "insufficient sample" in report["insufficient"][0]["line"]


def test_ignores_untagged_prose_reasons():
    report = op.build_report(
        decisions=[
            {"ticker": "A", "category": "pass", "reason": "I was worried about position size"},
            {"ticker": "B", "category": "pass", "reason": "I was worried about position size"},
            {"ticker": "C", "category": "pass", "reason": "I was worried about position size"},
        ]
    )

    assert report["status"] == "not_checked"
    assert report["record_count"] == 0


def test_combines_trade_outcomes_decisions_and_dispositions():
    report = op.build_report(
        trade_outcomes=[
            {"ticker": "A", "Event Type": "FULL_EXIT", "Driver Tags": "stale thesis"},
        ],
        decisions=[
            {"ticker": "B", "verb": "PASS", "driver_tags": ["stale thesis"]},
        ],
        dispositions=[
            {"ticker": "C", "verb": "PASS", "driver_tags": ["stale thesis"]},
        ],
        threshold=3,
    )

    assert report["status"] == "insufficient_sample"
    categories = {row["category"] for row in report["insufficient"]}
    assert "FULL EXIT" in categories or "FULL EXIT".lower() in {c.lower() for c in categories}
    assert "PASS" in categories or "PASS".lower() in {c.lower() for c in categories}


def test_load_rows_supports_json_and_jsonl(tmp_path):
    json_path = tmp_path / "rows.json"
    json_path.write_text(json.dumps({"rows": [{"ticker": "A", "category": "win", "driver": "discipline"}]}), encoding="utf-8")
    jsonl_path = tmp_path / "rows.jsonl"
    jsonl_path.write_text('{"ticker":"B","category":"win","driver":"discipline"}\n', encoding="utf-8")

    assert op.load_rows(json_path)[0]["ticker"] == "A"
    assert op.load_rows(jsonl_path)[0]["ticker"] == "B"


def test_cli_writes_report(tmp_path):
    rows = tmp_path / "outcomes.json"
    rows.write_text(json.dumps([
        {"ticker": "A", "category": "win", "driver": "early add"},
        {"ticker": "B", "category": "win", "driver": "early add"},
        {"ticker": "C", "category": "win", "driver": "early add"},
    ]), encoding="utf-8")
    out = tmp_path / "report.json"

    rc = op.main(["--trade-outcomes", str(rows), "--dispositions", "", "--out", str(out), "--format", "json"])

    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["finding_count"] == 1
