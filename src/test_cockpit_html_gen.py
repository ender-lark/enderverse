"""Tests for the generated HTML summary/export dashboard."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cockpit_html_gen import generate_html


def _feed():
    return {
        "generated_at": "2026-06-05T14:00:00+00:00",
        "actions": [],
        "hero": {"hero": {"count": 0}, "needs_you": {"count": 0, "items": []}},
        "holdings": [],
        "lane_status": {
            "counts": {
                "has_data": 2,
                "checked_clear": 1,
                "not_checked": 3,
                "stale": 1,
                "failed": 0,
            },
            "rows": [
                {"key": "research", "label": "Research Queue", "status": "not_checked", "detail": "not supplied", "count": 0},
                {"key": "uw_price", "label": "Prices", "status": "stale", "detail": "past freshness window", "count": 0},
                {"key": "portfolio", "label": "Portfolio", "status": "has_data", "detail": "checked", "count": 18},
            ],
        },
        "feedback": {
            "source_calls": {
                "line": "Source-call scoring: 1 overdue.",
                "overdue_count": 1,
                "calibration": {"line": "Calibration chain not checked."},
                "persistence": {
                    "line": "1 provisional source-persistence cluster.",
                    "loud_count": 0,
                    "provisional_count": 1,
                },
            },
            "open_actions": {
                "line": "Open action backlog: 1 open; oldest 3 trading day(s).",
                "count": 1,
            },
            "recommendations": ["Resolve oldest open action."],
        },
    }


def test_generated_html_labels_summary_export_and_dark_lanes():
    html = generate_html(_feed())

    assert "Summary/export view" in html
    assert "not an all-clear read" in html
    assert "No Today" in html and "Actions are shown" in html
    assert "Lane status" in html
    assert "Research Queue" in html
    assert "not checked" in html
    assert "checked (18)" in html


def test_generated_html_surfaces_feedback_context():
    html = generate_html(_feed())

    assert "Feedback loops" in html
    assert "Source-call scoring: 1 overdue." in html
    assert "Open action backlog: 1 open" in html
    assert "Resolve oldest open action." in html


def test_generated_html_is_ascii_display_safe():
    html = generate_html(_feed())

    assert html.isascii()
    for artifact in ("Ã", "â", "Â", "ðŸ"):
        assert artifact not in html
