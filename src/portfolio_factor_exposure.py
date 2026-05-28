#!/usr/bin/env python3
"""
portfolio_factor_exposure.py — v11.26 rebuild

PURPOSE
    Aggregate portfolio exposure by factor tag.  Surface:
      - factor concentration (HHI)
      - effective-N factors  (1/HHI)
      - per-factor sleeve % + ticker list
      - WARNINGS: factors >25% of sleeve
      - SOURCE-FACTOR STACKS: when ≥3 positions of same factor share the same
        named research source (Meridian × Critical Minerals stack — the
        canonical correlation risk surfaced in 5/17 weekend session).

V11.26 ENHANCEMENTS OVER V11.22 ORIGINAL
    1. MACRO-REGIME STACK detector (v11.25): identifies positions that all
       benefit or all suffer from the same macro variable.  Examples:
         - dollar_WEAK tailwind stack: LEU + MP + UUUU + GLD all benefit when
           DXY weakens.  If DXY rallies, coordinated drawdown risk.
         - duration_WEAK headwind stack: NVDA + AMD + MU + MAGS all hurt
           when 10Y rises.
    2. SOURCE × TIER concentration (v11.26): when ≥3 positions are anchored
       on the same Newton/Lee/Meridian/Farrell × tier band, that's
       calibration-risk concentration (single source's hit rate disagreement
       moves a meaningful chunk of the portfolio).
    3. Feeds P-REASONING-ARCH Component 4 (Portfolio Coherence): macro
       regime + factor stacks become explicit inputs.

USAGE
    python portfolio_factor_exposure.py --self-test
    python portfolio_factor_exposure.py --positions P.json --theses T.json \\
        --sleeve-total 1875000 [--macro M.json] [--surface]
"""

import argparse
import json
import sys
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Tuple, Any


# ============================================================================
# CONSTANTS
# ============================================================================

CONCENTRATION_WARN_PCT = 0.25      # factor >25% sleeve → warn
SOURCE_STACK_THRESHOLD = 3         # ≥3 positions share source × factor → stack
MACRO_STACK_THRESHOLD = 3          # ≥3 positions share macro exposure → stack
SOURCE_TIER_CONCENTRATION_PCT = 0.20  # source×tier >20% sleeve → warn

# Map factor tag → which macro variable drives it
# (longhand → which macro state benefits/hurts)
# NB: keys here MUST be lowercase to match normalized regime parsing
MACRO_FACTOR_MAP = {
    # Long-duration growth + AI hurt by rising rates
    "long_duration_growth":   {"duration_weak": "headwind", "duration_strong": "tailwind"},
    "ai_complex":             {"duration_weak": "headwind", "duration_strong": "tailwind"},
    "long_duration":          {"duration_weak": "headwind", "duration_strong": "tailwind"},
    "high_pe":                {"duration_weak": "headwind", "duration_strong": "tailwind"},

    # Critical minerals benefit from dollar weakness, oil/inflation strength
    "critical_minerals":      {"dollar_weak": "tailwind", "dollar_strong": "headwind",
                               "inflation_persistent": "tailwind"},
    "rare_earth":             {"dollar_weak": "tailwind", "dollar_strong": "headwind"},
    "uranium":                {"dollar_weak": "tailwind", "dollar_strong": "headwind"},
    "nuclear":                {"dollar_weak": "tailwind", "dollar_strong": "headwind"},
    "gold":                   {"dollar_weak": "tailwind", "dollar_strong": "headwind",
                               "real_yield_low": "tailwind"},

    # Crypto / ETH inversely correlated with real rates
    "crypto":                 {"real_yield_low": "tailwind", "real_yield_high": "headwind"},
    "eth":                    {"real_yield_low": "tailwind", "real_yield_high": "headwind"},

    # Cyclicals + financials benefit from curve steepening
    "cyclicals":              {"curve_steepening": "tailwind", "curve_flattening": "headwind"},
    "financials":             {"curve_steepening": "tailwind", "curve_flattening": "headwind"},

    # Energy + oil services
    "energy":                 {"inflation_persistent": "tailwind"},
    "oil_services":           {"inflation_persistent": "tailwind"},

    # Global exporters hurt by strong dollar
    "global_exporter":        {"dollar_weak": "tailwind", "dollar_strong": "headwind"},
}

