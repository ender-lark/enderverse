#!/usr/bin/env python3
"""
Tests for thesis_strengthening_backtest.py — validates classification logic
and forward-return math with deterministic synthetic fixtures.
"""

import sys
sys.path.insert(0, '/home/claude/v11_9_update')

import thesis_strengthening_backtest as tsb

print("=" * 80)
print("THESIS-STRENGTHENING BACKTEST TEST SUITE")
print("=" * 80)

passes = 0
fails = 0


def assert_eq(name, got, expected):
    global passes, fails
    if got == expected:
        passes += 1
        print(f"  PASS  {name}")
    else:
        fails += 1
        print(f"  FAIL  {name}")
        print(f"        expected: {expected!r}")
        print(f"        got:      {got!r}")


def assert_close(name, got, expected, tol=0.01):
    global passes, fails
    if abs(got - expected) <= tol:
        passes += 1
        print(f"  PASS  {name} ({got:.4f})")
    else:
        fails += 1
        print(f"  FAIL  {name}: expected {expected:.4f}, got {got:.4f}")


def assert_true(name, cond, hint=""):
    global passes, fails
    if cond:
        passes += 1
        print(f"  PASS  {name}")
    else:
        fails += 1
        print(f"  FAIL  {name}  {hint}")


# =============================================================================
# Forward return calculation
# =============================================================================
print("\n--- compute_fwd_return_pct ---")

assert_close("100 -> 110 = +10%", tsb.compute_fwd_return_pct(100, 110), 10.0)
assert_close("100 -> 90 = -10%", tsb.compute_fwd_return_pct(100, 90), -10.0)
assert_close("50 -> 75 = +50%", tsb.compute_fwd_return_pct(50, 75), 50.0)
assert_close("0 -> 100 = 0% (div by zero guard)",
             tsb.compute_fwd_return_pct(0, 100), 0.0)
assert_close("100 -> 100 = 0%", tsb.compute_fwd_return_pct(100, 100), 0.0)


# =============================================================================
# step_6_would_fire
# =============================================================================
print("\n--- step_6_would_fire ---")


def mk_event(event_type, pre=100, fwd_60d=110, spy_pre=600, spy_60d=620):
    return tsb.HistoricalEvent(
        ticker="TEST",
        event_date="2025-01-01",
        event_type=event_type,
        description="test",
        pre_event_price=pre,
        forward_prices={"5d": pre, "30d": pre, "60d": fwd_60d, "90d": fwd_60d},
        spy_pre_event=spy_pre,
        spy_forward={"5d": spy_pre, "30d": spy_pre, "60d": spy_60d, "90d": spy_60d},
    )


assert_true("fires on CAT2_ANCHOR_ADDITION",
            tsb.step_6_would_fire(mk_event("CAT2_ANCHOR_ADDITION")))
assert_true("fires on NAMED_SOURCE_ADDITION",
            tsb.step_6_would_fire(mk_event("NAMED_SOURCE_ADDITION")))
assert_true("fires on EARNINGS_BEAT_RAISED_GUIDE",
            tsb.step_6_would_fire(mk_event("EARNINGS_BEAT_RAISED_GUIDE")))
assert_true("fires on EARNINGS_BEAT_NEW_ANCHOR",
            tsb.step_6_would_fire(mk_event("EARNINGS_BEAT_NEW_ANCHOR")))
assert_eq("no fire on NON_EVENT_CONTROL",
          tsb.step_6_would_fire(mk_event("NON_EVENT_CONTROL")), False)


# =============================================================================
# in_scope_for_step_6 property
# =============================================================================
print("\n--- in_scope_for_step_6 property ---")

assert_true("CAT2 in scope",
            mk_event("CAT2_ANCHOR_ADDITION").in_scope_for_step_6)
assert_true("NAMED_SOURCE in scope",
            mk_event("NAMED_SOURCE_ADDITION").in_scope_for_step_6)
assert_eq("NON_EVENT_CONTROL out of scope",
          mk_event("NON_EVENT_CONTROL").in_scope_for_step_6, False)


# =============================================================================
# classify_event — confusion-matrix labels
# =============================================================================
print("\n--- classify_event confusion matrix ---")

# TP: fires + beats benchmark
# ticker +20% / SPY +3% = excess +17pp > 5pp threshold
tp_event = mk_event("CAT2_ANCHOR_ADDITION", pre=100, fwd_60d=120,
                    spy_pre=600, spy_60d=618)
tp_result = tsb.classify_event(tp_event)
assert_eq("TP classification", tp_result.classification, "TP")
assert_close("TP fwd return", tp_result.fwd_return_60d_pct, 20.0)
assert_close("TP spy return", tp_result.spy_return_60d_pct, 3.0)
assert_close("TP excess", tp_result.excess_return_60d_pct, 17.0)

# FP: fires + does not beat benchmark
# ticker -5% / SPY +10% = excess -15pp
fp_event = mk_event("EARNINGS_BEAT_RAISED_GUIDE", pre=100, fwd_60d=95,
                    spy_pre=600, spy_60d=660)
fp_result = tsb.classify_event(fp_event)
assert_eq("FP classification", fp_result.classification, "FP")

# FN: doesn't fire + beats benchmark
# ticker +30% / SPY +5% = excess +25pp
fn_event = mk_event("NON_EVENT_CONTROL", pre=100, fwd_60d=130,
                    spy_pre=600, spy_60d=630)
fn_result = tsb.classify_event(fn_event)
assert_eq("FN classification", fn_result.classification, "FN")
assert_eq("FN didn't fire", fn_result.step_6_fired, False)

# TN: doesn't fire + doesn't beat benchmark
# ticker +3% / SPY +5% = excess -2pp
tn_event = mk_event("NON_EVENT_CONTROL", pre=100, fwd_60d=103,
                    spy_pre=600, spy_60d=630)
