import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from watch_interest import build_watch_interest_index, validate_watch_interest
from validators import validate_cockpit_feed
import cockpit_html_gen as chg


def test_manual_interest_cross_links_other_surfaces():
    payload = build_watch_interest_index(
        manual={
            "items": [{
                "ticker": "CISO",
                "aliases": ["Cerberus", "Cerberus Cyber Sentinel"],
                "interest_reason": "operator interest",
                "ambiguity": "could mean Cerebras",
            }]
        },
        top_prospects={"CISO": {"ticker": "CISO", "direction": "long", "urgency": "QUIET"}},
        research={"pending": [{"ticker": "CISO", "r": "research valuation", "pr": "low"}]},
        parabolic={"results": [{"ticker": "CISO", "surface_tier": "WATCHLIST", "score": 7.0}]},
        generated_at="2026-06-26T00:00:00Z",
    )

    row = payload["rows"][0]

    assert row["ticker"] == "CISO"
    assert row["manual_interest"] is True
    assert row["aliases"] == ["Cerberus", "Cerberus Cyber Sentinel"]
    assert row["ambiguity"] == "could mean Cerebras"
    assert {"manual_interest", "top_prospects", "research_queue", "parabolic_setups"} <= set(row["sources"])


def test_index_includes_non_manual_existing_lists():
    payload = build_watch_interest_index(
        manual={"items": [{"ticker": "CISO", "interest_reason": "operator interest"}]},
        theses=[{"ticker": "GOOGL", "stance": "ACTIVE", "tier": "T1", "lane": "Speed"}],
        account_positions={"account_positions": [{"ticker": "GOOGL", "market_value": 1234.56}]},
        feed={"lean_in": [{"ticker": "GOOGL", "headline": "Lean-in"}]},
        generated_at="2026-06-26T00:00:00Z",
    )

    googl = next(row for row in payload["rows"] if row["ticker"] == "GOOGL")

    assert googl["manual_interest"] is False
    assert googl["held_market_value"] == 1234.56
    assert {"theses", "account_positions", "feed.lean_in"} <= set(googl["sources"])


def test_watch_interest_rejects_trade_status():
    problems = validate_watch_interest({"items": [{"ticker": "CISO", "status": "buy"}]})

    assert any("must stay watch/research/interest" in problem for problem in problems)


def test_cockpit_feed_validates_watch_interest_block():
    feed = {
        "generated_at": "2026-06-26T00:00:00Z",
        "staleness": {"stamp": "test", "entries": [], "stale": []},
        "hero": {"count": 0, "names": [], "leading_sleeves": []},
        "fresh_signals": [],
        "holdings": [{
            "cat": "Test",
            "pos": [{
                "t": "GOOGL", "n": "Alphabet", "pct": 1.0, "st": "Owned",
                "cv": "Strong", "ty": "Core", "own": "s", "lock": "",
                "fresh": False, "cd": "flat", "cdNote": "", "nr": "Hold",
                "dr": [], "be": "AI spend slows",
            }],
        }],
        "rotation": [],
        "macro": {"line": "test", "regime": {}, "alerts": [], "implications": []},
        "watch_interest": {"rows": [{"ticker": "CISO", "status": "interest", "sources": ["manual_interest"]}]},
    }

    assert validate_cockpit_feed(feed) == []

    feed["watch_interest"]["rows"][0]["status"] = "buy"
    assert any("watch_interest" in problem and "direct trade" in problem for problem in validate_cockpit_feed(feed))


def test_opportunity_context_renders_manual_interest_column():
    html = chg._opportunity_context({
        "watch_interest": {
            "rows": [{
                "ticker": "CISO",
                "status": "interest",
                "manual_interest": True,
                "source_count": 1,
                "ambiguity": "confirm intended ticker",
            }]
        }
    })

    assert "Interest" in html
    assert "CISO" in html
    assert "confirm intended ticker" in html
