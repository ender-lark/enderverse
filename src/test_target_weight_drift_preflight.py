"""Target-weight drift wiring for session preflight."""

import pytest

from position_drift_check import (
    load_actuals_from_positions_cache,
    target_baselines_from_reallocate_model,
    target_weight_drift,
    target_weight_drift_summary,
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


def test_full_book_account_positions_classifies_untracked_held_name_as_undersized():
    account_positions = {
        "sleeve_value": BOOK,
        "account_positions": [
            {**_pos("GOOGL", 2.00), "account": "Taxable", "tracked": False},
            {**_pos("GOOGL", 1.76), "account": "Roth", "tracked": False},
            {**_pos("NVDA", 12.00), "account": "Taxable", "tracked": True},
        ],
    }

    drift, unmatched, _untracked = target_weight_drift(account_positions, BOOK)
    by_ticker = {d.ticker: d for d in drift}

    assert by_ticker["GOOGL"].direction == "UNDERSIZED"
    assert by_ticker["GOOGL"].actual_pct == pytest.approx(0.0376)
    assert all(b.ticker != "GOOGL" for b in unmatched)


def test_true_zero_target_uses_honest_zero_held_wording():
    account_positions = {
        "sleeve_value": BOOK,
        "account_positions": [
            {**_pos("GOOGL", 3.76), "account": "Taxable", "tracked": False},
            {**_pos("NVDA", 12.00), "account": "Taxable", "tracked": True},
        ],
    }

    summary = target_weight_drift_summary(account_positions, BOOK, limit=20)
    by_ticker = {row["ticker"]: row for row in summary["rows"]}

    assert by_ticker["GOOGL"]["direction"] == "UNDERSIZED"
    assert by_ticker["VRT"]["direction"] == "MISSING"
    assert "GOOGL undersized 3.8% vs 8.0%" in summary["line"]
    assert "VRT 0.0% held vs 2.0% target" in summary["line"]
    assert "VRT missing vs 2.0% target" not in summary["line"]


def test_target_weight_drift_summary_is_feed_ready():
    positions = {
        "sleeve_value": BOOK,
        "positions": [
            _pos("NVDA", 6.0),
            _pos("GOOGL", 1.0),
            _pos("SMH", 8.0),
        ],
    }
    summary = target_weight_drift_summary(positions, BOOK)

    assert summary["status"] == "has_data"
    assert summary["actionable_count"] > 0
    assert summary["undersized_count"] >= 2
    assert summary["missing_count"] > 0
    assert "Target drift:" in summary["line"]
    assert {r["ticker"] for r in summary["rows"]} >= {"NVDA", "GOOGL"}


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


def test_account_positions_shape_reads_full_combined_book_not_tracked_only():
    # Exact shape of the real account_positions.json: `combined_positions` (the FULL book,
    # including untracked GOOGL/AVGO/MSFT) co-exists with `tracked_combined_positions` (which
    # OMITS them). The drift read MUST measure the full combined book so held-but-untracked
    # names show their real weight and never fall into the MISSING/0% bucket. This is the exact
    # regression behind the 2026-06-25 stale-feed report (GOOGL/AVGO/MSFT shown MISSING@0%).
    account_positions = {
        "snapshot_date": "2026-06-24",
        "sleeve_value": BOOK,
        "combined_positions": [
            {"ticker": "NVDA", "market_value": 0.12 * BOOK, "tracked": True},
            {"ticker": "GOOGL", "market_value": 0.0376 * BOOK, "tracked": False},
            {"ticker": "AVGO", "market_value": 0.0212 * BOOK, "tracked": False},
            {"ticker": "MSFT", "market_value": 0.0155 * BOOK, "tracked": False},
        ],
        "tracked_combined_positions": [
            {"ticker": "NVDA", "market_value": 0.12 * BOOK, "tracked": True},
        ],
        "account_positions": [
            {"ticker": "NVDA", "market_value": 0.12 * BOOK, "account": "A", "tracked": True},
            {"ticker": "GOOGL", "market_value": 0.0376 * BOOK, "account": "B", "tracked": False},
        ],
    }
    actuals = {a.ticker: a for a in load_actuals_from_positions_cache(account_positions)}
    assert actuals["GOOGL"].pct_of_portfolio == pytest.approx(0.0376)
    assert "AVGO" in actuals and "MSFT" in actuals

    summary = target_weight_drift_summary(account_positions, BOOK, limit=20)
    by_ticker = {r["ticker"]: r for r in summary["rows"]}
    for tk in ("GOOGL", "AVGO", "MSFT"):
        assert by_ticker[tk]["direction"] == "UNDERSIZED"
        assert by_ticker[tk]["actual_pct"] > 0
        assert by_ticker[tk]["direction"] != "MISSING"


def test_combined_positions_preferred_over_tracked_only_key():
    # Direct guard on the foot-gun: pointing the reader at tracked_combined_positions would make
    # untracked GOOGL vanish (MISSING). Pin that the FULL combined book is what gets measured.
    account_positions = {
        "sleeve_value": BOOK,
        "combined_positions": [
            {"ticker": "GOOGL", "market_value": 0.04 * BOOK, "tracked": False},
            {"ticker": "NVDA", "market_value": 0.12 * BOOK, "tracked": True},
        ],
        "tracked_combined_positions": [
            {"ticker": "NVDA", "market_value": 0.12 * BOOK, "tracked": True},
        ],
    }
    tickers = {a.ticker for a in load_actuals_from_positions_cache(account_positions)}
    assert "GOOGL" in tickers  # would be absent if tracked_combined_positions were read


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