# Display-case mapping: lowercase key → preferred display form
MACRO_DISPLAY_CASE = {
    "duration_weak":         "duration_WEAK",
    "duration_strong":       "duration_STRONG",
    "dollar_weak":           "dollar_WEAK",
    "dollar_strong":         "dollar_STRONG",
    "real_yield_low":        "real_yield_LOW",
    "real_yield_high":       "real_yield_HIGH",
    "curve_steepening":      "curve_STEEPENING",
    "curve_flattening":      "curve_FLATTENING",
    "inflation_persistent":  "inflation_PERSISTENT",
}


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class FactorAggregate:
    factor: str
    total_value: float
    pct_of_sleeve: float
    tickers: List[str] = field(default_factory=list)
    by_source: Dict[str, float] = field(default_factory=dict)  # source -> value


@dataclass
class SourceFactorStack:
    source: str
    factor: str
    total_value: float
    pct_of_sleeve: float
    tickers: List[str]
    n_positions: int


@dataclass
class MacroRegimeStack:
    macro_state: str          # e.g., "dollar_STRONG"
    direction: str            # "headwind" or "tailwind"
    total_value: float
    pct_of_sleeve: float
    tickers: List[str]
    factors_involved: List[str]


@dataclass
class SourceTierConcentration:
    source: str
    tier: str
    total_value: float
    pct_of_sleeve: float
    tickers: List[str]


@dataclass
class FactorReport:
    sleeve_total: float
    factor_aggregates: List[FactorAggregate] = field(default_factory=list)
    hhi: float = 0.0
    effective_n_factors: float = 0.0
    concentration_warnings: List[str] = field(default_factory=list)
    source_factor_stacks: List[SourceFactorStack] = field(default_factory=list)
    macro_regime_stacks: List[MacroRegimeStack] = field(default_factory=list)
    source_tier_concentrations: List[SourceTierConcentration] = field(default_factory=list)
    summary: str = ""


# ============================================================================
# CORE LOGIC
# ============================================================================

def _aggregate_factors(positions: List[Dict], theses: List[Dict],
                       sleeve_total: float) -> Dict[str, FactorAggregate]:
    """
    Build factor aggregates from positions + theses.
    """
    # Map ticker -> aggregate value, source, tier, factor_tags
    by_ticker: Dict[str, Dict] = {}
    for p in positions:
        t = (p.get("ticker") or "").upper().strip()
        if not t:
            continue
        if t not in by_ticker:
            by_ticker[t] = {"value": 0.0, "source": None, "tier": None, "factors": []}
        by_ticker[t]["value"] += float(p.get("market_value", 0) or 0)

    # Enrich with thesis data
    for th in theses:
        t = (th.get("ticker") or "").upper().strip()
        if t in by_ticker:
            by_ticker[t]["source"] = th.get("source") or th.get("source_at_entry")
            by_ticker[t]["tier"] = (th.get("tier") or "").upper()
            by_ticker[t]["factors"] = th.get("factor_tags") or []

    # Aggregate by factor
    factor_map: Dict[str, FactorAggregate] = {}
    for ticker, info in by_ticker.items():
        for factor in info["factors"]:
            f = factor.strip().lower()
            if not f:
                continue
            if f not in factor_map:
                factor_map[f] = FactorAggregate(
                    factor=f, total_value=0.0, pct_of_sleeve=0.0
                )
            factor_map[f].total_value += info["value"]
            if ticker not in factor_map[f].tickers:
                factor_map[f].tickers.append(ticker)
            if info["source"]:
                factor_map[f].by_source[info["source"]] = (
                    factor_map[f].by_source.get(info["source"], 0.0) + info["value"]
                )

    for f, agg in factor_map.items():
        agg.pct_of_sleeve = agg.total_value / sleeve_total

    return factor_map, by_ticker


def _detect_source_factor_stacks(factor_map: Dict[str, FactorAggregate],
                                 by_ticker: Dict[str, Dict],
                                 sleeve_total: float
                                 ) -> List[SourceFactorStack]:
    """
    For each (source, factor) combo, count positions; if ≥3, surface as stack.
    """
    # Build (source, factor) -> list of (ticker, value)
    sf_map: Dict[Tuple[str, str], List[Tuple[str, float]]] = {}
    for ticker, info in by_ticker.items():
        s = info["source"]
        if not s:
            continue
        for f in info["factors"]:
            key = (s, f.strip().lower())
            sf_map.setdefault(key, []).append((ticker, info["value"]))

    stacks = []
    for (source, factor), items in sf_map.items():
        if len(items) >= SOURCE_STACK_THRESHOLD:
            total = sum(v for _, v in items)
            stacks.append(SourceFactorStack(
                source=source,
                factor=factor,
                total_value=total,
                pct_of_sleeve=total / sleeve_total,
                tickers=[t for t, _ in items],
                n_positions=len(items),
            ))
    stacks.sort(key=lambda s: s.total_value, reverse=True)
    return stacks


