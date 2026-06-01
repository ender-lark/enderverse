"""
test_macro_freshness.py — v12.0 macro session-open refresh.

Covers the consumer-side staleness guard (session_orchestrator.macro_freshness +
_run_macro) and the producer-side cache writer (macro_pulse_scan.build_macro_state).
First pytest coverage for either module — both previously had only internal
--self-test entrypoints.
"""

# macro_pulse_scan is imported FIRST: importing session_orchestrator runs a
# module-level sys.path.insert(0, "/mnt/project") for the live environment, which in
# a dual-checkout sandbox (repo clone + project snapshot both present) can otherwise
# shadow the repo copy with a stale one. Binding mp first caches it in sys.modules.
import macro_pulse_scan as mp
import session_orchestrator as so


# ---------- freshness helper ----------

def test_freshness_same_trading_day_is_fresh():
    r = so.macro_freshness("2026-05-29", today="2026-05-29")   # Fri / Fri
    assert r["fresh"] is True
    assert r["age_days"] == 0


def test_freshness_prior_day_is_stale():
    r = so.macro_freshness("2026-05-19", today="2026-05-29")
    assert r["fresh"] is False
    assert r["age_days"] == 10
    assert "STALE 10d" in r["label"]


def test_freshness_missing_snapshot_date_is_stale():
    r = so.macro_freshness(None, today="2026-05-29")
    assert r["fresh"] is False
    assert "no snapshot_date" in r["label"]


def test_freshness_weekend_accepts_friday():
    # Saturday 5/30 reading Friday 5/29's macro is fresh
    assert so.macro_freshness("2026-05-29", today="2026-05-30")["fresh"] is True
    # Sunday 5/31 too
    assert so.macro_freshness("2026-05-29", today="2026-05-31")["fresh"] is True


def test_freshness_monday_wants_monday():
    # Strict same-trading-day: Monday 6/1 reading Friday 5/29 is stale
    assert so.macro_freshness("2026-05-29", today="2026-06-01")["fresh"] is False


# ---------- _run_macro surfacing ----------

def test_run_macro_stale_marks_surface_and_elevates_priority():
    macro = {"regime_label": "duration_WEAK", "alerts": [],
             "snapshot_date": "2026-05-19"}
    res = so._run_macro(macro, today="2026-05-29")
    assert "STALE" in res.surface_line
    assert res.priority == "HIGH"            # stale forces visibility even with 0 alerts
    assert res.actionable_count >= 1
    assert res.payload["freshness"]["fresh"] is False


def test_run_macro_fresh_no_alerts_is_quiet():
    macro = {"regime_label": "duration_WEAK", "alerts": [],
             "snapshot_date": "2026-05-29"}
    res = so._run_macro(macro, today="2026-05-29")
    assert "STALE" not in res.surface_line
    assert res.priority == "INFO"
    assert res.actionable_count == 0


def test_run_macro_no_cache_unavailable():
    res = so._run_macro(None, today="2026-05-29")
    assert res.available is False


# ---------- build_macro_state writer ----------

def _sample_curve_cross():
    curve = mp.YieldCurveSnapshot(
        date="2026-05-29",
        yields={"2y": 4.00, "10y": 4.50, "30y": 5.00},
    )
    cross = mp.CrossAssetSnapshot(
        tlt_price=83.0, ief_price=93.0, lqd_price=107.0, hyg_price=79.0,
        uup_price=27.0, vix_level=18.0, gld_price=417.0, uso_price=148.0,
        move_index=95.0,
    )
    return curve, cross


def test_build_macro_state_schema_and_snapshot_date():
    curve, cross = _sample_curve_cross()
    regime = mp.assemble_regime(curve, cross)
    alerts = mp.check_alerts(curve, cross)
    state = mp.build_macro_state(curve, cross, regime, alerts)

    # snapshot_date is the yield-curve date (what the freshness guard reads)
    assert state["snapshot_date"] == "2026-05-29"
    for key in ("regime_label", "duration_state", "credit_state", "dollar_state",
                "vol_state", "inflation_state", "indicators", "alerts",
                "implications", "generated_at"):
        assert key in state, f"missing key: {key}"
    assert state["indicators"]["yield_10y"] == 4.50
    assert state["indicators"]["spread_2s10s"] == 0.50
    assert isinstance(state["alerts"], list)


def test_build_macro_state_roundtrips_into_freshness_guard():
    # The writer's output, read back, should be judged FRESH on its own date.
    curve, cross = _sample_curve_cross()
    state = mp.build_macro_state(curve, cross,
                                 mp.assemble_regime(curve, cross),
                                 mp.check_alerts(curve, cross))
    res = so._run_macro(state, today="2026-05-29")
    assert "STALE" not in res.surface_line
