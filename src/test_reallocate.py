#!/usr/bin/env python3
"""
test_reallocate.py — Chunk 1 tests for reallocate.py

Covers: norm_tier / tier_band, classify_holding (every class + the VOLT
factor-priority edge), classify_book, positions_from_feed + cash, and the
schema validator (happy path + ONE negative per guardrail invariant).

Run: python3 test_reallocate.py    (also pytest-discoverable)
"""
from __future__ import annotations

import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reallocate import (  # noqa: E402
    ADD, TRIM,
    CLS_CORE, CLS_OTHER_HC, CLS_MONITOR, CLS_TAIL, CLS_UNDOCUMENTED,
    SOURCE_TAG_PREFILLED, SOURCE_TAG_REQUIRED, SOURCE_TAG_ROTATION,
    SIZING_TIER_BAND, SIZING_EXPLICIT_TARGET, ETF_LOOKTHROUGH,
    norm_tier, tier_band, classify_holding, classify_book,
    positions_from_feed, cash_pct_from_positions,
    Leg, TargetRow, FundingSummary, ReallocationResult,
    validate_reallocation, is_valid_reallocation,
    plan_reallocation, plan_target_reallocation, summary_line,
    run_gate_on_legs, annotate_net_factor_overrides, net_factor_is_flat_or_down,
    format_reallocation, reallocate,
)

# --- tiny assert harness (also works under pytest as individual test fns) ---
_PASS = [0]
_FAIL = []


def _ok(cond, msg):
    if cond:
        _PASS[0] += 1
    else:
        _FAIL.append(msg)
        print("  FAIL:", msg)


# ===========================================================================
# norm_tier / tier_band
# ===========================================================================

def test_norm_tier():
    _ok(norm_tier("T1 Generational") == "T1", "norm_tier strips suffix")
    _ok(norm_tier("t3") == "T3", "norm_tier uppercases")
    _ok(norm_tier("") == "", "norm_tier empty -> ''")
    _ok(norm_tier("Generational") == "", "norm_tier unknown -> ''")


def test_tier_band():
    lo, hi = tier_band("T1")
    _ok((lo, hi) == (8.0, 12.0), "T1 band = 8-12%")
    lo, hi = tier_band("T2")
    _ok((lo, hi) == (4.0, 7.0), "T2 band = 4-7%")
    # untiered -> UNTIERED_DEFAULT (T3) band
    lo, hi = tier_band("")
    _ok((lo, hi) == (1.5, 3.0), "untiered -> T3 band")


# ===========================================================================
# classify_holding — every class + edges
# ===========================================================================

def test_classify_holding():
    bmnr = {"ticker": "BMNR", "tier": "T1", "stance": "MONITOR",
            "factor_tags": ["crypto", "eth"]}
    _ok(classify_holding(bmnr) == CLS_MONITOR, "MONITOR stance -> MONITOR")

    nvda = {"ticker": "NVDA", "tier": "T2",
            "factor_tags": ["ai_complex", "semiconductors"]}
    _ok(classify_holding(nvda) == CLS_CORE, "ai_complex -> CORE")

    xlf = {"ticker": "XLF", "tier": "T3", "factor_tags": ["financials", "cyclicals"]}
    _ok(classify_holding(xlf) == CLS_OTHER_HC, "financials -> OTHER_HIGH_CONVICTION")

    # VOLT = nuclear + ai_complex, NO MONITOR stance -> CORE (factor priority)
    volt = {"ticker": "VOLT", "tier": "T3", "factor_tags": ["nuclear", "ai_complex"]}
    _ok(classify_holding(volt) == CLS_CORE, "nuclear+ai, no stance -> CORE (priority)")

    t4 = {"ticker": "SPEC", "tier": "T4", "factor_tags": ["ai_complex"]}
    _ok(classify_holding(t4) == CLS_TAIL, "T4 -> TAIL_SPEC (even with core factor)")

    _ok(classify_holding(None) == CLS_UNDOCUMENTED, "no thesis -> UNDOCUMENTED")
    _ok(classify_holding({"ticker": "X"}) == CLS_UNDOCUMENTED,
        "thesis without tier -> UNDOCUMENTED")


def test_classify_book():
    positions = [
        {"ticker": "NVDA", "_pct": 6.73, "_sleeve": "AI / Semiconductors"},
        {"ticker": "BMNR", "_pct": 3.87, "_sleeve": "Crypto / ETH"},
        {"ticker": "MSFT", "_pct": 2.2, "_sleeve": "AI / Semiconductors"},  # undocumented
    ]
    theses = [
        {"ticker": "NVDA", "tier": "T2", "source": "Lee",
         "factor_tags": ["ai_complex", "semiconductors"]},
        {"ticker": "BMNR", "tier": "T1", "stance": "MONITOR",
         "factor_tags": ["crypto", "eth"]},
    ]
    rows = classify_book(positions, theses)
    by = {r.ticker: r for r in rows}
    _ok(by["NVDA"].sleeve_class == CLS_CORE and by["NVDA"].leggable,
        "NVDA -> CORE, leggable")
    _ok(by["NVDA"].ceiling_pct == 7.0, "NVDA ceiling 7%")
    _ok(by["BMNR"].sleeve_class == CLS_MONITOR and not by["BMNR"].leggable,
        "BMNR -> MONITOR, NOT leggable")
    _ok(by["MSFT"].sleeve_class == CLS_UNDOCUMENTED and not by["MSFT"].leggable,
        "MSFT (no thesis) -> UNDOCUMENTED, NOT leggable")


# ===========================================================================
# FEED adapter
# ===========================================================================

