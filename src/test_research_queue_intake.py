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


def _notion_page(topic, ticker, priority, status, findings="", reason=""):
    """Build a raw Notion API page shape for the Research Queue data source."""
    def rich(text):
        return {"type": "rich_text", "rich_text": [{"plain_text": text}]}

    props = {
        "Topic": {"type": "title", "title": [{"plain_text": topic}]},
        "Ticker": rich(ticker),
        "Priority": {"type": "select", "select": {"name": priority}},
        "Status": {"type": "select", "select": {"name": status}},
        "Added": {"type": "created_time", "created_time": "2026-06-09T13:03:45.610Z"},
    }
    if findings:
        props["Findings"] = rich(findings)
    if reason:
        props["Reason"] = rich(reason)
    return {"properties": props}


def test_from_notion_flattens_api_properties_and_prefers_findings():
    row = normalize_row(
        _notion_page(
            "GOOGL - re-check AI infrastructure financing",
            "GOOGL",
            "High",
            "Queued",
            findings="ATM up to $40B; $10B Berkshire placement",
            reason="close the loop from proposed to executed terms",
        )
    )

    assert row["r"] == "GOOGL - re-check AI infrastructure financing"
    assert row["ticker"] == "GOOGL"
    assert row["pr"] == "high"
    assert row["status"] == "Queued"
    assert row["notes"] == "ATM up to $40B; $10B Berkshire placement"


def test_from_notion_killed_status_routed_out_of_pending():
    queue = build_research_queue([
        _notion_page("MAGS leftover thesis question", "MAGS", "Low", "Killed"),
        _notion_page("GOOGL tranche-2 context", "GOOGL", "High", "Queued"),
    ])

    assert validate_research_queue(queue) == []
    assert queue["summary"]["pending"] == 1
    assert queue["summary"]["killed"] == 1
    assert queue["pending"][0]["ticker"] == "GOOGL"
    assert queue["killed"][0]["ticker"] == "MAGS"
    # Killed rows are preserved for the audit trail, never silently dropped.
    assert all(r["ticker"] != "MAGS" for r in queue["pending"])


def test_cli_from_notion_export_writes_with_provenance(tmp_path):
    export = tmp_path / "notion_pull.json"
    export.write_text(json.dumps({"results": [
        _notion_page("AVGO - standalone AI-networking thesis", "AVGO", "Med", "Queued",
                     findings="~$40K held, untracked"),
    ]}), encoding="utf-8")
    out = tmp_path / "research_queue.json"

    proc = subprocess.run(
        [
            sys.executable,
            os.path.join(os.path.dirname(__file__), "research_queue_intake.py"),
            "--from-notion",
            "--notion-export",
            str(export),
            "--out",
            str(out),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["source"] == "research_queue_intake:notion"
    assert summary["pending"] == 1
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["data_source_id"] == "cab89576-0933-40b0-ad2e-6f9a6188e804"
    assert written["pending"][0]["r"] == "AVGO - standalone AI-networking thesis"


def test_cli_from_notion_empty_does_not_overwrite(tmp_path):
    out = tmp_path / "research_queue.json"
    sentinel = {"pending": [{"r": "PRIOR - keep me", "pr": "high"}], "done": []}
    out.write_text(json.dumps(sentinel), encoding="utf-8")
    empty = tmp_path / "empty_pull.json"
    empty.write_text(json.dumps({"results": []}), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            os.path.join(os.path.dirname(__file__), "research_queue_intake.py"),
            "--from-notion",
            "--notion-export",
            str(empty),
            "--out",
            str(out),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["not_checked"] is True
    assert summary["written"] is None
    # Existing cache must be untouched (honesty rail: no overwrite on empty pull).
    assert json.loads(out.read_text(encoding="utf-8")) == sentinel


def test_cli_export_file_fallback_path_writes(tmp_path):
    export = tmp_path / "research_export.json"
    export.write_text(
        json.dumps([
            {"Ticker": "CCJ", "Name": "standalone uranium thesis", "Priority": "Med",
             "Status": "Working"},
        ]),
        encoding="utf-8",
    )
    out = tmp_path / "research_queue.json"

    proc = subprocess.run(
        [
            sys.executable,
            os.path.join(os.path.dirname(__file__), "research_queue_intake.py"),
            str(export),
            "--out",
            str(out),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["source"] == "research_queue_intake"
    assert written["pending"][0]["r"] == "CCJ - standalone uranium thesis"


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
