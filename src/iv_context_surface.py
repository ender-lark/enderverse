#!/usr/bin/env python3
"""
iv_context_surface.py — v11.19 IV Context Block renderer.

Operationalizes P-IV-CONTEXT (CI v11.19, 15th principle): never characterize
IV without IVR and IV-vs-RV. Produces an IV Context Block (header + separator
+ 3 substantive lines) that MUST appear before any options structure
recommendation, sizing call, or premium "expensive/cheap" framing.

Wraps uw_iv_context.py classification primitives for the cheap/normal/expensive
bands, adds explicit IV-vs-RV spread layer (which uw_iv_context.py doesn't
take as direct input — it only knows IV-vs-30d-mean-of-IV).

Shared constants imported from uw_iv_context to avoid drift.

Inputs:
  --ticker TICKER       ticker symbol
  --ivr FLOAT           IV Rank 0-100 (UW get_stock_screener.iv_rank)
  --iv30 FLOAT          IV30 decimal (UW iv30d or volatility_30)
  --rv30 FLOAT          Realized vol 30d decimal (UW realized_volatility)
  --vrp FLOAT           (audit only) variance_risk_premium from UW
  --atm-iv-front FLOAT  (optional) front-expiry ATM IV for term structure
  --atm-iv-back FLOAT   (optional) back-expiry ATM IV for term structure
  --tier {A,B,C}        conviction tier (default A)
  --catalyst-within-dte catalyst sits inside DTE window
  --json                JSON output
  --self-test           run unit tests and exit

Usage:
  python iv_context_surface.py --ticker BMNR --ivr 3.3 --iv30 0.754 --rv30 0.644
  python iv_context_surface.py --self-test
  python iv_context_surface.py --ticker LEU --ivr 13.4 --iv30 0.74 --rv30 1.024 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from typing import Optional

# Shared constants — single source of truth in uw_iv_context.py.
# Fallback duplication only if import unavailable.
try:
    from uw_iv_context import (
        IVR_CHEAP_MAX,
        IVR_EXPENSIVE_MIN,
        BACKWARDATION_THRESHOLD,
        CONTANGO_THRESHOLD,
        SIZING_MOD_CHEAP,
        SIZING_MOD_NORMAL,
        SIZING_MOD_EXPENSIVE,
        CATALYST_EXPENSIVE_OFFSET,
    )
    _CONSTANTS_SOURCE = "uw_iv_context (canonical)"
except ImportError:  # pragma: no cover
    IVR_CHEAP_MAX = 30.0
    IVR_EXPENSIVE_MIN = 70.0
    BACKWARDATION_THRESHOLD = 1.05
    CONTANGO_THRESHOLD = 0.95
    SIZING_MOD_CHEAP = 1.15
    SIZING_MOD_NORMAL = 1.00
    SIZING_MOD_EXPENSIVE = 0.80
    CATALYST_EXPENSIVE_OFFSET = 0.10
    _CONSTANTS_SOURCE = "fallback (uw_iv_context unavailable)"


# v11.19-specific thresholds for IV-vs-RV spread.
# Asymmetric because average variance risk premium across equities is
# positive (~3-5 vol pts), so IV slightly above RV is the normal state.
VRP_PREMIUM_PTS = 0.05      # IV > RV by 5+ vol pts → PREMIUM
VRP_DISCOUNT_PTS = -0.03    # IV < RV by 3+ vol pts → DISCOUNT


@dataclass
class IVSurfaceBlock:
    ticker: str
    tier: str
    iv_rank: Optional[float]
    iv30: Optional[float]
    rv30: Optional[float]
    iv_rv_spread_pts: Optional[float]
    atm_iv_front: Optional[float]
    atm_iv_back: Optional[float]
    ivr_class: str
    iv_rv_class: str
    term_class: str
    composite_class: str
    recommended_structure: str
    sizing_modifier: float
    surface_block: str


# ============================================================================
# Pure classification functions
# ============================================================================

def _classify_ivr(iv_rank: Optional[float]) -> str:
    """Boundary policy: 30.0 → NORMAL, 70.0 → NORMAL (strict inequality)."""
    if iv_rank is None:
        return "UNKNOWN"
    if iv_rank < IVR_CHEAP_MAX:
        return "CHEAP"
    if iv_rank > IVR_EXPENSIVE_MIN:
        return "EXPENSIVE"
    return "NORMAL"


def _classify_iv_rv(
    iv30: Optional[float], rv30: Optional[float]
) -> tuple[str, Optional[float]]:
    """Returns (class, spread_in_vol_points). Spread positive = IV > RV."""
    if iv30 is None or rv30 is None:
        return "UNKNOWN", None
    spread_decimal = iv30 - rv30
    spread_pts = spread_decimal * 100
    if spread_decimal > VRP_PREMIUM_PTS:
        return "PREMIUM", spread_pts
    if spread_decimal < VRP_DISCOUNT_PTS:
        return "DISCOUNT", spread_pts
    return "FAIR", spread_pts


def _classify_term(front: Optional[float], back: Optional[float]) -> str:
    """front/back ratio: >1.05 front-loaded (backwardation), <0.95 back-loaded."""
    if front is None or back is None or back <= 0:
        return "unknown"
    ratio = front / back
    if ratio > BACKWARDATION_THRESHOLD:
        return "front-loaded"
    if ratio < CONTANGO_THRESHOLD:
        return "back-loaded"
    return "flat"


def _composite(ivr_class: str, iv_rv_class: str) -> str:
    """IVR primary; IV-vs-RV refines NORMAL band only."""
    if ivr_class == "UNKNOWN":
        return "unknown"
    if ivr_class == "CHEAP":
        return "cheap"
    if ivr_class == "EXPENSIVE":
        return "expensive"
    if iv_rv_class == "DISCOUNT":
        return "cheap"
    if iv_rv_class == "PREMIUM":
        return "expensive"
    return "normal"


def _recommend_structure(composite: str, term: str, tier: str) -> str:
    tier = tier.upper()
    if composite == "cheap" and term == "front-loaded":
        return "CALENDAR"
    if composite == "cheap":
        return "LEAP_CALL"
    if composite == "expensive" and tier == "A":
        return "DIAGONAL"
    if composite == "expensive":
        return "VERTICAL"
    if composite == "normal" and tier == "A":
        return "LEAP_CALL"
    if composite == "normal":
        return "VERTICAL"
    return "VERTICAL"


def _sizing_modifier(composite: str, catalyst_within_dte: bool) -> float:
    if composite == "cheap":
        return SIZING_MOD_CHEAP
    if composite == "expensive":
        mod = SIZING_MOD_EXPENSIVE
        if catalyst_within_dte:
            mod = min(mod + CATALYST_EXPENSIVE_OFFSET, 1.00)
        return mod
    return SIZING_MOD_NORMAL


# ============================================================================
# Surface block rendering
# ============================================================================

def _render_surface_block(
    ticker: str,
    iv_rank: Optional[float],
    iv30: Optional[float],
    rv30: Optional[float],
    iv_rv_spread_pts: Optional[float],
    iv_rv_class: str,
    term_class: str,
    composite: str,
    structure: str,
    sizing_mod: float,
) -> str:
    icon = {"cheap": "🟢", "normal": "⚪", "expensive": "🔴", "unknown": "❓"}.get(
        composite, "❓"
    )

    if iv_rank is None:
        line1 = "  IVR: — (unknown)"
    else:
        line1 = f"  IVR: {iv_rank:.1f} [{_classify_ivr(iv_rank)}]"

    if iv_rv_spread_pts is None or iv30 is None or rv30 is None:
        line2 = "  IV30 vs RV30: — (RV not provided)"
    else:
        sign = "+" if iv_rv_spread_pts >= 0 else ""
        line2 = (
            f"  IV30 vs RV30: {iv30*100:.1f}% vs {rv30*100:.1f}% "
            f"= {sign}{iv_rv_spread_pts:.1f} vol pts [{iv_rv_class}]"
        )

    sizing_pct = (sizing_mod - 1) * 100
    sizing_str = f"{sizing_pct:+.0f}%" if abs(sizing_pct) > 1e-6 else "0%"
    line3 = (
        f"  Term: {term_class} · → {icon} {composite.upper()} · "
        f"Structure: {structure} · Sizing: {sizing_str}"
    )

    return "\n".join([
        f"  IV CONTEXT — {ticker.upper()}",
        "  " + "-" * 60,
        line1,
        line2,
        line3,
    ])


# ============================================================================
# Core API
# ============================================================================

def build_surface(
    ticker: str,
    iv_rank: Optional[float] = None,
    iv30: Optional[float] = None,
    rv30: Optional[float] = None,
    vrp: Optional[float] = None,
    atm_iv_front: Optional[float] = None,
    atm_iv_back: Optional[float] = None,
    tier: str = "A",
    catalyst_within_dte: bool = False,
) -> IVSurfaceBlock:
    ivr_class = _classify_ivr(iv_rank)
    iv_rv_class, iv_rv_spread_pts = _classify_iv_rv(iv30, rv30)
    term_class = _classify_term(atm_iv_front, atm_iv_back)
    composite = _composite(ivr_class, iv_rv_class)
    structure = _recommend_structure(composite, term_class, tier)
    sizing_mod = _sizing_modifier(composite, catalyst_within_dte)

    surface = _render_surface_block(
        ticker=ticker, iv_rank=iv_rank, iv30=iv30, rv30=rv30,
        iv_rv_spread_pts=iv_rv_spread_pts, iv_rv_class=iv_rv_class,
        term_class=term_class, composite=composite,
        structure=structure, sizing_mod=sizing_mod,
    )

    return IVSurfaceBlock(
        ticker=ticker, tier=tier.upper(),
        iv_rank=iv_rank, iv30=iv30, rv30=rv30,
        iv_rv_spread_pts=iv_rv_spread_pts,
        atm_iv_front=atm_iv_front, atm_iv_back=atm_iv_back,
        ivr_class=ivr_class, iv_rv_class=iv_rv_class,
        term_class=term_class, composite_class=composite,
        recommended_structure=structure, sizing_modifier=sizing_mod,
        surface_block=surface,
    )


# ============================================================================
# Self-test (P-SIMPLICITY runner-coverage leg 2)
# ============================================================================

def _selftest() -> int:
    failures: list[str] = []
    n_cases = 14

    # 1. BMNR calibration (CI v11.19 deployment session)
    bmnr = build_surface(ticker="BMNR", iv_rank=3.3, iv30=0.754, rv30=0.644, tier="A")
    if bmnr.ivr_class != "CHEAP":
        failures.append(f"#1 BMNR ivr_class: expected CHEAP got {bmnr.ivr_class}")
    if bmnr.iv_rv_class != "PREMIUM":
        failures.append(f"#1 BMNR iv_rv_class: expected PREMIUM got {bmnr.iv_rv_class}")
    if bmnr.composite_class != "cheap":
        failures.append(f"#1 BMNR composite: expected cheap got {bmnr.composite_class}")
    if bmnr.recommended_structure != "LEAP_CALL":
        failures.append(f"#1 BMNR structure: expected LEAP_CALL got {bmnr.recommended_structure}")
    if abs(bmnr.sizing_modifier - 1.15) > 1e-6:
        failures.append(f"#1 BMNR sizing: expected 1.15 got {bmnr.sizing_modifier}")

    # 2. LEU calibration
    leu = build_surface(ticker="LEU", iv_rank=13.4, iv30=0.740, rv30=1.024, tier="A")
    if leu.iv_rv_class != "DISCOUNT":
        failures.append(f"#2 LEU iv_rv_class: expected DISCOUNT got {leu.iv_rv_class}")
    if leu.iv_rv_spread_pts is None or abs(leu.iv_rv_spread_pts - (-28.4)) > 0.5:
        failures.append(f"#2 LEU iv_rv_spread_pts: expected ~-28.4 got {leu.iv_rv_spread_pts}")
    if leu.composite_class != "cheap":
        failures.append(f"#2 LEU composite: expected cheap got {leu.composite_class}")

    # 3. EXPENSIVE Tier A → DIAGONAL
    exp_a = build_surface(ticker="XA", iv_rank=85.0, iv30=0.9, rv30=0.5, tier="A")
    if exp_a.recommended_structure != "DIAGONAL":
        failures.append(f"#3 XA structure: expected DIAGONAL got {exp_a.recommended_structure}")

    # 4. EXPENSIVE Tier B → VERTICAL
    exp_b = build_surface(ticker="XB", iv_rank=85.0, iv30=0.9, rv30=0.5, tier="B")
    if exp_b.recommended_structure != "VERTICAL":
        failures.append(f"#4 XB structure: expected VERTICAL got {exp_b.recommended_structure}")

    # 5. NORMAL IVR + DISCOUNT → cheap nudge
    nudge_c = build_surface(ticker="ND", iv_rank=45.0, iv30=0.40, rv30=0.55, tier="A")
    if nudge_c.composite_class != "cheap":
        failures.append(f"#5 ND composite: expected cheap got {nudge_c.composite_class}")

    # 6. NORMAL IVR + PREMIUM → expensive nudge
    nudge_e = build_surface(ticker="NP", iv_rank=45.0, iv30=0.80, rv30=0.50, tier="A")
    if nudge_e.composite_class != "expensive":
        failures.append(f"#6 NP composite: expected expensive got {nudge_e.composite_class}")

    # 7. NORMAL IVR + FAIR → normal
    nudge_f = build_surface(ticker="NF", iv_rank=45.0, iv30=0.50, rv30=0.48, tier="A")
    if nudge_f.composite_class != "normal":
        failures.append(f"#7 NF composite: expected normal got {nudge_f.composite_class}")
    if nudge_f.recommended_structure != "LEAP_CALL":
        failures.append(f"#7 NF structure: expected LEAP_CALL got {nudge_f.recommended_structure}")

    # 8. Term: cheap + front-loaded → CALENDAR
    cal = build_surface(
        ticker="CAL", iv_rank=15.0, iv30=0.50, rv30=0.45,
        atm_iv_front=0.85, atm_iv_back=0.50, tier="A",
    )
    if cal.term_class != "front-loaded":
        failures.append(f"#8 CAL term: expected front-loaded got {cal.term_class}")
    if cal.recommended_structure != "CALENDAR":
        failures.append(f"#8 CAL structure: expected CALENDAR got {cal.recommended_structure}")

    # 9. Catalyst-within-DTE partial offset on expensive
    cat = build_surface(
        ticker="CAT", iv_rank=85.0, iv30=0.9, rv30=0.5, tier="A",
        catalyst_within_dte=True,
    )
    expected = min(SIZING_MOD_EXPENSIVE + CATALYST_EXPENSIVE_OFFSET, 1.00)
    if abs(cat.sizing_modifier - expected) > 1e-6:
        failures.append(f"#9 CAT sizing: expected {expected} got {cat.sizing_modifier}")

    # 10. Unknown inputs
    unk = build_surface(ticker="UNK", iv_rank=None, iv30=None, rv30=None)
    if unk.ivr_class != "UNKNOWN":
        failures.append(f"#10 UNK ivr_class: expected UNKNOWN got {unk.ivr_class}")
    if unk.composite_class != "unknown":
        failures.append(f"#10 UNK composite: expected unknown got {unk.composite_class}")
    if "IVR: — (unknown)" not in unk.surface_block:
        failures.append("#10 UNK surface block missing IVR placeholder")

    # 11. Boundary IVR=30.0 → NORMAL
    b30 = build_surface(ticker="B30", iv_rank=30.0, iv30=0.5, rv30=0.5)
    if b30.ivr_class != "NORMAL":
        failures.append(f"#11 B30 ivr_class: expected NORMAL got {b30.ivr_class}")

    # 12. Boundary IVR=70.0 → NORMAL
    b70 = build_surface(ticker="B70", iv_rank=70.0, iv30=0.5, rv30=0.5)
    if b70.ivr_class != "NORMAL":
        failures.append(f"#12 B70 ivr_class: expected NORMAL got {b70.ivr_class}")

    # 13. Tier C → falls through conservative
    tc = build_surface(ticker="TC", iv_rank=85.0, iv30=0.9, rv30=0.5, tier="C")
    if tc.recommended_structure != "VERTICAL":
        failures.append(f"#13 TC structure: expected VERTICAL got {tc.recommended_structure}")

    # 14. Partial inputs: IVR only
    prt = build_surface(ticker="PRT", iv_rank=15.0, iv30=None, rv30=None)
    if prt.ivr_class != "CHEAP":
        failures.append(f"#14 PRT ivr_class: expected CHEAP got {prt.ivr_class}")
    if prt.iv_rv_class != "UNKNOWN":
        failures.append(f"#14 PRT iv_rv_class: expected UNKNOWN got {prt.iv_rv_class}")
    if prt.composite_class != "cheap":
        failures.append(f"#14 PRT composite: expected cheap got {prt.composite_class}")
    if "RV not provided" not in prt.surface_block:
        failures.append("#14 PRT surface block missing RV-not-provided note")

    if failures:
        print(f"❌ SELF-TEST FAILED — {len(failures)} failures across {n_cases} cases:")
        for f in failures:
            print(f"  • {f}")
        return 1

    print(f"✅ SELF-TEST PASSED — {n_cases}/{n_cases} cases")
    print(f"   Constants source: {_CONSTANTS_SOURCE}")
    print()
    print("Sample output (BMNR, CI v11.19 calibration case):")
    print()
    print(bmnr.surface_block)
    print()
    print("Sample output (LEU, deep IV-vs-RV DISCOUNT):")
    print()
    print(leu.surface_block)
    return 0


# ============================================================================
# CLI
# ============================================================================

def main() -> int:
    p = argparse.ArgumentParser(description="v11.19 P-IV-CONTEXT surface block renderer")
    p.add_argument("--ticker", help="Ticker symbol")
    p.add_argument("--ivr", type=float, help="IV Rank 0-100")
    p.add_argument("--iv30", type=float, help="IV30 decimal")
    p.add_argument("--rv30", type=float, help="RV30 decimal")
    p.add_argument("--vrp", type=float, help="(audit only) variance_risk_premium")
    p.add_argument("--atm-iv-front", type=float, help="Front-expiry ATM IV")
    p.add_argument("--atm-iv-back", type=float, help="Back-expiry ATM IV")
    p.add_argument("--tier", choices=["A", "B", "C"], default="A")
    p.add_argument("--catalyst-within-dte", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--self-test", action="store_true",
                   help="Run unit tests (P-SIMPLICITY runner-coverage leg 2)")
    args = p.parse_args()

    if args.self_test:
        return _selftest()

    if not args.ticker:
        p.error("--ticker required unless --self-test")

    result = build_surface(
        ticker=args.ticker, iv_rank=args.ivr, iv30=args.iv30, rv30=args.rv30,
        vrp=args.vrp, atm_iv_front=args.atm_iv_front, atm_iv_back=args.atm_iv_back,
        tier=args.tier, catalyst_within_dte=args.catalyst_within_dte,
    )

    if args.json:
        print(json.dumps(asdict(result), indent=2))
    else:
        print(result.surface_block)

    return 0


if __name__ == "__main__":
    sys.exit(main())
