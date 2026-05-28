#!/usr/bin/env python3
"""
rationale_decay_v3.py — Option Position Re-evaluation Cadence (v11.10)

EXTENDS rationale_decay v2 with 7-rule forcing function for OPTION positions.
Equity rationales unchanged — they continue using v2 time-decay (STALE_SOFT
14d, STALE_HARD 21d, TIER_A_HARD 7d).

The 7 rules (per v11.10 CI behavioral standing rule):
  1. Anchor check       — original named anchor broken
  2. Catalyst-in-DTE    — no meaningful catalyst remaining
  3. Long-call time gate — 180/120/90 DTE thresholds for OTM single-name longs
  4. Vertical profit gate — 80-90% max value with >21 DTE
  5. Theta gate         — 15% option value or 0.25%/day sleeve
  6. Vol gate           — 10 vol-point post-event collapse
  7. Factor gate        — 35% theme concentration breach

Self-contained rules (work standalone, no external state lookups):
  - Long-call time gate (rule 3)    — only needs option_symbol + current date
  - Vertical profit gate (rule 4)   — needs current_value + max_value + DTE
  - Theta gate (rule 5)             — needs option_value + theta from UW chain
  - Vol gate (rule 6)               — needs iv_at_entry + current_iv

Externally-dependent rules (stubbed; require integration with Notion DBs):
  - Anchor check (rule 1)           — TODO: Live Theses DB anchor_status field
  - Catalyst-in-DTE (rule 2)        — TODO: Catalyst Calendar query within DTE
  - Factor gate (rule 7)            — TODO: sleeve heat aggregator across positions

Usage:
  python rationale_decay_v3.py --option-symbol IONQ280119C00070000 \\
                                --debit 560 --current-value 580 \\
                                --iv-entry 0.65 --current-iv 0.55

  python rationale_decay_v3.py --equity AAPL  # falls through to v2 behavior

Designed to run weekly (Sunday morning cron) on all Live Theses option
positions. Output formatted as Launcher Step 1 surface.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, Literal


# ============================================================================
# OPTION SYMBOL PARSING (OCC standard)
# ============================================================================

OCC_RE = re.compile(
    r"^([A-Z]+)"          # underlying
    r"(\d{2})(\d{2})(\d{2})"  # YY MM DD expiry
    r"([CP])"             # call or put
    r"(\d{8})$"           # strike × 1000
)


def parse_occ_symbol(symbol: str) -> Optional[dict]:
    """Parse OCC option symbol (e.g., IONQ280119C00070000) to components."""
    m = OCC_RE.match(symbol.strip().upper())
    if not m:
        return None
    underlying, yy, mm, dd, cp, strike_raw = m.groups()
    return {
        "underlying": underlying,
        "expiry": datetime(2000 + int(yy), int(mm), int(dd), tzinfo=timezone.utc),
        "right": "call" if cp == "C" else "put",
        "strike": int(strike_raw) / 1000,
    }


def days_to_expiry(symbol: str, as_of: Optional[datetime] = None) -> Optional[int]:
    parsed = parse_occ_symbol(symbol)
    if not parsed:
        return None
    if as_of is None:
        as_of = datetime.now(timezone.utc)
    delta = parsed["expiry"] - as_of
    return delta.days


# ============================================================================
# CONFIGURATION — 7-RULE THRESHOLDS
# ============================================================================

# Rule 3 — Long-call time gate
LONG_CALL_REVIEW_DTE = 180   # hard review trigger
LONG_CALL_ACTION_DTE = 120   # mandatory action trigger
LONG_CALL_BLOCK_DTE = 90     # never carry OTM single-name long calls below this

# Rule 4 — Vertical profit gate
VERT_PROFIT_GATE_PCT = 0.80          # close at 80% of max value
VERT_PROFIT_HARD_PCT = 0.90          # mandatory close at 90% of max value
VERT_PROFIT_MIN_DTE = 21             # rule applies only with >21 DTE remaining

# Rule 5 — Theta gate
THETA_PCT_OF_VALUE_30D = 0.15        # next 30d theta > 15% of option value
THETA_PCT_OF_SLEEVE_DAILY = 0.0025   # OR sleeve theta > 0.25%/day

# Rule 6 — Vol gate
VOL_COLLAPSE_THRESHOLD_PTS = 10.0    # IV collapsed 10 vol points
VOL_GATE_REQUIRES_NO_2ND_CATALYST = True

# Rule 7 — Factor gate
FACTOR_CONCENTRATION_CAP = 0.35      # 35% per factor bucket (per Candidate O)


# ============================================================================
# DATA STRUCTURES
# ============================================================================

TriggerResult = Literal["FIRE", "PASS", "STUB"]


@dataclass
class RuleEvaluation:
    rule_number: int
    rule_name: str
    result: TriggerResult
    detail: str
    action: Optional[str] = None  # "EXIT" | "ROLL" | "TRIM" | "REVIEW" | None


@dataclass
class OptionRationaleEvaluation:
    """Result of running 7-rule cadence on one option position."""
    option_symbol: str
    underlying: str
    expiry: str
    right: str
    strike: float
    dte: int
    rules: list[RuleEvaluation] = field(default_factory=list)
    overall_action: Optional[str] = None
    overall_priority: Literal["NONE", "REVIEW", "ACTION_NEEDED", "EXIT_NOW"] = "NONE"


# ============================================================================
# RULE EVALUATORS — SELF-CONTAINED
# ============================================================================

def eval_long_call_time_gate(
    option_symbol: str,
    is_otm: bool = True,
    is_single_name: bool = True,
    as_of: Optional[datetime] = None,
) -> RuleEvaluation:
    """
    Rule 3: Long-call time gate.
    Hard review at 180 DTE, mandatory action by 120 DTE,
    never carry OTM single-name long calls into last 90 DTE.
    Only applies to long-call structures (not verticals, not puts).
    """
    parsed = parse_occ_symbol(option_symbol)
    if not parsed or parsed["right"] != "call":
        return RuleEvaluation(3, "long_call_time_gate", "PASS",
                              "Not a long call — rule N/A")

    dte = days_to_expiry(option_symbol, as_of)
    if dte is None:
        return RuleEvaluation(3, "long_call_time_gate", "PASS",
                              "Could not parse DTE")

    if dte <= LONG_CALL_BLOCK_DTE and is_otm and is_single_name:
        return RuleEvaluation(
            3, "long_call_time_gate", "FIRE",
            f"DTE {dte} ≤ {LONG_CALL_BLOCK_DTE} — OTM single-name long call "
            f"in last 90 DTE; never carry. Roll or close immediately.",
            action="ROLL_OR_CLOSE",
        )
    elif dte <= LONG_CALL_ACTION_DTE:
        return RuleEvaluation(
            3, "long_call_time_gate", "FIRE",
            f"DTE {dte} ≤ {LONG_CALL_ACTION_DTE} — mandatory action gate. "
            f"Roll out (time) or close.",
            action="ROLL_OUT",
        )
    elif dte <= LONG_CALL_REVIEW_DTE:
        return RuleEvaluation(
            3, "long_call_time_gate", "FIRE",
            f"DTE {dte} ≤ {LONG_CALL_REVIEW_DTE} — hard review gate. "
            f"Evaluate roll vs close; theta acceleration approaching.",
            action="REVIEW",
        )
    return RuleEvaluation(
        3, "long_call_time_gate", "PASS",
        f"DTE {dte} > {LONG_CALL_REVIEW_DTE} — no time-gate fire",
    )


def eval_vertical_profit_gate(
    option_symbol: str,
    debit_paid: float,
    current_value: float,
    spread_max_value: Optional[float] = None,
    as_of: Optional[datetime] = None,
) -> RuleEvaluation:
    """
    Rule 4: Vertical profit gate.
    Close at 80-90% of max value with >21 DTE remaining.
    spread_max_value = width × 100 for a vertical (e.g., $50/$100 spread = $5,000 max).
    For LEAPS or naked calls, this rule degenerates — skip via PASS.
    """
    if spread_max_value is None or spread_max_value <= debit_paid:
        return RuleEvaluation(4, "vertical_profit_gate", "PASS",
                              "Not a defined-width spread — rule N/A")

    dte = days_to_expiry(option_symbol, as_of)
    if dte is None or dte < VERT_PROFIT_MIN_DTE:
        return RuleEvaluation(
            4, "vertical_profit_gate", "PASS",
            f"DTE {dte} < {VERT_PROFIT_MIN_DTE} — rule only applies with >21 DTE remaining",
        )

    profit_pct = current_value / spread_max_value
    if profit_pct >= VERT_PROFIT_HARD_PCT:
        return RuleEvaluation(
            4, "vertical_profit_gate", "FIRE",
            f"Spread at {profit_pct*100:.1f}% of max value (≥{VERT_PROFIT_HARD_PCT*100:.0f}%) "
            f"with {dte} DTE — mandatory close to lock profit. Roll only if new structure "
            f"clears reward floor from new debit basis.",
            action="CLOSE_LOCK_PROFIT",
        )
    elif profit_pct >= VERT_PROFIT_GATE_PCT:
        return RuleEvaluation(
            4, "vertical_profit_gate", "FIRE",
            f"Spread at {profit_pct*100:.1f}% of max value (≥{VERT_PROFIT_GATE_PCT*100:.0f}%) "
            f"with {dte} DTE — close to lock profit unless thesis upside extends meaningfully.",
            action="CONSIDER_CLOSE",
        )
    return RuleEvaluation(
        4, "vertical_profit_gate", "PASS",
        f"Spread at {profit_pct*100:.1f}% of max value — under gate",
    )


def eval_theta_gate(
    option_value: float,
    theta_per_day: float,
    sleeve_value: Optional[float] = None,
    sleeve_total_theta: Optional[float] = None,
) -> RuleEvaluation:
    """
    Rule 5: Theta gate.
    Fire if next 30d theta > 15% of option value
    OR sleeve theta > 0.25%/day of sleeve value.
    theta_per_day passed as a NEGATIVE number (theta is decay).
    """
    if option_value <= 0:
        return RuleEvaluation(5, "theta_gate", "PASS",
                              "Option value ≤ 0 — rule N/A")

    theta_abs = abs(theta_per_day)
    theta_30d_pct = (theta_abs * 30) / option_value
    if theta_30d_pct > THETA_PCT_OF_VALUE_30D:
        return RuleEvaluation(
            5, "theta_gate", "FIRE",
            f"30d theta burn ${theta_abs*30:.0f} = {theta_30d_pct*100:.1f}% of "
            f"option value ${option_value:.0f} (>{THETA_PCT_OF_VALUE_30D*100:.0f}% threshold). "
            f"Reduce or roll out.",
            action="REDUCE_OR_ROLL",
        )

    if sleeve_value and sleeve_total_theta is not None:
        sleeve_theta_pct = abs(sleeve_total_theta) / sleeve_value
        if sleeve_theta_pct > THETA_PCT_OF_SLEEVE_DAILY:
            return RuleEvaluation(
                5, "theta_gate", "FIRE",
                f"Sleeve aggregate theta {abs(sleeve_total_theta):.2f}/day = "
                f"{sleeve_theta_pct*100:.3f}% of sleeve "
                f"(>{THETA_PCT_OF_SLEEVE_DAILY*100:.2f}% threshold). Reduce sleeve theta.",
                action="REDUCE_SLEEVE",
            )

    return RuleEvaluation(
        5, "theta_gate", "PASS",
        f"30d theta {theta_30d_pct*100:.1f}% of option value — under gate",
    )


def eval_vol_gate(
    iv_at_entry: float,
    current_iv: float,
    has_second_catalyst: bool = False,
) -> RuleEvaluation:
    """
    Rule 6: Vol gate.
    Fire on post-event IV collapse ≥10 vol points with no 2nd catalyst.
    IVs passed as decimals (0.55 = 55%).
    """
    if iv_at_entry <= 0 or current_iv <= 0:
        return RuleEvaluation(6, "vol_gate", "PASS",
                              "IV data unavailable — rule N/A")

    iv_drop_pts = (iv_at_entry - current_iv) * 100  # vol points
    if iv_drop_pts >= VOL_COLLAPSE_THRESHOLD_PTS:
        if VOL_GATE_REQUIRES_NO_2ND_CATALYST and has_second_catalyst:
            return RuleEvaluation(
                6, "vol_gate", "PASS",
                f"IV dropped {iv_drop_pts:.1f}pts (≥{VOL_COLLAPSE_THRESHOLD_PTS}pt threshold) "
                f"but 2nd catalyst pending — hold for next vol event",
            )
        return RuleEvaluation(
            6, "vol_gate", "FIRE",
            f"IV collapse: {iv_at_entry*100:.0f}% → {current_iv*100:.0f}% "
            f"({iv_drop_pts:.1f}pt drop, ≥{VOL_COLLAPSE_THRESHOLD_PTS}pt threshold) "
            f"without 2nd catalyst. Harvest remaining vega — do not 'give it time.'",
            action="HARVEST_VEGA",
        )
    return RuleEvaluation(
        6, "vol_gate", "PASS",
        f"IV {iv_at_entry*100:.0f}% → {current_iv*100:.0f}% ({iv_drop_pts:.1f}pt change) — under gate",
    )


# ============================================================================
# RULE EVALUATORS — EXTERNAL-DEPENDENCY STUBS
# ============================================================================

def eval_anchor_check(
    option_symbol: str,
    underlying: str,
    live_theses_data: Optional[dict] = None,
) -> RuleEvaluation:
    """
    Rule 1: Anchor check — STUB.

    REQUIRES INTEGRATION: Query Live Theses DB row by underlying, read
    anchor_status field. Fire if anchor flipped to broken/contradicted/superseded.

    Expected schema: live_theses_data = {
        "anchor_status": "INTACT" | "WEAKENED" | "BROKEN" | "SUPERSEDED",
        "anchor_text": "...",
        "last_updated": "ISO timestamp",
    }
    """
    if live_theses_data is None:
        return RuleEvaluation(
            1, "anchor_check", "STUB",
            "TODO: integrate with Live Theses DB (0f083d6f-be67-4815-a64a-a21959812f0d) "
            f"to read anchor_status for {underlying}",
        )

    status = live_theses_data.get("anchor_status", "UNKNOWN")
    if status in ("BROKEN", "SUPERSEDED"):
        return RuleEvaluation(
            1, "anchor_check", "FIRE",
            f"Anchor {status}: {live_theses_data.get('anchor_text', 'N/A')}. "
            f"Exit immediately — Greeks do not overrule thesis failure.",
            action="EXIT_IMMEDIATELY",
        )
    elif status == "WEAKENED":
        return RuleEvaluation(
            1, "anchor_check", "FIRE",
            f"Anchor WEAKENED: {live_theses_data.get('anchor_text', 'N/A')}. "
            f"Reduce position or set tighter stop.",
            action="REDUCE_OR_TIGHTEN_STOP",
        )
    return RuleEvaluation(1, "anchor_check", "PASS",
                          f"Anchor {status}")


def eval_catalyst_in_dte(
    option_symbol: str,
    underlying: str,
    catalyst_data: Optional[list] = None,
    as_of: Optional[datetime] = None,
) -> RuleEvaluation:
    """
    Rule 2: Catalyst-in-DTE — STUB.

    REQUIRES INTEGRATION: Query Catalyst Calendar (UUID 35fc50314bb681c5ae90d8a84919999b)
    for upcoming catalysts on `underlying` within DTE window.

    Expected schema: catalyst_data = [
        {"name": "Q2 earnings", "date": "ISO", "ticker": "IONQ", "type": "earnings"},
        ...
    ]
    Fire if no catalyst date falls within DTE window.
    """
    if catalyst_data is None:
        return RuleEvaluation(
            2, "catalyst_in_dte", "STUB",
            "TODO: integrate with Catalyst Calendar (35fc50314bb681c5ae90d8a84919999b) "
            f"to count catalysts within DTE on {underlying}",
        )

    dte = days_to_expiry(option_symbol, as_of)
    if dte is None:
        return RuleEvaluation(2, "catalyst_in_dte", "PASS", "Could not parse DTE")

    if as_of is None:
        as_of = datetime.now(timezone.utc)
    expiry = as_of + (parse_occ_symbol(option_symbol)["expiry"] - as_of)

    within_dte = [
        c for c in catalyst_data
        if c.get("ticker", "").upper() == underlying.upper()
        and as_of <= datetime.fromisoformat(c["date"].replace("Z", "+00:00")) <= expiry
    ]

    if not within_dte:
        return RuleEvaluation(
            2, "catalyst_in_dte", "FIRE",
            f"No catalysts for {underlying} within {dte} DTE — long premium without "
            f"live catalyst is rented hope. Close or replace structure.",
            action="CLOSE_OR_REPLACE",
        )
    return RuleEvaluation(
        2, "catalyst_in_dte", "PASS",
        f"{len(within_dte)} catalyst(s) within DTE: " +
        ", ".join(c["name"] for c in within_dte[:3]),
    )


def eval_factor_gate(
    underlying: str,
    factor: str,
    factor_heat: Optional[float] = None,
    sleeve_value: Optional[float] = None,
) -> RuleEvaluation:
    """
    Rule 7: Factor gate — STUB (partial).

    Self-contained if (factor_heat, sleeve_value) provided directly; otherwise
    REQUIRES INTEGRATION with sleeve heat aggregator across all Live Theses
    option positions tagged with this factor.
    """
    if factor_heat is None or sleeve_value is None or sleeve_value <= 0:
        return RuleEvaluation(
            7, "factor_gate", "STUB",
            f"TODO: integrate with sleeve aggregator to compute current "
            f"factor heat for '{factor}' — pass --factor-heat and --sleeve-value explicitly",
        )

    factor_concentration = factor_heat / sleeve_value
    if factor_concentration > FACTOR_CONCENTRATION_CAP:
        return RuleEvaluation(
            7, "factor_gate", "FIRE",
            f"Factor concentration '{factor}' at {factor_concentration*100:.1f}% of sleeve "
            f"exceeds {FACTOR_CONCENTRATION_CAP*100:.0f}% cap. Trim factor exposure even if "
            f"individual thesis intact.",
            action="TRIM_FACTOR",
        )
    return RuleEvaluation(
        7, "factor_gate", "PASS",
        f"Factor '{factor}' at {factor_concentration*100:.1f}% — under {FACTOR_CONCENTRATION_CAP*100:.0f}% cap",
    )


# ============================================================================
# ORCHESTRATION
# ============================================================================

def evaluate_option_position(
    option_symbol: str,
    *,
    # Self-contained inputs
    debit_paid: Optional[float] = None,
    current_value: Optional[float] = None,
    spread_max_value: Optional[float] = None,
    theta_per_day: Optional[float] = None,
    iv_at_entry: Optional[float] = None,
    current_iv: Optional[float] = None,
    is_otm: bool = True,
    is_single_name: bool = True,
    has_second_catalyst: bool = False,
    # Sleeve context
    sleeve_value: Optional[float] = None,
    sleeve_total_theta: Optional[float] = None,
    # External-dependency inputs (pass None to STUB)
    live_theses_data: Optional[dict] = None,
    catalyst_data: Optional[list] = None,
    factor: str = "solo",
    factor_heat: Optional[float] = None,
    as_of: Optional[datetime] = None,
) -> OptionRationaleEvaluation:
    """Evaluate all 7 rules. STUB rules return STUB result (not FIRE)."""
    parsed = parse_occ_symbol(option_symbol)
    if not parsed:
        raise ValueError(f"Cannot parse OCC symbol: {option_symbol!r}")

    underlying = parsed["underlying"]
    dte = days_to_expiry(option_symbol, as_of) or 0

    results = []

    # Rule 1 — Anchor check (external)
    results.append(eval_anchor_check(option_symbol, underlying, live_theses_data))

    # Rule 2 — Catalyst-in-DTE (external)
    results.append(eval_catalyst_in_dte(option_symbol, underlying, catalyst_data, as_of))

    # Rule 3 — Long-call time gate (self-contained)
    results.append(eval_long_call_time_gate(option_symbol, is_otm, is_single_name, as_of))

    # Rule 4 — Vertical profit gate (self-contained, requires market data inputs)
    if current_value is not None and debit_paid is not None:
        results.append(eval_vertical_profit_gate(
            option_symbol, debit_paid, current_value, spread_max_value, as_of))
    else:
        results.append(RuleEvaluation(
            4, "vertical_profit_gate", "STUB",
            "Pass --current-value and --spread-max-value to enable rule",
        ))

    # Rule 5 — Theta gate (self-contained, requires Greeks)
    if current_value is not None and theta_per_day is not None:
        results.append(eval_theta_gate(
            current_value, theta_per_day, sleeve_value, sleeve_total_theta))
    else:
        results.append(RuleEvaluation(
            5, "theta_gate", "STUB",
            "Pass --current-value and --theta to enable rule (pull live from UW chain)",
        ))

    # Rule 6 — Vol gate (self-contained, requires IV history)
    if iv_at_entry is not None and current_iv is not None:
        results.append(eval_vol_gate(iv_at_entry, current_iv, has_second_catalyst))
    else:
        results.append(RuleEvaluation(
            6, "vol_gate", "STUB",
            "Pass --iv-entry and --current-iv to enable rule",
        ))

    # Rule 7 — Factor gate (partial-external)
    results.append(eval_factor_gate(underlying, factor, factor_heat, sleeve_value))

    # Determine overall priority
    fires = [r for r in results if r.result == "FIRE"]
    stubs = [r for r in results if r.result == "STUB"]
    overall_priority: Literal["NONE", "REVIEW", "ACTION_NEEDED", "EXIT_NOW"] = "NONE"
    overall_action: Optional[str] = None

    if any(r.action == "EXIT_IMMEDIATELY" for r in fires):
        overall_priority = "EXIT_NOW"
        overall_action = "EXIT_IMMEDIATELY"
    elif any(r.action in ("ROLL_OR_CLOSE", "CLOSE_LOCK_PROFIT", "HARVEST_VEGA") for r in fires):
        overall_priority = "ACTION_NEEDED"
        overall_action = next(r.action for r in fires
                              if r.action in ("ROLL_OR_CLOSE", "CLOSE_LOCK_PROFIT", "HARVEST_VEGA"))
    elif fires:
        overall_priority = "REVIEW"
        overall_action = fires[0].action

    return OptionRationaleEvaluation(
        option_symbol=option_symbol,
        underlying=underlying,
        expiry=parsed["expiry"].date().isoformat(),
        right=parsed["right"],
        strike=parsed["strike"],
        dte=dte,
        rules=results,
        overall_action=overall_action,
        overall_priority=overall_priority,
    )


# ============================================================================
# OUTPUT FORMATTING
# ============================================================================

def format_text(eval_result: OptionRationaleEvaluation) -> str:
    icons = {"FIRE": "🔴", "PASS": "🟢", "STUB": "⚪"}
    priority_icons = {
        "NONE": "✓",
        "REVIEW": "📋",
        "ACTION_NEEDED": "⚠️ ",
        "EXIT_NOW": "🚨",
    }
    lines = []
    lines.append("=" * 72)
    lines.append(f" OPTION RATIONALE EVALUATION (v11.10 7-rule cadence)")
    lines.append("=" * 72)
    lines.append(f"  Symbol:    {eval_result.option_symbol}")
    lines.append(f"  Underlying: {eval_result.underlying} {eval_result.right} ${eval_result.strike:.2f}")
    lines.append(f"  Expiry:    {eval_result.expiry} ({eval_result.dte} DTE)")
    lines.append("")
    lines.append("  7-RULE CADENCE")
    lines.append("  " + "-" * 68)
    for r in eval_result.rules:
        lines.append(f"  {icons[r.result]} Rule {r.rule_number} ({r.rule_name}): {r.detail}")
        if r.action:
            lines.append(f"     → Action: {r.action}")
    lines.append("")
    lines.append("  OVERALL")
    lines.append("  " + "-" * 68)
    lines.append(f"  {priority_icons[eval_result.overall_priority]} Priority: {eval_result.overall_priority}")
    if eval_result.overall_action:
        lines.append(f"  Action: {eval_result.overall_action}")
    if any(r.result == "STUB" for r in eval_result.rules):
        stub_rules = [r.rule_number for r in eval_result.rules if r.result == "STUB"]
        lines.append(f"  ⚠️  Rules {stub_rules} STUBBED — see TODO notes for required integrations")
    lines.append("=" * 72)
    return "\n".join(lines)


# ============================================================================
# CLI
# ============================================================================

def main():
    p = argparse.ArgumentParser(
        description="v11.10 Option Position Re-evaluation Cadence (7-rule)")
    p.add_argument("--option-symbol", required=False, help="OCC option symbol")
    p.add_argument("--equity", help="Equity ticker (falls through to v2 time-decay)")
    p.add_argument("--debit", type=float, help="Debit paid at entry ($)")
    p.add_argument("--current-value", type=float,
                   help="Current mark-to-market value ($)")
    p.add_argument("--spread-max-value", type=float,
                   help="Max value for vertical spreads (width × 100)")
    p.add_argument("--theta", type=float, help="Daily theta ($/day, typically negative)")
    p.add_argument("--iv-entry", type=float, help="IV at entry (decimal, e.g., 0.55)")
    p.add_argument("--current-iv", type=float, help="Current IV (decimal)")
    p.add_argument("--is-otm", action="store_true", default=True)
    p.add_argument("--is-itm", dest="is_otm", action="store_false")
    p.add_argument("--has-2nd-catalyst", action="store_true",
                   help="Skip vol-gate fire if 2nd catalyst pending")
    p.add_argument("--sleeve", type=float, help="Sleeve value ($)")
    p.add_argument("--sleeve-theta", type=float, help="Aggregate sleeve theta ($/day)")
    p.add_argument("--factor", default="solo")
    p.add_argument("--factor-heat", type=float, help="$ at risk in factor bucket")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    if args.equity:
        print(f"[v3] Equity rationale for {args.equity} — falls through to "
              f"rationale_decay v2 time-decay (no 7-rule cadence)")
        return 0

    if not args.option_symbol:
        p.print_help()
        print("\nERROR: --option-symbol required for option evaluation", file=sys.stderr)
        return 1

    try:
        result = evaluate_option_position(
            option_symbol=args.option_symbol,
            debit_paid=args.debit,
            current_value=args.current_value,
            spread_max_value=args.spread_max_value,
            theta_per_day=args.theta,
            iv_at_entry=args.iv_entry,
            current_iv=args.current_iv,
            is_otm=args.is_otm,
            has_second_catalyst=args.has_2nd_catalyst,
            sleeve_value=args.sleeve,
            sleeve_total_theta=args.sleeve_theta,
            factor=args.factor,
            factor_heat=args.factor_heat,
        )
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if args.json:
        # Manual dict conversion since dataclass has nested dataclass list
        out = asdict(result)
        print(json.dumps(out, indent=2))
    else:
        print(format_text(result))

    return 0


if __name__ == "__main__":
    sys.exit(main())
