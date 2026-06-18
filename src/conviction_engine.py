"""Conviction engine â€” weighted evidence â†’ capped independence groups â†’ read.

The unified conviction read for a name. Pieces existed across V2 (fundstrat
lane metadata, UW endpoint interpretation, source-call tiers); this engine is
where they finally SUM â€” with independence discipline:

* **Item weight** = ``tier_base[A/B/C/D] Ã— calibration multiplier Ã— freshness
  decay``. Tiers per the canonical 4-tier call ladder (P-SOURCE-CALIBRATION).
  Tier D ("should/favor" narrative) is track-only and NEVER scores â€” enforced
  here and in the tunables guard. Undated items cannot decay-score and are
  track-only (honesty over guesswork).
* **Calibration** = hit-rate bands per sourceÃ—tier once ``min_n`` scored calls
  exist; absent/insufficient history â†’ INSUFFICIENT_DATA 1.0Ã— (earned weight,
  never asserted).
* **Groups** (items cap inside, groups sum across): ``fs`` (all Fundstrat
  authors â€” one cluster), ``uw`` (V2 interpretation semantics verbatim:
  supports=+1, full battery=1.25, single-day flowâ‰¤0.5 pending OI confirm,
  inconclusive=0 because a fetch is not a direction, contradicts=âˆ’1 AND forces
  re-check), ``operator_insight`` (register hook 2 â€” max, never sum),
  ``institutional`` (honest not-checked stub until the 13F/insider wiring
  chunk).
* **Read**: HIGH/MODERATE/LOW from weighted points vs ``signals_high_min`` /
  ``signals_mod_min`` (operator tunables; starting points for the learning
  loop). Cross-group convergence is the only path up â€” same-group repetition
  is capped away. Every read ships with "what would raise this" and explicit
  ``not_checked`` lanes.

Pure functions; I/O only in the small adapters at the bottom.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import battery_evidence as be
from insight_register import conviction_points as _insight_points
from insight_register import match as _insight_match

SRC = Path(__file__).resolve().parent
SOURCE_CALLS_PATH = SRC / "source_calls.json"
TOP_PROSPECTS_PATH = SRC / "top_prospects.json"
FEED_PATH = SRC / "latest_cockpit_feed.json"

GROUPS = ("fs", "uw", "operator_insight", "institutional")
TIERS = ("A", "B", "C", "D")
_FS_SOURCES = {"fundstrat", "newton", "lee", "farrell", "tlee", "mark newton", "tom lee"}
_EPS = 1e-9
_BAND_ORDER = {"LOW": 0, "MODERATE": 1, "HIGH": 2}
_BAND_BY_ORDER = {v: k for k, v in _BAND_ORDER.items()}

CONFLICTED = "CONFLICTED"        # NEW read sentinel (distinct from LOW/NEUTRAL)
RECHECK = "RE-CHECK"             # NEW direction sentinel (already in decision_card.DIRECTIONS)
CONFLICT_STRENGTH_5 = 3          # fixed "loud question" rung — module constant, NOT a tunable

def _today(today: str | date | None) -> date:
    if today is None:
        return date.today()
    if isinstance(today, date):
        return today
    return datetime.strptime(str(today), "%Y-%m-%d").date()

# ---------------------------------------------------------------------------
# Calibration â€” earned multipliers, honest when history is thin
# ---------------------------------------------------------------------------
def calibration_multiplier(
    source: str, tier: str, rates: dict[str, Any] | None, weights: dict[str, Any]
) -> tuple[float, str]:
    bands = weights["calibration_bands"]
    mults = bands["multipliers"]
    row = ((rates or {}).get(str(source).lower()) or {}).get(tier)
    if not isinstance(row, dict):
        return float(mults["INSUFFICIENT_DATA"]), "INSUFFICIENT_DATA"
    n = row.get("n", 0)
    rate = row.get("win_rate")
    if not isinstance(n, (int, float)) or n < bands["min_n"] or not isinstance(rate, (int, float)):
        return float(mults["INSUFFICIENT_DATA"]), "INSUFFICIENT_DATA"
    if rate <= bands["consistent_miss_max"]:
        return float(mults["CONSISTENT_MISS"]), "CONSISTENT_MISS"
    if rate <= bands["below_breakeven_max"]:
        return float(mults["BELOW_BREAKEVEN"]), "BELOW_BREAKEVEN"
    if rate <= bands["normal_max"]:
        return float(mults["NORMAL"]), "NORMAL"
    return float(mults["HIGH_CONVICTION"]), "HIGH_CONVICTION"

# ---------------------------------------------------------------------------
# Item scoring â€” tier Ã— calibration Ã— freshness decay
# ---------------------------------------------------------------------------
def score_item(
    item: dict[str, Any],
    *,
    weights: dict[str, Any],
    rates: dict[str, Any] | None = None,
    today: str | date | None = None,
) -> dict[str, Any]:
    now = _today(today)
    tier = item.get("tier")
    source = str(item.get("source") or "unknown")
    direction = str(item.get("direction") or "bullish").lower()
    sign = -1.0 if direction in ("bearish", "short", "sell", "sell_fast", "avoid") else 1.0

    out: dict[str, Any] = {
        "source": source,
        "tier": tier,
        "note": str(item.get("note") or "")[:160],
        "date": item.get("date"),
        "direction": "bearish" if sign < 0 else "bullish",
        "kind": item.get("kind", "call"),
    }

    if tier not in TIERS or tier == "D":
        out.update(weight=0.0, track_only=True, expired=False, fresh=0.0,
                   reason="Tier D / unknown tier â€” track-only by doctrine, never scores")
        return out

    raw_date = item.get("date")
    try:
        item_date = datetime.strptime(str(raw_date), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        out.update(weight=0.0, track_only=True, expired=False, fresh=0.0,
                   reason="undated item cannot decay-score â€” track-only")
        return out

    window = int(weights["tier_window_days"].get(tier, 0))
    age = (now - item_date).days
    if age < 0:
        age = 0
    fresh = max(0.0, 1.0 - (age / window)) if window > 0 else 0.0
    expired = age > window
    base = float(weights["tier_base"][tier])
    mult, band = calibration_multiplier(source, tier, rates, weights)
    weight = 0.0 if expired else sign * base * mult * fresh
    out.update(
        weight=round(weight, 4), base=base, calibration=mult, calibration_band=band,
        fresh=round(fresh, 3), age_days=age, window_days=window,
        expired=expired, track_only=False,
    )
    return out

def _signed_capped_sum(scored: list[dict[str, Any]], cap: float) -> dict[str, Any]:
    live = [s for s in scored if not s.get("track_only") and not s.get("expired")]
    raw = sum(s["weight"] for s in live)
    points = max(-cap, min(cap, raw))
    return {
        "points": round(points, 3),
        "raw": round(raw, 3),
        "capped": abs(raw) > abs(points) + 1e-9,
        "items": scored,
        "n_live": len(live),
    }

def fs_group(
    items: list[dict[str, Any]],
    *,
    weights: dict[str, Any],
    rates: dict[str, Any] | None = None,
    today: str | date | None = None,
) -> dict[str, Any]:
    scored = [score_item(i, weights=weights, rates=rates, today=today) for i in items]
    return _signed_capped_sum(scored, float(weights["group_caps"]["fs"]))

def uw_group(uw_state: dict[str, Any] | None, *, weights: dict[str, Any]) -> dict[str, Any]:
    """V2 endpoint-interpretation semantics, verbatim."""
    pts_map = weights["uw_points"]
    cap = float(weights["group_caps"]["uw"])
    state = uw_state or {}
    interp = state.get("interpretation")
    note = state.get("note") or ""
    force_recheck = False
    if interp == "supports":
        pts = float(pts_map["battery_full"]) if state.get("battery_complete") else float(pts_map["supports"])
        why = "same-session UW evidence SUPPORTS" + (" (full multi-day battery)" if state.get("battery_complete") else "")
    elif interp == "contradicts":
        pts = float(pts_map["contradicts"])
        force_recheck = True
        why = "same-session UW evidence CONTRADICTS â€” re-check forced"
    elif interp == "inconclusive":
        pts = 0.0
        why = "UW proof inconclusive â€” a successful fetch is not a direction"
    elif state.get("single_day_flow"):
        pts = float(pts_map["single_day_flow_max"])
        why = "single-day directional flow only â€” unconfirmed until next-morning OI"
    else:
        pts = 0.0
        why = "no same-session UW proof captured"
    return {
        "points": round(max(-cap, min(cap, pts)), 3),
        "why": why + (f" â€” {note}" if note else ""),
        "interpretation": interp,
        "single_day_flow": bool(state.get("single_day_flow")),
        "battery_complete": bool(state.get("battery_complete")),
        "force_recheck": force_recheck,
        "date": state.get("date"),
    }

def institutional_group(
    inst_state: dict[str, Any] | None, *, weights: dict[str, Any]
) -> dict[str, Any]:
    cap = float(weights["group_caps"]["institutional"])
    if not inst_state:
        return {
            "points": 0.0,
            "status": "not_checked",
            "why": "13F/insider scans not wired into the feed yet (orphan-wiring chunk) â€” not checked â‰  no signal",
        }
    pts = float(inst_state.get("points", 0.0))
    return {
        "points": round(max(-cap, min(cap, pts)), 3),
        "status": inst_state.get("status", "ok"),
        "why": inst_state.get("why", ""),
    }

def _read_from_magnitude(magnitude: float, *, high_min: float, mod_min: float) -> str:
    return "HIGH" if magnitude >= high_min else "MODERATE" if magnitude >= mod_min else "LOW"

def _strength_5(
    magnitude: float, *, high_min: float, mod_min: float, weights: dict[str, Any]
) -> int:
    mapping = weights["read_to_5"]
    if magnitude >= high_min:
        return int(mapping["high_score"])
    if magnitude >= mod_min:
        return int(mapping["moderate_score"])
    if magnitude >= mod_min * float(mapping["mid_fraction"]):
        return int(mapping["moderate_0_66_score"])
    if magnitude >= mod_min * float(mapping["low_fraction"]):
        return int(mapping["moderate_0_33_score"])
    return int(mapping["floor_score"])

def _direction_from_points(points: float) -> str:
    if points > _EPS:
        return "BUY"
    if points < -_EPS:
        return "SELL"
    return "NEUTRAL"

def _conflict_sides(
    groups: dict[str, float],
    *,
    force_recheck: bool,
) -> dict[str, Any]:
    """Split evidence into non-negative bull/bear MAGNITUDES and decide if the
    name is in genuine two-sided opposition (a loud QUESTION), distinct from
    quiet absence. A signed sum hides this; opposed groups never cancel here.
    """
    bull_points = round(sum(v for v in groups.values() if v > _EPS), 3)
    bear_points = round(sum(-v for v in groups.values() if v < -_EPS), 3)
    bull_groups = sorted(k for k, v in groups.items() if v > _EPS)
    bear_groups = sorted(k for k, v in groups.items() if v < -_EPS)
    material_two_sided = bool(bull_groups and bear_groups)
    # A forced re-check (UW contradicts) is categorical: conflict even if the
    # contradicting group's points are capped small, or one-sided.
    conflicted = material_two_sided or force_recheck
    opposition = round(min(bull_points, bear_points), 3) if material_two_sided else 0.0
    return {
        "conflicted": conflicted,
        "material_two_sided": material_two_sided,
        "bull_points": bull_points,
        "bear_points": bear_points,
        "bull_groups": bull_groups,
        "bear_groups": bear_groups,
        "deciding_groups": bull_groups + bear_groups,
        "opposition_magnitude": opposition,
        "force_recheck": force_recheck,
    }

def _layer_settings(weights: dict[str, Any]) -> dict[str, Any]:
    section = weights.get("conviction_layers")
    if isinstance(section, dict):
        return section
    return {"mode": "off"}

def _layer_mode(weights: dict[str, Any]) -> str:
    mode = str(_layer_settings(weights).get("mode") or "off").lower()
    return mode if mode in {"off", "shadow", "active"} else "off"

def _sleeve_subjects(settings: dict[str, Any]) -> dict[str, list[str]]:
    subjects = settings.get("sleeve_subjects")
    return subjects if isinstance(subjects, dict) else {}

def _ticker_to_sleeve(settings: dict[str, Any]) -> dict[str, str]:
    mapping = settings.get("ticker_to_sleeve")
    return mapping if isinstance(mapping, dict) else {}

def _sleeve_category(settings: dict[str, Any], sleeve: str) -> str:
    categories = settings.get("sleeve_categories")
    if isinstance(categories, dict):
        return str(categories.get(sleeve) or sleeve)
    return sleeve

def _is_sleeve_proxy(ticker: str, settings: dict[str, Any]) -> bool:
    tick = ticker.upper()
    return any(tick in {str(v).upper() for v in values} for values in _sleeve_subjects(settings).values())

def _sleeve_for_ticker(ticker: str, settings: dict[str, Any]) -> str | None:
    sleeve = _ticker_to_sleeve(settings).get(ticker.upper())
    return str(sleeve).upper() if sleeve else None

def _sector_shelf_life_days(item: dict[str, Any], settings: dict[str, Any]) -> int:
    shelf = settings.get("sector_shelf_life_days") or {}
    kind = str(item.get("kind") or "").lower()
    if "monthly" in kind or "bible" in kind or "stance" in kind:
        return int(shelf.get("monthly_stance", 35))
    if item.get("catalyst_until_resolved"):
        return int(shelf.get("catalyst_backstop", 35))
    return int(shelf.get("daily_tactical", shelf.get("default", 7)))

def score_sector_item(
    item: dict[str, Any],
    *,
    weights: dict[str, Any],
    rates: dict[str, Any] | None = None,
    today: str | date | None = None,
) -> dict[str, Any]:
    """Score a sector/sleeve item using sector shelf-life settings.

    This deliberately does not change name-specific scoring. Sector evidence is
    a shadow layer with shorter shelf lives and a capped lift.
    """
    settings = _layer_settings(weights)
    window_days = int(item.get("sector_window_days") or _sector_shelf_life_days(item, settings))
    sector_weights = dict(weights)
    sector_weights["tier_window_days"] = {tier: window_days for tier in TIERS}
    scored = score_item(item, weights=sector_weights, rates=rates, today=today)
    scored["sector_window_days"] = window_days
    scored["sector_subject"] = item.get("sector_subject") or item.get("source_call_ticker")
    scored["sleeve"] = item.get("sleeve")
    scored["category"] = item.get("category")
    scored["source_call_id"] = item.get("source_call_id")
    return scored

def _item_week(item: dict[str, Any]) -> str:
    raw = item.get("date")
    try:
        iso = datetime.strptime(str(raw), "%Y-%m-%d").date().isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    except (TypeError, ValueError):
        return str(raw or "undated")

def _dedupe_sector_scored(scored: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Count a same-source, same-week sleeve view once.

    This guards against correlated inflation such as a Bible cue plus a
    same-week same-author sleeve call, or two proxy rows for the same sleeve.
    """
    best: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    suppressed: list[dict[str, Any]] = []
    for item in scored:
        key = (
            str(item.get("source") or "").lower(),
            str(item.get("direction") or ""),
            str(item.get("sleeve") or ""),
            _item_week(item),
        )
        current = best.get(key)
        if current is None:
            best[key] = item
            continue
        current_weight = abs(float(current.get("weight") or 0.0))
        item_weight = abs(float(item.get("weight") or 0.0))
        if item_weight > current_weight:
            suppressed.append(current)
            best[key] = item
        else:
            suppressed.append(item)
    return list(best.values()), suppressed

