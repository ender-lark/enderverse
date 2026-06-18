import os
import sys
import json
from copy import deepcopy

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import battery_feed_adapter as bfa
import conviction_engine as ce
import decision_card as dc
from directive_recs import build_directive_cards
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
            {"ticker": "GOOGL", "goal_score": 80, "kind": "lean_in"},
            {"ticker": "MAGS", "goal_score": 70, "kind": "trim"},
        ],
        "holdings": [
            {
                "cat": "Quality core",
                "rot": {"w": "LEADING"},
                "pos": [{"t": "GOOGL", "cd": "up", "cdNote": "test momentum"}],
            }
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

def _build():
    return build_directive_cards(
        feed=_feed(), weights=W, goal=G, insights_payload=_insights(),
        accounts=_accounts(), gates=[_gate()], uw_states={}, entry_zones={},
        today=TODAY,
    )

def test_stack_builds_and_respects_card_max():
    out = _build()
    assert out["built"] == TODAY
    assert len(out["cards"]) <= G["daily_card_max"]
    assert len(out["cards"]) + len(out["backlog"]) == 3

def test_every_card_carries_a_valid_decision_card():
    out = _build()
    for card in out["cards"] + out["backlog"]:
        assert dc.validate_decision_card(card["decision_card"]) == []
        assert set(dc.CARD_FIELDS) <= set(card["decision_card"])

def test_buy_adds_are_gate_capped_stage_only():
    out = _build()
    buys = [c for c in out["cards"] + out["backlog"] if c["direction"] == "BUY"]
    assert buys
    for c in buys:
        assert c["window"]["class"] == "STAGE-ONLY"
        assert c["window"]["stage_fraction"] == W["timing"]["stage_only_fraction"]

def test_oversized_trim_opens_now_with_named_trigger():
    out = _build()
    mags = [c for c in out["cards"] + out["backlog"] if c["ticker"] == "MAGS"][0]
    assert mags["direction"] == "SELL"  # target 0%
    assert mags["window"]["class"] == "OPEN-NOW"
    assert "overexposed" in mags["window"]["named_trigger"]
    assert "NVDA" in mags["funds"]
    # F2: sell-gate present and NOT_EVALUABLE on the schema-less MAGS SELL; the
    # card stays actionable (the gate FLAGs by default, never blocks on missing data).
    assert mags["sell_gate"]["verdict"] == "NOT_EVALUABLE"
    assert mags["sell_gate"]["evaluable"] is False

def test_priority_blend_orders_the_stack():
    out = _build()
    ranked = out["cards"] + out["backlog"]
    assert [c["priority"] for c in ranked] == sorted(
        (c["priority"] for c in ranked), reverse=True
    )
    googl = [c for c in ranked if c["ticker"] == "GOOGL"][0]
    nvda = [c for c in ranked if c["ticker"] == "NVDA"][0]
    assert googl["priority"] > nvda["priority"]  # goal_score 80 + 'now' bump vs default
    assert ranked[0]["ticker"] == "GOOGL"
    assert googl["impact"]["material"] is True


def test_immaterial_funding_leg_cannot_hero_rank_above_material_adds():
    feed = _feed()
    feed["target_drift"] = {"rows": []}
    feed["reallocation_brief"]["trims"][0]["notional_usd"] = 400
    feed["reallocation_brief"]["trims"][0]["funds"] = [{"ticker": "GOOGL", "notional_usd": 400}]

    out = build_directive_cards(
        feed=feed, weights=W, goal=G, insights_payload=_insights(),
        accounts=_accounts(), gates=[_gate()], uw_states={}, entry_zones={},
        today=TODAY,
    )
    ranked = out["cards"] + out["backlog"]
    tickers = [c["ticker"] for c in ranked]
    mags = [c for c in ranked if c["ticker"] == "MAGS"][0]

    assert tickers.index("GOOGL") < tickers.index("MAGS")
    assert tickers.index("NVDA") < tickers.index("MAGS")
    assert mags["priority"] <= 9.0
    assert mags["priority_note"].startswith("funding-only immaterial leg")
    assert mags["window"]["class"] == "STAGE-ONLY"
    assert mags["impact"]["material"] is False
    # F2: the sell-gate rides an ADDITIVE field; on real schema-less trims it is
    # NOT_EVALUABLE, so it never overwrites the salience priority_note (precedence).
    assert mags["sell_gate"]["verdict"] == "NOT_EVALUABLE"

def test_execution_blocks_surface_pcra_and_cash_honesty():
    out = _build()
    buys = [c for c in out["cards"] + out["backlog"] if c["direction"] == "BUY"]
    for c in buys:
        assert any("ETF-ONLY" in e["why_not"] for e in c["execution"]["excluded"])
        assert c["execution"]["cash"].startswith("not_checked")
    mags = [c for c in out["cards"] + out["backlog"] if c["ticker"] == "MAGS"][0]
    pcra_legs = [l for l in mags["execution"]["legs"] if "PCRA" in l["account"]]
    assert pcra_legs and "proceeds_constraint" in pcra_legs[0]

def test_buy_cards_carry_caps_sizing_payload():
    out = _build()
    buys = [c for c in out["cards"] + out["backlog"] if c["direction"] in {"BUY", "ADD"}]
    assert buys
    for card in buys:
        sizing = card.get("sizing")
        assert sizing["source"] == "caps"
        assert isinstance(sizing["suggested_usd"], (int, float))
        assert sizing["heat"]
        assert sizing["cap_basis"]


# ---------------------------------------------------------------------------
# F2 -- conviction drives the LIVE size; no hard caps; sell-gate is a FLAG
# ---------------------------------------------------------------------------
import directive_recs as dr

_F2_POS = [{"ticker": "BMNR", "market_value": 71500}]
_F2_THESES = [{"ticker": "BMNR", "tier": "T1"}]
_F2_BOOK = 1875000


def _size(conv, *, tunables=None, proposed=25000, available_cash=None, funding_pool=None):
    return dr._caps_sizing(
        ticker="BMNR", proposed_usd=proposed, book=_F2_BOOK,
        positions=_F2_POS, theses=_F2_THESES,
        conviction=conv, tunables=tunables or dr.load_sizing_tunables(),
        available_cash=available_cash, funding_pool=funding_pool,
    )


def test_high_converging_buy_sizes_up_no_hard_cap():
    conv = {"read": "HIGH", "direction": "BUY", "strength_5": 5, "n_groups": 3, "conflicted": False}
    s = _size(conv)
    # conviction LIFTS the live suggested size ABOVE the proposed anchor; the
    # former hard ceiling/cap_room would have clipped this -- it no longer does.
    assert s["size_lift_mult"] > 1.0
    assert s["suggested_usd"] > 25000
    assert s["heat"] == "CONVICTION_LIFTED"
    assert "soft reference" in s["cap_basis"]
    assert "context, not a limit" in s["cap_basis"]


def test_conflicted_read_is_never_sized_up():
    conv = {"read": "CONFLICTED", "direction": "RE-CHECK", "strength_5": 3, "n_groups": 2, "conflicted": True}
    s = _size(conv)
    assert s["size_lift_mult"] == 1.0
    assert s["suggested_usd"] == 25000
    assert s["heat"] == "CONFLICTED_FLOOR"


def test_high_but_single_group_is_not_echo_upsized():
    # HIGH read that does NOT converge across independent groups = faked/echo
    # conviction. It must NOT lift -- size keys off the honest, independence-
    # collapsed read, never off raw echo or a single repeated source.
    conv = {"read": "HIGH", "direction": "BUY", "strength_5": 5, "n_groups": 1, "conflicted": False}
    s = _size(conv)
    assert s["size_lift_mult"] == 1.0
    assert s["suggested_usd"] == 25000


def test_non_buy_direction_does_not_lift():
    conv = {"read": "HIGH", "direction": "NEUTRAL", "strength_5": 5, "n_groups": 3, "conflicted": False}
    assert _size(conv)["size_lift_mult"] == 1.0
    conv2 = {"read": "HIGH", "direction": "SELL", "strength_5": 5, "n_groups": 3, "conflicted": False}
    assert _size(conv2)["size_lift_mult"] == 1.0


def test_no_conviction_is_base_size_no_lift():
    s = _size(None)
    assert s["size_lift_mult"] == 1.0
    assert s["suggested_usd"] == 25000


def test_per_name_soft_max_holds_visibly_not_silently():
    cfg = dr.load_sizing_tunables()
    cfg["per_name_soft_max_usd"] = 30000
    conv = {"read": "HIGH", "direction": "BUY", "strength_5": 5, "n_groups": 3, "conflicted": False}
    s = _size(conv, tunables=cfg)
    assert s["suggested_usd"] == 30000
    assert "per-name soft max" in s["cap_basis"]
    # the original lifted number is still stated -- never a silent clamp.
    assert "$50,000" in s["cap_basis"]


def test_soft_max_off_by_default_lets_conviction_flow():
    cfg = dr.load_sizing_tunables()
    assert cfg["per_name_soft_max_usd"] is None
    assert cfg["concentration_soft_max_pct"] is None
    conv = {"read": "HIGH", "direction": "BUY", "strength_5": 5, "n_groups": 3, "conflicted": False}
    s = _size(conv, tunables=cfg)
    assert s["suggested_usd"] == 50000  # full conviction-driven size, unclamped


def test_cash_reality_is_a_number_never_a_hidden_block():
    conv = {"read": "HIGH", "direction": "BUY", "strength_5": 5, "n_groups": 3, "conflicted": False}
    # with a real cash number smaller than the suggested size -> exceeds flag + number
    s = _size(conv, available_cash=20000)
    assert s["exceeds_cash"] is True
    assert s["available_cash"] == 20000.0
    assert "EXCEEDS available cash" in s["cap_basis"]
    # the size is NOT silently reduced -- the operator sizes by hand to cash.
    assert s["suggested_usd"] == 50000


def test_cash_not_checked_when_absent():
    conv = {"read": "HIGH", "direction": "BUY", "strength_5": 5, "n_groups": 3, "conflicted": False}
    s = _size(conv, available_cash=None)
    assert s["available_cash"] == "not_checked"
    assert s["exceeds_cash"] is False
    assert "available cash not_checked" in s["cap_basis"]


# --- FUNDING-AWARE affordability reality (F2-FUNDING-REALITY) -----------------

_FUND_BUY = {"read": "HIGH", "direction": "BUY", "strength_5": 5, "n_groups": 3, "conflicted": False}


def test_new_tunable_treat_funding_pool_default_is_true():
    cfg = dr.load_sizing_tunables()
    # The operator usually funds a buy by CONVERSION, not idle cash -> default TRUE.
    assert cfg["treat_funding_pool_as_available"] is True


def test_funding_reality_counts_cash_plus_pool():
    # suggested 50000; cash 20000 alone is short, but cash + 40000 pool covers it.
    s = _size(_FUND_BUY, available_cash=20000, funding_pool=40000)
    assert s["suggested_usd"] == 50000
    # cash-only fields stay for transparency and still flag exceeds_cash.
    assert s["available_cash"] == 20000.0
    assert s["exceeds_cash"] is True
    # funding-aware: cash + pool = 60000 covers the 50000 suggested.
    assert s["funding_pool_usd"] == 40000.0
    assert s["funding_available_usd"] == 60000.0
    assert s["exceeds_funding"] is False
    assert s["funding_shortfall_usd"] == 0.0
    assert "from sells (sell-gate-ordered)" in s["funding_note"]
    assert "covers suggested" in s["funding_note"]


def test_funding_shortfall_is_a_number_never_blocks_or_clamps():
    # suggested 50000; cash 5000 + pool 10000 = 15000 -> short 35000.
    s = _size(_FUND_BUY, available_cash=5000, funding_pool=10000)
    # The size is NEVER clamped to the funded number -- it stays the lifted size.
    assert s["suggested_usd"] == 50000
    assert s["funding_available_usd"] == 15000.0
    assert s["exceeds_funding"] is True
    # the shortfall is shown as a NUMBER, not a block.
    assert s["funding_shortfall_usd"] == 35000.0
    assert "SHORT" in s["funding_note"]
    assert "$35,000" in s["funding_note"]


def test_funding_pool_byte_stable_does_not_change_suggested_or_lift():
    # Same conviction, three pool scenarios -> suggested_usd and the lift are
    # IDENTICAL; only the additive funding fields differ (F2 byte-stability).
    base = _size(_FUND_BUY, available_cash=None, funding_pool=None)
    with_cash = _size(_FUND_BUY, available_cash=20000, funding_pool=None)
    with_pool = _size(_FUND_BUY, available_cash=20000, funding_pool=500000)
    for s in (base, with_cash, with_pool):
        assert s["suggested_usd"] == base["suggested_usd"]
        assert s["size_lift_mult"] == base["size_lift_mult"]
        assert s["size_lift_strength"] == base["size_lift_strength"]


def test_funding_pool_off_when_tunable_false():
    cfg = dr.load_sizing_tunables()
    cfg["treat_funding_pool_as_available"] = False
    # pool exists but is NOT counted -> only cash funds the affordability number.
    s = _size(_FUND_BUY, tunables=cfg, available_cash=20000, funding_pool=500000)
    assert s["funding_available_usd"] == 20000.0
    assert s["exceeds_funding"] is True  # 50000 > 20000 cash-only
    assert s["treat_funding_pool_as_available"] is False


def test_funding_not_checked_when_no_cash_and_no_pool():
    s = _size(_FUND_BUY, available_cash=None, funding_pool=None)
    assert s["funding_available_usd"] == "not_checked"
    assert s["exceeds_funding"] is False
    assert s["funding_shortfall_usd"] == 0.0
    assert "not_checked" in s["funding_note"]


def test_real_available_cash_from_cash_and_money_market_rows():
    import execution_plan as ep
    cache = {
        "account_positions": [
            {"ticker": "SPAXX", "description": "Fidelity Government Money Market",
             "market_value": 24659.01, "asset_type": "Open Ended Fund"},
            {"ticker": "FCASH", "description": "CASH", "market_value": 86.26,
             "asset_type": "Security type is not defined"},
            {"ticker": "NVDA", "description": "NVIDIA", "market_value": 99999.0,
             "asset_type": "Common Stock"},
        ]
    }
    # cash = 24659.01 + 86.26; the equity row is NOT counted.
    assert ep.available_cash_usd(cache) == 24745.27


def test_settlement_artifact_rows_are_not_counted_as_cash():
    import execution_plan as ep
    cache = {
        "account_positions": [
            {"ticker": "SPAXX", "description": "Margin Debit Balance",
             "market_value": 50000.0, "asset_type": "Open Ended Fund"},
            {"ticker": "SPAXX", "description": "Cash Debit from Unsettled Activity",
             "market_value": 12000.0, "asset_type": "Open Ended Fund"},
            {"ticker": "SPAXX", "description": "Fidelity Government Money Market",
             "market_value": 1000.0, "asset_type": "Open Ended Fund"},
        ]
    }
    # Only the genuine money-market row counts; the SPAXX-backed settlement
    # artifacts are excluded (conservative under-count -> honest funding need).
    assert ep.available_cash_usd(cache) == 1000.0


def test_equity_open_ended_fund_not_miscounted_as_cash():
    import execution_plan as ep
    # FBGKX (Blue Chip Growth) is an "Open Ended Fund" but NOT cash -- matching by
    # asset_type alone would over-count it. Symbol allowlist prevents that.
    cache = {"account_positions": [
        {"ticker": "FBGKX", "description": "Fidelity Blue Chip Growth Fund",
         "market_value": 1058.10, "asset_type": "Open Ended Fund"},
    ]}
    assert ep.available_cash_usd(cache) is None


def test_funding_pool_read_from_reallocation_brief():
    feed = {"reallocation_brief": {"funding": {"pool_total_usd": 194171.97,
                                               "remaining_usd": 0, "shortfall_usd": 100}}}
    assert dr._funding_pool(feed) == 194171.97
    assert dr._funding_pool({}) is None
    assert dr._funding_pool({"reallocation_brief": {"funding": {}}}) is None


def test_lift_does_not_change_validate_decision_card():
    out = _build()
    for card in out["cards"] + out["backlog"]:
        assert dc.validate_decision_card(card["decision_card"]) == []
        assert set(dc.CARD_FIELDS) <= set(card["decision_card"])


def test_jsx_consumed_sizing_keys_still_present():
    # JSX parity contract reads source/suggested_usd/heat/cap_basis -- all kept.
    conv = {"read": "HIGH", "direction": "BUY", "strength_5": 5, "n_groups": 3, "conflicted": False}
    s = _size(conv)
    for key in ("source", "suggested_usd", "heat", "cap_basis"):
        assert key in s


def test_real_trim_sell_gate_not_evaluable_keeps_card_actionable():
    out = _build()
    trims = [c for c in out["cards"] + out["backlog"] if c.get("sell_gate")]
    assert trims
    for card in trims:
        gate = card["sell_gate"]
        assert gate["verdict"] == "NOT_EVALUABLE"
        assert gate["evaluable"] is False
        # the gate did not overwrite a salience priority_note nor block the card.
        if card.get("priority_note"):
            assert not card["priority_note"].startswith("sell-gate BLOCK")

def test_directive_conviction_carries_battery_without_render_or_priority_coupling(monkeypatch, tmp_path):
    cache = tmp_path / "uw_opportunity_signals.json"
    cache.write_text(
        json.dumps(
            {
                "as_of": TODAY,
                "signals": [
                    {
                        "ticker": "GOOGL",
                        "signal_type": "sweep",
                        "direction": "bullish",
                        "strength": "strong",
                        "evidence": "ask-side call sweeps",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(bfa, "DEFAULT_OPPORTUNITY_SIGNALS_PATH", cache)

    out = _build()
    googl = [c for c in out["cards"] + out["backlog"] if c["ticker"] == "GOOGL"][0]
    battery = googl["conviction"]["battery"]
    keys = {row["key"] for row in battery["factors"]}

    assert "uw_opportunity_sweep" in keys
    assert "group_rotation_momentum" in keys
    assert "battery" not in googl["decision_card"]["conviction"]

    blend = W["priority_blend"]
    expected = round(
        float(blend["capital_priority_weight"]) * 80
        + float(blend["conviction_weight"]) * googl["conviction"]["points"]
        + float(blend["window_decay_weight"]) * 0.66,
        1,
    ) + 5.0
    assert googl["priority"] == expected


def test_shadow_sector_layer_does_not_change_ranking_or_priority(monkeypatch):
    calls = [
        {"ticker": "SMH", "source": "newton", "tier": "A", "date": TODAY, "direction": "bullish", "id": "smh"}
    ]
    monkeypatch.setattr(ce, "load_source_calls", lambda: calls)
    shadow = build_directive_cards(
        feed=_feed(), weights=W, goal=G, insights_payload=_insights(),
        accounts=_accounts(), gates=[_gate()], uw_states={}, entry_zones={},
        today=TODAY,
    )
    off_weights = deepcopy(W)
    off_weights["conviction_layers"]["mode"] = "off"
    off = build_directive_cards(
        feed=_feed(), weights=off_weights, goal=G, insights_payload=_insights(),
        accounts=_accounts(), gates=[_gate()], uw_states={}, entry_zones={},
        today=TODAY,
    )

    shadow_ranked = shadow["cards"] + shadow["backlog"]
    off_ranked = off["cards"] + off["backlog"]
    assert [(c["ticker"], c["priority"]) for c in shadow_ranked] == [
        (c["ticker"], c["priority"]) for c in off_ranked
    ]
    nvda = [c for c in shadow_ranked if c["ticker"] == "NVDA"][0]
    nvda_off = [c for c in off_ranked if c["ticker"] == "NVDA"][0]
    assert nvda["conviction"]["conviction_layers"]["sector"]["status"] == "active"
    assert nvda["conviction"]["points"] == nvda_off["conviction"]["points"]


def test_avgo_card_attaches_synced_stale_dossier_as_peer_block():
    feed = _feed()
    feed["actions"].append({"ticker": "AVGO", "goal_score": 65, "kind": "lean_in"})
    feed["reallocation_brief"]["rows"].append(
        {"ticker": "AVGO", "notional_usd": 25000, "current_pct": 0.0, "target_pct": 6.0}
    )

    out = build_directive_cards(
        feed=feed, weights=W, goal=G, insights_payload=_insights(),
        accounts=_accounts(), gates=[_gate()], uw_states={}, entry_zones={},
        today=TODAY,
    )
    avgo = [c for c in out["cards"] + out["backlog"] if c["ticker"] == "AVGO"][0]

    assert avgo["dossier"]["status"] == "stale"
    assert avgo["dossier"]["next_review_due"] == "2026-05-27"
    assert avgo["dossier"]["reads"]["price"]["text"].startswith("UNKNOWN")
    assert avgo["dossier"]["reads"]["timing"]["freshness"]["status"] == "stale"
    assert "dossier" not in avgo["decision_card"]


def test_honesty_footer_and_funding_passthrough():
    out = _build()
    h = out["honesty"]
    assert h["cash"].startswith("not_checked")
    assert "not wired" in h["institutional"]
    assert h["gates_as_of"] == "2026-06-08"
    assert h["positions_as_of"] == "2026-06-09"
    assert out["funding"]["pool_usd"] == 503646


def test_directive_recs_conflicted_material_card_stays_on_surface():
    # GOOGL ADD has bullish FS+insight; injecting a contradicting UW makes it a
    # genuine two-sided conflict. The card must NOT fall into backlog.
    out = build_directive_cards(
        feed=_feed(), weights=W, goal=G, insights_payload=_insights(),
        accounts=_accounts(), gates=[_gate()],
        uw_states={"GOOGL": {"interpretation": "contradicts"}}, entry_zones={},
        today=TODAY,
    )
    payload_tickers = {c["ticker"] for c in out["cards"]}
    backlog_tickers = {c["ticker"] for c in out["backlog"]}
    assert "GOOGL" in payload_tickers
    assert "GOOGL" not in backlog_tickers
    googl = [c for c in out["cards"] if c["ticker"] == "GOOGL"][0]
    assert googl["conviction"]["read"] == "CONFLICTED"
    assert googl["conviction"]["conflicted"] is True
    assert googl["conflict_recheck"] is True
    assert googl["decision_card"]["move"]["direction"] == "RE-CHECK"
    assert googl["decision_card"]["conviction"]["read"] == "CONFLICTED"
    assert dc.validate_decision_card(googl["decision_card"]) == []


def test_directive_recs_conflicted_trim_outranks_no_evidence_trim():
    # A conflicted material trim (the "never sell a live thesis into weakness"
    # case) must read LOUD and rank above a no-evidence trim, not get zeroed by
    # the old max(0.0, -points) funding-trim math.
    feed = _feed()
    feed["target_drift"] = {"rows": [
        {"ticker": "MAGS", "direction": "OVERSIZED"},
        {"ticker": "NVDA", "direction": "OVERSIZED"},
    ]}
    feed["reallocation_brief"]["trims"] = [
        {"ticker": "MAGS", "notional_usd": 70216, "current_pct": 3.7, "target_pct": 1.0,
         "funds": [{"ticker": "GOOGL", "notional_usd": 51500}]},
        {"ticker": "NVDA", "notional_usd": 70216, "current_pct": 5.0, "target_pct": 1.0,
         "funds": [{"ticker": "GOOGL", "notional_usd": 51500}]},
    ]
    feed["reallocation_brief"]["rows"] = [
        {"ticker": "GOOGL", "notional_usd": 151266, "current_pct": 0.0,
         "target_pct": 8.0, "sequence": "now", "entry_note": "x", "gate": "QQQ"},
    ]
    out = build_directive_cards(
        feed=feed, weights=W, goal=G, insights_payload=_insights(),
        accounts=_accounts(), gates=[_gate()],
        # MAGS gets a contradicting UW → conflicted trim; NVDA stays no-evidence.
        uw_states={"MAGS": {"interpretation": "contradicts"}}, entry_zones={},
        today=TODAY,
    )
    ranked = out["cards"] + out["backlog"]
    mags = [c for c in ranked if c["ticker"] == "MAGS"][0]
    nvda = [c for c in ranked if c["ticker"] == "NVDA"][0]
    assert mags["conviction"]["conflicted"] is True
    assert mags["conflict_recheck"] is True
    assert mags["decision_card"]["move"]["direction"] == "RE-CHECK"
    assert nvda["conviction"]["conflicted"] is False
    assert mags["priority"] > nvda["priority"]
