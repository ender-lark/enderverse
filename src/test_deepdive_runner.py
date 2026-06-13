from __future__ import annotations

import json

import deepdive_runner as dr


OI_ROWS = [
    {"option_symbol": "NVDA260717C00230000", "date": "2026-06-10", "oi_diff_plain": 1200},
    {"option_symbol": "NVDA260717C00235000", "date": "2026-06-11", "oi_diff_plain": 900},
    {"option_symbol": "NVDA260717C00240000", "date": "2026-06-12", "oi_diff_plain": 500},
    {"option_symbol": "NVDA260717P00190000", "date": "2026-06-12", "oi_diff_plain": 100},
    {"option_symbol": "NVDA260620C00230000", "date": "2026-06-12", "oi_diff_plain": 5000},
]


DARK_POOL_ROWS = [
    {"executed_at": "2026-06-12T15:30:00Z", "premium": "6500000", "price": 204, "nbbo_bid": 203, "nbbo_ask": 204},
    {"executed_at": "2026-06-10T14:30:00Z", "size": 30000, "price": 210, "above_vwap": False},
    {"executed_at": "2026-05-20T14:30:00Z", "premium": 8000000, "above_vwap": True},
    {"executed_at": "2026-06-12T14:30:00Z", "premium": 900000, "above_vwap": True},
]


class FakeFetcher:
    def __init__(self):
        self.calls = []

    def get_open_interest_changes(self, ticker, *, min_dte=30):
        self.calls.append(("oi", ticker, min_dte))
        return {"data": OI_ROWS}

    def get_dark_pool_trades(self, ticker, *, days=10, min_notional=5_000_000.0):
        self.calls.append(("dark_pool", ticker, days, min_notional))
        return {"data": DARK_POOL_ROWS}


def _lanes(payload):
    return {lane["name"]: lane for lane in payload["lanes"]}


def test_evidence_battery_flags_multiday_oi_and_dark_pool_blocks():
    fetcher = FakeFetcher()

    payload = dr.build_evidence_battery("nvda", fetcher=fetcher, as_of="2026-06-13")
    lanes = _lanes(payload)

    assert payload["ticker"] == "NVDA"
    assert payload["counts"] == {"fetched": 2}
    assert fetcher.calls == [
        ("oi", "NVDA", 30),
        ("dark_pool", "NVDA", 10, 5_000_000.0),
    ]
    assert lanes["multi_day_oi_build"]["status"] == "fetched"
    assert lanes["multi_day_oi_build"]["days_of_oi_increases"] == 3
    assert lanes["multi_day_oi_build"]["flagged"] is True
    assert lanes["multi_day_oi_build"]["dominant_side"] == "call"
    assert lanes["multi_day_oi_build"]["skipped_short_dte"] == 1
    assert lanes["dark_pool_blocks"]["status"] == "fetched"
    assert lanes["dark_pool_blocks"]["qualifying_blocks"] == 2
    assert lanes["dark_pool_blocks"]["flagged"] is True
    assert lanes["dark_pool_blocks"]["skipped_old"] == 1
    assert lanes["dark_pool_blocks"]["skipped_small"] == 1


def test_evidence_battery_marks_absent_lanes_not_checked():
    payload = dr.build_evidence_battery("NVDA", as_of="2026-06-13")
    lanes = _lanes(payload)

    assert payload["counts"] == {"not_checked": 2}
    assert lanes["multi_day_oi_build"]["status"] == "not_checked"
    assert "no UW OI response supplied" in lanes["multi_day_oi_build"]["summary"]
    assert lanes["dark_pool_blocks"]["status"] == "not_checked"
    assert "not_checked lanes never imply all clear" in payload["honesty_rule"]


def test_oi_analysis_uses_native_days_of_oi_increases_field():
    payload = dr.analyze_multi_day_oi_build({
        "data": [
            {
                "option_symbol": "NVDA260717C00230000",
                "curr_date": "2026-06-12",
                "oi_diff_plain": 1200,
                "days_of_oi_increases": 5,
            }
        ]
    }, as_of="2026-06-13")

    assert payload["days_of_oi_increases"] == 5
    assert payload["flagged"] is True


def test_render_json_includes_evidence_battery():
    battery = dr.build_evidence_battery(
        "NVDA",
        oi_raw={"data": OI_ROWS},
        dark_pool_raw={"data": DARK_POOL_ROWS},
        as_of="2026-06-13",
    )

    payload = json.loads(dr.render_json("NVDA", evidence_battery=battery))

    assert payload["evidence_battery"]["ticker"] == "NVDA"
    assert payload["evidence_battery"]["counts"] == {"fetched": 2}
