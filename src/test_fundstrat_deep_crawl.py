import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fundstrat_deep_crawl as fdc


def test_committed_deep_crawl_targets_validate():
    payload = fdc.read_json(fdc.DEFAULT_TARGETS)

    assert fdc.validate_targets(payload) == []
    summary = fdc.summarize_targets(payload)
    assert "sector_allocation_current_outlook" in summary["stock_list_targets"]
    assert "large_cap_top_ideas" in summary["stock_list_targets"]
    assert "smid_cap_top_ideas" in summary["stock_list_targets"]
    assert summary["daily_call_eligible"] >= 1


def test_stock_list_targets_cannot_be_daily_call_eligible():
    payload = {
        "schema_version": 1,
        "targets": [
            {
                "id": "flash",
                "family": "FlashInsights",
                "priority": 1,
                "cadence": "every_run",
                "navigation_path": ["FlashInsights"],
                "capture_rule": "complete card",
                "checked_behavior": "visible",
                "daily_call_eligible": True,
            },
            {
                "id": "sector",
                "family": "Stock Lists",
                "priority": 4,
                "cadence": "deep_crawl",
                "navigation_path": ["Stock Lists", "Sector Allocation"],
                "capture_rule": "baseline diff",
                "checked_behavior": "table visible",
                "daily_call_eligible": True,
            },
        ],
    }

    assert any("Stock Lists targets must not be daily-call eligible" in problem for problem in fdc.validate_targets(payload))


def test_deep_crawl_cli_summary_passes(tmp_path):
    script = os.path.join(os.path.dirname(__file__), "fundstrat_deep_crawl.py")
    proc = subprocess.run(
        [sys.executable, script, "--summary"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["valid"] is True
    assert payload["summary"]["baseline_diff_only"] >= 1
