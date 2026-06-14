import json
from pathlib import Path


SRC = Path(__file__).resolve().parent


def _rows():
    return json.loads((SRC / "catalysts.json").read_text(encoding="utf-8"))


def test_catalysts_json_has_no_duplicate_event_rows():
    keys = [
        (
            str(row.get("ticker") or "").upper(),
            str(row.get("date") or ""),
            str(row.get("label") or "").casefold(),
        )
        for row in _rows()
    ]
    assert len(keys) == len(set(keys))


def test_c5_required_june_and_policy_events_present():
    rows = _rows()
    labels_by_date = {
        (str(row.get("ticker") or "").upper(), str(row.get("date") or "")): str(row.get("label") or "")
        for row in rows
    }

    fomc = labels_by_date[("SPX", "2026-06-17")]
    assert "FOMC" in fomc and "Warsh" in fomc
    assert "SpaceX lockup" in labels_by_date[("SPX", "2026-12-09")]
    assert "midterm elections" in labels_by_date[("SPX", "2026-11-03")]
