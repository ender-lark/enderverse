#!/usr/bin/env python3
"""
13f_quarterly_pull.py — v11.11 Patch 5 implementation
Shipped: May 14, 2026 late PM

Quarterly driver to pull institutional 13F holdings via UW
`get_institution_holdings` for every ticker in fs_holdings.json held list,
classify deltas vs prior quarter, and write Tier-1/2/3/CLUSTER entries to
📊 13F Deltas DB.

Materiality thresholds (per CI v11.12):
    TIER 1: single named whale delta >$100M absolute notional change
    TIER 2: single named whale delta >20% of prior reported position
    TIER 3: single named whale delta >5% of ticker market cap
    CLUSTER: 3+ institutions moving same direction in same quarter

Architecture (mirrors live_theses_helpers.py pattern):
    - Pure-logic core `classify_13f_delta()` — testable without Notion/UW
    - Schedule logic `should_run_today()` — calendar guard for 5-trading-day
      window after each filing deadline (Feb 15 / May 15 / Aug 15 / Nov 15)
    - Live integration `pull_and_classify_for_ticker()` — caller provides
      UW data; this module classifies and writes records
    - CLI: --self-test (no live deps), --dry-run, --run

Notion targets:
    DELTAS_13F_DS = 4c61f105-8229-476e-941b-26d8af3cae9a

13F Deltas DB schema (write-side):
    - Ticker (title)
    - Filing Period (select: "Q1 2026", "Q2 2026", ...)
    - Named Whale (rich_text)
    - Share Delta (number, signed)
    - Position Value Delta (number, signed dollars)
    - Direction (select: ACCUMULATION / DISTRIBUTION / NEW POSITION / EXIT)
    - Materiality Tier (select: TIER 1 / TIER 2 / TIER 3 / CLUSTER)
    - Filed Date (date)
    - Notes (rich_text)
    - Source (select: "UW get_institution_holdings")
    - Linked Thesis (rich_text — ticker for cross-link)
    - Status (select: New / Reviewed / Acted Upon / Watchlist) — default "New"

UW input shape (per-ticker, passed in by caller):
    {
        "ticker": "NVDA",
        "market_cap": 3_500_000_000_000,
        "filing_period": "Q1 2026",
        "filed_date": "2026-05-15",
        "holdings": [
            {
                "institution": "Blackrock Inc",
                "current_value": 250_000_000_000,
                "prior_value": 245_000_000_000,
                "current_shares": 1_100_000_000,
                "prior_shares": 1_080_000_000,
            },
            ...
        ],
    }

Usage:
    # Pure-logic
    from importlib import import_module
    mod = import_module("13f_quarterly_pull")
    cls = mod.classify_13f_delta(
        institution="Citadel", current_value=180_000_000, prior_value=50_000_000,
        current_shares=1_000_000, prior_shares=300_000, market_cap=3.5e12,
    )
    # cls.tier == "TIER 1" (>$100M absolute notional change)

    # Schedule check
    mod.should_run_today(date(2026, 5, 22))
    # -> (True, "within 5 trading days of 2026-05-15 deadline")

    # Dry-run (no Notion writes)
    python3 13f_quarterly_pull.py --dry-run --data /tmp/uw_pulls.json

CLI:
    python3 13f_quarterly_pull.py --self-test
    python3 13f_quarterly_pull.py --check-schedule
    python3 13f_quarterly_pull.py --dry-run --data path/to/pulls.json
    python3 13f_quarterly_pull.py --run --data path/to/pulls.json  # live writes
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))

try:
    from notion_helpers import NotionClient
    _HAS_NOTION = True
except ImportError:
    _HAS_NOTION = False


# ============================================================================
# Constants
# ============================================================================

DELTAS_13F_DS = "4c61f105-8229-476e-941b-26d8af3cae9a"

# 13F filing deadlines: 45 days after each calendar-quarter end
# Q4 end Dec 31 → Feb 15; Q1 → May 15; Q2 → Aug 15; Q3 → Nov 15
FILING_DEADLINES = (  # (month, day)
    (2, 15), (5, 15), (8, 15), (11, 15),
)

TIER1_NOTIONAL_THRESHOLD = 100_000_000     # $100M
TIER2_PCT_OF_PRIOR_THRESHOLD = 0.20         # 20%
TIER3_PCT_OF_MKT_CAP_THRESHOLD = 0.05       # 5%
CLUSTER_MIN_INSTITUTIONS = 3                # 3+ same direction


# ============================================================================
# Pure-logic core
# ============================================================================

@dataclass
class DeltaClassification:
    """Classification result for one institution-ticker delta."""
    institution: str
    ticker: str
    filing_period: str
    share_delta: int
    value_delta: float        # signed dollars
    pct_of_prior: float        # signed; 0 when prior was 0 and there's a new pos
    pct_of_mkt_cap: float      # absolute share of mkt cap (always >= 0)
    direction: str             # ACCUMULATION / DISTRIBUTION / NEW POSITION / EXIT
    tier: Optional[str]        # TIER 1 / TIER 2 / TIER 3 / None (not material)
    surface_notes: str
    is_material: bool


def classify_13f_delta(
    institution: str,
    current_value: float,
    prior_value: float,
    current_shares: int,
    prior_shares: int,
    market_cap: float,
    ticker: str = "",
    filing_period: str = "",
) -> DeltaClassification:
    """
    Pure-logic delta classifier. No I/O.

    Direction logic:
        - prior 0, current > 0 → NEW POSITION
        - prior > 0, current 0 → EXIT
        - current > prior → ACCUMULATION
        - current < prior → DISTRIBUTION
        - else → no-change (returned as ACCUMULATION with 0 delta for shape)

    Tier logic (worst-case-wins; first to apply):
        - TIER 1: abs(value_delta) > TIER1_NOTIONAL_THRESHOLD
        - TIER 2: abs(pct_of_prior) > TIER2_PCT_OF_PRIOR_THRESHOLD
                  AND prior_value > 0   (NEW POSITION fits TIER 1 path, not 2)
        - TIER 3: abs(value_delta) / market_cap > TIER3_PCT_OF_MKT_CAP_THRESHOLD
                  AND market_cap > 0
        - else None (not material)
    """
    share_delta = current_shares - prior_shares
    value_delta = current_value - prior_value

    if prior_shares == 0 and current_shares > 0:
        direction = "NEW POSITION"
    elif prior_shares > 0 and current_shares == 0:
        direction = "EXIT"
    elif current_shares > prior_shares:
        direction = "ACCUMULATION"
    elif current_shares < prior_shares:
        direction = "DISTRIBUTION"
    else:
        direction = "ACCUMULATION"  # no-change; share_delta == 0

    pct_of_prior = (value_delta / prior_value) if prior_value > 0 else 0.0
    pct_of_mkt_cap = (abs(value_delta) / market_cap) if market_cap > 0 else 0.0

    tier: Optional[str] = None
    if abs(value_delta) > TIER1_NOTIONAL_THRESHOLD:
        tier = "TIER 1"
    elif prior_value > 0 and abs(pct_of_prior) > TIER2_PCT_OF_PRIOR_THRESHOLD:
        tier = "TIER 2"
    elif market_cap > 0 and pct_of_mkt_cap > TIER3_PCT_OF_MKT_CAP_THRESHOLD:
        tier = "TIER 3"

    is_material = tier is not None

    notes_parts = [
        f"{direction}: ${value_delta:,.0f} ({share_delta:+,d} shares)",
    ]
    if prior_value > 0:
        notes_parts.append(f"{pct_of_prior * 100:+.1f}% of prior")
    if market_cap > 0:
        notes_parts.append(f"{pct_of_mkt_cap * 100:.3f}% of mkt cap")
    surface_notes = " · ".join(notes_parts)

    return DeltaClassification(
        institution=institution.strip(),
        ticker=ticker.upper().strip(),
        filing_period=filing_period,
        share_delta=share_delta,
        value_delta=value_delta,
        pct_of_prior=pct_of_prior,
        pct_of_mkt_cap=pct_of_mkt_cap,
        direction=direction,
        tier=tier,
        surface_notes=surface_notes,
        is_material=is_material,
    )


def classify_ticker_payload(payload: dict) -> tuple[list[DeltaClassification],
                                                     Optional[str]]:
    """
    Take a per-ticker UW payload (shape in module docstring), classify all
    holdings, and additionally detect CLUSTER (3+ institutions moving same
    direction within this filing period).

    Returns (list of individual classifications, optional CLUSTER summary note).
    The CLUSTER summary is meant to be written as a separate Notion row with
    Materiality Tier = "CLUSTER".
    """
    ticker = payload.get("ticker", "").upper()
    filing_period = payload.get("filing_period", "")
    market_cap = float(payload.get("market_cap") or 0)

    classifications: list[DeltaClassification] = []
    accumulators = 0
    distributors = 0

    for h in payload.get("holdings", []) or []:
        inst = (h.get("institution") or "").strip()
        if not inst:
            continue
        try:
            cv = float(h.get("current_value") or 0)
            pv = float(h.get("prior_value") or 0)
            cs = int(h.get("current_shares") or 0)
            ps = int(h.get("prior_shares") or 0)
        except (TypeError, ValueError):
            continue

        c = classify_13f_delta(
            institution=inst,
            current_value=cv, prior_value=pv,
            current_shares=cs, prior_shares=ps,
            market_cap=market_cap, ticker=ticker,
            filing_period=filing_period,
        )
        classifications.append(c)
        # Cluster direction counting (only meaningful moves)
        if c.share_delta > 0:
            accumulators += 1
        elif c.share_delta < 0:
            distributors += 1

    cluster_note: Optional[str] = None
    if accumulators >= CLUSTER_MIN_INSTITUTIONS:
        cluster_note = (
            f"CLUSTER: {accumulators} institutions accumulating "
            f"{ticker} in {filing_period}"
        )
    elif distributors >= CLUSTER_MIN_INSTITUTIONS:
        cluster_note = (
            f"CLUSTER: {distributors} institutions distributing "
            f"{ticker} in {filing_period}"
        )

    return classifications, cluster_note


# ============================================================================
# Schedule logic
# ============================================================================

def should_run_today(today: Optional[date] = None,
                     trading_day_window: int = 5) -> tuple[bool, str]:
    """
    Return (should_run, reason) — True iff `today` is within
    `trading_day_window` *calendar* days of any 13F filing deadline.

    We approximate trading-day window with calendar window (max ~7 cal days for
    5 trading days). This is intentionally conservative — caller checks
    duplicates against Notion to avoid double-writes.

    Args:
        today: date (defaults to UTC today)
        trading_day_window: how many trading days post-deadline to keep firing
    """
    today = today or datetime.now(timezone.utc).date()
    # Calendar window ≈ trading_day_window * 1.4, rounded up
    cal_window = max(int(trading_day_window * 1.4) + 1, trading_day_window + 2)
    for mo, day in FILING_DEADLINES:
        deadline = date(today.year, mo, day)
        delta_days = (today - deadline).days
        if 0 <= delta_days <= cal_window:
            return True, (
                f"within {delta_days} calendar days of "
                f"{deadline.isoformat()} 13F filing deadline"
            )
    return False, "not within any 13F filing window"


def filing_period_for_deadline(deadline: date) -> str:
    """Map a deadline date to the period it reports on."""
    # Feb 15 reports Q4 prior year; May 15 reports Q1 same year;
    # Aug 15 reports Q2 same year; Nov 15 reports Q3 same year.
    mo = deadline.month
    if mo == 2:
        return f"Q4 {deadline.year - 1}"
    elif mo == 5:
        return f"Q1 {deadline.year}"
    elif mo == 8:
        return f"Q2 {deadline.year}"
    elif mo == 11:
        return f"Q3 {deadline.year}"
    return ""


# ============================================================================
# Notion writer
# ============================================================================

def build_notion_properties(c: DeltaClassification,
                             ticker_link: Optional[str] = None) -> dict:
    """Map a DeltaClassification to Notion properties dict for create_page."""
    props = {
        "Ticker": {"title": [{"text": {"content": c.ticker}}]},
        "Named Whale": {
            "rich_text": [{"text": {"content": c.institution[:1900]}}]},
        "Share Delta": {"number": int(c.share_delta)},
        "Position Value Delta": {"number": float(c.value_delta)},
        "Direction": {"select": {"name": c.direction}},
        "Source": {"select": {"name": "UW get_institution_holdings"}},
        "Notes": {
            "rich_text": [{"text": {"content": c.surface_notes[:1900]}}]},
        "Status": {"select": {"name": "New"}},
    }
    if c.filing_period:
        props["Filing Period"] = {"select": {"name": c.filing_period}}
    if c.tier:
        props["Materiality Tier"] = {"select": {"name": c.tier}}
    if ticker_link:
        props["Linked Thesis"] = {
            "rich_text": [{"text": {"content": ticker_link}}]}
    return props


def build_cluster_properties(ticker: str, filing_period: str,
                              cluster_note: str,
                              filed_date: Optional[str] = None) -> dict:
    """Map a CLUSTER summary to Notion properties dict."""
    props = {
        "Ticker": {"title": [{"text": {"content": ticker.upper()}}]},
        "Named Whale": {"rich_text": [{"text": {"content": "(cluster)"}}]},
        "Direction": {"select": {
            "name": "ACCUMULATION" if "accumulating" in cluster_note
            else "DISTRIBUTION"
        }},
        "Materiality Tier": {"select": {"name": "CLUSTER"}},
        "Source": {"select": {"name": "UW get_institution_holdings"}},
        "Notes": {"rich_text": [{"text": {"content": cluster_note[:1900]}}]},
        "Linked Thesis": {"rich_text": [{"text": {"content": ticker.upper()}}]},
        "Status": {"select": {"name": "New"}},
    }
    if filing_period:
        props["Filing Period"] = {"select": {"name": filing_period}}
    return props


def existing_rows_for_period(
    client: NotionClient,
    ticker: str,
    filing_period: str,
) -> set[str]:
    """
    Query 📊 13F Deltas DB for existing rows matching (ticker, filing_period).
    Returns set of normalized whale-name strings already present, for dedup.

    Used by write_classifications to skip duplicate inserts on cron re-runs.
    Names are lowercased and whitespace-stripped for matching.
    """
    if not filing_period:
        return set()

    filter_body = {
        "and": [
            {"property": "Ticker", "title": {"equals": ticker.upper()}},
            {"property": "Filing Period",
             "select": {"equals": filing_period}},
        ],
    }
    seen: set[str] = set()
    cursor = None
    while True:
        res = client.query_database(
            data_source_id=DELTAS_13F_DS,
            filter_=filter_body,
            page_size=100,
            start_cursor=cursor,
        )
        if not res.ok or not res.data:
            break
        for page in res.data.get("results", []):
            props = page.get("properties", {})
            nw = props.get("Named Whale", {})
            if nw.get("type") == "rich_text":
                chunks = nw.get("rich_text", [])
                name = "".join(c.get("plain_text", "") for c in chunks)
                if name:
                    seen.add(name.lower().strip())
        if res.data.get("has_more"):
            cursor = res.data.get("next_cursor")
        else:
            break
    return seen


def write_classifications(
    client: NotionClient,
    classifications: list[DeltaClassification],
    cluster_note: Optional[str],
    ticker: str,
    filing_period: str,
    filed_date: Optional[str] = None,
    dry_run: bool = False,
    skip_duplicates: bool = True,
) -> dict:
    """
    Write material classifications + optional cluster row to 📊 13F Deltas DB.
    Skips non-material classifications by default (caller can override by
    pre-filtering).

    Dedup: when skip_duplicates=True, pre-queries the DB for existing
    (ticker, filing_period) rows and skips any whose Named Whale already
    appears. The CLUSTER row is also deduped (matched against the literal
    string "(cluster)").

    Returns: dict with counts (written, skipped, errors, duplicates).
    """
    parent = {"data_source_id": DELTAS_13F_DS}
    written = 0
    skipped = 0
    duplicates = 0
    errors: list[str] = []

    # Pre-fetch existing whales for dedup (live mode only)
    existing: set[str] = set()
    if skip_duplicates and not dry_run:
        try:
            existing = existing_rows_for_period(client, ticker, filing_period)
        except Exception as e:
            errors.append(f"dedup query failed: {e}")
            # Continue without dedup rather than fail the whole write

    for c in classifications:
        if not c.is_material:
            skipped += 1
            continue
        whale_key = c.institution.lower().strip()
        if skip_duplicates and whale_key in existing:
            duplicates += 1
            continue
        if dry_run:
            written += 1
            existing.add(whale_key)  # treat as written for dry-run dedup
            continue
        props = build_notion_properties(c, ticker_link=ticker.upper())
        res = client.create_page(parent=parent, properties=props)
        if not res.ok:
            errors.append(f"{c.institution} {c.tier}: {res.error}")
        else:
            written += 1
            existing.add(whale_key)

    if cluster_note:
        cluster_key = "(cluster)"
        if skip_duplicates and cluster_key in existing:
            duplicates += 1
        else:
            if dry_run:
                written += 1
            else:
                props = build_cluster_properties(
                    ticker, filing_period, cluster_note, filed_date)
                res = client.create_page(parent=parent, properties=props)
                if not res.ok:
                    errors.append(f"CLUSTER {ticker}: {res.error}")
                else:
                    written += 1

    return {
        "ticker": ticker, "filing_period": filing_period,
        "written": written, "skipped": skipped,
        "duplicates": duplicates,
        "errors": errors,
    }


def pull_and_classify_for_ticker(
    client: NotionClient,
    payload: dict,
    dry_run: bool = False,
    skip_duplicates: bool = True,
) -> dict:
    """
    Top-level per-ticker driver. Caller passes the UW payload; this function
    classifies + writes to Notion (or simulates if dry_run).

    skip_duplicates=True (default) pre-queries existing rows for
    (ticker, filing_period) and skips inserts for whales already recorded.
    Set False to force-write (rare; useful only after manual cleanup).
    """
    ticker = payload.get("ticker", "").upper()
    filing_period = payload.get("filing_period", "")
    filed_date = payload.get("filed_date")

    classifications, cluster_note = classify_ticker_payload(payload)
    summary = write_classifications(
        client=client,
        classifications=classifications,
        cluster_note=cluster_note,
        ticker=ticker, filing_period=filing_period,
        filed_date=filed_date, dry_run=dry_run,
        skip_duplicates=skip_duplicates,
    )
    summary["total_holdings_classified"] = len(classifications)
    summary["cluster_detected"] = cluster_note is not None
    return summary


# ============================================================================
# Self-test
# ============================================================================

def _self_test() -> int:
    failed = 0
    passed = 0

    def check(name, cond):
        nonlocal failed, passed
        if cond:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {name}", file=sys.stderr)

    # Test 1: TIER 1 by absolute notional
    c = classify_13f_delta(
        institution="Blackrock", current_value=350_000_000,
        prior_value=200_000_000, current_shares=1_500_000,
        prior_shares=850_000, market_cap=3_500_000_000_000,
        ticker="NVDA", filing_period="Q1 2026",
    )
    check("TIER 1 fires on $150M notional change", c.tier == "TIER 1")
    check("direction ACCUMULATION", c.direction == "ACCUMULATION")
    check("share_delta positive", c.share_delta == 650_000)

    # Test 2: TIER 2 by % of prior
    c = classify_13f_delta(
        institution="Citadel", current_value=80_000_000,
        prior_value=50_000_000, current_shares=1_000_000,
        prior_shares=500_000, market_cap=200_000_000_000,
    )
    check("TIER 2 fires on 60% increase, $30M notional",
          c.tier == "TIER 2")
    check("pct_of_prior ~ 0.6", abs(c.pct_of_prior - 0.6) < 0.001)

    # Test 3: TIER 3 by % of mkt cap (small cap)
    c = classify_13f_delta(
        institution="Ark", current_value=50_000_000,
        prior_value=30_000_000, current_shares=1_000_000,
        prior_shares=500_000, market_cap=300_000_000,  # $300M cap
    )
    # $20M / $300M = 6.7% > 5% threshold; also 67% of prior so TIER 2 fires first
    # but our worst-tier-wins logic is sequential: TIER 1 ($20M < $100M) no,
    # TIER 2 (67% > 20%) yes
    check("TIER 2 wins over TIER 3 when both apply (sequential check)",
          c.tier == "TIER 2")

    # Test 3b: TIER 3 fires when TIER 1/2 do not
    c = classify_13f_delta(
        institution="Tiger Global", current_value=50_000_000,
        prior_value=45_000_000, current_shares=1_000_000,
        prior_shares=900_000, market_cap=80_000_000,  # $80M cap
    )
    # $5M delta / $80M cap = 6.25% > 5%; pct_of_prior ~11% < 20%
    check("TIER 3 fires when TIER 2 does not", c.tier == "TIER 3")

    # Test 4: NEW POSITION direction
    c = classify_13f_delta(
        institution="Anchorage", current_value=120_000_000, prior_value=0,
        current_shares=600_000, prior_shares=0,
        market_cap=200_000_000_000,
    )
    check("NEW POSITION direction", c.direction == "NEW POSITION")
    check("TIER 1 fires on >$100M new", c.tier == "TIER 1")
    check("pct_of_prior is 0 when prior was 0", c.pct_of_prior == 0.0)

    # Test 5: EXIT direction
    c = classify_13f_delta(
        institution="Bridgewater", current_value=0, prior_value=140_000_000,
        current_shares=0, prior_shares=700_000,
        market_cap=200_000_000_000,
    )
    check("EXIT direction", c.direction == "EXIT")
    check("TIER 1 fires on full exit > $100M", c.tier == "TIER 1")
    check("share_delta negative", c.share_delta == -700_000)

    # Test 6: non-material (small change)
    c = classify_13f_delta(
        institution="Generic", current_value=10_000_000, prior_value=9_500_000,
        current_shares=50_000, prior_shares=47_500,
        market_cap=200_000_000_000,
    )
    check("non-material returns tier None", c.tier is None)
    check("non-material is_material False", c.is_material is False)

    # Test 7: zero-change
    c = classify_13f_delta(
        institution="Static", current_value=10_000_000, prior_value=10_000_000,
        current_shares=50_000, prior_shares=50_000,
        market_cap=200_000_000_000,
    )
    check("zero-change has share_delta 0", c.share_delta == 0)
    check("zero-change is_material False", c.is_material is False)

    # Test 8: surface_notes content
    c = classify_13f_delta(
        institution="Pershing", current_value=250_000_000,
        prior_value=100_000_000, current_shares=1_000_000,
        prior_shares=400_000, market_cap=500_000_000_000,
    )
    check("surface includes value delta",
          "$150,000,000" in c.surface_notes
          or "150,000,000" in c.surface_notes)
    check("surface includes share delta", "+600,000" in c.surface_notes)
    check("surface includes pct of mkt cap",
          "% of mkt cap" in c.surface_notes)

    # Test 9: CLUSTER detection — 3+ accumulators
    payload = {
        "ticker": "ASTS", "filing_period": "Q1 2026",
        "market_cap": 15_000_000_000,
        "holdings": [
            {"institution": "BlackRock", "current_value": 200_000_000,
             "prior_value": 50_000_000, "current_shares": 2_500_000,
             "prior_shares": 600_000},
            {"institution": "Vanguard", "current_value": 90_000_000,
             "prior_value": 70_000_000, "current_shares": 1_100_000,
             "prior_shares": 800_000},
            {"institution": "Fidelity", "current_value": 60_000_000,
             "prior_value": 40_000_000, "current_shares": 750_000,
             "prior_shares": 500_000},
            {"institution": "TwoSigma", "current_value": 30_000_000,
             "prior_value": 35_000_000, "current_shares": 350_000,
             "prior_shares": 400_000},  # one distributor
        ],
    }
    cls, cluster = classify_ticker_payload(payload)
    check("4 classifications produced", len(cls) == 4)
    check("CLUSTER detected on 3 accumulators",
          cluster is not None and "3 institutions accumulating ASTS" in cluster)

    # Test 10: no CLUSTER when below 3 same-direction
    payload["holdings"] = payload["holdings"][:2]
    cls, cluster = classify_ticker_payload(payload)
    check("no CLUSTER with 2 accumulators", cluster is None)

    # Test 11: CLUSTER detection — 3+ distributors
    payload = {
        "ticker": "X", "filing_period": "Q1 2026",
        "market_cap": 10_000_000_000,
        "holdings": [
            {"institution": "A", "current_value": 30_000_000,
             "prior_value": 80_000_000, "current_shares": 300_000,
             "prior_shares": 800_000},
            {"institution": "B", "current_value": 10_000_000,
             "prior_value": 50_000_000, "current_shares": 100_000,
             "prior_shares": 500_000},
            {"institution": "C", "current_value": 0,
             "prior_value": 25_000_000, "current_shares": 0,
             "prior_shares": 250_000},
        ],
    }
    _, cluster = classify_ticker_payload(payload)
    check("CLUSTER detected on 3 distributors",
          cluster is not None and "distributing X" in cluster)

    # Test 12: should_run_today — within window
    ok, why = should_run_today(date(2026, 5, 22))  # 7 days after May 15
    check("May 22 within window", ok is True)
    check("reason mentions May 15", "2026-05-15" in why)

    # Test 13: should_run_today — exact deadline day
    ok, why = should_run_today(date(2026, 5, 15))
    check("May 15 (deadline day) within window", ok is True)

    # Test 14: should_run_today — far outside any window
    ok, why = should_run_today(date(2026, 3, 1))
    check("March 1 outside any window", ok is False)

    # Test 15: should_run_today — Aug 15 deadline window
    ok, _ = should_run_today(date(2026, 8, 20))
    check("Aug 20 within Aug 15 window", ok is True)

    # Test 16: filing_period_for_deadline mapping
    check("Feb 15 2026 -> Q4 2025",
          filing_period_for_deadline(date(2026, 2, 15)) == "Q4 2025")
    check("May 15 2026 -> Q1 2026",
          filing_period_for_deadline(date(2026, 5, 15)) == "Q1 2026")
    check("Aug 15 2026 -> Q2 2026",
          filing_period_for_deadline(date(2026, 8, 15)) == "Q2 2026")
    check("Nov 15 2026 -> Q3 2026",
          filing_period_for_deadline(date(2026, 11, 15)) == "Q3 2026")

    # Test 17: build_notion_properties shape
    c = classify_13f_delta(
        institution="Test Whale", current_value=150_000_000,
        prior_value=0, current_shares=750_000, prior_shares=0,
        market_cap=50_000_000_000, ticker="NVDA",
        filing_period="Q1 2026",
    )
    props = build_notion_properties(c, ticker_link="NVDA")
    check("props has Ticker title",
          props["Ticker"]["title"][0]["text"]["content"] == "NVDA")
    check("props has Named Whale",
          props["Named Whale"]["rich_text"][0]["text"]["content"]
          == "Test Whale")
    check("props has Direction NEW POSITION",
          props["Direction"]["select"]["name"] == "NEW POSITION")
    check("props has Tier", props["Materiality Tier"]["select"]["name"]
          == "TIER 1")
    check("props has Status New", props["Status"]["select"]["name"] == "New")
    check("props has Linked Thesis",
          props["Linked Thesis"]["rich_text"][0]["text"]["content"] == "NVDA")

    # Test 18: build_cluster_properties shape
    props = build_cluster_properties(
        "ASTS", "Q1 2026",
        "CLUSTER: 4 institutions accumulating ASTS in Q1 2026",
    )
    check("cluster props tier CLUSTER",
          props["Materiality Tier"]["select"]["name"] == "CLUSTER")
    check("cluster direction ACCUMULATION",
          props["Direction"]["select"]["name"] == "ACCUMULATION")
    check("cluster named whale is (cluster)",
          props["Named Whale"]["rich_text"][0]["text"]["content"] == "(cluster)")

    # Test 19: write_classifications dry-run integration
    class _FakeClient:
        def __init__(self):
            self.calls = []

        def create_page(self, parent, properties, children=None):
            from notion_helpers import NotionResult
            self.calls.append({"parent": parent, "properties": properties})
            return NotionResult(ok=True, status=200,
                                 data={"id": f"pg-{len(self.calls)}"},
                                 error=None)

    fake = _FakeClient()
    payload = {
        "ticker": "LEU", "filing_period": "Q1 2026",
        "market_cap": 8_000_000_000,
        "holdings": [
            {"institution": "Pershing Square",
             "current_value": 200_000_000, "prior_value": 50_000_000,
             "current_shares": 1_000_000, "prior_shares": 250_000},
            {"institution": "Small Fund",
             "current_value": 5_000_000, "prior_value": 4_800_000,
             "current_shares": 25_000, "prior_shares": 24_000},
        ],
    }
    res = pull_and_classify_for_ticker(fake, payload, dry_run=True)
    check("dry-run: total_holdings_classified == 2",
          res["total_holdings_classified"] == 2)
    check("dry-run: 1 material written",
          res["written"] == 1)
    check("dry-run: 1 non-material skipped",
          res["skipped"] == 1)
    check("dry-run: no Notion calls made",
          len(fake.calls) == 0)

    # Test 20: write_classifications live-mode integration (fake)
    fake = _FakeClient()
    res = pull_and_classify_for_ticker(fake, payload, dry_run=False,
                                        skip_duplicates=False)
    check("live: 1 Notion call for material classification",
          len(fake.calls) == 1)
    check("live: written count == 1", res["written"] == 1)
    check("live: ticker NVDA -> properties Ticker correct",
          fake.calls[0]["properties"]["Ticker"]["title"][0]["text"]
          ["content"] == "LEU")

    # Test 21: ticker upper-casing
    payload2 = {**payload, "ticker": "leu", "holdings": payload["holdings"][:1]}
    res = pull_and_classify_for_ticker(_FakeClient(), payload2, dry_run=True)
    check("ticker upper-cased in summary", res["ticker"] == "LEU")

    # Test 22: cluster path triggers extra write
    fake = _FakeClient()
    payload3 = {
        "ticker": "ASTS", "filing_period": "Q1 2026",
        "market_cap": 15_000_000_000,
        "holdings": [
            {"institution": f"Whale{i}",
             "current_value": 50_000_000, "prior_value": 30_000_000,
             "current_shares": 500_000, "prior_shares": 300_000}
            for i in range(4)
        ],
    }
    res = pull_and_classify_for_ticker(fake, payload3, dry_run=False,
                                        skip_duplicates=False)
    check("cluster: 4 material classifications + 1 cluster row",
          len(fake.calls) == 5)
    cluster_row = [c for c in fake.calls if c["properties"]
                   .get("Materiality Tier", {})
                   .get("select", {}).get("name") == "CLUSTER"]
    check("cluster row written", len(cluster_row) == 1)

    # Test 23: duplicate detection — existing rows skipped
    class _DedupClient:
        """Returns 2 existing rows when queried; tracks create_page calls."""

        def __init__(self):
            self.create_calls = []
            self.query_calls = []

        def query_database(self, **kwargs):
            from notion_helpers import NotionResult
            self.query_calls.append(kwargs)
            return NotionResult(ok=True, status=200, data={
                "results": [
                    {"properties": {"Named Whale": {
                        "type": "rich_text",
                        "rich_text": [{"plain_text": "Whale0"}],
                    }}},
                    {"properties": {"Named Whale": {
                        "type": "rich_text",
                        "rich_text": [{"plain_text": "Whale1"}],
                    }}},
                ],
                "has_more": False,
            }, error=None)

        def create_page(self, parent, properties, children=None):
            from notion_helpers import NotionResult
            self.create_calls.append({"parent": parent, "properties": properties})
            return NotionResult(ok=True, status=200,
                                 data={"id": f"pg-{len(self.create_calls)}"},
                                 error=None)

    dedup_client = _DedupClient()
    res = pull_and_classify_for_ticker(dedup_client, payload3, dry_run=False,
                                        skip_duplicates=True)
    check("dedup: query_database called once for pre-fetch",
          len(dedup_client.query_calls) == 1)
    check("dedup: 2 whales already in DB skipped as duplicates",
          res["duplicates"] == 2)
    # Whale0 + Whale1 in DB → skipped; Whale2 + Whale3 written; +1 cluster row
    check("dedup: 3 actual writes (2 new whales + cluster)",
          len(dedup_client.create_calls) == 3)
    check("dedup: cluster still written (different key)",
          any(c["properties"].get("Materiality Tier", {})
              .get("select", {}).get("name") == "CLUSTER"
              for c in dedup_client.create_calls))

    # Test 24: skip_duplicates=False forces all writes
    dedup_client2 = _DedupClient()
    res = pull_and_classify_for_ticker(dedup_client2, payload3, dry_run=False,
                                        skip_duplicates=False)
    check("skip_duplicates=False: no dedup query made",
          len(dedup_client2.query_calls) == 0)
    check("skip_duplicates=False: all 4 whale writes + 1 cluster = 5 writes",
          len(dedup_client2.create_calls) == 5)

    # Test 25: dedup with empty existing set (fresh quarter)
    class _EmptyDedupClient(_DedupClient):
        def query_database(self, **kwargs):
            from notion_helpers import NotionResult
            self.query_calls.append(kwargs)
            return NotionResult(ok=True, status=200, data={
                "results": [], "has_more": False,
            }, error=None)

    empty = _EmptyDedupClient()
    res = pull_and_classify_for_ticker(empty, payload3, dry_run=False,
                                        skip_duplicates=True)
    check("empty dedup: 0 duplicates",
          res.get("duplicates", 0) == 0)
    check("empty dedup: all 5 rows written",
          len(empty.create_calls) == 5)

    # Test 26: dedup case-insensitivity
    class _CaseClient(_DedupClient):
        def query_database(self, **kwargs):
            from notion_helpers import NotionResult
            return NotionResult(ok=True, status=200, data={
                "results": [
                    {"properties": {"Named Whale": {
                        "type": "rich_text",
                        "rich_text": [{"plain_text": "  WHALE0  "}],
                    }}},
                ],
                "has_more": False,
            }, error=None)

    case = _CaseClient()
    res = pull_and_classify_for_ticker(case, payload3, dry_run=False,
                                        skip_duplicates=True)
    check("case-insensitive dedup matches 'WHALE0' to 'Whale0'",
          res["duplicates"] == 1)

    print(f"\n  13f_quarterly_pull self-test: {passed} pass / {failed} fail")
    return 0 if failed == 0 else 1


# ============================================================================
# CLI
# ============================================================================

def main():
    p = argparse.ArgumentParser(
        description="v11.11 Patch 5 — 13F Quarterly Pull")
    p.add_argument("--self-test", action="store_true",
                   help="Run inline self-test")
    p.add_argument("--check-schedule", action="store_true",
                   help="Print whether today is in any 13F window")
    p.add_argument("--data", default=None,
                   help="Path to UW-pull JSON (list of per-ticker payloads)")
    p.add_argument("--dry-run", action="store_true",
                   help="Classify and report without writing to Notion")
    p.add_argument("--run", action="store_true",
                   help="Live mode: write to 📊 13F Deltas DB")
    p.add_argument("--force", action="store_true",
                   help="Skip schedule guard (run outside 13F window)")
    p.add_argument("--force-write", action="store_true",
                   help="Skip duplicate-row dedup (re-write rows that "
                        "already exist in 📊 13F Deltas DB). Use sparingly.")
    args = p.parse_args()

    if args.self_test:
        return _self_test()

    if args.check_schedule:
        ok, why = should_run_today()
        print(f"should_run_today: {ok} ({why})")
        return 0

    if args.dry_run or args.run:
        if not args.data:
            print("--data is required for --dry-run / --run", file=sys.stderr)
            return 2

        # Schedule guard — bypassable with --force
        if not args.force:
            ok, why = should_run_today()
            if not ok:
                print(f"SKIP: {why}. Use --force to override.",
                      file=sys.stderr)
                return 0

        with open(args.data) as f:
            payloads = json.load(f)
        if not isinstance(payloads, list):
            print("ERROR: --data must be a list of payloads", file=sys.stderr)
            return 2

        if args.run:
            if not _HAS_NOTION:
                print("ERROR: notion_helpers not importable", file=sys.stderr)
                return 3
            client = NotionClient()
        else:
            # Dry-run uses dry NotionClient
            from notion_helpers import NotionClient as _NC
            client = _NC(dry_run=True) if _HAS_NOTION else None

        summaries = []
        for payload in payloads:
            s = pull_and_classify_for_ticker(
                client, payload, dry_run=args.dry_run,
                skip_duplicates=not args.force_write,
            )
            summaries.append(s)
            print(
                f"  {s['ticker']:6} {s.get('filing_period', ''):<10}: "
                f"{s['written']} written, "
                f"{s['skipped']} skipped, "
                f"{s.get('duplicates', 0)} duplicate, "
                f"cluster={s['cluster_detected']}"
            )

        total_written = sum(s["written"] for s in summaries)
        total_skipped = sum(s["skipped"] for s in summaries)
        total_duplicates = sum(s.get("duplicates", 0) for s in summaries)
        total_errors = sum(len(s.get("errors", [])) for s in summaries)
        print(
            f"\nTotal: {total_written} written, {total_skipped} skipped, "
            f"{total_duplicates} duplicate, "
            f"{total_errors} errors across {len(summaries)} tickers."
        )
        if total_errors:
            for s in summaries:
                for e in s.get("errors", []):
                    print(f"  ERROR {s['ticker']}: {e}")
        return 0 if total_errors == 0 else 1

    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