def _layer_read(points: float, *, high_min: float, mod_min: float, weights: dict[str, Any]) -> dict[str, Any]:
    magnitude = abs(points)
    read = _read_from_magnitude(magnitude, high_min=high_min, mod_min=mod_min)
    strength = _strength_5(magnitude, high_min=high_min, mod_min=mod_min, weights=weights)
    return {
        "points": round(points, 3),
        "magnitude": round(magnitude, 3),
        "direction": _direction_from_points(points),
        "read": read,
        "strength_5": strength,
    }

def _cap_read_lift(
    *,
    name_read: str,
    name_points: float,
    candidate_read: str,
    mod_min: float,
    settings: dict[str, Any],
) -> tuple[str, bool, str | None]:
    name_idx = _BAND_ORDER.get(str(name_read or "LOW").upper(), 0)
    cand_idx = _BAND_ORDER.get(str(candidate_read or "LOW").upper(), 0)
    if cand_idx <= name_idx:
        return candidate_read, False, None
    max_raise = int(settings.get("sector_lift_max_band_raise", 1))
    max_idx = min(name_idx + max_raise, _BAND_ORDER["HIGH"])
    if settings.get("sector_lift_high_requires_name_moderate", True) and abs(name_points) < mod_min:
        max_idx = min(max_idx, _BAND_ORDER["MODERATE"])
    if cand_idx > max_idx:
        capped = _BAND_BY_ORDER[max_idx]
        return capped, True, f"sector lift capped read from {candidate_read} to {capped}"
    return candidate_read, False, None

