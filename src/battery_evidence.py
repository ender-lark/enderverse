"""Normalized entry-quality battery evidence contract.

This module is deliberately pure: callers inject already-fetched UW price,
IV, and deepdive battery payloads. Missing producer lanes remain visible as
neutral zero-strength factors; absence is never treated as a checked-clear
signal.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from analyst_config import UW_OPP_STRENGTH_TRUST


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


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _pct(value: Any) -> str:
    parsed = _f(value)
    if parsed is None:
        return "n/a"
    return f"{parsed * 100:+.1f}%"


def _source_with_as_of(source: str, as_of: Any) -> str:
    stamp = _safe_text(as_of) or "unknown"
    return f"{source}:{stamp}"


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


def _signal_type_key(value: Any) -> str:
    text = _safe_text(value).lower().replace("-", "_").replace(" ", "_")
    return text or "unknown"


def _opportunity_detail_text(detail: Any) -> str:
    if not isinstance(detail, dict):
        return ""
    bits: list[str] = []
    if "premium" in detail:
        bits.append(f"premium {_money(detail.get('premium'))}")
    if "notional" in detail:
        bits.append(f"notional {_money(detail.get('notional'))}")
    if "call_put_ratio" in detail:
        ratio = _f(detail.get("call_put_ratio"))
        if ratio is not None:
            bits.append(f"c/p {ratio:.2f}")
    if "side" in detail:
        side = _safe_text(detail.get("side"))
        if side:
            bits.append(f"side {side}")
    if "oi_change_pct" in detail:
        pct = _f(detail.get("oi_change_pct"))
        if pct is not None:
            bits.append(f"OI {pct:+.0f}%")
    if "sessions" in detail:
        sessions = _f(detail.get("sessions"))
        if sessions is not None:
            bits.append(f"{sessions:.0f} session(s)")
    strikes = detail.get("strikes")
    if isinstance(strikes, list) and strikes:
        bits.append("strikes " + "/".join(str(x) for x in strikes[:4]))
    return "; ".join(bits)


def _uw_opportunity_payload(uw_opportunity: Any) -> dict[str, Any]:
    if uw_opportunity is None:
        return {}
    if isinstance(uw_opportunity, list):
        return {"status": "checked", "signals": uw_opportunity}
    if isinstance(uw_opportunity, dict):
        return uw_opportunity
    return {"status": "not_checked", "signals": []}


def _uw_opportunity_unavailable_factor(
    *, ticker: str, reason: str = "uw_opportunity source unavailable"
) -> dict[str, Any]:
    value = reason if "not_checked" in reason else f"not_checked: {reason}"
    return _factor(
        key="uw_opportunity_not_checked",
        label="UW opportunity signals",
        direction="neutral",
        strength=0.0,
        value_str=value,
        source="uw_opportunity_signals:unavailable",
        decisive=False,
    )


def _uw_opportunity_none_factor(*, ticker: str, as_of: Any) -> dict[str, Any]:
    tick = str(ticker or "").upper() or "UNKNOWN"
    stamp = _safe_text(as_of) or "unknown"
    return _factor(
        key="uw_opportunity_none",
        label="UW opportunity signals",
        direction="neutral",
        strength=0.0,
        value_str=f"UW opportunity sweep as_of {stamp}: no signal for {tick}",
        source=_source_with_as_of("uw_opportunity_signals", stamp),
        decisive=False,
    )


def uw_opportunity_factors(
    signals_for_ticker: Any,
    *,
    ticker: str = "",
    as_of: Any = None,
    status: str = "checked",
    unavailable_reason: str = "uw_opportunity source unavailable",
) -> list[dict[str, Any]]:
    """Map real uw_opportunity_signals rows into battery factor rows."""
    payload = _uw_opportunity_payload(signals_for_ticker)
    if payload:
        status = str(payload.get("status") or status)
        as_of = payload.get("as_of") or payload.get("generated_at") or as_of
        ticker = str(payload.get("ticker") or ticker)
        unavailable_reason = str(payload.get("reason") or unavailable_reason)
        rows = payload.get("signals")
    else:
        rows = signals_for_ticker

    if status != "checked":
        return [
            _uw_opportunity_unavailable_factor(
                ticker=str(ticker or ""), reason=unavailable_reason
            )
        ]
    if not isinstance(rows, list):
        return [
            _uw_opportunity_unavailable_factor(
                ticker=str(ticker or ""),
                reason="uw_opportunity source unavailable",
            )
        ]
    if not rows:
        return [_uw_opportunity_none_factor(ticker=str(ticker or ""), as_of=as_of)]

    factors: list[dict[str, Any]] = []
    stamp = _safe_text(as_of) or "unknown"
    for row in rows:
        if not isinstance(row, dict):
            continue
        signal_type = _signal_type_key(row.get("signal_type"))
        strength_label = _safe_text(row.get("strength")).lower()
        strength = UW_OPP_STRENGTH_TRUST.get(strength_label)
        direction = str(row.get("direction") or "").lower()
        if strength is None:
            mapped_direction = "neutral"
            mapped_strength = 0.0
        else:
            mapped_direction = (
                "bull" if direction == "bullish"
                else "bear" if direction == "bearish"
                else "neutral"
            )
            mapped_strength = strength if mapped_direction != "neutral" else 0.0
        evidence = _safe_text(row.get("evidence")) or f"{direction or 'unknown'} {signal_type}"
        detail_text = _opportunity_detail_text(row.get("detail"))
        value = evidence
        if detail_text:
            value = f"{value}; {detail_text}"
        value = f"{value} (as_of {stamp})"
        factors.append(
            _factor(
                key=f"uw_opportunity_{signal_type}",
                label=f"UW opportunity {signal_type.replace('_', ' ')}",
                direction=mapped_direction,
                strength=mapped_strength,
                value_str=value,
                source=_source_with_as_of("uw_opportunity_signals", stamp),
                decisive=mapped_strength >= 0.9 and mapped_direction != "neutral",
            )
        )
    if not factors:
        return [_uw_opportunity_none_factor(ticker=str(ticker or ""), as_of=as_of)]
    return factors


def _group_rotation_payload(group_rotation: Any) -> dict[str, Any]:
    if group_rotation is None:
        return {}
    if isinstance(group_rotation, dict):
        return group_rotation
    return {"status": "checked", "rot_w": group_rotation}


def group_rotation_factor(group_rotation: Any = None, cd: Any = None) -> dict[str, Any]:
    """Map holdings group rotation into one honest group-level battery factor."""
    payload = _group_rotation_payload(group_rotation)
    status = str(payload.get("status") or "checked")
    tick = _safe_text(payload.get("ticker"))
    if status != "checked":
        suffix = f" for {tick}" if tick else ""
        return _factor(
            key="group_rotation_not_checked",
            label="Group rotation / momentum",
            direction="neutral",
            strength=0.0,
            value_str=f"not_checked: holdings group rotation unavailable{suffix}",
            source="feed.holdings",
            decisive=False,
        )
    rot_w = _safe_text(payload.get("rot_w") or payload.get("w") or payload.get("rotation"))
    cd = _safe_text(payload.get("cd") if "cd" in payload else cd)
    category = _safe_text(payload.get("category") or payload.get("cat"))
    label = rot_w.upper() if rot_w else "NO DATA"
    if label in {"LEADING", "TURNING UP"}:
        direction = "bull"
        strength = 0.5
    elif label in {"LAGGING", "TURNING DOWN"}:
        direction = "bear"
        strength = 0.5
    else:
        direction = "neutral"
        strength = 0.0
    cat_text = category or "unknown group"
    cd_text = cd or "unknown"
    return _factor(
        key="group_rotation_momentum",
        label="Group rotation / momentum",
        direction=direction,
        strength=strength,
        value_str=(
            f"GROUP-level context: {cat_text} rotation {label}; "
            f"ticker momentum {cd_text}"
        ),
        source="feed.holdings",
        decisive=False,
    )


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


def select_decisive_factors(
    factors: list[dict[str, Any]],
    *,
    cap: int = 4,
) -> list[dict[str, Any]]:
    """Select compact factors for later rendering without changing scoring."""
    valid = [factor for factor in factors if isinstance(factor, dict)]
    if not valid or cap <= 0:
        return []
    bull = sum(f["strength"] for f in valid if f.get("direction") == "bull")
    bear = sum(f["strength"] for f in valid if f.get("direction") == "bear")
    net = "bull" if bull > bear else "bear" if bear > bull else "neutral"

    selected: list[dict[str, Any]] = []

    def add(row: dict[str, Any]) -> None:
        if row not in selected and len(selected) < cap:
            selected.append(row)

    if bull > 0 and bear > 0:
        bull_top = max(
            (f for f in valid if f.get("direction") == "bull"),
            key=lambda f: (bool(f.get("decisive")), f.get("strength", 0.0)),
        )
        bear_top = max(
            (f for f in valid if f.get("direction") == "bear"),
            key=lambda f: (bool(f.get("decisive")), f.get("strength", 0.0)),
        )
        add(bull_top)
        add(bear_top)

    def priority(row: dict[str, Any]) -> tuple[int, int, float]:
        direction = row.get("direction")
        opposes = int(net != "neutral" and direction in {"bull", "bear"} and direction != net)
        return (
            int(bool(row.get("decisive"))),
            opposes,
            float(row.get("strength") or 0.0),
        )

    for row in sorted(valid, key=priority, reverse=True):
        add(row)
    return selected


def _battery_summary(
    factors: list[dict[str, Any]],
    *,
    verdict_line: str,
    iv_hint: dict[str, Any],
) -> dict[str, Any]:
    return {
        "decisive_factors": select_decisive_factors(factors, cap=4),
        "verdict_line": verdict_line,
        "iv_hint": iv_hint,
    }


BATTERY_SOURCE_KEYS = (
    "deepdive_battery",
    "price_rotation",
    "uw_opportunity",
    "group_rotation",
)

BATTERY_SOURCES = [
    {
        "key": "deepdive_battery",
        "mapper": _deepdive_factors,
        "input": "deepdive_battery",
        "call": "input_only",
        "returns": "list",
        "skip_when_none": False,
    },
    {
        "key": "price_rotation",
        "mapper": _price_factors,
        "input": "uw_price",
        "call": "ticker_input",
        "returns": "list",
        "skip_when_none": False,
    },
    {
        "key": "uw_opportunity",
        "mapper": uw_opportunity_factors,
        "input": "uw_opportunity",
        "call": "input_with_ticker_kw",
        "returns": "list",
        "skip_when_none": True,
    },
    {
        "key": "group_rotation",
        "mapper": group_rotation_factor,
        "input": "group_rotation",
        "call": "input_only",
        "returns": "single",
        "skip_when_none": True,
    },
]


def _source_settings(
    source_key: str,
    battery_source_config: dict[str, Any] | None,
) -> tuple[bool, float]:
    if battery_source_config is None:
        return True, 1.0
    if not isinstance(battery_source_config, dict):
        raise ValueError("battery_source_config must be a map when supplied")
    unknown = sorted(set(battery_source_config) - set(BATTERY_SOURCE_KEYS))
    if unknown:
        raise ValueError(f"battery_source_config unknown source key(s): {unknown}")
    row = battery_source_config.get(source_key)
    if row is None:
        return True, 1.0
    if not isinstance(row, dict):
        raise ValueError(f"battery_source_config[{source_key}] must be an object")
    enabled = row.get("enabled")
    weight = row.get("weight")
    if not isinstance(enabled, bool):
        raise ValueError(f"battery_source_config[{source_key}].enabled must be true/false")
    if isinstance(weight, bool) or not isinstance(weight, (int, float)):
        raise ValueError(f"battery_source_config[{source_key}].weight must be numeric")
    return enabled, max(0.0, min(1.0, float(weight)))


def _scale_source_factors(
    factors: list[dict[str, Any]],
    *,
    weight: float,
) -> list[dict[str, Any]]:
    if weight == 1.0:
        return factors
    scaled: list[dict[str, Any]] = []
    for factor in factors:
        row = dict(factor)
        row["strength"] = _clamp01(float(row.get("strength") or 0.0) * weight)
        scaled.append(row)
    return scaled


def _call_battery_source(
    source: dict[str, Any],
    *,
    tick: str,
    value: Any,
) -> list[dict[str, Any]]:
    mapper = source["mapper"]
    call = source["call"]
    if call == "ticker_input":
        out = mapper(tick, value)
    elif call == "input_with_ticker_kw":
        out = mapper(value, ticker=tick)
    else:
        out = mapper(value)

    if source.get("returns") == "single":
        return [out] if isinstance(out, dict) else []
    if isinstance(out, list):
        return [row for row in out if isinstance(row, dict)]
    if isinstance(out, dict):
        return [out]
    return []


def build_battery_evidence(
    ticker: str,
    *,
    uw_price: Any = None,
    iv_ctx: Any = None,
    deepdive_battery: Any = None,
    uw_opportunity: Any = None,
    group_rotation: Any = None,
    battery_source_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Map injected producer outputs into the battery evidence contract."""
    tick = str(ticker or "").upper()
    inputs = {
        "deepdive_battery": deepdive_battery,
        "uw_price": uw_price,
        "uw_opportunity": uw_opportunity,
        "group_rotation": group_rotation,
    }
    factors: list[dict[str, Any]] = []
    for source in BATTERY_SOURCES:
        value = inputs.get(str(source["input"]))
        if source.get("skip_when_none") and value is None:
            continue
        enabled, weight = _source_settings(str(source["key"]), battery_source_config)
        if not enabled:
            continue
        source_factors = _call_battery_source(source, tick=tick, value=value)
        factors.extend(_scale_source_factors(source_factors, weight=weight))
    iv_hint = _iv_hint(iv_ctx)
    verdict_line = _verdict_line(factors)
    payload = {
        "factors": factors,
        "iv_hint": iv_hint,
        "verdict_line": verdict_line,
        "battery_summary": _battery_summary(
            factors,
            verdict_line=verdict_line,
            iv_hint=iv_hint,
        ),
    }
    return assert_valid_battery_evidence(payload)
