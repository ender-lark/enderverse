#!/usr/bin/env python3
"""
test_uw_opportunity_wiring.py — Strand 3, Chunk 3b: the feed-build WIRING.

Proves the cockpit FULL build now LOADS + PASSES the opportunity-signals cache:
``build_full_feed(..., uw_opportunity=cache)`` threads through ``assemble_feed`` so
fresh bullish flow on a HELD conviction name reaches the lean-in lane as a
direction up-event + a ``UW ▲`` evidence row — exactly the Chunk-2 hook, now fed by
the scout's cache instead of a hand-passed sample.

Golden-safety is the other half: default-None (and an empty / malformed cache) leave
the feed byte-identical, and the golden bundle carries no flow cache — so the golden
master (test_golden_master.py, unchanged) stays drift-free. build_skeleton_feed is
intentionally NOT wired (the fast-view "Dashboard" is book + rotation only).
"""
from __future__ import annotations

import json

from runtime_skeleton import build_full_feed


# ── minimal fixtures (same shape as test_runtime_full.py) ──
def _page(rows):
    head = (
        "<content>\n# 📊 Latest Portfolio\n**As of:** 2026-05-31\n"
        "## Per-Ticker Aggregation (≥\\$500, by MV)\n<table>\n"
        "<tr>\n<td>Ticker</td>\n<td>Shares</td>\n<td>MV</td>\n<td>%</td>\n<td>Owners</td>\n</tr>\n"
    )
    body = "".join(
        f"<tr>\n<td>{t}</td>\n<td>{sh}</td>\n<td>\\${mv}</td>\n<td>{pct}</td>\n<td>{ow}</td>\n</tr>\n"
        for t, sh, mv, pct, ow in rows
    )
    return head + body + "</table>\n</content>\n"


def _series(base, n=70):
    return {"data": [{"c": round(base + i * 0.5, 2), "date": f"d{(n - i):04d}"} for i in range(n)]}


PAGE = _page([
    ("SMH", "285.05", "170,734", "8.88%", "ps"),
    ("NVDA", "596.00", "126,076", "6.56%", "ps"),
])
UW = {"SMH": _series(400), "SPY": _series(650)}
THESES = [
    {"ticker": "NVDA", "tier": "T2", "lane": "Speed", "stance": "ACTIVE",
     "source": "Lee", "factor_tags": ["ai_complex"]},
]
RT = "2026-05-31T16:00:00Z"      # fixes the feed as_of -> 2026-05-31 (deterministic recency)
GEN = "2026-05-31T16:00:00Z"     # fixes generated_at (deterministic byte-compare)

EVIDENCE = "ask-side call sweeps $3.4M, 4:1 c/p"
FRESH_BULL = {
    "as_of": "2026-05-31", "generated_at": "2026-05-31T15:30:00Z", "source": "uw_opportunity_scan",
    "signals": [{"ticker": "NVDA", "signal_type": "sweep", "direction": "bullish",
                 "strength": "strong", "evidence": EVIDENCE, "as_of": "2026-05-31T15:30:00Z"}],
}


def _feed(uw_opportunity=None):
    return build_full_feed(PAGE, UW, THESES, run_timestamp=RT, generated_at=GEN,
                           uw_opportunity=uw_opportunity)


def _lean_row(feed, ticker):
    for row in feed.get("lean_in") or []:
        if row.get("ticker") == ticker:
            return row
    return None


# ════════════════════════════════════════════════════════════════════════════
# 1. The cache THREADS THROUGH to the lean-in lane (end-to-end)
# ════════════════════════════════════════════════════════════════════════════
def test_fresh_flow_reaches_lean_in_lane():
    with_cache = _feed(FRESH_BULL)
    without = _feed(None)

    # the evidence one-liner appears only when the cache is passed
    assert EVIDENCE in json.dumps(with_cache)
    assert EVIDENCE not in json.dumps(without)

    row = _lean_row(with_cache, "NVDA")
    assert row is not None
    assert row["cd"] == "up"                                    # bullish flow -> direction up-event
    assert any("UW" in e for e in row["evidence"])              # the UW ▲ evidence row landed
    # without the cache, NVDA does not surface a UW-driven lean row
    row_without = _lean_row(without, "NVDA")
    assert row_without is None or not any("UW" in e for e in row_without["evidence"])