def _detect_macro_stacks(factor_map: Dict[str, FactorAggregate],
                         by_ticker: Dict[str, Dict],
                         sleeve_total: float,
                         macro_pulse: Optional[Dict]
                         ) -> List[MacroRegimeStack]:
    """
    v11.26: For each macro state (e.g., dollar_STRONG), gather all positions
    whose factor tags map to a known headwind/tailwind under that state.
    If ≥3 positions share exposure, surface as macro stack.
    """
    if not macro_pulse:
        return []

    # Determine which macro states are currently in play
    regime_str = (macro_pulse.get("regime_label")
                  or macro_pulse.get("regime") or "").lower()
    if not regime_str:
        return []

    # Extract substrings like duration_weak, dollar_strong, etc.
    # Convention: macro states use UNDERSCORE_separated tokens
    active_states = set()
    for token in regime_str.replace(" ", "").replace("·", "_").split("_"):
        # No-op: try matching pairs from regime tokens by scanning known states
        pass
    # Better: scan known macro keys in MACRO_FACTOR_MAP for any that appear
    known_states = set()
    for factor, mapping in MACRO_FACTOR_MAP.items():
        for state in mapping:
            known_states.add(state.lower())
    for state in known_states:
        if state.lower() in regime_str.lower():
            active_states.add(state)

    if not active_states:
        return []

    # For each active state, find positions exposed
    state_to_positions: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for ticker, info in by_ticker.items():
        for factor in info["factors"]:
            f = factor.strip().lower()
            mapping = MACRO_FACTOR_MAP.get(f)
            if not mapping:
                continue
            for state in active_states:
                direction = mapping.get(state)
                if not direction:
                    continue
                key = (state, direction)
                if key not in state_to_positions:
                    state_to_positions[key] = {
                        "tickers": [], "value": 0.0, "factors": set()
                    }
                if ticker not in state_to_positions[key]["tickers"]:
                    state_to_positions[key]["tickers"].append(ticker)
                    state_to_positions[key]["value"] += info["value"]
                state_to_positions[key]["factors"].add(f)

    stacks = []
    for (state, direction), data in state_to_positions.items():
        if len(data["tickers"]) >= MACRO_STACK_THRESHOLD:
            display_state = MACRO_DISPLAY_CASE.get(state, state)
            stacks.append(MacroRegimeStack(
                macro_state=display_state,
                direction=direction,
                total_value=data["value"],
                pct_of_sleeve=data["value"] / sleeve_total,
                tickers=data["tickers"],
                factors_involved=sorted(data["factors"]),
            ))
    # Sort by largest stack first
    stacks.sort(key=lambda s: s.total_value, reverse=True)
    return stacks


def _detect_source_tier_concentration(by_ticker: Dict[str, Dict],
                                      sleeve_total: float
                                      ) -> List[SourceTierConcentration]:
    """
    v11.26: aggregate by (source, tier) — if any bucket >20% of sleeve, surface.
    """
    st_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for ticker, info in by_ticker.items():
        s = info["source"]
        tier = info["tier"]
        if not s or not tier:
            continue
        key = (s, tier)
        if key not in st_map:
            st_map[key] = {"tickers": [], "value": 0.0}
        if ticker not in st_map[key]["tickers"]:
            st_map[key]["tickers"].append(ticker)
            st_map[key]["value"] += info["value"]

    concentrations = []
    for (source, tier), data in st_map.items():
        pct = data["value"] / sleeve_total
        if pct >= SOURCE_TIER_CONCENTRATION_PCT:
            concentrations.append(SourceTierConcentration(
                source=source, tier=tier,
                total_value=data["value"], pct_of_sleeve=pct,
                tickers=data["tickers"]
            ))
    concentrations.sort(key=lambda c: c.total_value, reverse=True)
    return concentrations


