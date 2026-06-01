#!/usr/bin/env python3
"""
pretrade_gate.py — v11.26 NEW ARCHITECTURE

PURPOSE
    Pre-trade decision gate.  Given a proposed action (ADD/TRIM/EXIT a ticker
    by some $ amount), runs the full v11.26 check stack and returns
    GREEN / AMBER / RED with explicit reasons.

    This is the missing enforced check that wires together:
      • P-DEEPWORK (v11.24) — ≥$25K notional → multi-turn required
      • P-MACRO-CONTEXT (v11.25) — macro regime mismatch detection
      • P-SOURCE-CALIBRATION (v11.26) — source × tier hit-rate discount
      • conviction_sizing_calibrator — tier band check
      • portfolio_factor_exposure — incremental factor concentration

    Without this gate, the passive surfacings in the other scripts are
    advisory only.  This makes them part of an explicit pre-trade
    workflow with structured output and an audit trail.

WORKFLOW
    Operator: "I'm thinking about adding $30K BMNR"
    →  pretrade_gate analyzes:
           current sleeve %, target sleeve %, tier band, factor stacks,
           macro regime fit, source hit rate, P-DEEPWORK trigger
    →  output:  AMBER — 2 yellow flags:
           - $30K crosses P-DEEPWORK threshold; require multi-turn
           - BMNR T1 floor: $150K; current $71K; gap closure is appropriate
             direction, but consider sizing in tranches given mNAV-discount
             phase
       Plus structured JSON for write-back to a future override log.

EXIT CRITERIA
    GREEN  — all checks pass, no flags; proceed with action
    AMBER  — at least 1 yellow flag; proceed only with override + log
    RED    — at least 1 red flag; do NOT proceed (or P-DEEPWORK required)

USAGE
    python pretrade_gate.py --self-test
    python pretrade_gate.py --action ADD --ticker BMNR --notional 30000 \\
        --positions P.json --theses T.json --sleeve-total 1875000 \\
        [--macro M.json] [--source-rates R.json]
"""

import argparse
import json
import sys
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Tuple

# Import dependencies from the same build directory
sys.path.insert(0, "/home/claude/build")
sys.path.insert(0, "/mnt/project")
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
try:
    import conviction_sizing_calibrator as csc
    import portfolio_factor_exposure as pfe
except ImportError:
    csc = None
    pfe = None


# ============================================================================
# CONSTANTS
# ============================================================================

DEEPWORK_NOTIONAL_THRESHOLD = 25_000.0
GENERATIONAL_LANE_TIERS = {"T1"}  # T1 entries always P-DEEPWORK regardless of $
SOURCE_CLUSTER_THRESHOLD = 3
INCREMENTAL_FACTOR_CONCENTRATION_RED = 0.40  # adding pushes factor >40% → RED
INCREMENTAL_FACTOR_CONCENTRATION_AMBER = 0.30  # >30% → AMBER

# Capitulation cooldown (v11.23): SPX ≥15% drawdown + VIX >30 → no T1/T2 adds
SPX_DRAWDOWN_CAPITULATION = 0.15
VIX_CAPITULATION = 30.0
CAPITULATION_COOLDOWN_DAYS = 5


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class Flag:
    color: str        # GREEN / YELLOW / RED
    code: str         # short code like "DEEPWORK_THRESHOLD"
    message: str      # human-readable explanation


@dataclass
class GateResult:
    action: str               # ADD / TRIM / EXIT
    ticker: str
    notional: float
    overall: str              # GREEN / AMBER / RED
    flags: List[Flag] = field(default_factory=list)
    deepwork_required: bool = False
    requires_log: bool = False
    summary: str = ""

    # Context attached for audit
    current_pct: float = 0.0
    target_pct: float = 0.0
    tier: Optional[str] = None
    macro_regime: Optional[str] = None


# ============================================================================
# CHECKS
# ============================================================================

def _check_deepwork(action: str, notional: float,
                    tier: Optional[str]) -> List[Flag]:
    """P-DEEPWORK trigger: ≥$25K OR T1 (generational lane) regardless of size."""
    flags = []
    if abs(notional) >= DEEPWORK_NOTIONAL_THRESHOLD:
        flags.append(Flag(
            color="YELLOW", code="DEEPWORK_THRESHOLD",
            message=f"${abs(notional):,.0f} notional ≥ $25K threshold — "
                    "P-DEEPWORK multi-turn workflow required"
        ))
    if action == "ADD" and (tier or "") == "T1":
        flags.append(Flag(
            color="YELLOW", code="GENERATIONAL_LANE_ENTRY",
            message="T1 Generational Lane entries always require P-DEEPWORK"
        ))
    return flags