def _name_layer(
    ticker: str,
    *,
    total: float,
    read: str,
    strength_5: int,
    direction: str,
    groups: dict[str, float],
    not_checked: list[str],
    high_min: float,
    mod_min: float,
) -> dict[str, Any]:
    moved = any(abs(float(value or 0.0)) > _EPS for value in groups.values())
    status = "active" if moved else "not_checked" if not_checked else "checked_no_signal"
    return {
        "ticker": ticker,
        "status": status,
        "points": total,
        "magnitude": round(abs(total), 3),
        "direction": direction,
        "read": read,
        "strength_5": strength_5,
        "groups": groups,
        "thresholds": {"high": high_min, "moderate": mod_min},
        "not_checked": list(not_checked),
    }

def _sector_layer(
    ticker: str,
    *,
    sector_items: list[dict[str, Any]],
    weights: dict[str, Any],
    rates: dict[str, Any] | None,
    today: str | date | None,
    high_min: float,
    mod_min: float,
) -> dict[str, Any]:
    settings = _layer_settings(weights)
    if _layer_mode(weights) == "off":
        return {"status": "off", "points": 0.0, "why": []}

    if _is_sleeve_proxy(ticker, settings):
        sleeve = _sleeve_for_ticker(ticker, settings) or ticker
        return {
            "status": "not_applicable",
            "points": 0.0,
            "sleeve": sleeve,
            "category": _sleeve_category(settings, sleeve),
            "why": ["ticker is itself a sleeve proxy; sector layer would double-count"],
            "not_checked": [],
        }

    sleeve = _sleeve_for_ticker(ticker, settings)
    if not sleeve:
        return {
            "status": "not_checked",
            "points": 0.0,
            "why": [],
            "not_checked": ["sector_map"],
        }

    if not sector_items:
        return {
            "status": "checked_no_signal",
            "points": 0.0,
            "sleeve": sleeve,
            "category": _sleeve_category(settings, sleeve),
            "why": [],
            "not_checked": [],
        }

    scored_all = [
        score_sector_item(item, weights=weights, rates=rates, today=today)
        for item in sector_items
    ]
    scored, suppressed = _dedupe_sector_scored(scored_all)
    group = _signed_capped_sum(scored, float(weights["group_caps"]["fs"]))
    live = [
        item for item in scored
        if not item.get("track_only") and not item.get("expired") and abs(float(item.get("weight") or 0.0)) > _EPS
    ]
    if live:
        status = "active"
    elif any(item.get("expired") for item in scored):
        status = "stale"
    else:
        status = "checked_no_signal"
    read = _layer_read(
        float(group["points"]),
        high_min=high_min,
        mod_min=mod_min,
        weights=weights,
    )
    return {
        **read,
        "status": status,
        "sleeve": sleeve,
        "category": _sleeve_category(settings, sleeve),
        "items": scored,
        "deduped_count": len(suppressed),
        "why": [
            f"{item.get('source')} {item.get('tier')} {item.get('sector_subject') or item.get('sleeve')}: {item.get('note')}"
            for item in live[:3]
        ],
        "not_checked": [],
    }

