import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import disposition_log as dl
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

    assert "Primary command" in html
    assert "Size/tranche" in html
    assert "Blocked by" in html
    assert "Changed" in html
    assert "Risk rail" in html
    assert "Can wait" in html
    assert "No prior reliable committed build baseline yet" in html
    assert "hidden queue" not in html.lower()


def test_command_strip_is_render_only_and_blocks_act_shape_when_resolving():
    payload = _payload()
    strip = payload["command_strip"]

    assert strip["counts"] == {"ACT": 0, "DECIDE": 2, "RESOLVE": 3, "WATCH": 0}
    assert strip["system_state"] == "starved"
    assert "Render-only command surface" in strip["honesty_rule"]

    for card in payload["cards"] + payload["backlog"]:
        taxonomy = card.get("blocker_taxonomy") or {}
        if taxonomy.get("unmet"):
            assert card["command_state"] == "RESOLVE"

    html = render_today_decide_html(payload)
    for card in payload["cards"] + payload["backlog"]:
        if card["command_state"] != "ACT":
            assert f'data-copy="ACT {card["card_id"]}"' not in html


def test_readiness_layers_separate_routine_fire_from_boundary_and_execution():
    payload = _payload()
    html = render_today_decide_html(payload)

    assert "routine fired proof 14/14; boundary data not implied" in html
    assert "scheduled proof 14/14" not in html
    assert "Readiness layers" in html
    assert "Resolve checklist" in html
    assert "Routine fired" in html
    assert "Boundary artifact" in html
    assert "Signal interpreted" in html
    assert "Decision eligible" in html
    assert "Trade executable" in html

    for card in payload["cards"] + payload["backlog"]:
        readiness = card["readiness"]
        layers = {row["key"]: row for row in readiness["layers"]}
        assert layers["routine_fired"]["status"] == "ok"
        assert layers["routine_fired"]["status"] != layers["trade_executable"]["status"]
        if card["command_state"] != "ACT":
            assert layers["trade_executable"]["status"] != "ok"

        checks = {row["key"]: row for row in readiness["checklist"]}
        assert set(checks) == {
            "uw_interpreted", "cash_buying_power", "account_eligibility",
            "cap_room", "research_disconfirmation", "event_risk",
        }


def test_overdue_held_reviews_surface_as_decide_pressure(tmp_path):
    held = tmp_path / "held.json"
    held.write_text(json.dumps([
        {
            "id": "overdue-packet",
            "title": "Overdue packet",
            "parked_date": "2026-06-13",
            "review_by": "2026-06-14",
            "status": "held",
            "notion_url": "https://example.test/overdue",
        },
        {
            "id": "future-packet",
            "title": "Future packet",
            "parked_date": "2026-06-13",
            "review_by": "2026-06-30",
            "status": "held",
        },
        {
            "id": "done-packet",
            "title": "Done packet",
            "parked_date": "2026-06-13",
            "review_by": "2026-06-14",
            "status": "passed",
        },
    ]), encoding="utf-8")

    payload = _payload(today="2026-06-17", held_decisions_path=held)
    pressure = payload["disposition_pressure"]
    html = render_today_decide_html(payload)

    assert pressure["counts"] == {"review_due": 1, "promoted_watch": 0, "total": 1}
    assert pressure["rows"][0]["state"] == "DECIDE"
    assert pressure["rows"][0]["age_days"] == 3
    assert "Review due: Overdue packet" in html
    assert "KEEP HELD" in html and "RECHECK overdue-packet new_review_by: " in html
    assert "Decision pressure" in html
    assert html.index("Decision pressure") < html.index("Ownership-aware passivity")
    assert 'data-copy="ACT ' not in html.split("Decision pressure", 1)[1].split("Ownership-aware passivity", 1)[0]


