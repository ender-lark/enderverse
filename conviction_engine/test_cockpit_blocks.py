"""Tests for the Tier-1 additive FEED blocks: `heartbeat` (layer run-status
strip), `synthesis` (Daily-Synthesis state-of-play), and `research` (the live
Research Queue). All three are EXTERNAL reads threaded through additively — the
assembler defaults them empty, the optional Contract-C validators check them
only when present, and build_full_feed passes them straight through.

Run:  python -m pytest test_cockpit_blocks.py -q
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from feed_assembler import assemble_feed
from runtime_skeleton import build_full_feed
from validators import validate_cockpit_feed

HERE = os.path.dirname(os.path.abspath(__file__))

HB = [
    {"layer": "Morning Scan", "status": "ok", "last_run": "2026-06-01T12:17", "note": "Signal Log"},
    {"layer": "Insider feed", "status": "down", "last_run": None, "note": "reads a stub (non-functional)"},
    {"layer": "Macro cache", "status": "stale", "last_run": "2026-05-28", "note": "no auto-refresh"},
]
SY = {"date": "2026-06-01", "state_of_play": "AI leads everything.",
      "delta": "XLF added; AVGO into earnings.", "hanging": ["AVGO thesis line"],
      "source": "Daily Synthesis"}
RS = {"pending": [{"title": "AVGO thesis line", "priority": "high", "note": "Tier-A, time-sensitive"}],
      "done": [{"title": "Rotation engine live", "finding": "AI leads; burned sleeves lag."}]}


def _load_snapshot():
    with open(os.path.join(HERE, "golden_snapshot.json")) as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
# assemble_feed: defaults empty + threads when supplied
# --------------------------------------------------------------------------- #
def test_assemble_feed_blocks_default_empty():
    feed = assemble_feed(_load_snapshot(), parabolic={"MU"})
    assert feed["heartbeat"] == []
    assert feed["synthesis"] == {}
    assert feed["research"] == {}
    assert validate_cockpit_feed(feed) == []


def test_assemble_feed_threads_supplied_blocks():
    feed = assemble_feed(_load_snapshot(), parabolic={"MU"},
                         heartbeat=HB, synthesis=SY, research=RS)
    assert feed["heartbeat"] == HB
    assert feed["synthesis"] == SY
    assert feed["research"] == RS
    assert validate_cockpit_feed(feed) == []


# --------------------------------------------------------------------------- #
# validators: optional (absent → valid), shape-checked when present
# --------------------------------------------------------------------------- #
def _minimal_feed():
    return {"generated_at": "2026-06-01T16:00:00", "staleness": {}, "hero": {},
            "macro": {}, "fresh_signals": [], "holdings": [], "rotation": []}


def test_validator_absent_blocks_still_valid():
    assert validate_cockpit_feed(_minimal_feed()) == []   # all three optional


def test_validator_accepts_valid_heartbeat():
    feed = _minimal_feed(); feed["heartbeat"] = HB
    assert validate_cockpit_feed(feed) == []


def test_validator_catches_bad_heartbeat_status():
    feed = _minimal_feed()
    feed["heartbeat"] = [{"layer": "X", "status": "exploded"}]
    probs = validate_cockpit_feed(feed)
    assert any("status must be one of" in p for p in probs)


def test_validator_catches_heartbeat_missing_layer():
    feed = _minimal_feed()
    feed["heartbeat"] = [{"status": "ok"}]
    probs = validate_cockpit_feed(feed)
    assert any("missing field: layer" in p for p in probs)


def test_validator_catches_non_list_heartbeat():
    feed = _minimal_feed(); feed["heartbeat"] = {"not": "a list"}
    probs = validate_cockpit_feed(feed)
    assert any("heartbeat must be a list" in p for p in probs)


def test_validator_catches_non_dict_synthesis():
    feed = _minimal_feed(); feed["synthesis"] = ["not", "a", "dict"]
    probs = validate_cockpit_feed(feed)
    assert any("synthesis must be a dict" in p for p in probs)


# --------------------------------------------------------------------------- #
# build_full_feed threads all three through (the real integration seam)
# --------------------------------------------------------------------------- #
_PAGE = """## Per-Ticker Aggregation (>= $500, by MV)
<table>
<tr><td>Ticker</td><td>Shares</td><td>MV</td><td>%</td><td>Owners</td></tr>
<tr><td>---</td><td>--:</td><td>--:</td><td>--:</td><td>---</td></tr>
<tr><td>NVDA</td><td>100.00</td><td>$10,000</td><td>5.00%</td><td>ps</td></tr>
</table>"""


def test_build_full_feed_threads_blocks():
    theses = [{"ticker": "NVDA", "tier": "T1", "stance": "ACTIVE", "factor_tags": ["AI_complex"]}]
    feed = build_full_feed(_PAGE, {}, theses,            # empty prices → NO-DATA rotation, no abort
                           heartbeat=HB, synthesis=SY, research=RS,
                           as_of="2026-06-01", run_timestamp="2026-06-01T16:00:00")
    assert feed["heartbeat"] == HB
    assert feed["synthesis"] == SY
    assert feed["research"] == RS
    assert validate_cockpit_feed(feed) == []


# --------------------------------------------------------------------------- #
# radar (block ⑨ — endorsed, not owned): optional + empty valid, list-of-dicts;
# DERIVED off the daily calls by default, an explicit list overrides additively.
# --------------------------------------------------------------------------- #
RADAR_ROW = {"ticker": "JETS", "author": "Newton", "direction": "long", "entry": None,
             "stop": 24.79, "target": 34, "window": "2-4wk", "date": "2026-06-01", "quote": "base breakout"}


def test_validator_radar_absent_and_empty_are_valid():
    assert validate_cockpit_feed(_minimal_feed()) == []          # absent → valid
    feed = _minimal_feed(); feed["radar"] = []
    assert validate_cockpit_feed(feed) == []                     # empty list → valid


def test_validator_accepts_valid_radar():
    feed = _minimal_feed(); feed["radar"] = [RADAR_ROW]
    assert validate_cockpit_feed(feed) == []


def test_validator_catches_non_list_radar():
    feed = _minimal_feed(); feed["radar"] = {"not": "a list"}
    assert any("radar must be a list" in p for p in validate_cockpit_feed(feed))


def test_validator_catches_radar_non_dict_row():
    feed = _minimal_feed(); feed["radar"] = ["JETS"]
    assert any("radar[0] must be a dict" in p for p in validate_cockpit_feed(feed))


def test_validator_catches_radar_missing_ticker():
    feed = _minimal_feed(); feed["radar"] = [{"author": "Newton"}]
    assert any("ticker must be a non-empty string" in p for p in validate_cockpit_feed(feed))


def test_assemble_feed_radar_defaults_derived_empty():
    # the golden snapshot's daily calls are all owned/parked → derived radar is [].
    feed = assemble_feed(_load_snapshot(), parabolic={"MU"})
    assert feed["radar"] == []
    assert validate_cockpit_feed(feed) == []


def test_assemble_feed_radar_explicit_override():
    feed = assemble_feed(_load_snapshot(), parabolic={"MU"}, radar=[RADAR_ROW])
    assert feed["radar"] == [RADAR_ROW]
    assert validate_cockpit_feed(feed) == []
