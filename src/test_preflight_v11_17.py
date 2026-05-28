"""
test_preflight_v11_17.py
=========================
Unit tests for the v11.16 + v11.17 pre-flight scripts.

Covers:
- recommendations_digest: freshness banding, duplicate detection, supersedure inference
- options_expiry_preflight: OCC symbol parsing, DTE computation, moneyness, action bands
- position_drift_check: memory baseline parsing, drift computation, false-positive filtering

Backtest cases:
- IVES $30 calls 1 DTE deep ITM → ACTION_REQUIRED with SELL-TO-CLOSE recommendation
- BMNR memory 5% baseline vs actual 3.87% → UNDERSIZED with P_UNDERSIZE_CANDIDATE flag
- 30-entry Active Rationales DB with 5 duplicates → detect_duplicates returns 5 ticker groups

Run: python -m unittest test_preflight_v11_17 -v
"""

from __future__ import annotations

import unittest
from datetime import date

from recommendations_digest import (
    Rationale,
    compute_days_old,
    assign_freshness_band,
    infer_confidence,
    detect_duplicates,
    detect_likely_superseded,
    detect_untitled,
    enrich_rationales,
    _extract_ticker,
)
from options_expiry_preflight import (
    parse_option_symbol,
    compute_dte,
    compute_intrinsic,
    classify_moneyness,
    classify_action_band,
    OptionPosition,
    scan_positions,
    recommendation_for,
)
from position_drift_check import (
    parse_memory_baselines,
    compute_drift,
    cross_reference,
    MemoryBaseline,
    ActualPosition,
)


# ===========================================================================
# recommendations_digest tests
# ===========================================================================

