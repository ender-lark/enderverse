import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from social_watch import build_social_watch, normalize_social_watch_row
from validators import validate_cockpit_feed


def test_social_watch_missing_cache_is_not_checked():
    block = build_social_watch(None)

    assert block["status"] == "not_checked"
    assert block["rows"] == []
    assert "not checked" in block["line"].lower()
    assert "never a standalone trade signal" in block["honesty_rule"]


def test_social_watch_normalizes_velocity_and_keeps_watch_only():
    block = build_social_watch(
        {
            "generated_at": "2026-06-07T12:00:00Z",
            "items": [
                {
                    "ticker": "NVDA",
                    "subreddit": "stocks",
                    "title_snippet": "NVDA Blackwell channel check rumor",
                    "mention_series": [2, 3, 2, 4, 3, 3, 2, 4, 3, 3, 19],
                    "evidence": ["Blackwell lead times"],
                    "independent_confirmation": ["news headline pending"],
                },
                {
                    "entity": "AI chips",
                    "summary": "Broad AI-chip chatter with no confirm.",
                    "mentions": 12,
                    "velocity_z": 1.5,
                },
            ],
        },
        material_tickers={"NVDA"},
    )

    assert block["status"] == "has_data"
    assert block["count"] == 2
    assert block["rows"][0]["ticker"] == "NVDA"
    assert block["rows"][0]["fired"] is True
    assert block["rows"][0]["escalation"] == "Re-check Before Acting candidate"
    assert "non-social confirmation" in block["rows"][0]["confirmation_required"]
    assert "Key Now" in block["promotion_rule"]


def test_social_watch_empty_supplied_cache_is_checked_clear():
    block = build_social_watch({"generated_at": "2026-06-07T12:00:00Z", "items": []})

    assert block["status"] == "checked_clear"
    assert block["count"] == 0
    assert "checked clear" in block["line"]


def test_social_watch_preserves_not_checked_cache_status():
    block = build_social_watch({
        "generated_at": "2026-06-07T12:00:00Z",
        "status": "not_checked",
        "line": "Social watch not checked: Reddit fetch failed.",
        "failures": [{"subreddit": "stocks", "error": "rate limited"}],
        "rows": [],
    })

    assert block["status"] == "not_checked"
    assert block["count"] == 0
    assert block["failures"][0]["subreddit"] == "stocks"
    assert "not checked" in block["line"].lower()


def test_social_watch_preserves_review_prompt_fields():
    row = normalize_social_watch_row({
        "ticker": "UUUU",
        "summary": "AI data-center nuclear demand chatter",
        "source_group": "critical_minerals_nuclear",
        "source_role": "specialized_catalyst_scout",
        "source_type": "ai_power_nuclear_narrative",
        "source_health_status": "thin_but_current",
        "source_interpretation_limit": "company/policy catalyst scout; verify outside Reddit",
        "signal_kind": "theme/research prompt",
        "usefulness": "medium",
        "destroy_reason": "",
        "why_it_matters": "Could change uranium/nuclear research priority.",
        "portfolio_implication": "Quiet Watch only until confirmed.",
        "confidence": "low scout",
        "decay_speed": "medium",
        "confirmation_needed": "Check filings, news, UW, price-volume.",
        "blocker_before_action": "No action from Reddit alone.",
        "suggested_next_check": "Verify with non-social sources.",
    })

    assert row["source_group"] == "critical_minerals_nuclear"
    assert row["source_role"] == "specialized_catalyst_scout"
    assert row["source_type"] == "ai_power_nuclear_narrative"
    assert row["source_health_status"] == "thin_but_current"
    assert row["signal_kind"] == "theme/research prompt"
    assert row["usefulness"] == "medium"
    assert row["why_it_matters"].startswith("Could change")
    assert row["portfolio_implication"] == "Quiet Watch only until confirmed."
    assert row["confirmation_needed"].startswith("Check filings")
    assert row["blocker_before_action"].startswith("No action")
    assert row["suggested_next_check"].startswith("Verify")


def test_social_watch_feed_contract_rejects_trade_escalation():
    row = normalize_social_watch_row({
        "ticker": "BMNR",
        "summary": "Social spike",
        "escalation": "buy",
    })
    feed = {
        "generated_at": "2026-06-07T12:00:00Z",
        "staleness": {},
        "hero": {},
        "macro": {},
        "fresh_signals": [],
        "holdings": [],
        "rotation": [],
        "social_watch": {"rows": [row]},
    }

    problems = validate_cockpit_feed(feed)
    assert any("social_watch" in problem and "direct trade" in problem for problem in problems)
