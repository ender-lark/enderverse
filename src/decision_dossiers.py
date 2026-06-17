"""Decision Dossier repo mirror and card payload helpers.

The human-editable narrative can live in Notion, but runtime card builders read
only this compact repo mirror. Freshness is enforced per read so stale price or
timing text cannot render as current.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any


SRC = Path(__file__).resolve().parent
DEFAULT_DOSSIERS_PATH = SRC / "decision_dossiers.json"

READ_KEYS = ("edge", "price", "timing", "avoid")
VALID_STATUSES = {"fresh", "stale", "not_checked", "missing", "pending_sync"}


class DossierValidationError(ValueError):
    """Raised when the repo dossier mirror is malformed."""


def _today(value: str | date | None = None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _age_days(as_of: Any, today: date) -> int | None:
    if not as_of:
        return None
    try:
        return (today - date.fromisoformat(str(as_of)[:10])).days
    except ValueError:
        return None


def _problem(problems: list[str], text: str) -> None:
    problems.append(text)


def validate_payload(payload: Any) -> list[str]:
    problems: list[str] = []
    if not isinstance(payload, dict):
        return ["decision_dossiers root must be an object"]
    dossiers = payload.get("dossiers")
    if not isinstance(dossiers, dict):
        return ["decision_dossiers.dossiers must be an object keyed by ticker"]
    for ticker, row in dossiers.items():
        path = f"dossiers.{ticker}"
        if not isinstance(ticker, str) or ticker != ticker.upper().strip() or not ticker:
            _problem(problems, f"{path}: key must be an uppercase ticker")
        if not isinstance(row, dict):
            _problem(problems, f"{path}: row must be an object")
            continue
        if row.get("ticker") != ticker:
            _problem(problems, f"{path}.ticker must match key")
        if row.get("status") not in VALID_STATUSES:
            _problem(problems, f"{path}.status must be one of {sorted(VALID_STATUSES)}")
        if not isinstance(row.get("one_liner"), str) or not row.get("one_liner", "").strip():
            _problem(problems, f"{path}.one_liner must be a non-empty string")
        reads = row.get("reads")
        if not isinstance(reads, dict):
            _problem(problems, f"{path}.reads must be an object")
            continue
        missing = [key for key in READ_KEYS if key not in reads]
        if missing:
            _problem(problems, f"{path}.reads missing key(s) {missing}")
        for key, read in reads.items():
            rpath = f"{path}.reads.{key}"
            if key not in READ_KEYS:
                _problem(problems, f"{rpath}: unknown read key")
            if not isinstance(read, dict):
                _problem(problems, f"{rpath}: read must be an object")
                continue
            for field in ("label", "text"):
                if not isinstance(read.get(field), str) or not read.get(field, "").strip():
                    _problem(problems, f"{rpath}.{field} must be a non-empty string")
            max_age = read.get("max_age_days")
            if max_age is not None and (isinstance(max_age, bool) or not isinstance(max_age, int) or max_age < 0):
                _problem(problems, f"{rpath}.max_age_days must be a non-negative integer or null")
            if read.get("as_of") is not None:
                try:
                    date.fromisoformat(str(read.get("as_of"))[:10])
                except ValueError:
                    _problem(problems, f"{rpath}.as_of must be an ISO date or null")
    return problems


def assert_valid_payload(payload: dict[str, Any]) -> dict[str, Any]:
    problems = validate_payload(payload)
    if problems:
        raise DossierValidationError("; ".join(problems))
    return payload


def load_payload(path: Path | str = DEFAULT_DOSSIERS_PATH) -> dict[str, Any]:
    p = Path(path)
    try:
        payload = json.loads(p.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {"dossiers": {}}
    except json.JSONDecodeError as exc:
        raise DossierValidationError(f"{p.name}: invalid JSON: {exc}") from exc
    return assert_valid_payload(payload)


def load_dossiers(path: Path | str = DEFAULT_DOSSIERS_PATH) -> dict[str, dict[str, Any]]:
    payload = load_payload(path)
    return {
        str(ticker).upper(): row
        for ticker, row in (payload.get("dossiers") or {}).items()
        if isinstance(row, dict)
    }


def _freshness(read: dict[str, Any], today: date) -> dict[str, Any]:
    age = _age_days(read.get("as_of"), today)
    max_age = read.get("max_age_days")
    if age is None:
        return {
            "status": "not_checked",
            "fresh": False,
            "age_days": None,
            "reason": "missing or invalid as_of",
        }
    if isinstance(max_age, int) and age > max_age:
        return {
            "status": "stale",
            "fresh": False,
            "age_days": age,
            "reason": f"as_of {read.get('as_of')} is older than {max_age} day freshness window",
        }
    return {"status": "fresh", "fresh": True, "age_days": age, "reason": ""}


def _render_read(key: str, read: dict[str, Any], today: date) -> dict[str, Any]:
    freshness = _freshness(read, today)
    text = str(read.get("text") or "").strip()
    if not freshness["fresh"] and not text.upper().startswith("UNKNOWN"):
        text = f"UNKNOWN - {read.get('label') or key} read is {freshness['status']}; re-check before action."
    return {
        "key": key,
        "label": read.get("label") or key,
        "text": text,
        "as_of": read.get("as_of"),
        "source": read.get("source"),
        "freshness": freshness,
    }


def card_dossier(
    ticker: str,
    *,
    dossiers: dict[str, dict[str, Any]] | None = None,
    today: str | date | None = None,
) -> dict[str, Any] | None:
    tick = str(ticker or "").upper().strip()
    if not tick:
        return None
    rows = dossiers if dossiers is not None else load_dossiers()
    row = rows.get(tick)
    if not row:
        return None
    today_date = _today(today)
    reads = {
        key: _render_read(key, row["reads"][key], today_date)
        for key in READ_KEYS
    }
    read_statuses = {item["freshness"]["status"] for item in reads.values()}
    status = str(row.get("status") or "not_checked")
    if status == "fresh" and read_statuses - {"fresh"}:
        status = "stale"
    return {
        "ticker": tick,
        "status": status,
        "one_liner": row.get("one_liner"),
        "notion_url": row.get("notion_url"),
        "last_reviewed": row.get("last_reviewed"),
        "next_review_due": row.get("next_review_due"),
        "synced_at": row.get("synced_at"),
        "reads": reads,
    }


def attach_card_dossier(
    card: dict[str, Any],
    *,
    dossiers: dict[str, dict[str, Any]] | None = None,
    today: str | date | None = None,
) -> dict[str, Any]:
    dossier = card_dossier(str(card.get("ticker") or ""), dossiers=dossiers, today=today)
    if dossier:
        card["dossier"] = dossier
    return card
