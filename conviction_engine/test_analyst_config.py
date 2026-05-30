"""Unit tests for the Analyst config (A1).

Run:  python -m pytest src/test_analyst_config.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import uw_price
import analyst_config as cfg


# theses.json-shaped fixture (mirrors the real structure)
FAKE_THESES = [
    {"ticker": "BMNR", "tier": "T1", "lane": "Generational", "source": "operator",
     "factor_tags": ["crypto", "eth"]},
    {"ticker": "LEU", "tier": "T1", "lane": "Generational", "source": "Meridian",
     "factor_tags": ["critical_minerals", "nuclear"]},
    {"ticker": "NVDA", "tier": "T2", "lane": "Speed", "source": "Lee",
     "factor_tags": ["ai_complex", "semiconductors"]},
    {"ticker": "XLF", "tier": "T3", "lane": "BuyAndHold", "source": "Lee",
     "factor_tags": ["financials"]},
]


# --------------------------------------------------------------------------- #
# rotation bands — single source of truth
# --------------------------------------------------------------------------- #
def test_rotation_bands_are_the_uw_price_object():
    # the Analyst reuses the plug's bands — no divergent second definition
    assert cfg.ROTATION_BANDS is uw_price.ROTATION_BANDS


# --------------------------------------------------------------------------- #
# macro alerts
# --------------------------------------------------------------------------- #
def test_macro_alerts_thresholds():
    a = cfg.MACRO_ALERTS
    assert a["10y_above"]["threshold"] == 4.75
    assert a["move_above"]["threshold"] == 120
    assert a["vix_above"]["threshold"] == 25
    assert a["dxy_5d_move"]["threshold"] == 2.0
    assert a["wti_5d_move_pct"]["threshold"] == 5.0
    assert a["real10y_5d_bp"]["threshold"] == 25
    assert a["2s10s_flip"]["kind"] == "sign_cross"


def test_macro_alerts_cover_the_seven():
    assert len(cfg.MACRO_ALERTS) == 7


# --------------------------------------------------------------------------- #
# staleness budgets by cadence — the Meridian payoff
# --------------------------------------------------------------------------- #
def test_staleness_budget_values():
    assert cfg.staleness_budget_for("daily") == 2
    assert cfg.staleness_budget_for("on_refresh") == 7
    assert cfg.staleness_budget_for("monthly") == 35
    assert cfg.staleness_budget_for("static") is None
    assert cfg.staleness_budget_for("weekly") == 2     # unknown -> conservative daily


def test_is_stale_daily():
    assert cfg.is_stale(1, "daily") is False
    assert cfg.is_stale(2, "daily") is False           # boundary: == budget, not stale
    assert cfg.is_stale(3, "daily") is True


def test_is_stale_monthly_and_on_refresh():
    assert cfg.is_stale(30, "monthly") is False
    assert cfg.is_stale(40, "monthly") is True
    assert cfg.is_stale(5, "on_refresh") is False
    assert cfg.is_stale(8, "on_refresh") is True


def test_static_source_is_never_stale():
    # the crux: a frozen baseline (Meridian) never alarms, however old
    assert cfg.is_stale(9999, "static") is False


# --------------------------------------------------------------------------- #
# name -> source map + theses_by_ticker
# --------------------------------------------------------------------------- #
def test_name_source_map():
    m = cfg.name_source_map(FAKE_THESES)
    assert m == {"BMNR": "operator", "LEU": "Meridian", "NVDA": "Lee", "XLF": "Lee"}


def test_name_source_map_skips_tickerless():
    m = cfg.name_source_map([{"source": "Lee"}, {"ticker": "NVDA", "source": "Lee"}])
    assert m == {"NVDA": "Lee"}


def test_theses_by_ticker_lookup():
    by = cfg.theses_by_ticker(FAKE_THESES)
    assert by["NVDA"]["tier"] == "T2"
    assert by["NVDA"]["lane"] == "Speed"
    assert "ai_complex" in by["NVDA"]["factor_tags"]
    assert by["LEU"]["source"] == "Meridian"


def test_empty_theses_safe():
    assert cfg.name_source_map([]) == {}
    assert cfg.theses_by_ticker(None) == {}


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-q"]))
