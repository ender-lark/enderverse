import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import live_dashboard_refresh as refresh


def test_refresh_plan_runs_synthesis_between_two_builds():
    steps = refresh.refresh_plan(publish=True)
    names = [step.name for step in steps]

    assert names == [
        "heartbeat_pre_synthesis",
        "build_publish_pre_synthesis",
        "repo_evidence_synthesis",
        "heartbeat_post_synthesis",
        "build_publish_final",
        "render_canonical_jsx",
        "render_summary_html",
        "render_preview_html",
        "write_parity_feed",
    ]
    first_build = steps[1].command
    final_build = steps[4].command
    synthesis = steps[2].command
    assert "src/full_build_runner.py" in first_build
    assert "--publish" in first_build
    assert first_build == final_build
    assert "src/daily_synthesis_from_feed.py" in synthesis
    assert any(part.replace("\\", "/") == "src/latest_cockpit_feed.json" for part in synthesis)


def test_refresh_plan_can_rehearse_without_publish():
    steps = refresh.refresh_plan(publish=False)

    assert "--publish" not in steps[1].command
    assert "--publish" not in steps[4].command


def test_live_dashboard_refresh_dry_run_lists_steps():
    script = os.path.join(os.path.dirname(__file__), "live_dashboard_refresh.py")

    proc = subprocess.run(
        [sys.executable, script, "--dry-run", "--no-publish"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["steps"][2]["name"] == "repo_evidence_synthesis"
    assert payload["steps"][-1]["name"] == "write_parity_feed"


def test_build_refresh_summary_surfaces_live_state(tmp_path):
    feed = tmp_path / "feed.json"
    feed.write_text(json.dumps({
        "generated_at": "2026-06-05T14:00:00+00:00",
        "staleness": {"stamp": "sourced: portfolio 05-31"},
        "lane_status": {
            "counts": {"has_data": 7, "not_checked": 1},
            "rows": [
                {"key": "catalysts", "label": "Catalysts", "status": "not_checked",
                 "next_step": "Supply catalysts.", "missing_impact": "Timing may be missing."},
            ],
        },
        "actions": [
            {"ticker": "NVDA", "kind": "conviction_gap", "urgency": "ACT_NOW",
             "headline": "Conviction gap: NVDA is under target"},
        ],
        "feedback": {
            "source_calls": {
                "status": "not_checked",
                "line": "Source-call calibration not checked; 3 unscored daily call(s) are flowing.",
                "observed_count": 3,
            },
        },
    }), encoding="utf-8")

    summary = refresh.build_refresh_summary(
        feed,
        preview_out=tmp_path / "preview.html",
        readiness={
            "go_live_ready": True,
            "publish_ready": True,
            "required_inputs_ready": True,
            "live_data_ready": True,
            "next_steps": ["Review dark lanes."],
        },
    )

    assert summary["actions"]["count"] == 1
    assert summary["actions"]["top"][0]["ticker"] == "NVDA"
    assert summary["actions"]["top"][0]["what"] == "Conviction gap: NVDA is under target"
    assert summary["actions"]["top"][0]["action_state"] == "ACT_NOW"
    assert summary["data_flow"]["lanes_with_data"] == 7
    assert summary["data_flow"]["dark_lane_keys"] == ["catalysts"]
    assert summary["source_calls"]["observed_count"] == 3
    assert summary["readiness"]["go_live_ready"] is True
    assert summary["readiness"]["next_steps"] == ["Review dark lanes."]
