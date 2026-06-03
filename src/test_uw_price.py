"""Unit tests for the uw_price real fetcher (S2).

Convention: lives in src/ beside the module. Run:
    python -m pytest src/test_uw_price.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from validators import validate_items
from uw_price import (
    pct_return,
    relative_strength,
    classify_rotation,
    uw_price_rotation_reader,
    build_uw_price_source,
    ROTATION_BANDS,
)


# --------------------------------------------------------------------------- #
# pct_return — the core return math
# --------------------------------------------------------------------------- #
def test_pct_return_one_step():
    assert pct_return([100, 110], 1) == pytest.approx(0.10)


def test_pct_return_three_step_uses_correct_reference():
    # lookback=3 -> reference is the 4th-from-last close (index -4).
    assert pct_return([100, 104, 108, 130], 3) == pytest.approx(0.30)


def test_pct_return_negative():
    assert pct_return([100, 90], 1) == pytest.approx(-0.10)


def test_pct_return_insufficient_length_raises():
    with pytest.raises(ValueError):
        pct_return([100, 110], 3)          # len 2, lookback 3


def test_pct_return_zero_reference_raises():
    with pytest.raises(ValueError):
        pct_return([0, 100], 1)


def test_pct_return_none_raises():
    with pytest.raises(ValueError):
        pct_return(None, 1)


# --------------------------------------------------------------------------- #
# relative_strength — proxy return minus benchmark return
# --------------------------------------------------------------------------- #
def test_relative_strength_basic():
    # proxy +10%, benchmark +5% -> rel +5%.
    assert relative_strength([100, 110], [100, 105], 1) == pytest.approx(0.05)


def test_relative_strength_underperformer_negative():
    # proxy +2%, benchmark +10% -> rel -8%.
    assert relative_strength([100, 102], [100, 110], 1) == pytest.approx(-0.08)


# --------------------------------------------------------------------------- #
# classify_rotation — mechanical bands + boundaries
# --------------------------------------------------------------------------- #
def test_classify_leading():
    assert classify_rotation(0.06, 0.47) == "LEADING"


def test_classify_lagging():
    assert classify_rotation(-0.01, -0.08) == "LAGGING"


def test_classify_in_line():
    assert classify_rotation(0.0, 0.0) == "IN LINE"


def test_classify_turning_down():
    # led over 3M (+10%) but sharply weaker last month (-5%).
    assert classify_rotation(-0.05, 0.10) == "TURNING DOWN"


def test_classify_turning_up():
    # lagged over 3M (-10%) but inflecting up last month (+5%).
    assert classify_rotation(0.05, -0.10) == "TURNING UP"


def test_classify_lead_boundary_inclusive():
    # exactly at the +5% lead band -> LEADING (>=).
    assert classify_rotation(0.0, ROTATION_BANDS["lead_3m"]) == "LEADING"


def test_classify_lag_boundary_inclusive():
    # exactly at the -5% lag band -> LAGGING (<=).
    assert classify_rotation(0.0, ROTATION_BANDS["lag_3m"]) == "LAGGING"


def test_classify_just_inside_is_in_line():
    assert classify_rotation(0.0, 0.049) == "IN LINE"


def test_classify_none_is_no_data():
    assert classify_rotation(None, None) == "NO DATA"
    assert classify_rotation(0.1, None) == "NO DATA"


# --------------------------------------------------------------------------- #
# uw_price_rotation_reader — fake closes -> known rows
# closes are [oldest .. newest]; test uses lookback_1m=1, lookback_3m=3.
# --------------------------------------------------------------------------- #
FAKE_CLOSES = {
    "SPY":  [100, 104, 108, 110],   # 3M +10%
    "SMH":  [100, 130, 150, 157],   # 3M +57%  -> rel +47% vs SPY  (LEADING)
    "REMX": [100, 95, 96, 98],      # 3M  -2%  -> rel -12% vs SPY  (LAGGING)
    "VOLT": [100, 101],             # too short for lookback_3m=3  -> NO DATA
}
RK = dict(benchmark="SPY", ai_benchmark="SMH", lookback_1m=1, lookback_3m=3,
          as_of="2026-05-29")


def _rows_by_proxy(rows):
    return {r["proxy"]: r for r in rows}


def test_reader_leading_name():
    rows = _rows_by_proxy(
        uw_price_rotation_reader(FAKE_CLOSES, proxies=["SMH"], **RK))
    smh = rows["SMH"]
    assert smh["label"] == "LEADING"
    assert smh["rel_3m"] == pytest.approx(0.47)
    assert smh["abs_3m"] == pytest.approx(0.57)
    assert smh["rel_3m_vs_smh"] == 0.0          # SMH vs itself


def test_reader_lagging_name():
    rows = _rows_by_proxy(
        uw_price_rotation_reader(FAKE_CLOSES, proxies=["REMX"], **RK))
    remx = rows["REMX"]
    assert remx["label"] == "LAGGING"
    assert remx["rel_3m"] == pytest.approx(-0.12)
    assert remx["abs_3m"] == pytest.approx(-0.02)
    assert remx["rel_3m_vs_smh"] == pytest.approx(-0.59)   # -2% - 57%


def test_reader_no_data_row_for_short_series():
    rows = _rows_by_proxy(
        uw_price_rotation_reader(FAKE_CLOSES, proxies=["VOLT"], **RK))
    volt = rows["VOLT"]
    assert volt["label"] == "NO DATA"
    assert volt["rel_3m"] is None and volt["abs_3m"] is None
    assert "note" in volt


def test_reader_vs_smh_best_effort_when_smh_missing():
    closes = {k: v for k, v in FAKE_CLOSES.items() if k != "SMH"}
    rows = _rows_by_proxy(
        uw_price_rotation_reader(closes, proxies=["REMX"], **RK))
    remx = rows["REMX"]
    # vs-SPY card still computed...
    assert remx["label"] == "LAGGING"
    assert remx["rel_3m"] == pytest.approx(-0.12)
    # ...but the vs-SMH leg degrades to None rather than sinking the row.
    assert remx["rel_3m_vs_smh"] is None


# --------------------------------------------------------------------------- #
# build_uw_price_source — the wired plug emits VALID Contract-A cards
# --------------------------------------------------------------------------- #
def test_build_source_dials_and_card_shape():
    src = build_uw_price_source(FAKE_CLOSES, proxies=["SMH", "REMX"], **RK)
    assert src.name == "uw_price"
    assert src.trust_weight == 0.95
    assert src.independence_group == "market_data"

    items = src.fetch()
    # every emitted card passes the seam validator
    assert validate_items(items)["bad"] == []

    by_subj = {i.subject: i for i in items}
    smh = by_subj["SMH"]
    assert smh.kind == "rotation"
    assert smh.content == "LEADING +47%/3M vs mkt"
    assert smh.data["label"] == "LEADING"
    assert smh.data["rel_3m"] == pytest.approx(0.47)
    assert smh.data["rel_3m_vs_smh"] == 0.0

    remx = by_subj["REMX"]
    assert remx.content == "LAGGING -12%/3M vs mkt"


def test_build_source_no_data_card_still_valid():
    src = build_uw_price_source(FAKE_CLOSES, proxies=["VOLT"], **RK)
    items = src.fetch()
    assert validate_items(items)["bad"] == []     # NO DATA card is still well-formed
    assert items[0].content == "NO DATA"


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-q"]))