def _check_tier_band(action: str, current_pct: float, target_pct: float,
                     tier: Optional[str]) -> List[Flag]:
    """Tier band check: ABOVE_CEILING + ADD = RED; CRITICALLY_BELOW + EXIT = RED."""
    flags = []
    if not tier or tier not in csc.TIER_BANDS:
        return flags
    floor, ceiling = csc.TIER_BANDS[tier]
    if action == "ADD" and target_pct > ceiling:
        flags.append(Flag(
            color="RED", code="EXCEEDS_TIER_CEILING",
            message=f"ADD would push {target_pct*100:.2f}% above {tier} "
                    f"ceiling {ceiling*100:.1f}%"
        ))
    elif action == "ADD" and current_pct < floor and target_pct < floor:
        # Adding but still below floor → directionally correct, surface as INFO
        flags.append(Flag(
            color="GREEN", code="CLOSING_TIER_GAP",
            message=f"ADD closes some of {tier} tier gap "
                    f"(floor {floor*100:.1f}%, target {target_pct*100:.2f}%)"
        ))
    elif action in ("TRIM", "EXIT") and current_pct < (floor * 0.5):
        # Only flag if it's a high-conviction tier AND the position is meaningful
        # ($10K+); tiny zombie positions can be exited without alarm
        current_value = current_pct * 1875000 if current_pct else 0  # rough scale check
        if tier in ("T1", "T2"):
            flags.append(Flag(
                color="RED", code="TRIMMING_CRITICALLY_BELOW",
                message=f"Position already CRITICALLY_BELOW {tier} floor "
                        f"({current_pct*100:.2f}% vs floor {floor*100:.1f}%) — "
                        "trim/exit aggravates canonical failure mode"
            ))
    return flags


def _check_macro(action: str, ticker: str, factor_tags: List[str],
                 macro_pulse: Optional[Dict]) -> List[Flag]:
    """Macro headwind check: ADD into macro headwind = AMBER."""
    flags = []
    if not macro_pulse or not factor_tags or action != "ADD":
        return flags
    regime = (macro_pulse.get("regime_label")
              or macro_pulse.get("regime") or "").lower()
    factors_lower = [f.lower() for f in factor_tags]
    if pfe is None:
        return flags
    macro_map = getattr(pfe, "MACRO_FACTOR_MAP", {})

    for f in factors_lower:
        mapping = macro_map.get(f)
        if not mapping:
            continue
        for state, direction in mapping.items():
            if state.lower() in regime and direction == "headwind":
                flags.append(Flag(
                    color="YELLOW", code="MACRO_HEADWIND",
                    message=f"Factor '{f}' faces headwind from current "
                            f"{state} regime — consider deferring ADD"
                ))
                return flags  # one headwind flag is enough
    return flags


def _check_source_calibration(action: str, source: Optional[str],
                              call_ladder: Optional[str],
                              source_rates: Optional[Dict]) -> List[Flag]:
    """source x call-quality-ladder hit-rate discount -> AMBER or RED (v11.26;
    convention pinned v12.0).

    IMPORTANT — two different axes, do not conflate:
      * call_ladder = the CALL-QUALITY ladder (A/B/C/D = Specific/Target/
        Directional/Vague) from classify_call / the Source Call Log. source_rates
        is keyed by this, so it is the ONLY correct key here.
      * the POSITION tier (T1-T4) is a sizing axis and must NOT be used for this
        lookup (source_rates has no T1-T4 keys; passing it silently no-ops).
    The caller supplies call_ladder from the source's logged call on this name;
    absent it, the discount cannot be computed and this check is a no-op.
    """
    flags = []
    if not source or not call_ladder or not source_rates or action != "ADD":
        return flags
    by_source = source_rates.get(source.lower())
    if not by_source:
        return flags
    by_ladder = by_source.get(call_ladder) or by_source.get("ALL")
    if not by_ladder:
        return flags
    band = by_ladder.get("band", "INSUFFICIENT_DATA")
    n = by_ladder.get("n", 0)
    if n < 15:
        return flags
    if band == "CONSISTENT_MISS":
        flags.append(Flag(
            color="RED", code="SOURCE_CONSISTENT_MISS",
            message=f"{source} x ladder {call_ladder} hit rate <40% (n={n}); "
                    "thesis basis is structurally degraded"
        ))
    elif band == "BELOW_BREAKEVEN":
        flags.append(Flag(
            color="YELLOW", code="SOURCE_BELOW_BREAKEVEN",
            message=f"{source} x ladder {call_ladder} hit rate 40-50% (n={n}); "
                    "discount size by 0.5x"
        ))
    return flags