def test_flow_does_not_change_conviction_quality():
    """Flow moves DIRECTION, never QUALITY — NVDA's conviction read is identical
    with vs without the flow cache (ENDORSEMENT_KINDS gates quality; flow isn't in it)."""
    def cv(feed):
        return next(p["cv"] for h in feed["holdings"] for p in h["pos"] if p["t"] == "NVDA")
    assert cv(_feed(FRESH_BULL)) == cv(_feed(None))


def test_wired_feed_still_validates():
    from validators import validate_cockpit_feed
    assert validate_cockpit_feed(_feed(FRESH_BULL)) == []


# ════════════════════════════════════════════════════════════════════════════
# 2. GOLDEN-SAFE: default / empty / malformed cache leaves the feed byte-identical
# ════════════════════════════════════════════════════════════════════════════
def _norm(feed):
    # the only per-call-volatile field is staleness.entries[].date (a now() on the
    # source freshness, unaffected by the flow cache). Blank it so the parity compare
    # isolates the substantive lanes.
    import copy
    f = copy.deepcopy(feed)
    for row in (f.get("staleness") or {}).get("entries", []):
        if isinstance(row, dict):
            row["date"] = ""
    return json.dumps(f, sort_keys=True)


def test_default_none_is_byte_identical():
    assert _norm(_feed(None)) == _norm(build_full_feed(PAGE, UW, THESES, run_timestamp=RT, generated_at=GEN))


def test_empty_cache_is_inert():
    empty = {"as_of": "2026-05-31", "generated_at": "2026-05-31T15:30:00Z",
             "source": "uw_opportunity_scan", "signals": []}
    with_empty = _feed(empty)
    without = _feed(None)
    assert _lean_row(with_empty, "NVDA") == _lean_row(without, "NVDA")
    rows = {r["key"]: r for r in with_empty["lane_status"]["rows"]}
    assert rows["uw_opportunity"]["status"] == "checked_clear"


def test_malformed_cache_is_tolerant_and_inert():
    # contract violations are skipped by the adapter -> no cards -> feed unchanged, no raise.
    junk = {"signals": [
        {"ticker": "NVDA"},                                         # missing signal_type/direction
        {"signal_type": "sweep", "direction": "bullish"},           # missing ticker
        {"ticker": "NVDA", "signal_type": "nope", "direction": "bullish"},   # bad signal_type
        "not-a-dict",
    ]}
    with_junk = _feed(junk)
    without = _feed(None)
    assert _lean_row(with_junk, "NVDA") == _lean_row(without, "NVDA")
    rows = {r["key"]: r for r in with_junk["lane_status"]["rows"]}
    assert rows["uw_opportunity"]["status"] == "checked_clear"


def test_stale_flow_does_not_fire(monkeypatch=None):
    """A signal older than UW_OPP_FRESH_DAYS produces no direction event (stale flow
    self-expires) — so an old cache can't light up the lane."""
    stale = {
        "as_of": "2026-01-01", "generated_at": "2026-01-01T15:30:00Z", "source": "uw_opportunity_scan",
        "signals": [{"ticker": "NVDA", "signal_type": "sweep", "direction": "bullish",
                     "strength": "strong", "evidence": EVIDENCE, "as_of": "2026-01-01T15:30:00Z"}],
    }
    row = _lean_row(_feed(stale), "NVDA")
    # no fresh direction event -> NVDA either absent from lean_in or carries no UW ▲ row
    assert row is None or not any("UW" in e for e in row["evidence"])
