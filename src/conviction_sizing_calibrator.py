#!/usr/bin/env python3
"""
conviction_sizing_calibrator.py — v11.26 rebuild

PURPOSE
    For every held position, compare its actual sleeve % to the floor/ceiling
    defined by its conviction tier.  Surface "right but too small" gaps —
    the canonical failure mode named in operator memory ("April 2026 missed
    because allocations were sub-scale despite correct thesis").

    Tier bands:
      T1 (Generational)   8 – 12 %  sleeve target
      T2 (High-conv)      4 – 7  %
      T3 (Tactical)       1.5 – 3 %
      T4 (Spec)           0 – 1  %
      Untiered            treated as T3

V11.26 ENHANCEMENTS OVER V11.20 ORIGINAL
    1. Macro-aware urgency (v11.25): rate-sensitive positions in duration_WEAK
       regime get LOW_URGENCY on gap-closing.  Duration-tailwind positions
       (e.g., long-duration growth in duration_STRONG) get HIGH_URGENCY.
    2. Source hit-rate discount (v11.26): when a position is anchored on a
       source × tier band with CONSISTENT_MISS or BELOW_BREAKEVEN, the gap-
       closing recommendation drops to discount-only OR LOW_URGENCY.  Catches
       "right but too small" pre-flight: i.e., maybe the position is too small
       because the named source has degraded edge, not because operator was
       under-sized on conviction.
    3. P-DEEPWORK flag (v11.24): any gap-closing action ≥$25K notional gets
       flagged for multi-turn workflow.

USAGE
    python conviction_sizing_calibrator.py --self-test
    python conviction_sizing_calibrator.py --positions P.json --theses T.json \\
        --sleeve-total 1875000
    python conviction_sizing_calibrator.py --positions P.json --theses T.json \\
        --sleeve-total 1875000 --macro M.json --source-rates R.json
"""

import argparse
import json
import sys
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Tuple


# ============================================================================
# TIER BANDS
# ============================================================================

TIER_BANDS = {
    "T1": (0.08, 0.12),
    "T2": (0.04, 0.07),
    "T3": (0.015, 0.03),
    "T4": (0.00, 0.01),
}
UNTIERED_DEFAULT = "T3"

CRITICAL_BELOW_RATIO = 0.50  # actual / floor < 0.50 → CRITICALLY_BELOW
DEEPWORK_NOTIONAL_THRESHOLD = 25000.0

# Rate-sensitive factor tags — positions in these factor buckets are sensitive
# to duration_WEAK regime and should NOT be urgently floor-filled when 10Y
# rising / curve steepening
RATE_SENSITIVE_FACTORS = {
    "long_duration_growth", "long_duration", "high_pe",
    "small_cap_growth", "biotech_unprofitable",
}

# Source × tier hit-rate bands (per P-SOURCE-CALIBRATION)
HITRATE_BAND_DISCOUNT = {
    "CONSISTENT_MISS": 0.25,
    "BELOW_BREAKEVEN": 0.50,
    "NORMAL":           1.00,
    "HIGH_CONVICTION":  1.25,
    "INSUFFICIENT_DATA": 1.00,
}


# ============================================================================
# INPUT GUARDS
# ============================================================================

def _reject_sample_inputs_path(label: str, path: Optional[str]) -> None:
    if not path:
        return
    normalized = path.replace("\\", "/").lower()
    if "/sample_inputs/" in normalized or normalized.startswith("sample_inputs/"):
        raise ValueError(
            f"{label} must not point at sample_inputs; use canonical position, "
            "thesis, macro, and source-rate caches."
        )


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class ConvictionGap:
    ticker: str
    tier: str
    lane: Optional[str]
    source_at_entry: Optional[str]

    current_value: float
    current_pct: float
    floor_pct: float
    ceiling_pct: float
    classification: str           # CRITICALLY_BELOW / BELOW_FLOOR / IN_BAND / ABOVE_CEILING
    gap_to_floor_pct: float       # 0 if at/above floor, else positive
    gap_to_floor_value: float

    # v11.25 — macro lean
    macro_urgency: str = "NORMAL"  # LOW / NORMAL / HIGH
    macro_reason: Optional[str] = None

    # v11.26 — source calibration
    source_hit_rate_band: Optional[str] = None
    source_discount: float = 1.00
    discounted_gap_value: float = 0.0

    # v12.0 — MONITOR stance suppression (CI §7-D)
    stance: Optional[str] = None

    flags: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class ConvictionReport:
    sleeve_total: float
    critically_below: List[ConvictionGap] = field(default_factory=list)
    below_floor: List[ConvictionGap] = field(default_factory=list)
    in_band: List[ConvictionGap] = field(default_factory=list)
    above_ceiling: List[ConvictionGap] = field(default_factory=list)
    no_thesis: List[ConvictionGap] = field(default_factory=list)
    monitor_suppressed: List[ConvictionGap] = field(default_factory=list)

    gap_to_close_total: float = 0.0
    gap_to_close_discounted: float = 0.0
    deepwork_required_count: int = 0
    summary: str = ""