def _compute_hhi_and_neff(factor_map: Dict[str, FactorAggregate]
                          ) -> Tuple[float, float]:
    """
    Herfindahl-Hirschman Index and effective-N factors.

    HHI = sum(share_i^2) where share_i is each factor's share of total
    factor-tagged value.  Effective N = 1 / HHI.
    """
    total = sum(a.total_value for a in factor_map.values())
    if total <= 0:
        return 0.0, 0.0
    hhi = sum((a.total_value / total) ** 2 for a in factor_map.values())
    if hhi <= 0:
        return 0.0, 0.0
    return hhi, 1.0 / hhi


def analyze(positions: List[Dict], theses: List[Dict],
            sleeve_total: float,
            macro_pulse: Optional[Dict] = None) -> FactorReport:
    if sleeve_total <= 0:
        raise ValueError("sleeve_total must be > 0")

    factor_map, by_ticker = _aggregate_factors(positions, theses, sleeve_total)
    hhi, n_eff = _compute_hhi_and_neff(factor_map)

    # Concentration warnings
    warnings = []
    for f, agg in factor_map.items():
        if agg.pct_of_sleeve >= CONCENTRATION_WARN_PCT:
            warnings.append(
                f"{f}: {agg.pct_of_sleeve*100:.1f}% sleeve "
                f"({len(agg.tickers)} tickers)"
            )

    source_stacks = _detect_source_factor_stacks(factor_map, by_ticker, sleeve_total)
    macro_stacks = _detect_macro_stacks(factor_map, by_ticker, sleeve_total, macro_pulse)
    source_tier_conc = _detect_source_tier_concentration(by_ticker, sleeve_total)

    # Sort factor aggregates by size
    aggregates_sorted = sorted(factor_map.values(),
                               key=lambda a: a.total_value, reverse=True)

    report = FactorReport(
        sleeve_total=sleeve_total,
        factor_aggregates=aggregates_sorted,
        hhi=hhi,
        effective_n_factors=n_eff,
        concentration_warnings=warnings,
        source_factor_stacks=source_stacks,
        macro_regime_stacks=macro_stacks,
        source_tier_concentrations=source_tier_conc,
    )

    n_factors = sum(1 for a in factor_map.values() if a.pct_of_sleeve >= 0.01)
    report.summary = (
        f"{n_factors} factors ≥1% sleeve, "
        f"{len(warnings)} concentration warning(s), "
        f"{len(source_stacks)} source-factor stack(s), "
        f"{len(macro_stacks)} macro-regime stack(s), "
        f"{len(source_tier_conc)} source×tier concentration(s). "
        f"Effective-N = {n_eff:.1f} factors."
    )
    return report


# ============================================================================
# OUTPUT FORMATTERS
# ============================================================================

def format_text_report(r: FactorReport) -> str:
    out = []
    out.append("=" * 70)
    out.append("PORTFOLIO FACTOR EXPOSURE")
    out.append("=" * 70)
    out.append(r.summary)
    out.append(f"HHI = {r.hhi:.4f}   Effective-N factors = {r.effective_n_factors:.2f}")
    out.append("")

    if r.factor_aggregates:
        out.append("-- FACTOR AGGREGATES " + "-" * 50)
        for a in r.factor_aggregates:
            if a.pct_of_sleeve < 0.005:
                continue
            out.append(f"  {a.factor:32}  {a.pct_of_sleeve*100:5.2f}%  "
                       f"${a.total_value:>10,.0f}  ({len(a.tickers)} tickers)")
            out.append(f"        tickers: {', '.join(a.tickers)}")
        out.append("")

    if r.concentration_warnings:
        out.append("-- CONCENTRATION WARNINGS (>25% sleeve) " + "-" * 30)
        for w in r.concentration_warnings:
            out.append(f"  ⚠️  {w}")
        out.append("")

    if r.source_factor_stacks:
        out.append(f"-- SOURCE-FACTOR STACKS (≥{SOURCE_STACK_THRESHOLD} positions "
                   "share source × factor) " + "-" * 5)
        for s in r.source_factor_stacks:
            out.append(f"  📍 {s.source} × {s.factor}: "
                       f"${s.total_value:,.0f} ({s.pct_of_sleeve*100:.1f}% sleeve), "
                       f"n={s.n_positions}")
            out.append(f"        tickers: {', '.join(s.tickers)}")
        out.append("")

    if r.macro_regime_stacks:
        out.append(f"-- MACRO-REGIME STACKS (≥{MACRO_STACK_THRESHOLD} positions "
                   "share macro exposure) " + "-" * 5)
        for s in r.macro_regime_stacks:
            symbol = "🟢" if s.direction == "tailwind" else "🔴"
            out.append(f"  {symbol} {s.macro_state} ({s.direction}): "
                       f"${s.total_value:,.0f} "
                       f"({s.pct_of_sleeve*100:.1f}% sleeve), "
                       f"n={len(s.tickers)}")
            out.append(f"        tickers: {', '.join(s.tickers)}")
            out.append(f"        factors: {', '.join(s.factors_involved)}")
        out.append("")

    if r.source_tier_concentrations:
        out.append(f"-- SOURCE×TIER CONCENTRATIONS "
                   f"(>{SOURCE_TIER_CONCENTRATION_PCT*100:.0f}% sleeve) "
                   + "-" * 20)
        for c in r.source_tier_concentrations:
            out.append(f"  📊 {c.source} × {c.tier}: "
                       f"${c.total_value:,.0f} ({c.pct_of_sleeve*100:.1f}% sleeve)")
            out.append(f"        tickers: {', '.join(c.tickers)}")
        out.append("")

    return "\n".join(out)


