import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import decision_dossiers as dd
import decision_dossier_sync as sync


def _avgo_page():
    return {
        "url": "https://app.notion.com/p/360c50314bb68150b452e2176b79307f",
        "properties": {
            "Ticker": "AVGO",
            "Thesis Status": "Stable",
            "Stance": "ACTIVE",
            "Tier": "Buy-and-Hold",
            "Anchor Source": "Multiple",
            "Anchor Status": "INTACT",
            "Named Anchor": "Custom AI silicon leader; Meta/Google/MSFT ASIC contracts.",
            "Active Risks Named": "Custom-silicon vs merchant-silicon competitive dynamics.",
            "Exit Conditions": "Thesis break: hyperscaler in-housing ASIC capacity displaces AVGO custom silicon at scale.",
            "Factor Bucket": "ai_complex",
            "Forward Catalyst": "",
            "date:Anchor Date:start": "2024-06-01",
            "date:Last Two-Lens Run:start": "2026-05-13",
            "date:Next Review Due:start": "2026-05-27",
        },
    }


def test_live_thesis_row_maps_to_stale_avgo_dossier_without_action_signal():
    row = sync.dossier_from_live_thesis(_avgo_page(), today="2026-06-16")

    assert row["ticker"] == "AVGO"
    assert row["status"] == "stale"
    assert row["notion_url"].endswith("360c50314bb68150b452e2176b79307f")
    assert row["last_reviewed"] == "2026-05-13"
    assert row["next_review_due"] == "2026-05-27"
    assert "Custom AI silicon leader" in row["reads"]["edge"]["text"]
    assert row["reads"]["price"]["text"].startswith("UNKNOWN")
    assert row["reads"]["timing"]["as_of"] == "2026-05-27"
    assert "hyperscaler in-housing" in row["reads"]["avoid"]["text"]

    card = dd.card_dossier("AVGO", dossiers={"AVGO": row}, today="2026-06-16")
    assert card["status"] == "stale"
    assert card["next_review_due"] == "2026-05-27"
    assert card["reads"]["edge"]["freshness"]["status"] == "fresh"
    assert card["reads"]["price"]["freshness"]["status"] == "not_checked"
    assert card["reads"]["timing"]["freshness"]["status"] == "stale"


def test_connector_fetch_payload_can_be_used_when_query_tool_is_unavailable():
    outer = {
        "title": "AVGO",
        "url": "https://app.notion.com/p/360c50314bb68150b452e2176b79307f",
        "text": (
            '<page url="https://app.notion.com/p/360c50314bb68150b452e2176b79307f">'
            "<properties>\n"
            + json.dumps(_avgo_page()["properties"])
            + "\n</properties>"
            "</page>"
        ),
    }
    payload = {"content": [{"type": "text", "text": json.dumps(outer)}]}

    pages = sync.pages_from_connector_fetch(payload)
    row = sync.dossier_from_live_thesis(pages[0], today="2026-06-16")

    assert len(pages) == 1
    assert row["ticker"] == "AVGO"
    assert row["notion_url"].endswith("360c50314bb68150b452e2176b79307f")


def test_build_payload_preserves_existing_rows_and_marks_missing_requested_ticker_pending():
    existing = {
        "generated_at": "2026-06-15",
        "dossiers": {
            "OLD": {
                "ticker": "OLD",
                "status": "fresh",
                "one_liner": "Old row",
                "reads": {
                    key: {
                        "label": key,
                        "text": "Existing read",
                        "as_of": "2026-06-15",
                        "max_age_days": 90,
                        "source": "test",
                    }
                    for key in dd.READ_KEYS
                },
            }
        },
    }

    payload = sync.build_payload(
        [_avgo_page()],
        existing=existing,
        tickers=["AVGO", "NONE"],
        today="2026-06-16",
        sync_status="synced_from_verified_connector_fetch",
    )

    assert dd.validate_payload(payload) == []
    assert payload["dossiers"]["OLD"]["one_liner"] == "Old row"
    assert payload["dossiers"]["AVGO"]["status"] == "stale"
    assert payload["dossiers"]["NONE"]["status"] == "pending_sync"
    assert "staleness guard" in payload["source"]["alert_sequence_note"]
