import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import live_dashboard_refresh as refresh


def test_refresh_plan_tracks_source_calls_before_final_build():
    steps = refresh.refresh_plan(publish=True)
    names = [step.name for step in steps]

    assert names == [
        "heartbeat_pre_synthesis",
        "refresh_decision_dossier_dynamic_reads",
        "build_publish_pre_synthesis",
        "draft_source_call_candidates",
        "repo_evidence_synthesis",
        "heartbeat_post_synthesis",
        "build_publish_final",
        "render_jsx_validation_surface",
        "build_jsx_validation_preview",
        "render_summary_html",
        "render_preview_html",
        "write_parity_feed",
    ]
    dossier_refresh = steps[1].command
    first_build = steps[2].command
    source_calls = steps[3].command
    synthesis = steps[4].command
    final_build = steps[6].command
    assert "src/decision_dossier_refresh.py" in dossier_refresh
    assert any(part.replace("\\", "/") == "src/decision_dossiers.json" for part in dossier_refresh)
    assert "src/full_build_runner.py" in first_build
    assert "--publish" in first_build
    assert first_build == final_build
    assert "src/source_call_candidate_draft.py" in source_calls
    assert "--merge-existing" in source_calls
    assert "--merge-cache" in source_calls
    assert "src/daily_synthesis_from_feed.py" in synthesis
    assert "--merge-existing" in synthesis
    assert any(part.replace("\\", "/") == "src/latest_cockpit_feed.json" for part in synthesis)


def test_refresh_plan_can_rehearse_without_publish():
    steps = refresh.refresh_plan(publish=False)

    assert "--publish" not in steps[2].command
    assert "--publish" not in steps[6].command


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
    assert payload["steps"][1]["name"] == "refresh_decision_dossier_dynamic_reads"
    assert payload["steps"][3]["name"] == "draft_source_call_candidates"
    assert payload["steps"][4]["name"] == "repo_evidence_synthesis"
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
        preview_server={
            "url": "http://127.0.0.1:8765/dashboard_preview.html",
            "canonical_url": "http://127.0.0.1:8765/dashboard_preview.html",
            "html_url": "http://127.0.0.1:8765/dashboard_preview.html",
            "jsx_url": "http://127.0.0.1:8765/cockpit_jsx_preview.html",
            "preview_exists": True,
            "server_running": True,
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
    assert summary["preview_server"]["server_running"] is True
