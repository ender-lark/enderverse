#!/usr/bin/env python3
"""
test_position_sizer.py — unit tests for v11.10 sizing-to-caps math.

Run: python3 test_position_sizer.py
"""

import unittest
from position_sizer import (
    evaluate_position,
    TIER_HEAT_CAPS,
    THEME_CONCENTRATION_CAP,
    GREEK_CAPS,
    FACTOR_RHO_DEFAULTS,
)


class TestPositionHeatCap(unittest.TestCase):
    """Cap 1: position heat by tier."""

    def test_tier_a_green_at_low_heat(self):
        r = evaluate_position("LEU", "leap_call", debit=2000, tier="A",
                              factor="nuclear", sleeve_value=30000, contracts=1)
        # 2000/30000 = 6.7% — well under 15% × 80% = 12% GREEN threshold
        self.assertEqual(r.position_heat_gate, "GREEN")

    def test_tier_a_yellow_at_ceiling(self):
        r = evaluate_position("LEU", "leap_call", debit=4000, tier="A",
                              factor="nuclear", sleeve_value=30000, contracts=1)
        # 4000/30000 = 13.3% — over 12% GREEN, under 15% RED
        self.assertEqual(r.position_heat_gate, "YELLOW")

    def test_tier_a_red_above_cap(self):
        r = evaluate_position("LEU", "leap_call", debit=5000, tier="A",
                              factor="nuclear", sleeve_value=30000, contracts=1)
        # 5000/30000 = 16.7% — over 15% cap
        self.assertEqual(r.position_heat_gate, "RED")

    def test_tier_b_tighter_cap_than_a(self):
        r = evaluate_position("IONQ", "vert_spread", debit=3500, tier="B",
                              factor="quantum", sleeve_value=30000, contracts=5)
        # 3500/30000 = 11.7% — RED for Tier B (10% cap), but would be GREEN for Tier A
        self.assertEqual(r.position_heat_gate, "RED")

    def test_tier_c_tightest_cap(self):
        r = evaluate_position("XYZ", "leap_call", debit=2500, tier="C",
                              factor="solo", sleeve_value=30000, contracts=1)
        # 2500/30000 = 8.3% — RED for Tier C (7% cap)
        self.assertEqual(r.position_heat_gate, "RED")


class TestThemeConcentrationCap(unittest.TestCase):
    """Cap 2: theme concentration at 35% per factor bucket."""

    def test_factor_concentration_green(self):
        r = evaluate_position("NVDA", "leap_call", debit=2000, tier="A",
                              factor="ai_complex", sleeve_value=30000, contracts=1,
                              existing_factor_heat=5000)
        # (5000+2000)/30000 = 23.3% — under 35% × 80% = 28% GREEN
        self.assertEqual(r.theme_concentration_gate, "GREEN")

    def test_factor_concentration_yellow_at_ceiling(self):
        r = evaluate_position("NVDA", "leap_call", debit=2000, tier="A",
                              factor="ai_complex", sleeve_value=30000, contracts=1,
                              existing_factor_heat=8000)
        # (8000+2000)/30000 = 33.3% — between 28% and 35%
        self.assertEqual(r.theme_concentration_gate, "YELLOW")

    def test_factor_concentration_red(self):
        r = evaluate_position("NVDA", "leap_call", debit=2000, tier="A",
                              factor="ai_complex", sleeve_value=30000, contracts=1,
                              existing_factor_heat=9000)
        # (9000+2000)/30000 = 36.7% — over 35%
        self.assertEqual(r.theme_concentration_gate, "RED")


