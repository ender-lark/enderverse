import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fs_ingest_guard as guard


def _layer():
    return [{"source_id": "fundstrat_sector_allocation:2026-06-11", "title": "June Sector"}]


def test_guard_fires_on_skipped_sections():
    inventory = {
        "entries": [
            {
                "source_id": "fundstrat_sector_allocation:2026-06-11",
                "title": "June Sector",
                "ingested_at": "2026-06-12T12:00:00Z",
                "total_sections": 2,
                "sections": [
                    {"name": "rating changes", "status": "distilled"},
                    {"name": "tactical top/bottom", "status": "skipped"},
                ],
            }
        ]
    }

    findings = guard.check(inventory, _layer())

    assert len(findings) == 1
    assert findings[0]["key"] == "fs_ingest_partial"
    assert "1 of 2 sections never distilled" in findings[0]["line"]
    assert findings[0]["skipped_sections"] == ["tactical top/bottom"]


def test_guard_quiet_on_complete_inventory():
    inventory = {
        "entries": [
            {
                "source_id": "fundstrat_sector_allocation:2026-06-11",
                "title": "June Sector",
                "ingested_at": "2026-06-12T12:00:00Z",
                "sections": [
                    {"name": "rating changes", "status": "distilled"},
                    {"name": "tactical top/bottom", "status": "distilled"},
                ],
            }
        ]
    }

    assert guard.check(inventory, _layer()) == []


def test_guard_fires_on_missing_inventory_for_active_layer():
    findings = guard.check({"entries": []}, _layer())

    assert len(findings) == 1
    assert findings[0]["key"] == "fs_ingest_inventory_missing"
    assert "inventory missing" in findings[0]["line"]


def test_active_bible_layers_derive_live_layer_ids():
    layers = guard.active_bible_layers({
        "deck_date": "2026-06-11",
        "core_stock_ideas_as_of": "2026-05-28",
        "top5": ["AMD"],
        "sector_allocation": {"as_of": "2026-06-11"},
    })

    ids = [row["source_id"] for row in layers]
    assert ids == [
        "fundstrat_sector_allocation:2026-06-11",
        "fundstrat_core_stock_ideas:2026-05-28",
    ]


def test_upsert_inventory_replaces_same_source_id(tmp_path):
    path = tmp_path / "fs_ingest_inventory.json"
    guard.upsert_inventory(path, {
        "source_id": "source-1",
        "title": "Old",
        "sections": [{"name": "body", "status": "skipped"}],
    })
    guard.upsert_inventory(path, {
        "source_id": "source-1",
        "title": "New",
        "sections": [{"name": "body", "status": "distilled"}],
    })

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert len(payload["entries"]) == 1
    assert payload["entries"][0]["title"] == "New"
    assert payload["entries"][0]["skipped_count"] == 0