_FAKE_FEED = {
    "holdings": [
        {"cat": "AI / Semiconductors", "rot": {"w": "LEADING"}, "pos": [
            {"t": "SMH", "pct": 9.4, "own": "p,s", "ty": "Core"},
            {"t": "NVDA", "pct": 7.41, "own": "p,s", "ty": "Core"},
        ]},
        {"cat": "Financials", "rot": {"w": "IMPROVING"}, "pos": [
            {"t": "XLF", "pct": 1.0, "own": "p", "ty": "Tactical"},
        ]},
    ]
}


def test_positions_from_feed():
    pos = positions_from_feed(_FAKE_FEED, total_book_value=1_000_000)
    by = {p["ticker"]: p for p in pos}
    _ok(len(pos) == 3, "flattened 3 positions across 2 sleeves")
    _ok(abs(by["NVDA"]["market_value"] - 74_100) < 1, "NVDA mv = 7.41% * 1M")
    _ok(by["XLF"]["_sleeve"] == "Financials", "XLF sleeve from cat")
    _ok(by["SMH"]["_pct"] == 9.4, "pct preserved")
    # invested = 9.4+7.41+1.0 = 17.81 -> cash 82.19
    _ok(abs(cash_pct_from_positions(pos) - 82.19) < 0.01, "cash% = 100 - invested")

    try:
        positions_from_feed(_FAKE_FEED, total_book_value=0)
        _ok(False, "zero book should raise")
    except ValueError:
        _ok(True, "zero book raises ValueError")


# ===========================================================================
# Validator — happy path + one negative per invariant
# ===========================================================================

def _good_result() -> ReallocationResult:
    """A hand-built VALID reallocation: TRIM NVDA (above ceiling) funds ADD XLF
    (rotation, both high-conviction), MONITOR BMNR left untouched."""
    book = 1_875_000
    nvda_trim = Leg(
        leg_id="L1", action=TRIM, ticker="NVDA", sleeve="AI / Semiconductors",
        sleeve_class=CLS_CORE, tier="T2", current_pct=9.0, target_pct=7.0,
        delta_pct=-2.0, notional_usd=37_500, floor_pct=4.0, ceiling_pct=7.0,
        source_tag="Lee", source_tag_status=SOURCE_TAG_PREFILLED,
        funds_leg_id="L2", rotation=True, optional=True, rank=1,
        rationale="Trim over-ceiling semis to fund the financials add.",
        caveats=["NVDA is a strengthening winner — trim is optional."],
    )
    xlf_add = Leg(
        leg_id="L2", action=ADD, ticker="XLF", sleeve="Financials",
        sleeve_class=CLS_OTHER_HC, tier="T3", current_pct=1.0, target_pct=3.0,
        delta_pct=2.0, notional_usd=37_500, floor_pct=1.5, ceiling_pct=3.0,
        source_tag=None, source_tag_status=SOURCE_TAG_ROTATION,
        funded_by_leg_id="L1", rotation=True, rank=2,
        rationale="Below-target financials; funded by the semis trim.",
    )
    rows = [
        TargetRow("NVDA", "AI / Semiconductors", CLS_CORE, "T2", 9.0, 7.0, "ABOVE_CEILING"),
        TargetRow("XLF", "Financials", CLS_OTHER_HC, "T3", 1.0, 3.0, "BELOW_FLOOR"),
        TargetRow("BMNR", "Crypto / ETH", CLS_MONITOR, "T1", 3.0, 3.0, "CRITICALLY_BELOW"),
        TargetRow("REST", "AI / Semiconductors", CLS_CORE, "T2", 85.0, 85.0, "IN_BAND"),
    ]
    funding = FundingSummary(trims_total_usd=37_500, adds_total_usd=37_500,
                             cash_used_usd=0, shortfall_usd=0)
    return ReallocationResult(
        as_of="2026-06-01", total_book_value=book, cash_pct=2.0,
        mode={"names": "resize_only", "funding": "cash_neutral",
              "scope": "aggregate", "aggressiveness": "material_only"},
        legs=[nvda_trim, xlf_add], target_vs_current=rows, funding=funding,
        monitor_left_alone=["BMNR"], undocumented_excluded=[],
    )


def test_validator_happy_path():
    res = _good_result()
    errs = validate_reallocation(res)
    _ok(errs == [], f"good result validates clean (got {errs})")
    _ok(is_valid_reallocation(res), "is_valid_reallocation True")


def _expect_error(mutate, needle, label):
    d = _good_result().as_dict()
    mutate(d)
    errs = validate_reallocation(d)
    hit = any(needle in e for e in errs)
    _ok(hit, f"{label} (errors={errs})")


