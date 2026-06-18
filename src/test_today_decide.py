import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import disposition_log as dl
from today_decide import (
    build_conviction_display,
    build_today_decide_payload,
    detect_source_conflicts,
    render_today_decide_html,
)
from tunables import load_conviction_weights, load_goal_tunables

TODAY = "2026-06-10"
W = load_conviction_weights()
G = load_goal_tunables()

def _gate():
    return {
        "gate_id": "QQQ-TEST", "symbol": "QQQ", "kind": "support_band",
        "level_low": 695.0, "level_high": 705.0, "state": "red_but_tested",
        "source": "newton", "stated": "2026-06-08", "note": "band",
        "confirm_rule": "holds above ~705", "applies_to": ["ai_semis"],
        "blocks_full_size": True,
    }

def _accounts():
    base = {"crypto_only": False, "tax_type": "taxable",
            "tax_flag": "TAXABLE â€” gains realize", "option_value": 0.0}
    return [
        {**base, "owner": "Parents", "broker": "Fidelity", "account": "Joint WROS",
         "etf_only": False, "total_value": 612000.0,
         "holdings": {"NVDA": 50000.0, "MAGS": 20000.0}},
        {**base, "owner": "Parents", "broker": "Schwab", "account": "PCRA Trust",
         "etf_only": True, "total_value": 368000.0,
         "holdings": {"MAGS": 19710.0}, "tax_type": "traditional_ira",
         "tax_flag": "tax-advantaged (no cap-gains)"},
        {**base, "owner": "SKB", "broker": "Robinhood", "account": "Trad IRA",
         "etf_only": False, "total_value": 180000.0,
         "holdings": {"GOOGL": 10000.0}, "tax_type": "traditional_ira",
         "tax_flag": "tax-advantaged (no cap-gains)"},
    ]

def _insights():
    return {"insights": [{
        "insight_id": "INSIGHT-950", "statement": "s", "polarity": "bullish",
        "belief_strength": 50, "status": "ACTIVE", "stated": TODAY,
        "last_reviewed": TODAY, "sectors": [], "keywords": [],
        "tickers_mapped": ["GOOGL"], "tickers_adjacent": [], "watch_tickers": [],
        "factor_tags": [], "evidence_for": [], "evidence_against": [],
    }]}

def _feed():
    return {
        "portfolio_views": {"views": {"combined": {
            "rows": [{"ticker": "NVDA", "market_value": 50000}],
            "total_value": 1890000,
        }}},
        "actions": [
            {"ticker": "GOOGL", "goal_score": 80, "kind": "lean_in",
             "what": "FS lean-in: GOOGL"},
            {"ticker": "MAGS", "goal_score": 70, "kind": "lean_in",
             "what": "FS lean-in: hold/add MAGS"},
        ],
        "reallocation_brief": {
            "positions_snapshot_date": "2026-06-09",
            "rows": [
                {"ticker": "GOOGL", "notional_usd": 151266, "current_pct": 0.0,
                 "target_pct": 8.0, "sequence": "now", "entry_note": "x", "gate": "QQQ"},
                {"ticker": "NVDA", "notional_usd": 56609, "current_pct": 5.0,
                 "target_pct": 8.0},
            ],
            "trims": [
                {"ticker": "MAGS", "notional_usd": 70216, "current_pct": 3.7,
                 "target_pct": 0.0,
                 "funds": [{"ticker": "NVDA", "notional_usd": 51500}]},
            ],
            "funding": {"pool_usd": 503646, "shortfall_usd": 211916},
        },
        "target_drift": {"rows": [{"ticker": "MAGS", "direction": "OVERSIZED"}]},
        "event_risk": {"rows": []},
    }

def _congruence(flagged=True):
    return {
        "status": "ok", "total_value": 1890000.0, "flag_threshold_named_pct": 1.0,
        "rows": [{
            "insight_id": "INSIGHT-950", "statement": "s", "belief_strength": 50,
            "stale": False, "named_pct": 0.23, "combined_pct": 0.23,
            "flagged": flagged,
            "flag_note": "STRONGEST BELIEF Â· SMALLEST EXPOSURE" if flagged else "",
            "line": "named $4,268 (0.23%) â€” TSM",
        }],
        "flagged_ids": ["INSIGHT-950"] if flagged else [],
    }

