import os
from pathlib import Path
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_today_decide import _feed, _gate, _payload
from today_decide import render_today_decide_html


BANNED_URGENCY = ("act now", "don't miss", "or lose", "hurry", "last chance")


def test_passivity_copy_avoids_banned_manufactured_urgency():
    html = render_today_decide_html(_payload()).lower()

    for phrase in BANNED_URGENCY:
        assert phrase not in html


def test_decision_keys_are_ticker_lane_not_card_id():
    payload = _payload()

    for card in payload["cards"] + payload["backlog"]:
        key = card["decision_key"]
        assert key == f'{card["decision_key_parts"]["ticker"]}|{card["decision_key_parts"]["lane"]}'
        assert key != card["card_id"]
        assert not re.search(r"20\d{2}-\d{2}-\d{2}", key)


def test_only_operator_bucket_counts_as_latency_and_gets_open_days():
    payload = _payload()
    passivity = payload["passivity"]
    rows = passivity["rows"]
    operator_rows = [row for row in rows if row["bucket"] == "operator_owned_actionable_now"]

    assert passivity["operator_latency_count"] == len(operator_rows)
    for row in rows:
        if row["bucket"] == "operator_owned_actionable_now":
            assert "open_days" in row
        else:
            assert "open_days" not in row


def test_first_viewport_answers_required_questions_without_hidden_queue():
    payload = _payload()
    html = render_today_decide_html(payload)

    assert "Primary capital/risk decision" in html
    assert "Size/tranche" in html
    assert "Blocked by" in html
    assert "Changed" in html
    assert "Risk rail" in html
    assert "Can wait" in html
    assert "No prior reliable committed build baseline yet" in html
    assert "hidden queue" not in html.lower()


def test_since_last_build_delta_uses_committed_baseline_without_view_state_file():
    baseline = {
        "today_decide": {
            "cards": [
                {
                    "ticker": "MSFT",
                    "decision_card": {"move": {"lane": "reallocation_add"}},
                }
            ],
            "backlog": [],
            "watch_queue": [{"ticker": "FN"}],
            "gates": [{"gate_id": "QQQ-TEST", "symbol": "QQQ", "state": "red"}],
            "data_health": {
                "items": [
                    {"source": "fs_inbox", "label": "FS inbox", "status": "fresh"},
                ]
            },
        }
    }
    gate = _gate()
    gate["state"] = "green"
    payload = _payload(feed=_feed(), gates=[gate], baseline_feed=baseline)
    delta = payload["change_delta"]

    assert delta["label"] == "since last committed build"
    assert delta["status"] == "changed"
    assert any(row["kind"] == "new_decision" and "|" in row["key"] for row in delta["items"])
    assert any(row["kind"] == "gate_flip" for row in delta["items"])
    assert any(row["kind"] == "lane_dark" for row in delta["items"])
    assert all(not re.search(r"20\d{2}-\d{2}-\d{2}", row["key"]) for row in delta["items"])

    repo = Path(__file__).resolve().parents[1]
    assert not (repo / "dashboard_view_state.json").exists()
    assert not (repo / "src" / "dashboard_view_state.json").exists()


def test_change_delta_is_display_only_and_not_in_engine_paths():
    repo = Path(__file__).resolve().parents[1]
    engine_paths = [
        repo / "src" / "directive_recs.py",
        repo / "src" / "conviction_engine.py",
        repo / "src" / "timing_engine.py",
        repo / "src" / "data_health.py",
        repo / "src" / "disposition_log.py",
    ]

    for path in engine_paths:
        assert "change_delta" not in path.read_text(encoding="utf-8")