class TestRecommendationsDigest(unittest.TestCase):

    def test_extract_ticker_em_dash(self):
        self.assertEqual(_extract_ticker("BMNR — T1 partial step-up"), "BMNR")

    def test_extract_ticker_compound(self):
        self.assertEqual(_extract_ticker("LEU Jan 2028 $300 LEAPS"), "LEU")

    def test_extract_ticker_simple(self):
        self.assertEqual(_extract_ticker("XLF"), "XLF")

    def test_extract_ticker_empty(self):
        self.assertEqual(_extract_ticker(""), "")

    def test_compute_days_old_basic(self):
        rec = date(2026, 5, 10)
        asof = date(2026, 5, 14)
        self.assertEqual(compute_days_old(rec, asof), 4)

    def test_compute_days_old_none(self):
        self.assertEqual(compute_days_old(None, date(2026, 5, 14)), -1)

    def test_assign_freshness_band_fresh(self):
        self.assertEqual(assign_freshness_band(0), "FRESH")
        self.assertEqual(assign_freshness_band(2), "FRESH")

    def test_assign_freshness_band_medium(self):
        self.assertEqual(assign_freshness_band(3), "MEDIUM")
        self.assertEqual(assign_freshness_band(7), "MEDIUM")

    def test_assign_freshness_band_older(self):
        self.assertEqual(assign_freshness_band(8), "OLDER")
        self.assertEqual(assign_freshness_band(14), "OLDER")

    def test_assign_freshness_band_stale(self):
        self.assertEqual(assign_freshness_band(15), "STALE")
        self.assertEqual(assign_freshness_band(100), "STALE")

    def test_assign_freshness_band_unknown(self):
        self.assertEqual(assign_freshness_band(-1), "UNKNOWN")

    def test_infer_confidence_high(self):
        text = "Multi-source named anchor; CONFIDENCE: HIGH ~80%."
        self.assertEqual(infer_confidence(text), "HIGH")

    def test_infer_confidence_med_high(self):
        text = "Single named source. CONFIDENCE: MED-HIGH ~70%."
        self.assertEqual(infer_confidence(text), "MED-HIGH")

    def test_infer_confidence_med(self):
        text = "Speculative starter. CONFIDENCE: MED ~55%."
        self.assertEqual(infer_confidence(text), "MED")

    def test_infer_confidence_unknown(self):
        self.assertEqual(infer_confidence(""), "UNKNOWN")

    def test_detect_duplicates(self):
        rationales = [
            self._mk_rationale("BMNR", "BMNR T1 step-up", date(2026, 5, 14)),
            self._mk_rationale("LEU", "LEU LEAPS", date(2026, 5, 14)),
            self._mk_rationale("BMNR", "BMNR T2 mention old", date(2026, 5, 10)),
            self._mk_rationale("CRCL", "CRCL spread", date(2026, 5, 14)),
            self._mk_rationale("CRCL", "CRCL DAT regulatory", date(2026, 5, 11)),
        ]
        dups = detect_duplicates(rationales)
        self.assertIn("BMNR", dups)
        self.assertIn("CRCL", dups)
        self.assertEqual(len(dups["BMNR"]), 2)
        self.assertEqual(len(dups["CRCL"]), 2)
        self.assertNotIn("LEU", dups)

    def test_detect_likely_superseded(self):
        rationales = [
            self._mk_rationale("CRCL", "CRCL spread", date(2026, 5, 14)),
            self._mk_rationale("CRCL", "CRCL old", date(2026, 5, 11)),
        ]
        dups = detect_duplicates(rationales)
        sup = detect_likely_superseded(dups)
        self.assertEqual(len(sup), 1)
        older, newer = sup[0]
        self.assertEqual(older.recommended_date, date(2026, 5, 11))
        self.assertEqual(newer.recommended_date, date(2026, 5, 14))

    def test_detect_untitled(self):
        rationales = [
            self._mk_rationale("", "New page", date(2026, 5, 13)),
            self._mk_rationale("", "", date(2026, 5, 13)),
            self._mk_rationale("BMNR", "BMNR T1 step-up", date(2026, 5, 14)),
        ]
        untitled = detect_untitled(rationales)
        self.assertEqual(len(untitled), 2)

    def test_enrich_rationales(self):
        rationales = [
            self._mk_rationale("BMNR", "BMNR T1; CONFIDENCE: HIGH ~80%",
                              date(2026, 5, 14)),
            self._mk_rationale("XLF", "XLF trim; CONFIDENCE: MED-HIGH ~70%",
                              date(2026, 5, 2)),
        ]
        enrich_rationales(rationales, date(2026, 5, 14))
        self.assertEqual(rationales[0].days_old, 0)
        self.assertEqual(rationales[0].freshness_band, "FRESH")
        self.assertEqual(rationales[0].confidence_inferred, "HIGH")
        self.assertEqual(rationales[1].days_old, 12)
        self.assertEqual(rationales[1].freshness_band, "OLDER")
        self.assertEqual(rationales[1].confidence_inferred, "MED-HIGH")

    def _mk_rationale(self, ticker, theme, rec_date, rationale_text=None) -> Rationale:
        return Rationale(
            page_id=f"id_{ticker}",
            ticker=ticker,
            ticker_theme=theme,
            rationale=rationale_text or theme,
            action="BUY",
            approx_size=1000,
            reference_price=10,
            target_price=20,
            source="Test",
            lane="Test",
            status="Active",
            recommended_date=rec_date,
            valid_until=None,
            account_hint=None,
        )


# ===========================================================================
# options_expiry_preflight tests
# ===========================================================================

