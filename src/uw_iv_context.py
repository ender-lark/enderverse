#!/usr/bin/env python3
"""
uw_iv_context.py — IV context classifier for v11.11 Game B overlay.

Implements the cheap-option overlay on conviction names from the v11.11
stale-quote / undervalued-options strategy. Pure logic; UW data fetching
happens upstream (in chat session via MCP tools).

Inputs:
  iv_rank: IV Rank 0-100 (from UW get_stock_screener)
  atm_iv_current: current ATM IV at target DTE (from get_options_chain)
  atm_iv_30d_mean: 30-day mean of ATM IV (computed by caller)
  atm_iv_back: ATM IV at longer-dated expiry (for term structure)
  skew_slope: (put_25_delta_IV - call_25_delta_IV) / ATM_IV
              positive = fearful (puts bid up), negative = call frenzy

Outputs:
  classification: cheap / normal / expensive / unknown
  term_structure: backwardation / contango / flat / unknown
  skew_state: fearful / mild_fearful / neutral / call_frenzy / unknown
  recommended_structure: LEAP_CALL / VERTICAL / DIAGONAL / CALENDAR
  sizing_modifier: multiplier (0.70-1.20) applied to sized-to-caps max debit
  reasoning: list[str] bullet points

Defined-risk LONG side only per v11.10 CI rule
(VRP harvesting not enabled; no short-put or covered-call recommendations).

Usage (CLI smoke test):
  python uw_iv_context.py --ticker LEU --ivr 35 --atm-iv 0.62 --tier A
  python uw_iv_context.py --ticker IONQ --ivr 88 --atm-iv 0.95 --tier B --json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional

# ============================================================================
# CLASSIFICATION THRESHOLDS
# ============================================================================

# IV Rank bands (0-100, percentile-of-52-week-range)
IVR_CHEAP_MAX = 30.0
IVR_EXPENSIVE_MIN = 70.0

# Recent-IV-move (current vs 30d mean) thresholds
RECENT_CRUSH_RATIO = 0.85         # current < 85% of 30d mean → crushed
RECENT_INFLATION_RATIO = 1.20     # current > 120% of 30d mean → inflated

# Term structure thresholds (front_IV / back_IV ratio)
BACKWARDATION_THRESHOLD = 1.05    # front > back × 1.05 = backwardated
CONTANGO_THRESHOLD = 0.95         # front < back × 0.95 = contango

# Skew thresholds (put-call skew slope, as ATM-normalized difference)
SKEW_FEARFUL = 0.10               # put IV >> call IV → fearful market
SKEW_MILD_FEARFUL = 0.04
SKEW_CALL_FRENZY = -0.05          # call IV > put IV → unusual bullish frenzy

# Sizing modifier bounds
SIZING_MOD_CHEAP = 1.15           # +15% on caps-max debit when IV cheap
SIZING_MOD_NORMAL = 1.00
SIZING_MOD_EXPENSIVE = 0.80       # -20% on caps-max debit when IV expensive
CATALYST_EXPENSIVE_OFFSET = 0.10  # partial reverse of expensive penalty


# ============================================================================
# DATA STRUCTURE
# ============================================================================

@dataclass
class IVContext:
    """Result of IV context classification for a ticker."""
    ticker: str
    tier: str

    # Raw inputs (for audit)
    iv_rank: Optional[float]
    atm_iv_current: Optional[float]
    atm_iv_30d_mean: Optional[float]
    atm_iv_back: Optional[float]
    skew_slope: Optional[float]
    target_dte: Optional[int]
    catalyst_within_dte: bool

    # Classifications
    classification: str            # cheap / normal / expensive / unknown
    term_structure: str            # backwardation / contango / flat / unknown
    skew_state: str                # fearful / mild_fearful / neutral / call_frenzy / unknown

    # Recommendations
    recommended_structure: str     # LEAP_CALL / VERTICAL / DIAGONAL / CALENDAR
    sizing_modifier: float         # Multiplier applied to caps-max debit

    # Audit trail
    reasoning: list[str] = field(default_factory=list)


# ============================================================================
# CORE CLASSIFICATION
# ============================================================================

def classify_iv(
    ticker: str,
    iv_rank: Optional[float] = None,
    atm_iv_current: Optional[float] = None,
    atm_iv_30d_mean: Optional[float] = None,
    atm_iv_back: Optional[float] = None,
    skew_slope: Optional[float] = None,
    target_dte: Optional[int] = None,
    tier: str = "A",
    catalyst_within_dte: bool = False,
) -> IVContext:
    """
    Classify IV context for a ticker and recommend option structure.

    Per v11.11 Game B logic:
      - cheap IV  + conviction → upsize outright LEAPs (cheap vega)
      - expensive IV + conviction → finance theta via verticals/diagonals
      - cheap IV + backwardated term → calendar harvests asymmetry

    Defined-risk LONG side only (no VRP harvesting per CI v11.10).
    """
    tier = tier.upper()
    reasoning: list[str] = []

    # ----------------------------------------------------------------
    # IV Rank classification
    # ----------------------------------------------------------------
    if iv_rank is None:
        classification = "unknown"
        reasoning.append("IV Rank not provided — classification deferred")
    elif iv_rank < IVR_CHEAP_MAX:
        classification = "cheap"
        reasoning.append(
            f"IV Rank {iv_rank:.0f} below {IVR_CHEAP_MAX:.0f} — "
            f"options cheap vs 52w range"
        )
    elif iv_rank > IVR_EXPENSIVE_MIN:
        classification = "expensive"
        reasoning.append(
            f"IV Rank {iv_rank:.0f} above {IVR_EXPENSIVE_MIN:.0f} — "
            f"options expensive vs 52w range"
        )
    else:
        classification = "normal"
        reasoning.append(
            f"IV Rank {iv_rank:.0f} in normal band ({IVR_CHEAP_MAX:.0f}-{IVR_EXPENSIVE_MIN:.0f})"
        )

    # ----------------------------------------------------------------
    # Recent move check (current vs 30d mean) — can refine "normal"
    # ----------------------------------------------------------------
    if atm_iv_current is not None and atm_iv_30d_mean is not None and atm_iv_30d_mean > 0:
        recent_ratio = atm_iv_current / atm_iv_30d_mean
        if recent_ratio < RECENT_CRUSH_RATIO:
            reasoning.append(
                f"Current ATM IV {atm_iv_current*100:.1f}% is "
                f"{(1-recent_ratio)*100:.0f}% below 30d mean — recent IV crush"
            )
            if classification == "normal":
                classification = "cheap"
                reasoning.append("Reclassified normal → cheap (recent IV crush vs 30d mean)")
        elif recent_ratio > RECENT_INFLATION_RATIO:
            reasoning.append(
                f"Current ATM IV {atm_iv_current*100:.1f}% is "
                f"{(recent_ratio-1)*100:.0f}% above 30d mean — recent IV inflation"
            )
            if classification == "normal":
                classification = "expensive"
                reasoning.append("Reclassified normal → expensive (recent IV inflation vs 30d mean)")

    # ----------------------------------------------------------------
    # Term structure
    # ----------------------------------------------------------------
    if atm_iv_current is None or atm_iv_back is None or atm_iv_back <= 0:
        term_structure = "unknown"
    else:
        ratio = atm_iv_current / atm_iv_back
        if ratio > BACKWARDATION_THRESHOLD:
            term_structure = "backwardation"
            reasoning.append(
                f"Term backwardated: front IV {atm_iv_current*100:.1f}% > "
                f"back IV {atm_iv_back*100:.1f}% (ratio {ratio:.2f})"
            )
        elif ratio < CONTANGO_THRESHOLD:
            term_structure = "contango"
            reasoning.append(
                f"Term in contango: back IV {atm_iv_back*100:.1f}% > "
                f"front IV {atm_iv_current*100:.1f}% (ratio {ratio:.2f})"
            )
        else:
            term_structure = "flat"

    # ----------------------------------------------------------------
    # Skew
    # ----------------------------------------------------------------
    if skew_slope is None:
        skew_state = "unknown"
    elif skew_slope > SKEW_FEARFUL:
        skew_state = "fearful"
        reasoning.append(
            f"Skew slope {skew_slope:+.2f} — put premium elevated, fearful market"
        )
    elif skew_slope > SKEW_MILD_FEARFUL:
        skew_state = "mild_fearful"
    elif skew_slope < SKEW_CALL_FRENZY:
        skew_state = "call_frenzy"
        reasoning.append(
            f"Skew slope {skew_slope:+.2f} — calls > puts, unusual bullish frenzy"
        )
    else:
        skew_state = "neutral"

    # ----------------------------------------------------------------
    # Recommended structure
    # Decision tree: classification × term × tier × catalyst proximity
    # Defined-risk LONG-side only.
    # ----------------------------------------------------------------
    if classification == "cheap" and term_structure == "backwardation":
        recommended_structure = "CALENDAR"
        reasoning.append(
            "Cheap IV + backwardated term → CALENDAR (capture front-IV decay, "
            "own back-end optionality)"
        )
    elif classification == "cheap":
        recommended_structure = "LEAP_CALL"
        reasoning.append(
            "Cheap IV + conviction → LEAP_CALL outright (cheap vega, full convexity, "
            "no need to finance theta when premium already cheap)"
        )
    elif classification == "expensive" and tier == "A":
        recommended_structure = "DIAGONAL"
        reasoning.append(
            "Expensive IV + Tier A → DIAGONAL (sell elevated front IV, own back-dated "
            "exposure, partial theta financing)"
        )
    elif classification == "expensive":
        recommended_structure = "VERTICAL"
        reasoning.append(
            "Expensive IV + Tier B → VERTICAL (finance short leg, defined risk, lower vega)"
        )
    elif classification == "normal" and tier == "A":
        recommended_structure = "LEAP_CALL"
        reasoning.append("Normal IV + Tier A → LEAP_CALL (default convexity expression)")
    elif classification == "normal":
        recommended_structure = "VERTICAL"
        reasoning.append("Normal IV + Tier B → VERTICAL (defined-window, defined-risk)")
    else:
        # unknown classification — safest default
        recommended_structure = "VERTICAL"
        reasoning.append("Classification unknown — VERTICAL is safest default")

    # ----------------------------------------------------------------
    # Sizing modifier
    # cheap IV → size UP to caps (+15%)
    # expensive IV → size DOWN (-20%)
    # ----------------------------------------------------------------
    if classification == "cheap":
        sizing_modifier = SIZING_MOD_CHEAP
        reasoning.append(
            f"Cheap IV → sizing modifier {(SIZING_MOD_CHEAP-1)*100:+.0f}% "
            f"(premium discount earns upsize)"
        )
    elif classification == "expensive":
        sizing_modifier = SIZING_MOD_EXPENSIVE
        reasoning.append(
            f"Expensive IV → sizing modifier {(SIZING_MOD_EXPENSIVE-1)*100:+.0f}% "
            f"(premium tax warrants downsize)"
        )
    else:
        sizing_modifier = SIZING_MOD_NORMAL

    # Catalyst proximity bonus: if catalyst sits within DTE window,
    # expensive IV is partially justified by the upcoming event
    if catalyst_within_dte and classification == "expensive":
        sizing_modifier = min(sizing_modifier + CATALYST_EXPENSIVE_OFFSET, 1.00)
        reasoning.append(
            "Catalyst within DTE — expensive-IV size penalty partially reversed"
        )

    return IVContext(
        ticker=ticker,
        tier=tier,
        iv_rank=iv_rank,
        atm_iv_current=atm_iv_current,
        atm_iv_30d_mean=atm_iv_30d_mean,
        atm_iv_back=atm_iv_back,
        skew_slope=skew_slope,
        target_dte=target_dte,
        catalyst_within_dte=catalyst_within_dte,
        classification=classification,
        term_structure=term_structure,
        skew_state=skew_state,
        recommended_structure=recommended_structure,
        sizing_modifier=sizing_modifier,
        reasoning=reasoning,
    )


# ============================================================================
# OUTPUT FORMATTING
# ============================================================================

def format_iv_context_text(ctx: IVContext, include_reasoning: bool = True) -> str:
    """Compact text report for IV context. Used standalone and embedded in
    position_sizer output."""
    icons = {
        "cheap": "🟢",
        "normal": "⚪",
        "expensive": "🔴",
        "unknown": "❓",
    }
    icon = icons.get(ctx.classification, "❓")

    lines = []
    lines.append("  IV CONTEXT (v11.11 Game B)")
    lines.append("  " + "-" * 68)
    lines.append(f"  {icon} Classification: {ctx.classification.upper()}")
    if ctx.iv_rank is not None:
        lines.append(f"     IV Rank: {ctx.iv_rank:.0f}/100")
    if ctx.atm_iv_current is not None:
        s = f"     Current ATM IV: {ctx.atm_iv_current*100:.1f}%"
        if ctx.atm_iv_30d_mean is not None and ctx.atm_iv_30d_mean > 0:
            delta = (ctx.atm_iv_current - ctx.atm_iv_30d_mean) / ctx.atm_iv_30d_mean * 100
            s += f"  (30d mean: {ctx.atm_iv_30d_mean*100:.1f}%, {delta:+.0f}%)"
        lines.append(s)
    if ctx.term_structure != "unknown":
        lines.append(f"     Term structure: {ctx.term_structure}")
    if ctx.skew_state not in ("unknown", "neutral"):
        lines.append(f"     Skew state: {ctx.skew_state}")
    lines.append(f"     Recommended structure: {ctx.recommended_structure}")
    if ctx.sizing_modifier != 1.00:
        pct = (ctx.sizing_modifier - 1) * 100
        lines.append(f"     Sizing modifier: {pct:+.0f}% to caps-max debit")

    if include_reasoning and ctx.reasoning:
        lines.append("")
        lines.append("  IV REASONING")
        lines.append("  " + "-" * 68)
        for r in ctx.reasoning:
            lines.append(f"  • {r}")

    return "\n".join(lines)


# ============================================================================
# CLI
# ============================================================================

def main() -> int:
    p = argparse.ArgumentParser(description="v11.11 IV context classifier (Game B)")
    p.add_argument("--ticker", required=True)
    p.add_argument("--ivr", type=float,
                   help="IV Rank 0-100 from UW get_stock_screener")
    p.add_argument("--atm-iv", type=float,
                   help="Current ATM IV at target DTE (decimal, e.g. 0.45 = 45%)")
    p.add_argument("--atm-iv-30d-mean", type=float,
                   help="30-day mean of ATM IV (decimal)")
    p.add_argument("--atm-iv-back", type=float,
                   help="ATM IV at longer-dated expiry for term structure")
    p.add_argument("--skew-slope", type=float,
                   help="(25-delta-put IV - 25-delta-call IV) / ATM IV")
    p.add_argument("--target-dte", type=int)
    p.add_argument("--tier", choices=["A", "B", "C"], default="A")
    p.add_argument("--catalyst-within-dte", action="store_true",
                   help="Set when a binary catalyst sits inside the DTE window")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    ctx = classify_iv(
        ticker=args.ticker,
        iv_rank=args.ivr,
        atm_iv_current=args.atm_iv,
        atm_iv_30d_mean=args.atm_iv_30d_mean,
        atm_iv_back=args.atm_iv_back,
        skew_slope=args.skew_slope,
        target_dte=args.target_dte,
        tier=args.tier,
        catalyst_within_dte=args.catalyst_within_dte,
    )

    if args.json:
        print(json.dumps(asdict(ctx), indent=2))
    else:
        print(format_iv_context_text(ctx))

    return 0


if __name__ == "__main__":
    sys.exit(main())
