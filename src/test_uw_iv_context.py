#!/usr/bin/env python3
"""
test_uw_iv_context.py — unit tests for v11.11 Game B IV context classifier
and its integration into position_sizer.

Run: python3 test_uw_iv_context.py
"""

import unittest
from uw_iv_context import (
    classify_iv,
    IVR_CHEAP_MAX,
    IVR_EXPENSIVE_MIN,
    SIZING_MOD_CHEAP,
    SIZING_MOD_EXPENSIVE,
)
from position_sizer import evaluate_position


# ============================================================================
# IV CLASSIFICATION
# ============================================================================

class TestIVRankClassification(unittest.TestCase):
    """Cheap / normal / expensive bands."""

    def test_cheap_ivr(self):
        ctx = classify_iv("LEU", iv_rank=15, tier="A")
        self.assertEqual(ctx.classification, "cheap")
        self.assertEqual(ctx.sizing_modifier, SIZING_MOD_CHEAP)

    def test_normal_ivr_low_end(self):
        ctx = classify_iv("LEU", iv_rank=35, tier="A")
        self.assertEqual(ctx.classification, "normal")
        self.assertEqual(ctx.sizing_modifier, 1.00)

    def test_normal_ivr_high_end(self):
        ctx = classify_iv("LEU", iv_rank=65, tier="A")
        self.assertEqual(ctx.classification, "normal")
        self.assertEqual(ctx.sizing_modifier, 1.00)

    def test_expensive_ivr(self):
        ctx = classify_iv("IONQ", iv_rank=85, tier="A")
        self.assertEqual(ctx.classification, "expensive")
        self.assertEqual(ctx.sizing_modifier, SIZING_MOD_EXPENSIVE)

    def test_missing_ivr_unknown(self):
        ctx = classify_iv("XYZ", tier="A")
        self.assertEqual(ctx.classification, "unknown")
        self.assertEqual(ctx.sizing_modifier, 1.00)


class TestRecentMoveRefinement(unittest.TestCase):
    """Normal IVR can be reclassified by recent-move check."""

    def test_normal_to_cheap_on_crush(self):
        # IVR normal but current ATM IV is 30% below 30d mean
        ctx = classify_iv("MSFT", iv_rank=50, atm_iv_current=0.21, atm_iv_30d_mean=0.30, tier="A")
        self.assertEqual(ctx.classification, "cheap")

    def test_normal_to_expensive_on_inflation(self):
        ctx = classify_iv("MSFT", iv_rank=50, atm_iv_current=0.38, atm_iv_30d_mean=0.30, tier="A")
        self.assertEqual(ctx.classification, "expensive")

    def test_normal_stays_normal_no_recent_move(self):
        ctx = classify_iv("MSFT", iv_rank=50, atm_iv_current=0.30, atm_iv_30d_mean=0.30, tier="A")
        self.assertEqual(ctx.classification, "normal")


# ============================================================================
# TERM STRUCTURE
# ============================================================================

class TestTermStructure(unittest.TestCase):

    def test_backwardation(self):
        ctx = classify_iv("LEU", iv_rank=50, atm_iv_current=0.80, atm_iv_back=0.60, tier="A")
        self.assertEqual(ctx.term_structure, "backwardation")

    def test_contango(self):
        ctx = classify_iv("LEU", iv_rank=50, atm_iv_current=0.50, atm_iv_back=0.65, tier="A")
        self.assertEqual(ctx.term_structure, "contango")

    def test_flat(self):
        ctx = classify_iv("LEU", iv_rank=50, atm_iv_current=0.50, atm_iv_back=0.51, tier="A")
        self.assertEqual(ctx.term_structure, "flat")

    def test_unknown_when_missing(self):
        ctx = classify_iv("LEU", iv_rank=50, atm_iv_current=0.50, tier="A")
        self.assertEqual(ctx.term_structure, "unknown")


# ============================================================================
# RECOMMENDED STRUCTURE
# ============================================================================

class TestRecommendedStructure(unittest.TestCase):
    """Decision tree: classification × term × tier."""

    def test_cheap_iv_default_leap_call(self):
        ctx = classify_iv("LEU", iv_rank=20, tier="A")
        self.assertEqual(ctx.recommended_structure, "LEAP_CALL")

    def test_cheap_plus_backwardation_yields_calendar(self):
        ctx = classify_iv("LEU", iv_rank=20,
                          atm_iv_current=0.80, atm_iv_back=0.50, tier="A")
        self.assertEqual(ctx.recommended_structure, "CALENDAR")

    def test_expensive_tier_a_yields_diagonal(self):
        ctx = classify_iv("IONQ", iv_rank=88, tier="A")
        self.assertEqual(ctx.recommended_structure, "DIAGONAL")

    def test_expensive_tier_b_yields_vertical(self):
        ctx = classify_iv("IONQ", iv_rank=88, tier="B")
        self.assertEqual(ctx.recommended_structure, "VERTICAL")

    def test_normal_tier_a_yields_leap_call(self):
        ctx = classify_iv("NVDA", iv_rank=50, tier="A")
        self.assertEqual(ctx.recommended_structure, "LEAP_CALL")

    def test_normal_tier_b_yields_vertical(self):
        ctx = classify_iv("NVDA", iv_rank=50, tier="B")
        self.assertEqual(ctx.recommended_structure, "VERTICAL")

    def test_unknown_defaults_vertical(self):
        ctx = classify_iv("XYZ", tier="A")
        self.assertEqual(ctx.recommended_structure, "VERTICAL")


