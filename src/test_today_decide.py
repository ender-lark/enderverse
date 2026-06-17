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

def _payload(goal=None, congruence_result=None, tmp_path=None, dispositions_path=None, feed=None, gates=None, today=TODAY):
    return build_today_decide_payload(
        feed=feed or _feed(), weights=W, goal=goal or G, insights_payload=_insights(),
        accounts=_accounts(), gates=(gates if gates is not None else [_gate()]), uw_states={}, entry_zones={},
        congruence_result=congruence_result or _congruence(),
        dispositions_path=(dispositions_path if dispositions_path else
                           (tmp_path / "none.jsonl" if tmp_path else "_no_dispositions_.jsonl")),
        today=today,
    )

def test_payload_builds_and_goal_anchor_math():
    p = _payload()
    ga = p["goal_anchor"]
    assert ga["book_value"] == 1890000.0 and ga["fi_target"] == 3000000.0
    assert ga["pct_to_target"] == 63.0 and ga["gap_usd"] == 1110000.0
    assert "display-only" in ga["pace_line"]
    assert p["plan_line"]["positions_as_of"] == "2026-06-09"

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
    assert "Conviction to Buy GOOGL:" in html
    assert "Why it is this" in html
    assert "Name / sector split" in html
    assert "What would make it a confident move" in html
    assert "IV options-vs-shares" in html
    assert "not checked:" in html
    assert "LOW 0." not in html
    assert "MODERATE 0." not in html
    assert "HIGH 0." not in html
    why_block = html.split("Why it is this", 1)[1].split("What would make it a confident move", 1)[0]
    factor_pos = min(
        pos for pos in (why_block.find("decisive:"), why_block.find("conflicting:"), why_block.find("factor:"))
        if pos >= 0
    )
    assert factor_pos < why_block.find("Fundstrat / source calls")

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
    assert "SOURCE-CONFLICT" in html and "hold/add MAGS" in html
    assert "Conviction to Sell MAGS" in html
    assert "CONFLICT" in html
    assert "candidate SELL; blockers or conflicts must clear first" in html

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

    assert "Conviction to Buy GOOGL" in html
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

    assert html.count("CHECK DATA FIRST") == 1
    assert "Conviction to Buy GOOGL" in html
    assert 'data-copy="ACT MAGS-TRIM-2026-06-10"' in html


def test_backlog_is_collapsed_in_details():
    html = render_today_decide_html(_payload())
    assert "<details><summary>Backlog (" in html

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
