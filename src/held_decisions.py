#!/usr/bin/env python3
"""Manage operator-parked decision packets with dated review triggers."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HELD = ROOT / "src" / "held_decisions.json"
DEFAULT_REGISTRY = ROOT / "src" / "trigger_registry.json"
OPERATOR_TZ = ZoneInfo("America/New_York")
ACTIVE_STATUSES = {"held", "reparked"}
VALID_STATUSES = {"held", "reviewed", "released", "reparked"}
CONVERGENCE_PAGE = "https://app.notion.com/p/37ec50314bb681f88292d11876b0bd66"


def _now(now: Any = None) -> datetime:
    if now is None:
        return datetime.now(OPERATOR_TZ)
    if isinstance(now, datetime):
        parsed = now
    else:
        text = str(now).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=OPERATOR_TZ)
    return parsed.astimezone(OPERATOR_TZ)


def _today(now: Any = None) -> str:
    return _now(now).date().isoformat()


def _stamp(now: Any = None) -> str:
    return _now(now).isoformat(timespec="seconds")


def _parse_date(value: Any, field: str) -> str:
    try:
        return date.fromisoformat(str(value or "").strip()[:10]).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


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


def load_decisions(path: str | Path = DEFAULT_HELD) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, list):
        raise ValueError("held decisions file must be a JSON array")
    return [dict(row) for row in payload if isinstance(row, dict)]


def save_decisions(rows: list[dict[str, Any]], path: str | Path = DEFAULT_HELD) -> Path:
    for row in rows:
        _validate_packet(row)
    return _atomic_write_json(path, rows)


def load_registry(path: str | Path = DEFAULT_REGISTRY) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict):
        payload = payload.get("triggers") or []
    if not isinstance(payload, list):
        raise ValueError("trigger registry must be a list or object with triggers")
    return [dict(row) for row in payload if isinstance(row, dict)]


def save_registry(rows: list[dict[str, Any]], path: str | Path = DEFAULT_REGISTRY) -> Path:
    return _atomic_write_json(path, rows)


def _validate_packet(row: dict[str, Any]) -> None:
    required = ("id", "title", "notion_url", "parked_date", "review_by", "status", "log")
    missing = [key for key in required if key not in row]
    if missing:
        raise ValueError("held decision missing required field(s): " + ", ".join(missing))
    if str(row.get("status") or "") not in VALID_STATUSES:
        raise ValueError(f"held decision {row.get('id') or ''} has invalid status")
    _parse_date(row.get("parked_date"), "parked_date")
    _parse_date(row.get("review_by"), "review_by")
    if not isinstance(row.get("log"), list):
        raise ValueError(f"held decision {row.get('id') or ''} log must be a list")


def _trigger_id(decision_id: str) -> str:
    return f"held-review-{decision_id}"


def make_review_trigger(packet: dict[str, Any], *, now: Any = None) -> dict[str, Any]:
    decision_id = str(packet.get("id") or "").strip()
    if not decision_id:
        raise ValueError("decision id is required")
    review_by = _parse_date(packet.get("review_by"), "review_by")
    expires = (date.fromisoformat(review_by) + timedelta(days=7)).isoformat()
    title = str(packet.get("title") or decision_id).strip()
    notion_url = str(packet.get("notion_url") or "").strip()
    return {
        "id": _trigger_id(decision_id),
        "ticker": "HELD",
        "condition": {
            "type": "date_event",
            "params": {
                "date": review_by,
                "event": "held_decision_review",
                "held_decision_id": decision_id,
                "title": title,
                "notion_url": notion_url,
                "note": "Operator-parked decision packet review date reached.",
            },
        },
        "source": f"Held decision packet: {title} ({notion_url})",
        "registered_at": _now(now).astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z"),
        "expires": expires,
        "status": "armed",
    }


def upsert_review_trigger(registry: list[dict[str, Any]], packet: dict[str, Any], *, now: Any = None) -> list[dict[str, Any]]:
    trigger = make_review_trigger(packet, now=now)
    wanted = trigger["id"]
    out: list[dict[str, Any]] = []
    replaced = False
    for row in registry:
        if str(row.get("id") or "") == wanted:
            out.append(trigger)
            replaced = True
        else:
            out.append(row)
    if not replaced:
        out.append(trigger)
    return out


def resolve_review_trigger(
    registry: list[dict[str, Any]],
    decision_id: str,
    *,
    action: str,
    now: Any = None,
) -> list[dict[str, Any]]:
    wanted = _trigger_id(decision_id)
    out: list[dict[str, Any]] = []
    stamp = _now(now).astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")
    for row in registry:
        if str(row.get("id") or "") != wanted:
            out.append(row)
            continue
        updated = dict(row)
        if action == "go":
            updated["status"] = "fired"
            updated["fired_at"] = stamp
            updated["fire_reason"] = "operator resolved held decision: go"
        else:
            updated["status"] = "cancelled"
            updated["cancelled_at"] = stamp
            updated["cancel_reason"] = f"operator resolved held decision: {action}"
        out.append(updated)
    return out


def add_decision(
    *,
    decision_id: str,
    title: str,
    notion_url: str,
    review_by: str,
    parked_date: str | None = None,
    note: str = "",
    held_path: str | Path = DEFAULT_HELD,
    registry_path: str | Path = DEFAULT_REGISTRY,
    now: Any = None,
) -> dict[str, Any]:
    decision_id = str(decision_id or "").strip()
    if not decision_id:
        raise ValueError("--id is required")
    rows = load_decisions(held_path)
    if any(str(row.get("id") or "") == decision_id for row in rows):
        raise ValueError(f"held decision already exists: {decision_id}")
    packet = {
        "id": decision_id,
        "title": str(title or "").strip(),
        "notion_url": str(notion_url or "").strip(),
        "parked_date": _parse_date(parked_date or _today(now), "parked_date"),
        "review_by": _parse_date(review_by, "review_by"),
        "status": "held",
        "log": [{
            "at": _stamp(now),
            "action": "parked",
            "note": str(note or "operator parked decision packet").strip(),
        }],
    }
    _validate_packet(packet)
    registry = upsert_review_trigger(load_registry(registry_path), packet, now=now)
    rows.append(packet)
    save_decisions(rows, held_path)
    save_registry(registry, registry_path)
    return packet


def resolve_decision(
    decision_id: str,
    *,
    action: str,
    new_date: str | None = None,
    note: str = "",
    held_path: str | Path = DEFAULT_HELD,
    registry_path: str | Path = DEFAULT_REGISTRY,
    now: Any = None,
) -> dict[str, Any]:
    action = str(action or "").strip().lower()
    if action not in {"go", "kill", "repark"}:
        raise ValueError("--action must be one of go, kill, repark")
    rows = load_decisions(held_path)
    packet: dict[str, Any] | None = None
    for row in rows:
        if str(row.get("id") or "") == decision_id:
            packet = row
            break
    if packet is None:
        raise ValueError(f"held decision not found: {decision_id}")
    if action == "repark":
        if not new_date:
            raise ValueError("--new-date is required for --action repark")
        packet["status"] = "reparked"
        packet["review_by"] = _parse_date(new_date, "new_date")
        packet.setdefault("log", []).append({
            "at": _stamp(now),
            "action": "repark",
            "note": str(note or f"reparked for {packet['review_by']}").strip(),
        })
        registry = upsert_review_trigger(load_registry(registry_path), packet, now=now)
    else:
        packet["status"] = "released" if action == "go" else "reviewed"
        packet.setdefault("log", []).append({
            "at": _stamp(now),
            "action": action,
            "note": str(note or f"operator resolved held decision: {action}").strip(),
        })
        registry = resolve_review_trigger(load_registry(registry_path), decision_id, action=action, now=now)
    save_decisions(rows, held_path)
    save_registry(registry, registry_path)
    return packet


def active_decisions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if str(row.get("status") or "") in ACTIVE_STATUSES]


def format_list(rows: list[dict[str, Any]]) -> str:
    active = active_decisions(rows)
    if not active:
        return "held decisions: none"
    lines = [f"held decisions: {len(active)} active"]
    for row in active:
        lines.append(f"- {row.get('id')}: {row.get('title')} review_by={row.get('review_by')} status={row.get('status')}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage operator-held decision packets")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--add", action="store_true")
    mode.add_argument("--resolve", metavar="ID")
    mode.add_argument("--list", action="store_true")
    parser.add_argument("--held-path", default=str(DEFAULT_HELD))
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--id", help="Decision id for --add")
    parser.add_argument("--title", default="")
    parser.add_argument("--notion-url", default="")
    parser.add_argument("--parked-date")
    parser.add_argument("--review-by")
    parser.add_argument("--action", choices=("go", "kill", "repark"))
    parser.add_argument("--new-date")
    parser.add_argument("--note", default="")
    parser.add_argument("--now")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    if args.add:
        packet = add_decision(
            decision_id=args.id or "",
            title=args.title,
            notion_url=args.notion_url,
            parked_date=args.parked_date,
            review_by=args.review_by or "",
            note=args.note,
            held_path=args.held_path,
            registry_path=args.registry,
            now=args.now,
        )
        result: Any = {"added": packet}
    elif args.resolve:
        if not args.action:
            raise ValueError("--action is required with --resolve")
        packet = resolve_decision(
            args.resolve,
            action=args.action,
            new_date=args.new_date,
            note=args.note,
            held_path=args.held_path,
            registry_path=args.registry,
            now=args.now,
        )
        result = {"resolved": packet}
    else:
        rows = load_decisions(args.held_path)
        result = {"rows": rows, "active_count": len(active_decisions(rows))}

    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=False))
    elif args.list:
        print(format_list(result["rows"]))
    elif args.add:
        print(f"added held decision: {result['added']['id']} review_by={result['added']['review_by']}")
    else:
        print(f"resolved held decision: {result['resolved']['id']} status={result['resolved']['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
