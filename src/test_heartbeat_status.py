import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from heartbeat_status import heartbeat_rows, validate_heartbeat


def _base_report(**overrides):
    report = {
        "build_ready": True,
        "build_problem": "",
        "publish_gate_problems": [],
        "missing_required_inputs": [],
        "missing_minimum_live_inputs": [],
        "dark_lane_keys": [],
    }
    report.update(overrides)
    return report


def test_heartbeat_rows_show_missing_market_data_and_dark_lanes():
    rows = heartbeat_rows(
        _base_report(
            missing_minimum_live_inputs=[{"key": "macro"}, {"key": "uw_prices"}],
            publish_gate_problems=["cannot verify stamp"],
            dark_lane_keys=["uw_price", "uw_macro", "signal_log"],
            dark_lane_details=[
                {"key": "signal_log", "next_step": "Supply the Morning Scan or Signal Log JSON."}
            ],
        ),
        generated_at="2026-06-05T14:00:00+00:00",
    )
    by_layer = {row["layer"]: row for row in rows}

    assert by_layer["Required Inputs"]["status"] == "ok"
    assert by_layer["Minimum Market Data"]["status"] == "down"
    assert "macro" in by_layer["Minimum Market Data"]["note"]
    assert by_layer["Publish Gate"]["status"] == "down"
    assert by_layer["Optional Source Lanes"]["status"] == "stale"
    assert "Morning Scan" in by_layer["Optional Source Lanes"]["note"]
    assert by_layer["Daily Full Build"]["status"] == "ok"
    assert validate_heartbeat(rows) == []


def test_heartbeat_rows_keep_deferred_social_watch_from_becoming_issue():
    rows = heartbeat_rows(
        _base_report(
            dark_lane_keys=["social_watch"],
            dark_lane_details=[{
                "key": "social_watch",
                "next_step": "Supply social_watch.json from the compliant API/cache path.",
            }],
        ),
        generated_at="2026-06-05T14:00:00+00:00",
    )
    by_layer = {row["layer"]: row for row in rows}

    assert by_layer["Optional Source Lanes"]["status"] == "ok"
    assert "deferred optional lanes: social_watch" in by_layer["Optional Source Lanes"]["note"]
    assert "not a no-signal read" in by_layer["Optional Source Lanes"]["note"]
    assert "Supply social_watch" not in by_layer["Optional Source Lanes"]["note"]
    assert validate_heartbeat(rows) == []


def test_heartbeat_rows_warn_for_actionable_dark_lanes_even_with_deferred_social():
    rows = heartbeat_rows(
        _base_report(
            dark_lane_keys=["signal_log", "social_watch"],
            dark_lane_details=[
                {"key": "signal_log", "next_step": "Supply the Morning Scan or Signal Log JSON."},
                {"key": "social_watch", "next_step": "Supply social_watch.json."},
            ],
        ),
        generated_at="2026-06-05T14:00:00+00:00",
    )
    by_layer = {row["layer"]: row for row in rows}

    assert by_layer["Optional Source Lanes"]["status"] == "stale"
    assert "dark lanes: signal_log" in by_layer["Optional Source Lanes"]["note"]
    assert "deferred optional: social_watch" in by_layer["Optional Source Lanes"]["note"]
    assert "Morning Scan" in by_layer["Optional Source Lanes"]["note"]
    assert "Supply social_watch" not in by_layer["Optional Source Lanes"]["note"]
    assert validate_heartbeat(rows) == []


def test_heartbeat_rows_all_ok_when_report_is_clean():
    rows = heartbeat_rows(_base_report(), generated_at="2026-06-05T14:00:00+00:00")
    by_layer = {row["layer"]: row for row in rows}

    assert {row["status"] for row in rows} == {"ok"}
    assert by_layer["Optional Source Lanes"]["note"] == "no dark lanes reported in lane-status block"
    assert "checked clear" not in by_layer["Optional Source Lanes"]["note"]


def test_heartbeat_rows_show_overdue_cloud_routine_receipts():
    rows = heartbeat_rows(
        _base_report(
            routine_receipt_due={
                "rows": [{"routine_id": "investing-os-post-close-refresh"}],
                "overdue_count": 1,
                "overdue": [{
                    "routine_id": "investing-os-post-close-refresh",
                    "routine_name": "Investing OS Post-Close Refresh",
                    "last_ran_label": "never",
                    "overdue_line": "overdue: Investing OS Post-Close Refresh, last ran never",
                }],
                "due_waiting_count": 0,
            },
        ),
        generated_at="2026-06-05T21:10:00+00:00",
    )
    by_layer = {row["layer"]: row for row in rows}

    assert by_layer["Cloud Routine Receipts"]["status"] == "down"
    assert "overdue: Investing OS Post-Close Refresh, last ran never" in by_layer["Cloud Routine Receipts"]["note"]
    assert validate_heartbeat(rows) == []


def test_heartbeat_rows_show_stale_required_inputs():
    rows = heartbeat_rows(
        _base_report(stale_required_inputs=[{"key": "positions"}]),
        generated_at="2026-06-05T14:00:00+00:00",
    )
    by_layer = {row["layer"]: row for row in rows}

    assert by_layer["Required Inputs"]["status"] == "stale"
    assert "positions" in by_layer["Required Inputs"]["note"]
    assert validate_heartbeat(rows) == []


def test_validate_heartbeat_rejects_bad_status():
    problems = validate_heartbeat([{"layer": "X", "status": "exploded"}])

    assert any("status" in problem for problem in problems)


def test_heartbeat_cli_no_write(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "positions.json").write_text(json.dumps({
        "snapshot_date": "2026-06-05",
        "positions": [{"ticker": "NVDA", "market_value": 100}],
    }), encoding="utf-8")
    (src / "theses.json").write_text(json.dumps([
        {"ticker": "NVDA", "tier": "T2", "stance": "ACTIVE"}
    ]), encoding="utf-8")
    script = os.path.join(os.path.dirname(__file__), "heartbeat_status.py")
    out = tmp_path / "heartbeat.json"
    summary = tmp_path / "heartbeat_summary.json"

    proc = subprocess.run(
        [
            sys.executable,
            script,
            "--src-dir",
            str(src),
            "--out",
            str(out),
            "--summary",
            str(summary),
            "--no-write",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["valid"] is True
    assert not out.exists()
    assert not summary.exists()
