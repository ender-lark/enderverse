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
