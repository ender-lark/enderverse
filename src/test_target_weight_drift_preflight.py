"""Target-weight drift wiring for session preflight."""

from position_drift_check import (
    target_baselines_from_reallocate_model,
    target_weight_drift,
)
from session_orchestrator import _run_target_drift, orchestrate


BOOK = 1_000_000


def _pos(ticker, pct):
    return {"ticker": ticker, "market_value": pct / 100.0 * BOOK}


def test_reallocate_model_targets_become_drift_baselines():
    baselines = {b.ticker: b for b in target_baselines_from_reallocate_model()}
    assert baselines["NVDA"].baseline_pct == 0.12
    assert baselines["GOOGL"].baseline_pct == 0.08
    assert "reallocate_config" in baselines["NVDA"].source_text


def test_target_weight_drift_flags_undersized_and_missing_targets():
    positions = {
        "sleeve_value": BOOK,
        "positions": [
            _pos("NVDA", 6.0),
            _pos("GOOGL", 1.0),
            _pos("SMH", 8.0),
        ],
    }
    drift, unmatched, _untracked = target_weight_drift(positions, BOOK)
    by_ticker = {d.ticker: d for d in drift}

    assert by_ticker["NVDA"].direction == "UNDERSIZED"
    assert by_ticker["GOOGL"].direction == "UNDERSIZED"
    assert any(b.ticker == "AVGO" for b in unmatched)


def test_target_drift_subsystem_surfaces_in_priority_order():
    positions = [
        _pos("NVDA", 6.0),
        _pos("GOOGL", 1.0),
        _pos("SMH", 8.0),
    ]
    result = _run_target_drift(positions, BOOK)

    assert result.available is True
    assert result.priority == "HIGH"
    assert result.actionable_count > 0
    assert "TARGET DRIFT" in result.surface_line
    assert "NVDA undersized" in result.surface_line


def test_orchestrator_runs_target_drift_subsystem():
    positions = [
        _pos("NVDA", 6.0),
        _pos("GOOGL", 1.0),
        _pos("SMH", 8.0),
    ]
    dashboard = orchestrate(positions=positions, theses=[], sleeve_total=BOOK)
    names = [s.name for s in dashboard.subsystems]

    assert len(dashboard.subsystems) == 10
    assert "TARGET DRIFT" in names
    assert "TARGET DRIFT" in dashboard.priority_order
