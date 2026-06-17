import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import integration_debt_sweep as ids


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _minimal_repo(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path
    src = root / "src"
    (src / "codex_routines").mkdir(parents=True)
    _write(src / "pattern_engine.py", "def detect_stale_leaps(**kwargs):\n    return []\n")
    _write(src / "morning_scan.py", "def run_morning_scan(*, held_options=None):\n    return held_options\n")
    _write(src / "rationale_decay_v3.py", "# v11.10 7-rule cadence\n")
    _write(src / "cloud_automation_status.json", json.dumps({"routines": []}))
    _write(src / "codex_routine_manifest.json", json.dumps({"routines": []}))
    _write(src / "system_improvement_queue.json", json.dumps({"items": []}))
    return root, src


def test_options_cadence_warns_when_stale_leaps_is_dte_only(tmp_path):
    root, src = _minimal_repo(tmp_path)

    section = ids.options_exit_cadence_section(src, root)

    assert section["status"] == "warn"
    assert section["findings"][0]["id"] == "options_exit_7_rule_cadence"


def test_options_cadence_quiet_when_weekly_prompt_runs_cadence(tmp_path):
    root, src = _minimal_repo(tmp_path)
    _write(src / "codex_routines" / "weekly_pilot_run.md", "python src/rationale_decay_v3.py --format text\n")

    section = ids.options_exit_cadence_section(src, root)

    assert section["status"] == "ok"
    assert section["findings"] == []


def test_routine_schedule_flags_scheduled_role_without_repo_prompt(tmp_path):
    root, src = _minimal_repo(tmp_path)
    _write(src / "cloud_automation_status.json", json.dumps({
        "routines": [{
            "automation_id": "investing-os-weekly-pilot-run",
            "role": "weekly_pilot_run",
            "status": "ACTIVE",
            "schedule": "Sunday 6:00 PM ET",
        }]
    }))

    section = ids.routine_schedule_section(src, root)

    assert section["status"] == "info"
    assert any(row["area"] == "routine_schedule" for row in section["findings"])


def test_notion_queue_is_dark_without_supplied_rows(tmp_path):
    root, src = _minimal_repo(tmp_path)

    section = ids.notion_queue_section(root, src)

    assert section["status"] == "not_checked"
    assert section["findings"][0]["severity"] == "warn"


def test_build_report_writes_markdown_and_json(tmp_path):
    root, src = _minimal_repo(tmp_path)
    report = ids.build_report(root_dir=root, src_dir=src, generated_at="2026-06-13T00:00:00Z")
    out = tmp_path / "docs" / "integration_debt_report.md"
    json_out = tmp_path / "src" / "integration_debt_report.json"

    ids.write_report(report, out=out, json_out=json_out)

    assert out.exists()
    assert "Integration Debt Report" in out.read_text(encoding="utf-8")
    assert json.loads(json_out.read_text(encoding="utf-8"))["warning_count"] >= 1


def test_build_without_wire_treats_real_decision_reader_as_wired(tmp_path):
    root, src = _minimal_repo(tmp_path)
    _write(src / "fed_day_reallocation_packet.json", json.dumps({
        "deep_discount_research": {
            "rows": [{"ticker": "NVDA", "discount_pct": -15.0}]
        }
    }))
    _write(src / "today_decide.py", 'PACKET = "fed_day_reallocation_packet.json"\n')

    section = ids.build_without_wire_section(src, root)

    rows = {row["artifact"]: row for row in section["rows"]}
    assert rows["fed_day_reallocation_packet.json"]["wired"] is True
    assert rows["fed_day_reallocation_packet.json"]["wiring"] == "decision_path_reader"
    assert not any(row["id"] == "build_without_wire_fed_day_reallocation_packet" for row in section["findings"])


def test_build_without_wire_flags_unwired_candidate_json_and_allowlist_clears(tmp_path):
    root, src = _minimal_repo(tmp_path)
    _write(src / "orphan_candidates.json", json.dumps({
        "candidates": [{"ticker": "ABC", "why": "fixture"}]
    }))
    _write(src / "disconfirmation_registry.json", json.dumps({
        "entries": {"NVDA": {"ticker": "NVDA", "status": "DRAFT"}}
    }))

    section = ids.build_without_wire_section(src, root)

    assert section["status"] == "warn"
    assert any(row["id"] == "build_without_wire_orphan_candidates" for row in section["findings"])
    assert any(row["id"] == "build_without_wire_disconfirmation_registry" for row in section["findings"])

    _write(src / "non_surfacing_allowlist.json", json.dumps({
        "artifacts": [{
            "artifact": "orphan_candidates.json",
            "classification": "example_fixture",
            "non_surfacing_reason": "Fixture proves allowlist clearing.",
            "owner": "test",
            "added": "2026-06-17"
        }]
    }))
    section = ids.build_without_wire_section(src, root)

    assert not any(row["id"] == "build_without_wire_orphan_candidates" for row in section["findings"])
    assert any(row["id"] == "build_without_wire_disconfirmation_registry" for row in section["findings"])
