"""Event-risk lane helpers.

This is supplied-data only: it normalizes already-collected daily/weekly event
risk rows into conservative review actions. It does not fetch headlines or
invent market calls.
"""
from __future__ import annotations

from typing import Any


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
PROMOTE_SEVERITIES = {"critical", "high"}


def _text(value: Any) -> str:
    return str(value).strip() if value not in (None, "") else ""


def _string_list(value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value).strip()]


def normalize_event_risk_row(row: dict, *, default_date: str = "") -> dict | None:
    if not isinstance(row, dict):
        return None
    title = _text(
        row.get("title")
        or row.get("event")
        or row.get("headline")
        or row.get("what")
    )
    if not title:
        return None
    severity = _text(row.get("severity") or row.get("priority") or "medium").lower()
    if severity not in SEVERITY_ORDER:
        severity = "medium"
    horizon = _text(row.get("horizon") or row.get("time_horizon") or row.get("window") or "daily")
    date = _text(row.get("date") or row.get("as_of") or row.get("published_at") or default_date)
    channels = _string_list(row.get("channels") or row.get("channel") or row.get("asset_classes"))
    tickers = [tk.upper() for tk in _string_list(row.get("tickers") or row.get("ticker") or row.get("symbols"))]
    affected = _string_list(row.get("affected") or row.get("affected_sleeves") or row.get("sleeves"))
    source = _text(row.get("source") or "Event Risk")
    summary = _text(row.get("summary") or row.get("why") or row.get("detail"))
    trigger = _text(row.get("trigger") or row.get("watch_for") or row.get("next_evidence"))
    direction = _text(row.get("direction") or row.get("bias") or "risk_watch").lower()
    return {
        "date": date,
        "title": title,
        "severity": severity,
        "horizon": horizon,
        "channels": channels,
        "tickers": tickers,
        "affected": affected,
        "source": source,
        "summary": summary,
        "trigger": trigger,
        "direction": direction,
    }


def normalize_event_risks(payload: Any, *, default_date: str = "") -> list[dict]:
    rows = []
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        for key in ("event_risks", "events", "risks", "rows", "items", "results", "data"):
            if isinstance(payload.get(key), list):
                rows = payload[key]
                break
        if not rows:
            rows = [payload]
    out = [
        normalized
        for normalized in (normalize_event_risk_row(row, default_date=default_date) for row in rows)
        if normalized
    ]
    out.sort(key=lambda r: (SEVERITY_ORDER.get(r.get("severity"), 9), r.get("date") or "", r.get("title") or ""))
    return out


def validate_event_risks(rows: Any) -> list[str]:
    if not isinstance(rows, list):
        return ["event risks must be a list"]
    problems: list[str] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            problems.append(f"event_risks[{idx}] must be a dict")
            continue
        for field in ("title", "severity", "source"):
            if not isinstance(row.get(field), str) or not row.get(field, "").strip():
                problems.append(f"event_risks[{idx}].{field} must be a non-empty string")
        if row.get("severity") not in SEVERITY_ORDER:
            problems.append(f"event_risks[{idx}].severity must be one of {sorted(SEVERITY_ORDER)}")
        for field in ("channels", "tickers", "affected"):
            if field in row and not isinstance(row.get(field), list):
                problems.append(f"event_risks[{idx}].{field} must be a list")
    return problems


def event_risk_actions_read(event_risks: Any, *, max_items: int = 3) -> list[dict]:
    rows = normalize_event_risks(event_risks)
    actions: list[dict] = []
    for row in rows:
        if row.get("severity") not in PROMOTE_SEVERITIES:
            continue
        title = row["title"]
        channels = ", ".join(row.get("channels") or row.get("affected") or [])
        scope = f" ({channels})" if channels else ""
        severity = row["severity"]
        confidence = "High" if severity == "critical" else "Moderate"
        actions.append({
            "kind": "event_risk",
            "ticker": None,
            "what": f"Event risk: {title[:80]}",
            "confidence": confidence,
            "your_move": (
                f"Review exposure, hedges, and new buys before acting today: {title}{scope}. "
                "If the event changes oil/rates/vol or a held sleeve, decide whether to hold, hedge, trim, or wait."
            ),
            "gate": None,
            "source": "event_risk",
            "why": row.get("summary") or row.get("trigger") or f"{row.get('source')}: {title}",
            "time_window": "today" if severity == "critical" or row.get("horizon") == "daily" else "1-3 trading days",
            "capital_effect": "review",
            "goal_channels": ["downside_protection", "opportunity_cost", "data_quality"],
            "goal_impact": "High" if severity == "critical" else "Medium",
            "goal_score": 90 if severity == "critical" else 75,
            "action_label": "EVENT RISK",
            "why_it_moves_goal": "Fast exogenous shocks can change sizing, hedging, and opportunity cost before normal source lanes update.",
            "missing_evidence": [row.get("trigger") or "fresh price/source confirmation"],
        })
        if len(actions) >= max_items:
            break
    return actions


def active_event_watch(event_risks: Any) -> dict:
    """Return the highest-urgency supplied event risk for operator watch surfaces."""
    rows = normalize_event_risks(event_risks)
    if not rows:
        return {}
    row = rows[0]
    return {
        "active": True,
        "title": row.get("title") or "",
        "severity": row.get("severity") or "",
        "horizon": row.get("horizon") or "",
        "channels": row.get("channels") or [],
        "tickers": row.get("tickers") or [],
        "summary": row.get("summary") or "",
        "trigger": row.get("trigger") or "",
        "source": row.get("source") or "",
        "date": row.get("date") or "",
    }
