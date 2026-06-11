"""The Insight Register â€” the operator's worldview as first-class data.

Implements the Operator Insight Layer mandate: insights sit at the center;
every source is an evidence stream feeding them. This module owns the
InsightRecord contract (``src/insights.json``) and the pure helpers the
engines consume:

* **Hook 1 â€” discovery boost**: :func:`discovery_boost` (triage points for
  signals touching an ACTIVE insight's tickers).
* **Hook 2 â€” scoring**: :func:`conviction_points` â€” an insight match counts
  as ONE signal in its own ``operator_insight`` independence group.
  **Binding rule:** multiple matching insights take the MAX strength, never a
  sum â€” two operator-origin signals structurally cannot compound.
* **Hook 3 â€” standing research lens**: ACTIVE insights expose
  ``watch_tickers`` and sectors as persistent research scope.
* **Hook 5 â€” calibration**: evidence rows use confirmation-vs-change
  semantics. A ``confirmation`` row records that a source repeated the thesis
  and **changes no weight, status, or strength** â€” repetition is not
  strengthening (the doctrine anti-pattern). A ``change`` row records genuinely
  new information and marks the insight review-due.

(Hook 4 â€” book congruence â€” lives in ``congruence.py``.)

Honest absence: a missing/invalid ``insights.json`` raises; callers render
"not checked" â€” the register is never silently empty.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

SRC = Path(__file__).resolve().parent
INSIGHTS_PATH = SRC / "insights.json"

STATUSES = {"ACTIVE", "WEAKENED", "VALIDATED", "RETIRED"}
POLARITIES = {"bullish", "risk"}
EVIDENCE_KINDS = {"new", "confirmation", "change"}
MATCH_STRENGTHS = ("direct", "adjacent", "watch", "thematic")
_ID_PREFIX = "INSIGHT-"

class InsightsError(Exception):
    pass

class InsightsMissingError(InsightsError):
    pass

class InsightsInvalidError(InsightsError):
    pass

def _parse_date(value: Any, field: str, problems: list[str]) -> None:
    try:
        datetime.strptime(str(value), "%Y-%m-%d")
    except (TypeError, ValueError):
        problems.append(f"{field} '{value}' is not a YYYY-MM-DD date")

def load_insights(path: Path | str = INSIGHTS_PATH) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise InsightsMissingError(
            f"{path.name} is absent â€” insight register NOT loaded (honest absence)."
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InsightsInvalidError(f"{path.name} is not valid JSON: {exc}") from exc
    problems = validate_insights(payload)
    if problems:
        raise InsightsInvalidError(f"{path.name} invalid: " + "; ".join(problems))
    return payload

def validate_insights(payload: Any, *, max_active: int | None = None) -> list[str]:
    """Return problems (empty = valid)."""
    problems: list[str] = []
    if not isinstance(payload, dict) or not isinstance(payload.get("insights"), list):
        return ["payload must be an object with an 'insights' list"]
    seen: set[str] = set()
    active = 0
    for i, ins in enumerate(payload["insights"]):
        where = f"insights[{i}]"
        if not isinstance(ins, dict):
            problems.append(f"{where} must be an object")
            continue
        iid = str(ins.get("insight_id") or "")
        if not iid.startswith(_ID_PREFIX):
            problems.append(f"{where}: insight_id '{iid}' must start with {_ID_PREFIX}")
        if iid in seen:
            problems.append(f"{where}: duplicate insight_id '{iid}'")
        seen.add(iid)
        if not str(ins.get("statement") or "").strip():
            problems.append(f"{where}: statement is required (the operator's words)")
        if ins.get("status") not in STATUSES:
            problems.append(f"{where}: status '{ins.get('status')}' not in {sorted(STATUSES)}")
        if ins.get("polarity") not in POLARITIES:
            problems.append(f"{where}: polarity '{ins.get('polarity')}' not in {sorted(POLARITIES)}")
        strength = ins.get("belief_strength")
        if isinstance(strength, bool) or not isinstance(strength, (int, float)) or not 0 <= strength <= 100:
            problems.append(f"{where}: belief_strength must be 0-100")
        _parse_date(ins.get("stated"), f"{where}.stated", problems)
        _parse_date(ins.get("last_reviewed"), f"{where}.last_reviewed", problems)
        for key in ("tickers_mapped", "tickers_adjacent", "watch_tickers", "sectors", "keywords", "factor_tags"):
            vals = ins.get(key)
            if not isinstance(vals, list):
                problems.append(f"{where}: {key} must be a list")
            elif key.startswith(("tickers", "watch")):
                bad = [t for t in vals if not isinstance(t, str) or t != t.upper()]
                if bad:
                    problems.append(f"{where}: {key} tickers must be uppercase strings: {bad}")
        for side in ("evidence_for", "evidence_against"):
            for j, row in enumerate(ins.get(side) or []):
                if not isinstance(row, dict) or row.get("kind") not in EVIDENCE_KINDS:
                    problems.append(
                        f"{where}.{side}[{j}]: kind must be one of {sorted(EVIDENCE_KINDS)}"
                    )
                elif not str(row.get("note") or "").strip():
                    problems.append(f"{where}.{side}[{j}]: note required")
        if ins.get("status") == "ACTIVE":
            active += 1
    if max_active is not None and active > max_active:
        problems.append(
            f"{active} ACTIVE insights exceeds insight_max_active={max_active} â€” "
            "retire or merge before adding (cap is a focus rail, surfaced not silent)"
        )
    return problems

def _today(today: str | date | None) -> date:
    if today is None:
        return date.today()
    if isinstance(today, date):
        return today
    return datetime.strptime(str(today), "%Y-%m-%d").date()

def active_insights(
    payload: dict[str, Any], *, today: str | date | None = None, stale_days: int = 60
) -> list[dict[str, Any]]:
    """ACTIVE insights, each augmented with staleness (review-due) flags."""
    now = _today(today)
    out: list[dict[str, Any]] = []
    for ins in payload.get("insights", []):
        if ins.get("status") != "ACTIVE":
            continue
        reviewed = datetime.strptime(str(ins["last_reviewed"]), "%Y-%m-%d").date()
        days = (now - reviewed).days
        row = dict(ins)
        row["days_since_review"] = days
        row["stale"] = days > stale_days
        out.append(row)
    return out

def match(
    payload: dict[str, Any],
    *,
    ticker: str | None = None,
    sectors: list[str] | None = None,
    text: str | None = None,
    today: str | date | None = None,
) -> list[dict[str, Any]]:
    """Match a signal against ACTIVE insights.

    Strengths (strongest wins per insight): ``direct`` (tickers_mapped) >
    ``adjacent`` > ``watch`` > ``thematic`` (sector overlap or keyword in
    text). Non-ACTIVE insights never match.
    """
    tick = (ticker or "").upper().strip()
    secs = {s.lower() for s in (sectors or [])}
    blob = (text or "").lower()
    hits: list[dict[str, Any]] = []
    for ins in active_insights(payload, today=today, stale_days=10**6):
        strength = None
        if tick:
            if tick in ins.get("tickers_mapped", []):
                strength = "direct"
            elif tick in ins.get("tickers_adjacent", []):
                strength = "adjacent"
            elif tick in ins.get("watch_tickers", []):
                strength = "watch"
        if strength is None:
            if secs & {s.lower() for s in ins.get("sectors", [])}:
                strength = "thematic"
            elif blob and any(k.lower() in blob for k in ins.get("keywords", [])):
                strength = "thematic"
        if strength:
            hits.append(
                {"insight_id": ins["insight_id"], "strength": strength, "insight": ins}
            )
    return hits

def conviction_points(
    matches: list[dict[str, Any]], weights: dict[str, Any]
) -> dict[str, Any]:
    """Hook 2 â€” the operator_insight group contribution for one signal/name.

    BINDING: multiple matches take the MAX-strength single contribution and
    are then capped at ``group_caps.operator_insight`` â€” operator-origin
    items never compound with each other.
    """
    base = float(weights.get("insight_match_points", 1.0))
    cap = float(weights.get("group_caps", {}).get("operator_insight", 1.0))
    scale = {"direct": 1.0, "adjacent": 0.5, "watch": 0.25, "thematic": 0.25}
    best = 0.0
    best_strength = None
    for m in matches:
        pts = base * scale.get(m.get("strength"), 0.0)
        if pts > best:
            best, best_strength = pts, m.get("strength")
    return {
        "points": min(best, cap),
        "strength": best_strength,
        "matched": [m["insight_id"] for m in matches],
        "compounded": False,
    }

def discovery_boost(
    payload: dict[str, Any], ticker: str, weights: dict[str, Any]
) -> dict[str, Any]:
    """Hook 1 â€” triage boost for discovery-time signals on insight tickers.

    Full boost on direct/adjacent/watch ticker matches; thematic keyword
    matches get no boost (keyword noise must not move triage).
    """
    hits = [m for m in match(payload, ticker=ticker) if m["strength"] != "thematic"]
    boost = float(weights.get("insight_triage_boost", 0)) if hits else 0.0
    return {"boost": boost, "matches": [m["insight_id"] for m in hits]}

def research_scope(payload: dict[str, Any]) -> dict[str, Any]:
    """Hook 3 â€” the standing research lens from ACTIVE insights."""
    tickers: set[str] = set()
    sectors: set[str] = set()
    for ins in active_insights(payload, stale_days=10**6):
        tickers.update(ins.get("watch_tickers", []))
        tickers.update(ins.get("tickers_mapped", []))
        sectors.update(ins.get("sectors", []))
    return {"tickers": sorted(tickers), "sectors": sorted(sectors)}

def add_evidence(
    payload: dict[str, Any],
    insight_id: str,
    *,
    kind: str,
    note: str,
    side: str = "evidence_for",
    on: str | None = None,
) -> dict[str, Any]:
    """Append an evidence row. ``confirmation`` changes NO weight/status/strength;
    ``change`` marks the insight review-due (last_reviewed untouched so staleness
    machinery surfaces it)."""
    if kind not in EVIDENCE_KINDS:
        raise InsightsInvalidError(f"kind must be one of {sorted(EVIDENCE_KINDS)}")
    if side not in ("evidence_for", "evidence_against"):
        raise InsightsInvalidError("side must be evidence_for or evidence_against")
    ins = _find(payload, insight_id)
    row = {"date": on or date.today().isoformat(), "kind": kind, "note": note}
    ins.setdefault(side, []).append(row)
    ins.setdefault("history", []).append(
        {"date": row["date"], "event": f"evidence:{kind}", "note": note[:140]}
    )
    if kind == "change":
        ins["needs_review"] = True
    return row

def set_status(
    payload: dict[str, Any],
    insight_id: str,
    status: str,
    *,
    reason: str,
    on: str | None = None,
) -> dict[str, Any]:
    if status not in STATUSES:
        raise InsightsInvalidError(f"status must be one of {sorted(STATUSES)}")
    if not str(reason).strip():
        raise InsightsInvalidError("a reason is required for status changes")
    ins = _find(payload, insight_id)
    when = on or date.today().isoformat()
    ins.setdefault("history", []).append(
        {"date": when, "event": f"status:{ins.get('status')}->{status}", "note": reason}
    )
    ins["status"] = status
    ins["last_reviewed"] = when
    ins.pop("needs_review", None)
    return ins

def _find(payload: dict[str, Any], insight_id: str) -> dict[str, Any]:
    for ins in payload.get("insights", []):
        if ins.get("insight_id") == insight_id:
            return ins
    raise InsightsInvalidError(f"unknown insight_id '{insight_id}'")

def save_insights(payload: dict[str, Any], path: Path | str = INSIGHTS_PATH) -> None:
    problems = validate_insights(payload)
    if problems:
        raise InsightsInvalidError("refusing to save invalid register: " + "; ".join(problems))
    payload = dict(payload)
    payload["updated"] = date.today().isoformat()
    Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