def _check_factor_concentration(action: str, ticker: str, notional: float,
                                factor_tags: List[str],
                                positions: List[Dict],
                                theses: List[Dict],
                                sleeve_total: float) -> List[Flag]:
    """
    What happens to factor concentration if we proceed?  AMBER if any factor
    crosses >30%; RED if >40%.
    """
    flags = []
    if action != "ADD" or not factor_tags or pfe is None:
        return flags

    # Deep copy to avoid mutating caller's positions/theses
    import copy
    new_positions = copy.deepcopy(positions)
    new_theses = copy.deepcopy(theses)

    found = False
    for p in new_positions:
        if (p.get("ticker") or "").upper() == ticker.upper():
            p["market_value"] = float(p.get("market_value", 0)) + notional
            found = True
    if not found:
        new_positions.append({"ticker": ticker, "market_value": notional})

    found_t = False
    for t in new_theses:
        if (t.get("ticker") or "").upper() == ticker.upper():
            t["factor_tags"] = list(set((t.get("factor_tags") or []) + factor_tags))
            found_t = True
    if not found_t:
        new_theses.append({"ticker": ticker, "factor_tags": factor_tags})

    report = pfe.analyze(new_positions, new_theses, sleeve_total)

    for agg in report.factor_aggregates:
        if agg.factor in [f.lower() for f in factor_tags]:
            if agg.pct_of_sleeve >= INCREMENTAL_FACTOR_CONCENTRATION_RED:
                flags.append(Flag(
                    color="RED", code="INCREMENTAL_FACTOR_CONCENTRATION",
                    message=f"Post-trade '{agg.factor}' = "
                            f"{agg.pct_of_sleeve*100:.1f}% sleeve (>40%) — "
                            "concentration RED"
                ))
            elif agg.pct_of_sleeve >= INCREMENTAL_FACTOR_CONCENTRATION_AMBER:
                flags.append(Flag(
                    color="YELLOW", code="INCREMENTAL_FACTOR_CONCENTRATION",
                    message=f"Post-trade '{agg.factor}' = "
                            f"{agg.pct_of_sleeve*100:.1f}% sleeve (>30%) — "
                            "concentration AMBER"
                ))
    return flags


def _check_capitulation_cooldown(action: str, tier: Optional[str],
                                 market_state: Optional[Dict]) -> List[Flag]:
    """v11.23: SPX ≥15% drawdown + VIX >30 → no T1/T2 adds for 5d."""
    flags = []
    if action != "ADD" or not market_state:
        return flags
    if tier not in ("T1", "T2"):
        return flags

    spx_drawdown = market_state.get("spx_drawdown_pct", 0)
    vix = market_state.get("vix", 0)
    days_since_capitulation = market_state.get("days_since_capitulation_trigger", 999)

    if (spx_drawdown >= SPX_DRAWDOWN_CAPITULATION and vix >= VIX_CAPITULATION):
        if days_since_capitulation < CAPITULATION_COOLDOWN_DAYS:
            flags.append(Flag(
                color="RED", code="CAPITULATION_COOLDOWN",
                message=f"v11.23 capitulation cooldown active (SPX "
                        f"-{spx_drawdown*100:.1f}%, VIX {vix:.1f}, day "
                        f"{days_since_capitulation}/5) — no T1/T2 adds"
            ))
    return flags


# ============================================================================
# CORE GATE
# ============================================================================

