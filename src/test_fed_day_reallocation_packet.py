import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fed_day_reallocation_packet import BASE_ADD_TICKERS, build_packet


def _fake_quote(ticker):
    prices = {
        "GOOGL": (373.0, 408.0),
        "MSFT": (397.0, 560.0),
        "BMNR": (16.0, 160.0),
        "LEU": (171.0, 480.0),
        "AVGO": (394.0, 518.0),
        "FN": (619.0, 790.0),
        "VRT": (190.0, 241.0),
        "AMZN": (246.0, 278.0),
        "NVDA": (211.0, 241.0),
        "UUUU": (15.6, 28.5),
        "MP": (58.0, 102.0),
        "HOOD": (128.0, 204.0),
        "AVAV": (210.0, 526.0),
        "KTOS": (26.8, 63.8),
        "ELF": (82.0, 185.0),
        "SOFI": (17.1, 31.6),
    }
    price, high = prices.get(ticker, (100.0, 125.0))
    return {
        "ticker": ticker,
        "status": "has_data",
        "checked_at": "2026-06-17T05:30:00Z",
        "price": price,
        "fifty_two_week_high": high,
        "pct_below_high": round((price / high - 1) * 100, 2),
        "latest_price_date": "2026-06-16",
        "high_date": "2026-06-03",
        "currency": "USD",
        "source": "test quote provider",
    }


def test_fed_day_packet_is_candidate_only_and_has_required_sections():
    packet = build_packet(quote_provider=_fake_quote, max_tickers=8)

    assert packet["candidate_only"] is True
    assert "No trades executed" in packet["honesty_rule"]
    assert packet["source_status"]["positions"]["snapshot_date"] == "2026-06-17"
    assert packet["source_status"]["social_watch"]["status"] == "not_checked"
    assert packet["source_status"]["notion_research_queue"]["writeback"] == "not_needed_no_new_notion_write"
    assert [row["ticker"] for row in packet["act_if_green"]] == BASE_ADD_TICKERS
    assert packet["stage_if_amber"]["total_starter_band_usd"] == {"low": 25000, "high": 60000}
    assert any("Options remain review-only" in row for row in packet["do_not_touch_yet"])


def test_fed_day_packet_uses_broker_exposure_not_only_tracked_positions():
    packet = build_packet(quote_provider=_fake_quote, max_tickers=8)
    by_ticker = {row["ticker"]: row for row in packet["act_if_green"]}

    assert by_ticker["GOOGL"]["existing_exposure_usd"] > 0
    assert by_ticker["MSFT"]["existing_exposure_usd"] > 0
    assert by_ticker["GOOGL"]["post_band_exposure_pct"]["high"] > by_ticker["GOOGL"]["existing_exposure_pct"]
    assert by_ticker["GOOGL"]["execution_status"] == "not_executed"
    assert by_ticker["GOOGL"]["options_status"] == "review_only"


def test_deep_discounts_are_research_not_automatic_buys():
    packet = build_packet(quote_provider=_fake_quote, max_tickers=8)
    deep = {row["ticker"]: row for row in packet["deep_discount_research"]}

    assert deep["BMNR"]["pct_below_high"] < -80
    assert deep["BMNR"]["research_status"] == "MONITOR"
    assert "mNAV" in deep["BMNR"]["disconfirmation"]
    assert "source_disagreement" in deep["KTOS"]["source_flags"]
    assert "Fundstrat" in deep["KTOS"]["disconfirmation"]
