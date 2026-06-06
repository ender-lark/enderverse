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
        "action_decision_groups": {
            "sections": [
                {"key": "key_now", "label": "Key Now", "description": "current decisions", "count": 1, "ranks": [1]},
                {"key": "important_backlog", "label": "Important Backlog", "description": "still visible", "count": 0, "ranks": []},
            ],
            "counts": {"key_now": 1, "important_backlog": 0},
        },
        "asymmetric_opportunities": {
            "status": "has_data",
            "count": 1,
            "dedupe_rule": "One row per ticker.",
            "rows": [
                {
                    "ticker": "NVDA",
                    "source": "target_drift",
                    "score": 88,
                    "reason": "High-conviction target gap can make the thesis too small.",
                    "evidence": "UNDERSIZED vs target",
                    "decay_window": "until account/target changes",
                    "action": "review setup; no auto-trade",
                }
            ],
        },
        "source_audits": {
            "cloud_routines": {
                "line": "Cloud scheduled proof: 2/10 routines proven; failed latest=0.",
                "scheduled_success_count": 2,
                "expected_count": 10,
                "missing_scheduled_success": [
                    {"routine_name": "Morning Scan"},
                    {"routine_name": "Daily Synthesis"},
                ],
            },
            "connector_evidence": {
                "line": "Connector/supplied evidence: present=19/21; missing live-capable=1.",
            },
            "fundstrat": {
                "line": "Fundstrat intake: 4 full-body, 1 snippet-only, 0 daily calls, 3 stored source-call candidates.",
            },
            "notion_writeback": {
                "line": "Notion/writeback audit: 2 repo cache write(s) proven; connector writes must be verified by routine receipts when used.",
            },
        },
        "hero": {"hero": {"count": 0}, "needs_you": {"count": 0, "items": []}},
        "holdings": [],
        "lane_status": {
            "counts": {
                "has_data": 2,
                "checked_clear": 1,
                "not_checked": 4,
                "stale": 1,
                "failed": 0,
            },
            "rows": [
                {"key": "research", "label": "Research Queue", "status": "not_checked", "detail": "not supplied", "count": 0},
                {
                    "key": "account_positions",
                    "label": "Account Positions",
                    "status": "not_checked",
                    "detail": "missing live source input",
                    "next_step": "Supply src\\account_positions.json.",
                    "count": 0,
                },
                {"key": "uw_price", "label": "Prices", "status": "stale", "detail": "past freshness window", "count": 0},
                {"key": "portfolio", "label": "Portfolio", "status": "has_data", "detail": "checked", "count": 18},
            ],
        },
        "live_source_config": {
            "configured": False,
            "configured_count": 0,
            "total_count": 1,
            "missing_count": 1,
            "missing": [
                {
                    "key": "uw_api_key",
                    "label": "Unusual Whales API key",
                    "impact": "Live UW opportunity/parabolic fetches cannot run.",
                }
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
        "event_risk": [
            {
                "title": "Oil shock",
                "severity": "high",
                "channels": ["oil", "rates"],
                "tickers": ["XOP", "TNX"],
                "trigger": "WTI spike",
                "source": "Manual",
            }
        ],
        "fresh_signals": [
            {"ticker": "FN", "urgency": "watch", "what": "new_top5", "why": "Fresh Fundstrat Top 5.", "when": "2026-06-05"}
        ],
        "signal_log": [
            {"ticker": "NVDA", "signal": "AI leadership remains narrow", "source": "Morning Scan"}
        ],
        "research_actions": [
            {
                "rank": 1,
                "ticker": "AVGO",
                "kind": "research_review",
                "action_state": "RESEARCH",
                "action_label": "RESEARCH",
                "capital_effect": "review",
                "confidence": "Moderate",
                "goal_impact": "Medium",
                "goal_channels": ["conviction"],
                "goal_score": 50,
                "time_window": "1-2 weeks",
                "what": "Research AVGO thesis",
                "your_move": "Write the thesis before sizing.",
                "why": "Research queue needs decision-grade rationale.",
                "why_it_moves_goal": "Better thesis quality improves sizing.",
                "missing_evidence": ["decision-grade thesis"],
                "source": "research",
                "gate": None,
            }
        ],
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
        "portfolio_views": {
            "views": {
                "combined": {
                    "total_value": 120000,
                    "rows": [{"ticker": "NVDA"}, {"ticker": "SMH"}],
                },
                "skb": {
                    "total_value": 80000,
                    "rows": [{"ticker": "NVDA"}],
                },
            }
        },
    }


def test_generated_html_labels_summary_export_and_dark_lanes():
    html = generate_html(_feed())

    assert "Action-first summary view" in html
    assert "not an all-clear read" in html
    assert "No Today" in html and "Actions are shown" in html
    assert 'href="#today-actions"' in html
    assert 'href="#lane-status"' in html
    assert "Lane status" in html
    assert "Research Queue" in html
    assert "not checked" in html
    assert "checked (18)" in html


def test_generated_html_surfaces_action_cards_first():
    feed = _feed()
    feed["actions"] = [{
        "rank": 1,
        "ticker": "NVDA",
        "kind": "conviction_gap",
        "action_state": "ACT_NOW",
        "action_label": "SIZE GAP",
        "capital_effect": "review",
        "confidence": "High",
        "goal_impact": "High",
        "what": "Conviction gap: NVDA is under target",
        "your_move": "Decide whether to add, hold below target with a written reason, or cut the target.",
        "why": "Target drift shows a 5.4pp sizing gap vs the AI working model.",
        "source": "target_drift",
        "gate": {"preview": "size -> gate"},
        "goal_channels": ["sizing_gap", "conviction"],
        "goal_score": 85,
        "time_window": "1-3 trading days",
        "capital_effect": "review",
        "why_it_moves_goal": "A high-conviction target gap can make the right thesis too small.",
        "missing_evidence": ["funding leg"],
        "decision_group": "key_now",
        "decision_group_label": "Key Now",
        "freshness": "fresh: evidence 2026-06-05; decays until position, price, thesis, or target changes",
        "freshness_judgment": {
            "label": "fresh",
            "evidence_date": "2026-06-05",
            "decay_window": "until position, price, thesis, or target changes",
            "judgment": "Fresh enough for a decision prompt.",
        },
        "why_this_matters": "A high-conviction target gap can make the right thesis too small.",
    }]

    html = generate_html(feed)

    assert 'id="today-actions"' in html
    assert "1 ranked item; no auto-trade" in html
    assert "Conviction gap: NVDA is under target" in html
    assert "Target drift shows a 5.4pp sizing gap" in html
    assert "Key Now" in html
    assert "Why this matters" in html
    assert "Fresh enough for a decision prompt." in html
    assert html.index('id="today-actions"') < html.index('id="operator-status"')


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
    assert "Live fetch" in html
    assert "Build blockers" in html
    assert "Blocked" in html
    assert "cloud proof 2/10" in html
    assert "Live source configuration" in html
    assert "Unusual Whales API key" in html
    assert "Active event watch" in html
    assert "Oil shock" in html
    assert "HIGH | oil, rates | XOP, TNX" in html
    assert "Trigger: WTI spike" in html
    assert "1 overdue" in html
    assert "python src/completion_audit.py --format text" in html
    assert "python src/go_live_checklist.py --format text" in html
    assert "python src/sudden_event_refresh.py --title" in html


def test_generated_html_separates_waits_from_build_blockers():
    feed = _feed()
    feed["feedback"]["source_calls"] = {
        "status": "has_data",
        "pending_count": 0,
        "overdue_count": 0,
        "observed_count": 0,
    }
    feed["lane_status"]["counts"]["failed"] = 0

    html = generate_html(feed)

    assert "Build clear, not all clear" in html
    assert "operator-value operator-pass\">0</div>" in html
    assert "cloud proof 2/10" in html
    assert "source waits" in html


def test_generated_html_surfaces_dark_lane_validate_and_apply_commands():
    html = generate_html(_feed())

    assert "Account Positions template" in html
    assert "docs/manual_live_source_drop.template.json (shape only; fill a separate drop file)" in html
    assert "Account Positions validate" in html
    assert "python src/manual_source_drop.py manual-live-source-drop.json --src-dir src --validate-only" in html
    assert "Account Positions apply" in html
    assert "python src/manual_source_drop.py manual-live-source-drop.json --src-dir src" in html
    assert "&lt;manual-live-source-drop.json&gt;" not in html
    assert "Account Positions apply: python src/manual_source_drop.py docs/manual_live_source_drop.template.json" not in html


def test_generated_html_formats_utc_midnight_build_as_eastern_time():
    feed = _feed()
    feed["generated_at"] = "2026-06-06T00:03:00+00:00"

    html = generate_html(feed)

    assert "built 2026-06-05 20:03 ET" in html
    assert "built 2026-06-06 00:03 ET" not in html


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


def test_generated_html_surfaces_new_audit_and_missing_feed_blocks():
    html = generate_html(_feed())

    assert 'id="asymmetric-opportunities"' in html
    assert "Asymmetric opportunities" in html
    assert "High-conviction target gap" in html
    assert 'id="source-audits"' in html
    assert "Cloud scheduled proof: 2/10 routines proven" in html
    assert "Fundstrat intake: 4 full-body" in html
    assert "Notion/writeback audit" in html
    assert 'id="research-actions"' in html
    assert "Research AVGO thesis" in html
    assert 'id="fresh-signals"' in html
    assert "Fresh Fundstrat Top 5." in html
    assert 'id="signal-log"' in html
    assert "AI leadership remains narrow" in html
    assert 'id="portfolio-views"' in html
    assert "Portfolio views" in html
    assert "combined" in html
    assert "total $120,000" in html


def test_generated_html_commands_tab_surfaces_system_checks():
    html = generate_html(_feed())

    assert "System checks" in html
    assert "build audit" in html
    assert "python src/completion_audit.py --format text" in html
    assert "Current build blockers vs source/cloud/review waits" in html
    assert "go-live check" in html
    assert "python src/go_live_checklist.py --format text" in html
    assert "live status" in html
    assert "python src/live_status.py --format text" in html


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
    assert "Action-first summary view" in html
    assert "Lane status" in html
