"""Tests for the parabolic screener's Phase 3 -> acceleration auto-arm hook.

The hook is the bridge docs/efficacy_gaps.md GAP 1 was missing: when the screener
classifies a name as Phase 3 (parabola) it arms an `acceleration` trigger in the
trigger registry via the existing spine path. These tests prove it builds the
right row, writes idempotently, respects a fired trigger, and produces a row the
spine can actually fire -- without touching the research-surface output.
"""
from __future__ import annotations

import json

import parabolic_setup_screener as ps
import trigger_check
from parabolic_setup_screener import FeatureScores, ScreenResult


def _result(ticker: str, phase: str) -> ScreenResult:
    return ScreenResult(
        ticker=ticker, score=0.0, surface_tier="SKIP", phase=phase, features=FeatureScores()
    )


def test_phase3_acceleration_trigger_built_only_for_phase3():
    # Non-Phase-3 results map to None so a caller can sweep a whole screen.
    assert ps.phase3_acceleration_trigger(_result("VIAV", "Phase 2 (recognition)")) is None
    assert ps.phase3_acceleration_trigger(_result("BWXT", "Phase 0 (boredom)")) is None

    trig = ps.phase3_acceleration_trigger(
        _result("MU", "Phase 3 (parabola)"), registered_at="2026-06-14T12:00:00Z"
    )
    assert trig is not None
    assert trig["id"] == "parabolic-accel-mu"
    assert trig["ticker"] == "MU"
    assert trig["condition"]["type"] == "acceleration"
    assert trig["status"] == "armed"
    # A real, forward-looking arming window.
    assert trig["expires"] > trig["registered_at"][:10]
    # Required params are present and resolvable by the spine.
    assert trig["condition"]["params"]["threshold"] == ps.DEFAULT_ACCEL_PCT_THRESHOLD
    assert trig["condition"]["params"]["min_phase"] == ps.DEFAULT_ACCEL_MIN_PHASE


def test_auto_armed_trigger_fires_in_the_spine():
    trig = ps.phase3_acceleration_trigger(
        _result("MU", "Phase 3 (parabola)"), registered_at="2026-06-14T12:00:00Z"
    )
    fired = trigger_check.evaluate(
        [dict(trig)],
        trigger_check.quote_fn_from_map({"MU": {"pct_change_5d": 44.0, "phase": "Phase 3 (parabola)"}}),
        as_of="2026-06-15T14:00:00Z",
    )
    assert [row["id"] for row in fired] == ["parabolic-accel-mu"]


def test_register_writes_only_phase3_names_and_is_idempotent(tmp_path):
    reg = tmp_path / "trigger_registry.json"
    reg.write_text("[]", encoding="utf-8")
    results = [
        _result("MU", "Phase 3 (parabola)"),
        _result("VIAV", "Phase 2 (recognition)"),  # skipped
    ]

    armed = ps.register_phase3_acceleration_triggers(
        results, registry_path=reg, registered_at="2026-06-14T12:00:00Z"
    )
    assert [t["ticker"] for t in armed] == ["MU"]
    saved = json.loads(reg.read_text(encoding="utf-8"))
    assert [r["id"] for r in saved] == ["parabolic-accel-mu"]

    # Re-running upserts the same id -- no duplicate row.
    ps.register_phase3_acceleration_triggers(
        results, registry_path=reg, registered_at="2026-06-14T13:00:00Z"
    )
    saved_again = json.loads(reg.read_text(encoding="utf-8"))
    assert len(saved_again) == 1


def test_register_does_not_reset_a_fired_trigger(tmp_path):
    reg = tmp_path / "trigger_registry.json"
    fired_row = ps.phase3_acceleration_trigger(
        _result("MU", "Phase 3 (parabola)"), registered_at="2026-06-14T12:00:00Z"
    )
    fired_row["status"] = "fired"
    reg.write_text(json.dumps([fired_row]), encoding="utf-8")

    ps.register_phase3_acceleration_triggers([_result("MU", "Phase 3 (parabola)")], registry_path=reg)

    saved = json.loads(reg.read_text(encoding="utf-8"))
    assert len(saved) == 1
    assert saved[0]["status"] == "fired"  # upsert respects terminal status


def test_register_returns_empty_when_nothing_is_phase3(tmp_path):
    reg = tmp_path / "trigger_registry.json"
    reg.write_text("[]", encoding="utf-8")
    armed = ps.register_phase3_acceleration_triggers(
        [_result("VIAV", "Phase 2 (recognition)")], registry_path=reg
    )
    assert armed == []
    assert json.loads(reg.read_text(encoding="utf-8")) == []
