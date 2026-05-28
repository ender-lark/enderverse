#!/usr/bin/env python3
"""
rationale_decay.py — Live Theses auto-decay script
v11.7-rev2 W3 Notion Architecture v1

Purpose: detect stale theses in the Live Theses DB and flag/update Status fields
so the operator gets actionable surfacing at session open rather than rationales
quietly aging out.

Decay rules (per Reasoning Architecture v1):
  STALE_SOFT    — Last Two-Lens Run > 14 days ago AND Status != Validated/Watch
                  → flag for review, no Status mutation
  STALE_HARD    — Last Two-Lens Run > 21 days ago
                  → auto-set Status to "Re-review Required"
  OVERDUE       — Next Review Due < today AND Status != Re-review Required
                  → auto-set Status to "Re-review Required"
  TIER_A_HARD   — Tier=A or Generational AND Last Two-Lens Run > 7 days
                  → flag harder (more frequent review cadence for high-tier)

Usage:
  python rationale_decay.py                # report only (default)
  python rationale_decay.py --update       # write Status mutations to Notion
  python rationale_decay.py --tier A       # filter to specific tier
  python rationale_decay.py --json         # machine-readable output

Requires: NOTION_API_TOKEN env var with read+write access to Live Theses data
source 0f083d6f-be67-4815-a64a-a21959812f0d.

This is v1: operator-runnable, no scheduler, no Notion-side rollback. Future:
hook into Launcher Step 1 (session open) so stale items surface in the daily
dashboard automatically.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import requests

# ---------- Configuration ----------

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
LIVE_THESES_DATA_SOURCE_ID = "0f083d6f-be67-4815-a64a-a21959812f0d"

# Decay thresholds (days). Tunable.
STALE_SOFT_DAYS = 14
STALE_HARD_DAYS = 21
TIER_A_HARD_DAYS = 7

# Tier classifications that get the harder cadence
HIGH_TIER_LABELS = {"A", "Generational"}

# Statuses that should NOT be auto-mutated even if stale
LOCKED_STATUSES = {"Thesis-Break Watch", "Expired"}


# ---------- Data shapes ----------

@dataclass
class ThesisRow:
    page_id: str
    ticker: str
    tier: str | None
    status: str | None
    last_run: date | None
    next_review: date | None
    anchor_source: str | None
    position_pct: float | None

    @property
    def days_since_run(self) -> int | None:
        if self.last_run is None:
            return None
        return (date.today() - self.last_run).days

    @property
    def days_until_review(self) -> int | None:
        if self.next_review is None:
            return None
        return (self.next_review - date.today()).days


@dataclass
class DecayFinding:
    ticker: str
    page_id: str
    rule: str  # STALE_SOFT | STALE_HARD | OVERDUE | TIER_A_HARD
    days_stale: int | None
    current_status: str | None
    recommended_status: str | None
    needs_write: bool


# ---------- Notion client ----------

def notion_headers() -> dict[str, str]:
    token = os.environ.get("NOTION_API_TOKEN")
    if not token:
        sys.exit("ERROR: NOTION_API_TOKEN env var not set")
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def query_live_theses() -> list[dict[str, Any]]:
    """Page through the entire Live Theses data source."""
    url = f"{NOTION_API_BASE}/data_sources/{LIVE_THESES_DATA_SOURCE_ID}/query"
    headers = notion_headers()
    all_rows: list[dict[str, Any]] = []
    next_cursor: str | None = None

    while True:
        body: dict[str, Any] = {"page_size": 100}
        if next_cursor:
            body["start_cursor"] = next_cursor
        resp = requests.post(url, headers=headers, json=body, timeout=30)
        if resp.status_code != 200:
            sys.exit(f"ERROR: Notion query failed {resp.status_code}: {resp.text}")
        data = resp.json()
        all_rows.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        next_cursor = data.get("next_cursor")
    return all_rows


def update_status(page_id: str, new_status: str) -> bool:
    """Set Thesis Status select on a single page. Returns True on success."""
    url = f"{NOTION_API_BASE}/pages/{page_id}"
    headers = notion_headers()
    body = {
        "properties": {
            "Thesis Status": {"select": {"name": new_status}},
            "Last Update Trigger": {"select": {"name": "Auto-Decay"}},
        }
    }
    resp = requests.patch(url, headers=headers, json=body, timeout=30)
    if resp.status_code != 200:
        print(f"  ERROR updating {page_id}: {resp.status_code} {resp.text}",
              file=sys.stderr)
        return False
    return True


# ---------- Parsing helpers ----------

def _date_from_prop(prop: dict[str, Any] | None) -> date | None:
    if not prop:
        return None
    dval = prop.get("date")
    if not dval or not dval.get("start"):
        return None
    s = dval["start"]
    # Accept date-only or full ISO datetime
    try:
        if "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        return date.fromisoformat(s)
    except ValueError:
        return None


def _select_name(prop: dict[str, Any] | None) -> str | None:
    if not prop:
        return None
    sel = prop.get("select")
    return sel.get("name") if sel else None


def _title_text(prop: dict[str, Any] | None) -> str:
    if not prop:
        return ""
    parts = prop.get("title", [])
    return "".join(p.get("plain_text", "") for p in parts)


def _number(prop: dict[str, Any] | None) -> float | None:
    if not prop:
        return None
    return prop.get("number")


def parse_row(raw: dict[str, Any]) -> ThesisRow:
    props = raw.get("properties", {})
    return ThesisRow(
        page_id=raw["id"],
        ticker=_title_text(props.get("Ticker")),
        tier=_select_name(props.get("Tier")),
        status=_select_name(props.get("Thesis Status")),
        last_run=_date_from_prop(props.get("Last Two-Lens Run")),
        next_review=_date_from_prop(props.get("Next Review Due")),
        anchor_source=_select_name(props.get("Anchor Source")),
        position_pct=_number(props.get("Position % of Portfolio")),
    )


# ---------- Decay logic ----------

def evaluate_row(row: ThesisRow) -> list[DecayFinding]:
    findings: list[DecayFinding] = []
    days = row.days_since_run

    # No last-run data: flag as needs-initial-run
    if days is None:
        findings.append(DecayFinding(
            ticker=row.ticker, page_id=row.page_id, rule="NO_RUN_DATA",
            days_stale=None, current_status=row.status,
            recommended_status="Re-review Required",
            needs_write=row.status not in LOCKED_STATUSES,
        ))
        return findings

    # Overdue per scheduled Next Review Due
    if row.days_until_review is not None and row.days_until_review < 0:
        if row.status != "Re-review Required" and row.status not in LOCKED_STATUSES:
            findings.append(DecayFinding(
                ticker=row.ticker, page_id=row.page_id, rule="OVERDUE",
                days_stale=abs(row.days_until_review),
                current_status=row.status,
                recommended_status="Re-review Required",
                needs_write=True,
            ))

    # Tier-A / Generational hard cadence
    if row.tier in HIGH_TIER_LABELS and days >= TIER_A_HARD_DAYS:
        if days >= STALE_HARD_DAYS and row.status not in LOCKED_STATUSES:
            findings.append(DecayFinding(
                ticker=row.ticker, page_id=row.page_id, rule="TIER_A_HARD",
                days_stale=days, current_status=row.status,
                recommended_status="Re-review Required",
                needs_write=row.status != "Re-review Required",
            ))
        elif days >= TIER_A_HARD_DAYS:
            findings.append(DecayFinding(
                ticker=row.ticker, page_id=row.page_id, rule="TIER_A_HARD",
                days_stale=days, current_status=row.status,
                recommended_status=row.status,  # flag only, no mutation
                needs_write=False,
            ))
        return findings

    # General hard stale
    if days >= STALE_HARD_DAYS and row.status not in LOCKED_STATUSES:
        if row.status != "Re-review Required":
            findings.append(DecayFinding(
                ticker=row.ticker, page_id=row.page_id, rule="STALE_HARD",
                days_stale=days, current_status=row.status,
                recommended_status="Re-review Required",
                needs_write=True,
            ))
    # General soft stale
    elif days >= STALE_SOFT_DAYS:
        if row.status not in {"Validated", "Watch"} | LOCKED_STATUSES:
            findings.append(DecayFinding(
                ticker=row.ticker, page_id=row.page_id, rule="STALE_SOFT",
                days_stale=days, current_status=row.status,
                recommended_status=row.status,  # flag only
                needs_write=False,
            ))
    return findings


# ---------- Reporting ----------

def report_text(findings: list[DecayFinding], rows_total: int) -> str:
    lines = [
        f"Live Theses Decay Report — {date.today().isoformat()}",
        f"Scanned {rows_total} rows; surfaced {len(findings)} decay findings.",
        "",
    ]
    if not findings:
        lines.append("All positions current. No action required.")
        return "\n".join(lines)

    by_rule: dict[str, list[DecayFinding]] = {}
    for f in findings:
        by_rule.setdefault(f.rule, []).append(f)

    for rule in ("NO_RUN_DATA", "OVERDUE", "TIER_A_HARD", "STALE_HARD", "STALE_SOFT"):
        items = by_rule.get(rule, [])
        if not items:
            continue
        lines.append(f"[{rule}] — {len(items)} item(s)")
        for f in sorted(items, key=lambda x: -(x.days_stale or 0)):
            stale_str = f"{f.days_stale}d" if f.days_stale is not None else "no data"
            action = " → AUTO-UPDATE" if f.needs_write else " (flag only)"
            lines.append(
                f"  {f.ticker:<10} stale={stale_str:<8} "
                f"status={f.current_status or '?':<22} "
                f"rec={f.recommended_status or '?'}{action}"
            )
        lines.append("")
    return "\n".join(lines)


def report_json(findings: list[DecayFinding], rows_total: int) -> str:
    payload = {
        "scan_date": date.today().isoformat(),
        "rows_scanned": rows_total,
        "findings_count": len(findings),
        "findings": [
            {
                "ticker": f.ticker,
                "page_id": f.page_id,
                "rule": f.rule,
                "days_stale": f.days_stale,
                "current_status": f.current_status,
                "recommended_status": f.recommended_status,
                "needs_write": f.needs_write,
            }
            for f in findings
        ],
    }
    return json.dumps(payload, indent=2)


# ---------- Main ----------

def main() -> int:
    parser = argparse.ArgumentParser(description="Live Theses auto-decay scanner")
    parser.add_argument("--update", action="store_true",
                        help="Write recommended Status mutations to Notion "
                             "(default: report only)")
    parser.add_argument("--tier", default=None,
                        help="Filter to a single Tier (A/B/C/Generational/"
                             "Buy-and-Hold/Watchlist)")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON instead of text report")
    args = parser.parse_args()

    raw_rows = query_live_theses()
    rows = [parse_row(r) for r in raw_rows]

    if args.tier:
        rows = [r for r in rows if r.tier == args.tier]

    findings: list[DecayFinding] = []
    for r in rows:
        findings.extend(evaluate_row(r))

    output = report_json(findings, len(rows)) if args.json else \
        report_text(findings, len(rows))
    print(output)

    if args.update:
        writable = [f for f in findings if f.needs_write and f.recommended_status]
        if writable:
            print(f"\n--update flag set; writing {len(writable)} Status mutations...",
                  file=sys.stderr)
            n_ok = 0
            for f in writable:
                if update_status(f.page_id, f.recommended_status):
                    n_ok += 1
            print(f"Updated {n_ok}/{len(writable)} pages.", file=sys.stderr)
        else:
            print("\n--update flag set but nothing to write.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