def test_validator_negatives():
    # MONITOR name appears as a leg
    def m1(d):
        d["legs"][0]["sleeve_class"] = CLS_MONITOR
    _expect_error(m1, "not leggable", "MONITOR leg rejected")

    # ADD target above ceiling
    def m2(d):
        d["legs"][1]["target_pct"] = 5.0  # ceiling 3.0
        d["legs"][1]["delta_pct"] = 4.0
    _expect_error(m2, "exceeds tier ceiling", "ADD-above-ceiling rejected")

    # TRIM target below ceiling
    def m3(d):
        d["legs"][0]["target_pct"] = 5.0  # ceiling 7.0 -> below
        d["legs"][0]["delta_pct"] = -4.0
    _expect_error(m3, "below tier ceiling", "TRIM-below-ceiling rejected")

    # TRIM on a name not above its ceiling
    def m4(d):
        d["legs"][0]["current_pct"] = 6.5  # ceiling 7.0 -> not above
        d["legs"][0]["target_pct"] = 6.0
        d["legs"][0]["delta_pct"] = -0.5
    _expect_error(m4, "only ABOVE_CEILING names are trim-eligible",
                  "TRIM-not-above-ceiling rejected")

    # gate flag disagrees with $25K threshold
    def m5(d):
        d["legs"][0]["gate"]["needs_gate"] = False  # notional 37,500 needs gate
    _expect_error(m5, "gate.needs_gate disagrees", "gate-flag mismatch rejected")

    # reconciliation broken
    def m6(d):
        d["target_vs_current"][3]["target_pct"] = 50.0  # was 85 -> breaks sum
    _expect_error(m6, "reconciliation", "broken reconciliation rejected")

    # funding not balanced
    def m7(d):
        d["funding"]["adds_total_usd"] = 100_000  # trims still 37,500
    _expect_error(m7, "funding", "unbalanced funding rejected")

    # banner flipped
    def m8(d):
        d["tax_agnostic"] = False
    _expect_error(m8, "tax_agnostic", "tax_agnostic banner enforced")

    # MONITOR row moved off current in target table
    def m9(d):
        d["target_vs_current"][2]["target_pct"] = 8.0  # BMNR 3 -> 8
    _expect_error(m9, "must be left untouched", "moved MONITOR row rejected")

    # delta mismatch
    def m10(d):
        d["legs"][0]["delta_pct"] = -1.0  # target-current = -2.0
    _expect_error(m10, "delta_pct", "delta/target-current mismatch rejected")

    # PREFILLED status but empty source tag
    def m11(d):
        d["legs"][0]["source_tag"] = None  # status still PREFILLED
    _expect_error(m11, "source_tag is empty", "empty PREFILLED source_tag rejected")


# ===========================================================================
# Chunk 2 — planner core
# ===========================================================================

BOOK = 1_875_000
_THESES_PL = [
    {"ticker": "SMH", "tier": "T2", "source": "Lee", "factor_tags": ["ai_complex", "semiconductors"]},
    {"ticker": "MAGS", "tier": "T2", "source": "Lee", "factor_tags": ["ai_complex"]},
    {"ticker": "XLF", "tier": "T3", "source": "Lee", "factor_tags": ["financials", "cyclicals"]},
    {"ticker": "BMNR", "tier": "T1", "stance": "MONITOR", "source": "operator", "factor_tags": ["crypto", "eth"]},
    {"ticker": "LEU", "tier": "T1", "stance": "MONITOR", "source": "Meridian", "factor_tags": ["nuclear", "uranium"]},
    {"ticker": "MP", "tier": "T3", "stance": "MONITOR", "source": "Meridian", "factor_tags": ["critical_minerals", "rare_earth"]},
    {"ticker": "UUUU", "tier": "T3", "stance": "MONITOR", "source": "Meridian", "factor_tags": ["uranium"]},
]


def _pos(d: dict):
    return [{"ticker": t, "_pct": p} for t, p in d.items()]


def test_validator_shortfall_ok():
    # positive shortfall with balanced adds==trims is VALID (shortfall is
    # unmet demand, not a funding source)
    d = _good_result().as_dict()
    d["funding"]["shortfall_usd"] = 50_000
    d["funding"]["unfunded_adds"] = ["ZZZ"]
    _ok(validate_reallocation(d) == [], "positive shortfall + balanced funding is valid")


def test_planner_rotation():
    # SMH/MAGS over T2 ceiling fund a below-floor XLF (financials) -> rotation
    book = {"SMH": 9.4, "MAGS": 9.1, "XLF": 0.3,
            "BMNR": 3.87, "LEU": 5.12, "MP": 2.12, "UUUU": 2.29}
    r = plan_reallocation(positions=_pos(book), theses=_THESES_PL, total_book_value=BOOK)
    _ok(validate_reallocation(r) == [], f"rotation result valid ({validate_reallocation(r)})")

    by = {(l.action, l.ticker): l for l in r.legs}
    _ok(("ADD", "XLF") in by, "XLF ADD leg present")
    xlf = by.get(("ADD", "XLF"))
    if xlf:
        _ok(xlf.rotation and xlf.source_tag_status == SOURCE_TAG_ROTATION,
            "XLF add flagged rotation + ROTATION_RATIONALE_REQUIRED")
        _ok(abs(xlf.target_pct - 1.5) < 0.01, "XLF add target = floor 1.5%")
    trims = [l for l in r.legs if l.action == TRIM]
    _ok(len(trims) >= 1 and all(l.optional for l in trims), "trim leg(s) present + optional")
    _ok(all(l.target_pct >= l.ceiling_pct - 0.05 for l in trims), "trims stay at/above ceiling")
    legged = {l.ticker for l in r.legs} | {l.ticker for l in r.sub_threshold_legs}
    _ok(not ({"BMNR", "LEU", "MP", "UUUU"} & legged), "MONITOR names NEVER legged")
    _ok(set(r.monitor_left_alone) == {"BMNR", "LEU", "MP", "UUUU"}, "monitor_left_alone = 4 names")
    _ok(abs(r.funding.adds_total_usd - r.funding.trims_total_usd) < 1.0,
        "funded adds == trims (cash-neutral)")
    _ok(r.funding.shortfall_usd == 0, "no shortfall")


def test_planner_leaves_monitor_and_undoc():
    # MONITOR below floor (BMNR) + undocumented over ceiling (FOO) -> neither legged
    book = {"SMH": 9.4, "XLF": 0.3, "BMNR": 3.87, "FOO": 4.0}
    r = plan_reallocation(positions=_pos(book), theses=_THESES_PL, total_book_value=BOOK)
    _ok(validate_reallocation(r) == [], "valid")
    legged = {l.ticker for l in r.legs} | {l.ticker for l in r.sub_threshold_legs}
    _ok("BMNR" not in legged, "MONITOR BMNR not legged")
    _ok("FOO" not in legged, "undocumented FOO not legged (no spurious trim)")
    _ok("FOO" in r.undocumented_excluded, "FOO in undocumented_excluded")
    _ok("BMNR" in r.monitor_left_alone, "BMNR in monitor_left_alone")


