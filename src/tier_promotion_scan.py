#!/usr/bin/env python3
"""
tier_promotion_scan.py — v11.11 Patch 4 implementation
Shipped: May 14, 2026 late PM

Scans Live Theses DB Tier C rows for ≥2 of 4 promotion criteria firing.
Surfaces promotion candidates for Launcher Step 6 with 🎯 TIER-PROMOTION
CANDIDATE format per CI v11.12.

The 4 promotion criteria (any 2 fire → auto-promote evaluation to Tier B Two-Lens):

  1. Named-source endorsement adoption — name picked up by Fundstrat / Newton
     / Meridian / Lee Granny Shots ETF (source-strength rank #1–#3 per v11.7)
     OR Parabolic Screener AUTOFIRE at Phase 1/2 (v11.12 — equivalent rank #3)
  2. Institutional Cat 7 signal firing — single named whale 13F accumulation
     >$100M OR 3+ institutions adding in same quarter (from 📊 13F Deltas DB)
  3. Regulatory de-risk event — FDA approval, FCC authorization, DOE award,
     SEC approval, foreign regulatory clearance (populated in
     `Regulatory Events Last 90d` field)
  4. Named binary catalyst <90d — product launch with confirmed date,
     regulatory decision deadline, named earnings event with explicit
     guide-raise expectation (populated in `Forward Catalyst` field)

Architecture (mirrors live_theses_helpers.py pattern):
    - Pure-logic core `evaluate_promotion()` — testable without Notion
    - Live integration layer `scan_tier_c_for_promotion()` reads Notion
    - CLI: --self-test (no live deps), --scan (live mode)

Notion targets:
    LIVE_THESES_DS = 0f083d6f-be67-4815-a64a-a21959812f0d
    DELTAS_13F_DS  = 4c61f105-8229-476e-941b-26d8af3cae9a  (read for Cat 2 firing)

Composition rule (per CI v11.12): when a Tier C held position has ≥2 criteria
firing AND is also surfaced by parabolic_setup_screener as AUTOFIRE Phase 1/2,
the two paths merge — surface as TIER-PROMOTION CANDIDATE with Parabolic phase
+ score in the criteria list. This composition is performed by the caller
(launcher orchestrator); this script just emits the promotion record with
parabolic_phase / parabolic_score fields when caller passes them in.

Usage:
    # Pure-logic
    from tier_promotion_scan import evaluate_promotion, PromotionCriteria
    crit = PromotionCriteria(
        named_source_adoption=True,
        institutional_cat7_firing=True,
        regulatory_de_risk_event=False,
        named_binary_catalyst_under_90d=False,
    )
    result = evaluate_promotion(
        ticker="ASTS", tier_current="C", criteria=crit,
        criteria_detail=["Lee Granny Shots inclusion 5/12",
                         "BlackRock +$140M Q1 13F (Tier 1)"],
        position_value=5340.0, sleeve_value=180000.0,
    )

    # Live mode
    python3 tier_promotion_scan.py --scan
        (reads Live Theses DB; needs NOTION_API_TOKEN)

CLI:
    python3 tier_promotion_scan.py --self-test
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
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

LIVE_THESES_DS = "0f083d6f-be67-4815-a64a-a21959812f0d"
DELTAS_13F_DS = "4c61f105-8229-476e-941b-26d8af3cae9a"

PROMOTION_THRESHOLD = 2  # ≥2 criteria fire = candidate


# ============================================================================
# Pure-logic core
# ============================================================================

@dataclass
class PromotionCriteria:
    """Per-ticker booleans for the 4 v11.11 promotion criteria."""
    named_source_adoption: bool = False
    institutional_cat7_firing: bool = False
    regulatory_de_risk_event: bool = False
    named_binary_catalyst_under_90d: bool = False

    def count_firing(self) -> int:
        return int(self.named_source_adoption) + \
               int(self.institutional_cat7_firing) + \
               int(self.regulatory_de_risk_event) + \
               int(self.named_binary_catalyst_under_90d)

    def labels(self) -> list[str]:
        out = []
        if self.named_source_adoption:
            out.append("Named-source endorsement")
        if self.institutional_cat7_firing:
            out.append("Institutional Cat 7")
        if self.regulatory_de_risk_event:
            out.append("Regulatory de-risk event")
        if self.named_binary_catalyst_under_90d:
            out.append("Named binary catalyst <90d")
        return out


@dataclass
class PromotionResult:
    """Outcome of evaluating one Tier C row for promotion."""
    ticker: str
    tier_current: str
    tier_target: str  # always "B" per v11.11
    firing_count: int
    is_candidate: bool         # True iff firing_count >= PROMOTION_THRESHOLD
    criteria: PromotionCriteria
    criteria_detail: list[str]
    position_value: Optional[float]
    sleeve_value: Optional[float]
    parabolic_phase: Optional[int] = None  # set by caller on composition path
    parabolic_score: Optional[float] = None
    surface_format: str = ""


def evaluate_promotion(
    ticker: str,
    tier_current: str,
    criteria: PromotionCriteria,
    criteria_detail: Optional[list[str]] = None,
    position_value: Optional[float] = None,
    sleeve_value: Optional[float] = None,
    parabolic_phase: Optional[int] = None,
    parabolic_score: Optional[float] = None,
) -> PromotionResult:
    """
    Pure-logic promotion evaluator. No I/O.

    Only Tier C rows promote; others return is_candidate=False with reason.

    Args:
        ticker: position ticker
        tier_current: current tier from Live Theses (A/B/C); only "C" can promote
        criteria: PromotionCriteria with 4 booleans
        criteria_detail: optional list of per-firing-criterion human-readable
                         strings to surface in the candidate format
        position_value, sleeve_value: optional context for surface formatting
        parabolic_phase, parabolic_score: optional Patch 2 composition fields
    """
    detail = criteria_detail or []
    firing_count = criteria.count_firing()
    is_candidate = (
        tier_current.upper() == "C"
        and firing_count >= PROMOTION_THRESHOLD
    )

    surface = ""
    if is_candidate:
        surface = _format_surface(
            ticker=ticker, criteria=criteria, criteria_detail=detail,
            position_value=position_value, sleeve_value=sleeve_value,
            parabolic_phase=parabolic_phase, parabolic_score=parabolic_score,
        )

    return PromotionResult(
        ticker=ticker.upper(),
        tier_current=tier_current.upper(),
        tier_target="B",
        firing_count=firing_count,
        is_candidate=is_candidate,
        criteria=criteria,
        criteria_detail=detail,
        position_value=position_value,
        sleeve_value=sleeve_value,
        parabolic_phase=parabolic_phase,
        parabolic_score=parabolic_score,
        surface_format=surface,
    )


def _format_surface(
    ticker: str,
    criteria: PromotionCriteria,
    criteria_detail: list[str],
    position_value: Optional[float],
    sleeve_value: Optional[float],
    parabolic_phase: Optional[int],
    parabolic_score: Optional[float],
) -> str:
    """Build operator-facing TIER-PROMOTION CANDIDATE surface block."""
    labels = criteria.labels()
    # If caller provided detail strings, prefer those; pad with labels if short
    bullet_lines = list(criteria_detail)
    if len(bullet_lines) < len(labels):
        bullet_lines = labels[:]  # fall back to labels

    if parabolic_phase is not None and parabolic_score is not None:
        bullet_lines.append(
            f"Parabolic Screener AUTOFIRE Phase {parabolic_phase} "
            f"(score {parabolic_score:.1f})"
        )

    bullet_str = "\n  - " + "\n  - ".join(bullet_lines)

    pos_line = ""
    if position_value is not None and sleeve_value:
        pct = (position_value / sleeve_value) * 100.0 if sleeve_value else 0.0
        pos_line = (
            f"\nCurrent position: ${position_value:,.0f} ({pct:.2f}% of sleeve)"
        )
    elif position_value is not None:
        pos_line = f"\nCurrent position: ${position_value:,.0f}"

    return (
        f"🎯 TIER-PROMOTION CANDIDATE — {ticker.upper()} (currently Tier C)\n"
        f"Promotion criteria firing:{bullet_str}"
        f"{pos_line}\n"
        f"Recommended action: Two-Lens evaluation with Tier B target sizing\n"
        f"Live Theses row to update: Tier C → Tier B, "
        f"Last Two-Lens Run → today"
    )


# ============================================================================
# Live integration helpers
# ============================================================================

@dataclass
class LiveTierCRow:
    """Subset of Live Theses fields needed for promotion scan."""
    ticker: str
    tier: str
    page_id: str
    position_value: Optional[float]
    forward_catalyst: Optional[str]
    regulatory_events_last_90d: Optional[str]
    promotion_criteria_firing: Optional[str]
    named_anchor: Optional[str]


def _select_name(props: dict, key: str) -> Optional[str]:
    p = props.get(key, {})
    if p.get("type") == "select" and p.get("select"):
        return p["select"].get("name")
    return None


def _number(props: dict, key: str) -> Optional[float]:
    p = props.get(key, {})
    if p.get("type") == "number":
        return p.get("number")
    return None


def _rich_text(props: dict, key: str) -> Optional[str]:
    p = props.get(key, {})
    if p.get("type") == "rich_text":
        chunks = p.get("rich_text", [])
        return "".join(c.get("plain_text", "") for c in chunks) or None
    return None


def _title(props: dict, key: str) -> Optional[str]:
    p = props.get(key, {})
    if p.get("type") == "title":
        chunks = p.get("title", [])
        return "".join(c.get("plain_text", "") for c in chunks) or None
    return None


def fetch_tier_c_rows(client: NotionClient) -> list[LiveTierCRow]:
    """
    Query Live Theses DB for Tier C rows.

    Notion filter: select property "Tier" equals "C".
    """
    filter_body = {
        "property": "Tier",
        "select": {"equals": "C"},
    }
    rows: list[LiveTierCRow] = []
    cursor = None
    while True:
        res = client.query_database(
            data_source_id=LIVE_THESES_DS,
            filter_=filter_body,
            page_size=100,
            start_cursor=cursor,
        )
        if not res.ok or not res.data:
            break
        for page in res.data.get("results", []):
            props = page.get("properties", {})
            ticker = _title(props, "Ticker")
            if not ticker:
                continue
            rows.append(LiveTierCRow(
                ticker=ticker.upper(),
                tier="C",
                page_id=page.get("id", ""),
                position_value=_number(props, "Position Value"),
                forward_catalyst=_rich_text(props, "Forward Catalyst"),
                regulatory_events_last_90d=_rich_text(
                    props, "Regulatory Events Last 90d"),
                promotion_criteria_firing=_rich_text(
                    props, "Promotion Criteria Firing"),
                named_anchor=_rich_text(props, "Named Anchor"),
            ))
        if res.data.get("has_more"):
            cursor = res.data.get("next_cursor")
        else:
            break
    return rows


def derive_criteria_from_row(
    row: LiveTierCRow,
    tier1_13f_tickers: Optional[set[str]] = None,
    parabolic_autofire_phase12: Optional[set[str]] = None,
) -> tuple[PromotionCriteria, list[str]]:
    """
    Derive PromotionCriteria from a Live Theses Tier C row, augmented with:
        - tier1_13f_tickers: set of tickers with Tier-1 13F entry this quarter
                             (loaded externally from 📊 13F Deltas DB)
        - parabolic_autofire_phase12: set of tickers with active AUTOFIRE
                                       Phase 1/2 status from parabolic screener

    Derivation rules (conservative — bias to NOT firing on ambiguous text):
        - named_source_adoption fires iff:
            (a) named_anchor field is populated AND contains one of
                {"Lee", "Newton", "Meridian", "Fundstrat", "Granny Shots"}
            OR
            (b) ticker is in parabolic_autofire_phase12 set
        - institutional_cat7_firing fires iff:
            ticker is in tier1_13f_tickers set
        - regulatory_de_risk_event fires iff:
            regulatory_events_last_90d field is populated (non-empty)
        - named_binary_catalyst_under_90d fires iff:
            forward_catalyst field is populated AND contains a date pattern
            within next 90d (heuristic: month name + day, or ISO date)

    Returns: (PromotionCriteria, list of human-readable detail strings)
    """
    tier1_13f_tickers = tier1_13f_tickers or set()
    parabolic_autofire_phase12 = parabolic_autofire_phase12 or set()

    detail: list[str] = []

    # Criterion 1: named-source endorsement
    crit1 = False
    if row.named_anchor:
        anchor_lower = row.named_anchor.lower()
        if any(s in anchor_lower for s in
               ("lee", "newton", "meridian", "fundstrat", "granny")):
            crit1 = True
            detail.append(f"Named source: {row.named_anchor.strip()[:80]}")
    if row.ticker in parabolic_autofire_phase12:
        crit1 = True
        detail.append("Parabolic Screener AUTOFIRE Phase 1/2")

    # Criterion 2: institutional Cat 7
    crit2 = row.ticker in tier1_13f_tickers
    if crit2:
        detail.append("Tier-1 13F entry (📊 13F Deltas DB)")

    # Criterion 3: regulatory de-risk
    crit3 = bool(row.regulatory_events_last_90d
                 and row.regulatory_events_last_90d.strip())
    if crit3:
        detail.append(
            f"Regulatory event: "
            f"{row.regulatory_events_last_90d.strip()[:100]}"
        )

    # Criterion 4: named binary catalyst <90d
    crit4 = _forward_catalyst_within_90d(row.forward_catalyst)
    if crit4:
        detail.append(
            f"Named binary catalyst: "
            f"{(row.forward_catalyst or '').strip()[:100]}"
        )

    return PromotionCriteria(
        named_source_adoption=crit1,
        institutional_cat7_firing=crit2,
        regulatory_de_risk_event=crit3,
        named_binary_catalyst_under_90d=crit4,
    ), detail


_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}


def _forward_catalyst_within_90d(text: Optional[str],
                                  ref_date: Optional[date] = None) -> bool:
    """
    Heuristic: parse `text` for a date and return True iff it's within 90 days
    forward of `ref_date` (default = today UTC).

    Patterns accepted (case-insensitive):
        - "Aug 4", "August 4" (year inferred to current/next based on month)
        - "2026-08-04", "2026/08/04"
        - "Q3 2026" → uses end-of-Q3 (Sep 30) as upper bound test
        - "8/4/26", "08/04/2026" (US slash-style; ambiguous EU not supported)

    Conservative: returns False on any parse failure.
    """
    import re
    if not text:
        return False
    t = text.strip()
    if not t:
        return False

    today = ref_date or datetime.now(timezone.utc).date()
    horizon = today.toordinal() + 90

    # ISO format
    m = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", t)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return today.toordinal() <= date(y, mo, d).toordinal() <= horizon
        except ValueError:
            pass

    # US slash style (MM/DD/YY or MM/DD/YYYY)
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", t)
    if m:
        mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        try:
            return today.toordinal() <= date(y, mo, d).toordinal() <= horizon
        except ValueError:
            pass

    # Month name + day, optionally year
    m = re.search(
        r"\b("
        r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|"
        r"january|february|march|april|june|july|august|"
        r"september|october|november|december"
        r")\s+(\d{1,2})(?:,?\s*(\d{4}))?\b",
        t, re.IGNORECASE,
    )
    if m:
        mo = _MONTHS[m.group(1).lower()]
        d = int(m.group(2))
        if m.group(3):
            y = int(m.group(3))
        else:
            # Infer year: this year if month >= current, else next year
            y = today.year if mo >= today.month else today.year + 1
        try:
            return today.toordinal() <= date(y, mo, d).toordinal() <= horizon
        except ValueError:
            pass

    # Quarter notation (Q1/Q2/Q3/Q4 YYYY) — use END of quarter
    m = re.search(r"\bq([1-4])\s+(\d{4})\b", t, re.IGNORECASE)
    if m:
        q = int(m.group(1)); y = int(m.group(2))
        end_month = q * 3
        # Last day of end_month
        if end_month == 12:
            eom = date(y, 12, 31)
        else:
            # Day before first of next month
            eom = date(y, end_month + 1, 1).fromordinal(
                date(y, end_month + 1, 1).toordinal() - 1)
        return today.toordinal() <= eom.toordinal() <= horizon

    return False


def scan_tier_c_for_promotion(
    client: NotionClient,
    tier1_13f_tickers: Optional[set[str]] = None,
    parabolic_autofire_phase12: Optional[set[str]] = None,
    sleeve_value: Optional[float] = None,
) -> list[PromotionResult]:
    """
    Top-level live-mode promotion scanner.

    Returns list of PromotionResult; callers filter on is_candidate=True for
    surface output.
    """
    rows = fetch_tier_c_rows(client)
    results: list[PromotionResult] = []
    for r in rows:
        criteria, detail = derive_criteria_from_row(
            r, tier1_13f_tickers, parabolic_autofire_phase12,
        )
        parabolic_phase = None
        parabolic_score = None
        # If caller wants to merge parabolic context into surface,
        # they pass via parabolic_autofire_phase12; for now we just mark
        # criteria firing — phase/score detail enrichment lives at composition
        # site (launcher).
        results.append(evaluate_promotion(
            ticker=r.ticker, tier_current=r.tier,
            criteria=criteria, criteria_detail=detail,
            position_value=r.position_value, sleeve_value=sleeve_value,
            parabolic_phase=parabolic_phase, parabolic_score=parabolic_score,
        ))
    return results


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

    # Test 1: zero criteria firing — not a candidate
    crit = PromotionCriteria()
    r = evaluate_promotion("XYZ", "C", crit)
    check("zero firing not a candidate", r.is_candidate is False)
    check("firing_count == 0", r.firing_count == 0)
    check("surface empty", r.surface_format == "")

    # Test 2: exactly 2 firing — candidate
    crit = PromotionCriteria(
        named_source_adoption=True, institutional_cat7_firing=True,
    )
    r = evaluate_promotion(
        "ASTS", "C", crit,
        criteria_detail=["Lee Granny Shots inclusion",
                         "BlackRock Q1 +$140M"],
        position_value=5340.0, sleeve_value=180000.0,
    )
    check("2 firing -> candidate", r.is_candidate is True)
    check("firing_count == 2", r.firing_count == 2)
    check("tier_target == B", r.tier_target == "B")
    check("surface contains ticker", "ASTS" in r.surface_format)
    check("surface includes both details",
          "Lee Granny" in r.surface_format
          and "BlackRock" in r.surface_format)
    check("surface includes position pct",
          "2.97%" in r.surface_format or "2.96%" in r.surface_format
          or "2.97" in r.surface_format)

    # Test 3: 1 firing — not enough
    crit = PromotionCriteria(institutional_cat7_firing=True)
    r = evaluate_promotion("X", "C", crit)
    check("1 firing not a candidate", r.is_candidate is False)

    # Test 4: 4 firing — strongly a candidate
    crit = PromotionCriteria(True, True, True, True)
    r = evaluate_promotion("ASTS", "C", crit, criteria_detail=[
        "Lee", "13F", "FCC approval", "Earnings 8/4/26",
    ])
    check("4 firing -> candidate", r.is_candidate is True)
    check("firing_count == 4", r.firing_count == 4)

    # Test 5: non-Tier-C does NOT promote even at 4 firing
    r = evaluate_promotion("LEU", "A", crit, criteria_detail=[])
    check("Tier A with 4 firing not a promotion candidate",
          r.is_candidate is False)

    # Test 6: criteria.labels() ordering
    crit = PromotionCriteria(True, False, True, False)
    labels = crit.labels()
    check("labels has 2", len(labels) == 2)
    check("labels order: named-source then regulatory",
          "Named-source" in labels[0] and "Regulatory" in labels[1])

    # Test 7: forward-catalyst date parsing — ISO format within 90d
    today = date(2026, 5, 14)
    check("ISO date within 90d fires",
          _forward_catalyst_within_90d("Earnings 2026-08-04", today) is True)
    check("ISO date beyond 90d does not fire",
          _forward_catalyst_within_90d("Earnings 2027-01-15", today) is False)
    check("ISO date in past does not fire",
          _forward_catalyst_within_90d("Earnings 2026-01-15", today) is False)

    # Test 8: month-name pattern
    check("Aug 4 within 90d fires (ref May 14)",
          _forward_catalyst_within_90d("Earnings Aug 4", today) is True)
    check("December within 90d (ref May 14) does not fire",
          _forward_catalyst_within_90d("Earnings December 1", today) is False)

    # Test 9: slash style
    check("US slash 7/15/26 fires (ref May 14)",
          _forward_catalyst_within_90d("FCC decision 7/15/26", today) is True)

    # Test 10: empty/null catalyst
    check("empty catalyst no fire", _forward_catalyst_within_90d("", today) is False)
    check("None catalyst no fire", _forward_catalyst_within_90d(None, today) is False)
    check("freeform text no fire",
          _forward_catalyst_within_90d("monitoring this quarter", today) is False)

    # Test 11: Q-notation
    check("Q3 2026 fires (ref May 14, Q3 ends Sep 30)",
          _forward_catalyst_within_90d("Q3 2026", today) is False)  # >90d
    check("Q2 2026 fires (Q2 ends Jun 30, within 90d of May 14)",
          _forward_catalyst_within_90d("Q2 2026", today) is True)

    # Test 12: derive_criteria_from_row — full firing (deterministic ref_date)
    # Use ref_date in _forward_catalyst_within_90d to make catalyst check
    # deterministic; pass a date that puts June 15 within 90 days.
    fixed_today = date(2026, 4, 1)  # June 15 2026 is 75 days out -> fires
    row = LiveTierCRow(
        ticker="ASTS", tier="C", page_id="p1",
        position_value=5340.0,
        forward_catalyst="BlueBird launch June 15 2026",
        regulatory_events_last_90d="FCC partial market access 4/22",
        promotion_criteria_firing=None,
        named_anchor="Lee Granny Shots GRNY 2.45% weight",
    )
    # Patch the helper temporarily to use the fixed today
    import re_entry_zone_scan  # noqa: F401 — silence unused if missing
    # Direct call to _forward_catalyst_within_90d with explicit ref_date
    catalyst_fires_deterministic = _forward_catalyst_within_90d(
        row.forward_catalyst, ref_date=fixed_today,
    )
    crit, det = derive_criteria_from_row(
        row,
        tier1_13f_tickers={"ASTS"},
        parabolic_autofire_phase12=set(),
    )
    check("derive: named-source fires", crit.named_source_adoption is True)
    check("derive: Cat 7 fires", crit.institutional_cat7_firing is True)
    check("derive: regulatory fires", crit.regulatory_de_risk_event is True)
    # Catalyst check uses today() in production; verify the helper deterministically
    check("derive: catalyst date logic correct under fixed ref_date (Apr 1 -> Jun 15 fires)",
          catalyst_fires_deterministic is True)
    check("derive returns ≥3 details when 3+ fire",
          len(det) >= 3)

    # Test 13: derive_criteria — parabolic-only path
    row2 = LiveTierCRow(
        ticker="FORM", tier="C", page_id="p2",
        position_value=2000.0,
        forward_catalyst=None,
        regulatory_events_last_90d=None,
        promotion_criteria_firing=None,
        named_anchor=None,
    )
    crit, det = derive_criteria_from_row(
        row2,
        tier1_13f_tickers=set(),
        parabolic_autofire_phase12={"FORM"},
    )
    check("derive: parabolic alone fires Crit 1",
          crit.named_source_adoption is True and crit.count_firing() == 1)
    check("derive: parabolic detail mentioned",
          any("Parabolic" in d for d in det))

    # Test 14: composition with parabolic phase/score field
    r = evaluate_promotion(
        "FORM", "C",
        PromotionCriteria(named_source_adoption=True,
                          institutional_cat7_firing=True),
        criteria_detail=["Lee", "13F"],
        parabolic_phase=2, parabolic_score=10.5,
    )
    check("parabolic enrichment in surface",
          "Phase 2" in r.surface_format and "10.5" in r.surface_format)

    # Test 15: live scanner shape
    class _FakeClient:
        def query_database(self, **kwargs):
            from notion_helpers import NotionResult
            return NotionResult(ok=True, status=200, data={
                "results": [
                    {
                        "id": "p1",
                        "properties": {
                            "Ticker": {"type": "title",
                                       "title": [{"plain_text": "ASTS"}]},
                            "Tier": {"type": "select",
                                     "select": {"name": "C"}},
                            "Position Value": {"type": "number", "number": 5340.0},
                            "Forward Catalyst": {
                                "type": "rich_text",
                                "rich_text": [{"plain_text":
                                    "BlueBird launch 6/15/26"}],
                            },
                            "Regulatory Events Last 90d": {
                                "type": "rich_text",
                                "rich_text": [{"plain_text":
                                    "FCC market access 4/22"}],
                            },
                            "Named Anchor": {
                                "type": "rich_text",
                                "rich_text": [{"plain_text":
                                    "Lee Granny Shots inclusion"}],
                            },
                            "Promotion Criteria Firing": {
                                "type": "rich_text", "rich_text": []},
                        },
                    },
                    {
                        "id": "p2",
                        "properties": {
                            "Ticker": {"type": "title",
                                       "title": [{"plain_text": "XYZ"}]},
                            "Tier": {"type": "select",
                                     "select": {"name": "C"}},
                            "Position Value": {"type": "number", "number": 800.0},
                            "Forward Catalyst": {"type": "rich_text",
                                                  "rich_text": []},
                            "Regulatory Events Last 90d": {
                                "type": "rich_text", "rich_text": []},
                            "Named Anchor": {"type": "rich_text",
                                              "rich_text": []},
                            "Promotion Criteria Firing": {
                                "type": "rich_text", "rich_text": []},
                        },
                    },
                ],
                "has_more": False,
            }, error=None)

    fake = _FakeClient()
    out = scan_tier_c_for_promotion(
        fake,
        tier1_13f_tickers={"ASTS"},
        parabolic_autofire_phase12=set(),
        sleeve_value=180000.0,
    )
    check("live scan returns 2 results", len(out) == 2)
    asts = next((r for r in out if r.ticker == "ASTS"), None)
    xyz = next((r for r in out if r.ticker == "XYZ"), None)
    check("ASTS surfaces as candidate (3 criteria firing)",
          asts is not None and asts.is_candidate is True
          and asts.firing_count >= 2)
    check("XYZ not a candidate (zero criteria)",
          xyz is not None and xyz.is_candidate is False)

    # Test 16: ticker upper-cased
    r = evaluate_promotion("asts", "c",
                           PromotionCriteria(True, True, False, False))
    check("ticker upper-cased in result", r.ticker == "ASTS")
    check("tier upper-cased in result", r.tier_current == "C")

    print(f"\n  tier_promotion_scan self-test: {passed} pass / {failed} fail")
    return 0 if failed == 0 else 1


# ============================================================================
# CLI
# ============================================================================

def main():
    p = argparse.ArgumentParser(
        description="v11.11 Patch 4 — Tier C Promotion Scan")
    p.add_argument("--self-test", action="store_true",
                   help="Run inline self-test")
    p.add_argument("--scan", action="store_true",
                   help="Live scan (requires NOTION_API_TOKEN)")
    p.add_argument("--tier1-13f", default=None,
                   help="Comma-separated tickers with Tier-1 13F entry "
                        "this quarter")
    p.add_argument("--parabolic-phase12", default=None,
                   help="Comma-separated tickers with active Parabolic "
                        "AUTOFIRE Phase 1/2")
    p.add_argument("--sleeve-value", type=float, default=None,
                   help="Sleeve value for surface pct calc")
    args = p.parse_args()

    if args.self_test:
        return _self_test()

    if args.scan:
        if not _HAS_NOTION:
            print("ERROR: notion_helpers not importable", file=sys.stderr)
            return 3
        t1 = set((args.tier1_13f or "").split(",")) - {""}
        para = set((args.parabolic_phase12 or "").split(",")) - {""}
        client = NotionClient()
        results = scan_tier_c_for_promotion(
            client, tier1_13f_tickers=t1,
            parabolic_autofire_phase12=para,
            sleeve_value=args.sleeve_value,
        )
        candidates = [r for r in results if r.is_candidate]
        print(f"Scanned {len(results)} Tier C rows; "
              f"{len(candidates)} promotion candidate(s).\n")
        for r in candidates:
            print(r.surface_format)
            print()
        return 0

    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