def _payload(
    goal=None,
    congruence_result=None,
    tmp_path=None,
    dispositions_path=None,
    feed=None,
    gates=None,
    today=TODAY,
    baseline_feed=None,
    held_decisions_path=None,
):
    return build_today_decide_payload(
        feed=feed or _feed(), weights=W, goal=goal or G, insights_payload=_insights(),
        accounts=_accounts(), gates=(gates if gates is not None else [_gate()]), uw_states={}, entry_zones={},
        congruence_result=congruence_result or _congruence(),
        dispositions_path=(dispositions_path if dispositions_path else
                           (tmp_path / "none.jsonl" if tmp_path else "_no_dispositions_.jsonl")),
        held_decisions_path=held_decisions_path,
        baseline_feed=baseline_feed,
        load_committed_baseline=False,
        today=today,
    )

def test_payload_builds_and_goal_anchor_math():
    p = _payload()
    ga = p["goal_anchor"]
    assert ga["book_value"] == 1890000.0 and ga["fi_target"] == 3000000.0
    assert ga["pct_to_target"] == 63.0 and ga["gap_usd"] == 1110000.0
    assert "display-only" in ga["pace_line"]
    assert p["plan_line"]["positions_as_of"] == "2026-06-09"
    assert p["first_viewport"]["status"] == "has_primary"
    assert p["first_viewport"]["command_state"] == "RESOLVE"
    assert p["first_viewport"]["button"]["label"] == "RESOLVE"
    assert not p["first_viewport"]["button"]["copy"].startswith("ACT ")
    assert p["command_strip"]["counts"]["ACT"] == 0
    assert p["command_strip"]["counts"]["RESOLVE"] == 3
    assert "Render-only command surface" in p["command_strip"]["honesty_rule"]
    automation = next(row for row in p["trust_panel"]["items"] if row["label"] == "Automations")
    assert automation["detail"] == "routine fired proof 14/14; boundary data not implied"
    readiness = p["first_viewport"]["readiness"]
    assert [row["key"] for row in readiness["layers"]] == [
        "routine_fired", "boundary_artifact", "signal_interpreted", "decision_eligible", "trade_executable",
    ]
    layer_status = {row["key"]: row["status"] for row in readiness["layers"]}
    assert layer_status["routine_fired"] == "ok"
    assert layer_status["boundary_artifact"] == "unknown"
    assert layer_status["trade_executable"] == "blocked"
    assert "only the first layer" in readiness["honesty_rule"]
    assert {row["key"] for row in readiness["checklist"]} == {
        "uw_interpreted", "cash_buying_power", "account_eligibility",
        "cap_room", "research_disconfirmation", "event_risk",
    }
    assert p["change_delta"]["status"] == "no_baseline"
    assert p["passivity"]["honesty_rule"].startswith("Only bucket operator_owned_actionable_now")

def test_pace_is_display_only_and_isolated():
    p1 = _payload()
    g2 = copy.deepcopy(G)
    g2["fi_target"] = 6_000_000
    p2 = _payload(goal=g2)
    pri1 = [c["priority"] for c in p1["cards"] + p1["backlog"]]
    pri2 = [c["priority"] for c in p2["cards"] + p2["backlog"]]
    assert pri1 == pri2  # fi_target moved, ranking untouched
    assert p1["goal_anchor"]["pace_line"] != p2["goal_anchor"]["pace_line"]
    html = render_today_decide_html(p1)
    assert html.count("display-only") == 1  # pace appears once, in the anchor only

def test_html_renders_header_and_built_date():
    html = render_today_decide_html(_payload())
    assert "TODAY â€” DECIDE" in html and f"built {TODAY}" in html
    assert 'id="today-decide"' in html