# ============================================================================
# HELPERS
# ============================================================================

def _classify_gap(pct: float, floor: float, ceiling: float) -> str:
    if floor > 0 and (pct / floor) < CRITICAL_BELOW_RATIO:
        return "CRITICALLY_BELOW"
    if pct < floor:
        return "BELOW_FLOOR"
    if pct > ceiling:
        return "ABOVE_CEILING"
    return "IN_BAND"


def _macro_urgency_for(ticker: str, factor_tags: List[str],
                       macro_pulse: Optional[Dict]) -> Tuple[str, Optional[str]]:
    """
    Return (urgency, reason).  Default NORMAL with no reason.
    """
    if not macro_pulse:
        return "NORMAL", None

    regime = (macro_pulse.get("regime_label")
              or macro_pulse.get("regime") or "").lower()
    duration_state = "unknown"
    if "duration_weak" in regime:
        duration_state = "weak"
    elif "duration_strong" in regime:
        duration_state = "strong"

    factor_set = {f.lower() for f in (factor_tags or [])}
    rate_sensitive = bool(factor_set & {f.lower() for f in RATE_SENSITIVE_FACTORS})

    if duration_state == "weak" and rate_sensitive:
        return ("LOW",
                "duration_WEAK regime + rate-sensitive factor — defer floor-fill")
    if duration_state == "strong" and rate_sensitive:
        return ("HIGH",
                "duration_STRONG regime + rate-sensitive factor — fill urgently")

    # Dollar regime affects critical minerals
    dollar_state = "unknown"
    if "dollar_strong" in regime:
        dollar_state = "strong"
    elif "dollar_weak" in regime:
        dollar_state = "weak"

    crit_min = "critical_minerals" in factor_set or "rare_earth" in factor_set
    if dollar_state == "strong" and crit_min:
        return ("LOW", "dollar_STRONG headwind on critical minerals — defer")
    if dollar_state == "weak" and crit_min:
        return ("HIGH", "dollar_WEAK tailwind on critical minerals — fill")

    return "NORMAL", None


def _source_discount_for(ticker: str, source: Optional[str], tier: str,
                         source_rates: Optional[Dict]) -> Tuple[float, Optional[str]]:
    """
    Return (discount, band_label).  Default (1.00, None).

    source_rates structure (matches source_call_tracker.py output):
      {
        "newton": {"A": {"band": "NORMAL", "n": 18}, "B": {"band": "BELOW_BREAKEVEN", "n": 22}},
        "lee":    {"A": {"band": "INSUFFICIENT_DATA", "n": 4}}, ...
      }
    """
    if not source or not source_rates:
        return 1.00, None
    s = source.lower()
    by_source = source_rates.get(s)
    if not by_source:
        return 1.00, None
    by_tier = by_source.get(tier) or by_source.get("A+B") or by_source.get("ALL")
    if not by_tier:
        return 1.00, None
    band = by_tier.get("band", "INSUFFICIENT_DATA")
    n = by_tier.get("n", 0)
    if n < 15:
        return 1.00, "INSUFFICIENT_DATA"
    return HITRATE_BAND_DISCOUNT.get(band, 1.00), band


def _lookup_thesis(ticker: str, theses: List[Dict]) -> Optional[Dict]:
    for t in theses:
        if (t.get("ticker") or "").upper() == ticker.upper():
            return t
    return None


# ============================================================================
# CORE CALIBRATOR
# ============================================================================

