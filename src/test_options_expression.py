"""Tests for the Phase-1 options-expression engine + shadow log.

Mirrors repo convention (sibling import); a path insert keeps it runnable from repo root.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import options_expression as oe  # noqa: E402
import options_shadow_log as osl  # noqa: E402


def test_module_self_tests_pass():
    assert oe._self_test() == 0
    assert osl._self_test() == 0


def _cheap_act_subject(**over):
    base = {
        "ticker": "NVDA", "as_of": "2026-06-18", "spot": 100.0, "direction": "bullish",
        "conviction_intact": True, "iv_rank": 20.0, "atm_iv": 0.45, "one_day_return": -0.02,
        "thesis_horizon_days": 60, "portfolio_value": 100000, "open_premium_at_risk": 0,
        "chain": oe._chain("call", 100.0),
    }
    base.update(over)
    return base


def test_lead_with_move_and_act_timing():
    r = oe.build_expression(_cheap_act_subject())
    assert r["disposition"] == "ACT"
    assert r["move"].startswith("Buy ")            # leads with the move, not a score
    assert r["timing"]["verdict"] == "ACT_NOW"
    assert r["max_loss_pct_book"] is not None and r["max_loss_pct_book"] <= 2.01


def test_iv_tax_brake_routes_to_spread_and_names_flip_condition():
    r = oe.build_expression(_cheap_act_subject(iv_rank=70.0, atm_iv=0.6, one_day_return=-0.06))
    assert r["iv_tax_brake"] is True
    assert r["disposition"] == "WAIT"
    assert r["structure"] == "debit_call_spread"
    assert r["timing"]["flip_condition"] and "IV" in r["timing"]["flip_condition"]


def test_thesis_break_is_not_a_buy():
    r = oe.build_expression(_cheap_act_subject(thesis_break=True, one_day_return=-0.05))
    assert r["disposition"] == "SKIP"
    assert "THESIS" in (r["filter_reason"] or "").upper()


def test_illiquid_is_skipped_with_a_reason():
    thin = [dict(c, oi=5) for c in oe._chain("call", 100.0)]
    r = oe.build_expression(_cheap_act_subject(chain=thin))
    assert r["disposition"] == "SKIP"
    assert "illiquid" in (r["filter_reason"] or "").lower()


def test_tripwire_only_when_flagged():
    assert oe.build_expression(_cheap_act_subject())["tripwire_note"] is None
    assert oe.build_expression(_cheap_act_subject(recent_options_loss=True))["tripwire_note"]


def test_glossary_explains_every_used_term():
    r = oe.build_expression(_cheap_act_subject())
    for term in ("premium", "max loss", "defined risk"):
        assert term in r["glossary"] and r["glossary"][term]


def test_summarize_run_never_silent():
    acted = oe.build_expression(_cheap_act_subject())
    summ = oe.summarize_run([acted])
    assert summ["act"] and summ["headline"]
    empty = oe.summarize_run([{"ticker": "X", "disposition": "SKIP", "filter_reason": "illiquid"}])
    assert empty["honest_empty"] and "Nothing hidden" in empty["headline"]


def test_shadow_log_excludes_acted(tmp_path):
    acted = oe.build_expression(_cheap_act_subject())
    waited = oe.build_expression(_cheap_act_subject(iv_rank=70.0, one_day_return=-0.06))
    p = tmp_path / "shadow.jsonl"
    n = osl.append_rejections([acted, waited], path=p, as_of="2026-06-18")
    assert n == 1                                   # only the WAIT is logged
    assert osl.open_misses(p)[0]["ticker"] == waited["ticker"]


def test_conviction_scaled_sizing_with_shown_ceiling():
    # cheap premium ($100/contract) so many contracts fit -> conviction scaling is visible
    strong = oe.size_position(100.0, portfolio_value=100000, open_premium_at_risk=0,
                              conviction_strength=1.0, cfg=None)
    weak = oe.size_position(100.0, portfolio_value=100000, open_premium_at_risk=0,
                            conviction_strength=0.5, cfg=None)
    assert strong["ceiling_contracts"] == 20 and weak["ceiling_contracts"] == 20   # the cap rail is the same
    assert strong["contracts"] == 20                            # strong conviction sits AT the cap (never timid)
    assert weak["contracts"] < weak["ceiling_contracts"]        # weak sizes DOWN from the cap
    assert weak["contracts"] >= int(20 * oe.DEFAULTS["size_floor_frac"])   # but never below the floor
    assert weak["suggested_pct_of_cap"] is not None and weak["suggested_pct_of_cap"] < 100


def test_unknown_conviction_is_never_timid_defaults_to_full_cap():
    out = oe.size_position(100.0, portfolio_value=100000, open_premium_at_risk=0, cfg=None)  # no strength passed
    assert out["contracts"] == out["ceiling_contracts"] == 20   # default -> full cap, not a haircut


def test_summarize_run_shows_aggregate_budget():
    summ = oe.summarize_run([oe.build_expression(_cheap_act_subject())])
    assert summ["budget_line"] and "options budget" in summ["headline"]