def _overall_layer(
    *,
    name: dict[str, Any],
    sector: dict[str, Any],
    weights: dict[str, Any],
    high_min: float,
    mod_min: float,
) -> dict[str, Any]:
    settings = _layer_settings(weights)
    sector_points = float(sector.get("points") or 0.0) if sector.get("status") == "active" else 0.0
    raw_lift = sector_points * float(settings.get("sector_weight", 0.0))
    cap = float(settings.get("sector_lift_cap", 0.0))
    lift = max(-cap, min(cap, raw_lift))
    clamped_reasons: list[str] = []
    name_points = float(name.get("points") or 0.0)
    if name_points < -_EPS and lift > 0:
        lift = 0.0
        clamped_reasons.append("positive sector lift blocked because name-specific evidence is negative")
    overall_points = round(name_points + lift, 3)
    read_data = _layer_read(overall_points, high_min=high_min, mod_min=mod_min, weights=weights)
    capped_read, band_capped, band_reason = _cap_read_lift(
        name_read=str(name.get("read") or "LOW"),
        name_points=name_points,
        candidate_read=read_data["read"],
        mod_min=mod_min,
        settings=settings,
    )
    if band_reason:
        clamped_reasons.append(band_reason)
    if band_capped:
        read_data["read"] = capped_read
        if capped_read == "MODERATE":
            read_data["strength_5"] = min(int(read_data["strength_5"]), 4)
        elif capped_read == "LOW":
            read_data["strength_5"] = min(int(read_data["strength_5"]), 3)

    conflict = None
    if sector.get("status") == "active":
        sector_dir = str(sector.get("direction") or "NEUTRAL")
        name_dir = str(name.get("direction") or "NEUTRAL")
        if sector_dir != "NEUTRAL" and name_dir != "NEUTRAL" and sector_dir != name_dir:
            conflict = f"sector {sector_dir.lower()} vs name {name_dir.lower()}"
        elif clamped_reasons:
            conflict = clamped_reasons[0]

    sector_only_recheck = None
    if (
        abs(name_points) <= _EPS
        and sector.get("status") == "active"
        and str(sector.get("direction")) == "BUY"
        and not bool(settings.get("sector_only_capital_action_allowed", False))
    ):
        sector_only_recheck = {
            "eligible": True,
            "alert_enabled": bool(settings.get("sector_only_alert_enabled", False)),
            "next_step": "re-check the name; sector support alone is not a buy signal",
        }

    return {
        **read_data,
        "points_decimal": overall_points,
        "sector_lift": round(lift, 3),
        "sector_lift_raw": round(raw_lift, 3),
        "sector_lift_cap": cap,
        "sector_weight": float(settings.get("sector_weight", 0.0)),
        "band_capped": band_capped,
        "clamped_reasons": clamped_reasons,
        "conflict": conflict,
        "capital_action_allowed": not bool(sector_only_recheck),
        "sector_only_recheck": sector_only_recheck,
        "formula_version": str(settings.get("formula_version") or "shadow_v1"),
    }

