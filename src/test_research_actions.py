"""Tests for ⑦c research_actions — the SEPARATE "From Research" candidate-action
surface (cockpit `research_actions`).

Pins: ticker parsing (TICKER - ... only; process items skipped), the priority
filter (high/med in, low out) + the DORMANT structured-date clause, the
catalyst-precedence dedup (taken_tickers), the MONITOR-stance watch-only framing,
the action-row shape (each row passes validators._validate_action), deterministic
ordering, and the end-to-end assemble_feed emission + Contract-C validity.

Run:  python -m pytest test_research_actions.py -q
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analyst_judgment import research_actions_read, _parse_research_ticker
from feed_assembler import assemble_feed
import validators

HERE = os.path.dirname(os.path.abspath(__file__))

THESES = [
    {"ticker": "AVGO", "tier": "T2", "stance": "ACTIVE", "factor_tags": ["ai_complex"]},
    {"ticker": "MU", "tier": "T2", "stance": "ACTIVE", "factor_tags": ["semis"]},
    {"ticker": "XLF", "tier": "T3", "stance": "ACTIVE", "factor_tags": ["financials"]},
    {"ticker": "GS", "tier": "T3", "stance": "ACTIVE", "factor_tags": ["financials"]},
    {"ticker": "BMNR", "tier": "T1", "stance": "MONITOR", "factor_tags": ["crypto"]},
]

# mirrors the live feed's research block (r + pr), plus a non-ticker process item
RESEARCH = {"pending": [
    {"r": "AVGO \u2014 write the AI-networking + custom-ASIC thesis line; 6/3 print", "pr": "high"},
    {"r": "MU \u2014 sizing/risk review on the 3-insider non-plan sell cluster", "pr": "med"},
    {"r": "XLF \u2014 tiering conflict (T3 cap vs the financials buildout)", "pr": "med"},
    {"r": "Staleness triage of the Working pile", "pr": "low"},
], "done": []}


def _tickers(res):
    return [a["ticker"] for a in res["research_actions"]]


# --------------------------------------------------------------------------- #
# empties / shape robustness
# --------------------------------------------------------------------------- #
def test_empty_research_variants_yield_nothing():
    for r in ({}, None, [], {"pending": []}, {"done": [{"r": "X \u2014 done", "pr": "high"}]}):
        out = research_actions_read(r, THESES)
        assert out["research_actions"] == []
        assert out["total_candidates"] == 0


def test_non_dict_pending_items_skipped():
    out = research_actions_read({"pending": ["AVGO \u2014 x", None, 5]}, THESES)
    assert out["research_actions"] == []  # only dict rows are read


# --------------------------------------------------------------------------- #
# ticker parsing
# --------------------------------------------------------------------------- #
def test_parse_ticker():
    assert _parse_research_ticker("AVGO \u2014 thesis") == "AVGO"
    assert _parse_research_ticker("MU - sizing") == "MU"
    assert _parse_research_ticker("BRK.B \u2014 review") == "BRK.B"
    assert _parse_research_ticker("XLF: tiering") == "XLF"
    assert _parse_research_ticker("Staleness triage of the pile") is None
    assert _parse_research_ticker("a lowercase note") is None
    assert _parse_research_ticker(None) is None


def test_non_ticker_process_item_not_surfaced():
    out = research_actions_read(RESEARCH, THESES)
    assert "Staleness" not in str(_tickers(out))
    assert all(t is not None for t in _tickers(out))


# --------------------------------------------------------------------------- #
# priority filter
# --------------------------------------------------------------------------- #
def test_high_and_med_surface_low_filtered():
    out = research_actions_read(RESEARCH, THESES)
    assert set(_tickers(out)) == {"AVGO", "MU", "XLF"}  # low/no-ticker dropped


def test_confidence_maps_from_priority():
    out = research_actions_read(RESEARCH, THESES)
    by_t = {a["ticker"]: a for a in out["research_actions"]}
    assert by_t["AVGO"]["confidence"] == "High"
    assert by_t["MU"]["confidence"] == "Moderate"
    assert by_t["XLF"]["confidence"] == "Moderate"


def test_low_priority_ticker_item_filtered_when_undated():
    out = research_actions_read({"pending": [{"r": "GS \u2014 low note", "pr": "low"}]}, THESES)
    assert out["research_actions"] == []


# --------------------------------------------------------------------------- #
# dormant structured-date clause (forward-compat)
# --------------------------------------------------------------------------- #
def test_dated_low_priority_item_surfaces_via_date_clause():
    # low priority but a structured near-term date -> surfaces (date clause)
    out = research_actions_read(
        {"pending": [{"r": "GS \u2014 review", "pr": "low", "days_out": 2}]}, THESES)
    assert _tickers(out) == ["GS"]
    assert "(~2d)" in out["research_actions"][0]["what"]


def test_dated_beyond_horizon_low_priority_filtered():
    out = research_actions_read(
        {"pending": [{"r": "GS \u2014 review", "pr": "low", "days_out": 30}]},
        THESES, horizon_days=7)
    assert out["research_actions"] == []


# --------------------------------------------------------------------------- #
# dedup — catalyst precedence
# --------------------------------------------------------------------------- #
def test_dedup_drops_ticker_already_in_action_or_catalyst_lane():
    out = research_actions_read(RESEARCH, THESES, taken_tickers={"AVGO"})
    assert "AVGO" not in _tickers(out)
    assert set(_tickers(out)) == {"MU", "XLF"}  # AVGO yields to the catalyst/action lane


# --------------------------------------------------------------------------- #
# MONITOR stance — watch-only, no gate, no add nudge
# --------------------------------------------------------------------------- #
def test_monitor_stance_is_watch_only():
    out = research_actions_read({"pending": [{"r": "BMNR \u2014 review", "pr": "high"}]}, THESES)
    row = out["research_actions"][0]
    assert row["ticker"] == "BMNR"
    assert row["gate"] is None
    assert row["confidence"] == "Low"
    assert "no add" in row["your_move"].lower()


def test_non_monitor_carries_gate_hook():
    out = research_actions_read({"pending": [{"r": "AVGO \u2014 review", "pr": "high"}]}, THESES)
    g = out["research_actions"][0]["gate"]
    assert isinstance(g, dict) and g["needs_gate"] is True
    assert g["default_action"] == "REVIEW"


# --------------------------------------------------------------------------- #
# ordering — priority first, then confidence, then first-seen
# --------------------------------------------------------------------------- #
def test_high_priority_ranks_above_med():
    out = research_actions_read(RESEARCH, THESES)
    ranks = {a["ticker"]: a["rank"] for a in out["research_actions"]}
    assert ranks["AVGO"] < ranks["MU"] and ranks["AVGO"] < ranks["XLF"]


def test_ranks_are_contiguous_from_one():
    out = research_actions_read(RESEARCH, THESES)
    assert [a["rank"] for a in out["research_actions"]] == [1, 2, 3]


# --------------------------------------------------------------------------- #
# contract — every row is a valid action row; kind is registered
# --------------------------------------------------------------------------- #
def test_rows_pass_action_validator():
    out = research_actions_read(RESEARCH, THESES)
    assert out["research_actions"], "expected non-empty for this test"
    for a in out["research_actions"]:
        assert validators._validate_action(a) == []
        assert a["kind"] == "research_review"


# --------------------------------------------------------------------------- #
# end-to-end — assemble_feed emits research_actions; feed stays Contract-C valid
# --------------------------------------------------------------------------- #
def _load(name):
    with open(os.path.join(HERE, name)) as f:
        return json.load(f)


def test_assemble_feed_emits_research_actions_and_validates():
    feed = json.loads(json.dumps(
        assemble_feed(_load("golden_snapshot.json"), parabolic={"MU"}, research=RESEARCH)))
    assert "research_actions" in feed
    ra_tickers = {a["ticker"] for a in feed["research_actions"]}
    # AVGO/MU/XLF are not engine actions in the golden, none on a (non-passed)
    # catalyst lane -> all three surface here.
    assert {"AVGO", "MU", "XLF"} <= ra_tickers
    assert validators.validate_cockpit_feed(feed) == []


def test_assemble_feed_research_actions_empty_when_no_research():
    feed = assemble_feed(_load("golden_snapshot.json"), parabolic={"MU"})
    assert feed["research_actions"] == []  # absent research -> empty (golden stays minimal)