def test_planner_no_material_add():
    # core over ceiling, XLF IN-BAND, nothing below floor -> NO legs; trims not recommended
    book = {"SMH": 9.4, "MAGS": 9.1, "XLF": 2.0, "BMNR": 3.87}
    r = plan_reallocation(positions=_pos(book), theses=_THESES_PL, total_book_value=BOOK)
    _ok(validate_reallocation(r) == [], "valid")
    _ok(len(r.legs) == 0 and len(r.sub_threshold_legs) == 0, "no legs at all")
    _ok(any("not recommended" in n.lower() for n in r.notes),
        "trims-NOT-recommended note fires (no manufactured rotation)")
    _ok("BMNR" in r.monitor_left_alone, "BMNR untouched")


def test_planner_sub_threshold():
    # XLF 0.05pp below floor -> tiny add+trim -> sub-threshold, not in main legs
    book = {"SMH": 9.4, "XLF": 1.45, "BMNR": 3.87}
    r = plan_reallocation(positions=_pos(book), theses=_THESES_PL, total_book_value=BOOK)
    _ok(validate_reallocation(r) == [], "valid")
    _ok(len(r.legs) == 0, "tiny move NOT in material legs")
    _ok(len(r.sub_threshold_legs) >= 1, "tiny move surfaced in sub_threshold")


def test_planner_shortfall():
    # T1 core add needs $112.5K but only $3.75K trim capacity -> unfunded + shortfall
    theses = _THESES_PL + [{"ticker": "BIGC", "tier": "T1", "source": "Lee",
                            "factor_tags": ["ai_complex"]}]
    book = {"BIGC": 2.0, "SMH": 7.2, "BMNR": 3.87}
    r = plan_reallocation(positions=_pos(book), theses=theses, total_book_value=BOOK)
    _ok(validate_reallocation(r) == [], f"valid despite shortfall ({validate_reallocation(r)})")
    _ok("BIGC" in r.funding.unfunded_adds, "BIGC unfunded (insufficient trim capacity)")
    _ok(r.funding.shortfall_usd > 0, "shortfall surfaced")
    _ok(abs(r.funding.adds_total_usd - r.funding.trims_total_usd) < 1.0, "funded adds == trims")


def test_planner_deepwork_t1():
    # T1 core below floor WITH funding -> funded add, deepwork + gate flag
    theses = _THESES_PL + [{"ticker": "BIGC", "tier": "T1", "source": "Lee",
                            "factor_tags": ["ai_complex"]}]
    book = {"BIGC": 6.0, "SMH": 9.4, "BMNR": 3.87}
    r = plan_reallocation(positions=_pos(book), theses=theses, total_book_value=BOOK)
    _ok(validate_reallocation(r) == [], "valid")
    big = [l for l in r.legs if l.ticker == "BIGC" and l.action == ADD]
    _ok(len(big) == 1 and big[0].deepwork, "BIGC T1 add flagged deepwork")
    if big:
        _ok(big[0].gate["needs_gate"], "BIGC add (>=$25K) -> gate.needs_gate True")
        _ok(abs(big[0].target_pct - 8.0) < 0.01, "BIGC add target = T1 floor 8%")


# ===========================================================================
# Chunk 3 — gate wiring + renderer + e2e on the real FEED
# ===========================================================================

def test_gate_wiring():
    theses = _THESES_PL + [{"ticker": "BIGC", "tier": "T1", "source": "Lee",
                            "factor_tags": ["ai_complex"]}]
    book = {"BIGC": 6.0, "SMH": 9.4, "BMNR": 3.87}
    r = plan_reallocation(positions=_pos(book), theses=theses, total_book_value=BOOK)
    big = [l for l in r.legs if l.ticker == "BIGC" and l.action == ADD]
    _ok(len(big) == 1, "BIGC add present")
    if not big:
        return
    big = big[0]
    _ok(big.gate.get("result") is None, "gate result EMPTY before the live run (never baked in)")
    run_gate_on_legs(r, positions=_pos(book), theses=theses, total_book_value=BOOK,
                     macro={"regime": "NEUTRAL"}, source_rates={})
    res = big.gate.get("result")
    _ok(res is not None and res["overall"] in ("GREEN", "AMBER", "RED"),
        "live gate fired -> overall set")
    _ok(res["deepwork_required"], "T1 >=$25K -> deepwork_required True")


def test_render():
    book = {"SMH": 9.4, "MAGS": 9.1, "XLF": 0.3, "BMNR": 3.87, "LEU": 5.12}
    r = plan_reallocation(positions=_pos(book), theses=_THESES_PL, total_book_value=BOOK,
                          as_of="2026-06-01")
    md = format_reallocation(r)
    _ok("CANDIDATE" in md, "render carries the CANDIDATE banner")
    _ok("tax-agnostic" in md, "render carries tax-agnostic banner")
    _ok("XLF" in md and "Ranked moves" in md, "render shows the XLF move")
    _ok("MONITOR" in md and "BMNR" in md, "render shows MONITOR left-alone")


def test_render_no_material():
    book = {"SMH": 9.4, "MAGS": 9.1, "XLF": 2.0, "BMNR": 3.87}
    r = plan_reallocation(positions=_pos(book), theses=_THESES_PL, total_book_value=BOOK)
    md = format_reallocation(r)
    _ok("No material moves" in md, "render states no material moves")
    _ok("not recommended" in md.lower(), "render shows trims-not-recommended note")


