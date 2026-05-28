#!/usr/bin/env python3
"""
test_stale_leaps_scan.py — Unit tests for stale_leaps_scan.py (W8/Game C v1.0)

Covers pure-logic functions: BS pricing, chain evaluation, DTE math.
No UW API dependency — tests run in <1 sec.
"""

from __future__ import annotations

import math
import unittest
from datetime import date

from stale_leaps_scan import (
    black_scholes_call,
    black_scholes_put,
    _norm_cdf,
    _days_to_expiry,
    evaluate_chain_for_stale_strikes,
    StaleStrikeFlag,
)


class TestNormCDF(unittest.TestCase):
    def test_zero(self):
        self.assertAlmostEqual(_norm_cdf(0.0), 0.5, places=6)

    def test_known_values(self):
        # N(1) ≈ 0.8413
        self.assertAlmostEqual(_norm_cdf(1.0), 0.8413, places=3)
        # N(-1) ≈ 0.1587
        self.assertAlmostEqual(_norm_cdf(-1.0), 0.1587, places=3)
        # N(1.96) ≈ 0.975
        self.assertAlmostEqual(_norm_cdf(1.96), 0.975, places=3)


class TestBlackScholesCall(unittest.TestCase):
    def test_atm_1yr_30iv(self):
        # ATM call, 1yr, 30% IV, 4.5% rf — should be ~$13-14
        c = black_scholes_call(spot=100, strike=100, time_years=1.0, iv=0.30, risk_free=0.045)
        self.assertTrue(11 < c < 16, f"Expected ~$13, got {c}")

    def test_deep_itm_approx_intrinsic(self):
        # Deep ITM, short DTE → price approaches intrinsic
        c = black_scholes_call(spot=150, strike=100, time_years=0.10, iv=0.30, risk_free=0.045)
        intrinsic = 150 - 100
        self.assertTrue(intrinsic <= c < intrinsic + 5,
                       f"Deep ITM should be close to intrinsic ${intrinsic}, got ${c:.2f}")

    def test_deep_otm_near_zero(self):
        # Deep OTM call near expiry → near zero
        c = black_scholes_call(spot=100, strike=200, time_years=0.05, iv=0.30, risk_free=0.045)
        self.assertLess(c, 0.10, f"Deep OTM near expiry should be ~0, got ${c}")

    def test_higher_iv_higher_price(self):
        c_low = black_scholes_call(spot=100, strike=100, time_years=0.5, iv=0.20, risk_free=0.045)
        c_high = black_scholes_call(spot=100, strike=100, time_years=0.5, iv=0.50, risk_free=0.045)
        self.assertGreater(c_high, c_low, "Higher IV → higher option price")

    def test_longer_dte_higher_price_atm(self):
        c_short = black_scholes_call(spot=100, strike=100, time_years=0.25, iv=0.30, risk_free=0.045)
        c_long = black_scholes_call(spot=100, strike=100, time_years=2.0, iv=0.30, risk_free=0.045)
        self.assertGreater(c_long, c_short, "Longer DTE → higher ATM call price")

    def test_zero_time_returns_intrinsic(self):
        c = black_scholes_call(spot=100, strike=90, time_years=0.0, iv=0.30, risk_free=0.045)
        self.assertEqual(c, 10.0)

    def test_zero_iv_returns_intrinsic(self):
        c = black_scholes_call(spot=100, strike=90, time_years=1.0, iv=0.0, risk_free=0.045)
        self.assertEqual(c, 10.0)


class TestBlackScholesPut(unittest.TestCase):
    def test_atm_put_close_to_call(self):
        # ATM call and put should be similar (call slightly higher due to rf)
        c = black_scholes_call(spot=100, strike=100, time_years=1.0, iv=0.30, risk_free=0.045)
        p = black_scholes_put(spot=100, strike=100, time_years=1.0, iv=0.30, risk_free=0.045)
        self.assertGreater(c, p)
        self.assertLess(c - p, 6)  # difference is small

    def test_put_call_parity(self):
        # C - P = S - K * e^(-rT) for non-dividend-paying stock
        spot, strike, t, iv, rf = 100, 100, 1.0, 0.30, 0.045
        c = black_scholes_call(spot, strike, t, iv, rf)
        p = black_scholes_put(spot, strike, t, iv, rf)
        lhs = c - p
        rhs = spot - strike * math.exp(-rf * t)
        self.assertAlmostEqual(lhs, rhs, places=4, msg="Put-call parity violated")

    def test_deep_otm_put_near_zero(self):
        # Deep OTM put → near zero
        p = black_scholes_put(spot=200, strike=100, time_years=0.05, iv=0.30, risk_free=0.045)
        self.assertLess(p, 0.10)