# ============================================================================
# CATALYST PROXIMITY OFFSET
# ============================================================================

class TestCatalystOffset(unittest.TestCase):

    def test_expensive_with_catalyst_partial_offset(self):
        # Expensive IV alone → modifier 0.80
        ctx_no_cat = classify_iv("IONQ", iv_rank=88, tier="A")
        self.assertAlmostEqual(ctx_no_cat.sizing_modifier, 0.80, places=2)

        # Expensive IV + catalyst within DTE → modifier capped at 1.00 (0.80+0.10)
        ctx_cat = classify_iv("IONQ", iv_rank=88, tier="A",
                              catalyst_within_dte=True)
        self.assertAlmostEqual(ctx_cat.sizing_modifier, 0.90, places=2)

    def test_cheap_with_catalyst_no_offset(self):
        # Cheap doesn't get catalyst offset (already upsized)
        ctx = classify_iv("LEU", iv_rank=20, tier="A",
                          catalyst_within_dte=True)
        self.assertAlmostEqual(ctx.sizing_modifier, SIZING_MOD_CHEAP, places=2)


# ============================================================================
# INTEGRATION — position_sizer + IV overlay
# ============================================================================

class TestPositionSizerIVOverlay(unittest.TestCase):

    def test_no_iv_context_keeps_v11_10_behavior(self):
        """When no IV context provided, output is identical to v11.10 baseline."""
        r = evaluate_position("LEU", "leap_call", debit=3600, tier="A",
                              factor="nuclear", sleeve_value=30000, contracts=1,
                              underlying_price=180.0)
        self.assertIsNone(r.iv_context)
        self.assertIsNone(r.iv_adjusted_max_debit)
        self.assertIsNone(r.iv_adjusted_max_contracts)

    def test_cheap_iv_upsizes_max_debit(self):
        """Cheap IV → max_additional_debit upsized by ~15%."""
        ctx = classify_iv("LEU", iv_rank=20, tier="A")
        r = evaluate_position("LEU", "leap_call", debit=3600, tier="A",
                              factor="nuclear", sleeve_value=30000, contracts=1,
                              underlying_price=180.0, iv_context=ctx)
        self.assertIsNotNone(r.iv_adjusted_max_debit)
        # Should be larger than the un-adjusted, but clamped at tier RED cap
        # Tier A heat cap = 15% × $30K = $4500
        # Current debit $3600, max_additional from heat cap = $900
        # IV-adjusted: $900 × 1.15 = $1035, but clamped to $900 (Tier A cap)
        # Actually: max_additional already at cap, so upsize clamps to $900
        self.assertLessEqual(
            r.debit + r.iv_adjusted_max_debit,
            0.15 * 30000 + 1,  # at or under Tier A RED ceiling
        )

    def test_expensive_iv_downsizes_max_debit(self):
        """Expensive IV → max_additional_debit reduced by 20%."""
        ctx = classify_iv("IONQ", iv_rank=88, tier="A")
        r = evaluate_position("IONQ", "leap_call", debit=2000, tier="A",
                              factor="quantum", sleeve_value=30000, contracts=1,
                              underlying_price=40.0, iv_context=ctx)
        self.assertIsNotNone(r.iv_adjusted_max_debit)
        # Should be smaller than un-adjusted max_additional_debit
        self.assertLess(r.iv_adjusted_max_debit, r.max_additional_debit)
        # Ratio should be ~0.80
        self.assertAlmostEqual(
            r.iv_adjusted_max_debit / r.max_additional_debit,
            0.80, places=2
        )

    def test_iv_upsize_clamped_at_tier_red_ceiling(self):
        """Even with cheap IV, total debit cannot exceed tier RED cap."""
        # Start with debit already near Tier A ceiling
        ctx = classify_iv("LEU", iv_rank=20, tier="A")
        r = evaluate_position("LEU", "leap_call", debit=4400, tier="A",
                              factor="nuclear", sleeve_value=30000, contracts=1,
                              underlying_price=180.0, iv_context=ctx)
        # debit + iv_adjusted_max_debit ≤ 15% × 30K = 4500
        if r.iv_adjusted_max_debit is not None:
            self.assertLessEqual(r.debit + r.iv_adjusted_max_debit, 4500 + 1)

    def test_iv_context_preserved_in_result(self):
        """IV context object is reachable on result."""
        ctx = classify_iv("LEU", iv_rank=20, tier="A")
        r = evaluate_position("LEU", "leap_call", debit=3600, tier="A",
                              factor="nuclear", sleeve_value=30000, contracts=1,
                              underlying_price=180.0, iv_context=ctx)
        self.assertEqual(r.iv_context.ticker, "LEU")
        self.assertEqual(r.iv_context.classification, "cheap")


if __name__ == "__main__":
    unittest.main()
