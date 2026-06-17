import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from alert_policy import build_alert_policy
from decision_dossier_coverage import build_decision_dossier_coverage


def _read(label, text, as_of="2026-06-05", max_age_days=30):
    return {
        "label": label,
        "text": text,
        "as_of": as_of,
        "max_age_days": max_age_days,
        "source": "test",
    }


def _dossier(ticker, *, status="fresh", price_as_of="2026-06-05"):
    return {
        "ticker": ticker,
        "status": status,
        "one_liner": f"{ticker} test dossier.",
        "notion_url": f"https://example.test/{ticker}",
        "last_reviewed": "2026-06-05",
        "next_review_due": "2026-07-05",
        "reads": {
            "edge": _read("Edge/moat", "edge"),
            "price": _read("Good buy price?", "price", as_of=price_as_of, max_age_days=1),
            "timing": _read("Good timing?", "timing", max_age_days=1),
            "avoid": _read("What-not / avoid", "avoid"),
        },
    }


def test_missing_dossier_is_source_proof_debt_not_alert():
    feed = {
        "today_decide": {
            "cards": [{
                "card_id": "NVDA-ADD-2026-06-05",
                "ticker": "NVDA",
                "direction": "BUY",
                "action_state": "ACT_NOW",
                "decision_group": "key_now",
                "window": {"class": "OPEN-NOW"},
            }],
            "backlog": [],
            "data_health": {"items": []},
        },
        "source_audits": {},
    }

    audit = build_decision_dossier_coverage(feed, dossiers={}, today="2026-06-05")
    feed["source_audits"]["decision_dossier_coverage"] = audit
    policy = build_alert_policy(feed)

    assert audit["status"] == "missing"
    assert audit["missing_count"] == 1
    assert audit["blocks"] is False
    assert audit["alert_eligible"] is False
    assert audit["rows"][0]["ticker"] == "NVDA"
    assert audit["rows"][0]["status"] == "missing_dossier"
    assert "decision_dossier_freshness_blocker" not in {row["kind"] for row in policy["rows"]}


def test_stale_existing_dossier_is_review_debt_for_existing_guard():
    feed = {
        "today_decide": {
            "cards": [{"card_id": "AVGO-TRIM-2026-06-05", "ticker": "AVGO", "direction": "TRIM"}],
            "backlog": [],
        },
    }

    audit = build_decision_dossier_coverage(
        feed,
        dossiers={"AVGO": _dossier("AVGO", status="stale", price_as_of=None)},
        today="2026-06-05",
    )

    assert audit["status"] == "needs_review"
    assert audit["missing_count"] == 0
    assert audit["stale_count"] == 1
    row = audit["rows"][0]
    assert row["status"] == "stale_dossier"
    assert row["read_statuses"]["price"] == "not_checked"
    assert "staleness guard" in row["next_step"]


def test_material_holding_coverage_threshold_and_covered_row():
    feed = {
        "portfolio_views": {
            "views": {
                "combined": {
                    "rows": [
                        {"ticker": "SMH", "market_value": 8000, "pct": 8.0},
                        {"ticker": "TIN", "market_value": 500, "pct": 0.5},
                    ],
                },
            },
        },
    }

    audit = build_decision_dossier_coverage(
        feed,
        dossiers={"SMH": _dossier("SMH")},
        today="2026-06-05",
    )

    assert audit["status"] == "covered"
    assert audit["covered_count"] == 1
    assert audit["missing_count"] == 0
    assert [row["ticker"] for row in audit["rows"]] == ["SMH"]
    assert audit["rows"][0]["status"] == "covered"
