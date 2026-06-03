"""Tests for the Stage-5 skeleton wiring (runtime_skeleton.py, S5.3).

Proves the two critical plugs (portfolio + uw_price) alone produce a feed that
passes Contract-C validation, the holdings reflect the parsed positions, and the
critical-missing gate aborts when the book delivers nothing.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from runtime_skeleton import build_skeleton_feed, SkeletonFeedError
from runtime_adapters import UW_ROTATION_TICKERS
from validators import validate_cockpit_feed

HERE = os.path.dirname(os.path.abspath(__file__))


def _theses():
    with open(os.path.join(HERE, "golden_snapshot.json")) as f:
        return json.load(f)["theses"]          # known-good shape (with stance)


def _fake_uw(asc):
    data = [{"c": c, "date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}"}
            for i, c in enumerate(asc)]
    return {"data": list(reversed(data)), "returns": {}, "market_time": "postmarket"}


def _uw_all():
    """70-bar identical series for every rotation ticker -> all IN LINE (enough
    bars to clear the 63-bar lookback; rotation correctness is S5.2's concern)."""
    series = [100 + i * 0.1 for i in range(70)]
    return {t: _fake_uw(series) for t in UW_ROTATION_TICKERS}


PAGE = r"""# 📊 Latest Portfolio
**As of:** 2026-05-27 16:03 ET
## Per-Ticker Aggregation (≥\$500)
<table>
<tr>
<td>Ticker</td>
<td>Shares</td>
<td>MV</td>
<td>% Sleeve</td>
<td>Owners</td>
</tr>
<tr>
<td>---</td>
<td>---:</td>
<td>---:</td>
<td>---:</td>
<td>---</td>
</tr>
<tr>
<td>SMH</td>
<td>313.05</td>
<td>\$186,444</td>
<td>9.90%</td>
<td>p,s</td>
</tr>
<tr>
<td>NVDA</td>
<td>596.00</td>
<td>\$126,675</td>
<td>6.73%</td>
<td>p,s</td>
</tr>
<tr>
<td>LEU</td>
<td>511.00</td>
<td>\$92,102</td>
<td>4.89%</td>
<td>p,s</td>
</tr>
</table>
"""

EMPTY_PAGE = r"""# 📊 Latest Portfolio
## Per-Ticker Aggregation (≥\$500)
<table>
<tr>
<td>Ticker</td>
<td>Shares</td>
<td>MV</td>
<td>% Sleeve</td>
<td>Owners</td>
</tr>
<tr>
<td>---</td>
<td>---:</td>
<td>---:</td>
<td>---:</td>
<td>---</td>
</tr>
</table>
"""


def test_skeleton_feed_validates():
    feed = build_skeleton_feed(PAGE, _uw_all(), _theses(), run_timestamp="2026-05-29T16:00:00")
    assert isinstance(feed, dict)
    assert validate_cockpit_feed(feed) == []
    for k in ("generated_at", "rotation", "holdings", "macro", "hero", "fresh_signals"):
        assert k in feed
    assert len(feed["holdings"]) > 0


def test_holdings_reflect_positions():
    feed = build_skeleton_feed(PAGE, _uw_all(), _theses(), run_timestamp="2026-05-29T16:00:00")
    tickers = {p["t"] for h in feed["holdings"] for p in h["pos"]}
    assert {"SMH", "NVDA", "LEU"} <= tickers


def test_critical_missing_aborts_on_empty_book():
    try:
        build_skeleton_feed(EMPTY_PAGE, _uw_all(), _theses(), run_timestamp="2026-05-29T16:00:00")
        assert False, "expected SkeletonFeedError"
    except SkeletonFeedError as e:
        assert "portfolio" in str(e)


def test_as_of_param_flows_through():
    feed = build_skeleton_feed(PAGE, _uw_all(), _theses(),
                               as_of="2026-05-27", run_timestamp="2026-05-29T16:00:00")
    assert feed.get("generated_at") is not None