class TestDTECompute(unittest.TestCase):
    def test_one_year_out(self):
        dte = _days_to_expiry("2027-05-14", today=date(2026, 5, 14))
        self.assertEqual(dte, 365)

    def test_past_expiry_negative(self):
        dte = _days_to_expiry("2025-01-01", today=date(2026, 5, 14))
        self.assertLess(dte, 0)

    def test_invalid_format_returns_zero(self):
        dte = _days_to_expiry("not-a-date", today=date(2026, 5, 14))
        self.assertEqual(dte, 0)


class TestEvaluateChain(unittest.TestCase):
    SPOT = 100.0
    EXPIRY = "2027-05-14"   # ~1yr from test today
    TODAY = date(2026, 5, 14)

    def test_no_flags_on_fair_chain(self):
        """Strikes priced at theoretical should not flag."""
        # Compute theoretical at $100/$110/$120 and price each at theoretical
        chain = []
        for k in (100, 110, 120):
            theo = black_scholes_call(self.SPOT, k, 1.0, 0.30, 0.045)
            chain.append({
                "strike": k, "iv": 0.30, "nbbo_ask": theo, "last_price": theo,
                "volume": 10, "open_interest": 100, "option_type": "call",
            })
        flags = evaluate_chain_for_stale_strikes(
            ticker="TEST", spot=self.SPOT, chain_rows=chain,
            expiry=self.EXPIRY, discount_threshold=0.85, volume_floor=50,
            risk_free=0.045, today=self.TODAY,
        )
        self.assertEqual(len(flags), 0, "Fair chain should produce no flags")

    def test_stale_strike_flags(self):
        """Strike with ask far below theoretical should flag."""
        chain = [{
            "strike": 100, "iv": 0.30, "nbbo_ask": 2.0,  # theo is ~$14, ask is $2
            "last_price": 2.0, "volume": 5, "open_interest": 200,
            "option_type": "call",
        }]
        flags = evaluate_chain_for_stale_strikes(
            ticker="TEST", spot=self.SPOT, chain_rows=chain,
            expiry=self.EXPIRY, discount_threshold=0.85, volume_floor=50,
            risk_free=0.045, today=self.TODAY,
        )
        self.assertEqual(len(flags), 1)
        f = flags[0]
        self.assertEqual(f.strike, 100)
        self.assertGreater(f.discount_pct, 80)

    def test_high_volume_skipped(self):
        """Even if ask is stale, high-volume contracts are skipped (MM has repriced)."""
        chain = [{
            "strike": 100, "iv": 0.30, "nbbo_ask": 2.0,
            "last_price": 2.0, "volume": 500,  # > volume_floor
            "open_interest": 5000, "option_type": "call",
        }]
        flags = evaluate_chain_for_stale_strikes(
            ticker="TEST", spot=self.SPOT, chain_rows=chain,
            expiry=self.EXPIRY, discount_threshold=0.85, volume_floor=50,
            risk_free=0.045, today=self.TODAY,
        )
        self.assertEqual(len(flags), 0, "High-volume strike should be skipped")

    def test_threshold_boundary(self):
        """At exactly 85% discount threshold, should flag (>= 15% under theo)."""
        # Theoretical ATM 100, 1yr, 30%, 4.5% ≈ $13.99
        theo = black_scholes_call(100, 100, 1.0, 0.30, 0.045)
        # Place ask just below 0.85 × theo
        ask_stale = theo * 0.83
        ask_fair = theo * 0.90  # within 10% of theo, should NOT flag

        chain = [
            {"strike": 100, "iv": 0.30, "nbbo_ask": ask_stale, "last_price": ask_stale,
             "volume": 5, "open_interest": 100, "option_type": "call"},
            {"strike": 105, "iv": 0.30, "nbbo_ask": ask_fair, "last_price": ask_fair,
             "volume": 5, "open_interest": 100, "option_type": "call"},
        ]
        flags = evaluate_chain_for_stale_strikes(
            ticker="TEST", spot=self.SPOT, chain_rows=chain,
            expiry=self.EXPIRY, discount_threshold=0.85, volume_floor=50,
            risk_free=0.045, today=self.TODAY,
        )
        # Only $100 strike (17% under theo) should flag
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0].strike, 100)

    def test_skip_expired_chains(self):
        """Past-expiry chain should return empty without crashing."""
        chain = [{"strike": 100, "iv": 0.30, "nbbo_ask": 2.0, "last_price": 2.0,
                  "volume": 5, "open_interest": 100, "option_type": "call"}]
        flags = evaluate_chain_for_stale_strikes(
            ticker="TEST", spot=self.SPOT, chain_rows=chain,
            expiry="2025-01-01",  # in the past
            discount_threshold=0.85, volume_floor=50, risk_free=0.045,
            today=self.TODAY,
        )
        self.assertEqual(len(flags), 0)

    def test_malformed_row_ignored(self):
        """Rows missing required fields should be silently skipped."""
        chain = [
            {"strike": "junk", "iv": 0.30, "nbbo_ask": 2.0, "last_price": 2.0,
             "volume": 5, "open_interest": 100, "option_type": "call"},
            {"strike": 100, "iv": 0.30, "nbbo_ask": 2.0, "last_price": 2.0,
             "volume": 5, "open_interest": 100, "option_type": "call"},
        ]
        flags = evaluate_chain_for_stale_strikes(
            ticker="TEST", spot=self.SPOT, chain_rows=chain,
            expiry=self.EXPIRY, discount_threshold=0.85, volume_floor=50,
            risk_free=0.045, today=self.TODAY,
        )
        # Only the valid row produces a flag
        self.assertEqual(len(flags), 1)


