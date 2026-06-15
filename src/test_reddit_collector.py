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
    extract_mentions,
    iter_reddit_items,
    source_group_config,
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