def test_e2e_real_feed():
    import json as _json
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "conviction_engine")
    feed = _json.load(open(os.path.join(base, "golden_feed.json")))
    theses = _json.load(open(os.path.join(base, "theses.json")))
    r = plan_reallocation(feed=feed, theses=theses, total_book_value=1_875_000,
                          as_of="2026-06-01")
    _ok(validate_reallocation(r) == [], f"e2e real feed valid ({validate_reallocation(r)[:2]})")
    legged = {l.ticker for l in r.legs} | {l.ticker for l in r.sub_threshold_legs}
    _ok(not ({"BMNR", "LEU", "MP", "UUUU"} & legged), "real MONITOR set NEVER legged")
    _ok(set(r.monitor_left_alone) == {"BMNR", "LEU", "MP", "UUUU"}, "monitor_left_alone = real 4")
    for u in ("AVGO", "AMZN", "MSFT", "COST", "IBIT", "ITA", "ANET"):
        _ok(u in r.undocumented_excluded, f"{u} undocumented-excluded")
        _ok(u not in legged, f"{u} not legged (no spurious trim of undocumented core)")
    sub_tickers = {l.ticker for l in r.sub_threshold_legs}
    _ok("VOLT" in sub_tickers, "VOLT (sole below-floor CORE) surfaces as a sub-threshold add")
    _ok(len(r.legs) == 0, "no MATERIAL moves on the real book (honest)")
    md = format_reallocation(r)
    _ok(len(md) > 100 and "CANDIDATE" in md, "e2e render non-empty")


# ===========================================================================
# Chunk 4 — cash consistency + entry point
# ===========================================================================

def test_cash_consistency_warning():
    book = {"SMH": 9.4, "XLF": 0.3, "BMNR": 3.87}   # ~13.6% coverage
    r = plan_reallocation(positions=_pos(book), theses=_THESES_PL, total_book_value=BOOK,
                          expected_cash_pct=0.65)
    _ok(any("covers only" in w for w in r.warnings), "low FEED coverage warns")
    _ok(any("differs from stated" in w for w in r.warnings), "cash mismatch warns")
    _ok(validate_reallocation(r) == [], "warnings don't break the contract")


def test_entry_point():
    theses = _THESES_PL + [{"ticker": "BIGC", "tier": "T1", "source": "Lee",
                            "factor_tags": ["ai_complex"]}]
    book = {"BIGC": 6.0, "SMH": 9.4, "BMNR": 3.87}
    result, md = reallocate(positions=_pos(book), theses=theses, total_book_value=BOOK,
                            run_gate=True, macro={"regime": "NEUTRAL"}, source_rates={},
                            as_of="2026-06-01")
    _ok(isinstance(md, str) and "CANDIDATE" in md, "entry point returns rendered markdown")
    big = [l for l in result.legs if l.ticker == "BIGC" and l.action == ADD]
    _ok(bool(big) and big[0].gate.get("result") is not None,
        "run_gate=True populated the gate verdict")
    _ok(not any("CONTRACT VIOLATION" in w for w in result.warnings),
        "valid plan -> no contract-violation warning from self-validation")


# ===========================================================================
# Chunk 5 — TARGET-WEIGHT MODE (explicit per-name targets)
# ===========================================================================

TBOOK = 1_000_000   # clean book so target % == $ * 100

_THESES_TGT = [
    {"ticker": "NVDA", "tier": "T2", "source": "Lee", "factor_tags": ["ai_complex", "semiconductors"]},
    {"ticker": "SMH", "tier": "T2", "source": "Lee", "factor_tags": ["ai_complex", "semiconductors"]},
    {"ticker": "GOOGL", "tier": "T2", "source": "Lee", "factor_tags": ["ai_complex"]},
    {"ticker": "GRNY", "tier": "T2", "source": "Lee", "factor_tags": ["ai_complex"]},
    {"ticker": "MAGS", "tier": "T2", "source": "Lee", "factor_tags": ["ai_complex"]},
    {"ticker": "TSM", "tier": "T2", "source": "Lee", "factor_tags": ["ai_complex", "semiconductors"]},
    {"ticker": "ANET", "tier": "T3", "source": "Lee", "factor_tags": ["ai_complex"]},
    {"ticker": "XLF", "tier": "T3", "source": "Lee", "factor_tags": ["financials", "cyclicals"]},
    {"ticker": "BMNR", "tier": "T1", "stance": "MONITOR", "source": "op", "factor_tags": ["crypto", "eth"]},
]

# currents sum 42 -> cash 58. ANET is CORE but NOT in the target map (held).
_CUR_TGT = {"NVDA": 6.0, "SMH": 9.0, "GOOGL": 1.0, "GRNY": 8.0, "MAGS": 10.0,
            "XLF": 1.0, "ANET": 3.0, "BMNR": 4.0}
# TSM 0 -> 4 is a NEW position (not currently held). BMNR (MONITOR) -> 0 must be ignored.
_TGT_MAP = {"NVDA": 10.0, "SMH": 8.0, "GOOGL": 5.0, "GRNY": 3.0, "MAGS": 0.0,
            "XLF": 3.0, "TSM": 4.0, "BMNR": 0.0}


def _tgt_plan(**kw):
    return plan_reallocation(positions=_pos(_CUR_TGT), theses=_THESES_TGT,
                             total_book_value=TBOOK, target_weights=_TGT_MAP, **kw)


