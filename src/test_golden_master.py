"""Golden-master regression test for the Analyst output (Checkpoint A6).

Locks the behavior frozen at A5: `feed_assembler` run over the frozen
golden_snapshot MUST reproduce the frozen golden_feed — exactly. This is the
regression WALL. If any future change to a read, the config, or the assembler
quietly alters a grade / direction / fresh-signal, the full-feed test fails and
the granular tests pinpoint what drifted.

If a change here is INTENTIONAL (a deliberate rule or prose update), regenerate
the oracle on purpose:  `python build_golden.py`  then re-commit the two JSONs.
Never hand-edit golden_feed.json / golden_snapshot.json.

Run:  python -m pytest test_golden_master.py -q
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from feed_assembler import assemble_feed
from validators import validate_cockpit_feed

HERE = os.path.dirname(os.path.abspath(__file__))
PARABOLIC = {"MU"}          # the runtime parabolic flag baked into the oracle
FRESH_TARGET = sorted([("ITA", "act"), ("FN", "watch")])


def _load(name):
    with open(os.path.join(HERE, name)) as f:
        return json.load(f)


def _assembled():
    # round-trip through JSON so both sides are identical native types
    return json.loads(json.dumps(assemble_feed(_load("golden_snapshot.json"),
                                               parabolic=PARABOLIC)))


def _pos(feed):
    return {p["t"]: p for h in feed["holdings"] for p in h["pos"]}


# ── the wall: full, exact reproduction ──
def test_golden_master_reproduces_full_feed():
    got, want = _assembled(), _load("golden_feed.json")
    assert got == want, (
        "Analyst output diverged from the frozen oracle (golden_feed.json). "
        "If intentional, run `python build_golden.py` and re-commit the JSONs; "
        "otherwise a read/config/assembler change broke a frozen value."
    )


# ── granular diagnostics: pinpoint WHAT drifted when the wall fails ──
def test_golden_master_contract_c_valid():
    assert validate_cockpit_feed(_assembled()) == []


def test_golden_master_conviction_grades_per_name():
    got = {t: p["cv"] for t, p in _pos(_assembled()).items()}
    want = {t: p["cv"] for t, p in _pos(_load("golden_feed.json")).items()}
    assert got == want


def test_golden_master_direction_per_name():
    got = {t: p["cd"] for t, p in _pos(_assembled()).items()}
    want = {t: p["cd"] for t, p in _pos(_load("golden_feed.json")).items()}
    assert got == want


def test_golden_master_net_reads_per_name():
    got = {t: p["nr"] for t, p in _pos(_assembled()).items()}
    want = {t: p["nr"] for t, p in _pos(_load("golden_feed.json")).items()}
    assert got == want


def test_golden_master_fresh_signal_set():
    got = sorted((s["ticker"], s["urgency"]) for s in _assembled()["fresh_signals"])
    want = sorted((s["ticker"], s["urgency"]) for s in _load("golden_feed.json")["fresh_signals"])
    assert got == want == FRESH_TARGET


def test_golden_master_holdings_and_position_counts():
    got, want = _assembled(), _load("golden_feed.json")
    assert len(got["holdings"]) == len(want["holdings"])
    assert sum(len(h["pos"]) for h in got["holdings"]) == \
           sum(len(h["pos"]) for h in want["holdings"]) == 18
