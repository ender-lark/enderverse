import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collection import CollectedSnapshot
from collection_gate import (
    assert_valid_collection_gate,
    is_valid_collection_gate,
    validate_collection_gate,
)
from sources import SourceItem
from validators import validate_collected_snapshot


def _item(source="uw_price", kind="rotation", subject="SMH", timestamp="2026-06-05"):
    return SourceItem(
        source,
        kind,
        subject,
        "content",
        timestamp,
        0.95,
        "market_data",
        {},
    )


def _snapshot(**overrides):
    base = {
        "run_id": "run_20260605_140000",
        "run_timestamp": "2026-06-05T14:00:00+00:00",
        "items": [
            _item("uw_price", "rotation", "SMH", "2026-06-05"),
            _item("portfolio", "position", "SMH", "2026-06-04"),
        ],
        "sources_ok": ["uw_price", "portfolio"],
        "sources_failed": [],
        "staleness": {"uw_price": "2026-06-05", "portfolio": "2026-06-04"},
        "critical_missing": [],
    }
    base.update(overrides)
    return CollectedSnapshot(**base)


def test_valid_collection_gate_passes():
    snap = _snapshot()

    assert validate_collection_gate(snap) == []
    assert is_valid_collection_gate(snap) is True
    assert assert_valid_collection_gate(snap) is None


def test_contract_b_shape_failure_is_reported_first():
    snap = {
        "run_id": "",
        "run_timestamp": "2026-06-05T14:00:00+00:00",
        "items": [],
        "sources_ok": [],
        "sources_failed": [],
        "staleness": {},
        "critical_missing": [],
    }

    problems = validate_collection_gate(snap)

    assert problems
    assert problems[0].startswith("Contract-B:")


def test_run_timestamp_must_be_datetime_not_date_only():
    snap = _snapshot(run_timestamp="2026-06-05")

    problems = validate_collection_gate(snap)

    assert validate_collected_snapshot(snap) == []
    assert any("run_timestamp must be an ISO datetime" in p for p in problems)


def test_month_level_source_stamp_is_valid_for_monthly_baselines():
    snap = _snapshot(
        items=[
            _item("fundstrat_bible", "stance", "macro", "2026-05"),
            _item("portfolio", "position", "SMH", "2026-06-04"),
            _item("uw_price", "rotation", "SMH", "2026-06-05"),
        ],
        sources_ok=["fundstrat_bible", "portfolio", "uw_price"],
        staleness={
            "fundstrat_bible": "2026-05",
            "portfolio": "2026-06-04",
            "uw_price": "2026-06-05",
        },
    )

    assert validate_collection_gate(snap) == []


def test_critical_missing_fails_l2_to_l3_gate():
    snap = _snapshot(critical_missing=["portfolio"])

    problems = validate_collection_gate(snap)

    assert validate_collected_snapshot(snap) == []
    assert any("critical source(s) missing" in p for p in problems)


def test_staleness_must_match_newest_non_error_timestamp():
    snap = _snapshot(
        items=[
            _item("uw_price", "rotation", "SMH", "2026-06-04"),
            _item("uw_price", "rotation", "IGV", "2026-06-05"),
            _item("portfolio", "position", "SMH", "2026-06-04"),
        ],
        staleness={"uw_price": "2026-06-04", "portfolio": "2026-06-04"},
    )

    problems = validate_collection_gate(snap)

    assert any("staleness['uw_price']" in p and "2026-06-05" in p for p in problems)


def test_error_items_and_sources_failed_must_match():
    snap = _snapshot(
        items=[
            _item("uw_price", "rotation", "SMH", "2026-06-05"),
            _item("portfolio", "position", "SMH", "2026-06-04"),
            _item("meridian", "error", "meridian", "2026-06-05T14:00:00+00:00"),
        ],
        sources_failed=[],
    )

    problems = validate_collection_gate(snap)

    assert any("error SourceItem(s) missing from sources_failed: meridian" in p for p in problems)


def test_source_cannot_be_ok_and_failed():
    snap = _snapshot(
        items=[
            _item("uw_price", "rotation", "SMH", "2026-06-05"),
            _item("portfolio", "position", "SMH", "2026-06-04"),
            _item("meridian", "error", "meridian", "2026-06-05T14:00:00+00:00"),
        ],
        sources_ok=["uw_price", "portfolio", "meridian"],
        sources_failed=[{"name": "meridian", "error": "connector down"}],
    )

    problems = validate_collection_gate(snap)

    assert any("cannot be both ok and failed: meridian" in p for p in problems)
