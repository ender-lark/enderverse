"""Tests for the options_surface producer (consumes the engine + adapter)."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import options_surface as osf  # noqa: E402


def _bundle():
    screener = {"result": [{
        "ticker": "NVDA", "iv_rank": "23.6105", "iv30d": "0.358", "implied_move_perc": "0.070000",
        "next_earnings_date": "2026-08-26", "close": "210.69", "prev_close": "204.65",
        "week_52_high": "236.54", "week_52_low": "142.03", "date": "2026-06-18"}]}
    chain = {"states": [
        {"option_symbol": "NVDA260821C00205000", "strike": "205", "option_type": "call",
         "expires": "2026-08-21", "iv": 0.4152, "delta": 0.5979, "theo": 17.4998, "open_interest": 10123, "volume": 1326},
        {"option_symbol": "NVDA260821C00210000", "strike": "210", "option_type": "call",
         "expires": "2026-08-21", "iv": 0.4091, "delta": 0.5432, "theo": 14.7750, "open_interest": 18035, "volume": 3825}],
        "price_data": {"price": "210.69"}}
    return {
        "NVDA": {"screener": screener, "chain": chain},
        "ZZZ": {"screener": {"result": [{"ticker": "ZZZ", "close": "50", "prev_close": "49", "date": "2026-06-18"}]}},
    }


def test_self_test_passes():
    assert osf._self_test() == 0


def test_ranks_act_first_and_leads_with_move():
    res = osf.surface_options(_bundle(), conviction_lookup={"NVDA": {"thesis_horizon_days": 60}},
                              account={"portfolio_value": 100000}, as_of="2026-06-18", generated_at="x")
    assert res["ideas"][0]["ticker"] == "NVDA"
    assert res["ideas"][0]["disposition"] == "ACT"
    assert res["ideas"][0]["move"].startswith("Buy ")


def test_data_gap_is_honest_not_fake_illiquid():
    res = osf.surface_options(_bundle(), as_of="2026-06-18", generated_at="x")
    zzz = [i for i in res["ideas"] if i["ticker"] == "ZZZ"][0]
    assert zzz["disposition"] == "WATCH"
    assert "re-pull" in (zzz["filter_reason"] or "")


def test_never_silent_and_deterministic():
    a = osf.surface_options(_bundle(), conviction_lookup={"NVDA": {"thesis_horizon_days": 60}},
                            account={"portfolio_value": 100000}, as_of="2026-06-18", generated_at="x")
    b = osf.surface_options(_bundle(), conviction_lookup={"NVDA": {"thesis_horizon_days": 60}},
                            account={"portfolio_value": 100000}, as_of="2026-06-18", generated_at="x")
    assert a["ideas"] == b["ideas"]                     # deterministic
    assert a["summary"]["headline"]                     # never silent
    empty = osf.surface_options({}, generated_at="x")
    assert empty["summary"]["honest_empty"] and empty["summary"]["headline"]


def test_never_raises_on_malformed_inputs():
    bad = {
        "AAA": [1, 2, 3],                                   # non-dict per-name value
        "BBB": {"screener": 5, "chain": True},              # scalar screener + chain
        "CCC": {"chain": {"states": []}},                   # chain returned but empty
        "ddd": {"screener": {"result": [{"close": "10", "prev_close": "9", "date": "2026-06-18"}]}},  # no chain
    }
    res = osf.surface_options(bad, conviction_lookup="junk", account=7, as_of="2026-06-18", generated_at="x")
    assert len(res["ideas"]) == 4
    assert all(i["disposition"] in ("WATCH", "SKIP") for i in res["ideas"])   # never an ACT off junk
    assert res["summary"]["headline"]                                          # still not silent
    assert osf.surface_options([1, 2, 3], generated_at="x")["ideas"] == []     # non-dict bundle, no raise


def test_valid_chain_with_junk_context_does_not_raise():
    # the raise path that only surfaces once a real chain keeps the loop alive past the data-gap continue
    res = osf.surface_options(_bundle(), conviction_lookup="junk", account="junk",
                              as_of="2026-06-18", generated_at="x")
    nvda = [i for i in res["ideas"] if i["ticker"] == "NVDA"][0]
    assert nvda["disposition"] in ("ACT", "WAIT", "WATCH", "SKIP")


def test_shadow_log_records_only_near_misses(tmp_path):
    res = osf.surface_options(_bundle(), conviction_lookup={"NVDA": {"thesis_horizon_days": 60}},
                              account={"portfolio_value": 100000}, as_of="2026-06-18", generated_at="x")
    p = tmp_path / "shadow.jsonl"
    n = osf.persist_shadow_log(res, path=p)
    assert n == 1                                        # NVDA ACT excluded; ZZZ logged


# ─────────────────────────── SURFACE (render) layer ──────────────────────────
def _act_surface():
    return osf.surface_options(_bundle(), conviction_lookup={"NVDA": {"thesis_horizon_days": 60}},
                               account={"portfolio_value": 100000},
                               as_of="2026-06-18", generated_at="2026-06-18T21:50:00Z")


def _illiquid_bundle():
    """A real-shaped NVDA whose chain parses but is too thin to trade -> engine SKIPs it,
    so the whole surface is honest-empty (no ACT / no WAIT-with-flip)."""
    b = _bundle()
    for c in b["NVDA"]["chain"]["states"]:
        c["open_interest"] = 5
    return b


def test_loud_text_leads_with_move_and_shows_risk_and_terms():
    txt = osf.render_surface_text(_act_surface())
    first = txt.splitlines()[0]
    assert first.startswith("\U0001f3af OPTIONS EXPRESSION")     # labeled lane
    assert "▶ Buy" in txt                                        # LEAD WITH THE MOVE
    assert "Most you can lose" in txt                            # risk loud ($ and %)
    assert "% of book" in txt
    assert "plain terms:" in txt and "premium =" in txt          # glossary inline
    assert "as of 2026-06-18" in txt                             # freshness stamp


def test_loud_ideas_selects_act_and_wait_with_flip_only():
    surf = _act_surface()
    loud = osf.loud_ideas(surf)
    assert loud and loud[0]["ticker"] == "NVDA" and loud[0]["disposition"] == "ACT"
    # the data-gap ZZZ (WATCH, no flip) must NOT be loud
    assert all(i["ticker"] != "ZZZ" for i in loud)


def test_html_block_leads_with_move_one_tap_deep_and_loud_risk():
    h = osf.render_options_block_html(_act_surface())
    assert "OPTIONS EXPRESSION" in h
    assert "▶" in h and "Buy" in h                               # move on the face
    assert "Most you can lose" in h                              # risk loud
    assert "<details" in h and "plain-English terms" in h        # checklist/glossary one tap deep
    assert "never an order" in h                                 # honesty rail on the face


def test_cockpit_feed_block_shape_and_score_is_promotion_only():
    block = osf.cockpit_feed_block(_act_surface())
    assert block["status"] == "has_data" and block["count"] == 1
    row = block["rows"][0]
    assert row["action"] == _act_surface()["ideas"][0]["move"]   # action == the sized move
    assert row["disposition"] == "ACT" and row["score"] == 88
    assert row["risk_amount_usd"] is not None and row["risk_pct_book"] is not None
    assert "promotion-ordering metadata only" in block["_score_note"]


def test_honest_empty_never_silent_text_and_html():
    surf = osf.surface_options(_illiquid_bundle(),
                               conviction_lookup={"NVDA": {"thesis_horizon_days": 60}},
                               account={"portfolio_value": 100000},
                               as_of="2026-06-18", generated_at="x")
    assert not osf.loud_ideas(surf)                              # nothing actionable
    txt = osf.render_surface_text(surf)
    assert "Nothing hidden" in txt or "clean" in txt.lower() or "none" in txt.lower()
    h = osf.render_options_block_html(surf)
    assert "OPTIONS EXPRESSION" in h                             # lane still labeled, never silent
    block = osf.cockpit_feed_block(surf)
    assert block["status"] == "checked" and block["count"] == 0 and block["honest_empty"]


def test_render_none_surface_is_labeled_not_silent():
    h = osf.render_options_block_html(None)
    assert "OPTIONS EXPRESSION" in h and "not checked this build" in h


# ────────────────────────────── RECALL layer ─────────────────────────────────
def test_recall_for_ticker_surfaces_the_move():
    b = _bundle()["NVDA"]
    rec = osf.recall_for_ticker("nvda", screener=b["screener"], chain=b["chain"],
                                conviction={"thesis_horizon_days": 60},
                                account={"portfolio_value": 100000}, as_of="2026-06-18")
    assert rec["idea"]["disposition"] == "ACT"
    assert "▶ Buy" in rec["text"]


def test_recall_no_chain_is_honest_data_gap():
    rec = osf.recall_for_ticker("NVDA", screener=None, chain=None, as_of="2026-06-18")
    assert rec["idea"]["disposition"] == "WATCH"
    assert "re-pull" in (rec["idea"]["filter_reason"] or "")


def test_build_options_lane_honesty_rails():
    b = _bundle()["NVDA"]
    lane = osf.build_options_lane("NVDA", is_equity=True, screener=b["screener"], chain=b["chain"],
                                  conviction={"thesis_horizon_days": 60},
                                  account={"portfolio_value": 100000}, as_of="2026-06-18")
    assert lane["status"] == "ok"
    assert lane["blocks"] is False and lane["alert_eligible"] is False   # options never drive a decision
    assert lane["idea"]["move"].startswith("Buy ")


def test_build_options_lane_skips_macro_and_flags_data_gap():
    macro = osf.build_options_lane("DXY", is_equity=False)
    assert macro["status"] == "skipped" and macro["blocks"] is False
    gap = osf.build_options_lane("NVDA", is_equity=True, screener=None, chain=None)
    assert gap["status"] == "data_gap" and gap["idea"] is None


def test_no_add_rail_demotes_act_and_keeps_it_quiet():
    b = _bundle()["NVDA"]
    # recall path: a MONITOR sleeve must never yell ACT
    rec = osf.recall_for_ticker("NVDA", screener=b["screener"], chain=b["chain"],
                                conviction={"thesis_horizon_days": 60, "stance": "MONITOR"},
                                account={"portfolio_value": 100000}, as_of="2026-06-18")
    assert rec["idea"]["disposition"] == "WATCH"
    assert "MONITOR" in (rec["idea"]["filter_reason"] or "")
    assert not osf.loud_ideas(rec["surface"])
    # producer-fed path: apply_no_add_rails re-applies the dropped conviction context
    surf = osf.apply_no_add_rails(_act_surface(), {"NVDA": {"stance": "MONITOR"}})
    assert all(i["disposition"] != "ACT" for i in surf["ideas"])


def test_rank_prefers_cheap_single_name_over_rich_etf_spread():
    cheap_single = {"disposition": "ACT", "conviction_strength": 0.75, "iv_environment": "cheap",
                    "structure": "long_call", "ticker": "NVDA", "expected_move_pct": 12, "break_even_pct": 5}
    rich_etf = {"disposition": "ACT", "conviction_strength": 0.5, "iv_environment": "rich",
                "structure": "debit_call_spread", "ticker": "XLF", "expected_move_pct": 20, "break_even_pct": 2}
    ranked = sorted([rich_etf, cheap_single], key=osf._rank_key)
    assert [i["ticker"] for i in ranked] == ["NVDA", "XLF"]   # cheap single-name conviction leads, not the rich ETF spread


def test_rank_disposition_always_leads():
    strong_wait = {"disposition": "WAIT", "conviction_strength": 1.0, "iv_environment": "cheap",
                   "structure": "long_call", "ticker": "AAA"}
    weak_act = {"disposition": "ACT", "conviction_strength": 0.1, "iv_environment": "rich",
                "structure": "debit_call_spread", "ticker": "BBB"}
    assert sorted([strong_wait, weak_act], key=osf._rank_key)[0]["ticker"] == "BBB"  # an ACT is never demoted below a WAIT


def test_aggregate_budget_funds_strongest_first_and_demotes_rest():
    # three ACTs at 4% each = 12% > the ~10% aggregate cap -> fund the first two, demote the third (quiet, not dropped)
    ideas = [{"disposition": "ACT", "ticker": t, "max_loss_pct_book": 4.0, "structure": "long_call"}
             for t in ("A", "B", "C")]
    out = osf._apply_aggregate_budget(ideas)
    acts = [i for i in out if i["disposition"] == "ACT"]
    assert [i["ticker"] for i in acts] == ["A", "B"]                # strongest (rank-order) funded first
    assert sum(i["max_loss_pct_book"] for i in acts) <= 10.0        # run total within the aggregate cap
    held = [i for i in out if i.get("held_back")]
    assert held and held[0]["ticker"] == "C" and held[0]["disposition"] == "WATCH" and held[0]["held_back"] == "budget"


def test_aggregate_budget_caps_loud_count():
    # five cheap ACTs (2.5% total, within budget) but more than max_loud_ideas -> only the top few stay loud
    ideas = [{"disposition": "ACT", "ticker": t, "max_loss_pct_book": 0.5, "structure": "long_call"}
             for t in ("A", "B", "C", "D", "E")]
    out = osf._apply_aggregate_budget(ideas)
    acts = [i for i in out if i["disposition"] == "ACT"]
    assert len(acts) == osf.oe.DEFAULTS["max_loud_ideas"]          # only the top-N shout
    assert all(i["held_back"] == "loud_cap" for i in out if i.get("held_back"))