def test_html_renders_minimal_conviction_face_and_breakdown():
    html = render_today_decide_html(_payload())
    assert "Primary command" in html
    assert "0 ACT | 2 DECIDE | 3 RESOLVE | 0 WATCH" in html
    assert "Resolve GOOGL add" in html
    assert "Readiness layers" in html
    assert "Routine fired" in html
    assert "Boundary artifact" in html
    assert "Signal interpreted" in html
    assert "Trade executable" in html
    assert "Resolve checklist" in html
    assert "UW interpreted" in html
    assert "routine fired proof 14/14; boundary data not implied" in html
    assert 'data-copy="ACT GOOGL-ADD-2026-06-10"' not in html
    assert "Ownership-aware passivity" in html
    assert "Nothing actionable yet: scorer is starved or blocked, not bearish." in html
    assert "Next lever: fresh-check material names" in html
    assert "Stage $151,266 GOOGL buy" in html
    assert "$151,266 / material" in html
    assert "Name: supportive LOW | Sector: supportive LOW | Shadow: LOW" not in html
    assert "Conviction 1/5 LOW" in html
    assert "Conviction to Buy GOOGL:" not in html
    assert "Current answer" in html
    assert "Evidence that matters" in html
    assert "Name / sector split" in html
    assert "What would make this actionable" in html
    assert "Operator can do now" in html
    assert "System still needs wired" in html
    assert "IV options-vs-shares" in html
    assert "not checked:" in html
    assert "LOW 0." not in html
    assert "MODERATE 0." not in html
    assert "HIGH 0." not in html
    why_block = html.split("Evidence that matters", 1)[1].split("What would make this actionable", 1)[0]
    factor_pos = min(
        pos for pos in (why_block.find("bullish setup"), why_block.find("opposes card action"), why_block.find("context"))
        if pos >= 0
    )
    assert factor_pos < why_block.find("Fundstrat / source calls")

def test_top_panel_separates_trust_from_card_scoped_gates():
    html = render_today_decide_html(_payload())
    assert "Can I trust this screen?" in html
    assert "Source scoring is OFF" in html
    assert "FS inbox" in html
    assert "Core data" in html
    assert 'class="td-gates-full"' not in html
    assert "RED BUT TESTED" not in html
    assert "Capped to stage-only until holds above ~705" in html

def test_card_count_respects_daily_max():
    p = _payload()
    assert len(p["cards"]) <= G["daily_card_max"]
    assert len(p["cards"]) + len(p["backlog"]) == 3

def test_pcra_exclusion_rendered_on_stock_buys():
    html = render_today_decide_html(_payload())
    assert "ETF-ONLY" in html and "PCRA" in html

def test_caps_sizing_renders_on_buy_cards():
    html = render_today_decide_html(_payload())
    assert "sizing: caps suggested" in html
    assert "cap basis:" in html


def test_avgo_dossier_renders_with_stale_dynamic_reads():
    feed = _feed()
    feed["actions"].append({"ticker": "AVGO", "goal_score": 65, "kind": "lean_in"})
    feed["reallocation_brief"]["rows"].append(
        {"ticker": "AVGO", "notional_usd": 25000, "current_pct": 0.0, "target_pct": 6.0}
    )
    p = _payload(feed=feed)
    avgo = [c for c in p["cards"] + p["backlog"] if c["ticker"] == "AVGO"][0]

    assert avgo["dossier"]["status"] == "stale"
    assert "AVGO dossier" in p["data_health"]["blockers"]
    assert "AVGO dossier" in avgo["card_blockers"]
    assert all(
        "AVGO dossier" not in card["card_blockers"]
        for card in p["cards"] + p["backlog"]
        if card["ticker"] != "AVGO"
    )
    html = render_today_decide_html(p)

    assert "Decision dossier: AVGO" in html
    assert "Custom AI silicon leader" in html
    assert "due: 2026-05-27" in html
    assert "Good buy price? (not_checked):" in html
    assert "Good timing? (stale):" in html
    assert "UNKNOWN - no forward catalyst is mirrored" in html