def calibrate(positions: List[Dict], theses: List[Dict],
              sleeve_total: float,
              macro_pulse: Optional[Dict] = None,
              source_rates: Optional[Dict] = None) -> ConvictionReport:
    """
    Build a ConvictionReport across all positions.

    positions: [{"ticker": "BMNR", "market_value": 71500}, ...]
    theses:    [{"ticker": "BMNR", "tier": "T1", "lane": "Generational",
                 "source": "operator", "factor_tags": ["crypto", "eth"]}, ...]
    """
    if sleeve_total <= 0:
        raise ValueError("sleeve_total must be > 0")

    # Aggregate by ticker
    agg: Dict[str, float] = {}
    for p in positions:
        t = (p.get("ticker") or "").upper().strip()
        if not t:
            continue
        agg[t] = agg.get(t, 0.0) + float(p.get("market_value", 0) or 0)

    report = ConvictionReport(sleeve_total=sleeve_total)

    for ticker, value in agg.items():
        pct = value / sleeve_total
        thesis = _lookup_thesis(ticker, theses)

        if not thesis:
            tier = UNTIERED_DEFAULT
            lane = None
            source = None
            factor_tags = []
            stance = ""
        else:
            tier = (thesis.get("tier") or UNTIERED_DEFAULT).upper()
            if tier not in TIER_BANDS:
                # Strip prefixes like "T1 Generational" → "T1"
                first_two = tier[:2]
                tier = first_two if first_two in TIER_BANDS else UNTIERED_DEFAULT
            lane = thesis.get("lane")
            source = thesis.get("source") or thesis.get("source_at_entry")
            factor_tags = thesis.get("factor_tags") or []
            stance = (thesis.get("stance") or "").upper()

        floor, ceiling = TIER_BANDS[tier]
        classification = _classify_gap(pct, floor, ceiling)
        gap_pct = max(0.0, floor - pct)
        gap_value = gap_pct * sleeve_total

        macro_urg, macro_reason = _macro_urgency_for(ticker, factor_tags, macro_pulse)
        discount, band = _source_discount_for(ticker, source, tier, source_rates)

        gap = ConvictionGap(
            ticker=ticker,
            tier=tier,
            lane=lane,
            stance=stance,
            source_at_entry=source,
            current_value=value,
            current_pct=pct,
            floor_pct=floor,
            ceiling_pct=ceiling,
            classification=classification,
            gap_to_floor_pct=gap_pct,
            gap_to_floor_value=gap_value,
            macro_urgency=macro_urg,
            macro_reason=macro_reason,
            source_hit_rate_band=band,
            source_discount=discount,
            discounted_gap_value=gap_value * discount,
        )

        if not thesis:
            gap.flags.append("no_thesis_row")
            gap.notes.append("No Live Theses row — defaulted to T3 band")

        if gap.gap_to_floor_value >= DEEPWORK_NOTIONAL_THRESHOLD:
            gap.flags.append("deepwork_threshold")

        if stance == "MONITOR":
            # CI §7-D: MONITOR-stance names (crypto/ETH, nuclear/uranium,
            # critical-minerals) are intentionally below floor and are excluded
            # from gap / under-deployment flags and totals.
            gap.flags.append("monitor_suppressed")
            gap.notes.append(
                "MONITOR-stance — intentionally below floor; excluded from "
                "gap/under-deployment flags (CI §7-D)"
            )
            report.monitor_suppressed.append(gap)
            if not thesis:
                report.no_thesis.append(gap)
        else:
            if classification == "CRITICALLY_BELOW":
                report.critically_below.append(gap)
            elif classification == "BELOW_FLOOR":
                report.below_floor.append(gap)
            elif classification == "ABOVE_CEILING":
                report.above_ceiling.append(gap)
            else:
                report.in_band.append(gap)
            if not thesis:
                report.no_thesis.append(gap)

            if classification in ("CRITICALLY_BELOW", "BELOW_FLOOR"):
                report.gap_to_close_total += gap.gap_to_floor_value
                report.gap_to_close_discounted += gap.discounted_gap_value
                if "deepwork_threshold" in gap.flags:
                    report.deepwork_required_count += 1

    report.summary = (
        f"{len(report.critically_below)} CRITICALLY_BELOW, "
        f"{len(report.below_floor)} BELOW_FLOOR, "
        f"{len(report.in_band)} IN_BAND, "
        f"{len(report.above_ceiling)} ABOVE_CEILING. "
        f"Gap-to-floor total: ${report.gap_to_close_total:,.0f} "
        f"(discounted: ${report.gap_to_close_discounted:,.0f}). "
        f"{report.deepwork_required_count} require P-DEEPWORK. "
        f"{len(report.monitor_suppressed)} MONITOR-suppressed (CI §7-D)."
    )
    return report


