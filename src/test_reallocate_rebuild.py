#!/usr/bin/env python3
"""Tests for the rebuilt reallocate.py (target-weight rotation planner)."""
from reallocate import (
    reallocate, plan_reallocation, current_weights, build_funding_pool,
    effective_current_pct, kept_wrapper_weights,
    ADD, TRIM, TAG_PARABOLIC, TAG_CONSTRUCTIVE, GATE_AMBER, GATE_GREEN,
    AI_FACTOR_WRAPPERS, BROAD_RESERVOIRS,
)
from reallocate_config import (
    Dials, DEFAULT_DIALS, ConcentrationRail, default_working_model, RAIL_PRESET_DISCUSSED,
)

FAILS = []
def ok(c, m):
    if not c: FAILS.append(m)


# ---- fixture: the operator's 5/31 book (current weights -> market values) ----
BOOK = 1_921_934.0
CUR_PCT = {
    "NVDA": 6.56, "SMH": 8.88, "GOOGL": 1.09, "AVGO": 1.97, "MSFT": 1.41,
    "AMZN": 1.25, "TSM": 0.0, "MU": 3.28, "ANET": 0.29, "ASML": 0.39,
    "FN": 0.17, "VRT": 0.0, "MAGS": 8.96, "IGV": 5.10, "IVES": 3.88,
    "SOXX": 1.51, "GRNY": 8.72, "GRNJ": 7.28,
    # a couple of non-AI / MONITOR holdings to confirm they're left alone
    "LEU": 4.5, "GS": 3.0, "GLD": 2.0,
}
POS = [{"ticker": t, "market_value": p / 100.0 * BOOK} for t, p in CUR_PCT.items()]
# run-up tags from the 6/2 watchlist (1M %): constructive (off-highs) vs parabolic
RUN_UP = {
    "GOOGL": -5.5, "MSFT": -8.6, "AMZN": -4.0, "ANET": 1.0, "FN": -2.0,   # constructive
    "NVDA": 12.0, "TSM": 11.0, "ASML": 18.0, "AVGO": 12.0,                # extended
    "MU": 93.0,                                                            # parabolic
}


def test_weights_and_lookthrough():
    w = current_weights(POS, BOOK)
    ok(abs(w["NVDA"] - 6.56) < 0.01, "current weight NVDA")
    # kept wrappers under default dials: SMH 5 (GRNY is broad, not a look-through factor wrapper)
    kw = kept_wrapper_weights(DEFAULT_DIALS)
    ok(kw.get("SMH") == 5.0, "kept SMH = 5 (Approach B)")
    ok("GRNY" not in kw, "GRNY is broad, not in AI-factor look-through")
    # NVDA effective = direct 6.56 + SMH@5%*0.20 = 6.56 + 1.0 = 7.56
    eff = effective_current_pct("NVDA", w, DEFAULT_DIALS)
    ok(abs(eff - 7.56) < 0.02, f"NVDA effective incl look-through ~7.56, got {eff}")


def test_funding_pool_order():
    w = current_weights(POS, BOOK)
    pool, src = build_funding_pool(w, BOOK, DEFAULT_DIALS, default_working_model())
    etfs = [s["etf"] for s in src]
    # AI-factor wrappers must come before broad reservoirs in the draw order
    ai_idx = [i for i, e in enumerate(etfs) if e in AI_FACTOR_WRAPPERS]
    broad_idx = [i for i, e in enumerate(etfs) if e in BROAD_RESERVOIRS]
    if ai_idx and broad_idx:
        ok(max(ai_idx) < min(broad_idx), "AI-factor wrappers drawn before broad reservoirs")
    # pool > 0 (there IS convertible excess: MAGS 9, IGV 5.1, IVES 3.88, SOXX 1.51, SMH 3.88, GRNY 5.72...)
    ok(pool > 100_000, f"pool should be sizeable, got {pool}")
    ok("GRNJ" not in etfs, "GRNJ is protected from default funding pool")
    ok("GRNY" in etfs, "GRNY can still be a reviewable reservoir when above keep level")