def test_conviction_display_payload_contract_for_buy_and_not_checked():
    p = _payload()
    googl = [c for c in p["cards"] + p["backlog"] if c["ticker"] == "GOOGL"][0]
    display = googl["conviction_display"]

    assert display["text"].startswith("Conviction to Buy GOOGL:")
    assert display["band"] in {"LOW", "MODERATE", "HIGH"}
    assert display["band_color"]
    assert display["why"]["groups"]
    assert "Fundstrat / source calls" in {row["label"] for row in display["why"]["groups"]}
    assert isinstance(display["why"]["decisive_factors"], list)
    assert display["layers"]["mode"] == "shadow"
    assert {row["key"] for row in display["layers"]["rows"]} == {"name", "sector", "overall"}
    assert display["raises"]
    assert display["iv_hint"]["status"] == "not_checked"
    assert "institutional" in display["not_checked"]


def test_conviction_display_renders_shadow_layer_guards():
    display = build_conviction_display({
        "ticker": "NVDA",
        "direction": "BUY",
        "decision_card": {"move": {"direction": "BUY"}},
        "conviction": {
            "ticker": "NVDA",
            "direction": "BUY",
            "strength_5": 2,
            "read": "LOW",
            "groups": {"fs": 0.0, "uw": 0.0, "operator_insight": 0.0, "institutional": 0.0},
            "raises": [],
            "not_checked": [],
            "battery": {"battery_summary": {"decisive_factors": [], "iv_hint": {"status": "not_checked"}}},
            "conviction_layers": {
                "mode": "shadow",
                "name": {"status": "checked_no_signal", "points": 0.0, "read": "LOW", "direction": "NEUTRAL"},
                "sector": {"status": "active", "points": 1.0, "read": "LOW", "direction": "BUY", "category": "AI / Semiconductors"},
                "overall": {
                    "points_decimal": 0.33,
                    "read": "LOW",
                    "direction": "BUY",
                    "sector_lift": 0.33,
                    "sector_lift_cap": 0.5,
                    "conflict": None,
                    "clamped_reasons": [],
                    "sector_only_recheck": {
                        "eligible": True,
                        "alert_enabled": False,
                        "next_step": "re-check the name; sector support alone is not a buy signal",
                    },
                    "formula_version": "shadow_v1",
                },
            },
        },
    })

    assert display["layers"]["sector_only_recheck"]["eligible"] is True
    assert display["layers"]["rows"][1]["status"] == "active"


def test_conviction_display_handles_strong_sell_and_battery_conflict():
    strong_sell = build_conviction_display({
        "ticker": "MAGS",
        "direction": "SELL",
        "decision_card": {"move": {"direction": "SELL"}},
        "conviction": {
            "ticker": "MAGS",
            "direction": "SELL",
            "strength_5": 5,
            "read": "HIGH",
            "groups": {"fs": -1.2, "uw": 0.0, "operator_insight": 0.0, "institutional": 0.0},
            "raises": ["current target break confirmed"],
            "not_checked": ["institutional"],
            "battery": {"battery_summary": {"decisive_factors": [], "iv_hint": {"status": "not_checked"}}},
        },
    })
    assert strong_sell["text"] == "Conviction to Sell MAGS: 5/5 (HIGH)"
    assert strong_sell["conflict"] is None

    conflicted = build_conviction_display({
        "ticker": "MAGS",
        "direction": "SELL",
        "decision_card": {"move": {"direction": "SELL"}},
        "conviction": {
            "ticker": "MAGS",
            "direction": "SELL",
            "strength_5": 4,
            "read": "HIGH",
            "groups": {"fs": -1.0, "uw": 0.0, "operator_insight": 0.0, "institutional": 0.0},
            "raises": [],
            "not_checked": [],
            "battery": {"battery_summary": {"decisive_factors": [{
                "key": "uw_opportunity_sweep",
                "label": "UW opportunity sweep",
                "direction": "bull",
                "strength": 0.9,
                "value_str": "ask-side call sweeps",
                "source": "test",
                "decisive": True,
            }], "iv_hint": {"status": "not_checked"}}},
        },
    })
    assert "battery" in conflicted["conflict"]
    assert conflicted["why"]["decisive_factors"][0]["conflict"] is True

