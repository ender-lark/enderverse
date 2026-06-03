"""Unit tests for Contract B — CollectedSnapshot + validator (C1).

Run:  python -m pytest src/test_collection.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from sources import SourceItem, BaseSource, SourceRegistry
from collection import CollectedSnapshot, collect, CRITICAL_SOURCES, run_log_payload, write_run_log
from validators import (
    validate_collected_snapshot,
    is_valid_collected_snapshot,
    assert_valid_collected_snapshot,
)


def _items():
    return [
        SourceItem("uw_price", "rotation", "SMH", "LEADING +47%/3M vs mkt",
                   "2026-05-29", 0.95, "market_data", {"rel_3m": 0.47}),
        SourceItem("portfolio", "position", "SMH", "SMH 9.90% Owned",
                   "2026-05-27", 0.95, "own", {"pct": 9.9}),
        SourceItem("uw_price", "error", "uw_price", "fetch failed: RuntimeError: x",
                   "2026-05-29", 0.95, "market_data",
                   {"error_type": "RuntimeError", "error": "x"}),
    ]


def good_snapshot(**over):
    base = dict(
        run_id="run_20260529_120000",
        run_timestamp="2026-05-29T12:00:00",
        items=_items(),
        sources_ok=["uw_price", "portfolio"],
        sources_failed=[{"name": "meridian", "error": "doc not found"}],
        staleness={"uw_price": "2026-05-29", "portfolio": "2026-05-27"},
        critical_missing=[],
    )
    base.update(over)
    return CollectedSnapshot(**base)


def good_dict(**over):
    base = dict(
        run_id="run_1", run_timestamp="2026-05-29T12:00:00", items=_items(),
        sources_ok=["uw_price"], sources_failed=[], staleness={}, critical_missing=[])
    base.update(over)
    return base


# --------------------------------------------------------------------------- #
# valid
# --------------------------------------------------------------------------- #
def test_valid_snapshot_passes():
    assert validate_collected_snapshot(good_snapshot()) == []
    assert is_valid_collected_snapshot(good_snapshot()) is True


def test_valid_dict_form_passes():
    assert validate_collected_snapshot(good_dict()) == []


def test_minimal_snapshot_with_defaults_valid():
    # only the two required ids; lists/dict default empty -> still valid
    assert validate_collected_snapshot(
        CollectedSnapshot(run_id="r1", run_timestamp="2026-05-29T00:00:00")) == []


def test_error_item_in_items_accepted():
    # the kind="error" card is a valid SourceItem, so the snapshot stays valid
    assert validate_collected_snapshot(good_snapshot()) == []


# --------------------------------------------------------------------------- #
# required ids
# --------------------------------------------------------------------------- #
def test_missing_run_id_fails():
    d = good_dict()
    del d["run_id"]
    assert any("missing field: run_id" == p for p in validate_collected_snapshot(d))


def test_empty_run_timestamp_fails():
    probs = validate_collected_snapshot(good_snapshot(run_timestamp="   "))
    assert any("run_timestamp" in p and "non-empty" in p for p in probs)


# --------------------------------------------------------------------------- #
# items
# --------------------------------------------------------------------------- #
def test_items_not_a_list_fails():
    probs = validate_collected_snapshot(good_snapshot(items="notalist"))
    assert any("items must be a list" in p for p in probs)


def test_invalid_item_flagged_with_index():
    items = [_items()[0], {"kind": "rotation"}]   # 2nd is a malformed card
    probs = validate_collected_snapshot(good_snapshot(items=items))
    assert any(p.startswith("items[1] invalid SourceItem") for p in probs)


# --------------------------------------------------------------------------- #
# sources_ok / sources_failed / staleness / critical_missing
# --------------------------------------------------------------------------- #
def test_sources_ok_must_be_strings():
    probs = validate_collected_snapshot(good_snapshot(sources_ok=["uw_price", 7]))
    assert any("sources_ok must be a list of strings" in p for p in probs)


def test_sources_failed_entry_missing_error_fails():
    probs = validate_collected_snapshot(
        good_snapshot(sources_failed=[{"name": "meridian"}]))  # no 'error'
    assert any("sources_failed[0]" in p for p in probs)


def test_staleness_must_be_dict():
    probs = validate_collected_snapshot(good_snapshot(staleness=["2026-05-29"]))
    assert any("staleness must be a dict" in p for p in probs)


def test_critical_missing_must_be_strings():
    probs = validate_collected_snapshot(good_snapshot(critical_missing=[1, 2]))
    assert any("critical_missing must be a list of strings" in p for p in probs)


# --------------------------------------------------------------------------- #
# assert helper
# --------------------------------------------------------------------------- #
def test_assert_passes_on_good():
    assert assert_valid_collected_snapshot(good_snapshot()) is None


def test_assert_raises_on_bad():
    with pytest.raises(ValueError) as exc:
        assert_valid_collected_snapshot(good_dict(run_id=""))
    assert "invalid CollectedSnapshot" in str(exc.value)


# --------------------------------------------------------------------------- #
# convenience accessors
# --------------------------------------------------------------------------- #
def test_positions_accessor():
    pos = good_snapshot().positions()
    assert [p.subject for p in pos] == ["SMH"]
    assert all(p.kind == "position" for p in pos)


def test_errors_accessor():
    errs = good_snapshot().errors()
    assert len(errs) == 1 and errs[0].kind == "error"


def test_items_of_kind():
    assert len(good_snapshot().items_of_kind("rotation")) == 1


# =========================================================================== #
# C2/C3 — the collect() runner
# =========================================================================== #
def _src(name, rows):
    """A canned plug: BaseSource that returns `rows` (dicts) from its fetcher."""
    return BaseSource(name, lambda rows=rows: list(rows))


def _registry(*sources):
    reg = SourceRegistry()
    for s in sources:
        reg.register(s)
    return reg


def test_runner_happy_path():
    reg = _registry(
        _src("uw_price", [{"kind": "rotation", "subject": "SMH",
                           "content": "LEADING", "timestamp": "2026-05-29"}]),
        _src("portfolio", [{"kind": "position", "subject": "SMH",
                            "content": "SMH 9.9% Owned", "timestamp": "2026-05-27"}]),
        _src("fundstrat_bible", [{"kind": "stance", "subject": "macro stance",
                                  "content": "constructive", "timestamp": "2026-05-28"}]),
    )
    snap = collect(reg, run_timestamp="2026-05-29T12:00:00")
    assert validate_collected_snapshot(snap) == []
    assert set(snap.sources_ok) == {"uw_price", "portfolio", "fundstrat_bible"}
    assert snap.sources_failed == []
    assert snap.critical_missing == []
    assert snap.staleness == {"uw_price": "2026-05-29", "portfolio": "2026-05-27",
                              "fundstrat_bible": "2026-05-28"}
    assert snap.run_timestamp == "2026-05-29T12:00:00"
    assert len(snap.items) == 3


def test_runner_failing_plug_recorded_and_pull_survives():
    def boom():
        raise RuntimeError("connector down")
    reg = _registry(
        _src("uw_price", [{"kind": "rotation", "subject": "SMH",
                           "content": "x", "timestamp": "2026-05-29"}]),
        _src("portfolio", [{"kind": "position", "subject": "SMH",
                            "content": "x", "timestamp": "2026-05-27"}]),
        BaseSource("meridian", boom),
    )
    snap = collect(reg, run_timestamp="2026-05-29T12:00:00")
    assert validate_collected_snapshot(snap) == []
    assert "meridian" not in snap.sources_ok
    assert any(f["name"] == "meridian" and "connector down" in f["error"]
               for f in snap.sources_failed)
    assert snap.critical_missing == []          # uw_price + portfolio still delivered
    assert len(snap.items) == 3                  # 2 good + 1 error card


def test_runner_critical_missing_when_portfolio_fails():
    def boom():
        raise RuntimeError("notion down")
    reg = _registry(
        _src("uw_price", [{"kind": "rotation", "subject": "SMH",
                           "content": "x", "timestamp": "2026-05-29"}]),
        BaseSource("portfolio", boom),
    )
    snap = collect(reg)
    assert "portfolio" in snap.critical_missing
    assert "uw_price" not in snap.critical_missing
    assert any(f["name"] == "portfolio" for f in snap.sources_failed)


def test_runner_critical_missing_when_critical_absent():
    reg = _registry(_src("uw_price", [{"kind": "rotation", "subject": "SMH",
                                       "content": "x", "timestamp": "2026-05-29"}]))
    snap = collect(reg)
    assert "portfolio" in snap.critical_missing      # never registered


def test_runner_ok_but_empty_critical_is_missing():
    # portfolio ran cleanly but returned ZERO positions -> ok yet missing
    reg = _registry(
        _src("portfolio", []),
        _src("uw_price", [{"kind": "rotation", "subject": "SMH",
                           "content": "x", "timestamp": "2026-05-29"}]),
    )
    snap = collect(reg)
    assert "portfolio" in snap.sources_ok            # didn't error
    assert "portfolio" in snap.critical_missing       # but delivered no data


def test_runner_staleness_picks_newest_per_source():
    reg = _registry(_src("uw_price", [
        {"kind": "rotation", "subject": "SMH", "content": "x", "timestamp": "2026-05-20"},
        {"kind": "rotation", "subject": "IGV", "content": "y", "timestamp": "2026-05-29"},
    ]))
    snap = collect(reg)
    assert snap.staleness["uw_price"] == "2026-05-29"


def test_runner_output_valid_and_run_id_generated():
    reg = _registry(_src("uw_price", [{"kind": "rotation", "subject": "SMH",
                                       "content": "x", "timestamp": "2026-05-29"}]))
    snap = collect(reg)
    assert is_valid_collected_snapshot(snap)
    assert isinstance(snap.run_id, str) and snap.run_id.startswith("run_")
    assert isinstance(snap.run_timestamp, str) and snap.run_timestamp


def test_runner_custom_critical_set():
    reg = _registry(_src("uw_macro", [{"kind": "macro", "subject": "10Y",
                                       "content": "x", "timestamp": "2026-05-29"}]))
    assert collect(reg, critical=("uw_macro",)).critical_missing == []
    assert collect(reg, critical=("portfolio",)).critical_missing == ["portfolio"]


# =========================================================================== #
# C4 — the compact run-log writer
# =========================================================================== #
def test_run_log_payload_fields():
    snap = good_snapshot()
    p = run_log_payload(snap)
    assert p["run_id"] == snap.run_id
    assert p["item_count"] == 3
    assert p["sources_ok"] == ["uw_price", "portfolio"]
    assert p["sources_failed"] == ["meridian"]      # names only -> compact
    assert p["critical_missing"] == []
    assert p["staleness"] == {"uw_price": "2026-05-29", "portfolio": "2026-05-27"}
    assert "summary" in p


def test_write_run_log_calls_injected_writer():
    captured = []

    def writer(payload):
        captured.append(payload)
        return "notion_page_123"

    res = write_run_log(good_snapshot(), writer)
    assert res["written"] is True
    assert res["result"] == "notion_page_123"
    assert len(captured) == 1
    assert captured[0]["run_id"] == good_snapshot().run_id


def test_write_run_log_survives_writer_failure():
    def bad_writer(payload):
        raise RuntimeError("notion 500")

    res = write_run_log(good_snapshot(), bad_writer)
    assert res["written"] is False
    assert "notion 500" in res["error"]
    assert res["payload"]["item_count"] == 3        # payload still returned; run not sunk


def test_run_log_summary_contains_key_facts():
    p = run_log_payload(good_snapshot())
    assert "meridian" in p["summary"]               # the failed source
    assert "3 items" in p["summary"]
    assert "critical missing: none" in p["summary"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-q"]))
