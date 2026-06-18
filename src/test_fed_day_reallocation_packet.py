import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fed_day_reallocation_packet as fdp
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


def test_daily_packet_is_candidate_only_and_has_required_sections():
    packet = build_packet(quote_provider=_fake_quote, as_of="2026-06-17", max_tickers=8)
    positions = packet["source_status"]["positions"]

    assert packet["packet_kind"] == "daily_pullback_reallocation"
    assert packet["display_label"] == "Daily pullback packet"
    assert packet["candidate_only"] is True
    assert "No trades executed" in packet["honesty_rule"]
    assert positions["snapshot_date"]
    assert positions["status"] == (
        "has_data" if positions["snapshot_date"] == packet["as_of"] else "stale_or_dark"
    )
    assert packet["source_status"]["market_timing"]["status"] == "checked"
    assert packet["source_status"]["social_watch"]["status"] == "not_checked"
    assert packet["source_status"]["notion_research_queue"]["writeback"] == "not_needed_no_new_notion_write"
    assert packet["current_market_update"]["stance"] == "AMBER_PRE_FOMC_ROTATION"
    assert packet["gates"]["current_status"] == "AMBER_PRE_FOMC_ROTATION"
    assert [row["ticker"] for row in packet["act_if_green"]] == BASE_ADD_TICKERS
    assert packet["stage_if_amber"]["total_starter_band_usd"] == {"low": 20000, "high": 45000}
    assert any("Options remain review-only" in row for row in packet["do_not_touch_yet"])
    assert "AMBER_PRE_FOMC_ROTATION" in json.dumps(packet, sort_keys=True)


def test_daily_packet_uses_broker_exposure_not_only_tracked_positions():
    packet = build_packet(quote_provider=_fake_quote, as_of="2026-06-17", max_tickers=8)
    by_ticker = {row["ticker"]: row for row in packet["act_if_green"]}

    assert by_ticker["GOOGL"]["existing_exposure_usd"] > 0
    assert by_ticker["MSFT"]["existing_exposure_usd"] > 0
    assert by_ticker["GOOGL"]["dollar_band"] == {"low": 60000.0, "high": 110000.0}
    assert by_ticker["GOOGL"]["model_reference_band"] == {"low": 100000.0, "high": 155000.0}
    assert by_ticker["MSFT"]["dollar_band"] == {"low": 15000.0, "high": 30000.0}
    assert by_ticker["MSFT"]["model_reference_band"] == {"low": 25000.0, "high": 40000.0}
    assert by_ticker["GOOGL"]["post_band_exposure_pct"]["high"] > by_ticker["GOOGL"]["existing_exposure_pct"]
    assert by_ticker["GOOGL"]["execution_status"] == "not_executed"
    assert by_ticker["GOOGL"]["options_status"] == "review_only"


def test_deep_discounts_are_research_not_automatic_buys():
    packet = build_packet(quote_provider=_fake_quote, as_of="2026-06-17", max_tickers=8)
    deep = {row["ticker"]: row for row in packet["deep_discount_research"]}

    assert deep["BMNR"]["pct_below_high"] < -80
    assert deep["BMNR"]["research_status"] == "MONITOR"
    assert "mNAV" in deep["BMNR"]["disconfirmation"]
    assert "source_disagreement" in deep["KTOS"]["source_flags"]
    assert "Fundstrat" in deep["KTOS"]["disconfirmation"]


def test_structured_research_queue_buy_verdict_wires_pullback_conviction(monkeypatch):
    real_load_json = fdp._load_json

    def fake_load_json(path, default):
        name = Path(path).name
        if name == "research_queue.json":
            return {
                "pending": [{
                    "r": "VRT - starter after off-hours screen",
                    "pr": "high",
                    "status": "Working",
                    "ticker": "VRT",
                    "stance": "BUY",
                    "conviction": "HIGH",
                    "conviction_score": 4.6,
                    "size": "$8-10k starter",
                    "size_band_usd": {"low": 8000.0, "high": 10000.0},
                    "trigger_date": "2026-07-29",
                    "thesis": "$15B backlog; power/cooling demand supports a starter.",
                    "source": "off-hours screen #3",
                    "source_tags": ["off-hours screen", "vetted BUY"],
                    "source_groups": ["research_queue", "earnings_backlog"],
                    "n_groups": 2,
                    "first_flagged": "2026-06-18",
                    "flag_price": 180,
                }]
            }
        if name == "open_opportunities.json":
            return {"opportunities": []}
        return real_load_json(path, default)

    monkeypatch.setattr(fdp, "_load_json", fake_load_json)

    packet = build_packet(quote_provider=_fake_quote, as_of="2026-06-18", max_tickers=8)
    vrt = next(row for row in packet["higher_quality_pullbacks"] if row["ticker"] == "VRT")

    assert vrt["research_status"] == "BUY"
    assert "trusted BUY verdict" in vrt["source_tags"]
    assert "off-hours screen #3" in vrt["source_tags"]
    assert vrt["conviction"]["read"] == "HIGH"
    assert vrt["conviction"]["n_groups"] == 2
    assert vrt["conviction"]["source_groups"] == ["research_queue", "earnings_backlog"]
    assert vrt["thesis"].startswith("$15B backlog")
    assert vrt["size"] == "$8-10k starter"
    assert vrt["size_band_usd"] == {"low": 8000.0, "high": 10000.0}
    assert vrt["trigger_date"] == "2026-07-29"
    assert vrt["first_flagged"] == "2026-06-18"
    assert vrt["flag_price"] == 180
    assert vrt["move_since_flagged"] == "+6% since flag"


def test_daily_packet_accepts_new_as_of_without_event_specific_status():
    packet = build_packet(quote_provider=_fake_quote, as_of="2026-06-18", max_tickers=8)

    assert packet["as_of"] == "2026-06-18"
    assert packet["display_label"] == "Daily pullback packet"
    assert packet["gates"]["current_status"] == "STAGE_UNTIL_LIVE_TAPE_CONFIRMS"
    assert packet["stage_if_amber"]["total_starter_band_usd"] == {"low": 25000, "high": 60000}
    assert "Fed-day" not in json.dumps(packet, sort_keys=True)
    assert "AMBER_PRE_FOMC" not in json.dumps(packet, sort_keys=True)
