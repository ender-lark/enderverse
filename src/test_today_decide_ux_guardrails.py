import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_today_decide import _payload
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
    assert "No prior reliable build baseline yet" in html
    assert "hidden queue" not in html.lower()