class TestGreekStressCaps(unittest.TestCase):
    """Cap 3: Greek stress — delta-notional, theta, vol-shock."""

    def test_delta_notional_under_cap(self):
        r = evaluate_position("LEU", "leap_call", debit=3600, tier="A",
                              factor="nuclear", sleeve_value=30000, contracts=1,
                              underlying_price=162.0)
        # delta-notional = 0.45 × 1 × 100 × 162 = $7290; cap = 1.5 × 30000 = $45000
        self.assertLess(r.delta_notional, r.delta_notional_cap)
        self.assertEqual(r.delta_notional_gate, "GREEN")

    def test_theta_under_cap(self):
        r = evaluate_position("LEU", "leap_call", debit=3600, tier="A",
                              factor="nuclear", sleeve_value=30000, contracts=1)
        # theta = $13/day × 1; cap = 0.0025 × 30000 = $75/day
        self.assertLess(abs(r.daily_theta), r.daily_theta_cap)
        self.assertEqual(r.daily_theta_gate, "GREEN")

    def test_vol_shock_red_when_many_contracts(self):
        # Force a vol-shock cap violation with high contract count
        r = evaluate_position("LEU", "leap_call", debit=180000, tier="A",
                              factor="nuclear", sleeve_value=30000, contracts=50,
                              underlying_price=162.0)
        # vol_shock = 0.50 × 50 × 100 × 10 = $25000; cap = 0.12 × 30000 = $3600
        self.assertGreater(abs(r.vol_shock_pl), r.vol_shock_cap)
        self.assertEqual(r.vol_shock_gate, "RED")


class TestNEffCorrelationDiscount(unittest.TestCase):
    """Cap 4: N_eff = N / (1 + (N-1) × ρ)."""

    def test_n_eff_solo_position(self):
        r = evaluate_position("LEU", "leap_call", debit=3600, tier="A",
                              factor="nuclear", sleeve_value=30000, contracts=1,
                              n_in_factor=1)
        self.assertEqual(r.n_eff, 1.0)
        self.assertEqual(r.n_eff_ratio, 1.0)

    def test_n_eff_ai_complex_5_positions(self):
        r = evaluate_position("NVDA", "leap_call", debit=3000, tier="A",
                              factor="ai_complex", sleeve_value=30000, contracts=1,
                              n_in_factor=5)
        # AI complex ρ=0.70; N_eff = 5/(1 + 4×0.7) = 5/3.8 = 1.32
        self.assertAlmostEqual(r.n_eff, 1.316, places=2)
        # N_eff/N = 1.316/5 = 0.263
        self.assertAlmostEqual(r.n_eff_ratio, 0.263, places=2)

    def test_n_eff_uncorrelated(self):
        # Override ρ to 0 (perfectly uncorrelated)
        r = evaluate_position("XYZ", "leap_call", debit=2000, tier="A",
                              factor="ai_complex", sleeve_value=30000, contracts=1,
                              n_in_factor=3, rho_avg=0.0)
        # ρ=0 → N_eff = N = 3
        self.assertEqual(r.n_eff, 3.0)
        self.assertEqual(r.n_eff_ratio, 1.0)

    def test_n_eff_perfectly_correlated(self):
        r = evaluate_position("XYZ", "leap_call", debit=2000, tier="A",
                              factor="ai_complex", sleeve_value=30000, contracts=1,
                              n_in_factor=5, rho_avg=1.0)
        # ρ=1 → N_eff = 1 regardless of N
        self.assertEqual(r.n_eff, 1.0)


class TestBindingConstraint(unittest.TestCase):
    """Verify binding constraint correctly identifies the tightest cap."""

    def test_position_heat_binding(self):
        r = evaluate_position("LEU", "leap_call", debit=4000, tier="A",
                              factor="nuclear", sleeve_value=30000, contracts=1,
                              underlying_price=162.0)
        # Position heat 13.3%/15% = 89% utilization — highest
        self.assertEqual(r.binding_constraint, "position_heat")

    def test_theme_concentration_binding(self):
        r = evaluate_position("NVDA", "leap_call", debit=1500, tier="A",
                              factor="ai_complex", sleeve_value=30000, contracts=1,
                              existing_factor_heat=8500, underlying_price=160.0)
        # Position heat 5%/15% = 33%; Theme 33.3%/35% = 95% — theme binds
        self.assertEqual(r.binding_constraint, "theme_concentration")


