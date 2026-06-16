"""Operator-tunable configuration for the V3 decision layer.

Two config files, one append-only changelog (all live in ``src/`` per repo
convention):

* ``goal_tunables.json``       â€” Goal & Interface Mandate v1.2 thresholds.
* ``conviction_weights.json``  â€” evidence weighting for the conviction/timing
  engines and the trigger-pattern library.
* ``tunables_changelog.jsonl`` â€” one JSON object per line:
  ``{"date", "et_date", "parameter", "old", "new", "reason"}``.

Design rules carried from the Mandate ("tunables, bands, graded responses"):

* Every threshold is a named parameter; changing a value requires no code
  change (operator edits the JSON; ``update_goal_tunable`` is the convenience
  path that also writes the changelog).
* Zones use enter/exit hysteresis â€” see :func:`zone_state`.
* Every change appends to the changelog â€” see :func:`record_change`.
* **NOT tunable** (Mandate Â§3.4 + standing doctrine): honesty rails
  (dark-lane honesty, stale stamps, evidence traceability, PROVISIONAL guard),
  the existence of ACT/PASS/RECHECK, the MONITOR no-add-nudge rule, the
  never-trim-core rule, and any attempt to feed the pace line into ranking or
  urgency.  The loaders hard-fail (:class:`TunablesGuardError`) if a config
  file tries to define any of those.  Tier D ("should/favor" narrative) is
  track-only by P-SOURCE-CALIBRATION doctrine, so ``tier_base["D"]`` must be 0.

Honest absence: loaders raise :class:`TunablesMissingError` /
:class:`TunablesInvalidError` instead of inventing defaults.  Callers render
"not checked" states; silence is never a default.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SRC = Path(__file__).resolve().parent
GOAL_TUNABLES_PATH = SRC / "goal_tunables.json"
CONVICTION_WEIGHTS_PATH = SRC / "conviction_weights.json"
CHANGELOG_PATH = SRC / "tunables_changelog.jsonl"

_ET = ZoneInfo("America/New_York")

class TunablesError(Exception):
    """Base class for tunables failures."""

class TunablesMissingError(TunablesError):
    """A required config file is absent â€” render 'not checked', never defaults."""

class TunablesInvalidError(TunablesError):
    """A config file is malformed or a value is out of spec."""

class TunablesGuardError(TunablesError):
    """A config file tried to tune a Â§3.4 honesty rail or doctrine constant."""

# ---------------------------------------------------------------------------
# Â§3.4 guard â€” names and name-fragments that must never appear as tunables.
# Exact names first; the substring net is deliberately narrow so legitimate
# parameters (e.g. ``disposition_review_days``) are never caught.
# ---------------------------------------------------------------------------
FORBIDDEN_TUNABLE_KEYS = frozenset(
    {
        "dark_lane_honesty",
        "dark_lane_honesty_enabled",
        "honesty_rails",
        "honesty_rails_enabled",
        "stale_stamps_enabled",
        "stale_data_stamped",
        "evidence_traceability",
        "evidence_traceability_enabled",
        "provisional_guard",
        "provisional_guard_enabled",
        "dispositions_enabled",
        "disposition_required",
        "act_pass_recheck_enabled",
        "forcing_function_enabled",
        "monitor_add_nudge",
        "allow_monitor_add_nudge",
        "trim_core_below_conviction",
        "allow_trim_core_below_conviction",
        "pace_in_ranking",
        "pace_in_urgency",
        "pace_feeds_ranking",
        "pace_feeds_urgency",
    }
)
_FORBIDDEN_FRAGMENTS = ("honesty", "add_nudge", "pace_feeds", "pace_in_")

def _walk_keys(obj: Any):
    """Yield every dict key at every depth of a JSON-like structure."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield str(key)
            yield from _walk_keys(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk_keys(value)

def check_guard(cfg: Any, *, source: str) -> None:
    """Raise :class:`TunablesGuardError` if any forbidden key appears anywhere."""
    for key in _walk_keys(cfg):
        lowered = key.lower()
        if lowered in FORBIDDEN_TUNABLE_KEYS or any(
            frag in lowered for frag in _FORBIDDEN_FRAGMENTS
        ):
            raise TunablesGuardError(
                f"{source}: '{key}' tries to tune a Â§3.4 honesty rail or doctrine "
                "constant. Honesty rails, ACT/PASS/RECHECK, MONITOR no-add-nudge, "
                "never-trim-core, and pace-line isolation are NOT tunable."
            )

# ---------------------------------------------------------------------------
# goal_tunables.json â€” strict per-key spec (name -> (kind, lo, hi))
# ---------------------------------------------------------------------------
_GOAL_SPEC: dict[str, tuple[str, float | None, float | None]] = {
    "fi_target": ("int", 100_000, 1_000_000_000),
    "window_horizon": ("date", None, None),
    "window_review_cadence_days": ("int", 1, 3650),
    "dd_caution_enter_pct": ("num", 0, 100),
    "dd_caution_exit_pct": ("num", 0, 100),
    "dd_hard_enter_pct": ("num", 0, 100),
    "dd_hard_exit_pct": ("num", 0, 100),
    "act_now_horizon_days": ("int", 0, 365),
    "orphan_escalate_days": ("int", 0, 365),
    "orphan_pin_days": ("int", 0, 365),
    "signals_high_min": ("num", 0, 100),
    "signals_mod_min": ("num", 0, 100),
    "uw_flow_fresh_days": ("int", 0, 365),
    "impact_material_pct_book": ("num", 0, 100),
    "impact_material_pct_sleeve": ("num", 0, 100),
    "daily_card_min": ("int", 0, 50),
    "daily_card_max": ("int", 1, 50),
    "evidence_tap_depth_max": ("int", 1, 10),
    "surface_answer_seconds": ("int", 1, 3600),
    "recheck_default_days": ("int", 1, 365),
    "disposition_review_days": ("int", 1, 365),
    "concentration_rail_enabled": ("bool", None, None),
    "concentration_rail_pct": ("num", 0, 100),
}

def _read_json(path: Path) -> Any:
    if not path.exists():
        raise TunablesMissingError(
            f"{path.name} is absent â€” tunables are NOT loaded (honest absence; "
            "no silent defaults)."
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TunablesInvalidError(f"{path.name} is not valid JSON: {exc}") from exc

def _check_value(name: str, value: Any, kind: str, lo, hi, *, source: str) -> None:
    if kind == "bool":
        if not isinstance(value, bool):
            raise TunablesInvalidError(f"{source}: {name} must be true/false.")
        return
    if kind == "date":
        if not isinstance(value, str):
            raise TunablesInvalidError(f"{source}: {name} must be 'YYYY-MM-DD'.")
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise TunablesInvalidError(
                f"{source}: {name}='{value}' is not a YYYY-MM-DD date."
            ) from exc
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TunablesInvalidError(f"{source}: {name} must be a number.")
    if kind == "int" and int(value) != value:
        raise TunablesInvalidError(f"{source}: {name} must be an integer.")
    if lo is not None and value < lo:
        raise TunablesInvalidError(f"{source}: {name}={value} is below minimum {lo}.")
    if hi is not None and value > hi:
        raise TunablesInvalidError(f"{source}: {name}={value} is above maximum {hi}.")

def load_goal_tunables(path: Path | str = GOAL_TUNABLES_PATH) -> dict[str, Any]:
    """Load + strictly validate goal_tunables.json (unknown keys rejected)."""
    path = Path(path)
    cfg = _read_json(path)
    if not isinstance(cfg, dict):
        raise TunablesInvalidError(f"{path.name}: top level must be an object.")
    check_guard(cfg, source=path.name)
    unknown = sorted(set(cfg) - set(_GOAL_SPEC))
    if unknown:
        raise TunablesInvalidError(
            f"{path.name}: unknown parameter(s) {unknown}. Valid names: "
            f"{sorted(_GOAL_SPEC)}"
        )
    missing = sorted(set(_GOAL_SPEC) - set(cfg))
    if missing:
        raise TunablesInvalidError(f"{path.name}: missing parameter(s) {missing}.")
    for name, (kind, lo, hi) in _GOAL_SPEC.items():
        _check_value(name, cfg[name], kind, lo, hi, source=path.name)
    # Hysteresis sanity: exits must clear below their enters.
    if cfg["dd_caution_exit_pct"] >= cfg["dd_caution_enter_pct"]:
        raise TunablesInvalidError(
            f"{path.name}: dd_caution_exit_pct must be < dd_caution_enter_pct "
            "(hysteresis â€” zones enter at one value, clear at another)."
        )
    if cfg["dd_hard_exit_pct"] >= cfg["dd_hard_enter_pct"]:
        raise TunablesInvalidError(
            f"{path.name}: dd_hard_exit_pct must be < dd_hard_enter_pct."
        )
    if cfg["daily_card_min"] > cfg["daily_card_max"]:
        raise TunablesInvalidError(
            f"{path.name}: daily_card_min cannot exceed daily_card_max."
        )
    return cfg

_WEIGHTS_REQUIRED_TOP_KEYS = {
    "tier_base",
    "tier_window_days",
    "calibration_bands",
    "group_caps",
    "read_to_5",
    "uw_points",
    "insight_match_points",
    "insight_triage_boost",
    "insight_max_active",
    "insight_stale_days",
    "priority_blend",
    "pattern_thresholds",
    "timing",
}
_WEIGHTS_OPTIONAL_TOP_KEYS = {"battery_sources"}
_WEIGHTS_TOP_KEYS = _WEIGHTS_REQUIRED_TOP_KEYS | _WEIGHTS_OPTIONAL_TOP_KEYS
_BATTERY_SOURCE_KEYS = {
    "deepdive_battery",
    "price_rotation",
    "uw_opportunity",
    "group_rotation",
}


def _validate_battery_sources(section: Any, *, source: str) -> None:
    if not isinstance(section, dict):
        raise TunablesInvalidError(f"{source}: battery_sources must be an object.")
    unknown = sorted(set(section) - _BATTERY_SOURCE_KEYS)
    if unknown:
        raise TunablesInvalidError(
            f"{source}: battery_sources unknown source key(s) {unknown}. "
            f"Valid: {sorted(_BATTERY_SOURCE_KEYS)}"
        )
    for key, row in section.items():
        if not isinstance(row, dict):
            raise TunablesInvalidError(
                f"{source}: battery_sources[{key}] must be an object."
            )
        expected = {"enabled", "weight"}
        if set(row) != expected:
            raise TunablesInvalidError(
                f"{source}: battery_sources[{key}] must define exactly "
                f"{sorted(expected)}."
            )
        if not isinstance(row["enabled"], bool):
            raise TunablesInvalidError(
                f"{source}: battery_sources[{key}].enabled must be true/false."
            )
        weight = row["weight"]
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise TunablesInvalidError(
                f"{source}: battery_sources[{key}].weight must be a number in [0, 1]."
            )
        if weight < 0 or weight > 1:
            raise TunablesInvalidError(
                f"{source}: battery_sources[{key}].weight must be in [0, 1]."
            )

def load_conviction_weights(path: Path | str = CONVICTION_WEIGHTS_PATH) -> dict[str, Any]:
    """Load + validate conviction_weights.json (doctrine constraints enforced)."""
    path = Path(path)
    cfg = _read_json(path)
    if not isinstance(cfg, dict):
        raise TunablesInvalidError(f"{path.name}: top level must be an object.")
    check_guard(cfg, source=path.name)
    unknown = sorted(set(cfg) - _WEIGHTS_TOP_KEYS)
    if unknown:
        raise TunablesInvalidError(
            f"{path.name}: unknown section(s) {unknown}. Valid: {sorted(_WEIGHTS_TOP_KEYS)}"
        )
    missing = sorted(_WEIGHTS_REQUIRED_TOP_KEYS - set(cfg))
    if missing:
        raise TunablesInvalidError(f"{path.name}: missing section(s) {missing}.")
    if "battery_sources" in cfg:
        _validate_battery_sources(cfg["battery_sources"], source=path.name)

    tier_base = cfg["tier_base"]
    if set(tier_base) != {"A", "B", "C", "D"}:
        raise TunablesInvalidError(f"{path.name}: tier_base must define A, B, C, D.")
    if tier_base["D"] != 0:
        raise TunablesGuardError(
            f"{path.name}: tier_base['D'] must be 0 â€” Tier D ('should/favor' "
            "narrative) is track-only by P-SOURCE-CALIBRATION doctrine and never "
            "scores. The persistence detector is the only rescue path."
        )
    for tier, base in tier_base.items():
        if isinstance(base, bool) or not isinstance(base, (int, float)) or base < 0:
            raise TunablesInvalidError(f"{path.name}: tier_base[{tier}] must be >= 0.")

    for group, cap in cfg["group_caps"].items():
        if isinstance(cap, bool) or not isinstance(cap, (int, float)) or cap <= 0:
            raise TunablesInvalidError(f"{path.name}: group_caps[{group}] must be > 0.")
    if "operator_insight" not in cfg["group_caps"]:
        raise TunablesInvalidError(
            f"{path.name}: group_caps must include 'operator_insight'."
        )

    read_to_5 = cfg["read_to_5"]
    expected_read_keys = {
        "high_score",
        "moderate_score",
        "moderate_0_66_score",
        "moderate_0_33_score",
        "floor_score",
        "mid_fraction",
        "low_fraction",
    }
    if not isinstance(read_to_5, dict) or set(read_to_5) != expected_read_keys:
        raise TunablesInvalidError(
            f"{path.name}: read_to_5 must define {sorted(expected_read_keys)}."
        )
    score_path = [
        read_to_5["high_score"],
        read_to_5["moderate_score"],
        read_to_5["moderate_0_66_score"],
        read_to_5["moderate_0_33_score"],
        read_to_5["floor_score"],
    ]
    if score_path != [5, 4, 3, 2, 1]:
        raise TunablesInvalidError(
            f"{path.name}: read_to_5 score ladder must be 5, 4, 3, 2, 1."
        )
    for key in ("mid_fraction", "low_fraction"):
        value = read_to_5[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not (0 < value < 1):
            raise TunablesInvalidError(
                f"{path.name}: read_to_5['{key}'] must be a fraction between 0 and 1."
            )
    if read_to_5["low_fraction"] >= read_to_5["mid_fraction"]:
        raise TunablesInvalidError(
            f"{path.name}: read_to_5 low_fraction must be below mid_fraction."
        )

    uw = cfg["uw_points"]
    if uw.get("inconclusive") != 0:
        raise TunablesGuardError(
            f"{path.name}: uw_points['inconclusive'] must be 0 â€” a successful "
            "fetch is not a direction (V2 interpretation contract)."
        )
    if not (isinstance(uw.get("contradicts"), (int, float)) and uw["contradicts"] < 0):
        raise TunablesInvalidError(
            f"{path.name}: uw_points['contradicts'] must be negative."
        )
    return cfg

# ---------------------------------------------------------------------------
# Changelog + updates
# ---------------------------------------------------------------------------
def record_change(
    parameter: str,
    old: Any,
    new: Any,
    reason: str,
    *,
    path: Path | str = CHANGELOG_PATH,
) -> dict[str, Any]:
    """Append one change row to the append-only changelog and return it."""
    if not str(reason).strip():
        raise TunablesInvalidError("A one-line reason is required for every change.")
    now = datetime.now(timezone.utc)
    row = {
        "date": now.isoformat(timespec="seconds"),
        "et_date": now.astimezone(_ET).strftime("%Y-%m-%d"),
        "parameter": parameter,
        "old": old,
        "new": new,
        "reason": str(reason).strip(),
    }
    with Path(path).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return row

def update_goal_tunable(
    name: str,
    new: Any,
    reason: str,
    *,
    path: Path | str = GOAL_TUNABLES_PATH,
    changelog_path: Path | str = CHANGELOG_PATH,
) -> dict[str, Any]:
    """Validate, write, and log a single goal-tunable change."""
    path = Path(path)
    cfg = load_goal_tunables(path)
    if name not in _GOAL_SPEC:
        raise TunablesInvalidError(f"Unknown tunable '{name}'.")
    kind, lo, hi = _GOAL_SPEC[name]
    _check_value(name, new, kind, lo, hi, source=path.name)
    old = cfg[name]
    cfg[name] = new
    # Re-run cross-field checks on the candidate config before writing.
    tmp = json.dumps(cfg)
    path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    try:
        load_goal_tunables(path)
    except TunablesError:
        # Roll back the file write, then re-raise.
        cfg[name] = old
        path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        raise
    del tmp
    return record_change(name, old, new, reason, path=changelog_path)

def get(name: str, *, cfg: dict[str, Any] | None = None) -> Any:
    """Convenience accessor for a single goal tunable."""
    cfg = cfg if cfg is not None else load_goal_tunables()
    if name not in cfg:
        raise TunablesInvalidError(f"Unknown tunable '{name}'.")
    return cfg[name]

# ---------------------------------------------------------------------------
# Hysteresis helper â€” zones enter at one value and clear at another.
# ---------------------------------------------------------------------------
def zone_state(value: float, enter: float, exit_: float, prior_in_zone: bool) -> bool:
    """Two-threshold hysteresis for 'high value = in zone' gates.

    Enter when ``value >= enter``; once in, stay in until ``value <= exit_``.
    ``exit_`` must be strictly below ``enter`` (no flapping at a single line).
    """
    if exit_ >= enter:
        raise TunablesInvalidError("zone_state: exit threshold must be below enter.")
    if prior_in_zone:
        return value > exit_
    return value >= enter
