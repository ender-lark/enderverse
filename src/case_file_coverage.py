#!/usr/bin/env python3
"""Non-blocking thesis-of-record (.md) coverage lint.

Sibling to decision_dossier_coverage: that one audits the JSON Decision Dossier
mirror; this one audits the hand-authored docs/research_dossiers/<T>.md
thesis-of-record files that case_file.py leads with. The .md store is the single
hand-maintained input to the case file (4 of ~89 holdings today), so it is the
rot vector - this lint keeps it honest so it can't silently orphan.

Source-proof only: a missing/stale/unparsed verdict is coverage debt, never a
card blocker, alert trigger, sizing input, or trade signal. Reuses
current_action_material_tickers so it only ever flags names that are actually
current, and emits the same status/line/blocks:False/honesty_rule contract as the
JSON dossier coverage audit.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import decision_dossiers as dd
import case_file as cf
from decision_dossier_coverage import current_action_material_tickers


DEFAULT_MAX_VERDICT_AGE_DAYS = cf.VERDICT_MAX_AGE_DAYS


def _verdict_state(
    ticker: str,
    *,
    dossier_dir: Path | str | None,
    today: str | None,
    max_age: int,
) -> dict[str, Any]:
    base_dir = Path(dossier_dir) if dossier_dir else cf.DOSSIER_DIR
    path = base_dir / f"{ticker}.md"
    if not path.exists():
        return {"status": "missing", "summary": "no thesis-of-record (.md) on file"}
    parsed = cf.parse_verdict_header(path.read_text(encoding="utf-8"))
    if not parsed["date"]:
        return {"status": "unparsed", "summary": "CURRENT VERDICT header not parseable"}
    freshness = dd._freshness({"as_of": parsed["date"], "max_age_days": max_age}, dd._today(today))
    if freshness["fresh"]:
        return {"status": "covered", "summary": f"verdict dated {parsed['date']} (fresh)", "verdict_date": parsed["date"]}
    return {
        "status": "stale",
        "summary": f"verdict dated {parsed['date']} is {freshness.get('age_days')}d old",
        "verdict_date": parsed["date"],
    }


def build_case_file_coverage(
    feed: dict[str, Any],
    *,
    dossier_dir: Path | str | None = None,
    today: str | None = None,
    max_verdict_age_days: int = DEFAULT_MAX_VERDICT_AGE_DAYS,
) -> dict[str, Any]:
    """Audit thesis-of-record coverage for current action/material tickers."""
    targets = current_action_material_tickers(feed)
    rows: list[dict[str, Any]] = []
    for target in targets:
        state = _verdict_state(
            target["ticker"], dossier_dir=dossier_dir, today=today, max_age=max_verdict_age_days
        )
        rows.append({**target, **state})

    missing = [r for r in rows if r["status"] == "missing"]
    unparsed = [r for r in rows if r["status"] == "unparsed"]
    stale = [r for r in rows if r["status"] == "stale"]
    covered = [r for r in rows if r["status"] == "covered"]

    if not rows:
        status = "covered"
        line = "Thesis-of-record coverage: no current action/material ticker(s) to audit."
    else:
        status = "missing" if missing else "needs_review" if (stale or unparsed) else "covered"
        bits = [
            f"{len(covered)}/{len(rows)} current action/material ticker(s) have a fresh thesis-of-record",
            f"missing={len(missing)}",
            f"stale={len(stale)}",
            f"unparsed={len(unparsed)}",
        ]
        if missing:
            bits.append("missing " + ", ".join(r["ticker"] for r in missing[:8]))
        line = "Thesis-of-record coverage: " + "; ".join(bits) + "."

    return {
        "status": status,
        "line": line,
        "total_count": len(rows),
        "covered_count": len(covered),
        "missing_count": len(missing),
        "stale_count": len(stale),
        "unparsed_count": len(unparsed),
        "rows": rows,
        "blocks": False,
        "alert_eligible": False,
        "honesty_rule": (
            "Coverage debt only; a missing/stale thesis-of-record does not block cards, "
            "generate alerts, or imply a trade/no-trade decision."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit thesis-of-record (.md) coverage for a cockpit feed.")
    parser.add_argument("--feed", required=True)
    parser.add_argument("--today")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    args = parser.parse_args(argv)

    feed = json.loads(Path(args.feed).read_text(encoding="utf-8-sig"))
    audit = build_case_file_coverage(feed, today=args.today)
    if args.format == "json":
        print(json.dumps(audit, indent=2))
    else:
        print(audit["line"])
        for row in audit.get("rows") or []:
            print(f"- {row['ticker']}: {row['status']} ({row.get('summary', '')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
