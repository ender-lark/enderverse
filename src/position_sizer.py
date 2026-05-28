#!/usr/bin/env python3
"""
position_sizer.py — Sizing-to-caps helper for v11.10 P-ASYMMETRIC

Operationalizes the four-cap framework added in v11.10:
  1. Position heat cap by tier (15% / 10% / 7% for A / B / C)
  2. Theme concentration cap (35% of sleeve heat per factor bucket)
  3. Greek stress caps (1.5x delta-notional, 0.25%/day theta, 12% vol-shock)
  4. Correlation discount via N_eff = N / (1 + (N-1) * rho_avg)

Behavioral rule per v11.10: once structure clears reward floor AND fits all four
caps, size to MAXIMUM allowed by caps, not symbolic debit. This is the direct
fix for the documented 4.5-7.6x under-sizing failure mode.

Output: GREEN / YELLOW / RED gate + max-additional-size-at-cap-floor.

Usage:
  python position_sizer.py --ticker LEU --structure leap_call --debit 3600 \\
                           --tier A --factor nuclear --sleeve 30000

  python position_sizer.py --ticker IONQ --structure vert_spread --debit 3920 \\
                           --tier B --factor quantum --sleeve 30000 \\
                           --contracts 7

  python position_sizer.py --help-factors    # list factor buckets + ρ defaults
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict, field
from typing import Optional

# ============================================================================
# CONFIGURATION
# ============================================================================

# Tier-based position heat caps (worst-case loss / sleeve value)
TIER_HEAT_CAPS = {
    "A": 0.15,   # Tier A — Generational option
    "B": 0.10,   # Tier B — Defined-window thesis
    "C": 0.07,   # Tier C — Speculative
}

# Theme concentration cap (factor-bucket premium-at-risk / sleeve heat)
THEME_CONCENTRATION_CAP = 0.35

# Greek stress caps (sleeve-aggregate)
GREEK_CAPS = {
    "delta_notional_mult": 1.5,      # delta-notional / sleeve value
    "daily_theta_pct": 0.0025,        # daily theta / sleeve value (= 0.25%)
    "vol_shock_10pt_pct": 0.12,       # P/L on 10-vol-point IV shock / sleeve value
}

# Default ρ_avg per factor bucket (fallback when no live correlation matrix)
FACTOR_RHO_DEFAULTS = {
    "ai_complex":     0.70,   # NVDA / MU / AVGO / SMH / MAGS — calibrated
    "semis":          0.70,   # broader semi names
    "nuclear":        0.60,   # LEU / UUUU / CCJ / NRG fuel-cycle
    "critical_min":   0.55,   # MP / USAR rare-earth complex
    "quantum":        0.65,   # IONQ / RGTI / QBTS / QUBT
    "eth_complex":    0.75,   # BMNR / ETHA / ETH-DAT names
    "btc_complex":    0.75,   # MSTR / COIN / etc
    "ai_picks_n_shovels": 0.55,  # NBIS / CRWV / Oracle-AI / etc
    "spdr_sector":    0.60,   # same SPDR sector default
    "cross_sector":   0.30,   # unrelated factor — diversifying
    "solo":           1.00,   # only name in factor bucket → N_eff = N = 1
}

# Implied Greek defaults by structure (rough Black-Scholes inference)
# Used when live Greeks not supplied. Operator can override via CLI flags.
STRUCTURE_GREEK_DEFAULTS = {
    "leap_call": {
        "delta_per_contract": 0.45,        # ATM-ish 12+ month LEAP
        "theta_per_contract_per_day": 13,  # $13/day for LEU $300 LEAP — scale linearly with debit
        "vega_per_contract": 0.50,         # $50 per vol point
    },
    "vert_spread": {
        "delta_per_contract": 0.25,        # net delta on call vert spread ATM
        "theta_per_contract_per_day": 3,
        "vega_per_contract": 0.10,
    },
    "put_spread": {
        "delta_per_contract": -0.20,
        "theta_per_contract_per_day": 3,
        "vega_per_contract": 0.10,
    },
    "diagonal": {
        "delta_per_contract": 0.30,
        "theta_per_contract_per_day": 5,   # net positive on short front leg, but inferred neg here for conservatism
        "vega_per_contract": 0.30,
    },
    "calendar": {
        "delta_per_contract": 0.02,
        "theta_per_contract_per_day": 1,   # near-zero net theta
        "vega_per_contract": 0.30,
    },
    "atm_put": {
        "delta_per_contract": -0.45,
        "theta_per_contract_per_day": 15,
        "vega_per_contract": 0.40,
    },
}

SLEEVE_VALUE_DEFAULT = 30000  # $30K default Asymmetric Sleeve


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class CapEvaluation:
    """Result of evaluating a prospective position against all four caps."""
    ticker: str
    structure: str
    tier: str
    factor: str
    debit: float
    contracts: int
    sleeve_value: float
    underlying_price: Optional[float]

    # Position heat
    position_heat_pct: float
    position_heat_cap_pct: float
    position_heat_gate: str  # GREEN / YELLOW / RED

    # Theme concentration
    theme_concentration_pct: float
    theme_concentration_cap_pct: float
    theme_concentration_gate: str

    # Greek stress
    delta_notional: float
    delta_notional_cap: float
    delta_notional_gate: str
    daily_theta: float
    daily_theta_cap: float
    daily_theta_gate: str
    vol_shock_pl: float
    vol_shock_cap: float
    vol_shock_gate: str

    # N_eff correlation discount
    n_in_factor: int
    rho_avg: float
    n_eff: float
    n_eff_ratio: float  # N_eff / N — scale factor for factor-level sizing

    # Overall gate
    overall_gate: str  # GREEN / YELLOW / RED
    binding_constraint: str  # Which cap is tightest
    max_additional_debit: float  # How much more $ can be added before binding cap
    max_additional_contracts: int  # Same, in contract terms

    # Reasoning
    notes: list[str] = field(default_factory=list)

    # IV overlay (v11.12 Patch 1) — populated only when an iv_context is supplied.
    # When absent, all three stay None and output is identical to v11.10 baseline.
    iv_context: Optional[object] = None          # IVContext from uw_iv_context.classify_iv
    iv_adjusted_max_debit: Optional[float] = None
    iv_adjusted_max_contracts: Optional[int] = None


# ============================================================================
# CAP EVALUATION
# ============================================================================

def evaluate_position(
    ticker: str,
    structure: str,
    debit: float,
    tier: str,
    factor: str,
    sleeve_value: float = SLEEVE_VALUE_DEFAULT,
    contracts: int = 1,
    underlying_price: Optional[float] = None,
    existing_factor_heat: float = 0.0,
    existing_sleeve_delta_notional: float = 0.0,
    existing_sleeve_daily_theta: float = 0.0,
    existing_sleeve_vol_shock_pl: float = 0.0,
    n_in_factor: int = 1,  # Number of positions in this factor bucket AFTER adding this one
    rho_avg: Optional[float] = None,
    delta_override: Optional[float] = None,
    theta_override: Optional[float] = None,
    vega_override: Optional[float] = None,
    iv_context: Optional[object] = None,
) -> CapEvaluation:
    """
    Evaluate a prospective position against all four caps.

    Returns CapEvaluation with GREEN/YELLOW/RED gate + max-additional-size.
    """
    tier = tier.upper()
    if tier not in TIER_HEAT_CAPS:
        raise ValueError(f"Unknown tier {tier!r}; valid: {list(TIER_HEAT_CAPS.keys())}")

    if rho_avg is None:
        rho_avg = FACTOR_RHO_DEFAULTS.get(factor, 0.50)

    # Greek defaults from structure
    greek_defaults = STRUCTURE_GREEK_DEFAULTS.get(structure, STRUCTURE_GREEK_DEFAULTS["leap_call"])
    delta_per_contract = delta_override if delta_override is not None else greek_defaults["delta_per_contract"]
    theta_per_contract = theta_override if theta_override is not None else greek_defaults["theta_per_contract_per_day"]
    vega_per_contract = vega_override if vega_override is not None else greek_defaults["vega_per_contract"]

    notes = []

    # ------------------------------------------------------------------
    # CAP 1 — Position heat (worst-case loss / sleeve)
    # ------------------------------------------------------------------
    position_heat = debit / sleeve_value
    heat_cap = TIER_HEAT_CAPS[tier]
    if position_heat <= heat_cap * 0.8:
        heat_gate = "GREEN"
    elif position_heat <= heat_cap:
        heat_gate = "YELLOW"
    else:
        heat_gate = "RED"
        notes.append(
            f"Position heat {position_heat*100:.1f}% exceeds Tier {tier} cap of "
            f"{heat_cap*100:.0f}% — reduce debit or split entry"
        )

    # ------------------------------------------------------------------
    # CAP 2 — Theme concentration (factor heat / sleeve heat)
    # ------------------------------------------------------------------
    # Sleeve heat is the sum of all position max-losses (current + this one)
    new_factor_heat = existing_factor_heat + debit
    sleeve_heat_total = existing_factor_heat + debit  # conservative: assume this is the only known factor; operator may supply broader
    theme_concentration = new_factor_heat / sleeve_value  # vs sleeve value, not just sleeve heat — simpler/clearer
    theme_cap = THEME_CONCENTRATION_CAP
    if theme_concentration <= theme_cap * 0.8:
        theme_gate = "GREEN"
    elif theme_concentration <= theme_cap:
        theme_gate = "YELLOW"
    else:
        theme_gate = "RED"
        notes.append(
            f"Theme concentration ({factor}) at {theme_concentration*100:.1f}% of sleeve "
            f"exceeds 35% cap — reduce or hedge factor exposure"
        )

    # ------------------------------------------------------------------
    # CAP 3 — Greek stress (sleeve aggregate)
    # ------------------------------------------------------------------
    # Delta notional
    if underlying_price is None:
        # Estimate: typical AI/semi/nuclear name $50-300 range; use proxy $100 if missing
        underlying_price = 100.0
        notes.append(f"Underlying price not provided; using $100 proxy for delta-notional calc")
    position_delta_notional = delta_per_contract * contracts * 100 * underlying_price
    new_sleeve_delta_notional = existing_sleeve_delta_notional + position_delta_notional
    delta_cap = GREEK_CAPS["delta_notional_mult"] * sleeve_value
    if abs(new_sleeve_delta_notional) <= delta_cap * 0.8:
        delta_gate = "GREEN"
    elif abs(new_sleeve_delta_notional) <= delta_cap:
        delta_gate = "YELLOW"
    else:
        delta_gate = "RED"
        notes.append(
            f"Sleeve delta-notional ${new_sleeve_delta_notional:,.0f} exceeds "
            f"1.5× sleeve cap of ${delta_cap:,.0f}"
        )

    # Daily theta
    position_theta = theta_per_contract * contracts
    new_sleeve_theta = existing_sleeve_daily_theta + position_theta
    theta_cap_abs = GREEK_CAPS["daily_theta_pct"] * sleeve_value
    if abs(new_sleeve_theta) <= theta_cap_abs * 0.8:
        theta_gate = "GREEN"
    elif abs(new_sleeve_theta) <= theta_cap_abs:
        theta_gate = "YELLOW"
    else:
        theta_gate = "RED"
        notes.append(
            f"Sleeve daily theta ${new_sleeve_theta:.2f}/day exceeds 0.25%/day cap of "
            f"${theta_cap_abs:.2f}"
        )

    # Vol shock (10 vol point IV move)
    position_vol_shock = vega_per_contract * contracts * 100 * 10  # 10 vol points
    new_sleeve_vol_shock = existing_sleeve_vol_shock_pl + position_vol_shock
    vol_cap_abs = GREEK_CAPS["vol_shock_10pt_pct"] * sleeve_value
    if abs(new_sleeve_vol_shock) <= vol_cap_abs * 0.8:
        vol_gate = "GREEN"
    elif abs(new_sleeve_vol_shock) <= vol_cap_abs:
        vol_gate = "YELLOW"
    else:
        vol_gate = "RED"
        notes.append(
            f"Sleeve 10-vol-pt shock exposure ${new_sleeve_vol_shock:,.0f} exceeds "
            f"12% cap of ${vol_cap_abs:,.0f}"
        )

    # ------------------------------------------------------------------
    # CAP 4 — N_eff correlation discount
    # ------------------------------------------------------------------
    if n_in_factor <= 1:
        n_eff = 1.0
        n_eff_ratio = 1.0
    else:
        n_eff = n_in_factor / (1 + (n_in_factor - 1) * rho_avg)
        n_eff_ratio = n_eff / n_in_factor

    if n_eff_ratio < 0.5:
        notes.append(
            f"N_eff = {n_eff:.2f} for N={n_in_factor} at ρ={rho_avg:.2f} — factor-level "
            f"effective bets is {n_eff_ratio*100:.0f}% of nominal count. Scale factor heat by "
            f"sqrt({n_eff_ratio:.2f}) = {n_eff_ratio**0.5:.2f}"
        )

    # ------------------------------------------------------------------
    # OVERALL GATE
    # ------------------------------------------------------------------
    gates = [heat_gate, theme_gate, delta_gate, theta_gate, vol_gate]
    if "RED" in gates:
        overall_gate = "RED"
    elif "YELLOW" in gates:
        overall_gate = "YELLOW"
    else:
        overall_gate = "GREEN"

    # Binding constraint — find which cap is tightest (highest utilization ratio)
    utilizations = {
        "position_heat": position_heat / heat_cap,
        "theme_concentration": theme_concentration / theme_cap,
        "delta_notional": abs(new_sleeve_delta_notional) / delta_cap,
        "daily_theta": abs(new_sleeve_theta) / theta_cap_abs,
        "vol_shock_10pt": abs(new_sleeve_vol_shock) / vol_cap_abs,
    }
    binding = max(utilizations, key=utilizations.get)
    binding_pct = utilizations[binding]

    # Max additional debit at the binding constraint — how much more $ can we add
    # before binding hits 100%?
    if binding == "position_heat":
        max_additional_debit = max(0, heat_cap * sleeve_value - debit)
    elif binding == "theme_concentration":
        max_additional_debit = max(0, theme_cap * sleeve_value - new_factor_heat)
    elif binding == "delta_notional":
        delta_room = delta_cap - abs(new_sleeve_delta_notional)
        # Convert delta-notional headroom back to debit using debit-per-delta ratio
        delta_per_debit = position_delta_notional / debit if debit > 0 else 1
        max_additional_debit = max(0, delta_room / delta_per_debit if delta_per_debit > 0 else 0)
    elif binding == "daily_theta":
        theta_room = theta_cap_abs - abs(new_sleeve_theta)
        theta_per_debit = position_theta / debit if debit > 0 else 1
        max_additional_debit = max(0, theta_room / theta_per_debit if theta_per_debit > 0 else 0)
    else:  # vol_shock
        vol_room = vol_cap_abs - abs(new_sleeve_vol_shock)
        vol_per_debit = position_vol_shock / debit if debit > 0 else 1
        max_additional_debit = max(0, vol_room / vol_per_debit if vol_per_debit > 0 else 0)

    debit_per_contract = debit / contracts if contracts > 0 else debit
    max_additional_contracts = int(max_additional_debit // debit_per_contract) if debit_per_contract > 0 else 0

    # ------------------------------------------------------------------
    # IV OVERLAY (v11.12 Patch 1) — apply IV-context sizing modifier
    # ------------------------------------------------------------------
    # When an IVContext is supplied, scale the caps-max additional debit by
    # the IV sizing modifier (cheap → upsize, expensive → downsize), then
    # CLAMP so total debit (debit + adjusted headroom) can never exceed the
    # Tier heat ceiling. The clamp only bites on upsize; a downsize never
    # needs it. When no iv_context is supplied, both fields stay None and
    # behavior is identical to the v11.10 baseline.
    iv_adjusted_max_debit: Optional[float] = None
    iv_adjusted_max_contracts: Optional[int] = None
    if iv_context is not None:
        iv_modifier = getattr(iv_context, "sizing_modifier", 1.0)
        iv_classification = getattr(iv_context, "classification", "unknown")
        raw_iv_debit = max_additional_debit * iv_modifier
        tier_ceiling_debit = heat_cap * sleeve_value
        iv_adjusted_max_debit = max(0.0, min(raw_iv_debit, tier_ceiling_debit - debit))
        iv_adjusted_max_contracts = (
            int(iv_adjusted_max_debit // debit_per_contract)
            if debit_per_contract > 0 else 0
        )
        notes.append(
            f"IV overlay [{iv_classification}]: caps-max additional debit "
            f"${max_additional_debit:,.0f} × {iv_modifier:.2f} → "
            f"${iv_adjusted_max_debit:,.0f} "
            f"(clamped to Tier {tier} ceiling ${tier_ceiling_debit:,.0f})"
        )

    return CapEvaluation(
        ticker=ticker,
        structure=structure,
        tier=tier,
        factor=factor,
        debit=debit,
        contracts=contracts,
        sleeve_value=sleeve_value,
        underlying_price=underlying_price,
        position_heat_pct=position_heat * 100,
        position_heat_cap_pct=heat_cap * 100,
        position_heat_gate=heat_gate,
        theme_concentration_pct=theme_concentration * 100,
        theme_concentration_cap_pct=theme_cap * 100,
        theme_concentration_gate=theme_gate,
        delta_notional=new_sleeve_delta_notional,
        delta_notional_cap=delta_cap,
        delta_notional_gate=delta_gate,
        daily_theta=new_sleeve_theta,
        daily_theta_cap=theta_cap_abs,
        daily_theta_gate=theta_gate,
        vol_shock_pl=new_sleeve_vol_shock,
        vol_shock_cap=vol_cap_abs,
        vol_shock_gate=vol_gate,
        n_in_factor=n_in_factor,
        rho_avg=rho_avg,
        n_eff=n_eff,
        n_eff_ratio=n_eff_ratio,
        overall_gate=overall_gate,
        binding_constraint=binding,
        max_additional_debit=max_additional_debit,
        max_additional_contracts=max_additional_contracts,
        notes=notes,
        iv_context=iv_context,
        iv_adjusted_max_debit=iv_adjusted_max_debit,
        iv_adjusted_max_contracts=iv_adjusted_max_contracts,
    )


# ============================================================================
# OUTPUT FORMATTING
# ============================================================================

def format_text_report(e: CapEvaluation) -> str:
    """Human-readable text report."""
    gate_color = {
        "GREEN": "🟢",
        "YELLOW": "🟡",
        "RED": "🔴",
    }
    g = gate_color

    lines = []
    lines.append("=" * 72)
    lines.append(f" POSITION SIZER (v11.10) — {e.ticker} {e.structure}")
    lines.append("=" * 72)
    lines.append(f"  Tier:        {e.tier}")
    lines.append(f"  Factor:      {e.factor}")
    lines.append(f"  Debit:       ${e.debit:,.0f}  ({e.contracts} contracts @ ${e.debit/e.contracts:,.0f} ea)")
    lines.append(f"  Sleeve:      ${e.sleeve_value:,.0f}")
    if e.underlying_price:
        lines.append(f"  Underlying:  ${e.underlying_price:.2f}")
    lines.append("")
    lines.append("  FOUR-CAP EVALUATION")
    lines.append("  " + "-" * 68)
    lines.append(f"  {g[e.position_heat_gate]} Position heat:      "
                 f"{e.position_heat_pct:5.1f}% / {e.position_heat_cap_pct:5.1f}% cap "
                 f"(Tier {e.tier})")
    lines.append(f"  {g[e.theme_concentration_gate]} Theme concentration: "
                 f"{e.theme_concentration_pct:5.1f}% / {e.theme_concentration_cap_pct:5.1f}% cap "
                 f"(factor: {e.factor})")
    lines.append(f"  {g[e.delta_notional_gate]} Delta-notional:     "
                 f"${e.delta_notional:>10,.0f} / ${e.delta_notional_cap:>10,.0f} cap "
                 f"({abs(e.delta_notional)/e.delta_notional_cap*100:.0f}%)")
    lines.append(f"  {g[e.daily_theta_gate]} Daily theta:        "
                 f"${e.daily_theta:>8.2f}/day / ${e.daily_theta_cap:>8.2f}/day cap "
                 f"({abs(e.daily_theta)/e.daily_theta_cap*100:.0f}%)")
    lines.append(f"  {g[e.vol_shock_gate]} 10-vol-pt shock:    "
                 f"${e.vol_shock_pl:>10,.0f} / ${e.vol_shock_cap:>10,.0f} cap "
                 f"({abs(e.vol_shock_pl)/e.vol_shock_cap*100:.0f}%)")
    lines.append("")
    lines.append("  CORRELATION DISCOUNT (N_eff)")
    lines.append("  " + "-" * 68)
    lines.append(f"  N in {e.factor} bucket (incl. this): {e.n_in_factor}")
    lines.append(f"  ρ_avg (default): {e.rho_avg:.2f}")
    lines.append(f"  N_eff: {e.n_eff:.2f}  →  Effective independent bets: {e.n_eff_ratio*100:.0f}% of nominal")
    if e.n_eff_ratio < 0.5:
        lines.append(f"  ⚠️  Scale factor-level heat by sqrt(N_eff/N) = {e.n_eff_ratio**0.5:.2f}")
    lines.append("")
    lines.append("  OVERALL GATE")
    lines.append("  " + "-" * 68)
    lines.append(f"  {g[e.overall_gate]} **{e.overall_gate}**")
    lines.append(f"  Binding constraint: {e.binding_constraint}")
    if e.overall_gate != "RED":
        lines.append(f"  Max additional debit at binding cap: ${e.max_additional_debit:,.0f}")
        lines.append(f"  Max additional contracts at binding cap: {e.max_additional_contracts}")
        if e.max_additional_contracts >= 1:
            lines.append(f"  → Sizing-to-caps suggests {e.contracts + e.max_additional_contracts} "
                         f"total contracts (vs. current {e.contracts}) for ${e.debit + e.max_additional_debit:,.0f}")
    if e.iv_context is not None:
        lines.append("")
        lines.append("  IV OVERLAY (v11.12)")
        lines.append("  " + "-" * 68)
        cls = getattr(e.iv_context, "classification", "unknown")
        mod = getattr(e.iv_context, "sizing_modifier", 1.0)
        lines.append(f"  Classification: {cls.upper()}  ·  sizing modifier ×{mod:.2f}")
        if e.iv_adjusted_max_debit is not None:
            lines.append(f"  IV-adjusted max additional debit: ${e.iv_adjusted_max_debit:,.0f} "
                         f"({e.iv_adjusted_max_contracts} contracts)")
    if e.notes:
        lines.append("")
        lines.append("  NOTES")
        lines.append("  " + "-" * 68)
        for n in e.notes:
            lines.append(f"  • {n}")
    lines.append("=" * 72)
    return "\n".join(lines)


def format_json_report(e: CapEvaluation) -> str:
    return json.dumps(asdict(e), indent=2)


# ============================================================================
# CLI
# ============================================================================

def cmd_help_factors():
    print("Factor buckets and default ρ values (v11.10):")
    print("=" * 60)
    for factor, rho in sorted(FACTOR_RHO_DEFAULTS.items(), key=lambda x: -x[1]):
        print(f"  {factor:25s} ρ_avg = {rho:.2f}")
    print()
    print("Tier-based position heat caps:")
    for tier, cap in TIER_HEAT_CAPS.items():
        print(f"  Tier {tier}: {cap*100:.0f}% of sleeve max")
    print()
    print("Greek stress caps (sleeve-aggregate):")
    print(f"  Delta-notional: {GREEK_CAPS['delta_notional_mult']}× sleeve value")
    print(f"  Daily theta:    {GREEK_CAPS['daily_theta_pct']*100:.2f}% of sleeve value")
    print(f"  10-vol shock:   {GREEK_CAPS['vol_shock_10pt_pct']*100:.0f}% of sleeve value")


def main():
    p = argparse.ArgumentParser(description="v11.10 Position Sizer — four-cap gate")
    p.add_argument("--ticker", required=False, help="Ticker symbol")
    p.add_argument("--structure", choices=list(STRUCTURE_GREEK_DEFAULTS.keys()),
                   default="leap_call")
    p.add_argument("--debit", type=float, help="Total debit cost ($)")
    p.add_argument("--tier", choices=["A", "B", "C"], default="A")
    p.add_argument("--factor", default="solo",
                   help="Factor bucket name (see --help-factors)")
    p.add_argument("--sleeve", type=float, default=SLEEVE_VALUE_DEFAULT,
                   help=f"Sleeve value (default ${SLEEVE_VALUE_DEFAULT:,})")
    p.add_argument("--contracts", type=int, default=1)
    p.add_argument("--underlying", type=float, default=None,
                   help="Underlying price (for delta-notional)")
    p.add_argument("--existing-factor-heat", type=float, default=0.0,
                   help="$ already at risk in this factor bucket")
    p.add_argument("--existing-delta-notional", type=float, default=0.0)
    p.add_argument("--existing-theta", type=float, default=0.0,
                   help="$/day theta of existing positions")
    p.add_argument("--existing-vol-shock", type=float, default=0.0)
    p.add_argument("--n-in-factor", type=int, default=1,
                   help="Number of positions in this factor (incl. new) for N_eff")
    p.add_argument("--rho", type=float, default=None,
                   help="Override default ρ_avg for factor bucket")
    p.add_argument("--ivr", type=float, default=None,
                   help="IV Rank 0-100 — enables the v11.12 IV overlay")
    p.add_argument("--atm-iv", type=float, default=None,
                   help="Current ATM IV at target DTE (decimal)")
    p.add_argument("--atm-iv-30d-mean", type=float, default=None,
                   help="30-day mean ATM IV (decimal)")
    p.add_argument("--atm-iv-back", type=float, default=None,
                   help="ATM IV at longer-dated expiry (term structure)")
    p.add_argument("--catalyst-within-dte", action="store_true",
                   help="Binary catalyst sits inside the DTE window")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--help-factors", action="store_true",
                   help="List factor buckets and defaults")
    args = p.parse_args()

    if args.help_factors:
        cmd_help_factors()
        return 0

    if not args.ticker or args.debit is None:
        p.print_help()
        print("\nERROR: --ticker and --debit required (or use --help-factors)",
              file=sys.stderr)
        return 1

    # v11.12 IV overlay — build IVContext when --ivr supplied (lazy import so
    # position_sizer stays standalone-importable without uw_iv_context).
    iv_context = None
    if args.ivr is not None:
        try:
            from uw_iv_context import classify_iv
            iv_context = classify_iv(
                ticker=args.ticker,
                iv_rank=args.ivr,
                atm_iv_current=args.atm_iv,
                atm_iv_30d_mean=args.atm_iv_30d_mean,
                atm_iv_back=args.atm_iv_back,
                tier=args.tier,
                catalyst_within_dte=args.catalyst_within_dte,
            )
        except Exception as exc:  # pragma: no cover — defensive
            print(f"WARN: IV overlay skipped — {exc}", file=sys.stderr)

    result = evaluate_position(
        ticker=args.ticker,
        structure=args.structure,
        debit=args.debit,
        tier=args.tier,
        factor=args.factor,
        sleeve_value=args.sleeve,
        contracts=args.contracts,
        underlying_price=args.underlying,
        existing_factor_heat=args.existing_factor_heat,
        existing_sleeve_delta_notional=args.existing_delta_notional,
        existing_sleeve_daily_theta=args.existing_theta,
        existing_sleeve_vol_shock_pl=args.existing_vol_shock,
        n_in_factor=args.n_in_factor,
        rho_avg=args.rho,
        iv_context=iv_context,
    )

    if args.json:
        print(format_json_report(result))
    else:
        print(format_text_report(result))

    return 0 if result.overall_gate != "RED" else 2


if __name__ == "__main__":
    sys.exit(main())
