"""Conviction Engine · Seam B (event-driven ACT-NOW surfacing) — Surfacing fix, Chunk 1.

THE point of this build (handoff §4 negative test): on a FLAT-PRICE input — every
holding cd:"flat", exactly like the live 6/1 feed — a HELD name carrying a catalyst
within the horizon (AVGO, 6/3, ~2 days out) MUST surface on the act-now set, with
needs_you.count >= 1, a days-to-catalyst countdown, and a review-not-buy framing.
Without the catalyst it does NOT surface (movement-gated) — proving it's the
catalyst, not price movement, that puts it there.

MONITOR-stance holds (burned sleeves) surface a catalyst as WATCH/RISK only, never
an ADD nudge. The golden bundle (build_snapshot_bundle) has AVGO held + flat and the
burned-sleeve names (BMNR/LEU/...) held with stance MONITOR — the ideal base.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from feed_assembler import assemble_feed
from validators import validate_cockpit_feed
from build_golden import build_snapshot_bundle
from analyst_judgment import catalyst_needs_you, actions_read
from test_runtime_skeleton import _theses

THESES = _theses()  # golden theses: BMNR/LEU/UUUU/MP/IBIT carry stance MONITOR

AVGO_CAT = {"ticker": "AVGO", "label": "Q2 earnings", "date": "2026-06-03",
            "days_out": 2, "source": "Catalyst Calendar"}
BMNR_CAT = {"ticker": "BMNR", "label": "token unlock", "date": "2026-06-04",
            "days_out": 3, "source": "Catalyst Calendar"}


def _ny(feed):
    return feed["hero"]["needs_you"]


def _rows_for(feed, ticker):
    return [a for a in feed["actions"] if a.get("ticker") == ticker]


# --------------------------------------------------------------------------- #
# THE §4 NEGATIVE TEST — AVGO surfaces on flat prices
# --------------------------------------------------------------------------- #
def test_avgo_surfaces_on_flat_prices():
    bundle = build_snapshot_bundle()  # AVGO held + cd:"flat", not a fresh signal
    with_cat = assemble_feed(bundle, parabolic={"MU"}, catalysts=[AVGO_CAT])
    without = assemble_feed(bundle, parabolic={"MU"})

    # needs_you reflects the catalyst (the false count:0 fix) ...
    details_with = {i["detail"] for i in _ny(with_cat)["items"]}
    details_without = {i["detail"] for i in _ny(without)["items"]}
    assert "AVGO" in details_with
    assert "AVGO" not in details_without               # not surfaced by movement
    assert _ny(with_cat)["count"] == _ny(without)["count"] + 1
    assert _ny(with_cat)["count"] >= 1

    # ... and it lands on the Actions surface with a countdown, review-not-buy
    avgo = _rows_for(with_cat, "AVGO")
    assert len(avgo) == 1
    row = avgo[0]
    assert row["kind"] == "catalyst_imminent"
    assert row["kind"] != "buy_now"
    assert row["days_to_catalyst"] == 2
    assert row["confidence"] == "Moderate"             # held, non-MONITOR
    assert "decision prompt" in row["your_move"].lower()
    assert not _rows_for(without, "AVGO")              # absent without the catalyst

    assert validate_cockpit_feed(with_cat) == []       # still Contract-C valid


# --------------------------------------------------------------------------- #
# MONITOR hold — catalyst is WATCH/RISK, never an ADD
# --------------------------------------------------------------------------- #
def test_monitor_catalyst_is_watch_not_add():
    bundle = build_snapshot_bundle()  # BMNR held, stance MONITOR
    feed = assemble_feed(bundle, parabolic={"MU"}, catalysts=[BMNR_CAT])
    bmnr = _rows_for(feed, "BMNR")
    assert len(bmnr) == 1
    row = bmnr[0]
    assert row["kind"] == "catalyst_imminent"
    assert row["confidence"] == "Low"
    assert row["gate"] is None                          # no add gate hook
    mv = row["your_move"].lower()
    assert "watch" in mv and "no add" in mv
    assert validate_cockpit_feed(feed) == []


# --------------------------------------------------------------------------- #
# catalyst_needs_you — scope + determinism (the helper in isolation)
# --------------------------------------------------------------------------- #
def test_helper_held_name_within_horizon_fires():
    items = catalyst_needs_you([AVGO_CAT], {"AVGO"}, THESES)
    assert len(items) == 1
    assert items[0]["reason"] == "catalyst_imminent"
    assert items[0]["detail"] == "AVGO"
    assert items[0]["days_out"] == 2


def test_helper_non_held_skipped():
    assert catalyst_needs_you([AVGO_CAT], set(), THESES) == []


def test_helper_beyond_horizon_skipped():
    far = {**AVGO_CAT, "days_out": 10}                  # > default 7
    assert catalyst_needs_you([far], {"AVGO"}, THESES) == []


def test_helper_past_catalyst_skipped():
    past = {**AVGO_CAT, "days_out": -1}
    assert catalyst_needs_you([past], {"AVGO"}, THESES) == []


def test_helper_monitor_tagged():
    items = catalyst_needs_you([BMNR_CAT], {"BMNR"}, THESES)
    assert len(items) == 1
    assert items[0]["stance"] == "MONITOR"


def test_helper_deterministic_sort():
    cats = [{**AVGO_CAT, "ticker": "ZZZ", "days_out": 5},
            {**AVGO_CAT, "ticker": "AVGO", "days_out": 5},
            {**AVGO_CAT, "ticker": "MU", "days_out": 1}]
    items = catalyst_needs_you(cats, {"ZZZ", "AVGO", "MU"}, THESES)
    assert [(i["days_out"], i["detail"]) for i in items] == [(1, "MU"), (5, "AVGO"), (5, "ZZZ")]


def test_helper_malformed_rows_skipped():
    cats = ["AVGO", {"ticker": "AVGO"}, {**AVGO_CAT, "days_out": "2"}]
    assert catalyst_needs_you(cats, {"AVGO"}, THESES) == []


# --------------------------------------------------------------------------- #
# actions_read picks up the new reason (guards "unknown reasons are ignored")
# --------------------------------------------------------------------------- #
def test_actions_read_renders_catalyst_item():
    ny_items = [{"reason": "catalyst_imminent", "detail": "AVGO", "days_out": 2,
                 "label": "Q2 earnings", "stance": None, "note": "x"}]
    out = actions_read([], ny_items, THESES)
    rows = [a for a in out["actions"] if a["ticker"] == "AVGO"]
    assert len(rows) == 1 and rows[0]["kind"] == "catalyst_imminent"
    # a review prompt is NOT counted as an act-like (buy) action
    assert out["act_like"] == 0
