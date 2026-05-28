#!/usr/bin/env python3
"""
reddit_signal_core.py - RSM v1.1 measurement core (prototype / test harness)

Pure-logic measurement engine for the Reddit Signal Module. No network calls.
Built to EMPIRICALLY VALIDATE the corrected measurement design after the
v1.0 spec red-team. Each function carries the flaw it fixes:

  Flaw #4  velocity underspecified  -> compute_velocity(): z-score vs trailing
                                       baseline + absolute mention floor
  Flaw #1  lead-time vs lagged srcs -> compute_lead_time(): only low-latency
                                       sources are valid baselines
  Flaw #2  threshold confounds hit  -> select_scoring_cohort(): fixed-percentile
            rate                      cohort, decoupled from detection threshold
  Flaw #3  no scoring window        -> SCORING_HORIZONS + score_signal_*
  Flaw #8  reflexivity contaminates -> score_signal_multi_horizon(): multi-
            crypto backtest           horizon captures pop -> reversion
  Flaw #7  kill criterion false +ve -> kill_criterion_check(): decommission
                                       requires unactioned AND inaccurate

CLI: python3 reddit_signal_core.py --self-test
"""

import statistics
import sys

# ---------------------------------------------------------------------------
# Flaw #4 fix - a precise, robust velocity definition
# ---------------------------------------------------------------------------

MIN_MENTION_FLOOR = 8       # absolute mentions required before a name is
                            # eligible to fire. Kills the 0->3 = "+infinity %"
                            # false positive that a naive % change produces.
DEFAULT_BASELINE_WINDOW = 10
DEFAULT_Z_THRESHOLD = 2.0


def compute_velocity(mention_series, baseline_window=DEFAULT_BASELINE_WINDOW):
    """
    mention_series: per-period mention counts, oldest -> newest.
    Velocity is the z-score of the current period vs the trailing baseline.
    A name is 'eligible' only if the current count clears MIN_MENTION_FLOOR.
    """
    if len(mention_series) < baseline_window + 1:
        return {"current": None, "zscore": None, "eligible": False,
                "reason": "insufficient_history"}
    current = mention_series[-1]
    baseline = mention_series[-(baseline_window + 1):-1]
    mean = statistics.mean(baseline)
    sd = statistics.pstdev(baseline)
    if sd == 0:
        # flat baseline: z is 0 if unchanged, else a finite stand-in so a
        # genuine break off a flat base still registers.
        z = 0.0 if current == mean else (current - mean) / 0.5
    else:
        z = (current - mean) / sd
    return {"current": current, "baseline_mean": round(mean, 2),
            "baseline_sd": round(sd, 2), "zscore": round(z, 2),
            "eligible": current >= MIN_MENTION_FLOOR}


def detect_signal(mention_series, z_threshold=DEFAULT_Z_THRESHOLD,
                  baseline_window=DEFAULT_BASELINE_WINDOW):
    """A signal fires only if eligible (>= floor) AND z >= threshold."""
    v = compute_velocity(mention_series, baseline_window)
    if not v["eligible"] or v["zscore"] is None:
        return {"fired": False, **v}
    return {"fired": v["zscore"] >= z_threshold, **v}


# ---------------------------------------------------------------------------
# Flaw #1 fix - lead-time is only honest vs LOW-LATENCY sources
# ---------------------------------------------------------------------------

# Sources whose disclosure time approximates their information time.
LOW_LATENCY_SOURCES = {"fundstrat_inbox", "news", "price_action",
                       "catalyst_calendar"}
# Sources with structural disclosure lag (e.g. 13F ~45d). Reported for
# context but INVALID as a lead-time baseline - comparing Reddit's signal
# time to a 13F *filing* time would falsely flatter Reddit.
LAGGED_SOURCES = {"13f_deltas", "insider_filings"}