# ============================================================================
# OUTPUT FORMATTERS
# ============================================================================

def format_text_report(r: ConvictionReport) -> str:
    out = []
    out.append("=" * 70)
    out.append("CONVICTION SIZING CALIBRATION")
    out.append("=" * 70)
    out.append(r.summary)
    out.append("")

    def _section(label: str, items: List[ConvictionGap]) -> None:
        if not items:
            return
        out.append(f"-- {label} ({len(items)}) " + "-" * 50)
        for g in items:
            out.append(
                f"  {g.ticker:8} {g.tier}  "
                f"@ {g.current_pct*100:5.2f}% "
                f"(floor {g.floor_pct*100:.1f}%, ceil {g.ceiling_pct*100:.1f}%) "
                f"→ ${g.current_value:>10,.0f}"
            )
            if g.gap_to_floor_value > 0:
                out.append(
                    f"           gap to floor: ${g.gap_to_floor_value:,.0f} "
                    f"(discounted: ${g.discounted_gap_value:,.0f}, "
                    f"urgency: {g.macro_urgency})"
                )
            if g.macro_reason:
                out.append(f"           macro: {g.macro_reason}")
            if g.source_hit_rate_band and g.source_hit_rate_band != "INSUFFICIENT_DATA":
                out.append(
                    f"           source: {g.source_at_entry} "
                    f"× tier {g.tier} band: {g.source_hit_rate_band} "
                    f"× {g.source_discount}"
                )
            if g.flags:
                out.append(f"           flags: {', '.join(g.flags)}")
        out.append("")

    _section("CRITICALLY_BELOW (canonical failure mode)", r.critically_below)
    _section("BELOW_FLOOR", r.below_floor)
    _section("ABOVE_CEILING", r.above_ceiling)
    _section("IN_BAND", r.in_band)
    _section("MONITOR-SUPPRESSED (intentional, CI §7-D)", r.monitor_suppressed)
    if r.no_thesis:
        out.append(f"-- NO THESIS ROW ({len(r.no_thesis)}) " + "-" * 50)
        for g in r.no_thesis:
            out.append(f"  {g.ticker:8} @ {g.current_pct*100:5.2f}% (defaulted to T3)")
        out.append("")
    return "\n".join(out)


def format_json_report(r: ConvictionReport) -> str:
    return json.dumps(asdict(r), indent=2, default=str)


def surface_line(r: ConvictionReport) -> str:
    """
    One-line summary suitable for pre-flight surface.
    """
    crit = len(r.critically_below)
    below = len(r.below_floor)
    return (f"CONVICTION SIZING: {crit} CRITICALLY_BELOW, {below} BELOW_FLOOR, "
            f"${r.gap_to_close_total:,.0f} gap-to-floor "
            f"(${r.gap_to_close_discounted:,.0f} discounted, "
            f"{r.deepwork_required_count} require P-DEEPWORK)")


# ============================================================================
# SELF-TEST
# ============================================================================

