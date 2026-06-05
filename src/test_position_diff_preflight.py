import json
import sys
from types import SimpleNamespace

import daily_preflight
from session_orchestrator import _run_position_diff, orchestrate


def _reconciliation():
    return {
        "prior_snapshot_date": "2026-06-04",
        "current_snapshot_date": "2026-06-05",
        "counts": {"NEW": 1, "ADD": 1, "VALUE_CHANGE": 1},
        "changes": [
            {"ticker": "GOOGL", "account": "Taxable", "owner": "SKB", "broker": "Fidelity", "action": "NEW", "share_delta": 4},
            {"ticker": "NVDA", "account": "Taxable", "owner": "SKB", "broker": "Fidelity", "action": "ADD", "share_delta": 2},
            {"ticker": "SMH", "account": "Aggregate", "owner": "Parents", "broker": "Schwab", "action": "VALUE_CHANGE", "share_delta": 0},
        ],
    }


def test_position_diff_unavailable_when_no_file_supplied():
    result = _run_position_diff(None)
    assert result.available is False
    assert result.actionable_count == 0


def test_position_diff_not_checked_when_prior_missing():
    result = _run_position_diff({
        "status": "not_checked",
        "reason": "prior account-position cache missing",
        "changes": [],
        "counts": {},
    })
    assert result.available is False
    assert "prior account-position cache missing" in result.surface_line


def test_position_diff_surfaces_trade_like_changes():
    result = _run_position_diff(_reconciliation())
    assert result.available is True
    assert result.priority == "HIGH"
    assert result.actionable_count == 2
    assert "2 trade-like" in result.surface_line
    assert "GOOGL NEW +4sh" in result.surface_line


def test_orchestrator_includes_position_diff_in_priority_order():
    dashboard = orchestrate(
        positions=[],
        theses=[],
        sleeve_total=1,
        position_reconciliation=_reconciliation(),
    )
    assert len(dashboard.subsystems) == 10
    assert "POSITION DIFF" in dashboard.priority_order


def test_daily_preflight_passes_position_reconciliation(tmp_path, monkeypatch, capsys):
    captured = {}

    def fake_orchestrate(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    fake_so = SimpleNamespace(
        orchestrate=fake_orchestrate,
        format_text=lambda dashboard: "dashboard",
        format_json=lambda dashboard: json.dumps(dashboard),
    )
    monkeypatch.setitem(sys.modules, "session_orchestrator", fake_so)
    monkeypatch.setattr(sys, "argv", [
        "daily_preflight.py",
        "--inputs-dir", str(tmp_path),
    ])

    (tmp_path / "positions.json").write_text(json.dumps({
        "snapshot_date": daily_preflight.date.today().isoformat(),
        "positions": [],
    }), encoding="utf-8")
    (tmp_path / "theses.json").write_text("[]", encoding="utf-8")
    (tmp_path / "position_reconciliation.json").write_text(json.dumps(_reconciliation()), encoding="utf-8")

    daily_preflight.main()

    assert captured["position_reconciliation"]["counts"]["NEW"] == 1
    assert "dashboard" in capsys.readouterr().out