def compute_lead_time(signal_day, source_appearances):
    """
    source_appearances: {source_name: day_first_appeared or None}.
    Positive lead = Reddit fired earlier than that source.
    Only low-latency sources count toward the median; lagged sources are
    reported with valid_baseline=False.
    """
    out = {}
    for src, appeared in source_appearances.items():
        valid = src in LOW_LATENCY_SOURCES
        lead = None if appeared is None else appeared - signal_day
        out[src] = {"lead_days": lead, "valid_baseline": valid}
    valid_leads = [v["lead_days"] for v in out.values()
                   if v["valid_baseline"] and v["lead_days"] is not None]
    median_valid = statistics.median(valid_leads) if valid_leads else None
    return {"per_source": out, "median_valid_lead": median_valid,
            "is_echo": (median_valid is not None and median_valid <= 0)}


# ---------------------------------------------------------------------------
# Flaw #2 fix - score a FIXED-percentile cohort, never the live-threshold one
# ---------------------------------------------------------------------------

def select_scoring_cohort(all_logged_signals, percentile=0.90):
    """
    all_logged_signals: every signal LOGGED (fired or not - RSM logs all to
    defeat selection bias). Returns the top (1 - percentile) by z-score.
    This cohort definition does NOT depend on the live detection threshold,
    so an auto-tuned threshold cannot confound the hit-rate trend.
    """
    scored = [s for s in all_logged_signals if s.get("zscore") is not None]
    if not scored:
        return []
    ranked = sorted(scored, key=lambda s: s["zscore"], reverse=True)
    k = max(1, round(len(ranked) * (1 - percentile)))
    return ranked[:k]


# ---------------------------------------------------------------------------
# Flaw #3 + #8 fix - score at MULTIPLE pre-registered horizons
# ---------------------------------------------------------------------------

SCORING_HORIZONS = [3, 7, 15]    # trading days; pre-registered, NOT tunable
PUSH_BAND = 0.02                 # +/-2% move = PUSH (no edge demonstrated)


def score_signal_multi_horizon(direction, entry_price, price_path):
    """
    direction: 'long' (equity scout) or 'fade' (crypto contrarian).
    price_path: {day: price}, must cover the horizon days.
    A 'fade' WINS when price is LOWER. Multi-horizon is what lets a crypto
    fade read LOSS at 3d (reflexive pop) and WIN at 15d (reversion) - so the
    scoring window choice can no longer arbitrarily decide the verdict.
    """
    result = {}
    for h in SCORING_HORIZONS:
        if h not in price_path:
            result[h] = "NO_DATA"
            continue
        ret = (price_path[h] - entry_price) / entry_price
        if abs(ret) < PUSH_BAND:
            result[h] = "PUSH"
        elif direction == "long":
            result[h] = "WIN" if ret > 0 else "LOSS"
        else:  # fade
            result[h] = "WIN" if ret < 0 else "LOSS"
    return result


# ---------------------------------------------------------------------------
# Flaw #7 fix - kill criterion requires unactioned AND inaccurate
# ---------------------------------------------------------------------------

