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
