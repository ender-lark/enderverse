from __future__ import annotations

import json
from pathlib import Path

import cloud_routine_receipts
import full_build_runner
import trigger_check


def _price_trigger() -> dict:
    return trigger_check.make_trigger(
        trigger_id="nvda-above-100",
        ticker="NVDA",
        condition_type="price_cross",
        params={"field": "price", "direction": "above", "level": 100},
        source="unit test",
        registered_at="2026-06-13T00:00:00Z",
    )


def test_price_cross_fires_once_and_never_refires():
    registry = [_price_trigger()]

    fired = trigger_check.evaluate(
        registry,
        trigger_check.quote_fn_from_map({"NVDA": {"price": 101}}),
        as_of="2026-06-13T14:00:00Z",
    )
    fired_again = trigger_check.evaluate(
        registry,
        trigger_check.quote_fn_from_map({"NVDA": {"price": 102}}),
        as_of="2026-06-13T15:00:00Z",
    )

    assert [row["id"] for row in fired] == ["nvda-above-100"]
    assert fired_again == []
    assert registry[0]["status"] == "fired"
    assert registry[0]["fired_at"] == "2026-06-13T14:00:00Z"


def test_missing_quote_is_not_checked_not_clear():
    registry = [_price_trigger()]

    report = trigger_check.evaluate_registry(
        registry,
        trigger_check.quote_fn_from_map({}),
        as_of="2026-06-13",
    )

    assert report["fired_count"] == 0
    assert report["not_checked_count"] == 1
    assert report["status"] == "not_checked"
    assert registry[0]["status"] == "armed"
    assert "quote not checked" in report["not_checked"][0]["reason"]


def test_level_touch_uses_intraday_range():
    registry = [
        trigger_check.make_trigger(
            trigger_id="asts-zone",
            ticker="ASTS",
            condition_type="level_touch",
            params={"zone_low": 65, "zone_high": 70},
            source="unit test",
        )
    ]

    report = trigger_check.evaluate_registry(
        registry,
        trigger_check.quote_fn_from_map({"ASTS": {"intraday_low": 64.5, "intraday_high": 68.0}}),
        as_of="2026-06-13T14:00:00Z",
    )

    assert report["fired_count"] == 1
    assert "touched 65-70" in report["fired"][0]["fire_reason"]


def test_date_event_fires_when_due():
    registry = [
        trigger_check.make_trigger(
            trigger_id="googl-review",
            ticker="GOOGL",
            condition_type="date_event",
            params={"date": "2026-06-19"},
            source="unit test",
        )
    ]

    before = trigger_check.evaluate_registry(registry, trigger_check.quote_fn_from_map({}), as_of="2026-06-18")
    due = trigger_check.evaluate_registry(registry, trigger_check.quote_fn_from_map({}), as_of="2026-06-19")

    assert before["fired_count"] == 0
    assert due["fired_count"] == 1
    assert registry[0]["status"] == "fired"


def _accel_trigger(params: dict | None = None) -> dict:
    return trigger_check.make_trigger(
        trigger_id="mu-accel",
        ticker="MU",
        condition_type="acceleration",
        params=params or {"field": "pct_change_5d", "threshold": 40, "operator": "above", "min_phase": 3},
        source="unit test",
        registered_at="2026-05-01T00:00:00Z",
    )


def _pct_change(series: list[float], lookback: int = 5) -> float:
    return (series[-1] / series[-1 - lookback] - 1) * 100


def test_acceleration_fires_on_parabolic_series_once():
    # A synthetic parabolic blow-off: price more than doubles over 5 sessions.
    parabolic = [70, 78, 92, 115, 140, 150]
    quote = {"price": parabolic[-1], "pct_change_5d": _pct_change(parabolic), "phase": "Phase 3 (parabola)"}
    registry = [_accel_trigger()]

    fired = trigger_check.evaluate(
        registry, trigger_check.quote_fn_from_map({"MU": quote}), as_of="2026-05-27T14:00:00Z"
    )
    refired = trigger_check.evaluate(
        registry, trigger_check.quote_fn_from_map({"MU": quote}), as_of="2026-05-28T14:00:00Z"
    )

    assert [row["id"] for row in fired] == ["mu-accel"]
    assert "pct_change_5d" in fired[0]["fire_reason"]
    assert refired == []  # idempotent: fires once
    assert registry[0]["status"] == "fired"


def test_acceleration_does_not_fire_on_slow_grind_to_same_level():
    # The false positive the gaps doc warns about: the SAME end price (150)
    # reached by a slow grind prints a small 5-day move and a lower phase.
    grind = [142, 144, 146, 147, 149, 150]
    quote = {"price": grind[-1], "pct_change_5d": _pct_change(grind), "phase": "Phase 2 (recognition)"}
    registry = [_accel_trigger()]

    report = trigger_check.evaluate_registry(
        registry, trigger_check.quote_fn_from_map({"MU": quote}), as_of="2026-05-27T14:00:00Z"
    )

    assert report["fired_count"] == 0
    assert report["status"] == "checked_clear"
    assert registry[0]["status"] == "armed"


