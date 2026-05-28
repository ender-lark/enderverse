#!/usr/bin/env python3
"""
v0_score.py — v0 confidence scorer for the UW Asymmetric Discovery Engine.

Investing 2026 framework  ·  v0 build, Part 2 step 3  ·  pure-logic, deterministic.

WHY THIS EXISTS
---------------
v0 discovery scans market-wide SEC Form 4 open-market buys and keeps only
genuine insider CLUSTERS (2+ distinct insiders, real size, routine 10b5-1 /
grant / option-exercise noise stripped — insider_activity_scan.py does that
filtering). This module takes each surviving cluster and assigns it a lane
and a 3-band confidence score.

The score exists to answer v0 question #1: does a confidence score actually
sort — do higher-scored setups outperform lower-scored ones? Every threshold
below is a PROVISIONAL starting point, flagged for recalibration once the
🧪 v0 Calibration Log has trade density.

THE SCORE — three inputs, summed into a raw number, sorted into three bands
-----------------------------------------------------------------------------
  Cluster strength    2 insiders=1 · 3=2 · 4+=3 ; +1 if a CEO/CFO/Chair buys.
                      Range 1-4.  (Dollar size is the discovery filter, not a
                      score input — strength is breadth + seniority.)
  Buy-into-strength   stock up >10% on the month into the cluster = 2,
                      else (flat or down) = 1.  Range 1-2.  Binary by design
                      — insider dip-buying is a real signal too, just not the
                      strongest variant; raw run-up % is logged regardless.
  Catalyst proximity  catalyst <=14d = 2 · 15-45d = 1 · none/>45d = 0.
                      Range 0-2.

  Raw score = sum, range 2-8.
  Bands:  High 6-8  ·  Moderate 4-5  ·  Watch 2-3.

LANE is mechanical: a catalyst within 14 days -> Fast lane; everything else
-> Multi-week. Only a minority of clusters sit right before an event, which
is why the Fast lane stays naturally small.

OUTPUT KEY  ->  🧪 v0 Calibration Log FIELD
-------------------------------------------
  lane        ->  Lane
  score_raw   ->  Score Raw
  score_band  ->  Score Band
( inputs insider_count / top_exec / run_up_pct / days_to_catalyst map to the
  same-named Calibration Log fields. )

CLI
---
  python v0_score.py --self-test
  python v0_score.py --candidates candidates.json

candidates.json : [{"ticker":"X","insider_count":4,"top_exec":true,
                    "run_up_pct":18.0,"days_to_catalyst":9}, ...]
"""

import argparse
import json
import sys

# ---- Provisional thresholds — retune at the 6/28 retrospective -------------
RUN_UP_THRESHOLD = 10.0        # % monthly run-up earning the buy-into-strength bonus
FAST_LANE_DAYS = 14            # catalyst within N days -> Fast lane + 2 catalyst pts
MID_CATALYST_DAYS = 45         # catalyst within N days -> 1 catalyst pt
BAND_HIGH_MIN = 6              # raw score >= this -> High
BAND_MODERATE_MIN = 4          # raw score >= this -> Moderate ; below -> Watch
# ---------------------------------------------------------------------------


def cluster_strength(insider_count, top_exec):
    """Breadth + seniority points. Range 1-4."""
    if insider_count <= 2:
        base = 1
    elif insider_count == 3:
        base = 2
    else:
        base = 3
    return base + (1 if top_exec else 0)


def buy_into_strength(run_up_pct):
    """Buying into a rising stock scores higher. Range 1-2."""
    if run_up_pct is not None and run_up_pct > RUN_UP_THRESHOLD:
        return 2
    return 1


def catalyst_points(days_to_catalyst):
    """Near-term catalyst proximity. Range 0-2."""
    if days_to_catalyst is None:
        return 0
    if days_to_catalyst <= FAST_LANE_DAYS:
        return 2
    if days_to_catalyst <= MID_CATALYST_DAYS:
        return 1
    return 0


def lane_of(days_to_catalyst):
    """Fast if a catalyst is within FAST_LANE_DAYS, else Multi-week."""
    if days_to_catalyst is not None and days_to_catalyst <= FAST_LANE_DAYS:
        return "Fast"
    return "Multi-week"


def band_of(raw_score):
    """Sort a raw score into one of the three bands."""
    if raw_score >= BAND_HIGH_MIN:
        return "High"
    if raw_score >= BAND_MODERATE_MIN:
        return "Moderate"
    return "Watch"


def score_candidate(candidate):
    """Score one insider-cluster candidate. Degrades gracefully on partial
    data — a missing field produces a flag, never a crash."""
    flags = []
    count = candidate.get("insider_count")
    top = bool(candidate.get("top_exec"))
    run_up = candidate.get("run_up_pct")
    dtc = candidate.get("days_to_catalyst")

    if count is None:
        flags.append("insider_count_missing")
        count = 2  # minimum cluster, so a score still computes
    elif count < 2:
        flags.append("below_cluster_threshold")

    if run_up is None:
        flags.append("run_up_missing")

    if dtc is not None and dtc < 0:
        flags.append("catalyst_in_past")
        dtc = None  # a past event is not a forward catalyst

    strength = cluster_strength(count, top)
    buy = buy_into_strength(run_up)
    cat = catalyst_points(dtc)
    raw = strength + buy + cat

    return {
        "ticker": candidate.get("ticker"),
        "lane": lane_of(dtc),
        "score_raw": raw,
        "score_band": band_of(raw),
        "components": {
            "cluster_strength": strength,
            "buy_into_strength": buy,
            "catalyst_proximity": cat,
        },
        "flags": flags,
    }


