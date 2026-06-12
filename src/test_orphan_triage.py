import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import orphan_triage as ot


def _positions():
    return {
        "snapshot_date": "2026-06-12",
        "sleeve_value": 100_000,
        "account_positions": [
            {"ticker": "AVGO", "account": "Taxable", "tracked": False},
            {"ticker": "AVGO", "account": "IRA", "tracked": False},
            {"ticker": "CIBR", "account": "Taxable", "tracked": False},
            {"ticker": "SPAXX", "account": "Brokerage", "tracked": False},
            {"ticker": "ACON", "account": "Taxable", "tracked": False},
            {"ticker": "NVDA", "account": "Taxable", "tracked": True},
        ],
        "combined_positions": [
            {"ticker": "AVGO", "shares": 10, "market_value": 40_500, "owners": ["SKB"], "tracked": False},
            {"ticker": "CIBR", "shares": 50, "market_value": 4_000, "owners": ["SKB"], "tracked": False},
            {"ticker": "SPAXX", "shares": 25_000, "market_value": 25_000, "owners": ["Parents"], "tracked": False},
            {"ticker": "ACON", "shares": 2, "market_value": 5, "owners": ["SKB"], "tracked": False},
            {"ticker": "NVDA", "shares": 100, "market_value": 15_000, "owners": ["SKB"], "tracked": True},
        ],
    }


def _bible():
    return {
        "deck_date": "2026-06-11",
        "core_stock_ideas_as_of": "2026-05-28",
        "what_to_own": ["MAG7", "Software"],
        "top5": [{"ticker": "AVGO"}],
        "bottom5": ["ACME"],
        "top5_smid": ["FN"],
        "sector_allocation": {
            "as_of": "2026-06-11",
            "june_etf_basket": [
                {"ticker": "CIBR", "status": "new", "theme": "cybersecurity"},
            ],
        },
    }


def _by_ticker(payload):
    return {row["ticker"]: row for row in payload["orphans"]}


def test_classifies_only_untracked_positions_with_fs_and_theme_context():
    payload = ot.classify_orphans(_positions(), _bible(), generated_at="fixed")
    rows = _by_ticker(payload)

    assert set(rows) == {"AVGO", "CIBR", "SPAXX", "ACON"}
    assert rows["AVGO"]["market_value"] == 40500
    assert rows["AVGO"]["account_count"] == 2
    assert rows["AVGO"]["size_bucket"] == ">$10K material"
    assert rows["AVGO"]["themes"] == ["AI-infra", "semis"]
    assert rows["AVGO"]["fs_pick_status"]["direct_lists"] == [{"list": "top5", "rank": 1}]
    assert rows["AVGO"]["suggested_disposition"] == "NEEDS-THESIS"

    assert rows["CIBR"]["fs_pick_status"]["june_basket"][0]["status"] == "new"
    assert rows["CIBR"]["fs_pick_status"]["what_to_own"] == ["software"]
    assert rows["CIBR"]["suggested_disposition"] == "MERGE-INTO-SLEEVE"

    assert rows["SPAXX"]["themes"] == ["cash-equiv"]
    assert rows["SPAXX"]["suggested_disposition"] == "WATCH"

    assert rows["ACON"]["size_bucket"] == "<$2K dust"
    assert rows["ACON"]["suggested_disposition"] == "DUST"


def test_render_markdown_surfaces_summary_and_rows():
    payload = ot.classify_orphans(_positions(), _bible(), generated_at="fixed")
    md = ot.render_markdown(payload)

    assert "# Orphan Position Triage" in md
    assert "4 untracked tickers" in md
    assert "| AVGO | $40,500 | 40.50% | 2 | >$10K material" in md
    assert "top5#1" in md
    assert "june_basket:new" in md