def test_acceleration_not_checked_when_velocity_missing():
    # The quote exists but carries only a last price -- no velocity fields. This
    # must be not_checked (honest), never a false all-clear, and stay armed.
    registry = [_accel_trigger()]
    report = trigger_check.evaluate_registry(
        registry, trigger_check.quote_fn_from_map({"MU": {"price": 150}}), as_of="2026-05-27T14:00:00Z"
    )

    assert report["fired_count"] == 0
    assert report["status"] == "not_checked"
    assert report["status"] != "checked_clear"
    assert "no quote field pct_change_5d" in report["not_checked"][0]["reason"]
    assert registry[0]["status"] == "armed"


def test_acceleration_supports_consecutive_up_days_and_phase_floor():
    # A slope+phase trigger (no percent-move bar) fires when both confirm ...
    registry = [_accel_trigger({"min_consecutive_up_days": 5, "min_phase": 3})]
    fired = trigger_check.evaluate(
        registry,
        trigger_check.quote_fn_from_map({"MU": {"consecutive_up_days": 6, "phase": "Phase 3 (parabola)"}}),
        as_of="2026-05-27T14:00:00Z",
    )
    assert [row["id"] for row in fired] == ["mu-accel"]

    # ... and is not_checked when the slope field is absent.
    registry2 = [_accel_trigger({"min_consecutive_up_days": 5})]
    report = trigger_check.evaluate_registry(
        registry2,
        trigger_check.quote_fn_from_map({"MU": {"phase": "Phase 3 (parabola)"}}),
        as_of="2026-05-27T14:00:00Z",
    )
    assert report["status"] == "not_checked"
    assert "no quote field consecutive_up_days" in report["not_checked"][0]["reason"]


def test_cli_write_updates_registry_summary_and_fire_receipt(tmp_path, capsys):
    registry_path = tmp_path / "trigger_registry.json"
    summary_path = tmp_path / "trigger_check_summary.json"
    quotes_path = tmp_path / "quotes.json"
    receipts_path = tmp_path / "receipts.json"
    registry_path.write_text(json.dumps([_price_trigger()]), encoding="utf-8")
    quotes_path.write_text(json.dumps({"NVDA": {"price": 105}}), encoding="utf-8")

    rc = trigger_check.main([
        "--registry",
        str(registry_path),
        "--summary",
        str(summary_path),
        "--quotes-json",
        str(quotes_path),
        "--write",
        "--receipt-path",
        str(receipts_path),
        "--routine-id",
        "test-trigger-routine",
        "--run-source",
        "scheduled",
        "--format",
        "text",
        "--as-of",
        "2026-06-13T14:00:00Z",
    ])

    output = capsys.readouterr().out
    saved_registry = json.loads(registry_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    receipts = cloud_routine_receipts.load_receipts(receipts_path)
    assert rc == 0
    assert "fired=1" in output
    assert saved_registry[0]["status"] == "fired"
    assert summary["fired_count"] == 1
    assert receipts["receipts"][0]["routine_id"] == "test-trigger-routine"
    assert receipts["receipts"][0]["run_source"] == "scheduled"


def test_failed_notification_does_not_advance_trigger_state(tmp_path, monkeypatch):
    registry_path = tmp_path / "trigger_registry.json"
    summary_path = tmp_path / "trigger_check_summary.json"
    quotes_path = tmp_path / "quotes.json"
    receipts_path = tmp_path / "receipts.json"
    registry_path.write_text(json.dumps([_price_trigger()]), encoding="utf-8")
    quotes_path.write_text(json.dumps({"NVDA": {"price": 105}}), encoding="utf-8")

    monkeypatch.setattr(
        trigger_check.pushover_notify,
        "send_message",
        lambda **_kwargs: {"sent": False, "error": "network down"},
    )

    rc = trigger_check.main([
        "--registry",
        str(registry_path),
        "--summary",
        str(summary_path),
        "--quotes-json",
        str(quotes_path),
        "--write",
        "--send",
        "--receipt-path",
        str(receipts_path),
        "--routine-id",
        "test-trigger-routine",
        "--run-source",
        "scheduled",
        "--as-of",
        "2026-06-13T14:00:00Z",
    ])

    saved_registry = json.loads(registry_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    receipts = cloud_routine_receipts.load_receipts(receipts_path)
    assert rc == 2
    assert saved_registry[0]["status"] == "armed"
    assert summary["status"] == "send_failed"
    assert receipts["receipts"][0]["status"] == "failed"


def test_seeded_registry_contains_real_active_trigger_classes():
    registry = trigger_check.load_registry(Path(__file__).with_name("trigger_registry.json"))
    ids = {row["id"] for row in registry}

    assert "ewre-weekly-close-above-38-2026-06" in ids
    assert "googl-tranche-2-review-2026-06-19" in ids
    assert "asts-reentry-zone-65-70" in ids
    assert "rklb-reentry-zone-85-90" in ids


def test_dashboard_audit_warns_when_registry_has_no_check_summary(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "trigger_registry.json").write_text(json.dumps([_price_trigger()]), encoding="utf-8")

    audit = full_build_runner._build_trigger_registry_audit(src)

    assert audit["status"] == "not_checked"
    assert audit["armed_count"] == 1
    assert "not checked this build" in audit["line"]
