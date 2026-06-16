import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reddit_collector import (
    DEFAULT_TICKERS,
    build_cache,
    build_research_queue_rows,
    build_scout_report,
    extract_mentions,
    iter_reddit_items,
    source_group_config,
    source_group_names,
    write_scout_report,
)
from social_watch import build_social_watch


FIXTURES = Path(__file__).resolve().parent / "testdata" / "reddit"


def _load(name):
    with (FIXTURES / name).open(encoding="utf-8") as fh:
        return json.load(fh)


def test_extract_mentions_accepts_cashtags_names_and_rejects_common_words():
    mentions = extract_mentions(
        "CEO says IT is FOR real, but $NVDA and Nvidia suppliers moved. AMD also came up.",
        ticker_universe=DEFAULT_TICKERS,
    )

    assert mentions["NVDA"] == ["$NVDA", "NVDA", "nvidia"]
    assert mentions["AMD"] == ["AMD"]
    assert "IT" not in mentions
    assert "FOR" not in mentions
    assert "CEO" not in mentions


def test_iter_reddit_items_reads_posts_and_comments_without_authors():
    items = iter_reddit_items(_load("options_comments.json"))

    assert {item["kind"] for item in items} == {"post", "comment"}
    assert any("$AMD call skew" in item["body"] for item in items)
    assert all("author" not in item for item in items)


def test_iter_reddit_items_accepts_manual_snapshot_rows_without_authors():
    payload = [
        {
            "subreddit": "wallstreetbets",
            "title": "$NVDA calls are back on the menu",
            "snippet": "Crowded retail options thread.",
            "url": "https://www.reddit.com/r/wallstreetbets/comments/manual01/",
            "visible_time": "3h ago",
            "score": 510,
            "comments": 84,
            "flair": "Discussion",
            "author": "do-not-store",
            "raw_transcript": "do not persist this copied content",
        }
    ]

    items = iter_reddit_items(payload)

    assert len(items) == 1
    assert items[0]["id"].startswith("manual-")
    assert items[0]["subreddit"] == "wallstreetbets"
    assert items[0]["body"] == "Crowded retail options thread."
    assert items[0]["comment_count_observed"] == 84
    assert items[0]["source_time_label"] == "3h ago"
    assert "author" not in items[0]
    assert "raw_transcript" not in items[0]


def test_fixture_cache_scores_velocity_and_matches_social_watch_schema():
    cache = build_cache(
        [_load("stocks_new.json")],
        subreddits=["stocks"],
        generated_at=datetime(2026, 6, 14, 12, 0, tzinfo=ZoneInfo("America/New_York")),
        confirmation_map={"NVDA": ["price_action: same-day relative strength check"]},
    )
    block = build_social_watch(cache)

    nvda = next(row for row in cache["rows"] if row["tickers"] == ["NVDA"])
    assert cache["status"] == "has_data"
    assert nvda["mention_series"] == [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 9]
    assert nvda["eligible"] is True
    assert nvda["fired"] is True
    assert nvda["escalation"] == "Research Queue candidate"
    assert nvda["expires_at"].endswith("+00:00")
    assert "author" not in json.dumps(cache).lower()
    assert block["status"] == "has_data"
    assert block["rows"][0]["ticker"] == "NVDA"
    assert block["rows"][0]["fired"] is True
    assert block["rows"][0]["independent_confirmation"] == ["price_action: same-day relative strength check"]


def test_failed_fetch_cache_stays_not_checked_in_social_watch():
    cache = build_cache(
        [],
        subreddits=["stocks"],
        failures=[{"subreddit": "stocks", "error": "HTTPError: 429"}],
        generated_at=datetime(2026, 6, 14, 12, 0, tzinfo=ZoneInfo("America/New_York")),
    )
    block = build_social_watch(cache)

    assert cache["status"] == "not_checked"
    assert block["status"] == "not_checked"
    assert block["count"] == 0
    assert "not checked" in block["line"].lower()


def test_research_queue_candidates_require_fired_and_confirmation():
    cache = build_cache(
        [_load("stocks_new.json")],
        generated_at=datetime(2026, 6, 14, 12, 0, tzinfo=ZoneInfo("America/New_York")),
    )

    assert build_research_queue_rows(cache["rows"]) == []
    confirmed = build_cache(
        [_load("stocks_new.json")],
        generated_at=datetime(2026, 6, 14, 12, 0, tzinfo=ZoneInfo("America/New_York")),
        confirmation_map={"NVDA": ["news: product lead-time detail"]},
    )

    rows = build_research_queue_rows(confirmed["rows"])
    assert len(rows) == 1
    assert rows[0]["ticker"] == "NVDA"
    assert "before any action" in rows[0]["r"]


