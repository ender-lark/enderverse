import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from social_snapshot_intake import build_social_snapshot_cache, main  # noqa: E402
from social_watch import build_social_watch  # noqa: E402


def test_trumpstrades_snapshot_normalizes_mu_watch_row():
    cache = build_social_snapshot_cache(
        {
            "items": [
                {
                    "source": "reddit",
                    "subreddit": "TrumpsTrades",
                    "title": "Trump + MU",
                    "body": "Micron announced a Trump Accounts investment.",
                    "url": "https://reddit.example/post",
                }
            ]
        },
        generated_at="2026-07-01T12:00:00Z",
    )

    row = cache["items"][0]
    assert row["ticker"] == "MU"
    assert row["source_group"] == "trump_trade_watch"
    assert row["subreddits"] == ["TrumpsTrades"]
    assert "Trump + MU" in row["evidence"]


def test_snapshot_cache_flows_to_social_watch_as_watch_only():
    cache = build_social_snapshot_cache(
        {
            "items": [
                {
                    "source": "reddit",
                    "subreddit": "TrumpsTrades",
                    "title": "Trump + MU",
                    "body": "Micron announced a Trump Accounts investment.",
                }
            ]
        }
    )

    block = build_social_watch(cache, material_tickers={"MU"})

    assert block["status"] == "has_data"
    assert block["rows"][0]["ticker"] == "MU"
    assert block["rows"][0]["escalation"] == "Quiet Watch"
    assert "never a standalone trade signal" in block["honesty_rule"]


def test_cli_writes_social_watch_cache(tmp_path):
    raw = tmp_path / "social.json"
    out = tmp_path / "social_watch.json"
    raw.write_text(
        json.dumps({"items": [{"subreddit": "TrumpsTrades", "title": "Trump + MU"}]}),
        encoding="utf-8",
    )

    assert main([str(raw), "--out", str(out), "--generated-at", "2026-07-01T12:00:00Z"]) == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["count"] == 1
    assert written["items"][0]["ticker"] == "MU"