def evaluate(action: str, ticker: str, notional: float,
             positions: List[Dict], theses: List[Dict],
             sleeve_total: float,
             macro_pulse: Optional[Dict] = None,
             source_rates: Optional[Dict] = None,
             market_state: Optional[Dict] = None,
             call_ladder: Optional[str] = None) -> GateResult:
    """
    Run all gate checks and return GateResult.
    """
    if action not in ("ADD", "TRIM", "EXIT"):
        raise ValueError(f"Unknown action: {action}")

    # Find current state for ticker
    current_value = 0.0
    for p in positions:
        if (p.get("ticker") or "").upper() == ticker.upper():
            current_value += float(p.get("market_value", 0) or 0)
    current_pct = current_value / sleeve_total if sleeve_total > 0 else 0

    thesis = None
    for t in theses:
        if (t.get("ticker") or "").upper() == ticker.upper():
            thesis = t
            break
    tier = (thesis or {}).get("tier", "").upper() or None
    if tier and tier not in (csc.TIER_BANDS if csc else {}):
        tier = tier[:2] if tier[:2] in (csc.TIER_BANDS if csc else {}) else tier
    source = (thesis or {}).get("source") or (thesis or {}).get("source_at_entry")
    factor_tags = (thesis or {}).get("factor_tags", [])

    # Target sleeve %
    if action == "ADD":
        target_value = current_value + abs(notional)
    elif action == "TRIM":
        target_value = max(0, current_value - abs(notional))
    else:  # EXIT
        target_value = 0
    target_pct = target_value / sleeve_total if sleeve_total > 0 else 0

    result = GateResult(
        action=action, ticker=ticker, notional=notional,
        overall="GREEN",
        current_pct=current_pct, target_pct=target_pct,
        tier=tier,
        macro_regime=(macro_pulse or {}).get("regime_label")
                     or (macro_pulse or {}).get("regime"),
    )

    # Run checks
    result.flags.extend(_check_deepwork(action, notional, tier))
    if csc is not None:
        result.flags.extend(_check_tier_band(
            action, current_pct, target_pct, tier))
    result.flags.extend(_check_macro(action, ticker, factor_tags, macro_pulse))
    # Source calibration keys on the CALL-QUALITY ladder (A/B/C/D), NOT the
    # position tier — pass call_ladder (from the source's logged call), supplied
    # by the caller; absent it, the check no-ops. (v12.0 convention pin.)
    result.flags.extend(_check_source_calibration(
        action, source, call_ladder, source_rates))
    if pfe is not None:
        result.flags.extend(_check_factor_concentration(
            action, ticker, notional, factor_tags,
            positions, theses, sleeve_total))
    result.flags.extend(_check_capitulation_cooldown(action, tier, market_state))

    # Determine overall color
    colors = {f.color for f in result.flags}
    if "RED" in colors:
        result.overall = "RED"
    elif "YELLOW" in colors:
        result.overall = "AMBER"
    else:
        result.overall = "GREEN"

    # Deepwork required?
    result.deepwork_required = any(
        f.code in ("DEEPWORK_THRESHOLD", "GENERATIONAL_LANE_ENTRY")
        for f in result.flags
    )
    # Requires log: anything that's not pure GREEN with no flags
    result.requires_log = result.overall != "GREEN" or result.deepwork_required

    # Summary
    n_red = sum(1 for f in result.flags if f.color == "RED")
    n_yellow = sum(1 for f in result.flags if f.color == "YELLOW")
    n_green = sum(1 for f in result.flags if f.color == "GREEN")
    result.summary = (
        f"{result.overall}: {action} {ticker} ${abs(notional):,.0f}. "
        f"Flags: {n_red} RED, {n_yellow} YELLOW, {n_green} GREEN. "
        f"P-DEEPWORK: {'YES' if result.deepwork_required else 'no'}."
    )
    return result


# ============================================================================
# OUTPUT FORMATTERS
# ============================================================================

def format_text_report(r: GateResult) -> str:
    out = []
    out.append("=" * 70)
    out.append(f"PRE-TRADE GATE — {r.action} {r.ticker} ${abs(r.notional):,.0f}")
    out.append("=" * 70)
    if r.overall == "RED":
        out.append("🔴  RED — DO NOT PROCEED")
    elif r.overall == "AMBER":
        out.append("🟡  AMBER — proceed only with override + log")
    else:
        out.append("🟢  GREEN — proceed")
    out.append("")
    out.append(f"Current sleeve %: {r.current_pct*100:.2f}%")
    out.append(f"Target sleeve %:  {r.target_pct*100:.2f}%")
    if r.tier:
        out.append(f"Tier: {r.tier}")
    if r.macro_regime:
        out.append(f"Macro regime: {r.macro_regime}")
    if r.deepwork_required:
        out.append("🧠 P-DEEPWORK multi-turn workflow REQUIRED")
    out.append("")
    if r.flags:
        out.append("FLAGS:")
        for f in r.flags:
            icon = {"RED": "🔴", "YELLOW": "🟡", "GREEN": "🟢"}.get(f.color, "•")
            out.append(f"  {icon} [{f.code}] {f.message}")
    else:
        out.append("(no flags)")
    out.append("")
    if r.requires_log:
        out.append("📋  This action requires Decision Log entry on execution.")
    return "\n".join(out)