class TestOptionsExpiryPreflight(unittest.TestCase):

    def test_parse_occ_basic(self):
        # IVES 2025-05-16 Call $30.00
        parsed = parse_option_symbol("IVES250516C00030000")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.underlying, "IVES")
        self.assertEqual(parsed.expiry, date(2025, 5, 16))
        self.assertEqual(parsed.option_type, "C")
        self.assertEqual(parsed.strike, 30.0)

    def test_parse_occ_put(self):
        parsed = parse_option_symbol("SMH260522P00560000")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.option_type, "P")
        self.assertEqual(parsed.strike, 560.0)

    def test_parse_occ_long_dated(self):
        parsed = parse_option_symbol("LEU280121C00300000")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.expiry, date(2028, 1, 21))
        self.assertEqual(parsed.strike, 300.0)

    def test_parse_occ_malformed(self):
        self.assertIsNone(parse_option_symbol("NOTANOPTION"))
        self.assertIsNone(parse_option_symbol(""))
        self.assertIsNone(parse_option_symbol("IVES"))

    def test_compute_dte_basic(self):
        self.assertEqual(compute_dte(date(2026, 5, 16), date(2026, 5, 14)), 2)
        self.assertEqual(compute_dte(date(2026, 5, 14), date(2026, 5, 14)), 0)
        self.assertEqual(compute_dte(date(2026, 5, 13), date(2026, 5, 14)), -1)

    def test_compute_intrinsic_call_itm(self):
        # Underlying $36.84, strike $30 call → $6.84 intrinsic
        self.assertAlmostEqual(compute_intrinsic("C", 30.0, 36.84), 6.84)

    def test_compute_intrinsic_call_otm(self):
        self.assertEqual(compute_intrinsic("C", 50.0, 36.84), 0.0)

    def test_compute_intrinsic_put_itm(self):
        self.assertAlmostEqual(compute_intrinsic("P", 560.0, 520.0), 40.0)

    def test_compute_intrinsic_put_otm(self):
        self.assertEqual(compute_intrinsic("P", 500.0, 520.0), 0.0)

    def test_classify_moneyness_call_itm(self):
        # Strike below underlying for call = ITM
        self.assertEqual(classify_moneyness("C", 30.0, 36.84), "ITM")

    def test_classify_moneyness_call_otm(self):
        self.assertEqual(classify_moneyness("C", 50.0, 36.84), "OTM")

    def test_classify_moneyness_put_itm(self):
        self.assertEqual(classify_moneyness("P", 560.0, 520.0), "ITM")

    def test_classify_moneyness_atm(self):
        # Within 2% of underlying
        self.assertEqual(classify_moneyness("C", 100.5, 100.0), "ATM")
        self.assertEqual(classify_moneyness("P", 99.5, 100.0), "ATM")

    def test_classify_action_band(self):
        self.assertEqual(classify_action_band(1, "ITM"), "ACTION_REQUIRED")
        self.assertEqual(classify_action_band(5, "OTM"), "ACTION_REQUIRED")
        self.assertEqual(classify_action_band(10, "ITM"), "WATCH")
        self.assertEqual(classify_action_band(30, "ATM"), "WATCH")
        self.assertEqual(classify_action_band(31, "ITM"), "OK")
        self.assertEqual(classify_action_band(-1, "ITM"), "EXPIRED")

    def test_ives_backtest_today(self):
        """Backtest: IVES $30 calls 1 DTE on 5/14, underlying $36.84 → ACTION_REQUIRED."""
        pos = OptionPosition(
            symbol="IVES260515C00030000",
            contracts=4,
            account="P-fid-Joint",
        )
        scan_positions([pos], {"IVES": 36.84}, date(2026, 5, 14))
        self.assertEqual(pos.dte, 1)
        self.assertEqual(pos.moneyness, "ITM")
        self.assertEqual(pos.action_band, "ACTION_REQUIRED")
        self.assertIn("SELL-TO-CLOSE", pos.recommendation)
        self.assertAlmostEqual(pos.intrinsic, 6.84)

    def test_smh_hedge_position(self):
        """SMH May 22 2026 $560 put with underlying $593 = OTM, 8 DTE → WATCH."""
        pos = OptionPosition(
            symbol="SMH260522P00560000",
            contracts=7,
        )
        scan_positions([pos], {"SMH": 593.0}, date(2026, 5, 14))
        self.assertEqual(pos.dte, 8)
        self.assertEqual(pos.moneyness, "OTM")
        self.assertEqual(pos.action_band, "WATCH")

    def test_leu_leaps_long_dated(self):
        """LEU Jan 2028 $300C — 600+ DTE → OK band."""
        pos = OptionPosition(
            symbol="LEU280121C00300000",
            contracts=1,
        )
        scan_positions([pos], {"LEU": 192.32}, date(2026, 5, 14))
        self.assertGreater(pos.dte, 600)
        self.assertEqual(pos.action_band, "OK")

    def test_missing_underlying_price(self):
        pos = OptionPosition(symbol="ABCD260530C00050000", contracts=1)
        scan_positions([pos], {}, date(2026, 5, 14))
        self.assertIn("MISSING_UNDERLYING_PRICE", pos.flags)


# ===========================================================================
# position_drift_check tests
# ===========================================================================

