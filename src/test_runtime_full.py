"""Tests for build_full_feed (runtime_skeleton.py) — the full-feed runtime.

Confirms: parity with build_skeleton_feed when no optional plug is supplied; all
six plugs assemble + validate together; an empty optional plug degrades (no
error); and a Meridian item keeps its real (static, March) date so the cockpit
shows true age.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from runtime_skeleton import (
    build_full_feed,
    build_skeleton_feed,
    SkeletonFeedError,
    update_action_memory_after_publish,
)
from meridian import meridian_reader
from validators import validate_cockpit_feed
from goal_impact import annotate_action

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


def test_source_conflicts_surface_bull_bear_action_posture():
    page = _page([
        ("SMH", "285.05", "170,734", "8.88%", "ps"),
        ("HYPE", "100.00", "50,000", "2.50%", "s"),
    ])
    theses = [
        {"ticker": "HYPE", "tier": "T3", "lane": "Crypto", "stance": "ACTIVE", "source": "operator"},
    ]
    daily = [
        {"author": "Lee", "ticker": "HYPE", "direction": "buy",
         "quote": "HYPE risk appetite improving.", "date": "2026-06-05"},
        {"author": "Farrell", "ticker": "HYPE", "direction": "avoid",
         "quote": "HYPE setup remains fragile.", "date": "2026-06-05"},
    ]

    feed = build_full_feed(page, UW, theses, fs_daily_calls=daily, as_of="2026-06-05")

    assert validate_cockpit_feed(feed) == []
    block = feed["source_conflicts"]
    assert block["count"] == 1
    row = block["rows"][0]
    assert row["ticker"] == "HYPE"
    assert row["scope"] == "same_source"
    assert row["detail"] == "Lee vs Farrell"
    assert "Hold" in row["action_posture"]
    assert "no add" in row["action_posture"]
    assert "not a trade" in row["decision_effect"]
    hype = next(p for h in feed["holdings"] for p in h["pos"] if p["t"] == "HYPE")
    assert hype["conflict"] is True
    assert hype["conflict_detail"] == "Lee vs Farrell"


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


# --------------------------------------------------------------------------- #
# RADAR LANE (block ⑨) — endorsed (daily-call) names NOT owned yet.
# The book holds ITA / HYPE / MU, so those endorsed names are owned (→ excluded);
# JETS / DAL / UAL / PEJ / XHS are NOT in the book (→ surface on the radar).
# --------------------------------------------------------------------------- #
RADAR_PAGE = _page([
    ("SMH", "285.05", "170,734", "8.88%", "ps"),   # held — also the rotation proxy
    ("ITA", "240.00", "50,000", "2.50%", "ps"),     # held → excluded from radar
    ("HYPE", "55.00", "30,000", "1.50%", "s"),      # held → excluded
    ("MU", "120.00", "40,000", "2.00%", "ps"),      # held → excluded
])
RADAR_CALLS = [
    {"author": "Newton", "ticker": "JETS", "direction": "long", "stop": 24.79,
     "target": 34, "window": "2-4wk", "quote": "JETS cleared the base", "date": "2026-06-01"},
    {"author": "Newton", "ticker": "DAL", "direction": "long", "date": "2026-06-01"},
    {"author": "Newton", "ticker": "UAL", "direction": "long", "date": "2026-06-01"},
    {"author": "Newton", "ticker": "PEJ", "direction": "long", "stop": 58, "target": 72, "date": "2026-06-01"},
    {"author": "Newton", "ticker": "XHS", "direction": "long", "stop": 114.63, "target": 147, "date": "2026-06-01"},
    {"author": "Newton", "ticker": "ITA", "direction": "long", "stop": 220, "target": 250, "date": "2026-06-01"},  # held
    {"author": "Farrell", "ticker": "HYPE", "direction": "long", "stop": 59, "date": "2026-06-01"},                # held
    {"author": "Newton", "ticker": "MU", "direction": "long", "date": "2026-06-01"},                              # held
]


def _radar_tickers(feed):
    return [r["ticker"] for r in feed["radar"]]


def test_radar_surfaces_endorsed_not_owned():
    # (a) the non-held endorsed names — and ONLY those — populate the radar; the
    #     book and the Actions strip are unchanged (the names surface ONLY here).
    feed = build_full_feed(RADAR_PAGE, UW, THESES, fs_daily_calls=RADAR_CALLS, as_of="2026-06-01")
    assert set(_radar_tickers(feed)) == {"JETS", "DAL", "UAL", "PEJ", "XHS"}
    assert validate_cockpit_feed(feed) == []

    # each row is the daily-call shape, carrying author + structured levels + quote
    jets = next(r for r in feed["radar"] if r["ticker"] == "JETS")
    assert set(jets) == {"ticker", "author", "direction", "entry", "stop",
                         "target", "window", "date", "quote"}
    assert (jets["author"], jets["direction"], jets["stop"], jets["target"],
            jets["window"], jets["date"]) == ("Newton", "long", 24.79, 34, "2-4wk", "2026-06-01")
    assert jets["quote"] == "JETS cleared the base"

    # the radar names leak into NEITHER holdings NOR Actions (a separate surface),
    # and the Actions strip is byte-identical to the same build without the calls.
    base = build_full_feed(RADAR_PAGE, UW, THESES, as_of="2026-06-01")
    held = {p["t"] for h in feed["holdings"] for p in h["pos"]}
    acted = {a.get("ticker") for a in feed["actions"]}
    assert {"JETS", "DAL", "UAL", "PEJ", "XHS"}.isdisjoint(held | acted)
    assert feed["actions"] == base["actions"]
    assert [h["cat"] for h in feed["holdings"]] == [h["cat"] for h in base["holdings"]]


def test_radar_excludes_owned_names():
    # (b) endorsed names already in the book never show on the radar.
    feed = build_full_feed(RADAR_PAGE, UW, THESES, fs_daily_calls=RADAR_CALLS, as_of="2026-06-01")
    assert {"ITA", "HYPE", "MU"}.isdisjoint(_radar_tickers(feed))


def test_radar_excludes_monitor_stance():
    # (c) a non-held, endorsed name whose thesis is a parked MONITOR sleeve is held
    #     OFF the radar — even though it isn't owned.
    calls = RADAR_CALLS + [{"author": "Newton", "ticker": "ARKB", "direction": "long", "date": "2026-06-01"}]
    monitor = [{"ticker": "ARKB", "tier": "T3", "stance": "MONITOR", "source": "x", "factor_tags": ["crypto"]}]
    feed = build_full_feed(RADAR_PAGE, UW, THESES + monitor, fs_daily_calls=calls, as_of="2026-06-01")
    assert "ARKB" not in _radar_tickers(feed)
    # control: drop the MONITOR thesis and the SAME call surfaces — proving it was
    # the stance, not the holdings rule, that excluded it (ARKB is never owned).
    ctrl = build_full_feed(RADAR_PAGE, UW, THESES, fs_daily_calls=calls, as_of="2026-06-01")
    assert "ARKB" in _radar_tickers(ctrl)


def test_radar_omitted_yields_empty_and_unchanged():
    # (d) no daily calls -> nothing to surface: radar is [], and the block is
    #     purely additive — holdings + actions match the no-radar skeleton exactly.
    full = build_full_feed(PAGE, UW, THESES)
    skel = build_skeleton_feed(PAGE, UW, THESES)
    assert full["radar"] == [] == skel["radar"]
    assert full["holdings"] == skel["holdings"]
    assert full["actions"] == skel["actions"]


def test_radar_explicit_override_threads_through():
    # the kwarg is the additive seam: an explicit radar list is threaded straight
    # into feed["radar"] (no derivation), exactly like heartbeat/synthesis/research.
    rows = [{"ticker": "ZZZ", "author": "X", "direction": "long", "entry": None,
             "stop": None, "target": None, "window": None, "date": "2026-06-01", "quote": "q"}]
    feed = build_full_feed(PAGE, UW, THESES, fs_daily_calls=RADAR_CALLS, radar=rows, as_of="2026-06-01")
    assert feed["radar"] == rows
    assert validate_cockpit_feed(feed) == []


def _publishable_feed_with_action():
    action = annotate_action({
        "rank": 1,
        "kind": "buy_now",
        "ticker": "AVGO",
        "what": "Add AVGO through the sizing gate",
        "confidence": "High",
        "your_move": "Review sizing and execute if gate is clear",
        "gate": None,
        "source": "test",
        "why": "Fresh high-conviction opportunity",
    })
    return {
        "generated_at": "2026-06-04T16:00:00+00:00",
        "staleness": {
            "stamp": "sourced",
            "entries": [
                {"source": "portfolio", "date": "2026-06-04T16:00:00+00:00",
                 "age_days": 0, "stale": False, "flag": ""},
                {"source": "uw_price", "date": "2026-06-04T16:00:00+00:00",
                 "age_days": 0, "stale": False, "flag": ""},
            ],
            "stale": [],
        },
        "hero": {"hero": {"count": 0, "names": [], "leading_sleeves": []},
                 "needs_you": {"count": 0, "items": []}},
        "fresh_signals": [],
        "holdings": [],
        "rotation": [],
        "macro": {"line": "", "regime": {}, "alerts": [], "implications": []},
        "actions": [action],
        "catalysts": [],
        "questions": [],
        "research": {},
    }


def test_action_memory_publish_hook_writes_after_gate_pass(tmp_path):
    store = tmp_path / "open_opportunities.json"
    summary = update_action_memory_after_publish(
        _publishable_feed_with_action(),
        store_path=str(store),
        prices={"AVGO": 1400},
    )
    assert summary["updated"] is True
    assert summary["open_count"] == 1
    assert store.exists()


def test_action_memory_publish_hook_does_not_write_after_gate_fail(tmp_path):
    store = tmp_path / "open_opportunities.json"
    feed = _publishable_feed_with_action()
    feed["generated_at"] = "2026-06-04T10:00:00+00:00"
    summary = update_action_memory_after_publish(feed, store_path=str(store))
    assert summary["updated"] is False
    assert summary["reason"] == "publish_gate_failed"
    assert not store.exists()
