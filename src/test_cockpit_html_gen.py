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
        "uw_action_runbook": {
            "status": "has_data",
            "line": "UW action runbook: 2 check set(s), 3 scoped ticker(s); endpoint results not claimed.",
            "command": "python src/uw_action_runbook.py --feed src/latest_cockpit_feed.json --format text",
            "honesty_rule": "Runbook recommends UW checks from dashboard state only; it is not proof any endpoint was fetched.",
            "rows": [
                {
                    "mode": "event_risk_political_macro",
                    "label": "Event-risk and political macro",
                    "priority": 1,
                    "why": "Active event-risk lane can overpower normal thesis and flow signals.",
                    "ticker_scope": ["XOP", "TNX"],
                    "market_checks": ["MARKET_TIDE", "TOP_NET_IMPACT"],
                    "ticker_checks": ["NEWS_HEADLINES"],
                    "blocks_action_if": "same-session headlines are missing",
                    "promote_when": "macro tape confirms the risk",
                },
                {
                    "mode": "portfolio_reallocation",
                    "label": "Portfolio reallocation",
                    "priority": 2,
                    "why": "Sizing-gap actions need current exposure checks.",
                    "ticker_scope": ["NVDA"],
                    "market_checks": ["ETF_TIDE"],
                    "ticker_checks": ["TICKER_OHLC", "TICKER_FLOW_RECENT"],
                    "blocks_action_if": "latest positions are missing",
                    "promote_when": "current positions and live flow support the leg",
                },
            ],
        },
        "reallocation_brief": {
            "status": "test_data_only",
            "line": "Reallocation brief: test data only from 2026-05-31 positions; 2 add candidate(s), 1 funding trim(s); allocated $125,000; shortfall $10,000.",
            "honesty_rule": "Candidate reallocation brief only; no trades are executed and stale positions remain test-data only.",
            "command": "python src/reallocation_brief.py --feed src/latest_cockpit_feed.json --positions src/positions.json --format text",
            "funding": {
                "pool_total_usd": 150000,
                "allocated_usd": 125000,
                "shortfall_usd": 10000,
            },
            "blockers": [
                "positions snapshot 2026-05-31 is 6 day(s) old; use as test-data only until current positions are supplied",
                "same-session UW price/flow confirmation required before any capital action",
            ],
            "rows": [
                {
                    "ticker": "NVDA",
                    "notional_usd": 80000,
                    "sequence": "now",
                    "entry_note": "size now (constructive/ok entry)",
                    "funded_by": [{"ticker": "SMH", "notional_usd": 80000}],
                    "blockers": ["latest current positions", "same-session UW price/flow"],
                    "disconfirmation": "live flow/price argues for waiting",
                }
            ],
            "trims": [
                {
                    "ticker": "SMH",
                    "notional_usd": 80000,
                    "funds": [{"ticker": "NVDA", "notional_usd": 80000}],
                }
            ],
        },
        "source_audits": {
            "cloud_routines": {
                "line": "Background cloud proof: 2/10 scheduled receipts proven; failed latest=0.",
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
            "uw_routing": {
                "line": "UW routing: 2 scenario profile(s) recommended; top=Event-risk and political macro.",
                "rows": [
                    {
                        "label": "Event-risk and political macro",
                        "reason": "Active event-risk lane can overpower normal thesis and flow signals.",
                        "top_endpoints": ["MARKET_TIDE", "TOP_NET_IMPACT"],
                    },
                    {
                        "label": "Portfolio reallocation",
                        "reason": "Sizing-gap actions need current exposure checks.",
                        "top_endpoints": ["TICKER_OHLC", "ETF_TIDE"],
                    },
                ],
            },
            "uw_action_runbook": {
                "line": "UW action runbook: 2 check set(s), 3 scoped ticker(s); endpoint results not claimed.",
            },
            "fundstrat": {
                "line": "Fundstrat intake: 4 full-body, 1 snippet-only, 0 daily calls, 3 stored source-call candidates.",
            },
            "notion_writeback": {
                "line": "Notion/writeback audit: 2 repo cache write(s) proven; connector writes must be verified by routine receipts when used.",
            },
            "notion_collision": {
                "line": "Notion collision audit: verify live shared pages before trusting repo caches.",
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
                "line": "Open action backlog: 1 open; 1 due; 0 stale; oldest 3 trading day(s).",
                "count": 1,
                "due_count": 1,
                "stale_count": 0,
                "items": [{
                    "ticker": "ANET",
                    "age_days": 3,
                    "source": "lean_in",
                    "review_label": "review due",
                    "cleanup_priority": "medium",
                    "next_step": "Review soon: act, invalidate, ignore, or explicitly defer.",
                }],
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
        "operator_hardening": {
            "freshness_downgrades": {
                "line": "Freshness downgrade audit: 1 action(s) require re-check before capital action.",
                "rows": [{
                    "ticker": "QQQ",
                    "what": "Re-check QQQ support before acting",
                    "judgment": "Re-check before capital action.",
                    "evidence_date": "2026-06-05",
                    "action_state": "WATCH",
                }],
            },
            "stale_action_cleanup": {
                "line": "Stale-action cleanup: 1 due/stale open review(s).",
                "rows": [{
                    "ticker": "ANET",
                    "kind": "review",
                    "age_days": 3,
                    "state": "due",
                    "next_step": "Review due item before it becomes stale.",
                }],
            },
            "condition_checklist": {
                "line": "Condition checklist: 1 pre-action level/headline check(s).",
                "rows": [{
                    "source": "fundstrat_daily",
                    "ticker": "SOX",
                    "date": "2026-06-05",
                    "title": "SOX support",
                    "check": "Check support before adding.",
                }],
            },
            "watch_only_why": {
                "line": "Why-not-acting lane: 1 watch-only signal(s) kept out of trade prompts.",
                "rows": [{
                    "source": "signal_log",
                    "ticker": "NVDA",
                    "title": "AI leadership remains narrow",
                    "why_not_acting": "Signal Log is watch-only context.",
                }],
            },
        },
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
        "disconfirmation": {
            "summary": "Do not act if the funding leg makes risk worse.",
            "invalidates_if": ["The target weight is outdated."],
            "confirm_before_acting": ["Run the pre-trade gate."],
            "downgrade_to": "Re-check Before Acting",
        },
        "capital_efficiency": {
            "label": "compare and stage",
            "summary": "Do not park capital here only because it is good; compare it against higher-ranked uses and funding legs.",
            "timing_balance": "Avoid waiting for a perfect bottom; if live checks confirm, consider staged exposure rather than all-or-nothing timing.",
            "compare_against": ["higher-ranked Key Now actions", "funded reallocation legs"],
        },
    }]

    html = generate_html(feed)

    assert 'id="today-actions"' in html
    assert "1 ranked item; no auto-trade" in html
    assert "Conviction gap: NVDA is under target" in html
    assert "Target drift shows a 5.4pp sizing gap" in html
    assert "Key Now" in html
    assert "Why this matters" in html
    assert "Fresh enough for a decision prompt." in html
    assert "What could make this wrong?" in html
    assert "Do not act if the funding leg makes risk worse." in html
    assert "Run the pre-trade gate." in html
    assert "capital: compare and stage" in html
    assert "Capital efficiency" in html
    assert "Do not park capital here only because it is good" in html
    assert "Avoid waiting for a perfect bottom" in html
    assert "Compare against: higher-ranked Key Now actions / funded reallocation legs" in html
    assert html.index('id="today-actions"') < html.index('id="operator-status"')


def test_generated_html_surfaces_feedback_context():
    html = generate_html(_feed())

    assert "Feedback loops" in html
    assert "Source-call scoring: 1 overdue." in html
    assert "Open action backlog: 1 open; 1 due; 0 stale" in html
    assert "ANET" in html
    assert "3d open | review due | medium priority | lean_in" in html
    assert "Review soon: act, invalidate, ignore, or explicitly defer." in html
    assert "python src/action_memory_resolve.py --ticker ANET --status deferred --reason &quot;keep watching&quot;" in html
    assert "Resolve oldest open action." in html


def test_generated_html_surfaces_operator_status_card():
    html = generate_html(_feed())

    assert "Operator status" in html
    assert "Today actions" in html
    assert "Open reviews" in html
    assert 'operator-value operator-warn">1 due</div>' in html
    assert "Source lanes" in html
    assert "Source calls" in html
    assert "Live fetch" in html
    assert "Build blockers" in html
    assert "Blocked" in html
    assert "background cloud proof 2/10" in html
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


def test_generated_html_keeps_new_open_reviews_visible_without_warning():
    feed = _feed()
    feed["feedback"]["open_actions"] = {
        "line": "Open action backlog: 2 open; 0 due; 0 stale; oldest 0 trading day(s).",
        "count": 2,
        "oldest_age_days": 0,
        "due_count": 0,
        "stale_count": 0,
        "items": [
            {
                "ticker": "ANET",
                "age_days": 0,
                "source": "lean_in",
                "review_label": "new",
                "cleanup_priority": "low",
                "next_step": "Keep visible; no cleanup pressure yet.",
            }
        ],
    }

    html = generate_html(feed)

    assert 'operator-value operator-pass">2 new</div>' in html
    assert "Open action backlog: 2 open; 0 due; 0 stale" in html
    assert "0d open | new | lean_in" in html


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
    assert "background cloud proof 2/10" in html
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


def test_opportunity_context_radar_prefers_latest_rows():
    feed = _feed()
    feed["radar"] = [
        {"ticker": "XOP", "direction": "avoid", "author": "Newton", "date": "2026-06-03"},
        {"ticker": "RYF", "direction": "avoid", "author": "Newton", "date": "2026-06-03"},
        {"ticker": "QQQ", "direction": "watch", "author": "Newton", "date": "2026-06-05"},
        {"ticker": "SOX", "direction": "watch", "author": "Newton", "date": "2026-06-05"},
        {"ticker": "RSP", "direction": "watch", "author": "Newton", "date": "2026-06-05"},
    ]

    html = generate_html(feed)
    radar_section = html[html.index("Radar"):html.index("Bullish flow")]

    assert "QQQ" in radar_section
    assert "SOX" in radar_section
    assert "RSP" in radar_section
    assert "XOP" not in radar_section


def test_generated_html_surfaces_new_audit_and_missing_feed_blocks():
    html = generate_html(_feed())

    assert 'id="asymmetric-opportunities"' in html
    assert 'href="#operator-hardening"' in html
    assert 'id="operator-hardening"' in html
    assert "Freshness downgrades" in html
    assert "Stale-action cleanup" in html
    assert "Pre-action condition checklist" in html
    assert "Why not acting" in html
    assert "Re-check QQQ support before acting" in html
    assert "Check support before adding." in html
    assert "Asymmetric opportunities" in html
    assert "High-conviction target gap" in html
    assert 'id="uw-action-runbook"' in html
    assert "UW action runbook: 2 check set" in html
    assert "Event-risk and political macro" in html
    assert "TICKER_FLOW_RECENT" in html
    assert "checks, not proof" in html
    assert 'id="reallocation-brief"' in html
    assert "Candidate reallocation brief" in html
    assert "positions snapshot 2026-05-31" in html
    assert "add $80,000" in html
    assert "Funding trims" in html
    assert "SMH $80,000 -&gt; NVDA $80,000" in html
    assert 'id="source-audits"' in html
    assert "Background cloud proof: 2/10 scheduled receipts proven" in html
    assert "Fundstrat intake: 4 full-body" in html
    assert "UW routing: 2 scenario profile" in html
    assert "UW next checks" in html
    assert "MARKET_TIDE" in html
    assert "Notion/writeback audit" in html
    assert "Notion collision audit" in html
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