def test_end_to_end_default():
    res, md = reallocate(positions=POS, total_book_value=BOOK, run_up=RUN_UP, as_of="2026-05-31")
    adds = [l for l in res.legs if l.action == ADD]
    trims = [l for l in res.legs if l.action == TRIM]
    add_tk = {l.ticker for l in adds}

    # GOOGL is the biggest gap + constructive -> should rank #1 (conviction+entry, not gap)
    ok(adds and adds[0].ticker in {"GOOGL", "NVDA"}, f"top add is a T1 constructive/compute name, got {adds[0].ticker if adds else None}")
    # MU is HOLD-FLAT (target 3, current 3.28) -> no MU add
    ok("MU" not in add_tk, "MU not added (hold-flat, at target)")
    # AVGO is catalyst-gated -> sequence 'later', entry mentions the print
    avgo = next((l for l in adds if l.ticker == "AVGO"), None)
    ok(avgo is not None and "after" in avgo.sequence, "AVGO is catalyst-sequenced (after 6/3)")
    ok(("AVGO", ) not in [(t,) for t in res.sequence_now], "AVGO not in 'now'")
    # catalyst-correlation: NVDA + TSM inherit AVGO's 6/3 gate (your 6/2 sequence)
    nvda = next((l for l in adds if l.ticker == "NVDA"), None)
    ok(nvda is not None and nvda.sequence.startswith("after"), "NVDA waits for AVGO's correlated print")
    ok("NVDA" not in res.sequence_now and "TSM" not in res.sequence_now, "NVDA/TSM not in 'now' (correlated to AVGO)")
    # adds funded by AI wrappers are AMBER, not RED
    big = [l for l in adds if l.notional_usd >= 25_000]
    ok(all(l.gate == GATE_AMBER for l in big), "funded adds gate AMBER (factor-flat), none RED")
    # rotation is ~flat: total adds ~= total trims
    ta = sum(l.notional_usd for l in adds)
    tt = sum(l.notional_usd for l in trims)
    ok(abs(ta - tt) < 1.0, f"AI held flat: adds {ta:.0f} ~= trims {tt:.0f}")
    ok(all(l.ticker != "GRNJ" for l in trims), "GRNJ not trimmed by default")
    ok(any("GRNJ" in n and "protected" in n for n in res.notes), "GRNJ protection noted")
    # MONITOR/non-AI names left alone
    ok("LEU" in res.other_left_alone and "GS" in res.other_left_alone, "non-AI/MONITOR left alone")
    # rail OFF by default -> no violations reported
    ok(res.rail_status == "off" and res.rail_violations == [], "concentration rail off by default")
    # markdown renders
    ok("Ranked adds" in md and "Funding (one pool" in md, "markdown renders key sections")


def test_chase_gate():
    # make NVDA parabolic -> it should be 'on pullback', not 'now'
    runup2 = dict(RUN_UP, NVDA=80.0)
    res, _ = reallocate(positions=POS, total_book_value=BOOK, run_up=runup2)
    nvda = next((l for l in res.legs if l.action == ADD and l.ticker == "NVDA"), None)
    if nvda:
        ok(nvda.run_up_tag == TAG_PARABOLIC and nvda.sequence == "on pullback",
           "parabolic NVDA -> wait/pullback, not now")


def test_dial_change_changes_plan():
    # turn NVDA target down to 7 -> its gap shrinks vs default 12
    res12, _ = reallocate(positions=POS, total_book_value=BOOK, run_up=RUN_UP)
    n12 = next((l.notional_usd for l in res12.legs if l.action == ADD and l.ticker == "NVDA"), 0.0)
    d7 = Dials(nvda_target_pct=7.0)
    # also need the model NVDA target to reflect 7; model is separate -> build a model copy
    m = default_working_model()
    for t in m.targets:
        if t.ticker == "NVDA":
            t.target_pct = 7.0
    res7, _ = reallocate(positions=POS, total_book_value=BOOK, run_up=RUN_UP, dials=d7, model=m)
    n7 = next((l.notional_usd for l in res7.legs if l.action == ADD and l.ticker == "NVDA"), 0.0)
    ok(n7 < n12, f"lower NVDA target -> smaller NVDA add ({n7:.0f} < {n12:.0f})")


def test_optional_rail_on():
    # switch the rail ON via a dial -> the discussed preset; the default model
    # post-rotation has AI-ETF ~8% (SMH5+GRNY3) so an 18% floor trips -> violations appear
    d = Dials(concentration_rail=RAIL_PRESET_DISCUSSED)
    res, _ = reallocate(positions=POS, total_book_value=BOOK, run_up=RUN_UP, dials=d)
    ok(res.rail_status != "off", "rail reported ON when set")
    ok(any("floor" in v for v in res.rail_violations),
       "18% ETF floor trips under Approach B (the documented tension)")


def test_no_runup_degrades():
    res, _ = reallocate(positions=POS, total_book_value=BOOK)  # no run_up
    ok(any("chase-gate inactive" in w for w in res.warnings), "no run-up -> chase gate degrades with a warning")


def test_catalyst_correlation_dial():
    # default: AVGO's 6/3 gate propagates to NVDA + TSM (the 6/2 sequence)
    res, _ = reallocate(positions=POS, total_book_value=BOOK, run_up=RUN_UP)
    later = {t for t, _r in res.sequence_later}
    ok({"NVDA", "TSM", "AVGO"} <= later, "AVGO + correlated NVDA/TSM all sequenced later")
    # clear the correlation -> NVDA/TSM go now again (dial works both ways)
    d = Dials(catalyst_correlated={})
    res2, _ = reallocate(positions=POS, total_book_value=BOOK, run_up=RUN_UP, dials=d)
    ok("NVDA" in res2.sequence_now, "with correlation cleared, NVDA sequenced now")


if __name__ == "__main__":
    for fn in [test_weights_and_lookthrough, test_funding_pool_order, test_end_to_end_default,
               test_chase_gate, test_dial_change_changes_plan, test_optional_rail_on,
               test_no_runup_degrades, test_catalyst_correlation_dial]:
        fn()
    if FAILS:
        print("FAIL:")
        for f in FAILS:
            print("  -", f)
        raise SystemExit(1)
    print("test_reallocate_rebuild: OK (8 tests)")