def test_wrapper_etf_cards_disclose_lookthrough_overlap():
    feed = _feed()
    feed["reallocation_brief"]["rows"].append(
        {"ticker": "SMH", "notional_usd": 25000, "current_pct": 4.0, "target_pct": 5.0}
    )
    p = _payload(feed=feed)
    smh = [c for c in p["cards"] + p["backlog"] if c["ticker"] == "SMH"][0]

    assert smh["lookthrough"]["contains_line"].startswith("contains NVDA 14.5%")
    assert "AVGO 6.1%" in smh["lookthrough"]["contains_line"]
    assert smh["lookthrough"]["overlap_line"] == "overlap with held singles: NVDA 14.5%"

    html = render_today_decide_html(p)
    assert "look-through: contains NVDA 14.5%" in html
    assert "AVGO 6.1%" in html
    assert "overlap with held singles: NVDA 14.5%" in html

def test_mags_source_conflict_chip_renders():
    p = _payload()
    mags = [c for c in p["cards"] + p["backlog"] if c["ticker"] == "MAGS"][0]
    assert mags["conflicts"] and mags["conflicts"][0]["with"] == "lean_in lane"
    assert mags["conviction_display"]["conflict"]
    html = render_today_decide_html(p)
    assert "Source conflict:" in html and "hold/add MAGS" in html
    assert "Conviction to Sell MAGS" not in html
    assert "Resolve signal before selling MAGS" in html
    assert "resolve direction" in html
    assert "candidate SELL; blockers or conflicts must clear first" in html

def test_immaterial_funding_leg_is_not_a_standalone_sell():
    payload = {
        "built": TODAY,
        "goal_anchor": {"pace_line": "display-only"},
        "plan_line": {},
        "gates": [],
        "data_health": {"items": []},
        "cards": [{
            "card_id": "MAGS-FUND-TEST",
            "ticker": "MAGS",
            "direction": "SELL",
            "dollars": 400.0,
            "card_blockers": [],
            "conflicts": [{"with": "lean_in lane", "their_claim": "Lean-in looks good", "card_claim": "SELL $400"}],
            "decision_card": {
                "move": {"direction": "SELL", "lane": "funding_trim", "band": "$400"},
                "evidence": {"links": [{"label": "funds -> GOOGL $400", "ref": "feed.reallocation_brief.trims"}]},
            },
            "window": {"class": "STAGE-ONLY", "reasons": ["funding leg - execute paired with the adds it funds"], "flips": []},
            "execution": {"legs": [{"owner": "SKB", "broker": "Fidelity", "account": "HSA", "sell_usd": 400, "tax_flag": "tax-advantaged"}]},
            "impact": {"band": "about $400", "material": False},
            "recheck_date": TODAY,
            "conviction_display": {
                "text": "Conviction to Sell MAGS: 1/5 (LOW)",
                "x5": 1,
                "band": "LOW",
                "band_color": "#fb923c",
                "conflict": "no directional evidence; battery opposition: UW opportunity sweep",
                "why": {
                    "groups": [],
                    "decisive_factors": [{
                        "key": "uw_opportunity_sweep",
                        "label": "UW opportunity sweep",
                        "direction": "bull",
                        "strength": 0.9,
                        "value_str": "ask-side call sweeps (as_of 2026-06-01)",
                        "decisive": True,
                        "conflict": True,
                    }],
                },
                "layers": {"mode": "shadow", "rows": [
                    {"key": "name", "label": "Name-specific", "status": "not_checked", "points": 0, "read": "LOW", "direction": "NEUTRAL"},
                    {"key": "sector", "label": "Sector/sleeve", "status": "checked_no_signal", "points": 0, "read": "LOW", "direction": "NEUTRAL"},
                    {"key": "overall", "label": "Shadow overall", "status": "shadow", "points": 0, "read": "LOW", "direction": "NEUTRAL"},
                ]},
                "raises": [
                    "A dated entry/stop/target call (Tier A) on MAGS",
                    "State the thesis if you believe it",
                    "13F/insider lane goes live",
                ],
                "iv_hint": {"status": "not_checked", "hint": "IV not checked"},
                "not_checked": ["institutional"],
            },
        }],
        "backlog": [],
        "honesty": {},
        "congruence": {},
    }
    html = render_today_decide_html(payload)

    assert "funding sell only" in html
    assert "$400 funding sell" in html
    assert "only if paired with the buy it funds" in html
    assert "$400 / immaterial" in html
    assert "Funding sell. Only do this alongside the GOOGL $400 add" in html
    assert "Pair this sell with:" in html and "GOOGL $400 add" in html
    assert "Stale context, not current edge" in html
    assert "already-played or expired" in html
    assert "stale bullish context" in html
    assert "Signal/action split:" in html
    assert "funding sell only; do not sell standalone" in html
    assert "PAIR &amp; FUND" in html
    assert "Waiting on" in html
    operator_block = html.split("Operator can do now", 1)[1].split("Waiting on", 1)[0]
    assert "dated entry/stop/target" not in operator_block
    next_check_block = html.split("Next check", 1)[1].split("Score", 1)[0]
    assert "dated entry/stop/target" not in next_check_block
    assert "State the thesis" in next_check_block
    assert "dated entry/stop/target" in html.split("Waiting on", 1)[1]
    assert "plumbing" not in html.lower()