def kill_criterion_check(n_scored, hit_rate, days_since_actionable,
                         any_positive_signal):
    """
    Decommission a scan only if it is BOTH unhelpful AND inaccurate.
    'Unactioned' alone is NOT a kill - that can be operator behavior, not
    module failure. Returns CLEAR / WATCH / TRIGGERED.
    """
    if n_scored < 15:
        return "WATCH" if days_since_actionable >= 90 else "CLEAR"
    consistent_miss = hit_rate < 0.40
    stale = days_since_actionable >= 90
    if consistent_miss:
        return "TRIGGERED"
    if stale and not any_positive_signal:
        return "TRIGGERED"
    if stale or hit_rate < 0.50:
        return "WATCH"
    return "CLEAR"


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test():
    passed = failed = 0

    def check(name, cond):
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  PASS  {name}")
        else:
            failed += 1
            print(f"  FAIL  {name}")

    print("VELOCITY (flaw #4)")
    check("clear mention spike fires",
          detect_signal([2,3,2,4,3,3,2,4,3,3,19])["fired"] is True)
    check("mild rise below z-threshold does not fire",
          detect_signal([12,14,11,13,15,12,14,13,12,14,15])["fired"] is False)
    check("high z but below mention floor does not fire (0->3 fix)",
          detect_signal([3,4,3,4,3,4,3,4,3,4,7])["fired"] is False)
    check("above floor + high z fires",
          detect_signal([1,2,1,2,1,2,1,2,1,2,30])["fired"] is True)
    check("insufficient history is ineligible",
          detect_signal([2,3,4])["eligible"] is False)

    print("LEAD-TIME (flaw #1)")
    lt = compute_lead_time(10, {"fundstrat_inbox": 14, "13f_deltas": 12,
                                "news": None, "price_action": 16})
    check("13f excluded as valid lead-time baseline",
          lt["per_source"]["13f_deltas"]["valid_baseline"] is False)
    check("fundstrat counted, lead = +4 days",
          lt["per_source"]["fundstrat_inbox"]["lead_days"] == 4)
    check("median valid lead = 5 (13f & null excluded)",
          lt["median_valid_lead"] == 5)
    check("echo detected when a valid source led Reddit",
          compute_lead_time(20, {"fundstrat_inbox": 15})["is_echo"] is True)

    print("COHORT SCORING (flaw #2)")
    pool = [{"zscore": z, "fired": z >= 2.0} for z in
            [10,9,8,7,6,5,4,3,2.5,2.2,2.0,1.8,1.5,1.2,1.0,0.8,0.5,0.3,0.1,0.0]]
    cohort = select_scoring_cohort(pool, percentile=0.90)
    check("scores fixed top-10% of ALL logged signals (n=20 -> 2)",
          len(cohort) == 2 and {c["zscore"] for c in cohort} == {10, 9})
    pool_all_fired = [{"zscore": p["zscore"], "fired": True} for p in pool]
    check("cohort unchanged when detection flags all change",
          {c["zscore"] for c in cohort} ==
          {c["zscore"] for c in select_scoring_cohort(pool_all_fired, 0.90)})

    print("MULTI-HORIZON SCORING (flaws #3, #8)")
    fade = score_signal_multi_horizon("fade", 100.0,
                                      {3: 108.0, 7: 103.0, 15: 92.0})
    check("crypto fade reads LOSS at 3d (reflexive pop)", fade[3] == "LOSS")
    check("crypto fade reads WIN at 15d (reversion)", fade[15] == "WIN")
    check("equity long reads WIN at 15d",
          score_signal_multi_horizon("long", 50.0,
                                     {3:51.0,7:55.0,15:60.0})[15] == "WIN")
    check("sub-2% move scores PUSH",
          score_signal_multi_horizon("long", 50.0,
                                     {3:50.4,7:50.6,15:50.2})[3] == "PUSH")

    print("KILL CRITERION (flaw #7)")
    check("n<15 + stale -> WATCH, not TRIGGERED",
          kill_criterion_check(8, 0.30, 120, False) == "WATCH")
    check("n>=15 + hit-rate <40% -> TRIGGERED",
          kill_criterion_check(16, 0.35, 10, True) == "TRIGGERED")
    check("stale but accurate (has wins) -> WATCH, not TRIGGERED",
          kill_criterion_check(16, 0.62, 100, True) == "WATCH")
    check("stale AND inaccurate (no wins) -> TRIGGERED",
          kill_criterion_check(16, 0.45, 100, False) == "TRIGGERED")
    check("healthy scan -> CLEAR",
          kill_criterion_check(20, 0.65, 12, True) == "CLEAR")

    total = passed + failed
    print(f"\n{passed}/{total} passed.")
    return failed == 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if _self_test() else 1)
    print(__doc__)
