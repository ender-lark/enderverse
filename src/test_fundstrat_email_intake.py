import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fundstrat_email_intake import (
    build_intake_payload,
    dedupe_entries,
    entries_from_payload,
    extract_daily_calls,
    extract_tickers,
    filter_new_entries,
    load_entries,
    load_ticker_universe,
    normalize_email_entry,
    parse_date,
    update_state,
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


def test_load_entries_accepts_gmail_responses_json_file(tmp_path):
    p = tmp_path / "gmail_responses.json"
    p.write_text(json.dumps({"responses": [{
        "from_": "Mark Newton mark.newton@fundstratdirect.com",
        "subject": "Daily Technical Strategy",
        "body": "Buy RSPH.",
        "email_ts": "2026-06-04T23:35:18+00:00",
    }]}), encoding="utf-8")
    entries = load_entries([p])
    assert entries[0]["author"] == "Newton"
    assert entries[0]["date"] == "2026-06-04"


def test_load_entries_accepts_utf8_bom_json(tmp_path):
    p = tmp_path / "gmail_bom.json"
    p.write_text("\ufeff" + json.dumps({"messages": [{
        "from": "Fundstrat",
        "subject": "Mark Newton tech",
        "body": "Buy NVDA.",
        "date": "2026-06-05",
    }]}), encoding="utf-8")
    entries = load_entries([p])
    assert entries[0]["author"] == "Newton"
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


def test_dedupe_and_state_filter_use_message_ids():
    entries = entries_from_payload({"responses": [
        {"id": "m1", "subject": "A", "body": "Buy NVDA.", "email_ts": "2026-06-04T12:00:00Z"},
        {"id": "m1", "subject": "A", "body": "Buy NVDA.", "email_ts": "2026-06-04T12:00:00Z"},
        {"id": "m2", "subject": "B", "body": "Buy GOOGL.", "email_ts": "2026-06-05T12:00:00Z"},
    ]})
    assert [e["message_id"] for e in dedupe_entries(entries)] == ["m1", "m2"]
    new_entries = filter_new_entries(entries, {"processed_message_ids": ["m1"]})
    assert [e["message_id"] for e in new_entries] == ["m2"]
    state = update_state({"processed_message_ids": ["old"]}, new_entries,
                         generated_at="2026-06-05T14:00:00+00:00")
    assert state["processed_message_ids"] == ["m2", "old"]
    assert state["last_inbox_date"] == "2026-06-05"


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
    inbox_entries = json.loads((tmp_path / "fundstrat_inbox_entries.json").read_text(encoding="utf-8"))
    assert calls[0]["ticker"] == "NVDA"
    assert dates == ["2026-06-05"]
    assert "body" not in inbox_entries[0]
    assert inbox_entries[0]["body_redacted"] is True
    assert inbox_entries[0]["body_chars"] == len(entries[0]["body"])
    assert len(inbox_entries[0]["body_sha256"]) == 64


def test_write_convention_files_can_keep_bodies_for_local_debugging(tmp_path):
    payload = build_intake_payload([{
        "subject": "Mark Newton tech",
        "body": "Buy NVDA near 170.",
        "date": "2026-06-05",
        "author": "Newton",
        "from": "Fundstrat",
        "source_path": "x",
    }], universe={"NVDA"}, generated_at="2026-06-05T14:00:00+00:00")
    write_convention_files(payload, tmp_path, redact_bodies=False)
    inbox_entries = json.loads((tmp_path / "fundstrat_inbox_entries.json").read_text(encoding="utf-8"))
    summary = json.loads((tmp_path / "fundstrat_intake_summary.json").read_text(encoding="utf-8"))
    assert inbox_entries[0]["body"] == "Buy NVDA near 170."
    assert summary["bodies_redacted"] is False


def test_write_convention_files_can_merge_existing_and_write_state(tmp_path):
    (tmp_path / "fundstrat_daily_calls.json").write_text(json.dumps([
        {"author": "Newton", "ticker": "OLD", "date": "2026-06-04", "quote": "Buy OLD."}
    ]), encoding="utf-8")
    payload = build_intake_payload([{
        "subject": "Mark Newton tech",
        "body": "Buy NVDA near 170.",
        "date": "2026-06-05",
        "author": "Newton",
        "from": "Fundstrat",
        "source_path": "x",
        "message_id": "m1",
        "thread_id": "t1",
    }], universe={"NVDA"}, generated_at="2026-06-05T14:00:00+00:00")
    write_convention_files(
        payload,
        tmp_path,
        merge_existing=True,
        state={"last_run_at": "2026-06-05T14:00:00+00:00",
               "processed_message_ids": ["m1"]},
    )
    calls = json.loads((tmp_path / "fundstrat_daily_calls.json").read_text(encoding="utf-8"))
    state = json.loads((tmp_path / "fundstrat_intake_state.json").read_text(encoding="utf-8"))
    summary = json.loads((tmp_path / "fundstrat_intake_summary.json").read_text(encoding="utf-8"))
    assert [c["ticker"] for c in calls] == ["OLD", "NVDA"]
    assert state["processed_message_ids"] == ["m1"]
    assert summary["merged"] is True
    assert summary["stored_daily_calls"] == 2


def test_load_ticker_universe_uses_theses_and_positions(tmp_path):
    theses = tmp_path / "theses.json"
    positions = tmp_path / "positions.json"
    theses.write_text(json.dumps([{"ticker": "NVDA"}]), encoding="utf-8")
    positions.write_text(json.dumps({
        "sleeve_value": 100,
        "positions": [{"ticker": "SMH", "market_value": 10}],
    }), encoding="utf-8")
    assert load_ticker_universe(theses, positions) == {"NVDA", "SMH"}
