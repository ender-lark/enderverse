import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tunables
from tunables import (
    TunablesGuardError,
    TunablesInvalidError,
    TunablesMissingError,
    check_guard,
    load_conviction_weights,
    load_goal_tunables,
    record_change,
    update_goal_tunable,
    zone_state,
)

def _write(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path

def test_repo_goal_tunables_load_and_match_v1_2_spec():
    cfg = load_goal_tunables()
    assert cfg["fi_target"] == 3_000_000
    assert cfg["window_horizon"] == "2027-12-31"
    assert cfg["signals_high_min"] == 4
    assert cfg["daily_card_max"] == 3
    assert cfg["concentration_rail_enabled"] is False
    assert cfg["concentration_rail_pct"] == 55

def test_repo_conviction_weights_load():
    cfg = load_conviction_weights()
    assert cfg["tier_base"]["A"] == 1.0
    assert cfg["tier_base"]["D"] == 0.0
    assert cfg["uw_points"]["inconclusive"] == 0
    assert cfg["group_caps"]["operator_insight"] == 1.0

def test_missing_file_is_honest_absence(tmp_path):
    with pytest.raises(TunablesMissingError):
        load_goal_tunables(tmp_path / "nope.json")

def test_unknown_goal_key_rejected(tmp_path):
    cfg = load_goal_tunables()
    cfg["totally_new_knob"] = 1
    path = _write(tmp_path, "goal_tunables.json", cfg)
    with pytest.raises(TunablesInvalidError):
        load_goal_tunables(path)

def test_missing_goal_key_rejected(tmp_path):
    cfg = load_goal_tunables()
    cfg.pop("fi_target")
    path = _write(tmp_path, "goal_tunables.json", cfg)
    with pytest.raises(TunablesInvalidError):
        load_goal_tunables(path)

def test_range_violation_rejected(tmp_path):
    cfg = load_goal_tunables()
    cfg["dd_caution_enter_pct"] = 250
    path = _write(tmp_path, "goal_tunables.json", cfg)
    with pytest.raises(TunablesInvalidError):
        load_goal_tunables(path)

def test_hysteresis_cross_field_check(tmp_path):
    cfg = load_goal_tunables()
    cfg["dd_caution_exit_pct"] = cfg["dd_caution_enter_pct"]  # exit must be < enter
    path = _write(tmp_path, "goal_tunables.json", cfg)
    with pytest.raises(TunablesInvalidError):
        load_goal_tunables(path)

def test_guard_blocks_honesty_rail_tuning(tmp_path):
    cfg = load_goal_tunables()
    cfg["dark_lane_honesty"] = False
    path = _write(tmp_path, "goal_tunables.json", cfg)
    with pytest.raises(TunablesGuardError):
        load_goal_tunables(path)

def test_guard_blocks_nested_and_fragment_keys():
    with pytest.raises(TunablesGuardError):
        check_guard({"timing": {"pace_in_ranking": True}}, source="x")
    with pytest.raises(TunablesGuardError):
        check_guard({"a": [{"allow_monitor_add_nudge": 1}]}, source="x")
    with pytest.raises(TunablesGuardError):
        check_guard({"honesty_rails_strength": 0.5}, source="x")  # fragment net
    # Legitimate parameter that contains 'disposition' must pass.
    check_guard({"disposition_review_days": 30}, source="x")

def test_tier_d_must_stay_zero(tmp_path):
    cfg = load_conviction_weights()
    cfg["tier_base"]["D"] = 0.2
    path = _write(tmp_path, "conviction_weights.json", cfg)
    with pytest.raises(TunablesGuardError):
        load_conviction_weights(path)

def test_uw_inconclusive_must_stay_zero(tmp_path):
    cfg = load_conviction_weights()
    cfg["uw_points"]["inconclusive"] = 0.3
    path = _write(tmp_path, "conviction_weights.json", cfg)
    with pytest.raises(TunablesGuardError):
        load_conviction_weights(path)

def test_record_change_appends_jsonl(tmp_path):
    log = tmp_path / "log.jsonl"
    row1 = record_change("signals_high_min", 4, 5, "calibration n reached", path=log)
    row2 = record_change("signals_high_min", 5, 4, "reverted after review", path=log)
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["new"] == 5
    assert json.loads(lines[1])["reason"] == "reverted after review"
    assert row1["parameter"] == row2["parameter"] == "signals_high_min"
    assert row1["et_date"]

def test_record_change_requires_reason(tmp_path):
    with pytest.raises(TunablesInvalidError):
        record_change("x", 1, 2, "   ", path=tmp_path / "log.jsonl")

def test_update_goal_tunable_roundtrip(tmp_path):
    src_cfg = load_goal_tunables()
    path = _write(tmp_path, "goal_tunables.json", src_cfg)
    log = tmp_path / "log.jsonl"
    row = update_goal_tunable(
        "recheck_default_days", 7, "rechecks landing too soon", path=path, changelog_path=log
    )
    assert row["old"] == 5 and row["new"] == 7
    assert load_goal_tunables(path)["recheck_default_days"] == 7
    assert len(log.read_text().strip().splitlines()) == 1

def test_update_goal_tunable_rolls_back_on_cross_field_failure(tmp_path):
    src_cfg = load_goal_tunables()
    path = _write(tmp_path, "goal_tunables.json", src_cfg)
    log = tmp_path / "log.jsonl"
    with pytest.raises(TunablesInvalidError):
        update_goal_tunable(
            "dd_caution_exit_pct", 15, "bad: equals enter", path=path, changelog_path=log
        )
    # File rolled back, nothing logged.
    assert load_goal_tunables(path)["dd_caution_exit_pct"] == 12
    assert not log.exists() or not log.read_text().strip()

def test_zone_state_hysteresis():
    # Drawdown caution: enter 15, exit 12.
    assert zone_state(14.9, 15, 12, prior_in_zone=False) is False
    assert zone_state(15.0, 15, 12, prior_in_zone=False) is True
    # Inside the band: state persists (no flapping).
    assert zone_state(13.5, 15, 12, prior_in_zone=True) is True
    assert zone_state(13.5, 15, 12, prior_in_zone=False) is False
    # Clears only at/below exit.
    assert zone_state(12.0, 15, 12, prior_in_zone=True) is False
    with pytest.raises(TunablesInvalidError):
        zone_state(10, 12, 12, prior_in_zone=False)

def test_changelog_file_exists_in_repo():
    assert tunables.CHANGELOG_PATH.exists()