def test_target_mode_diff():
    r = _tgt_plan()
    _ok(validate_reallocation(r) == [], f"target plan valid ({validate_reallocation(r)})")
    _ok(r.mode["names"] == "target_weight", "mode flips to target_weight")
    _ok(all(l.binding == SIZING_EXPLICIT_TARGET for l in r.legs),
        "every target-mode leg is EXPLICIT_TARGET-bound")
    by = {(l.action, l.ticker): l for l in r.legs}
    nvda = by.get((ADD, "NVDA"))
    _ok(nvda is not None and abs(nvda.target_pct - 10.0) < 1e-6, "NVDA add hits exact 10% target")
    _ok(nvda and abs(nvda.delta_pct - 4.0) < 1e-6 and abs(nvda.notional_usd - 40_000) < 1,
        "NVDA delta +4pp / $40K")
    # explicit target ABOVE the tier ceiling is allowed (conscious promotion) + caveated
    _ok(nvda and nvda.target_pct > nvda.ceiling_pct, "NVDA 10% sits above its T2 ceiling (allowed)")
    _ok(nvda and any("ABOVE" in c for c in nvda.caveats), "above-ceiling promotion caveat present")
    _ok((ADD, "TSM") in by and abs(by[(ADD, "TSM")].current_pct) < 1e-6,
        "TSM is a NEW position add from 0%")
    _ok(r.explicit_targets.get("NVDA") == 10.0, "operator map stored on the result")


def test_target_full_exit_legs():
    r = _tgt_plan()
    mags = next((l for l in r.legs if l.ticker == "MAGS"), None)
    _ok(mags is not None and mags.action == TRIM and abs(mags.target_pct) < 1e-6,
        "MAGS is a full EXIT leg to 0%")
    _ok(mags and abs(mags.notional_usd - 100_000) < 1, "MAGS exit notional = full 10% position")
    _ok(mags and any("EXIT" in c for c in mags.caveats), "full-exit confirmation caveat present")


def test_target_monitor_untouched():
    r = _tgt_plan()
    legged = {l.ticker for l in r.legs} | {l.ticker for l in r.sub_threshold_legs}
    _ok("BMNR" not in legged, "MONITOR BMNR (in target map at 0) is NEVER legged")
    _ok("BMNR" in r.monitor_left_alone, "BMNR surfaced in monitor_left_alone")
    row = next((x for x in r.target_vs_current if x.ticker == "BMNR"), None)
    _ok(row and abs(row.target_pct - row.current_pct) < 1e-6, "BMNR row held at current (untouched)")
    _ok(any("MONITOR" in n for n in r.notes), "note explains the MONITOR name was left untouched")


def test_target_core_not_below_conviction():
    r = _tgt_plan()
    # (a) a CORE name NOT in the map is never trimmed — held at current
    legged = {l.ticker for l in r.legs}
    _ok("ANET" not in legged, "CORE ANET (not in map) is never trimmed by the planner")
    anet = next((x for x in r.target_vs_current if x.ticker == "ANET"), None)
    _ok(anet and abs(anet.target_pct - 3.0) < 1e-6, "ANET held flat at current 3%")
    # (b) an explicit below-floor CORE trim (GRNY 8->3, below T2 floor 4) is allowed
    #     but carries a visible de-conviction caveat
    grny = next((l for l in r.legs if l.ticker == "GRNY"), None)
    _ok(grny and grny.action == TRIM and abs(grny.target_pct - 3.0) < 1e-6, "GRNY trims to exact 3%")
    _ok(grny and grny.target_pct < grny.floor_pct, "GRNY 3% is below its T2 floor (4%)")
    _ok(grny and any("conviction floor" in c for c in grny.caveats),
        "below-floor CORE trim carries the de-conviction caveat")
    # (c) the validator pins every explicit leg to the map: a leg can't drift off it
    d = r.as_dict()
    d["explicit_targets"]["GRNY"] = 5.0   # leg still says 3% -> must be rejected
    errs = validate_reallocation(d)
    _ok(any("!= operator map" in e for e in errs), "explicit leg off the operator map is rejected")
    # (d) an explicit leg with NO map entry is rejected (no planner-invented trims)
    d2 = r.as_dict()
    d2["explicit_targets"].pop("GRNY", None)
    errs2 = validate_reallocation(d2)
    _ok(any("no entry in explicit_targets" in e for e in errs2),
        "explicit leg absent from the map is rejected")


def test_target_net_factor_neutral_pairing():
    r = _tgt_plan()
    by = {(l.action, l.ticker): l for l in r.legs}
    # ai add funded by ai trim -> NET-FACTOR-NEUTRAL (same-factor), NOT cross-sleeve
    for tk in ("NVDA", "GOOGL", "TSM"):
        leg = by.get((ADD, tk))
        _ok(leg and leg.net_factor_neutral and leg.net_factor_label == "ai_complex",
            f"{tk} add is NET-FACTOR-NEUTRAL on ai_complex (funded by a same-factor trim)")
        _ok(leg and not leg.rotation, f"{tk} same-factor funding is NOT a cross-sleeve rotation")
    # financials add funded by an ai trim -> cross-sleeve rotation, ROTATION tag, not neutral
    xlf = by.get((ADD, "XLF"))
    _ok(xlf and xlf.rotation and xlf.source_tag_status == SOURCE_TAG_ROTATION,
        "XLF (financials) funded cross-sleeve -> ROTATION_RATIONALE_REQUIRED")
    _ok(xlf and not xlf.net_factor_neutral, "cross-sleeve XLF is NOT net-factor-neutral")
    # whole-plan net factor delta: ai_complex is net flat-or-DOWN (a true rotation)
    _ok(r.net_factor_delta.get("ai_complex", 1) <= 0, "net ai_complex delta <= 0 (rotation, not net-new)")
    _ok(net_factor_is_flat_or_down(r, "ai_complex"), "ai_complex reads flat-or-down for the gate")
    _ok(r.net_factor_delta.get("financials", 0) > 0, "financials is a genuine net add (cross-sleeve)")