def test_rails_carry_exact_copy_payloads():
    p = _payload()
    html = render_today_decide_html(p)
    cid = p["cards"][0]["card_id"]
    assert f'data-copy="RECHECK {cid} candidate only; confirm gates before action"' in html
    assert f'data-copy="ACT {cid}"' not in html
    assert f'data-copy="PASS {cid} â€” reason: "' in html
    assert "UNDO " in html  # second-tap undo path in the script


def test_stage_only_cards_show_candidate_not_buy_sell_first():
    p = _payload()
    p["data_health"]["blockers"] = []
    html = render_today_decide_html(p)
    googl = [c for c in p["cards"] + p["backlog"] if c["ticker"] == "GOOGL"][0]

    assert "Stage $151,266 GOOGL buy" in html
    assert "Conviction to Buy GOOGL" not in html
    assert f'data-copy="RECHECK {googl["card_id"]} candidate only; confirm gates before action"' in html
    assert f'data-copy="RECHECK {googl["card_id"]} resurface 2026-06-15"' in html


def test_payload_scopes_stale_gate_blockers_to_applicable_cards():
    stale_gate = _gate()
    stale_gate["stated"] = "2026-06-01"
    p = _payload(gates=[stale_gate])
    by_ticker = {card["ticker"]: card for card in p["cards"] + p["backlog"]}

    assert "QQQ gate" in p["data_health"]["blockers"]
    assert by_ticker["GOOGL"]["card_blockers"] == ["QQQ gate"]
    assert by_ticker["MAGS"]["card_blockers"] == []


def test_renderer_uses_card_scoped_blockers_not_global_blocked_state():
    stale_gate = _gate()
    stale_gate["stated"] = "2026-06-01"
    feed = _feed()
    feed["actions"] = [row for row in feed["actions"] if row["ticker"] != "MAGS"]
    p = _payload(feed=feed, gates=[stale_gate])

    html = render_today_decide_html(p)

    assert html.count("Stage $151,266 GOOGL buy") == 1
    assert "Can I trust this screen?" in html
    assert "Capped to stage-only until holds above ~705" in html
    assert "Conviction to Buy GOOGL" not in html
    mags = [c for c in p["cards"] + p["backlog"] if c["ticker"] == "MAGS"][0]
    assert "QQQ gate" not in mags["card_blockers"]
    assert mags["command_state"] == "RESOLVE"
    assert 'data-copy="ACT MAGS-TRIM-2026-06-10"' not in html
    assert 'data-copy="RECHECK MAGS-TRIM-2026-06-10 named blocker must clear"' in html


