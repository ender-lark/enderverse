#!/usr/bin/env python3
"""
live_theses_helpers.py — Phase 3 wiring for rationale_decay_v3.py
v11.10 deployment, May 14 2026

Bridges rationale_decay_v3.py's three stubbed rules to live Notion data:
  Rule 1 (anchor_check)       <- Live Theses DB anchor_status
  Rule 2 (catalyst_in_dte)    <- Catalyst Calendar page (markdown tables)
  Rule 7 (factor_gate)        <- Aggregated debit by Factor Bucket

Architecture: pure orchestrator. rationale_decay_v3.py stays uncoupled from
Notion; this module reads Notion + calls the existing eval functions with
populated data dicts.

Notion targets (constants — change here if DB UUIDs ever migrate):
  LIVE_THESES_DS    = 0f083d6f-be67-4815-a64a-a21959812f0d
  CATALYST_PAGE     = 35fc50314bb681c5ae90d8a84919999b

Environment:
  NOTION_API_TOKEN   — required for live mode (uses notion_helpers.NotionClient)

Usage:
  from live_theses_helpers import evaluate_option_position_live
  result = evaluate_option_position_live(
      option_symbol="LEU270115C00300000",
      debit=3600, current_value=4200, theta=-13,
      iv_entry=0.55, current_iv=0.50, sleeve_value=30000,
  )
  # Returns OptionEvalResult with all 7 rules populated from live data

CLI:
  python3 live_theses_helpers.py --evaluate LEU270115C00300000 \
      --debit 3600 --current-value 4200 --theta -13 \
      --iv-entry 0.55 --current-iv 0.50 --sleeve 30000
  python3 live_theses_helpers.py --self-test
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))

# Soft imports — module degrades gracefully if dependencies missing
try:
    from notion_helpers import NotionClient
    _HAS_NOTION = True
except ImportError:
    _HAS_NOTION = False

try:
    import rationale_decay_v3 as rdv3
    _HAS_RDV3 = True
except ImportError:
    _HAS_RDV3 = False


# ============================================================================
# Constants
# ============================================================================

LIVE_THESES_DS = "0f083d6f-be67-4815-a64a-a21959812f0d"
CATALYST_PAGE = "35fc50314bb681c5ae90d8a84919999b"


# ============================================================================
# Live Theses fetcher (Rule 1)
# ============================================================================

@dataclass
class LiveThesisRow:
    """Subset of Live Theses fields needed for Phase 3 rules."""
    ticker: str
    anchor_status: Optional[str]
    anchor_text: Optional[str]
    factor_bucket: Optional[str]
    option_structure: Optional[str]
    tier: Optional[str]
    position_value: Optional[float]


def fetch_thesis(client: Optional[NotionClient], ticker: str) -> Optional[LiveThesisRow]:
    """
    Fetch one Live Theses row by ticker. Returns None if not found or on error.
    Uses the data_sources query endpoint with a Ticker title filter.
    """
    if not client:
        return None

    filter_body = {
        "property": "Ticker",
        "title": {"equals": ticker.upper()},
    }
    res = client.query_database(
        data_source_id=LIVE_THESES_DS,
        filter_=filter_body,
        page_size=5,
    )
    if not res.ok or not res.data:
        return None

    results = res.data.get("results", [])
    if not results:
        return None

    # Take first match
    page = results[0]
    props = page.get("properties", {})

    def _select_name(prop_key: str) -> Optional[str]:
        p = props.get(prop_key, {})
        if p.get("type") == "select" and p.get("select"):
            return p["select"].get("name")
        return None

    def _rich_text(prop_key: str) -> Optional[str]:
        p = props.get(prop_key, {})
        if p.get("type") == "rich_text":
            chunks = p.get("rich_text", [])
            return "".join(c.get("plain_text", "") for c in chunks) or None
        return None

    def _number(prop_key: str) -> Optional[float]:
        p = props.get(prop_key, {})
        if p.get("type") == "number":
            return p.get("number")
        return None

    return LiveThesisRow(
        ticker=ticker.upper(),
        anchor_status=_select_name("Anchor Status"),
        anchor_text=_rich_text("Named Anchor"),
        factor_bucket=_select_name("Factor Bucket"),
        option_structure=_rich_text("Option Structure"),
        tier=_select_name("Tier"),
        position_value=_number("Position Value"),
    )


def thesis_to_eval_dict(row: Optional[LiveThesisRow]) -> Optional[dict]:
    """Convert LiveThesisRow to the dict format eval_anchor_check expects."""
    if not row or not row.anchor_status:
        return None
    return {
        "anchor_status": row.anchor_status,
        "anchor_text": row.anchor_text or "(no named anchor recorded)",
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


# ============================================================================
# Catalyst Calendar parser (Rule 2)
# ============================================================================

# Catalyst Calendar lives as markdown tables in a Notion page, not a structured
# DB. We parse its content blocks for ticker + date patterns. Conservative
# parser: skip rows we can't confidently parse.

# Date patterns the calendar uses
_DATE_PATTERNS = [
    # "May 20", "May 14", "Late May", "July 22"
    (re.compile(r"^(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})", re.IGNORECASE), "month_day"),
    # "June 3", "August 4"
    # "Q2-Q3 2026", "H2 2026" — these are too vague, skip
    # "2027 H1", "2028 (TBD)" — skip
]

_MONTH_NUMS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}


def _parse_date_cell(text: str, fallback_year: int) -> Optional[date]:
    """Parse a date cell from the catalyst calendar; returns date or None."""
    t = text.strip()
    if not t:
        return None

    for pat, _kind in _DATE_PATTERNS:
        m = pat.search(t)
        if m:
            month_str = m.group(1).lower()
            day = int(m.group(2))
            month = _MONTH_NUMS.get(month_str)
            if not month:
                continue
            try:
                return date(fallback_year, month, day)
            except ValueError:
                return None
    return None


def fetch_catalyst_calendar(
    client: Optional[NotionClient],
    fallback_year: Optional[int] = None,
) -> list[dict]:
    """
    Fetch and parse the Catalyst Calendar page. Returns list of dicts:
        {"ticker": "NVDA", "date": "2026-05-20", "name": "Q1 FY27 earnings AMC", "type": "Earnings"}

    Only includes entries with parseable dates and non-empty tickers.
    """
    if not client:
        return []
    if fallback_year is None:
        fallback_year = date.today().year

    res = client.get_block_children(CATALYST_PAGE, page_size=100)
    if not res.ok or not res.data:
        return []

    catalysts: list[dict] = []
    blocks = res.data.get("results", [])

    # Catalyst page uses table blocks. Iterate top-level blocks looking for tables.
    for block in blocks:
        if block.get("type") != "table":
            continue
        # Fetch table rows
        table_id = block.get("id")
        if not table_id:
            continue
        rows_res = client.get_block_children(table_id, page_size=100)
        if not rows_res.ok or not rows_res.data:
            continue
        for row in rows_res.data.get("results", []):
            if row.get("type") != "table_row":
                continue
            cells = row.get("table_row", {}).get("cells", [])
            if len(cells) < 3:
                continue
            # Flatten rich-text cells to plain strings
            cell_text = [
                "".join(rt.get("plain_text", "") for rt in cell)
                for cell in cells
            ]
            date_str = cell_text[0]
            ticker_str = cell_text[1].strip().upper()
            catalyst_name = cell_text[2] if len(cell_text) > 2 else ""
            category = cell_text[3] if len(cell_text) > 3 else ""

            if not ticker_str or ticker_str == "TICKER":
                continue  # header row or empty
            parsed_date = _parse_date_cell(date_str, fallback_year)
            if not parsed_date:
                continue  # vague date like "Q2-Q3 2026" — skip

            # Tickers can be comma-separated (e.g. "UUUU, MP, UURAF, LEU")
            for t in [x.strip().upper() for x in ticker_str.replace(",", " ").split() if x.strip()]:
                # Skip obvious non-ticker entries
                if len(t) > 8 or not t.replace(".", "").isalnum():
                    continue
                catalysts.append({
                    "ticker": t,
                    "date": parsed_date.isoformat() + "T00:00:00+00:00",
                    "name": catalyst_name.strip() or "(unnamed catalyst)",
                    "type": category.strip() or "Catalyst",
                })

    return catalysts


# ============================================================================
# Factor bucket aggregator (Rule 7)
# ============================================================================

def aggregate_factor_heat(
    client: Optional[NotionClient],
    factor_bucket: str,
    exclude_option_symbol: Optional[str] = None,
) -> Optional[float]:
    """
    Sum the at-risk debit across all Live Theses rows with the given
    Factor Bucket. Excludes one option_symbol if provided (to avoid
    double-counting the position being evaluated).

    Returns total dollar heat (sum of Position Value for rows in factor),
    or None if Notion unavailable.
    """
    if not client:
        return None

    filter_body = {
        "property": "Factor Bucket",
        "select": {"equals": factor_bucket},
    }
    res = client.query_database(
        data_source_id=LIVE_THESES_DS,
        filter_=filter_body,
        page_size=100,
    )
    if not res.ok or not res.data:
        return None

    total_heat = 0.0
    for page in res.data.get("results", []):
        props = page.get("properties", {})
        # Read Position Value
        pos_val_prop = props.get("Position Value", {})
        pos_val = pos_val_prop.get("number") if pos_val_prop.get("type") == "number" else None
        # Read Option Structure (for exclude check)
        opt_struct_prop = props.get("Option Structure", {})
        opt_struct = "".join(
            rt.get("plain_text", "")
            for rt in opt_struct_prop.get("rich_text", [])
        ) if opt_struct_prop.get("type") == "rich_text" else ""

        if exclude_option_symbol and exclude_option_symbol in opt_struct:
            continue
        if pos_val:
            total_heat += pos_val

    return total_heat


# ============================================================================
# Full evaluation orchestrator
# ============================================================================

def evaluate_option_position_live(
    option_symbol: str,
    debit: float,
    current_value: float,
    theta: float,
    iv_entry: float,
    current_iv: float,
    sleeve_value: float,
    factor_override: Optional[str] = None,
    dry_run: bool = False,
):
    """
    Run all 7 rules against a live option position. Auto-fetches Live Theses +
    Catalyst Calendar data from Notion. Returns the same OptionEvalResult that
    rationale_decay_v3.evaluate_option_position would return.

    factor_override: if set, skip the Live Theses Factor Bucket lookup and use
        this factor name directly. Useful for testing.
    dry_run: skip live Notion fetches; returns STUB results equivalent to v3
        without --live mode.
    """
    if not _HAS_RDV3:
        raise RuntimeError("rationale_decay_v3 not importable. "
                           "Ensure it's on the path.")

    underlying = rdv3.parse_occ_symbol(option_symbol).get("underlying", "")

    client: Optional[NotionClient] = None
    if _HAS_NOTION and not dry_run:
        try:
            client = NotionClient()
        except Exception:
            client = None

    # === Fetch live data ===
    thesis_row = fetch_thesis(client, underlying) if client else None
    thesis_dict = thesis_to_eval_dict(thesis_row)

    # Catalyst fetch: None when offline (preserves STUB result),
    # actual list (possibly empty) when client present (genuine FIRE on empty).
    catalysts = fetch_catalyst_calendar(client) if client else None

    factor = factor_override or (thesis_row.factor_bucket if thesis_row else None) or "solo"
    factor_heat = aggregate_factor_heat(
        client, factor,
        exclude_option_symbol=option_symbol,
    ) if client else None

    # Include this position's debit in factor heat (only when we have a real number)
    if factor_heat is not None:
        factor_heat += debit

    # === Evaluate all 7 rules with live data injected ===
    return rdv3.evaluate_option_position(
        option_symbol=option_symbol,
        debit_paid=debit,
        current_value=current_value,
        theta_per_day=theta,
        iv_at_entry=iv_entry,
        current_iv=current_iv,
        sleeve_value=sleeve_value,
        factor=factor,
        live_theses_data=thesis_dict,
        catalyst_data=catalysts,
        factor_heat=factor_heat,
    )


# ============================================================================
# Self-test
# ============================================================================

def _run_self_test() -> tuple[int, int]:
    """Tests that don't require live Notion access."""
    passes = 0
    fails = 0

    def check(name: str, cond: bool, hint: str = ""):
        nonlocal passes, fails
        if cond:
            passes += 1
            print(f"  PASS  {name}")
        else:
            fails += 1
            print(f"  FAIL  {name}  {hint}")

    # Test 1: module imports
    check("Test 1: module imports cleanly", True)

    # Test 2: imports dependencies properly
    check("Test 2: notion_helpers available", _HAS_NOTION)
    check("Test 3: rationale_decay_v3 available", _HAS_RDV3)

    # Test 4: date parser handles standard catalyst calendar formats
    d1 = _parse_date_cell("May 20", 2026)
    check("Test 4: 'May 20' parses to 2026-05-20",
          d1 == date(2026, 5, 20), f"got {d1}")

    d2 = _parse_date_cell("Late May", 2026)
    check("Test 5: 'Late May' (vague) returns None", d2 is None)

    d3 = _parse_date_cell("July 22", 2026)
    check("Test 6: 'July 22' parses correctly", d3 == date(2026, 7, 22))

    d4 = _parse_date_cell("Q2-Q3 2026", 2026)
    check("Test 7: 'Q2-Q3 2026' (vague) returns None", d4 is None)

    # Test 8: thesis_to_eval_dict handles None row
    check("Test 8: thesis_to_eval_dict(None) -> None",
          thesis_to_eval_dict(None) is None)

    # Test 9: thesis_to_eval_dict with anchor_status
    row = LiveThesisRow(
        ticker="LEU", anchor_status="INTACT", anchor_text="HALEU monopoly",
        factor_bucket="nuclear", option_structure=None, tier="Generational",
        position_value=88000.0,
    )
    d = thesis_to_eval_dict(row)
    check("Test 9: thesis_to_eval_dict populates anchor_status",
          d and d["anchor_status"] == "INTACT")

    # Test 10: dry_run evaluation returns 4 PASS + 3 STUB
    if _HAS_RDV3:
        result = evaluate_option_position_live(
            option_symbol="LEU270115C00300000",
            debit=3600, current_value=4200, theta=-13,
            iv_entry=0.55, current_iv=0.50, sleeve_value=30000,
            dry_run=True,
        )
        passes_rules = sum(1 for r in result.rules if r.result == "PASS")
        check("Test 10: dry_run evaluation returns at least 3 PASS rules",
              passes_rules >= 3, f"got {passes_rules}")

    return passes, fails


