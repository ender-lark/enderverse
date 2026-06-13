"""Tests for the generated HTML summary/export dashboard."""
import copy
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cockpit_html_gen
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
        "market_open_packet": {
            "status": "recheck_first",
            "line": "Market-open packet: 1 key, 1 re-check, 0 backlog; 2 blocker(s).",
            "counts": {"key_now": 1, "recheck": 1, "backlog": 0, "blockers": 2},
            "honesty_rule": "Decision packet sequences review work only; it does not execute or recommend un-gated trades.",
            "rows": [
                {
                    "priority": 1,
                    "kind": "recheck_first",
                    "label": "Re-check first: EVENT: Oil/rates shock can change new-buy timing",
                    "why": "Fast-moving tape; same-session confirmation required.",
                    "next_step": "Refresh WTI, 10Y, and current headlines.",
                    "blocks": "Do not act until fast-moving evidence is fresh.",
                    "source": "event_risk",
                    "refresh_status": "changed_recheck",
                    "freshness_label": "fast-moving",
                    "evidence_date": "2026-06-05",
                    "last_checked": "2026-06-05",
                    "decay_window": "intraday",
                    "key_assumptions": "evidence 2026-06-05 is fast-moving; decays intraday",
                    "invalidates": "Headlines de-escalate or yields reverse.",
                    "do_nothing_risk": "Doing nothing can leave new buys mistimed.",
                    "capital_priority_reason": "Protection and timing risk outrank new adds while the shock is unresolved.",
                    "capital_priority_score": 104,
                    "compare_against": "higher-ranked Key Now actions / risk reduction",
                }
            ],
        },
        "alert_policy": {
            "status": "quiet",
            "line": "Push alerts: quiet - no market/action item qualifies for notification.",
            "policy": "Push alerts only interrupt for action-changing market, portfolio, Fundstrat, stale-review, or invalidated-decision items. Routine/system-health warnings stay in Ops.",
            "delivery": "review_only_no_send",
            "rows": [],
            "system_health": [
                {
                    "severity": "warn",
                    "kind": "cloud_routine_failed",
                    "title": "1 cloud routine(s) failed latest receipt",
                    "why": "Background cloud proof: 12/14 scheduled receipts proven; failed latest=1.",
                    "next_step": "Check Ops/System Health when debugging routines; this is not a portfolio alert.",
                }
            ],
            "suppressed": [
                {
                    "reason": "background_cloud_proof",
                    "count": 4,
                    "why": "Natural-schedule proof gaps are monitored in the dashboard, not alerted unless failed/overdue.",
                }
            ],
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
        "social_watch": {
            "status": "has_data",
            "line": "Social watch: 1 anomaly candidate(s); watch-only until independently confirmed.",
            "count": 1,
            "honesty_rule": "Watch-only until independently confirmed; never a standalone trade signal.",
            "promotion_rule": "Key Now is allowed only when Reddit is not primary evidence and same-day UW, price/news, Fundstrat, catalyst, or source-call evidence confirms the setup.",
            "command": "python src/social_watch.py --cache src/social_watch.json --format text",
            "rows": [
                {
                    "ticker": "NVDA",
                    "score": 34,
                    "summary": "Reddit channel-check rumor needs vetting.",
                    "subreddits": ["stocks", "wallstreetbets"],
                    "evidence": ["Blackwell lead time"],
                    "independent_confirmation": ["UW flow pending"],
                    "escalation": "Re-check Before Acting candidate",
                    "risk": "Pump/chase and echo risk.",
                }
            ],
        },
        "uw_action_runbook": {
            "status": "has_data",
            "line": "UW action runbook: 2 check set(s), 3 scoped ticker(s); endpoint results not claimed.",
            "command": "python src/uw_action_runbook.py --feed src/latest_cockpit_feed.json --format text",
            "honesty_rule": "Runbook recommends UW checks from dashboard state only; it is not proof any endpoint was fetched.",
            "endpoint_proof": {
                "status": "not_checked",
                "line": "UW endpoint proof: no captured endpoint result proof; runbook remains instructions only.",
                "blockers": ["captured UW endpoint results are missing"],
            },
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
            "uw_endpoint_proof": {
                "line": "UW endpoint proof: no captured endpoint result proof; runbook remains instructions only.",
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
        "uw_endpoint_proof": {
            "status": "not_checked",
            "line": "UW endpoint proof: no captured endpoint result proof; runbook remains instructions only.",
            "blockers": ["captured UW endpoint results are missing"],
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
            "caveat": "SnapTrade direct rows; ETF look-through is separate.",
            "snapshot_date": "2026-06-07",
            "allocation_guidance": {
                "working_model": "default_working_model",
                "basis": "visual guidance only; not an instruction to trade",
                "fundstrat_source_date": "2026-05-28",
            },
            "views": {
                "combined": {
                    "total_value": 120000,
                    "categories": [{
                        "category": "AI / Semiconductors",
                        "market_value": 120000,
                        "pct": 100,
                        "tickers": ["NVDA", "SMH"],
                        "working_model_target_pct": 32.0,
                        "working_model_gap_pct": -68.0,
                        "fundstrat_cue": "favored",
                        "fundstrat_source_date": "2026-05-28",
                        "fundstrat_reason": "Fundstrat what-to-own/top-bottom cue",
                    }],
                    "rows": [
                        {"ticker": "NVDA", "description": "NVIDIA", "account": "Fidelity Individual", "owner": "SKB", "category": "AI / Semiconductors", "shares": 10, "market_value": 100000, "pct": 83.3},
                        {"ticker": "SMH", "description": "VanEck Semiconductor ETF", "account": "Schwab Trust", "owner": "Parents", "category": "AI / Semiconductors", "shares": 20, "market_value": 20000, "pct": 16.7},
                    ],
                },
                "skb": {
                    "total_value": 80000,
                    "categories": [{
                        "category": "AI / Semiconductors",
                        "market_value": 80000,
                        "pct": 100,
                        "tickers": ["NVDA"],
                        "working_model_target_pct": 32.0,
                        "working_model_gap_pct": -68.0,
                        "fundstrat_cue": "favored",
                        "fundstrat_source_date": "2026-05-28",
                    }],
                    "rows": [{"ticker": "NVDA", "account": "Fidelity Individual", "owner": "SKB", "market_value": 80000, "pct": 100}],
                },
                "parents": {
                    "total_value": 20000,
                    "categories": [{
                        "category": "AI / Semiconductors",
                        "market_value": 20000,
                        "pct": 100,
                        "tickers": ["SMH"],
                        "working_model_target_pct": 32.0,
                        "working_model_gap_pct": -68.0,
                        "fundstrat_cue": "favored",
                        "fundstrat_source_date": "2026-05-28",
                    }],
                    "rows": [{"ticker": "SMH", "account": "Schwab Trust", "owner": "Parents", "market_value": 20000, "pct": 100}],
                },
            }
        },
    }


def test_generated_html_labels_summary_export_and_dark_lanes():
    html = generate_html(_feed())

    assert "Action-first dashboard view" in html
    assert "not an all-clear read" in html
    assert "No Today" in html and "Actions are shown" in html
    assert 'href="#today-actions"' in html
    assert 'href="#lane-status"' in html
    assert "Lane status" in html
    assert "Research Queue" in html
    assert "not checked" in html
    assert "checked (18)" in html


def test_generated_html_hero_uses_packet_attention_state():
    html = generate_html(_feed())

    assert "1 key review prompt ready" in html
    assert "Start with the Market-Open Packet; run gates before capital moves." in html
    assert "No decisions need attention" not in html


def test_generated_html_book_renders_allocation_guidance():
    html = generate_html(_feed())

    assert "Allocation guide: working model target + Fundstrat cue" in html
    assert "visual guidance only; not an instruction to trade" in html
    assert "model target 32.0% | gap -68.0pp" in html
    assert "Fundstrat favored | 2026-05-28" in html


def test_generated_html_treats_social_watch_as_deferred_optional_lane():
    feed = copy.deepcopy(_feed())
    feed["lane_status"] = {
        "counts": {
            "has_data": 3,
            "checked_clear": 2,
            "not_checked": 1,
            "stale": 0,
            "failed": 0,
        },
        "rows": [
            {
                "key": "social_watch",
                "label": "Social Watch",
                "status": "not_checked",
                "detail": "queued optional lane",
                "next_step": "Keep visible as not checked until social integration is enabled.",
                "count": 0,
            }
        ],
    }
    feed["live_source_config"] = {
        "configured": True,
        "configured_count": 1,
        "total_count": 1,
        "missing_count": 0,
        "missing": [],
    }
    feed["source_audits"]["cloud_routines"] = {
        "line": "Background cloud proof: 10/10 scheduled receipts proven; failed latest=0.",
        "scheduled_success_count": 10,
        "expected_count": 10,
        "missing_scheduled_success": [],
    }
    feed["feedback"]["source_calls"] = {
        "status": "checked_clear",
        "observed_count": 0,
        "pending_count": 0,
        "overdue_count": 0,
        "calibration": {"line": "No source calls pending."},
        "persistence": {"line": "No active persistence clusters.", "loud_count": 0, "provisional_count": 0},
    }
    feed["feedback"]["open_actions"] = {
        "line": "Open action backlog: clear.",
        "count": 0,
        "due_count": 0,
        "stale_count": 0,
        "items": [],
    }

    html = generate_html(feed)

    assert "Core source lanes are clear; 1 queued optional lane remains visible as not checked." in html
    assert "<strong>1 deferred</strong> source lanes" in html
    assert "Operator status" in html
    assert "PASS" in html
    assert "1 deferred" in html
    assert "not an all-clear read" not in html


def test_generated_html_surfaces_overdue_cloud_receipts():
    feed = copy.deepcopy(_feed())
    feed["source_audits"]["cloud_routines"] = {
        "line": "Background cloud proof: 0/1 scheduled receipts proven; failed latest=0; overdue=1.",
        "scheduled_success_count": 0,
        "expected_count": 1,
        "failed_latest_count": 0,
        "overdue_count": 1,
        "overdue": [{
            "routine_id": "investing-os-post-close-refresh",
            "routine_name": "Investing OS Post-Close Refresh",
            "last_ran_label": "never",
            "overdue_line": "overdue: Investing OS Post-Close Refresh, last ran never",
        }],
        "missing_scheduled_success": [],
    }

    html = generate_html(feed)

    assert "Cloud routine overdue" in html
    assert "overdue: Investing OS Post-Close Refresh, last ran never" in html
    assert "Overdue cloud receipts" in html


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
            "priority_reason": "Sizing gap beats ordinary research only if the gate still works.",
            "do_nothing_risk": "Doing nothing could leave NVDA too small if the gate confirms.",
            "timing_balance": "Avoid waiting for a perfect bottom; if live checks confirm, consider staged exposure rather than all-or-nothing timing.",
            "compare_against": ["higher-ranked Key Now actions", "funded reallocation legs"],
        },
        "synthesis_changes": "size",
        "capital_priority_score": 117,
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
    assert "changes: size" in html
    assert "priority: 117" in html
    assert "Capital efficiency" in html
    assert "Do not park capital here only because it is good" in html
    assert "Priority: Sizing gap beats ordinary research only if the gate still works." in html
    assert "Do nothing: Doing nothing could leave NVDA too small if the gate confirms." in html
    assert "Avoid waiting for a perfect bottom" in html
    assert "Compare against: higher-ranked Key Now actions / funded reallocation legs" in html
    assert "action action-act tone-red" in html
    assert html.index('id="today-actions"') < html.index('id="operator-status"')


def test_generated_html_surfaces_market_open_packet_before_actions():
    feed = _feed()
    feed["actions"] = [{
        "rank": 1,
        "ticker": "NVDA",
        "kind": "conviction_gap",
        "action_state": "WATCH",
        "action_label": "SIZE GAP",
        "confidence": "High",
        "goal_impact": "High",
        "what": "NVDA is under target",
        "your_move": "Gate before sizing.",
        "why": "Position is below target.",
        "source": "target_drift",
        "decision_group": "key_now",
        "decision_group_label": "Key Now",
    }]
    html = generate_html(feed)

    assert 'href="#market-open-packet"' in html
    assert 'id="market-open-packet"' in html
    assert "Market-open packet" in html
    assert "Market-open packet: 1 key, 1 re-check, 0 backlog; 2 blocker(s)." in html
    assert "Re-check first: EVENT: Oil/rates shock can change new-buy timing" in html
    assert "Priority: 104" in html
    assert "Freshness: fast-moving | evidence 2026-06-05 | checked 2026-06-05 | decays intraday" in html
    assert "small-item tone-amber" in html
    assert "tag t-amber" in html
    assert "Assumptions: evidence 2026-06-05 is fast-moving; decays intraday" in html
    assert "Capital priority: Protection and timing risk outrank new adds while the shock is unresolved." in html
    assert "Do nothing: Doing nothing can leave new buys mistimed." in html
    assert "Invalidates: Headlines de-escalate or yields reverse." in html
    assert "Decision packet sequences review work only" in html
    assert "python src/market_open_packet.py --feed src/latest_cockpit_feed.json --format text" in html
    assert html.index('id="market-open-packet"') < html.index('id="today-actions"')


def test_generated_html_surfaces_source_conflicts_after_actions():
    feed = _feed()
    feed["actions"] = [{
        "rank": 1,
        "ticker": "HYPE",
        "kind": "lean_in",
        "action_state": "WATCH",
        "confidence": "Medium",
        "what": "Watch HYPE split",
    }]
    feed["source_conflicts"] = {
        "status": "has_data",
        "count": 1,
        "honesty_rule": "Conflicts downgrade action posture; they do not create buy/sell execution.",
        "rows": [{
            "ticker": "HYPE",
            "scope": "same_source",
            "label": "same-source split",
            "bull_read": "Lee macro is constructive.",
            "bear_read": "Crypto analyst says setup is fragile.",
            "action_posture": "Hold - same-source split (Lee vs Farrell); no add until it resolves.",
            "decision_effect": "Re-check before adding or resizing; this is a hold/no-add conflict flag, not a trade.",
        }],
    }

    html = generate_html(feed)

    assert 'id="source-conflicts"' in html
    assert "Source conflicts" in html
    assert "Lee macro is constructive" in html
    assert "Crypto analyst says setup is fragile" in html
    assert "no add until it resolves" in html
    assert html.index('id="today-actions"') < html.index('id="source-conflicts"')


def test_generated_html_surfaces_system_health_instead_of_push_alert_noise():
    html = generate_html(_feed())

    assert "System health" in html
    assert "No push alert. System warning is visible for Ops review only." in html
    assert "1 cloud routine(s) failed latest receipt" in html
    assert "this is not a portfolio alert" in html
    assert "python src/alert_policy.py --feed src/latest_cockpit_feed.json --format text" in html


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


def test_generated_html_surfaces_social_watch_as_watch_only():
    html = generate_html(_feed())

    assert 'id="social-watch"' in html
    assert "Social Watch" in html
    assert "watch-only until independently confirmed" in html
    assert "Reddit channel-check rumor needs vetting." in html
    assert "Re-check Before Acting candidate" in html
    assert "never a standalone trade signal" in html
    assert "Key Now is allowed only when Reddit is not primary evidence" in html
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

    assert 'id="opportunity-context"' in html
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


def test_generated_html_prioritizes_prospects_and_pushes_social_to_bottom():
    feed = _feed()
    feed["actions"] = [{
        "rank": 1,
        "ticker": "NVDA",
        "kind": "conviction_gap",
        "action_state": "WATCH",
        "confidence": "High",
        "goal_impact": "High",
        "what": "NVDA is under target",
        "your_move": "Gate before sizing.",
        "decision_group": "key_now",
        "decision_group_label": "Key Now",
    }]
    html = generate_html(feed)

    assert 'href="#opportunity-context"' in html
    assert html.index('href="#opportunity-context"') < html.index('href="#social-watch"')
    assert html.index('id="today-actions"') < html.index('id="opportunity-context"')
    assert html.index('id="opportunity-context"') < html.index('id="operator-status"')
    assert html.index('id="social-watch"') > html.index('id="portfolio-views"')


def test_generated_html_has_collapsible_dashboard_cards():
    html = generate_html(_feed())

    assert ".card.is-collapsible.is-collapsed" in html
    assert "function setupCollapsibleCards()" in html
    assert "card-mini" in html
    assert "const keepOpen = new Set([]);" in html


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
    assert "endpoint proof not_checked" in html
    assert "runbook remains instructions only" in html
    assert "Proof blocker: captured UW endpoint results are missing" in html
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
    assert "UW endpoint proof: no captured endpoint result proof" in html
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


def test_book_tab_renders_full_account_portfolio_rows():
    feed = _feed()
    feed["portfolio_views"]["views"]["combined"]["rows"] = [
        {
            "ticker": f"TICK{i:02d}",
            "description": f"Position {i}",
            "account": "SnapTrade Account",
            "owner": "SKB",
            "category": "Test Sleeve",
            "shares": i + 1,
            "market_value": 1000 + i,
            "pct": i,
        }
        for i in range(10)
    ]

    html = generate_html(feed)

    assert 'id="tab-book"' in html
    assert "Account portfolio source" in html
    assert "Combined account portfolio" in html
    assert "10 direct rows" in html
    assert "TICK09" in html
    assert "SKB account portfolio" in html
    assert "Parents account portfolio" in html
    assert "No conviction-book data" in html


def _write_account_positions(path, snapshot_date="2026-06-12"):
    path.write_text(json.dumps({
        "snapshot_date": snapshot_date,
        "sleeve_value": 100000,
        "account_positions": [
            {
                "ticker": "AVGO",
                "description": "Broadcom Inc.",
                "shares": 40,
                "market_value": 30000,
                "account": "Parents Fidelity",
                "owner": "Parents",
                "broker": "Fidelity",
                "tracked": False,
                "asset_type": "Common Stock",
            },
            {
                "ticker": "AVGO",
                "description": "Broadcom Inc.",
                "shares": 10,
                "market_value": 10500,
                "account": "SKB Robinhood",
                "owner": "SKB",
                "broker": "Robinhood",
                "tracked": False,
                "asset_type": "Common Stock",
            },
            {
                "ticker": "NVDA",
                "description": "NVIDIA Corporation",
                "shares": 5,
                "market_value": 5000,
                "account": "Parents Fidelity",
                "owner": "Parents",
                "broker": "Fidelity",
                "tracked": True,
                "asset_type": "Common Stock",
            },
        ],
        "combined_positions": [
            {
                "ticker": "AVGO",
                "shares": 50,
                "market_value": 40500,
                "account": "Multiple",
                "owners": ["Parents", "SKB"],
                "tracked": False,
            },
            {
                "ticker": "NVDA",
                "shares": 5,
                "market_value": 5000,
                "account": "Parents Fidelity",
                "owners": ["Parents"],
                "tracked": True,
            },
        ],
        "tracked_combined_positions": [
            {"ticker": "NVDA", "shares": 5, "market_value": 5000, "tracked": True}
        ],
    }), encoding="utf-8")


def test_holdings_tab_renders_all_positions_with_tracking_and_drilldown(tmp_path, monkeypatch):
    positions_path = tmp_path / "account_positions.json"
    _write_account_positions(positions_path)
    monkeypatch.setattr(cockpit_html_gen, "ACCOUNT_POSITIONS_PATH", positions_path)
    feed = _feed()
    feed["generated_at"] = "2026-06-12T19:05:31+00:00"

    html = generate_html(feed)

    assert 'showTab(\'holdings\',this)' in html
    assert 'id="tab-holdings"' in html
    assert 'class="tab-badge">1</span>' in html
    assert "2</strong> tickers" in html
    assert "3</strong> account rows" in html
    assert "AVGO" in html
    assert "$40,500" in html
    assert "40.5%" in html
    assert "2 accounts" in html
    assert "UNTRACKED" in html
    assert "Build log: untracked tickers in account_positions: AVGO" in html
    assert "NVDA" in html
    assert "TRACKED" in html


def test_holdings_tab_fail_soft_for_missing_or_stale_positions(tmp_path, monkeypatch):
    missing_path = tmp_path / "missing_account_positions.json"
    monkeypatch.setattr(cockpit_html_gen, "ACCOUNT_POSITIONS_PATH", missing_path)

    html = generate_html(_feed())

    assert "Holdings not checked" in html
    assert "account positions file missing" in html

    positions_path = tmp_path / "account_positions.json"
    _write_account_positions(positions_path, snapshot_date="2026-06-10")
    monkeypatch.setattr(cockpit_html_gen, "ACCOUNT_POSITIONS_PATH", positions_path)
    feed = _feed()
    feed["generated_at"] = "2026-06-12T19:05:31+00:00"

    stale_html = generate_html(feed)

    assert "STALE HOLDINGS" in stale_html
    assert "2 days old" in stale_html


def test_generated_html_commands_tab_surfaces_system_checks():
    html = generate_html(_feed())

    assert "System checks" in html
    assert "Current operating actions" in html
    assert "open dashboard" in html
    assert "review full book" in html
    assert "http://127.0.0.1:8765/dashboard_preview.html" in html
    assert "default operator dashboard" in html
    assert "SnapTrade book refresh" in html
    assert "python src/snaptrade_book_refresh.py --refresh-dashboard" in html
    assert "python src/live_dashboard_refresh.py" in html
    assert "go-live checklist" in html
    assert "python src/go_live_checklist.py --format text" in html
    assert "live status" in html
    assert "python src/live_status.py --format text" in html
    assert "Claude commands" not in html


def test_generated_html_surfaces_fundstrat_tab(tmp_path, monkeypatch):
    bible_path = tmp_path / "fundstrat_bible.json"
    bible_path.write_text(json.dumps({
        "deck_date": "2026-06-11",
        "layers_note": "Two-layer bible test note.",
        "core_stock_ideas_as_of": "2026-05-28",
        "sector_allocation": {
            "as_of": "2026-06-11",
            "source": "Fundstrat June 2026 Sector Allocation Update",
            "newton_rating_changes": [
                {"sector": "Health Care", "change": "Neutral -> Overweight", "why": "XHS breakout."}
            ],
            "agreement": {
                "both_overweight": ["Basic Materials", "Real Estate"],
                "both_underweight": ["Consumer Staples"],
                "note": "Different time horizons.",
            },
            "june_etf_basket": [
                {"ticker": "CIBR", "status": "new", "theme": "cybersecurity"}
            ],
            "may_basket_grade": "May basket graded.",
        },
        "what_to_own": ["MAG7", "Financials"],
        "top5": [{"ticker": "AMD", "name": "Advanced Micro Devices"}],
        "top5_smid": [{"ticker": "STRL", "name": "Sterling Infrastructure"}],
        "bottom5": [{"ticker": "DE", "name": "Deere"}],
        "bottom5_smid": [{"ticker": "ELF", "name": "e.l.f. Beauty", "report_move_pct": 5.97}],
        "source_file": "may.pdf",
    }), encoding="utf-8")
    monkeypatch.setattr(cockpit_html_gen, "FUNDSTRAT_BIBLE_PATH", bible_path)
    feed = _feed()
    feed["fundstrat_news"] = {
        "status": "has_data",
        "honesty_rule": "Monthly list membership is not an execution trigger.",
        "daily": {
            "latest_date": "2026-06-05",
            "count": 6,
            "freshness_judgment": "Daily calls are timing input.",
            "rows": [
                {"ticker": "QQQ", "date": "2026-06-05", "author": "Newton", "subject": "One", "action_implication": "re-check timing", "quote": "Support matters."},
                {"ticker": "RYF", "date": "2026-06-05", "author": "Newton", "subject": "Two", "quote": "Financials matter."},
                {"ticker": "EWRE", "date": "2026-06-05", "author": "Newton", "subject": "Three", "quote": "REITs matter."},
                {"ticker": "XHS", "date": "2026-06-05", "author": "Newton", "subject": "Four", "quote": "Health care matters."},
                {"ticker": "SPX", "date": "2026-06-05", "author": "Newton", "subject": "Five", "quote": "Breadth matters."},
                {"ticker": "CL", "date": "2026-06-05", "author": "Newton", "subject": "Six", "quote": "Should not render."},
            ],
        },
        "gaps": [
            {"key": "missing_smid_top5", "line": "Top 5 SMID is not present.", "next_step": "Re-read source."}
        ],
    }
    feed["if_i_were_you"] = {
        "line": "If I were you: 1 review priority item.",
        "honesty_rule": "Review only.",
        "rows": [
            {"rank": 1, "label": "Fix Fundstrat storage gaps", "posture": "research/store", "why": "SMID missing.", "what_i_would_do": "Backfill.", "source": "fundstrat_news"}
        ],
    }

    html = generate_html(feed)

    assert "Conviction Dashboard" in html
    assert 'showTab(\'fundstrat\',this)' in html
    assert 'id="tab-fundstrat"' in html
    assert ">FundStrat<" in html
    assert "FundStrat: sector allocation 2026-06-11; core stock ideas 2026-05-28; daily calls 6 latest 2026-06-05." in html
    assert "FundStrat Bible Layers" in html
    assert "Sector Allocation Layer" in html
    assert "Core Stock Ideas Layer" in html
    assert "Health Care: Neutral -&gt; Overweight" in html
    assert "Tactical Top 3 not captured" in html
    assert "Tactical Bottom 3 not captured" in html
    assert "Named levels not captured" in html
    assert "CIBR" in html
    assert "cybersecurity" in html
    assert "Deck 2026-06-11 | sector allocation 2026-06-11 | core stock ideas 2026-05-28" in html
    assert "Top 5 SMID" in html
    assert "Bottom 5 SMID" in html
    assert "AMD" in html
    assert "STRL" in html
    assert "DE" in html
    assert "ELF" in html
    assert "Latest Daily Notes" in html
    assert "showing latest 5 of 6" in html
    assert "Breadth matters." in html
    assert "Should not render." not in html
    assert "If I Were You" in html


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
    assert "Action-first dashboard view" in html
    assert "Lane status" in html