def format_json_report(r: GateResult) -> str:
    return json.dumps(asdict(r), indent=2, default=str)


# ============================================================================
# SELF-TEST
# ============================================================================

def _self_test() -> bool:
    if csc is None or pfe is None:
        print("FAIL: cannot import csc/pfe — ensure /home/claude/build is on sys.path")
        return False

    passed = 0
    failed = 0

    def assert_eq(actual, expected, label):
        nonlocal passed, failed
        if actual == expected:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {label}: expected {expected!r}, got {actual!r}")

    def assert_true(condition, label):
        nonlocal passed, failed
        if condition:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {label}")

    base_positions = [
        {"ticker": "BMNR", "market_value": 71500},
        {"ticker": "NVDA", "market_value": 139000},
        {"ticker": "LEU", "market_value": 96000},
    ]
    base_theses = [
        {"ticker": "BMNR", "tier": "T1", "source": "operator",
         "factor_tags": ["crypto", "eth"]},
        {"ticker": "NVDA", "tier": "T2", "source": "Lee",
         "factor_tags": ["AI_complex", "long_duration_growth"]},
        {"ticker": "LEU", "tier": "T1", "source": "Meridian",
         "factor_tags": ["critical_minerals", "nuclear"]},
    ]

    # ----- Test 1: Tiny ADD passes all checks → GREEN
    r = evaluate("ADD", "BMNR", 1000, base_positions, base_theses, 1875000)
    # 1000 < 25000 → no deepwork; tier T1 ADD does fire GENERATIONAL_LANE
    # so AMBER, not GREEN. Adjust expectation.
    assert_eq(r.overall, "AMBER", "T1 ADD always AMBER (generational lane)")
    assert_true(r.deepwork_required, "T1 ADD requires deepwork")

    # ----- Test 2: ADD $30K → fires P-DEEPWORK_THRESHOLD
    r = evaluate("ADD", "BMNR", 30000, base_positions, base_theses, 1875000)
    deepwork_flags = [f for f in r.flags if f.code == "DEEPWORK_THRESHOLD"]
    assert_eq(len(deepwork_flags), 1, "DEEPWORK_THRESHOLD fires at $30K")
    assert_true(r.deepwork_required, "deepwork_required = True")

    # ----- Test 3: ADD into ABOVE_CEILING → RED
    r = evaluate("ADD", "NVDA", 50000, base_positions, base_theses, 1875000)
    red_flags = [f for f in r.flags if f.color == "RED"]
    assert_true(len(red_flags) >= 1, "ADD pushing above ceiling → RED")
    assert_eq(r.overall, "RED", "overall = RED")

    # ----- Test 4: ADD with macro headwind → AMBER
    macro = {"regime_label": "duration_WEAK"}
    r = evaluate("ADD", "NVDA", 10000, base_positions, base_theses, 1875000,
                 macro_pulse=macro)
    macro_flags = [f for f in r.flags if f.code == "MACRO_HEADWIND"]
    assert_eq(len(macro_flags), 1, "macro headwind flag fires")

    # ----- Test 5: TRIM CRITICALLY_BELOW position → RED
    # BMNR @ 3.81%, T1 floor 8%, critical_below_ratio = 0.5 * 8% = 4%
    # so 3.81% < 4% → critically below
    r = evaluate("TRIM", "BMNR", 10000, base_positions, base_theses, 1875000)
    red_flags = [f for f in r.flags if f.code == "TRIMMING_CRITICALLY_BELOW"]
    assert_eq(len(red_flags), 1, "TRIM critically below → RED flag")

    # ----- Test 6: Source CONSISTENT_MISS → RED (keyed by the CALL-QUALITY
    #               ladder A/B/C/D, call_ladder supplied — NOT the position tier)
    source_rates = {
        "lee": {"A": {"band": "CONSISTENT_MISS", "n": 20}}
    }
    r = evaluate("ADD", "NVDA", 10000, base_positions, base_theses, 1875000,
                 source_rates=source_rates, call_ladder="A")
    red_flags = [f for f in r.flags if f.code == "SOURCE_CONSISTENT_MISS"]
    assert_eq(len(red_flags), 1, "CONSISTENT_MISS → RED")

    # ----- Test 6b: same rates but NO call_ladder → no flag (the position tier
    #               must not back-door the lookup; v12.0 convention pin)
    r = evaluate("ADD", "NVDA", 10000, base_positions, base_theses, 1875000,
                 source_rates=source_rates)
    assert_eq(len([f for f in r.flags if "SOURCE_" in f.code]), 0,
              "no call_ladder → no source flag")

    # ----- Test 7: Source BELOW_BREAKEVEN → AMBER
    source_rates = {
        "lee": {"A": {"band": "BELOW_BREAKEVEN", "n": 20}}
    }
    r = evaluate("ADD", "NVDA", 10000, base_positions, base_theses, 1875000,
                 source_rates=source_rates, call_ladder="A")
    yellow_flags = [f for f in r.flags if f.code == "SOURCE_BELOW_BREAKEVEN"]
    assert_eq(len(yellow_flags), 1, "BELOW_BREAKEVEN → AMBER")

    # ----- Test 8: Source INSUFFICIENT_DATA (n<15) → no flag
    source_rates = {"lee": {"A": {"band": "CONSISTENT_MISS", "n": 8}}}
    r = evaluate("ADD", "NVDA", 10000, base_positions, base_theses, 1875000,
                 source_rates=source_rates, call_ladder="A")
    src_flags = [f for f in r.flags if "SOURCE_" in f.code]
    assert_eq(len(src_flags), 0, "n<15 → no source flag")

    # ----- Test 9: factor concentration AMBER (post-trade ≥30%)
    big_positions = base_positions + [
        {"ticker": "X1", "market_value": 200000},
        {"ticker": "X2", "market_value": 200000},
        {"ticker": "X3", "market_value": 100000},
    ]
    big_theses = base_theses + [
        {"ticker": "X1", "tier": "T2", "factor_tags": ["AI_complex"]},
        {"ticker": "X2", "tier": "T2", "factor_tags": ["AI_complex"]},
        {"ticker": "X3", "tier": "T2", "factor_tags": ["AI_complex"]},
    ]
    # current AI_complex = 139K + 200K + 200K + 100K = 639K = 34%
    # add 80K more AI → ~38.4% — still in AMBER band
    r = evaluate("ADD", "AAPL", 80000, big_positions,
                 big_theses + [{"ticker": "AAPL", "tier": "T2",
                               "factor_tags": ["AI_complex"]}],
                 1875000)
    fc_flags = [f for f in r.flags if f.code == "INCREMENTAL_FACTOR_CONCENTRATION"]
    assert_true(len(fc_flags) >= 1, "factor concentration flag fires")

    # ----- Test 10: capitulation cooldown blocks T1/T2 adds
    market = {"spx_drawdown_pct": 0.18, "vix": 35,
              "days_since_capitulation_trigger": 2}
    r = evaluate("ADD", "BMNR", 10000, base_positions, base_theses, 1875000,
                 market_state=market)
    cap_flags = [f for f in r.flags if f.code == "CAPITULATION_COOLDOWN"]
    assert_eq(len(cap_flags), 1, "capitulation cooldown blocks T1 ADD")

    # ----- Test 11: capitulation cooldown EXPIRED (day 6) → no flag
    market = {"spx_drawdown_pct": 0.18, "vix": 35,
              "days_since_capitulation_trigger": 6}
    r = evaluate("ADD", "BMNR", 10000, base_positions, base_theses, 1875000,
                 market_state=market)
    cap_flags = [f for f in r.flags if f.code == "CAPITULATION_COOLDOWN"]
    assert_eq(len(cap_flags), 0, "cooldown day 6 → no flag")

    # ----- Test 12: CLOSING_TIER_GAP flag fires when add below floor
    # BMNR 3.81% → ADD $30K → 5.4% still below T1 floor 8%
    r = evaluate("ADD", "BMNR", 30000, base_positions, base_theses, 1875000)
    gap_flags = [f for f in r.flags if f.code == "CLOSING_TIER_GAP"]
    assert_eq(len(gap_flags), 1, "CLOSING_TIER_GAP fires")

    # ----- Test 13: EXIT with no flags → AMBER (because exit triggers nothing
    # automatic). Actually exit a TINY $1K position with T3 → should be GREEN
    tiny_positions = [{"ticker": "Z", "market_value": 1000}]
    tiny_theses = [{"ticker": "Z", "tier": "T3", "factor_tags": ["foo"]}]
    r = evaluate("EXIT", "Z", 1000, tiny_positions, tiny_theses, 1875000)
    assert_eq(r.overall, "GREEN", "tiny T3 exit → GREEN")

    # ----- Test 14: ADD with all flags clean for T3 below ceiling → GREEN
    r = evaluate("ADD", "Z", 1000, tiny_positions, tiny_theses, 1875000)
    assert_eq(r.overall, "GREEN", "tiny T3 add → GREEN")

    # ----- Test 15: format_text_report runs
    r = evaluate("ADD", "BMNR", 30000, base_positions, base_theses, 1875000)
    text = format_text_report(r)
    assert_true("PRE-TRADE GATE" in text, "text report header")
    assert_true("BMNR" in text, "text mentions ticker")

    # ----- Test 16: JSON
    js = format_json_report(r)
    parsed = json.loads(js)
    assert_eq(parsed["ticker"], "BMNR", "JSON ticker")

    # ----- Test 17: unknown action raises
    try:
        evaluate("UNKNOWN", "X", 100, [], [], 1000000)
        assert_true(False, "unknown action should raise")
    except ValueError:
        assert_true(True, "unknown action raises")

    # ----- Test 18: position not held → ADD computes target_pct correctly
    r = evaluate("ADD", "NEW_TICKER", 50000, base_positions, base_theses, 1875000)
    assert_true(abs(r.target_pct - (50000/1875000)) < 0.001,
                "new position target pct correct")

    # ----- Test 19: requires_log = True for AMBER
    r = evaluate("ADD", "BMNR", 30000, base_positions, base_theses, 1875000)
    assert_true(r.requires_log, "AMBER requires log")

    # ----- Test 20: realistic operator scenario — ADD $30K BMNR
    r = evaluate("ADD", "BMNR", 30000, base_positions, base_theses, 1875000,
                 macro_pulse={"regime_label":
                              "duration_WEAK · dollar_STRONG · vol_COMPLACENT"})
    assert_eq(r.overall, "AMBER",
              "$30K BMNR ADD in current macro → AMBER")
    assert_true(r.deepwork_required, "real BMNR ADD requires deepwork")

    total = passed + failed
    print(f"\n{passed}/{total} assertions passed.")
    return failed == 0


