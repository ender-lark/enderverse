#!/usr/bin/env python3
"""Daily audit for owned option premium decay risk.

This is a position-risk monitor, not an options idea generator. It reads the
promoted broker book, enriches from the local options-chain cache when fresh,
and flags long option positions that can quietly lose value through theta,
mostly-extrinsic premium, near expiry, or missing chain/underlying data.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pushover_notify


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POSITIONS = ROOT / "src" / "account_positions.json"
DEFAULT_CHAIN_CACHE = ROOT / "src" / "options_chain_cache.json"
DEFAULT_OUT = ROOT / "src" / "options_decay_audit.json"
ET = ZoneInfo("America/New_York")

DESCRIPTION_RE = re.compile(
    r"(?P<strike>\d+(?:\.\d+)?)\s+(?P<kind>Call|Put)\s+(?P<expiry>\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)

DEFAULT_MATERIAL_VALUE_USD = 500.0
DEFAULT_MATERIAL_UNPRICED_VALUE_USD = 1000.0
DEFAULT_CRITICAL_DTE = 5
DEFAULT_ACTION_DTE = 14
DEFAULT_WATCH_DTE = 45
DEFAULT_PREMIUM_DECAY_DTE = 120
DEFAULT_CHAIN_MAX_AGE_DAYS = 3
HIGH_EXTRINSIC_PCT = 0.75
WATCH_EXTRINSIC_PCT = 0.50
HIGH_THETA_WEEK_PCT = 0.10
WATCH_THETA_WEEK_PCT = 0.05


@dataclass(frozen=True)
class OptionPosition:
    ticker: str
    description: str
    contracts: float
    market_value: float
    account: str
    owner: str
    broker: str
    tracked: bool
    underlying: str
    expiry: str
    call_put: str
    strike: float
    multiplier: float
    occ_symbol: str


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        value = float(value)
        return None if math.isnan(value) else value
    text = str(value).replace("$", "").replace(",", "").replace("%", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _as_of(value: str | None = None) -> date:
    if value:
        return datetime.fromisoformat(value[:10]).date()
    return datetime.now(ET).date()


def _date_or_none(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _atomic_write_json(path: str | Path, payload: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=False, default=str)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def _read_json(path: str | Path, default: Any) -> Any:
    path = Path(path)
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _account_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        rows = payload.get("account_positions") or payload.get("positions") or []
    else:
        rows = payload if isinstance(payload, list) else []
    return [row for row in rows if isinstance(row, dict)]


def _option_from_description(row: dict[str, Any]) -> dict[str, Any]:
    description = _text(row.get("description"))
    match = DESCRIPTION_RE.search(description)
    if not match:
        return {}
    return {
        "underlying": _text(row.get("ticker")).upper(),
        "expiry": match.group("expiry"),
        "call_put": match.group("kind").lower(),
        "strike": _num(match.group("strike")) or 0.0,
        "multiplier": 100,
        "occ_symbol": "",
    }


def extract_option_positions(payload: Any) -> list[OptionPosition]:
    positions: list[OptionPosition] = []
    for row in _account_rows(payload):
        raw_option = row.get("option") if isinstance(row.get("option"), dict) else {}
        is_option = bool(raw_option) or _text(row.get("asset_type")).lower() == "option"
        if not is_option:
            continue
        option = dict(raw_option or _option_from_description(row))
        expiry = _text(option.get("expiry"))
        call_put = _text(option.get("call_put")).lower()
        strike = _num(option.get("strike"))
        underlying = _text(option.get("underlying") or row.get("ticker")).upper()
        contracts = _num(row.get("shares") or row.get("quantity") or row.get("contracts")) or 0.0
        market_value = _num(row.get("market_value") or row.get("current_value")) or 0.0
        if not (underlying and expiry and call_put and strike is not None):
            continue
        positions.append(
            OptionPosition(
                ticker=_text(row.get("ticker") or underlying).upper(),
                description=_text(row.get("description")),
                contracts=contracts,
                market_value=market_value,
                account=_text(row.get("account")),
                owner=_text(row.get("owner")),
                broker=_text(row.get("broker")),
                tracked=bool(row.get("tracked")),
                underlying=underlying,
                expiry=expiry,
                call_put=call_put,
                strike=float(strike),
                multiplier=float(_num(option.get("multiplier")) or 100.0),
                occ_symbol=_text(option.get("occ_symbol")),
            )
        )
    return positions


def underlying_prices_from_book(payload: Any) -> dict[str, float]:
    prices: dict[str, float] = {}
    for row in _account_rows(payload):
        if row.get("option") or _text(row.get("asset_type")).lower() == "option":
            continue
        ticker = _text(row.get("ticker") or row.get("symbol")).upper()
        shares = _num(row.get("shares") or row.get("quantity"))
        market_value = _num(row.get("market_value") or row.get("current_value"))
        if ticker and shares and market_value and shares > 0 and market_value > 0:
            prices.setdefault(ticker, market_value / shares)
    return prices


def _cache_as_of(cache: Any) -> date | None:
    meta = cache.get("_meta") if isinstance(cache, dict) else {}
    return _date_or_none((meta or {}).get("as_of") or (meta or {}).get("generated_at"))


def chain_cache_status(cache: Any, as_of: date, max_age_days: int) -> dict[str, Any]:
    if not isinstance(cache, dict) or not cache:
        return {"status": "missing", "as_of": "", "age_days": None}
    cache_date = _cache_as_of(cache)
    if not cache_date:
        return {"status": "unknown_date", "as_of": "", "age_days": None}
    age_days = (as_of - cache_date).days
    status = "fresh" if age_days <= max_age_days else "stale"
    return {"status": status, "as_of": cache_date.isoformat(), "age_days": age_days}


def _rows_from_chain(chain: Any) -> list[dict[str, Any]]:
    if isinstance(chain, list):
        return [row for row in chain if isinstance(row, dict)]
    if not isinstance(chain, dict):
        return []
    for key in ("states", "data", "result", "results", "contracts"):
        rows = chain.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _first_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        for row in value:
            if isinstance(row, dict):
                return row
    return {}


def _chain_underlying_price(entry: dict[str, Any]) -> float | None:
    chain = entry.get("chain") if isinstance(entry.get("chain"), dict) else {}
    price_data = chain.get("price_data") if isinstance(chain.get("price_data"), dict) else {}
    for key in ("price", "underlying_price", "close"):
        value = _num(price_data.get(key))
        if value:
            return value
    screener = _first_dict((entry.get("screener") or {}).get("result") if isinstance(entry.get("screener"), dict) else entry.get("screener"))
    for key in ("price", "close", "last", "underlying_price"):
        value = _num(screener.get(key))
        if value:
            return value
    return None


def _contract_type(row: dict[str, Any]) -> str:
    text = _text(row.get("option_type") or row.get("type")).lower()
    if text in {"c", "call", "calls"}:
        return "call"
    if text in {"p", "put", "puts"}:
        return "put"
    symbol = _text(row.get("option_symbol") or row.get("symbol")).upper().replace(" ", "")
    if len(symbol) >= 15:
        if "C" in symbol[-9:]:
            return "call"
        if "P" in symbol[-9:]:
            return "put"
    return text


def _matches_contract(row: dict[str, Any], pos: OptionPosition) -> bool:
    expiry = _text(row.get("expires") or row.get("expiry") or row.get("expiration"))
    strike = _num(row.get("strike"))
    return (
        expiry[:10] == pos.expiry[:10]
        and _contract_type(row) == pos.call_put
        and strike is not None
        and abs(float(strike) - pos.strike) < 0.001
    )


def find_chain_contract(pos: OptionPosition, cache: Any) -> dict[str, Any] | None:
    if not isinstance(cache, dict):
        return None
    entry = cache.get(pos.underlying)
    if not isinstance(entry, dict):
        return None
    rows = _rows_from_chain(entry.get("chain"))
    for row in rows:
        if _matches_contract(row, pos):
            return row
    return None


def _intrinsic_value(pos: OptionPosition, underlying_price: float | None) -> float | None:
    if underlying_price is None:
        return None
    if pos.call_put == "call":
        per_share = max(0.0, underlying_price - pos.strike)
    elif pos.call_put == "put":
        per_share = max(0.0, pos.strike - underlying_price)
    else:
        return None
    return per_share * pos.multiplier * abs(pos.contracts)


def _option_mark_per_share(pos: OptionPosition) -> float | None:
    contracts = abs(pos.contracts)
    value = abs(pos.market_value)
    if contracts <= 0 or pos.multiplier <= 0 or value <= 0:
        return None
    return value / contracts / pos.multiplier


def _break_even(pos: OptionPosition, mark_per_share: float | None) -> float | None:
    if mark_per_share is None:
        return None
    if pos.call_put == "call":
        return pos.strike + mark_per_share
    if pos.call_put == "put":
        return pos.strike - mark_per_share
    return None


def _theta_metrics(pos: OptionPosition, contract: dict[str, Any] | None) -> dict[str, Any]:
    if not contract:
        return {"theta_per_contract_day": None, "theta_week_pct_value": None}
    theta = _num(contract.get("theta"))
    value = abs(pos.market_value)
    if theta is None or value <= 0:
        return {"theta_per_contract_day": None, "theta_week_pct_value": None}
    per_contract = theta * pos.multiplier
    total_week_decay = abs(per_contract * abs(pos.contracts) * 7)
    return {
        "theta_per_contract_day": per_contract,
        "theta_week_pct_value": total_week_decay / value,
    }


def _set_severity(current: str, candidate: str) -> str:
    order = {"ok": 0, "watch": 1, "high": 2, "critical": 3}
    return candidate if order.get(candidate, 0) > order.get(current, 0) else current


def audit_position(
    pos: OptionPosition,
    *,
    as_of: date,
    book_prices: dict[str, float],
    chain_cache: Any,
    chain_is_fresh: bool,
    material_value: float = DEFAULT_MATERIAL_VALUE_USD,
    material_unpriced_value: float = DEFAULT_MATERIAL_UNPRICED_VALUE_USD,
    critical_dte: int = DEFAULT_CRITICAL_DTE,
    action_dte: int = DEFAULT_ACTION_DTE,
    watch_dte: int = DEFAULT_WATCH_DTE,
    premium_decay_dte: int = DEFAULT_PREMIUM_DECAY_DTE,
) -> dict[str, Any]:
    expiry = _date_or_none(pos.expiry)
    dte = (expiry - as_of).days if expiry else None
    contract = find_chain_contract(pos, chain_cache) if chain_is_fresh else None
    chain_entry = chain_cache.get(pos.underlying) if chain_is_fresh and isinstance(chain_cache, dict) else None
    underlying_price = book_prices.get(pos.underlying)
    if underlying_price is None and isinstance(chain_entry, dict):
        underlying_price = _chain_underlying_price(chain_entry)
    current_value = abs(pos.market_value)
    intrinsic = _intrinsic_value(pos, underlying_price)
    extrinsic = max(0.0, current_value - intrinsic) if intrinsic is not None else None
    extrinsic_pct = (extrinsic / current_value) if extrinsic is not None and current_value > 0 else None
    mark = _option_mark_per_share(pos)
    breakeven = _break_even(pos, mark)
    theta = _theta_metrics(pos, contract)
    theta_week_pct = theta.get("theta_week_pct_value")
    reasons: list[str] = []
    gaps: list[str] = []
    severity = "ok"

    if dte is None:
        gaps.append("expiry_not_checked")
        severity = _set_severity(severity, "watch")
    elif dte < 0 and current_value > 0:
        reasons.append("expired_position_still_marked")
        severity = _set_severity(severity, "critical")
    elif dte <= critical_dte and current_value >= material_value:
        reasons.append(f"expires_in_{dte}_days")
        severity = _set_severity(severity, "critical")
    elif dte <= action_dte and current_value >= material_value:
        reasons.append(f"expires_in_{dte}_days")
        severity = _set_severity(severity, "high")
    elif dte <= watch_dte and current_value >= material_value:
        reasons.append(f"expires_in_{dte}_days")
        severity = _set_severity(severity, "watch")

    long_position = pos.contracts > 0
    if not long_position:
        reasons.append("short_or_flat_option_time_decay_not_loss_risk")

    if long_position and current_value >= material_value:
        if theta_week_pct is not None:
            if theta_week_pct >= HIGH_THETA_WEEK_PCT:
                reasons.append("theta_decay_exceeds_10pct_of_value_per_week")
                severity = _set_severity(severity, "high")
            elif theta_week_pct >= WATCH_THETA_WEEK_PCT:
                reasons.append("theta_decay_exceeds_5pct_of_value_per_week")
                severity = _set_severity(severity, "watch")
        if dte is not None and dte <= premium_decay_dte and extrinsic_pct is not None:
            if extrinsic_pct >= HIGH_EXTRINSIC_PCT:
                reasons.append("mostly_extrinsic_premium")
                severity = _set_severity(severity, "high")
            elif extrinsic_pct >= WATCH_EXTRINSIC_PCT:
                reasons.append("large_extrinsic_premium")
                severity = _set_severity(severity, "watch")
        if dte is not None and dte <= premium_decay_dte and current_value >= material_unpriced_value and underlying_price is None:
            gaps.append("underlying_or_fresh_chain_not_checked")
            reasons.append("material_option_premium_unpriced_inside_decay_window")
            severity = _set_severity(severity, "high")
        elif underlying_price is None:
            gaps.append("underlying_or_fresh_chain_not_checked")

    if not contract:
        gaps.append("matching_fresh_chain_contract_not_checked")

    if severity == "ok":
        recommendation = "No immediate decay action; keep in daily audit."
    elif severity == "watch":
        recommendation = "Review on the next portfolio pass; decay risk is visible but not urgent."
    elif severity == "high":
        recommendation = "Review today: close, roll, or explicitly keep the premium at risk."
    else:
        recommendation = "Action required: close, roll, exercise, or verify settlement before time value disappears."

    return {
        "ticker": pos.underlying,
        "contract": {
            "description": pos.description,
            "expiry": pos.expiry,
            "call_put": pos.call_put,
            "strike": pos.strike,
            "occ_symbol": pos.occ_symbol,
        },
        "account": pos.account,
        "owner": pos.owner,
        "broker": pos.broker,
        "tracked": pos.tracked,
        "contracts": pos.contracts,
        "direction": "long" if pos.contracts > 0 else "short_or_flat",
        "market_value": pos.market_value,
        "dte": dte,
        "underlying_price": underlying_price,
        "mark_per_share": mark,
        "intrinsic_value": intrinsic,
        "extrinsic_value": extrinsic,
        "extrinsic_pct_value": extrinsic_pct,
        "break_even_at_expiry": breakeven,
        "theta_per_contract_day": theta.get("theta_per_contract_day"),
        "theta_week_pct_value": theta_week_pct,
        "iv": _num(contract.get("iv") if contract else None),
        "delta": _num(contract.get("delta") if contract else None),
        "volume": _num(contract.get("volume") if contract else None),
        "open_interest": _num(contract.get("open_interest") if contract else None),
        "severity": severity,
        "reasons": sorted(set(reasons)),
        "data_gaps": sorted(set(gaps)),
        "recommendation": recommendation,
    }


def build_audit(
    positions_payload: Any,
    *,
    chain_cache: Any = None,
    as_of: date | None = None,
    chain_max_age_days: int = DEFAULT_CHAIN_MAX_AGE_DAYS,
) -> dict[str, Any]:
    as_of = as_of or _as_of()
    option_positions = extract_option_positions(positions_payload)
    book_prices = underlying_prices_from_book(positions_payload)
    chain_cache = chain_cache if isinstance(chain_cache, dict) else {}
    chain_status = chain_cache_status(chain_cache, as_of, chain_max_age_days)
    chain_is_fresh = chain_status.get("status") == "fresh"
    rows = [
        audit_position(
            pos,
            as_of=as_of,
            book_prices=book_prices,
            chain_cache=chain_cache,
            chain_is_fresh=chain_is_fresh,
        )
        for pos in option_positions
    ]
    rows.sort(
        key=lambda row: (
            {"critical": 0, "high": 1, "watch": 2, "ok": 3}.get(row.get("severity"), 4),
            row.get("dte") if row.get("dte") is not None else 9999,
            -abs(float(row.get("market_value") or 0)),
            row.get("ticker") or "",
        )
    )
    counts = {
        "option_positions": len(rows),
        "critical": sum(1 for row in rows if row.get("severity") == "critical"),
        "high": sum(1 for row in rows if row.get("severity") == "high"),
        "watch": sum(1 for row in rows if row.get("severity") == "watch"),
        "ok": sum(1 for row in rows if row.get("severity") == "ok"),
        "not_checked_rows": sum(1 for row in rows if row.get("data_gaps")),
    }
    alert_rows = [row for row in rows if row.get("severity") in {"critical", "high"}]
    if not rows:
        status = "quiet"
        line = "Options decay audit: quiet - no open option positions in the checked broker book."
    elif alert_rows:
        status = "notify"
        line = (
            "Options decay audit: "
            f"{len(alert_rows)} material option position(s) need same-day review."
        )
    elif counts["watch"]:
        status = "review"
        line = f"Options decay audit: {counts['watch']} option position(s) are on watch."
    else:
        status = "quiet"
        line = f"Options decay audit: quiet - {len(rows)} option position(s) checked."
    return {
        "schema_version": 1,
        "valid": True,
        "checked_at": datetime.now(ET).isoformat(),
        "as_of": as_of.isoformat(),
        "status": status,
        "line": line,
        "counts": counts,
        "chain_cache": chain_status,
        "thresholds": {
            "material_value_usd": DEFAULT_MATERIAL_VALUE_USD,
            "material_unpriced_value_usd": DEFAULT_MATERIAL_UNPRICED_VALUE_USD,
            "critical_dte": DEFAULT_CRITICAL_DTE,
            "action_dte": DEFAULT_ACTION_DTE,
            "watch_dte": DEFAULT_WATCH_DTE,
            "premium_decay_dte": DEFAULT_PREMIUM_DECAY_DTE,
            "high_extrinsic_pct": HIGH_EXTRINSIC_PCT,
            "high_theta_week_pct": HIGH_THETA_WEEK_PCT,
        },
        "alerts": alert_rows,
        "rows": rows,
        "policy": (
            "Flags owned options for review when time value, theta, near expiry, or missing "
            "fresh chain/underlying data creates material premium-at-risk. Review only; no trades execute."
        ),
    }


def build_push_message(report: dict[str, Any]) -> tuple[str, str, int]:
    alerts = [row for row in report.get("alerts") or [] if isinstance(row, dict)]
    title = f"Options decay audit: {len(alerts)} review"
    priority = 1 if any(row.get("severity") == "critical" for row in alerts) else 0
    lines = [report.get("line") or title]
    for row in alerts[:5]:
        contract = row.get("contract") or {}
        value = abs(float(row.get("market_value") or 0))
        reasons = ", ".join(row.get("reasons") or []) or row.get("severity")
        lines.append(
            f"{row.get('ticker')} {contract.get('expiry')} {str(contract.get('call_put') or '').upper()} "
            f"{contract.get('strike')}: ${value:,.0f}, {row.get('dte')} DTE, "
            f"{row.get('account') or 'account ?'} - {reasons}"
        )
    if len(alerts) > 5:
        lines.append(f"+{len(alerts) - 5} more in the audit file.")
    lines.append("Open the broker/cockpit before acting; no trade is executed by this alert.")
    return title, "\n".join(lines), priority


def run_audit(
    *,
    positions_path: str | Path = DEFAULT_POSITIONS,
    chain_cache_path: str | Path = DEFAULT_CHAIN_CACHE,
    out_path: str | Path = DEFAULT_OUT,
    as_of_text: str | None = None,
    send: bool = False,
    dry_run: bool = False,
    chain_max_age_days: int = DEFAULT_CHAIN_MAX_AGE_DAYS,
) -> dict[str, Any]:
    as_of = _as_of(as_of_text)
    positions_path = Path(positions_path)
    if not positions_path.is_file():
        report = {
            "schema_version": 1,
            "valid": False,
            "checked_at": datetime.now(ET).isoformat(),
            "as_of": as_of.isoformat(),
            "status": "failed",
            "line": f"Options decay audit failed: positions file missing at {positions_path}",
            "counts": {"option_positions": 0},
            "alerts": [],
            "rows": [],
        }
        _atomic_write_json(out_path, report)
        return report
    positions_payload = _read_json(positions_path, {})
    chain_cache = _read_json(chain_cache_path, {}) if Path(chain_cache_path).is_file() else {}
    report = build_audit(
        positions_payload,
        chain_cache=chain_cache,
        as_of=as_of,
        chain_max_age_days=chain_max_age_days,
    )
    delivery = {"attempted": False, "sent": False, "reason": "quiet or --send not requested"}
    if send and report.get("status") == "notify":
        title, message, priority = build_push_message(report)
        try:
            delivery = pushover_notify.send_message(
                title=title,
                message=message,
                priority=priority,
                dry_run=dry_run,
            )
            delivery["attempted"] = True
        except Exception as exc:
            delivery = {"attempted": True, "sent": False, "error": str(exc), "dry_run": dry_run}
    report["delivery"] = delivery
    _atomic_write_json(out_path, report)
    return report


def format_text(report: dict[str, Any]) -> str:
    lines = [
        report.get("line") or "Options decay audit",
        f"valid: {bool(report.get('valid'))}",
        f"status: {report.get('status')}",
        f"counts: {report.get('counts') or {}}",
        f"chain_cache: {report.get('chain_cache') or {}}",
    ]
    for row in (report.get("alerts") or [])[:8]:
        contract = row.get("contract") or {}
        value = abs(float(row.get("market_value") or 0))
        reasons = ", ".join(row.get("reasons") or []) or row.get("severity")
        lines.append(
            f"- {row.get('severity')} {row.get('ticker')} "
            f"{contract.get('expiry')} {str(contract.get('call_put') or '').upper()} {contract.get('strike')}: "
            f"${value:,.0f}, dte={row.get('dte')}, acct={row.get('account') or '?'}"
        )
        lines.append(f"  why: {reasons}")
        if row.get("data_gaps"):
            lines.append(f"  not_checked: {', '.join(row.get('data_gaps') or [])}")
        lines.append(f"  next: {row.get('recommendation')}")
    delivery = report.get("delivery") or {}
    if delivery:
        lines.append(f"Pushover: attempted={bool(delivery.get('attempted'))} sent={bool(delivery.get('sent'))}")
        if delivery.get("error"):
            lines.append(f"Pushover error: {delivery.get('error')}")
    return "\n".join(lines)


def _self_test() -> int:
    payload = {
        "account_positions": [
            {
                "ticker": "HOOD",
                "description": "100 Call 2026-09-18",
                "shares": 2,
                "market_value": 2886,
                "account": "Rollover IRA",
                "owner": "Parents",
                "broker": "Fidelity",
                "asset_type": "option",
                "option": {
                    "underlying": "HOOD",
                    "expiry": "2026-09-18",
                    "call_put": "call",
                    "strike": 100,
                    "multiplier": 100,
                    "occ_symbol": "HOOD  260918C00100000",
                },
            }
        ]
    }
    report = build_audit(payload, chain_cache={}, as_of=date(2026, 6, 30))
    assert report["status"] == "notify"
    assert report["alerts"][0]["ticker"] == "HOOD"
    assert "material_option_premium_unpriced_inside_decay_window" in report["alerts"][0]["reasons"]
    assert build_audit({"account_positions": []}, as_of=date(2026, 6, 30))["status"] == "quiet"
    print("options_decay_audit self-test: PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit owned options for time-decay risk.")
    parser.add_argument("--positions", default=str(DEFAULT_POSITIONS))
    parser.add_argument("--chain-cache", default=str(DEFAULT_CHAIN_CACHE))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--as-of")
    parser.add_argument("--chain-max-age-days", type=int, default=DEFAULT_CHAIN_MAX_AGE_DAYS)
    parser.add_argument("--send", action="store_true", help="Send Pushover when material same-day review is needed.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()

    report = run_audit(
        positions_path=args.positions,
        chain_cache_path=args.chain_cache,
        out_path=args.out,
        as_of_text=args.as_of,
        send=args.send,
        dry_run=args.dry_run,
        chain_max_age_days=args.chain_max_age_days,
    )
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=False, default=str))
    else:
        print(format_text(report))
    delivery = report.get("delivery") or {}
    delivery_failed = bool(delivery.get("attempted")) and not (
        delivery.get("sent") or delivery.get("dry_run")
    )
    return 2 if not report.get("valid") or delivery_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
