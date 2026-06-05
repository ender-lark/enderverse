import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import state_ownership_map as som


def test_repo_state_ownership_map_validates():
    with open(os.path.join(os.path.dirname(__file__), "state_ownership_map.json"), encoding="utf-8") as fh:
        payload = json.load(fh)

    assert som.validate_ownership_map(payload) == []


def test_validator_rejects_missing_required_fields():
    payload = {"objects": [{"id": "positions"}]}

    problems = som.validate_ownership_map(payload)

    assert any("source_of_truth" in problem for problem in problems)
    assert any("missing expected artifact" in problem for problem in problems)


def test_cli_self_test_passes():
    proc = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__), "state_ownership_map.py"), "--self-test"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert "self-test: PASS" in proc.stdout