def test_target_lookthrough_warning():
    r = _tgt_plan()  # SMH held at 8% AND NVDA/TSM sized as singles
    _ok(len(r.lookthrough) >= 1, "look-through finding surfaced")
    smh = next((lt for lt in r.lookthrough if lt["etf"] == "SMH"), None)
    _ok(smh is not None, "SMH look-through present")
    nvda_ov = next((o for o in (smh or {}).get("overlaps", []) if o["ticker"] == "NVDA"), None)
    _ok(nvda_ov is not None, "NVDA flagged as an SMH constituent double-counted")
    if nvda_ov:
        # SMH 8% * 0.13 NVDA = 1.04% via the ETF; true ~ 10 + 1.04
        _ok(abs(nvda_ov["via_etf_pct"] - round(8.0 * ETF_LOOKTHROUGH["SMH"]["constituents"]["NVDA"], 4)) < 1e-6,
            "look-through NVDA% = SMH% * constituent weight")
        _ok(abs(nvda_ov["true_pct"] - (nvda_ov["single_pct"] + nvda_ov["via_etf_pct"])) < 1e-6,
            "true exposure = single + via-ETF")
    _ok(any("look-through" in w.lower() for w in r.warnings), "look-through warning text surfaced")
    _ok(any("Approach A" in w and "Approach B" in w for w in r.warnings),
        "warning offers both approach A and B")


def test_target_funding_conservation():
    r = _tgt_plan()
    f = r.funding
    # sources (trims + cash_used) == uses (funded adds + cash_freed)
    _ok(abs((f.trims_total_usd + f.cash_used_usd) - (f.adds_total_usd + f.cash_freed_usd)) < 1.0,
        "funding conserved: trims+cash_used == adds+cash_freed")
    # trims 160K > adds 140K -> 20K surplus parks to cash
    _ok(abs(f.trims_total_usd - 160_000) < 1 and abs(f.adds_total_usd - 140_000) < 1,
        "trims $160K fund adds $140K")
    _ok(abs(f.cash_freed_usd - 20_000) < 1 and f.cash_used_usd == 0, "surplus $20K freed to cash")
    # reconciliation: sum(target%) over EVERY holding + cash% ~= 100
    tot = round(sum(x.target_pct for x in r.target_vs_current) + r.cash_pct, 3)
    _ok(abs(tot - 100.0) < 0.5, f"sum(target%) + cash% == 100 (got {tot})")
    _ok(abs(r.cash_pct - 60.0) < 0.01, "cash 58% + $20K freed -> 60%")


def test_target_shortfall_when_adds_exceed_capacity():
    # adds need more than trims + available cash -> unfunded, listed names stay put
    theses = _THESES_TGT
    cur = {"NVDA": 6.0, "GRNY": 7.0, "BMNR": 4.0}   # invested 17 -> cash 83? no: 17 -> cash 83
    # shrink cash by adding a big non-target holding so there's little cash
    cur = {"NVDA": 6.0, "GRNY": 7.0, "ANET": 80.0, "BMNR": 4.0}   # cash ~3%
    tmap = {"NVDA": 60.0, "GRNY": 6.0}              # NVDA needs $540K, GRNY frees $10K
    r = plan_reallocation(positions=_pos(cur), theses=theses, total_book_value=TBOOK,
                          target_weights=tmap)
    _ok(validate_reallocation(r) == [], f"shortfall plan still valid ({validate_reallocation(r)})")
    _ok("NVDA" in r.funding.unfunded_adds, "NVDA unfunded (insufficient trims + cash)")
    _ok(r.funding.shortfall_usd > 0, "shortfall surfaced")
    nvda_row = next((x for x in r.target_vs_current if x.ticker == "NVDA"), None)
    _ok(nvda_row and abs(nvda_row.target_pct - 6.0) < 1e-6, "unfunded NVDA stays at current (not partial)")


def test_target_sequencing():
    r = _tgt_plan(sequence_events={"NVDA": "AVGO 6/3 print", "TSM": "AVGO 6/3 print"})
    nvda = next((l for l in r.legs if l.ticker == "NVDA"), None)
    googl = next((l for l in r.legs if l.ticker == "GOOGL"), None)
    _ok(nvda and nvda.stage_after == "AVGO 6/3 print", "NVDA leg tagged stage-after the print")
    _ok(googl and googl.stage_after is None, "GOOGL leg is 'now' (untagged)")
    _ok(any("Sequencing" in n for n in r.notes), "sequencing note surfaced")
    md = format_reallocation(r)
    _ok("stage after AVGO 6/3 print" in md, "renderer shows the staging tag")


