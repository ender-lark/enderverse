"""Unit tests for the Conviction Engine Contract-A validator (S1).

Convention: lives in src/ beside the module it tests (like the repo's other
test_*.py files). Run:  python -m pytest src/test_validators.py -q
"""
import os
import sys

# Be robust whether invoked via pytest (prepend mode) or directly.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from sources import SourceItem, BaseSource, SourceRegistry
from validators import (
    validate_source_item,
    is_valid_source_item,
    assert_valid_source_item,
    validate_items,
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def good_kwargs(**overrides):
    base = dict(
        source="uw_price",
        kind="rotation",
        subject="SMH",
        content="LEADING +47%/3M vs mkt",
        timestamp="2026-05-29",
        trust_weight=0.95,
        independence_group="market_data",
        data={"rel_3m": 0.47},
    )
    base.update(overrides)
    return base


def good_item(**overrides):
    return SourceItem(**good_kwargs(**overrides))


# --------------------------------------------------------------------------- #
# valid cases
# --------------------------------------------------------------------------- #
def test_valid_dataclass_passes():
    assert validate_source_item(good_item()) == []
    assert is_valid_source_item(good_item()) is True


def test_valid_dict_form_passes():
    # Duck-typed: a SourceItem-shaped dict is equally valid.
    assert validate_source_item(good_kwargs()) == []


def test_trust_boundaries_inclusive():
    assert validate_source_item(good_item(trust_weight=0.0)) == []
    assert validate_source_item(good_item(trust_weight=1.0)) == []


def test_content_may_be_empty():
    # content must be a string but is allowed to be empty.
    assert validate_source_item(good_item(content="")) == []


def test_error_kind_item_is_well_formed():
    # The kind="error" item the registry emits is still a valid SourceItem.
    err = SourceItem(
        source="uw_price", kind="error", subject="uw_price",
        content="fetch failed: RuntimeError: connector down",
        timestamp="2026-05-29", trust_weight=0.95,
        independence_group="market_data",
        data={"error_type": "RuntimeError", "error": "connector down"},
    )
    assert validate_source_item(err) == []


# --------------------------------------------------------------------------- #
# non-empty-string contract
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("field", ["source", "kind", "subject", "timestamp"])
def test_empty_required_string_fails(field):
    probs = validate_source_item(good_item(**{field: ""}))
    assert any(field in p and "non-empty" in p for p in probs)


@pytest.mark.parametrize("field", ["source", "kind", "subject", "timestamp"])
def test_whitespace_only_required_string_fails(field):
    probs = validate_source_item(good_item(**{field: "   "}))
    assert any(field in p and "non-empty" in p for p in probs)


@pytest.mark.parametrize("field", ["source", "kind", "subject", "timestamp"])
def test_missing_required_field_fails(field):
    kw = good_kwargs()
    del kw[field]                      # dict form lets us actually drop a field
    probs = validate_source_item(kw)
    assert any(f"missing field: {field}" == p for p in probs)


@pytest.mark.parametrize("field", ["source", "kind", "subject", "timestamp"])
def test_non_string_required_field_fails(field):
    probs = validate_source_item(good_item(**{field: 123}))
    assert any(field in p and "must be a string" in p for p in probs)


# --------------------------------------------------------------------------- #
# trust_weight contract
# --------------------------------------------------------------------------- #
def test_trust_above_one_fails():
    probs = validate_source_item(good_item(trust_weight=1.5))
    assert any("trust_weight must be in [0, 1]" in p for p in probs)


def test_trust_below_zero_fails():
    probs = validate_source_item(good_item(trust_weight=-0.1))
    assert any("trust_weight must be in [0, 1]" in p for p in probs)


def test_trust_non_number_fails():
    probs = validate_source_item(good_item(trust_weight="high"))
    assert any("trust_weight must be a number" in p for p in probs)


def test_trust_bool_rejected():
    # bool subclasses int; a weight of True/False must NOT sneak through.
    probs = validate_source_item(good_item(trust_weight=True))
    assert any("trust_weight must be a number" in p for p in probs)


def test_trust_missing_fails():
    kw = good_kwargs()
    del kw["trust_weight"]
    probs = validate_source_item(kw)
    assert any("missing field: trust_weight" == p for p in probs)


# --------------------------------------------------------------------------- #
# structural shape: independence_group / content / data
# --------------------------------------------------------------------------- #
def test_blank_independence_group_fails():
    probs = validate_source_item(good_item(independence_group=""))
    assert any("independence_group" in p for p in probs)


def test_content_non_string_fails():
    probs = validate_source_item(good_item(content=42))
    assert any("content must be a string" in p for p in probs)


def test_data_non_dict_fails():
    probs = validate_source_item(good_item(data=["not", "a", "dict"]))
    assert any("data must be a dict" in p for p in probs)


def test_data_missing_fails():
    kw = good_kwargs()
    del kw["data"]
    probs = validate_source_item(kw)
    assert any("missing field: data" == p for p in probs)


def test_multiple_problems_all_reported():
    # empty subject + out-of-range trust + bad data type -> three problems.
    probs = validate_source_item(good_item(subject="", trust_weight=9, data=7))
    assert len(probs) >= 3


# --------------------------------------------------------------------------- #
# assert_valid_source_item
# --------------------------------------------------------------------------- #
def test_assert_passes_silently_on_good():
    assert assert_valid_source_item(good_item()) is None


def test_assert_raises_on_bad():
    with pytest.raises(ValueError) as exc:
        assert_valid_source_item(good_item(source=""))
    assert "invalid SourceItem" in str(exc.value)


# --------------------------------------------------------------------------- #
# validate_items over a real fetch_all() haul (the seam in action)
# --------------------------------------------------------------------------- #
def test_validate_items_counts_good_and_bad():
    items = [good_item(), good_kwargs(subject=""), good_item(trust_weight=2)]
    report = validate_items(items)
    assert report["total"] == 3
    assert report["ok"] == 1
    assert len(report["bad"]) == 2
    bad_indices = [idx for idx, _ in report["bad"]]
    assert bad_indices == [1, 2]


def test_validator_runs_clean_over_fetch_all_including_error_item():
    # Build a registry with one good plug + one that raises; fetch_all emits a
    # kind="error" item. EVERY item (including the error) must validate.
    def boom():
        raise RuntimeError("connector down")

    reg = SourceRegistry()
    reg.register(BaseSource("uw_macro", lambda: [
        {"kind": "macro", "subject": "10Y", "content": "10Y 4.45%"}]))
    reg.register(BaseSource("uw_price", boom))

    haul = reg.fetch_all()
    report = validate_items(haul)
    assert report["total"] == 2
    assert report["bad"] == []          # nothing malformed
    assert report["ok"] == 2
    # sanity: the error item really is in the haul
    assert any(i.kind == "error" for i in haul)


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-q"]))


# =========================================================================== #
# Contract C — validate_cockpit_feed (A4)
# =========================================================================== #
from validators import (
    validate_cockpit_feed, is_valid_cockpit_feed, assert_valid_cockpit_feed,
)


def _pos(**over):
    p = {"t": "SMH", "n": "Semiconductor ETF", "pct": 9.9, "st": "Owned",
         "cv": "Strong", "ty": "Core", "own": "p,s", "lock": "", "fresh": False,
         "cd": "flat", "cdNote": "No recent change.",
         "nr": "Core hold — ride it.", "dr": [["Lee", "AI complex"]],
         "be": "AI capex slows."}
    p.update(over)
    return p


def _signal(**over):
    s = {"ticker": "ITA", "urgency": "act", "what": "breakout",
         "why": "laggard turning up", "when": "2026-05-28", "detail": "Newton note"}
    s.update(over)
    return s


def _feed(**over):
    f = {
        "generated_at": "2026-05-29T12:00:00",
        "staleness": {"stamp": "sourced: FS 5/28 · rotation 5/29", "entries": [], "stale": []},
        "hero": {"count": 3, "names": ["SMH"], "leading_sleeves": ["SMH"]},
        "fresh_signals": [_signal()],
        "holdings": [{"cat": "AI / Semis", "rot": {"w": "LEADING", "c": "#0f0"}, "pos": [_pos()]}],
        "rotation": [{"s": "SMH", "w": "LEADING"}],
        "macro": {"line": "10Y 4.45%", "regime": {}, "alerts": [], "implications": []},
        "catalysts": [], "questions": [], "research": {},
    }
    f.update(over)
    return f


def test_feed_valid_minimal():
    assert validate_cockpit_feed(_feed()) == []
    assert is_valid_cockpit_feed(_feed())


def test_feed_not_a_dict():
    assert validate_cockpit_feed(["nope"])


def test_feed_missing_generated_at():
    f = _feed(); del f["generated_at"]
    assert any("generated_at" in p for p in validate_cockpit_feed(f))


def test_feed_missing_required_dict_block():
    f = _feed(); del f["hero"]
    assert any("hero" in p for p in validate_cockpit_feed(f))


def test_feed_missing_required_list_block():
    f = _feed(); del f["holdings"]
    assert any("holdings" in p for p in validate_cockpit_feed(f))


def test_feed_wrong_type_block():
    assert any("rotation" in p for p in validate_cockpit_feed(_feed(rotation={"not": "a list"})))
    assert any("macro" in p for p in validate_cockpit_feed(_feed(macro=["not", "a", "dict"])))


def test_feed_holding_missing_pos():
    assert any("pos" in p for p in
               validate_cockpit_feed(_feed(holdings=[{"cat": "AI"}])))


def test_feed_holding_missing_cat():
    assert any("cat" in p for p in
               validate_cockpit_feed(_feed(holdings=[{"pos": [_pos()]}])))


def test_feed_pos_missing_required_field():
    p = _pos(); del p["nr"]
    f = _feed(holdings=[{"cat": "AI", "pos": [p]}])
    assert any("nr" in prob for prob in validate_cockpit_feed(f))


def test_feed_pos_empty_ticker():
    f = _feed(holdings=[{"cat": "AI", "pos": [_pos(t="")]}])
    assert any("ticker" in prob.lower() for prob in validate_cockpit_feed(f))


def test_feed_pos_bad_pct_type():
    f = _feed(holdings=[{"cat": "AI", "pos": [_pos(pct="9.9")]}])
    assert any("pct" in prob for prob in validate_cockpit_feed(f))


def test_feed_fresh_signal_missing_field():
    s = _signal(); del s["why"]
    assert any("why" in prob for prob in validate_cockpit_feed(_feed(fresh_signals=[s])))


def test_feed_fresh_signal_bad_urgency():
    assert any("urgency" in prob for prob in
               validate_cockpit_feed(_feed(fresh_signals=[_signal(urgency="maybe")])))


def test_feed_optional_blocks_absent_is_valid():
    f = _feed()
    for k in ("catalysts", "questions", "research"):
        del f[k]
    assert validate_cockpit_feed(f) == []


def test_feed_accepts_valid_target_drift_block():
    f = _feed(target_drift={
        "status": "has_data",
        "line": "Target drift: 1 sizing gap.",
        "actionable_count": 1,
        "undersized_count": 1,
        "oversized_count": 0,
        "missing_count": 0,
        "alarm_count": 1,
        "rows": [{
            "ticker": "NVDA",
            "direction": "UNDERSIZED",
            "actual_pct": 6.0,
            "target_pct": 12.0,
            "drift_relative": -0.5,
            "drift_absolute_pct": -6.0,
        }],
    })
    assert validate_cockpit_feed(f) == []


def test_feed_rejects_bad_target_drift_block():
    f = _feed(target_drift={
        "status": "mystery",
        "line": "",
        "actionable_count": -1,
        "undersized_count": 0,
        "oversized_count": 0,
        "missing_count": 0,
        "alarm_count": 0,
        "rows": [{"ticker": "", "direction": "SIDEWAYS", "actual_pct": "6"}],
    })
    problems = validate_cockpit_feed(f)
    assert any("target_drift status" in p for p in problems)
    assert any("target_drift line" in p for p in problems)
    assert any("target_drift actionable_count" in p for p in problems)
    assert any("target_drift rows[0].ticker" in p for p in problems)


def test_feed_portfolio_views_optional_block_validates_when_present():
    effective = {
        "basis": "direct_plus_estimated_etf_lookthrough",
        "overlap_rows": [{
            "ticker": "NVDA",
            "direct_market_value": 1000,
            "lookthrough_market_value": 200,
            "effective_market_value": 1200,
            "effective_pct": 12.0,
        }],
        "sleeves": [{
            "category": "AI / Semiconductors",
            "direct_market_value": 1000,
            "lookthrough_market_value": 200,
            "effective_market_value": 1200,
            "direct_pct": 10.0,
            "lookthrough_pct": 2.0,
            "effective_pct": 12.0,
        }],
    }
    good = {
        "views": {
            "combined": {"total_value": 1000, "rows": [{"ticker": "NVDA", "market_value": 1000}], "categories": [], "effective_exposure": effective},
            "skb": {"total_value": 1000, "rows": [{"ticker": "NVDA", "market_value": 1000}], "categories": []},
            "parents": {"total_value": 0, "rows": [], "categories": []},
        }
    }
    assert validate_cockpit_feed(_feed(portfolio_views=good)) == []

    bad = {
        "views": {
            "combined": {
                "total_value": -1,
                "rows": [{"ticker": "", "market_value": "x"}],
                "categories": [],
                "effective_exposure": {
                    "overlap_rows": [{"ticker": "", "lookthrough_market_value": "x"}],
                    "sleeves": [{"category": "", "effective_pct": -1}],
                },
            },
            "skb": {"total_value": 0, "rows": [], "categories": []},
            "parents": {"total_value": 0, "rows": [], "categories": []},
        }
    }
    problems = validate_cockpit_feed(_feed(portfolio_views=bad))
    assert any("portfolio_views" in p for p in problems)
    assert any("effective_exposure" in p for p in problems)


def test_feed_research_wrong_type_flagged():
    assert any("research" in prob for prob in validate_cockpit_feed(_feed(research="nope")))


def test_feed_assert_raises_and_passes():
    assert_valid_cockpit_feed(_feed())          # no raise
    try:
        assert_valid_cockpit_feed({"generated_at": ""})
        assert False, "should have raised"
    except ValueError as e:
        assert "invalid CockpitFeed" in str(e)