def _self_test() -> bool:
    passed = 0
    failed = 0

    def assert_eq(actual, expected, label):
        nonlocal passed, failed
        if actual == expected:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {label}: expected {expected!r}, got {actual!r}")

    def assert_close(actual, expected, label, tol=1.0):
        nonlocal passed, failed
        if actual is None:
            failed += 1
            print(f"  FAIL: {label}: actual is None")
            return
        if abs(actual - expected) <= tol:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {label}: expected ~{expected}, got {actual}")

    def assert_true(condition, label):
        nonlocal passed, failed
        if condition:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {label}")

    # ----- Test 1: CRITICALLY_BELOW (canonical BMNR example)
    positions = [{"ticker": "BMNR", "market_value": 71500}]
    theses = [{"ticker": "BMNR", "tier": "T1", "lane": "Generational",
               "source": "operator"}]
    r = calibrate(positions, theses, sleeve_total=1875000)
    # 71500 / 1875000 = 3.81%; T1 floor 8% → 3.81/8 = 0.476 < 0.50 → CRITICALLY_BELOW
    assert_eq(len(r.critically_below), 1, "BMNR CRITICALLY_BELOW count")
    assert_eq(r.critically_below[0].ticker, "BMNR", "BMNR ticker")
    assert_close(r.critically_below[0].current_pct * 100, 3.81, "BMNR pct", 0.1)
    assert_close(r.critically_below[0].gap_to_floor_value, 78500, "BMNR gap-to-floor", 100)
    assert_true("deepwork_threshold" in r.critically_below[0].flags,
                "BMNR fires deepwork_threshold ($78K > $25K)")

    # ----- Test 2: BELOW_FLOOR (not critical)
    positions = [{"ticker": "LEU", "market_value": 96000}]  # 96/1875 = 5.12%
    theses = [{"ticker": "LEU", "tier": "T1", "lane": "Generational",
               "source": "Meridian"}]
    r = calibrate(positions, theses, sleeve_total=1875000)
    # 5.12% / 8% = 0.64 > 0.50 → BELOW_FLOOR not CRITICALLY_BELOW
    assert_eq(len(r.below_floor), 1, "LEU BELOW_FLOOR count")
    assert_eq(len(r.critically_below), 0, "LEU not critical")

    # ----- Test 3: IN_BAND
    positions = [{"ticker": "NVDA", "market_value": 139000}]  # 7.41%
    theses = [{"ticker": "NVDA", "tier": "T2", "lane": "Speed", "source": "Lee"}]
    r = calibrate(positions, theses, sleeve_total=1875000)
    # T2 = 4-7% — 7.41% is just above ceiling
    assert_eq(len(r.above_ceiling), 1, "NVDA ABOVE_CEILING")

    # ----- Test 4: untiered defaults to T3
    positions = [{"ticker": "ZZZ", "market_value": 50000}]  # 2.67%
    theses = []
    r = calibrate(positions, theses, sleeve_total=1875000)
    # untiered → T3 band 1.5-3%; 2.67% is in band
    assert_eq(len(r.in_band), 1, "untiered IN_BAND")
    assert_eq(r.in_band[0].tier, "T3", "untiered defaults to T3")
    assert_true("no_thesis_row" in r.in_band[0].flags, "no_thesis_row flag")

    # ----- Test 5: empty positions
    r = calibrate([], [], sleeve_total=1875000)
    assert_eq(len(r.critically_below), 0, "empty: no critical")
    assert_eq(r.gap_to_close_total, 0, "empty: no gap")

    # ----- Test 6: tier prefix stripping ("T1 Generational" → "T1")
    positions = [{"ticker": "AAA", "market_value": 71500}]
    theses = [{"ticker": "AAA", "tier": "T1 Generational"}]
    r = calibrate(positions, theses, sleeve_total=1875000)
    assert_eq(r.critically_below[0].tier, "T1", "tier prefix stripped")

    # ----- Test 7: cross-account aggregation
    positions = [
        {"ticker": "MP", "market_value": 20000, "account": "A"},
        {"ticker": "MP", "market_value": 19680, "account": "B"},
    ]
    theses = [{"ticker": "MP", "tier": "T3", "source": "Meridian"}]
    r = calibrate(positions, theses, sleeve_total=1875000)
    # 39680/1875000 = 2.12% — T3 band 1.5-3% → IN_BAND
    assert_eq(len(r.in_band), 1, "MP aggregated → IN_BAND")
    assert_close(r.in_band[0].current_value, 39680, "MP aggregated value")

    # ----- Test 8: macro LOW urgency (duration_WEAK + rate-sensitive)
    positions = [{"ticker": "RATE_SENS", "market_value": 50000}]
    theses = [{
        "ticker": "RATE_SENS",
        "tier": "T1",  # 8% floor → 100K → gap 100K
        "factor_tags": ["long_duration_growth"]
    }]
    macro = {"regime_label": "duration_WEAK · credit_COMPLACENT"}
    r = calibrate(positions, theses, sleeve_total=1875000, macro_pulse=macro)
    target = r.critically_below[0] if r.critically_below else r.below_floor[0]
    assert_eq(target.macro_urgency, "LOW",
              "duration_WEAK + rate-sensitive → LOW urgency")
    assert_true("rate-sensitive" in (target.macro_reason or ""),
                "macro reason mentions rate-sensitive")

    # ----- Test 9: macro HIGH urgency (dollar_WEAK + critical minerals)
    positions = [{"ticker": "MP", "market_value": 50000}]
    theses = [{
        "ticker": "MP",
        "tier": "T1",
        "factor_tags": ["critical_minerals"]
    }]
    macro = {"regime_label": "dollar_WEAK · credit_NORMAL"}
    r = calibrate(positions, theses, sleeve_total=1875000, macro_pulse=macro)
    target = r.critically_below[0] if r.critically_below else r.below_floor[0]
    assert_eq(target.macro_urgency, "HIGH", "dollar_WEAK + crit_minerals → HIGH")

    # ----- Test 10: source hit-rate discount (BELOW_BREAKEVEN at n≥15)
    positions = [{"ticker": "BMNR", "market_value": 71500}]
    theses = [{"ticker": "BMNR", "tier": "T1", "source": "Newton"}]
    source_rates = {
        "newton": {"T1": {"band": "BELOW_BREAKEVEN", "n": 22}}
    }
    r = calibrate(positions, theses, sleeve_total=1875000,
                  source_rates=source_rates)
    assert_close(r.critically_below[0].source_discount, 0.50,
                 "BELOW_BREAKEVEN → 0.50x discount", 0.001)
    # gap was $78500; discounted = $39250
    assert_close(r.critically_below[0].discounted_gap_value, 39250,
                 "discounted gap value", 100)

    # ----- Test 11: source hit-rate INSUFFICIENT_DATA (n<15) → no discount
    source_rates = {"newton": {"T1": {"band": "NORMAL", "n": 8}}}
    r = calibrate(positions, theses, sleeve_total=1875000,
                  source_rates=source_rates)
    assert_close(r.critically_below[0].source_discount, 1.00,
                 "n<15 → no discount", 0.001)
    assert_eq(r.critically_below[0].source_hit_rate_band, "INSUFFICIENT_DATA",
              "band labeled INSUFFICIENT_DATA")

    # ----- Test 12: source hit-rate HIGH_CONVICTION (1.25x boost)
    source_rates = {"newton": {"T1": {"band": "HIGH_CONVICTION", "n": 30}}}
    r = calibrate(positions, theses, sleeve_total=1875000,
                  source_rates=source_rates)
    assert_close(r.critically_below[0].source_discount, 1.25,
                 "HIGH_CONVICTION → 1.25x boost", 0.001)

    # ----- Test 13: source hit-rate CONSISTENT_MISS (0.25x discount)
    source_rates = {"newton": {"T1": {"band": "CONSISTENT_MISS", "n": 25}}}
    r = calibrate(positions, theses, sleeve_total=1875000,
                  source_rates=source_rates)
    assert_close(r.critically_below[0].source_discount, 0.25,
                 "CONSISTENT_MISS → 0.25x", 0.001)

    # ----- Test 14: gap_to_close_total accumulates only below-floor gaps
    positions = [
        {"ticker": "BMNR", "market_value": 71500},   # T1 floor 150K → gap 78500
        {"ticker": "NVDA", "market_value": 139000},  # T2 ceiling 131K → ABOVE
        {"ticker": "MP", "market_value": 50000},      # T3 ceiling 56K → IN_BAND
    ]
    theses = [
        {"ticker": "BMNR", "tier": "T1"},
        {"ticker": "NVDA", "tier": "T2"},
        {"ticker": "MP", "tier": "T3"},
    ]
    r = calibrate(positions, theses, sleeve_total=1875000)
    assert_close(r.gap_to_close_total, 78500, "gap total = BMNR only", 100)

    # ----- Test 15: P-DEEPWORK count
    assert_true(r.deepwork_required_count >= 1, "BMNR gap triggers deepwork count")

    # ----- Test 16: surface_line
    line = surface_line(r)
    assert_true("CONVICTION SIZING" in line, "surface_line label")
    assert_true("CRITICALLY_BELOW" in line, "surface_line CRITICALLY_BELOW")

    # ----- Test 17: format_text_report runs without crashing
    text = format_text_report(r)
    assert_true("BMNR" in text, "text report contains BMNR")

    # ----- Test 18: JSON report
    js = format_json_report(r)
    parsed = json.loads(js)
    assert_true("critically_below" in parsed, "JSON has critically_below")

    # ----- Test 19: invalid sleeve_total
    try:
        calibrate(positions, theses, sleeve_total=0)
        assert_true(False, "sleeve_total=0 should raise")
    except ValueError:
        assert_true(True, "sleeve_total=0 raises ValueError")

    # ----- Test 20: realistic operator portfolio (BMNR + LEU + NVDA + MP)
    positions = [
        {"ticker": "BMNR", "market_value": 71500},   # T1 floor 8% → CRIT
        {"ticker": "LEU", "market_value": 96000},    # T1 floor 8% → 5.12% BELOW
        {"ticker": "NVDA", "market_value": 139000},  # T2 ceil 7% → 7.41% ABOVE
        {"ticker": "MP", "market_value": 39680},      # T3 ceil 3% → 2.12% IN_BAND
        {"ticker": "UUUU", "market_value": 43000},    # T3 ceil 3% → 2.29% IN_BAND
    ]
    theses = [
        {"ticker": "BMNR", "tier": "T1", "lane": "Generational", "source": "operator"},
        {"ticker": "LEU", "tier": "T1", "lane": "Generational", "source": "Meridian"},
        {"ticker": "NVDA", "tier": "T2", "lane": "Speed", "source": "Lee"},
        {"ticker": "MP", "tier": "T3", "lane": "Speed", "source": "Meridian"},
        {"ticker": "UUUU", "tier": "T3", "lane": "Speed", "source": "Meridian"},
    ]
    r = calibrate(positions, theses, sleeve_total=1875000)
    assert_eq(len(r.critically_below), 1, "realistic: BMNR critical")
    assert_eq(len(r.below_floor), 1, "realistic: LEU below floor")
    assert_eq(len(r.above_ceiling), 1, "realistic: NVDA above ceiling")
    assert_eq(len(r.in_band), 2, "realistic: MP + UUUU in band")

    total = passed + failed
    print(f"\n{passed}/{total} assertions passed.")
    return failed == 0