def test_target_gate_and_override():
    # high-AI book (~60% ai) so the gate REDs the AI add in isolation; the funded
    # same-factor rotation is net-flat -> override re-reads RED as AMBER.
    theses = [
        {"ticker": "NVDA", "tier": "T1", "source": "Lee", "factor_tags": ["ai_complex", "semiconductors"]},
        {"ticker": "MAGS", "tier": "T2", "source": "Lee", "factor_tags": ["ai_complex"]},
        {"ticker": "SMH", "tier": "T2", "source": "Lee", "factor_tags": ["ai_complex", "semiconductors"]},
        {"ticker": "BMNR", "tier": "T1", "stance": "MONITOR", "source": "op", "factor_tags": ["crypto"]},
    ]
    cur = {"NVDA": 8.0, "MAGS": 40.0, "SMH": 12.0, "BMNR": 4.0}   # ai ~60%
    tmap = {"NVDA": 11.0, "MAGS": 37.0}                            # +$30K NVDA <- -$30K MAGS
    result, md = reallocate(positions=_pos(cur), theses=theses, total_book_value=TBOOK,
                            target_weights=tmap, run_gate=True, macro={"regime": "NEUTRAL"},
                            source_rates={})
    _ok(not any("CONTRACT VIOLATION" in w for w in result.warnings), "valid plan, no self-violation")
    nvda = next((l for l in result.legs if l.ticker == "NVDA" and l.action == ADD), None)
    _ok(nvda is not None, "NVDA add present")
    if not nvda:
        return
    _ok(nvda.gate["needs_gate"], "NVDA add >=$25K -> needs_gate")
    _ok(nvda.deepwork, "NVDA is T1 -> leg flagged DEEPWORK")
    g = nvda.gate.get("result")
    _ok(g is not None and g["deepwork_required"], "live gate fired -> deepwork_required")
    reds = [fl for fl in g["flags"] if fl["code"] == "INCREMENTAL_FACTOR_CONCENTRATION"
            and fl["color"] == "RED"]
    _ok(len(reds) >= 1 and g["overall"] == "RED", "gate REDs the AI add in isolation")
    ov = g.get("overrides", [])
    _ok(any(o["read_as"] == "AMBER" and o["factor"] == "ai_complex" for o in ov),
        "net-factor reconciliation re-reads the concentration RED as AMBER")
    _ok("read as **AMBER**" in md, "renderer surfaces the override")


def test_target_undocumented_in_map_excluded():
    # a target name with no thesis/tier is excluded (not legged) + warned
    cur = {"NVDA": 6.0, "MAGS": 10.0, "BMNR": 4.0}
    tmap = {"NVDA": 10.0, "MAGS": 0.0, "ZZZ": 5.0}   # ZZZ has no thesis
    r = plan_reallocation(positions=_pos(cur), theses=_THESES_TGT, total_book_value=TBOOK,
                          target_weights=tmap)
    _ok(validate_reallocation(r) == [], "valid despite undocumented target")
    legged = {l.ticker for l in r.legs}
    _ok("ZZZ" not in legged, "undocumented ZZZ not legged")
    _ok("ZZZ" in r.undocumented_excluded, "ZZZ in undocumented_excluded")
    _ok(any("no thesis" in n for n in r.notes), "note explains the undocumented exclusion")


def test_target_validator_funding_negatives():
    r = _tgt_plan()
    # break the cash_freed conservation -> funding error
    d = r.as_dict()
    d["funding"]["cash_freed_usd"] = 999_999
    _ok(any("funding" in e for e in validate_reallocation(d)),
        "broken cash_freed conservation rejected")
    # negative cash_freed rejected
    d2 = r.as_dict()
    d2["funding"]["cash_freed_usd"] = -10.0
    _ok(any("cash_freed_usd must be >= 0" in e for e in validate_reallocation(d2)),
        "negative cash_freed rejected")
    # MONITOR name legged in target mode rejected (reuses the leggable guard)
    d3 = r.as_dict()
    d3["legs"][0]["sleeve_class"] = CLS_MONITOR
    _ok(any("not leggable" in e for e in validate_reallocation(d3)),
        "MONITOR-classed target leg rejected")


def test_target_dispatch_and_tierband_unaffected():
    # omitting target_weights -> tier-band mode, legs are TIER_BAND-bound
    book = {"SMH": 9.4, "MAGS": 9.1, "XLF": 0.3, "BMNR": 3.87, "LEU": 5.12, "MP": 2.12, "UUUU": 2.29}
    tb = plan_reallocation(positions=_pos(book), theses=_THESES_PL, total_book_value=BOOK)
    _ok(tb.mode["names"] != "target_weight", "no target_weights -> tier-band mode")
    _ok(all(l.binding == SIZING_TIER_BAND for l in tb.legs), "tier-band legs are TIER_BAND-bound")
    _ok(tb.explicit_targets == {} and tb.net_factor_delta == {},
        "tier-band result carries no target-mode artifacts")
    # the entry point routes target_weights through to target mode
    res, md = reallocate(positions=_pos(_CUR_TGT), theses=_THESES_TGT, total_book_value=TBOOK,
                         target_weights=_TGT_MAP)
    _ok(res.mode["names"] == "target_weight" and "NET-FACTOR" in md.upper(),
        "reallocate() entry point drives target mode when target_weights given")


def test_target_e2e_real_feed():
    import json as _json
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "conviction_engine")
    feed = _json.load(open(os.path.join(base, "golden_feed.json")))
    theses = _json.load(open(os.path.join(base, "theses.json")))
    # documented CORE names in the real theses; MONITOR set (BMNR/LEU/MP/UUUU) must stay untouched
    tmap = {"NVDA": 9.0, "SMH": 7.0, "MAGS": 0.0, "BMNR": 0.0}  # BMNR is MONITOR -> ignored
    r = plan_reallocation(feed=feed, theses=theses, total_book_value=1_875_000,
                          target_weights=tmap, as_of="2026-06-02")
    _ok(validate_reallocation(r) == [], f"real-feed target plan valid ({validate_reallocation(r)[:2]})")
    legged = {l.ticker for l in r.legs} | {l.ticker for l in r.sub_threshold_legs}
    _ok(not ({"BMNR", "LEU", "MP", "UUUU"} & legged), "real MONITOR set never legged in target mode")
    _ok("BMNR" in r.monitor_left_alone, "BMNR (targeted but MONITOR) left alone")
    md = format_reallocation(r)
    _ok(len(md) > 100 and "CANDIDATE" in md, "real-feed target render non-empty")


def _run_all():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    total = _PASS[0] + len(_FAIL)
    print(f"\n{_PASS[0]}/{total} assertions passed.")
    return not _FAIL


if __name__ == "__main__":
    sys.exit(0 if _run_all() else 1)