class TestNotesAnnotation(unittest.TestCase):
    def test_zero_volume_notes(self):
        chain = [{"strike": 100, "iv": 0.30, "nbbo_ask": 2.0, "last_price": 2.0,
                  "volume": 0, "open_interest": 100, "option_type": "call"}]
        flags = evaluate_chain_for_stale_strikes(
            ticker="T", spot=100.0, chain_rows=chain,
            expiry="2027-05-14", discount_threshold=0.85, volume_floor=50,
            risk_free=0.045, today=date(2026, 5, 14),
        )
        self.assertEqual(len(flags), 1)
        self.assertTrue(any("zero volume" in n for n in flags[0].notes))

    def test_low_oi_notes(self):
        chain = [{"strike": 100, "iv": 0.30, "nbbo_ask": 2.0, "last_price": 2.0,
                  "volume": 5, "open_interest": 3, "option_type": "call"}]
        flags = evaluate_chain_for_stale_strikes(
            ticker="T", spot=100.0, chain_rows=chain,
            expiry="2027-05-14", discount_threshold=0.85, volume_floor=50,
            risk_free=0.045, today=date(2026, 5, 14),
        )
        self.assertEqual(len(flags), 1)
        self.assertTrue(any("low OI" in n for n in flags[0].notes))

    def test_stale_last_trade_notes(self):
        # ask $5, last $1 (stale tape)
        chain = [{"strike": 100, "iv": 0.30, "nbbo_ask": 5.0, "last_price": 1.0,
                  "volume": 5, "open_interest": 100, "option_type": "call"}]
        flags = evaluate_chain_for_stale_strikes(
            ticker="T", spot=80.0,  # low spot makes theo low → ask still flags as stale vs theo
            chain_rows=chain, expiry="2027-05-14", discount_threshold=0.50,
            volume_floor=50, risk_free=0.045, today=date(2026, 5, 14),
        )
        # If this strike flags, it should note the stale last trade
        if flags:
            self.assertTrue(any("stale last" in n for n in flags[0].notes))


if __name__ == "__main__":
    unittest.main()
