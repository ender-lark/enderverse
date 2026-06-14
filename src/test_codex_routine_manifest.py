import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import codex_routine_manifest as crm


def test_committed_manifest_validates():
    manifest = crm.load_manifest()

    assert crm.validate_manifest(manifest) == []
    assert set(crm.EXPECTED_ROUTINES) == {routine["id"] for routine in manifest["routines"]}
    assert crm.summary(manifest)["daily_convention_inputs"] == len(crm._full_build_default_keys())


def test_daily_full_build_stays_separate_from_source_intake():
    manifest = crm.load_manifest()
    daily = next(r for r in manifest["routines"] if r["id"] == "daily_full_build")
    daily_text = json.dumps(daily)

    assert "fundstrat_email_intake.py" not in daily_text
    assert "codex_uw.orchestrator" not in daily_text
    assert "broker_pdf_extractor.py" not in daily_text
    assert daily["separation_group"] == "feed_build_publish"


def test_manifest_rejects_duplicate_output_ownership():
    manifest = {
        "schema_version": 1,
        "routines": [
            _routine("fundstrat_intake", owns=["src/shared.json"]),
            _routine("catalyst_intake", owns=["src/shared.json"]),
            _routine("broker_position_intake", owns=["src/positions.json"]),
            _routine("uw_cache_refresh", group="market_data_refresh", owns=["src/uw_opportunity_signals.json"]),
            _routine("daily_synthesis_intake", owns=["src/daily_synthesis.json"]),
            _routine("signal_log_intake", owns=["src/signal_log.json"]),
            _routine("social_watch_intake", owns=["src/social_watch.json"]),
            _routine("event_risk_intake", owns=["src/event_risks.json"]),
            _routine("daily_full_build", group="feed_build_publish", owns=["src/latest_cockpit_feed.json"]),
            _routine("off_hours_research_queue", owns=["src/research_queue.json"]),
        ],
    }

    problems = crm.validate_manifest(manifest)

    assert any("owned by both" in problem for problem in problems)


def test_manifest_rejects_checked_clear_no_input_behavior():
    manifest = {
        "schema_version": 1,
        "routines": [
            _routine("fundstrat_intake", no_input="Treat missing inputs as checked clear."),
            _routine("catalyst_intake"),
            _routine("broker_position_intake"),
            _routine("uw_cache_refresh", group="market_data_refresh"),
            _routine("daily_synthesis_intake"),
            _routine("signal_log_intake"),
            _routine("social_watch_intake"),
            _routine("event_risk_intake"),
            _routine("daily_full_build", group="feed_build_publish"),
            _routine("off_hours_research_queue"),
        ],
    }

    problems = crm.validate_manifest(manifest)

    assert any("not-checked" in problem or "dark-lane" in problem for problem in problems)


def test_manifest_requires_daily_full_build_convention_input_coverage():
    manifest = crm.load_manifest()
    daily = next(r for r in manifest["routines"] if r["id"] == "daily_full_build")
    daily["convention_inputs"] = [
        row
        for row in daily["convention_inputs"]
        if row.get("key") != "signal_log"
    ]

    problems = crm.validate_manifest(manifest)

    assert any(
        "daily_full_build.convention_inputs missing full_build_runner.DEFAULT_FILES keys" in problem
        and "signal_log" in problem
        for problem in problems
    )


def test_cli_self_test_and_list_pass():
    script = os.path.join(os.path.dirname(__file__), "codex_routine_manifest.py")
    selftest = subprocess.run(
        [sys.executable, script, "--self-test"],
        text=True,
        capture_output=True,
        check=False,
    )
    listing = subprocess.run(
        [sys.executable, script, "--list"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert selftest.returncode == 0, selftest.stderr
    assert "self-test: PASS" in selftest.stdout
    assert listing.returncode == 0, listing.stderr
    assert "daily_full_build" in listing.stdout
    assert "fundstrat_intake" in listing.stdout


def _routine(routine_id, *, group="source_intake", owns=None, no_input="Report source as not checked."):
    doc_by_id = {
        "fundstrat_intake": "src/codex_routines/fundstrat_intake.md",
        "catalyst_intake": "src/codex_routines/catalyst_intake.md",
        "broker_position_intake": "src/codex_routines/broker_position_intake.md",
        "uw_cache_refresh": "src/codex_routines/uw_cache_refresh.md",
        "daily_synthesis_intake": "src/codex_routines/daily_synthesis.md",
        "signal_log_intake": "src/codex_routines/signal_log.md",
        "social_watch_intake": "src/codex_routines/social_watch_intake.md",
        "event_risk_intake": "src/codex_routines/event_risk.md",
        "daily_full_build": "src/codex_routines/daily_full_build.md",
        "off_hours_research_queue": "src/codex_routines/off_hours_research.md",
    }
    routine = {
        "id": routine_id,
        "title": routine_id.replace("_", " ").title(),
        "status": "active",
        "cadence": "daily",
        "doc": doc_by_id[routine_id],
        "separation_group": group,
        "input_boundaries": ["input"],
        "owns": owns or [f"src/{routine_id}.json"],
        "commands": [{"id": "run", "command": "python src/example.py"}],
        "verification": "python -m pytest src/test_example.py -q",
        "no_input_behavior": no_input,
    }
    if routine_id == "daily_full_build":
        routine["convention_inputs"] = [
            {
                "key": key,
                "paths": [f"src/{key}.json"],
                "required": key in {"positions", "theses"},
                "source": "test",
                "missing_behavior": "Build failure if required; otherwise report source as not checked.",
            }
            for key in sorted(crm._full_build_default_keys())
        ]
    return routine
