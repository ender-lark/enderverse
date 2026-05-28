#!/usr/bin/env python3
"""
regime_detector.py — Market regime classifier
Candidate L (v11.9) — Launcher Step 7

Classifies the current market regime into one of:
  RISK_ON      — trend intact, breadth healthy, vol contained
  TRANSITION   — mixed signals, breadth deteriorating, vol elevated
  DEFENSIVE    — clear trend break, broad weakness, vol expanded
  CAPITULATION — SPX -15%+ from high AND VIX >30 AND >10d off high

Designed for Launcher Step 7 surfacing. Pure functions — no I/O. Caller
provides current market data via a MarketSnapshot dataclass.

Used by P-WAKE-UP trigger evaluation and by Two-Lens / asymmetric output
formatting (current regime appears in the launcher output header).

Usage:
  from regime_detector import classify, MarketSnapshot
  snap = MarketSnapshot(spx=7444, spx_50dma=7150, spx_200dma=6500,
                        spx_from_52w_high_pct=-0.005,
                        days_since_52w_high=4, vix=18.5,
                        breadth_above_20dma_pct=0.45)
  regime, reasons = classify(snap)

Self-test:
  python3 regime_detector.py --self-test
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ============================================================================
# Regime constants
# ============================================================================

RISK_ON = "RISK_ON"
TRANSITION = "TRANSITION"
DEFENSIVE = "DEFENSIVE"
CAPITULATION = "CAPITULATION"


# Thresholds (operator-tunable, conservative defaults)
@dataclass
class RegimeThresholds:
    # CAPITULATION (per P-WAKE-UP trigger)
    capit_spx_drawdown: float = -0.15      # SPX from 52w high
    capit_vix: float = 30.0
    capit_days_off_high: int = 10

    # DEFENSIVE
    def_spx_below_50dma: bool = True       # SPX below 50DMA
    def_breadth_max: float = 0.30          # < 30% of R3K above 20DMA
    def_vix_min: float = 22.0

    # RISK_ON (must satisfy ALL)
    risk_spx_above_50dma: bool = True
    risk_breadth_min: float = 0.50         # ≥ 50% of R3K above 20DMA
    risk_vix_max: float = 18.0

    # Everything else = TRANSITION


@dataclass
class MarketSnapshot:
    """Current market data inputs. All required."""
    spx: float
    spx_50dma: float
    spx_200dma: float
    spx_from_52w_high_pct: float  # negative if below high (e.g. -0.08 for -8%)
    days_since_52w_high: int
    vix: float
    breadth_above_20dma_pct: float  # 0.0-1.0, e.g. 0.45 for 45%

    # Optional context
    spx_20dma: Optional[float] = None
    dxy: Optional[float] = None
    wti: Optional[float] = None
    tnx: Optional[float] = None


# ============================================================================
# Classification logic
# ============================================================================

def classify(
    snap: MarketSnapshot, thresholds: Optional[RegimeThresholds] = None
) -> tuple[str, list[str]]:
    """
    Classify the regime. Returns (regime_name, list_of_reasons).

    Reasons are short human-readable strings explaining the call.
    """
    t = thresholds or RegimeThresholds()
    reasons: list[str] = []

    # CAPITULATION — strictest gate, all three must fire
    if (snap.spx_from_52w_high_pct <= t.capit_spx_drawdown
            and snap.vix >= t.capit_vix
            and snap.days_since_52w_high >= t.capit_days_off_high):
        reasons.append(
            f"SPX {snap.spx_from_52w_high_pct*100:.1f}% from 52w high "
            f"(≤ {t.capit_spx_drawdown*100:.0f}%)"
        )
        reasons.append(f"VIX {snap.vix:.1f} (≥ {t.capit_vix:.0f})")
        reasons.append(
            f"{snap.days_since_52w_high}d off high (≥ {t.capit_days_off_high}d)"
        )
        return CAPITULATION, reasons

    # DEFENSIVE — SPX below 50DMA AND (breadth broken OR vix elevated)
    spx_below_50 = snap.spx < snap.spx_50dma
    breadth_broken = snap.breadth_above_20dma_pct < t.def_breadth_max
    vix_elevated = snap.vix >= t.def_vix_min

    if spx_below_50 and (breadth_broken or vix_elevated):
        reasons.append(f"SPX {snap.spx:.0f} below 50DMA {snap.spx_50dma:.0f}")
        if breadth_broken:
            reasons.append(
                f"Breadth {snap.breadth_above_20dma_pct*100:.0f}% "
                f"(< {t.def_breadth_max*100:.0f}% threshold)"
            )
        if vix_elevated:
            reasons.append(f"VIX {snap.vix:.1f} (≥ {t.def_vix_min:.0f})")
        return DEFENSIVE, reasons

    # RISK_ON — all three must fire
    spx_above_50 = snap.spx > snap.spx_50dma
    breadth_healthy = snap.breadth_above_20dma_pct >= t.risk_breadth_min
    vix_contained = snap.vix < t.risk_vix_max

    if spx_above_50 and breadth_healthy and vix_contained:
        reasons.append(f"SPX {snap.spx:.0f} above 50DMA {snap.spx_50dma:.0f}")
        reasons.append(
            f"Breadth {snap.breadth_above_20dma_pct*100:.0f}% "
            f"(≥ {t.risk_breadth_min*100:.0f}% threshold)"
        )
        reasons.append(f"VIX {snap.vix:.1f} (< {t.risk_vix_max:.0f})")
        return RISK_ON, reasons

    # TRANSITION — mixed signals
    if spx_above_50:
        reasons.append(f"SPX {snap.spx:.0f} above 50DMA — trend intact")
    else:
        reasons.append(f"SPX {snap.spx:.0f} below 50DMA — trend pressured")

    reasons.append(
        f"Breadth {snap.breadth_above_20dma_pct*100:.0f}% — "
        + ("healthy" if breadth_healthy else "deteriorating")
    )
    reasons.append(
        f"VIX {snap.vix:.1f} — "
        + ("contained" if vix_contained else "elevated")
    )
    return TRANSITION, reasons


def regime_summary_line(snap: MarketSnapshot,
                        thresholds: Optional[RegimeThresholds] = None) -> str:
    """One-line summary suitable for Launcher Step 7 output."""
    regime, reasons = classify(snap, thresholds)
    return f"Regime: {regime}. " + " | ".join(reasons)


# ============================================================================
# P-WAKE-UP trigger evaluation
# ============================================================================

def is_p_wake_up_capitulation(snap: MarketSnapshot) -> bool:
    """
    Returns True if the SPX-wide capitulation trigger of P-WAKE-UP fires.
    This is distinct from the single-name capitulation trigger (which lives
    in the position-level evaluator, not here).
    """
    regime, _ = classify(snap)
    return regime == CAPITULATION


# ============================================================================
# Self-test
# ============================================================================

def _run_self_test() -> tuple[int, int]:
    passes = 0
    fails = 0

    def check(name: str, cond: bool):
        nonlocal passes, fails
        if cond:
            passes += 1
            print(f"  PASS  {name}")
        else:
            fails += 1
            print(f"  FAIL  {name}")

    # Test 1: clean RISK_ON
    snap = MarketSnapshot(
        spx=7500, spx_50dma=7100, spx_200dma=6500,
        spx_from_52w_high_pct=-0.002,
        days_since_52w_high=1, vix=15.5,
        breadth_above_20dma_pct=0.65,
    )
    r, _ = classify(snap)
    check("Test 1: clean RISK_ON classified", r == RISK_ON)

    # Test 2: current state (5/14/26) classifies as TRANSITION
    snap = MarketSnapshot(
        spx=7444, spx_50dma=7150, spx_200dma=6500,
        spx_from_52w_high_pct=-0.005,
        days_since_52w_high=4, vix=18.5,
        breadth_above_20dma_pct=0.45,
    )
    r, _ = classify(snap)
    check("Test 2: current 5/14/26 state -> TRANSITION", r == TRANSITION)

    # Test 3: DEFENSIVE on SPX below 50DMA + breadth broken
    snap = MarketSnapshot(
        spx=6900, spx_50dma=7100, spx_200dma=6500,
        spx_from_52w_high_pct=-0.08,
        days_since_52w_high=8, vix=24.0,
        breadth_above_20dma_pct=0.22,
    )
    r, _ = classify(snap)
    check("Test 3: SPX below 50DMA + bad breadth -> DEFENSIVE", r == DEFENSIVE)

    # Test 4: CAPITULATION (matches P-WAKE-UP)
    snap = MarketSnapshot(
        spx=5500, spx_50dma=6900, spx_200dma=6500,
        spx_from_52w_high_pct=-0.20,
        days_since_52w_high=15, vix=35.0,
        breadth_above_20dma_pct=0.12,
    )
    r, _ = classify(snap)
    check("Test 4: SPX -20%, VIX 35, 15d off high -> CAPITULATION",
          r == CAPITULATION)
    check("Test 4b: is_p_wake_up_capitulation returns True",
          is_p_wake_up_capitulation(snap))

    # Test 5: borderline — VIX 21, breadth 0.45, SPX above 50DMA -> TRANSITION
    snap = MarketSnapshot(
        spx=7300, spx_50dma=7100, spx_200dma=6500,
        spx_from_52w_high_pct=-0.03,
        days_since_52w_high=6, vix=21.0,
        breadth_above_20dma_pct=0.45,
    )
    r, _ = classify(snap)
    check("Test 5: VIX 21 + breadth 45% + SPX above 50DMA -> TRANSITION",
          r == TRANSITION)

    # Test 6: SPX below 50DMA but breadth ok, vix ok -> NOT defensive
    snap = MarketSnapshot(
        spx=7050, spx_50dma=7100, spx_200dma=6500,
        spx_from_52w_high_pct=-0.04,
        days_since_52w_high=6, vix=17.0,
        breadth_above_20dma_pct=0.52,
    )
    r, _ = classify(snap)
    check("Test 6: SPX barely under 50DMA, otherwise healthy -> TRANSITION",
          r == TRANSITION)

    # Test 7: not all 3 capit conditions -> not CAPITULATION
    snap = MarketSnapshot(
        spx=6300, spx_50dma=6900, spx_200dma=6500,
        spx_from_52w_high_pct=-0.16,  # ≤ threshold
        days_since_52w_high=12,        # ≥ threshold
        vix=28.0,                       # < 30, fails
        breadth_above_20dma_pct=0.18,
    )
    r, _ = classify(snap)
    check("Test 7: SPX -16% + 12d off + VIX 28 -> DEFENSIVE (not CAPIT)",
          r == DEFENSIVE)

    # Test 8: regime_summary_line returns string with regime + reasons
    snap = MarketSnapshot(
        spx=7444, spx_50dma=7150, spx_200dma=6500,
        spx_from_52w_high_pct=-0.005,
        days_since_52w_high=4, vix=18.5,
        breadth_above_20dma_pct=0.45,
    )
    summary = regime_summary_line(snap)
    check("Test 8: regime_summary_line returns useful string",
          "Regime:" in summary and "TRANSITION" in summary)

    return passes, fails


def _main_cli():
    import argparse, sys
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true",
                    help="Run self-test (8 assertions)")
    ap.add_argument("--spx", type=float, help="SPX close")
    ap.add_argument("--spx-50dma", type=float, help="SPX 50-day moving avg")
    ap.add_argument("--spx-200dma", type=float, help="SPX 200-day moving avg")
    ap.add_argument("--vix", type=float, help="VIX close")
    ap.add_argument("--breadth", type=float,
                    help="% R3K above 20DMA (0-1)")
    ap.add_argument("--drawdown", type=float, default=0.0,
                    help="SPX % from 52w high (e.g. -0.05 for -5%%)")
    ap.add_argument("--days-off-high", type=int, default=0)
    args = ap.parse_args()

    if args.self_test:
        print("=" * 70)
        print("REGIME_DETECTOR SELF-TEST")
        print("=" * 70)
        passes, fails = _run_self_test()
        print()
        print(f"RESULT: {passes}/{passes + fails} passed")
        return 0 if fails == 0 else 1

    if args.spx and args.spx_50dma and args.vix and args.breadth is not None:
        snap = MarketSnapshot(
            spx=args.spx, spx_50dma=args.spx_50dma,
            spx_200dma=args.spx_200dma or args.spx_50dma * 0.85,
            spx_from_52w_high_pct=args.drawdown,
            days_since_52w_high=args.days_off_high,
            vix=args.vix, breadth_above_20dma_pct=args.breadth,
        )
        print(regime_summary_line(snap))
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main_cli())