def conviction_layers(
    ticker: str,
    *,
    total: float,
    read: str,
    strength_5: int,
    direction: str,
    groups: dict[str, float],
    not_checked: list[str],
    sector_items: list[dict[str, Any]] | None,
    weights: dict[str, Any],
    goal: dict[str, Any],
    rates: dict[str, Any] | None = None,
    today: str | date | None = None,
    conflicted: bool = False,
    signed_total: float | None = None,
) -> dict[str, Any]:
    high_min = float(goal["signals_high_min"])
    mod_min = float(goal["signals_mod_min"])
    name_total = total
    name_read = read
    name_direction = direction
    if conflicted:
        name_total = signed_total if signed_total is not None else total
        name_read = CONFLICTED
        name_direction = RECHECK
    name = _name_layer(
        ticker,
        total=name_total,            # signed under conflict → sign guards work
        read=name_read,              # CONFLICTED
        strength_5=strength_5,
        direction=name_direction,    # RE-CHECK
        groups=groups,
        not_checked=not_checked,
        high_min=high_min,
        mod_min=mod_min,
    )
    sector = _sector_layer(
        ticker,
        sector_items=sector_items or [],
        weights=weights,
        rates=rates,
        today=today,
        high_min=high_min,
        mod_min=mod_min,
    )
    overall = _overall_layer(
        name=name,
        sector=sector,
        weights=weights,
        high_min=high_min,
        mod_min=mod_min,
    )
    if conflicted:
        overall = {
            **overall,
            "read": CONFLICTED,
            "direction": RECHECK,
            "conflict": overall.get("conflict") or "name-level bull/bear opposition; resolve before sizing",
        }
    return {
        "mode": _layer_mode(weights),
        "legacy": {
            "points": total,
            "read": read,
            "strength_5": strength_5,
            "direction": direction,
        },
        "name": name,
        "sector": sector,
        "overall": overall,
    }