def test_live_gate_evaluation_overrides_stale_stored_state_on_cards():
    feed = _feed()
    feed["current_closes"] = {"QQQ": 721.34}
    gate = _gate()
    gate.update({
        "gate_type": "close",
        "level_low": 717.5,
        "level_high": 717.5,
        "state": "red_but_tested",
        "stated": "2026-06-11",
        "confirm_rule": "full size only after QQQ closes/holds above 717.50",
        "applies_to": ["*BUY*"],
    })
    p = _payload(feed=feed, gates=[gate])
    googl = [c for c in p["cards"] + p["backlog"] if c["ticker"] == "GOOGL"][0]

    assert p["gates"][0]["stored_state"] == "red_but_tested"
    assert p["gates"][0]["state"] == "green"
    assert "QQQ gate" not in googl["card_blockers"]
    assert googl["gate_notes"][0]["status"] == "ok"
    assert "Price condition now MET" in googl["gate_notes"][0]["summary"]

    html = render_today_decide_html(p)
    googl_face = html.split('id="td-card-GOOGL"', 1)[1].split("</summary>", 1)[0]
    assert "Price condition now MET: QQQ close 721.34 clears 717.50" in html
    assert "Price condition now MET: QQQ close 721.34 clears 717.50" in googl_face
    assert "Context only: SMH" not in googl_face
    assert "RED BUT TESTED" not in html


def test_remaining_decisions_render_as_full_cards_not_raw_backlog():
    goal = copy.deepcopy(G)
    goal["daily_card_max"] = 1
    p = _payload(goal=goal)
    html = render_today_decide_html(p)
    backlog_ticker = p["backlog"][0]["ticker"]

    assert "More impact-ranked decisions" in html
    assert "Backlog (" not in html
    assert "Show top" not in html
    assert f'id="td-card-{backlog_ticker}"' in html
    backlog_block = html.split(f'id="td-card-{backlog_ticker}"', 1)[1]
    assert "Current answer" in backlog_block
    assert "Evidence that matters" in backlog_block


def test_fed_day_packet_builds_watch_queue_and_card_context():
    feed = copy.deepcopy(_feed())
    feed["fed_day_reallocation_packet"] = {
        "display_label": "Daily pullback packet",
        "act_if_green": [{
            "ticker": "GOOGL",
            "dollar_band": {"low": 100000, "high": 155000},
            "green_first_tranche": {"low": 50000, "high": 108500},
            "gate_status": "green only after Fed/tape confirms",
            "do_nothing_cost": "GOOGL stays undersized if thesis is right.",
            "disconfirmation": "Do not deploy if QQQ/SPY fail.",
        }],
        "higher_quality_pullbacks": [
            {
                "ticker": "AVGO",
                "rank_score": 23.49,
                "pct_below_high": -23.9,
                "price": 377,
                "current_exposure_usd": 40696,
                "research_status": "STAGE",
                "source_tags": ["Notion Working STAGE"],
                "disconfirmation": "Advance only if flow beats GOOGL/MSFT.",
            },
            {
                "ticker": "VRT",
                "rank_score": 21.14,
                "pct_below_high": -21.14,
                "price": 300,
                "current_exposure_usd": 0,
                "source_tags": [],
                "disconfirmation": "Needs power/cooling confirmation.",
            },
        ],
        "deep_discount_research": [{
            "ticker": "BMNR",
            "rank_score": 89.2,
            "pct_below_high": -89.93,
            "price": 16,
            "current_exposure_usd": 73020,
            "research_status": "MONITOR",
            "source_tags": ["Notion Working MONITOR"],
            "disconfirmation": "Do not add until financing impact clears.",
        }],
        "do_not_touch_yet": ["Social Watch remains dark/watch-only."],
    }
    p = _payload(feed=feed)
    googl = [card for card in p["cards"] + p["backlog"] if card["ticker"] == "GOOGL"][0]
    html = render_today_decide_html(p)

    assert googl["fed_day_context"]["label"] == "Daily pullback packet act-if-green candidate"
    assert [row["ticker"] for row in p["watch_queue"]] == ["AVGO", "VRT", "BMNR"]
    assert "GOOGL" not in {row["ticker"] for row in p["watch_queue"]}
    assert "Daily pullback packet act-if-green candidate" in html
    assert "Watchlist / pullback impact queue (3)" in html
    assert "3 watchlist/pullback candidates" in html
    assert "AVGO" in html and "BMNR" in html
    assert "Do-not-touch / research-only guardrails (1)" in html
    assert "Show top" not in html
    assert "Backlog (" not in html