def test_high_impact_watch_row_promotes_to_decide_and_leaves_watch_queue():
    feed = _feed()
    feed["fed_day_reallocation_packet"] = {
        "as_of": "2026-06-17",
        "higher_quality_pullbacks": [
            {
                "ticker": "RYF",
                "rank_score": 92,
                "pct_below_high": -30,
                "price": 108,
                "current_exposure_usd": 0,
                "source_tags": ["top_prospects:sell_fast"],
                "disconfirmation": "Only re-open if broker beta confirms.",
            },
            {
                "ticker": "FN",
                "rank_score": 88,
                "pct_below_high": -21,
                "price": 592,
                "current_exposure_usd": 7741,
                "source_tags": ["Fundstrat top-list"],
                "disconfirmation": "Needs fresh flow.",
            },
        ],
    }

    payload = _payload(feed=feed, today="2026-06-17", held_decisions_path=None)
    pressure = payload["disposition_pressure"]
    html = render_today_decide_html(payload)

    assert pressure["counts"] == {"review_due": 0, "promoted_watch": 1, "total": 1}
    assert pressure["rows"][0]["decision_key"] == "RYF|higher_quality_pullbacks"
    assert pressure["rows"][0]["title"] == "Decide RYF: avoid new exposure?"
    assert [row["ticker"] for row in payload["watch_queue"]] == ["FN"]
    assert payload["command_strip"]["counts"]["DECIDE"] == 3
    assert payload["command_strip"]["counts"]["WATCH"] == 1
    assert "Decide RYF: avoid new exposure?" in html
    assert "Watchlist / pullback impact queue (1)" in html
    assert "AVOID_NEW RYF reason: " in html


def test_candidate_feed_index_merges_sources_by_ticker_lane():
    feed = _feed()
    feed["asymmetric_opportunities"] = {
        "rows": [{
            "ticker": "GOOGL",
            "source": "uw_opportunity",
            "reason": "same ticker extra context",
        }]
    }
    feed["uw_action_runbook"] = {
        "rows": [{
            "ticker_scope": ["GOOGL"],
            "blocks_action_if": "endpoint proof missing",
        }]
    }

    payload = _payload(feed=feed, today="2026-06-17", held_decisions_path=None)
    index = payload["candidate_feed_index"]
    keys = [row["decision_key"] for row in index["rows"]]
    html = render_today_decide_html(payload)

    assert len(keys) == len(set(keys))
    assert index["counts"]["total"] == len(index["rows"])
    googl_add = next(row for row in index["rows"] if row["decision_key"] == "GOOGL|reallocation_add")
    assert googl_add["state"] == "RESOLVE"
    assert set(googl_add["sources"]) >= {"today_decide_card", "reallocation_brief"}
    assert googl_add["independent_source_count"] >= 2
    assert any(row["decision_key"] == "GOOGL|uw_runbook" for row in index["rows"])
    assert "Merged candidate feeder index" in html
    assert "source families are shown for context only" in html
    assert html.index("Merged candidate feeder index") < html.index("Ownership-aware passivity")


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


def test_command_state_is_display_only_and_not_in_engine_paths():
    repo = Path(__file__).resolve().parents[1]
    engine_paths = [
        repo / "src" / "directive_recs.py",
        repo / "src" / "conviction_engine.py",
        repo / "src" / "timing_engine.py",
        repo / "src" / "data_health.py",
        repo / "src" / "disposition_log.py",
    ]

    for path in engine_paths:
        text = path.read_text(encoding="utf-8")
        assert "command_state" not in text
        assert "command_strip" not in text


def test_readiness_is_display_only_and_not_in_engine_paths():
    repo = Path(__file__).resolve().parents[1]
    engine_paths = [
        repo / "src" / "directive_recs.py",
        repo / "src" / "conviction_engine.py",
        repo / "src" / "timing_engine.py",
        repo / "src" / "data_health.py",
        repo / "src" / "disposition_log.py",
    ]

    for path in engine_paths:
        text = path.read_text(encoding="utf-8")
        assert "readiness" not in text
        assert "trade_executable" not in text

