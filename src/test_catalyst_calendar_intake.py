import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from catalyst_calendar_intake import (
    load_catalyst_rows,
    main,
    merge_catalysts,
    normalize_catalyst_row,
)
from full_build_runner import build_full_feed_from_files


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _series(base, n=70):
    return [base + i for i in range(n)]


def _required_files(src):
    _write(src / "positions.json", {
        "snapshot_date": "2026-06-04",
        "sleeve_value": 100000,
        "positions": [
            {"ticker": "AVGO", "shares": 10, "market_value": 6000, "account": "SKB"},
        ],
    })
    _write(src / "theses.json", [
        {"ticker": "AVGO", "tier": "T2", "stance": "ACTIVE", "factor_tags": ["ai_complex"]},
    ])
    _write(src / "uw_closes.json", {"SMH": _series(400), "SPY": _series(600)})


def test_normalize_catalyst_row_accepts_export_aliases():
    row = normalize_catalyst_row({
        "Symbol": "avgo",
        "Event Date": "2026-06-06T00:00:00+00:00",
        "Title": "Q2 earnings",
    })
    assert row == {
        "ticker": "AVGO",
        "date": "2026-06-06",
        "label": "Q2 earnings",
        "source": "Catalyst Calendar",
    }


def test_normalize_catalyst_row_accepts_notion_properties():
    row = normalize_catalyst_row({
        "properties": {
            "Tickers": {
                "type": "multi_select",
                "multi_select": [{"name": "AVGO"}, {"name": "NVDA"}],
            },
            "Event Date": {
                "type": "date",
                "date": {"start": "2026-06-06T00:00:00+00:00"},
            },
            "Name": {
                "type": "title",
                "title": [{"plain_text": "Q2 earnings"}],
            },
            "Source": {
                "type": "select",
                "select": {"name": "Company calendar"},
            },
        }
    })

    assert row == {
        "ticker": "AVGO, NVDA",
        "date": "2026-06-06",
        "label": "Q2 earnings",
        "source": "Company calendar",
    }


def test_load_catalyst_rows_accepts_json_and_csv(tmp_path):
    js = tmp_path / "catalysts.json"
    csvp = tmp_path / "catalysts.csv"
    _write(js, {"events": [{"ticker": "AVGO", "date": "2026-06-06", "label": "Earnings"}]})
    csvp.write_text("ticker,date,label\nNVDA,2026-06-07,Earnings\n", encoding="utf-8")
    rows = load_catalyst_rows([js, csvp])
    assert [r.get("ticker") for r in rows] == ["AVGO", "NVDA"]


def test_merge_catalysts_dedupes_and_sorts():
    rows, summary = merge_catalysts(
        [{"ticker": "NVDA", "date": "2026-06-07", "label": "Earnings"}],
        [
            {"ticker": "AVGO", "date": "2026-06-06", "label": "Earnings"},
            {"ticker": "NVDA", "date": "2026-06-07", "label": "Earnings"},
        ],
        generated_at="2026-06-05T14:00:00+00:00",
    )
    assert [(r["ticker"], r["date"]) for r in rows] == [
        ("AVGO", "2026-06-06"),
        ("NVDA", "2026-06-07"),
    ]
    assert summary["existing"] == 1
    assert summary["input_rows"] == 2
    assert summary["added"] == 1


def test_cli_writes_catalysts_and_summary(tmp_path):
    raw = tmp_path / "raw.json"
    out = tmp_path / "catalysts.json"
    summary = tmp_path / "summary.json"
    _write(raw, [{"ticker": "AVGO", "date": "2026-06-06", "label": "Q2 earnings"}])
    assert main([
        str(raw),
        "--out", str(out),
        "--summary", str(summary),
        "--generated-at", "2026-06-05T14:00:00+00:00",
    ]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))[0]["ticker"] == "AVGO"
    assert json.loads(summary.read_text(encoding="utf-8"))["stored"] == 1


def test_cli_stdin_accepts_connector_result_envelope(tmp_path):
    out = tmp_path / "catalysts.json"
    summary = tmp_path / "summary.json"
    payload = json.dumps({
        "result": [{
            "properties": {
                "Ticker": {"type": "title", "title": [{"plain_text": "AVGO"}]},
                "Date": {"type": "date", "date": {"start": "2026-06-06"}},
                "Event": {"type": "rich_text", "rich_text": [{"plain_text": "Q2 earnings"}]},
            }
        }]
    })

    proc = subprocess.run(
        [
            sys.executable,
            os.path.join(os.path.dirname(__file__), "catalyst_calendar_intake.py"),
            "--stdin-json",
            "--out", str(out),
            "--summary", str(summary),
            "--generated-at", "2026-06-05T14:00:00+00:00",
        ],
        input=payload,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert json.loads(out.read_text(encoding="utf-8"))[0] == {
        "ticker": "AVGO",
        "date": "2026-06-06",
        "label": "Q2 earnings",
        "source": "Catalyst Calendar",
    }
    assert json.loads(summary.read_text(encoding="utf-8"))["input_rows"] == 1


def test_intake_output_reaches_full_build_actions(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _required_files(src)
    raw = tmp_path / "raw.json"
    _write(raw, [{"ticker": "AVGO", "date": "2026-06-06", "label": "Q2 earnings"}])
    main([
        str(raw),
        "--out", str(src / "catalysts.json"),
        "--summary", str(src / "catalyst_intake_summary.json"),
        "--generated-at", "2026-06-05T14:00:00+00:00",
    ])

    feed = build_full_feed_from_files(
        src_dir=src,
        as_of="2026-06-05",
        run_timestamp="2026-06-05T14:00:00+00:00",
    )
    by_ticker = {a.get("ticker"): a for a in feed["actions"] if a.get("ticker")}
    assert by_ticker["AVGO"]["kind"] == "catalyst_imminent"
    assert by_ticker["AVGO"]["action_state"] == "ACT_NOW"