class TestMaxAdditionalDebit(unittest.TestCase):
    """Verify max-additional-debit calc at binding constraint."""

    def test_max_additional_at_position_heat_cap(self):
        r = evaluate_position("IONQ", "vert_spread", debit=560, tier="B",
                              factor="quantum", sleeve_value=30000, contracts=1,
                              underlying_price=56.0)
        # Tier B 10% × 30000 = 3000 max debit; current 560 → 2440 headroom
        self.assertAlmostEqual(r.max_additional_debit, 2440, delta=1)
        # At $560/contract, max additional = 2440/560 = 4 contracts
        self.assertEqual(r.max_additional_contracts, 4)


class TestOverallGate(unittest.TestCase):
    """Overall gate = worst of all cap gates."""

    def test_all_green_gives_green(self):
        r = evaluate_position("LEU", "leap_call", debit=2000, tier="A",
                              factor="nuclear", sleeve_value=30000, contracts=1,
                              underlying_price=162.0)
        self.assertEqual(r.overall_gate, "GREEN")

    def test_one_red_gives_red(self):
        r = evaluate_position("LEU", "leap_call", debit=5000, tier="A",
                              factor="nuclear", sleeve_value=30000, contracts=1,
                              underlying_price=162.0)
        # Position heat 16.7% > 15% cap = RED
        self.assertEqual(r.overall_gate, "RED")

    def test_one_yellow_no_red_gives_yellow(self):
        r = evaluate_position("LEU", "leap_call", debit=4000, tier="A",
                              factor="nuclear", sleeve_value=30000, contracts=1,
                              underlying_price=162.0)
        # Position heat 13.3% YELLOW; everything else GREEN
        self.assertEqual(r.overall_gate, "YELLOW")


class TestCalibratedScenarios(unittest.TestCase):
    """v11.10 CI calibration scenarios — verify changelog claims are accurate."""

    def test_leu_jan_2027_300_call_at_30k_sleeve(self):
        """CI claim: 1 contract at 12% heat, GREEN, $900 headroom, 0 additional contracts."""
        r = evaluate_position("LEU", "leap_call", debit=3600, tier="A",
                              factor="nuclear", sleeve_value=30000, contracts=1,
                              underlying_price=162.0)
        self.assertAlmostEqual(r.position_heat_pct, 12.0, places=1)
        self.assertEqual(r.overall_gate, "GREEN")
        self.assertAlmostEqual(r.max_additional_debit, 900, delta=1)
        self.assertEqual(r.max_additional_contracts, 0)

    def test_ionq_5_contracts_at_30k_sleeve(self):
        """CI claim: 5 contracts × $560 = $2,800 at 9.3% heat, YELLOW."""
        r = evaluate_position("IONQ", "vert_spread", debit=2800, tier="B",
                              factor="quantum", sleeve_value=30000, contracts=5,
                              underlying_price=56.0)
        self.assertAlmostEqual(r.position_heat_pct, 9.33, places=1)
        self.assertEqual(r.position_heat_gate, "YELLOW")
        self.assertEqual(r.overall_gate, "YELLOW")

    def test_ionq_7_contracts_red_at_30k_sleeve(self):
        """CI claim: 7 contracts × $560 = $3,920 RED at $30K Tier B."""
        r = evaluate_position("IONQ", "vert_spread", debit=3920, tier="B",
                              factor="quantum", sleeve_value=30000, contracts=7,
                              underlying_price=56.0)
        self.assertAlmostEqual(r.position_heat_pct, 13.07, places=1)
        self.assertEqual(r.position_heat_gate, "RED")
        self.assertEqual(r.overall_gate, "RED")


if __name__ == "__main__":
    unittest.main()