def score_batch(candidates):
    """Score a list of candidates, returned sorted by raw score descending."""
    scored = [score_candidate(c) for c in candidates]
    return sorted(scored, key=lambda r: r["score_raw"], reverse=True)


def _self_test():
    passed = failed = 0

    def check(name, cond):
        nonlocal passed, failed
        if cond:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {name}")

    # 1. worked example 1 — 4 insiders + CEO, +18%, earnings in 9d -> 8 High Fast
    r = score_candidate({"ticker": "AAA", "insider_count": 4, "top_exec": True,
                         "run_up_pct": 18.0, "days_to_catalyst": 9})
    check("ex1 raw 8", r["score_raw"] == 8)
    check("ex1 High", r["score_band"] == "High")
    check("ex1 Fast", r["lane"] == "Fast")

    # 2. worked example 2 — 2 insiders, no exec, flat, no catalyst -> 2 Watch MW
    r = score_candidate({"ticker": "BBB", "insider_count": 2, "top_exec": False,
                         "run_up_pct": 0.0, "days_to_catalyst": None})
    check("ex2 raw 2", r["score_raw"] == 2)
    check("ex2 Watch", r["score_band"] == "Watch")
    check("ex2 Multi-week", r["lane"] == "Multi-week")

    # 3. Moderate — 3 insiders, no exec, +5%, catalyst 30d -> 2+1+1 = 4
    r = score_candidate({"ticker": "CCC", "insider_count": 3, "top_exec": False,
                         "run_up_pct": 5.0, "days_to_catalyst": 30})
    check("mod raw 4", r["score_raw"] == 4)
    check("mod Moderate", r["score_band"] == "Moderate")
    check("mod Multi-week (30d)", r["lane"] == "Multi-week")

    # 4. dip-buy is NOT penalized to zero — 4 insiders, -15% run-up, no catalyst
    r = score_candidate({"ticker": "DDD", "insider_count": 4, "top_exec": False,
                         "run_up_pct": -15.0, "days_to_catalyst": None})
    check("dip-buy buy_into_strength == 1", r["components"]["buy_into_strength"] == 1)
    check("dip-buy raw 4 (3+1+0)", r["score_raw"] == 4)

    # 5. catalyst boundaries
    check("14d -> Fast", lane_of(14) == "Fast")
    check("15d -> Multi-week", lane_of(15) == "Multi-week")
    check("14d -> 2 catalyst pts", catalyst_points(14) == 2)
    check("15d -> 1 catalyst pt", catalyst_points(15) == 1)
    check("45d -> 1 catalyst pt", catalyst_points(45) == 1)
    check("46d -> 0 catalyst pts", catalyst_points(46) == 0)

    # 6. band boundaries
    check("raw 6 -> High", band_of(6) == "High")
    check("raw 5 -> Moderate", band_of(5) == "Moderate")
    check("raw 4 -> Moderate", band_of(4) == "Moderate")
    check("raw 3 -> Watch", band_of(3) == "Watch")

    # 7. partial-data flags
    r = score_candidate({"ticker": "EEE", "top_exec": False, "days_to_catalyst": None})
    check("missing insider_count flagged", "insider_count_missing" in r["flags"])
    check("missing run_up flagged", "run_up_missing" in r["flags"])
    r = score_candidate({"ticker": "FFF", "insider_count": 1, "top_exec": False,
                         "run_up_pct": 3.0, "days_to_catalyst": None})
    check("below-cluster flagged", "below_cluster_threshold" in r["flags"])
    r = score_candidate({"ticker": "GGG", "insider_count": 3, "top_exec": False,
                         "run_up_pct": 3.0, "days_to_catalyst": -3})
    check("catalyst_in_past flagged", "catalyst_in_past" in r["flags"])
    check("past catalyst -> Multi-week", r["lane"] == "Multi-week")

    # 8. batch sorts descending by raw score
    batch = score_batch([
        {"ticker": "LOW", "insider_count": 2, "top_exec": False,
         "run_up_pct": 0.0, "days_to_catalyst": None},
        {"ticker": "HIGH", "insider_count": 4, "top_exec": True,
         "run_up_pct": 18.0, "days_to_catalyst": 9},
    ])
    check("batch sorted desc", [b["ticker"] for b in batch] == ["HIGH", "LOW"])

    print(f"\nv0_score self-test: {passed} passed, {failed} failed")
    return failed == 0


def main():
    ap = argparse.ArgumentParser(description="v0 confidence scorer (v0 Part 2 step 3)")
    ap.add_argument("--self-test", action="store_true", help="run the self-test suite")
    ap.add_argument("--candidates", help="path to candidate cluster JSON (a list)")
    args = ap.parse_args()

    if args.self_test:
        sys.exit(0 if _self_test() else 1)

    if args.candidates:
        with open(args.candidates) as fh:
            candidates = json.load(fh)
        print(json.dumps(score_batch(candidates), indent=2))
        return

    ap.print_help()


if __name__ == "__main__":
    main()
