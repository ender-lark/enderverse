import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fundstrat_news import build_fundstrat_news, build_if_i_were_you


def test_fundstrat_news_surfaces_monthly_lists_and_gaps():
    news = build_fundstrat_news(
        fundstrat_bible={
            "deck_date": "2026-05-28",
            "source_file": "may.pdf",
            "what_to_own": ["MAG7", "Financials"],
            "top5": ["AMD", "ANET"],
            "bottom5": ["DE"],
        },
        fundstrat_daily_calls=[
            {
                "author": "Newton",
                "ticker": "QQQ",
                "direction": "watch",
                "quote": "Support near 695-705 matters before adding beta.",
                "date": "2026-06-05",
                "subject": "Daily Technical Strategy",
            }
        ],
        top_prospects={
            "AMD": {
                "ticker": "AMD",
                "add_date": "2026-05-28",
                "add_price": 120.5,
                "provenance": "FS Top 5 - 2026-05-28",
            },
            "ANET": {
                "ticker": "ANET",
                "add_date": "2026-05-28",
                "add_price": None,
                "provenance": "FS Top 5 - 2026-05-28",
            },
        },
        intake_summary={"full_body_entries": 1, "stored_daily_calls": 1},
        as_of="2026-06-08",
    )

    assert news["status"] == "has_data"
    assert news["monthly"]["deck_date"] == "2026-05-28"
    assert news["monthly"]["allocation_plan"] == ["MAG7", "Financials"]
    assert news["monthly"]["top_large_cap"][0]["ticker"] == "AMD"
    assert news["monthly"]["top_large_cap"][0]["add_price_label"] == "$120.50"
    assert news["monthly"]["top_large_cap"][1]["add_price_label"] == "not captured"
    assert news["monthly"]["top_smid"] == []
    assert any(gap["key"] == "missing_smid_top5" for gap in news["gaps"])
    assert any(gap["key"] == "missing_add_prices" for gap in news["gaps"])
    assert news["daily"]["rows"][0]["source_domain"] == "technical_timing"
    assert news["daily"]["rows"][0]["publication_type"] == "daily_technical"
    assert news["daily"]["rows"][0]["capture_policy"] == "daily_call"
    assert news["daily"]["rows"][0]["action_implication"] == "re-check timing"


def test_fundstrat_news_uses_future_smid_cache_when_present():
    news = build_fundstrat_news(
        fundstrat_bible={
            "deck_date": "2026-05-28",
            "top5": ["AMD"],
            "top5_smid": [
                {"ticker": "FN", "name": "Fabrinet", "report_move_pct": 0.9},
            ],
            "bottom5_smid": ["ELF"],
        },
        top_prospects={
            "FN": {
                "ticker": "FN",
                "add_date": "2026-05-28",
                "add_price": 600,
                "provenance": "FS Top 5 SMID - 2026-05-28",
            }
        },
        as_of="2026-06-08",
    )

    assert news["monthly"]["top_smid"][0]["ticker"] == "FN"
    assert news["monthly"]["top_smid"][0]["name"] == "Fabrinet"
    assert news["monthly"]["top_smid"][0]["report_move_pct"] == 0.9
    assert news["monthly"]["top_smid"][0]["add_price_label"] == "$600.00"
    assert news["monthly"]["bottom5_smid"][0]["ticker"] == "ELF"
    assert not any(gap["key"] == "missing_smid_top5" for gap in news["gaps"])


def test_fundstrat_news_surfaces_tactical_sector_layer():
    news = build_fundstrat_news(
        fundstrat_bible={
            "deck_date": "2026-06-11",
            "top5_smid": ["FN"],
            "sector_allocation": {
                "as_of": "2026-06-11",
                "tactical_top3": [
                    {"sector": "Health Care", "ticker": "XLV"},
                    {"sector": "Real Estate", "ticker": "XLRE"},
                    {"sector": "Utilities", "ticker": "XLU"},
                ],
                "tactical_bottom3": [
                    {"sector": "Energy", "ticker": "XLE"},
                    {"sector": "Consumer Discretionary", "ticker": "XLY"},
                    {"sector": "Consumer Staples", "ticker": "XLP"},
                ],
                "named_levels": [
                    {"ticker": "EWRE", "condition": "weekly close above", "level": 38.0},
                ],
                "monthly_checklist": [
                    {"item": "EWRE breakout gate", "status": "armed"},
                ],
            },
        },
        as_of="2026-06-14",
    )

    assert "tactical 3x3 3/3" in news["line"]
    assert [row["ticker"] for row in news["monthly"]["tactical_top3"]] == ["XLV", "XLRE", "XLU"]
    assert news["monthly"]["tactical_bottom3"][0]["ticker"] == "XLE"
    assert news["monthly"]["named_levels"][0]["ticker"] == "EWRE"
    assert news["monthly"]["monthly_checklist"][0]["item"] == "EWRE breakout gate"
    assert not any(gap["key"] == "missing_tactical_3x3" for gap in news["gaps"])
    assert not any(gap["key"] == "missing_named_levels" for gap in news["gaps"])


def test_fundstrat_news_surfaces_ingest_guard_findings():
    news = build_fundstrat_news(
        fundstrat_bible={
            "deck_date": "2026-06-11",
            "top5_smid": ["FN"],
        },
        ingest_findings=[
            {
                "key": "fs_ingest_partial",
                "source_id": "fundstrat_sector_allocation:2026-06-11",
                "line": "June Sector: 1 of 5 sections never distilled - verdicts leaning on this source are partial",
                "next_step": "Distill tactical top/bottom.",
            }
        ],
        as_of="2026-06-12",
    )

    gap = [row for row in news["gaps"] if row["key"] == "fs_ingest_partial"][0]
    assert "never distilled" in gap["line"]
    assert gap["source_id"] == "fundstrat_sector_allocation:2026-06-11"


def test_if_i_were_you_is_review_only_and_uses_feed_priorities():
    feed = {
        "actions": [
            {
                "ticker": "NVDA",
                "what": "Conviction gap: NVDA is under target",
                "why_this_matters": "Sizing gap can make the right thesis too small.",
                "source": "target_drift",
            }
        ],
        "market_open_packet": {"counts": {"recheck": 2}},
        "reallocation_brief": {
            "line": "Reallocation brief: candidate only.",
            "rows": [{"ticker": "GOOGL", "action": "ADD_CANDIDATE"}],
        },
        "fundstrat_news": {
            "gaps": [{"line": "Top 5 SMID is not present."}],
            "daily": {"rows": [{"ticker": "QQQ"}]},
        },
    }

    block = build_if_i_were_you(feed)

    assert block["status"] == "review_only"
    assert "no execution" in block["line"]
    assert block["rows"][0]["label"].startswith("Start with NVDA")
    assert any(row["source"] == "fundstrat_news" for row in block["rows"])
    assert any(row["posture"] == "size/compare" for row in block["rows"])
