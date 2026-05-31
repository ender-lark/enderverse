"""Full-chain capstone: Sources -> Collection -> assemble_feed -> seam -> view-model.

The ONE end-to-end proof with NO frozen intermediate. It regenerates the feed
from the REAL collect() + REAL assemble_feed() (fixture-replay sources, the same
plugs test_end_to_end.py uses), confirms the live feed equals the frozen oracle,
then hands the LIVE feed across the Python->JS boundary to the REAL seam
(feed_to_cockpit.js) and proves the cockpit view-model is complete and identical
to the golden path.

The React render layer over this exact view-model is proven by the K2 SSR
smoke-test; this capstone proves the data chain that feeds it.

Run:  python full_chain_smoke.py
"""
import dataclasses
import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sources import BaseSource, SourceRegistry
from collection import collect
from feed_assembler import assemble_feed

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


def _live_feed():
    """REAL chain: 6 fixture-replay plugs -> collect() -> assemble_feed()."""
    snap_g, _ = _golden()
    by_src = defaultdict(list)
    for it in snap_g["snapshot"]["items"]:
        by_src[it["source"]].append(it)
    reg = SourceRegistry()
    for s in SOURCE_ORDER:
        reg.register(BaseSource(name=s, fetcher=(lambda r=by_src[s]: [dict(x) for x in r])))
    snap = collect(reg, run_timestamp=RUN_TS)
    return assemble_feed(
        {"as_of": snap_g["as_of"], "snapshot": dataclasses.asdict(snap), "theses": snap_g["theses"]},
        parabolic=PARABOLIC,
    )


def main():
    _, feed_g = _golden()
    live = _live_feed()

    # Py half: the live chain reproduces the oracle (regenerated, not read).
    assert json.loads(json.dumps(live)) == feed_g, \
        "live feed (collect -> assemble_feed) diverged from golden_feed"
    print("\u2713 Py half: collect -> assemble_feed -> live feed == frozen oracle (regenerated, not read)")

    # Hand the LIVE feed across the Python->JS boundary to the real seam.
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
        json.dump(live, tf)
        live_path = tf.name
    try:
        r = subprocess.run(["node", os.path.join(HERE, "full_chain_render.js"), live_path],
                           capture_output=True, text=True)
    finally:
        os.unlink(live_path)
    sys.stdout.write(r.stdout)
    if r.stderr:
        sys.stderr.write(r.stderr)
    if r.returncode != 0:
        print("FULL CHAIN FAILED at the JS half")
        sys.exit(1)

    print("\u2713 FULL CHAIN OK: Sources -> Collection -> assemble_feed -> seam -> "
          "complete view-model (React render layer per K2 SSR smoke-test)")


if __name__ == "__main__":
    main()