def format_json_report(r: FactorReport) -> str:
    return json.dumps(asdict(r), indent=2, default=str)


def surface_line(r: FactorReport) -> str:
    n_warn = len(r.concentration_warnings)
    n_src = len(r.source_factor_stacks)
    n_macro = len(r.macro_regime_stacks)
    n_st = len(r.source_tier_concentrations)
    n_factors = sum(1 for a in r.factor_aggregates if a.pct_of_sleeve >= 0.01)
    return (f"FACTOR EXPOSURE: {n_factors} factors ≥1% sleeve, "
            f"{n_warn} concentration warning(s), "
            f"{n_src} source-factor stack(s), "
            f"{n_macro} macro-regime stack(s), "
            f"{n_st} source×tier concentration(s). "
            f"Effective-N = {r.effective_n_factors:.1f} factors.")


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

    # ----- Test 1: basic single-factor aggregation
    positions = [{"ticker": "BMNR", "market_value": 71500}]
    theses = [{"ticker": "BMNR", "tier": "T1", "source": "operator",
               "factor_tags": ["crypto", "eth"]}]
    r = analyze(positions, theses, sleeve_total=1875000)
    assert_eq(len(r.factor_aggregates), 2, "two factors for BMNR (crypto + eth)")
    assert_close(r.factor_aggregates[0].total_value, 71500, "crypto value", 1)
    assert_close(r.factor_aggregates[0].pct_of_sleeve * 100, 3.81, "crypto pct", 0.05)

    # ----- Test 2: cross-ticker factor aggregation
    positions = [
        {"ticker": "LEU", "market_value": 96000},
        {"ticker": "MP", "market_value": 39680},
        {"ticker": "UUUU", "market_value": 43000},
    ]
    theses = [
        {"ticker": "LEU", "tier": "T1", "source": "Meridian",
         "factor_tags": ["critical_minerals", "nuclear"]},
        {"ticker": "MP", "tier": "T3", "source": "Meridian",
         "factor_tags": ["critical_minerals", "rare_earth"]},
        {"ticker": "UUUU", "tier": "T3", "source": "Meridian",
         "factor_tags": ["critical_minerals", "uranium"]},
    ]
    r = analyze(positions, theses, sleeve_total=1875000)
    crit_min_agg = next(a for a in r.factor_aggregates if a.factor == "critical_minerals")
    assert_close(crit_min_agg.total_value, 178680, "critical_minerals total", 1)
    assert_eq(len(crit_min_agg.tickers), 3, "critical_minerals: 3 tickers")

    # ----- Test 3: source-factor stack detection (canonical Meridian × Crit Min)
    assert_eq(len(r.source_factor_stacks), 1,
              "one source-factor stack (Meridian × critical_minerals)")
    stack = r.source_factor_stacks[0]
    assert_eq(stack.source, "Meridian", "stack source")
    assert_eq(stack.factor, "critical_minerals", "stack factor")
    assert_eq(stack.n_positions, 3, "stack n_positions")
    assert_close(stack.total_value, 178680, "stack value", 1)

    # ----- Test 4: HHI computation
    positions = [{"ticker": "A", "market_value": 100000}]
    theses = [{"ticker": "A", "factor_tags": ["AI_complex"]}]
    r = analyze(positions, theses, sleeve_total=1000000)
    # Single factor → HHI = 1.0, effective N = 1.0
    assert_close(r.hhi, 1.0, "single-factor HHI", 0.001)
    assert_close(r.effective_n_factors, 1.0, "single-factor effective_n", 0.001)

    # ----- Test 5: HHI with multiple equal factors
    positions = [
        {"ticker": "A", "market_value": 100000},
        {"ticker": "B", "market_value": 100000},
        {"ticker": "C", "market_value": 100000},
        {"ticker": "D", "market_value": 100000},
    ]
    theses = [
        {"ticker": "A", "factor_tags": ["f1"]},
        {"ticker": "B", "factor_tags": ["f2"]},
        {"ticker": "C", "factor_tags": ["f3"]},
        {"ticker": "D", "factor_tags": ["f4"]},
    ]
    r = analyze(positions, theses, sleeve_total=1000000)
    # 4 equal factors → HHI = 4 * 0.25^2 = 0.25, effective N = 4
    assert_close(r.hhi, 0.25, "4 equal factors HHI", 0.001)
    assert_close(r.effective_n_factors, 4.0, "4 equal factors effective_n", 0.01)

    # ----- Test 6: concentration warning at >25%
    positions = [
        {"ticker": "A", "market_value": 300000},  # 30%
        {"ticker": "B", "market_value": 100000},
    ]
    theses = [
        {"ticker": "A", "factor_tags": ["AI_complex"]},
        {"ticker": "B", "factor_tags": ["other"]},
    ]
    r = analyze(positions, theses, sleeve_total=1000000)
    assert_eq(len(r.concentration_warnings), 1, "1 concentration warning at 30%")
    assert_true("ai_complex" in r.concentration_warnings[0].lower(),
                "warning mentions ai_complex (case-insensitive)")

    # ----- Test 7: macro stack — dollar_STRONG headwind on crit minerals
    positions = [
        {"ticker": "LEU", "market_value": 96000},
        {"ticker": "MP", "market_value": 39680},
        {"ticker": "UUUU", "market_value": 43000},
    ]
    theses = [
        {"ticker": "LEU", "source": "Meridian", "factor_tags": ["critical_minerals"]},
        {"ticker": "MP", "source": "Meridian", "factor_tags": ["critical_minerals"]},
        {"ticker": "UUUU", "source": "Meridian", "factor_tags": ["critical_minerals"]},
    ]
    macro = {"regime_label": "dollar_STRONG · duration_NORMAL"}
    r = analyze(positions, theses, sleeve_total=1875000, macro_pulse=macro)
    # Should detect dollar_STRONG headwind stack
    dollar_stacks = [s for s in r.macro_regime_stacks if s.macro_state == "dollar_STRONG"]
    assert_eq(len(dollar_stacks), 1, "dollar_STRONG headwind stack detected")
    assert_eq(dollar_stacks[0].direction, "headwind", "stack direction headwind")
    assert_eq(len(dollar_stacks[0].tickers), 3, "stack: 3 tickers")

    # ----- Test 8: macro stack — duration_WEAK headwind on AI
    positions = [
        {"ticker": "NVDA", "market_value": 100000},
        {"ticker": "AMD", "market_value": 80000},
        {"ticker": "MU", "market_value": 50000},
    ]
    theses = [
        {"ticker": "NVDA", "factor_tags": ["AI_complex", "long_duration_growth"]},
        {"ticker": "AMD", "factor_tags": ["AI_complex"]},
        {"ticker": "MU", "factor_tags": ["AI_complex"]},
    ]
    macro = {"regime_label": "duration_WEAK"}
    r = analyze(positions, theses, sleeve_total=1000000, macro_pulse=macro)
    duration_stacks = [s for s in r.macro_regime_stacks
                       if s.macro_state == "duration_WEAK"]
    assert_true(len(duration_stacks) >= 1,
                "duration_WEAK headwind on AI complex")

    # ----- Test 9: source-tier concentration (>20%)
    positions = [
        {"ticker": "LEU", "market_value": 96000},
        {"ticker": "BMNR", "market_value": 71500},
        # add more Meridian × T1 positions to exceed 20%
        {"ticker": "X1", "market_value": 100000},
        {"ticker": "X2", "market_value": 150000},
    ]
    theses = [
        {"ticker": "LEU", "source": "Meridian", "tier": "T1",
         "factor_tags": ["nuclear"]},
        {"ticker": "BMNR", "source": "Meridian", "tier": "T1",
         "factor_tags": ["crypto"]},
        {"ticker": "X1", "source": "Meridian", "tier": "T1",
         "factor_tags": ["other"]},
        {"ticker": "X2", "source": "Meridian", "tier": "T1",
         "factor_tags": ["other"]},
    ]
    r = analyze(positions, theses, sleeve_total=1875000)
    # Total Meridian × T1 = 417,500 = 22.3% of 1875000
    st_concs = [c for c in r.source_tier_concentrations
                if c.source == "Meridian" and c.tier == "T1"]
    assert_true(len(st_concs) == 1, "Meridian × T1 concentration surfaced")
    assert_close(st_concs[0].pct_of_sleeve * 100, 22.27,
                 "Meridian × T1 pct", 0.5)

    # ----- Test 10: missing factor_tags handled gracefully
    positions = [{"ticker": "X", "market_value": 50000}]
    theses = [{"ticker": "X"}]  # no factor_tags
    r = analyze(positions, theses, sleeve_total=1000000)
    assert_eq(len(r.factor_aggregates), 0, "no factors when factor_tags missing")
    # Should not crash
    assert_eq(r.hhi, 0.0, "HHI = 0 when no factors")

    # ----- Test 11: empty inputs
    r = analyze([], [], sleeve_total=1000000)
    assert_eq(len(r.factor_aggregates), 0, "empty: no factors")
    assert_eq(len(r.source_factor_stacks), 0, "empty: no stacks")

    # ----- Test 12: factor case-insensitive
    positions = [{"ticker": "X", "market_value": 50000}]
    theses = [{"ticker": "X", "factor_tags": ["Critical_Minerals", "CRITICAL_MINERALS",
                                              "critical_minerals"]}]
    r = analyze(positions, theses, sleeve_total=1000000)
    # Should dedupe via lowercase
    crit_aggs = [a for a in r.factor_aggregates if a.factor == "critical_minerals"]
    assert_eq(len(crit_aggs), 1, "factor case normalized")

    # ----- Test 13: cross-account aggregation
    positions = [
        {"ticker": "LEU", "market_value": 50000, "account": "A"},
        {"ticker": "LEU", "market_value": 46000, "account": "B"},
    ]
    theses = [{"ticker": "LEU", "factor_tags": ["nuclear"]}]
    r = analyze(positions, theses, sleeve_total=1000000)
    nuc_agg = next(a for a in r.factor_aggregates if a.factor == "nuclear")
    assert_close(nuc_agg.total_value, 96000, "LEU cross-account aggregated", 1)

    # ----- Test 14: source-factor stack threshold = 3 (not 2)
    positions = [
        {"ticker": "A", "market_value": 10000},
        {"ticker": "B", "market_value": 10000},
    ]
    theses = [
        {"ticker": "A", "source": "Meridian", "factor_tags": ["x"]},
        {"ticker": "B", "source": "Meridian", "factor_tags": ["x"]},
    ]
    r = analyze(positions, theses, sleeve_total=1000000)
    assert_eq(len(r.source_factor_stacks), 0, "2 positions ≠ stack")

    # ----- Test 15: format_text_report runs
    positions = [
        {"ticker": "LEU", "market_value": 96000},
        {"ticker": "MP", "market_value": 39680},
        {"ticker": "UUUU", "market_value": 43000},
    ]
    theses = [
        {"ticker": "LEU", "source": "Meridian", "factor_tags": ["critical_minerals"]},
        {"ticker": "MP", "source": "Meridian", "factor_tags": ["critical_minerals"]},
        {"ticker": "UUUU", "source": "Meridian", "factor_tags": ["critical_minerals"]},
    ]
    r = analyze(positions, theses, sleeve_total=1875000)
    text = format_text_report(r)
    assert_true("PORTFOLIO FACTOR EXPOSURE" in text, "text report header")
    assert_true("Meridian" in text, "text report mentions Meridian")
    assert_true("critical_minerals" in text, "text report mentions critical_minerals")

    # ----- Test 16: surface_line format
    line = surface_line(r)
    assert_true("FACTOR EXPOSURE" in line, "surface_line label")
    assert_true("source-factor stack" in line, "surface_line stack")

    # ----- Test 17: JSON output
    js = format_json_report(r)
    parsed = json.loads(js)
    assert_eq(parsed["sleeve_total"], 1875000, "JSON sleeve_total")
    assert_true(len(parsed["source_factor_stacks"]) >= 1, "JSON has stacks")

    # ----- Test 18: invalid sleeve_total raises
    try:
        analyze([], [], sleeve_total=-1)
        assert_true(False, "negative sleeve_total should raise")
    except ValueError:
        assert_true(True, "negative sleeve_total raises")

    # ----- Test 19: realistic top-7 portfolio (canonical 5/17 weekend result)
    positions = [
        {"ticker": "SMH", "market_value": 177000},
        {"ticker": "GRNY", "market_value": 171000},
        {"ticker": "MAGS", "market_value": 171000},
        {"ticker": "NVDA", "market_value": 139000},
        {"ticker": "GRNJ", "market_value": 135000},
        {"ticker": "LEU", "market_value": 96000},
        {"ticker": "IGV", "market_value": 87000},
    ]
    theses = [
        {"ticker": "SMH", "source": "Lee", "tier": "T2",
         "factor_tags": ["AI_complex", "semiconductors"]},
        {"ticker": "GRNY", "source": "Lee", "tier": "T1",
         "factor_tags": ["AI_complex"]},
        {"ticker": "MAGS", "source": "Lee", "tier": "T2",
         "factor_tags": ["AI_complex", "long_duration_growth"]},
        {"ticker": "NVDA", "source": "Lee", "tier": "T2",
         "factor_tags": ["AI_complex", "semiconductors"]},
        {"ticker": "GRNJ", "source": "Lee", "tier": "T2",
         "factor_tags": ["AI_complex"]},
        {"ticker": "LEU", "source": "Meridian", "tier": "T1",
         "factor_tags": ["critical_minerals", "nuclear"]},
        {"ticker": "IGV", "source": "Lee", "tier": "T3",
         "factor_tags": ["software", "AI_complex"]},
    ]
    r = analyze(positions, theses, sleeve_total=1875000)
    # AI_complex should be dominant
    ai_agg = next((a for a in r.factor_aggregates if a.factor == "ai_complex"), None)
    assert_true(ai_agg is not None, "ai_complex factor present in top-7")
    assert_true(ai_agg.pct_of_sleeve > 0.25,
                "ai_complex >25% sleeve in top-7")
    # Lee × ai_complex should be a stack
    lee_ai_stacks = [s for s in r.source_factor_stacks
                     if s.source == "Lee" and "ai" in s.factor]
    assert_true(len(lee_ai_stacks) >= 1, "Lee × ai_complex stack detected")

    # ----- Test 20: macro stack false-positive prevention
    positions = [
        {"ticker": "A", "market_value": 10000},
        {"ticker": "B", "market_value": 10000},
    ]
    theses = [
        {"ticker": "A", "factor_tags": ["critical_minerals"]},
        {"ticker": "B", "factor_tags": ["critical_minerals"]},
    ]
    macro = {"regime_label": "dollar_STRONG"}
    r = analyze(positions, theses, sleeve_total=1000000, macro_pulse=macro)
    assert_eq(len(r.macro_regime_stacks), 0,
              "2 positions on same macro ≠ stack")

    total = passed + failed
    print(f"\n{passed}/{total} assertions passed.")
    return failed == 0


# ============================================================================
# CLI
# ============================================================================

def main():
    p = argparse.ArgumentParser(description="Portfolio Factor Exposure v11.26")
    p.add_argument("--positions", help="Positions JSON")
    p.add_argument("--theses", help="Live Theses JSON")
    p.add_argument("--sleeve-total", type=float, help="Sleeve total")
    p.add_argument("--macro", help="Macro pulse JSON")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--surface", action="store_true", help="Surface line")
    p.add_argument("--self-test", action="store_true", help="Self-test")
    args = p.parse_args()

    if args.self_test:
        sys.exit(0 if _self_test() else 1)

    if not (args.positions and args.theses and args.sleeve_total):
        p.error("--positions, --theses, --sleeve-total required (or --self-test)")

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

    r = analyze(positions, theses, args.sleeve_total, macro)
    if args.surface:
        print(surface_line(r))
    elif args.json:
        print(format_json_report(r))
    else:
        print(format_text_report(r))


if __name__ == "__main__":
    main()