def _live_fs_item_directions(fs: dict[str, Any]) -> set[str]:
    directions: set[str] = set()
    for item in fs.get("items", []):
        if item.get("track_only") or item.get("expired"):
            continue
        if abs(float(item.get("weight") or 0.0)) <= _EPS:
            continue
        direction = item.get("direction")
        if direction in ("bullish", "bearish"):
            directions.add(direction)
    return directions

def _conflicted(
    *,
    direction: str,
    fs: dict[str, Any],
    groups: dict[str, float],
    force_recheck: bool,
) -> bool:
    if force_recheck:
        return True
    live_fs = _live_fs_item_directions(fs)
    has_positive = any(float(value) > _EPS for value in groups.values()) or "bullish" in live_fs
    has_negative = any(float(value) < -_EPS for value in groups.values()) or "bearish" in live_fs
    if direction == "BUY":
        return has_negative
    if direction == "SELL":
        return has_positive
    return has_positive and has_negative

def conviction_label(action_direction: str, conviction: dict[str, Any]) -> dict[str, Any]:
    action = str(action_direction or "").upper().strip()
    if action in ("ADD", "BUY_ADD", "BUY/ADD"):
        action = "BUY"
    elif action in ("REDUCE", "EXIT", "SELL_FAST", "AVOID"):
        action = "SELL" if action != "REDUCE" else "TRIM"
    verb = {"BUY": "Buy", "TRIM": "Trim", "SELL": "Sell"}.get(action, action.title() or "Act")
    evidence_direction = str(conviction.get("direction") or "NEUTRAL").upper()
    strength = int(conviction.get("strength_5") or 1)
    band = str(conviction.get("read") or "LOW").upper()
    ticker = str(conviction.get("ticker") or "").upper()

    if band == "CONFLICTED" or conviction.get("conflicted"):
        cd = conviction.get("conflict_detail") or {}
        bull = float(cd.get("bull_points") or 0.0)
        bear = float(cd.get("bear_points") or 0.0)
        settle = ", ".join(cd.get("deciding_groups") or []) or "the opposed lanes"
        if bull > 0 and bear > 0:
            note = (f"conflicted: bull and bear evidence both live "
                    f"(+{bull} vs -{bear}); resolve {settle} before sizing")
        else:
            note = (f"conflicted: a contradicting signal forces a re-check "
                    f"(resolve {settle} before sizing)")
        return {
            "text": f"Conviction on {ticker}: CONFLICTED — resolve before acting",
            "x5": int(conviction.get("strength_5") or CONFLICT_STRENGTH_5),
            "band": "CONFLICTED",
            "aligned": False,
            "conflict_note": note,
        }

    aligned = (
        (action == "BUY" and evidence_direction == "BUY")
        or (action in ("TRIM", "SELL") and evidence_direction == "SELL")
    )
    conflict_note = ""
    if evidence_direction == "NEUTRAL":
        x5 = 1
        aligned = False
        conflict_note = "no directional evidence"
    elif aligned:
        x5 = strength
        if conviction.get("conflicted"):
            conflict_note = "mixed evidence present; re-check opposing factors"
    else:
        x5 = 1
        opposing = "HOLD/BUY" if evidence_direction == "BUY" else "TRIM/SELL"
        conflict_note = f"evidence favors {opposing} at {strength}/5"
        if conviction.get("conflicted"):
            conflict_note += "; mixed evidence present"

    return {
        "text": f"Conviction to {verb} {ticker}: {x5}/5 ({band})",
        "x5": x5,
        "band": band,
        "aligned": aligned,
        "conflict_note": conflict_note,
    }