def test_blocker_taxonomy_m_of_n_matches_real_unmet_blockers():
    gate = _gate()
    gate["state"] = "red"
    gate["stated"] = "2026-05-30"
    payload = _payload(gates=[gate])
    cards = payload["cards"] + payload["backlog"]
    enumerable = [
        card for card in cards
        if (card.get("blocker_taxonomy") or {}).get("enumerable")
    ]

    assert enumerable
    for card in enumerable:
        taxonomy = card["blocker_taxonomy"]
        assert taxonomy["met"] == 0
        assert taxonomy["total"] == len(taxonomy["unmet"])
        assert taxonomy["line"].startswith(f'0 of {taxonomy["total"]} blockers cleared')

    html = render_today_decide_html(payload)
    assert "Distance to actionable" in html
    assert any(f'0 of {card["blocker_taxonomy"]["total"]} blockers cleared' in html for card in enumerable)
    assert "never means the move is ready" in html


def test_size_to_goal_never_renders_goal_percent_without_survival_rails():
    payload = _payload()
    buy_cards = [
        card for card in payload["cards"] + payload["backlog"]
        if str(((card.get("decision_card") or {}).get("move") or {}).get("direction") or card.get("direction") or "").upper() in {"BUY", "ADD"}
    ]

    assert buy_cards
    for card in buy_cards:
        model = card.get("size_to_goal") or {}
        line = str(model.get("line") or "").lower()
        assert "% of goal gap" in line
        for token in ("cap room", "funding source", "concentration", "account eligibility", "leverage/margin"):
            assert token in line

    html = render_today_decide_html(payload)
    assert "Size to goal with rails" in html
    for line in re.findall(r'<div class="td-size-goal-line">([^<]+)</div>', html):
        low = line.lower()
        assert "% of goal gap" in low
        for token in ("cap room", "funding source", "concentration", "account eligibility", "leverage/margin"):
            assert token in low


def test_disposition_coverage_does_not_promote_watch_social_or_research_rows():
    feed = _feed()
    feed["actions"].append({"ticker": "AVGO", "kind": "lean_in", "what": "FS lean-in: AVGO"})
    feed["research_actions"] = [{"ticker": "RDDT", "what": "research only: RDDT"}]
    feed["prospects"] = [{"ticker": "CRWD", "title": "prospect only: CRWD"}]
    feed["social_watch"] = {"rows": [{"ticker": "XYZ", "label": "social watch only: XYZ"}]}
    payload = _payload(feed=feed)
    coverage = payload["disposition_coverage"]
    rows = coverage["rows"]

    assert coverage["counts"]["not_covered"] >= 4
    assert any(row["ticker"] == "AVGO" and row["status"] == "could_promote_to_today_decide" for row in rows)
    for source in {"research_actions", "prospects", "social_watch"}:
        assert any(row["source"] == source and row["status"] == "intentionally_watch_research_only" for row in rows)
    assert "not promoted into trade cards" in coverage["honesty_rule"]


def test_after_action_loop_shows_age_next_review_and_open_state(tmp_path):
    seed = _payload(tmp_path=tmp_path)
    card = seed["cards"][0]
    pth = tmp_path / "dispositions.jsonl"
    dl.append_disposition(
        "2026-06-10",
        card["card_id"],
        card["ticker"],
        "RECHECK",
        resurface_date="2026-06-15",
        path=pth,
    )
    payload = _payload(dispositions_path=pth, tmp_path=tmp_path)
    updated = next(row for row in payload["cards"] + payload["backlog"] if row["card_id"] == card["card_id"])
    after = updated["after_action"]

    assert after["verb"] == "RECHECK"
    assert after["age_days"] == 0
    assert after["next_review_date"] == "2026-06-15"
    assert after["open"] is True
    html = render_today_decide_html(payload)
    assert "last disposition: RECHECK on 2026-06-10" in html
    assert "next review 2026-06-15" in html
    assert "open" in html
