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
