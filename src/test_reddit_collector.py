import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reddit_collector import (
    DEFAULT_TICKERS,
    append_snapshot_history,
    build_cache,
    build_research_queue_rows,
    build_repeat_snapshot_comparison,
    build_scout_report,
    build_snapshot_history_record,
    build_source_health,
    build_weekly_pattern_report,
    extract_mentions,
    iter_reddit_items,
    load_snapshot_history,
    source_group_config,
    source_group_names,
    source_group_role,
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


def test_source_health_classifies_active_thin_stale_and_fringe_subreddits():
    generated = datetime(2026, 6, 16, 9, 30, tzinfo=ZoneInfo("America/New_York"))
    rows = [
        *[
            {
                "subreddit": "activeSub",
                "title": f"Policy catalyst {idx}",
                "created_utc": f"2026-06-16T1{idx}:00:00+00:00",
                "score_observed": 10 + idx,
                "comment_count_observed": idx,
            }
            for idx in range(5)
        ],
        {
            "subreddit": "thinSub",
            "title": "Specific company update",
            "source_time_label": "4 hr. ago",
            "score_observed": 5,
            "comment_count_observed": 1,
        },
        {
            "subreddit": "thinSub",
            "title": "Another current post",
            "source_time_label": "1 day ago",
            "score_observed": 7,
            "comment_count_observed": 2,
        },
        {
            "subreddit": "staleSub",
            "title": "Old post",
            "source_time_label": "9 days ago",
            "score_observed": 3,
            "comment_count_observed": 0,
        },
        {
            "subreddit": "fringeSub",
            "title": "Buy this moonshot YOLO",
            "flair": "YOLO",
            "source_time_label": "2 hr. ago",
            "score_observed": 20,
            "comment_count_observed": 4,
        },
        {
            "subreddit": "fringeSub",
            "title": "Gain screenshot to the moon",
            "flair": "Gain",
            "source_time_label": "3 hr. ago",
            "score_observed": 25,
            "comment_count_observed": 5,
        },
    ]

    health = build_source_health(
        rows,
        subreddits=["activeSub", "thinSub", "staleSub", "fringeSub"],
        generated=generated,
    )

    assert health["activeSub"]["status"] == "active"
    assert health["thinSub"]["status"] == "thin_but_current"
    assert health["staleSub"]["status"] == "stale"
    assert health["fringeSub"]["status"] == "fringe"
    assert health["activeSub"]["posts_seen_7d"] == 5
    assert health["fringeSub"]["promo_noise_ratio"] == 1.0


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


def test_stale_tiny_subreddit_cannot_create_sentiment_conclusion():
    payload = [
        {
            "subreddit": "tinyminerals",
            "title": "$MP is going to moon with no external source",
            "snippet": "Unsupported thesis.",
            "visible_time": "12 days ago",
            "score": 1,
            "comments": 0,
        }
    ]

    cache = build_cache(
        [payload],
        subreddits=["tinyminerals"],
        generated_at=datetime(2026, 6, 16, 9, 30, tzinfo=ZoneInfo("America/New_York")),
    )
    row = cache["rows"][0]

    assert row["source_health_status"] == "stale"
    assert row["signal_kind"] == "destroy/noise"
    assert "primary-source/link scout only" in row["source_interpretation_limit"]
    assert row["destroy_reason"]


def test_wsb_high_engagement_becomes_crowding_prompt_not_buy_prompt():
    payload = [
        {
            "subreddit": "wallstreetbets",
            "members": "20m",
            "online": "45k",
            "source_sort": "hot",
            "title": "$NVDA calls are everywhere after the bond offering",
            "snippet": "Retail crowding thread.",
            "visible_time": "2 hr. ago",
            "score": "4.8k",
            "comments": "1.5k",
            "flair": "Discussion",
        },
        {
            "subreddit": "wallstreetbets",
            "title": "$NVDA meme",
            "visible_time": "3 hr. ago",
            "score": 900,
            "comments": 120,
            "flair": "Meme",
        },
        {
            "subreddit": "wallstreetbets",
            "title": "$MU YOLO",
            "visible_time": "4 hr. ago",
            "score": 300,
            "comments": 60,
            "flair": "YOLO",
        },
        {
            "subreddit": "wallstreetbets",
            "title": "$SPY calls gain",
            "visible_time": "5 hr. ago",
            "score": 200,
            "comments": 40,
            "flair": "Gain",
        },
        {
            "subreddit": "wallstreetbets",
            "title": "$TSLA discussion",
            "visible_time": "6 hr. ago",
            "score": 150,
            "comments": 35,
            "flair": "Discussion",
        },
    ]

    cache = build_cache(
        [payload],
        subreddits=source_group_config("retail_risk_wsb")["subreddits"],
        source_group="retail_risk_wsb",
        generated_at=datetime(2026, 6, 16, 9, 30, tzinfo=ZoneInfo("America/New_York")),
    )
    nvda = next(row for row in cache["rows"] if row["tickers"] == ["NVDA"])

    assert source_group_role("retail_risk_wsb") == "retail_crowding_risk"
    assert nvda["source_role"] == "retail_crowding_risk"
    assert nvda["signal_kind"] == "retail crowding/risk"
    assert "crowding/risk" in nvda["portfolio_implication"].lower()
    assert nvda["escalation"] == "Quiet Watch"
    assert cache["research_queue_candidates"] == []


def test_weekly_pattern_report_surfaces_louder_fading_cross_subreddit_and_noise():
    early = build_cache(
        [[
            {
                "subreddit": "criticalmineralstocks",
                "title": "Ucore rare earth update $UURAF",
                "created_utc": "2026-06-10T13:00:00+00:00",
                "score": 6,
                "comments": 1,
            },
            {
                "subreddit": "wallstreetbets",
                "title": "$NVDA meme gain screenshot",
                "created_utc": "2026-06-10T14:00:00+00:00",
                "score": 900,
                "comments": 80,
                "flair": "Meme",
            },
        ]],
        source_group="critical_minerals_nuclear",
        generated_at=datetime(2026, 6, 10, 9, 30, tzinfo=ZoneInfo("America/New_York")),
    )
    late = build_cache(
        [[
            {
                "subreddit": "criticalmineralstocks",
                "title": "AI power demand keeps $UUUU in uranium focus",
                "created_utc": "2026-06-16T13:00:00+00:00",
                "score": 12,
                "comments": 4,
            },
            {
                "subreddit": "UraniumSqueeze",
                "title": "AI data center power demand and uranium $UUUU",
                "created_utc": "2026-06-16T14:00:00+00:00",
                "score": 42,
                "comments": 30,
            },
        ]],
        source_group="critical_minerals_nuclear",
        generated_at=datetime(2026, 6, 16, 9, 30, tzinfo=ZoneInfo("America/New_York")),
    )

    report = build_weekly_pattern_report([early, late])

    assert "UUUU" in report
    assert "Themes Getting Louder" in report
    assert "Cross-Subreddit Spread" in report
    assert "Destroy / Noise Bucket" in report
    assert "NVDA" in report


def test_repeat_snapshot_history_flags_new_louder_fading_and_compact_storage(tmp_path):
    prior = build_cache(
        [[
            {
                "subreddit": "wallstreetbets",
                "title": "$NVDA calls are everywhere",
                "created_utc": "2026-06-15T13:00:00+00:00",
                "score": 800,
                "comments": 120,
                "flair": "Discussion",
            },
            {
                "subreddit": "UraniumSqueeze",
                "title": "AI power keeps $UUUU in focus",
                "created_utc": "2026-06-15T14:00:00+00:00",
                "score": 10,
                "comments": 2,
            },
        ]],
        generated_at=datetime(2026, 6, 15, 9, 30, tzinfo=ZoneInfo("America/New_York")),
    )
    current = build_cache(
        [[
            {
                "subreddit": "UraniumSqueeze",
                "title": "AI data centers keep $UUUU uranium demand in focus",
                "created_utc": "2026-06-16T13:00:00+00:00",
                "score": 80,
                "comments": 55,
            },
            {
                "subreddit": "criticalmineralstocks",
                "title": "Critical minerals and $UUUU nuclear fuel chain update",
                "created_utc": "2026-06-16T14:00:00+00:00",
                "score": 50,
                "comments": 20,
            },
            {
                "subreddit": "StockMarket",
                "title": "$SPCX price discovery is spreading across Reddit",
                "created_utc": "2026-06-16T15:00:00+00:00",
                "score": 300,
                "comments": 90,
            },
        ]],
        generated_at=datetime(2026, 6, 16, 9, 30, tzinfo=ZoneInfo("America/New_York")),
    )
    history_path = tmp_path / "reddit_history.jsonl"
    prior_record = build_snapshot_history_record(prior)
    append_report = append_snapshot_history(history_path, prior_record)

    comparison = build_repeat_snapshot_comparison(current, load_snapshot_history(history_path))
    current["repeat_snapshot"] = comparison
    report = build_scout_report(current)
    weekly = build_weekly_pattern_report([current, *load_snapshot_history(history_path)])

    assert append_report["appended"] is True
    assert load_snapshot_history(history_path)[0]["schema"] == "reddit_snapshot_history_v1"
    assert "raw_transcript" not in history_path.read_text(encoding="utf-8")
    assert comparison["status"] == "compared"
    assert {row["topic"] for row in comparison["new_topics"]} == {"SPCX"}
    assert "UUUU" in {row["topic"] for row in comparison["getting_louder"]}
    assert "NVDA" in {row["topic"] for row in comparison["fading"]}
    assert "Repeat Snapshot Comparison" in report
    assert "Getting Louder" in report
    assert "UUUU: getting_louder" in weekly


def test_retail_risk_wsb_source_group_is_detachable():
    config = source_group_config("retail_risk_wsb")

    assert "retail_risk_wsb" in source_group_names()
    assert config["subreddits"] == ["wallstreetbets"]
    assert "NVDA" in config["tickers"]
