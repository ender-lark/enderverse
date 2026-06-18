import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analyst_judgment import research_actions_read
from research_queue_intake import (
    build_research_queue,
    load_rows,
    merge_queues,
    normalize_row,
    validate_research_queue,
)


THESES = [
    {"ticker": "AVGO", "tier": "T2", "stance": "ACTIVE", "factor_tags": ["ai_complex"]},
    {"ticker": "BMNR", "tier": "T1", "stance": "MONITOR", "factor_tags": ["crypto"]},
]


def test_normalizes_ticker_priority_status_and_days_out():
    row = normalize_row(
        {
            "Ticker": "AVGO",
            "Name": "post-print dossier",
            "Priority": "High",
            "Status": "Working",
            "Catalyst Date": "2026-06-07",
            "Action State": "ACT_NOW",
        },
        as_of="2026-06-05",
    )

    assert row["r"] == "AVGO - post-print dossier"
    assert row["ticker"] == "AVGO"
    assert row["pr"] == "high"
    assert row["days_out"] == 2
    assert row["urgency"] == "ACT_NOW"


def test_preserves_structured_buy_verdict_fields():
    row = normalize_row(
        {
            "Ticker": "VRT",
            "Name": "starter after off-hours screen",
            "Priority": "High",
            "Status": "Working",
            "Stance": "BUY",
            "Conviction": "HIGH",
            "Conviction Score": "4.6",
            "Size": "$8-10k starter",
            "Trigger Date": "2026-07-29",
            "Thesis": "$15B backlog; power/cooling demand supports a starter.",
            "Source": "off-hours screen #3",
            "Source Tags": "off-hours screen; vetted BUY",
            "Source Groups": "research_queue; earnings_backlog",
            "First Flagged": "2026-06-18",
            "Flag Price": "$190",
        },
        as_of="2026-06-18",
    )

    assert row["ticker"] == "VRT"
    assert row["stance"] == "BUY"
    assert row["conviction"] == "HIGH"
    assert row["conviction_score"] == 4.6
    assert row["size_band_usd"] == {"low": 8000.0, "high": 10000.0}
    assert row["trigger_date"] == "2026-07-29"
    assert row["thesis"].startswith("$15B backlog")
    assert row["source_tags"] == ["off-hours screen", "vetted BUY"]
    assert row["source_groups"] == ["research_queue", "earnings_backlog"]
    assert row["first_flagged"] == "2026-06-18"
    assert row["flag_price"] == 190.0


def test_existing_pending_done_shape_preserves_done_bucket(tmp_path):
    p = tmp_path / "research.json"
    p.write_text(json.dumps({
        "pending": [{"r": "AVGO - active review", "pr": "High"}],
        "done": [{"r": "Research process cleanup", "pr": "Low"}],
    }), encoding="utf-8")

    queue = build_research_queue(load_rows(p), as_of="2026-06-05")

    assert queue["summary"]["pending"] == 1
    assert queue["summary"]["done"] == 1
    assert queue["done"][0]["r"] == "Research process cleanup"
    assert validate_research_queue(queue) == []


def test_loads_csv_export(tmp_path):
    p = tmp_path / "research.csv"
    p.write_text(
        "Ticker,Name,Priority,Status,Catalyst Date\n"
        "AVGO,post-print dossier,High,Working,2026-06-07\n",
        encoding="utf-8",
    )

    queue = build_research_queue(load_rows(p), as_of="2026-06-05")

    assert queue["pending"][0]["r"] == "AVGO - post-print dossier"
    assert queue["pending"][0]["days_out"] == 2


def test_research_act_now_surfaces_but_monitor_stays_review_only():
    queue = build_research_queue([
        {"Ticker": "AVGO", "Name": "urgent decision dossier", "Priority": "High",
         "Status": "Working", "Action State": "ACT_NOW"},
        {"Ticker": "BMNR", "Name": "burned sleeve check", "Priority": "High",
         "Status": "Working", "Action State": "ACT_NOW"},
        {"Name": "Research process cleanup", "Priority": "Low", "Status": "Working"},
    ])

    out = research_actions_read(queue, THESES)
    by_ticker = {row["ticker"]: row for row in out["research_actions"]}

    assert by_ticker["AVGO"]["kind"] == "research_act_now"
    assert by_ticker["AVGO"]["action_state"] == "ACT_NOW"
    assert by_ticker["BMNR"]["kind"] == "research_review"
    assert by_ticker["BMNR"]["action_state"] == "RESEARCH"
    assert "Research process cleanup" not in str(out["research_actions"])


def test_merge_existing_dedupes_rows():
    existing = build_research_queue([
        {"Ticker": "AVGO", "Name": "urgent decision dossier", "Priority": "High"}
    ])
    new = build_research_queue([
        {"Ticker": "AVGO", "Name": "urgent decision dossier", "Priority": "High"}
    ])

    merged = merge_queues(existing, new)

    assert len(merged["pending"]) == 1
    assert merged["summary"]["merged"] is True


def test_cli_stdin_dry_run_does_not_write(tmp_path):
    out = tmp_path / "research_queue.json"
    payload = json.dumps([
        {"Ticker": "AVGO", "Name": "urgent decision dossier", "Priority": "High"}
    ])

    proc = subprocess.run(
        [
            sys.executable,
            os.path.join(os.path.dirname(__file__), "research_queue_intake.py"),
            "--stdin-json",
            "--dry-run",
            "--out",
            str(out),
        ],
        input=payload,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["dry_run"] is True
    assert summary["written"] is None
    assert not out.exists()
