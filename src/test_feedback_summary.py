"""Tests for cockpit feedback-loop summary."""
from feedback_summary import build_feedback_summary, source_call_feedback, open_action_feedback
from feed_assembler import assemble_feed
from build_golden import build_snapshot_bundle
from validators import validate_cockpit_feed


CALLS = [
    {"source": "newton", "ticker": "NVDA", "tier": "A", "outcome": None,
     "date": "2026-04-01", "window_end": "2026-04-15"},
    {"source": "lee", "ticker": "MU", "tier": "A", "outcome": "Win",
     "date": "2026-04-01", "window_end": "2026-04-15"},
]


def test_source_call_feedback_flags_overdue_scoring():
    fb = source_call_feedback(CALLS, as_of="2026-05-31")
    assert fb["status"] == "has_data"
    assert fb["overdue_count"] == 1
    assert fb["due"][0]["ticker"] == "NVDA"
    assert any(r["source"] == "lee" and r["n"] == 1 for r in fb["rates"])


def test_source_call_feedback_not_checked_when_omitted():
    fb = source_call_feedback(None, as_of="2026-05-31")
    assert fb["status"] == "not_checked"
    assert fb["overdue_count"] == 0


def test_open_action_feedback_surfaces_oldest_backlog():
    store = {"opportunities": [
        {"ticker": "FN", "first_flagged": "2026-05-28", "flag_price": 600,
         "source": "fundstrat_top5", "kind": "lean_in", "status": "open"},
    ]}
    fb = open_action_feedback(store, prices={"FN": 660}, as_of="2026-06-04")
    assert fb["status"] == "has_data"
    assert fb["count"] == 1
    assert fb["items"][0]["ticker"] == "FN"
    assert fb["items"][0]["move_since"] == "+10% since flag"


def test_feedback_summary_recommends_scoring_and_resolution():
    store = {"opportunities": [
        {"ticker": "FN", "first_flagged": "2026-05-28", "kind": "lean_in", "status": "open"},
    ]}
    fb = build_feedback_summary(source_calls=CALLS, open_opportunities=store, as_of="2026-05-31")
    assert any("Score overdue" in r for r in fb["recommendations"])
    assert any("Resolve oldest" in r for r in fb["recommendations"])


def test_assemble_feed_emits_valid_feedback_block():
    feed = assemble_feed(build_snapshot_bundle(), parabolic={"MU"}, source_calls=CALLS)
    assert feed["feedback"]["source_calls"]["overdue_count"] >= 1
    assert validate_cockpit_feed(feed) == []
