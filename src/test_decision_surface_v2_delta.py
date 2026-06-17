import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_today_decide import _feed, _payload
from today_decide import render_today_decide_html


def _packet(as_of: str = "2026-06-17") -> dict:
    return {
        "display_label": "Daily pullback packet",
        "as_of": as_of,
        "act_if_green": [{
            "ticker": "GOOGL",
            "dollar_band": {"low": 100000, "high": 155000},
            "green_first_tranche": {"low": 50000, "high": 108500},
            "gate_status": "green only after Fed/tape confirms",
            "do_nothing_cost": "GOOGL stays undersized if thesis is right.",
            "disconfirmation": "Do not deploy if QQQ/SPY fail.",
        }],
        "higher_quality_pullbacks": [{
            "ticker": "AVGO",
            "rank_score": 23.49,
            "pct_below_high": -23.9,
            "price": 377,
            "current_exposure_usd": 40696,
            "research_status": "STAGE",
            "source_tags": ["Notion Working STAGE"],
            "disconfirmation": "Advance only if flow beats GOOGL/MSFT.",
        }],
        "deep_discount_research": [],
        "do_not_touch_yet": [],
    }


def test_fed_packet_fresh_populates_watch_queue_without_stale_note():
    feed = copy.deepcopy(_feed())
    feed["fed_day_reallocation_packet"] = _packet("2026-06-17")

    payload = _payload(feed=feed, today="2026-06-17")
    html = render_today_decide_html(payload)

    assert payload["watch_queue_meta"]["freshness"] == "fresh"
    assert payload["watch_queue"][0]["ticker"] == "AVGO"
    assert "fed_day_packet" not in payload["honesty"]
    assert "STALE/not_checked" not in html
    assert "Daily pullback packet current as of 2026-06-17" in html


def test_fed_packet_stale_keeps_rows_but_marks_research_context_only():
    feed = copy.deepcopy(_feed())
    feed["fed_day_reallocation_packet"] = _packet("2026-06-16")

    payload = _payload(feed=feed, today="2026-06-17")
    html = render_today_decide_html(payload)

    assert payload["watch_queue_meta"]["freshness"] == "stale"
    assert payload["watch_queue"][0]["ticker"] == "AVGO"
    assert payload["watch_queue"][0]["packet_as_of"] == "2026-06-16"
    assert payload["honesty"]["fed_day_packet"] == "stale (as_of 2026-06-16) - research context only, prices not current"
    assert "price $377 as of 2026-06-16 - STALE, research context only" in html
    assert "Shown but not counted" in html


def test_fed_packet_absent_does_not_fabricate_watch_rows():
    payload = _payload(feed=copy.deepcopy(_feed()), today="2026-06-17")
    html = render_today_decide_html(payload)

    assert payload["watch_queue"] == []
    assert payload["watch_queue_meta"]["freshness"] == "absent"
    assert payload["honesty"]["fed_day_packet"] == "not_checked - no packet on disk"
    assert "Daily pullback packet not_checked - no packet on disk" in html
    assert "Watchlist / pullback impact queue (0)" in html
