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
    norm_tier, tier_band, classify_holding, classify_book,
    positions_from_feed, cash_pct_from_positions,
    Leg, TargetRow, FundingSummary, ReallocationResult,
    validate_reallocation, is_valid_reallocation,
    plan_reallocation, summary_line,
    run_gate_on_legs, format_reallocation, reallocate,
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
