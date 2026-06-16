"""Normalized entry-quality battery evidence contract.

This module is deliberately pure: callers inject already-fetched UW price,
IV, and deepdive battery payloads. Missing producer lanes remain visible as
neutral zero-strength factors; absence is never treated as a checked-clear
signal.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any


VALID_DIRECTIONS = {"bull", "bear", "neutral"}
VALID_INSTRUMENTS = {"shares", "options", "either"}
FACTOR_KEYS = {
    "key",
    "label",
    "direction",
    "strength",
    "value_str",
    "source",
    "decisive",
}
IV_HINT_KEYS = {"instrument", "why", "iv_rank"}
CONTAINER_KEYS = {"factors", "iv_hint", "verdict_line"}


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if is_dataclass(value):
        return asdict(value)
    data: dict[str, Any] = {}
    for key in (
        "ticker",
        "classification",
        "composite_class",
        "recommended_structure",
        "iv_rank",
        "ivr",
        "reasoning",
    ):
        if hasattr(value, key):
            data[key] = getattr(value, key)
    return data


def _f(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("$", "").replace(",", "").replace("%", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _clamp01(value: Any) -> float:
    parsed = _f(value)
    if parsed is None:
        return 0.0
    return round(max(0.0, min(1.0, parsed)), 3)


def _money(value: Any) -> str:
    parsed = _f(value)
    if parsed is None:
        return "unknown"
    sign = "-" if parsed < 0 else ""
    value = abs(parsed)
    if value >= 1_000_000_000:
        return f"{sign}${value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"{sign}${value / 1_000_000:.1f}M"
    return f"{sign}${value:,.0f}"


def _pct(value: Any) -> str:
    parsed = _f(value)
    if parsed is None:
        return "n/a"
    return f"{parsed * 100:+.1f}%"


def _factor(
    *,
    key: str,
    label: str,
    direction: str,
    strength: Any,
    value_str: str,
    source: str,
    decisive: bool,
) -> dict[str, Any]:
    direction = direction if direction in VALID_DIRECTIONS else "neutral"
    factor = {
        "key": str(key),
        "label": str(label),
        "direction": direction,
        "strength": _clamp01(strength),
        "value_str": str(value_str),
        "source": str(source),
        "decisive": bool(decisive),
    }
    problems = validate_factor(factor)
    if problems:
        raise ValueError("; ".join(problems))
    return factor


def validate_factor(row: Any, *, path: str = "factor") -> list[str]:
    problems: list[str] = []
    if not isinstance(row, dict):
        return [f"{path}: must be an object"]
    missing = sorted(FACTOR_KEYS - set(row))
    if missing:
        problems.append(f"{path}: missing key(s) {missing}")
    direction = row.get("direction")
    if direction not in VALID_DIRECTIONS:
        problems.append(
            f"{path}.direction: must be one of {sorted(VALID_DIRECTIONS)}"
        )
    strength = row.get("strength")
    if isinstance(strength, bool) or not isinstance(strength, (int, float)):
        problems.append(f"{path}.strength: must be a number in [0, 1]")
    elif strength < 0 or strength > 1:
        problems.append(f"{path}.strength: must be in [0, 1]")
    if not isinstance(row.get("decisive"), bool):
        problems.append(f"{path}.decisive: must be true/false")
    for key in ("key", "label", "value_str", "source"):
        if key in row and not isinstance(row.get(key), str):
            problems.append(f"{path}.{key}: must be a string")
    return problems


def validate_battery_evidence(payload: Any) -> list[str]:
    problems: list[str] = []
    if not isinstance(payload, dict):
        return ["battery_evidence: must be an object"]
    missing = sorted(CONTAINER_KEYS - set(payload))
    if missing:
        problems.append(f"battery_evidence: missing key(s) {missing}")
    factors = payload.get("factors")
    if not isinstance(factors, list):
        problems.append("battery_evidence.factors: must be a list")
    else:
        for idx, factor in enumerate(factors):
            problems.extend(validate_factor(factor, path=f"factors[{idx}]"))

    hint = payload.get("iv_hint")
    if not isinstance(hint, dict):
        problems.append("battery_evidence.iv_hint: must be an object")
    else:
        missing_hint = sorted(IV_HINT_KEYS - set(hint))
        if missing_hint:
            problems.append(f"battery_evidence.iv_hint: missing key(s) {missing_hint}")
        if hint.get("instrument") not in VALID_INSTRUMENTS:
            problems.append(
                "battery_evidence.iv_hint.instrument: must be one of "
                f"{sorted(VALID_INSTRUMENTS)}"
            )
        if not isinstance(hint.get("why"), str):
            problems.append("battery_evidence.iv_hint.why: must be a string")
        iv_rank = hint.get("iv_rank")
        if iv_rank is not None and (
            isinstance(iv_rank, bool) or not isinstance(iv_rank, (int, float))
        ):
            problems.append("battery_evidence.iv_hint.iv_rank: must be number/null")

    if not isinstance(payload.get("verdict_line"), str):
        problems.append("battery_evidence.verdict_line: must be a string")
    return problems


def assert_valid_battery_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    problems = validate_battery_evidence(payload)
    if problems:
        raise ValueError("; ".join(problems))
    return payload


def _lane_source(lane: dict[str, Any], fallback_endpoint: str) -> str:
    endpoint = str(lane.get("endpoint") or fallback_endpoint)
    return f"deepdive_runner:{endpoint}"


def _not_checked_factor(
    lane: dict[str, Any], *, key: str, label: str, endpoint: str
) -> dict[str, Any]:
    status = str(lane.get("status") or "not_checked")
    summary = str(lane.get("summary") or lane.get("reason") or "not checked")
    return _factor(
        key=key,
        label=label,
        direction="neutral",
        strength=0.0,
        value_str=f"{status}: {summary}",
        source=_lane_source(lane, endpoint),
        decisive=False,
    )


def _multi_day_oi_factor(lane: dict[str, Any]) -> dict[str, Any]:
    if lane.get("status") != "fetched":
        return _not_checked_factor(
            lane,
            key="multi_day_oi_build",
            label="Multi-day OI build",
            endpoint="get_open_interest_changes",
        )
    days = int(_f(lane.get("days_of_oi_increases")) or 0)
    side = str(lane.get("dominant_side") or "unknown").lower()
    direction = "bull" if side == "call" else "bear" if side == "put" else "neutral"
    strength = min(1.0, days / 5.0) if days > 0 else 0.0
    summary = str(lane.get("summary") or f"{days} OI increase day(s), side {side}")
    return _factor(
        key="multi_day_oi_build",
        label="Multi-day OI build",
        direction=direction,
        strength=strength,
        value_str=summary,
        source=_lane_source(lane, "get_open_interest_changes"),
        decisive=bool(lane.get("flagged")) and direction != "neutral",
    )


def _dark_pool_factor(lane: dict[str, Any]) -> dict[str, Any]:
    if lane.get("status") != "fetched":
        return _not_checked_factor(
            lane,
            key="dark_pool_blocks",
            label="Dark-pool blocks",
            endpoint="get_dark_pool_trades",
        )
    net = _f(lane.get("net_signed_notional")) or 0.0
    direction = "bull" if net > 0 else "bear" if net < 0 else "neutral"
    strength = min(1.0, abs(net) / 25_000_000.0) if net else 0.0
    summary = str(lane.get("summary") or "")
    if not summary:
        blocks = int(_f(lane.get("qualifying_blocks")) or 0)
        summary = f"{blocks} block(s), net {_money(net)}"
    return _factor(
        key="dark_pool_blocks",
        label="Dark-pool blocks",
        direction=direction,
        strength=strength,
        value_str=summary,
        source=_lane_source(lane, "get_dark_pool_trades"),
        decisive=bool(lane.get("flagged")) and direction != "neutral",
    )


def _deepdive_factors(deepdive_battery: Any) -> list[dict[str, Any]]:
    payload = _as_dict(deepdive_battery)
    lanes = payload.get("lanes") if isinstance(payload, dict) else None
    if not isinstance(lanes, list):
        return []
    factors: list[dict[str, Any]] = []
    for lane in lanes:
        if not isinstance(lane, dict):
            continue
        name = str(lane.get("name") or "")
        if name == "multi_day_oi_build":
            factors.append(_multi_day_oi_factor(lane))
        elif name == "dark_pool_blocks":
            factors.append(_dark_pool_factor(lane))
    return factors


def _price_rows(uw_price: Any) -> list[dict[str, Any]]:
    if uw_price is None:
        return []
    if isinstance(uw_price, list):
        return [row for row in uw_price if isinstance(row, dict)]
    if isinstance(uw_price, dict):
        for key in ("rows", "data", "items", "prices"):
            value = uw_price.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        if any(key in uw_price for key in ("proxy", "ticker", "subject", "label")):
            return [uw_price]
    return []


def _price_factors(ticker: str, uw_price: Any) -> list[dict[str, Any]]:
    rows = []
    for row in _price_rows(uw_price):
        row_ticker = str(
            row.get("ticker") or row.get("proxy") or row.get("subject") or ""
        ).upper()
        if row_ticker == ticker:
            rows.append(row)
    factors: list[dict[str, Any]] = []
    for row in rows:
        label = str(row.get("label") or "NO DATA").upper()
        if label in {"LEADING", "TURNING UP"}:
            direction = "bull"
        elif label in {"LAGGING", "TURNING DOWN"}:
            direction = "bear"
        else:
            direction = "neutral"
        rel_3m = _f(row.get("rel_3m"))
        rel_1m = _f(row.get("rel_1m"))
        move = max(abs(rel_3m or 0.0), abs(rel_1m or 0.0))
        strength = min(1.0, move / 0.15) if direction != "neutral" else 0.0
        factors.append(
            _factor(
                key="price_rotation",
                label="Price rotation",
                direction=direction,
                strength=strength,
                value_str=(
                    f"{label}; rel_3m {_pct(rel_3m)}; rel_1m {_pct(rel_1m)}"
                ),
                source="uw_price",
                decisive=direction != "neutral" and strength >= 0.4,
            )
        )
    return factors


def _iv_hint(iv_ctx: Any) -> dict[str, Any]:
    data = _as_dict(iv_ctx)
    if not data:
        return {
            "instrument": "either",
            "why": "IV context not_checked; no options-vs-shares edge inferred.",
            "iv_rank": None,
        }
    classification = str(
        data.get("classification") or data.get("composite_class") or "unknown"
    ).lower()
    structure = str(data.get("recommended_structure") or "").upper()
    iv_rank = _f(data.get("iv_rank") if "iv_rank" in data else data.get("ivr"))
    if classification == "cheap":
        instrument = "options"
        why = "IV is cheap; options can carry convexity more efficiently"
    elif classification == "expensive":
        instrument = "shares"
        why = "IV is expensive; prefer shares unless a defined-risk spread is required"
    else:
        instrument = "either"
        why = "IV is normal or unknown; no instrument edge from IV alone"
    if structure:
        why = f"{why} (producer structure: {structure})"
    return {"instrument": instrument, "why": why, "iv_rank": iv_rank}


def _verdict_line(factors: list[dict[str, Any]]) -> str:
    if not factors:
        return "Battery evidence not checked; no producer payload was supplied."
    if all(
        factor["direction"] == "neutral" and factor["strength"] == 0
        for factor in factors
    ):
        return "Battery evidence not_checked or neutral; no lane can be treated as clear."

    bull = sum(f["strength"] for f in factors if f["direction"] == "bull")
    bear = sum(f["strength"] for f in factors if f["direction"] == "bear")
    if bull > 0 and bear > 0:
        return f"Battery evidence mixed: bull {bull:.2f} vs bear {bear:.2f}."
    if bull > bear:
        top = max(
            (f for f in factors if f["direction"] == "bull"),
            key=lambda f: f["strength"],
        )
        return f"Battery evidence leans bull: {top['label']} {top['value_str']}."
    if bear > bull:
        top = max(
            (f for f in factors if f["direction"] == "bear"),
            key=lambda f: f["strength"],
        )
        return f"Battery evidence leans bear: {top['label']} {top['value_str']}."
    return "Battery evidence neutral; checked factors do not lean bull or bear."


def build_battery_evidence(
    ticker: str,
    *,
    uw_price: Any = None,
    iv_ctx: Any = None,
    deepdive_battery: Any = None,
) -> dict[str, Any]:
    """Map injected producer outputs into the battery evidence contract."""
    tick = str(ticker or "").upper()
    factors: list[dict[str, Any]] = []
    factors.extend(_deepdive_factors(deepdive_battery))
    factors.extend(_price_factors(tick, uw_price))
    payload = {
        "factors": factors,
        "iv_hint": _iv_hint(iv_ctx),
        "verdict_line": _verdict_line(factors),
    }
    return assert_valid_battery_evidence(payload)
