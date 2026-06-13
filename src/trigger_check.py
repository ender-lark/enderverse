#!/usr/bin/env python3
"""Evaluate operator trigger conditions and surface missed-trigger risk.

The registry is intentionally small and explicit. Routines can add armed
triggers, and this checker turns them into review prompts when the condition is
proven. Missing quote data is reported as not_checked, never as clear.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

import cloud_routine_receipts
import pushover_notify


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "src" / "trigger_registry.json"
DEFAULT_SUMMARY = ROOT / "src" / "trigger_check_summary.json"
DEFAULT_RECEIPTS = ROOT / "src" / "cloud_routine_receipts.json"

ARMED_STATUSES = {"armed", "active"}
TERMINAL_STATUSES = {"fired", "expired", "cancelled"}
CONDITION_TYPES = {"price_cross", "level_touch", "iv_threshold", "date_event"}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _as_datetime(value: Any = None) -> datetime:
    if value is None:
        return _now_utc()
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed_date = date.fromisoformat(text[:10])
        return datetime(parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=timezone.utc)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _date_from_text(value: Any) -> date | None:
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
            json.dump(payload, fh, indent=2, sort_keys=False)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if math.isnan(float(value)):
            return None
        return float(value)
    text = str(value).replace("$", "").replace(",", "").replace("%", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def load_registry(path: str | Path = DEFAULT_REGISTRY) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict):
        payload = payload.get("triggers") or []
    if not isinstance(payload, list):
        raise ValueError("trigger registry must be a list or an object with a triggers list")
    return [dict(row) for row in payload if isinstance(row, dict)]


def save_registry(registry: list[dict[str, Any]], path: str | Path = DEFAULT_REGISTRY) -> Path:
    return _atomic_write_json(path, registry)


def load_quotes(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("quote payload must be a JSON object keyed by ticker")
    return {str(key).upper(): value for key, value in payload.items()}


def load_quote_cache(src_dir: str | Path = ROOT / "src") -> dict[str, Any]:
    """Load best-effort local quote cache without pretending it is complete."""
    src = Path(src_dir)
    quotes: dict[str, Any] = {}
    closes_path = src / "uw_closes.json"
    if closes_path.is_file():
        try:
            closes = json.loads(closes_path.read_text(encoding="utf-8-sig"))
        except Exception:
            closes = {}
        if isinstance(closes, dict):
            for ticker, series in closes.items():
                if isinstance(series, list) and series:
                    last = _num(series[-1])
                    if last is not None:
                        quotes[str(ticker).upper()] = {
                            "price": last,
                            "last": last,
                            "close": last,
                            "weekly_close": last,
                            "source": "uw_closes.json",
                        }
                elif isinstance(series, dict):
                    quotes[str(ticker).upper()] = dict(series)
    return quotes


def quote_fn_from_map(quotes: dict[str, Any]) -> Callable[[str], Any]:
    normalized = {str(key).upper(): value for key, value in quotes.items()}
    return lambda ticker: normalized.get(str(ticker).upper())


def make_trigger(
    *,
    trigger_id: str,
    ticker: str,
    condition_type: str,
    params: dict[str, Any],
    source: str,
    registered_at: str | None = None,
    expires: str | None = None,
    status: str = "armed",
    note: str = "",
) -> dict[str, Any]:
    return {
        "id": trigger_id,
        "ticker": ticker.upper().strip(),
        "condition": {"type": condition_type, "params": params},
        "source": source,
        "registered_at": registered_at or _now_utc().isoformat().replace("+00:00", "Z"),
        "expires": expires or "",
        "status": status,
        **({"note": note} if note else {}),
    }


def upsert_trigger(registry: list[dict[str, Any]], trigger: dict[str, Any]) -> list[dict[str, Any]]:
    """Insert or update an armed trigger without resetting fired history."""
    incoming_id = str(trigger.get("id") or "").strip()
    if not incoming_id:
        raise ValueError("trigger.id is required")
    out: list[dict[str, Any]] = []
    replaced = False
    for row in registry:
        if str(row.get("id") or "") != incoming_id:
            out.append(row)
            continue
        existing_status = str(row.get("status") or "armed").lower()
        if existing_status in TERMINAL_STATUSES:
            out.append(row)
        else:
            merged = dict(row)
            merged.update(trigger)
            merged.setdefault("status", "armed")
            out.append(merged)
        replaced = True
    if not replaced:
        out.append(dict(trigger))
    return out


def _trigger_base(row: dict[str, Any]) -> dict[str, Any]:
    condition = row.get("condition") if isinstance(row.get("condition"), dict) else {}
    return {
        "id": row.get("id") or "",
        "ticker": str(row.get("ticker") or "").upper(),
        "condition_type": condition.get("type") or "",
        "source": row.get("source") or "",
        "status": row.get("status") or "armed",
    }


def _quote_value(quote: Any, field: str) -> float | None:
    if not isinstance(quote, dict):
        return _num(quote)
    candidates = [field]
    if field in {"price", "last"}:
        candidates.extend(["last", "price", "close", "last_close", "mark"])
    if field == "weekly_close":
        candidates.extend(["weekly_close", "close", "last_close", "price", "last"])
    for key in candidates:
        if key in quote:
            value = _num(quote.get(key))
            if value is not None:
                return value
    return None


def _evaluate_price_cross(row: dict[str, Any], quote: Any) -> tuple[bool, str | None]:
    condition = row.get("condition") if isinstance(row.get("condition"), dict) else {}
    params = condition.get("params") if isinstance(condition.get("params"), dict) else {}
    field = str(params.get("field") or "price")
    direction = str(params.get("direction") or params.get("operator") or "above").lower()
    level = _num(params.get("level") or params.get("threshold"))
    value = _quote_value(quote, field)
    if level is None:
        return False, "price_cross missing level"
    if value is None:
        return False, f"no quote field {field}"
    if direction in {"above", ">", ">=", "crosses_above"}:
        fired = value >= level
        return fired, f"{field} {value:g} >= {level:g}" if fired else None
    if direction in {"below", "<", "<=", "crosses_below"}:
        fired = value <= level
        return fired, f"{field} {value:g} <= {level:g}" if fired else None
    return False, f"unsupported price_cross direction {direction}"


def _evaluate_level_touch(row: dict[str, Any], quote: Any) -> tuple[bool, str | None]:
    condition = row.get("condition") if isinstance(row.get("condition"), dict) else {}
    params = condition.get("params") if isinstance(condition.get("params"), dict) else {}
    zone_low = _num(params.get("zone_low") or params.get("low"))
    zone_high = _num(params.get("zone_high") or params.get("high"))
    if zone_low is None or zone_high is None:
        return False, "level_touch missing zone"
    lo, hi = sorted([zone_low, zone_high])
    if isinstance(quote, dict):
        low_field = str(params.get("low_field") or "intraday_low")
        high_field = str(params.get("high_field") or "intraday_high")
        quote_low = _quote_value(quote, low_field)
        quote_high = _quote_value(quote, high_field)
        if quote_low is None:
            quote_low = _quote_value(quote, "low")
        if quote_high is None:
            quote_high = _quote_value(quote, "high")
        if quote_low is not None and quote_high is not None:
            qlo, qhi = sorted([quote_low, quote_high])
            fired = qlo <= hi and qhi >= lo
            return fired, f"range {qlo:g}-{qhi:g} touched {lo:g}-{hi:g}" if fired else None
    price = _quote_value(quote, "price")
    if price is None:
        return False, "no quote range or price"
    fired = lo <= price <= hi
    return fired, f"price {price:g} inside {lo:g}-{hi:g}" if fired else None


def _evaluate_iv_threshold(row: dict[str, Any], quote: Any) -> tuple[bool, str | None]:
    condition = row.get("condition") if isinstance(row.get("condition"), dict) else {}
    params = condition.get("params") if isinstance(condition.get("params"), dict) else {}
    field = str(params.get("field") or "iv_rank")
    operator = str(params.get("operator") or params.get("direction") or "below").lower()
    threshold = _num(params.get("threshold") or params.get("level"))
    value = _quote_value(quote, field)
    if threshold is None:
        return False, "iv_threshold missing threshold"
    if value is None:
        return False, f"no quote field {field}"
    if operator in {"below", "<", "<="}:
        fired = value <= threshold
        return fired, f"{field} {value:g} <= {threshold:g}" if fired else None
    if operator in {"above", ">", ">="}:
        fired = value >= threshold
        return fired, f"{field} {value:g} >= {threshold:g}" if fired else None
    return False, f"unsupported iv_threshold operator {operator}"


def _evaluate_date_event(row: dict[str, Any], as_of: datetime) -> tuple[bool, str | None]:
    condition = row.get("condition") if isinstance(row.get("condition"), dict) else {}
    params = condition.get("params") if isinstance(condition.get("params"), dict) else {}
    event_date = _date_from_text(params.get("date") or params.get("event_date"))
    if event_date is None:
        return False, "date_event missing date"
    fired = as_of.date() >= event_date
    return fired, f"date_event due {event_date.isoformat()}" if fired else None


def evaluate_registry(
    registry: list[dict[str, Any]],
    quote_fn: Callable[[str], Any],
    *,
    as_of: Any = None,
) -> dict[str, Any]:
    checked_at = _as_datetime(as_of)
    fired: list[dict[str, Any]] = []
    not_checked: list[dict[str, Any]] = []
    expired: list[dict[str, Any]] = []
    checked: list[dict[str, Any]] = []

    for row in registry:
        status = str(row.get("status") or "armed").lower()
        base = _trigger_base(row)
        if status in TERMINAL_STATUSES:
            continue
        if status not in ARMED_STATUSES:
            not_checked.append({**base, "reason": f"unsupported status {status}"})
            continue
        expires = _date_from_text(row.get("expires"))
        if expires and expires < checked_at.date():
            row["status"] = "expired"
            row["expired_at"] = checked_at.isoformat().replace("+00:00", "Z")
            expired.append({**base, "status": "expired", "reason": f"expired {expires.isoformat()}"})
            continue
        ticker = str(row.get("ticker") or "").upper().strip()
        condition = row.get("condition") if isinstance(row.get("condition"), dict) else {}
        condition_type = str(condition.get("type") or "")
        if not ticker:
            not_checked.append({**base, "reason": "missing ticker"})
            continue
        if condition_type not in CONDITION_TYPES:
            not_checked.append({**base, "reason": f"unsupported condition {condition_type or 'missing'}"})
            continue

        quote = None if condition_type == "date_event" else quote_fn(ticker)
        if condition_type != "date_event" and quote is None:
            not_checked.append({**base, "reason": "quote not checked"})
            continue

        if condition_type == "price_cross":
            did_fire, reason = _evaluate_price_cross(row, quote)
        elif condition_type == "level_touch":
            did_fire, reason = _evaluate_level_touch(row, quote)
        elif condition_type == "iv_threshold":
            did_fire, reason = _evaluate_iv_threshold(row, quote)
        else:
            did_fire, reason = _evaluate_date_event(row, checked_at)

        if reason and reason.startswith(("no quote", "price_cross missing", "level_touch missing", "iv_threshold missing", "date_event missing", "unsupported")):
            not_checked.append({**base, "reason": reason})
            continue
        checked.append({**base, "fired": did_fire})
        if did_fire:
            row["status"] = "fired"
            row["fired_at"] = checked_at.isoformat().replace("+00:00", "Z")
            row["fire_reason"] = reason or "condition fired"
            fired.append({**_trigger_base(row), "status": "fired", "fire_reason": row["fire_reason"]})

    armed_count = sum(1 for row in registry if str(row.get("status") or "armed").lower() in ARMED_STATUSES)
    return {
        "checked_at": checked_at.isoformat().replace("+00:00", "Z"),
        "status": "fired" if fired else "not_checked" if not_checked else "checked_clear",
        "fired_count": len(fired),
        "not_checked_count": len(not_checked),
        "expired_count": len(expired),
        "checked_count": len(checked),
        "armed_count": armed_count,
        "fired": fired,
        "not_checked": not_checked,
        "expired": expired,
        "line": _summary_line(len(fired), len(not_checked), armed_count, len(expired)),
    }


def evaluate(registry: list[dict[str, Any]], quote_fn: Callable[[str], Any], as_of: Any = None) -> list[dict[str, Any]]:
    """Mutate registry and return newly fired trigger rows."""
    return evaluate_registry(registry, quote_fn, as_of=as_of)["fired"]


def _summary_line(fired_count: int, not_checked_count: int, armed_count: int, expired_count: int) -> str:
    return (
        "Trigger check: "
        f"fired={fired_count}; not_checked={not_checked_count}; "
        f"armed={armed_count}; expired={expired_count}."
    )


def write_summary(report: dict[str, Any], path: str | Path = DEFAULT_SUMMARY) -> Path:
    return _atomic_write_json(path, report)


def _notification_message(fired: list[dict[str, Any]]) -> str:
    lines = ["Open the cockpit before acting. Newly fired trigger(s):"]
    for row in fired[:8]:
        lines.append(
            f"- {row.get('ticker') or 'UNKNOWN'}: {row.get('id') or ''} "
            f"({row.get('fire_reason') or 'condition fired'})"
        )
    if len(fired) > 8:
        lines.append(f"- +{len(fired) - 8} more")
    return "\n".join(lines)


def send_fired_notifications(
    fired: list[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not fired:
        return {"attempted": False, "sent": False, "reason": "no fired triggers"}
    try:
        result = pushover_notify.send_message(
            title="Investing OS trigger fired",
            message=_notification_message(fired),
            priority=1,
            dry_run=dry_run,
        )
    except Exception as exc:
        return {"attempted": True, "sent": False, "error": str(exc)}
    return {"attempted": True, **result}


def append_fire_receipt(
    report: dict[str, Any],
    *,
    receipt_path: str | Path = DEFAULT_RECEIPTS,
    routine_id: str = "investing-os-trigger-check",
    run_source: str = "scheduled",
) -> dict[str, Any] | None:
    fired = report.get("fired") or []
    if not fired:
        return None
    tickers = ", ".join(row.get("ticker") or "UNKNOWN" for row in fired[:8])
    summary = f"trigger check fired {len(fired)} trigger(s): {tickers}"
    return cloud_routine_receipts.append_receipt(
        path=receipt_path,
        routine_id=routine_id,
        status="success",
        run_source=run_source,
        summary=summary,
        details={
            "fired": fired,
            "not_checked_count": report.get("not_checked_count") or 0,
            "summary_line": report.get("line") or "",
        },
    )


def format_text(report: dict[str, Any]) -> str:
    lines = [str(report.get("line") or "Trigger check: no report.")]
    fired = report.get("fired") or []
    if fired:
        lines.append("Fired:")
        for row in fired:
            lines.append(
                f"- {row.get('ticker') or 'UNKNOWN'} {row.get('id') or ''}: "
                f"{row.get('fire_reason') or 'condition fired'}"
            )
    not_checked = report.get("not_checked") or []
    if not_checked:
        lines.append("Not checked:")
        for row in not_checked[:10]:
            lines.append(
                f"- {row.get('ticker') or 'UNKNOWN'} {row.get('id') or ''}: "
                f"{row.get('reason') or 'not checked'}"
            )
        if len(not_checked) > 10:
            lines.append(f"- +{len(not_checked) - 10} more")
    delivery = report.get("delivery") or {}
    if delivery:
        lines.append(f"Pushover: attempted={bool(delivery.get('attempted'))} sent={bool(delivery.get('sent'))}")
        if delivery.get("error"):
            lines.append(f"Pushover error: {delivery.get('error')}")
    if report.get("receipt"):
        lines.append(f"Receipt: {report['receipt'].get('routine_id')} {report['receipt'].get('status')}")
    if report.get("write_blocked"):
        lines.append(f"Write blocked: {report.get('write_blocked')}")
    if report.get("written"):
        lines.append(f"Written: {report.get('registry_path') or ''} {report.get('summary_path') or ''}".strip())
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate Investing OS trigger registry")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--src-dir", default=str(ROOT / "src"))
    parser.add_argument("--quotes-json", help="Optional quote map JSON keyed by ticker")
    parser.add_argument("--write", action="store_true", help="Persist registry state and trigger summary")
    parser.add_argument("--send", action="store_true", help="Send Pushover notification when triggers fire")
    parser.add_argument("--dry-run", action="store_true", help="Dry-run notification; does not imply --write")
    parser.add_argument("--receipt-path", default=str(DEFAULT_RECEIPTS))
    parser.add_argument("--routine-id", default="investing-os-trigger-check")
    parser.add_argument("--run-source", choices=["manual", "scheduled"], default="scheduled")
    parser.add_argument("--as-of")
    parser.add_argument("--format", choices=["json", "text"], default="json")
    args = parser.parse_args(argv)

    registry = load_registry(args.registry)
    original_registry = copy.deepcopy(registry)
    quotes = load_quotes(args.quotes_json) if args.quotes_json else load_quote_cache(args.src_dir)
    report = evaluate_registry(registry, quote_fn_from_map(quotes), as_of=args.as_of)

    delivery_failed = False
    if args.send and report.get("fired"):
        report["delivery"] = send_fired_notifications(report["fired"], dry_run=args.dry_run)
        delivery_failed = not args.dry_run and not bool((report.get("delivery") or {}).get("sent"))
        if delivery_failed:
            report["status"] = "send_failed"
            report["write_blocked"] = (
                "Pushover notification failed; trigger registry state was not advanced "
                "so the next scheduled check can retry."
            )
    if args.write:
        save_registry(original_registry if delivery_failed else registry, args.registry)
        write_summary(report, args.summary)
        report["written"] = True
        report["registry_path"] = args.registry
        report["summary_path"] = args.summary
        if delivery_failed and report.get("fired"):
            report["receipt"] = cloud_routine_receipts.append_receipt(
                path=args.receipt_path,
                routine_id=args.routine_id,
                status="failed",
                run_source=args.run_source,
                summary="trigger check fired but Pushover notification failed; registry state not advanced",
                details={
                    "fired": report.get("fired") or [],
                    "delivery": report.get("delivery") or {},
                    "summary_line": report.get("line") or "",
                },
            )
        else:
            receipt = append_fire_receipt(
                report,
                receipt_path=args.receipt_path,
                routine_id=args.routine_id,
                run_source=args.run_source,
            )
            if receipt:
                report["receipt"] = receipt

    if args.format == "text":
        print(format_text(report))
    else:
        print(json.dumps(report, indent=2, sort_keys=False))
    return 2 if delivery_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
