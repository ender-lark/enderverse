"""
macro_pulse_scan.py — P-MACRO-CONTEXT operational script (CI v11.25)

Pulls cross-asset macro state and classifies regime. Surfaces structured
macro block for session-open pre-flight + before every Tier A/B capital action.

Same pattern as iv_context_surface.py: pure-logic core, structured output,
UW endpoints feed the inputs.

CLI:
    python macro_pulse_scan.py --yield-data <json> --cross-asset <json> [--prior-10y <float>]
    python macro_pulse_scan.py --self-test
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import Optional


# ---------- ALERT THRESHOLDS ----------

ALERT_10Y_LEVEL = 4.75          # Newton resistance reference
ALERT_2S10S_FLIP = 0            # Curve inversion trigger
ALERT_MOVE_LEVEL = 120          # Rates vol spike
ALERT_DXY_WEEKLY_PCT = 2.0      # Dollar move
ALERT_VIX_LEVEL = 25            # Equity vol
ALERT_WTI_5D_PCT = 5.0          # Oil shock
ALERT_REAL_10Y_5D_BP = 25       # Real-yield shock


# ---------- DATA STRUCTURES ----------

@dataclass
class YieldCurveSnapshot:
    """US Treasury curve state."""
    date: str
    yields: dict  # {"2y": 4.00, "5y": 4.13, "10y": 4.47, "30y": 5.02, ...}

    @property
    def two_ten_spread_bp(self) -> float:
        return round((self.yields.get("10y", 0) - self.yields.get("2y", 0)) * 100, 1)

    @property
    def ten_thirty_spread_bp(self) -> float:
        return round((self.yields.get("30y", 0) - self.yields.get("10y", 0)) * 100, 1)


@dataclass
class CrossAssetSnapshot:
    """Key ETF + index levels for cross-asset reads."""
    tlt_price: float          # 20Y+ Treasury ETF
    ief_price: float          # 7-10Y Treasury ETF
    lqd_price: float          # IG credit
    hyg_price: float          # HY credit
    uup_price: float          # Dollar
    vix_level: float
    gld_price: float
    uso_price: float
    fxi_price: Optional[float] = None
    eem_price: Optional[float] = None
    move_index: Optional[float] = None  # Rates vol; pulled separately or estimated
    # 52w ranges for "testing-lows" classification
    tlt_52w_low: Optional[float] = None
    tlt_52w_high: Optional[float] = None
    ief_52w_low: Optional[float] = None
    ief_52w_high: Optional[float] = None
    hyg_52w_high: Optional[float] = None
    uso_52w_high: Optional[float] = None


@dataclass
class MacroAlerts:
    """Active alerts firing this read."""
    items: list = field(default_factory=list)

    def fire(self, name: str, detail: str):
        self.items.append(f"{name}: {detail}")

    def any_fired(self) -> bool:
        return len(self.items) > 0


@dataclass
class MacroRegime:
    """Classified regime + decision-feed implications."""
    label: str                    # e.g. "DURATION_WEAK_CREDIT_COMPLACENT"
    duration: str                 # "WEAK" / "NEUTRAL" / "STRONG"
    credit: str                   # "RISK_ON" / "NEUTRAL" / "STRESSED"
    dollar: str                   # "STRONG" / "NEUTRAL" / "WEAK"
    vol_regime: str               # "COMPLACENT" / "NORMAL" / "ELEVATED"
    inflation_tape: str           # "HOT" / "NEUTRAL" / "COOL"
    implications: list = field(default_factory=list)


# ---------- CLASSIFIERS ----------

def classify_duration(cross: CrossAssetSnapshot, ten_y: float) -> str:
    """Duration regime from TLT/IEF positioning + 10Y level."""
    if cross.tlt_52w_low and cross.tlt_price <= cross.tlt_52w_low * 1.005:
        return "WEAK"
    if cross.ief_52w_low and cross.ief_price <= cross.ief_52w_low * 1.005:
        return "WEAK"
    if ten_y > ALERT_10Y_LEVEL:
        return "WEAK"
    if cross.tlt_52w_high and cross.tlt_price >= cross.tlt_52w_high * 0.97:
        return "STRONG"
    return "NEUTRAL"


def classify_credit(cross: CrossAssetSnapshot) -> str:
    """Credit regime from HYG positioning. RISK_ON at >=97% of 52w high."""
    if cross.hyg_52w_high and cross.hyg_price >= cross.hyg_52w_high * 0.97:
        return "RISK_ON"
    if cross.hyg_52w_high and cross.hyg_price <= cross.hyg_52w_high * 0.92:
        return "STRESSED"
    return "NEUTRAL"


def classify_dollar(cross: CrossAssetSnapshot, dxy_5d_pct: Optional[float]) -> str:
    """Dollar regime from UUP + 5d change."""
    if dxy_5d_pct is not None:
        if dxy_5d_pct > 1.5:
            return "STRONG"
        if dxy_5d_pct < -1.5:
            return "WEAK"
    # Fallback: UUP level proxy
    if cross.uup_price >= 28.0:
        return "STRONG"
    if cross.uup_price <= 26.5:
        return "WEAK"
    return "NEUTRAL"


def classify_vol(vix: float, move: Optional[float]) -> str:
    """Vol regime from VIX + MOVE."""
    if vix >= ALERT_VIX_LEVEL:
        return "ELEVATED"
    if move is not None and move >= ALERT_MOVE_LEVEL:
        return "ELEVATED"
    if vix <= 19:
        return "COMPLACENT"
    return "NORMAL"


def classify_inflation_tape(cross: CrossAssetSnapshot) -> str:
    """Inflation regime from oil + gold."""
    oil_hot = cross.uso_52w_high and cross.uso_price >= cross.uso_52w_high * 0.95
    if oil_hot:
        return "HOT"
    if cross.uso_52w_high and cross.uso_price <= cross.uso_52w_high * 0.75:
        return "COOL"
    return "NEUTRAL"


# ---------- ALERT CHECKER ----------

def check_alerts(curve: YieldCurveSnapshot, cross: CrossAssetSnapshot,
                 prior_10y: Optional[float] = None,
                 dxy_5d_pct: Optional[float] = None,
                 wti_5d_pct: Optional[float] = None,
                 real_10y_5d_bp: Optional[float] = None) -> MacroAlerts:
    alerts = MacroAlerts()

    ten_y = curve.yields.get("10y", 0)
    if ten_y >= ALERT_10Y_LEVEL:
        alerts.fire("10Y_BREACH", f"10Y at {ten_y:.2f}% (>= {ALERT_10Y_LEVEL}%)")

    if curve.two_ten_spread_bp <= ALERT_2S10S_FLIP:
        alerts.fire("CURVE_FLIP", f"2s10s at {curve.two_ten_spread_bp:.0f}bp")

    if cross.move_index and cross.move_index >= ALERT_MOVE_LEVEL:
        alerts.fire("RATES_VOL", f"MOVE at {cross.move_index:.0f}")

    if dxy_5d_pct is not None and abs(dxy_5d_pct) >= ALERT_DXY_WEEKLY_PCT:
        alerts.fire("DXY_MOVE", f"DXY 5d delta {dxy_5d_pct:+.1f}%")

    if cross.vix_level >= ALERT_VIX_LEVEL:
        alerts.fire("VIX_SPIKE", f"VIX at {cross.vix_level:.1f}")

    if wti_5d_pct is not None and abs(wti_5d_pct) >= ALERT_WTI_5D_PCT:
        alerts.fire("OIL_SHOCK", f"WTI 5d delta {wti_5d_pct:+.1f}%")

    if real_10y_5d_bp is not None and abs(real_10y_5d_bp) >= ALERT_REAL_10Y_5D_BP:
        alerts.fire("REAL_YIELD_SHOCK", f"Real 10Y 5d delta {real_10y_5d_bp:+.0f}bp")

    return alerts


# ---------- REGIME ASSEMBLY ----------

def assemble_regime(curve: YieldCurveSnapshot, cross: CrossAssetSnapshot,
                    dxy_5d_pct: Optional[float] = None) -> MacroRegime:
    ten_y = curve.yields.get("10y", 0)
    duration = classify_duration(cross, ten_y)
    credit = classify_credit(cross)
    dollar = classify_dollar(cross, dxy_5d_pct)
    vol = classify_vol(cross.vix_level, cross.move_index)
    inflation = classify_inflation_tape(cross)

    label = f"{duration}_DUR_{credit}_CREDIT_{vol}_VOL"

    implications = []
    # Decision-feed logic per CI v11.25
    if duration == "WEAK":
        implications.append("LONG_DURATION_HEADWIND: high-P/E growth (NVDA, MU), long-LEAPS face multiple compression")
        implications.append("BMNR_CRYPTO_HEADWIND: real yields rising = alt-asset bid weakens")
    if duration == "WEAK" and credit == "RISK_ON":
        implications.append("LATE_CYCLE_DIVERGENCE: bonds breaking, equity complacent = asymmetric risk")
    if vol == "COMPLACENT":
        implications.append("HEDGE_COST_FAVORABLE: low vol = cheap protection; consider upsizing tail hedges")
    if vol == "ELEVATED":
        implications.append("HEDGE_COST_EXPENSIVE: upsize hedges with caution; consider spread structures vs naked")
    if dollar == "STRONG":
        implications.append("CRITICAL_MINERALS_HEADWIND: DXY strong = commodity headwind")
        implications.append("GLOBAL_EXPORTERS_HEADWIND: NVDA China revenue, AVGO international exposure")
    if dollar == "WEAK":
        implications.append("CRITICAL_MINERALS_TAILWIND: DXY weak = commodity bid (LEU, MP, UUUU)")
    if inflation == "HOT":
        implications.append("LEE_INFLATION_THESIS_CONFIRMED: oil bid supports sticky-inflation regime")
    if curve.two_ten_spread_bp >= 40:
        implications.append("CYCLICAL_TAILWIND: steep curve = financials (XLF, GS), industrials favored")

    return MacroRegime(
        label=label,
        duration=duration,
        credit=credit,
        dollar=dollar,
        vol_regime=vol,
        inflation_tape=inflation,
        implications=implications,
    )


# ---------- SURFACE OUTPUT ----------

def format_macro_block(curve: YieldCurveSnapshot, cross: CrossAssetSnapshot,
                       regime: MacroRegime, alerts: MacroAlerts,
                       prior_10y: Optional[float] = None,
                       dxy_5d_pct: Optional[float] = None,
                       fed_cut_prob_jun: Optional[float] = None,
                       real_10y: Optional[float] = None) -> str:
    """Format the structured macro block for surfacing."""
    ten_y = curve.yields.get("10y", 0)
    ten_y_delta = ""
    if prior_10y is not None:
        delta_bp = round((ten_y - prior_10y) * 100, 0)
        ten_y_delta = f" (Δ {delta_bp:+.0f}bp 5d)"

    dxy_str = f"DXY proxy UUP {cross.uup_price:.2f}"
    if dxy_5d_pct is not None:
        dxy_str = f"DXY {cross.uup_price:.2f} (Δ {dxy_5d_pct:+.1f}%)"

    move_str = f"MOVE {cross.move_index:.0f}" if cross.move_index else "MOVE n/a"
    fed_str = f"Fed Jun cut prob {fed_cut_prob_jun*100:.0f}%" if fed_cut_prob_jun else "Fed Jun cut prob n/a"
    real_str = f"Real 10Y {real_10y:.2f}%" if real_10y else ""

    line1 = (f"MACRO: 10Y {ten_y:.2f}%{ten_y_delta} · 2s10s "
             f"{curve.two_ten_spread_bp:+.0f}bp · {dxy_str} · "
             f"VIX {cross.vix_level:.1f} · {move_str}")
    line2 = (f"       WTI proxy USO ${cross.uso_price:.2f} · {fed_str}"
             + (f" · {real_str}" if real_str else ""))

    output_lines = [
        "MACRO PULSE",
        "-" * 60,
        line1,
        line2,
        f"       REGIME: {regime.label}",
        f"       Duration={regime.duration} · Credit={regime.credit} · "
        f"Dollar={regime.dollar} · Vol={regime.vol_regime} · Inflation={regime.inflation_tape}",
    ]

    if alerts.any_fired():
        output_lines.append("")
        output_lines.append("🚨 MACRO ALERTS FIRING:")
        for item in alerts.items:
            output_lines.append(f"   • {item}")

    if regime.implications:
        output_lines.append("")
        output_lines.append("IMPLICATIONS (decision feed):")
        for imp in regime.implications:
            output_lines.append(f"   • {imp}")

    return "\n".join(output_lines)


# ---------- SELF TEST ----------

def self_test() -> bool:
    """Verify pure-logic with synthetic Monday 5/18/26 inputs."""
    print("macro_pulse_scan self-test starting...")
    print()

    # Real Monday 5/18/26 data from this session
    curve = YieldCurveSnapshot(
        date="2026-05-14",
        yields={"2y": 4.00, "5y": 4.13, "10y": 4.47, "30y": 5.02},
    )

    cross = CrossAssetSnapshot(
        tlt_price=83.66, tlt_52w_low=83.30, tlt_52w_high=92.19,
        ief_price=93.51, ief_52w_low=93.03, ief_52w_high=98.05,
        lqd_price=107.86,
        hyg_price=79.46, hyg_52w_high=81.36,
        uup_price=27.77,
        vix_level=18.43,
        gld_price=417.29,
        uso_price=148.23, uso_52w_high=151.63,
        move_index=None,
    )

    alerts = check_alerts(curve, cross, dxy_5d_pct=0.5)
    regime = assemble_regime(curve, cross, dxy_5d_pct=0.5)
    output = format_macro_block(curve, cross, regime, alerts, prior_10y=4.42)
    print(output)
    print()

    # Assertions
    assertions_passed = 0
    assertions_failed = 0

    def assert_eq(label, actual, expected):
        nonlocal assertions_passed, assertions_failed
        if actual == expected:
            print(f"  ✓ {label}: {actual}")
            assertions_passed += 1
        else:
            print(f"  ✗ {label}: got {actual}, expected {expected}")
            assertions_failed += 1

    print("Assertions:")
    assert_eq("2s10s spread", curve.two_ten_spread_bp, 47.0)
    assert_eq("10s30s spread", curve.ten_thirty_spread_bp, 55.0)
    assert_eq("Duration regime (TLT at 52w lows)", regime.duration, "WEAK")
    assert_eq("Credit regime (HYG near 52w highs)", regime.credit, "RISK_ON")
    assert_eq("Vol regime (VIX 18.43)", regime.vol_regime, "COMPLACENT")
    assert_eq("Inflation tape (oil near 52w highs)", regime.inflation_tape, "HOT")
    assert_eq("No 10Y alert (4.47 < 4.75)", any("10Y_BREACH" in a for a in alerts.items), False)
    assert_eq("No curve flip alert", any("CURVE_FLIP" in a for a in alerts.items), False)

    # Verify decision-feed implications
    impl_text = " ".join(regime.implications)
    assert_eq("LONG_DURATION_HEADWIND surfaced", "LONG_DURATION_HEADWIND" in impl_text, True)
    assert_eq("LATE_CYCLE_DIVERGENCE surfaced", "LATE_CYCLE_DIVERGENCE" in impl_text, True)
    assert_eq("HEDGE_COST_FAVORABLE surfaced", "HEDGE_COST_FAVORABLE" in impl_text, True)
    assert_eq("LEE_INFLATION_THESIS_CONFIRMED surfaced", "LEE_INFLATION_THESIS_CONFIRMED" in impl_text, True)
    assert_eq("CYCLICAL_TAILWIND surfaced", "CYCLICAL_TAILWIND" in impl_text, True)

    # Edge case: alert firing
    print()
    print("Alert-firing test (10Y > 4.75% scenario):")
    curve_alert = YieldCurveSnapshot(date="test", yields={"2y": 4.00, "10y": 4.80, "30y": 5.10})
    cross_alert = CrossAssetSnapshot(
        tlt_price=82.0, tlt_52w_low=82.0, tlt_52w_high=92.0,
        ief_price=92.5, ief_52w_low=92.5, ief_52w_high=98.0,
        lqd_price=106.0, hyg_price=78.0, hyg_52w_high=81.0,
        uup_price=28.5, vix_level=26.0,
        gld_price=415.0, uso_price=150.0, uso_52w_high=151.0,
        move_index=135,
    )
    alerts_test = check_alerts(curve_alert, cross_alert, dxy_5d_pct=2.5, wti_5d_pct=6.0)
    assert_eq("10Y breach fired", any("10Y_BREACH" in a for a in alerts_test.items), True)
    assert_eq("MOVE alert fired", any("RATES_VOL" in a for a in alerts_test.items), True)
    assert_eq("DXY alert fired", any("DXY_MOVE" in a for a in alerts_test.items), True)
    assert_eq("VIX alert fired", any("VIX_SPIKE" in a for a in alerts_test.items), True)
    assert_eq("Oil alert fired", any("OIL_SHOCK" in a for a in alerts_test.items), True)

    print()
    print(f"Results: {assertions_passed} passed, {assertions_failed} failed")
    return assertions_failed == 0


# ---------- CLI ENTRY ----------

def main():
    parser = argparse.ArgumentParser(description="macro_pulse_scan — P-MACRO-CONTEXT")
    parser.add_argument("--self-test", action="store_true", help="Run self-test with synthetic 5/18/26 data")
    parser.add_argument("--yield-data", type=str, help="Path to JSON file with yield curve data")
    parser.add_argument("--cross-asset", type=str, help="Path to JSON file with cross-asset data")
    parser.add_argument("--prior-10y", type=float, help="Prior 10Y yield (for delta calc)")
    parser.add_argument("--dxy-5d-pct", type=float, help="DXY 5-day change %")
    args = parser.parse_args()

    if args.self_test:
        ok = self_test()
        sys.exit(0 if ok else 1)

    if not (args.yield_data and args.cross_asset):
        parser.print_help()
        sys.exit(1)

    with open(args.yield_data) as f:
        ydata = json.load(f)
    with open(args.cross_asset) as f:
        cdata = json.load(f)

    curve = YieldCurveSnapshot(date=ydata["date"], yields=ydata["yields"])
    cross = CrossAssetSnapshot(**cdata)
    alerts = check_alerts(curve, cross, prior_10y=args.prior_10y, dxy_5d_pct=args.dxy_5d_pct)
    regime = assemble_regime(curve, cross, dxy_5d_pct=args.dxy_5d_pct)
    print(format_macro_block(curve, cross, regime, alerts,
                              prior_10y=args.prior_10y, dxy_5d_pct=args.dxy_5d_pct))


if __name__ == "__main__":
    main()
