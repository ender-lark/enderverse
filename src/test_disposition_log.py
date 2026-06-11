import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import disposition_log as dl


def test_append_disposition_roundtrip_and_open_cards_with_undo(tmp_path):
    p = tmp_path / "dispositions.jsonl"
    dl.append_disposition("2026-06-10", "AAA-ADD-2026-06-10", "AAA", "ACT", path=p)
    dl.append_disposition(
        "2026-06-10", "BBB-ADD-2026-06-10", "BBB", "PASS", reason="shadowed by risk",
        path=p,
    )
    dl.append_disposition("2026-06-11", "BBB-ADD-2026-06-10", "BBB", "UNDO", path=p)

    cards = [
        {"card_id": "AAA-ADD-2026-06-10", "ticker": "AAA"},
        {"card_id": "BBB-ADD-2026-06-10", "ticker": "BBB"},
        {"card_id": "CCC-ADD-2026-06-10", "ticker": "CCC"},
    ]
    open_cards = dl.load_open_cards(cards, path=p)
    assert [c["card_id"] for c in open_cards] == ["BBB-ADD-2026-06-10", "CCC-ADD-2026-06-10"]


def test_pass_requires_reason_and_maps_to_action_memory(tmp_path):
    p = tmp_path / "dispositions.jsonl"
    with open(p, "w", encoding="utf-8"):
        pass
    try:
        dl.append_disposition("2026-06-10", "AAA", "AAA", "PASS", path=p)
        assert False, "PASS without reason must fail"
    except ValueError:
        pass

    assert dl.map_to_action_memory("ACT") == "acted"
    assert dl.map_to_action_memory("PASS") == "ignored"
    assert dl.map_to_action_memory("RECHECK") == "deferred"
    assert dl.map_to_action_memory("UNDO") is None


def test_orphan_escalation_marks_escalate_and_pin():
    rows = [
        {"card_id": "AAA", "first_flagged": "2026-06-01"},
        {"card_id": "BBB", "first_flagged": "2026-06-04"},
        {"card_id": "CCC", "first_flagged": "2026-06-09"},
    ]
    out = dl.orphan_escalation(
        rows,
        as_of="2026-06-10",
        tunables={"orphan_escalate_days": 3, "orphan_pin_days": 7},
    )
    assert [r["orphan_state"] for r in out] == ["pin", "escalate", "open"]


def test_lookback_30d_scores_act_and_pass_using_add_price_stubs(tmp_path):
    disp = tmp_path / "dispositions.jsonl"
    tp = tmp_path / "top_prospects.json"
    tp.write_text(
        '{"AAA":{"add_price":100.0,"add_date":"2026-05-01"},'
        '"BBB":{"add_price":50.0,"add_date":"2026-05-01"}}',
        encoding="utf-8",
    )
    dl.append_disposition("2026-06-10", "A", "AAA", "ACT", path=disp)
    dl.append_disposition("2026-06-09", "P", "BBB", "PASS", reason="not ready", path=disp)
    calls = {}

    def price(ticker, on_date=None):
        if on_date:
            calls[f"{ticker}|{on_date}"] = calls.get(f"{ticker}|{on_date}", 0) + 1
        return {"AAA": 120.0, "BBB": 47.0, "SPY": 420.0}.get(ticker)

    rows = dl.lookback_30d(
        disp,
        as_of="2026-06-10",
        top_prospects_path=tp,
        price_fn=price,
        window_days=30,
    )
    assert [r["verb"] for r in rows] == ["ACT", "PASS"]
    assert rows[0]["pct_since_add"] == 0.2
    assert rows[1]["pct_since_add"] == -0.06
    assert "pct_vs_spy" in rows[0]
