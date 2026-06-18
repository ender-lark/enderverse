import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sell_gate
from sell_gate import evaluate_sell_gate, PASS, BLOCK, FLAG, NOT_EVALUABLE


def _gate(**kw):
    base = dict(
        ticker="LEU",
        direction="SELL",
        thesis=None,
        range_position=None,
        next_catalyst=None,
        funding_tier=None,
        thesis_break=None,
        blocks=False,
    )
    base.update(kw)
    return evaluate_sell_gate(**base)


def test_not_evaluable_on_missing_thesis_state():
    g = _gate(thesis={}, range_position={"near_52wk_low": True})
    assert g["verdict"] == NOT_EVALUABLE
    assert g["evaluable"] is False
    assert "thesis state" in g["reasons"][0]


def test_not_evaluable_on_missing_range():
    g = _gate(thesis={"state": "alive"}, range_position={"near_52wk_low": "not_checked"})
    assert g["verdict"] == NOT_EVALUABLE
    assert g["evaluable"] is False
    assert "52wk range" in g["reasons"][0]


def test_leu_janus_flags_by_default_never_blocks():
    # live thesis at/near a 52-week low, no thesis-break: the doctrine hit.
    # With the sell_gate_blocks dial OFF (default), this FLAGs -- a visible
    # prompt, the card stays actionable; it does NOT block.
    g = _gate(thesis={"state": "alive"}, range_position={"near_52wk_low": True})
    assert g["verdict"] == FLAG
    assert g["requires_thesis_break"] is True
    assert g["blocks"] is False
    assert any("near 52-wk low" in r for r in g["reasons"])


def test_leu_janus_blocks_only_when_dial_on():
    g = _gate(thesis={"state": "alive"}, range_position={"near_52wk_low": True}, blocks=True)
    assert g["verdict"] == BLOCK
    assert g["requires_thesis_break"] is True
    assert g["blocks"] is True


def test_explicit_thesis_break_clears_near_low():
    g = _gate(
        thesis={"state": "alive"},
        range_position={"near_52wk_low": True},
        thesis_break="enrichment program cancelled",
        blocks=True,
    )
    assert g["verdict"] in (PASS, FLAG)
    assert g["verdict"] != BLOCK


def test_dead_thesis_passes():
    g = _gate(thesis={"state": "dead"}, range_position={"near_52wk_low": True})
    assert g["verdict"] == PASS
    assert g["alive"] is False


def test_permitted_funding_tier_passes():
    g = _gate(
        thesis={"state": "alive"},
        range_position={"near_52wk_low": True},
        funding_tier="redundant_wrapper",
    )
    assert g["verdict"] == PASS


def test_live_thesis_not_near_low_flags_only():
    g = _gate(thesis={"state": "alive"}, range_position={"near_52wk_low": False})
    assert g["verdict"] == FLAG
    assert g["near_52wk_low"] is False


def test_live_catalyst_surfaces_as_flag_text():
    g = _gate(
        thesis={"state": "alive"},
        range_position={"near_52wk_low": False},
        next_catalyst={"live": True, "label": "FDA decision"},
    )
    assert g["catalyst_flag"] and "FDA decision" in g["catalyst_flag"]
