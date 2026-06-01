import conviction_sizing_calibrator as csc

def run():
    sleeve = 1_000_000.0
    positions = [
        {"ticker": "BMNR", "market_value": 35_000},  # T1 3.5% << 8% floor
        {"ticker": "NVDA", "market_value": 25_000},  # T2 2.5% < 4% floor, NON-monitor
    ]
    theses = [
        {"ticker": "BMNR", "tier": "T1", "stance": "MONITOR", "factor_tags": ["crypto"]},
        {"ticker": "NVDA", "tier": "T2", "factor_tags": ["ai_complex"]},
    ]
    r = csc.calibrate(positions, theses, sleeve)
    mon   = [g.ticker for g in r.monitor_suppressed]
    crit  = [g.ticker for g in r.critically_below]
    below = [g.ticker for g in r.below_floor]
    assert "BMNR" in mon, f"BMNR must be MONITOR-suppressed, got {mon}"
    assert "BMNR" not in crit and "BMNR" not in below, "MONITOR name leaked into gap buckets"
    assert "NVDA" in (crit + below), f"non-MONITOR below-floor must still flag, crit={crit} below={below}"
    nvda_gap = next(g for g in (r.critically_below + r.below_floor) if g.ticker == "NVDA").gap_to_floor_value
    assert abs(r.gap_to_close_total - nvda_gap) < 1.0, \
        f"gap total {r.gap_to_close_total} should equal NVDA gap {nvda_gap} only (BMNR suppressed)"
    print("test_conviction_sizing_calibrator: PASS — MONITOR suppressed, non-MONITOR still flagged")

if __name__ == "__main__":
    run()
