"""End-to-end full-chain test (Checkpoint 3): Sources -> Collection -> Analyst.

Wires REAL BaseSource plugs through the REAL collection runner into the REAL
feed_assembler and proves the whole pipeline composes into a valid CockpitFeed
that reproduces the frozen oracle. The plugs here are FIXTURE-REPLAY plugs: they
inject the canned golden rows (the live plugs fetch UW / Notion / Fundstrat), so
this exercises the WIRING + contracts, not the data sourcing.

What this guards that the unit tests + golden-master don't:
  • the Source -> Collection contract (plugs -> CollectedSnapshot, ok/failed,
    staleness, critical_missing) actually runs;
  • the Collection -> Analyst contract (a real collected snapshot, with
    collection-computed metadata, flows into assemble_feed) actually runs;
  • a bad plug can't sink the pull (error tolerance end-to-end).

Run:  python -m pytest test_end_to_end.py -q
"""
import dataclasses
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sources import BaseSource, SourceRegistry
from collection import collect
from feed_assembler import assemble_feed
from validators import validate_collected_snapshot, validate_cockpit_feed

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE_ORDER = ["uw_price", "uw_macro", "fundstrat_bible",
                "fundstrat_daily", "meridian", "portfolio"]
PARABOLIC = {"MU"}
RUN_TS = "2026-05-29T16:00:00"


def _golden():
    with open(os.path.join(HERE, "golden_snapshot.json")) as f:
        snap = json.load(f)
    with open(os.path.join(HERE, "golden_feed.json")) as f:
        feed = json.load(f)
    return snap, feed


def _replay_registry(extra=None, drop=()):
    """6 fixture-replay plugs (golden rows grouped by source). `extra` appends
    plugs (e.g. a broken one); `drop` omits named sources."""
    snap, _ = _golden()
    by_src = defaultdict(list)
    for it in snap["snapshot"]["items"]:
        by_src[it["source"]].append(it)
    reg = SourceRegistry()
    for s in SOURCE_ORDER:
        if s in drop:
            continue
        reg.register(BaseSource(name=s, fetcher=(lambda r=by_src[s]: [dict(x) for x in r])))
    for plug in (extra or []):
        reg.register(plug)
    return reg


def _broken_plug(name):
    def boom():
        raise RuntimeError("connector down")
    return BaseSource(name=name, fetcher=boom)


def _run(reg):
    snap = collect(reg, run_timestamp=RUN_TS)
    return snap, dataclasses.asdict(snap)


# ── the chain composes cleanly ──
def test_e2e_collection_is_clean():
    snap, _ = _run(_replay_registry())
    assert sorted(snap.sources_ok) == sorted(SOURCE_ORDER)
    assert snap.sources_failed == []
    assert snap.critical_missing == []


def test_e2e_collected_snapshot_valid():
    _, sd = _run(_replay_registry())
    assert validate_collected_snapshot(sd) == []
    assert len(sd["items"]) == 48


def test_e2e_staleness_matches_golden():
    snap_g, _ = _golden()
    _, sd = _run(_replay_registry())
    assert sd["staleness"] == snap_g["snapshot"]["staleness"]


# ── the headline: full chain reproduces the frozen oracle ──
def test_e2e_full_chain_reproduces_oracle():
    snap_g, feed_g = _golden()
    _, sd = _run(_replay_registry())
    feed = assemble_feed({"as_of": snap_g["as_of"], "snapshot": sd,
                          "theses": snap_g["theses"]}, parabolic=PARABOLIC)
    assert validate_cockpit_feed(feed) == []
    assert json.loads(json.dumps(feed)) == feed_g, (
        "full chain (plugs -> collection -> assembler) diverged from the oracle"
    )


# ── error tolerance: a bad plug can't sink the pull ──
def test_e2e_noncritical_plug_failure_survives():
    snap_g, _ = _golden()
    snap, sd = _run(_replay_registry(extra=[_broken_plug("flaky_extra")]))
    assert "flaky_extra" in [f["name"] for f in snap.sources_failed]
    assert sorted(snap.sources_ok) == sorted(SOURCE_ORDER)   # the 6 still clean
    assert snap.critical_missing == []                       # flaky isn't critical
    # the Analyst still builds a valid feed from the survivors
    feed = assemble_feed({"as_of": snap_g["as_of"], "snapshot": sd,
                          "theses": snap_g["theses"]}, parabolic=PARABOLIC)
    assert validate_cockpit_feed(feed) == []


def test_e2e_critical_plug_failure_flags_degradation():
    # drop the real uw_price, register a BROKEN uw_price -> critical_missing fires
    snap, _ = _run(_replay_registry(drop=("uw_price",), extra=[_broken_plug("uw_price")]))
    assert "uw_price" in [f["name"] for f in snap.sources_failed]
    assert "uw_price" in snap.critical_missing
