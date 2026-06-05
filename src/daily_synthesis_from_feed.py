#!/usr/bin/env python3
"""Build a conservative Daily Synthesis cache from an existing cockpit feed.

This does not fetch market data or invent a discretionary narrative. It
summarizes evidence already present in a validated cockpit feed so the dashboard
has a live top-down read while missing source lanes remain visible.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from daily_synthesis_intake import normalize_synthesis, validate_synthesis


DEFAULT_FEED = Path(__file__).resolve().parent / "latest_cockpit_feed.json"
DEFAULT_OUT = Path(__file__).resolve().parent / "daily_synthesis.json"
DEFAULT_SUMMARY = Path(__file__).resolve().parent / "daily_synthesis_intake_summary.json"


def _read_json(path: str | Path) -> Any:
    with Path(path).open(encoding="utf-8") as fh:
        return json.load(fh)


def _atomic_write_json(path: str | Path, payload: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".daily_synthesis_from_feed.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def _text(value: Any) -> str:
    return str(value).strip() if value not in (None, "", [], {}) else ""


def _lane_rows(feed: dict[str, Any]) -> list[dict[str, Any]]:
    rows = ((feed.get("lane_status") or {}).get("rows") or [])
    return [row for row in rows if isinstance(row, dict)]


def _dark_lanes(feed: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row for row in _lane_rows(feed)
        if row.get("status") == "not_checked" and row.get("key") != "synthesis"
    ]


def _prospective_lane_counts(feed: dict[str, Any]) -> tuple[int, int]:
    counts = (feed.get("lane_status") or {}).get("counts") or {}
    has_data = int(counts.get("has_data") or 0)
    dark_count = int(counts.get("not_checked") or 0)
    synthesis_dark = any(
        row.get("key") == "synthesis" and row.get("status") == "not_checked"
        for row in _lane_rows(feed)
    )
    if synthesis_dark:
        has_data += 1
        dark_count = max(0, dark_count - 1)
    return has_data, dark_count


def _top_action_line(feed: dict[str, Any]) -> str:
    actions = [row for row in feed.get("actions") or [] if isinstance(row, dict)]
    if not actions:
        return "No Today's Actions are currently promoted from the checked lanes."
    action = actions[0]
    what = _text(action.get("what")) or _text(action.get("your_move")) or "current top action"
    state = _text(action.get("action_state")) or "review"
    confidence = _text(action.get("confidence"))
    source = _text(action.get("source"))
    pieces = [f"Top action is {what} ({state.lower()}"]
    if confidence:
        pieces.append(f", {confidence.lower()} confidence")
    if source:
        pieces.append(f", source {source}")
    pieces.append(").")
    return "".join(pieces)


def _event_risk_line(feed: dict[str, Any]) -> str:
    risks = [row for row in feed.get("event_risk") or [] if isinstance(row, dict)]
    if not risks:
        return ""
    high = [row for row in risks if str(row.get("severity") or "").lower() == "high"]
    lead = high[0] if high else risks[0]
    title = _text(lead.get("title")) or "event risk"
    trigger = _text(lead.get("trigger"))
    if trigger:
        return f"Primary event-risk watch is {title}; trigger evidence: {trigger}"
    return f"Primary event-risk watch is {title}."


def _target_drift_line(feed: dict[str, Any]) -> str:
    drift = feed.get("target_drift") or {}
    if not isinstance(drift, dict):
        return ""
    line = _text(drift.get("line"))
    return line


def _fs_daily_line(feed: dict[str, Any]) -> str:
    radar = feed.get("radar") or {}
    items = []
    if isinstance(radar, list):
        items.extend(row for row in radar if isinstance(row, dict))
    elif isinstance(radar, dict):
        for bucket in ("avoid", "watch", "long", "rows", "items"):
            value = radar.get(bucket)
            if isinstance(value, list):
                items.extend(row for row in value if isinstance(row, dict))
    else:
        return ""
    fs_items = [
        row for row in items
        if "fundstrat" in str(row.get("source") or row.get("provenance") or "").lower()
        or str(row.get("ticker") or "").upper() in {"RYF", "TNX", "XOP"}
    ]
    if not fs_items:
        return ""
    labels = []
    for row in fs_items[:3]:
        ticker = _text(row.get("ticker")).upper()
        direction = _text(row.get("direction") or row.get("action") or row.get("stance"))
        if ticker and direction:
            labels.append(f"{ticker} {direction}")
        elif ticker:
            labels.append(ticker)
    if not labels:
        return ""
    return "Fundstrat Daily compact calls in radar: " + ", ".join(labels) + "."


def _dark_lane_hanging(feed: dict[str, Any]) -> list[str]:
    hanging: list[str] = []
    for row in _dark_lanes(feed):
        label = _text(row.get("label")) or _text(row.get("key")) or "Source lane"
        impact = _text(row.get("missing_impact"))
        next_step = _text(row.get("next_step"))
        detail = impact or next_step or "not checked"
        hanging.append(f"{label} is not checked: {detail}")
    return hanging


def build_synthesis_from_feed(feed: dict[str, Any], *, as_of: str | None = None) -> dict[str, Any]:
    generated = _text(feed.get("generated_at"))
    synthesis_date = as_of or generated[:10] or date.today().isoformat()
    actions = [row for row in feed.get("actions") or [] if isinstance(row, dict)]
    has_data, dark_count = _prospective_lane_counts(feed)

    state_parts = [
        f"Repo evidence read: {has_data} lane(s) have data and {dark_count} optional lane(s) are not checked.",
        _top_action_line(feed),
    ]
    event_line = _event_risk_line(feed)
    if event_line:
        state_parts.append(event_line)

    delta_parts = []
    fs_line = _fs_daily_line(feed)
    if fs_line:
        delta_parts.append(fs_line)
    drift_line = _target_drift_line(feed)
    if drift_line:
        delta_parts.append(drift_line)
    if not delta_parts:
        delta_parts.append("No additional repo-evidence delta beyond the current action stack.")

    hanging = _dark_lane_hanging(feed)
    top_move = _text((actions[0] if actions else {}).get("your_move"))
    if top_move:
        hanging.insert(0, f"Operator review still required: {top_move}")

    payload = {
        "source": "Repo Evidence Synthesis",
        "date": synthesis_date,
        "state_of_play": " ".join(part for part in state_parts if part),
        "delta": " ".join(part for part in delta_parts if part),
        "hanging": hanging[:6],
        "notes": [
            "Derived only from the existing cockpit feed.",
            "No standalone market fetch or autonomous trade recommendation was generated.",
        ],
    }
    return normalize_synthesis(payload, default_date=synthesis_date)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build Daily Synthesis from existing cockpit feed evidence")
    parser.add_argument("--feed", default=str(DEFAULT_FEED))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--date")
    args = parser.parse_args(argv)

    feed = _read_json(args.feed)
    synthesis = build_synthesis_from_feed(feed, as_of=args.date)
    problems = validate_synthesis(synthesis)
    summary = {
        "valid": not problems,
        "problems": problems,
        "source": synthesis.get("source", ""),
        "out": args.out,
        "feed": args.feed,
        "written": False,
        "hanging_count": len(synthesis.get("hanging") or []),
        "action_count": len(synthesis.get("actions") or []),
    }
    if problems:
        _atomic_write_json(args.summary, summary)
        print(json.dumps(summary, indent=2))
        return 2
    _atomic_write_json(args.out, synthesis)
    summary["written"] = True
    _atomic_write_json(args.summary, summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