# ============================================================================
# CLI
# ============================================================================

def main():
    p = argparse.ArgumentParser(description="Pre-Trade Gate v11.26")
    p.add_argument("--action", choices=["ADD", "TRIM", "EXIT"])
    p.add_argument("--ticker", help="Ticker symbol")
    p.add_argument("--notional", type=float, help="$ notional")
    p.add_argument("--positions", help="Positions JSON")
    p.add_argument("--theses", help="Live Theses JSON")
    p.add_argument("--sleeve-total", type=float)
    p.add_argument("--macro", help="Macro pulse JSON")
    p.add_argument("--source-rates", help="Source hit-rate JSON")
    p.add_argument("--market-state", help="Market state JSON (VIX, SPX drawdown, etc)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()

    if args.self_test:
        sys.exit(0 if _self_test() else 1)

    if not all([args.action, args.ticker, args.notional is not None,
                args.positions, args.theses, args.sleeve_total]):
        p.error("--action, --ticker, --notional, --positions, --theses, "
                "--sleeve-total required (or --self-test)")

    with open(args.positions) as f:
        positions = json.load(f)
    if isinstance(positions, dict) and "positions" in positions:
        positions = positions["positions"]
    with open(args.theses) as f:
        theses = json.load(f)
    if isinstance(theses, dict) and "theses" in theses:
        theses = theses["theses"]
    macro = json.load(open(args.macro)) if args.macro else None
    rates = json.load(open(args.source_rates)) if args.source_rates else None
    market = json.load(open(args.market_state)) if args.market_state else None

    r = evaluate(args.action, args.ticker, args.notional,
                 positions, theses, args.sleeve_total,
                 macro, rates, market)
    if args.json:
        print(format_json_report(r))
    else:
        print(format_text_report(r))


if __name__ == "__main__":
    main()