# ============================================================================
# CLI
# ============================================================================

def main():
    p = argparse.ArgumentParser(description="Conviction Sizing Calibrator v11.26")
    p.add_argument("--positions", help="Positions JSON")
    p.add_argument("--theses", help="Live Theses JSON")
    p.add_argument("--sleeve-total", type=float, help="Sleeve total $")
    p.add_argument("--macro", help="Macro pulse JSON (optional)")
    p.add_argument("--source-rates", help="Source hit-rate JSON (optional)")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--surface", action="store_true", help="One-line surface")
    p.add_argument("--self-test", action="store_true", help="Self-test")
    args = p.parse_args()

    if args.self_test:
        sys.exit(0 if _self_test() else 1)

    if not (args.positions and args.theses and args.sleeve_total):
        p.error("--positions, --theses, --sleeve-total required (or --self-test)")

    _reject_sample_inputs_path("--positions", args.positions)
    _reject_sample_inputs_path("--theses", args.theses)
    _reject_sample_inputs_path("--macro", args.macro)
    _reject_sample_inputs_path("--source-rates", args.source_rates)

    with open(args.positions) as f:
        positions = json.load(f)
    if isinstance(positions, dict) and "positions" in positions:
        positions = positions["positions"]
    with open(args.theses) as f:
        theses = json.load(f)
    macro = None
    if args.macro:
        with open(args.macro) as f:
            macro = json.load(f)
    rates = None
    if args.source_rates:
        with open(args.source_rates) as f:
            rates = json.load(f)

    r = calibrate(positions, theses, args.sleeve_total, macro, rates)
    if args.surface:
        print(surface_line(r))
    elif args.json:
        print(format_json_report(r))
    else:
        print(format_text_report(r))


if __name__ == "__main__":
    main()
