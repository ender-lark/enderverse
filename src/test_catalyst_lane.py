"""Conviction Engine · Seam A (catalyst lane) — Surfacing fix, Chunk 0.

The catalyst lane was a DARK lane: `feed_assembler` hardcoded `catalysts: []`, so
a near-term event could never reach the feed (the 6/1 root cause, half of it).
Seam A threads a `catalysts` plug through build_full_feed -> assemble_feed ->
feed["catalysts"], validated by Contract-C as an OPTIONAL block: empty/absent is
an HONEST dark lane (never "no catalysts"); a malformed row is caught at the seam.

These tests pin that PLUMBING only. The SURFACING of a catalyst onto the act-now
set (the needs_you / actions union) is Seam B (Chunk 1), tested there.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from feed_assembler import assemble_feed
from runtime_skeleton import build_full_feed
from runtime_adapters import catalysts_from_calendar_rows
from validators import validate_cockpit_feed, _validate_catalyst
from build_golden import build_snapshot_bundle
from test_runtime_skeleton import PAGE, _uw_all, _theses

# a well-formed catalyst row (the Seam-A contract shape)
AVGO_CAT = {"ticker": "AVGO", "label": "Q2 earnings", "date": "2026-06-03",
            "days_out": 2, "source": "Catalyst Calendar"}


# --------------------------------------------------------------------------- #
# assemble_feed — the emit site (was the hardcoded `[]`)
# --------------------------------------------------------------------------- #
def test_assemble_emits_supplied_catalysts():
    feed = assemble_feed(build_snapshot_bundle(), parabolic={"MU"},
                         catalysts=[AVGO_CAT])
    assert feed["catalysts"] == [AVGO_CAT]
    assert validate_cockpit_feed(feed) == []


def test_assemble_defaults_to_dark_lane():
    """No catalysts supplied -> [] (an unsourced/dark lane), never invented."""
    feed = assemble_feed(build_snapshot_bundle(), parabolic={"MU"})
    assert feed["catalysts"] == []
    assert validate_cockpit_feed(feed) == []


# --------------------------------------------------------------------------- #
# build_full_feed — the plug threads end to end through the real entry point
# --------------------------------------------------------------------------- #
def test_full_feed_threads_catalysts():
    feed = build_full_feed(PAGE, _uw_all(), _theses(),
                           catalysts=[AVGO_CAT],
                           run_timestamp="2026-06-01T16:00:00")
    assert feed["catalysts"] == [AVGO_CAT]


def test_calendar_adapter_output_surfaces_in_full_feed_actions():
    cats = catalysts_from_calendar_rows(
        [{"ticker": "NVDA", "date": "2026-06-03T00:00:00+00:00", "name": "Q2 earnings"}],
        as_of="2026-06-01",
        horizon_days=7,
    )
    feed = build_full_feed(PAGE, _uw_all(), _theses(),
                           catalysts=cats,
                           run_timestamp="2026-06-01T16:00:00",
                           as_of="2026-06-01")
    row = next(a for a in feed["actions"] if a.get("ticker") == "NVDA")
    assert row["kind"] == "catalyst_imminent"
    assert row["days_to_catalyst"] == 2


def test_full_feed_omitted_catalysts_is_dark_lane():
    feed = build_full_feed(PAGE, _uw_all(), _theses(),
                           run_timestamp="2026-06-01T16:00:00")
    assert feed["catalysts"] == []


# --------------------------------------------------------------------------- #
# Contract-C — row-shape validation (optional block)
# --------------------------------------------------------------------------- #
def test_valid_catalyst_row_passes():
    assert _validate_catalyst(AVGO_CAT) == []


def test_missing_field_caught():
    bad = {k: v for k, v in AVGO_CAT.items() if k != "days_out"}
    assert any("days_out" in e for e in _validate_catalyst(bad))


def test_days_out_must_be_int():
    bad = {**AVGO_CAT, "days_out": "2"}
    assert any("days_out must be an int" in e for e in _validate_catalyst(bad))


def test_empty_string_field_caught():
    bad = {**AVGO_CAT, "ticker": "  "}
    assert any("ticker must be a non-empty string" in e for e in _validate_catalyst(bad))


def test_non_dict_catalyst_caught():
    assert _validate_catalyst("AVGO") == ["must be a dict"]


def test_feed_with_malformed_catalyst_row_fails_validation():
    """A bad row reaches validate_cockpit_feed and is caught at the seam."""
    feed = assemble_feed(build_snapshot_bundle(), parabolic={"MU"},
                         catalysts=[{"ticker": "AVGO"}])  # missing 4 fields
    errs = validate_cockpit_feed(feed)
    assert any(e.startswith("catalysts[0]") for e in errs)


def test_absent_catalysts_key_still_valid():
    """A feed dict with no `catalysts` key at all stays Contract-C valid."""
    feed = assemble_feed(build_snapshot_bundle(), parabolic={"MU"})
    feed.pop("catalysts", None)
    assert validate_cockpit_feed(feed) == []
