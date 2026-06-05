"""Tests for SOURCE PERSISTENCE wired into the orchestrator subsystem stack (v12.5, Issue #10),
with the calibration-staleness guard. persistence_scan itself is tested in source_call_tracker;
here we test the WIRING + the guard (LOUD -> PROVISIONAL when calibration isn't confirmed fresh)
+ the core-quiet / MONITOR-loud escalation convention."""

from datetime import date, timedelta
from session_orchestrator import _run_persistence, orchestrate

TODAY = date.today()
D = [(TODAY - timedelta(days=n)).isoformat() for n in (14, 7, 2)]  # all within the 30d window

THESES = [
    {"ticker": "NVDA", "tier": "T2", "stance": "CORE", "factor_tags": []},      # core -> quiet
    {"ticker": "BMNR", "tier": "T1", "stance": "MONITOR", "factor_tags": ["crypto"]},  # monitor -> loud-eligible
]


def _calls(tickers=("HYPE", "NVDA", "BMNR"), n=3):
    rows = []
    for tkr in tickers:
        for d in D[:n]:
            rows.append({"source": "farrell", "ticker": tkr, "date": d, "tier": "C"})
    return rows


def test_no_source_calls_unavailable():
    r = _run_persistence(None, THESES, calibration_fresh=True)
    assert r.available is False and "no source calls" in r.surface_line


def test_fresh_calibration_lets_loud_fire():
    r = _run_persistence(_calls(), THESES, calibration_fresh=True, now=TODAY.isoformat())
    assert r.priority == "HIGH"
    assert r.payload["loud"] == 2          # HYPE + BMNR (NVDA is core-quiet)
    assert r.payload["guarded"] is False
    assert "P-WAKE-UP" in r.surface_line


def test_stale_calibration_downgrades_loud_to_provisional():
    r = _run_persistence(_calls(), THESES, calibration_fresh=False, now=TODAY.isoformat())
    assert r.priority == "MED"             # surfaced, not auto-firing
    assert r.payload["loud"] == 0
    assert r.payload["provisional"] == 2
    assert r.payload["guarded"] is True
    assert "PROVISIONAL" in r.surface_line
    assert "P-WAKE-UP" not in r.surface_line


def test_core_name_is_quiet_monitor_name_is_loud():
    r = _run_persistence(_calls(), THESES, calibration_fresh=True, now=TODAY.isoformat())
    # exactly the two non-core names fire loud; NVDA (core) never does
    assert r.payload["loud"] == 2


def test_single_mention_does_not_fire():
    r = _run_persistence(_calls(n=1), THESES, calibration_fresh=True, now=TODAY.isoformat())
    assert "none firing" in r.surface_line


def test_orchestrator_runs_ten_subsystems_and_guards_by_default():
    d = orchestrate(positions=[], theses=THESES, sleeve_total=1_000_000,
                    source_calls=_calls())
    assert len(d.subsystems) == 10
    p = next(s for s in d.subsystems if s.name == "SOURCE PERSISTENCE")
    # no live Inbox/Log supplied -> calibration not confirmed -> guarded/provisional
    assert p.payload["guarded"] is True
    assert p.payload["loud"] == 0


def test_orchestrator_with_fresh_live_dates_lets_loud_fire():
    d = orchestrate(positions=[], theses=THESES, sleeve_total=1_000_000,
                    source_calls=_calls(), inbox_call_dates=D, log_call_dates=D)
    p = next(s for s in d.subsystems if s.name == "SOURCE PERSISTENCE")
    assert p.payload["guarded"] is False
    assert p.payload["loud"] == 2
    assert p.priority == "HIGH"