def test_congruence_strip_flag_and_not_checked():
    flagged_html = render_today_decide_html(_payload())
    assert "\U0001f6a9" in flagged_html and "INSIGHT-950" in flagged_html
    nc = _payload(congruence_result={"status": "not_checked",
                                     "reason": "no positions cache", "rows": []})
    nc_html = render_today_decide_html(nc)
    assert "congruence: not checked" in nc_html

def test_honesty_footer_lists_all_lanes():
    p = _payload()
    assert p["honesty"]["dispositions"].startswith("none logged")
    html = render_today_decide_html(p)
    assert "not_checked" in html and "institutional" in html and "dispositions" in html


def test_last_disposition_renders_from_file(tmp_path):
    pth = tmp_path / "dispositions.jsonl"
    first = _payload(tmp_path=tmp_path)["cards"][0]
    dl.append_disposition(
        "2026-06-10",
        first["card_id"],
        first["ticker"],
        "PASS",
        reason="pilot note",
        path=pth,
    )
    p = _payload(dispositions_path=pth, tmp_path=tmp_path)
    html = render_today_decide_html(p)
    assert "last disposition: PASS on 2026-06-10" in html
    assert "outcome: not logged; source grading unchanged" in html


# ---------------------------------------------------------------------------
# F1 — CONFLICTED conviction posture (surface)
# ---------------------------------------------------------------------------
import today_decide as _td  # noqa: E402


def _conflicted_payload():
    """`_payload()` but with a contradicting UW on GOOGL → conflicted card."""
    return build_today_decide_payload(
        feed=_feed(), weights=W, goal=G, insights_payload=_insights(),
        accounts=_accounts(), gates=[_gate()],
        uw_states={"GOOGL": {"interpretation": "contradicts"}}, entry_zones={},
        congruence_result=_congruence(),
        dispositions_path="_no_dispositions_.jsonl",
        load_committed_baseline=False,
        today=TODAY,
    )


def _conflicted_googl(payload):
    cards = payload["cards"] + payload["backlog"]
    matches = [c for c in cards if c["ticker"] == "GOOGL"]
    assert matches, "fixture stopped producing a GOOGL card"
    return matches[0]


def test_conflicted_card_rail_is_not_act():
    p = _conflicted_payload()
    googl = _conflicted_googl(p)
    # (a) command state is RESOLVE
    assert googl["command_state"] == "RESOLVE"
    # (b) the conflicted card is on-surface, not buried in backlog
    assert googl in p["cards"]
    # (c) rendered HTML data-verb is never ACT for this card
    html = render_today_decide_html(p)
    import re
    rail_re = re.compile(
        r'data-card="(?P<cid>[^"]+)"[^>]*data-verb="(?P<verb>ACT|CANDIDATE|PASS|RECHECK)"'
    )
    verbs = {m["verb"] for m in rail_re.finditer(html) if m["cid"] == googl["card_id"]}
    assert "ACT" not in verbs
    assert verbs & {"RECHECK", "CANDIDATE"}
    # (d) primary button model is never ACT
    assert _td._primary_button_model(googl)["state_verb"] != "ACT"
    # (e) decision_card still validates
    import decision_card as dc
    assert dc.validate_decision_card(googl["decision_card"]) == []


def test_build_conviction_display_marks_conflicted():
    p = _conflicted_payload()
    googl = _conflicted_googl(p)
    display = googl["conviction_display"]
    assert display["band"] == "CONFLICTED"
    assert display["conflicted"] is True
    assert display["band_color"] == "#fb923c"
    assert "resolve" in str(display["conflict"]).lower()


def test_conflicted_card_excluded_from_lean_in():
    # lean-in-ready requires no display.conflict; a conflicted card always sets it.
    p = _conflicted_payload()
    googl = _conflicted_googl(p)
    display = googl["conviction_display"]
    lean_ready = (
        _is_material_safe(googl)
        and not (googl.get("card_blockers") or [])
        and not display.get("conflict")
        and (googl.get("window") or {}).get("class") == "OPEN-NOW"
    )
    assert lean_ready is False


def _is_material_safe(card):
    try:
        return _td._is_material(card)
    except Exception:
        return bool((card.get("impact") or {}).get("material"))