def test_critical_minerals_source_group_adds_detachable_watchlist_and_prompt_fields():
    config = source_group_config("critical_minerals_nuclear")
    payload = {
        "subreddit": "criticalmineralstocks",
        "items": [
            {
                "id": "cm01",
                "created_utc": "2026-06-15T12:38:00+00:00",
                "subreddit": "criticalmineralstocks",
                "title": "Ucore Rare Metals announces rare earth supply chain collaboration $UURAF",
                "selftext": "Critical minerals processing and allied supply-chain prompt.",
                "permalink": "/r/criticalmineralstocks/comments/cm01/ucore/",
                "score": 26,
                "num_comments": 1,
            },
            {
                "id": "uranium01",
                "created_utc": "2026-06-15T13:10:00+00:00",
                "subreddit": "UraniumSqueeze",
                "title": "AI data center power demand keeps uranium and $UUUU in focus",
                "selftext": "Nuclear power and uranium miners are being discussed as data-center power demand rises.",
                "permalink": "/r/UraniumSqueeze/comments/uranium01/ai_power/",
                "score": 48,
                "num_comments": 34,
            },
        ],
    }

    cache = build_cache(
        [payload],
        subreddits=config["subreddits"],
        source_group="critical_minerals_nuclear",
        generated_at=datetime(2026, 6, 15, 12, 0, tzinfo=ZoneInfo("America/New_York")),
    )

    tickers = {row["tickers"][0] for row in cache["rows"]}
    assert cache["source_group"] == "critical_minerals_nuclear"
    assert {"UURAF", "UUUU"} <= tickers
    row = next(row for row in cache["rows"] if row["tickers"] == ["UUUU"])
    assert row["source_group"] == "critical_minerals_nuclear"
    assert row["source_type"] in {"ai_power_nuclear_narrative", "company_or_policy_catalyst"}
    assert "Critical-minerals/nuclear Reddit scout item" in row["why_it_matters"]
    assert row["portfolio_implication"].startswith("Quiet Watch")
    assert row["blocker_before_action"].startswith("Reddit is not a trade trigger")
    assert row["suggested_next_check"]
    assert cache["research_queue_candidates"] == []


def test_manual_critical_minerals_snapshot_builds_report_without_action_promotion(tmp_path):
    payload = [
        {
            "subreddit": "criticalmineralstocks",
            "title": "Ucore Rare Metals rare earth processing update",
            "snippet": "Manual Chrome-visible snapshot references $UURAF and allied supply chain.",
            "permalink": "/r/criticalmineralstocks/comments/manual_ucore/",
            "visible_time": "2h ago",
            "score": 18,
            "comments": 6,
            "author": "not persisted",
            "raw_transcript": "not persisted",
        },
        {
            "subreddit": "UraniumSqueeze",
            "title": "AI data center power demand keeps $UUUU and uranium miners in focus",
            "snippet": "Nuclear power demand thread from a browser-visible snapshot.",
            "permalink": "/r/UraniumSqueeze/comments/manual_uuuu/",
            "visible_time": "45m ago",
            "score": 66,
            "comments": 41,
        },
    ]

    cache = build_cache(
        [payload],
        subreddits=source_group_config("critical_minerals_nuclear")["subreddits"],
        source_group="critical_minerals_nuclear",
        generated_at=datetime(2026, 6, 16, 9, 30, tzinfo=ZoneInfo("America/New_York")),
    )
    report_path = tmp_path / "critical_minerals_reddit_scout.md"
    write_scout_report(cache, out=str(report_path))
    report = report_path.read_text(encoding="utf-8")

    assert cache["status"] == "has_data"
    assert {row["tickers"][0] for row in cache["rows"]} == {"UURAF", "UUUU"}
    assert cache["research_queue_candidates"] == []
    assert "author" not in json.dumps(cache).lower()
    assert "raw_transcript" not in json.dumps(cache).lower()
    assert "Reddit is not a trade trigger" in report
    assert "Why it matters" in report
    assert "Portfolio implication" in report
    assert "Confirmation needed" in report
    assert "Suggested next check" in report
    assert "45m ago" in report


def test_report_preserves_not_checked_honesty():
    cache = build_cache(
        [],
        subreddits=["wallstreetbets"],
        source_group="retail_risk_wsb",
        failures=[{"subreddit": "wallstreetbets", "error": "HTTPError: 403"}],
        generated_at=datetime(2026, 6, 16, 9, 30, tzinfo=ZoneInfo("America/New_York")),
    )
    report = build_scout_report(cache)

    assert "Status: not_checked" in report
    assert "Missing or blocked Reddit data is not checked" in report


def test_retail_risk_wsb_source_group_is_detachable():
    config = source_group_config("retail_risk_wsb")

    assert "retail_risk_wsb" in source_group_names()
    assert config["subreddits"] == ["wallstreetbets"]
    assert "NVDA" in config["tickers"]
