"""Tests for build_full_feed (runtime_skeleton.py) — the full-feed runtime.

Confirms: parity with build_skeleton_feed when no optional plug is supplied; all
six plugs assemble + validate together; an empty optional plug degrades (no
error); and a Meridian item keeps its real (static, March) date so the cockpit
shows true age.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from runtime_skeleton import build_full_feed, build_skeleton_feed, SkeletonFeedError
from meridian import meridian_reader

ROTATION = ["SMH", "SPY"]  # minimal: a proxy + the benchmark


def _page(rows):
    """Minimal Latest-Portfolio markup the runtime adapter parses."""
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
    """A get_ticker_close_prices-shaped response: n gently rising daily closes."""
    return {"data": [{"c": round(base + i * 0.5, 2), "date": f"d{(n - i):04d}"} for i in range(n)]}


PAGE = _page([
    ("SMH", "285.05", "170,734", "8.88%", "ps"),
    ("NVDA", "596.00", "126,076", "6.56%", "ps"),
    ("LEU", "511.00", "93,143", "4.85%", "ps"),
])
UW = {"SMH": _series(400), "SPY": _series(650)}
THESES = [
    {"ticker": "NVDA", "tier": "T2", "lane": "Speed", "stance": "ACTIVE", "source": "Lee", "factor_tags": ["ai_complex"]},
    {"ticker": "LEU", "tier": "T1", "lane": "Generational", "stance": "MONITOR", "source": "Meridian", "factor_tags": ["nuclear"]},
]

MACRO = {"rates": {"2Y": {"value": 3.99, "value_5d_ago": None},
                   "10Y": {"value": 4.45, "value_5d_ago": None}},
         "levels": {"VIX": {"value": 17.2, "value_5d_ago": 15.0}}}
BIBLE = {"deck_date": "2026-05", "macro_stance": "Constructive into year-end",
         "what_to_own": ["Technology", "Financials"],
         "top5": ["NVDA", {"ticker": "GOOGL", "note": "AI"}], "bottom5": ["XYZ"]}
DAILY = [{"author": "Newton", "ticker": "SMH", "direction": "long", "entry": 560,
          "stop": 540, "target": 620, "window": "2-4wk", "quote": "SMH breaking out", "date": "2026-05-30"}]
MERIDIAN = [
    {"subject": "LEU", "item_type": "thesis", "direction": "long",
     "theme": "HALEU monopoly", "quote": "LEU sole US HALEU enricher", "date": "2026-03-05"},
    {"subject": "Project Janus", "item_type": "model", "direction": "long",
     "entry": 10, "target": 20, "date": "2026-03-05"},
]


def test_parity_when_no_optional_plugs():
    full = build_full_feed(PAGE, UW, THESES)
    skel = build_skeleton_feed(PAGE, UW, THESES)
    # identical sleeve groups + position counts (same 2 critical plugs)
    assert [h["cat"] for h in full["holdings"]] == [h["cat"] for h in skel["holdings"]]
    assert sum(len(h["pos"]) for h in full["holdings"]) == sum(len(h["pos"]) for h in skel["holdings"]) == 3


def test_all_six_plugs_assemble_and_validate():
    full = build_full_feed(PAGE, UW, THESES, macro_snapshot=MACRO, fs_bible_deck=BIBLE,
                           fs_daily_calls=DAILY, meridian_items=MERIDIAN)
    skel = build_skeleton_feed(PAGE, UW, THESES)
    # macro section fills in only when the macro plug is present
    assert full["macro"]["line"] and not skel["macro"]["line"]

    # the Fundstrat plugs measurably lift conviction: NVDA (FS Top-5 + a Newton/Lee
    # daily call) reads Strong with the plugs in, and weaker without them.
    def cv(feed, t):
        return next(p["cv"] for h in feed["holdings"] for p in h["pos"] if p["t"] == t)
    assert cv(full, "NVDA") == "Strong"
    assert cv(skel, "NVDA") != "Strong"


def test_empty_optional_plug_degrades_not_errors():
    # empty lists / dict still register but deliver nothing -> no error, no enrichment
    full = build_full_feed(PAGE, UW, THESES, fs_daily_calls=[], meridian_items=[], macro_snapshot={})
    assert sum(len(h["pos"]) for h in full["holdings"]) == 3


def test_meridian_item_keeps_real_static_date():
    # the honesty point: a Meridian card carries its real March date (true age),
    # and a model trade is non-actionable (kind=model_trade), never a fresh buy.
    cards = meridian_reader(MERIDIAN)
    by = {c["subject"]: c for c in cards}
    assert by["LEU"]["timestamp"] == "2026-03-05"
    assert by["Project Janus"]["kind"] == "model_trade"
    assert by["Project Janus"]["data"]["is_model"] is True


def test_missing_prices_degrade_to_no_data_not_abort():
    # DESIGN: uw_price emits a NO-DATA rotation card per proxy when prices are
    # absent, so missing prices do NOT abort — the book still renders with
    # visible NO-DATA rotation rows (honest degradation, not a silent gap).
    full = build_full_feed(PAGE, {}, THESES, macro_snapshot=MACRO)
    assert {r["label"] for r in full["rotation"]} == {"NO DATA"}
    assert sum(len(h["pos"]) for h in full["holdings"]) == 3


def test_missing_portfolio_aborts():
    # the portfolio IS the hard-critical source: no positions -> abort.
    try:
        build_full_feed(_page([]), UW, THESES)
    except (SkeletonFeedError, ValueError):
        pass
    else:
        raise AssertionError("expected an abort when the portfolio delivers no positions")
