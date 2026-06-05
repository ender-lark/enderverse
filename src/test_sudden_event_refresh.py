import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sudden_event_refresh


def test_sudden_event_plan_intakes_refreshes_and_prints_status():
    steps = sudden_event_refresh.sudden_event_plan(
        title="Iran oil headline risk",
        why="Review exposure before adding risk.",
        trigger="WTI spike or Strait headline.",
        channels="oil,rates",
        tickers="XOP,TNX",
        event_date="2026-06-05",
    )

    assert [step.name for step in steps] == [
        "event_risk_intake",
        "live_dashboard_refresh",
        "live_status",
    ]
    intake = steps[0].command
    assert "src/event_risk_intake.py" in intake
    assert "--merge-existing" in intake
    assert "--title" in intake and "Iran oil headline risk" in intake
    assert "--channels" in intake and "oil,rates" in intake
    assert "--tickers" in intake and "XOP,TNX" in intake
    assert "src/live_dashboard_refresh.py" in steps[1].command
    assert steps[2].command[-2:] == ["--format", "text"]


def test_sudden_event_refresh_dry_run_lists_steps():
    script = os.path.join(os.path.dirname(__file__), "sudden_event_refresh.py")

    proc = subprocess.run(
        [
            sys.executable,
            script,
            "--title",
            "Iran oil headline risk",
            "--why",
            "Review exposure before adding risk.",
            "--trigger",
            "WTI spike or Strait headline.",
            "--channels",
            "oil,rates",
            "--tickers",
            "XOP,TNX",
            "--date",
            "2026-06-05",
            "--dry-run",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["steps"][0]["name"] == "event_risk_intake"
    assert payload["steps"][1]["name"] == "live_dashboard_refresh"
    assert payload["steps"][2]["name"] == "live_status"
