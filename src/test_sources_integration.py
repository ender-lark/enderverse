"""Sources-layer INTEGRATION test (S8) — the Layer ① capstone / Checkpoint 1.

Wires all six v1 plug-builders through one `SourceRegistry` with fake inputs and
asserts the whole source foundation behaves:
  - `fetch_all` gathers every plug's cards, all valid against Contract A
  - error-tolerance: one bad plug -> a single kind="error" item, the rest survive
  - `independence_summary` groups correctly (the two Fundstrat plugs collapse to
    one echo-chamber group) — the Phase-2 weighting hook
  - cadence flows through (meridian static / bible monthly / …)
  - provenance is end-to-end (every card traces back to its source)

No live creds — every fetcher is injected with canned data. Run:
    python -m pytest src/test_sources_integration.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from sources import SourceRegistry, BaseSource
from validators import validate_items
from uw_price import build_uw_price_source
from uw_macro import build_uw_macro_source
from fundstrat_bible import build_fundstrat_bible_source
from fundstrat_daily import build_fundstrat_daily_source
from meridian import build_meridian_source
from portfolio import build_portfolio_source


# --------------------------------------------------------------------------- #
# the standard fake-data registry of all 6 v1 plugs (11 good cards total)
# --------------------------------------------------------------------------- #
def build_full_registry() -> SourceRegistry:
    reg = SourceRegistry()

    # uw_price -> 2 rotation cards (SMH leading, REMX lagging)
    closes = {"SPY": [100, 104, 108, 110], "SMH": [100, 130, 150, 157],
              "REMX": [100, 95, 96, 98]}
    reg.register(build_uw_price_source(
        closes, proxies=["SMH", "REMX"], benchmark="SPY", ai_benchmark="SMH",
        lookback_1m=1, lookback_3m=3, as_of="2026-05-29"))

    # uw_macro -> 2 macro cards (10Y rate + VIX level; no spread w/o a 2nd leg)
    reg.register(build_uw_macro_source(
        {"rates": {"10Y": {"value": 4.45, "value_5d_ago": 4.48}},
         "levels": {"VIX": {"value": 17.2, "value_5d_ago": 15.0}}},
        as_of="2026-05-29"))

    # fundstrat_bible -> 3 cards (stance + 1 sector + 1 top5)
    reg.register(build_fundstrat_bible_source(
        {"deck_date": "2026-05", "macro_stance": "constructive",
         "what_to_own": ["Technology"], "top5": ["NVDA"]}))

    # fundstrat_daily -> 1 analyst_call
    reg.register(build_fundstrat_daily_source(
        [{"author": "Newton", "ticker": "ITA", "direction": "buy",
          "quote": "ITA breakout", "date": "2026-05-28"}]))

    # meridian -> 1 analyst_call (thesis)
    reg.register(build_meridian_source(
        [{"subject": "LEU", "item_type": "thesis", "quote": "HALEU monopoly",
          "theme": "HALEU", "date": "2026-03-05"}]))

    # portfolio -> 2 position cards
    reg.register(build_portfolio_source(
        [{"ticker": "SMH", "pct": 9.9, "account": "Parents Fidelity"},
         {"ticker": "LEU", "pct": 4.89, "account": "SKB Schwab"}],
        as_of="2026-05-27"))

    return reg


EXPECTED_SOURCES = {"uw_price", "uw_macro", "fundstrat_bible",
                    "fundstrat_daily", "meridian", "portfolio"}


# --------------------------------------------------------------------------- #
# fetch_all gathers all 6, every card valid
# --------------------------------------------------------------------------- #
def test_fetch_all_gathers_every_plug():
    haul = build_full_registry().fetch_all()
    assert len(haul) == 11
    assert {c.source for c in haul} == EXPECTED_SOURCES


def test_full_haul_passes_contract_validator():
    haul = build_full_registry().fetch_all()
    report = validate_items(haul)
    assert report["total"] == 11
    assert report["ok"] == 11
    assert report["bad"] == []


def test_all_expected_kinds_present():
    kinds = {c.kind for c in build_full_registry().fetch_all()}
    # rotation(uw_price) macro(uw_macro) stance+what_to_own+analyst_call(bible/daily/meridian) position(portfolio)
    assert kinds == {"rotation", "macro", "stance", "what_to_own",
                     "analyst_call", "position"}


# --------------------------------------------------------------------------- #
# error-tolerance — one bad plug can't sink the pull
# --------------------------------------------------------------------------- #
def test_one_bad_plug_degrades_to_error_item():
    reg = build_full_registry()

    def boom():
        raise RuntimeError("notion read failed")
    reg.register(BaseSource("portfolio", boom))     # a portfolio fetch that throws

    haul = reg.fetch_all()
    errs = [c for c in haul if c.kind == "error"]
    goods = [c for c in haul if c.kind != "error"]
    assert len(errs) == 1
    assert errs[0].source == "portfolio"
    assert "notion read failed" in errs[0].content
    assert len(goods) == 11                          # all good plugs survived
    assert validate_items(haul)["bad"] == []         # the error item is well-formed


def test_real_plug_resilient_to_bad_input():
    # A too-short series makes uw_price emit a NO-DATA card internally — NOT a
    # registry error item. (Two layers of resilience: plug-internal + registry.)
    reg = SourceRegistry().register(build_uw_price_source(
        {"SPY": [100, 104, 108, 110], "VOLT": [100, 101]},
        proxies=["VOLT"], benchmark="SPY", ai_benchmark="SMH",
        lookback_1m=1, lookback_3m=3))
    haul = reg.fetch_all()
    assert all(c.kind != "error" for c in haul)
    assert haul[0].content == "NO DATA"
    assert validate_items(haul)["bad"] == []


# --------------------------------------------------------------------------- #
# independence summary — the echo-chamber grouping
# --------------------------------------------------------------------------- #
def test_independence_summary_groups():
    summ = build_full_registry().independence_summary()
    assert set(summ.keys()) == {"market_data", "fundstrat", "thematic_research", "own"}
    assert summ["market_data"] == ["uw_macro", "uw_price"]
    # the crux: the two Fundstrat plugs collapse into ONE independent voice
    assert summ["fundstrat"] == ["fundstrat_bible", "fundstrat_daily"]
    assert summ["thematic_research"] == ["meridian"]
    assert summ["own"] == ["portfolio"]


# --------------------------------------------------------------------------- #
# cadence flows through (the 5/30 addition)
# --------------------------------------------------------------------------- #
def test_cadence_carried_through_registry():
    cad = {s.name: s.cadence for s in build_full_registry().sources}
    assert cad["meridian"] == "static"
    assert cad["fundstrat_bible"] == "monthly"
    assert cad["uw_price"] == "daily"
    assert cad["uw_macro"] == "daily"
    assert cad["portfolio"] == "on_refresh"


# --------------------------------------------------------------------------- #
# provenance — every card traces back to its source, end to end
# --------------------------------------------------------------------------- #
def test_provenance_end_to_end():
    haul = build_full_registry().fetch_all()
    for c in haul:
        p = c.provenance()
        assert c.source in p and c.subject in p
    by = {(c.source, c.subject): c for c in haul}
    assert "meridian" in by[("meridian", "LEU")].provenance()
    assert "trust=0.95" in by[("portfolio", "SMH")].provenance()


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-q"]))