# ---------------------------------------------------------------------------
# The unified read
# ---------------------------------------------------------------------------
def conviction(
    ticker: str,
    *,
    fs_items: list[dict[str, Any]] | None = None,
    sector_items: list[dict[str, Any]] | None = None,
    uw_state: dict[str, Any] | None = None,
    insight_payload: dict[str, Any] | None = None,
    inst_state: dict[str, Any] | None = None,
    weights: dict[str, Any],
    goal: dict[str, Any],
    rates: dict[str, Any] | None = None,
    today: str | date | None = None,
    battery: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tick = ticker.upper()
    battery_payload = (
        battery
        if battery is not None
        else be.build_battery_evidence(
            tick,
            battery_source_config=weights.get("battery_sources"),
        )
    )
    be.assert_valid_battery_evidence(battery_payload)
    fs = fs_group(fs_items or [], weights=weights, rates=rates, today=today)
    uw = uw_group(uw_state, weights=weights)
    matches = _insight_match(insight_payload, ticker=tick, today=today) if insight_payload else []
    op = _insight_points(matches, weights)
    inst = institutional_group(inst_state, weights=weights)

    groups = {
        "fs": fs["points"],
        "uw": uw["points"],
        "operator_insight": round(op["points"], 3),
        "institutional": inst["points"],
    }
    signed_total = round(sum(groups.values()), 3)
    n_groups = sum(1 for v in groups.values() if v > 0)

    high_min = float(goal["signals_high_min"])
    mod_min = float(goal["signals_mod_min"])

    sides = _conflict_sides(groups, force_recheck=uw["force_recheck"])
    conflicted = sides["conflicted"]

    if conflicted:
        # First-class CONFLICTED: opposed evidence does NOT cancel into a calm
        # middling number. `total` becomes the OPPOSITION magnitude (the larger
        # of the two sides), so priority/sizing see a LOUD number, never zero.
        # Read is its own band; direction asks plainly (RE-CHECK).
        total = round(
            max(sides["opposition_magnitude"], sides["bull_points"], sides["bear_points"]),
            3,
        )
        magnitude = total
        read = CONFLICTED
        direction = RECHECK
        strength_5 = CONFLICT_STRENGTH_5
    else:
        total = signed_total
        magnitude = abs(total)
        read = _read_from_magnitude(magnitude, high_min=high_min, mod_min=mod_min)
        direction = _direction_from_points(total)
        strength_5 = _strength_5(
            magnitude, high_min=high_min, mod_min=mod_min, weights=weights
        )

    contradictions: list[str] = []
    for s in fs["items"]:
        if s.get("direction") == "bearish" and not s.get("track_only") and not s.get("expired"):
            contradictions.append(f"{s['source']} bearish ({s['tier']}): {s['note']}")
    if uw["force_recheck"]:
        contradictions.append(uw["why"])

    not_checked: list[str] = []
    if inst.get("status") == "not_checked":
        not_checked.append("institutional")
    if uw["points"] == 0 and not uw["interpretation"] and not uw["single_day_flow"]:
        not_checked.append("uw_same_session")

    raises: list[str] = []
    fs_cap = float(weights["group_caps"]["fs"])
    live_tiers = {s["tier"] for s in fs["items"] if not s.get("track_only") and not s.get("expired")}
    if fs["points"] < fs_cap and "A" not in live_tiers:
        raises.append(
            f"A dated entry/stop/target call (Tier A) on {tick}"
            + (" â€” a Tier B exists; A upgrades it" if "B" in live_tiers else "")
        )
    if "uw_same_session" in not_checked:
        raises.append("Same-session UW proof interpreted 'supports' (9:40 ET gate runs it)")
    elif uw["single_day_flow"] and not uw["interpretation"]:
        raises.append("Next-morning OI confirmation of the flow (battery completes â†’ 1.25)")
    if groups["operator_insight"] == 0:
        raises.append(f"No ACTIVE insight maps {tick} â€” state the thesis as one if you believe it")
    if "institutional" in not_checked:
        raises.append("13F/insider lane goes live in the orphan-wiring chunk")

    return {
        "ticker": tick,
        "points": total,
        "signed_points": signed_total,
        "magnitude": magnitude,
        "direction": direction,
        "strength_5": strength_5,
        "read": read,
        "n_groups": n_groups,
        "thresholds": {"high": high_min, "moderate": mod_min},
        "groups": groups,
        "group_detail": {"fs": fs, "uw": uw, "operator_insight": op, "institutional": inst},
        "contradictions": contradictions,
        "force_recheck": uw["force_recheck"],
        "conflicted": conflicted,
        "conflict_detail": {
            "bull_points": sides["bull_points"],
            "bear_points": sides["bear_points"],
            "bull_groups": sides["bull_groups"],
            "bear_groups": sides["bear_groups"],
            "deciding_groups": sides["deciding_groups"],
            "opposition_magnitude": sides["opposition_magnitude"],
            "material_two_sided": sides["material_two_sided"],
        } if conflicted else None,
        "battery": battery_payload,
        "conviction_layers": conviction_layers(
            tick,
            total=total,
            read=read,
            strength_5=strength_5,
            direction=direction,
            groups=groups,
            not_checked=not_checked,
            sector_items=sector_items,
            weights=weights,
            goal=goal,
            rates=rates,
            today=today,
            conflicted=conflicted,           # NEW
            signed_total=signed_total,       # NEW: signed net for the layer math
        ),
        "raises": raises,
        "not_checked": not_checked,
        "computed_at": _today(today).isoformat(),
    }

# ---------------------------------------------------------------------------
# Adapters (defensive I/O over existing V2 caches)
# ---------------------------------------------------------------------------
def load_source_calls(path: Path | str = SOURCE_CALLS_PATH) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        return rows if isinstance(rows, list) else []
    except json.JSONDecodeError:
        return []

def fs_items_from_source_calls(
    ticker: str, calls: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    calls = load_source_calls() if calls is None else calls
    tick = ticker.upper()
    items: list[dict[str, Any]] = []
    for row in calls:
        if str(row.get("ticker") or "").upper() != tick:
            continue
        if str(row.get("source") or "").lower() not in _FS_SOURCES:
            continue
        items.append(
            {
                "group": "fs",
                "source": str(row.get("source")).lower(),
                "tier": row.get("tier"),
                "date": row.get("date"),
                "direction": row.get("direction", "bullish"),
                "note": row.get("verbatim_quote") or row.get("note") or "",
                "kind": "source_call",
                "source_call_id": row.get("id"),
                "source_call_ticker": str(row.get("ticker") or "").upper(),
                "window_end": row.get("window_end"),
                "window_days": row.get("window_days"),
            }
        )
    return items

def fs_sector_items_for_ticker(
    ticker: str,
    calls: list[dict[str, Any]] | None = None,
    *,
    weights: dict[str, Any],
) -> list[dict[str, Any]]:
    settings = _layer_settings(weights)
    if _layer_mode(weights) == "off":
        return []
    tick = ticker.upper()
    if _is_sleeve_proxy(tick, settings):
        return []
    sleeve = _sleeve_for_ticker(tick, settings)
    if not sleeve:
        return []
    broad = {str(value).upper() for value in settings.get("broad_market_subjects") or []}
    subjects = {
        str(value).upper()
        for value in _sleeve_subjects(settings).get(sleeve, [])
        if str(value).upper() not in {tick} | broad
    }
    if not subjects:
        return []
    calls = load_source_calls() if calls is None else calls
    items: list[dict[str, Any]] = []
    for row in calls:
        subject = str(row.get("ticker") or "").upper()
        if subject not in subjects:
            continue
        if str(row.get("source") or "").lower() not in _FS_SOURCES:
            continue
        item = {
            "group": "fs",
            "source": str(row.get("source")).lower(),
            "tier": row.get("tier"),
            "date": row.get("date"),
            "direction": row.get("direction", "bullish"),
            "note": row.get("verbatim_quote") or row.get("note") or "",
            "kind": "sector_source_call",
            "source_call_id": row.get("id"),
            "source_call_ticker": subject,
            "sector_subject": subject,
            "sleeve": sleeve,
            "category": _sleeve_category(settings, sleeve),
            "window_end": row.get("window_end"),
            "window_days": row.get("window_days"),
            "sector_window_days": _sector_shelf_life_days(
                {"kind": "sector_source_call", **row},
                settings,
            ),
        }
        items.append(item)
    return items

def fs_membership_item(
    ticker: str, prospects: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """Monthly-list membership = Tier-C thesis context (never an execution trigger)."""
    if prospects is None:
        path = TOP_PROSPECTS_PATH
        if not path.exists():
            return None
        try:
            prospects = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    row = (prospects or {}).get(ticker.upper())
    if not isinstance(row, dict):
        return None
    direction = str(row.get("direction") or "long").lower()
    return {
        "group": "fs",
        "source": "fundstrat",
        "tier": "C",
        "date": row.get("add_date"),
        "direction": "bearish" if direction in ("short", "sell", "sell_fast", "avoid") else "bullish",
        "note": f"monthly list membership ({row.get('conviction', 'listed')})",
        "kind": "monthly_membership",
    }

def uw_state_from_feed(ticker: str, feed: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pull same-session interpretation for a ticker from the feed's UW proof
    section if present; honest empty state otherwise."""
    if feed is None:
        try:
            feed = json.loads(FEED_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    proof = feed.get("uw_endpoint_result_proof") or {}
    rows = proof.get("rows") if isinstance(proof, dict) else proof
    tick = ticker.upper()
    best: dict[str, Any] = {}
    for row in rows or []:
        if str(row.get("ticker") or "").upper() != tick:
            continue
        interp = row.get("decision_interpretation") or row.get("interpretation")
        if interp in ("supports", "contradicts", "inconclusive"):
            best = {
                "interpretation": interp,
                "note": row.get("note") or row.get("check") or "",
                "date": row.get("date") or row.get("captured_at"),
                "battery_complete": bool(row.get("battery_complete")),
            }
            if interp == "contradicts":
                break
    return best
