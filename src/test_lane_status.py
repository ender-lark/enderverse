"""Tests for dark-lane honesty status rows."""
from lane_status import (
    STATUS_CHECKED_CLEAR,
    STATUS_FAILED,
    STATUS_HAS_DATA,
    STATUS_NOT_CHECKED,
    STATUS_STALE,
    build_lane_status,
)
from validators import validate_cockpit_feed


def _snapshot():
    return {
        "sources_ok": ["portfolio", "uw_price"],
        "sources_failed": [{"name": "fundstrat_daily", "error": "timeout"}],
        "staleness": {
            "portfolio": "2026-06-04",
            "uw_price": "2026-06-01",
            "fundstrat_daily": "2026-06-03",
        },
    }


def test_source_rows_distinguish_ok_stale_failed_and_not_checked():
    lane = build_lane_status(_snapshot(), {"stale": ["uw_price"]})
    rows = {r["key"]: r for r in lane["rows"]}
    assert rows["portfolio"]["status"] == STATUS_HAS_DATA
    assert rows["uw_price"]["status"] == STATUS_STALE
    assert rows["fundstrat_daily"]["status"] == STATUS_FAILED
    assert rows["fundstrat_bible"]["status"] == STATUS_NOT_CHECKED
    assert lane["has_stale_or_failed"] is True


def test_source_rows_do_not_mark_empty_clean_source_as_has_data():
    snap = {
        "sources_ok": ["portfolio", "fundstrat_daily"],
        "sources_failed": [],
        "staleness": {"portfolio": "2026-06-04"},
    }

    lane = build_lane_status(snap, {"stale": []})
    rows = {r["key"]: r for r in lane["rows"]}

    assert rows["portfolio"]["status"] == STATUS_HAS_DATA
    assert rows["fundstrat_daily"]["status"] == STATUS_CHECKED_CLEAR


def test_external_lanes_distinguish_not_checked_from_checked_clear():
    lane = build_lane_status(
        _snapshot(),
        {"stale": []},
        catalysts=[],
        research={"pending": []},
        synthesis=None,
        uw_opportunity={"signals": [{"ticker": "NVDA"}]},
        signal_log=[{"signal": "Morning scan flag"}],
        event_risk=[],
        top_prospects={},
    )
    rows = {r["key"]: r for r in lane["rows"]}
    assert rows["catalysts"]["status"] == STATUS_CHECKED_CLEAR
    assert rows["research"]["status"] == STATUS_CHECKED_CLEAR
    assert rows["synthesis"]["status"] == STATUS_NOT_CHECKED
    assert rows["uw_opportunity"]["status"] == STATUS_HAS_DATA
    assert rows["signal_log"]["status"] == STATUS_HAS_DATA
    assert rows["event_risk"]["status"] == STATUS_CHECKED_CLEAR
    assert rows["top_prospects"]["status"] == STATUS_CHECKED_CLEAR
    assert lane["has_dark_lanes"] is True


def test_lane_status_feed_contract_accepts_rows():
    feed = {
        "generated_at": "2026-06-04T16:00:00",
        "staleness": {},
        "hero": {},
        "macro": {},
        "fresh_signals": [],
        "holdings": [],
        "rotation": [],
        "lane_status": build_lane_status(_snapshot(), {"stale": []}, catalysts=[]),
    }
    assert validate_cockpit_feed(feed) == []