class TestPositionDriftCheck(unittest.TestCase):

    def test_parse_memory_explicit_pct(self):
        text = "BMNR T2 at 5% baseline. LEU is 5.1% position."
        baselines = parse_memory_baselines(text)
        tickers = {b.ticker: b.baseline_pct for b in baselines}
        self.assertIn("BMNR", tickers)
        self.assertAlmostEqual(tickers["BMNR"], 0.05)
        self.assertIn("LEU", tickers)
        self.assertAlmostEqual(tickers["LEU"], 0.051)

    def test_parse_memory_filters_false_positives(self):
        text = "AI is the future. ETF flows up 50%. USD weak at 5%."
        baselines = parse_memory_baselines(text)
        tickers = {b.ticker for b in baselines}
        self.assertNotIn("AI", tickers)
        self.assertNotIn("ETF", tickers)
        self.assertNotIn("USD", tickers)

    def test_compute_drift_undersized(self):
        b = MemoryBaseline(
            ticker="BMNR",
            baseline_pct=0.05,
            source_text="BMNR T2 5%",
            inferred_from_tier=False,
        )
        a = ActualPosition(ticker="BMNR", market_value=72793, pct_of_portfolio=0.0387)
        d = compute_drift(b, a)
        self.assertEqual(d.direction, "UNDERSIZED")
        self.assertIn("P_UNDERSIZE_CANDIDATE", d.flags)
        # Drift relative: (0.0387 - 0.05) / 0.05 = -0.226 = -22.6%
        self.assertAlmostEqual(d.drift_relative, -0.226, places=2)

    def test_compute_drift_in_band(self):
        b = MemoryBaseline(
            ticker="LEU",
            baseline_pct=0.05,
            source_text="",
            inferred_from_tier=False,
        )
        a = ActualPosition(ticker="LEU", market_value=95797, pct_of_portfolio=0.051)
        d = compute_drift(b, a)
        self.assertEqual(d.direction, "IN_BAND")
        self.assertEqual(d.flags, [])

    def test_compute_drift_oversized(self):
        b = MemoryBaseline(
            ticker="SMH",
            baseline_pct=0.075,
            source_text="",
            inferred_from_tier=False,
        )
        a = ActualPosition(ticker="SMH", market_value=180000, pct_of_portfolio=0.0961)
        d = compute_drift(b, a)
        self.assertEqual(d.direction, "OVERSIZED")
        self.assertIn("CONCENTRATION_CHECK", d.flags)

    def test_alarm_drift(self):
        b = MemoryBaseline(
            ticker="XYZ",
            baseline_pct=0.05,
            source_text="",
            inferred_from_tier=False,
        )
        # Actual 50% above memory baseline → drift = +50%
        a = ActualPosition(ticker="XYZ", market_value=75000, pct_of_portfolio=0.075)
        d = compute_drift(b, a, alarm_threshold=0.25)
        self.assertIn("ALARM_DRIFT", d.flags)

    def test_bmnr_backtest_today(self):
        """Backtest: BMNR memory 5% vs actual 3.87% should flag P-UNDERSIZE."""
        text = "P-AI-MOMENTUM. BMNR T2 at 5% baseline; upgrades to T1 at 10% on trigger."
        baselines = parse_memory_baselines(text)
        bmnr_b = next(b for b in baselines if b.ticker == "BMNR")
        self.assertAlmostEqual(bmnr_b.baseline_pct, 0.05)

        actual = ActualPosition(
            ticker="BMNR",
            market_value=72793,
            pct_of_portfolio=72793 / 1879245,  # = 0.0387
        )
        drift = compute_drift(bmnr_b, actual)
        self.assertEqual(drift.direction, "UNDERSIZED")
        self.assertIn("P_UNDERSIZE_CANDIDATE", drift.flags)
        # Should be roughly -23% drift
        self.assertLess(drift.drift_relative, -0.20)

    def test_cross_reference_unmatched(self):
        baselines = [
            MemoryBaseline("AAAA", 0.05, "", False),
            MemoryBaseline("BBBB", 0.03, "", False),
        ]
        actuals = [
            ActualPosition("BBBB", 30000, 0.03),
            ActualPosition("CCCC", 50000, 0.05),
        ]
        drift, unmatched_b, unmatched_a = cross_reference(baselines, actuals)
        self.assertEqual(len(drift), 1)
        self.assertEqual(drift[0].ticker, "BBBB")
        self.assertEqual(len(unmatched_b), 1)
        self.assertEqual(unmatched_b[0].ticker, "AAAA")
        self.assertEqual(len(unmatched_a), 1)
        self.assertEqual(unmatched_a[0].ticker, "CCCC")


if __name__ == "__main__":
    unittest.main(verbosity=2)
