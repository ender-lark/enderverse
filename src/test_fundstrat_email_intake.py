import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fundstrat_email_intake import (
    build_intake_payload,
    entries_from_payload,
    extract_daily_calls,
    extract_tickers,
    load_entries,
    load_ticker_universe,
    normalize_email_entry,
    parse_date,
    write_convention_files,
)


def test_parse_date_accepts_email_iso_and_gmail_ms():
    assert parse_date("Fri, 05 Jun 2026 09:30:00 -0400") == "2026-06-05"
    assert parse_date("2026-06-04T20:00:00Z") == "2026-06-04"
    assert parse_date(1780660800000) == "2026-06-05"


def test_normalize_email_entry_reads_headers_and_detects_author():
    raw = "\n".join([
        "From: research@fundstrat.com",
        "Date: Fri, 05 Jun 2026 09:30:00 -0400",
        "Subject: Mark Newton: NVDA breakout",
        "",
        "Buy NVDA near 170, stop 160, target 200.",
    ])
    entry = normalize_email_entry(raw)
    assert entry["subject"] == "Mark Newton: NVDA breakout"
    assert entry["date"] == "2026-06-05"
    assert entry["author"] == "Newton"
    assert "Buy NVDA" in entry["body"]


def test_extract_tickers_uses_cashtags_headers_verbs_and_universe():
    text = "Tickers in Report: NVDA, FN\nAdd $AVGO. Watch GOOGL. AI is broad."
    tickers = extract_tickers(text, universe={"GOOGL", "SMH"})
    assert tickers == ["AVGO", "NVDA", "FN", "GOOGL"]


def test_extract_daily_calls_only_emits_action_like_context():
    entries = [
        {
            "subject": "Tom Lee note",
            "body": "NVDA was mentioned in passing. Add GOOGL near 170, stop 160, target 220.",
            "date": "2026-06-05",
            "author": "Lee",
        }
    ]
    calls, mentions = extract_daily_calls(entries, universe={"NVDA", "GOOGL"})
    assert {m["ticker"] for m in mentions} == {"NVDA", "GOOGL"}
    assert [c["ticker"] for c in calls] == ["GOOGL"]
    assert calls[0]["direction"] == "buy"
    assert calls[0]["entry"] == 170.0
    assert calls[0]["stop"] == 160.0
    assert calls[0]["target"] == 220.0


def test_load_entries_accepts_gmail_like_json(tmp_path):
    p = tmp_path / "gmail.json"
    p.write_text(json.dumps({"messages": [{
        "from": "Fundstrat",
        "subject": "Sean Farrell crypto",
        "body": "Accumulate HYPE on dips.",
        "internalDate": 1780660800000,
    }]}), encoding="utf-8")
    entries = load_entries([p])
    assert len(entries) == 1
    assert entries[0]["author"] == "Farrell"
    assert entries[0]["date"] == "2026-06-05"


def test_entries_from_payload_accepts_gmail_connector_responses_shape():
    entries = entries_from_payload({"responses": [{
        "from_": "Mark Newton mark.newton@fundstratdirect.com",
        "subject": "Daily Technical Strategy",
        "body": "Buy RSPH on relative breakout.",
        "email_ts": "2026-06-04T23:35:18+00:00",
    }]})
    assert len(entries) == 1
    assert entries[0]["author"] == "Newton"
    assert entries[0]["subject"] == "Daily Technical Strategy"
    assert entries[0]["date"] == "2026-06-04"
    assert "RSPH" in entries[0]["body"]


def test_build_payload_and_write_convention_files(tmp_path):
    entries = [{
        "subject": "Mark Newton tech",
        "body": "Buy NVDA near 170, stop 160, target 200.",
        "date": "2026-06-05",
        "author": "Newton",
        "from": "Fundstrat",
        "source_path": "x",
    }]
    payload = build_intake_payload(entries, universe={"NVDA"},
                                   generated_at="2026-06-05T14:00:00+00:00")
    assert payload["summary"]["daily_calls"] == 1
    assert payload["inbox_call_dates"] == ["2026-06-05"]
    assert payload["source_call_candidates"][0]["ticker"] == "NVDA"

    written = write_convention_files(payload, tmp_path)
    assert set(written) == {
        "fundstrat_inbox_entries",
        "fundstrat_daily_calls",
        "inbox_call_dates",
        "source_call_candidates",
        "fundstrat_intake_summary",
    }
    calls = json.loads((tmp_path / "fundstrat_daily_calls.json").read_text(encoding="utf-8"))
    dates = json.loads((tmp_path / "inbox_call_dates.json").read_text(encoding="utf-8"))
    assert calls[0]["ticker"] == "NVDA"
    assert dates == ["2026-06-05"]


def test_load_ticker_universe_uses_theses_and_positions(tmp_path):
    theses = tmp_path / "theses.json"
    positions = tmp_path / "positions.json"
    theses.write_text(json.dumps([{"ticker": "NVDA"}]), encoding="utf-8")
    positions.write_text(json.dumps({
        "sleeve_value": 100,
        "positions": [{"ticker": "SMH", "market_value": 10}],
    }), encoding="utf-8")
    assert load_ticker_universe(theses, positions) == {"NVDA", "SMH"}