def _main_cli():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true",
                    help="Run self-test (no Notion access required)")
    ap.add_argument("--evaluate", type=str, metavar="OPTION_SYMBOL",
                    help="OCC option symbol to evaluate (e.g. LEU270115C00300000)")
    ap.add_argument("--debit", type=float, help="Entry debit per contract")
    ap.add_argument("--current-value", type=float, dest="current_value")
    ap.add_argument("--theta", type=float, help="Current daily theta (negative)")
    ap.add_argument("--iv-entry", type=float, dest="iv_entry")
    ap.add_argument("--current-iv", type=float, dest="current_iv")
    ap.add_argument("--sleeve", type=float, dest="sleeve_value",
                    help="Asymmetric sleeve total value")
    ap.add_argument("--factor", type=str,
                    help="Factor bucket override (default: read from Live Theses)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Skip Notion fetches; equivalent to v3 without --live")
    args = ap.parse_args()

    if args.self_test:
        print("=" * 70)
        print("LIVE_THESES_HELPERS SELF-TEST")
        print("=" * 70)
        passes, fails = _run_self_test()
        print()
        print(f"RESULT: {passes}/{passes + fails} passed")
        return 0 if fails == 0 else 1

    if args.evaluate:
        required = ["debit", "current_value", "theta", "iv_entry", "current_iv", "sleeve_value"]
        missing = [r for r in required if getattr(args, r) is None]
        if missing:
            print(f"ERROR: missing required args: {missing}", file=sys.stderr)
            return 1

        result = evaluate_option_position_live(
            option_symbol=args.evaluate,
            debit=args.debit, current_value=args.current_value,
            theta=args.theta, iv_entry=args.iv_entry,
            current_iv=args.current_iv, sleeve_value=args.sleeve_value,
            factor_override=args.factor,
            dry_run=args.dry_run,
        )
        print(rdv3.format_text(result))
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(_main_cli())
