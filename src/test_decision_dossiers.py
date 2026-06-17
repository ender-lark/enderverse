import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import decision_dossiers as dd


def _read(label, text, as_of="2026-06-16", max_age_days=7):
    return {
        "label": label,
        "text": text,
        "as_of": as_of,
        "max_age_days": max_age_days,
        "source": "test",
    }


def _payload(reads=None, status="fresh"):
    base_reads = {
        "edge": _read("Edge/moat", "Durable edge read", max_age_days=90),
        "price": _read("Good buy price?", "Fresh price read", max_age_days=1),
        "timing": _read("Good timing?", "Fresh timing read", max_age_days=1),
        "avoid": _read("What-not / avoid", "Fresh avoid read", max_age_days=90),
    }
    if reads:
        base_reads.update(reads)
    return {
        "generated_at": "2026-06-16",
        "dossiers": {
            "TEST": {
                "ticker": "TEST",
                "status": status,
                "one_liner": "Test one-liner.",
                "notion_url": None,
                "last_reviewed": "2026-06-16",
                "synced_at": "2026-06-16",
                "reads": base_reads,
            }
        },
    }


def test_synced_avgo_dossier_validates_and_keeps_dynamic_reads_not_current():
    payload = dd.load_payload()
    assert dd.validate_payload(payload) == []

    dossier = dd.card_dossier("AVGO", today="2026-06-16")

    assert dossier["status"] == "stale"
    assert dossier["notion_url"].endswith("360c50314bb68150b452e2176b79307f")
    assert dossier["last_reviewed"] == "2026-05-13"
    assert dossier["next_review_due"] == "2026-05-27"
    assert "Custom AI silicon leader" in dossier["one_liner"]
    assert dossier["reads"]["edge"]["freshness"]["status"] == "fresh"
    assert dossier["reads"]["price"]["freshness"]["status"] == "not_checked"
    assert dossier["reads"]["price"]["text"].startswith("UNKNOWN")
    assert dossier["reads"]["timing"]["freshness"]["status"] == "stale"
    assert "review was due 2026-05-27" in dossier["reads"]["timing"]["text"]


def test_fresh_source_status_is_downgraded_when_dynamic_reads_are_stale():
    payload = _payload(
        reads={
            "price": _read(
                "Good buy price?",
                "Buy below a stale level",
                as_of="2026-06-10",
                max_age_days=1,
            )
        },
        status="fresh",
    )
    rows = payload["dossiers"]

    dossier = dd.card_dossier("TEST", dossiers=rows, today="2026-06-16")

    assert dossier["status"] == "stale"
    assert dossier["reads"]["price"]["freshness"]["status"] == "stale"
    assert dossier["reads"]["price"]["text"].startswith("UNKNOWN")
    assert "stale" in dossier["reads"]["price"]["text"]


def test_load_payload_rejects_missing_required_read(tmp_path):
    payload = _payload()
    del payload["dossiers"]["TEST"]["reads"]["timing"]
    path = tmp_path / "decision_dossiers.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(dd.DossierValidationError) as exc:
        dd.load_payload(path)

    assert "missing key" in str(exc.value)


def test_absent_ticker_returns_none():
    assert dd.card_dossier("NONE", dossiers=_payload()["dossiers"], today="2026-06-16") is None
