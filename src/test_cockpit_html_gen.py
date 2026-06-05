"""Tests for the generated HTML summary/export dashboard."""
import json
import os
import subprocess
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
                "items": [{"ticker": "ANET", "age_days": 3, "source": "lean_in"}],
            },
            "recommendations": ["Resolve oldest open action."],
        },
        "target_drift": {
            "rows": [
                {"ticker": "NVDA", "direction": "UNDERSIZED", "actual_pct": 6.6, "target_pct": 12.0}
            ]
        },
        "prospects": {
            "sell_fast": [
                {"ticker": "DE", "direction": "avoid", "summary": "DE: sell-pressure building."}
            ]
        },
        "radar": [
            {"ticker": "JETS", "direction": "long", "author": "Newton", "date": "2026-06-05"}
        ],
        "bullish_flow": {
            "rows": [
                {"ticker": "BMNR", "direction": "bullish", "strength": "strong", "signal_types": ["sweep"]}
            ]
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
    assert "ANET" in html
    assert "3d open | lean_in" in html
    assert "python src/action_memory_resolve.py --ticker ANET --status deferred --reason &quot;keep watching&quot;" in html
    assert "Resolve oldest open action." in html


def test_generated_html_surfaces_operator_status_card():
    html = generate_html(_feed())

    assert "Operator status" in html
    assert "Today actions" in html
    assert "Open reviews" in html
    assert "Source lanes" in html
    assert "Source calls" in html
    assert "python src/go_live_checklist.py --format text" in html


def test_generated_html_surfaces_opportunity_context():
    html = generate_html(_feed())

    assert "Opportunity context" in html
    assert "context, not orders" in html
    assert "Target drift" in html
    assert "NVDA" in html
    assert "6.6% actual vs 12.0% target" in html
    assert "Prospects" in html
    assert "DE: sell-pressure building." in html
    assert "Radar" in html
    assert "JETS" in html
    assert "Bullish flow" in html
    assert "BMNR" in html


def test_generated_html_is_ascii_display_safe():
    html = generate_html(_feed())

    assert html.isascii()
    for artifact in ("Ã", "â", "Â", "ðŸ"):
        assert artifact not in html


def test_cockpit_html_gen_cli_writes_output(tmp_path):
    feed_path = tmp_path / "feed.json"
    out_path = tmp_path / "dashboard.html"
    feed_path.write_text(json.dumps(_feed()), encoding="utf-8")
    script = os.path.join(os.path.dirname(__file__), "cockpit_html_gen.py")

    proc = subprocess.run(
        [sys.executable, script, str(feed_path), "--out", str(out_path)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    html = out_path.read_text(encoding="utf-8")
    assert "Summary/export view" in html
    assert "Lane status" in html
