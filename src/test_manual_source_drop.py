import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import manual_source_drop


def test_ingest_manual_source_drop_routes_explicit_sections(tmp_path):
    payload = {
        "event_risks": [
            {"title": "Oil shock headline", "severity": "high", "source": "Manual drop", "channels": "oil,rates"}
        ],
        "signal_log": [
            {"ticker": "NVDA", "signal": "Watch semis reaction to oil/rates tape", "date": "2026-06-05"}
        ],
        "catalysts": [
            {"ticker": "NVDA", "date": "2026-06-06", "label": "Supplier update"}
        ],
    }

    report = manual_source_drop.ingest_manual_source_drop([payload], src_dir=tmp_path, default_date="2026-06-05")

    assert report["valid"] is True
    assert report["sections_seen"] == ["catalysts", "event_risks", "signal_log"]
    assert json.loads((tmp_path / "event_risks.json").read_text(encoding="utf-8"))[0]["title"] == "Oil shock headline"
    assert json.loads((tmp_path / "signal_log.json").read_text(encoding="utf-8"))[0]["ticker"] == "NVDA"
    assert json.loads((tmp_path / "catalysts.json").read_text(encoding="utf-8"))[0]["label"] == "Supplier update"


def test_ingest_manual_source_drop_dry_run_does_not_write(tmp_path):
    report = manual_source_drop.ingest_manual_source_drop(
        [{"event_risks": [{"title": "Policy shock", "severity": "critical", "source": "Manual"}]}],
        src_dir=tmp_path,
        default_date="2026-06-05",
        dry_run=True,
    )

    assert report["valid"] is True
    assert report["sections"]["event_risks"]["written"] is False
    assert not (tmp_path / "event_risks.json").exists()


def test_ingest_manual_source_drop_merges_existing_rows(tmp_path):
    existing = [{"ticker": "ANET", "date": "2026-06-07", "label": "Existing", "source": "Manual Source Drop"}]
    (tmp_path / "catalysts.json").write_text(json.dumps(existing), encoding="utf-8")

    report = manual_source_drop.ingest_manual_source_drop(
        [{"catalysts": [{"ticker": "GOOGL", "date": "2026-06-08", "label": "New"}]}],
        src_dir=tmp_path,
    )

    rows = json.loads((tmp_path / "catalysts.json").read_text(encoding="utf-8"))
    assert report["sections"]["catalysts"]["stored"] == 2
    assert [row["ticker"] for row in rows] == ["ANET", "GOOGL"]


def test_manual_source_drop_cli_writes_sections(tmp_path):
    drop = tmp_path / "drop.json"
    drop.write_text(json.dumps({
        "event_risks": [{"title": "Rates shock", "severity": "high", "source": "Manual"}],
        "signal_log": [{"signal": "Watch breadth under rates shock"}],
    }), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / "manual_source_drop.py"),
            str(drop),
            "--src-dir",
            str(tmp_path),
            "--date",
            "2026-06-05",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["sections_seen"] == ["event_risks", "signal_log"]
    assert (tmp_path / "event_risks.json").is_file()
    assert (tmp_path / "signal_log.json").is_file()


def test_manual_source_drop_cli_fails_without_supported_sections(tmp_path):
    drop = tmp_path / "drop.json"
    drop.write_text(json.dumps({"events": [{"title": "Ambiguous"}]}), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / "manual_source_drop.py"),
            str(drop),
            "--src-dir",
            str(tmp_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 2
    assert json.loads(proc.stdout)["sections_seen"] == []