tn_result = tsb.classify_event(tn_event)
assert_eq("TN classification", tn_result.classification, "TN")


# =============================================================================
# build_calibration_report — in-scope filtering
# =============================================================================
print("\n--- build_calibration_report in-scope filtering ---")

# Build a mixed set: 3 in-scope (2 TP + 1 FP) + 2 out-of-scope (1 winner + 1 dud)
events = [
    mk_event("CAT2_ANCHOR_ADDITION", pre=100, fwd_60d=130, spy_pre=600, spy_60d=618),  # TP
    mk_event("NAMED_SOURCE_ADDITION", pre=100, fwd_60d=140, spy_pre=600, spy_60d=618),  # TP
    mk_event("EARNINGS_BEAT_RAISED_GUIDE", pre=100, fwd_60d=98, spy_pre=600, spy_60d=618),  # FP
    mk_event("NON_EVENT_CONTROL", pre=100, fwd_60d=120, spy_pre=600, spy_60d=618),  # OOS winner
    mk_event("NON_EVENT_CONTROL", pre=100, fwd_60d=100, spy_pre=600, spy_60d=618),  # OOS dud
]

report = tsb.build_calibration_report(events)

assert_eq("n_events counts in-scope only", report.n_events, 3)
assert_eq("3 in-scope all fired", report.n_fired, 3)
assert_eq("TP count", report.true_positives, 2)
assert_eq("FP count", report.false_positives, 1)
assert_eq("FN count", report.false_negatives, 0)
assert_eq("TN count", report.true_negatives, 0)
assert_close("precision = 2/3 * 100", report.precision_pct, 66.67, tol=0.1)
assert_close("recall = 2/2 * 100", report.recall_pct, 100.0)

# Verify by_event_type includes ALL events (including OOS)
assert_true("by_event_type has NON_EVENT_CONTROL",
            "NON_EVENT_CONTROL" in report.by_event_type)
assert_eq("NON_EVENT_CONTROL n=2",
          report.by_event_type["NON_EVENT_CONTROL"]["n"], 2)
assert_eq("NON_EVENT_CONTROL didn't fire",
          report.by_event_type["NON_EVENT_CONTROL"]["n_fired"], 0)


# =============================================================================
# Edge cases
# =============================================================================
print("\n--- Edge cases ---")

# All events are FP
all_fp = [
    mk_event("CAT2_ANCHOR_ADDITION", pre=100, fwd_60d=95, spy_pre=600, spy_60d=620),
    mk_event("NAMED_SOURCE_ADDITION", pre=100, fwd_60d=90, spy_pre=600, spy_60d=620),
]
fp_report = tsb.build_calibration_report(all_fp)
assert_close("all-FP precision = 0%", fp_report.precision_pct, 0.0)
assert_true("rejection in recommendation",
            "REJECT" in fp_report.threshold_recommendation
            or "DEFER" in fp_report.threshold_recommendation)

# Threshold exactly at 5pp boundary (should not beat)
boundary = mk_event("CAT2_ANCHOR_ADDITION", pre=100, fwd_60d=110, spy_pre=600, spy_60d=630)
boundary_result = tsb.classify_event(boundary)
# ticker +10% - SPY +5% = excess +5pp (NOT > 5pp threshold; should be FP)
assert_close("boundary excess = 5pp", boundary_result.excess_return_60d_pct, 5.0)
assert_eq("boundary at 5pp = FP (NOT > 5)", boundary_result.classification, "FP")

# Just over threshold
over = mk_event("CAT2_ANCHOR_ADDITION", pre=100, fwd_60d=111, spy_pre=600, spy_60d=630)
over_result = tsb.classify_event(over)
# excess = 6pp > 5pp threshold; should be TP
assert_eq("just-over boundary = TP", over_result.classification, "TP")


# =============================================================================
# Embedded fixtures sanity
# =============================================================================
print("\n--- Embedded fixtures sanity ---")

assert_true("embedded events list non-empty",
            len(tsb.EMBEDDED_EVENTS) > 0)
assert_true("includes NBIS Sep 2025 event",
            any(e.ticker == "NBIS" and e.event_date == "2025-09-08"
                for e in tsb.EMBEDDED_EVENTS))
assert_true("includes NBIS Lee GRNJ Nov 2025",
            any(e.ticker == "NBIS" and e.event_date == "2025-11-18"
                for e in tsb.EMBEDDED_EVENTS))
assert_true("includes NBIS Q1 2026 print",
            any(e.ticker == "NBIS" and e.event_date == "2026-05-13"
                for e in tsb.EMBEDDED_EVENTS))

# Run on embedded — must produce GRADUATE recommendation (current state of fixtures)
embedded_report = tsb.build_calibration_report(tsb.EMBEDDED_EVENTS)
assert_true("embedded fixtures hit precision >= 80%",
            embedded_report.precision_pct >= 80.0,
            f"got {embedded_report.precision_pct}")
assert_true("embedded fixtures hit recall >= 70%",
            embedded_report.recall_pct >= 70.0,
            f"got {embedded_report.recall_pct}")


# =============================================================================
# JSON output round-trip
# =============================================================================
print("\n--- JSON serialization ---")

import json
js = tsb.format_json(embedded_report)
parsed = json.loads(js)
assert_true("json contains classifications",
            "classifications" in parsed)
assert_true("json contains recommendation",
            "threshold_recommendation" in parsed)
assert_true("json precision matches",
            parsed["precision_pct"] == round(embedded_report.precision_pct, 2))


print("\n" + "=" * 80)
print(f"RESULT: {passes}/{passes + fails} tests passed")
print("=" * 80)

if fails > 0:
    sys.exit(1)
